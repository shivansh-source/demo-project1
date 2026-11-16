"""The function RQ executes for every job. Referenced by import path in enqueue.TASK."""

from __future__ import annotations

import logging
from typing import Any

from rq import get_current_job

from app.queue.enqueue import enqueue_deferred
from app.queue.errors import DeferJob
from app.queue.runtime import get_runtime

log = logging.getLogger(__name__)


def run_job(job_type: str, payload: dict[str, Any]) -> None:
    """Run one handler in its own transaction: its writes commit together, or not at all.

    Failure: the exception propagates and RQ retries with the job's backoff intervals. On the
    final attempt (no retries left) the type's final-failure hook runs first.
    DeferJob: the job is re-scheduled later and this run counts as a success (no attempt used)."""
    runtime = get_runtime()
    job = get_current_job()
    handler = runtime.handlers.get(job_type)
    if handler is None:
        raise ValueError(f"no handler for job type {job_type!r}")
    try:
        with runtime.session_factory() as session:
            handler(session, payload, runtime.ctx)
            session.commit()
    except DeferJob as exc:
        job_id = job.id if job is not None else job_type
        base, _, count = job_id.partition("-defer")
        next_id = f"{base}-defer{int(count or 0) + 1}"
        max_attempts = int(job.meta.get("max_attempts", 5)) if job is not None else 5
        enqueue_deferred(job_type, payload, next_id, max_attempts, exc.delay_seconds)
        log.info("%s deferred %.0fs: %s", job_type, exc.delay_seconds, exc)
    except Exception as exc:
        if job is not None:  # RQ keeps no error for attempts that will be retried
            job.meta["last_error"] = f"{type(exc).__name__}: {exc}"[:2000]
            job.save_meta()  # type: ignore[no-untyped-call]
        final = job is None or not job.retries_left
        hook = runtime.final_failure_hooks.get(job_type)
        if final and hook is not None:
            with runtime.session_factory() as session:
                hook(session, payload)
                session.commit()
        raise
