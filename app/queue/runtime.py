"""What a job needs to run: handlers, their dependencies and a session factory."""

from __future__ import annotations

from dataclasses import dataclass

from app.core.config import get_settings
from app.core.db import get_sessionmaker
from app.services.crm import get_crm
from app.services.enrichment import get_enrichment_provider
from app.services.reasoning import build_reasoner
from app.services.scoring.config import load_scoring_config
from app.worker.context import HandlerContext, SessionFactory
from app.worker.handlers import FINAL_FAILURE_HOOKS, HANDLERS, FinalFailureHook, Handler


@dataclass
class Runtime:
    session_factory: SessionFactory
    ctx: HandlerContext
    handlers: dict[str, Handler]
    final_failure_hooks: dict[str, FinalFailureHook]


_runtime: Runtime | None = None


def build_runtime() -> Runtime:
    """Builds providers from settings. Raises on bad config (e.g. reasoning on, no API key),
    so the worker can fail at start-up rather than on the first job."""
    settings = get_settings()
    ctx = HandlerContext(
        settings=settings,
        enrichment=get_enrichment_provider(settings),
        scoring=load_scoring_config(settings.scoring_config_path),
        crm=get_crm(settings),
        reasoner=build_reasoner(settings),
    )
    return Runtime(get_sessionmaker(), ctx, dict(HANDLERS), dict(FINAL_FAILURE_HOOKS))


def get_runtime() -> Runtime:
    global _runtime
    if _runtime is None:
        _runtime = build_runtime()
    return _runtime


def set_runtime(runtime: Runtime | None) -> None:
    global _runtime
    _runtime = runtime
