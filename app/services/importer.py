"""CSV parsing, row validation and the shared import path for CSV and API imports."""

from __future__ import annotations

import csv
import io
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.core.errors import ValidationFailed
from app.models import Company, ImportBatch, ImportRowError, Lead
from app.queue.enqueue import enqueue_job

REQUIRED_COLUMNS = ("email", "company_domain")
OPTIONAL_COLUMNS = ("first_name", "last_name", "job_title")
MAX_FIELD_LEN = 255

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_DOMAIN_RE = re.compile(r"^(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,63}$")


class RowInvalid(Exception):
    """A single row failed validation; the message becomes the stored reason."""


@dataclass(frozen=True)
class ValidRow:
    email: str
    domain: str
    first_name: str | None
    last_name: str | None
    job_title: str | None


def normalize_email(value: str) -> str:
    return value.strip().lower()


def normalize_domain(value: str) -> str:
    domain = value.strip().lower()
    return domain.removeprefix("www.")


def _clean(raw: Mapping[str, Any], field: str) -> str | None:
    value = raw.get(field)
    if value is None:
        return None
    if not isinstance(value, str):
        raise RowInvalid(f"{field} must be a string")
    value = value.strip()
    if len(value) > MAX_FIELD_LEN:
        raise RowInvalid(f"{field} is longer than {MAX_FIELD_LEN} characters")
    return value or None


def validate_row(raw: Mapping[str, Any]) -> ValidRow:
    """Validate and normalize one row. Raises RowInvalid with a human-readable reason."""
    email = _clean(raw, "email")
    domain = _clean(raw, "company_domain")
    if email is None:
        raise RowInvalid("email is required")
    if domain is None:
        raise RowInvalid("company_domain is required")

    email = normalize_email(email)
    if not _EMAIL_RE.match(email):
        raise RowInvalid(f"invalid email: {email!r}")
    domain = normalize_domain(domain)
    if not _DOMAIN_RE.match(domain):
        raise RowInvalid(f"invalid company_domain: {domain!r}")

    return ValidRow(
        email=email,
        domain=domain,
        first_name=_clean(raw, "first_name"),
        last_name=_clean(raw, "last_name"),
        job_title=_clean(raw, "job_title"),
    )


def parse_csv(content: bytes) -> list[dict[str, Any]]:
    """Parse CSV bytes into row dicts. A file-level problem (not UTF-8, no header, missing
    required columns) raises ValidationFailed; row-level problems are handled per row later.
    Lines that are completely empty are not rows and are ignored by the csv module."""
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValidationFailed("file is not valid UTF-8") from exc

    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValidationFailed("file is empty: no header row")
    fieldnames = [(f or "").strip().lower() for f in reader.fieldnames]
    missing = [c for c in REQUIRED_COLUMNS if c not in fieldnames]
    if missing:
        raise ValidationFailed(f"missing required column(s): {', '.join(missing)}")
    reader.fieldnames = fieldnames

    rows: list[dict[str, Any]] = []
    for record in reader:
        # Extra cells beyond the header land under key None; keep them out of the payload keys.
        extra = record.pop(None, None)
        row: dict[str, Any] = dict(record)
        if extra:
            row["_extra_cells"] = extra
        rows.append(row)
    return rows


def _upsert_company(session: Session, domain: str) -> Company:
    session.execute(
        pg_insert(Company)
        .values(domain=domain, enrichment_status="pending")
        .on_conflict_do_nothing(index_elements=[Company.domain])
    )
    return session.execute(select(Company).where(Company.domain == domain)).scalar_one()


def _upsert_lead(session: Session, row: ValidRow, company_id: int) -> int:
    insert_stmt = pg_insert(Lead).values(
        email=row.email,
        first_name=row.first_name,
        last_name=row.last_name,
        job_title=row.job_title,
        company_id=company_id,
    )
    upsert = insert_stmt.on_conflict_do_update(
        index_elements=[Lead.email],
        set_={
            # A re-import never blanks out data that was previously known.
            "first_name": func.coalesce(insert_stmt.excluded.first_name, Lead.first_name),
            "last_name": func.coalesce(insert_stmt.excluded.last_name, Lead.last_name),
            "job_title": func.coalesce(insert_stmt.excluded.job_title, Lead.job_title),
            "company_id": insert_stmt.excluded.company_id,
            "updated_at": func.now(),
        },
    ).returning(Lead.id)
    return int(session.execute(upsert).scalar_one())


def import_rows(
    session: Session,
    *,
    source: str,
    filename: str | None,
    rows: Sequence[Mapping[str, Any]],
) -> ImportBatch:
    """The single import code path used by both CSV and API imports.

    Invalid rows are recorded in import_row_errors, never dropped. Valid rows upsert the
    lead (by email) and company (by domain), then jobs are enqueued. The caller commits."""
    batch = ImportBatch(source=source, filename=filename, total_rows=len(rows))
    session.add(batch)
    session.flush()

    companies: dict[str, Company] = {}
    lead_ids: dict[str, int] = {}
    accepted = 0

    for number, raw in enumerate(rows, start=1):
        try:
            valid = validate_row(raw)
        except RowInvalid as exc:
            session.add(
                ImportRowError(
                    batch_id=batch.id, row_number=number, reason=str(exc), raw_payload=dict(raw)
                )
            )
            continue
        company = companies.get(valid.domain) or _upsert_company(session, valid.domain)
        companies[valid.domain] = company
        lead_ids[valid.email] = _upsert_lead(session, valid, company.id)
        accepted += 1

    batch.accepted_rows = accepted
    batch.rejected_rows = len(rows) - accepted

    for company in companies.values():
        if company.enrichment_status == "pending":
            enqueue_job(session, "enrich_company", {"company_id": company.id})
    for lead_id in lead_ids.values():
        enqueue_job(session, "score_lead", {"lead_id": lead_id})

    session.flush()
    return batch
