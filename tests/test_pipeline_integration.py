import threading
from typing import Any

import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.models import Company, CrmPush, Lead, LeadScore
from app.queue.enqueue import enqueue_job
from app.services.crm import MockCrm
from app.services.crm.push import push_lead
from app.services.reasoning import ReasoningInput
from tests.helpers import drain as _drain
from tests.helpers import job_types, jobs, make_runtime, release_scheduled

pytestmark = pytest.mark.integration


class FakeReasoner:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls = 0

    def explain(self, facts: ReasoningInput) -> str:
        self.calls += 1
        if self.fail:
            raise RuntimeError("anthropic unavailable")
        return f"Scored {facts.score} as {facts.segment}."


def seed_lead(
    session: Session, title: str, employees: int = 300, industry: str = "software", n: int = 1
) -> Lead:
    company = Company(
        domain=f"co{n}.com",
        name="Co",
        employee_count=employees,
        industry=industry,
        country="US",
        enrichment_status="enriched",
    )
    session.add(company)
    session.flush()
    lead = Lead(email=f"x{n}@co{n}.com", job_title=title, company_id=company.id)
    session.add(lead)
    session.flush()
    enqueue_job(session, "score_lead", {"lead_id": lead.id})
    session.commit()
    return lead


def make_worker(engine: Engine, **kwargs: Any) -> None:
    make_runtime(engine, **kwargs)


def drain(_worker: Any = None) -> None:
    _drain()


# --- segmentation + CRM ------------------------------------------------------------------
def test_hot_lead_is_segmented_and_pushed_exactly_once(session: Session, engine: Engine) -> None:
    lead = seed_lead(session, "CEO")  # 35 + 25 + 40 = 100
    crm = MockCrm()
    drain(make_worker(engine, crm=crm))
    session.expire_all()

    assert session.get_one(Lead, lead.id).segment == "hot"
    score = session.scalars(select(LeadScore)).one()
    push = session.scalars(select(CrmPush)).one()
    assert push.idempotency_key == f"{lead.id}:{score.id}"
    assert push.status == "pushed" and push.external_id == "mock-crm-1"
    assert len(crm.pushes) == 1 and crm.pushes[0].segment == "hot"


def test_repeated_push_job_does_not_call_crm_again(session: Session, engine: Engine) -> None:
    lead = seed_lead(session, "CEO")
    crm = MockCrm()
    worker = make_worker(engine, crm=crm)
    drain(worker)
    score = session.scalars(select(LeadScore)).one()
    enqueue_job(session, "push_crm", {"lead_id": lead.id, "score_id": score.id})
    session.commit()
    drain(worker)
    assert len(crm.pushes) == 1
    assert len(session.scalars(select(CrmPush)).all()) == 1


def test_new_score_gets_its_own_push(session: Session, engine: Engine) -> None:
    lead = seed_lead(session, "CEO")
    crm = MockCrm()
    worker = make_worker(engine, crm=crm)
    drain(worker)
    enqueue_job(session, "score_lead", {"lead_id": lead.id})  # rescore => new score id
    session.commit()
    drain(worker)
    assert len(crm.pushes) == 2
    keys = {p.idempotency_key for p in session.scalars(select(CrmPush))}
    assert len(keys) == 2


@pytest.mark.parametrize(
    ("title", "employees", "industry", "segment"),
    [
        ("Head of Growth", 300, "retail", "nurture"),  # 35 + 0 + 30 = 65
        ("Engineer", 5, "retail", "disqualified"),  # 5
    ],
)
def test_only_hot_leads_are_pushed(
    session: Session, engine: Engine, title: str, employees: int, industry: str, segment: str
) -> None:
    lead = seed_lead(session, title, employees, industry)
    crm = MockCrm()
    drain(make_worker(engine, crm=crm))
    session.expire_all()
    assert session.get_one(Lead, lead.id).segment == segment
    assert crm.pushes == []
    assert session.scalars(select(CrmPush)).all() == []
    assert "push_crm" not in job_types()


def test_push_lead_refuses_non_hot_segments(session: Session) -> None:
    lead = seed_lead(session, "CEO")
    score = LeadScore(lead_id=lead.id, score=50, rule_breakdown={}, rules_version="v")
    session.add(score)
    session.flush()
    assert push_lead(session, MockCrm(), lead, score, "nurture") is False


def test_crm_failure_rolls_back_the_claim_and_retry_succeeds(
    session: Session, engine: Engine, settings_env: Any
) -> None:
    settings_env(job_backoff_base_seconds=30)
    lead = seed_lead(session, "CEO")

    class FlakyCrm(MockCrm):
        fail = True

        async def upsert_lead(self, lead: Lead, score: LeadScore, segment: str) -> str:
            if self.fail:
                raise ConnectionError("crm down")
            return await super().upsert_lead(lead, score, segment)

    crm = FlakyCrm()
    make_worker(engine, crm=crm)
    drain()  # score ok, push fails and is re-queued with backoff
    session.expire_all()
    assert session.scalars(select(CrmPush)).all() == []  # claim rolled back
    (push_job,) = [j for j in jobs("queued") if j.type == "push_crm"]
    assert push_job.attempts == 1 and "crm down" in (push_job.last_error or "")

    crm.fail = False
    release_scheduled()
    drain()
    session.expire_all()
    assert session.scalars(select(CrmPush)).one().status == "pushed"
    assert lead.id


def test_concurrent_pushes_of_the_same_score_call_crm_once(
    session: Session, engine: Engine
) -> None:
    lead = seed_lead(session, "CEO")
    score = LeadScore(lead_id=lead.id, score=95, rule_breakdown={}, rules_version="v")
    session.add(score)
    session.commit()
    crm = MockCrm()
    results: list[bool] = []
    lock = threading.Lock()

    def work() -> None:
        with Session(engine, expire_on_commit=False) as s:
            ld = s.get_one(Lead, lead.id)
            sc = s.get_one(LeadScore, score.id)
            pushed = push_lead(s, crm, ld, sc, "hot")
            s.commit()
        with lock:
            results.append(pushed)

    threads = [threading.Thread(target=work) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert sorted(results) == [False, False, False, True]
    assert len(crm.pushes) == 1


# --- reasoning ----------------------------------------------------------------------------
def test_reasoning_fills_the_explanation_without_touching_the_score(
    session: Session, engine: Engine
) -> None:
    seed_lead(session, "CEO")
    reasoner = FakeReasoner()
    drain(make_worker(engine, reasoner=reasoner))
    session.expire_all()
    score = session.scalars(select(LeadScore)).one()
    assert (score.score, score.reasoning_status) == (100, "ok")
    assert score.reasoning == "Scored 100 as hot."
    assert reasoner.calls == 1


def test_reasoning_failure_keeps_score_and_retries_with_backoff(
    session: Session, engine: Engine, settings_env: Any
) -> None:
    settings_env(job_backoff_base_seconds=30)
    seed_lead(session, "CEO")
    reasoner = FakeReasoner(fail=True)
    make_worker(engine, reasoner=reasoner)
    drain()
    session.expire_all()
    score = session.scalars(select(LeadScore)).one()
    assert (score.score, score.reasoning, score.reasoning_status) == (100, None, "pending")
    (job,) = [j for j in jobs("queued") if j.type == "reason_lead"]
    assert job.attempts == 1 and "anthropic unavailable" in (job.last_error or "")
    assert reasoner.calls == 1  # backoff: not retried immediately

    # the CRM push is independent of the explanation
    assert session.scalars(select(CrmPush)).one().status == "pushed"

    # API recovers, retry becomes due: explanation is filled in on the retry
    reasoner.fail = False
    release_scheduled()
    drain()
    session.expire_all()
    score = session.scalars(select(LeadScore)).one()
    assert (score.reasoning_status, score.score) == ("ok", 100)
    assert jobs("failed") == []


def test_reasoning_marked_failed_after_all_retries(
    session: Session, engine: Engine, settings_env: Any
) -> None:
    settings_env(job_backoff_base_seconds=0)
    seed_lead(session, "CEO")
    reasoner = FakeReasoner(fail=True)
    make_worker(engine, reasoner=reasoner)
    drain()
    session.expire_all()
    assert reasoner.calls == 5  # default JOB_MAX_ATTEMPTS, then give up
    score = session.scalars(select(LeadScore)).one()
    assert (score.score, score.reasoning_status) == (100, "failed")
    assert [j.type for j in jobs("failed")] == ["reason_lead"]


def test_reasoning_disabled_needs_no_client_and_marks_skipped(
    session: Session, engine: Engine
) -> None:
    seed_lead(session, "CEO")
    drain(make_worker(engine, reasoner=None))
    session.expire_all()
    score = session.scalars(select(LeadScore)).one()
    assert (score.reasoning, score.reasoning_status) == (None, "skipped")
    assert "reason_lead" not in job_types()
    assert session.scalars(select(Lead)).one().segment == "hot"
