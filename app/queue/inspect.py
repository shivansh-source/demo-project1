"""Read-only view of the queue for GET /jobs, built from RQ's registries."""

from __future__ import annotations

from typing import Any, cast

from rq.job import Job

from app.queue.client import get_connection, get_queue
from app.schemas.jobs import JobOut

STATUSES = ("queued", "running", "done", "failed")


def _ids(status: str) -> list[str]:
    queue = get_queue()
    if status == "queued":
        return [*queue.job_ids, *queue.scheduled_job_registry.get_job_ids()]
    registry = {
        "running": queue.started_job_registry,
        "done": queue.finished_job_registry,
        "failed": queue.failed_job_registry,
    }[status]
    return cast("list[str]", registry.get_job_ids())


def _last_error(job: Job) -> str | None:
    recorded = job.meta.get("last_error")
    if recorded:
        return str(recorded)
    result = job.latest_result()
    text = getattr(result, "exc_string", None) if result is not None else None
    if not text:
        return None
    return str(text).strip().splitlines()[-1][:2000]


def _to_out(job: Job, status: str) -> JobOut:
    max_attempts = int(job.meta.get("max_attempts", 1))
    failures = max(max_attempts - 1 - int(job.retries_left or 0), 0)
    # RQ counts retries left, not attempts: every failure used one retry.
    attempts = failures + (0 if status == "queued" else 1)
    args: Any = job.args
    return JobOut(
        id=job.id,
        type=str(job.meta.get("type", args[0] if args else "unknown")),
        payload=dict(args[1]) if len(args) > 1 else {},
        status=status,
        attempts=attempts,
        max_attempts=max_attempts,
        last_error=_last_error(job) if (status == "failed" or failures) else None,
        enqueued_at=job.enqueued_at,
    )


def list_jobs(status: str | None, limit: int, offset: int) -> list[JobOut]:
    """Newest first. Each status is read from its RQ registry; finished jobs disappear after
    JOB_RESULT_TTL_SECONDS and failed jobs after JOB_FAILURE_TTL_SECONDS."""
    wanted = [status] if status else list(STATUSES)
    out: list[JobOut] = []
    for name in wanted:
        ids = _ids(name)
        for job in Job.fetch_many(ids, connection=get_connection()):
            if job is not None:
                out.append(_to_out(job, name))
    out.sort(key=lambda j: j.enqueued_at.timestamp() if j.enqueued_at else 0.0, reverse=True)
    return out[offset : offset + limit]
