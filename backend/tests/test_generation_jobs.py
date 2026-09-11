"""Phase 7 — durable generation jobs.

Covers the database-backed job lifecycle: creation, atomic claiming,
concurrent workers, lease/heartbeat stale recovery, bounded retries, retry
exhaustion, duplicate requests, cancellation, worker-restart recovery and
blueprint persistence — all against the real (in-memory SQLite) database.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta

import pytest
from sqlalchemy import text
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from app.database import SessionLocal, engine
from app.models.generation_job import (
    CANCELLED,
    COMPLETED,
    FAILED,
    QUEUED,
    RUNNING,
    GenerationJob,
)
from app.models.project import Project
from app.models.user import User
from app.services import generation_jobs as jobs
from app.services.ai.agents import run_pipeline
from app.services.generation_jobs import (
    MAX_ATTEMPTS,
    cancel_job,
    claim_job,
    create_job,
    execute_job,
    heartbeat,
    recover_stale_jobs,
)
from tests.test_projects import PROJECT_PAYLOAD


@pytest.fixture()
def project_id(client, auth_headers):
    return client.post("/api/v1/projects", json=PROJECT_PAYLOAD, headers=auth_headers).json()["id"]


def _drain_all_queued():
    """Execute every queued job so later claim tests see a clean queue."""
    with SessionLocal() as db:
        while True:
            job_id = claim_job(db, "test-drainer")
            if job_id is None:
                break
            execute_job(job_id, "test-drainer")


@pytest.fixture()
def job_id(client, auth_headers, project_id):
    _drain_all_queued()
    resp = client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    assert resp.status_code == 202
    return resp.json()["job_id"]


def _get_job(job_id):
    with SessionLocal() as db:
        return db.get(GenerationJob, job_id)


def _get_project(project_id):
    with SessionLocal() as db:
        return db.get(Project, project_id)


def _expire_lease(job_id):
    """Backdate a claimed job's lease so it never lingers claimable.

    Claim-only tests must not leave RUNNING jobs behind: a later claim in the
    suite would pick them up once their 60s lease expires, polluting global
    claim assertions. Expiring the lease makes the next drain consume them.
    """
    with SessionLocal() as db:
        db.execute(
            jobs.update(GenerationJob)
            .where(GenerationJob.id == job_id)
            .values(lease_expires_at=datetime.utcnow() - timedelta(seconds=1))
        )
        db.commit()


# ---------------------------------------------------------------------------
# 1-2. Job creation / queued state
# ---------------------------------------------------------------------------


def test_generate_creates_queued_job(client, auth_headers, project_id, job_id):
    job = _get_job(job_id)
    assert job.status == QUEUED
    assert job.current_stage == QUEUED
    assert job.progress == 0
    assert job.attempt_count == 0
    assert job.project_id == project_id
    assert job.created_at is not None
    project = _get_project(project_id)
    assert project.status == "draft"  # HTTP layer must not touch project state


def test_jobs_list_and_detail_endpoints(client, auth_headers, project_id, job_id):
    resp = client.get(f"/api/v1/projects/{project_id}/jobs", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["id"] == job_id
    assert body[0]["status"] == QUEUED

    resp = client.get(f"/api/v1/projects/{project_id}/jobs/{job_id}", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["project_id"] == project_id

    other = client.post(
        "/api/v1/auth/register",
        json={"email": "phase7-intruder@example.com", "password": "password123", "full_name": "I"},
    )
    other_headers = {"Authorization": f"Bearer {other.json()['access_token']}"}
    assert client.get(f"/api/v1/projects/{project_id}/jobs/{job_id}", headers=other_headers).status_code == 404


# ---------------------------------------------------------------------------
# 3. Worker claim
# ---------------------------------------------------------------------------


def test_worker_claims_queued_job(job_id):
    claimed = claim_job(SessionLocal(), "worker-a")
    assert claimed == job_id
    job = _get_job(job_id)
    assert job.status == RUNNING
    assert job.lease_owner == "worker-a"
    assert job.attempt_count == 1
    assert job.started_at is not None
    assert job.lease_expires_at > datetime.utcnow()
    _expire_lease(job_id)


# ---------------------------------------------------------------------------
# 4. Concurrent claim — exactly one worker wins
# ---------------------------------------------------------------------------


def test_concurrent_claim_only_one_worker_wins(job_id):
    first = claim_job(SessionLocal(), "worker-a")
    second = claim_job(SessionLocal(), "worker-b")
    assert first == job_id
    assert second is None
    job = _get_job(job_id)
    assert job.lease_owner == "worker-a"
    _expire_lease(job_id)


def test_two_workers_race_on_same_candidate():
    _drain_all_queued()
    with SessionLocal() as db:
        owner = User(email="race-owner@example.com", hashed_password="x", full_name="O")
        db.add(owner)
        db.commit()
        db.refresh(owner)
        project = Project(user_id=owner.id, name="Race", description="d", category="c")
        db.add(project)
        db.commit()
        db.refresh(project)
        job_a = create_job(db, project.id)
        job_b = create_job(db, project.id)  # duplicate -> returns same active job
        assert job_a.id == job_b.id
        pid = project.id

    claimed = [claim_job(SessionLocal(), f"worker-{i}") for i in range(4)]
    winners = [c for c in claimed if c is not None]
    assert len(winners) == 1
    with SessionLocal() as db:
        job = db.get(GenerationJob, winners[0])
        assert job.status == RUNNING
        # only one active job was ever created
        assert db.query(GenerationJob).filter(GenerationJob.project_id == pid).count() == 1
    _expire_lease(winners[0])


# ---------------------------------------------------------------------------
# 5-6. Running state, progress/stage updates
# ---------------------------------------------------------------------------


def test_claim_sets_running_state_and_start_stage(job_id):
    claim_job(SessionLocal(), "worker-a")
    job = _get_job(job_id)
    assert job.status == RUNNING
    assert job.current_stage == "starting"
    assert job.progress == jobs.STAGE_PROGRESS["starting"] == 5
    _expire_lease(job_id)


def test_stage_updates_are_persisted_during_execution(job_id, monkeypatch):
    observed: list[tuple[str, int]] = []
    real_pipeline = run_pipeline

    def slow_pipeline(input_data):
        with SessionLocal() as db:
            j = db.get(GenerationJob, job_id)
            observed.append((j.current_stage, j.progress))
        return real_pipeline(input_data)

    monkeypatch.setattr("app.services.generation_jobs.run_pipeline", slow_pipeline)
    claim_job(SessionLocal(), "worker-a")
    assert execute_job(job_id, "worker-a") == "completed"
    assert observed  # stage was visible mid-pipeline
    job = _get_job(job_id)
    assert job.current_stage == "completed"
    assert job.progress == 100


# ---------------------------------------------------------------------------
# 7. Successful completion + blueprint persistence
# ---------------------------------------------------------------------------


def test_successful_completion_persists_blueprint(client, auth_headers, project_id, job_id):
    assert claim_job(SessionLocal(), "worker-a") == job_id
    assert execute_job(job_id, "worker-a") == "completed"

    job = _get_job(job_id)
    assert job.status == COMPLETED
    assert job.completed_at is not None
    assert job.error_message is None

    project = _get_project(project_id)
    assert project.status == "complete"
    assert project.blueprint is not None
    assert project.blueprint["metadata"]["version"] == "3.0"
    assert project.last_generated_at is not None

    # frontend polling sees the durable job state
    resp = client.get(f"/api/v1/projects/{project_id}/jobs/{job_id}", headers=auth_headers)
    assert resp.json()["status"] == COMPLETED
    assert resp.json()["progress"] == 100


# ---------------------------------------------------------------------------
# 8. Failure — permanent error fails immediately
# ---------------------------------------------------------------------------


def test_permanent_failure_fails_job(job_id, monkeypatch):
    def boom(_input):
        raise ValueError("malformed blueprint data")

    monkeypatch.setattr("app.services.generation_jobs.run_pipeline", boom)
    claim_job(SessionLocal(), "worker-a")
    assert execute_job(job_id, "worker-a") == "failed"
    job = _get_job(job_id)
    assert job.status == FAILED
    assert "ValueError" in job.error_message
    assert job.current_stage == "failed"
    project = _get_project(job.project_id)
    assert project.status == "failed"
    assert project.generation_error == job.error_message
    assert not project.blueprint


# ---------------------------------------------------------------------------
# 9-10. Bounded retry + exhaustion
# ---------------------------------------------------------------------------


def test_transient_failure_schedules_bounded_retry(job_id, monkeypatch):
    def timeout(_input):
        raise TimeoutError("llm timed out")

    monkeypatch.setattr("app.services.generation_jobs.run_pipeline", timeout)
    assert claim_job(SessionLocal(), "worker-a") == job_id
    assert execute_job(job_id, "worker-a") == "retry_scheduled"
    job = _get_job(job_id)
    assert job.status == QUEUED
    assert job.attempt_count == 1
    assert "TimeoutError" in job.error_message
    project = _get_project(job.project_id)
    assert project.status == "processing"


def test_retry_exhaustion_marks_failed(job_id, monkeypatch):
    def timeout(_input):
        raise TimeoutError("llm timed out")

    monkeypatch.setattr("app.services.generation_jobs.run_pipeline", timeout)
    outcomes = []
    for _ in range(MAX_ATTEMPTS):
        with SessionLocal() as db:
            claimed = claim_job(db, "worker-a")
        assert claimed == job_id
        outcomes.append(execute_job(job_id, "worker-a"))

    assert outcomes == ["retry_scheduled", "retry_scheduled", "failed"]
    job = _get_job(job_id)
    assert job.status == FAILED
    assert job.attempt_count == MAX_ATTEMPTS
    assert "llm timed out" in job.error_message
    project = _get_project(job.project_id)
    assert project.status == "failed"

    # no further attempt after exhaustion
    with SessionLocal() as db:
        assert claim_job(db, "worker-a") is None


def test_stale_job_after_exhaustion_fails_not_retries(job_id, monkeypatch):
    """A job that crashed MAX_ATTEMPTS times must never be reclaimed."""
    with SessionLocal() as db:
        db.execute(
            jobs.update(GenerationJob)
            .where(GenerationJob.id == job_id)
            .values(status=RUNNING, attempt_count=MAX_ATTEMPTS, lease_expires_at=datetime.utcnow() - timedelta(minutes=5))
        )
        db.commit()
    with SessionLocal() as db:
        assert claim_job(db, "worker-a") is None
    job = _get_job(job_id)
    assert job.status == FAILED


# ---------------------------------------------------------------------------
# 11. Stale-job recovery (lease expiry)
# ---------------------------------------------------------------------------


def test_stale_running_job_is_reclaimed(job_id, monkeypatch):
    # claim as worker-a (attempt 1)
    with SessionLocal() as db:
        claim_job(db, "worker-a")
    # worker-a dies: no heartbeat; lease expires
    with SessionLocal() as db:
        db.execute(
            jobs.update(GenerationJob)
            .where(GenerationJob.id == job_id)
            .values(lease_expires_at=datetime.utcnow() - timedelta(minutes=5))
        )
        db.commit()
    # worker-b reclaims the stale job
    with SessionLocal() as db:
        assert claim_job(db, "worker-b") == job_id
    job = _get_job(job_id)
    assert job.status == RUNNING
    assert job.attempt_count == 2
    assert job.lease_owner == "worker-b"
    assert "Recovered after stale lease" in job.error_message
    _expire_lease(job_id)


def test_heartbeat_refreshes_lease(job_id):
    with SessionLocal() as db:
        claim_job(db, "worker-a")
    assert heartbeat("worker-a", job_id) is True
    job = _get_job(job_id)
    assert job.lease_expires_at > datetime.utcnow()
    assert heartbeat("worker-b", job_id) is False  # wrong owner cannot refresh
    _expire_lease(job_id)


def test_recover_stale_jobs_resets_legacy_stuck_projects(client, auth_headers, project_id):
    # a project stuck in 'processing' with no active job (pre-durable era)
    with SessionLocal() as db:
        project = db.get(Project, project_id)
        project.status = "processing"
        db.commit()
    with SessionLocal() as db:
        recover_stale_jobs(db)
    assert _get_project(project_id).status == "draft"


# ---------------------------------------------------------------------------
# 12. Duplicate generation request
# ---------------------------------------------------------------------------


def test_duplicate_generate_returns_same_job(client, auth_headers, project_id, job_id):
    resp = client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    assert resp.status_code == 202
    assert resp.json()["job_id"] == job_id
    with SessionLocal() as db:
        assert db.query(GenerationJob).filter(GenerationJob.project_id == project_id).count() == 1


def test_duplicate_generate_while_running_returns_active_job(client, auth_headers, project_id, job_id):
    claim_job(SessionLocal(), "worker-a")
    resp = client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    assert resp.status_code == 202
    assert resp.json()["job_id"] == job_id
    assert resp.json()["status"] == RUNNING


def test_regenerate_after_completion_creates_new_job(client, auth_headers, project_id, drain_jobs):
    resp = client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    first_job = resp.json()["job_id"]
    drain_jobs()
    resp = client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    second_job = resp.json()["job_id"]
    assert second_job != first_job
    with SessionLocal() as db:
        assert db.query(GenerationJob).filter(GenerationJob.project_id == project_id).count() == 2


# ---------------------------------------------------------------------------
# Cancellation
# ---------------------------------------------------------------------------


def test_cancel_queued_job(client, auth_headers, project_id, job_id):
    resp = client.post(f"/api/v1/projects/{project_id}/jobs/{job_id}/cancel", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == CANCELLED
    job = _get_job(job_id)
    assert job.status == CANCELLED
    with SessionLocal() as db:
        assert claim_job(db, "worker-a") is None  # cancelled jobs are not claimable


def test_cancel_does_not_affect_terminal_job(client, auth_headers, project_id, drain_jobs):
    job_id_ = client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers).json()["job_id"]
    drain_jobs()
    resp = client.post(f"/api/v1/projects/{project_id}/jobs/{job_id_}/cancel", headers=auth_headers)
    assert resp.json()["status"] == COMPLETED


# ---------------------------------------------------------------------------
# 13. Worker restart recovery — full lifecycle integration
# ---------------------------------------------------------------------------


def test_worker_restart_recovery_full_lifecycle(client, auth_headers, project_id):
    """create -> claim(worker A) -> A dies -> stale -> claim(worker B) -> complete."""
    resp = client.post(f"/api/v1/projects/{project_id}/generate", headers=auth_headers)
    job_id_ = resp.json()["job_id"]

    with SessionLocal() as db:
        assert claim_job(db, "worker-a") == job_id_
    job = _get_job(job_id_)
    assert job.status == RUNNING
    assert job.attempt_count == 1

    # worker A crashes mid-run: no heartbeat ever fires, lease expires
    with SessionLocal() as db:
        db.execute(
            jobs.update(GenerationJob)
            .where(GenerationJob.id == job_id_)
            .values(lease_expires_at=datetime.utcnow() - timedelta(seconds=1))
        )
        db.commit()

    # replacement worker detects the stale job and retries it
    with SessionLocal() as db:
        assert claim_job(db, "worker-b") == job_id_
    assert _get_job(job_id_).attempt_count == 2

    assert execute_job(job_id_, "worker-b") == "completed"

    job = _get_job(job_id_)
    assert job.status == COMPLETED
    assert job.completed_at is not None
    project = _get_project(project_id)
    assert project.status == "complete"
    assert project.blueprint is not None
    assert project.blueprint["metadata"]["version"] == "3.0"
    assert project.blueprint["project"]["name"] == "Hospital Management System"

    # the frontend sees a finished job
    resp = client.get(f"/api/v1/projects/{project_id}/jobs/{job_id_}", headers=auth_headers)
    assert resp.json()["status"] == COMPLETED
    assert resp.json()["progress"] == 100


# ---------------------------------------------------------------------------
# 16. SQLite compatibility + PostgreSQL index DDL
# ---------------------------------------------------------------------------


def test_partial_unique_index_ddl_compiles_for_postgresql():
    index = next(i for i in GenerationJob.__table__.indexes if i.name == "uq_generation_jobs_active_project")
    ddl = str(CreateIndex(index).compile(dialect=postgresql.dialect()))
    assert "generation_jobs" in ddl
    upper = ddl.upper()
    assert "UNIQUE INDEX" in upper
    assert "WHERE STATUS IN" in upper
    assert "'QUEUED'" in upper and "'RUNNING'" in upper


def test_sqlite_schema_creates_generation_jobs_table():
    with engine.connect() as conn:
        rows = conn.execute(
            text("SELECT name FROM sqlite_master WHERE type='table' AND name='generation_jobs'")
        ).fetchall()
    assert rows


# ---------------------------------------------------------------------------
# Cancel races and lease-loss behaviour
# ---------------------------------------------------------------------------


def test_cancelled_while_running_stops_persistence(job_id, monkeypatch):
    real_pipeline = run_pipeline
    cancelled_at_stage = threading.Event()

    def slow_pipeline(input_data):
        cancelled_at_stage.set()
        # simulate the worker being blocked while the user cancels
        with SessionLocal() as db:
            cancel_job(db, db.get(GenerationJob, job_id))
        return real_pipeline(input_data)

    monkeypatch.setattr("app.services.generation_jobs.run_pipeline", slow_pipeline)
    with SessionLocal() as db:
        assert claim_job(db, "worker-a") == job_id
    assert execute_job(job_id, "worker-a") == "cancelled"
    job = _get_job(job_id)
    assert job.status == CANCELLED
    project = _get_project(job.project_id)
    assert project.blueprint is None  # nothing persisted after cancellation
    assert project.status == "draft"
