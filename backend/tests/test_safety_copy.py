"""A safety copy of the database before every upgrade (cabledrawer 28 Oct, review of v0.6.0)."""

import sqlite3
from datetime import UTC, datetime
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from mealwright import migrate
from mealwright.config import Settings
from mealwright.db import make_engine
from mealwright.main import create_app

OLD = "a4c8e1f7b296"  # 0.6 PR 5's migration: any revision before the newest will do


def _old_database(path: Path) -> Engine:
    engine = make_engine(f"sqlite:///{path}")
    migrate.upgrade(engine, OLD)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO household (id, name, created_at) VALUES (1, 'Home', '2026-10-01')"
        )
    return engine


def _head() -> str:
    return str(ScriptDirectory.from_config(migrate.alembic_config()).get_current_head())


def _copies(backups: Path) -> list[str]:
    return sorted(p.name for p in backups.iterdir()) if backups.exists() else []


def test_an_upgrade_copies_the_database_first_and_the_copy_opens_at_the_old_revision(
    tmp_path: Path,
) -> None:
    engine = _old_database(tmp_path / "mealwright.db")
    backups = tmp_path / "backups"
    copy = migrate.safety_copy(engine, backups, now=datetime(2026, 10, 30, 14, 25, 1, tzinfo=UTC))
    assert copy == backups / f"pre-upgrade-{OLD}-20261030-142501.db"
    migrate.upgrade(engine)
    assert migrate.current_revision(engine) == _head()
    # The copy is a whole database, still at the revision it was copied from, with its rows
    # (the household was written to the WAL file, not yet folded into the database file).
    with sqlite3.connect(copy) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone() == (OLD,)
        assert db.execute("SELECT name FROM household").fetchall() == [("Home",)]
        assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
    assert _copies(backups) == [copy.name]  # nothing half-written left beside it


def test_upgrade_with_backups_makes_the_copy(tmp_path: Path) -> None:
    engine = _old_database(tmp_path / "mealwright.db")
    backups = tmp_path / "backups"
    migrate.upgrade(engine, backups=backups)
    [name] = _copies(backups)
    assert migrate.SAFETY_COPY_NAME.match(name)
    assert name.startswith(f"pre-upgrade-{OLD}-")
    assert migrate.current_revision(engine) == _head()


def test_no_copy_when_already_up_to_date(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'mealwright.db'}")
    migrate.upgrade(engine)
    backups = tmp_path / "backups"
    assert migrate.safety_copy(engine, backups) is None
    migrate.upgrade(engine, backups=backups)
    assert _copies(backups) == []


def test_no_copy_of_a_new_database(tmp_path: Path) -> None:
    engine = make_engine(f"sqlite:///{tmp_path / 'mealwright.db'}")
    backups = tmp_path / "backups"
    migrate.upgrade(engine, backups=backups)
    assert _copies(backups) == []
    assert migrate.current_revision(engine) == _head()


def test_only_the_newest_three_copies_stay_and_other_files_are_left_alone(
    tmp_path: Path,
) -> None:
    backups = tmp_path / "backups"
    backups.mkdir()
    older = [
        "pre-upgrade-d7a4c2e81f56-20261024-090000.db",
        "pre-upgrade-e3b7a95c4d18-20261026-090000.db",
        "pre-upgrade-c5e8a1f3b7d2-20261027-090000.db",  # a revision that sorts first by name
    ]
    for name in older:
        (backups / name).write_bytes(b"old")
    others = ["data-0.6.0-20261020-1200.tar.gz", "pre-upgrade-notes.txt", "mine.db"]
    for name in others:
        (backups / name).write_bytes(b"keep")
    engine = _old_database(tmp_path / "mealwright.db")
    copy = migrate.safety_copy(engine, backups, now=datetime(2026, 10, 30, 8, 0, tzinfo=UTC))
    assert copy is not None
    assert _copies(backups) == sorted([*older, copy.name, *others])  # not trimmed yet
    copy.unlink()
    migrate.upgrade(engine, backups=backups)  # trimmed once the upgrade has worked
    [new] = [name for name in _copies(backups) if name not in older and name not in others]
    assert _copies(backups) == sorted([*older[1:], new, *others])


def test_a_failing_upgrade_trims_no_copies(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A start-up that fails on a migration, again and again, keeps every copy: the last
    good one is never trimmed away."""
    backups = tmp_path / "backups"
    backups.mkdir()
    older = [f"pre-upgrade-d7a4c2e81f56-202610{day}-090000.db" for day in (24, 25, 26)]
    for name in older:
        (backups / name).write_bytes(b"old")
    engine = _old_database(tmp_path / "mealwright.db")

    def broken(*_args: object) -> None:
        raise RuntimeError("a migration failed")

    monkeypatch.setattr(migrate, "_run", broken)
    for _start in range(2):
        with pytest.raises(RuntimeError):
            migrate.upgrade(engine, backups=backups)
    assert set(older) <= set(_copies(backups))
    assert len(_copies(backups)) > len(older)  # and the copies the two starts made


def test_if_the_copy_fails_nothing_is_upgraded(tmp_path: Path) -> None:
    engine = _old_database(tmp_path / "mealwright.db")
    backups = tmp_path / "backups"
    backups.write_text("a file where the folder should be")
    with pytest.raises(migrate.SafetyCopyFailed, match="The database was not changed"):
        migrate.upgrade(engine, backups=backups)
    assert migrate.current_revision(engine) == OLD


def test_start_up_copies_an_old_database_into_the_data_folder(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    _old_database(data_dir / "mealwright.db").dispose()
    with TestClient(create_app(Settings(data_dir=data_dir, run_jobs=False))):
        pass
    [name] = _copies(data_dir / "backups")
    assert name.startswith(f"pre-upgrade-{OLD}-")


def test_start_up_on_a_new_install_makes_no_copy(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    with TestClient(create_app(Settings(data_dir=data_dir, run_jobs=False))):
        pass
    assert (data_dir / "mealwright.db").exists()
    assert _copies(data_dir / "backups") == []
