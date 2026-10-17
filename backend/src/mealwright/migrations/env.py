"""Alembic environment. The database URL comes from Mealwright's settings."""

from alembic import context
from sqlalchemy import Connection

from mealwright import models  # noqa: F401  (registers the tables)
from mealwright.config import get_settings
from mealwright.db import Base, make_engine

config = context.config
target_metadata = Base.metadata


def _configure(connection: Connection) -> None:
    # Batch mode lets ALTER TABLE work on SQLite.
    context.configure(connection=connection, target_metadata=target_metadata, render_as_batch=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection)
        return
    url = config.get_main_option("sqlalchemy.url") or get_settings().sqlalchemy_url
    engine = make_engine(url)
    with engine.connect() as connection:
        _configure(connection)
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline migrations are not supported.")
run_migrations_online()
