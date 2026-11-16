"""Idempotent CRM push."""

from __future__ import annotations

import asyncio

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from app.models import CrmPush, Lead, LeadScore
from app.services.crm.base import CrmClient, idempotency_key
from app.services.segmentation import HOT


def push_lead(session: Session, crm: CrmClient, lead: Lead, score: LeadScore, segment: str) -> bool:
    """Push a hot lead once per (lead, score). Returns True if the CRM was called.

    The key is claimed with INSERT ... ON CONFLICT DO NOTHING *before* calling the CRM. A repeat
    (or a concurrent worker, which blocks on the unique index until the first transaction ends)
    gets no row back and never reaches the CRM. If the CRM call raises, the transaction rolls
    back, the claim disappears, and the job retry starts clean. The caller commits."""
    if segment != HOT:
        return False
    key = idempotency_key(lead.id, score.id)
    claimed = session.execute(
        pg_insert(CrmPush)
        .values(lead_id=lead.id, score_id=score.id, status="pending", idempotency_key=key)
        .on_conflict_do_nothing(index_elements=[CrmPush.idempotency_key])
        .returning(CrmPush.id)
    ).scalar_one_or_none()
    if claimed is None:
        return False
    external_id = asyncio.run(crm.upsert_lead(lead, score, segment))
    push = session.get_one(CrmPush, claimed)
    push.status = "pushed"
    push.external_id = external_id
    return True
