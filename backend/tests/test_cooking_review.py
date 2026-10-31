"""K2 after the Opus review (round 1): Undo and the list line it joined, one rule for "add to
list", running low, a whole meal in one confirm, Undo when something newer touched the packets,
a typed amount with an ask-once answer, the counter, and the Pantry's own order."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_cooking import FAR, _listed, amounts, cook, dal_curry, far_curry
from test_deduction import DAY, plan_item, propose, recipe_of, row_of
from test_plan import db_of
from test_recipe_list import line, place_id, stock
from test_recipes import food, make

from mealwright.models import Household, ListItem, StockLot
from mealwright.shopping import Batch
from mealwright.stock import ordered

API = "/api/v1"


def list_lines(client: TestClient, food_id: int) -> list[ListItem]:
    with db_of(client) as db:
        found = list(db.scalars(select(ListItem).where(ListItem.food_id == food_id)))
        db.expunge_all()
        return [i for i in found if i.deleted_at is None]


def undo(client: TestClient, done: dict[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = ok(client.post(f"{API}/changes/{done['change']['id']}/undo"))
    return result


# --- 1. Undo and the line it joined ----


def test_undo_gives_the_joined_plan_line_back_exactly(kitchen: TestClient) -> None:
    dal, item = dal_curry(kitchen, in_stock=60)  # the plan itself lists 40 g
    [before] = list_lines(kitchen, dal["id"])
    assert (before.amount_milli, before.source, before.hand_edited) == (40_000, "plan", False)
    typed = [{"key": f"food:{dal['id']}", "used": {"amount": 150, "unit": "g"}}]
    done = ok(cook(kitchen, item, typed), 201)  # 60 g there: 90 g short, more than the line has
    [joined] = list_lines(kitchen, dal["id"])
    assert (joined.amount_milli, joined.hand_edited) == (90_000, True)
    assert undo(kitchen, done)["result"] == "done"
    [after] = list_lines(kitchen, dal["id"])
    assert (after.amount_milli, after.source, after.hand_edited) == (40_000, "plan", False)


def test_undo_leaves_a_line_the_person_changed_since_and_says_partly(kitchen: TestClient) -> None:
    dal, item = dal_curry(kitchen, in_stock=60)
    typed = [{"key": f"food:{dal['id']}", "used": {"amount": 150, "unit": "g"}}]
    done = ok(cook(kitchen, item, typed), 201)
    with db_of(kitchen) as db:
        line_ = db.scalars(select(ListItem).where(ListItem.food_id == dal["id"])).one()
        line_.amount_milli, line_.version = 500_000, line_.version + 1  # edited on Shopping
        db.commit()
    result = undo(kitchen, done)
    assert result["result"] == "partly"
    [kept] = list_lines(kitchen, dal["id"])
    assert kept.amount_milli == 500_000


# --- 2. One rule for add to list ----


def two_far(client: TestClient) -> tuple[dict[str, Any], int, int]:
    dal = food(client, "Zorba dal")
    recipe = recipe_of(client, [line(dal["id"], 200, "g")])
    a = plan_item(client, recipe, servings=2, day=FAR)
    b = plan_item(client, recipe, servings=2, day=FAR + timedelta(days=1))
    return dal, a, b


def test_a_row_with_nothing_in_the_house_is_added_whatever_the_use_switch_says(
    kitchen: TestClient,
) -> None:
    dal, a, b = two_far(kitchen)
    row = row_of(propose(kitchen, a), "Zorba dal")
    assert (row["use"], row["add_to_list"], row["list_amount"]["amount"]) == (False, True, 100)
    ok(cook(kitchen, a, [{"key": f"food:{dal['id']}", "use": False}]), 201)  # as the screen echoes
    assert _listed(kitchen, dal["id"]) == [100_000]
    ok(cook(kitchen, b), 201)  # a row left out gets what the proposal said
    assert _listed(kitchen, dal["id"]) == [100_000]  # the open line already covers the second


def test_the_tick_is_its_own_choice(kitchen: TestClient) -> None:
    dal, a, b = two_far(kitchen)
    ok(cook(kitchen, a, [{"key": f"food:{dal['id']}", "add_to_list": False}]), 201)
    assert _listed(kitchen, dal["id"]) == []
    ok(cook(kitchen, b, [{"key": f"food:{dal['id']}", "use": False, "add_to_list": True}]), 201)
    assert _listed(kitchen, dal["id"]) == [100_000]


def test_stock_only_in_the_freezer_is_not_added_unless_ticked(kitchen: TestClient) -> None:
    peas = food(kitchen, "Zorba peas")
    stock(kitchen, peas["id"], 300, "g", place_id=place_id(kitchen, "Freezer"))
    recipe = recipe_of(kitchen, [line(peas["id"], 200, "g")])
    a = plan_item(kitchen, recipe, servings=2, day=FAR)
    b = plan_item(kitchen, recipe, servings=2, day=FAR + timedelta(days=1))
    row = row_of(propose(kitchen, a), "Zorba peas")
    assert (row["use"], row["add_to_list"], row["in_freezer"]["amount"]) == (False, False, 300)
    ok(cook(kitchen, a), 201)
    assert _listed(kitchen, peas["id"]) == []
    ok(cook(kitchen, b, [{"key": f"food:{peas['id']}", "use": False, "add_to_list": True}]), 201)
    assert _listed(kitchen, peas["id"]) == [100_000]


# --- 3. Running low ----


def low_curry(kitchen: TestClient, in_stock: int, level: int = 300) -> tuple[dict[str, Any], int]:
    dal = food(kitchen, "Zorba dal")
    stock(kitchen, dal["id"], in_stock, "g")
    ok(
        kitchen.patch(
            f"{API}/foods/{dal['id']}", json={"running_low_at": {"amount": level, "unit": "g"}}
        )
    )
    recipe = recipe_of(kitchen, [line(dal["id"], 200, "g")])
    return dal, plan_item(kitchen, recipe, servings=2, day=FAR)


def test_what_is_left_at_or_below_the_running_low_level_offers_the_list_unticked(
    kitchen: TestClient,
) -> None:
    dal, item = low_curry(kitchen, 350)  # 250 g left after 100 g: at or below 300 g
    row = row_of(propose(kitchen, item), "Zorba dal")
    assert row["running_low"] is True and row["short"] is None
    assert (row["add_to_list"], row["list_amount"]["amount"]) == (False, 300)
    ok(cook(kitchen, item), 201)
    assert _listed(kitchen, dal["id"]) == []  # not ticked, so not added
    other = plan_item(
        kitchen,
        recipe_of(kitchen, [line(dal["id"], 40, "g")]),
        servings=2,
        day=FAR + timedelta(days=1),
    )
    ok(cook(kitchen, other, [{"key": f"food:{dal['id']}", "add_to_list": True}]), 201)
    assert _listed(kitchen, dal["id"]) == [300_000]


def test_enough_left_is_not_running_low_and_a_small_pack_is_what_is_offered(
    kitchen: TestClient,
) -> None:
    dal, item = low_curry(kitchen, 500)
    assert row_of(propose(kitchen, item), "Zorba dal")["running_low"] is False
    ok(kitchen.post(f"{API}/foods/{dal['id']}/sizes", json={"name": "pack", "amount": 250}), 201)
    ok(kitchen.post(f"{API}/foods/{dal['id']}/sizes", json={"name": "sack", "amount": 1000}), 201)
    stock(kitchen, dal["id"], 1, "g")  # 501 g: still more than 400 g after the cook
    item2 = plan_item(
        kitchen,
        recipe_of(kitchen, [line(dal["id"], 300, "g")]),
        servings=2,
        day=FAR + timedelta(days=1),
    )
    row = row_of(propose(kitchen, item2), "Zorba dal")  # 150 g taken: 351 g left, above 300
    assert row["running_low"] is False
    item3 = plan_item(
        kitchen,
        recipe_of(kitchen, [line(dal["id"], 600, "g")]),
        servings=2,
        day=FAR + timedelta(days=2),
    )
    row = row_of(propose(kitchen, item3), "Zorba dal")  # 300 g taken: 201 g left
    assert row["running_low"] is True and row["list_amount"]["amount"] == 250  # the smallest size


# --- 4a. A whole meal ----


def a_meal(kitchen: TestClient, in_stock: int) -> tuple[dict[str, Any], int, list[int]]:
    dal = food(kitchen, "Zorba dal")
    if in_stock:
        stock(kitchen, dal["id"], in_stock, "g")
    first = make(kitchen, "Zorba sambar", serves=4, lines=[line(dal["id"], 200, "g")])
    second = make(kitchen, "Zorba rasam", serves=4, lines=[line(dal["id"], 200, "g")])
    from test_plan import slot_ids

    slot = slot_ids(kitchen)["Dinner"]
    items = []
    meal = 0
    for recipe in (first, second):
        planned = ok(
            kitchen.post(
                f"{API}/plan/items",
                json={
                    "date": FAR.isoformat(),
                    "slot_id": slot,
                    "recipe_id": recipe["id"],
                    "servings": 4,
                },
            ),
            201,
        )
        items.append(planned["item_id"])
        meal = planned["meal_id"]
    return dal, meal, items


def test_two_recipes_of_a_meal_never_propose_the_same_grams(kitchen: TestClient) -> None:
    _, meal, items = a_meal(kitchen, 300)  # each needs 200 g
    shown = ok(kitchen.post(f"{API}/plan/meals/{meal}/cook/preview", json={}))
    takes = [row_of(i["proposal"], "Zorba dal") for i in shown["items"]]
    assert [i["item_id"] for i in shown["items"]] == items
    assert [r["takes"][0]["amount"]["amount"] for r in takes] == [200, 100]
    assert takes[1]["short"]["amount"] == 100 and takes[1]["takes"][0]["before"]["amount"] == 100


def test_a_meal_is_one_confirm_one_change_and_one_undo(kitchen: TestClient) -> None:
    dal, meal, items = a_meal(kitchen, 300)
    done = ok(kitchen.post(f"{API}/plan/meals/{meal}/cook", json={}), 201)
    assert amounts(kitchen, dal["id"]) == [0]
    assert done["change"]["summary"] == "Cooked Zorba sambar and Zorba rasam"
    assert sorted(c["meal_item_id"] for c in done["cooked"]) == sorted(items)
    assert _listed(kitchen, dal["id"]) == [100_000]  # the two shortfalls, once
    for item in items:
        assert kitchen.get(f"{API}/plan/items/{item}/cooked").status_code == 200
        assert cook(kitchen, item).status_code == 409
    assert undo(kitchen, done)["result"] == "done"
    assert amounts(kitchen, dal["id"]) == [300_000] and _listed(kitchen, dal["id"]) == []
    for item in items:
        assert kitchen.get(f"{API}/plan/items/{item}/cooked").status_code == 404


def test_a_meal_is_all_or_nothing(kitchen: TestClient) -> None:
    dal, meal, items = a_meal(kitchen, 300)
    toor = food(kitchen, "Zorba toor")
    stock(kitchen, toor["id"], 500, "g")
    odd = make(kitchen, "Zorba odd", serves=4, lines=[line(toor["id"], 1, "cup")])
    from test_plan import slot_ids

    ok(
        kitchen.post(
            f"{API}/plan/items",
            json={
                "date": FAR.isoformat(),
                "slot_id": slot_ids(kitchen)["Dinner"],
                "recipe_id": odd["id"],
            },
        ),
        201,
    )
    refused = kitchen.post(f"{API}/plan/meals/{meal}/cook", json={})
    assert refused.status_code == 409 and refused.json()["code"] == "ask_once"
    assert amounts(kitchen, dal["id"]) == [300_000] and amounts(kitchen, toor["id"]) == [500_000]
    only = kitchen.post(f"{API}/plan/meals/{meal}/cook", json={"items": [{"item_id": items[0]}]})
    assert only.status_code == 201 and len(only.json()["cooked"]) == 1
    nothing = kitchen.post(f"{API}/plan/meals/{meal}/cook", json={"items": [{"item_id": 99999}]})
    assert nothing.status_code == 404


def test_a_meal_with_a_batch_is_refused_and_a_retry_takes_once(kitchen: TestClient) -> None:
    dal, meal, items = a_meal(kitchen, 900)
    ok(
        kitchen.post(
            f"{API}/plan/items/{items[0]}/batch", json={"tub_count": 2, "pattern": "pick"}
        ),
        201,
    )
    refused = kitchen.post(f"{API}/plan/meals/{meal}/cook", json={})
    assert refused.status_code == 409 and refused.json()["code"] == "cook_the_batch"
    assert amounts(kitchen, dal["id"]) == [900_000]
    headers = {"Idempotency-Key": "meal-1"}
    url = f"{API}/plan/meals/{meal}/cook"
    body = {"items": [{"item_id": items[1]}]}
    one = kitchen.post(url, json=body, headers=headers)
    two = kitchen.post(url, json=body, headers=headers)
    assert (one.status_code, two.status_code) == (201, 200)
    assert amounts(kitchen, dal["id"]) == [700_000]


# --- 4b. Undo after something newer changed the packets: the stock Undo's own rule ----


def used_by_hand(client: TestClient, food_id: int, grams: int) -> None:
    ok(client.post(f"{API}/foods/{food_id}/used", json={"amount": {"amount": grams, "unit": "g"}}))


def test_undo_puts_back_what_was_taken_even_after_a_newer_use(kitchen: TestClient) -> None:
    dal, item = dal_curry(kitchen, in_stock=200)
    done = ok(cook(kitchen, item), 201)  # 100 g taken: 100 g left
    used_by_hand(kitchen, dal["id"], 40)  # a real Used change: 60 g left
    result = undo(kitchen, done)
    assert result["result"] == "done"  # later changes stay; this one is reversed
    assert amounts(kitchen, dal["id"]) == [160_000]
    assert kitchen.get(f"{API}/plan/items/{item}/cooked").status_code == 404


def test_undo_says_partly_when_a_packet_it_took_from_is_gone(kitchen: TestClient) -> None:
    """The stock Undo's own words: a packet the tidy-up has deleted can't be given back."""
    dal = food(kitchen, "Zorba dal")
    stock(kitchen, dal["id"], 100, "g", use_by=(DAY + timedelta(days=1)).isoformat())
    stock(kitchen, dal["id"], 500, "g")
    item = plan_item(kitchen, recipe_of(kitchen, [line(dal["id"], 400, "g")]), servings=4)
    done = ok(cook(kitchen, item), 201)  # empties the first packet, 300 g from the second
    with db_of(kitchen) as db:
        first = db.scalars(select(StockLot).where(StockLot.food_id == dal["id"])).all()[0]
        db.delete(first)
        db.commit()
    result = undo(kitchen, done)
    assert result["result"] == "partly"
    assert result["message"] == "Put back what could be: some of it has changed again since."
    assert amounts(kitchen, dal["id"]) == [500_000]
    assert kitchen.get(f"{API}/plan/items/{item}/cooked").status_code == 404


# --- 5. A typed amount with an ask-once answer ----


def test_a_typed_cup_is_worked_out_with_the_answer_sent_beside_it(kitchen: TestClient) -> None:
    toor = food(kitchen, "Zorba toor")
    stock(kitchen, toor["id"], 1000, "g")
    item = plan_item(kitchen, recipe_of(kitchen, [line(toor["id"], 200, "g")]), servings=4)
    answer = {"kind": "weight_per_ml", "food_id": toor["id"], "grams": 200, "remember": False}
    typed = [{"key": f"food:{toor['id']}", "used": {"amount": 1, "unit": "cup"}}]
    ok(cook(kitchen, item, typed, answers=[answer]), 201)
    assert amounts(kitchen, toor["id"]) == [800_000]


# --- 6. The counter ----


def test_undo_with_a_ticked_line_takes_no_counter_number(kitchen: TestClient) -> None:
    dal, item = far_curry(kitchen, 60)
    done = ok(cook(kitchen, item), 201)
    with db_of(kitchen) as db:
        listed = db.scalars(select(ListItem).where(ListItem.food_id == dal["id"])).one()
        from mealwright.models import utcnow

        listed.ticked_at = utcnow()
        db.commit()
        before = db.get(Household, 1).list_seq  # type: ignore[union-attr]
    assert undo(kitchen, done)["result"] == "partly"  # the stock came back; the ticked line stays
    with db_of(kitchen) as db:
        assert db.get(Household, 1).list_seq == before  # type: ignore[union-attr]


def test_a_confirm_that_adds_nothing_takes_no_counter_number(kitchen: TestClient) -> None:
    _, item = dal_curry(kitchen, in_stock=60)  # the plan's own line already covers the 40 g
    with db_of(kitchen) as db:
        before = db.get(Household, 1).list_seq  # type: ignore[union-attr]
    ok(cook(kitchen, item), 201)
    with db_of(kitchen) as db:
        assert db.get(Household, 1).list_seq == before  # type: ignore[union-attr]
    assert Batch  # imported for the counter's own tests


# --- 7. The Pantry's own order ----


def test_the_pantry_takes_the_opened_packet_first_among_equal_use_by_dates(
    kitchen: TestClient,
) -> None:
    """ "Opened" in code: the packet was bought as a size (`size_id`) and now holds less than that
    size. A packet that holds more than its size (a 1½ packet bought as 1½ x 500 g in one lot)
    is not opened; with no size, nothing is."""
    rice = food(kitchen, "Zorba rice")
    size = ok(
        kitchen.post(f"{API}/foods/{rice['id']}/sizes", json={"name": "bag", "amount": 500}), 201
    )
    bag = next(s for s in size["food"]["sizes"] if s["name"] == "bag")
    day = DAY.isoformat()
    for _ in range(2):
        body = {"food_id": rice["id"], "amount": {"amount": 1, "size_id": bag["id"]}, "use_by": day}
        ok(kitchen.post(f"{API}/stock", json=body), 201)
    with db_of(kitchen) as db:
        lots = list(
            db.scalars(select(StockLot).where(StockLot.food_id == rice["id"]).order_by(StockLot.id))
        )
        lots[1].amount_milli = 300_000
        opened = lots[1].id
        db.commit()
    ok(
        kitchen.post(
            f"{API}/foods/{rice['id']}/used", json={"amount": {"amount": 100, "unit": "g"}}
        )
    )
    with db_of(kitchen) as db:
        assert db.get(StockLot, opened).amount_milli == 200_000  # type: ignore[union-attr]
        from mealwright.api.v1.context import Kitchen
        from mealwright.models import Login

        k = Kitchen(db, db.scalars(select(Login)).first(), db.get(Household, 1), None, "T")  # type: ignore[arg-type]
        first = ordered(k, db.scalars(select(StockLot).where(StockLot.food_id == rice["id"])))[0]
        assert first.id == opened


# --- Every path: the batch and the meal share the item's rules ----


def a_batch(
    client: TestClient, in_stock: int, level: int | None = None
) -> tuple[dict[str, Any], int]:
    dal = food(client, "Zorba dal")
    if in_stock:
        stock(client, dal["id"], in_stock, "g")
    if level:
        patch = {"running_low_at": {"amount": level, "unit": "g"}}
        ok(client.patch(f"{API}/foods/{dal['id']}", json=patch))
    item = plan_item(client, recipe_of(client, [line(dal["id"], 200, "g")]), day=FAR)
    body = {"tub_count": 3, "pattern": "pick"}
    made = ok(client.post(f"{API}/plan/items/{item}/batch", json=body), 201)
    return dal, made["batch_id"]


def test_a_batch_adds_a_missing_ingredient_whatever_use_says(kitchen: TestClient) -> None:
    dal, batch = a_batch(kitchen, 0)  # 4 portions of a recipe for 4: 200 g
    shown = ok(kitchen.post(f"{API}/plan/batches/{batch}/cook/preview", json={}))
    row = row_of(shown, "Zorba dal")
    assert (row["use"], row["add_to_list"], row["list_amount"]["amount"]) == (False, True, 200)
    echo = {"choices": [{"key": f"food:{dal['id']}", "use": False}]}
    ok(kitchen.post(f"{API}/plan/batches/{batch}/cook", json=echo), 201)
    assert _listed(kitchen, dal["id"]) == [200_000]


def test_a_batch_says_running_low_unticked_and_takes_a_typed_cup_with_its_answer(
    kitchen: TestClient,
) -> None:
    dal, batch = a_batch(kitchen, 300, level=150)  # 100 g left after the 200 g
    row = row_of(ok(kitchen.post(f"{API}/plan/batches/{batch}/cook/preview", json={})), "Zorba dal")
    assert (row["running_low"], row["add_to_list"], row["list_amount"]["amount"]) == (
        True,
        False,
        150,
    )
    answer = {"kind": "weight_per_ml", "food_id": dal["id"], "grams": 100, "remember": False}
    typed = {"choices": [{"key": f"food:{dal['id']}", "used": {"amount": 1, "unit": "cup"}}]}
    ok(kitchen.post(f"{API}/plan/batches/{batch}/cook", json={**typed, "answers": [answer]}), 201)
    assert amounts(kitchen, dal["id"]) == [200_000]  # a cup of 100 g a cup... 250 ml x 0.1 g: 100 g
    assert _listed(kitchen, dal["id"]) == []


def test_a_meal_adds_whatever_use_says_and_marks_running_low_and_takes_a_typed_cup(
    kitchen: TestClient,
) -> None:
    dal, meal, items = a_meal(kitchen, 0)  # nothing in the house
    shown = ok(kitchen.post(f"{API}/plan/meals/{meal}/cook/preview", json={}))
    rows = [row_of(i["proposal"], "Zorba dal") for i in shown["items"]]
    assert [(r["use"], r["add_to_list"]) for r in rows] == [(False, True), (False, True)]
    echo = {
        "items": [
            {"item_id": i, "choices": [{"key": f"food:{dal['id']}", "use": False}]} for i in items
        ]
    }
    ok(kitchen.post(f"{API}/plan/meals/{meal}/cook", json=echo), 201)
    assert _listed(kitchen, dal["id"]) == [400_000]  # both recipes' 200 g, on one line

    toor = food(kitchen, "Zorba toor")
    stock(kitchen, toor["id"], 500, "g")
    ok(
        kitchen.patch(
            f"{API}/foods/{toor['id']}", json={"running_low_at": {"amount": 450, "unit": "g"}}
        )
    )
    other = make(kitchen, "Zorba other", serves=4, lines=[line(toor["id"], 100, "g")])
    from test_plan import slot_ids

    planned = ok(
        kitchen.post(
            f"{API}/plan/items",
            json={
                "date": (FAR + timedelta(days=3)).isoformat(),
                "slot_id": slot_ids(kitchen)["Dinner"],
                "recipe_id": other["id"],
                "servings": 4,
            },
        ),
        201,
    )
    low = ok(kitchen.post(f"{API}/plan/meals/{planned['meal_id']}/cook/preview", json={}))
    row = row_of(low["items"][0]["proposal"], "Zorba toor")
    assert (row["running_low"], row["add_to_list"]) == (True, False)
    answer = {"kind": "weight_per_ml", "food_id": toor["id"], "grams": 200, "remember": False}
    typed = {
        "items": [
            {
                "item_id": planned["item_id"],
                "choices": [{"key": f"food:{toor['id']}", "used": {"amount": 1, "unit": "cup"}}],
            }
        ],
        "answers": [answer],
    }
    ok(kitchen.post(f"{API}/plan/meals/{planned['meal_id']}/cook", json=typed), 201)
    assert amounts(kitchen, toor["id"]) == [300_000]


def test_undoing_an_eaten_tub_after_a_newer_eat_gives_back_what_it_ate(kitchen: TestClient) -> None:
    from test_tub_eating import eat, quarters, tubs_of_a_batch

    _, tubs = tubs_of_a_batch(kitchen)
    first = ok(eat(kitchen, tubs[0], quarters=1))
    ok(eat(kitchen, tubs[0], quarters=1))
    undone = ok(kitchen.post(f"{API}/changes/{first['change']['id']}/undo"))
    assert undone["result"] == "done" and quarters(kitchen, tubs[0]) == 3


def test_another_households_meal_and_item_are_not_found(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    _, meal, items = a_meal(kitchen, 300)
    assert neighbour.post(f"{API}/plan/meals/{meal}/cook/preview", json={}).status_code == 404
    assert neighbour.post(f"{API}/plan/meals/{meal}/cook", json={}).status_code == 404
    theirs = neighbour.post(
        f"{API}/plan/meals/{meal}/cook", json={"items": [{"item_id": items[0]}]}
    )
    assert theirs.status_code == 404


# --- A ticked "add to list" is kept when Use is off, on every path ----------------


def one_recipe(
    client: TestClient, path: str, name: str, stocked: int, freezer: bool
) -> tuple[int, Any]:
    """Zorba dal needing 200 g on the item, batch (4 portions) or meal path; returns the food id
    and a function that confirms it with these choices."""
    from test_plan import slot_ids

    dal = food(client, name)
    if stocked:
        where = {"place_id": place_id(client, "Freezer")} if freezer else {}
        stock(client, dal["id"], stocked, "g", **where)
    recipe = recipe_of(client, [line(dal["id"], 200, "g")])
    planned = ok(
        client.post(
            f"{API}/plan/items",
            json={
                "date": FAR.isoformat(),
                "slot_id": slot_ids(client)["Dinner"],
                "recipe_id": recipe["id"],
            },
        ),
        201,
    )
    item, meal = planned["item_id"], planned["meal_id"]
    key = f"food:{dal['id']}"
    if path == "batch":
        batch = ok(
            client.post(f"{API}/plan/items/{item}/batch", json={"tub_count": 3, "pattern": "pick"}),
            201,
        )["batch_id"]

    def confirm(**choice: Any) -> Any:
        body = {"choices": [{"key": key, **choice}]}
        if path == "item":
            return client.post(f"{API}/plan/items/{item}/cook", json=body)
        if path == "batch":
            return client.post(f"{API}/plan/batches/{batch}/cook", json=body)
        return client.post(
            f"{API}/plan/meals/{meal}/cook", json={"items": [{"item_id": item, **body}]}
        )

    return dal["id"], confirm


@pytest.mark.parametrize("path", ["item", "batch", "meal"])
@pytest.mark.parametrize(
    ("stocked", "freezer", "listed"),
    [(0, False, 200_000), (100, False, 100_000), (300, True, 200_000)],
    ids=["none in the house", "short", "freezer only"],
)
def test_a_ticked_add_to_list_is_kept_when_use_is_off(
    kitchen: TestClient, path: str, stocked: int, freezer: bool, listed: int
) -> None:
    food_id, confirm = one_recipe(kitchen, path, "Zorba dal", stocked, freezer)
    ok(confirm(use=False, add_to_list=True), 201)
    assert _listed(kitchen, food_id) == [listed]
    assert amounts(kitchen, food_id) == ([stocked * 1000] if stocked else [])  # nothing taken


@pytest.mark.parametrize("path", ["item", "batch", "meal"])
def test_use_off_with_enough_in_the_house_offers_nothing(kitchen: TestClient, path: str) -> None:
    food_id, confirm = one_recipe(kitchen, path, "Zorba dal", 500, False)
    ok(confirm(use=False, add_to_list=True), 201)
    assert _listed(kitchen, food_id) == []


# --- The sync log says what the Undo undoes ---------------------------------------


def test_the_undos_sync_log_row_says_what_it_undoes(kitchen: TestClient) -> None:
    from mealwright.models import SyncAction

    dal, item = far_curry(kitchen, 60)
    done = ok(cook(kitchen, item), 201)
    with db_of(kitchen) as db:
        added = db.scalars(
            select(SyncAction).where(SyncAction.change_id == done["change"]["id"])
        ).one()
        assert added.kind == "plan_update" and added.undone_by_action_id is None
        action_id = added.id
    undone = undo(kitchen, done)
    assert undone["result"] == "done"
    with db_of(kitchen) as db:
        row = db.scalars(
            select(SyncAction).where(SyncAction.change_id == undone["change"]["id"])
        ).one()
        assert row.kind == "undo" and row.payload == {"undoes": action_id}
        assert db.get(SyncAction, (1, action_id)).undone_by_action_id == row.id  # type: ignore[union-attr]
        assert dal["id"]
