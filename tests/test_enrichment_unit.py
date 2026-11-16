import asyncio

import pytest

from app.core.config import Settings
from app.queue.enqueue import backoff_seconds
from app.services.enrichment import MockEnrichmentProvider, get_enrichment_provider
from app.services.enrichment.mock import COUNTRIES, EMPLOYEE_COUNTS, INDUSTRIES


def _enrich(domain: str):  # type: ignore[no-untyped-def]
    return asyncio.run(MockEnrichmentProvider().enrich(domain))


def test_mock_is_deterministic() -> None:
    assert _enrich("acme.com") == _enrich("acme.com")


def test_mock_output_is_in_known_ranges_and_varies_by_domain() -> None:
    results = [_enrich(f"company{i}.com") for i in range(40)]
    assert all(r is not None for r in results)
    for r in results:
        assert r is not None
        assert r.employee_count in EMPLOYEE_COUNTS
        assert r.industry in INDUSTRIES
        assert r.country in COUNTRIES
    assert len({r.industry for r in results if r}) > 1
    assert len({r.employee_count for r in results if r}) > 1


def test_mock_name_comes_from_domain_label() -> None:
    result = _enrich("big-corp.io")
    assert result is not None and result.name == "Big Corp"


def test_mock_unknown_domain_returns_none() -> None:
    assert _enrich("ghost.invalid") is None


def test_provider_factory() -> None:
    assert get_enrichment_provider(Settings(_env_file=None)).name == "mock"  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="unknown ENRICHMENT_PROVIDER"):
        get_enrichment_provider(Settings(_env_file=None, enrichment_provider="nope"))  # type: ignore[call-arg]


def test_backoff_is_exponential_and_capped() -> None:
    assert [backoff_seconds(n, 2) for n in (1, 2, 3, 4)] == [2, 4, 8, 16]
    assert backoff_seconds(50, 2) == 3600
