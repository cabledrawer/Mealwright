"""The shopping list built from the plan (0.6 PR 5): plan minus stock minus staples, stand-ins
counted, plan-made items keyed by ingredient + shop, hand edits never overwritten, the staples
card, and every change going through the sync counter and log (docs/dev/sync-protocol.md rule
L-5, SY-44). The other household is in the two-household tests at the end."""

import threading
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sync_kit import (
    action,
    changes,
    counter,
    db,
    main_id,
    new_id,
    ok,
    one,
    send,
)
from test_plan import slot_ids
from test_plan_writes import plan_recipe, undo
from test_recipe_list import line, stock, today
from test_recipes import food as new_food
from test_recipes import make

from mealwright.models import (
    Household,
    ListItem,
    Meal,
    MealItem,
    StapleCheck,
    SyncAction,
)

API = "/api/v1"


def day(kitchen: TestClient, n: int) -> date:
    return today(kitchen) + timedelta(days=n)


def dinner(kitchen: TestClient) -> int:
    return slot_ids(kitchen)["Dinner"]


def recipe(kitchen: TestClient, name: str, *lines: dict[str, Any], **fields: Any) -> int:
    return int(make(kitchen, name, lines=list(lines), **fields)["id"])


def plan(
    kitchen: TestClient, recipe_id: int, n: int = 1, slot: str = "Dinner", **extra: Any
) -> dict[str, Any]:
    slots = {m["name"]: m["id"] for m in ok(kitchen.get(f"{API}/meal-slots"))}
    return plan_recipe(kitchen, recipe_id, day(kitchen, n), slots[slot], **extra)


def live(kitchen: TestClient) -> dict[int, dict[str, Any]]:
    """The main list's live lines by ingredient (the first of each)."""
    out: dict[int, dict[str, Any]] = {}
    for row in changes(kitchen)["items"]:
        if not row.get("deleted"):
            out.setdefault(row["food_id"], row)
    return out


def plan_lines(kitchen: TestClient) -> list[dict[str, Any]]:
    return [r for r in changes(kitchen)["items"] if not r.get("deleted") and r["source"] == "plan"]


def amounts(kitchen: TestClient) -> dict[int, Any]:
    return {r["food_id"]: r["amount"] for r in plan_lines(kitchen)}


def from_plan(kitchen: TestClient) -> dict[str, Any]:
    result: dict[str, Any] = ok(kitchen.post(f"{API}/shopping/from-plan"))
    return result


def plan_actions(kitchen: TestClient) -> list[SyncAction]:
    with db(kitchen) as session:
        rows = list(
            session.scalars(
                select(SyncAction).where(SyncAction.kind == "plan_update").order_by(SyncAction.seq)
            )
        )
        session.expunge_all()
        return rows


@pytest.fixture
def rice(kitchen: TestClient) -> dict[str, Any]:
    return new_food(kitchen, "Plan rice")


@pytest.fixture
def dal(kitchen: TestClient) -> dict[str, Any]:
    return new_food(kitchen, "Plan dal")


# --- The sums ------------------------------------------------------------------------------------


def test_planning_a_recipe_puts_its_ingredients_on_the_list_at_once(
    kitchen: TestClient, rice: dict[str, Any], dal: dict[str, Any]
) -> None:
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"), line(dal["id"], 1, "kg"))
    assert plan_lines(kitchen) == []
    plan(kitchen, sambar)
    assert amounts(kitchen) == {rice["id"]: 200, dal["id"]: 1000}
    for row in plan_lines(kitchen):
        assert row["source"] == "plan" and row["hand_edited"] is False and row["ticks"] == []


def test_servings_scale_the_recipe_and_two_meals_add_up(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"), serves=4)
    plan(kitchen, sambar, 1, servings=8)
    assert amounts(kitchen) == {rice["id"]: 400}
    plan(kitchen, sambar, 2, "Lunch")  # its own serves: 4
    assert amounts(kitchen) == {rice["id"]: 600}


def test_stock_is_taken_off_and_units_are_converted_only_when_they_differ(
    kitchen: TestClient, rice: dict[str, Any], dal: dict[str, Any]
) -> None:
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 1, "kg"), line(dal["id"], 100, "g"))
    stock(kitchen, rice["id"], 400, "g")
    stock(kitchen, dal["id"], 1, "kg")
    plan(kitchen, sambar)
    assert amounts(kitchen) == {rice["id"]: 600}  # dal is covered, rice is 1 kg - 400 g


def test_whole_grams_and_whole_items_of_a_count_are_rounded_up(kitchen: TestClient) -> None:
    onion = new_food(kitchen, "Plan onion", counted_as="count")
    rice = new_food(kitchen, "Plan rounding rice")
    stew = recipe(kitchen, "Stew", line(onion["id"], 3, None), line(rice["id"], 100, "g"), serves=3)
    stock(kitchen, onion["id"], 1, "count")
    plan(kitchen, stew, 1, servings=2)  # 2/3 of 3 onions = 2, less 1 in stock
    assert amounts(kitchen)[onion["id"]] == 1
    assert amounts(kitchen)[rice["id"]] == 67  # 66.67 g, up to a whole gram


def test_a_counted_thing_is_never_listed_in_halves(kitchen: TestClient) -> None:
    """F56: "Cinnamon sticks 5½" - counted things go up to a whole one on the list."""
    stick = new_food(kitchen, "Plan cinnamon stick", counted_as="count")
    stew = recipe(kitchen, "Spiced", line(stick["id"], 5, None), serves=4)
    plan(kitchen, stew, 1, servings=5)  # 5/4 of 5 sticks = 6.25 -> 7, not 6.5
    assert amounts(kitchen)[stick["id"]] == 7


def test_stand_ins_are_counted_and_one_pack_covers_only_one_ingredient(
    kitchen: TestClient,
) -> None:
    onion = new_food(kitchen, "Plan onion", counted_as="count")
    shallot = new_food(kitchen, "Plan shallot", counted_as="count")
    red = new_food(kitchen, "Plan red onion", counted_as="count")
    for wanted in (onion, shallot):
        ok(kitchen.post(f"{API}/foods/{wanted['id']}/stand-ins", json={"food_id": red["id"]}), 201)
    stock(kitchen, red["id"], 3, "count")
    stock(kitchen, shallot["id"], 1, "count")
    stew = recipe(kitchen, "Stew", line(onion["id"], 2, None), line(shallot["id"], 3, None))
    plan(kitchen, stew)
    # Ingredients are taken in order: onions use two of the three red ones; the shallots have
    # one of their own and the last red one, so they still need one.
    assert amounts(kitchen) == {shallot["id"]: 1}


def test_a_stand_in_counted_another_way_is_not_added_up(kitchen: TestClient) -> None:
    onion = new_food(kitchen, "Plan onion", counted_as="count")
    flakes = new_food(kitchen, "Plan onion flakes")  # by weight
    ok(kitchen.post(f"{API}/foods/{onion['id']}/stand-ins", json={"food_id": flakes["id"]}), 201)
    stock(kitchen, flakes["id"], 500, "g")
    plan(kitchen, recipe(kitchen, "Stew", line(onion["id"], 2, None)))
    assert amounts(kitchen) == {onion["id"]: 2}


def test_a_line_that_cannot_be_compared_counts_stock_as_enough_or_goes_on_with_no_amount(
    kitchen: TestClient,
) -> None:
    salt = new_food(kitchen, "Plan salt flakes")
    pepper = new_food(kitchen, "Plan pepper")
    stew = recipe(kitchen, "Stew", line(salt["id"], None), line(pepper["id"], 1, "pinch"))
    stock(kitchen, salt["id"], 100, "g")
    plan(kitchen, stew)
    assert amounts(kitchen) == {pepper["id"]: None}  # salt is in stock; pepper is not


def test_plain_ingredients_add_nothing(kitchen: TestClient) -> None:
    fruit = new_food(kitchen, "Plan fruit")
    ok(
        kitchen.post(
            f"{API}/plan/items",
            json={
                "date": day(kitchen, 1).isoformat(),
                "slot_id": dinner(kitchen),
                "ingredient_id": fruit["id"],
            },
        ),
        201,
    )
    assert plan_lines(kitchen) == []


def test_a_removed_recipe_counts_for_nothing(kitchen: TestClient, rice: dict[str, Any]) -> None:
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"))
    plan(kitchen, sambar)
    assert amounts(kitchen) == {rice["id"]: 200}
    ok(kitchen.delete(f"{API}/recipes/{sambar}"))
    assert from_plan(kitchen)["changed"] is True
    assert plan_lines(kitchen) == []


# --- Which meals count ---------------------------------------------------------------------------


def test_cooked_didnt_moved_and_switched_off_meals_drop_out_by_themselves(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 100, "g"))
    meals = [plan(kitchen, sambar, 1, slot)["meal_id"] for slot in ("Breakfast", "Lunch", "Dinner")]
    assert amounts(kitchen) == {rice["id"]: 300}
    for status, meal_id in zip(("cooked", "didnt", "moved"), meals, strict=True):
        with db(kitchen) as session:
            session.get(Meal, meal_id).status = status  # type: ignore[union-attr]
            session.commit()
        from_plan(kitchen)
    assert plan_lines(kitchen) == []  # all three are over
    with db(kitchen) as session:
        for meal_id in meals:
            session.get(Meal, meal_id).status = "planned"  # type: ignore[union-attr]
        session.commit()
    assert from_plan(kitchen)["changed"] is True and amounts(kitchen) == {rice["id"]: 300}
    ok(kitchen.patch(f"{API}/meal-slots/{slot_ids(kitchen)['Lunch']}", json={"enabled": False}))
    assert amounts(kitchen) == {rice["id"]: 200}


def test_the_look_ahead_is_the_households_setting(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 100, "g"))
    for n in (0, 2, 3):
        plan(kitchen, sambar, n)
    # 7 days: today to day 6, so all three.
    assert amounts(kitchen) == {rice["id"]: 300}
    with db(kitchen) as session:
        session.get(Household, 1).plan_ahead_days = 3  # type: ignore[union-attr]
        session.commit()
    assert from_plan(kitchen)["days"] == 3
    assert amounts(kitchen) == {rice["id"]: 200}  # today and day 2; day 3 is outside
    with db(kitchen) as session:
        session.get(Household, 1).plan_ahead_days = 1  # type: ignore[union-attr]
        session.commit()
    from_plan(kitchen)
    assert amounts(kitchen) == {rice["id"]: 100}


def test_a_meal_in_the_past_does_not_count(kitchen: TestClient, rice: dict[str, Any]) -> None:
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 100, "g"))
    plan(kitchen, sambar, -1)
    assert plan_lines(kitchen) == []


def test_a_batch_cook_is_worked_out_for_the_cook_day_portion_plus_one_per_tub(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"), serves=4)
    cook = plan(kitchen, sambar, 1)
    assert amounts(kitchen) == {rice["id"]: 200}
    ok(
        kitchen.post(
            f"{API}/plan/items/{cook['item_id']}/batch",
            json={"tub_count": 6, "pattern": "lunch_dinner"},
        ),
        201,
    )
    # F58 (cabledrawer 28 Oct): the cook-day meal is one portion and six tubs are six more, so 7
    # portions of a recipe that serves 4: 7/4 of 200 g, which is what Cook once says. Not the full
    # recipe on top. The tubs in the next meals add nothing.
    assert amounts(kitchen) == {rice["id"]: 350}


def test_the_list_follows_the_tub_count_exactly(kitchen: TestClient, rice: dict[str, Any]) -> None:
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 800, "g"), serves=8)
    cook = plan(kitchen, sambar, 1)
    ok(
        kitchen.post(
            f"{API}/plan/items/{cook['item_id']}/batch",
            json={"tub_count": 6, "pattern": "lunch_dinner"},
        ),
        201,
    )
    assert amounts(kitchen) == {rice["id"]: 700}  # 7 portions of 8, 100 g each


def test_a_cook_meal_with_its_own_servings_buys_for_those_people_plus_the_tubs(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    # Proposed, for cabledrawer (B1 review): a cook meal planned "for 4" feeds 4 on the cook day, so
    # 4 + 6 tubs = 10 portions, not 7. Cook once's own meals have no servings: 1 + tubs, as above.
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"), serves=4)
    cook = plan(kitchen, sambar, 1, servings=4)
    ok(
        kitchen.post(
            f"{API}/plan/items/{cook['item_id']}/batch",
            json={"tub_count": 6, "pattern": "lunch_dinner"},
        ),
        201,
    )
    assert amounts(kitchen) == {rice["id"]: 500}  # 10/4 of 200 g


@pytest.mark.parametrize(("servings", "expected"), [(None, 550), (2, 450)], ids=["serves", "for-2"])
def test_a_second_copy_of_the_cooked_recipe_buys_for_itself_not_for_the_batch(
    kitchen: TestClient, rice: dict[str, Any], servings: int | None, expected: int
) -> None:
    # PR 114's left-over (pre-beta): only the cook item (the first copy, by position then id, as
    # cook_batches_of says) gets the batch's portions; a second copy of the same recipe in the
    # cook meal is an ordinary item. 1 + 6 tubs = 7/4 of 200 g = 350 g for the cook item, and
    # the copy its own: 4 (the recipe's serves) = 200 g, or 2 = 100 g. Before the fix the copy
    # was bought for the batch too: 700 g.
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"), serves=4)
    cook = plan(kitchen, sambar, 1)
    ok(
        kitchen.post(
            f"{API}/plan/items/{cook['item_id']}/batch",
            json={"tub_count": 6, "pattern": "lunch_dinner"},
        ),
        201,
    )
    extra = {} if servings is None else {"servings": servings}
    copy = plan(kitchen, sambar, 1, **extra)
    assert copy["meal_id"] == cook["meal_id"]  # the same meal: a second copy, not a new meal
    assert amounts(kitchen) == {rice["id"]: expected}


def test_the_cook_item_is_the_first_copy_by_position(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"), serves=4)
    first = plan(kitchen, sambar, 1)
    ok(
        kitchen.post(
            f"{API}/plan/items/{first['item_id']}/batch",
            json={"tub_count": 6, "pattern": "lunch_dinner"},
        ),
        201,
    )
    copy = plan(kitchen, sambar, 1, servings=2)
    with db(kitchen) as session:
        a, b = session.get(MealItem, first["item_id"]), session.get(MealItem, copy["item_id"])
        assert a is not None and b is not None
        assert a.position < b.position
        a.position, b.position = b.position, a.position
        session.commit()
    from_plan(kitchen)  # the list is worked out again after a plan change; this was none
    # The copy for 2 is first now, so it is the cook item: 2 + 6 tubs = 8/4 of 200 g = 400 g;
    # the other is an ordinary meal at the recipe's serves, 200 g.
    assert amounts(kitchen) == {rice["id"]: 600}


def test_leftovers_are_bought_for_on_top_of_the_meal(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"), serves=4)
    cook = plan(kitchen, sambar, 1)
    slots = {m["name"]: m["id"] for m in ok(kitchen.get(f"{API}/meal-slots"))}
    ok(
        kitchen.post(
            f"{API}/plan/items/{cook['item_id']}/move",
            json={
                "date": day(kitchen, 2).isoformat(),
                "slot_id": slots["Lunch"],
                "mode": "leftovers",
            },
        )
    )
    # Leftovers make a batch of one tub: a meal for 4 is bought for 5, not for 1.
    assert amounts(kitchen) == {rice["id"]: 250}


# --- Updating the list ---------------------------------------------------------------------------


def test_working_it_out_again_changes_nothing_and_takes_no_counter_number(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    plan(kitchen, recipe(kitchen, "Sambar", line(rice["id"], 200, "g")))
    before_rows, before = changes(kitchen)["items"], counter(kitchen)
    for _ in range(3):
        assert from_plan(kitchen)["changed"] is False
    assert counter(kitchen) == before
    assert changes(kitchen)["items"] == before_rows
    assert len(plan_lines(kitchen)) == 1


def test_a_change_takes_one_counter_number_stamps_the_items_and_is_logged(
    kitchen: TestClient, rice: dict[str, Any], dal: dict[str, Any]
) -> None:
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"), line(dal["id"], 100, "g"))
    start = counter(kitchen)
    plan(kitchen, sambar)
    assert counter(kitchen) == start + 1
    rows = plan_lines(kitchen)
    assert {r["version"] for r in rows} == {start + 1}
    logged = plan_actions(kitchen)
    assert len(logged) == 1 and logged[0].seq == start + 1 and logged[0].status == "applied"
    assert sorted(logged[0].payload["created"]) == sorted(r["id"] for r in rows)
    assert logged[0].login_name == "The plan" and logged[0].device_id is None
    # A phone that was at `start` gets exactly these rows from the catching-up call.
    assert sorted(r["id"] for r in changes(kitchen, start)["items"]) == sorted(
        r["id"] for r in rows
    )
    # Changing an amount bumps the version again.
    plan(kitchen, sambar, 2)
    assert {r["version"] for r in plan_lines(kitchen)} == {start + 2}
    assert [a.seq for a in plan_actions(kitchen)] == [start + 1, start + 2]
    assert plan_actions(kitchen)[1].payload["changed"][0][1:] == [200, 400]


def test_an_item_whose_need_drops_to_nothing_is_removed_the_sync_way(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    made = plan(kitchen, recipe(kitchen, "Sambar", line(rice["id"], 200, "g")))
    item = plan_lines(kitchen)[0]["id"]
    before = counter(kitchen)
    ok(kitchen.delete(f"{API}/plan/meals/{made['meal_id']}"))
    assert plan_lines(kitchen) == []
    seen = changes(kitchen, before)["items"]
    assert [(r["id"], r["deleted"]) for r in seen] == [(item, True)]
    assert seen[0]["version"] == counter(kitchen) and seen[0]["removed_by"] == "The plan"
    assert plan_actions(kitchen)[-1].payload["removed"] == [item]
    # The plan's own removal doesn't block: the need comes back as a new item.
    plan(kitchen, recipe(kitchen, "Pilau", line(rice["id"], 100, "g")))
    assert amounts(kitchen) == {rice["id"]: 100}
    assert plan_lines(kitchen)[0]["id"] != item


def test_undo_of_a_plan_write_updates_the_list(kitchen: TestClient, rice: dict[str, Any]) -> None:
    written = plan(kitchen, recipe(kitchen, "Sambar", line(rice["id"], 200, "g")))
    assert amounts(kitchen) == {rice["id"]: 200}
    undo(kitchen, written)
    assert plan_lines(kitchen) == []


def test_items_are_keyed_by_ingredient_and_shop(kitchen: TestClient) -> None:
    market = ok(kitchen.post(f"{API}/shops", json={"name": "Market"}), 201)["id"]
    grocer = ok(kitchen.post(f"{API}/shops", json={"name": "Grocer"}), 201)["id"]
    rice = new_food(kitchen, "Keyed rice", shop_id=market)
    dal = new_food(kitchen, "Keyed dal")
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 100, "g"), line(dal["id"], 100, "g"))
    plan(kitchen, sambar)
    rows = {r["food_id"]: r for r in plan_lines(kitchen)}
    assert rows[rice["id"]]["shop_id"] == market and rows[dal["id"]]["shop_id"] is None
    # The ingredient's usual shop changes: its unticked line follows, and there is still one.
    ok(kitchen.patch(f"{API}/foods/{rice['id']}", json={"shop_id": grocer}))
    plan(kitchen, sambar, 2)
    rows = {r["food_id"]: r for r in plan_lines(kitchen)}
    assert len(plan_lines(kitchen)) == 2 and rows[rice["id"]]["shop_id"] == grocer
    assert rows[rice["id"]]["amount"] == 200


# --- Hand edits, ticks, typed items, removals ----------------------------------------------------


def test_a_hand_edited_item_is_never_changed(kitchen: TestClient, rice: dict[str, Any]) -> None:
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"))
    plan(kitchen, sambar)
    item = plan_lines(kitchen)[0]["id"]
    one(kitchen, "set_amount", counter(kitchen), item_id=item, amount=750)
    row = plan_lines(kitchen)[0]
    assert row["hand_edited"] is True and row["amount"] == 750
    before = counter(kitchen)
    plan(kitchen, sambar, 2)  # the plan now needs 400
    assert plan_lines(kitchen)[0]["amount"] == 750 and counter(kitchen) == before
    # ... and it stays when the plan needs nothing at all.
    for meal in list(plan_meals(kitchen)):
        ok(kitchen.delete(f"{API}/plan/meals/{meal}"))
    assert plan_lines(kitchen)[0]["id"] == item and plan_lines(kitchen)[0]["amount"] == 750


def plan_meals(kitchen: TestClient) -> list[int]:
    with db(kitchen) as session:
        return list(session.scalars(select(Meal.id)))


def test_a_ticked_item_is_never_changed_and_what_is_still_lacking_is_one_new_line(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"))
    plan(kitchen, sambar)
    item = plan_lines(kitchen)[0]["id"]
    one(kitchen, "tick", counter(kitchen), item_id=item)
    plan(kitchen, sambar, 2)
    plan(kitchen, sambar, 3)
    rows = plan_lines(kitchen)
    # The 200 g bought is now in the pantry, so the plan needs 600 - 200 more. The ticked line
    # stays as it was; the 400 g still lacking is one line to buy (RF2 Sh3, cabledrawer 11 Nov:
    # this used to leave it off the list, and said "no second line" for the same key).
    assert [(r["id"], r["amount"]) for r in rows if r["id"] == item] == [(item, 200)]
    assert rows[0]["ticks"][0]["standing"] is True
    assert sorted(r["amount"] for r in rows) == [200, 400]
    plan(kitchen, sambar, 4)  # 800 needed: the line to buy follows, still just one
    assert sorted(r["amount"] for r in plan_lines(kitchen)) == [200, 600]


def test_a_typed_item_is_never_touched_and_covers_the_need(
    kitchen: TestClient, rice: dict[str, Any], dal: dict[str, Any]
) -> None:
    main = main_id(kitchen)
    typed = new_id()
    send(
        kitchen,
        action("add", list_id=main, item_id=typed, food_id=rice["id"], amount=1000),
    )
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"), line(dal["id"], 100, "g"))
    plan(kitchen, sambar)
    rows = {r["food_id"]: r for r in changes(kitchen)["items"]}
    assert rows[rice["id"]]["source"] == "typed" and rows[rice["id"]]["amount"] == 1000
    assert amounts(kitchen) == {dal["id"]: 100}  # the typed rice stands for the plan's rice
    ok(kitchen.delete(f"{API}/plan/meals/{plan_meals(kitchen)[0]}"))
    assert [r["id"] for r in changes(kitchen)["items"] if r["food_id"] == rice["id"]] == [typed]


def test_typing_beside_a_plan_line_joins_it_and_counts_as_a_hand_edit(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"))
    plan(kitchen, sambar)
    send(
        kitchen,
        action("add", list_id=main_id(kitchen), item_id=new_id(), food_id=rice["id"], amount=300),
    )
    row = plan_lines(kitchen)[0]
    assert row["amount"] == 500 and row["hand_edited"] is True
    plan(kitchen, sambar, 2)
    assert plan_lines(kitchen)[0]["amount"] == 500


def test_a_plan_line_moved_to_another_shop_is_a_hand_edit_and_not_doubled(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    shop = ok(kitchen.post(f"{API}/shops", json={"name": "Moved to"}), 201)["id"]
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"))
    plan(kitchen, sambar)
    item = plan_lines(kitchen)[0]["id"]
    one(kitchen, "move", counter(kitchen), item_id=item, list_id=main_id(kitchen), shop_id=shop)
    plan(kitchen, sambar, 2)
    rows = plan_lines(kitchen)
    assert [(r["id"], r["shop_id"], r["hand_edited"]) for r in rows] == [(item, shop, True)]


def test_a_plan_item_a_person_removed_stays_removed_for_the_same_need(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"))
    plan(kitchen, sambar)
    item = plan_lines(kitchen)[0]["id"]
    one(kitchen, "delete", counter(kitchen), item_id=item)
    assert plan_lines(kitchen) == []
    assert from_plan(kitchen)["changed"] is False
    plan(kitchen, recipe(kitchen, "Pilau", line(rice["id"], 100, "g")), 2)  # 300 g needed now
    assert [r["amount"] for r in plan_lines(kitchen)] == [300]  # more than they removed: a new line
    assert plan_lines(kitchen)[0]["id"] != item


def test_a_removal_a_person_made_stays_when_the_plan_changes_but_needs_no_more(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"))
    plan(kitchen, sambar)
    one(kitchen, "delete", counter(kitchen), item_id=plan_lines(kitchen)[0]["id"])
    plan(kitchen, sambar, 2, servings=2)  # 100 g more is wanted in total: 300, then 300 - 0
    # Total need is now 300 g, which is more than the 200 g that was removed: a new line.
    assert [r["amount"] for r in plan_lines(kitchen)] == [300]
    ok(kitchen.delete(f"{API}/plan/meals/{plan_meals(kitchen)[-1]}"))
    assert [r["amount"] for r in plan_lines(kitchen)] == [200]


def test_an_old_removal_does_not_block_next_weeks_shop(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"))
    plan(kitchen, sambar)
    item = plan_lines(kitchen)[0]["id"]
    one(kitchen, "delete", counter(kitchen), item_id=item)
    with db(kitchen) as session:
        row = session.get(ListItem, item)
        row.deleted_at = row.deleted_at - timedelta(days=8)  # type: ignore[union-attr, operator]
        session.commit()
    assert from_plan(kitchen)["changed"] is True
    assert [r["amount"] for r in plan_lines(kitchen)] == [200]


def test_phones_replaying_old_actions_against_plan_made_items(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    made = plan(kitchen, recipe(kitchen, "Sambar", line(rice["id"], 200, "g")))
    item = plan_lines(kitchen)[0]["id"]
    seen = counter(kitchen)
    # The plan changes while the phone is away: the item goes.
    ok(kitchen.delete(f"{API}/plan/meals/{made['meal_id']}"))
    assert plan_lines(kitchen) == []
    # The phone then sends what it did to the item: an amount, a delete, a tick.
    answer = send(
        kitchen,
        action("set_amount", seen, item_id=item, amount=900),
        action("delete", seen, item_id=item),
        action("tick", seen, item_id=item),
        since=seen,
    )
    statuses = [(r["status"], r.get("reason")) for r in answer["results"]]
    assert statuses[0] == ("ignored", "deleted") and statuses[1] == ("ignored", "deleted")
    assert plan_lines(kitchen) == []  # nothing is brought back
    assert from_plan(kitchen)["changed"] is False
    # The same action sent again is a repeat and changes nothing.
    again = action("set_amount", seen, item_id=item, amount=900)
    send(kitchen, again)
    before = counter(kitchen)
    send(kitchen, again)
    assert counter(kitchen) == before


def test_a_phone_editing_a_plan_item_the_plan_has_just_changed_wins(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"))
    plan(kitchen, sambar)
    item = plan_lines(kitchen)[0]["id"]
    seen = counter(kitchen)
    plan(kitchen, sambar, 2)  # the plan makes it 400 while the phone still has 200
    assert plan_lines(kitchen)[0]["amount"] == 400
    one(kitchen, "set_amount", seen, item_id=item, amount=250)
    assert plan_lines(kitchen)[0]["amount"] == 250 and plan_lines(kitchen)[0]["hand_edited"]
    plan(kitchen, sambar, 3)
    assert plan_lines(kitchen)[0]["amount"] == 250


def test_opening_the_list_picks_up_a_change_in_the_pantry(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    plan(kitchen, recipe(kitchen, "Sambar", line(rice["id"], 200, "g")))
    stock(kitchen, rice["id"], 500, "g")
    assert amounts(kitchen) == {rice["id"]: 200}  # the pantry is not a plan write
    answer = from_plan(kitchen)
    assert answer["changed"] is True and answer["from_plan"] == 0
    assert plan_lines(kitchen) == []


# --- The staples card ----------------------------------------------------------------------------


def test_a_staple_is_never_listed_and_shows_on_the_card_with_the_recipes_that_use_it(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    oil = new_food(kitchen, "Plan oil", staple=True)
    turmeric = new_food(kitchen, "Plan turmeric", staple=True)
    stew = recipe(kitchen, "Stew", line(oil["id"], 1, "tbsp"), line(rice["id"], 50, "g"))
    curry = recipe(kitchen, "Curry", line(oil["id"], 1, "tbsp"), line(turmeric["id"], 1, "tsp"))
    plan(kitchen, stew, 1)
    plan(kitchen, curry, 2)
    assert amounts(kitchen) == {rice["id"]: 50}
    card = from_plan(kitchen)["staples"]
    assert [(s["food"]["name"], s["used_in"]) for s in card] == [
        ("Plan oil", ["Curry", "Stew"]),
        ("Plan turmeric", ["Curry"]),
    ]


def test_got_it_hides_a_staple_until_the_plans_use_of_it_changes(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    oil = new_food(kitchen, "Plan oil", staple=True)
    stew = recipe(kitchen, "Stew", line(oil["id"], 1, "tbsp"))
    plan(kitchen, stew, 1)
    card = ok(kitchen.put(f"{API}/shopping/staples/{oil['id']}/got-it"))["staples"]
    assert card == []
    assert from_plan(kitchen)["staples"] == []
    ok(kitchen.put(f"{API}/shopping/staples/{oil['id']}/got-it"))  # twice is fine
    with db(kitchen) as session:
        assert len(list(session.scalars(select(StapleCheck)))) == 1
    # The same meals, a different day: nothing changed about the need.
    plan(kitchen, recipe(kitchen, "Plain", line(rice["id"], 10, "g")), 3)
    assert from_plan(kitchen)["staples"] == []
    # Another meal that uses it: the card asks again.
    plan(kitchen, stew, 2)
    assert [s["food"]["name"] for s in from_plan(kitchen)["staples"]] == ["Plan oil"]
    # Undo of Got it.
    ok(kitchen.put(f"{API}/shopping/staples/{oil['id']}/got-it"))
    back = ok(kitchen.delete(f"{API}/shopping/staples/{oil['id']}/got-it"))["staples"]
    assert [s["food"]["name"] for s in back] == ["Plan oil"]
    with db(kitchen) as session:
        assert list(session.scalars(select(StapleCheck))) == []


def test_got_it_is_forgotten_when_the_meal_that_used_it_goes(kitchen: TestClient) -> None:
    oil = new_food(kitchen, "Plan oil", staple=True)
    stew = recipe(kitchen, "Stew", line(oil["id"], 1, "tbsp"))
    made = plan(kitchen, stew, 1)
    ok(kitchen.put(f"{API}/shopping/staples/{oil['id']}/got-it"))
    ok(kitchen.delete(f"{API}/plan/meals/{made['meal_id']}"))
    assert from_plan(kitchen)["staples"] == []
    plan(kitchen, stew, 1)  # a new meal is a new use
    assert [s["food"]["name"] for s in from_plan(kitchen)["staples"]] == ["Plan oil"]


def test_adding_a_staple_from_the_card_puts_a_typed_item_on_the_list_and_leaves_the_card(
    kitchen: TestClient,
) -> None:
    oil = new_food(kitchen, "Plan oil", staple=True)
    plan(kitchen, recipe(kitchen, "Stew", line(oil["id"], 1, "tbsp")))
    assert [s["food"]["id"] for s in from_plan(kitchen)["staples"]] == [oil["id"]]
    result = one(
        kitchen,
        "add",
        counter(kitchen),
        list_id=main_id(kitchen),
        item_id=new_id(),
        food_id=oil["id"],
    )
    assert result["status"] == "applied", result
    row = live(kitchen)[oil["id"]]
    assert row["source"] == "typed"
    assert from_plan(kitchen)["staples"] == []
    assert from_plan(kitchen)["changed"] is False  # and the plan never touches it


def test_a_staple_marked_after_it_was_listed_leaves_the_plans_line(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    plan(kitchen, recipe(kitchen, "Stew", line(rice["id"], 50, "g")))
    assert amounts(kitchen) == {rice["id"]: 50}
    ok(kitchen.patch(f"{API}/foods/{rice['id']}", json={"staple": True}))
    from_plan(kitchen)
    assert plan_lines(kitchen) == []
    assert [s["food"]["id"] for s in from_plan(kitchen)["staples"]] == [rice["id"]]


def test_nothing_planned_gives_an_empty_card_and_no_lines(kitchen: TestClient) -> None:
    answer = from_plan(kitchen)
    assert answer == {"days": 7, "from_plan": 0, "changed": False, "staples": []}


def test_the_counts_say_how_many_lines_the_plan_made(
    kitchen: TestClient, rice: dict[str, Any], dal: dict[str, Any]
) -> None:
    plan(kitchen, recipe(kitchen, "Sambar", line(rice["id"], 200, "g"), line(dal["id"], 1, "kg")))
    assert from_plan(kitchen)["from_plan"] == 2


# --- Another household ---------------------------------------------------------------------------


def test_another_households_plan_and_stock_are_never_counted(
    kitchen: TestClient, neighbour: TestClient, rice: dict[str, Any]
) -> None:
    # Household 2 plans a lot, and has rice in stock; household 1 has neither.
    theirs = new_food(neighbour, "Plan rice")
    their_stew = recipe(neighbour, "Their stew", line(theirs["id"], 900, "g"))
    plan(neighbour, their_stew, 1)
    plan(neighbour, their_stew, 2)
    stock(neighbour, theirs["id"], 5, "kg")
    ok(kitchen.post(f"{API}/shopping/from-plan"))
    assert plan_lines(kitchen) == [] and plan_actions(kitchen) != []  # theirs is logged, ours not
    assert all(a.household_id == 2 for a in plan_actions(kitchen))
    # Household 1 plans a little: its sums use only its own pantry (none), not household 2's 5 kg.
    plan(kitchen, recipe(kitchen, "Our stew", line(rice["id"], 100, "g")))
    assert amounts(kitchen) == {rice["id"]: 100}
    from_plan(neighbour)  # their 5 kg covers their 1.8 kg, and none of it is ours
    assert plan_lines(neighbour) == []


def test_the_staples_card_and_got_it_stay_inside_the_household(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    oil = new_food(kitchen, "Plan oil", staple=True)
    plan(kitchen, recipe(kitchen, "Stew", line(oil["id"], 1, "tbsp")))
    assert [s["food"]["id"] for s in from_plan(kitchen)["staples"]] == [oil["id"]]
    assert from_plan(neighbour)["staples"] == []
    refused = neighbour.put(f"{API}/shopping/staples/{oil['id']}/got-it")
    assert refused.status_code == 404
    assert neighbour.delete(f"{API}/shopping/staples/{oil['id']}/got-it").status_code == 404
    assert [s["food"]["id"] for s in from_plan(kitchen)["staples"]] == [oil["id"]]
    with db(kitchen) as session:
        assert list(session.scalars(select(StapleCheck))) == []


# --- Review round 1 ------------------------------------------------------------------------------


def test_a_plan_line_moved_to_another_list_is_not_made_again_on_the_main_list(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    party = ok(kitchen.post(f"{API}/shopping/lists", json={"name": "Party"}), 201)["shopping_list"][
        "id"
    ]
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"))
    plan(kitchen, sambar)
    item = plan_lines(kitchen)[0]["id"]
    one(kitchen, "move", counter(kitchen), item_id=item, list_id=party, shop_id=None)
    for n in (2, 3):  # the plan changes twice, and the list is opened
        plan(kitchen, sambar, n)
        from_plan(kitchen)
    rows = plan_lines(kitchen)
    assert [(r["id"], r["list_id"]) for r in rows] == [(item, party)]


def test_a_plan_line_joined_onto_a_line_at_another_shop_is_not_made_again(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    shop = ok(kitchen.post(f"{API}/shops", json={"name": "Joined shop"}), 201)["id"]
    main = main_id(kitchen)
    typed = new_id()
    send(
        kitchen,
        action("add", list_id=main, item_id=typed, food_id=rice["id"], amount=100, shop_id=shop),
    )
    sambar = recipe(kitchen, "Sambar", line(rice["id"], 200, "g"))
    plan(kitchen, sambar)
    item = plan_lines(kitchen)[0]["id"]
    moved = one(kitchen, "move", counter(kitchen), item_id=item, list_id=main, shop_id=shop)
    assert moved["status"] == "merged"
    plan(kitchen, sambar, 2)
    from_plan(kitchen)
    assert [r for r in changes(kitchen)["items"] if not r.get("deleted")] != []
    assert plan_lines(kitchen) == []  # the plan line went into the typed one; no new one


def test_got_it_stays_hidden_as_days_pass_and_comes_back_for_a_new_meal(
    kitchen: TestClient,
) -> None:
    oil = new_food(kitchen, "Plan oil", staple=True)
    stew = recipe(kitchen, "Stew", line(oil["id"], 1, "tbsp"))
    monday = plan(kitchen, stew, 0)
    plan(kitchen, stew, 2)
    ok(kitchen.put(f"{API}/shopping/staples/{oil['id']}/got-it"))
    # Tuesday: Monday's meal is behind us (the window starts today), nothing new is planned.
    with db(kitchen) as session:
        session.get(Meal, monday["meal_id"]).day = day(kitchen, -1)  # type: ignore[union-attr]
        session.commit()
    assert from_plan(kitchen)["staples"] == []
    # A meal that was not planned then, and uses it: it asks again.
    plan(kitchen, stew, 3)
    assert [s["food"]["name"] for s in from_plan(kitchen)["staples"]] == ["Plan oil"]


def test_a_staple_added_and_ticked_does_not_come_back_on_the_card(kitchen: TestClient) -> None:
    oil = new_food(kitchen, "Plan oil", staple=True)
    plan(kitchen, recipe(kitchen, "Stew", line(oil["id"], 1, "tbsp")))
    item = new_id()
    send(kitchen, action("add", list_id=main_id(kitchen), item_id=item, food_id=oil["id"]))
    one(kitchen, "tick", counter(kitchen), item_id=item)
    assert from_plan(kitchen)["staples"] == []


# --- Security pass round 1 -----------------------------------------------------------------------


def _max_action_seq(kitchen: TestClient) -> int:
    with db(kitchen) as session:
        return int(session.scalar(select(func.max(SyncAction.seq))) or 0)


def test_undoing_a_plan_write_keeps_the_list_counter_in_step_and_the_list_writable(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    written = plan(kitchen, recipe(kitchen, "Sambar", line(rice["id"], 200, "g")))
    assert counter(kitchen) == _max_action_seq(kitchen)
    undone = undo(kitchen, written)
    assert undone is not None
    assert plan_lines(kitchen) == []
    # The counter is where the last logged action left it, not wound back (S-H1).
    assert counter(kitchen) == _max_action_seq(kitchen)
    assert counter(kitchen) >= 2  # the plan's update, then the Undo's
    # And the next list write works (it used to fail with a 500, for ever).
    milk = new_food(kitchen, "Plan milk")
    ok(
        kitchen.post(
            f"{API}/shopping/lists/{main_id(kitchen)}/items", json={"food_id": milk["id"]}
        ),
        201,
    )
    assert counter(kitchen) == _max_action_seq(kitchen)


def test_a_plan_write_and_the_list_update_share_one_transaction_and_one_counter(
    kitchen: TestClient, rice: dict[str, Any]
) -> None:
    start = counter(kitchen)
    plan(kitchen, recipe(kitchen, "Sambar", line(rice["id"], 200, "g")))
    assert counter(kitchen) == start + 1 == _max_action_seq(kitchen)
    # An Undo that also changes the list (here the plan's Undo) numbers its own and the list's
    # changes without a clash, many times over.
    for n in range(3):
        written = plan(kitchen, recipe(kitchen, f"Pilau {n}", line(rice["id"], 50, "g")), 2 + n)
        undo(kitchen, written)
        assert counter(kitchen) == _max_action_seq(kitchen)


def test_a_huge_amount_goes_on_the_list_with_no_amount_instead_of_overflowing(
    kitchen: TestClient,
) -> None:
    flour = new_food(kitchen, "Plan flour")
    sugar = new_food(kitchen, "Plan sugar")
    # Each line is under the limit, together they are over: unknown, not 3,000,000 kg.
    big = recipe(
        kitchen,
        "Big bake",
        line(flour["id"], 600000, "kg"),
        line(flour["id"], 600000, "kg"),
        line(sugar["id"], 10, "g"),
        serves=1,
    )
    plan(kitchen, big, 1, servings=99)  # a tenfold scale-up of a huge recipe, up to 99 servings
    assert amounts(kitchen) == {flour["id"]: None, sugar["id"]: 990}
    plan(kitchen, big, 2)
    assert amounts(kitchen)[flour["id"]] is None
    with db(kitchen) as session:
        assert all(
            (i.amount_milli or 0) <= 1_000_000_000 for i in session.scalars(select(ListItem))
        )


@pytest.mark.parametrize("big_first", [False, True])
def test_one_recipe_over_the_limit_leaves_the_ingredient_with_no_amount_in_either_order(
    kitchen: TestClient, big_first: bool
) -> None:
    flour = new_food(kitchen, "Order flour")
    small = recipe(kitchen, "Small bake", line(flour["id"], 100, "g"), serves=1)
    huge = recipe(
        kitchen,
        "Huge bake",  # each line under the limit, the recipe's own total over it
        line(flour["id"], 600, "kg"),
        line(flour["id"], 600, "kg"),
        serves=1,
    )
    first, second = (huge, small) if big_first else (small, huge)
    plan(kitchen, first, 1)
    plan(kitchen, second, 2)
    assert amounts(kitchen)[flour["id"]] is None


def test_two_phones_saying_got_it_at_once_both_get_an_answer(kitchen: TestClient) -> None:
    salt = new_food(kitchen, "Race salt", staple=True)
    plan(kitchen, recipe(kitchen, "Salty", line(salt["id"], 1, "tsp")), 1)
    url = f"{API}/shopping/staples/{salt['id']}/got-it"
    for _ in range(5):
        ok(kitchen.delete(url))
        start = threading.Barrier(2)
        codes: list[int] = []

        def say_it(start: threading.Barrier = start, codes: list[int] = codes) -> None:
            other = TestClient(kitchen.app, base_url="https://testserver")
            other.cookies.update(kitchen.cookies)
            start.wait()
            codes.append(other.put(url).status_code)

        threads = [threading.Thread(target=say_it) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert codes == [200, 200]
    with db(kitchen) as session:
        assert len(list(session.scalars(select(StapleCheck)))) == 1


# --- Recipes inside recipes: the work grows with the recipes, not the paths (release M2) ----------


def nested_tree(kitchen: TestClient, depth: int, width: int) -> tuple[int, dict[str, Any]]:
    """L0 uses 1 g of seed; each level above lists the level below on `width` lines."""
    seed = new_food(kitchen, "Seed")
    below = recipe(kitchen, "L0", line(seed["id"], 1, "g"))
    for k in range(1, depth + 1):
        inner = [{"kind": "ingredient", "words": f"w{i}", "recipe_id": below} for i in range(width)]
        below = recipe(kitchen, f"L{k}", *inner)
    return below, seed


def test_a_nested_recipe_adds_up_once_per_line(kitchen: TestClient) -> None:
    top, seed = nested_tree(kitchen, 3, 4)
    plan(kitchen, top)
    assert amounts(kitchen) == {seed["id"]: 4**3}


def test_a_deep_wide_recipe_tree_is_worked_out_in_bounded_steps(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mealwright import shop_from_plan

    calls = {"n": 0}
    real = shop_from_plan._must_make

    def counted(*args: Any, **kwargs: Any) -> bool:
        calls["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(shop_from_plan, "_must_make", counted)
    top, seed = nested_tree(kitchen, 6, 10)
    plan(kitchen, top)  # the plan step
    assert calls["n"] <= 1000  # 60 lines a pass; walking every path would be a million
    assert amounts(kitchen) == {seed["id"]: 10**6}
    calls["n"] = 0
    ok(kitchen.get(f"{API}/shopping/lists/{main_id(kitchen)}"))  # the list read
    assert calls["n"] <= 1000
