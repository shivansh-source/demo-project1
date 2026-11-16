from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import get_session
from app.models import Company, CrmPush, Lead, LeadScore
from app.schemas.crm import CrmOverview, CrmPushOut

router = APIRouter(prefix="/crm", tags=["crm"])


@router.get("", response_model=CrmOverview)
def crm_overview(
    session: Annotated[Session, Depends(get_session)],
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> CrmOverview:
    """Which CRM is connected and what has been pushed to it (newest first)."""
    provider = get_settings().crm_provider
    rows = session.execute(
        select(CrmPush, Lead, LeadScore, Company)
        .join(Lead, Lead.id == CrmPush.lead_id)
        .join(LeadScore, LeadScore.id == CrmPush.score_id)
        .join(Company, Company.id == Lead.company_id)
        .order_by(CrmPush.id.desc())
        .limit(limit)
    ).all()
    pushes = [
        CrmPushOut(
            id=push.id,
            lead_id=lead.id,
            email=lead.email,
            name=" ".join(p for p in (lead.first_name, lead.last_name) if p) or None,
            company=company.name or company.domain,
            score=score.score,
            status=push.status,
            external_id=push.external_id,
            created_at=push.created_at,
        )
        for push, lead, score, company in rows
    ]
    hot = session.scalar(select(func.count()).select_from(Lead).where(Lead.segment == "hot")) or 0
    pushed = (
        session.scalar(
            select(func.count(func.distinct(CrmPush.lead_id))).where(CrmPush.status == "pushed")
        )
        or 0
    )
    return CrmOverview(
        provider=provider, live=provider != "mock", hot_leads=hot, pushed=pushed, pushes=pushes
    )
