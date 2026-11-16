"""Shared fixtures. Integration tests run against a real Postgres (TEST_DATABASE_URL).

The test database is created if missing and migrated with Alembic once per session;
every integration test starts from empty tables."""

from __future__ import annotations

import os
from collections.abc import Callable, Iterator

import fakeredis
import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.core.db import get_session
from app.main import app
from app.queue.client import set_connection
from app.queue.runtime import set_runtime

TABLES = "crm_pushes, lead_scores, leads, import_row_errors, import_batches, companies"


@pytest.fixture(autouse=True)
def fake_redis() -> Iterator[fakeredis.FakeStrictRedis]:
    """Every test gets its own empty in-memory Redis; no server is needed."""
    connection = fakeredis.FakeStrictRedis()
    set_connection(connection)
    set_runtime(None)
    yield connection
    set_connection(None)
    set_runtime(None)


@pytest.fixture
def settings_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[Callable[..., None]]:
    """Override settings (e.g. JOB_BACKOFF_BASE_SECONDS=0) for one test."""
    from app.core.config import get_settings

    def apply(**values: object) -> None:
        for key, value in values.items():
            monkeypatch.setenv(key.upper(), str(value))
        get_settings.cache_clear()

    yield apply
    monkeypatch.undo()
    get_settings.cache_clear()


def _test_url() -> str:
    return os.environ.get("TEST_DATABASE_URL") or Settings().test_database_url


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    url = make_url(_test_url())
    admin = create_engine(url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        exists = conn.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :n"), {"n": url.database}
        )
        if not exists:
            conn.execute(text(f'CREATE DATABASE "{url.database}"'))
    admin.dispose()

    cfg = Config("alembic.ini")
    cfg.attributes["url"] = url.render_as_string(hide_password=False)
    command.upgrade(cfg, "head")

    eng = create_engine(url)
    yield eng
    eng.dispose()


@pytest.fixture
def session(engine: Engine) -> Iterator[Session]:
    with engine.begin() as conn:
        conn.execute(text(f"TRUNCATE {TABLES} RESTART IDENTITY CASCADE"))
    with Session(engine, expire_on_commit=False) as s:
        yield s


@pytest.fixture
def client(engine: Engine, session: Session) -> Iterator[TestClient]:
    def _override() -> Iterator[Session]:
        with Session(engine, expire_on_commit=False) as s:
            yield s

    app.dependency_overrides[get_session] = _override
    yield TestClient(app)
    app.dependency_overrides.clear()
