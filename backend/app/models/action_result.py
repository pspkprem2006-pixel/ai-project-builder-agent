"""Action Result — persistent storage for AI action executions.

Stores the result of every action execution so users can review, apply, or
re-run. Results belong to a project and inherit project ownership.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class ActionResult(Base):
    __tablename__ = "action_results"

    __table_args__ = (
        Index("ix_action_results_project_created", "project_id", "created_at"),
        Index("ix_action_results_action_created", "action_id", "created_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    action_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    status: Mapped[str] = mapped_column(String(20), nullable=False)
    input: Mapped[str | None] = mapped_column(Text, nullable=True)
    result: Mapped[str | None] = mapped_column(Text, nullable=True)
    section: Mapped[str | None] = mapped_column(String(64), nullable=True)
    warnings: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider: Mapped[str | None] = mapped_column(String(32), nullable=True)
    blueprint_revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Quality classification: valid | invalid | partial
    quality: Mapped[str | None] = mapped_column(String(16), nullable=True)
    completeness: Mapped[int | None] = mapped_column(Integer, nullable=True)
    consistency_status: Mapped[str | None] = mapped_column(String(16), nullable=True)

    # Whether the action produced a downloadable artifact (CI/CD, test scaffold)
    artifact_available: Mapped[bool] = mapped_column(default=False, nullable=False)

    applied: Mapped[bool] = mapped_column(default=False, nullable=False)
    applied_at: Mapped[datetime | None] = mapped_column(nullable=True)
    applied_by: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)

    project = relationship("Project")
    applied_by_user = relationship("User", foreign_keys=[applied_by])
