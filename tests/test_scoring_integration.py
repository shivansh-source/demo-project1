from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.models import Company, Lead, LeadScore
from app.queue.client import get_queue
from app.queue.enqueue import enqueue_job
from app.services.scoring.config import load_scoring_config
from tests.helpers import drain, job_types, jobs, make_runtime

pytestmark = pytest.mark.integration


def test_import_then_worker_scores_every_lead(
    client: TestClient, session: Session, engine: Engine
) -> None:
    client.post(
        "/imports/api",
        json=[
            {"email": "vp@acme.com", "company_domain": "acme.com", "job_title": "VP Sales"},
            {"email": "dev@acme.com", "company_domain": "acme.com", "job_title": "Engineer"},
        ],
    )
    make_runtime(engine)
    drain()
    session.expire_all()

    scores = session.scalars(select(LeadScore).order_by(LeadScore.lead_id)).all()
    assert len(scores) == 2
    version = load_scoring_config("config/scoring.yaml").rules_version
    for s in scores:
        assert s.rules_version == version
        assert 0 <= s.score <= 100
        assert set(s.rule_breakdown["rules"]) == {
            "company_size",
            "industry_fit",
            "seniority",
            "engagement",
        }
        assert s.reasoning_status == "skipped"  # REASONING_ENABLED defaults to false
    vp, dev = scores
    assert vp.score - dev.score == 30  # same company, only the seniority rule differs
    assert jobs("failed") == [] and jobs("queued") == []


def test_scoring_uses_enriched_company_data(
    client: TestClient, session: Session, engine: Engine
) -> None:
    client.post("/imports/api", json=[{"email": "a@acme.com", "company_domain": "acme.com"}])
    make_runtime(engine)
    drain()
    session.expire_all()
    company = session.scalars(select(Company)).one()
    score = session.scalars(select(LeadScore)).one()
    assert score.rule_breakdown["rules"]["company_size"]["reason"].startswith(
        f"{company.employee_count} employees"
    )


def test_score_waits_for_pending_enrichment(
    client: TestClient, session: Session, engine: Engine
) -> None:
    client.post("/imports/api", json=[{"email": "a@acme.com", "company_domain": "acme.com"}])
    # Park the enrichment job in the future so score_lead is picked up first.
    queue = get_queue()
    enrich = queue.fetch_job("enrich_company-company_id-1")
    assert enrich is not None
    queue.remove(enrich)
    queue.enqueue_in(
        timedelta(hours=1),
        "app.queue.tasks.run_job",
        "enrich_company",
        {"company_id": 1},
        job_id="enrich_company-company_id-1",
        meta={"type": "enrich_company", "max_attempts": 5},
    )
    make_runtime(engine)
    drain()  # score_lead runs, sees enrichment still pending, defers
    session.expire_all()
    assert session.scalars(select(LeadScore)).all() == []
    assert jobs("failed") == []
    waiting = {j.id: j for j in jobs("queued")}
    assert "score_lead-lead_id-1-defer1" in waiting
    assert waiting["score_lead-lead_id-1-defer1"].attempts == 0  # no attempt consumed


def test_score_proceeds_when_enrichment_is_not_coming(
    client: TestClient, session: Session, engine: Engine
) -> None:
    client.post("/imports/api", json=[{"email": "a@acme.com", "company_domain": "acme.com"}])
    queue = get_queue()
    enrich = queue.fetch_job("enrich_company-company_id-1")
    assert enrich is not None
    enrich.delete()  # as if enrichment failed for good: no active enrichment job remains
    make_runtime(engine)
    drain()
    session.expire_all()
    score = session.scalars(select(LeadScore)).one()
    assert score.rule_breakdown["rules"]["company_size"]["reason"] == "company size unknown"


def test_each_scoring_run_appends_a_row(
    client: TestClient, session: Session, engine: Engine
) -> None:
    client.post("/imports/api", json=[{"email": "a@acme.com", "company_domain": "acme.com"}])
    make_runtime(engine)
    drain()
    lead = session.scalars(select(Lead)).one()
    client.post("/imports/api", json=[{"email": "a@acme.com", "company_domain": "acme.com"}])
    assert job_types("queued") == ["score_lead"]  # company already enriched
    drain()
    session.expire_all()
    scores = session.scalars(select(LeadScore).where(LeadScore.lead_id == lead.id)).all()
    assert len(scores) == 2
    assert scores[0].id != scores[1].id


def test_enqueue_uses_session_transaction(session: Session) -> None:
    assert enqueue_job(session, "score_lead", {"lead_id": 9}) is not None
    session.commit()
    assert job_types("queued") == ["score_lead"]
