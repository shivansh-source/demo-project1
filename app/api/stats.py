"""Numbers for the dashboard and the live pipeline view."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import Select, distinct, func, select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.models import Company, CrmPush, Lead, LeadScore

router = APIRouter(prefix="/stats", tags=["stats"])


class PipelineCounts(BaseModel):
    imported: int
    enriched: int
    scored: int
    explained: int
    pushed: int


class HotLead(BaseModel):
    lead_id: int
    name: str | None
    email: str
    job_title: str | None
    company: str | None
    score: int
    reasoning: str | None


class Stats(BaseModel):
    pipeline: PipelineCounts
    segments: dict[str, int]
    hot_leads: list[HotLead]


def _count(session: Session, query: Select[tuple[int]]) -> int:
    return session.scalar(query) or 0


@router.get("", response_model=Stats)
def stats(
    session: Annotated[Session, Depends(get_session)],
    since: Annotated[
        datetime | None, Query(description="Only leads created at or after this time")
    ] = None,
) -> Stats:
    """How many leads reached each pipeline stage, segment counts, and the top hot leads.
    With `since`, only leads created from that moment on (used by the live demo)."""
    leads = select(Lead.id)
    if since is not None:
        leads = leads.where(Lead.created_at >= since)
    ids = leads.scalar_subquery()

    pipeline = PipelineCounts(
        imported=_count(session, select(func.count()).where(Lead.id.in_(ids))),
        enriched=_count(
            session,
            select(func.count())
            .select_from(Lead)
            .join(Company, Company.id == Lead.company_id)
            .where(Lead.id.in_(ids), Company.enrichment_status != "pending"),
        ),
        scored=_count(
            session,
            select(func.count(distinct(LeadScore.lead_id))).where(LeadScore.lead_id.in_(ids)),
        ),
        explained=_count(
            session,
            select(func.count(distinct(LeadScore.lead_id))).where(
                LeadScore.lead_id.in_(ids), LeadScore.reasoning_status == "ok"
            ),
        ),
        pushed=_count(
            session,
            select(func.count(distinct(CrmPush.lead_id))).where(
                CrmPush.lead_id.in_(ids), CrmPush.status == "pushed"
            ),
        ),
    )

    segments = {"hot": 0, "nurture": 0, "disqualified": 0}
    for segment, n in session.execute(
        select(Lead.segment, func.count())
        .where(Lead.id.in_(ids), Lead.segment.is_not(None))
        .group_by(Lead.segment)
    ):
        segments[str(segment)] = int(n)

    latest = (
        select(LeadScore.lead_id, func.max(LeadScore.id).label("score_id"))
        .group_by(LeadScore.lead_id)
        .subquery()
    )
    rows = session.execute(
        select(Lead, Company, LeadScore)
        .join(Company, Company.id == Lead.company_id)
        .join(latest, latest.c.lead_id == Lead.id)
        .join(LeadScore, LeadScore.id == latest.c.score_id)
        .where(Lead.id.in_(ids), Lead.segment == "hot")
        .order_by(LeadScore.score.desc(), Lead.id.desc())
        .limit(6)
    ).all()
    hot = [
        HotLead(
            lead_id=lead.id,
            name=" ".join(p for p in (lead.first_name, lead.last_name) if p) or None,
            email=lead.email,
            job_title=lead.job_title,
            company=company.name or company.domain,
            score=score.score,
            reasoning=score.reasoning,
        )
        for lead, company, score in rows
    ]
    return Stats(pipeline=pipeline, segments=segments, hot_leads=hot)
