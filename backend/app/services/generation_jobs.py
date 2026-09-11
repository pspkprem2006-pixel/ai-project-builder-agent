"""Durable generation-job lifecycle.

The database is the source of truth. A dedicated worker process claims jobs
with an atomic conditional UPDATE (safe on both SQLite and PostgreSQL), holds
a lease that it refreshes with a heartbeat thread, and updates honest
stage-based progress. Transient failures retry up to a bounded count; stale
jobs (crashed workers) are reclaimed after their lease expires.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.generation_job import (
    ACTIVE_STATUSES,
    CANCELLED,
    COMPLETED,
    FAILED,
    QUEUED,
    RUNNING,
    GenerationJob,
)
from app.models.project import Project
from app.services.ai.agents import run_pipeline
from app.services.ai.llm import LLMError
from app.services.orchestrator import persist_blueprint, project_to_input

logger = logging.getLogger("generation_jobs")

MAX_ATTEMPTS = 3
LEASE_TTL_SECONDS = 60
HEARTBEAT_INTERVAL_SECONDS = 15
CLAIM_INTERVAL_SECONDS = 2

#: Stage weights are honest: the pipeline is the bulk of the work, and a stage
#: only advances when it actually starts. Progress never moves backwards and
#: never reports completion ahead of time.
STAGE_PROGRESS: dict[str, int] = {
    "queued": 0,
    "starting": 5,
    "generating": 60,
    "finalizing": 90,
    "persisting": 95,
    "completed": 100,
    "failed": 100,
}

#: Failures that justify a bounded retry. Anything else (programming errors,
#: malformed input, invalid configuration, deterministic validation failures)
#: is permanent and fails the job immediately.
TRANSIENT_ERRORS: tuple[type[BaseException], ...] = (TimeoutError, ConnectionError, OSError, LLMError)


class JobLeaseLost(Exception):
    """The job is no longer owned by this worker (cancelled or reclaimed)."""


def _utcnow() -> datetime:
    # Naive UTC to match the SQLite/PostgreSQL DateTime columns and the
    # existing Project timestamps (stored values come back naive).
    return datetime.utcnow()


def _safe_error(exc: BaseException) -> str:
    """A truncated, safe error message — no tracebacks, no secrets."""
    return f"{type(exc).__name__}: {exc}"[:500]


def _is_transient(exc: BaseException) -> bool:
    return isinstance(exc, TRANSIENT_ERRORS)


def create_job(db: Session, project_id: int) -> GenerationJob:
    """Create a queued job, or return the existing active job for the project.

    A partial unique index (``uq_generation_jobs_active_project``) makes this
    safe under concurrent duplicate requests on SQLite and PostgreSQL.
    """
    job = GenerationJob(
        project_id=project_id, status=QUEUED, current_stage=QUEUED, progress=0, attempt_count=0
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        active = _active_job(db, project_id)
        if active is not None:
            logger.info(
                "job_duplicate_request job_id=%s project_id=%s status=%s",
                active.id,
                project_id,
                active.status,
            )
            return active
        raise
    db.refresh(job)
    logger.info("job_created job_id=%s project_id=%s status=%s", job.id, project_id, QUEUED)
    return job


def create_action_job(
    db: Session, project_id: int, action_id: str, action_input: dict[str, Any] | None = None
) -> GenerationJob:
    """Create a queued durable action job, or return the active one for it.

    Action jobs ride the same durable worker, lease, retry and cancellation
    machinery as blueprint generation. ``uq_generation_jobs_active_action``
    guarantees at most one active job per (project, action).
    """
    job = GenerationJob(
        project_id=project_id,
        action_id=action_id,
        action_input=json.dumps(action_input or {}),
        status=QUEUED,
        current_stage=QUEUED,
        progress=0,
        attempt_count=0,
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        active = (
            db.query(GenerationJob)
            .filter(
                GenerationJob.project_id == project_id,
                GenerationJob.action_id == action_id,
                GenerationJob.status.in_(ACTIVE_STATUSES),
            )
            .first()
        )
        if active is not None:
            logger.info(
                "action_job_duplicate_request job_id=%s project_id=%s action=%s status=%s",
                active.id,
                project_id,
                action_id,
                active.status,
            )
            return active
        raise
    db.refresh(job)
    logger.info(
        "action_job_created job_id=%s project_id=%s action=%s status=%s",
        job.id,
        project_id,
        action_id,
        QUEUED,
    )
    return job


def _active_job(db: Session, project_id: int) -> GenerationJob | None:
    return (
        db.query(GenerationJob)
        .filter(GenerationJob.project_id == project_id, GenerationJob.status.in_(ACTIVE_STATUSES))
        .first()
    )


def _candidate_job_id(db: Session) -> int | None:
    """Pick the next claimable job: an active queued job, else a stale running job."""
    now = _utcnow()
    return (
        db.query(GenerationJob.id)
        .filter(
            or_(
                GenerationJob.status == QUEUED,
                and_(GenerationJob.status == RUNNING, GenerationJob.lease_expires_at < now),
            )
        )
        .order_by(GenerationJob.id)
        .limit(1)
        .scalar()
    )


def claim_job(db: Session, worker_id: str) -> int | None:
    """Atomically claim one job; returns its id or None.

    The conditional UPDATE is the atomic gate: exactly one worker wins even
    when several race on the same candidate (single-statement transition on
    SQLite and PostgreSQL; no SELECT-then-UPDATE race window).
    """
    now = _utcnow()
    candidate = _candidate_job_id(db)
    if candidate is None:
        return None

    job = db.get(GenerationJob, candidate)
    if job is None:
        return None

    if job.status == QUEUED:
        if job.attempt_count >= MAX_ATTEMPTS:
            _fail_job(
                db,
                job,
                db.get(Project, job.project_id),
                f"Generation was lost after {job.attempt_count} attempts.",
            )
            return None
        result = db.execute(
            update(GenerationJob)
            .where(GenerationJob.id == candidate, GenerationJob.status == QUEUED)
            .values(
                status=RUNNING,
                lease_owner=worker_id,
                lease_expires_at=now + timedelta(seconds=LEASE_TTL_SECONDS),
                started_at=now,
                attempt_count=job.attempt_count + 1,
                current_stage="starting",
                progress=STAGE_PROGRESS["starting"],
            )
        )
        kind = "queued"
    else:
        # Stale running job: the previous worker died without a heartbeat.
        if job.attempt_count >= MAX_ATTEMPTS:
            _fail_job(
                db,
                job,
                db.get(Project, job.project_id),
                f"Generation was lost after {job.attempt_count} attempts.",
            )
            return None
        result = db.execute(
            update(GenerationJob)
            .where(
                GenerationJob.id == candidate,
                GenerationJob.status == RUNNING,
                GenerationJob.lease_expires_at < now,
            )
            .values(
                status=RUNNING,
                lease_owner=worker_id,
                lease_expires_at=now + timedelta(seconds=LEASE_TTL_SECONDS),
                started_at=now,
                attempt_count=job.attempt_count + 1,
                current_stage="starting",
                progress=STAGE_PROGRESS["starting"],
                error_message=f"Recovered after stale lease (attempt {job.attempt_count + 1})",
            )
        )
        kind = "stale"

    if result.rowcount == 1:
        db.commit()
        logger.info(
            "job_claimed job_id=%s project_id=%s worker=%s attempt=%s kind=%s",
            candidate,
            job.project_id,
            worker_id,
            job.attempt_count + 1,
            kind,
        )
        return candidate
    db.rollback()
    return None


def _set_stage(db: Session, job: GenerationJob, stage: str, worker_id: str) -> None:
    """Advance the job's stage/progress and refresh its lease.

    Uses a conditional UPDATE so a cancelled or reclaimed job aborts the
    attempt (the worker then stops without persisting anything).
    """
    now = _utcnow()
    result = db.execute(
        update(GenerationJob)
        .where(
            GenerationJob.id == job.id,
            GenerationJob.status == RUNNING,
            GenerationJob.lease_owner == worker_id,
        )
        .values(
            current_stage=stage,
            progress=STAGE_PROGRESS.get(stage, job.progress),
            lease_expires_at=now + timedelta(seconds=LEASE_TTL_SECONDS),
        )
    )
    if result.rowcount != 1:
        raise JobLeaseLost(f"Job {job.id} is no longer owned by worker {worker_id}")
    db.commit()
    logger.info(
        "job_stage_changed job_id=%s project_id=%s stage=%s progress=%s",
        job.id,
        job.project_id,
        stage,
        STAGE_PROGRESS.get(stage),
    )


def heartbeat(worker_id: str, job_id: int) -> bool:
    """Refresh the job lease; returns False when the worker lost ownership."""
    now = _utcnow()
    with SessionLocal() as db:
        result = db.execute(
            update(GenerationJob)
            .where(GenerationJob.id == job_id, GenerationJob.lease_owner == worker_id)
            .values(lease_expires_at=now + timedelta(seconds=LEASE_TTL_SECONDS))
        )
        db.commit()
        return result.rowcount == 1


def _heartbeat_loop(worker_id: str, job_id: int, stop_event: threading.Event) -> None:
    while not stop_event.wait(HEARTBEAT_INTERVAL_SECONDS):
        if not heartbeat(worker_id, job_id):
            return


def _retry_job(db: Session, job: GenerationJob, message: str) -> None:
    result = db.execute(
        update(GenerationJob)
        .where(GenerationJob.id == job.id, GenerationJob.status == RUNNING)
        .values(status=QUEUED, current_stage=QUEUED, progress=0, error_message=message)
    )
    if result.rowcount == 1:
        db.commit()
        logger.info(
            "job_retry_scheduled job_id=%s project_id=%s attempt=%s max_attempts=%s reason=%s",
            job.id,
            job.project_id,
            job.attempt_count,
            MAX_ATTEMPTS,
            message,
        )
    else:
        db.rollback()


def _fail_job(db: Session, job: GenerationJob, project: Project | None, message: str) -> None:
    result = db.execute(
        update(GenerationJob)
        .where(GenerationJob.id == job.id, GenerationJob.status.in_(ACTIVE_STATUSES))
        .values(
            status=FAILED,
            current_stage="failed",
            progress=STAGE_PROGRESS["failed"],
            error_message=message,
            completed_at=_utcnow(),
        )
    )
    if result.rowcount == 1:
        if project is not None and project.status == "processing":
            project.status = "failed"
            project.generation_error = message
        db.commit()
        logger.error(
            "job_failed job_id=%s project_id=%s attempt=%s reason=%s",
            job.id,
            job.project_id,
            job.attempt_count,
            message,
        )
    else:
        db.rollback()


def _complete_job(db: Session, job: GenerationJob) -> None:
    result = db.execute(
        update(GenerationJob)
        .where(GenerationJob.id == job.id, GenerationJob.status == RUNNING)
        .values(
            status=COMPLETED,
            current_stage="completed",
            progress=100,
            completed_at=_utcnow(),
            error_message=None,
        )
    )
    if result.rowcount == 1:
        db.commit()
        logger.info(
            "job_completed job_id=%s project_id=%s attempts=%s",
            job.id,
            job.project_id,
            job.attempt_count,
        )
    else:
        db.rollback()
        raise JobLeaseLost(f"Job {job.id} was not running; cannot complete it")


def execute_job(job_id: int, worker_id: str) -> str:
    """Run a claimed job to completion, retry or failure. Returns the outcome."""
    with SessionLocal() as db:
        job = db.get(GenerationJob, job_id)
        if job is None or job.status != RUNNING or job.lease_owner != worker_id:
            return "skipped"

        project = db.get(Project, job.project_id)
        if project is None:
            _fail_job(db, job, None, "The project was deleted while the job was queued.")
            return "failed"

        project.status = "processing"
        project.generation_error = None
        db.commit()
        logger.info(
            "job_started job_id=%s project_id=%s worker=%s attempt=%s",
            job.id,
            job.project_id,
            worker_id,
            job.attempt_count,
        )

        stop_heartbeat = threading.Event()
        heartbeat_thread = threading.Thread(
            target=_heartbeat_loop,
            args=(worker_id, job_id, stop_heartbeat),
            daemon=True,
            name=f"heartbeat-{job_id}",
        )
        heartbeat_thread.start()
        try:
            _set_stage(db, job, "generating", worker_id)
            if job.action_id is not None:
                outcome = _run_action_job(db, job, project)
                return outcome
            try:
                blueprint, provider = run_pipeline(project_to_input(project))
            except Exception as exc:  # noqa: BLE001 - classification decides retry vs fail
                retried = _handle_pipeline_failure(db, job, project, exc)
                return "retry_scheduled" if retried else "failed"

            _set_stage(db, job, "finalizing", worker_id)
            persist_blueprint(db, project, blueprint, provider)
            _set_stage(db, job, "persisting", worker_id)
            _complete_job(db, job)
            return "completed"
        except JobLeaseLost:
            return "cancelled"
        finally:
            stop_heartbeat.set()
            heartbeat_thread.join(timeout=2)


def _run_action_job(db: Session, job: GenerationJob, project: Project) -> str:
    """Run a durable AI action job through the central action executor.

    Handlers classify every failure themselves (LLM errors fall back to the
    deterministic engine); only a completed action finishes the job. Results
    are persisted to the action history so durable executions are as
    traceable as synchronous ones.
    """
    from app.services.action_results import create_action_result, get_current_blueprint_revision
    from app.services.actions.executor import execute_action

    action_input = {}
    if job.action_input:
        try:
            action_input = json.loads(job.action_input)
        except (TypeError, ValueError):
            action_input = {}
    result = execute_action(job.action_id or "", project, action_input, db)
    if result.status in ("success", "fallback"):
        revision = get_current_blueprint_revision(db, project.id)
        create_action_result(
            db=db,
            project=project,
            action_id=job.action_id or "",
            status=result.status,
            input_data=action_input,
            result_data=result.result,
            section=result.section,
            warnings=result.warnings,
            provider=result.provider,
            blueprint_revision=revision,
            artifact_available=result.artifact is not None,
        )
        _set_stage(db, job, "finalizing", worker_id=job.lease_owner or "")
        _complete_job(db, job)
        return "completed"
    _fail_job(db, job, project, result.message or f"Action '{job.action_id}' failed.")
    return "failed"


def _handle_pipeline_failure(db: Session, job: GenerationJob, project: Project, exc: BaseException) -> bool:
    """Classify a pipeline failure; returns True when a retry was scheduled."""
    message = _safe_error(exc)
    if _is_transient(exc) and job.attempt_count < MAX_ATTEMPTS:
        _retry_job(db, job, message)
        return True
    _fail_job(db, job, project, message)
    return False


def recover_stale_jobs(db: Session) -> None:
    """Startup/loop recovery: fix project rows stuck in 'processing'.

    A project stuck in processing with no active job means the process died
    before the durable job era (or an old job was hard-deleted); reset it to
    draft so the user can regenerate.
    """
    stuck_project_ids = [
        row[0]
        for row in db.query(Project.id)
        .filter(Project.status == "processing")
        .all()
        if _active_job(db, row[0]) is None
    ]
    for project_id in stuck_project_ids:
        project = db.get(Project, project_id)
        if project is not None:
            project.status = "draft"
            project.generation_error = None
            logger.info("job_recovered project_id=%s status=processing->draft no_active_job", project_id)
    if stuck_project_ids:
        db.commit()


def cancel_job(db: Session, job: GenerationJob) -> bool:
    """Cancel a queued or running job. Returns True when the transition applied."""
    now = _utcnow()
    result = db.execute(
        update(GenerationJob)
        .where(GenerationJob.id == job.id, GenerationJob.status.in_(ACTIVE_STATUSES))
        .values(
            status=CANCELLED,
            current_stage="cancelled",
            error_message="Cancelled by user",
            completed_at=now,
        )
    )
    if result.rowcount == 1:
        project = db.get(Project, job.project_id)
        if project is not None and project.status == "processing":
            project.status = "draft"
            project.generation_error = None
        db.commit()
        logger.info("job_cancelled job_id=%s project_id=%s", job.id, job.project_id)
        return True
    db.rollback()
    return False


def job_to_dict(job: GenerationJob) -> dict[str, Any]:
    return {
        "id": job.id,
        "project_id": job.project_id,
        "status": job.status,
        "current_stage": job.current_stage,
        "progress": job.progress,
        "attempt_count": job.attempt_count,
        "error_message": job.error_message,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
    }
