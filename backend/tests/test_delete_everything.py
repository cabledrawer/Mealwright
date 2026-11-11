"""Delete everything / start again (0.9, D1; the mockup's proposal, for cabledrawer).

Admins only, with the typed words and the admin's own password. A safety backup first, and
nothing deleted if it can't be made. Every row and photo of the household goes; the backups
stay; everyone is signed out; Mealwright then asks for first-run setup. The other household
(tests only) is untouched.
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
import test_households
from conftest import ADMIN
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from test_households import snapshot

from mealwright import backups
from mealwright.auth import hash_password
from mealwright.models import Change, ListItem, ListTick, Login

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
    (safety,) = after - before
    assert safety.startswith("before-delete-everything-")
    assert (folder / safety).stat().st_size > 0
    # Everyone is signed out, the admin's cookie with them.
    assert "mealwright_session" not in kitchen.cookies
    assert kitchen.get("/api/v1/me").status_code == 401
    assert member.get("/api/v1/me").status_code == 401
    # Mealwright starts again at first-run setup, and setup works.
    assert kitchen.get("/api/v1/setup").json()["needs_setup"] is True
    assert kitchen.post("/api/v1/setup", json=ADMIN).status_code == 201
    assert kitchen.get("/api/v1/recipes").status_code == 200


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
