"""PR O2's one database change: the new, empty `api_token` table."""

from pathlib import Path

import pytest
from sqlalchemy import Connection, Engine, inspect, text
from sqlalchemy.exc import IntegrityError

from mealwright import migrate
from mealwright.db import make_engine

BEFORE = "c1d5e9a3f702"  # the migration just before (0.9 O1: single sign-on)
TOKENS = "c3a7e5d1f824"


def _tables(engine: Engine) -> set[str]:
    return set(inspect(engine).get_table_names())


def _rows(engine: Engine) -> list[tuple[object, ...]]:
    with engine.connect() as connection:
        return list(
            connection.exec_driver_sql(
                "SELECT id, household_id, username, password_hash, role FROM login"
            ).all()
        )


def _token(connection: Connection, token_hash: str, scope: str = "read") -> None:
    connection.exec_driver_sql(
        "INSERT INTO api_token (household_id, login_id, name, token_hash, scope, created_at)"
        " VALUES (1, 1, 'Home Assistant', ?, ?, '2026-11-14')",
        (token_hash, scope),
    )


def _old_database(tmp_path: Path) -> Engine:
    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    migrate.upgrade(engine, BEFORE)
    with engine.begin() as connection:
        for sql in (
            "INSERT INTO household (id, name, created_at) VALUES (1, 'Home', '2026-10-01')",
            "INSERT INTO login (id, household_id, username, name, password_hash, role, theme,"
            " created_at) VALUES (1, 1, 'tess', 'Tess', 'x', 'admin', 'auto',"
            " '2026-10-01')",
        ):
            connection.execute(text(sql))
    return engine


def test_api_token_migration_adds_one_empty_table_and_goes_back_and_forward(
    tmp_path: Path,
) -> None:
    engine = _old_database(tmp_path)
    before = _rows(engine)
    assert "api_token" not in _tables(engine)

    migrate.upgrade(engine, TOKENS)
    assert "api_token" in _tables(engine)
    columns = {c["name"] for c in inspect(engine).get_columns("api_token")}
    assert columns == {
        "id",
        "household_id",
        "login_id",
        "name",
        "token_hash",
        "scope",
        "created_at",
        "last_used_at",
        "expires_at",
        "revoked_at",
    }
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM api_token").scalar_one() == 0
    assert _rows(engine) == before
    with engine.begin() as connection:
        _token(connection, "a" * 64)

    migrate.downgrade(engine, BEFORE)
    assert "api_token" not in _tables(engine)
    assert _rows(engine) == before  # every login kept; only the tokens go

    migrate.upgrade(engine, TOKENS)  # and forward again starts it empty
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT count(*) FROM api_token").scalar_one() == 0
    assert _rows(engine) == before


def test_the_database_keeps_the_token_rules(tmp_path: Path) -> None:
    engine = _old_database(tmp_path)
    migrate.upgrade(engine, TOKENS)
    sql = str(
        engine.connect()
        .exec_driver_sql("SELECT sql FROM sqlite_master WHERE name = 'api_token'")
        .scalar_one()
    )
    assert "AUTOINCREMENT" in sql  # a deleted token's id is never handed out again
    with engine.begin() as connection:
        _token(connection, "b" * 64)
    with pytest.raises(IntegrityError), engine.begin() as connection:
        _token(connection, "b" * 64)  # each token is one of a kind
    with pytest.raises(IntegrityError), engine.begin() as connection:
        _token(connection, "c" * 64, scope="admin")  # read or full only
    with engine.begin() as connection:  # a login's tokens go with it
        connection.exec_driver_sql("DELETE FROM login WHERE id = 1")
        assert connection.exec_driver_sql("SELECT count(*) FROM api_token").scalar_one() == 0
