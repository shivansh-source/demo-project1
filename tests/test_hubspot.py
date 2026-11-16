import asyncio
import json
from typing import Any

import httpx
import pytest
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.models import Company, CrmPush, Lead, LeadScore
from app.services.crm import HubSpotCrm, MockCrm, get_crm
from app.services.crm.hubspot import (
    HubSpotAuthError,
    HubSpotError,
    HubSpotRateLimited,
)
from tests.helpers import drain, make_runtime
from tests.test_pipeline_integration import seed_lead

TOKEN = "pat-na1-test-token"


def make_lead() -> tuple[Lead, LeadScore]:
    company = Company(domain="acme.com", name="Acme")
    lead = Lead(
        id=1,
        email="jane@acme.com",
        first_name="Jane",
        last_name="Doe",
        job_title="VP Sales",
        company=company,
    )
    return lead, LeadScore(id=9, lead_id=1, score=92)


class Recorder:
    """An httpx transport that records requests and answers with a canned response."""

    def __init__(self, status: int = 200, body: Any = None, headers: dict[str, str] | None = None):
        self.status = status
        self.body = body if body is not None else {"results": [{"id": "5150"}]}
        self.headers = headers or {}
        self.requests: list[httpx.Request] = []

    def transport(self) -> httpx.MockTransport:
        def handler(request: httpx.Request) -> httpx.Response:
            self.requests.append(request)
            return httpx.Response(self.status, json=self.body, headers=self.headers)

        return httpx.MockTransport(handler)


def push(crm: HubSpotCrm, segment: str = "hot") -> str:
    lead, score = make_lead()
    return asyncio.run(crm.upsert_lead(lead, score, segment))


def test_upsert_sends_one_authenticated_request_and_returns_the_id() -> None:
    rec = Recorder()
    crm = HubSpotCrm(TOKEN, transport=rec.transport())
    assert push(crm) == "5150"

    (request,) = rec.requests
    assert request.method == "POST"
    assert str(request.url) == "https://api.hubapi.com/crm/v3/objects/contacts/batch/upsert"
    assert request.headers["authorization"] == f"Bearer {TOKEN}"
    (item,) = json.loads(request.content)["inputs"]
    assert item["idProperty"] == "email" and item["id"] == "jane@acme.com"
    assert item["properties"] == {
        "email": "jane@acme.com",
        "firstname": "Jane",
        "lastname": "Doe",
        "jobtitle": "VP Sales",
        "company": "Acme",
        "website": "acme.com",
    }


def test_custom_score_and_segment_properties_are_opt_in() -> None:
    rec = Recorder()
    crm = HubSpotCrm(
        TOKEN,
        base_url="https://sandbox.example.test/",
        score_property="lead_score",
        segment_property="lead_segment",
        transport=rec.transport(),
    )
    push(crm)
    props = json.loads(rec.requests[0].content)["inputs"][0]["properties"]
    assert props["lead_score"] == "92" and props["lead_segment"] == "hot"
    assert str(rec.requests[0].url).startswith("https://sandbox.example.test/crm/")


def test_missing_optional_fields_are_left_out() -> None:
    lead = Lead(id=2, email="x@y.co", company=Company(domain="y.co"))
    props = HubSpotCrm(TOKEN).build_properties(lead, LeadScore(id=1, score=1), "hot")
    assert props == {"email": "x@y.co", "company": "y.co", "website": "y.co"}


@pytest.mark.parametrize(
    ("status", "error", "text"),
    [
        (401, HubSpotAuthError, "rejected the token"),
        (403, HubSpotAuthError, "rejected the token"),
        (429, HubSpotRateLimited, "Retry-After: 7s"),
        (500, HubSpotError, "500"),
        (400, HubSpotError, "lead_score does not exist"),
    ],
)
def test_error_responses_raise_typed_errors(status: int, error: type[Exception], text: str) -> None:
    body = {"message": "Property lead_score does not exist"}
    rec = Recorder(status, body, {"Retry-After": "7"})
    with pytest.raises(error) as info:
        push(HubSpotCrm(TOKEN, transport=rec.transport()))
    assert text in str(info.value)


def test_response_without_an_id_is_an_error() -> None:
    with pytest.raises(HubSpotError, match="did not contain a contact id"):
        push(HubSpotCrm(TOKEN, transport=Recorder(200, {"results": []}).transport()))


def test_network_failure_is_wrapped() -> None:
    def down(_request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("no route")

    with pytest.raises(HubSpotError, match="request failed"):
        push(HubSpotCrm(TOKEN, transport=httpx.MockTransport(down)))


def test_factory_selects_hubspot_and_requires_a_token() -> None:
    cfg = Settings(_env_file=None, crm_provider="hubspot", crm_api_token=TOKEN)  # type: ignore[call-arg]
    assert isinstance(get_crm(cfg), HubSpotCrm)
    no_token = Settings(_env_file=None, crm_provider="hubspot")  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="CRM_API_TOKEN"):
        get_crm(no_token)
    assert isinstance(get_crm(Settings(_env_file=None)), MockCrm)  # type: ignore[call-arg]


# --- through the real pipeline ---------------------------------------------------------------
@pytest.mark.integration
def test_hot_lead_reaches_hubspot_once_even_when_the_job_repeats(
    session: Session, engine: Engine
) -> None:
    from app.queue.enqueue import enqueue_job

    lead = seed_lead(session, "CEO")
    rec = Recorder()
    make_runtime(engine, crm=HubSpotCrm(TOKEN, transport=rec.transport()))
    drain()
    session.expire_all()

    push_row = session.scalars(select(CrmPush)).one()
    assert push_row.external_id == "5150" and push_row.status == "pushed"
    assert len(rec.requests) == 1
    props = json.loads(rec.requests[0].content)["inputs"][0]["properties"]
    assert props["email"] == lead.email and props["jobtitle"] == "CEO"

    enqueue_job(session, "push_crm", {"lead_id": lead.id, "score_id": push_row.score_id})
    session.commit()
    drain()
    assert len(rec.requests) == 1  # same idempotency key: HubSpot is not called again


@pytest.mark.integration
def test_hubspot_outage_keeps_the_lead_and_retries(
    session: Session, engine: Engine, settings_env: Any
) -> None:
    from tests.helpers import jobs, release_scheduled

    settings_env(job_backoff_base_seconds=30)
    seed_lead(session, "CEO")
    rec = Recorder(500, {"message": "boom"})
    make_runtime(engine, crm=HubSpotCrm(TOKEN, transport=rec.transport()))
    drain()
    session.expire_all()
    assert session.scalars(select(CrmPush)).all() == []  # claim rolled back
    (waiting,) = [j for j in jobs("queued") if j.type == "push_crm"]
    assert "HubSpot returned 500" in (waiting.last_error or "")

    rec.status, rec.body = 200, {"results": [{"id": "77"}]}
    release_scheduled()
    drain()
    session.expire_all()
    assert session.scalars(select(CrmPush)).one().external_id == "77"
