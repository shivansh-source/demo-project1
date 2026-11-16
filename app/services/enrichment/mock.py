import hashlib

from app.services.enrichment.base import CompanyData

INDUSTRIES = (
    "software",
    "saas",
    "fintech",
    "healthcare",
    "manufacturing",
    "retail",
    "education",
    "logistics",
    "media",
    "consulting",
)
COUNTRIES = ("US", "GB", "DE", "FR", "IN", "CA", "AU", "SG", "BR", "NL")
EMPLOYEE_COUNTS = (3, 8, 15, 40, 75, 150, 300, 800, 2500, 12000)


class MockEnrichmentProvider:
    """Deterministic fake: the same domain always yields the same data, so tests are repeatable.
    Domains ending in `.invalid` are reported as unknown (returns None)."""

    name = "mock"

    async def enrich(self, domain: str) -> CompanyData | None:
        if domain.endswith(".invalid"):
            return None
        digest = hashlib.sha256(domain.encode()).digest()
        label = domain.split(".")[0]
        return CompanyData(
            name=label.replace("-", " ").title(),
            employee_count=EMPLOYEE_COUNTS[digest[0] % len(EMPLOYEE_COUNTS)],
            industry=INDUSTRIES[digest[1] % len(INDUSTRIES)],
            country=COUNTRIES[digest[2] % len(COUNTRIES)],
        )
