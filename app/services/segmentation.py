"""Maps a score to a segment using the thresholds from scoring.yaml."""

from __future__ import annotations

from app.services.scoring.config import Thresholds

HOT = "hot"
NURTURE = "nurture"
DISQUALIFIED = "disqualified"


def segment_for(score: int, thresholds: Thresholds) -> str:
    if score >= thresholds.hot:
        return HOT
    if score >= thresholds.nurture:
        return NURTURE
    return DISQUALIFIED
