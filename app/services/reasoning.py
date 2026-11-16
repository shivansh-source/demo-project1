"""LLM explanation step. The model explains a score that rules already computed; it never
sets or changes it, and it is only ever shown facts, never asked for a number."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Protocol

import anthropic

from app.core.config import Settings

MAX_SENTENCES = 2
CLIENT_TIMEOUT_SECONDS = 20.0

SYSTEM_PROMPT = (
    "You explain lead-scoring results to a sales rep. The score was already computed by fixed "
    "rules and is final: never suggest a different score or contradict the breakdown. "
    "Reply with at most two plain-text sentences: no markdown, no lists, no preamble. "
    "Mention the factors that contributed most to the score."
)


@dataclass(frozen=True)
class ReasoningInput:
    score: int
    segment: str
    breakdown: dict[str, Any]
    job_title: str | None
    company_name: str | None
    industry: str | None
    employee_count: int | None
    country: str | None


class Reasoner(Protocol):
    def explain(self, facts: ReasoningInput) -> str: ...


def build_user_prompt(facts: ReasoningInput) -> str:
    payload = {
        "score": facts.score,
        "segment": facts.segment,
        "rule_breakdown": facts.breakdown.get("rules", {}),
        "lead": {"job_title": facts.job_title},
        "company": {
            "name": facts.company_name,
            "industry": facts.industry,
            "employee_count": facts.employee_count,
            "country": facts.country,
        },
    }
    return "Explain this result:\n" + json.dumps(payload, indent=2)


def limit_sentences(text: str, limit: int = MAX_SENTENCES) -> str:
    """Strip markdown noise and keep at most `limit` sentences."""
    cleaned = re.sub(r"[*_`#>]+", "", text)
    cleaned = " ".join(cleaned.split())
    sentences = re.split(r"(?<=[.!?])\s+", cleaned)
    return " ".join(sentences[:limit]).strip()


class AnthropicReasoner:
    # `client` is an anthropic.Anthropic (or any object with .messages.create); typed Any so tests
    # can pass a fake without importing SDK internals.
    def __init__(self, client: Any, model: str, max_tokens: int) -> None:
        self._client = client
        self._model = model
        self._max_tokens = max_tokens

    def explain(self, facts: ReasoningInput) -> str:
        response = self._client.messages.create(
            model=self._model,
            max_tokens=self._max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": build_user_prompt(facts)}],
        )
        text = "".join(
            block.text for block in response.content if getattr(block, "type", "") == "text"
        )
        explanation = limit_sentences(text)
        if not explanation:
            raise ValueError("model returned an empty explanation")
        return explanation


def build_reasoner(settings: Settings) -> Reasoner | None:
    """None when REASONING_ENABLED=false: the system then needs no API key at all."""
    if not settings.reasoning_enabled:
        return None
    if not settings.anthropic_api_key:
        raise ValueError("REASONING_ENABLED=true requires ANTHROPIC_API_KEY")
    client = anthropic.Anthropic(api_key=settings.anthropic_api_key, timeout=CLIENT_TIMEOUT_SECONDS)
    return AnthropicReasoner(client, settings.anthropic_model, settings.reasoning_max_tokens)
