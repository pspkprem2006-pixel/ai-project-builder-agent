"""Durable generation worker process.

A separate process from the HTTP server: claims queued/stale generation jobs
from the database, runs the (unchanged) LangGraph pipeline and persists the
blueprint. Multiple workers may run concurrently; atomic conditional UPDATEs
guarantee each job is processed by exactly one worker. A per-job heartbeat
thread refreshes the lease so a crashed worker's job becomes stale and is
reclaimed elsewhere.

Usage:
    python -m app.worker            # run the claim loop
    python -m app.worker --check    # healthcheck: verify DB connectivity

Graceful shutdown: on SIGINT/SIGTERM the loop stops claiming; a job currently
running is left to its lease, which expires and is reclaimed by another worker
(stale-job recovery), so no state is lost.
"""
from __future__ import annotations

import argparse
import logging
import signal
import sys
import time
import uuid

from sqlalchemy import text

from app.database import SessionLocal
from app.services.generation_jobs import (
    CLAIM_INTERVAL_SECONDS,
    claim_job,
    execute_job,
    recover_stale_jobs,
)

logger = logging.getLogger("worker")


def check_database() -> None:
    """Healthcheck: open a session and run a trivial query."""
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    print("worker: database ok")


def run_once(worker_id: str) -> bool:
    """Claim and execute at most one job. Returns True when a job was handled."""
    with SessionLocal() as db:
        recover_stale_jobs(db)
        job_id = claim_job(db, worker_id)
    if job_id is None:
        return False
    outcome = execute_job(job_id, worker_id)
    logger.info("job_executed job_id=%s outcome=%s", job_id, outcome)
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="Durable blueprint generation worker")
    parser.add_argument("--check", action="store_true", help="Healthcheck: verify the database is reachable")
    args = parser.parse_args()

    if args.check:
        check_database()
        return

    worker_id = f"worker-{uuid.uuid4().hex[:12]}"
    logger.info("worker_started worker_id=%s claim_interval=%ss", worker_id, CLAIM_INTERVAL_SECONDS)

    stop = False

    def _stop(_signum, _frame) -> None:
        nonlocal stop
        stop = True
        logger.info("worker_stopping signal=%s", _signum)

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while not stop:
        try:
            handled = run_once(worker_id)
        except Exception:  # noqa: BLE001 - never let the worker die silently
            logger.exception("worker_loop_error worker_id=%s", worker_id)
            time.sleep(CLAIM_INTERVAL_SECONDS)
            continue
        if not handled:
            time.sleep(CLAIM_INTERVAL_SECONDS)

    logger.info("worker_stopped worker_id=%s", worker_id)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
    sys.exit(main())
