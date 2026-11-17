"""Enqueueing jobs on RQ, tied to the database transaction.

Jobs requested through `enqueue_job` are held on the SQLAlchemy session and sent to Redis only
after that session COMMITS (and are dropped on rollback). That gives the same guarantee the old
Postgres job table had in one direction: a job never runs against rows that were rolled back.

The opposite window exists now: if Redis is unreachable right after a commit the job is logged
and lost (the data is saved, the work is not queued). The fix is an outbox table; see the README.
"""

from __future__ import annotations

import logging
import time
import uuid
from datetime import timedelta
from typing import Any

from rq import Retry
from rq.job import JobStatus
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.queue.client import get_queue

log = logging.getLogger(__name__)

JOB_TYPES = ("enrich_company", "score_lead", "reason_lead", "push_crm")
ACTIVE = {JobStatus.QUEUED, JobStatus.STARTED, JobStatus.SCHEDULED, JobStatus.DEFERRED}
_PENDING_KEY = "pending_jobs"
TASK = "app.queue.tasks.run_job"


def backoff_seconds(attempts: int, base: float) -> float:
    """Delay before retry number `attempts` (1-based): base * 2^(attempts-1), capped at 1 h."""
    return float(min(base * (2 ** max(attempts - 1, 0)), 3600.0))


def retry_policy(max_attempts: int, base: float) -> Retry | None:
    retries = max_attempts - 1
    if retries <= 0:
        return None
    return Retry(
        max=retries, interval=[int(backoff_seconds(n, base)) for n in range(1, retries + 1)]
    )


def job_key(job_type: str, payload: dict[str, Any]) -> str:
    """Deterministic id, e.g. `score_lead-lead_id-5`. Used for de-duplication."""
    parts = [f"{k}-{v}" for k, v in sorted(payload.items())]
    return "-".join([job_type, *parts])


def is_active(job_id: str) -> bool:
    job = get_queue().fetch_job(job_id)
    return job is not None and job.get_status(refresh=True) in ACTIVE


def has_active_job(job_type: str, payload: dict[str, Any]) -> bool:
    return is_active(job_key(job_type, payload))


def _send(
    job_type: str,
    payload: dict[str, Any],
    job_id: str,
    max_attempts: int,
    delay_seconds: float | None = None,
) -> None:
    settings = get_settings()
    queue = get_queue()
    stale = queue.fetch_job(job_id)
    if stale is not None:
        stale.delete()  # a finished/failed job with this id would otherwise block reuse
    options: dict[str, Any] = {
        "job_id": job_id,
        "retry": retry_policy(max_attempts, settings.job_backoff_base_seconds),
        "job_timeout": settings.job_timeout_seconds,
        "result_ttl": settings.job_result_ttl_seconds,
        "failure_ttl": settings.job_failure_ttl_seconds,
        "meta": {"type": job_type, "max_attempts": max_attempts},
    }
    if delay_seconds is None:
        queue.enqueue(TASK, job_type, payload, **options)
    else:
        queue.enqueue_in(timedelta(seconds=delay_seconds), TASK, job_type, payload, **options)


def enqueue_job(
    session: Session,
    job_type: str,
    payload: dict[str, Any],
    *,
    dedupe: bool = True,
    max_attempts: int | None = None,
) -> str | None:
    """Request a job; it is sent to Redis when `session` commits. With `dedupe`, returns None
    (and sends nothing) if an identical job is already queued, scheduled or running."""
    if job_type not in JOB_TYPES:
        raise ValueError(f"unknown job type: {job_type!r}")
    job_id = job_key(job_type, payload)
    if dedupe:
        if is_active(job_id):
            return None
    else:
        job_id = f"{job_id}-{uuid.uuid4().hex[:8]}"
    attempts = max_attempts or get_settings().job_max_attempts
    session.connection()  # begin the transaction now so a rollback is seen and drops the jobs
    pending: list[tuple[str, dict[str, Any], str, int]] = session.info.setdefault(_PENDING_KEY, [])
    if dedupe and any(p[2] == job_id for p in pending):
        return None
    pending.append((job_type, payload, job_id, attempts))
    return job_id


def enqueue_deferred(
    job_type: str, payload: dict[str, Any], job_id: str, max_attempts: int, delay_seconds: float
) -> None:
    """Re-schedule a job that asked to wait (DeferJob). Sent immediately: no session involved."""
    _send(job_type, payload, job_id, max_attempts, delay_seconds)


SEND_ATTEMPTS = 3
SEND_RETRY_DELAY_SECONDS = 0.2


def _send_with_retry(job_type: str, payload: dict[str, Any], job_id: str, attempts: int) -> None:
    """A dropped Redis connection is usually transient: redis-py reconnects on the next call."""
    for attempt in range(1, SEND_ATTEMPTS + 1):
        try:
            _send(job_type, payload, job_id, attempts)
            return
        except Exception:
            if attempt == SEND_ATTEMPTS:
                raise
            time.sleep(SEND_RETRY_DELAY_SECONDS * attempt)


@event.listens_for(Session, "after_commit")
def _flush_pending(session: Session) -> None:
    pending = session.info.pop(_PENDING_KEY, [])
    for job_type, payload, job_id, attempts in pending:
        try:
            _send_with_retry(job_type, payload, job_id, attempts)
        except Exception:
            log.exception("committed, but could not enqueue %s (%s)", job_type, job_id)


@event.listens_for(Session, "after_rollback")
def _drop_pending(session: Session) -> None:
    session.info.pop(_PENDING_KEY, None)
