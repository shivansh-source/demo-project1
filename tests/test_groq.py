import json
from typing import Any

import httpx
import pytest

from app.core.config import DEFAULT_GROQ_MODEL, Settings
from app.services.reasoning import SYSTEM_PROMPT, GroqReasoner, ReasoningInput, build_reasoner

FACTS = ReasoningInput(
    score=88,
    segment="hot",
    breakdown={"rules": {"seniority": {"points": 40, "reason": "CEO"}}},
    job_title="CEO",
    company_name="Acme",
    industry="software",
    employee_count=300,
    country="US",
)


def reasoner(status: int = 200, body: Any = None) -> tuple[GroqReasoner, list[httpx.Request]]:
    seen: list[httpx.Request] = []
    payload = (
        body
        if body is not None
        else {"choices": [{"message": {"content": "**Hot** lead: senior buyer. Good fit. Extra."}}]}
    )

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json=payload)

    return GroqReasoner("gsk-test", "m1", 99, transport=httpx.MockTransport(handler)), seen


def test_groq_request_shape_and_cleaned_reply() -> None:
    r, seen = reasoner()
    assert r.explain(FACTS) == "Hot lead: senior buyer. Good fit."
    (req,) = seen
    assert str(req.url) == "https://api.groq.com/openai/v1/chat/completions"
    assert req.headers["authorization"] == "Bearer gsk-test"
    body = json.loads(req.content)
    assert body["model"] == "m1" and body["max_tokens"] == 99
    assert "reasoning_effort" not in body  # only sent for gpt-oss models
    assert body["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert "@" not in body["messages"][1]["content"]  # no personal identifiers are sent


def test_groq_errors_are_raised_so_the_job_retries() -> None:
    r, _ = reasoner(429, {"error": {"message": "rate limited"}})
    with pytest.raises(RuntimeError, match="Groq returned 429"):
        r.explain(FACTS)
    r, _ = reasoner(200, {"choices": []})
    with pytest.raises(RuntimeError, match="no message content"):
        r.explain(FACTS)
    r, _ = reasoner(200, {"choices": [{"message": {"content": "  "}}]})
    with pytest.raises(ValueError, match="empty"):
        r.explain(FACTS)


def _cfg(**kw: Any) -> Settings:
    return Settings(_env_file=None, **kw)  # type: ignore[call-arg]


def test_build_reasoner_defaults_to_groq_and_needs_a_key() -> None:
    assert build_reasoner(_cfg()) is None
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        build_reasoner(_cfg(reasoning_enabled=True))
    built = build_reasoner(_cfg(reasoning_enabled=True, groq_api_key="k"))
    assert isinstance(built, GroqReasoner)
    assert _cfg().groq_model == DEFAULT_GROQ_MODEL


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(ValueError, match="unknown REASONING_PROVIDER"):
        build_reasoner(_cfg(reasoning_enabled=True, reasoning_provider="nope"))


def test_gpt_oss_models_get_low_reasoning_effort() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Good lead."}}]})

    r = GroqReasoner("k", "openai/gpt-oss-20b", 150, transport=httpx.MockTransport(handler))
    assert r.explain(FACTS) == "Good lead."
    assert json.loads(seen[0].content)["reasoning_effort"] == "low"
