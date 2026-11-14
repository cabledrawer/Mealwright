"""0.9.5 Import from Mealie's one database change: the `mealie_import` table, the two links to
it, and drafts of kind 'mealie'."""

from pathlib import Path

import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from mealwright import migrate
from mealwright.db import make_engine

BEFORE = "d3a9f1c7e254"  # the line's newest before this (beta fix5, former names)
MEALIE = "b6e2d8f4a913"


def _draft(kind: str, mealie: str = "NULL") -> str:
    return (
        "INSERT INTO import_draft (household_id, source_kind, source_text, name, review,"
        " choices, lines_total, lines_checked, started_by_name, created_at, updated_at"
        + (", mealie_import_id" if mealie != "NULL" else "")
        + f") VALUES (1, '{kind}', '', 'Dal', '{{}}', '{{}}', 0, 0, 'Sam', '2026-11-01',"
        " '2026-11-01'" + (f", {mealie}" if mealie != "NULL" else "") + ")"
    )


def test_mealie_import_comes_and_goes_with_the_migration(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'old.db'}")
    migrate.upgrade(engine, BEFORE)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO household (id, name, created_at) VALUES (1, 'Home', '2026-10-01')"
        )
        connection.exec_driver_sql(_draft("link"))
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.exec_driver_sql(_draft("mealie"))
    migrate.upgrade(engine, MEALIE)
    look = inspect(engine)
    assert "mealie_import" in look.get_table_names()
    assert "mealie_import_id" in {c["name"] for c in look.get_columns("food")}
    assert "mealie_import_id" in {c["name"] for c in look.get_columns("import_draft")}
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO mealie_import (id, household_id, state, file_name, preview, choices,"
            " total, done, results, started_by_name, created_at)"
            " VALUES (1, 1, 'done', 'mealie.zip', '{}', '{}', 0, 0, '[]', 'Sam', '2026-11-01')"
        )
        connection.exec_driver_sql(_draft("mealie", "1"))
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.exec_driver_sql(_draft("paper"))
        with pytest.raises(IntegrityError), connection.begin_nested():
            connection.exec_driver_sql(
                "INSERT INTO mealie_import (household_id, state, file_name, preview, choices,"
                " total, done, results, started_by_name, created_at)"
                " VALUES (1, 'odd', 'x.zip', '{}', '{}', 0, 0, '[]', '', '2026-11-01')"
            )
        # The existing draft is kept as it was.
        assert connection.exec_driver_sql("SELECT count(*) FROM import_draft").scalar_one() == 2
    migrate.downgrade(engine, BEFORE)
    look = inspect(engine)
    assert "mealie_import" not in look.get_table_names()
    assert "mealie_import_id" not in {c["name"] for c in look.get_columns("food")}
    with engine.begin() as connection:
        # The Mealie draft went; the link draft stayed.
        kinds = connection.exec_driver_sql("SELECT source_kind FROM import_draft").scalars()
        assert list(kinds) == ["link"]
    migrate.upgrade(engine, MEALIE)
    assert "mealie_import" in inspect(engine).get_table_names()


def test_every_table_points_at_its_household(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'new.db'}")
    migrate.upgrade(engine, MEALIE)
    keys = inspect(engine).get_foreign_keys("mealie_import")
    household = [k for k in keys if k["referred_table"] == "household"]
    assert household and household[0]["options"].get("ondelete") == "CASCADE"
