"""DB-backed fixed-window rate limiting.

Why the database and not an in-memory dict: the production topology may run
several uvicorn worker processes (and the generation worker), each with its
own memory. An in-memory limiter would multiply the effective limit by the
number of processes and lose state on restart. A single small table in the
existing PostgreSQL/SQLite database is shared, durable and requires no new
infrastructure.

Atomicity: the common path is one conditional UPDATE that increments the
counter and returns it (row-locked on PostgreSQL, single-writer on SQLite).
A missing/expired window falls back to an INSERT; a lost insert race is
resolved by retrying the UPDATE against the winner's fresh row.

The limiter never inspects account state, so it cannot reveal whether an
email/account exists — the 429 response is identical for every identity.
"""

import logging
from datetime import datetime

from fastapi import HTTPException, Request, status
from sqlalchemy import insert, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.rate_limit import RateLimit

logger = logging.getLogger(__name__)

GENERIC_429 = "Too many attempts. Please try again later."


def _utcnow() -> datetime:
    return datetime.utcnow()


def _window_start(now: datetime, window_seconds: int) -> datetime:
    epoch = int(now.timestamp())
    bucket = epoch - (epoch % window_seconds)
    return datetime.utcfromtimestamp(bucket)


def check_rate_limit(
    db: Session, key: str, limit: int, window_seconds: int
) -> tuple[bool, int, int]:
    """Record one attempt and report whether it is within the limit.

    Returns ``(allowed, remaining, limit)``. ``remaining`` is 0 once the
    limit is reached or exceeded.
    """
    if limit <= 0:
        return False, 0, limit
    now = _utcnow()
    ws = _window_start(now, window_seconds)

    result = db.execute(
        update(RateLimit)
        .where(RateLimit.key == key, RateLimit.window_start == ws)
        .values(count=RateLimit.count + 1, updated_at=now)
        .returning(RateLimit.count)
    )
    count = result.scalar_one_or_none()
    if count is None:
        try:
            db.execute(
                insert(RateLimit).values(key=key, window_start=ws, count=1, updated_at=now)
            )
            db.commit()
            count = 1
        except IntegrityError:
            db.rollback()
            # The key already exists. If a concurrent request won the insert for
            # this window, increment it; if the stored row belongs to an older
            # window, atomically reset it to the current window.
            result = db.execute(
                update(RateLimit)
                .where(RateLimit.key == key, RateLimit.window_start == ws)
                .values(count=RateLimit.count + 1, updated_at=now)
                .returning(RateLimit.count)
            )
            count = result.scalar_one_or_none()
            if count is None:
                result = db.execute(
                    update(RateLimit)
                    .where(RateLimit.key == key)
                    .values(window_start=ws, count=1, updated_at=now)
                    .returning(RateLimit.count)
                )
                count = result.scalar_one()
            db.commit()
    else:
        db.commit()
    remaining = max(0, limit - count)
    return count <= limit, remaining, limit


def client_ip(request: Request) -> str:
    """Client address for rate-limit keys.

    ``request.client`` is None under some ASGI transports (e.g. TestClient);
    such requests share the ``unknown`` bucket. Behind a reverse proxy the
    proxy must rewrite/forward the client address; unauthenticated rate
    limits are additionally keyed per-account where applicable.
    """
    if request.client is not None and request.client.host:
        return request.client.host
    return "unknown"


def enforce_rate_limit(
    db: Session,
    request: Request,
    scope: str,
    identity: str,
    limit: int,
    window_seconds: int,
) -> None:
    """Raise HTTP 429 when the (scope, identity) window limit is exceeded."""
    allowed, remaining, limit = check_rate_limit(
        db, f"{scope}:{identity}", limit, window_seconds
    )
    if allowed:
        return
    logger.info("rate_limit_exceeded scope=%s", scope)
    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail=GENERIC_429,
        headers={"Retry-After": str(window_seconds)},
    )
