from fastapi import FastAPI

from app.api import batches, crm, health, imports, jobs, leads
from app.core.config import get_settings
from app.core.errors import register_error_handlers
from app.core.logging import configure_logging


def create_app() -> FastAPI:
    configure_logging(get_settings().log_level)
    app = FastAPI(
        title="Lead Qualification API",
        description="Import, enrich, score, explain, segment and push leads to a CRM.",
        version="0.1.0",
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(imports.router)
    app.include_router(batches.router)
    app.include_router(leads.router)
    app.include_router(jobs.router)
    app.include_router(crm.router)
    return app


app = create_app()
