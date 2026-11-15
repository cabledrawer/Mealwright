"""Delete everything / start again (0.9, D1; the mockup's proposal, for cabledrawer).

Admins only, with the typed words and the admin's own password. A safety backup first, and
nothing deleted if it can't be made. Every row and photo of the household goes; the backups
stay; everyone is signed out; Mealwright then asks for first-run setup. The other household
(tests only) is untouched.
"""

import logging
import threading
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import test_households
from conftest import ADMIN, SETUP_CODE
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from test_households import snapshot

from mealwright import backups
from mealwright.api.v1 import your_data
from mealwright.auth import COOKIE, hash_password
from mealwright.models import Change, Household, ListItem, ListTick, Login

API = "/api/v1/delete-everything"
# Household 1 with something in nearly every table (the households test's own fixture).
filled = test_households.mine

RIGHT = {"words": "delete everything", "password": ADMIN["password"]}


@pytest.fixture
def member(kitchen: TestClient) -> Iterator[TestClient]:
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(
            Login(
                household_id=1,
                username="wren",
                name="Wren",
                password_hash=hash_password("wren's own password"),
                role="member",
            )
        )
        db.commit()
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        body = {"username": "wren", "password": "wren's own password"}
        assert other.post("/api/v1/session", json=body).status_code == 200
        yield other


def _data(client: TestClient) -> Path:
    return Path(client.app.state.settings.data_dir)  # type: ignore[attr-defined]


def _rows(client: TestClient) -> int:
    return sum(len(rows) for rows in snapshot(client).values())


def _tick_on_a_change(client: TestClient, change_id: int) -> None:
    """A shopping tick and a change pointing at it: the two tables that point at each other."""
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        item = db.scalars(select(ListItem).where(ListItem.household_id == 1)).first()
        assert item is not None
        db.add(ListTick(household_id=1, id="tick-1", item_id=item.id, login_name="Tess"))
        db.flush()
        db.execute(update(Change).where(Change.id == change_id).values(tick_id="tick-1"))
        db.commit()


def test_it_deletes_every_row_and_photo_keeps_backups_and_starts_again(
    kitchen: TestClient, filled: dict[str, Any], member: TestClient
) -> None:
    _tick_on_a_change(kitchen, filled["change_id"])
    assert _rows(kitchen) > 50
    photos = _data(kitchen) / "photos" / "1"
    assert any(photos.iterdir())
    assert kitchen.post("/api/v1/backups").status_code == 200
    folder = _data(kitchen) / backups.FOLDER
    (folder / "pre-upgrade-0.8.0-20261101-020000.db").write_bytes(b"older copy")
    before = {p.name for p in folder.iterdir()}

    response = kitchen.post(API, json=RIGHT)
    assert response.status_code == 204, response.text

    # Every row of the household, in every table, is gone.
    assert all(rows == [] for rows in snapshot(kitchen).values())
    assert not photos.exists()
    # The backups are kept, and a safety backup was made first, holding the data.
    after = {p.name for p in folder.iterdir()}
    assert before < after
    # The safety backup: the database, and the photos beside it (D2, 0.9.5), so a restore
    # brings them back.
    (safety,) = {name for name in after - before if name.endswith(".db")}
    assert safety.startswith("before-delete-everything-")
    assert (folder / safety).stat().st_size > 0
    assert after - before == {safety, safety.removesuffix(".db") + "-photos"}
    assert any((folder / (safety.removesuffix(".db") + "-photos") / "1").iterdir())
    # Everyone is signed out, the admin's cookie with them.
    assert COOKIE not in kitchen.cookies
    assert kitchen.get("/api/v1/me").status_code == 401
    assert member.get("/api/v1/me").status_code == 401
    # Mealwright starts again at first-run setup, and setup works.
    assert kitchen.get("/api/v1/setup").json()["needs_setup"] is True
    assert kitchen.post("/api/v1/setup", json=ADMIN).status_code == 201
    assert kitchen.get("/api/v1/recipes").status_code == 200


def test_it_prints_a_new_setup_code_because_first_run_setup_needs_one(
    kitchen: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    """First-run setup needs the code from the log (0.9 A2), and the one from start-up was
    forgotten when the admin was made: without a new one nobody could set up again until a
    restart."""
    assert kitchen.app.state.setup_code is None  # type: ignore[attr-defined]
    with caplog.at_level(logging.WARNING, logger="mealwright.setup"):
        assert kitchen.post(API, json=RIGHT).status_code == 204
    assert kitchen.app.state.setup_code == SETUP_CODE  # type: ignore[attr-defined]
    assert any(SETUP_CODE in record.getMessage() for record in caplog.records)
    without = ADMIN | {"setup_code": "ABCD-EFGH-JKMN"}
    assert kitchen.post("/api/v1/setup", json=without).status_code == 403
    assert kitchen.post("/api/v1/setup", json=ADMIN).status_code == 201


def test_the_safety_backup_holds_what_was_deleted(kitchen: TestClient) -> None:
    import sqlite3

    assert kitchen.post("/api/v1/recipes", json={"name": "Kept in the backup"}).status_code == 201
    assert kitchen.post(API, json=RIGHT).status_code == 204
    (safety,) = (_data(kitchen) / backups.FOLDER).glob("before-delete-everything-*.db")
    with sqlite3.connect(safety) as copy:
        assert copy.execute("SELECT name FROM recipe").fetchall() == [("Kept in the backup",)]


@pytest.mark.parametrize(
    "words", ["", "delete", "delete everything!", "delete  all", "please delete everything"]
)
def test_wrong_words_delete_nothing(kitchen: TestClient, words: str) -> None:
    kitchen.post("/api/v1/recipes", json={"name": "Still here"})
    rows = _rows(kitchen)
    response = kitchen.post(API, json={"words": words, "password": ADMIN["password"]})
    assert response.status_code == 422
    assert response.json()["detail"] == "Type “delete everything” to confirm."
    assert _rows(kitchen) == rows
    assert not (_data(kitchen) / backups.FOLDER).exists()  # no backup either


@pytest.mark.parametrize("words", ["Delete Everything", "  delete everything  "])
def test_the_words_ignore_capitals_and_spaces_around(kitchen: TestClient, words: str) -> None:
    assert (
        kitchen.post(API, json={"words": words, "password": ADMIN["password"]}).status_code == 204
    )


def test_a_wrong_password_deletes_nothing_and_is_slowed_down(kitchen: TestClient) -> None:
    rows = _rows(kitchen)
    wrong = {"words": "delete everything", "password": "not the password"}
    for _ in range(5):
        response = kitchen.post(API, json=wrong)
        assert response.status_code == 403
        assert response.json()["detail"] == "That password isn’t right."
    assert kitchen.post(API, json=wrong).status_code == 429
    assert kitchen.post(API, json=RIGHT).status_code == 429  # even the right one, for now
    assert _rows(kitchen) == rows
    assert kitchen.get("/api/v1/me").status_code == 200  # still signed in


# --- The password check counts wrong tries like sign-in and Change password (counted_check) ---


def _sign_in(kitchen: TestClient, password: str) -> int:
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        body = {"username": ADMIN["username"], "password": password}
        return other.post("/api/v1/session", json=body).status_code


def test_wrong_passwords_are_paused_in_sign_ins_words(kitchen: TestClient) -> None:
    wrong = {"words": "delete everything", "password": "not the password"}
    for _ in range(5):
        assert kitchen.post(API, json=wrong).status_code == 403
    paused = kitchen.post(API, json=RIGHT)
    assert paused.status_code == 429
    assert paused.json()["code"] == "username_paused"
    assert paused.json()["detail"].startswith("Too many wrong passwords for tess. Try again in")
    assert int(paused.headers["retry-after"]) > 0


def test_guessing_at_sign_in_doesnt_stop_the_admin_deleting(kitchen: TestClient) -> None:
    """As for Change password (0.9 A2): this check has the login's own count, apart from
    sign-in's, so someone guessing at the username can't hold the signed-in admin up."""
    for _ in range(6):
        _sign_in(kitchen, "a wrong guess")
    kitchen.app.state.slow_down.succeeded("addr:testclient")  # type: ignore[attr-defined]
    assert _sign_in(kitchen, ADMIN["password"]) == 429  # the username is paused at sign-in
    assert kitchen.post(API, json=RIGHT).status_code == 204


def test_wrong_passwords_here_dont_pause_signing_in(kitchen: TestClient) -> None:
    wrong = {"words": "delete everything", "password": "not the password"}
    for _ in range(5):
        assert kitchen.post(API, json=wrong).status_code == 403
    assert kitchen.post(API, json=wrong).status_code == 429
    assert _sign_in(kitchen, ADMIN["password"]) == 200


def test_wrong_passwords_here_and_in_change_password_are_one_count(kitchen: TestClient) -> None:
    wrong = {"words": "delete everything", "password": "not the password"}
    change = {"current_password": "not the password", "new_password": "a brand new password"}
    for _ in range(3):
        assert kitchen.post(API, json=wrong).status_code == 403
    for _ in range(2):
        assert kitchen.put("/api/v1/me/password", json=change).status_code == 422
    assert kitchen.post(API, json=RIGHT).status_code == 429
    assert kitchen.put("/api/v1/me/password", json=change).status_code == 429


def test_a_try_is_counted_before_its_password_is_hashed(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Counted first, so tries sent at once can't all be checked before any of them counts."""
    slow = kitchen.app.state.slow_down  # type: ignore[attr-defined]
    counted_at_the_hash: list[int] = []
    real = your_data.check_password

    def check(login: Login | None, password: str) -> bool:
        counted_at_the_hash.append(sum(len(times) for times in slow._failures.values()))
        return real(login, password)

    monkeypatch.setattr(your_data, "check_password", check)
    wrong = {"words": "delete everything", "password": "not the password"}
    assert kitchen.post(API, json=wrong).status_code == 403
    assert counted_at_the_hash == [1]
    # A right password takes its try back.
    assert kitchen.post(API, json=RIGHT).status_code == 204
    assert counted_at_the_hash == [1, 2]
    # And the wrong try before it, counted for a person who is now gone, goes with them.
    assert sum(len(times) for times in slow._failures.values()) == 0


def test_a_member_cannot_even_with_the_admins_password(member: TestClient) -> None:
    rows = _rows(member)
    response = member.post(API, json=RIGHT)
    assert response.status_code == 403
    assert response.json()["detail"] == "Only the household’s admin can change this."
    response = member.post(API, json={**RIGHT, "password": "wren's own password"})
    assert response.status_code == 403
    assert _rows(member) == rows


def test_signed_out_cannot(client: TestClient) -> None:
    assert client.post(API, json=RIGHT).status_code == 401


def test_nothing_is_deleted_when_the_safety_backup_fails(kitchen: TestClient) -> None:
    rows = _rows(kitchen)
    (_data(kitchen) / backups.FOLDER).write_text("a file where the folder should be")
    response = kitchen.post(API, json=RIGHT)
    assert response.status_code == 503
    assert response.json()["detail"].endswith("Nothing was deleted.")
    assert _rows(kitchen) == rows
    assert kitchen.get("/api/v1/me").status_code == 200


def test_the_other_household_is_untouched(kitchen: TestClient, neighbour: TestClient) -> None:
    assert neighbour.post("/api/v1/recipes", json={"name": "Next door's"}).status_code == 201
    assert kitchen.post(API, json=RIGHT).status_code == 204
    assert [r["name"] for r in neighbour.get("/api/v1/recipes").json()["recipes"]] == [
        "Next door's"
    ]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalar(select(func.count()).select_from(Login)) == 1


# --- Review r1 --------------------------------------------------------------------------------


def test_two_at_once_the_first_safety_backup_stays_whole(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two Delete everything requests in the same second (a double click, two tabs): the
    second waits for the first, then finds nothing to delete, and the first's safety backup
    is never replaced by a copy of the emptied database."""
    import sqlite3
    import threading
    from datetime import UTC, datetime

    from mealwright.api.v1 import your_data

    assert kitchen.post("/api/v1/recipes", json={"name": "Kept in the backup"}).status_code == 201
    second_client = TestClient(kitchen.app, base_url="https://testserver")
    body = {"username": ADMIN["username"], "password": ADMIN["password"]}
    assert second_client.post("/api/v1/session", json=body).status_code == 200

    real = backups.before_delete_everything
    same_second = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)
    first_in = threading.Event()
    first_done = threading.Event()
    calls: list[str] = []

    def in_the_same_second(
        engine: object, folder: Path, now: object = None, photos: Path | None = None
    ) -> Path:
        if not calls:
            calls.append("first")
            first_in.set()
            second_in.wait(timeout=2)  # without the lock, the second is let in meanwhile
        else:
            calls.append("second")
            second_in.set()
            first_done.wait(timeout=5)  # copy only once the first has deleted
        return real(engine, folder, same_second, photos)  # type: ignore[arg-type]

    second_in = threading.Event()
    monkeypatch.setattr(your_data.backups, "before_delete_everything", in_the_same_second)
    statuses: dict[str, int] = {}

    def first() -> None:
        statuses["first"] = kitchen.post(API, json=RIGHT).status_code
        first_done.set()

    def second() -> None:
        first_in.wait(timeout=5)
        statuses["second"] = second_client.post(API, json=RIGHT).status_code

    threads = [threading.Thread(target=first), threading.Thread(target=second)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=20)
    second_client.close()

    assert statuses == {"first": 204, "second": 204}
    assert calls == ["first"]  # the second found nothing left to delete
    folder = _data(kitchen) / backups.FOLDER
    (safety,) = folder.glob("before-delete-everything-*.db")
    with sqlite3.connect(safety) as copy:
        assert copy.execute("SELECT name FROM recipe").fetchall() == [("Kept in the backup",)]


def test_a_photo_that_cant_be_removed_is_moved_out_of_reach(
    kitchen: TestClient, filled: dict[str, Any], caplog: pytest.LogCaptureFixture
) -> None:
    """The next household is household 1 again: a photo left in photos/1 would be served
    and exported as its own. What can't be removed goes aside, out of photos/ (review r1)."""
    from mealwright import export

    store = _data(kitchen) / "photos"
    photos = store / "1"
    stuck = photos / "stuck"
    stuck.mkdir()
    (stuck / "left.jpg").write_bytes(b"a photo")
    stuck.chmod(0o500)  # its file can't be removed
    try:
        with caplog.at_level("WARNING"):
            assert kitchen.post(API, json=RIGHT).status_code == 204
        assert not photos.exists()
        (aside,) = _data(kitchen).glob("photos-left-over-*")
        assert (aside / "stuck" / "left.jpg").read_bytes() == b"a photo"
        assert "couldn't remove photo files (1); moved them out of photos" in caplog.text
        assert "left.jpg" not in caplog.text
        # Start again: the new household is 1 again, and nothing of the old one is its own.
        assert kitchen.post("/api/v1/setup", json=ADMIN).status_code == 201
        with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            assert db.scalars(select(Household.id)).all() == [1]
        assert export.photo_files(store, 1) == []
        assert not photos.exists() or not any(photos.rglob("*"))
    finally:
        for folder in _data(kitchen).glob("photos-left-over-*/stuck"):
            folder.chmod(0o700)


def test_deleting_one_household_forgets_only_its_own_wrong_password_counts(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    """Whole-0.9 fix A review, finding 3: the other household's counts stay."""
    slow = kitchen.app.state.slow_down  # type: ignore[attr-defined]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        mine = db.scalar(select(Login.id).where(Login.username == ADMIN["username"]))
        theirs = db.scalar(select(Login.id).where(Login.username == "neighbour"))
    ours = [f"user:{ADMIN['username']}", f"dev:{mine}:abc", f"change:{mine}"]
    others = ["user:neighbour", f"dev:{theirs}:abc", f"change:{theirs}", "addr:1.2.3.4"]
    slow.failed(ours + others)
    assert kitchen.post(API, json=RIGHT).status_code == 204
    assert sorted(slow._failures) == sorted(others)


def test_it_also_removes_the_households_uploaded_mealie_files(
    kitchen: TestClient, neighbour: TestClient, tmp_path: Path
) -> None:
    """A file read but not yet brought in is the household's own data: it goes with the rest,
    and next door's file stays (release security pass L1)."""
    from test_mealie_import import mealie_files, upload, zipped

    raw = zipped(tmp_path / "backup.zip")
    mine = upload(kitchen, raw)
    theirs = upload(neighbour, raw)
    assert mine.status_code == 201 and theirs.status_code == 201
    assert len(mealie_files(kitchen)) == 2
    home = _data(kitchen) / "mealie"
    assert (home / "1").is_dir()

    assert kitchen.post(API, json=RIGHT).status_code == 204

    assert not (home / "1").exists()
    assert [path.parent.name for path in mealie_files(kitchen)] == ["2"]


def test_a_symlinked_mealie_folder_is_unlinked_not_followed(
    kitchen: TestClient, tmp_path: Path
) -> None:
    from test_mealie_import import upload, zipped

    assert upload(kitchen, zipped(tmp_path / "b.zip")).status_code == 201
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "precious.txt").write_text("keep")
    home = _data(kitchen) / "mealie" / "1"
    for path in home.iterdir():
        path.unlink()
    home.rmdir()
    home.symlink_to(outside, target_is_directory=True)

    assert kitchen.post(API, json=RIGHT).status_code == 204

    assert not home.is_symlink()
    assert (outside / "precious.txt").read_text() == "keep"


def test_an_upload_the_route_then_refuses_leaves_nothing_in_incoming(
    kitchen: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The file arrived, then the route failed (a refused sign-in, say): the half-named file in
    `mealie/incoming/` goes at once, not a day on (security check of L1)."""
    from test_mealie_import import upload, zipped

    from mealwright import mealie_import
    from mealwright.errors import Problem

    def refuse(*_: object) -> None:
        raise Problem(401, "unauthorized", "Sign in first.")

    monkeypatch.setattr(mealie_import, "create", refuse)
    assert upload(kitchen, zipped(tmp_path / "b.zip")).status_code == 401
    incoming = _data(kitchen) / "mealie" / "incoming"
    assert list(incoming.iterdir()) == []


def test_an_import_running_while_everything_is_deleted_leaves_no_photo_and_no_traceback(
    kitchen: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The job has the household's number and is about to save a photo when Delete everything
    happens. It goes on, finds the household gone and stops: no row, and the photo file it then
    writes is removed, so the next household with the same number never gets it."""
    from test_mealie_import import upload, zipped

    from mealwright import photos
    from mealwright.models import MealieImport, Recipe

    made = upload(kitchen, zipped(tmp_path / "b.zip")).json()["id"]
    in_write, go_on = threading.Event(), threading.Event()
    real = photos.write

    def slow_write(*args: Any, **kwargs: Any) -> int:
        in_write.set()  # the job is writing a photo: Delete everything happens now
        assert go_on.wait(timeout=30)
        return real(*args, **kwargs)

    monkeypatch.setattr(photos, "write", slow_write)
    with caplog.at_level(logging.DEBUG):
        started = kitchen.post(f"/api/v1/mealie-imports/{made}/start", json={})
        assert started.status_code == 202
        assert in_write.wait(timeout=30)
        assert kitchen.post(API, json=RIGHT).status_code == 204
        go_on.set()
        kitchen.app.state.mealie.wait()  # type: ignore[attr-defined]
    folder = _data(kitchen) / "photos" / "1"
    assert not folder.exists() or [p for p in folder.rglob("*") if p.is_file()] == []
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalar(select(func.count()).select_from(MealieImport)) == 0
        assert db.scalar(select(func.count()).select_from(Recipe)) == 0
    assert "Traceback" not in caplog.text
