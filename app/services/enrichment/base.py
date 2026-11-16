from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class CompanyData:
    name: str
    employee_count: int
    industry: str
    country: str


class EnrichmentProvider(Protocol):
    """Looks up firmographic data for a company domain.

    Return None when the provider has no data for the domain (a normal outcome, recorded as
    `not_found`). Raise for transient failures so the job is retried."""

    name: str

    async def enrich(self, domain: str) -> CompanyData | None: ...
