import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient
from rq.job import Job
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.models import Company
from app.queue import enqueue as enqueue_module
from app.queue.client import get_connection, get_queue
from app.queue.enqueue import backoff_seconds, enqueue_job, has_active_job, job_key, retry_policy
from app.queue.errors import DeferJob
from app.worker.context import HandlerContext
from tests.helpers import drain, job_types, jobs, make_runtime, release_scheduled

pytestmark = pytest.mark.integration


def boom(_s: Session, _p: dict[str, Any], _c: HandlerContext) -> None:
    raise RuntimeError("boom")


def noop(_s: Session, _p: dict[str, Any], _c: HandlerContext) -> None:
    return None


# --- pure helpers --------------------------------------------------------------------------
def test_backoff_is_exponential_and_capped() -> None:
    assert [backoff_seconds(n, 2) for n in (1, 2, 3, 4)] == [2, 4, 8, 16]
    assert backoff_seconds(50, 2) == 3600


def test_retry_policy_has_one_interval_per_retry() -> None:
    policy = retry_policy(4, 2)
    assert policy is not None and policy.max == 3 and policy.intervals == [2, 4, 8]
    assert retry_policy(1, 2) is None


def test_job_key_is_deterministic_and_valid_for_rq() -> None:
    assert job_key("score_lead", {"lead_id": 5}) == "score_lead-lead_id-5"
    assert job_key("push_crm", {"score_id": 2, "lead_id": 1}) == "push_crm-lead_id-1-score_id-2"


def test_unknown_job_type_is_rejected_at_enqueue(session: Session) -> None:
    with pytest.raises(ValueError, match="unknown job type"):
        enqueue_job(session, "nope", {})


# --- enqueue is tied to the DB transaction -------------------------------------------------
def test_job_is_sent_only_after_commit(session: Session) -> None:
    enqueue_job(session, "score_lead", {"lead_id": 1})
    assert jobs() == []  # not visible before commit
    session.commit()
    assert job_types("queued") == ["score_lead"]


def test_rolled_back_transaction_enqueues_nothing(session: Session) -> None:
    enqueue_job(session, "score_lead", {"lead_id": 1})
    session.rollback()
    session.commit()
    assert jobs() == []


def test_identical_active_jobs_are_deduplicated(session: Session) -> None:
    assert enqueue_job(session, "score_lead", {"lead_id": 1}) is not None
    assert enqueue_job(session, "score_lead", {"lead_id": 1}) is None  # same transaction
    session.commit()
    assert enqueue_job(session, "score_lead", {"lead_id": 1}) is None  # already queued
    assert has_active_job("score_lead", {"lead_id": 1})
    assert enqueue_job(session, "score_lead", {"lead_id": 2}) is not None


def test_job_id_can_be_reused_once_the_job_finished(session: Session, engine: Engine) -> None:
    make_runtime(engine, handlers={"score_lead": noop})
    enqueue_job(session, "score_lead", {"lead_id": 1})
    session.commit()
    drain()
    assert job_types("done") == ["score_lead"]
    assert not has_active_job("score_lead", {"lead_id": 1})
    enqueue_job(session, "score_lead", {"lead_id": 1})
    session.commit()
    assert job_types("queued") == ["score_lead"]


def test_redis_outage_after_commit_is_logged_not_raised(
    session: Session, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def down(*_a: object, **_k: object) -> None:
        raise ConnectionError("redis down")

    enqueue_job(session, "score_lead", {"lead_id": 1})
    monkeypatch.setattr(enqueue_module, "_send", down)
    with caplog.at_level(logging.ERROR):
        session.commit()  # the data is saved; losing the job is logged, not raised
    assert "could not enqueue score_lead" in caplog.text


# --- running jobs ---------------------------------------------------------------------------
def test_import_then_worker_enriches_and_scores(
    client: TestClient, session: Session, engine: Engine
) -> None:
    client.post("/imports/api", json=[{"email": "a@acme.com", "company_domain": "acme.com"}])
    assert job_types("queued") == ["enrich_company", "score_lead"]
    make_runtime(engine)
    drain()
    session.expire_all()
    company = session.scalars(select(Company)).one()
    assert company.enrichment_status == "enriched" and company.enrichment_source == "mock"
    assert job_types("done") == ["enrich_company", "score_lead"]
    assert jobs("failed") == []


def test_unknown_domain_marks_not_found(
    client: TestClient, session: Session, engine: Engine
) -> None:
    row = {"email": "a@ghost.invalid", "company_domain": "ghost.invalid"}
    client.post("/imports/api", json=[row])
    make_runtime(engine)
    drain()
    session.expire_all()
    assert session.scalars(select(Company)).one().enrichment_status == "not_found"


def test_failing_job_retries_then_fails_for_good(
    session: Session, engine: Engine, settings_env: Any
) -> None:
    settings_env(job_backoff_base_seconds=0)
    calls: list[int] = []

    def counting_boom(s: Session, p: dict[str, Any], c: HandlerContext) -> None:
        calls.append(1)
        boom(s, p, c)

    make_runtime(engine, handlers={"enrich_company": counting_boom})
    enqueue_job(session, "enrich_company", {"company_id": 1}, max_attempts=3)
    session.commit()
    drain()
    assert len(calls) == 3
    (failed,) = jobs("failed")
    assert (failed.attempts, failed.max_attempts) == (3, 3)
    assert failed.last_error is not None and "boom" in failed.last_error
    assert jobs("queued") == []


def test_retry_waits_for_the_backoff_interval(
    session: Session, engine: Engine, settings_env: Any
) -> None:
    settings_env(job_backoff_base_seconds=30)
    make_runtime(engine, handlers={"enrich_company": boom})
    enqueue_job(session, "enrich_company", {"company_id": 1}, max_attempts=3)
    session.commit()
    drain()
    (waiting,) = jobs("queued")  # backed off, not running again yet
    assert waiting.attempts == 1 and "boom" in (waiting.last_error or "")
    assert get_queue().scheduled_job_registry.get_job_ids() == [waiting.id]
    drain()
    assert jobs("queued")[0].attempts == 1  # still waiting: nothing ran
    release_scheduled()
    drain()
    assert jobs("queued")[0].attempts == 2  # second failure, next (longer) backoff


def test_handler_effects_roll_back_when_it_fails(
    client: TestClient, session: Session, engine: Engine, settings_env: Any
) -> None:
    settings_env(job_backoff_base_seconds=0)

    def partial_then_fail(s: Session, p: dict[str, Any], _c: HandlerContext) -> None:
        s.get_one(Company, p["company_id"]).name = "changed"
        s.flush()
        raise RuntimeError("after write")

    client.post("/imports/api", json=[{"email": "a@acme.com", "company_domain": "acme.com"}])
    make_runtime(engine, handlers={"enrich_company": partial_then_fail})
    drain()
    session.expire_all()
    assert session.scalars(select(Company)).one().name is None


def test_final_failure_hook_runs_once_on_the_last_attempt(
    session: Session, engine: Engine, settings_env: Any
) -> None:
    settings_env(job_backoff_base_seconds=0)
    seen: list[dict[str, Any]] = []
    make_runtime(
        engine,
        handlers={"reason_lead": boom},
        hooks={"reason_lead": lambda _s, payload: seen.append(payload)},
    )
    enqueue_job(session, "reason_lead", {"score_id": 7}, max_attempts=3)
    session.commit()
    drain()
    assert seen == [{"score_id": 7}]  # not once per attempt


def test_job_without_a_handler_fails(session: Session, engine: Engine, settings_env: Any) -> None:
    settings_env(job_backoff_base_seconds=0)
    make_runtime(engine, handlers={})
    enqueue_job(session, "push_crm", {"lead_id": 1}, max_attempts=2)
    session.commit()
    drain()
    (failed,) = jobs("failed")
    assert "no handler" in (failed.last_error or "")


def test_deferred_job_is_rescheduled_without_using_an_attempt(
    session: Session, engine: Engine
) -> None:
    def later(_s: Session, _p: dict[str, Any], _c: HandlerContext) -> None:
        raise DeferJob(30, "waiting for enrichment")

    make_runtime(engine, handlers={"enrich_company": later})
    enqueue_job(session, "enrich_company", {"company_id": 1}, max_attempts=3)
    session.commit()
    drain()
    assert jobs("failed") == []
    (waiting,) = jobs("queued")
    assert waiting.id == "enrich_company-company_id-1-defer1" and waiting.attempts == 0
    release_scheduled()
    drain()
    assert [j.id for j in jobs("queued")] == ["enrich_company-company_id-1-defer2"]
    stored = Job.fetch("enrich_company-company_id-1-defer2", connection=get_connection())
    assert stored.meta["max_attempts"] == 3
    assert stored.args == ("enrich_company", {"company_id": 1})
