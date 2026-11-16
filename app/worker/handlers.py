"""Job handlers. A handler does its work in the given session and must not commit: the runner
commits handler effects and the job's `done` status in one transaction."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from app.models import Company, Lead, LeadScore
from app.queue.enqueue import enqueue_job, has_active_job
from app.queue.errors import DeferJob
from app.services.crm.push import push_lead
from app.services.reasoning import ReasoningInput
from app.services.scoring.service import score_lead_now
from app.services.segmentation import HOT, segment_for
from app.worker.context import HandlerContext

Handler = Callable[[Session, dict[str, Any], HandlerContext], None]


def enrich_company(session: Session, payload: dict[str, Any], ctx: HandlerContext) -> None:
    company = session.get(Company, payload["company_id"])
    if company is None or company.enrichment_status != "pending":
        return  # deleted, or already handled by an earlier job: nothing to do
    data = asyncio.run(ctx.enrichment.enrich(company.domain))
    if data is None:
        company.enrichment_status = "not_found"
    else:
        company.name = data.name
        company.employee_count = data.employee_count
        company.industry = data.industry
        company.country = data.country
        company.enrichment_status = "enriched"
    company.enriched_at = datetime.now(UTC)
    company.enrichment_source = ctx.enrichment.name


def score_lead(session: Session, payload: dict[str, Any], ctx: HandlerContext) -> None:
    lead = session.get(Lead, payload["lead_id"])
    if lead is None:
        return
    company = lead.company
    if company.enrichment_status == "pending" and has_active_job(
        "enrich_company", {"company_id": company.id}
    ):
        # Score with real company data: wait (without using an attempt) for enrichment. If the
        # enrichment job has failed for good there is no active job, so we score anyway.
        raise DeferJob(ctx.settings.score_defer_seconds, "waiting for company enrichment")
    reasoning_status = "pending" if ctx.reasoner is not None else "skipped"
    _, score = score_lead_now(session, lead.id, ctx.scoring, reasoning_status=reasoning_status)
    segment = segment_for(score.score, ctx.scoring.thresholds)
    lead.segment = segment
    if ctx.reasoner is not None:
        enqueue_job(session, "reason_lead", {"score_id": score.id})
    if segment == HOT:
        enqueue_job(session, "push_crm", {"lead_id": lead.id, "score_id": score.id})


def reason_lead(session: Session, payload: dict[str, Any], ctx: HandlerContext) -> None:
    """Fill in the LLM explanation. Any failure raises, so the runner retries with backoff and
    the score row stays as it is (reasoning_status stays "pending")."""
    score = session.get(LeadScore, payload["score_id"])
    if score is None or score.reasoning_status == "ok":
        return
    if ctx.reasoner is None:
        score.reasoning_status = "skipped"
        return
    lead = session.get_one(Lead, score.lead_id)
    company = lead.company
    score.reasoning = ctx.reasoner.explain(
        ReasoningInput(
            score=score.score,
            segment=segment_for(score.score, ctx.scoring.thresholds),
            breakdown=score.rule_breakdown,
            job_title=lead.job_title,
            company_name=company.name,
            industry=company.industry,
            employee_count=company.employee_count,
            country=company.country,
        )
    )
    score.reasoning_status = "ok"


def reason_lead_exhausted(session: Session, payload: dict[str, Any]) -> None:
    """All retries used up: keep the score, mark the explanation as failed."""
    score = session.get(LeadScore, payload["score_id"])
    if score is not None and score.reasoning_status != "ok":
        score.reasoning_status = "failed"


def push_crm(session: Session, payload: dict[str, Any], ctx: HandlerContext) -> None:
    lead = session.get(Lead, payload["lead_id"])
    score = session.get(LeadScore, payload["score_id"])
    if lead is None or score is None:
        return
    # Decide from the score being pushed, not lead.segment, which a newer score may have changed.
    push_lead(session, ctx.crm, lead, score, segment_for(score.score, ctx.scoring.thresholds))


HANDLERS: dict[str, Handler] = {
    "enrich_company": enrich_company,
    "score_lead": score_lead,
    "reason_lead": reason_lead,
    "push_crm": push_crm,
}

# Called once a job has failed for good (after max_attempts), in its own transaction.
FinalFailureHook = Callable[[Session, dict[str, Any]], None]
FINAL_FAILURE_HOOKS: dict[str, FinalFailureHook] = {
    "reason_lead": reason_lead_exhausted,
}
