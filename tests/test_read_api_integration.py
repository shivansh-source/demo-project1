from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from app.worker.handlers import HANDLERS
from tests.helpers import drain, make_runtime
from tests.test_pipeline_integration import FakeReasoner, seed_lead

pytestmark = pytest.mark.integration


def test_full_flow_through_the_api(client: TestClient, engine: Engine) -> None:
    rows = [
        {"email": "ceo@acme.com", "company_domain": "acme.com", "job_title": "CEO"},
        {"email": "dev@acme.com", "company_domain": "acme.com", "job_title": "Engineer"},
        {"email": "bad", "company_domain": "acme.com"},
    ]
    batch = client.post("/imports/api", json=rows).json()
    assert batch["rejected_rows"] == 1
    make_runtime(engine, reasoner=FakeReasoner())
    drain()

    leads = client.get("/leads").json()
    assert leads["total"] == 2 and len(leads["items"]) == 2
    assert all(item["segment"] is not None for item in leads["items"])

    detail = client.get(f"/leads/{leads['items'][0]['id']}").json()
    assert detail["company"]["enrichment_status"] == "enriched"
    latest = detail["latest_score"]
    assert 0 <= latest["score"] <= 100
    assert set(latest["rule_breakdown"]["rules"]) >= {"company_size", "seniority"}
    assert latest["reasoning_status"] == "ok" and latest["reasoning"].startswith("Scored")
    assert len(latest["rules_version"]) == 64


def test_filter_by_segment_and_pagination(
    client: TestClient, session: Session, engine: Engine
) -> None:
    seed_lead(session, "CEO", n=1)  # hot
    seed_lead(session, "CEO", n=2)  # hot
    seed_lead(session, "Engineer", employees=5, industry="retail", n=3)  # disqualified
    make_runtime(engine)
    drain()

    hot = client.get("/leads", params={"segment": "hot"}).json()
    assert hot["total"] == 2 and {i["segment"] for i in hot["items"]} == {"hot"}
    page = client.get("/leads", params={"limit": 1, "offset": 1}).json()
    assert page["total"] == 3 and len(page["items"]) == 1 and page["offset"] == 1
    assert client.get("/leads", params={"segment": "nope"}).status_code == 422
    assert client.get("/leads", params={"limit": 0}).status_code == 422
    assert client.get("/leads", params={"limit": 500}).status_code == 422


def test_score_history_and_rescore(client: TestClient, session: Session, engine: Engine) -> None:
    lead = seed_lead(session, "CEO")
    make_runtime(engine)
    drain()

    r = client.post(f"/leads/{lead.id}/rescore")
    assert r.status_code == 202 and r.json()["queued"] is True
    again = client.post(f"/leads/{lead.id}/rescore").json()
    assert again["queued"] is False and again["job_id"] is None  # already queued: deduped
    drain()

    history = client.get(f"/leads/{lead.id}/scores").json()
    assert len(history) == 2
    assert history[0]["id"] > history[1]["id"]  # newest first
    assert client.get(f"/leads/{lead.id}").json()["latest_score"]["id"] == history[0]["id"]


def test_unscored_lead_has_null_latest_score(client: TestClient) -> None:
    client.post("/imports/api", json=[{"email": "a@acme.com", "company_domain": "acme.com"}])
    lead_id = client.get("/leads").json()["items"][0]["id"]
    detail = client.get(f"/leads/{lead_id}").json()
    assert detail["latest_score"] is None and detail["segment"] is None
    assert client.get(f"/leads/{lead_id}/scores").json() == []


def test_missing_lead_returns_404(client: TestClient) -> None:
    assert client.get("/leads/999").status_code == 404
    assert client.get("/leads/999/scores").status_code == 404
    assert client.post("/leads/999/rescore").status_code == 404


def test_jobs_listing_filters_by_status(
    client: TestClient, engine: Engine, settings_env: Any
) -> None:
    settings_env(job_backoff_base_seconds=0, job_max_attempts=2)

    def boom(*_args: object) -> None:
        raise RuntimeError("scoring exploded")

    client.post("/imports/api", json=[{"email": "a@acme.com", "company_domain": "acme.com"}])
    queued = client.get("/jobs", params={"status": "queued"}).json()
    assert sorted(j["type"] for j in queued) == ["enrich_company", "score_lead"]

    handlers = {"enrich_company": HANDLERS["enrich_company"], "score_lead": boom}
    make_runtime(engine, handlers=handlers)
    drain()

    failed = client.get("/jobs", params={"status": "failed"}).json()
    assert len(failed) == 1
    assert failed[0]["type"] == "score_lead" and failed[0]["payload"] == {"lead_id": 1}
    assert failed[0]["attempts"] == 2 and "scoring exploded" in failed[0]["last_error"]
    assert [j["type"] for j in client.get("/jobs", params={"status": "done"}).json()] == [
        "enrich_company"
    ]
    assert client.get("/jobs", params={"status": "queued"}).json() == []
    assert len(client.get("/jobs").json()) == 2
    assert len(client.get("/jobs", params={"limit": 1}).json()) == 1
    assert client.get("/jobs", params={"status": "bogus"}).status_code == 422


def test_openapi_lists_every_endpoint(client: TestClient) -> None:
    paths = client.get("/openapi.json").json()["paths"]
    expected = {
        "/health",
        "/imports/csv",
        "/imports/api",
        "/batches/{batch_id}",
        "/leads",
        "/leads/{lead_id}",
        "/leads/{lead_id}/scores",
        "/leads/{lead_id}/rescore",
        "/jobs",
    }
    assert expected <= set(paths)
    assert client.get("/docs").status_code == 200


def test_crm_overview_lists_pushes(client: TestClient, session: Session, engine: Engine) -> None:
    empty = client.get("/crm").json()
    assert empty["provider"] == "mock" and empty["live"] is False and empty["pushes"] == []

    seed_lead(session, "CEO", n=1)
    seed_lead(session, "Engineer", employees=5, industry="retail", n=2)
    make_runtime(engine)
    drain()

    body = client.get("/crm").json()
    assert (body["hot_leads"], body["pushed"]) == (1, 1)
    (push,) = body["pushes"]
    assert push["email"] == "x1@co1.com" and push["score"] == 100
    assert push["status"] == "pushed" and push["external_id"] == "mock-crm-1"
    assert push["company"] == "Co"


def test_stats_counts_each_pipeline_stage(
    client: TestClient, session: Session, engine: Engine
) -> None:
    before = client.get("/stats").json()
    assert before["pipeline"]["imported"] == 0 and before["hot_leads"] == []

    seed_lead(session, "CEO", n=1)
    seed_lead(session, "Engineer", employees=5, industry="retail", n=2)
    make_runtime(engine, reasoner=FakeReasoner())
    drain()

    body = client.get("/stats").json()
    assert body["pipeline"] == {
        "imported": 2,
        "enriched": 2,
        "scored": 2,
        "explained": 2,
        "pushed": 1,
    }
    assert body["segments"] == {"hot": 1, "nurture": 0, "disqualified": 1}
    (hot,) = body["hot_leads"]
    assert hot["score"] == 100 and hot["reasoning"].startswith("Scored 100")

    future = client.get("/stats", params={"since": "2999-01-01T00:00:00Z"}).json()
    assert future["pipeline"]["imported"] == 0
