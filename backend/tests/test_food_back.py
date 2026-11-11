"""A removed ingredient that comes back by another way than undoing its removal (an Undo
in Pantry that puts stock back into it, or an offline phone adding it): Ingredients'
Recent changes gets a line "Lemon is back in Ingredients", with no Undo of its own, and
the old "Removed Lemon from Ingredients" loses its Undo. Only the newest removal of an
ingredient can have Undo, and only while the ingredient is still removed (worked out when
the list is read; nothing extra is stored)."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sync_kit import PHONE_A, PHONE_R, new_id, one, s0, tick

from mealwright.auth import hash_password
from mealwright.household import add_default_places
from mealwright.models import Household, Login

API = "/api/v1"
NEIGHBOUR = {"username": "neighbour", "password": "next door’s own password"}


def ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def food(client: TestClient, name: str) -> dict[str, Any]:
    """An ingredient counted by weight, so the tests' 100 g stays 100 g."""
    body = {"name": name, "counted_as": "weight"}
    found: dict[str, Any] = ok(client.post(f"{API}/foods", json=body), 201)["food"]
    return found


def stocked_then_used(client: TestClient, food_id: int) -> dict[str, Any]:
    """100 g put in the pantry and used up: the change whose Undo puts it back."""
    body = {"food_id": food_id, "amount": {"amount": 100, "unit": "g"}}
    lot = ok(client.post(f"{API}/stock", json=body), 201)["groups"][0]["lots"][0]
    used: dict[str, Any] = ok(client.post(f"{API}/stock/{lot['id']}/used"))["change"]
    return used


def remove(client: TestClient, food_id: int) -> dict[str, Any]:
    change: dict[str, Any] = ok(client.delete(f"{API}/foods/{food_id}"))["change"]
    return change


def ingredients_lines(client: TestClient) -> list[tuple[str, str, bool]]:
    """Ingredients → Recent changes, newest first: (kind, summary, has Undo)."""
    rows = ok(client.get(f"{API}/changes", params={"area": "ingredients"}))["changes"]
    return [(row["kind"], row["summary"], row["can_undo"]) for row in rows]


@pytest.fixture
def neighbour(kitchen: TestClient) -> Iterator[TestClient]:
    """Household 2, with its own admin, signed in on its own client."""
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(Household(id=2, name="Next door"))
        db.flush()
        add_default_places(db, 2)
        db.add(
            Login(
                household_id=2,
                username=NEIGHBOUR["username"],
                name="Neighbour",
                password_hash=hash_password(NEIGHBOUR["password"]),
                role="admin",
            )
        )
        db.commit()
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        ok(other.post(f"{API}/session", json=NEIGHBOUR))
        yield other


# --- By an Undo in Pantry -----------------------------------------------------------------------


def test_a_pantry_undo_that_brings_it_back_adds_a_line_and_takes_the_removal_s_undo(
    kitchen: TestClient,
) -> None:
    lemon = food(kitchen, "Lemon")
    used = stocked_then_used(kitchen, lemon["id"])
    removed = remove(kitchen, lemon["id"])
    assert ingredients_lines(kitchen)[0] == ("food_removed", removed["summary"], True)

    undo = ok(kitchen.post(f"{API}/changes/{used['id']}/undo"))
    assert undo["brought_back"] == [{"id": lemon["id"], "name": "Lemon"}]
    assert ingredients_lines(kitchen)[:2] == [
        ("food_back", "Lemon is back in Ingredients", False),
        ("food_removed", "Removed Lemon from Ingredients", False),
    ]
    # Neither can be undone by asking the server directly either.
    rows = ok(kitchen.get(f"{API}/changes", params={"area": "ingredients"}))["changes"]
    back = rows[0]
    assert back["who"]["name"] == "Tess"
    for change_id in (back["id"], removed["id"]):
        response = kitchen.post(f"{API}/changes/{change_id}/undo")
        assert response.status_code == 409, response.text
        assert response.json()["code"] == "cannot_undo"
    # Lemon is still back, with its stock.
    assert ok(kitchen.get(f"{API}/foods/{lemon['id']}"))["stock"]["amount"] == 100.0


def test_the_line_never_takes_the_undo_s_request_key(kitchen: TestClient) -> None:
    lemon = food(kitchen, "Lemon")
    used = stocked_then_used(kitchen, lemon["id"])
    remove(kitchen, lemon["id"])
    key = {"Idempotency-Key": "undo-used-lemon-1"}
    first = kitchen.post(f"{API}/changes/{used['id']}/undo", headers=key)
    again = kitchen.post(f"{API}/changes/{used['id']}/undo", headers=key)
    assert first.status_code == again.status_code == 200
    assert again.headers.get("Idempotent-Replayed") == "true"
    assert again.json()["change"]["id"] == first.json()["change"]["id"]
    assert again.json()["brought_back"] == [{"id": lemon["id"], "name": "Lemon"}]
    # Only one line, however many times the request is sent.
    kinds = [kind for kind, *_ in ingredients_lines(kitchen)]
    assert kinds.count("food_back") == 1


def test_ctrl_z_skips_the_line(kitchen: TestClient) -> None:
    """Ctrl+Z undoes your newest change that has an Undo: never the "back" line."""
    lemon = food(kitchen, "Lemon")
    used = stocked_then_used(kitchen, lemon["id"])
    remove(kitchen, lemon["id"])
    ok(kitchen.post(f"{API}/changes/{used['id']}/undo"))
    newest = ok(kitchen.get(f"{API}/changes", params={"mine": "true", "limit": 1}))["changes"]
    assert [row["kind"] for row in newest] != ["food_back"]


def test_removed_back_and_removed_again_only_the_newest_removal_has_undo(
    kitchen: TestClient,
) -> None:
    lemon = food(kitchen, "Lemon")
    used = stocked_then_used(kitchen, lemon["id"])
    first = remove(kitchen, lemon["id"])
    ok(kitchen.post(f"{API}/changes/{used['id']}/undo"))  # Lemon is back, with 100 g
    lot = ok(kitchen.get(f"{API}/foods/{lemon['id']}"))["stock"]
    assert lot["amount"] == 100.0
    pantry = ok(kitchen.get(f"{API}/pantry"))
    lots = [
        lot
        for place in pantry["places"]
        for group in place["groups"]
        if group["food"]["id"] == lemon["id"]
        for lot in group["lots"]
    ]
    ok(kitchen.post(f"{API}/stock/{lots[0]['id']}/used"))
    second = remove(kitchen, lemon["id"])
    lines = [line for line in ingredients_lines(kitchen) if "Lemon" in line[1]]
    assert lines[:3] == [
        ("food_removed", "Removed Lemon from Ingredients", True),
        ("food_back", "Lemon is back in Ingredients", False),
        ("food_removed", "Removed Lemon from Ingredients", False),
    ]
    response = kitchen.post(f"{API}/changes/{first['id']}/undo")
    assert response.status_code == 409 and response.json()["code"] == "cannot_undo"
    # The newest removal's Undo works, and then no removal line has one.
    ok(kitchen.post(f"{API}/changes/{second['id']}/undo"))
    removals = [line for line in ingredients_lines(kitchen) if line[0] == "food_removed"]
    assert [has_undo for *_, has_undo in removals] == [False, False]


def test_a_removal_undone_the_usual_way_adds_no_line(kitchen: TestClient) -> None:
    lemon = food(kitchen, "Lemon")
    removed = remove(kitchen, lemon["id"])
    ok(kitchen.post(f"{API}/changes/{removed['id']}/undo"))
    assert "food_back" not in [kind for kind, *_ in ingredients_lines(kitchen)]


# --- By an offline phone adding it (sync protocol 5.9) -------------------------------------------


def test_an_offline_add_that_brings_it_back_adds_a_line_and_takes_the_removal_s_undo(
    kitchen: TestClient,
) -> None:
    s = s0(kitchen)
    eggs = s.foods["Eggs"]
    ok(kitchen.delete(f"{API}/foods/{eggs}"))
    added = one(
        s.wren, "add", s.c0, PHONE_R, list_id=s.main, item_id=new_id(), food_id=eggs, amount=6
    )
    assert added["status"] == "applied"
    assert added["message"] == "Eggs is back in Ingredients."
    rows = ok(kitchen.get(f"{API}/changes", params={"area": "ingredients"}))["changes"]
    eggs_rows = [row for row in rows if "Eggs" in row["summary"]]
    assert [(r["kind"], r["summary"], r["can_undo"]) for r in eggs_rows[:2]] == [
        ("food_back", "Eggs is back in Ingredients", False),
        ("food_removed", "Removed Eggs from Ingredients", False),
    ]
    assert eggs_rows[0]["who"]["name"] == "Wren"  # whoever's phone brought it back
    # Undoing the add removes Eggs again (0.3's rule), so the removal stands again: it is
    # the newest removal and Eggs is removed, so it has its Undo back.
    one(s.wren, "undo", 0, PHONE_R, undoes=added["id"])
    removal = next(
        row
        for row in ok(kitchen.get(f"{API}/changes", params={"area": "ingredients"}))["changes"]
        if row["kind"] == "food_removed" and "Eggs" in row["summary"]
    )
    assert removal["can_undo"] is True
    assert_back_undone(kitchen, "Eggs")


def assert_back_undone(client: TestClient, name: str) -> None:
    """cabledrawer 21 Oct: once the change that brought it back is undone, "… is back in
    Ingredients" is undone too, the same way any other undone line looks: it says who undid
    it, and the Undo's own "Undid: …" line is in Ingredients' list above it."""
    rows = ok(client.get(f"{API}/changes", params={"area": "ingredients"}))["changes"]
    back = next(row for row in rows if row["kind"] == "food_back" and name in row["summary"])
    assert back["undone"] is not None
    undid = rows[: rows.index(back)]
    assert [row["kind"] for row in undid] == ["undo"]
    assert undid[0]["summary"].startswith("Undid: ")


# --- By a tick, or a new ingredient with its name -----------------------------------------------


def back_lines(client: TestClient, name: str) -> list[dict[str, Any]]:
    rows = ok(client.get(f"{API}/changes", params={"area": "ingredients"}))["changes"]
    return [row for row in rows if row["kind"] == "food_back" and name in row["summary"]]


def test_a_tick_that_brings_it_back_adds_one_line_and_its_undo_undoes_the_line(
    kitchen: TestClient,
) -> None:
    s = s0(kitchen)
    one(s.wren, "delete", s.c0, PHONE_R, item_id=s.items["Paneer"])
    ok(s.wren.delete(f"{API}/foods/{s.foods['Paneer']}"))
    done = tick(kitchen, s, "Paneer")
    assert done["message"] == "Paneer is back in Ingredients."
    [back] = back_lines(kitchen, "Paneer")
    assert back["undone"] is None and back["can_undo"] is False
    # Its Undo takes the stock out and removes Paneer again (7.1).
    assert one(kitchen, "undo", 0, PHONE_A, undoes=done["id"])["status"] == "applied"
    assert_back_undone(kitchen, "Paneer")


def test_a_new_ingredient_with_a_removed_one_s_name_adds_one_line(kitchen: TestClient) -> None:
    s = s0(kitchen)
    ok(kitchen.delete(f"{API}/foods/{s.foods['Eggs']}"))
    added = one(
        s.wren,
        "add",
        s.c0,
        PHONE_R,
        list_id=s.main,
        item_id=new_id(),
        new_food={"name": "eggs", "counted_as": "count"},
    )
    assert added["status"] == "applied"
    assert added["message"] == "Eggs is back in Ingredients."
    [back] = back_lines(kitchen, "Eggs")
    assert back["undone"] is None


def test_an_undo_that_leaves_it_in_ingredients_leaves_the_line(kitchen: TestClient) -> None:
    """Still on a list, so the Undo of the tick keeps Paneer (0.2's rule): it is still back."""
    s = s0(kitchen)
    one(s.wren, "delete", s.c0, PHONE_R, item_id=s.items["Paneer"])
    ok(s.wren.delete(f"{API}/foods/{s.foods['Paneer']}"))
    done = tick(kitchen, s, "Paneer")
    one(s.wren, "add", s.c0, PHONE_R, list_id=s.main, item_id=new_id(), food_id=s.foods["Paneer"])
    one(kitchen, "undo", 0, PHONE_A, undoes=done["id"])
    [back] = back_lines(kitchen, "Paneer")
    assert back["undone"] is None


# --- Another household ---------------------------------------------------------------------------


def test_another_household_is_untouched(kitchen: TestClient, neighbour: TestClient) -> None:
    theirs = food(neighbour, "Lemon")
    their_removal = remove(neighbour, theirs["id"])
    before = ok(neighbour.get(f"{API}/changes", params={"area": "ingredients"}))

    lemon = food(kitchen, "Lemon")
    used = stocked_then_used(kitchen, lemon["id"])
    remove(kitchen, lemon["id"])
    ok(kitchen.post(f"{API}/changes/{used['id']}/undo"))
    assert ingredients_lines(kitchen)[0][0] == "food_back"

    after = ok(neighbour.get(f"{API}/changes", params={"area": "ingredients"}))
    assert after == before
    assert after["changes"][0]["id"] == their_removal["id"]
    assert after["changes"][0]["can_undo"] is True
    # And the neighbour can't undo, or even see, ours.
    ours = ok(kitchen.get(f"{API}/changes", params={"area": "ingredients"}))["changes"]
    for row in ours:
        assert neighbour.post(f"{API}/changes/{row['id']}/undo").status_code == 404
