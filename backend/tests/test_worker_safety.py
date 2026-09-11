"""Generation worker safety regression tests.

Phase 7 covered the lifecycle; these add the Phase 8 audit findings:
deleted projects cannot leave active jobs, cancelled jobs can never be
resurrected, and job error messages never contain internals.
"""

from datetime import datetime, timedelta

from app.database import SessionLocal
from app.models.generation_job import CANCELLED, FAILED, GenerationJob
from app.models.project import Project
from app.models.user import User
from app.services.generation_jobs import MAX_ATTEMPTS, cancel_job, claim_job, create_job, execute_job
from tests.test_projects import PROJECT_PAYLOAD


def _make_project(db) -> int:
    import uuid

    owner = User(email=f"ws-{uuid.uuid4().hex[:8]}@example.com", hashed_password="x", full_name="W")
    db.add(owner)
    db.commit()
    db.refresh(owner)
    project = Project(user_id=owner.id, name="WorkerSafe", description="d", category="c")
    db.add(project)
    db.commit()
    db.refresh(project)
    return project.id


def test_deleted_project_queued_job_cannot_be_claimed(client, auth_headers, drain_jobs):
    """Deleting a project cascades its jobs: nothing left to claim."""
    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    resp = client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    assert resp.status_code == 202
    job_id = resp.json()["job_id"]
    resp = client.delete(f"/api/v1/projects/{project_id}", headers=auth_headers)
    assert resp.status_code == 204
    with SessionLocal() as db:
        assert db.get(GenerationJob, job_id) is None
        assert claim_job(db, "worker-x") is None


def test_orphaned_job_with_missing_project_fails_safely():
    """A job whose project row vanished (legacy/orphaned) fails, not crashes."""
    with SessionLocal() as db:
        project_id = _make_project(db)
        job_id = create_job(db, project_id).id
        db.delete(db.get(Project, project_id))
        db.commit()

    with SessionLocal() as db:
        claimed = claim_job(db, "worker-y")
        assert claimed == job_id
    outcome = execute_job(job_id, "worker-y")
    assert outcome == "failed"
    with SessionLocal() as db:
        job = db.get(GenerationJob, job_id)
        assert job.status == FAILED
        assert job.error_message == "The project was deleted while the job was queued."


def test_cancelled_job_cannot_be_resurrected_after_lease_expiry():
    """Cancel is terminal: even an expired lease never reclaims a cancelled job."""

    with SessionLocal() as db:
        project_id = _make_project(db)
        job = db.get(GenerationJob, create_job(db, project_id).id)
        cancel_job(db, job)
        # Backdate the lease as if a worker had held it and died.
        job.lease_expires_at = datetime.utcnow() - timedelta(minutes=10)
        job.status = CANCELLED
        db.commit()
        assert claim_job(db, "worker-z") is None


def test_exhausted_failed_job_never_loops():
    """Failed jobs stay terminal: repeated claims find nothing to run."""

    with SessionLocal() as db:
        project_id = _make_project(db)
        job = db.get(GenerationJob, create_job(db, project_id).id)
        # Simulate an exhausted job left running with an expired lease.
        job.attempt_count = MAX_ATTEMPTS
        job.lease_expires_at = datetime.utcnow() - timedelta(minutes=10)
        db.commit()
        assert claim_job(db, "worker-w") is None


def test_job_error_message_is_generic_for_llm_failures(client, auth_headers, drain_jobs, monkeypatch):
    """LLM failures surface as generic text, never provider internals."""
    from app.services.ai import llm as llm_module

    project_id = client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]
    client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)

    def _failing_pipeline(*args, **kwargs):
        raise llm_module.LLMError("LLM request failed")

    monkeypatch.setattr("app.services.generation_jobs.run_pipeline", _failing_pipeline)
    outcomes = drain_jobs()
    assert "failed" in outcomes

    from app.database import SessionLocal

    with SessionLocal() as db:
        from app.models.generation_job import GenerationJob

        job = db.query(GenerationJob).filter(GenerationJob.project_id == project_id).one()
        assert job.status == FAILED
        assert "LLM request failed" in (job.error_message or "")
        assert "api.x.ai" not in (job.error_message or "")
        assert "sk-" not in (job.error_message or "")
