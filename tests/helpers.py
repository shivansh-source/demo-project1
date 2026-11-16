"""Test helpers for the RQ-based worker. Jobs run in-process with RQ's SimpleWorker against
fakeredis, so no Redis server is needed."""

from __future__ import annotations

from typing import Any

from rq import SimpleWorker
from rq.job import Job
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.queue.client import get_connection, get_queue
from app.queue.inspect import list_jobs
from app.queue.runtime import Runtime, set_runtime
from app.schemas.jobs import JobOut
from app.services.crm import CrmClient, MockCrm
from app.services.enrichment import MockEnrichmentProvider
from app.services.reasoning import Reasoner
from app.services.scoring.config import load_scoring_config
from app.worker.context import HandlerContext
from app.worker.handlers import FINAL_FAILURE_HOOKS, HANDLERS, FinalFailureHook, Handler


def make_runtime(
    engine: Engine,
    *,
    handlers: dict[str, Handler] | None = None,
    hooks: dict[str, FinalFailureHook] | None = None,
    reasoner: Reasoner | None = None,
    crm: CrmClient | None = None,
) -> Runtime:
    ctx = HandlerContext(
        settings=get_settings(),
        enrichment=MockEnrichmentProvider(),
        scoring=load_scoring_config("config/scoring.yaml"),
        crm=crm or MockCrm(),
        reasoner=reasoner,
    )
    runtime = Runtime(
        session_factory=lambda: Session(engine, expire_on_commit=False),
        ctx=ctx,
        handlers=dict(HANDLERS) if handlers is None else handlers,
        final_failure_hooks=dict(FINAL_FAILURE_HOOKS) if hooks is None else hooks,
    )
    set_runtime(runtime)
    return runtime


def drain() -> None:
    """Run every job that is queued right now (and immediate retries) to completion."""
    queue = get_queue()
    SimpleWorker([queue], connection=get_connection()).work(burst=True, with_scheduler=False)


def release_scheduled() -> int:
    """Make backed-off retries and deferred jobs due now: what RQ's scheduler does on a tick."""
    queue = get_queue()
    registry = queue.scheduled_job_registry
    released = 0
    for job_id in registry.get_job_ids():
        job = Job.fetch(job_id, connection=get_connection())
        registry.remove(job)
        queue.enqueue_job(job)
        released += 1
    return released


def jobs(status: str | None = None) -> list[JobOut]:
    return list_jobs(status, 200, 0)


def job_types(status: str | None = None) -> list[str]:
    return sorted(j.type for j in jobs(status))


def queued_payloads(job_type: str) -> list[dict[str, Any]]:
    return [j.payload for j in jobs("queued") if j.type == job_type]
