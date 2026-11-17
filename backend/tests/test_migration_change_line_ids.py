"""B7 low: `change_line` and `food_merge` never reuse an id, and the rebuild keeps every row."""

from pathlib import Path

from sqlalchemy import Engine

from mealwright import migrate
from mealwright.db import make_engine

BEFORE = "d7a3e1b5c924"  # the line's newest before this
THIS = "e5b9c3a7d1f2"
TABLES = ("change_line", "food_merge")


def _sql(engine: Engine, table: str) -> str:
    with engine.connect() as connection:
        return str(
            connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
            ).scalar_one()
        )


def _rows(engine: Engine, table: str) -> list[tuple[object, ...]]:
    with engine.connect() as connection:
        return [tuple(r) for r in connection.exec_driver_sql(f"SELECT * FROM {table} ORDER BY id")]  # noqa: S608


def _fill(engine: Engine) -> None:
    with engine.begin() as connection:
        run = connection.exec_driver_sql
        run("INSERT INTO household (id, name, created_at) VALUES (1, 'Home', '2026-10-01')")
        for food in (1, 2, 3):
            run(
                "INSERT INTO food (id, household_id, name, counted_as, staple, created_at)"  # noqa: S608
                f" VALUES ({food}, 1, 'F{food}', 'each', 0, '2026-10-01')"
            )
        run(
            "INSERT INTO change (id, household_id, request, kind, login_name, at, summary)"
            " VALUES (1, 1, 'x', 'stock', 'Sam', '2026-10-02', 's')"
        )
        for line in (1, 2, 3):
            run(
                "INSERT INTO change_line (id, household_id, change_id, food_id,"  # noqa: S608
                " amount_before_milli, amount_after_milli) VALUES"
                f" ({line}, 1, 1, 1, 1000, 2000)"
            )
        for merge, (a, b) in enumerate(((2, 1), (3, 1)), start=1):
            run(
                "INSERT INTO food_merge (id, household_id, from_food_id, into_food_id, merged_at)"  # noqa: S608
                f" VALUES ({merge}, 1, {a}, {b}, '2026-10-03')"
            )


def test_the_tables_keep_every_row_and_never_reuse_a_deleted_top_id(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    migrate.upgrade(engine, BEFORE)
    for table in TABLES:
        assert "AUTOINCREMENT" not in _sql(engine, table)
    _fill(engine)
    before = {table: _rows(engine, table) for table in TABLES}
    migrate.upgrade(engine, THIS)
    for table in TABLES:
        assert "AUTOINCREMENT" in _sql(engine, table)
        assert _rows(engine, table) == before[table]
    with engine.begin() as connection:  # delete the top id, then make a new row
        connection.exec_driver_sql("DELETE FROM change_line WHERE id = 3")
        connection.exec_driver_sql("DELETE FROM food_merge WHERE id = 2")
        connection.exec_driver_sql(
            "INSERT INTO change_line (household_id, change_id, food_id, amount_before_milli,"
            " amount_after_milli) VALUES (1, 1, 1, 0, 1)"
        )
        connection.exec_driver_sql(
            "INSERT INTO food_merge (household_id, from_food_id, into_food_id, merged_at)"
            " VALUES (1, 2, 3, '2026-10-04')"
        )
    assert [r[0] for r in _rows(engine, "change_line")] == [1, 2, 4]  # 3 is not used again
    assert [r[0] for r in _rows(engine, "food_merge")] == [1, 3]
    migrate.downgrade(engine, BEFORE)
    for table in TABLES:
        assert "AUTOINCREMENT" not in _sql(engine, table)
    assert [r[0] for r in _rows(engine, "change_line")] == [1, 2, 4]
    assert [r[0] for r in _rows(engine, "food_merge")] == [1, 3]
    migrate.upgrade(engine, THIS)
    assert all("AUTOINCREMENT" in _sql(engine, table) for table in TABLES)
