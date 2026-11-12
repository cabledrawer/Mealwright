"""Beta fix5's one database change: the empty table `former_name`."""

from pathlib import Path

from sqlalchemy import inspect

from mealwright import migrate
from mealwright.db import make_engine

BEFORE = "c3a7e5d1f824"  # the line's newest before this (O2 API tokens)
FORMER_NAMES = "d3a9f1c7e254"


def test_former_name_table_comes_and_goes_with_the_migration(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    migrate.upgrade(engine, BEFORE)
    assert "former_name" not in inspect(engine).get_table_names()
    migrate.upgrade(engine, FORMER_NAMES)
    columns = {c["name"] for c in inspect(engine).get_columns("former_name")}
    assert columns == {"id", "household_id", "kind", "name", "at"}
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO household (id, name, created_at) VALUES (1, 'Home', '2026-10-01')"
        )
        connection.exec_driver_sql(
            "INSERT INTO former_name (household_id, kind, name, at)"
            " VALUES (1, 'person', 'Old', '2026-11-01')"
        )
        # Every table points at its household with ON DELETE CASCADE.
        connection.exec_driver_sql("PRAGMA foreign_keys=ON")
        connection.exec_driver_sql("DELETE FROM household WHERE id = 1")
        assert connection.exec_driver_sql("SELECT count(*) FROM former_name").scalar_one() == 0
    migrate.downgrade(engine, BEFORE)
    assert "former_name" not in inspect(engine).get_table_names()
    migrate.upgrade(engine, FORMER_NAMES)
    assert "former_name" in inspect(engine).get_table_names()
