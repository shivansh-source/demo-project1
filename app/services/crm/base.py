from typing import Protocol

from app.models import Lead, LeadScore


def idempotency_key(lead_id: int, score_id: int) -> str:
    return f"{lead_id}:{score_id}"


class CrmClient(Protocol):
    """Creates or updates a lead in the CRM and returns the CRM's external id.

    Implementations should be upserts (keyed by email) so that an unlucky retry after a
    crash cannot create a duplicate record."""

    async def upsert_lead(self, lead: Lead, score: LeadScore, segment: str) -> str: ...
