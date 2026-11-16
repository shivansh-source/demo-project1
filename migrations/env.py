from alembic import context
from sqlalchemy import create_engine

import app.models  # noqa: F401  (registers tables on Base.metadata)
from app.core.config import get_settings
from app.core.db import Base

target_metadata = Base.metadata


def _url() -> str:
    # Tests pass the URL through config.attributes; `alembic -x url=...` also works.
    from_attrs = context.config.attributes.get("url")
    if isinstance(from_attrs, str):
        return from_attrs
    return context.get_x_argument(as_dictionary=True).get("url") or get_settings().database_url


def run_migrations_online() -> None:
    engine = create_engine(_url())
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


run_migrations_online()
