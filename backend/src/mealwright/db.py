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


# How many requests may use the database at once; the rest wait their turn, in the order
# they came, holding nothing (`mealwright.auth.get_db`). 40 is the number of worker threads
# a request's steps run in, so a request that has a thread to run in is never kept waiting
# here for long.
#
# Why there is a limit at all: a request keeps its database connection from its first step
# (the sign-in check) to its last, and between steps it waits for a free thread. Without a
# limit, a burst of more requests than threads could leave every connection with a request
# waiting for a thread, and every thread with a request waiting for a connection: nothing
# moved for 30 seconds, then most of them failed (X1 security review r2).
REQUESTS_AT_ONCE = 40
# Connections kept spare for the short reads made beside the requests: a Privacy switch
# looked up while a request runs, the live streams' sign-in checks, announcing a change, the
# hourly jobs. Each is taken and given back inside one thread, so they can't hold each
# other up.
SPARE_CONNECTIONS = 10
# Connections kept open while idle; the rest are opened for a burst and closed after it.
IDLE_CONNECTIONS = 5


def _pool() -> dict[str, int]:
    """A pool that can't run dry: a connection for every request let in, and the spare ones.
    The same on SQLite and on Postgres later (50 at most, under Postgres's usual 100)."""
    most = REQUESTS_AT_ONCE + SPARE_CONNECTIONS
    idle = min(IDLE_CONNECTIONS, most)
    return {"pool_size": idle, "max_overflow": most - idle}


def make_engine(url: str) -> Engine:
    if not url.startswith("sqlite"):
        return create_engine(url, hide_parameters=True, **_pool())

    # hide_parameters: a database error's text leaves out the values (a typed username,
    # food names…), so a traceback in the log never carries what people typed.
    # timeout: how long a write waits for another one to finish (sync protocol 5.2: longer
    # than any batch of list changes takes).
    engine = create_engine(
        url,
        connect_args={"check_same_thread": False, "timeout": 30},
        hide_parameters=True,
        **_pool(),
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


# The session hook that keeps old names (problem reports scrub them): imported here so that any
# process using the database has it registered. Last, because it imports `Base` from this file.
from mealwright import former_names  # noqa: E402,F401
