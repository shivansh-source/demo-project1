from app.core.config import Settings
from app.services.crm.base import CrmClient, idempotency_key
from app.services.crm.mock import MockCrm

__all__ = ["CrmClient", "MockCrm", "get_crm", "idempotency_key"]


def get_crm(settings: Settings) -> CrmClient:
    """Pick the CRM named by CRM_PROVIDER. Real adapters register here."""
    if settings.crm_provider == "mock":
        return MockCrm()
    raise ValueError(f"unknown CRM_PROVIDER: {settings.crm_provider!r}")
