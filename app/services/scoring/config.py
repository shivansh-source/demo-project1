"""Loads and validates config/scoring.yaml; computes rules_version from the raw file bytes."""

from __future__ import annotations

import hashlib
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.errors import ValidationFailed


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SizeBand(_Strict):
    max_employees: int | None = Field(default=None, ge=0)
    points: int = Field(ge=0)


class CompanySizeRule(_Strict):
    bands: list[SizeBand]

    @model_validator(mode="after")
    def _ordered(self) -> CompanySizeRule:
        bounded = [b.max_employees for b in self.bands if b.max_employees is not None]
        if bounded != sorted(bounded):
            raise ValueError("company_size bands must be in ascending max_employees order")
        if any(b.max_employees is None for b in self.bands[:-1]):
            raise ValueError("only the last company_size band may omit max_employees")
        return self


class IndustryFitRule(_Strict):
    industries: dict[str, int]
    default: int = 0


class SeniorityTier(_Strict):
    points: int = Field(ge=0)
    keywords: list[str] = Field(min_length=1)


class SeniorityRule(_Strict):
    tiers: list[SeniorityTier]
    default: int = 0


class EngagementRule(_Strict):
    default: int = 0


class Rules(_Strict):
    company_size: CompanySizeRule
    industry_fit: IndustryFitRule
    seniority: SeniorityRule
    engagement: EngagementRule


class Thresholds(_Strict):
    hot: int = Field(ge=0, le=100)
    nurture: int = Field(ge=0, le=100)

    @model_validator(mode="after")
    def _ordered(self) -> Thresholds:
        if self.nurture >= self.hot:
            raise ValueError("thresholds.nurture must be lower than thresholds.hot")
        return self


class ScoringConfig(_Strict):
    thresholds: Thresholds
    rules: Rules
    rules_version: str = ""


def parse_scoring_config(raw: bytes) -> ScoringConfig:
    try:
        data = yaml.safe_load(raw)
        config = ScoringConfig.model_validate(data)
    except (yaml.YAMLError, ValueError) as exc:
        raise ValidationFailed(f"invalid scoring config: {exc}") from exc
    return config.model_copy(update={"rules_version": hashlib.sha256(raw).hexdigest()})


def load_scoring_config(path: str | Path) -> ScoringConfig:
    return parse_scoring_config(Path(path).read_bytes())
