from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.errors import NotFoundError
from app.models import Lead, LeadScore
from app.queue.enqueue import enqueue_job
from app.schemas.leads import LeadDetail, LeadList, LeadSummary, RescoreOut, ScoreOut

router = APIRouter(prefix="/leads", tags=["leads"])

SessionDep = Annotated[Session, Depends(get_session)]


def _get_lead(session: Session, lead_id: int) -> Lead:
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise NotFoundError(f"lead {lead_id} not found")
    return lead


def _latest_score(session: Session, lead_id: int) -> LeadScore | None:
    return session.scalars(
        select(LeadScore)
        .where(LeadScore.lead_id == lead_id)
        .order_by(LeadScore.created_at.desc(), LeadScore.id.desc())
        .limit(1)
    ).first()


@router.get("", response_model=LeadList)
def list_leads(
    session: SessionDep,
    segment: Literal["hot", "nurture", "disqualified"] | None = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> LeadList:
    query = select(Lead)
    if segment is not None:
        query = query.where(Lead.segment == segment)
    total = session.scalar(select(func.count()).select_from(query.subquery())) or 0
    rows = session.scalars(query.order_by(Lead.id).limit(limit).offset(offset)).all()
    return LeadList(
        items=[LeadSummary.model_validate(r) for r in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{lead_id}", response_model=LeadDetail)
def get_lead(lead_id: int, session: SessionDep) -> LeadDetail:
    """The lead, its company, and the latest score with breakdown and reasoning."""
    lead = _get_lead(session, lead_id)
    latest = _latest_score(session, lead_id)
    return LeadDetail.model_validate(
        {
            **LeadSummary.model_validate(lead).model_dump(),
            "company": lead.company,
            "latest_score": latest,
        }
    )


@router.get("/{lead_id}/scores", response_model=list[ScoreOut])
def score_history(lead_id: int, session: SessionDep) -> list[ScoreOut]:
    """Every score ever computed for the lead, newest first."""
    _get_lead(session, lead_id)
    rows = session.scalars(
        select(LeadScore)
        .where(LeadScore.lead_id == lead_id)
        .order_by(LeadScore.created_at.desc(), LeadScore.id.desc())
    ).all()
    return [ScoreOut.model_validate(r) for r in rows]


@router.post("/{lead_id}/rescore", response_model=RescoreOut, status_code=202)
def rescore(lead_id: int, session: SessionDep) -> RescoreOut:
    """Queue a fresh scoring run. If one is already queued the request is a no-op."""
    _get_lead(session, lead_id)
    job_id = enqueue_job(session, "score_lead", {"lead_id": lead_id})
    session.commit()  # the job is sent to Redis after this commit
    return RescoreOut(lead_id=lead_id, job_id=job_id, queued=job_id is not None)
