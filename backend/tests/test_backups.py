"""Mealwright's own backups (0.9, D1; spec section 7, "Backups", cabledrawer 17 Oct).

A backup is a consistent copy that opens on its own, readable by Mealwright only, in a folder
only it can open; the job makes one when a slot has passed and keeps the number chosen; an admin
changes how often and how many and can back up now; everyone else can only look.
"""

import sqlite3
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from mealwright import backups
from mealwright.models import Household

API = "/api/v1/your-data/backups"
ADMINS_ONLY = "Only the household’s admin can change this."


def _folder(client: TestClient) -> Path:
    return Path(client.app.state.settings.data_dir) / backups.FOLDER  # type: ignore[attr-defined]


def _household(client: TestClient) -> Household:
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        household = db.get(Household, 1)
        assert household is not None
        db.expunge(household)
        return household


def _add_recipe(client: TestClient, title: str) -> None:
    response = client.post("/api/v1/recipes", json={"name": title})
    assert response.status_code == 201, response.text


# --- The copy -------------------------------------------------------------------------------------


def test_a_backup_opens_on_its_own_and_holds_the_data(kitchen: TestClient) -> None:
    _add_recipe(kitchen, "Dal for the backup")
    response = kitchen.post(API)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["problem"] is None
    assert body["count"] == 1
    path = backups.backups(_folder(kitchen))[0].path
    assert body["last"]["size"] == path.stat().st_size > 0
    # One file: no "-wal" or "-shm" beside it, and nothing half-written left.
    assert sorted(p.name for p in path.parent.iterdir()) == [path.name]
    with sqlite3.connect(path) as copy:
        assert copy.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert copy.execute("PRAGMA journal_mode").fetchone() == ("delete",)
        titles = [row[0] for row in copy.execute("SELECT name FROM recipe")]
    assert titles == ["Dal for the backup"]


def test_backups_are_readable_by_mealwright_only(kitchen: TestClient) -> None:
    folder = _folder(kitchen)
    folder.mkdir(mode=0o755)
    folder.chmod(0o755)  # as a folder made before 0.9 could be
    assert kitchen.post(API).status_code == 200
    assert stat.S_IMODE(folder.stat().st_mode) == 0o700
    for path in folder.iterdir():
        assert stat.S_IMODE(path.stat().st_mode) == 0o600


def test_only_the_newest_are_kept_and_other_copies_are_never_trimmed(
    kitchen: TestClient,
) -> None:
    engine = kitchen.app.state.engine  # type: ignore[attr-defined]
    folder = _folder(kitchen)
    start = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)
    backups.make_folder(folder)
    (folder / "pre-upgrade-0.8.0-20261101-020000.db").write_bytes(b"x")
    backups.before_delete_everything(engine, folder, start)
    for day in range(5):
        backups.back_up(engine, folder, 3, start + timedelta(days=day))
    names = sorted(p.name for p in folder.iterdir())
    assert names == [
        "backup-20261103-030000.db",
        "backup-20261104-030000.db",
        "backup-20261105-030000.db",
        "before-delete-everything-20261101-030000.db",
        "pre-upgrade-0.8.0-20261101-020000.db",
    ]


def test_a_backup_that_cannot_be_written_says_why_and_leaves_nothing(
    kitchen: TestClient,
) -> None:
    folder = _folder(kitchen)
    folder.write_text("a file where the folder should be")
    body = kitchen.post(API).json()
    assert body["problem"].startswith("The backup couldn’t be written (")
    assert body["problem_at"] is not None
    assert body["last"] is None
    folder.unlink()
    body = kitchen.post(API).json()  # works again: the problem goes
    assert body["problem"] is None
    assert body["problem_at"] is None
    assert body["last"] is not None


# --- When -----------------------------------------------------------------------------------------


def _at(household: Household, every: str, time_zone: str | None = None) -> Household:
    household.backup_every = every
    household.time_zone = time_zone
    household.backup_problem_at = None
    return household


@pytest.mark.parametrize(
    ("every", "now", "slot"),
    [
        ("daily", datetime(2026, 11, 11, 2, 59, tzinfo=UTC), datetime(2026, 11, 10, 3, tzinfo=UTC)),
        ("daily", datetime(2026, 11, 11, 3, 0, tzinfo=UTC), datetime(2026, 11, 11, 3, tzinfo=UTC)),
        (
            "twice-daily",
            datetime(2026, 11, 11, 16, tzinfo=UTC),
            datetime(2026, 11, 11, 15, tzinfo=UTC),
        ),
        (
            "twice-daily",
            datetime(2026, 11, 11, 14, tzinfo=UTC),
            datetime(2026, 11, 11, 3, tzinfo=UTC),
        ),
        # 11 Nov 2026 is a Wednesday: the last Monday 03:00 was the 9th.
        ("weekly", datetime(2026, 11, 11, 12, tzinfo=UTC), datetime(2026, 11, 9, 3, tzinfo=UTC)),
        ("weekly", datetime(2026, 11, 9, 2, tzinfo=UTC), datetime(2026, 11, 2, 3, tzinfo=UTC)),
    ],
)
def test_the_last_slot(every: str, now: datetime, slot: datetime) -> None:
    household = _at(Household(name="Home"), every)
    assert backups.last_slot(household, now) == slot


def test_the_slot_is_03_00_in_the_households_own_time() -> None:
    household = _at(Household(name="Home"), "daily", "Asia/Kolkata")  # UTC+05:30
    now = datetime(2026, 11, 11, 0, 0, tzinfo=UTC)  # 05:30 there
    assert backups.last_slot(household, now) == datetime(2026, 11, 10, 21, 30, tzinfo=UTC)


def test_the_job_backs_up_when_due_and_not_again(kitchen: TestClient) -> None:
    app = kitchen.app
    folder = _folder(kitchen)
    now = datetime(2026, 11, 11, 3, 5, tzinfo=UTC)
    made = backups.run_if_due(app.state.sessionmaker, app.state.engine, folder, now)  # type: ignore[attr-defined]
    assert made is not None
    assert made.made_at == datetime(2026, 11, 11, 3, 5, tzinfo=UTC)
    later = now + timedelta(minutes=10)
    assert backups.run_if_due(app.state.sessionmaker, app.state.engine, folder, later) is None  # type: ignore[attr-defined]
    tomorrow = now + timedelta(days=1)
    assert backups.run_if_due(app.state.sessionmaker, app.state.engine, folder, tomorrow)  # type: ignore[attr-defined]
    assert len(backups.backups(folder)) == 2


def test_after_a_failure_the_job_waits_an_hour(kitchen: TestClient) -> None:
    app = kitchen.app
    folder = _folder(kitchen)
    folder.write_text("in the way")
    now = datetime(2026, 11, 11, 3, 0, tzinfo=UTC)
    assert backups.run_if_due(app.state.sessionmaker, app.state.engine, folder, now) is None  # type: ignore[attr-defined]
    assert _household(kitchen).backup_problem is not None
    folder.unlink()
    soon = now + timedelta(minutes=50)
    assert backups.run_if_due(app.state.sessionmaker, app.state.engine, folder, soon) is None  # type: ignore[attr-defined]
    assert not folder.exists()
    hour = now + timedelta(hours=1)
    assert backups.run_if_due(app.state.sessionmaker, app.state.engine, folder, hour) is not None  # type: ignore[attr-defined]
    assert _household(kitchen).backup_problem is None


def test_the_job_never_raises(kitchen: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    app = kitchen.app

    def broken(*_: object) -> None:
        raise RuntimeError("something unexpected")

    monkeypatch.setattr(backups, "back_up", broken)
    now = datetime(2026, 11, 11, 3, 0, tzinfo=UTC)
    assert (
        backups.run_if_due(app.state.sessionmaker, app.state.engine, _folder(kitchen), now) is None
    )  # type: ignore[attr-defined]
    assert _household(kitchen).backup_problem == "The backup failed. The log says why."


# --- The settings ---------------------------------------------------------------------------------


def test_daily_and_7_until_changed(kitchen: TestClient) -> None:
    body = kitchen.get(API).json()
    assert body["every"] == "daily"
    assert body["keep"] == 7
    assert body["last"] is None
    assert body["count"] == 0
    assert body["folder"] == str(_folder(kitchen))


def test_an_admin_changes_how_often_and_how_many(kitchen: TestClient) -> None:
    engine = kitchen.app.state.engine  # type: ignore[attr-defined]
    folder = _folder(kitchen)
    start = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)
    for day in range(4):
        backups.back_up(engine, folder, 7, start + timedelta(days=day))
    response = kitchen.patch(
        API, json={"every": "weekly", "keep": 2, "password": "correct horse battery"}
    )  # keeping fewer than there are asks for the password (R6)
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["every"], body["keep"], body["count"]) == ("weekly", 2, 2)
    assert body["last"]["at"].startswith("2026-11-04T03:00:00")
    household = _household(kitchen)
    assert (household.backup_every, household.backup_keep) == ("weekly", 2)


def test_twice_a_day_is_twice_daily_in_the_api(kitchen: TestClient) -> None:
    """D3 (BE29): the API says `twice_daily`, snake_case like every other value; the database
    keeps "twice-daily" as stored before, so a household that chose it still reads right."""
    response = kitchen.patch(API, json={"every": "twice_daily"})
    assert response.status_code == 200, response.text
    assert response.json()["every"] == "twice_daily"
    assert _household(kitchen).backup_every == "twice-daily"
    assert kitchen.get(API).json()["every"] == "twice_daily"
    assert kitchen.patch(API, json={"every": "twice-daily"}).status_code == 422


@pytest.mark.parametrize("body", [{"keep": 0}, {"keep": 31}, {"every": "hourly"}])
def test_out_of_range_is_refused(kitchen: TestClient, body: dict[str, object]) -> None:
    assert kitchen.patch(API, json=body).status_code == 422
    assert kitchen.get(API).json()["keep"] == 7


def test_a_member_cannot_look_change_or_back_up(kitchen: TestClient, member: TestClient) -> None:
    # D4, BE12 (proposed, for cabledrawer): the Household group is for admins only.
    for response in (member.get(API), member.patch(API, json={"keep": 3}), member.post(API)):
        assert response.status_code == 403
        assert response.json()["detail"] == ADMINS_ONLY
    assert kitchen.get(API).json()["keep"] == 7
    assert not _folder(member).exists()


def test_signed_out_sees_nothing(client: TestClient) -> None:
    assert client.get(API).status_code == 401
    assert client.post(API).status_code == 401


def test_one_households_settings_are_its_own(kitchen: TestClient, neighbour: TestClient) -> None:
    assert neighbour.patch(API, json={"keep": 3}).status_code == 200
    assert kitchen.get(API).json()["keep"] == 7
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        keeps = {h.id: h.backup_keep for h in db.scalars(select(Household))}
    assert keeps == {1: 7, 2: 3}


def test_the_partial_file_is_removed_when_the_copy_fails(kitchen: TestClient) -> None:
    folder = _folder(kitchen)
    backups.make_folder(folder)
    real = kitchen.app.state.engine  # type: ignore[attr-defined]

    class NotSqlite:
        driver_connection = object()

        def close(self) -> None:
            pass

    class Engine:  # SQLite by its name, but its connection isn't one: the copy fails midway
        dialect = real.dialect
        url = real.url

        def raw_connection(self) -> NotSqlite:
            assert [p.suffix for p in folder.iterdir()] == [".part"]  # made before the copy
            return NotSqlite()

    with pytest.raises(sqlite3.Error):
        backups.copy_database(Engine(), folder / "copy.db")  # type: ignore[arg-type]
    assert list(folder.iterdir()) == []


# --- Never over another copy (review r1) ------------------------------------------------------


def _recipes_in(path: Path) -> list[str]:
    with sqlite3.connect(path) as copy:
        return [row[0] for row in copy.execute("SELECT name FROM recipe")]


def test_a_copy_never_overwrites_a_file_already_there(kitchen: TestClient) -> None:
    engine = kitchen.app.state.engine  # type: ignore[attr-defined]
    folder = _folder(kitchen)
    backups.make_folder(folder)
    target = folder / "copy.db"
    target.write_bytes(b"the good copy")
    with pytest.raises(FileExistsError):
        backups.copy_database(engine, target)
    assert target.read_bytes() == b"the good copy"
    assert [p.name for p in folder.iterdir()] == ["copy.db"]  # nothing half-written left


def test_a_copy_never_overwrites_one_that_appears_while_it_is_written(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = kitchen.app.state.engine  # type: ignore[attr-defined]
    folder = _folder(kitchen)
    backups.make_folder(folder)
    target = folder / "copy.db"
    real = sqlite3.connect

    def another_writer_meanwhile(path: object, *args: object, **kwargs: object) -> object:
        target.write_bytes(b"the good copy")  # made by someone else while this copy is written
        return real(path, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(backups.sqlite3, "connect", another_writer_meanwhile)
    with pytest.raises(FileExistsError):
        backups.copy_database(engine, target)
    assert target.read_bytes() == b"the good copy"
    assert [p.name for p in folder.iterdir()] == ["copy.db"]


def test_without_hard_links_a_copy_still_never_overwrites(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Some shared folders (a NAS share) can't make hard links: the copy is renamed instead."""
    _add_recipe(kitchen, "Dal")
    engine = kitchen.app.state.engine  # type: ignore[attr-defined]
    folder = _folder(kitchen)
    backups.make_folder(folder)

    def no_links(*_args: object, **_kwargs: object) -> None:
        raise PermissionError(1, "Operation not permitted")

    monkeypatch.setattr(backups.os, "link", no_links)
    backups.copy_database(engine, folder / "copy.db")
    assert _recipes_in(folder / "copy.db") == ["Dal"]
    (folder / "taken.db").write_bytes(b"the good copy")
    with pytest.raises(FileExistsError):
        backups.copy_database(engine, folder / "taken.db")
    assert (folder / "taken.db").read_bytes() == b"the good copy"
    assert sorted(p.name for p in folder.iterdir()) == ["copy.db", "taken.db"]


def test_two_backups_in_the_same_second_the_first_stands(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = kitchen.app.state.engine  # type: ignore[attr-defined]
    folder = _folder(kitchen)
    at = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)
    _add_recipe(kitchen, "In the first")
    first = backups.back_up(engine, folder, 7, at)
    _add_recipe(kitchen, "After it")
    second = backups.back_up(engine, folder, 7, at)
    assert second.path == first.path
    assert _recipes_in(first.path) == ["In the first"]


def test_a_backup_whose_name_is_taken_while_it_is_made_leaves_the_other_one(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Another Mealwright process (say, one starting up) writes the same name meanwhile."""
    engine = kitchen.app.state.engine  # type: ignore[attr-defined]
    folder = _folder(kitchen)
    at = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)
    real = backups.copy_database

    def taken_meanwhile(engine: object, target: Path, photos: Path | None = None) -> None:
        target.write_bytes(b"the other process's copy")
        real(engine, target)  # type: ignore[arg-type]

    monkeypatch.setattr(backups, "copy_database", taken_meanwhile)
    made = backups.back_up(engine, folder, 7, at)
    assert made.path.name == "backup-20261101-030000.db"
    assert made.path.read_bytes() == b"the other process's copy"
    assert [p.name for p in folder.iterdir()] == [made.path.name]


def test_two_safety_backups_in_the_same_second_both_stay(kitchen: TestClient) -> None:
    engine = kitchen.app.state.engine  # type: ignore[attr-defined]
    folder = _folder(kitchen)
    at = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)
    _add_recipe(kitchen, "Kept")
    first = backups.before_delete_everything(engine, folder, at)
    with kitchen.app.state.engine.begin() as connection:  # type: ignore[attr-defined]
        connection.exec_driver_sql("DELETE FROM recipe")
    second = backups.before_delete_everything(engine, folder, at)
    third = backups.before_delete_everything(engine, folder, at)
    assert first.name == "before-delete-everything-20261101-030000.db"
    assert second.name == "before-delete-everything-20261101-030000-2.db"
    assert third.name == "before-delete-everything-20261101-030000-3.db"
    assert _recipes_in(first) == ["Kept"]  # the good copy is never replaced by an empty one
    assert _recipes_in(second) == []
    assert backups.backups(folder) == []  # not Mealwright's own: never trimmed
