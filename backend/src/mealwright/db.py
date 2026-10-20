"""Database engine, sessions and the declarative base."""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

from sqlalchemy import Engine, MetaData, create_engine, event
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

# Stable constraint names, so Alembic migrations stay predictable on SQLite and Postgres.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


def make_engine(url: str) -> Engine:
    if not url.startswith("sqlite"):
        return create_engine(url, hide_parameters=True)

    # hide_parameters: a database error's text leaves out the values (a typed username,
    # food names…), so a traceback in the log never carries what people typed.
    # timeout: how long a write waits for another one to finish (sync protocol 5.2: longer
    # than any batch of list changes takes).
    engine = create_engine(
        url, connect_args={"check_same_thread": False, "timeout": 30}, hide_parameters=True
    )

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_connection: Any, _record: Any) -> None:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()

    return engine


def make_sessionmaker(engine: Engine, photos: Path | None = None) -> sessionmaker[Session]:
    """`photos`: the folder recipe photo files are kept in, so a session can delete a
    photo's files once its record is gone (mealwright.photos)."""
    info = {} if photos is None else {"mealwright.photos.store": str(photos)}
    return sessionmaker(bind=engine, expire_on_commit=False, info=info)


def session_scope(factory: sessionmaker[Session]) -> Iterator[Session]:
    with factory() as session:
        yield session
