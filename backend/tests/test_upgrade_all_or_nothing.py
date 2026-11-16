"""An upgrade is all or nothing (B7 R1, Fable break-it review of 0.9.5-beta.1).

Before the fix, Python's sqlite3 module committed each schema change the moment it ran, so an
upgrade killed part-way left `food.date_kind` in place under the old version stamp (every later
start then failed with "duplicate column name"), and a step that failed was committed half-done.
"""

import subprocess
import sys
import textwrap
from pathlib import Path

import pytest
from sqlalchemy import Engine, inspect

from mealwright import migrate
from mealwright.db import make_engine
from mealwright.migrations import counters

BEFORE = "5fbd6d33c434"  # 0.7.0's newest step; the next one adds food.date_kind


def _old_database(path: Path) -> Engine:
    engine = make_engine(f"sqlite:///{path}")
    migrate.upgrade(engine, BEFORE)
    return engine


def _state(engine: Engine) -> tuple[str | None, bool, list[str]]:
    engine.dispose()
    tables = inspect(engine).get_table_names()
    columns = [c["name"] for c in inspect(engine).get_columns("food")]
    return migrate.current_revision(engine), "date_kind" in columns, tables


def test_a_step_that_fails_leaves_the_database_as_it_was(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _old_database(tmp_path / "old.db")
    before = _state(engine)
    calls = []
    real = counters.restore_counters

    def fail_on_the_third_step(connection: object, saved: dict[str, int]) -> None:
        calls.append(1)
        if len(calls) == 3:
            raise RuntimeError("disk full")
        real(connection, saved)  # type: ignore[arg-type]

    monkeypatch.setattr(counters, "restore_counters", fail_on_the_third_step)
    with pytest.raises(RuntimeError, match="disk full"):
        migrate.upgrade(engine)
    assert _state(engine) == before
    monkeypatch.undo()
    migrate.upgrade(engine)  # trying again works
    assert (
        migrate.current_revision(engine)
        == migrate.ScriptDirectory.from_config(migrate.alembic_config()).get_current_head()
    )


def test_an_upgrade_killed_part_way_leaves_the_database_as_it_was(tmp_path: Path) -> None:
    path = tmp_path / "old.db"
    engine = _old_database(path)
    before = _state(engine)
    script = textwrap.dedent(
        f"""
        import os
        from mealwright import migrate
        from mealwright.db import make_engine
        from mealwright.migrations import counters
        calls = []
        real = counters.restore_counters
        def killed(connection, saved):
            calls.append(1)
            if len(calls) == 2:  # after the first step (ALTER TABLE food ADD date_kind)
                os._exit(9)
            real(connection, saved)
        counters.restore_counters = killed
        migrate.upgrade(make_engine("sqlite:///{path}"))
        """
    )
    done = subprocess.run([sys.executable, "-c", script], check=False, timeout=120)  # noqa: S603
    assert done.returncode == 9
    assert _state(engine) == before
    migrate.upgrade(engine)  # the next start's upgrade works
    columns = [c["name"] for c in inspect(engine).get_columns("food")]
    assert "date_kind" in columns
