from pathlib import Path

import pytest

from app.core.errors import ValidationFailed
from app.services.scoring import rules
from app.services.scoring.config import (
    ScoringConfig,
    Thresholds,
    load_scoring_config,
    parse_scoring_config,
)
from app.services.scoring.engine import ScoringInput, compute_score
from app.services.segmentation import DISQUALIFIED, HOT, NURTURE, segment_for


@pytest.fixture(scope="module")
def config() -> ScoringConfig:
    return load_scoring_config("config/scoring.yaml")


# --- company_size -------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("employees", "points"),
    [
        (1, 5),
        (10, 5),  # upper edge of band 1 is inclusive
        (11, 15),
        (50, 15),
        (51, 25),
        (200, 25),
        (201, 35),
        (1000, 35),
        (1001, 30),  # catch-all band
        (100000, 30),
        (None, 0),
    ],
)
def test_company_size_bands(config: ScoringConfig, employees: int | None, points: int) -> None:
    assert rules.company_size(employees, config.rules.company_size).points == points


# --- industry_fit -------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("industry", "points"),
    [("software", 25), ("SaaS", 25), (" fintech ", 20), ("retail", 0), ("", 0), (None, 0)],
)
def test_industry_fit(config: ScoringConfig, industry: str | None, points: int) -> None:
    assert rules.industry_fit(industry, config.rules.industry_fit).points == points


# --- seniority ----------------------------------------------------------------------------
@pytest.mark.parametrize(
    ("title", "points"),
    [
        ("Founder & CEO", 40),
        ("CTO", 40),
        ("co-founder", 40),
        ("VP of Sales", 30),
        ("Vice President, Growth", 30),
        ("Head of Growth", 30),
        ("director of marketing", 30),
        ("Engineering Manager", 15),
        ("Software Engineer", 0),
        ("Intern", 0),
        ("", 0),
        (None, 0),
        ("Advisor", 0),  # "vp"/"cto" must not match inside other words
        ("Director, reporting to the CEO", 40),  # highest matching tier wins
    ],
)
def test_seniority(config: ScoringConfig, title: str | None, points: int) -> None:
    assert rules.seniority(title, config.rules.seniority).points == points


def test_seniority_requires_whole_words(config: ScoringConfig) -> None:
    assert rules.seniority("Victor Spectacle", config.rules.seniority).points == 0
    assert rules.seniority("Octopus", config.rules.seniority).points == 0  # "cto" inside a word


def test_engagement_defaults_to_zero(config: ScoringConfig) -> None:
    assert rules.engagement(config.rules.engagement).points == 0


# --- engine -------------------------------------------------------------------------------
def test_engine_sums_rules_and_records_breakdown(config: ScoringConfig) -> None:
    result = compute_score(ScoringInput(300, "software", "VP Sales"), config)
    assert result.score == 35 + 25 + 30
    rules_out = result.breakdown["rules"]
    assert {k: v["points"] for k, v in rules_out.items()} == {
        "company_size": 35,
        "industry_fit": 25,
        "seniority": 30,
        "engagement": 0,
    }
    assert all(v["reason"] for v in rules_out.values())
    assert result.breakdown["raw_total"] == 90 and result.breakdown["capped"] is False
    assert result.rules_version == config.rules_version


def test_engine_caps_at_100(config: ScoringConfig) -> None:
    boosted = parse_scoring_config(
        b"""
thresholds: {hot: 70, nurture: 40}
rules:
  company_size: {bands: [{points: 60}]}
  industry_fit: {default: 0, industries: {software: 30}}
  seniority: {default: 0, tiers: [{points: 40, keywords: [ceo]}]}
  engagement: {default: 0}
"""
    )
    result = compute_score(ScoringInput(10, "software", "CEO"), boosted)
    assert result.score == 100
    assert result.breakdown["raw_total"] == 130 and result.breakdown["capped"] is True


def test_engine_with_no_facts_scores_zero(config: ScoringConfig) -> None:
    assert compute_score(ScoringInput(), config).score == 0


def test_engine_is_deterministic(config: ScoringConfig) -> None:
    facts = ScoringInput(75, "fintech", "Head of Data")
    assert compute_score(facts, config) == compute_score(facts, config)


# --- thresholds (segmentation) -----------------------------------------------------------
@pytest.mark.parametrize(
    ("score", "segment"),
    [
        (100, HOT),
        (70, HOT),  # hot >= 70
        (69, NURTURE),
        (40, NURTURE),  # nurture >= 40
        (39, DISQUALIFIED),
        (0, DISQUALIFIED),
    ],
)
def test_threshold_boundaries(config: ScoringConfig, score: int, segment: str) -> None:
    assert segment_for(score, config.thresholds) == segment


def test_thresholds_must_be_ordered() -> None:
    with pytest.raises(ValueError, match="lower than"):
        Thresholds(hot=40, nurture=40)


# --- config & rules_version --------------------------------------------------------------
def test_real_config_loads_with_a_sha256_version(config: ScoringConfig) -> None:
    assert len(config.rules_version) == 64
    assert config.thresholds.hot == 70 and config.thresholds.nurture == 40


def test_rules_version_is_a_hash_of_file_contents() -> None:
    raw = Path("config/scoring.yaml").read_bytes()
    assert parse_scoring_config(raw).rules_version == parse_scoring_config(raw).rules_version
    changed = raw.replace(b"hot: 70", b"hot: 71")
    assert parse_scoring_config(changed).rules_version != parse_scoring_config(raw).rules_version
    # even a comment-only edit changes the version: it is a hash of the bytes
    assert (
        parse_scoring_config(raw + b"\n# note").rules_version
        != parse_scoring_config(raw).rules_version
    )


@pytest.mark.parametrize(
    "mutate",
    [
        lambda raw: raw.replace(b"hot: 70", b"hot: 30"),  # hot below nurture
        lambda raw: raw.replace(b"{ max_employees: 10,", b"{ max_employees: 5000,"),  # unordered
        lambda raw: raw + b"\nunknown_key: 1\n",
        lambda raw: b"not: [valid",
        lambda raw: b"",
    ],
)
def test_invalid_config_is_rejected(mutate) -> None:  # type: ignore[no-untyped-def]
    raw = Path("config/scoring.yaml").read_bytes()
    with pytest.raises(ValidationFailed, match="invalid scoring config"):
        parse_scoring_config(mutate(raw))
