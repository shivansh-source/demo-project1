"""Database glue for scoring: read facts, compute, append a new lead_scores row."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.core.errors import NotFoundError
from app.models import Lead, LeadScore
from app.services.scoring.config import ScoringConfig
from app.services.scoring.engine import ScoringInput, compute_score


def score_lead_now(
    session: Session, lead_id: int, config: ScoringConfig, *, reasoning_status: str
) -> tuple[Lead, LeadScore]:
    """Compute a score and insert it as a NEW row (history is never overwritten)."""
    lead = session.get(Lead, lead_id)
    if lead is None:
        raise NotFoundError(f"lead {lead_id} not found")
    company = lead.company
    result = compute_score(
        ScoringInput(
            employee_count=company.employee_count,
            industry=company.industry,
            job_title=lead.job_title,
        ),
        config,
    )
    row = LeadScore(
        lead_id=lead.id,
        score=result.score,
        rule_breakdown=result.breakdown,
        rules_version=result.rules_version,
        reasoning_status=reasoning_status,
    )
    session.add(row)
    session.flush()
    return lead, row
