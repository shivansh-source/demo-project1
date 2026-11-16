"""Pure scoring rules: facts + config in, points + a human-readable reason out. No I/O."""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.services.scoring.config import (
    CompanySizeRule,
    EngagementRule,
    IndustryFitRule,
    SeniorityRule,
)


@dataclass(frozen=True)
class RuleResult:
    rule: str
    points: int
    reason: str


def company_size(employee_count: int | None, rule: CompanySizeRule) -> RuleResult:
    if employee_count is None:
        return RuleResult("company_size", 0, "company size unknown")
    for band in rule.bands:
        if band.max_employees is None or employee_count <= band.max_employees:
            upper = "any size" if band.max_employees is None else f"<= {band.max_employees}"
            return RuleResult(
                "company_size", band.points, f"{employee_count} employees (band {upper})"
            )
    return RuleResult("company_size", 0, f"{employee_count} employees (no matching band)")


def industry_fit(industry: str | None, rule: IndustryFitRule) -> RuleResult:
    if not industry:
        return RuleResult("industry_fit", rule.default, "industry unknown")
    table = {k.lower(): v for k, v in rule.industries.items()}
    key = industry.strip().lower()
    if key in table:
        return RuleResult("industry_fit", table[key], f"industry {industry!r} is a target")
    return RuleResult("industry_fit", rule.default, f"industry {industry!r} is not a target")


def _contains_word(title: str, keyword: str) -> bool:
    pattern = r"(?<![a-z0-9])" + re.escape(keyword.lower()) + r"(?![a-z0-9])"
    return re.search(pattern, title.lower()) is not None


def seniority(job_title: str | None, rule: SeniorityRule) -> RuleResult:
    if not job_title:
        return RuleResult("seniority", rule.default, "job title missing")
    best: tuple[int, str] | None = None
    for tier in rule.tiers:
        for keyword in tier.keywords:
            if _contains_word(job_title, keyword) and (best is None or tier.points > best[0]):
                best = (tier.points, keyword)
    if best is None:
        return RuleResult("seniority", rule.default, f"no seniority keyword in {job_title!r}")
    return RuleResult("seniority", best[0], f"title {job_title!r} matches {best[1]!r}")


def engagement(rule: EngagementRule) -> RuleResult:
    return RuleResult("engagement", rule.default, "no engagement data")
