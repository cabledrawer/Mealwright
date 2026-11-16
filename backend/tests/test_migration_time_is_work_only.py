"""L6 (beta.2): the hidden `time_is_work_only` mark on `recipe` and `recipe_method`."""

from pathlib import Path

from sqlalchemy import inspect

from mealwright import migrate
from mealwright.db import make_engine

BEFORE = "c4f7a2d9e816"  # the line's newest before this (change body hash)
THIS = "d7a3e1b5c924"


def _columns(engine: object, table: str) -> set[str]:
    return {c["name"] for c in inspect(engine).get_columns(table)}  # type: ignore[arg-type]


def test_every_recipe_and_way_starts_unmarked_and_the_columns_come_and_go(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    migrate.upgrade(engine, BEFORE)
    for table in ("recipe", "recipe_method"):
        assert "time_is_work_only" not in _columns(engine, table)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO household (id, name, created_at) VALUES (1, 'Home', '2026-10-01')"
        )
        connection.exec_driver_sql(
            "INSERT INTO recipe (id, household_id, name, time_minutes, version, created_at,"
            " updated_at, updated_by_name, made_ahead) VALUES (1, 1, 'Stew', 360, 1,"
            " '2026-10-19', '2026-10-19', 'Sam', 0)"
        )
        connection.exec_driver_sql(
            "INSERT INTO recipe_method (id, household_id, recipe_id, position, name, time_minutes)"
            " VALUES (1, 1, 1, 0, '', 360)"
        )
    migrate.upgrade(engine, THIS)
    with engine.connect() as connection:
        for table in ("recipe", "recipe_method"):
            rows = connection.exec_driver_sql(f"SELECT time_is_work_only FROM {table}")  # noqa: S608
            assert rows.scalars().all() == [0]  # they keep today's behaviour
    migrate.downgrade(engine, BEFORE)
    for table in ("recipe", "recipe_method"):
        assert "time_is_work_only" not in _columns(engine, table)
    with engine.connect() as connection:  # the recipe and its time stay
        row = connection.exec_driver_sql("SELECT name, time_minutes FROM recipe").one()
        assert tuple(row) == ("Stew", 360)
    migrate.upgrade(engine, THIS)
    assert "time_is_work_only" in _columns(engine, "recipe_method")
