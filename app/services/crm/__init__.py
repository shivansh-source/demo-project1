from app.core.config import Settings
from app.services.crm.base import CrmClient, idempotency_key
from app.services.crm.hubspot import HubSpotCrm
from app.services.crm.mock import MockCrm

__all__ = ["CrmClient", "HubSpotCrm", "MockCrm", "get_crm", "idempotency_key"]


def get_crm(settings: Settings) -> CrmClient:
    """Pick the CRM named by CRM_PROVIDER ("mock" or "hubspot")."""
    if settings.crm_provider == "mock":
        return MockCrm()
    if settings.crm_provider == "hubspot":
        return HubSpotCrm(
            settings.crm_api_token,
            base_url=settings.hubspot_base_url,
            score_property=settings.hubspot_score_property,
            segment_property=settings.hubspot_segment_property,
        )
    raise ValueError(f"unknown CRM_PROVIDER: {settings.crm_provider!r}")
