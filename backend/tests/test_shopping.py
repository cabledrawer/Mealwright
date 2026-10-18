"""Shopping lists: the plain online API (docs/dev/sync-protocol.md sections 3, 5.7 and 9).

Ticking and the pantry side arrive in the next pull request, so ticked items are set up
here by writing the rows directly.
"""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from mealwright import jobs
from mealwright.models import (
    Change,
    Food,
    Household,
    ListItem,
    ListTick,
    ShoppingList,
    SyncAction,
    utcnow,
)

API = "/api/v1"


def db(kitchen: TestClient) -> Any:
    return kitchen.app.state.sessionmaker()  # type: ignore[attr-defined]


def ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def food(kitchen: TestClient, name: str, **extra: Any) -> dict[str, Any]:
    found: dict[str, Any] = ok(kitchen.post(f"{API}/foods", json={"name": name, **extra}), 201)[
        "food"
    ]
    return found


def main_id(kitchen: TestClient) -> str:
    lists = ok(kitchen.get(f"{API}/shopping/lists"))["lists"]
    assert lists[0]["main"]
    return str(lists[0]["id"])


def add(kitchen: TestClient, list_id: str, food_id: int, **body: Any) -> dict[str, Any]:
    result: dict[str, Any] = ok(
        kitchen.post(f"{API}/shopping/lists/{list_id}/items", json={"food_id": food_id, **body}),
        201,
    )
    return result


def counter(kitchen: TestClient) -> int:
    with db(kitchen) as session:
        return int(session.get(Household, 1).list_seq)


def tick(kitchen: TestClient, item_id: str) -> None:
    """What PR 3's tick will leave behind: the item's ticked_at and a standing tick."""
    with db(kitchen) as session:
        item = session.get(ListItem, item_id)
        item.ticked_at = utcnow()
        item.ticked_by_name = "Tess"
        session.add(
            ListTick(household_id=1, id=f"tick-{item_id}", item_id=item_id, login_name="Tess")
        )
        session.commit()


# --- Lists -------------------------------------------------------------------------------------


def test_needs_sign_in(client: TestClient) -> None:
    assert client.get(f"{API}/shopping/lists").status_code == 401


def test_new_household_has_a_main_list(kitchen: TestClient) -> None:
    lists = ok(kitchen.get(f"{API}/shopping/lists"))["lists"]
    assert [(x["name"], x["main"], x["to_buy"], x["ticked"]) for x in lists] == [
        ("This week", True, 0, 0)
    ]
    with db(kitchen) as session:  # made with the household, not on first look
        assert session.scalar(select(func.count()).select_from(ShoppingList)) == 1


def test_only_one_main_list_per_household(kitchen: TestClient) -> None:
    from sqlalchemy.exc import IntegrityError

    with db(kitchen) as session:
        session.add(ShoppingList(id="x" * 36, household_id=1, name="Second", main=True))
        with pytest.raises(IntegrityError):
            session.commit()


def test_make_rename_and_remove_an_extra_list(kitchen: TestClient) -> None:
    made = ok(kitchen.post(f"{API}/shopping/lists", json={"name": "  Party   on Saturday "}), 201)
    assert made["shopping_list"]["name"] == "Party on Saturday"
    assert made["shopping_list"]["main"] is False
    assert made["change"]["kind"] == "list_made"
    party = made["shopping_list"]["id"]
    ok(kitchen.post(f"{API}/shopping/lists", json={"name": "Party on Saturday"}), 201)  # no clash
    names = [x["name"] for x in ok(kitchen.get(f"{API}/shopping/lists"))["lists"]]
    assert names == ["This week", "Party on Saturday", "Party on Saturday"]

    renamed = ok(kitchen.patch(f"{API}/shopping/lists/{party}", json={"name": "BBQ"}))
    assert renamed["shopping_list"]["name"] == "BBQ"
    assert renamed["change"]["summary"] == "Renamed the list Party on Saturday to BBQ"
    same = ok(kitchen.patch(f"{API}/shopping/lists/{party}", json={"name": "BBQ"}))
    assert same["change"] is None  # nothing to do, no change, no number

    removed = ok(kitchen.delete(f"{API}/shopping/lists/{party}"))
    assert removed["change"]["kind"] == "list_removed"
    assert kitchen.get(f"{API}/shopping/lists/{party}").status_code == 404
    assert party not in [x["id"] for x in ok(kitchen.get(f"{API}/shopping/lists"))["lists"]]
    assert kitchen.delete(f"{API}/shopping/lists/{party}").status_code == 404


def test_the_main_list_can_be_renamed_but_never_removed(kitchen: TestClient) -> None:  # SY-33
    main = main_id(kitchen)
    before = counter(kitchen)
    refused = kitchen.delete(f"{API}/shopping/lists/{main}")
    assert refused.status_code == 409 and refused.json()["code"] == "main_list"
    assert counter(kitchen) == before
    renamed = ok(kitchen.patch(f"{API}/shopping/lists/{main}", json={"name": "Our week"}))
    assert renamed["shopping_list"]["name"] == "Our week" and renamed["shopping_list"]["main"]


def test_list_names_must_be_real(kitchen: TestClient) -> None:
    assert kitchen.post(f"{API}/shopping/lists", json={"name": "   "}).status_code == 422
    assert kitchen.post(f"{API}/shopping/lists", json={"name": "x" * 61}).status_code == 422
    bad = kitchen.post(f"{API}/shopping/lists", json={"id": "not-a-uuid", "name": "A"})
    assert bad.status_code == 422


def test_phone_made_list_ids(kitchen: TestClient) -> None:
    new_id = "0b6c3f0e-7c1a-4f7e-9d0b-2f7a3c1e5d42"
    made = ok(kitchen.post(f"{API}/shopping/lists", json={"id": new_id, "name": "Camp"}), 201)
    assert made["shopping_list"]["id"] == new_id
    again = kitchen.post(f"{API}/shopping/lists", json={"id": new_id, "name": "Camp"})
    assert again.status_code == 409 and again.json()["code"] == "id_taken"


def test_undo_make_rename_and_remove_a_list(kitchen: TestClient) -> None:
    made = ok(kitchen.post(f"{API}/shopping/lists", json={"name": "Party"}), 201)
    party = made["shopping_list"]["id"]
    renamed = ok(kitchen.patch(f"{API}/shopping/lists/{party}", json={"name": "BBQ"}))
    ok(kitchen.post(f"{API}/changes/{renamed['change']['id']}/undo"))
    assert ok(kitchen.get(f"{API}/shopping/lists/{party}"))["shopping_list"]["name"] == "Party"

    removed = ok(kitchen.delete(f"{API}/shopping/lists/{party}"))
    ok(kitchen.post(f"{API}/changes/{removed['change']['id']}/undo"))
    assert kitchen.get(f"{API}/shopping/lists/{party}").status_code == 200

    ok(kitchen.post(f"{API}/changes/{made['change']['id']}/undo"))  # "make" undone: gone
    assert kitchen.get(f"{API}/shopping/lists/{party}").status_code == 404


def test_a_removed_list_keeps_its_items_for_undo(kitchen: TestClient) -> None:
    party = ok(kitchen.post(f"{API}/shopping/lists", json={"name": "Party"}), 201)["shopping_list"]
    crisps = food(kitchen, "Crisps", counted_as="count")
    item = add(kitchen, party["id"], crisps["id"])["item"]
    removed = ok(kitchen.delete(f"{API}/shopping/lists/{party['id']}"))
    assert (
        kitchen.patch(
            f"{API}/shopping/items/{item['id']}", json={"amount": {"amount": 3, "unit": "g"}}
        ).status_code
        == 404
    )  # hidden list: nothing to edit online
    ok(kitchen.post(f"{API}/changes/{removed['change']['id']}/undo"))
    view = ok(kitchen.get(f"{API}/shopping/lists/{party['id']}"))
    assert view["shopping_list"]["to_buy"] == 1


# --- Items: adding ----------------------------------------------------------------------------


def test_add_with_a_typed_amount(kitchen: TestClient) -> None:
    flour = food(kitchen, "Plain flour")
    added = add(kitchen, main_id(kitchen), flour["id"], amount={"amount": 1.5, "unit": "kg"})
    item = added["item"]
    assert item["amount"]["amount"] == 1500 and item["amount"]["unit"] == "g"
    assert item["food"] == {"id": flour["id"], "name": "Plain flour"}
    assert item["source"] == "typed" and item["hand_edited"] is False
    assert item["added_by"] == "Tess" and item["ticked_by"] is None
    assert added["merged"] is False
    assert added["change"]["summary"] == "Added Plain flour to This week"


def test_blank_amounts(kitchen: TestClient) -> None:  # SY-40
    main = main_id(kitchen)
    dal = food(kitchen, "Toor dal")
    ok(kitchen.post(f"{API}/foods/{dal['id']}/sizes", json={"name": "packet", "amount": 500}), 201)
    onions = food(kitchen, "Onions", counted_as="count")
    tahini = food(kitchen, "Tahini")  # weight, no size
    packet = add(kitchen, main, dal["id"])["item"]["amount"]
    assert packet["amount"] == 500 and packet["as_sold"]["count"] == 1
    assert packet["as_sold"]["size"]["name"] == "packet"
    assert add(kitchen, main, onions["id"])["item"]["amount"]["amount"] == 1
    assert add(kitchen, main, tahini["id"])["item"]["amount"] is None
    explicit_null = add(kitchen, main, onions["id"], amount=None, shop_id=None)["item"]
    assert explicit_null["amount"]["amount"] == 2  # joined: 1 + 1


def test_added_by_size(kitchen: TestClient) -> None:
    dal = food(kitchen, "Toor dal")
    sized = ok(
        kitchen.post(f"{API}/foods/{dal['id']}/sizes", json={"name": "packet", "amount": 500}), 201
    )["food"]["sizes"][0]
    item = add(kitchen, main_id(kitchen), dal["id"], amount={"amount": 2, "size_id": sized["id"]})[
        "item"
    ]
    assert item["amount"]["amount"] == 1000 and item["amount"]["as_sold"]["count"] == 2


def test_add_refuses_other_things(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    dal = food(kitchen, "Toor dal")
    url = f"{API}/shopping/lists/{main}/items"
    assert kitchen.post(url, json={"food_id": 9999}).status_code == 404
    assert kitchen.post(url, json={"food_id": dal["id"], "shop_id": 9999}).status_code == 404
    huge = {"food_id": dal["id"], "amount": {"amount": 1_000_000, "unit": "kg"}}
    assert kitchen.post(url, json=huge).json()["code"] == "too_big"
    asks = kitchen.post(
        url, json={"food_id": dal["id"], "amount": {"amount": 1, "unit": "cup"}}
    )  # weight per cup unknown: asked once, like the rest of the API
    assert asks.status_code == 409 and asks.json()["code"] == "ask_once"
    assert (
        kitchen.post(f"{API}/shopping/lists/nope/items", json={"food_id": dal["id"]}).status_code
        == 404
    )
    kitchen.delete(f"{API}/foods/{dal['id']}")
    assert kitchen.post(url, json={"food_id": dal["id"]}).status_code == 404  # removed


def test_phone_made_item_ids(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    dal = food(kitchen, "Toor dal")
    new_id = "6f1c0000-0000-4000-8000-000000000001"
    added = add(kitchen, main, dal["id"], id=new_id, amount={"amount": 1, "unit": "kg"})
    assert added["item"]["id"] == new_id
    again = kitchen.post(
        f"{API}/shopping/lists/{main}/items",
        json={"id": new_id, "food_id": dal["id"], "shop_id": None},
    )
    assert again.status_code == 409 and again.json()["code"] == "id_taken"


def test_usual_shop_is_copied_and_any_shop_can_be_chosen(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    shop = ok(kitchen.post(f"{API}/shops", json={"name": "Supermarket"}), 201)
    milk = food(kitchen, "Milk", shop_id=shop["id"])
    assert add(kitchen, main, milk["id"], amount={"amount": 1, "unit": "l"})["item"]["shop"] == {
        "id": shop["id"],
        "name": "Supermarket",
    }
    anywhere = add(kitchen, main, milk["id"], amount={"amount": 1, "unit": "l"}, shop_id=None)
    assert anywhere["item"]["shop"] is None and anywhere["merged"] is False  # different shop


def test_adding_the_same_thing_adds_the_amounts_up(kitchen: TestClient) -> None:  # SY-64, SY-65
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    first = add(kitchen, main, milk["id"], amount={"amount": 2, "unit": "l"})
    second = add(kitchen, main, milk["id"], amount={"amount": 1, "unit": "l"})
    assert second["merged"] is True and second["item"]["id"] == first["item"]["id"]
    assert second["item"]["amount"]["amount"] == 3000
    view = ok(kitchen.get(f"{API}/shopping/lists/{main}"))
    assert view["shopping_list"]["to_buy"] == 1
    # Undo puts the line back to its earlier amount.
    ok(kitchen.post(f"{API}/changes/{second['change']['id']}/undo"))
    view = ok(kitchen.get(f"{API}/shopping/lists/{main}"))
    assert view["shops"][0]["aisles"][0]["items"][0]["amount"]["amount"] == 2000


def test_a_blank_amount_joins_a_line_by_adding_its_usual_size(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    dal = food(kitchen, "Toor dal")
    ok(kitchen.post(f"{API}/foods/{dal['id']}/sizes", json={"name": "packet", "amount": 500}), 201)
    add(kitchen, main, dal["id"])
    joined = add(kitchen, main, dal["id"], amount={"amount": 250, "unit": "g"})
    assert joined["item"]["amount"]["amount"] == 750
    assert joined["item"]["amount"]["short"].startswith("1½")  # "1½ packets"


def test_ticked_lines_and_other_lists_do_not_join(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    party = ok(kitchen.post(f"{API}/shopping/lists", json={"name": "Party"}), 201)["shopping_list"]
    eggs = food(kitchen, "Eggs")
    first = add(kitchen, main, eggs["id"])["item"]
    elsewhere = add(kitchen, party["id"], eggs["id"])
    assert elsewhere["merged"] is False and elsewhere["item"]["id"] != first["id"]
    tick(kitchen, first["id"])
    again = add(kitchen, main, eggs["id"])
    assert again["merged"] is False and again["item"]["id"] != first["id"]


def test_an_amountless_line_takes_the_amount_of_the_one_added(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    tahini = food(kitchen, "Tahini")
    add(kitchen, main, tahini["id"])
    joined = add(kitchen, main, tahini["id"], amount={"amount": 200, "unit": "g"})
    assert joined["merged"] and joined["item"]["amount"]["amount"] == 200


# --- Items: amount, delete, clear ------------------------------------------------------------


def test_change_the_amount(kitchen: TestClient) -> None:  # SY-44
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    item = add(kitchen, main, milk["id"], amount={"amount": 2, "unit": "l"})["item"]
    changed = ok(
        kitchen.patch(
            f"{API}/shopping/items/{item['id']}", json={"amount": {"amount": 4, "unit": "l"}}
        )
    )
    assert changed["item"]["amount"]["amount"] == 4000
    assert changed["item"]["hand_edited"] is True and changed["item"]["source"] == "typed"
    assert changed["change"]["kind"] == "item_amount"
    same = ok(
        kitchen.patch(
            f"{API}/shopping/items/{item['id']}", json={"amount": {"amount": 4, "unit": "l"}}
        )
    )
    assert same["change"] is None
    missing = kitchen.patch(
        f"{API}/shopping/items/nope", json={"amount": {"amount": 4, "unit": "l"}}
    )
    assert missing.status_code == 404


def test_undo_change_amount_only_if_it_is_still_that_amount(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    item = add(kitchen, main, milk["id"], amount={"amount": 2, "unit": "l"})["item"]
    path = f"{API}/shopping/items/{item['id']}"
    first = ok(kitchen.patch(path, json={"amount": {"amount": 3, "unit": "l"}}))
    ok(kitchen.patch(path, json={"amount": {"amount": 4, "unit": "l"}}))
    undone = ok(kitchen.post(f"{API}/changes/{first['change']['id']}/undo"))
    assert undone["result"] == "nothing"  # someone changed it again since; left alone
    amount = ok(kitchen.get(f"{API}/shopping/lists/{main}"))["shops"][0]["aisles"][0]["items"][0]
    assert amount["amount"]["amount"] == 4000


def test_delete_leaves_a_tombstone_and_undo_brings_it_back(kitchen: TestClient) -> None:  # SY-45
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    item = add(kitchen, main, milk["id"], amount={"amount": 2, "unit": "l"})["item"]
    path = f"{API}/shopping/items/{item['id']}"
    deleted = ok(kitchen.delete(path))
    assert deleted["change"]["summary"] == "Took Milk off the list"
    with db(kitchen) as session:  # the row stays, hidden
        row = session.get(ListItem, item["id"])
        assert row.deleted_at is not None and row.deleted_by_name == "Tess"
    assert ok(kitchen.get(f"{API}/shopping/lists/{main}"))["shops"] == []
    before = counter(kitchen)
    assert ok(kitchen.delete(path))["change"] is None  # again: nothing happens
    assert counter(kitchen) == before
    gone = kitchen.patch(path, json={"amount": {"amount": 4, "unit": "l"}})
    assert gone.status_code == 409 and gone.json()["code"] == "item_deleted"
    ok(kitchen.post(f"{API}/changes/{deleted['change']['id']}/undo"))
    assert ok(kitchen.get(f"{API}/shopping/lists/{main}"))["shopping_list"]["to_buy"] == 1


def test_undo_an_add_takes_the_item_off(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    added = add(kitchen, main, milk["id"])
    ok(kitchen.post(f"{API}/changes/{added['change']['id']}/undo"))
    assert ok(kitchen.get(f"{API}/shopping/lists/{main}"))["shopping_list"]["to_buy"] == 0
    with db(kitchen) as session:
        assert session.get(ListItem, added["item"]["id"]).deleted_at is not None


def test_clear_ticked(kitchen: TestClient) -> None:  # SY-29, SY-31
    main = main_id(kitchen)
    dal, paneer, milk = (food(kitchen, n) for n in ("Toor dal", "Paneer", "Milk"))
    items = [add(kitchen, main, f["id"])["item"] for f in (dal, paneer, milk)]
    tick(kitchen, items[0]["id"])
    tick(kitchen, items[1]["id"])
    view = ok(kitchen.get(f"{API}/shopping/lists/{main}"))
    assert view["shopping_list"]["to_buy"] == 1 and view["shopping_list"]["ticked"] == 2
    cleared = ok(kitchen.post(f"{API}/shopping/lists/{main}/clear-ticked", json={}))
    assert sorted(cleared["cleared"]) == sorted([items[0]["id"], items[1]["id"]])
    assert cleared["change"]["summary"] == "Cleared 2 ticked items from This week"
    view = ok(kitchen.get(f"{API}/shopping/lists/{main}"))
    assert view["shopping_list"]["to_buy"] == 1 and view["shopping_list"]["ticked"] == 0
    nothing = ok(kitchen.post(f"{API}/shopping/lists/{main}/clear-ticked", json={}))
    assert nothing == {"cleared": [], "change": None}
    ok(kitchen.post(f"{API}/changes/{cleared['change']['id']}/undo"))
    view = ok(kitchen.get(f"{API}/shopping/lists/{main}"))
    assert view["shopping_list"]["to_buy"] == 1 and view["shopping_list"]["ticked"] == 2


def test_clear_ticked_only_the_listed_ones_and_only_if_still_ticked(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    dal, milk = food(kitchen, "Toor dal"), food(kitchen, "Milk")
    first, second = (add(kitchen, main, f["id"])["item"] for f in (dal, milk))
    tick(kitchen, first["id"])
    cleared = ok(
        kitchen.post(
            f"{API}/shopping/lists/{main}/clear-ticked",
            json={"item_ids": [first["id"], second["id"]]},
        )
    )
    assert cleared["cleared"] == [first["id"]]  # the unticked one stays


# --- Reading: by shop, then aisle ---------------------------------------------------------------


def test_grouped_by_shop_then_aisle(kitchen: TestClient) -> None:  # FE-1 on the server's side
    main = main_id(kitchen)
    supermarket = ok(kitchen.post(f"{API}/shops", json={"name": "Supermarket"}), 201)
    grocer = ok(kitchen.post(f"{API}/shops", json={"name": "Indian grocer"}), 201)
    milk = food(kitchen, "Milk", shop_id=supermarket["id"], aisle="dairy")
    carrots = food(kitchen, "Carrots", shop_id=supermarket["id"], aisle="veg_fruit")
    cumin = food(kitchen, "Cumin seeds", shop_id=grocer["id"])  # from the table: spices
    string = food(kitchen, "String", aisle="household")
    weird = food(kitchen, "Zzz")  # no aisle of its own: Other
    stuff = food(kitchen, "Aaa", shop_id=supermarket["id"])  # Other, same shop
    for f in (milk, carrots, cumin, string, weird, stuff):
        amount = None if f is weird else {"amount": 1, "unit": "g"}
        add(kitchen, main, f["id"], amount=amount)
    view = ok(kitchen.get(f"{API}/shopping/lists/{main}"))
    shops = [
        (g["name"], [(a["name"], [i["food"]["name"] for i in a["items"]]) for a in g["aisles"]])
        for g in view["shops"]
    ]
    assert shops == [
        (
            "Supermarket",
            [("Veg & fruit", ["Carrots"]), ("Dairy", ["Milk"]), ("Other", ["Aaa"])],
        ),
        ("Indian grocer", [("Spices", ["Cumin seeds"])]),
        ("Any shop", [("Household", ["String"]), ("Other", ["Zzz"])]),
    ]
    assert view["shops"][-1]["shop"] is None


def test_ticked_items_fold_into_the_trolley(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    shop = ok(kitchen.post(f"{API}/shops", json={"name": "Supermarket"}), 201)
    milk = food(kitchen, "Milk", shop_id=shop["id"])
    eggs = food(kitchen, "Eggs", shop_id=shop["id"])
    item = add(kitchen, main, milk["id"])["item"]
    add(kitchen, main, eggs["id"])
    tick(kitchen, item["id"])
    group = ok(kitchen.get(f"{API}/shopping/lists/{main}"))["shops"][0]
    assert [i["food"]["name"] for a in group["aisles"] for i in a["items"]] == ["Eggs"]
    assert [i["food"]["name"] for i in group["in_trolley"]] == ["Milk"]
    assert group["in_trolley"][0]["ticked_by"]["name"] == "Tess"


def test_a_shops_own_aisle_order(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    shop = ok(kitchen.post(f"{API}/shops", json={"name": "Supermarket"}), 201)
    milk = food(kitchen, "Milk", shop_id=shop["id"], aisle="dairy")
    carrots = food(kitchen, "Carrots", shop_id=shop["id"], aisle="veg_fruit")
    add(kitchen, main, milk["id"])
    add(kitchen, main, carrots["id"])
    with db(kitchen) as session:
        from mealwright.models import Shop

        session.get(Shop, shop["id"]).aisle_order = ["dairy"]
        session.commit()
    aisles = ok(kitchen.get(f"{API}/shopping/lists/{main}"))["shops"][0]["aisles"]
    assert [a["aisle"] for a in aisles] == ["dairy", "veg_fruit"]


def test_merged_away_ingredients_show_as_the_kept_one(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    arhar, toor = food(kitchen, "Arhar dal"), food(kitchen, "Toor dal")
    add(kitchen, main, arhar["id"])
    ok(kitchen.post(f"{API}/foods/{arhar['id']}/merge", json={"into_id": toor["id"]}))
    items = ok(kitchen.get(f"{API}/shopping/lists/{main}"))["shops"][0]["aisles"][0]["items"]
    assert [i["food"]["name"] for i in items] == ["Toor dal"]


# --- The counter, the sync log, retries --------------------------------------------------------


def test_every_write_takes_one_number_and_stamps_its_rows(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    start = counter(kitchen)
    item = add(kitchen, main, milk["id"])["item"]
    assert counter(kitchen) == start + 1 and item["version"] == start + 1
    ok(
        kitchen.patch(
            f"{API}/shopping/items/{item['id']}", json={"amount": {"amount": 5, "unit": "l"}}
        )
    )
    ok(kitchen.delete(f"{API}/shopping/items/{item['id']}"))
    ok(kitchen.post(f"{API}/shopping/lists", json={"name": "Party"}), 201)
    assert counter(kitchen) == start + 4
    with db(kitchen) as session:
        # Making the ingredient took a number too (a food_edit row, PR 3): only these four.
        query = select(SyncAction).where(SyncAction.seq > start).order_by(SyncAction.seq)
        rows = list(session.scalars(query))
        assert [r.seq for r in rows] == [start + 1, start + 2, start + 3, start + 4]
        assert [r.kind for r in rows] == ["add", "set_amount", "delete", "create_list"]
        assert all(r.status in ("applied", "merged") and r.device_id is None for r in rows)
        assert all(r.change_id is not None for r in rows)
        assert session.get(ListItem, item["id"]).version == start + 3  # last change to it


def test_refused_writes_and_no_ops_take_no_number(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    start = counter(kitchen)
    assert (
        kitchen.post(f"{API}/shopping/lists/{main}/items", json={"food_id": 999}).status_code == 404
    )
    assert kitchen.delete(f"{API}/shopping/lists/{main}").status_code == 409
    ok(kitchen.patch(f"{API}/shopping/lists/{main}", json={"name": "This week"}))
    add(kitchen, main, milk["id"], id="6f1c0000-0000-4000-8000-000000000002")
    assert (
        kitchen.post(
            f"{API}/shopping/lists/{main}/items",
            json={"food_id": milk["id"], "id": "6f1c0000-0000-4000-8000-000000000002"},
        ).status_code
        == 409
    )
    assert counter(kitchen) == start + 1


def test_undo_is_logged_and_marks_the_action_it_undid(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    added = add(kitchen, main, milk["id"])
    start = counter(kitchen)
    ok(kitchen.post(f"{API}/changes/{added['change']['id']}/undo"))
    assert counter(kitchen) == start + 1
    with db(kitchen) as session:
        undo = session.scalar(select(SyncAction).where(SyncAction.kind == "undo"))
        original = session.scalar(select(SyncAction).where(SyncAction.kind == "add"))
        assert undo.seq == start + 1 and original.undone_by_action_id == undo.id
        assert undo.payload == {"undoes": original.id}


def test_retry_with_the_same_key_changes_nothing(kitchen: TestClient) -> None:  # SY-19
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    headers = {"Idempotency-Key": "add-milk-1"}
    url = f"{API}/shopping/lists/{main}/items"
    first = kitchen.post(url, json={"food_id": milk["id"]}, headers=headers)
    assert first.status_code == 201
    start = counter(kitchen)
    again = kitchen.post(url, json={"food_id": milk["id"]}, headers=headers)
    assert again.status_code == 200 and again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["change"]["id"] == first.json()["change"]["id"]
    assert counter(kitchen) == start
    view = ok(kitchen.get(f"{API}/shopping/lists/{main}"))
    assert view["shopping_list"]["to_buy"] == 1
    with db(kitchen) as session:
        row = session.scalar(select(SyncAction).where(SyncAction.id == "add-milk-1"))
        assert row is not None and row.kind == "add"
        change = session.scalar(select(Change).where(Change.idempotency_key == "add-milk-1"))
        assert change is not None  # the first change carries the action ID (sync protocol 4.4)


def test_retries_of_other_writes(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    item = add(kitchen, main, milk["id"])["item"]
    for method, url, body, key in (
        ("POST", f"{API}/shopping/lists", {"name": "Party"}, "k-list"),
        ("PATCH", f"{API}/shopping/lists/{main}", {"name": "Our week"}, "k-rename"),
        (
            "PATCH",
            f"{API}/shopping/items/{item['id']}",
            {"amount": {"amount": 3, "unit": "l"}},
            "k-set",
        ),
        ("POST", f"{API}/shopping/lists/{main}/clear-ticked", {}, "k-clear-none"),
        ("DELETE", f"{API}/shopping/items/{item['id']}", None, "k-del"),
    ):
        first = kitchen.request(method, url, json=body, headers={"Idempotency-Key": key})
        assert first.status_code in (200, 201), first.text
        start = counter(kitchen)
        again = kitchen.request(method, url, json=body, headers={"Idempotency-Key": key})
        assert again.status_code in (200, 201), again.text
        assert counter(kitchen) == start
        if first.json().get("change"):
            assert again.json()["change"]["id"] == first.json()["change"]["id"]


def test_a_key_already_used_as_an_action_id_is_refused_by_the_0_2_api(
    kitchen: TestClient,
) -> None:  # SY-20 (the 0.2 side)
    with db(kitchen) as session:
        session.add(
            SyncAction(
                household_id=1,
                id="action-x",
                seq=1,
                kind="tick",
                login_name="Wren",
                payload={},
                payload_hash="0",
                status="applied",
                result={},
            )
        )
        session.commit()
    refused = kitchen.post(
        f"{API}/foods", json={"name": "Salt"}, headers={"Idempotency-Key": "action-x"}
    )
    assert refused.status_code == 409 and refused.json()["code"] == "key_reused"
    assert kitchen.get(f"{API}/foods").json()["total"] == 0


def test_a_key_used_for_something_else_is_refused(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    headers = {"Idempotency-Key": "same"}
    ok(kitchen.post(f"{API}/shopping/lists", json={"name": "A"}, headers=headers), 201)
    other = kitchen.post(
        f"{API}/shopping/lists/{main}/items", json={"food_id": milk["id"]}, headers=headers
    )
    assert other.status_code == 409 and other.json()["code"] == "key_reused"


# --- Ingredients and lists ---------------------------------------------------------------------


def test_an_ingredient_on_a_list_cannot_be_removed(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    item = add(kitchen, main, milk["id"])["item"]
    blocked = kitchen.delete(f"{API}/foods/{milk['id']}")
    assert blocked.status_code == 409 and blocked.json()["code"] == "in_use"
    assert "shopping list" in blocked.json()["detail"]
    # A tombstone doesn't block.
    ok(kitchen.delete(f"{API}/shopping/items/{item['id']}"))
    ok(kitchen.delete(f"{API}/foods/{milk['id']}"))


def test_an_ingredient_on_a_removed_list_is_blocked_until_the_undo_window_ends(
    kitchen: TestClient,
) -> None:
    party = ok(kitchen.post(f"{API}/shopping/lists", json={"name": "Party"}), 201)["shopping_list"]
    crisps = food(kitchen, "Crisps")
    add(kitchen, party["id"], crisps["id"])
    ok(kitchen.delete(f"{API}/shopping/lists/{party['id']}"))
    assert (
        kitchen.delete(f"{API}/foods/{crisps['id']}").status_code == 409
    )  # Undo could bring it back
    with db(kitchen) as session:
        session.execute(update(ShoppingList).values(removed_at=utcnow() - timedelta(days=8)))
        session.commit()
    ok(kitchen.delete(f"{API}/foods/{crisps['id']}"))


def test_an_ingredient_that_is_deleted_for_good_takes_its_list_rows_with_it(
    kitchen: TestClient,
) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    item = add(kitchen, main, milk["id"])["item"]
    ok(kitchen.delete(f"{API}/shopping/items/{item['id']}"))
    ok(kitchen.delete(f"{API}/foods/{milk['id']}"))
    with db(kitchen) as session:
        session.execute(update(Food).values(removed_at=utcnow() - timedelta(days=9)))
        session.add(ListTick(household_id=1, id="t1", item_id=item["id"], login_name="Tess"))
        session.commit()
    jobs.purge_removed_ingredients(kitchen.app.state.sessionmaker)  # type: ignore[attr-defined]
    with db(kitchen) as session:
        assert session.scalar(select(func.count()).select_from(Food)) == 0
        assert session.scalar(select(func.count()).select_from(ListItem)) == 0
        assert session.scalar(select(func.count()).select_from(ListTick)) == 0
        assert session.scalar(select(func.count()).select_from(ShoppingList)) == 1


# --- Aisles ------------------------------------------------------------------------------------


def test_new_ingredients_start_in_the_tables_aisle_or_other(kitchen: TestClient) -> None:
    assert food(kitchen, "Cumin seeds")["aisle"] == "spices"
    assert food(kitchen, "Eggs")["aisle"] == "dairy"
    assert food(kitchen, "Frozen peas")["aisle"] == "frozen"
    toor = food(kitchen, "Toor dal")
    assert toor["aisle"] == "other" and toor["aisle_name"] == "Other"
    assert food(kitchen, "Spuds", aisle="veg_fruit")["aisle_name"] == "Veg & fruit"


def test_every_bundled_food_has_an_aisle() -> None:
    from mealwright.aisles import AISLE_KEYS
    from mealwright.conversions import table

    rows = table().rows.values()
    assert rows and all(row.aisle in AISLE_KEYS for row in rows)


def test_aisle_is_editable_and_undoable(kitchen: TestClient) -> None:
    toor = food(kitchen, "Toor dal")
    changed = ok(kitchen.patch(f"{API}/foods/{toor['id']}", json={"aisle": "dry_goods"}))
    assert changed["food"]["aisle"] == "dry_goods"
    assert changed["change"]["summary"] == "Toor dal is now in Dry goods"
    same = ok(kitchen.patch(f"{API}/foods/{toor['id']}", json={"aisle": "dry_goods"}))
    assert same["change"] is None
    assert kitchen.patch(f"{API}/foods/{toor['id']}", json={"aisle": "sweets"}).status_code == 422
    assert kitchen.patch(f"{API}/foods/{toor['id']}", json={"aisle": None}).status_code == 422
    ok(kitchen.post(f"{API}/changes/{changed['change']['id']}/undo"))
    assert ok(kitchen.get(f"{API}/foods/{toor['id']}"))["aisle"] == "other"


def test_the_list_shows_the_new_aisle(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    toor = food(kitchen, "Toor dal")
    add(kitchen, main, toor["id"])
    ok(kitchen.patch(f"{API}/foods/{toor['id']}", json={"aisle": "dry_goods"}))
    aisle = ok(kitchen.get(f"{API}/shopping/lists/{main}"))["shops"][0]["aisles"][0]
    assert aisle["name"] == "Dry goods"


def test_openapi_lists_the_shopping_endpoints(kitchen: TestClient) -> None:
    paths = kitchen.get(f"{API}/openapi.json").json()["paths"]
    assert {"/api/v1/shopping/lists", "/api/v1/shopping/lists/{list_id}/items"} <= set(paths)


# --- Merging, versions and Undo edge cases ------------------------------------------------------


def food_version(kitchen: TestClient, food_id: int) -> int:
    with db(kitchen) as session:
        return int(session.get(Food, food_id).version)


def test_merging_moves_the_list_items_and_keeps_the_kept_one_on_its_list(
    kitchen: TestClient,
) -> None:  # sync protocol 5.8
    main = main_id(kitchen)
    arhar, toor = food(kitchen, "Arhar dal"), food(kitchen, "Toor dal")
    on_a = add(kitchen, main, arhar["id"])["item"]
    on_b = add(kitchen, main, toor["id"])["item"]
    start = counter(kitchen)
    merged = ok(kitchen.post(f"{API}/foods/{arhar['id']}/merge", json={"into_id": toor["id"]}))
    with db(kitchen) as session:
        moved = session.get(ListItem, on_a["id"])
        assert moved.food_id == toor["id"] and moved.version > start
        assert session.get(ListItem, on_b["id"]).food_id == toor["id"]  # still two lines
    blocked = kitchen.delete(f"{API}/foods/{toor['id']}")
    assert blocked.status_code == 409 and "shopping list" in blocked.json()["detail"]
    assert ok(kitchen.get(f"{API}/shopping/lists/{main}"))["shopping_list"]["to_buy"] == 2
    ok(kitchen.post(f"{API}/changes/{merged['change']['id']}/undo"))
    with db(kitchen) as session:
        assert session.get(ListItem, on_a["id"]).food_id == arhar["id"]
        assert session.get(ListItem, on_b["id"]).food_id == toor["id"]


def test_the_safety_nets_follow_merge_chains(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    arhar, toor = food(kitchen, "Arhar dal"), food(kitchen, "Toor dal")
    add(kitchen, main, arhar["id"])
    ok(kitchen.post(f"{API}/foods/{arhar['id']}/merge", json={"into_id": toor["id"]}))
    with db(kitchen) as session:  # a stray item left on the merged-away ingredient
        session.execute(update(ListItem).values(food_id=arhar["id"]))
        session.commit()
    assert kitchen.delete(f"{API}/foods/{toor['id']}").status_code == 409
    with db(kitchen) as session:  # removed anyway: the tidy-up must not delete a live item
        session.execute(
            update(Food)
            .where(Food.id == toor["id"])
            .values(removed_at=utcnow() - timedelta(days=9))
        )
        session.commit()
    jobs.purge_removed_ingredients(kitchen.app.state.sessionmaker)  # type: ignore[attr-defined]
    with db(kitchen) as session:
        assert session.scalar(select(func.count()).select_from(ListItem)) == 1
        assert session.get(Food, toor["id"]).removed_at is None


def test_ingredient_edits_bump_the_food_version(kitchen: TestClient) -> None:  # sync protocol 3.7
    milk = food(kitchen, "Milk")
    other = food(kitchen, "Oat milk")
    path = f"{API}/foods/{milk['id']}"
    seen = food_version(kitchen, milk["id"])
    for body in ({"name": "Whole milk"}, {"aisle": "frozen"}, {"staple": True}):
        before = counter(kitchen)
        ok(kitchen.patch(path, json=body))
        assert food_version(kitchen, milk["id"]) == before + 1 > seen
        seen = before + 1
    before = counter(kitchen)
    merged = ok(kitchen.post(f"{API}/foods/{other['id']}/merge", json={"into_id": milk["id"]}))
    assert food_version(kitchen, milk["id"]) == before + 1
    assert food_version(kitchen, other["id"]) == before + 1
    ok(kitchen.post(f"{API}/changes/{merged['change']['id']}/undo"))
    assert food_version(kitchen, other["id"]) > before + 1
    removed = counter(kitchen)
    ok(kitchen.delete(f"{API}/foods/{other['id']}"))
    assert food_version(kitchen, other["id"]) == removed + 1


def test_an_edit_that_changes_nothing_takes_no_number(kitchen: TestClient) -> None:
    milk = food(kitchen, "Milk")
    before = counter(kitchen)
    ok(kitchen.patch(f"{API}/foods/{milk['id']}", json={"name": "Milk"}))
    assert counter(kitchen) == before


def test_undo_of_a_delete_stays_off_when_the_ingredient_was_removed(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    item = add(kitchen, main, milk["id"])["item"]
    deleted = ok(kitchen.delete(f"{API}/shopping/items/{item['id']}"))
    ok(kitchen.delete(f"{API}/foods/{milk['id']}"))
    undone = ok(kitchen.post(f"{API}/changes/{deleted['change']['id']}/undo"))
    assert undone["result"] == "nothing"
    lists = ok(kitchen.get(f"{API}/shopping/lists"))["lists"]
    assert lists[0]["to_buy"] == 0
    with db(kitchen) as session:
        assert session.get(ListItem, item["id"]).deleted_at is not None


def test_counts_only_count_what_the_list_shows(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    add(kitchen, main, milk["id"])
    with db(kitchen) as session:  # a live item on a removed ingredient
        session.execute(update(Food).values(removed_at=utcnow()))
        session.commit()
    assert ok(kitchen.get(f"{API}/shopping/lists"))["lists"][0]["to_buy"] == 0


def test_undo_an_add_leaves_an_item_that_has_changed_since(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    added = add(kitchen, main, milk["id"], amount={"amount": 1, "unit": "l"})
    ok(
        kitchen.patch(
            f"{API}/shopping/items/{added['item']['id']}",
            json={"amount": {"amount": 3, "unit": "l"}},
        )
    )
    undone = ok(kitchen.post(f"{API}/changes/{added['change']['id']}/undo"))
    assert undone["result"] == "nothing"
    with db(kitchen) as session:
        assert session.get(ListItem, added["item"]["id"]).deleted_at is None
    ticked = add(kitchen, main, food(kitchen, "Eggs")["id"])
    tick(kitchen, ticked["item"]["id"])
    undone = ok(kitchen.post(f"{API}/changes/{ticked['change']['id']}/undo"))
    assert undone["result"] == "nothing"
    with db(kitchen) as session:
        assert session.get(ListItem, ticked["item"]["id"]).deleted_at is None
