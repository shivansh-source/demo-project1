import pytest

from app.core.config import DEFAULT_ANTHROPIC_MODEL, Settings


def test_empty_placeholders_fall_back_to_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    for k in ("ENRICHMENT_PROVIDER", "CRM_PROVIDER", "ANTHROPIC_MODEL", "REASONING_ENABLED"):
        monkeypatch.setenv(k, "")
    s = Settings(_env_file=None)  # type: ignore[call-arg]
    assert s.enrichment_provider == "mock"
    assert s.crm_provider == "mock"
    assert s.anthropic_model == DEFAULT_ANTHROPIC_MODEL
    assert s.reasoning_enabled is False
