from app.core.config import Settings
from app.services.enrichment.base import CompanyData, EnrichmentProvider
from app.services.enrichment.mock import MockEnrichmentProvider

__all__ = ["CompanyData", "EnrichmentProvider", "MockEnrichmentProvider", "get_enrichment_provider"]


def get_enrichment_provider(settings: Settings) -> EnrichmentProvider:
    """Pick the provider named by ENRICHMENT_PROVIDER. Real providers register here."""
    if settings.enrichment_provider == "mock":
        return MockEnrichmentProvider()
    raise ValueError(f"unknown ENRICHMENT_PROVIDER: {settings.enrichment_provider!r}")
