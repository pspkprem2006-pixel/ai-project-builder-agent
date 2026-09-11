"""Rate-limit counters for auth abuse protection.

One row per (scope, identity) key; the window is a fixed bucket of
``window_seconds``. Counters are bumped with atomic conditional UPDATEs so the
limits hold under concurrent requests and across multiple worker processes
(PostgreSQL row locks / SQLite single-writer semantics).
"""

from datetime import datetime

from sqlalchemy import DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base


class RateLimit(Base):
    __tablename__ = "rate_limits"

    id: Mapped[int] = mapped_column(primary_key=True)
    key: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    window_start: Mapped[datetime] = mapped_column(DateTime)
    count: Mapped[int] = mapped_column(Integer, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime)
