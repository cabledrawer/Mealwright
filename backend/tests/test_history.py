"""Recent changes and Undo: just that change, partly when it must, within the window."""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from mealwright.auth import hash_password
from mealwright.models import Change, Login, utcnow

API = "/api/v1"


def add(kitchen: TestClient, name: str, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = kitchen.post(f"{API}/foods", json={"name": name, **extra}).json()
    return body


def undo(client: TestClient, change_id: int, **headers: str) -> Any:
    return client.post(f"{API}/changes/{change_id}/undo", headers=headers)


@pytest.fixture
def wren(kitchen: TestClient) -> Iterator[TestClient]:
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
        other.post(f"{API}/session", json={"username": "wren", "password": "wren's own password"})
        yield other


def test_undo_reverses_just_that_change(kitchen: TestClient) -> None:
    food = add(kitchen, "Toor dal")["food"]
    staple = kitchen.patch(f"{API}/foods/{food['id']}", json={"staple": True}).json()["change"]
    kitchen.patch(f"{API}/foods/{food['id']}", json={"name": "Tuvar dal"})

    response = undo(kitchen, staple["id"])
    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "done"
    assert body["message"] == "Undone."
    assert body["change"]["kind"] == "undo"
    assert body["change"]["summary"] == "Undid: Toor dal is now a staple"
    assert body["change"]["can_undo"] is False
    assert body["undone"]["undone"]["who"]["name"] == "Tess"
    # The later rename stays.
    assert body["food"]["name"] == "Tuvar dal"
    assert body["food"]["staple"] is False


def test_partly_undone_when_changed_since(kitchen: TestClient) -> None:
    food = add(kitchen, "Toor dal")["food"]
    url = f"{API}/foods/{food['id']}"
    first = kitchen.patch(url, json={"name": "Tuvar dal"}).json()["change"]
    kitchen.patch(url, json={"name": "Arhar dal"})
    body = undo(kitchen, first["id"]).json()
    assert body["result"] == "nothing"
    assert body["food"]["name"] == "Arhar dal"

    sized = kitchen.post(f"{url}/sizes", json={"name": "packet", "amount": 500}).json()
    size_id = sized["food"]["sizes"][0]["id"]
    kitchen.patch(f"{url}/sizes/{size_id}", json={"amount": 400})
    two = kitchen.post(f"{url}/other-names", json={"name": "toor"}).json()["change"]
    assert undo(kitchen, two["id"]).json()["result"] == "done"
    # The size was added and then changed: undoing the add leaves it alone.
    body = undo(kitchen, sized["change"]["id"]).json()
    assert body["result"] == "nothing"
    assert body["food"]["sizes"][0]["amount"] == 400.0


def test_undo_twice(kitchen: TestClient) -> None:
    change = add(kitchen, "Toor dal")["change"]
    assert undo(kitchen, change["id"]).status_code == 200
    again = undo(kitchen, change["id"])
    assert again.status_code == 409
    assert again.json()["code"] == "already_undone"


def test_an_undo_cannot_be_undone(kitchen: TestClient) -> None:
    change = add(kitchen, "Toor dal")["change"]
    undo_change = undo(kitchen, change["id"]).json()["change"]
    response = undo(kitchen, undo_change["id"])
    assert response.status_code == 409
    assert response.json()["code"] == "cannot_undo"


def test_too_old_to_undo(kitchen: TestClient) -> None:
    change = add(kitchen, "Toor dal")["change"]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(
            update(Change).where(Change.id == change["id"]).values(at=utcnow() - timedelta(days=8))
        )
        db.commit()
    response = undo(kitchen, change["id"])
    assert response.status_code == 410
    assert response.json()["code"] == "too_old"
    listed = kitchen.get(f"{API}/changes").json()["changes"]
    assert listed[0]["can_undo"] is False


def test_anyone_can_undo_anyones_change(kitchen: TestClient, wren: TestClient) -> None:
    change = add(kitchen, "Toor dal")["change"]
    body = undo(wren, change["id"]).json()
    assert body["result"] == "done"
    assert body["change"]["who"]["name"] == "Wren"


def test_undo_retry(kitchen: TestClient) -> None:
    change = add(kitchen, "Toor dal")["change"]
    first = undo(kitchen, change["id"], **{"Idempotency-Key": "undo-1"})
    again = undo(kitchen, change["id"], **{"Idempotency-Key": "undo-1"})
    assert again.status_code == 200
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["change"]["id"] == first.json()["change"]["id"]


def test_recent_changes(kitchen: TestClient, wren: TestClient) -> None:
    toor = add(kitchen, "Toor dal")["food"]
    add(wren, "Onion")
    kitchen.patch(f"{API}/foods/{toor['id']}", json={"staple": True})

    listed = kitchen.get(f"{API}/changes").json()
    assert [c["summary"] for c in listed["changes"]] == [
        "Toor dal is now a staple",
        "Added Onion",
        "Added Toor dal",
    ]
    assert listed["changes"][1]["who"]["name"] == "Wren"

    mine = kitchen.get(f"{API}/changes", params={"mine": True, "limit": 1}).json()
    assert [c["summary"] for c in mine["changes"]] == ["Toor dal is now a staple"]
    assert mine["next"] is not None
    older = kitchen.get(
        f"{API}/changes", params={"mine": True, "limit": 1, "before": mine["next"]}
    ).json()
    assert [c["summary"] for c in older["changes"]] == ["Added Toor dal"]

    by_food = kitchen.get(f"{API}/changes", params={"food_id": toor["id"]}).json()
    assert len(by_food["changes"]) == 2
    assert kitchen.get(f"{API}/changes", params={"area": "pantry"}).json()["changes"] == []


def test_another_households_change_is_404(kitchen: TestClient) -> None:
    assert undo(kitchen, 12345).status_code == 404


def test_undo_remove_when_the_name_is_taken_again(kitchen: TestClient) -> None:
    food = add(kitchen, "Toor dal")["food"]
    removed = kitchen.delete(f"{API}/foods/{food['id']}").json()["change"]
    add(kitchen, "Toor dal")
    body = undo(kitchen, removed["id"]).json()
    assert body["result"] == "nothing"
    assert kitchen.get(f"{API}/foods/{food['id']}").status_code == 404


def test_undo_merge_after_more_changes_is_partly(kitchen: TestClient) -> None:
    moringa = add(kitchen, "Moringa")["food"]
    kitchen.post(f"{API}/foods/{moringa['id']}/sizes", json={"name": "bundle", "amount": 300})
    drumsticks = add(kitchen, "Drumsticks")["food"]
    merged = kitchen.post(
        f"{API}/foods/{moringa['id']}/merge", json={"into_id": drumsticks["id"]}
    ).json()
    size_id = merged["food"]["sizes"][0]["id"]
    kitchen.patch(f"{API}/foods/{drumsticks['id']}/sizes/{size_id}", json={"amount": 250})
    body = undo(kitchen, merged["change"]["id"]).json()
    assert body["result"] == "partly"
    assert body["message"] == "Put back what could be: some of it has changed again since."
    back = kitchen.get(f"{API}/foods/{moringa['id']}").json()
    assert back["id"] == moringa["id"]  # the food itself came back
    assert back["sizes"] == []  # the size was changed since, so it stays where it is
