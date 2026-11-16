"""Applies the config to a lead's facts. Pure and deterministic; no AI, no I/O."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.services.scoring import rules
from app.services.scoring.config import ScoringConfig

MAX_SCORE = 100


@dataclass(frozen=True)
class ScoringInput:
    employee_count: int | None = None
    industry: str | None = None
    job_title: str | None = None


@dataclass(frozen=True)
class ScoreResult:
    score: int
    breakdown: dict[str, Any]
    rules_version: str


def compute_score(facts: ScoringInput, config: ScoringConfig) -> ScoreResult:
    results = [
        rules.company_size(facts.employee_count, config.rules.company_size),
        rules.industry_fit(facts.industry, config.rules.industry_fit),
        rules.seniority(facts.job_title, config.rules.seniority),
        rules.engagement(config.rules.engagement),
    ]
    raw_total = sum(r.points for r in results)
    score = max(0, min(raw_total, MAX_SCORE))
    breakdown: dict[str, Any] = {
        "rules": {r.rule: {"points": r.points, "reason": r.reason} for r in results},
        "raw_total": raw_total,
        "capped": raw_total > MAX_SCORE,
    }
    return ScoreResult(score=score, breakdown=breakdown, rules_version=config.rules_version)
