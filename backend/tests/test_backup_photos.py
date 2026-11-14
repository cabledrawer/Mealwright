"""Backups and the safety copy include the recipe photos (0.9.5 step 16f, D2; cabledrawer 13 Nov).

A copy of the database gets a photo folder beside it (`backup-<stamp>-photos/`) of hard links to
the live photo files; "Include photos" (on by default) leaves it out; a failure leaves nothing
half-made and the older backups alone; a photo added or deleted while a backup runs breaks nothing.
"""

import errno
import os
import shutil
import sqlite3
import stat
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from photo_kit import uploaded
from sqlalchemy import Engine

from mealwright import backups, migrate
from mealwright.auth import hash_password
from mealwright.db import make_engine
from mealwright.models import Login

API = "/api/v1/backups"


@pytest.fixture
def member(kitchen: TestClient) -> Iterator[TestClient]:
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(
            Login(
                household_id=1,
                username="lorna",
                name="Lorna",
                password_hash=hash_password("lorna's own password"),
                role="member",
            )
        )
        db.commit()
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        body = {"username": "lorna", "password": "lorna's own password"}
        assert other.post("/api/v1/session", json=body).status_code == 200
        yield other


def _data(client: TestClient) -> Path:
    return Path(client.app.state.settings.data_dir)  # type: ignore[attr-defined]


def _folder(client: TestClient) -> Path:
    return _data(client) / backups.FOLDER


def _store(client: TestClient) -> Path:
    return _data(client) / "photos"


def _engine(client: TestClient) -> Engine:
    return client.app.state.engine  # type: ignore[attr-defined, no-any-return]


def _photo(store: Path, key: str, content: bytes = b"a photo", household: int = 1) -> Path:
    folder = store / str(household)
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{key * 32}.jpg"
    path.write_bytes(content)
    return path


def _files(folder: Path) -> dict[str, bytes]:
    return {str(p.relative_to(folder)): p.read_bytes() for p in folder.rglob("*") if p.is_file()}


# --- What a backup holds ----------------------------------------------------------------------


def test_a_backup_holds_the_photos_as_links_to_the_live_files(kitchen: TestClient) -> None:
    live = _photo(_store(kitchen), "a", b"sambar")
    _photo(_store(kitchen), "b", b"dal", household=2)
    assert kitchen.post(API).status_code == 200
    (backup,) = backups.backups(_folder(kitchen))
    beside = backups.photos_beside(backup.path)
    assert beside.name == backup.path.name.removesuffix(".db") + "-photos"
    assert backup.photos is True
    assert _files(beside) == _files(_store(kitchen))  # the same <household>/<file> layout
    # A link, not a second copy: no extra disk for a photo that hasn't changed.
    assert (beside / "1" / live.name).stat().st_ino == live.stat().st_ino
    # Only Mealwright's own user can open the folders.
    assert stat.S_IMODE(beside.stat().st_mode) == 0o700
    assert stat.S_IMODE((beside / "1").stat().st_mode) == 0o700
    assert sorted(p.name for p in _folder(kitchen).iterdir()) == [
        beside.name,
        backup.path.name,
    ]


def test_a_backup_with_no_photos_has_no_photo_folder(kitchen: TestClient) -> None:
    assert kitchen.post(API).status_code == 200
    (backup,) = backups.backups(_folder(kitchen))
    assert backup.photos is False
    assert [p.name for p in _folder(kitchen).iterdir()] == [backup.path.name]


def test_files_that_are_not_photos_are_left_out(kitchen: TestClient) -> None:
    _photo(_store(kitchen), "a")
    (_store(kitchen) / "1" / ".upload-abc").write_bytes(b"half an upload")
    (_store(kitchen) / "1" / "notes.txt").write_bytes(b"not a photo")
    (_store(kitchen) / "stray.jpg").write_bytes(b"not in a household folder")
    assert kitchen.post(API).status_code == 200
    (backup,) = backups.backups(_folder(kitchen))
    assert list(_files(backups.photos_beside(backup.path))) == [f"1/{'a' * 32}.jpg"]


def test_a_photo_deleted_after_the_backup_stays_in_it(kitchen: TestClient) -> None:
    live = _photo(_store(kitchen), "a", b"sambar")
    assert kitchen.post(API).status_code == 200
    live.unlink()
    (backup,) = backups.backups(_folder(kitchen))
    assert _files(backups.photos_beside(backup.path)) == {f"1/{live.name}": b"sambar"}


def test_the_size_counts_the_photos(kitchen: TestClient) -> None:
    _photo(_store(kitchen), "a", b"x" * 5000)
    body = kitchen.post(API).json()
    (backup,) = backups.backups(_folder(kitchen))
    assert body["photos_size"] == 5000
    assert body["database_size"] > 0
    assert body["last"]["photos"] is True
    assert body["last"]["size"] == backup.size + 5000


# --- The switch -------------------------------------------------------------------------------


def test_photos_are_included_unless_the_switch_is_off(kitchen: TestClient) -> None:
    assert kitchen.get(API).json()["photos"] is True  # the usual
    _photo(_store(kitchen), "a")
    body = kitchen.patch(API, json={"photos": False}).json()
    assert body["photos"] is False
    assert kitchen.get(API).json()["photos"] is False  # kept
    body = kitchen.post(API).json()
    assert body["last"]["photos"] is False
    assert [p.suffix for p in _folder(kitchen).iterdir()] == [".db"]
    assert kitchen.patch(API, json={"photos": True}).json()["photos"] is True


def test_the_switch_changes_nothing_else_and_only_what_is_sent(kitchen: TestClient) -> None:
    kitchen.patch(API, json={"every": "weekly", "keep": 3})
    body = kitchen.patch(API, json={"photos": False}).json()
    assert (body["every"], body["keep"], body["photos"]) == ("weekly", 3, False)
    body = kitchen.patch(API, json={"keep": 5}).json()
    assert (body["every"], body["keep"], body["photos"]) == ("weekly", 5, False)


def test_only_an_admin_changes_the_switch(kitchen: TestClient, member: TestClient) -> None:
    assert member.get(API).json()["photos"] is True  # a member can look
    assert member.patch(API, json={"photos": False}).status_code == 403
    assert kitchen.get(API).json()["photos"] is True


def test_the_scheduled_job_follows_the_switch(kitchen: TestClient) -> None:
    app = kitchen.app
    _photo(_store(kitchen), "a")
    start = datetime(2026, 11, 11, 3, 5, tzinfo=UTC)
    args = (app.state.sessionmaker, app.state.engine, _folder(kitchen))  # type: ignore[attr-defined]
    first = backups.run_if_due(*args, start)
    assert first is not None
    assert first.photos is True
    assert backups.photos_beside(first.path).is_dir()
    kitchen.patch(API, json={"photos": False})
    second = backups.run_if_due(*args, start + timedelta(days=1))
    assert second is not None
    assert second.photos is False
    assert not backups.photos_beside(second.path).exists()


# --- Staying consistent while the app is in use -----------------------------------------------


def test_a_photo_added_while_the_database_is_copied_is_in_the_backup(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The database copy may point to a photo saved after the first look at the folder."""
    _photo(_store(kitchen), "a")
    engine = _engine(kitchen)
    real = sqlite3.connect

    def a_photo_arrives(path: object, *args: object, **kwargs: object) -> object:
        _photo(_store(kitchen), "b", b"arrived meanwhile")
        return real(path, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(sqlite3, "connect", a_photo_arrives)
    backups.back_up(engine, _folder(kitchen), 7, photos=_store(kitchen))
    (backup,) = backups.backups(_folder(kitchen))
    held = _files(backups.photos_beside(backup.path))
    assert held == {f"1/{'a' * 32}.jpg": b"a photo", f"1/{'b' * 32}.jpg": b"arrived meanwhile"}


def test_a_photo_deleted_while_the_database_is_copied_does_not_break_the_backup(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """It was linked before the database was copied, so the copy that points to it has it."""
    gone = _photo(_store(kitchen), "a", b"deleted meanwhile")
    engine = _engine(kitchen)
    real = sqlite3.connect

    def a_photo_goes(path: object, *args: object, **kwargs: object) -> object:
        gone.unlink()
        return real(path, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(sqlite3, "connect", a_photo_goes)
    made = backups.back_up(engine, _folder(kitchen), 7, photos=_store(kitchen))
    assert made.photos is True
    assert _files(backups.photos_beside(made.path)) == {f"1/{gone.name}": b"deleted meanwhile"}


def test_a_photo_that_vanishes_before_it_is_linked_is_skipped(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _photo(_store(kitchen), "a")
    _photo(_store(kitchen), "b")
    real = os.link

    def one_is_gone(source: object, target: object, *args: object, **kwargs: object) -> None:
        if str(source).endswith(f"{'a' * 32}.jpg"):
            raise FileNotFoundError(errno.ENOENT, "No such file or directory")
        real(source, target, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "link", one_is_gone)
    made = backups.back_up(_engine(kitchen), _folder(kitchen), 7, photos=_store(kitchen))
    assert list(_files(backups.photos_beside(made.path))) == [f"1/{'b' * 32}.jpg"]


def test_the_photo_copies_are_made_before_the_database_is_copied_never_during(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The database's online copy is one call, started after the photos are linked and finished
    before they are looked at again: no photo is copied while it runs."""
    _photo(_store(kitchen), "a")
    events: list[str] = []
    real_link = os.link
    real_connect = sqlite3.connect

    def link(source: object, target: object, *args: object, **kwargs: object) -> None:
        events.append("photo")
        real_link(source, target, *args, **kwargs)  # type: ignore[arg-type]

    def connect(path: object, *args: object, **kwargs: object) -> object:
        events.append("database")
        return real_connect(path, *args, **kwargs)  # type: ignore[call-overload]

    monkeypatch.setattr(os, "link", link)
    monkeypatch.setattr(sqlite3, "connect", connect)
    backups.back_up(_engine(kitchen), _folder(kitchen), 7, photos=_store(kitchen))
    assert events[:2] == ["photo", "database"]


# --- Where a hard link can't be made, and where the disk is full -------------------------------


def test_where_hard_links_cant_be_made_the_photos_are_copied(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    live = _photo(_store(kitchen), "a", b"sambar")

    def no_links(*_args: object, **_kwargs: object) -> None:
        raise OSError(errno.EXDEV, "Invalid cross-device link")

    real = os.link
    monkeypatch.setattr(
        os,
        "link",
        lambda source, target, *a, **k: (
            no_links() if str(target).find("-photos") >= 0 else real(source, target, *a, **k)
        ),
    )
    made = backups.back_up(_engine(kitchen), _folder(kitchen), 7, photos=_store(kitchen))
    copy = backups.photos_beside(made.path) / "1" / live.name
    assert copy.read_bytes() == b"sambar"
    assert copy.stat().st_ino != live.stat().st_ino  # a real copy
    assert stat.S_IMODE(copy.stat().st_mode) == 0o600
    assert made.path.is_file()


def test_a_full_disk_fails_with_one_plain_line_and_leaves_no_half_made_file(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _photo(_store(kitchen), "a")
    _photo(_store(kitchen), "b")
    folder = _folder(kitchen)
    old = backups.back_up(
        _engine(kitchen), folder, 7, datetime(2026, 11, 1, 3, tzinfo=UTC), _store(kitchen)
    )
    before = sorted(p.name for p in folder.iterdir())
    real = os.link
    count = []

    def disk_fills_up(source: object, target: object, *args: object, **kwargs: object) -> None:
        count.append(1)
        if len(count) > 1:
            raise OSError(errno.ENOSPC, "No space left on device")
        real(source, target, *args, **kwargs)  # type: ignore[arg-type]

    monkeypatch.setattr(os, "link", disk_fills_up)
    with pytest.raises(backups.BackupFailed) as failed:
        backups.back_up(
            _engine(kitchen), folder, 7, datetime(2026, 11, 2, 3, tzinfo=UTC), _store(kitchen)
        )
    assert str(failed.value) == "The backup couldn’t be written (No space left on device)."
    assert sorted(p.name for p in folder.iterdir()) == before  # nothing half-made, old one stays
    assert backups.backups(folder)[0].path == old.path


def test_a_full_disk_while_a_photo_is_copied_leaves_nothing_either(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _photo(_store(kitchen), "a")
    folder = _folder(kitchen)

    def no_links(*_args: object, **_kwargs: object) -> None:
        raise PermissionError(errno.EPERM, "Operation not permitted")

    def disk_full(*_args: object, **_kwargs: object) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    real = os.link
    monkeypatch.setattr(
        os,
        "link",
        lambda source, target, *a, **k: (
            no_links() if "-photos" in str(target) else real(source, target, *a, **k)
        ),
    )
    monkeypatch.setattr(shutil, "copyfile", disk_full)
    with pytest.raises(backups.BackupFailed, match="No space left on device"):
        backups.back_up(_engine(kitchen), folder, 7, photos=_store(kitchen))
    assert list(folder.iterdir()) == []


def test_a_failed_by_hand_backup_says_so_on_the_screen(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _photo(_store(kitchen), "a")

    def disk_full(*_args: object, **_kwargs: object) -> None:
        raise OSError(errno.ENOSPC, "No space left on device")

    monkeypatch.setattr(os, "link", disk_full)
    body = kitchen.post(API).json()
    assert body["problem"] == "The backup couldn’t be written (No space left on device)."
    assert list(_folder(kitchen).iterdir()) == []


# --- Trimming ---------------------------------------------------------------------------------


def test_trimming_removes_the_photo_folder_with_its_backup(kitchen: TestClient) -> None:
    live = _photo(_store(kitchen), "a", b"sambar")
    folder = _folder(kitchen)
    start = datetime(2026, 11, 1, 3, tzinfo=UTC)
    for day in range(4):
        backups.back_up(_engine(kitchen), folder, 2, start + timedelta(days=day), _store(kitchen))
    assert sorted(p.name for p in folder.iterdir()) == [
        "backup-20261103-030000-photos",
        "backup-20261103-030000.db",
        "backup-20261104-030000-photos",
        "backup-20261104-030000.db",
    ]
    assert live.read_bytes() == b"sambar"  # the live photo is never touched by a trim


def test_a_photo_folder_with_no_database_or_half_made_is_tidied_away(kitchen: TestClient) -> None:
    folder = _folder(kitchen)
    backups.make_folder(folder)
    (folder / "backup-20261101-030000-photos" / "1").mkdir(parents=True)
    (folder / "backup-20261101-030000-photos.99999999.part" / "1").mkdir(parents=True)
    (folder / "pre-upgrade-abc-20261101-030000-photos").mkdir()  # not a backup's: left alone
    backups.trim(folder, 7)
    assert [p.name for p in folder.iterdir()] == ["pre-upgrade-abc-20261101-030000-photos"]


# --- Restoring --------------------------------------------------------------------------------


def test_copying_the_photo_folder_back_restores_the_photos(kitchen: TestClient) -> None:
    """The restore page's step: `cp -an <backup>-photos/. data/photos/`."""
    live = _photo(_store(kitchen), "a", b"sambar")
    assert kitchen.post(API).status_code == 200
    (backup,) = backups.backups(_folder(kitchen))
    shutil.rmtree(_store(kitchen))
    shutil.copytree(backups.photos_beside(backup.path), _store(kitchen), dirs_exist_ok=True)
    assert live.read_bytes() == b"sambar"


def test_a_backup_from_an_older_version_has_no_photo_folder_and_is_listed(
    kitchen: TestClient,
) -> None:
    folder = _folder(kitchen)
    backups.make_folder(folder)
    backups.copy_database(_engine(kitchen), folder / "backup-20261001-030000.db")
    body = kitchen.get(API).json()
    assert body["last"]["photos"] is False
    assert body["count"] == 1


# --- Delete everything's safety backup -------------------------------------------------------


def test_the_safety_backup_before_delete_everything_holds_the_photos(kitchen: TestClient) -> None:
    live = _photo(_store(kitchen), "a", b"sambar")
    path = backups.before_delete_everything(
        _engine(kitchen), _folder(kitchen), datetime(2026, 11, 1, 3, tzinfo=UTC), _store(kitchen)
    )
    shutil.rmtree(_store(kitchen))  # what Delete everything does
    assert (backups.photos_beside(path) / "1" / live.name).read_bytes() == b"sambar"
    # Never trimmed, with or without the photos.
    backups.trim(_folder(kitchen), 1)
    assert path.is_file()
    assert backups.photos_beside(path).is_dir()


# --- The safety copy before an upgrade --------------------------------------------------------

OLD = "a4c8e1f7b296"  # any revision before the newest (as test_safety_copy.py)
BEFORE_SWITCH = "b8e2d4f6a913"  # the line's head before the switch's column


def _old_database(path: Path, revision: str = OLD) -> Engine:
    engine = make_engine(f"sqlite:///{path}")
    migrate.upgrade(engine, revision)
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "INSERT INTO household (id, name, created_at) VALUES (1, 'Home', '2026-10-01')"
        )
    return engine


def test_the_safety_copy_holds_the_photos_and_going_back_by_it_brings_them(tmp_path: Path) -> None:
    engine = _old_database(tmp_path / "mealwright.db")  # an older database: no switch column yet
    store = tmp_path / "photos"
    live = _photo(store, "a", b"sambar")
    folder = tmp_path / "backups"
    migrate.upgrade(engine, backups=folder, photos=store)
    (copy,) = folder.glob("pre-upgrade-*.db")
    assert _files(backups.photos_beside(copy)) == {f"1/{live.name}": b"sambar"}
    assert (backups.photos_beside(copy) / "1" / live.name).stat().st_ino == live.stat().st_ino


def test_the_switch_is_read_from_the_database_before_the_upgrade(tmp_path: Path) -> None:
    engine = _old_database(tmp_path / "mealwright.db", BEFORE_SWITCH)
    assert migrate.include_photos(engine) is True  # no column yet: the usual
    migrate.upgrade(engine, "head")
    assert migrate.include_photos(engine) is True
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE household SET backup_photos = 0")
    assert migrate.include_photos(engine) is False
    with engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM household")
    assert migrate.include_photos(engine) is True  # nobody to ask: the usual


def test_a_safety_copy_without_the_switch_column_is_made_with_the_photos(tmp_path: Path) -> None:
    engine = _old_database(tmp_path / "mealwright.db", BEFORE_SWITCH)
    store = tmp_path / "photos"
    _photo(store, "a")
    copy = migrate.safety_copy(engine, tmp_path / "backups", photos=store)
    assert copy is not None
    assert backups.photos_beside(copy).is_dir()


def test_the_safety_copy_with_the_switch_off_has_no_photo_folder(tmp_path: Path) -> None:
    engine = _old_database(tmp_path / "mealwright.db", BEFORE_SWITCH)
    migrate.upgrade(engine, "head")
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE household SET backup_photos = 0")
    # Pretend the database is behind: stamp it back one revision without touching the column.
    with engine.begin() as connection:
        connection.exec_driver_sql("UPDATE alembic_version SET version_num = ?", (BEFORE_SWITCH,))
    store = tmp_path / "photos"
    _photo(store, "a")
    copy = migrate.safety_copy(engine, tmp_path / "backups", photos=store)
    assert copy is not None
    assert not backups.photos_beside(copy).exists()


def test_the_safety_copies_are_trimmed_with_their_photo_folders(tmp_path: Path) -> None:
    store = tmp_path / "photos"
    _photo(store, "a")
    engine = _old_database(tmp_path / "mealwright.db")
    folder = tmp_path / "backups"
    for number in range(5):
        stamp = datetime(2026, 10, 1 + number, 3, tzinfo=UTC)
        migrate.safety_copy(engine, folder, now=stamp, photos=store)
    migrate.upgrade(engine, backups=folder, photos=store)
    names = sorted(p.name for p in folder.iterdir())
    dbs = [n for n in names if n.endswith(".db")]
    dirs = [n for n in names if n.endswith("-photos")]
    assert len(dbs) == migrate.SAFETY_COPIES_KEPT
    assert dirs == [n.removesuffix(".db") + "-photos" for n in dbs]


def test_a_real_photo_comes_back_from_the_backup_and_a_missing_one_is_only_a_404(
    kitchen: TestClient,
) -> None:
    """With photos in the backup, copying the folder back brings the photo; without them (the
    switch off) the restored database still points to it, the file answers 404, and the recipe
    and everything else carry on (what the app really does, D2)."""
    photo = uploaded(kitchen)
    made = kitchen.post("/api/v1/recipes", json={"name": "Sambar", "photo_id": photo["id"]})
    assert made.status_code == 201, made.text
    recipe_id = made.json()["id"]
    url = made.json()["photo"]["url"]
    assert kitchen.get(url).status_code == 200
    assert kitchen.post(API).status_code == 200
    (backup,) = backups.backups(_folder(kitchen))
    shutil.rmtree(_store(kitchen))  # a new server: the database is back, the photo files aren't
    assert kitchen.get(url).status_code == 404  # no photos in the restore: a plain "not found"
    assert kitchen.get(f"/api/v1/recipes/{recipe_id}").status_code == 200
    assert kitchen.get("/api/v1/recipes").status_code == 200
    shutil.copytree(backups.photos_beside(backup.path), _store(kitchen))  # cp -an, as the docs say
    assert kitchen.get(url).status_code == 200
