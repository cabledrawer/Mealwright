"""Alembic environment. The database URL comes from Mealwright's settings."""

from collections.abc import Collection, Mapping
from typing import Any

from alembic import context
from alembic.runtime.migration import MigrationContext, MigrationInfo
from sqlalchemy import Connection

from mealwright import models  # noqa: F401  (registers the tables)
from mealwright.config import get_settings
from mealwright.db import Base, make_engine
from mealwright.migrate import foreign_keys_off
from mealwright.migrations.counters import read_counters, restore_counters

config = context.config
target_metadata = Base.metadata


def _configure(connection: Connection) -> None:
    # A rebuilt table would start its "never reuse an id" counter again (D1): keep the counters,
    # putting them back after every step so a later step never hands out a removed row's id
    # (RF1 review r1). The highest counter seen so far is what each table keeps.
    counters = read_counters(connection)

    def keep_counters(  # Alembic passes these by name
        ctx: MigrationContext,
        step: MigrationInfo,
        heads: Collection[Any],
        run_args: Mapping[str, Any],
    ) -> None:
        restore_counters(connection, counters)
        for table, seq in read_counters(connection).items():
            counters[table] = max(seq, counters.get(table, 0))

    # Batch mode lets ALTER TABLE work on SQLite.
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        render_as_batch=True,
        on_version_apply=keep_counters,
    )
    with context.begin_transaction():
        context.run_migrations()
        restore_counters(connection, counters)


def run_migrations_online() -> None:
    connection = config.attributes.get("connection")
    if connection is not None:
        _configure(connection)
        return
    url = config.get_main_option("sqlalchemy.url") or get_settings().sqlalchemy_url
    engine = make_engine(url)
    with engine.connect() as connection, foreign_keys_off(connection):
        _configure(connection)  # foreign_keys_off commits only if every step worked (B7 R1)
    engine.dispose()


if context.is_offline_mode():
    raise SystemExit("Offline migrations are not supported.")
run_migrations_online()
