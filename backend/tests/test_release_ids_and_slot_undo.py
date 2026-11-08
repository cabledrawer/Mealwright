"""0.8.0-alpha.2 security findings: a removed place or shop id is never handed out again, an
Undo never puts back another household's place or shop (M1), and only an admin can undo a
meal-slot change (L1)."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_settings_lists import member  # noqa: F401  (fixture)

from mealwright.models import Food, Place, Shop

API = "/api/v1"


def ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def test_undo_never_shows_another_households_shop(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    shop = ok(kitchen.post(f"{API}/shops", json={"name": "A shop"}), 201)
    milk = ok(kitchen.post(f"{API}/foods", json={"name": "Milk", "shop_id": shop["id"]}), 201)
    food_id = milk["food"]["id"]
    cleared = ok(kitchen.patch(f"{API}/foods/{food_id}", json={"shop_id": None}))
    ok(kitchen.delete(f"{API}/shops/{shop['id']}"))
    theirs = ok(neighbour.post(f"{API}/shops", json={"name": "Neighbour's secret shop"}), 201)
    assert theirs["id"] != shop["id"]  # the removed id is not handed out again
    kitchen.post(f"{API}/changes/{cleared['change']['id']}/undo")
    assert ok(kitchen.get(f"{API}/foods/{food_id}"))["shop"] is None


def test_undo_never_shows_another_households_place(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    garage = ok(kitchen.post(f"{API}/places", json={"name": "Garage", "kind": "cupboard"}), 201)
    rice = ok(kitchen.post(f"{API}/foods", json={"name": "Rice", "place_id": garage["id"]}), 201)
    food_id = rice["food"]["id"]
    fridge = next(p["id"] for p in ok(kitchen.get(f"{API}/places")) if p["name"] == "Fridge")
    moved = ok(kitchen.patch(f"{API}/foods/{food_id}", json={"place_id": fridge}))
    ok(kitchen.delete(f"{API}/places/{garage['id']}"))
    shed = ok(
        neighbour.post(f"{API}/places", json={"name": "Neighbour's shed", "kind": "cupboard"}), 201
    )
    assert shed["id"] != garage["id"]
    kitchen.post(f"{API}/changes/{moved['change']['id']}/undo")
    assert ok(kitchen.get(f"{API}/foods/{food_id}"))["place"] is None


def test_reads_ignore_a_place_or_shop_of_another_household(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    """Even a row that already points at another household's place or shop (from before the
    ids were never reused) shows as none, and stock goes to this household's Cupboard."""
    from mealwright.stock import default_place

    theirs_shop = ok(neighbour.post(f"{API}/shops", json={"name": "Secret"}), 201)
    theirs_place = ok(
        neighbour.post(f"{API}/places", json={"name": "Shed", "kind": "cupboard"}), 201
    )
    food = ok(kitchen.post(f"{API}/foods", json={"name": "Dal"}), 201)["food"]
    with kitchen.app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        row = session.get(Food, food["id"])
        row.shop_id, row.place_id = theirs_shop["id"], theirs_place["id"]
        session.commit()
    seen = ok(kitchen.get(f"{API}/foods/{food['id']}"))
    assert seen["shop"] is None and seen["place"] is None
    with kitchen.app.state.sessionmaker() as session:  # type: ignore[attr-defined]
        from mealwright.api.v1.context import Kitchen
        from mealwright.models import Household, Login

        k = Kitchen(
            db=session,
            login=session.scalars(select(Login).where(Login.household_id == 1)).first(),
            household=session.get(Household, 1),
            idempotency_key=None,
            request="",
        )
        place = default_place(k, session.get(Food, food["id"]))
        assert place.household_id == 1 and place.kind == "cupboard"
        assert session.get(Shop, theirs_shop["id"]).household_id == 2
        assert session.get(Place, theirs_place["id"]).household_id == 2


def test_a_member_cannot_undo_an_admins_meal_slot_change(
    kitchen: TestClient,
    member: TestClient,  # noqa: F811
) -> None:
    lunch = next(s for s in ok(kitchen.get(f"{API}/meal-slots")) if s["name"] == "Lunch")
    hid = ok(kitchen.patch(f"{API}/meal-slots/{lunch['id']}", json={"enabled": False}))
    change_id = hid["change"]["id"]
    assert (
        member.patch(f"{API}/meal-slots/{lunch['id']}", json={"enabled": True}).status_code == 403
    )
    assert member.post(f"{API}/changes/{change_id}/undo").status_code == 403
    now = next(s for s in ok(kitchen.get(f"{API}/meal-slots")) if s["id"] == lunch["id"])
    assert now["enabled"] is False
    # Recent changes does not offer the member an Undo on it; the admin still has it.
    for client, offered in ((member, False), (kitchen, True)):
        rows = ok(client.get(f"{API}/changes"))["changes"]
        row = next(c for c in rows if c["id"] == change_id)
        assert row["can_undo"] is offered
    ok(kitchen.post(f"{API}/changes/{change_id}/undo"))
