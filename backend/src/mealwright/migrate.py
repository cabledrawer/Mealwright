"""Run database migrations from code (on start-up and in tests)."""

from collections.abc import Iterator
from contextlib import contextmanager

from alembic import command
from alembic.config import Config
from sqlalchemy import Connection, Engine


def alembic_config() -> Config:
    config = Config()
    config.set_main_option("script_location", "mealwright:migrations")
    return config


@contextmanager
def foreign_keys_off(connection: Connection) -> Iterator[None]:
    """On SQLite, switch foreign keys off while migrating.

    Batch migrations rebuild a table to change it (copy, drop, rename). With foreign keys
    on, dropping the old copy of a parent table counts as deleting its rows, and ON DELETE
    CASCADE would then delete every row that points at it: changing `household` would
    delete every login. SQLite's own advice is to switch foreign keys off for this. It
    can only be changed outside a transaction. Afterwards every foreign key is checked.
    """
    if connection.dialect.name != "sqlite":
        yield
        return
    connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
    connection.commit()
    try:
        yield
        broken = connection.exec_driver_sql("PRAGMA foreign_key_check").fetchall()
        if broken:
            raise RuntimeError(f"Migration left broken links between tables: {broken[:5]}")
        connection.commit()
    finally:
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.commit()


def _run(engine: Engine, action: str, revision: str) -> None:
    config = alembic_config()
    with engine.connect() as connection, foreign_keys_off(connection):
        config.attributes["connection"] = connection
        if action == "upgrade":
            command.upgrade(config, revision)
        else:
            command.downgrade(config, revision)
        connection.commit()


def upgrade(engine: Engine, revision: str = "head") -> None:
    _run(engine, "upgrade", revision)


def downgrade(engine: Engine, revision: str) -> None:
    _run(engine, "downgrade", revision)
