from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Company, ImportRowError, Lead
from app.queue.client import get_queue
from tests.helpers import job_types, jobs

pytestmark = pytest.mark.integration

EXAMPLE = Path("examples/leads.csv")


def _upload(client: TestClient, content: bytes, name: str = "leads.csv"):  # type: ignore[no-untyped-def]
    return client.post("/imports/csv", files={"file": (name, content, "text/csv")})


def _count(session: Session, model: type) -> int:
    session.expire_all()
    return session.scalar(select(func.count()).select_from(model)) or 0


def test_csv_import_end_to_end(client: TestClient, session: Session) -> None:
    r = _upload(client, EXAMPLE.read_bytes())
    assert r.status_code == 201
    body = r.json()
    assert (body["total_rows"], body["accepted_rows"], body["rejected_rows"]) == (10, 7, 3)
    assert body["source"] == "csv" and body["filename"] == "leads.csv"
    assert [e["row_number"] for e in body["errors"]] == [8, 9, 10]
    assert "invalid email" in body["errors"][0]["reason"]
    assert body["errors"][0]["raw_payload"]["email"] == "not-an-email"

    assert _count(session, Lead) == 7
    assert _count(session, Company) == 7
    assert _count(session, ImportRowError) == 3
    john = session.scalar(select(Lead).where(Lead.email == "john.smith@globex.com"))
    assert john is not None  # email lowercased
    assert john.company.domain == "globex.com"  # company domain normalized, no www.

    types = job_types("queued")
    assert types.count("enrich_company") == 7
    assert types.count("score_lead") == 7


def test_reimport_creates_no_duplicates(client: TestClient, session: Session) -> None:
    first = _upload(client, EXAMPLE.read_bytes()).json()
    second = _upload(client, EXAMPLE.read_bytes()).json()
    assert second["id"] != first["id"]
    assert second["accepted_rows"] == 7
    assert _count(session, Lead) == 7
    assert _count(session, Company) == 7
    # Identical queued jobs are not duplicated either.
    assert len(jobs()) == 14
    # Rejected rows are recorded per batch each time.
    assert _count(session, ImportRowError) == 6


def test_api_import_uses_same_path(client: TestClient, session: Session) -> None:
    rows = [
        {"email": "Jane@Acme.com", "company_domain": "www.acme.com", "job_title": "VP"},
        {"email": "bad", "company_domain": "acme.com"},
        {"email": "jane@acme.com", "company_domain": "acme.com", "first_name": "Jane"},
    ]
    r = client.post("/imports/api", json=rows)
    assert r.status_code == 201
    body = r.json()
    assert body["source"] == "api" and body["filename"] is None
    assert (body["accepted_rows"], body["rejected_rows"]) == (2, 1)
    assert _count(session, Lead) == 1
    lead = session.scalars(select(Lead)).one()
    assert (lead.first_name, lead.job_title) == ("Jane", "VP")  # merged, nothing blanked


def test_reimport_with_blank_fields_keeps_existing_data(
    client: TestClient, session: Session
) -> None:
    client.post(
        "/imports/api",
        json=[{"email": "a@b.co", "company_domain": "b.co", "first_name": "Al"}],
    )
    client.post("/imports/api", json=[{"email": "a@b.co", "company_domain": "b.co"}])
    session.expire_all()
    assert session.scalars(select(Lead)).one().first_name == "Al"


def test_non_object_rows_are_rejected_not_dropped(client: TestClient) -> None:
    r = client.post("/imports/api", json=[{"email": 5, "company_domain": "b.co"}])
    assert r.status_code == 201
    assert r.json()["rejected_rows"] == 1
    assert r.json()["errors"][0]["reason"] == "email must be a string"


def test_csv_missing_required_column_is_422(client: TestClient, session: Session) -> None:
    r = _upload(client, b"email,first_name\na@b.co,A\n")
    assert r.status_code == 422
    assert "company_domain" in r.json()["detail"]
    assert _count(session, Lead) == 0


def test_get_batch_and_404(client: TestClient) -> None:
    batch_id = _upload(client, EXAMPLE.read_bytes()).json()["id"]
    got = client.get(f"/batches/{batch_id}")
    assert got.status_code == 200
    assert len(got.json()["errors"]) == 3
    assert client.get("/batches/9999").status_code == 404


def test_enrichment_job_skipped_for_already_enriched_company(
    client: TestClient, session: Session
) -> None:
    client.post("/imports/api", json=[{"email": "a@b.co", "company_domain": "b.co"}])
    company = session.scalars(select(Company)).one()
    company.enrichment_status = "enriched"
    session.commit()
    for queued in get_queue().jobs:
        queued.delete()

    client.post("/imports/api", json=[{"email": "c@b.co", "company_domain": "b.co"}])
    assert job_types() == ["score_lead"]
