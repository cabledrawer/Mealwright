"""A safety copy of the database before every upgrade (cabledrawer 28 Oct, review of v0.6.0)."""

import os
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


def _broken(*_args: object) -> None:
    raise RuntimeError("a migration failed")


def test_a_failing_upgrade_makes_one_copy_and_trims_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A start-up that fails on a migration, again and again, copies the database once (the
    clean copy, from before the first try) and trims nothing."""
    backups = tmp_path / "backups"
    backups.mkdir()
    older = [f"pre-upgrade-d7a4c2e81f56-202610{day}-090000.db" for day in (24, 25, 26)]
    for name in older:
        (backups / name).write_bytes(b"old")
    engine = _old_database(tmp_path / "mealwright.db")
    monkeypatch.setattr(migrate, "_run", _broken)
    for _start in range(2):
        with pytest.raises(RuntimeError):
            migrate.upgrade(engine, backups=backups)
    [clean] = [n for n in _copies(backups) if n not in older and n != migrate.UPGRADE_FAILED]
    assert _copies(backups) == sorted([*older, clean, migrate.UPGRADE_FAILED])
    assert (backups / migrate.UPGRADE_FAILED).read_text().strip() == clean


def test_a_failing_upgrade_says_plainly_where_the_data_is(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """The log says what happened and what to do, naming the clean copy (cabledrawer 31 Oct)."""
    backups = tmp_path / "backups"
    engine = _old_database(tmp_path / "mealwright.db")
    monkeypatch.setattr(migrate, "_run", _broken)
    with caplog.at_level("WARNING", logger=migrate.__name__), pytest.raises(RuntimeError):
        migrate.upgrade(engine, backups=backups)
    [clean] = [n for n in _copies(backups) if n != migrate.UPGRADE_FAILED]
    assert (
        f"Database upgrade failed. Your data from before is safe in {backups / clean}. "
        "Mealwright didn't start. See docs/dev/test-on-homelab.md, 'Going back to the "
        "previous version'."
    ) in caplog.messages
    caplog.clear()
    with caplog.at_level("WARNING", logger=migrate.__name__), pytest.raises(RuntimeError):
        migrate.upgrade(engine, backups=backups)
    assert caplog.messages[0] == (
        f"An earlier database upgrade failed. Your data from before it is safe in "
        f"{backups / clean} (made on {clean[-18:-14]}-{clean[-14:-12]}-{clean[-12:-10]}). "
        "Trying the upgrade again."
    )


def test_the_clean_copy_outlives_the_trim_once_the_upgrade_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    backups = tmp_path / "backups"
    engine = _old_database(tmp_path / "mealwright.db")
    monkeypatch.setattr(migrate, "_run", _broken)
    with pytest.raises(RuntimeError):
        migrate.upgrade(engine, backups=backups)
    [clean] = [n for n in _copies(backups) if n != migrate.UPGRADE_FAILED]
    # Three newer copies turn up meanwhile (say, from a copy of the data folder).
    newer = [f"pre-upgrade-d7a4c2e81f56-209910{day}-090000.db" for day in (24, 25, 26)]
    for name in newer:
        (backups / name).write_bytes(b"new")
    monkeypatch.undo()
    migrate.upgrade(engine, backups=backups)
    assert migrate.current_revision(engine) == _head()
    assert _copies(backups) == sorted([clean, *newer])  # and the marker is gone


def test_the_tidy_up_failing_doesnt_fail_the_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    def no_tidy(*_args: object, **_kwargs: object) -> None:
        raise PermissionError("read-only folder")

    engine = _old_database(tmp_path / "mealwright.db")
    monkeypatch.setattr(migrate, "_keep_newest", no_tidy)
    migrate.upgrade(engine, backups=tmp_path / "backups")
    assert migrate.current_revision(engine) == _head()
    assert "Couldn't tidy the safety copies" in caplog.text


def test_the_half_written_copy_is_named_for_its_process(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[str] = []
    real = sqlite3.connect

    def spy(target: object, *args: object, **kwargs: object) -> sqlite3.Connection:
        seen.append(str(target))
        return real(target, *args, **kwargs)  # type: ignore[arg-type]

    engine = _old_database(tmp_path / "mealwright.db")
    monkeypatch.setattr(migrate.sqlite3, "connect", spy)
    migrate.safety_copy(engine, tmp_path / "backups")
    assert any(name.endswith(f".{os.getpid()}.part") for name in seen)


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


def test_a_marker_naming_a_missing_copy_is_removed_and_a_fresh_copy_made(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    backups = tmp_path / "backups"
    backups.mkdir()
    gone = "pre-upgrade-d7a4c2e81f56-20261031-090000.db"
    (backups / migrate.UPGRADE_FAILED).write_text(gone + "\n")
    engine = _old_database(tmp_path / "mealwright.db")
    monkeypatch.setattr(migrate, "_run", _broken)
    with caplog.at_level("WARNING", logger=migrate.__name__), pytest.raises(RuntimeError):
        migrate.upgrade(engine, backups=backups)
    assert any("is missing" in m and gone in m for m in caplog.messages)
    [fresh] = [n for n in _copies(backups) if n != migrate.UPGRADE_FAILED]
    assert fresh != gone
    assert (backups / migrate.UPGRADE_FAILED).read_text().strip() == fresh


def test_the_stale_marker_warning_shows_the_copys_date(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    backups = tmp_path / "backups"
    backups.mkdir()
    name = "pre-upgrade-d7a4c2e81f56-20261031-090000.db"
    (backups / name).write_bytes(b"old")
    (backups / migrate.UPGRADE_FAILED).write_text(name + "\n")
    engine = _old_database(tmp_path / "mealwright.db")
    monkeypatch.setattr(migrate, "_run", _broken)
    with caplog.at_level("WARNING", logger=migrate.__name__), pytest.raises(RuntimeError):
        migrate.upgrade(engine, backups=backups)
    assert "(made on 2026-10-31)" in caplog.messages[0]


def test_a_part_file_from_another_process_is_tidied_and_our_own_stays(tmp_path: Path) -> None:
    backups = tmp_path / "backups"
    backups.mkdir()
    stale = backups / "pre-upgrade-d7a4c2e81f56-20261031-090000.db.99999999.part"
    mine = backups / f"pre-upgrade-d7a4c2e81f56-20261031-090001.db.{os.getpid()}.part"
    other = backups / "notes.txt"
    for path in (stale, mine, other):
        path.write_bytes(b"x")
    migrate._keep_newest(backups)
    assert not stale.exists()
    assert mine.exists()
    assert other.exists()


def test_a_part_file_that_cant_be_removed_doesnt_stop_the_start(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    backups = tmp_path / "backups"
    backups.mkdir()
    stale = backups / "pre-upgrade-d7a4c2e81f56-20261031-090000.db.99999999.part"
    stale.write_bytes(b"x")
    real = Path.unlink

    def refuse(self: Path, *args: object, **kwargs: object) -> None:
        if self == stale:
            raise PermissionError("read-only")
        real(self, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(Path, "unlink", refuse)
    engine = _old_database(tmp_path / "mealwright.db")
    with caplog.at_level("WARNING", logger=migrate.__name__):
        migrate.upgrade(engine, backups=backups)
    assert migrate.current_revision(engine) == _head()
    assert "Couldn't remove the half-written copy" in caplog.text


def test_an_unreadable_marker_stops_the_start_with_a_plain_message(tmp_path: Path) -> None:
    backups = tmp_path / "backups"
    (backups / migrate.UPGRADE_FAILED).mkdir(parents=True)  # a folder: reading it fails
    engine = _old_database(tmp_path / "mealwright.db")
    with pytest.raises(migrate.SafetyCopyFailed, match=r"Couldn't read .*The database was not"):
        migrate.upgrade(engine, backups=backups)
    assert migrate.current_revision(engine) == OLD


def test_a_marker_that_cant_be_written_stops_the_start_before_any_upgrade(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = Path.write_text

    def refuse(self: Path, *args: object, **kwargs: object) -> int:
        if self.name == migrate.UPGRADE_FAILED:
            raise PermissionError("read-only")
        return real(self, *args, **kwargs)  # type: ignore[arg-type]

    engine = _old_database(tmp_path / "mealwright.db")
    monkeypatch.setattr(Path, "write_text", refuse)
    with pytest.raises(migrate.SafetyCopyFailed, match=r"Couldn't write .*not changed"):
        migrate.upgrade(engine, backups=tmp_path / "backups")
    assert migrate.current_revision(engine) == OLD


def test_the_backups_folder_is_for_the_owner_only(tmp_path: Path) -> None:
    engine = _old_database(tmp_path / "mealwright.db")
    backups = tmp_path / "backups"
    assert migrate.safety_copy(engine, backups) is not None
    assert backups.stat().st_mode & 0o777 == 0o700


def test_two_safety_copies_in_the_same_second_never_overwrite_each_other(tmp_path: Path) -> None:
    """Two Mealwrights started at once: the second copy could be of a half-upgraded database,
    so it must never replace the clean one (review r1)."""
    engine = _old_database(tmp_path / "mealwright.db")
    backups = tmp_path / "backups"
    at = datetime(2026, 10, 30, 14, 25, 1, tzinfo=UTC)
    first = migrate.safety_copy(engine, backups, now=at)
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE household SET name = 'Changed'")
    second = migrate.safety_copy(engine, backups, now=at)
    assert first is not None and second is not None
    assert first.name == f"pre-upgrade-{OLD}-20261030-142501.db"
    assert second.name == f"pre-upgrade-{OLD}-20261030-142501-2.db"
    with sqlite3.connect(first) as db:
        assert db.execute("SELECT name FROM household").fetchall() == [("Home",)]
    assert migrate.SAFETY_COPY_NAME.match(second.name)
    assert migrate._made_on(second.name) == " (made on 2026-10-30)"


def test_a_same_second_copy_counts_as_newer_in_the_trim(tmp_path: Path) -> None:
    backups = tmp_path / "backups"
    backups.mkdir()
    names = [
        "pre-upgrade-d7a4c2e81f56-20261030-090000.db",
        "pre-upgrade-d7a4c2e81f56-20261031-090000.db",
        "pre-upgrade-d7a4c2e81f56-20261031-090000-2.db",
        "pre-upgrade-d7a4c2e81f56-20261031-090000-10.db",
    ]
    for name in names:
        (backups / name).write_bytes(b"x")
    migrate._keep_newest(backups)
    assert _copies(backups) == sorted(names[1:])


def test_a_same_second_part_file_from_another_process_is_tidied(tmp_path: Path) -> None:
    backups = tmp_path / "backups"
    backups.mkdir()
    stale = backups / "pre-upgrade-d7a4c2e81f56-20261031-090000-2.db.99999999.part"
    stale.write_bytes(b"x")
    migrate._keep_newest(backups)
    assert not stale.exists()
