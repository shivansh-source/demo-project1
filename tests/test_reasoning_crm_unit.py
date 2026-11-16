from types import SimpleNamespace
from typing import Any

import pytest

from app.core.config import Settings
from app.models import Lead, LeadScore
from app.services.crm import MockCrm, get_crm, idempotency_key
from app.services.reasoning import (
    SYSTEM_PROMPT,
    AnthropicReasoner,
    ReasoningInput,
    build_reasoner,
    build_user_prompt,
    limit_sentences,
)

FACTS = ReasoningInput(
    score=90,
    segment="hot",
    breakdown={"rules": {"seniority": {"points": 30, "reason": "VP"}}},
    job_title="VP Sales",
    company_name="Acme",
    industry="software",
    employee_count=300,
    country="US",
)


class FakeMessages:
    def __init__(self, blocks: list[Any] | Exception) -> None:
        self.blocks = blocks
        self.calls: list[dict[str, Any]] = []

    def create(self, **kwargs: Any) -> Any:
        self.calls.append(kwargs)
        if isinstance(self.blocks, Exception):
            raise self.blocks
        return SimpleNamespace(content=self.blocks)


class FakeClient:
    def __init__(self, blocks: list[Any] | Exception) -> None:
        self.messages = FakeMessages(blocks)


def text(value: str) -> SimpleNamespace:
    return SimpleNamespace(type="text", text=value)


def test_limit_sentences_keeps_two_and_strips_markdown() -> None:
    raw = "**Strong fit.** The VP title\nhelps! It is a `software` firm. Extra sentence."
    assert limit_sentences(raw) == "Strong fit. The VP title helps!"
    assert limit_sentences("One sentence only") == "One sentence only"
    assert limit_sentences("   ") == ""


def test_prompt_contains_facts_but_no_personal_identifiers() -> None:
    prompt = build_user_prompt(FACTS)
    assert "VP Sales" in prompt and "software" in prompt and '"score": 90' in prompt
    assert "@" not in prompt  # no emails are sent to the model


def test_reasoner_sends_model_token_cap_and_returns_clean_text() -> None:
    client = FakeClient([text("Great fit. Senior buyer. Third sentence.")])
    reasoner = AnthropicReasoner(client, "some-model", 123)
    assert reasoner.explain(FACTS) == "Great fit. Senior buyer."
    call = client.messages.calls[0]
    assert call["model"] == "some-model" and call["max_tokens"] == 123
    assert call["system"] == SYSTEM_PROMPT
    assert "never suggest a different score" in SYSTEM_PROMPT


def test_reasoner_ignores_non_text_blocks_and_rejects_empty() -> None:
    mixed = FakeClient([SimpleNamespace(type="thinking", thinking="x"), text("Fine.")])
    assert AnthropicReasoner(mixed, "m", 10).explain(FACTS) == "Fine."
    with pytest.raises(ValueError, match="empty"):
        AnthropicReasoner(FakeClient([]), "m", 10).explain(FACTS)


def test_reasoner_propagates_api_errors() -> None:
    reasoner = AnthropicReasoner(FakeClient(RuntimeError("api down")), "m", 10)
    with pytest.raises(RuntimeError, match="api down"):
        reasoner.explain(FACTS)


def _settings(**kw: Any) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[call-arg]


def test_reasoning_disabled_needs_no_api_key() -> None:
    assert build_reasoner(_settings(reasoning_enabled=False, anthropic_api_key="")) is None


def test_reasoning_enabled_requires_a_key() -> None:
    with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
        build_reasoner(_settings(reasoning_enabled=True, anthropic_api_key=""))


def test_reasoning_enabled_builds_reasoner_without_network() -> None:
    r = build_reasoner(_settings(reasoning_enabled=True, anthropic_api_key="test-key"))
    assert isinstance(r, AnthropicReasoner)


def test_idempotency_key_format() -> None:
    assert idempotency_key(12, 34) == "12:34"
    assert idempotency_key(1, 23) != idempotency_key(12, 3)


def test_mock_crm_upserts_by_email() -> None:
    import asyncio

    crm = MockCrm()
    a = Lead(id=1, email="a@x.co")
    b = Lead(id=2, email="b@x.co")
    s = LeadScore(id=1, lead_id=1, score=90)
    ids = [asyncio.run(crm.upsert_lead(x, s, "hot")) for x in (a, b, a)]
    assert ids[0] == ids[2] != ids[1]
    assert len(crm.pushes) == 3


def test_crm_factory() -> None:
    assert isinstance(get_crm(_settings()), MockCrm)
    with pytest.raises(ValueError, match="unknown CRM_PROVIDER"):
        get_crm(_settings(crm_provider="nope"))
