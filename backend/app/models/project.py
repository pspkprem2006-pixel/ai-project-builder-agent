from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base

PROJECT_STATUSES = ("draft", "processing", "complete", "failed")


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)

    # --- Wizard input -------------------------------------------------
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="General", nullable=False)
    target_users: Mapped[str] = mapped_column(Text, default="", nullable=False)
    features: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
    preferred_frontend: Mapped[str] = mapped_column(String(80), default="React", nullable=False)
    preferred_backend: Mapped[str] = mapped_column(String(80), default="FastAPI", nullable=False)
    database: Mapped[str] = mapped_column(String(80), default="PostgreSQL", nullable=False)
    auth_method: Mapped[str] = mapped_column(String(80), default="JWT", nullable=False)
    deployment_platform: Mapped[str] = mapped_column(String(80), default="Docker", nullable=False)
    language: Mapped[str] = mapped_column(String(80), default="TypeScript", nullable=False)

    # --- Generation state ---------------------------------------------
    status: Mapped[str] = mapped_column(String(20), default="draft", nullable=False)
    blueprint: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    ai_provider: Mapped[str] = mapped_column(String(40), default="template", nullable=False)
    generation_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False
    )
    last_generated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    user = relationship("User")
