from dataclasses import dataclass

from app.models import Lead, LeadScore


@dataclass(frozen=True)
class RecordedPush:
    external_id: str
    email: str
    score: int
    segment: str


class MockCrm:
    """In-memory CRM. Upserts by email like a real one: same email, same external id."""

    def __init__(self) -> None:
        self.pushes: list[RecordedPush] = []
        self._ids: dict[str, str] = {}

    async def upsert_lead(self, lead: Lead, score: LeadScore, segment: str) -> str:
        external_id = self._ids.setdefault(lead.email, f"mock-crm-{len(self._ids) + 1}")
        self.pushes.append(RecordedPush(external_id, lead.email, score.score, segment))
        return external_id
