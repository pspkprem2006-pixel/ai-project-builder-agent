"""Durable AI generation job.

The database is the source of truth for generation state. A dedicated worker
process claims jobs, runs the (unchanged) LangGraph pipeline, and persists
progress, leases and the final blueprint. If the worker or backend dies, the
job survives and is reclaimed after its lease expires.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

QUEUED = "queued"
RUNNING = "running"
COMPLETED = "completed"
FAILED = "failed"
CANCELLED = "cancelled"

JOB_STATUSES = (QUEUED, RUNNING, COMPLETED, FAILED, CANCELLED)

ACTIVE_STATUSES = (QUEUED, RUNNING)


class GenerationJob(Base):
    __tablename__ = "generation_jobs"

    # At most one active (queued/running) generation per project: duplicate
    # requests cannot create a second pipeline. Works on SQLite and PostgreSQL.
    __table_args__ = (
        Index(
            "uq_generation_jobs_active_project",
            "project_id",
            unique=True,
            sqlite_where=text("status IN ('queued', 'running')"),
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
        # Action jobs: at most one active job per (project, action). Blueprint
        # jobs (action_id NULL) are governed by the index above.
        Index(
            "uq_generation_jobs_active_action",
            "project_id",
            "action_id",
            unique=True,
            sqlite_where=text("status IN ('queued', 'running') AND action_id IS NOT NULL"),
            postgresql_where=text("status IN ('queued', 'running') AND action_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )

    # Optional AI Action Engine dispatch: when set, this job runs a blueprint
    # action instead of the full generation pipeline.
    action_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    action_input: Mapped[str | None] = mapped_column(Text, nullable=True)

    status: Mapped[str] = mapped_column(String(20), default=QUEUED, nullable=False, index=True)
    current_stage: Mapped[str] = mapped_column(String(60), default=QUEUED, nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Lease: the worker identity that currently holds the job and when its
    # heartbeat expires. A running job whose lease has expired is stale and
    # eligible for reclaim by another worker.
    lease_owner: Mapped[str | None] = mapped_column(String(64), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    project = relationship("Project")
