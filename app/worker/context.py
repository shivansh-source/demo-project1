from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.crm import CrmClient
from app.services.enrichment import EnrichmentProvider
from app.services.reasoning import Reasoner
from app.services.scoring.config import ScoringConfig


@dataclass
class HandlerContext:
    """Everything a job handler may depend on. Built once at worker start-up; tests inject fakes."""

    settings: Settings
    enrichment: EnrichmentProvider
    scoring: ScoringConfig
    crm: CrmClient
    reasoner: Reasoner | None = None  # None <=> REASONING_ENABLED=false


SessionFactory = Callable[[], Session]
