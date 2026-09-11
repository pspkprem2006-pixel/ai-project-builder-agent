"""Blueprint Revision — lightweight version tracking for blueprint changes.

Each revision records a single section change with the source action.
This enables stale-result detection and future rollback/compare features.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


class BlueprintRevision(Base):
    __tablename__ = "blueprint_revisions"

    __table_args__ = (
        Index("ix_blueprint_revisions_project_rev", "project_id", "revision"),
        Index("ix_blueprint_revisions_created", "project_id", "created_at"),
        # At most one revision per project per revision number: concurrent
        # applies cannot both claim the same revision, so the blueprint can
        # never be corrupted by two simultaneous applies.
        Index(
            "uq_blueprint_revisions_project_rev",
            "project_id",
            "revision",
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )

    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    section: Mapped[str] = mapped_column(String(64), nullable=False)
    source_action: Mapped[str] = mapped_column(String(64), nullable=False)
    action_result_id: Mapped[int | None] = mapped_column(nullable=True)

    # JSON snapshot of the section before the change (for diff/rollback)
    previous_section: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Who caused this revision (applied an action, or restored a revision)
    applied_by: Mapped[int | None] = mapped_column(nullable=True)

    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, nullable=False)

    project = relationship("Project")
