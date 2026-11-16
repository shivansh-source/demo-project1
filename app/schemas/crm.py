from datetime import datetime

from pydantic import BaseModel


class CrmPushOut(BaseModel):
    id: int
    lead_id: int
    email: str
    name: str | None
    company: str | None
    score: int
    status: str
    external_id: str | None
    created_at: datetime


class CrmOverview(BaseModel):
    provider: str  # "mock" or "hubspot"
    live: bool  # true when pushes go to a real external CRM
    hot_leads: int
    pushed: int
    pushes: list[CrmPushOut]
