"""Settings → Meal slots, Shops & places: renaming, ordering, adding, removing, and Undo."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_shopping import add as add_line
from test_shopping import main_id

from mealwright.auth import hash_password
from mealwright.models import ChangeLine, Food, ListItem, Place, Shop, StockLot

API = "/api/v1"


def ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def db(kitchen: TestClient) -> Any:
    return kitchen.app.state.sessionmaker()  # type: ignore[attr-defined]


@pytest.fixture
def member(kitchen: TestClient) -> Iterator[TestClient]:
    from mealwright.models import Login

    with db(kitchen) as session:
        session.add(
            Login(
                household_id=1,
                username="wren",
                name="Wren",
                password_hash=hash_password("wren's own password"),
                role="member",
            )
        )
        session.commit()
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        body = {"username": "wren", "password": "wren's own password"}
        assert other.post(f"{API}/session", json=body).status_code == 200
        yield other


def slots(kitchen: TestClient) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = ok(kitchen.get(f"{API}/meal-slots"))
    return found


def names(rows: list[dict[str, Any]]) -> list[str]:
    return [r["name"] for r in rows]


def food(kitchen: TestClient, name: str, **extra: Any) -> dict[str, Any]:
    found: dict[str, Any] = ok(kitchen.post(f"{API}/foods", json={"name": name, **extra}), 201)[
        "food"
    ]
    return found


def place_id(kitchen: TestClient, name: str) -> int:
    return next(p["id"] for p in ok(kitchen.get(f"{API}/places")) if p["name"] == name)


def stock(kitchen: TestClient, food_id: int, place: int, grams: float = 100) -> None:
    ok(
        kitchen.post(
            f"{API}/stock",
            json={"food_id": food_id, "amount": {"amount": grams, "unit": "g"}, "place_id": place},
        ),
        201,
    )


# --- Meal slots -------------------------------------------------------------------------------


def test_an_admin_renames_a_meal_and_undo_puts_the_name_back(kitchen: TestClient) -> None:
    lunch = next(s for s in slots(kitchen) if s["name"] == "Lunch")
    done = ok(kitchen.patch(f"{API}/meal-slots/{lunch['id']}", json={"name": "  Midday  meal "}))
    assert "Midday meal" in names(slots(kitchen))
    assert done["change"]["summary"] == "Renamed Lunch to Midday meal"
    ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))
    assert "Lunch" in names(slots(kitchen))


def test_renaming_to_the_same_name_changes_nothing(kitchen: TestClient) -> None:
    lunch = next(s for s in slots(kitchen) if s["name"] == "Lunch")
    done = ok(kitchen.patch(f"{API}/meal-slots/{lunch['id']}", json={"name": "lunch"}))
    assert done["change"] is not None  # a new case is a rename
    again = ok(kitchen.patch(f"{API}/meal-slots/{lunch['id']}", json={"name": "lunch"}))
    assert again["change"] is None


def test_a_meal_name_the_household_has_is_refused(kitchen: TestClient) -> None:
    lunch = next(s for s in slots(kitchen) if s["name"] == "Lunch")
    refused = kitchen.patch(f"{API}/meal-slots/{lunch['id']}", json={"name": "dinner"})
    assert refused.status_code == 409 and refused.json()["code"] == "slot_exists"
    added = kitchen.post(f"{API}/meal-slots", json={"name": "DINNER"})
    assert added.status_code == 409 and added.json()["code"] == "slot_exists"


def test_a_patch_with_nothing_in_it_is_refused(kitchen: TestClient) -> None:
    response = kitchen.patch(f"{API}/meal-slots/{slots(kitchen)[0]['id']}", json={})
    assert response.status_code == 422 and response.json()["code"] == "nothing_to_change"


def test_switch_and_rename_in_one_call(kitchen: TestClient) -> None:
    snack = next(s for s in slots(kitchen) if s["name"] == "Snack")
    assert snack["enabled"] is False
    ok(
        kitchen.patch(
            f"{API}/meal-slots/{snack['id']}", json={"name": "Elevenses", "enabled": True}
        )
    )
    now = next(s for s in slots(kitchen) if s["id"] == snack["id"])
    assert now["name"] == "Elevenses" and now["enabled"] is True


def test_adding_a_meal_puts_it_last_and_on(kitchen: TestClient) -> None:
    added = ok(kitchen.post(f"{API}/meal-slots", json={"name": " Supper "}), 201)
    assert added["name"] == "Supper" and added["enabled"] is True
    assert names(slots(kitchen))[-1] == "Supper"
    assert added["position"] > slots(kitchen)[-2]["position"]


def test_a_household_has_at_most_twelve_meals(kitchen: TestClient) -> None:
    for number in range(8):
        ok(kitchen.post(f"{API}/meal-slots", json={"name": f"Extra {number}"}), 201)
    refused = kitchen.post(f"{API}/meal-slots", json={"name": "One too many"})
    assert refused.status_code == 422 and refused.json()["code"] == "too_many_slots"


def test_reordering_the_meals_and_undo(kitchen: TestClient) -> None:
    before = slots(kitchen)
    ids = [s["id"] for s in before]
    wanted = [ids[3], ids[0], ids[1], ids[2]]
    done = ok(kitchen.put(f"{API}/meal-slots/order", json={"ids": wanted}))
    assert [s["id"] for s in slots(kitchen)] == wanted
    assert done["change"]["summary"] == "Changed the order of the meals"
    ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))
    assert [s["id"] for s in slots(kitchen)] == ids


def test_an_order_must_name_every_meal_once(kitchen: TestClient) -> None:
    ids = [s["id"] for s in slots(kitchen)]
    for bad in (ids[:-1], [*ids, ids[0]], [*ids[:-1], 9999]):
        response = kitchen.put(f"{API}/meal-slots/order", json={"ids": bad})
        assert response.status_code == 422 and response.json()["code"] == "not_all_slots"


def test_the_same_order_changes_nothing(kitchen: TestClient) -> None:
    ids = [s["id"] for s in slots(kitchen)]
    assert ok(kitchen.put(f"{API}/meal-slots/order", json={"ids": ids}))["change"] is None


def test_only_admins_change_meals(member: TestClient, kitchen: TestClient) -> None:
    slot = slots(kitchen)[0]
    ids = [s["id"] for s in slots(kitchen)]
    for response in (
        member.patch(f"{API}/meal-slots/{slot['id']}", json={"name": "Nope"}),
        member.patch(f"{API}/meal-slots/{slot['id']}", json={"enabled": False}),
        member.post(f"{API}/meal-slots", json={"name": "Nope"}),
        member.put(f"{API}/meal-slots/order", json={"ids": ids}),
    ):
        assert response.status_code == 403 and response.json()["code"] == "admins_only"
    assert member.get(f"{API}/meal-slots").status_code == 200  # everyone can read them


def test_another_households_meals_are_not_found(kitchen: TestClient, neighbour: TestClient) -> None:
    theirs = slots(neighbour)[0]["id"]
    assert kitchen.patch(f"{API}/meal-slots/{theirs}", json={"name": "Mine"}).status_code == 404
    mine = [s["id"] for s in slots(kitchen)]
    assert (
        kitchen.put(f"{API}/meal-slots/order", json={"ids": [*mine[:-1], theirs]}).status_code
        == 422
    )
    assert "Mine" not in names(slots(neighbour))


# --- Shops ------------------------------------------------------------------------------------


def shops(kitchen: TestClient) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = ok(kitchen.get(f"{API}/shops"))
    return found


def test_a_member_renames_and_orders_shops(member: TestClient, kitchen: TestClient) -> None:
    a = ok(kitchen.post(f"{API}/shops", json={"name": "Aldi"}), 201)
    b = ok(kitchen.post(f"{API}/shops", json={"name": "Butcher"}), 201)
    assert ok(member.patch(f"{API}/shops/{a['id']}", json={"name": " Lidl "})) == {
        "id": a["id"],
        "name": "Lidl",
    }
    order = ok(member.put(f"{API}/shops/order", json={"ids": [b["id"], a["id"]]}))
    assert names(order) == ["Butcher", "Lidl"] and names(shops(kitchen)) == ["Butcher", "Lidl"]


def test_a_shop_name_another_shop_has_is_a_409(kitchen: TestClient) -> None:
    a = ok(kitchen.post(f"{API}/shops", json={"name": "Aldi"}), 201)
    b = ok(kitchen.post(f"{API}/shops", json={"name": "Butcher"}), 201)
    refused = kitchen.patch(f"{API}/shops/{b['id']}", json={"name": "aldi"})
    assert refused.status_code == 409 and refused.json()["code"] == "shop_exists"
    assert refused.json()["shop"] == {"id": a["id"], "name": "Aldi"}
    # Its own name, in other letters, is a rename.
    ok(kitchen.patch(f"{API}/shops/{b['id']}", json={"name": "BUTCHER"}))
    assert kitchen.patch(f"{API}/shops/{b['id']}", json={"name": "  "}).status_code == 422


def test_a_shop_order_must_name_every_shop_once(kitchen: TestClient) -> None:
    a = ok(kitchen.post(f"{API}/shops", json={"name": "Aldi"}), 201)
    ok(kitchen.post(f"{API}/shops", json={"name": "Butcher"}), 201)
    response = kitchen.put(f"{API}/shops/order", json={"ids": [a["id"]]})
    assert response.status_code == 422 and response.json()["code"] == "not_all_shops"


def test_removing_a_shop_sends_its_ingredients_to_any_shop_and_undo_brings_it_back(
    kitchen: TestClient,
) -> None:
    aldi = ok(kitchen.post(f"{API}/shops", json={"name": "Aldi"}), 201)
    other = ok(kitchen.post(f"{API}/shops", json={"name": "Butcher"}), 201)
    milk = food(kitchen, "Milk", shop_id=aldi["id"])
    mince = food(kitchen, "Mince", shop_id=other["id"])
    main = main_id(kitchen)
    line = add_line(kitchen, main, milk["id"], amount={"amount": 1, "unit": "l"})["item"]
    assert line["shop"]["name"] == "Aldi"
    removed = ok(kitchen.delete(f"{API}/shops/{aldi['id']}"))
    assert removed["change"]["summary"] == "Removed the shop Aldi"
    assert names(shops(kitchen)) == ["Butcher"]
    assert ok(kitchen.get(f"{API}/foods/{milk['id']}"))["shop"] is None
    assert ok(kitchen.get(f"{API}/foods/{mince['id']}"))["shop"]["name"] == "Butcher"
    view = ok(kitchen.get(f"{API}/shopping/lists/{main}"))
    assert [s["shop"] for s in view["shops"]] == [None]  # the line is in Any shop
    # It is in Recent changes, with an Undo.
    listed = ok(kitchen.get(f"{API}/changes"))["changes"]
    assert listed[0]["id"] == removed["change"]["id"] and listed[0]["can_undo"] is True
    undone = ok(kitchen.post(f"{API}/changes/{removed['change']['id']}/undo"))
    assert undone["result"] == "done"
    assert names(shops(kitchen)) == ["Aldi", "Butcher"]
    assert shops(kitchen)[0]["id"] == aldi["id"]  # the same shop, with its old id
    assert ok(kitchen.get(f"{API}/foods/{milk['id']}"))["shop"]["name"] == "Aldi"
    view = ok(kitchen.get(f"{API}/shopping/lists/{main}"))
    assert [s["shop"]["name"] for s in view["shops"]] == ["Aldi"]


def test_a_ticked_line_in_a_removed_shop_moves_too(kitchen: TestClient) -> None:
    aldi = ok(kitchen.post(f"{API}/shops", json={"name": "Aldi"}), 201)
    milk = food(kitchen, "Milk")
    line = add_line(
        kitchen, main_id(kitchen), milk["id"], amount={"amount": 1, "unit": "l"}, shop_id=aldi["id"]
    )["item"]
    assert line["shop"]["name"] == "Aldi"
    ok(kitchen.delete(f"{API}/shops/{aldi['id']}"))
    with db(kitchen) as session:
        assert session.get(ListItem, line["id"]).shop_id is None


def test_removing_a_shop_keeps_its_aisle_order_for_undo(kitchen: TestClient) -> None:
    aldi = ok(kitchen.post(f"{API}/shops", json={"name": "Aldi"}), 201)
    with db(kitchen) as session:
        session.get(Shop, aldi["id"]).aisle_order = ["dairy", "bakery"]
        session.commit()
    removed = ok(kitchen.delete(f"{API}/shops/{aldi['id']}"))
    ok(kitchen.post(f"{API}/changes/{removed['change']['id']}/undo"))
    with db(kitchen) as session:
        assert session.get(Shop, aldi["id"]).aisle_order == ["dairy", "bakery"]


def test_undo_is_refused_when_a_newer_shop_took_the_id(kitchen: TestClient) -> None:
    aldi = ok(kitchen.post(f"{API}/shops", json={"name": "Aldi"}), 201)
    removed = ok(kitchen.delete(f"{API}/shops/{aldi['id']}"))
    again = ok(kitchen.post(f"{API}/shops", json={"name": "Lidl"}), 201)
    if again["id"] == aldi["id"]:  # SQLite reuses the highest id
        refused = kitchen.post(f"{API}/changes/{removed['change']['id']}/undo")
        assert refused.status_code == 409 and refused.json()["code"] == "cannot_undo"
        assert names(shops(kitchen)) == ["Lidl"]


def test_any_household_member_removes_a_shop(member: TestClient, kitchen: TestClient) -> None:
    aldi = ok(kitchen.post(f"{API}/shops", json={"name": "Aldi"}), 201)
    ok(member.delete(f"{API}/shops/{aldi['id']}"))
    assert shops(kitchen) == []


def test_another_households_shop_is_not_found(kitchen: TestClient, neighbour: TestClient) -> None:
    theirs = ok(neighbour.post(f"{API}/shops", json={"name": "Theirs"}), 201)
    assert kitchen.delete(f"{API}/shops/{theirs['id']}").status_code == 404
    assert kitchen.patch(f"{API}/shops/{theirs['id']}", json={"name": "Mine"}).status_code == 404
    assert names(shops(neighbour)) == ["Theirs"]
    ours = ok(kitchen.post(f"{API}/shops", json={"name": "Ours"}), 201)
    refused = kitchen.put(f"{API}/shops/order", json={"ids": [theirs["id"]]})
    assert refused.status_code == 422 and ours


def test_removing_a_shop_twice_with_one_key_is_one_removal(kitchen: TestClient) -> None:
    aldi = ok(kitchen.post(f"{API}/shops", json={"name": "Aldi"}), 201)
    headers = {"Idempotency-Key": "remove-aldi-1"}
    first = ok(kitchen.delete(f"{API}/shops/{aldi['id']}", headers=headers))
    again = kitchen.delete(f"{API}/shops/{aldi['id']}", headers=headers)
    assert again.status_code == 200 and again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["change"]["id"] == first["change"]["id"]


# --- Places -----------------------------------------------------------------------------------


def test_rename_and_order_places(member: TestClient, kitchen: TestClient) -> None:
    spice = place_id(kitchen, "Spice rack")
    renamed = ok(member.patch(f"{API}/places/{spice}", json={"name": " Spices "}))
    assert renamed == {"id": spice, "name": "Spices", "kind": "cupboard"}
    clash = kitchen.patch(f"{API}/places/{spice}", json={"name": "cupboard"})
    assert clash.status_code == 409 and clash.json()["code"] == "place_exists"
    ids = [p["id"] for p in ok(kitchen.get(f"{API}/places"))]
    wanted = [ids[3], ids[0], ids[1], ids[2]]
    order = ok(member.put(f"{API}/places/order", json={"ids": wanted}))
    assert [p["id"] for p in order] == wanted
    assert [p["id"] for p in ok(kitchen.get(f"{API}/places"))] == wanted
    bad = kitchen.put(f"{API}/places/order", json={"ids": ids[:2]})
    assert bad.status_code == 422 and bad.json()["code"] == "not_all_places"


def test_an_empty_place_is_removed_and_undo_makes_it_again(kitchen: TestClient) -> None:
    spice = place_id(kitchen, "Spice rack")
    removed = ok(kitchen.delete(f"{API}/places/{spice}"))
    assert removed["change"]["summary"] == "Removed the place Spice rack"
    assert "Spice rack" not in names(ok(kitchen.get(f"{API}/places")))
    ok(kitchen.post(f"{API}/changes/{removed['change']['id']}/undo"))
    back = ok(kitchen.get(f"{API}/places"))
    assert names(back) == ["Fridge", "Freezer", "Cupboard", "Spice rack"]
    assert back[3] == {"id": spice, "name": "Spice rack", "kind": "cupboard"}


def test_a_place_with_things_in_it_says_how_many_and_stays(kitchen: TestClient) -> None:
    cupboard = place_id(kitchen, "Cupboard")
    for number in range(3):
        stock(kitchen, food(kitchen, f"Rice {number}")["id"], cupboard)
    refused = kitchen.delete(f"{API}/places/{cupboard}")
    body = refused.json()
    assert refused.status_code == 409 and body["code"] == "place_not_empty"
    assert body["things"] == 3
    assert body["detail"] == "Cupboard has 3 things in it. Move them to…"
    assert "Cupboard" in names(ok(kitchen.get(f"{API}/places")))


def test_things_in_a_place_move_then_it_goes_and_undo_puts_everything_back(
    kitchen: TestClient,
) -> None:
    cupboard = place_id(kitchen, "Cupboard")
    spice = place_id(kitchen, "Spice rack")
    rice = food(kitchen, "Rice", place_id=cupboard)
    lentils = food(kitchen, "Lentils")
    stock(kitchen, rice["id"], cupboard, 500)
    stock(kitchen, lentils["id"], cupboard, 300)
    removed = ok(kitchen.delete(f"{API}/places/{cupboard}", params={"move_to": spice}))
    assert "Cupboard" not in names(ok(kitchen.get(f"{API}/places")))
    with db(kitchen) as session:
        lots = list(session.scalars(select(StockLot)))
        assert lots and all(lot.place_id == spice for lot in lots)
        assert session.get(Food, rice["id"]).place_id == spice  # "usually kept in" follows
        # The earlier changes' lines point at a place that is still there.
        assert all(
            line.place_after_id in (None, spice) for line in session.scalars(select(ChangeLine))
        )
    undone = ok(kitchen.post(f"{API}/changes/{removed['change']['id']}/undo"))
    assert undone["result"] == "done"
    assert place_id(kitchen, "Cupboard") == cupboard
    with db(kitchen) as session:
        assert all(lot.place_id == cupboard for lot in session.scalars(select(StockLot)))
        assert session.get(Food, rice["id"]).place_id == cupboard
        assert {line.place_after_id for line in session.scalars(select(ChangeLine))} == {cupboard}


def test_undo_leaves_what_moved_again_since(kitchen: TestClient) -> None:
    cupboard = place_id(kitchen, "Cupboard")
    spice = place_id(kitchen, "Spice rack")
    fridge = place_id(kitchen, "Fridge")
    stock(kitchen, food(kitchen, "Rice")["id"], cupboard)
    stock(kitchen, food(kitchen, "Dal")["id"], cupboard)
    removed = ok(kitchen.delete(f"{API}/places/{cupboard}", params={"move_to": spice}))
    with db(kitchen) as session:
        first = session.scalars(select(StockLot).order_by(StockLot.id)).first()
        first.place_id = fridge
        session.commit()
    ok(kitchen.post(f"{API}/changes/{removed['change']['id']}/undo"))
    with db(kitchen) as session:
        where = {lot.id: lot.place_id for lot in session.scalars(select(StockLot))}
    assert sorted(where.values()) == sorted([fridge, cupboard])


def test_the_last_fridge_and_the_last_freezer_stay(kitchen: TestClient) -> None:
    for name in ("Fridge", "Freezer"):
        refused = kitchen.delete(f"{API}/places/{place_id(kitchen, name)}")
        assert refused.status_code == 409 and refused.json()["code"] == "last_of_kind"
        assert name in names(ok(kitchen.get(f"{API}/places")))
    assert refused.json()["detail"] == (
        "Mealwright needs a freezer, and Freezer is your last one, so it stays."
    )


def test_a_household_with_one_place_keeps_it(kitchen: TestClient) -> None:
    # Review r1 L5: with data made outside the app (no Fridge or Freezer), a 409, not a 500.
    from mealwright.models import Place

    only = place_id(kitchen, "Cupboard")
    with db(kitchen) as session:
        for place in session.query(Place).filter(Place.id != only):
            session.delete(place)
        session.commit()
    refused = kitchen.delete(f"{API}/places/{only}")
    assert refused.status_code == 409 and refused.json()["code"] == "last_of_kind"


def test_a_second_fridge_can_go_and_the_first_then_stays(kitchen: TestClient) -> None:
    garage = ok(
        kitchen.post(f"{API}/places", json={"name": "Garage fridge", "kind": "fridge"}), 201
    )
    ok(kitchen.delete(f"{API}/places/{garage['id']}"))
    refused = kitchen.delete(f"{API}/places/{place_id(kitchen, 'Fridge')}")
    assert refused.status_code == 409 and refused.json()["code"] == "last_of_kind"


def test_removing_a_fridge_with_things_in_it_moves_them_to_the_other_fridge(
    kitchen: TestClient,
) -> None:
    garage = ok(
        kitchen.post(f"{API}/places", json={"name": "Garage fridge", "kind": "fridge"}), 201
    )
    fridge = place_id(kitchen, "Fridge")
    stock(kitchen, food(kitchen, "Milk")["id"], garage["id"])
    ok(kitchen.delete(f"{API}/places/{garage['id']}", params={"move_to": fridge}))
    with db(kitchen) as session:
        assert [lot.place_id for lot in session.scalars(select(StockLot))] == [fridge]


def test_empty_packets_kept_for_undo_do_not_count_and_do_not_block(kitchen: TestClient) -> None:
    cupboard = place_id(kitchen, "Cupboard")
    spice = place_id(kitchen, "Spice rack")
    rice = food(kitchen, "Rice")
    stock(kitchen, rice["id"], cupboard, 100)
    with db(kitchen) as session:
        lot_id = session.scalars(select(StockLot.id)).one()
    ok(kitchen.post(f"{API}/stock/{lot_id}/used"))
    ok(kitchen.delete(f"{API}/places/{cupboard}"))
    with db(kitchen) as session:
        lots = list(session.scalars(select(StockLot)))
        assert len(lots) == 1 and lots[0].amount_milli == 0 and lots[0].place_id == spice


def test_move_to_must_be_another_place_of_the_household(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    cupboard = place_id(kitchen, "Cupboard")
    same = kitchen.delete(f"{API}/places/{cupboard}", params={"move_to": cupboard})
    assert same.status_code == 422 and same.json()["code"] == "same_place"
    theirs = place_id(neighbour, "Cupboard")
    stolen = kitchen.delete(f"{API}/places/{cupboard}", params={"move_to": theirs})
    assert stolen.status_code == 404
    assert kitchen.delete(f"{API}/places/{theirs}").status_code == 404
    assert "Cupboard" in names(ok(neighbour.get(f"{API}/places")))


def test_a_member_removes_a_place(member: TestClient, kitchen: TestClient) -> None:
    ok(member.delete(f"{API}/places/{place_id(kitchen, 'Spice rack')}"))
    assert "Spice rack" not in names(ok(kitchen.get(f"{API}/places")))


def test_the_other_households_places_are_not_in_an_order(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    ids = [p["id"] for p in ok(kitchen.get(f"{API}/places"))]
    theirs = [p["id"] for p in ok(neighbour.get(f"{API}/places"))]
    refused = kitchen.put(f"{API}/places/order", json={"ids": [*ids[:-1], theirs[0]]})
    assert refused.status_code == 422
    with db(kitchen) as session:
        assert session.get(Place, theirs[0]).household_id == 2


# --- Recent changes: every kind, in one list (F172) -------------------------------------------


def test_recent_changes_lists_every_kind_newest_first_and_pages(kitchen: TestClient) -> None:
    rice = food(kitchen, "Rice")
    stock(kitchen, rice["id"], place_id(kitchen, "Cupboard"))  # a pantry change
    dinner = next(s for s in slots(kitchen) if s["name"] == "Dinner")
    ok(
        kitchen.post(
            f"{API}/plan/items",
            json={
                "date": ok(kitchen.get(f"{API}/household"))["today"],
                "slot_id": dinner["id"],
                "ingredient_id": rice["id"],
            },
        ),
        201,
    )  # a plan change
    ok(kitchen.patch(f"{API}/meal-slots/{dinner['id']}", json={"name": "Supper"}))
    aldi = ok(kitchen.post(f"{API}/shops", json={"name": "Aldi"}), 201)
    ok(kitchen.delete(f"{API}/shops/{aldi['id']}"))
    everything = ok(kitchen.get(f"{API}/changes"))["changes"]
    kinds = [c["kind"] for c in everything]
    assert kinds[:3] == ["shop_removed", "shop_added", "plan_slot"]
    assert "added" in kinds and any(k.startswith("plan_") for k in kinds)
    assert [c["id"] for c in everything] == sorted((c["id"] for c in everything), reverse=True)
    # Paging: the next page starts below the first page's last change.
    first = ok(kitchen.get(f"{API}/changes", params={"limit": 2}))
    assert len(first["changes"]) == 2 and first["next"] is not None
    second = ok(kitchen.get(f"{API}/changes", params={"limit": 2, "before": first["next"]}))
    assert second["changes"][0]["id"] < first["changes"][-1]["id"]
    # The old filters still work.
    pantry = ok(kitchen.get(f"{API}/changes", params={"area": "pantry"}))["changes"]
    assert [c["kind"] for c in pantry] == ["added"]


def test_adding_a_shop_is_in_recent_changes_and_undo_takes_it_away(kitchen: TestClient) -> None:
    # Fails without F225: adding a shop recorded nothing, so there was no change to undo.
    aldi = ok(kitchen.post(f"{API}/shops", json={"name": "Aldi"}), 201)
    listed = ok(kitchen.get(f"{API}/changes"))["changes"]
    assert listed[0]["summary"] == "Added the shop Aldi" and listed[0]["can_undo"] is True
    assert listed[0]["kind"] == "shop_added"
    undone = ok(kitchen.post(f"{API}/changes/{listed[0]['id']}/undo"))
    assert undone["result"] == "done"
    assert names(shops(kitchen)) == []
    assert aldi["id"]


def test_adding_a_shop_that_is_already_there_records_nothing(kitchen: TestClient) -> None:
    ok(kitchen.post(f"{API}/shops", json={"name": "Aldi"}), 201)
    ok(kitchen.post(f"{API}/shops", json={"name": "aldi"}), 200)
    summaries = [c["summary"] for c in ok(kitchen.get(f"{API}/changes"))["changes"]]
    assert summaries == ["Added the shop Aldi"]


def test_a_shop_in_use_cannot_have_its_adding_undone(kitchen: TestClient) -> None:
    aldi = ok(kitchen.post(f"{API}/shops", json={"name": "Aldi"}), 201)
    change = ok(kitchen.get(f"{API}/changes"))["changes"][0]
    food(kitchen, "Milk", shop_id=aldi["id"])
    refused = kitchen.post(f"{API}/changes/{change['id']}/undo")
    assert refused.status_code == 409 and refused.json()["code"] == "cannot_undo"
    assert names(shops(kitchen)) == ["Aldi"]


def test_renaming_a_shop_is_in_recent_changes_and_undo_puts_the_old_name_back(
    kitchen: TestClient,
) -> None:
    # Fails without F225: a rename recorded nothing.
    aldi = ok(kitchen.post(f"{API}/shops", json={"name": "Aldi"}), 201)
    ok(kitchen.patch(f"{API}/shops/{aldi['id']}", json={"name": "Lidl"}))
    top = ok(kitchen.get(f"{API}/changes"))["changes"][0]
    assert top["summary"] == "Renamed the shop Aldi to Lidl" and top["can_undo"] is True
    assert ok(kitchen.post(f"{API}/changes/{top['id']}/undo"))["result"] == "done"
    assert names(shops(kitchen)) == ["Aldi"]


def test_a_rename_to_the_same_name_records_nothing_and_a_stale_rename_cannot_be_undone(
    kitchen: TestClient,
) -> None:
    aldi = ok(kitchen.post(f"{API}/shops", json={"name": "Aldi"}), 201)
    ok(kitchen.patch(f"{API}/shops/{aldi['id']}", json={"name": "Aldi"}))
    ok(kitchen.patch(f"{API}/shops/{aldi['id']}", json={"name": "Lidl"}))
    first = ok(kitchen.get(f"{API}/changes"))["changes"][0]
    ok(kitchen.patch(f"{API}/shops/{aldi['id']}", json={"name": "Spar"}))
    refused = kitchen.post(f"{API}/changes/{first['id']}/undo")
    assert refused.status_code == 409 and refused.json()["code"] == "cannot_undo"
    assert names(shops(kitchen)) == ["Spar"]
    summaries = [c["summary"] for c in ok(kitchen.get(f"{API}/changes"))["changes"]]
    assert summaries.count("Renamed the shop Aldi to Lidl") == 1


# --- The rest of Settings, in Recent changes with an Undo (RF5, H8; cabledrawer 11 Nov) -----------
# Each of these failed on the base: nothing was recorded, so there was no change to undo.


def latest(kitchen: TestClient) -> dict[str, Any]:
    found: dict[str, Any] = ok(kitchen.get(f"{API}/changes"))["changes"][0]
    return found


def undo(kitchen: TestClient, change: dict[str, Any]) -> Any:
    return kitchen.post(f"{API}/changes/{change['id']}/undo")


def test_adding_a_place_is_in_recent_changes_and_undo_takes_it_away(kitchen: TestClient) -> None:
    made = ok(kitchen.post(f"{API}/places", json={"name": "Garage", "kind": "cupboard"}), 201)
    top = latest(kitchen)
    assert top["kind"] == "place_added" and top["summary"] == "Added the place Garage"
    assert top["can_undo"] is True
    assert ok(undo(kitchen, top))["result"] == "done"
    assert made["id"] not in [p["id"] for p in ok(kitchen.get(f"{API}/places"))]


def test_a_place_in_use_cannot_have_its_adding_undone(kitchen: TestClient) -> None:
    made = ok(kitchen.post(f"{API}/places", json={"name": "Garage", "kind": "cupboard"}), 201)
    top = latest(kitchen)
    rice = food(kitchen, "Rice")
    stock(kitchen, rice["id"], made["id"])
    refused = undo(kitchen, top)
    assert refused.status_code == 409 and refused.json()["code"] == "cannot_undo"
    assert "Garage" in names(ok(kitchen.get(f"{API}/places")))


def test_adding_a_place_twice_with_one_key_is_one_place(kitchen: TestClient) -> None:
    headers = {"Idempotency-Key": "place-once"}
    body = {"name": "Garage", "kind": "cupboard"}
    first = ok(kitchen.post(f"{API}/places", json=body, headers=headers), 201)
    again = kitchen.post(f"{API}/places", json=body, headers=headers)
    assert again.status_code == 200 and again.json() == first
    kinds = [c["kind"] for c in ok(kitchen.get(f"{API}/changes"))["changes"]]
    assert kinds.count("place_added") == 1


def test_renaming_a_place_is_in_recent_changes_and_undo_puts_the_old_name_back(
    kitchen: TestClient,
) -> None:
    spice = place_id(kitchen, "Spice rack")
    ok(kitchen.patch(f"{API}/places/{spice}", json={"name": "Larder"}))
    top = latest(kitchen)
    assert top["kind"] == "place_renamed"
    assert top["summary"] == "Renamed the place Spice rack to Larder" and top["can_undo"] is True
    assert ok(undo(kitchen, top))["result"] == "done"
    assert "Spice rack" in names(ok(kitchen.get(f"{API}/places")))


def test_a_place_rename_to_the_same_name_records_nothing_and_a_stale_one_cannot_be_undone(
    kitchen: TestClient,
) -> None:
    spice = place_id(kitchen, "Spice rack")
    ok(kitchen.patch(f"{API}/places/{spice}", json={"name": "Spice rack"}))
    assert ok(kitchen.get(f"{API}/changes"))["changes"] == []
    ok(kitchen.patch(f"{API}/places/{spice}", json={"name": "Larder"}))
    first = latest(kitchen)
    ok(kitchen.patch(f"{API}/places/{spice}", json={"name": "Pantry shelf"}))
    refused = undo(kitchen, first)
    assert refused.status_code == 409 and refused.json()["code"] == "cannot_undo"
    assert "Pantry shelf" in names(ok(kitchen.get(f"{API}/places")))


def test_reordering_the_shops_is_in_recent_changes_and_undo_puts_the_order_back(
    kitchen: TestClient,
) -> None:
    a = ok(kitchen.post(f"{API}/shops", json={"name": "Aldi"}), 201)
    b = ok(kitchen.post(f"{API}/shops", json={"name": "Lidl"}), 201)
    ok(kitchen.put(f"{API}/shops/order", json={"ids": [b["id"], a["id"]]}))
    top = latest(kitchen)
    assert top["kind"] == "shops_ordered" and top["summary"] == "Changed the order of the shops"
    assert names(shops(kitchen)) == ["Lidl", "Aldi"]
    assert ok(undo(kitchen, top))["result"] == "done"
    assert names(shops(kitchen)) == ["Aldi", "Lidl"]


def test_reordering_the_places_is_in_recent_changes_and_undo_puts_the_order_back(
    kitchen: TestClient,
) -> None:
    ids = [p["id"] for p in ok(kitchen.get(f"{API}/places"))]
    wanted = [ids[3], ids[0], ids[1], ids[2]]
    ok(kitchen.put(f"{API}/places/order", json={"ids": wanted}))
    top = latest(kitchen)
    assert top["kind"] == "places_ordered" and top["summary"] == "Changed the order of the places"
    assert ok(undo(kitchen, top))["result"] == "done"
    assert [p["id"] for p in ok(kitchen.get(f"{API}/places"))] == ids


def test_the_same_order_records_nothing_and_a_stale_order_cannot_be_undone(
    kitchen: TestClient,
) -> None:
    a = ok(kitchen.post(f"{API}/shops", json={"name": "Aldi"}), 201)
    b = ok(kitchen.post(f"{API}/shops", json={"name": "Lidl"}), 201)
    ok(kitchen.put(f"{API}/shops/order", json={"ids": [a["id"], b["id"]]}))
    kinds = [c["kind"] for c in ok(kitchen.get(f"{API}/changes"))["changes"]]
    assert "shops_ordered" not in kinds
    ok(kitchen.put(f"{API}/shops/order", json={"ids": [b["id"], a["id"]]}))
    first = latest(kitchen)
    ok(kitchen.put(f"{API}/shops/order", json={"ids": [a["id"], b["id"]]}))
    refused = undo(kitchen, first)
    assert refused.status_code == 409 and refused.json()["code"] == "cannot_undo"
    assert names(shops(kitchen)) == ["Aldi", "Lidl"]


def test_a_shop_added_after_an_order_does_not_stop_its_undo(kitchen: TestClient) -> None:
    a = ok(kitchen.post(f"{API}/shops", json={"name": "Aldi"}), 201)
    b = ok(kitchen.post(f"{API}/shops", json={"name": "Lidl"}), 201)
    ok(kitchen.put(f"{API}/shops/order", json={"ids": [b["id"], a["id"]]}))
    first = latest(kitchen)
    ok(kitchen.post(f"{API}/shops", json={"name": "Spar"}), 201)
    assert ok(undo(kitchen, first))["result"] == "done"
    assert names(shops(kitchen)) == ["Aldi", "Lidl", "Spar"]


def test_the_kitchens_equipment_is_in_recent_changes_and_undo_puts_it_back(
    kitchen: TestClient,
) -> None:
    before = ok(kitchen.get(f"{API}/household/kitchen"))
    ok(
        kitchen.patch(
            f"{API}/household/kitchen",
            json={"hob_rings": before["hob_rings"] + 1, "pressure_cookers": 0, "oven": False},
        )
    )
    top = latest(kitchen)
    assert top["kind"] == "kitchen_changed" and top["can_undo"] is True
    assert top["summary"].startswith("Changed your kitchen: ")
    assert f"{before['hob_rings'] + 1} hob rings (was {before['hob_rings']})" in top["summary"]
    assert "no oven (was yes)" in top["summary"]
    assert ok(undo(kitchen, top))["result"] == "done"
    after = ok(kitchen.get(f"{API}/household/kitchen"))
    assert {k: after[k] for k in ("hob_rings", "pressure_cookers", "oven")} == {
        k: before[k] for k in ("hob_rings", "pressure_cookers", "oven")
    }
    assert after["asked"] is True  # asked stays: the kitchen was asked, whatever the numbers


def test_saving_the_same_kitchen_records_nothing_and_a_stale_one_cannot_be_undone(
    kitchen: TestClient,
) -> None:
    before = ok(kitchen.get(f"{API}/household/kitchen"))
    ok(kitchen.patch(f"{API}/household/kitchen", json={"hob_rings": before["hob_rings"]}))
    assert ok(kitchen.get(f"{API}/changes"))["changes"] == []
    ok(kitchen.patch(f"{API}/household/kitchen", json={"hob_rings": 2}))
    first = latest(kitchen)
    ok(kitchen.patch(f"{API}/household/kitchen", json={"hob_rings": 3}))
    refused = undo(kitchen, first)
    assert refused.status_code == 409 and refused.json()["code"] == "cannot_undo"
    assert ok(kitchen.get(f"{API}/household/kitchen"))["hob_rings"] == 3


def test_the_batch_cook_switch_is_in_recent_changes_and_only_an_admin_undoes_it(
    member: TestClient, kitchen: TestClient
) -> None:
    ok(kitchen.patch(f"{API}/household", json={"batch_cook": False}))
    top = latest(kitchen)
    assert top["kind"] == "batch_cook_switch" and top["summary"] == "Switched Batch cook off"
    assert ok(kitchen.get(f"{API}/household"))["batch_cook"] is False
    forbidden = undo(member, top)
    assert forbidden.status_code == 403, forbidden.text
    assert ok(undo(kitchen, top))["result"] == "done"
    assert ok(kitchen.get(f"{API}/household"))["batch_cook"] is True
    # Setting it to what it already is records nothing; a switch back on is a change again.
    ok(kitchen.patch(f"{API}/household", json={"batch_cook": True}))
    ok(kitchen.patch(f"{API}/household", json={"batch_cook": False}))
    ok(kitchen.patch(f"{API}/household", json={"batch_cook": True}))
    kinds = [c["kind"] for c in ok(kitchen.get(f"{API}/changes"))["changes"]]
    assert kinds.count("batch_cook_switch") == 3  # off, then off and on again (the first undone)
    assert latest(kitchen)["summary"] == "Switched Batch cook on"


def test_a_stale_batch_cook_switch_cannot_be_undone(kitchen: TestClient) -> None:
    ok(kitchen.patch(f"{API}/household", json={"batch_cook": False}))
    first = latest(kitchen)
    ok(kitchen.patch(f"{API}/household", json={"batch_cook": True}))
    refused = undo(kitchen, first)
    assert refused.status_code == 409 and refused.json()["code"] == "cannot_undo"
    assert ok(kitchen.get(f"{API}/household"))["batch_cook"] is True


def test_undoing_the_adding_of_a_place_cannot_leave_no_fridge_or_freezer(
    kitchen: TestClient,
) -> None:
    # RF5 fix round 1: add a second freezer, remove the first, then Undo the adding: that would
    # leave the household with no freezer, which the removal itself never allows.
    ok(kitchen.post(f"{API}/places", json={"name": "Chest freezer", "kind": "freezer"}), 201)
    added = latest(kitchen)
    ok(kitchen.delete(f"{API}/places/{place_id(kitchen, 'Freezer')}"))
    before = ok(kitchen.get(f"{API}/places"))
    refused = undo(kitchen, added)
    assert refused.status_code == 409 and refused.json()["code"] == "cannot_undo"
    assert ok(kitchen.get(f"{API}/places")) == before
    assert "Chest freezer" in names(before)
