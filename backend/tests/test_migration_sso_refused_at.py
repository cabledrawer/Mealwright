"""O2 fix13's one database change: the empty column `login.sso_refused_at`."""

from pathlib import Path

from sqlalchemy import inspect

from mealwright import migrate
from mealwright.db import make_engine

BEFORE = "c3a7e5d1f824"  # the line's newest before this (O2 API tokens)
REFUSED = "e5b3c9a1d742"


def _columns(engine: object) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns("login")}  # type: ignore[arg-type]


def test_the_column_comes_and_goes_and_the_rows_stay(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    migrate.upgrade(engine, BEFORE)
    assert "sso_refused_at" not in _columns(engine)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO household (id, name, created_at) VALUES (1, 'Home', '2026-10-01')"
        )
        connection.exec_driver_sql(
            "INSERT INTO login (id, household_id, username, name, password_hash, role, theme,"
            " created_at) VALUES (1, 1, 'tess', 'Tess', 'x', 'admin', 'auto', '2026-10-01')"
        )
    migrate.upgrade(engine, REFUSED)
    assert "sso_refused_at" in _columns(engine)
    with engine.connect() as connection:
        row = connection.exec_driver_sql("SELECT username, sso_refused_at FROM login").one()
    assert tuple(row) == ("tess", None)  # the mark starts empty
    migrate.downgrade(engine, BEFORE)
    assert "sso_refused_at" not in _columns(engine)
    with engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT username FROM login").scalar_one() == "tess"
    migrate.upgrade(engine, REFUSED)
    assert "sso_refused_at" in _columns(engine)
