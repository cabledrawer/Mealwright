""" "Cooked it" takes the ingredients out of the pantry (0.7 K2; spec section 2, points 5 and 7):
the confirm, its one change with Undo, the cooked record with the choices, batch cooks
deducting once, and the refusals. The rules themselves are in test_deduction.py."""

from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_deduction import DAY, plan_item, propose, recipe_of, row_of
from test_plan import db_of, slot_ids
from test_recipe_list import line, place_id, stock
from test_recipes import food, make

from mealwright import cooked
from mealwright.models import (
    Change,
    ChangeLine,
    CookedRecord,
    FoodConversion,
    ListItem,
    StockLot,
)

API = "/api/v1"


def cook(
    client: TestClient, item_id: int, choices: list[dict[str, Any]] | None = None, **body: Any
) -> Any:
    return client.post(f"{API}/plan/items/{item_id}/cook", json={"choices": choices or [], **body})


def amounts(client: TestClient, food_id: int) -> list[int]:
    """The thousandths each packet of this ingredient holds, oldest first."""
    with db_of(client) as db:
        return [
            lot.amount_milli
            for lot in db.scalars(
                select(StockLot).where(StockLot.food_id == food_id).order_by(StockLot.id)
            )
        ]


def dal_curry(client: TestClient, in_stock: int = 800) -> tuple[dict[str, Any], int]:
    dal = food(client, "Zorba dal")
    stock(client, dal["id"], in_stock, "g")
    return dal, plan_item(client, recipe_of(client, [line(dal["id"], 200, "g")]), servings=2)


# --- The confirm ---------------------------------------------------------------------------------


def test_confirming_takes_the_proposal_as_one_change_with_a_line_for_each_packet(
    kitchen: TestClient,
) -> None:
    dal = food(kitchen, "Zorba dal")
    onion = food(kitchen, "Zorba onion", counted_as="count")
    stock(kitchen, dal["id"], 60, "g", use_by=(DAY + timedelta(days=1)).isoformat())
    stock(kitchen, dal["id"], 500, "g")
    stock(kitchen, onion["id"], 5, "count")
    recipe = recipe_of(kitchen, [line(dal["id"], 200, "g"), line(onion["id"], 2, None)])
    item = plan_item(kitchen, recipe, servings=2)

    done = ok(cook(kitchen, item), 201)
    assert done["change"]["kind"] == "cooked" and done["change"]["can_undo"] is True
    assert done["change"]["summary"] == "Cooked Zorba curry (2 portions)"
    assert amounts(kitchen, dal["id"]) == [0, 460_000]  # the dated packet first
    assert amounts(kitchen, onion["id"]) == [4_000]
    with db_of(kitchen) as db:
        lines = db.scalars(select(ChangeLine).where(ChangeLine.change_id == done["change"]["id"]))
        assert sorted((ln.amount_before_milli, ln.amount_after_milli) for ln in lines) == [
            (5_000, 4_000),
            (60_000, 0),
            (500_000, 460_000),
        ]
    # It is in Recent changes beside the other stock changes.
    listed = ok(kitchen.get(f"{API}/changes", params={"area": "pantry"}))["changes"]
    assert listed[0]["kind"] == "cooked" and listed[0]["id"] == done["change"]["id"]
    assert [c["kind"] for c in listed].count("cooked") == 1


def test_the_record_keeps_the_recipe_and_each_rows_choice(kitchen: TestClient) -> None:
    dal, item = dal_curry(kitchen)
    done = ok(cook(kitchen, item), 201)
    record = done["cooked"]
    assert record["meal_item_id"] == item and record["portions"] == 2
    assert record["change_id"] == done["change"]["id"]
    assert ok(kitchen.get(f"{API}/plan/items/{item}/cooked")) == record
    assert record["snapshot"]["name"] == "Zorba curry" and record["snapshot"]["servings"] == 4
    [choice] = record["snapshot"]["choices"]
    assert choice["key"] == f"food:{dal['id']}" and choice["food_name"] == "Zorba dal"
    assert choice["use"] is True and choice["status"] == "take"
    assert (choice["needed_milli"], choice["used_milli"], choice["short_milli"]) == (
        100_000,
        100_000,
        0,
    )
    assert choice["entered"] is None and len(choice["line_ids"]) == 1
    assert choice["takes"] == [
        {"food_id": dal["id"], "food_name": "Zorba dal", "stand_in": False, "amount_milli": 100_000}
    ]


def test_a_row_switched_off_is_left_alone_and_the_record_says_so(kitchen: TestClient) -> None:
    dal = food(kitchen, "Zorba dal")
    rice = food(kitchen, "Zorba rice")
    stock(kitchen, dal["id"], 800, "g")
    stock(kitchen, rice["id"], 800, "g")
    recipe = recipe_of(kitchen, [line(dal["id"], 200, "g"), line(rice["id"], 200, "g")])
    item = plan_item(kitchen, recipe, servings=4)
    done = ok(cook(kitchen, item, [{"key": f"food:{rice['id']}", "use": False}]), 201)
    assert amounts(kitchen, dal["id"]) == [600_000] and amounts(kitchen, rice["id"]) == [800_000]
    off = next(c for c in done["cooked"]["snapshot"]["choices"] if c["food_id"] == rice["id"])
    assert off["use"] is False and off["used_milli"] == 0 and off["needed_milli"] == 200_000
    assert off["short_milli"] == 0


def test_how_much_was_used_or_left_can_be_typed_and_is_kept(kitchen: TestClient) -> None:
    dal = food(kitchen, "Zorba dal")
    onion = food(kitchen, "Zorba onion", counted_as="count")
    stock(kitchen, dal["id"], 800, "g")
    stock(kitchen, onion["id"], 5, "count")
    recipe = recipe_of(kitchen, [line(dal["id"], 200, "g"), line(onion["id"], 2, None)])
    item = plan_item(kitchen, recipe, servings=4)
    choices = [
        {"key": f"food:{dal['id']}", "used": {"amount": 0.25, "unit": "kg"}},  # used 250 g
        {"key": f"food:{onion['id']}", "left": {"amount": 3, "unit": "count"}},  # 3 left
    ]
    done = ok(cook(kitchen, item, choices), 201)
    assert amounts(kitchen, dal["id"]) == [550_000] and amounts(kitchen, onion["id"]) == [3_000]
    by_food = {c["food_id"]: c for c in done["cooked"]["snapshot"]["choices"]}
    assert (by_food[dal["id"]]["entered"], by_food[dal["id"]]["entered_milli"]) == ("used", 250_000)
    assert (by_food[onion["id"]]["entered"], by_food[onion["id"]]["entered_milli"]) == (
        "left",
        3_000,
    )
    assert (
        by_food[onion["id"]]["used_milli"] == 2_000
        and by_food[onion["id"]]["needed_milli"] == 2_000
    )


def test_none_left_takes_the_lot_and_more_used_than_there_is_never_goes_below_zero(
    kitchen: TestClient,
) -> None:
    dal, item = dal_curry(kitchen, in_stock=150)
    done = ok(
        cook(kitchen, item, [{"key": f"food:{dal['id']}", "left": {"amount": 0, "unit": "g"}}]), 201
    )
    assert amounts(kitchen, dal["id"]) == [0]
    assert done["cooked"]["snapshot"]["choices"][0]["used_milli"] == 150_000

    rice = food(kitchen, "Zorba rice")
    stock(kitchen, rice["id"], 100, "g")
    item2 = plan_item(
        kitchen,
        recipe_of(kitchen, [line(rice["id"], 50, "g")]),
        servings=4,
        day=DAY + timedelta(days=1),
    )
    done2 = ok(
        cook(kitchen, item2, [{"key": f"food:{rice['id']}", "used": {"amount": 400, "unit": "g"}}]),
        201,
    )
    assert amounts(kitchen, rice["id"]) == [0]
    choice = done2["cooked"]["snapshot"]["choices"][0]
    assert (choice["used_milli"], choice["short_milli"]) == (100_000, 300_000)  # "add to list"


def test_a_stand_in_is_taken_from_and_recorded(kitchen: TestClient) -> None:
    onion = food(kitchen, "Zorba onion", counted_as="count")
    red = food(kitchen, "Zorba red onion", counted_as="count")
    ok(kitchen.post(f"{API}/foods/{onion['id']}/stand-ins", json={"food_id": red["id"]}), 201)
    stock(kitchen, red["id"], 4, "count")
    item = plan_item(kitchen, recipe_of(kitchen, [line(onion["id"], 2, None)]), servings=4)
    done = ok(cook(kitchen, item), 201)
    assert amounts(kitchen, red["id"]) == [2_000]
    [choice] = done["cooked"]["snapshot"]["choices"]
    assert choice["food_name"] == "Zorba onion" and choice["used_milli"] == 2_000
    assert [(t["food_name"], t["stand_in"]) for t in choice["takes"]] == [("Zorba red onion", True)]
    # Undo gives the stand-in back.
    ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))
    assert amounts(kitchen, red["id"]) == [4_000]


def test_the_freezer_is_used_only_when_the_row_says_so(kitchen: TestClient) -> None:
    peas = food(kitchen, "Zorba peas")
    stock(kitchen, peas["id"], 100, "g")
    stock(kitchen, peas["id"], 300, "g", place_id=place_id(kitchen, "Freezer"))
    recipe = make(kitchen, "Zorba peas curry", serves=4, lines=[line(peas["id"], 250, "g")])
    item = plan_item(kitchen, recipe, servings=4)
    done = ok(cook(kitchen, item, [{"key": f"food:{peas['id']}", "from_freezer": True}]), 201)
    assert amounts(kitchen, peas["id"]) == [0, 150_000]
    choice = done["cooked"]["snapshot"]["choices"][0]
    assert choice["from_freezer"] is True and choice["short_milli"] == 0
    # Without it the freezer is left alone, and what is missing is recorded.
    peas2 = food(kitchen, "Zorba peas two")
    stock(kitchen, peas2["id"], 100, "g")
    stock(kitchen, peas2["id"], 300, "g", place_id=place_id(kitchen, "Freezer"))
    recipe2 = make(kitchen, "Zorba peas curry two", serves=4, lines=[line(peas2["id"], 250, "g")])
    item3 = plan_item(kitchen, recipe2, servings=4)
    done3 = ok(cook(kitchen, item3), 201)
    assert amounts(kitchen, peas2["id"]) == [0, 300_000]
    assert done3["cooked"]["snapshot"]["choices"][0]["short_milli"] == 150_000


def test_staples_inner_recipes_and_unlinked_lines_are_in_the_record_but_take_nothing(
    kitchen: TestClient,
) -> None:
    oil = food(kitchen, "Zorba oil", staple=True)
    podi = make(kitchen, "Zorba podi")
    recipe = recipe_of(
        kitchen,
        [
            line(oil["id"], 1, "tbsp"),
            {"words": "podi", "amount": 2, "unit": "tbsp", "recipe_id": podi["id"]},
            {"words": "a lime"},
        ],
    )
    done = ok(cook(kitchen, plan_item(kitchen, recipe)), 201)
    got = {c["key"].split(":")[0]: c for c in done["cooked"]["snapshot"]["choices"]}
    assert {k: (v["status"], v["use"], v["used_milli"]) for k, v in got.items()} == {
        "food": ("staple", False, 0),
        "recipe": ("make_first", False, 0),
        "line": ("not_linked", False, 0),
    }
    assert got["recipe"]["recipe_name"] == "Zorba podi"


# --- Refusals ------------------------------------------------------------------------------------


def test_choices_for_things_that_are_not_there_are_refused(kitchen: TestClient) -> None:
    dal, item = dal_curry(kitchen)
    cases: list[tuple[list[dict[str, Any]], int, str]] = [
        ([{"key": "food:99999"}], 422, "unknown_row"),
        ([{"key": "nonsense"}], 422, "unknown_row"),
        (
            [{"key": f"food:{dal['id']}", "left": {"amount": 900, "unit": "g"}}],
            422,
            "left_too_much",
        ),
        ([{"key": f"food:{dal['id']}"}, {"key": f"food:{dal['id']}"}], 422, "twice"),
        ([{"key": "line:1", "used": {"amount": 1, "unit": "g"}}], 422, "no_ingredient"),
    ]
    for choices, code_status, code in cases:
        answer = cook(kitchen, item, choices)
        assert (answer.status_code, answer.json()["code"]) == (code_status, code), choices
    both = {
        "key": f"food:{dal['id']}",
        "used": {"amount": 1, "unit": "g"},
        "left": {"amount": 1, "unit": "g"},
    }
    assert cook(kitchen, item, [both]).status_code == 422
    assert amounts(kitchen, dal["id"]) == [800_000]  # nothing was taken


def test_a_staple_cannot_be_given_an_amount(kitchen: TestClient) -> None:
    oil = food(kitchen, "Zorba oil", staple=True)
    item = plan_item(kitchen, recipe_of(kitchen, [line(oil["id"], 1, "tbsp")]))
    bad = [{"key": f"food:{oil['id']}", "used": {"amount": 1, "unit": "g"}}]
    answer = cook(kitchen, item, bad)
    assert (answer.status_code, answer.json()["code"]) == (422, "staple")


def test_a_second_confirm_for_the_same_item_is_refused_not_doubled(kitchen: TestClient) -> None:
    dal, item = dal_curry(kitchen)
    ok(cook(kitchen, item), 201)
    again = cook(kitchen, item)
    assert again.status_code == 409 and again.json()["code"] == "already_cooked"
    assert again.json()["detail"].startswith("This was already cooked on ")
    assert amounts(kitchen, dal["id"]) == [700_000]
    assert propose_status(kitchen, item) == 409  # the proposal says the same


def propose_status(client: TestClient, item: int) -> int:
    return client.post(f"{API}/plan/items/{item}/cook/preview", json={}).status_code


def test_a_retry_with_the_same_key_takes_once(kitchen: TestClient) -> None:
    dal, item = dal_curry(kitchen)
    headers = {"Idempotency-Key": "cook-1"}
    first = kitchen.post(f"{API}/plan/items/{item}/cook", json={}, headers=headers)
    second = kitchen.post(f"{API}/plan/items/{item}/cook", json={}, headers=headers)
    assert (first.status_code, second.status_code) == (201, 200)
    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.json()["change"]["id"] == first.json()["change"]["id"]
    assert second.json()["cooked"] == first.json()["cooked"]
    assert amounts(kitchen, dal["id"]) == [700_000]
    # The same key for something else is not a retry.
    other = kitchen.post(f"{API}/plan/items/{item + 1}/cook", json={}, headers=headers)
    assert other.status_code == 409 and other.json()["code"] == "key_reused"


def test_a_meal_that_was_skipped_or_moved_a_removed_recipe_and_a_plain_item_cannot_be_cooked(
    kitchen: TestClient,
) -> None:
    dal = food(kitchen, "Zorba dal")
    recipe = recipe_of(kitchen, [line(dal["id"], 200, "g")])
    today = date.today()
    planned = ok(
        kitchen.post(
            f"{API}/plan/items",
            json={
                "date": today.isoformat(),
                "slot_id": slot_ids(kitchen)["Lunch"],
                "recipe_id": recipe["id"],
            },
        ),
        201,
    )
    ok(kitchen.post(f"{API}/plan/meals/{planned['meal_id']}/didnt"))
    answer = cook(kitchen, planned["item_id"])
    assert (answer.status_code, answer.json()["code"]) == (409, "meal_done")

    gone = plan_item(kitchen, recipe, day=DAY + timedelta(days=1))
    ok(kitchen.delete(f"{API}/recipes/{recipe['id']}"))
    answer = cook(kitchen, gone)
    assert (answer.status_code, answer.json()["code"]) == (422, "not_a_recipe")

    banana = food(kitchen, "Zorba banana", counted_as="count")
    plain = ok(
        kitchen.post(
            f"{API}/plan/items",
            json={
                "date": DAY.isoformat(),
                "slot_id": slot_ids(kitchen)["Lunch"],
                "ingredient_id": banana["id"],
            },
        ),
        201,
    )
    assert cook(kitchen, plain["item_id"]).json()["code"] == "not_a_recipe"


def test_a_meal_already_marked_cooked_on_today_can_still_be_given_its_record(
    kitchen: TestClient,
) -> None:
    dal = food(kitchen, "Zorba dal")
    stock(kitchen, dal["id"], 800, "g")
    recipe = recipe_of(kitchen, [line(dal["id"], 200, "g")])
    planned = ok(
        kitchen.post(
            f"{API}/plan/items",
            json={
                "date": date.today().isoformat(),
                "slot_id": slot_ids(kitchen)["Lunch"],
                "recipe_id": recipe["id"],
            },
        ),
        201,
    )
    ok(kitchen.post(f"{API}/plan/meals/{planned['meal_id']}/cooked", json={}))
    ok(cook(kitchen, planned["item_id"], portions=4), 201)
    assert amounts(kitchen, dal["id"]) == [600_000]


def test_another_households_item_batch_and_food_are_not_found(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    dal, item = dal_curry(kitchen)
    assert cook(neighbour, item).status_code == 404
    assert neighbour.post(f"{API}/plan/batches/1/cook", json={}).status_code == 404
    # A choice naming the other household's ingredient is not found either.
    theirs = food(neighbour, "Next door's rice")
    mine = cook(
        kitchen, item, [{"key": f"food:{theirs['id']}", "used": {"amount": 1, "unit": "g"}}]
    )
    assert mine.status_code == 404
    assert amounts(kitchen, dal["id"]) == [800_000]


# --- Ask once ------------------------------------------------------------------------------------


def _toor_curry(client: TestClient) -> tuple[dict[str, Any], int]:
    toor = food(client, "Zorba toor")
    stock(client, toor["id"], 1000, "g")
    return toor, plan_item(client, recipe_of(client, [line(toor["id"], 1, "cup")]), servings=4)


def test_a_row_still_asking_is_not_confirmed_until_it_is_answered(kitchen: TestClient) -> None:
    toor, item = _toor_curry(kitchen)
    asked = cook(kitchen, item)
    assert asked.status_code == 409 and asked.json()["code"] == "ask_once"
    assert asked.json()["ask"]["food_id"] == toor["id"]
    assert amounts(kitchen, toor["id"]) == [1_000_000]
    # Switched off, it needs no answer.
    ok(cook(kitchen, item, [{"key": f"food:{toor['id']}", "use": False}]), 201)


def test_the_answer_is_used_and_remembered_for_next_time(kitchen: TestClient) -> None:
    toor, item = _toor_curry(kitchen)
    answer = {"kind": "weight_per_ml", "food_id": toor["id"], "grams": 200}
    ok(cook(kitchen, item, answers=[answer]), 201)
    assert amounts(kitchen, toor["id"]) == [800_000]
    with db_of(kitchen) as db:
        [saved] = db.scalars(select(FoodConversion).where(FoodConversion.food_id == toor["id"]))
        assert (saved.kind, saved.value_milli) == ("weight_per_ml", 800)
    # Asked once: the next proposal works it out.
    item2 = plan_item(
        kitchen,
        recipe_of(kitchen, [line(toor["id"], 1, "cup")]),
        servings=4,
        day=DAY + timedelta(days=1),
    )
    assert row_of(propose(kitchen, item2), "Zorba toor")["needed"]["amount"] == 200


def test_an_answer_without_remember_is_used_once_and_forgotten(kitchen: TestClient) -> None:
    toor, item = _toor_curry(kitchen)
    answer = {"kind": "weight_per_ml", "food_id": toor["id"], "grams": 200, "remember": False}
    ok(cook(kitchen, item, answers=[answer]), 201)
    assert amounts(kitchen, toor["id"]) == [800_000]
    with db_of(kitchen) as db:
        assert db.scalars(select(FoodConversion)).first() is None


def test_an_amount_typed_for_a_row_that_asks_needs_no_answer(kitchen: TestClient) -> None:
    toor, item = _toor_curry(kitchen)
    typed = [{"key": f"food:{toor['id']}", "used": {"amount": 150, "unit": "g"}}]
    ok(cook(kitchen, item, typed), 201)
    assert amounts(kitchen, toor["id"]) == [850_000]


# --- Undo ----------------------------------------------------------------------------------------


def test_undo_puts_every_packet_back_and_the_item_can_be_cooked_again(kitchen: TestClient) -> None:
    dal = food(kitchen, "Zorba dal")
    onion = food(kitchen, "Zorba onion", counted_as="count")
    stock(kitchen, dal["id"], 800, "g")
    stock(kitchen, onion["id"], 5, "count")
    item = plan_item(
        kitchen,
        recipe_of(kitchen, [line(dal["id"], 200, "g"), line(onion["id"], 2, None)]),
        servings=4,
    )
    done = ok(cook(kitchen, item), 201)
    undone = ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))
    assert undone["result"] == "done"
    assert amounts(kitchen, dal["id"]) == [800_000] and amounts(kitchen, onion["id"]) == [5_000]
    assert (
        kitchen.get(f"{API}/plan/items/{item}/cooked").status_code == 409
    )  # not cooked (any more)
    with db_of(kitchen) as db:
        assert db.scalars(select(CookedRecord)).first() is None
    again = ok(cook(kitchen, item), 201)
    assert amounts(kitchen, dal["id"]) == [600_000]
    assert again["cooked"]["id"] != done["cooked"]["id"]


def test_undo_after_the_packet_was_used_by_hand_still_lets_it_be_cooked_again(
    kitchen: TestClient,
) -> None:
    dal, item = dal_curry(kitchen, in_stock=200)
    done = ok(cook(kitchen, item), 201)  # takes 100 g of 200
    with db_of(kitchen) as db:
        stocked = db.scalars(select(StockLot).where(StockLot.food_id == dal["id"])).one()
        stocked.amount_milli = 0  # someone used the rest by hand
        db.commit()
    undone = ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))
    assert undone["result"] == "done"
    assert amounts(kitchen, dal["id"]) == [100_000]  # what the meal took comes back; no more
    assert (
        kitchen.get(f"{API}/plan/items/{item}/cooked").status_code == 409
    )  # not cooked (any more)


# --- The record on its own -----------------------------------------------------------------------


def test_a_record_made_before_there_were_choices_still_reads(kitchen: TestClient) -> None:
    _, item = dal_curry(kitchen)
    done = ok(cook(kitchen, item), 201)
    with db_of(kitchen) as db:
        record = db.get(CookedRecord, done["cooked"]["id"])
        assert record is not None
        record.snapshot = {k: v for k, v in record.snapshot.items() if k != "choices"}
        db.commit()
        assert cooked.read(record).choices == []
    assert ok(kitchen.get(f"{API}/plan/items/{item}/cooked"))["snapshot"]["choices"] == []
    with db_of(kitchen) as db:
        assert db.scalar(select(Change.kind).where(Change.id == done["change"]["id"])) == "cooked"


# --- Batch cooks: once, on the cook day ----------------------------------------------------------


def _batch(
    client: TestClient, stock_g: int = 2000
) -> tuple[dict[str, Any], int, int, dict[str, Any]]:
    dal = food(client, "Zorba dal")
    stock(client, dal["id"], stock_g, "g")
    recipe = recipe_of(client, [line(dal["id"], 200, "g")])
    item = plan_item(client, recipe)
    made = ok(
        client.post(f"{API}/plan/items/{item}/batch", json={"tub_count": 3, "pattern": "pick"}), 201
    )
    return dal, item, made["batch_id"], recipe


def test_a_batch_deducts_once_for_the_cook_day_eaters_and_every_tub(kitchen: TestClient) -> None:
    dal, _, batch, _ = _batch(kitchen)
    proposal = ok(kitchen.post(f"{API}/plan/batches/{batch}/cook/preview", json={}))
    assert proposal["portions"] == 4  # one for the cook-day meal and a portion for each of 3 tubs
    assert row_of(proposal, "Zorba dal")["needed"]["amount"] == 200  # the recipe serves 4
    done = ok(kitchen.post(f"{API}/plan/batches/{batch}/cook", json={}), 201)
    assert amounts(kitchen, dal["id"]) == [1_800_000]
    assert done["cooked"]["batch_id"] == batch and done["cooked"]["meal_item_id"] is None
    assert ok(kitchen.get(f"{API}/plan/batches/{batch}/cooked")) == done["cooked"]
    # The tubs Cook once made are still there, whole.
    tubs = ok(kitchen.get(f"{API}/plan", params={"from": DAY.isoformat(), "to": DAY.isoformat()}))
    assert [t["amount_quarters"] for t in tubs["tubs"]] == [4, 4, 4]


def test_a_second_batch_confirm_is_refused_and_so_is_cooking_its_item_on_its_own(
    kitchen: TestClient,
) -> None:
    dal, item, batch, _ = _batch(kitchen)
    ok(kitchen.post(f"{API}/plan/batches/{batch}/cook", json={}), 201)
    again = kitchen.post(f"{API}/plan/batches/{batch}/cook", json={})
    assert (again.status_code, again.json()["code"]) == (409, "already_cooked")
    alone = cook(kitchen, item)
    assert (alone.status_code, alone.json()["code"]) == (409, "cook_the_batch")
    assert amounts(kitchen, dal["id"]) == [1_800_000]  # taken once


def test_undoing_a_batch_cook_lets_it_be_cooked_again(kitchen: TestClient) -> None:
    dal, _, batch, _ = _batch(kitchen)
    done = ok(kitchen.post(f"{API}/plan/batches/{batch}/cook", json={}), 201)
    ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))
    assert amounts(kitchen, dal["id"]) == [2_000_000]
    ok(kitchen.post(f"{API}/plan/batches/{batch}/cook", json={"portions": 8}), 201)
    assert amounts(kitchen, dal["id"]) == [1_600_000]


def test_a_batch_whose_recipe_is_gone_cannot_be_cooked(kitchen: TestClient) -> None:
    _, _, batch, recipe = _batch(kitchen)
    ok(kitchen.delete(f"{API}/recipes/{recipe['id']}"))
    answer = kitchen.post(f"{API}/plan/batches/{batch}/cook", json={})
    assert (answer.status_code, answer.json()["code"]) == (422, "not_a_recipe")


# --- The shortfall goes on the shopping list ----------------------------------------


def _listed(client: TestClient, food_id: int) -> list[int]:
    with db_of(client) as db:
        return [
            item.amount_milli
            for item in db.scalars(select(ListItem).where(ListItem.food_id == food_id))
            if item.deleted_at is None and item.amount_milli is not None
        ]


FAR = DAY + timedelta(days=20)  # beyond the shopping list's look-ahead: the plan adds nothing


def far_curry(client: TestClient, in_stock: int) -> tuple[dict[str, Any], int]:
    dal = food(client, "Zorba dal")
    stock(client, dal["id"], in_stock, "g")
    recipe = recipe_of(client, [line(dal["id"], 200, "g")])
    return dal, plan_item(client, recipe, servings=2, day=FAR)


def test_confirming_puts_what_was_missing_on_the_list_and_undo_takes_it_off(
    kitchen: TestClient,
) -> None:
    dal, item = far_curry(kitchen, 60)  # needs 100 g
    done = ok(cook(kitchen, item), 201)
    assert amounts(kitchen, dal["id"]) == [0]
    assert _listed(kitchen, dal["id"]) == [40_000]
    choice = done["cooked"]["snapshot"]["choices"][0]
    assert choice["short_milli"] == 40_000 and choice["add_to_list"] is True
    ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))
    assert _listed(kitchen, dal["id"]) == []


def test_a_shortfall_can_be_left_off_the_list(kitchen: TestClient) -> None:
    dal, item = far_curry(kitchen, 60)
    done = ok(cook(kitchen, item, [{"key": f"food:{dal['id']}", "add_to_list": False}]), 201)
    assert _listed(kitchen, dal["id"]) == []
    assert done["cooked"]["snapshot"]["choices"][0]["add_to_list"] is False


def test_make_first_rows_are_not_put_on_the_shopping_list(kitchen: TestClient) -> None:
    batter = make(kitchen, "Zorba batter", made_ahead=True, makes={"amount": 2, "unit": "l"})
    dosa = recipe_of(
        kitchen, [{"words": "batter", "amount": 500, "unit": "ml", "recipe_id": batter["id"]}]
    )
    ok(cook(kitchen, plan_item(kitchen, dosa, servings=4)), 201)
    assert _listed(kitchen, batter["homemade"]["id"]) == []
