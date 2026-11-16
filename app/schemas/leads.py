from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    domain: str
    name: str | None
    employee_count: int | None
    industry: str | None
    country: str | None
    enrichment_status: str
    enriched_at: datetime | None
    enrichment_source: str | None


class ScoreOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    lead_id: int
    score: int
    rule_breakdown: dict[str, Any]
    rules_version: str
    reasoning: str | None
    reasoning_status: str
    created_at: datetime


class LeadSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: str
    first_name: str | None
    last_name: str | None
    job_title: str | None
    segment: str | None
    company_id: int
    created_at: datetime
    updated_at: datetime


class LeadDetail(LeadSummary):
    company: CompanyOut
    latest_score: ScoreOut | None


class LeadList(BaseModel):
    items: list[LeadSummary]
    total: int
    limit: int
    offset: int


class RescoreOut(BaseModel):
    lead_id: int
    job_id: str | None
    queued: bool
