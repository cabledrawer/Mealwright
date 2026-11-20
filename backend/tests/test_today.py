"""Today (0.6 PR 6): the read, and the three answers to "Did you cook Sambar?" - Cooked it,
Didn't, Move it - each with its Undo, the locks, the shopping list following, leftovers as
tubs, the household's own day, ids from another household, and the first-day conditions."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sync_kit import changes, ok
from test_plan import add_food, db_of, slot_ids
from test_plan_writes import plan_recipe, undo
from test_recipe_list import line
from test_recipes import food as new_food
from test_recipes import make

from mealwright import household as household_module
from mealwright.models import BatchCook, Household, Meal, MealItem, Tub

API = "/api/v1"


def household_day(kitchen: TestClient) -> date:
    return date.fromisoformat(ok(kitchen.get(f"{API}/household"))["today"])


def ago(kitchen: TestClient, n: int) -> date:
    return household_day(kitchen) - timedelta(days=n)


def ahead(kitchen: TestClient, n: int) -> date:
    return household_day(kitchen) + timedelta(days=n)


def new_recipe(kitchen: TestClient, name: str, *lines: dict[str, Any]) -> int:
    return int(make(kitchen, name, lines=list(lines))["id"])


def plan_lines(kitchen: TestClient) -> list[Any]:
    """The amounts of the main list's lines the plan made."""
    return [
        r["amount"]
        for r in changes(kitchen)["items"]
        if not r.get("deleted") and r["source"] == "plan"
    ]


def get_today(kitchen: TestClient) -> dict[str, Any]:
    return ok(kitchen.get(f"{API}/today"))  # type: ignore[no-any-return]


def meal_status(kitchen: TestClient, meal_id: int) -> str:
    with db_of(kitchen) as db:
        meal = db.get(Meal, meal_id)
        assert meal is not None
        return meal.status


def tubs_left(kitchen: TestClient) -> list[dict[str, Any]]:
    return ok(kitchen.get(f"{API}/plan/tubs-left"))["tubs"]  # type: ignore[no-any-return]


# The answer word, and its route (D3, BE13: actions are imperative, kebab-case).
ROUTE = {"cooked": "mark-cooked", "didnt": "mark-not-cooked", "moved": "mark-moved"}


def answer(kitchen: TestClient, meal_id: int, what: str, body: Any = None, code: int = 200) -> Any:
    r = kitchen.post(f"{API}/plan/meals/{meal_id}/{ROUTE[what]}", json=body)
    assert r.status_code == code, r.text
    return r.json()


@pytest.fixture
def slots(kitchen: TestClient) -> dict[str, int]:
    return slot_ids(kitchen)


@pytest.fixture
def sambar(kitchen: TestClient) -> int:
    return new_recipe(kitchen, "Sambar")


@pytest.fixture
def yesterday(kitchen: TestClient, sambar: int, slots: dict[str, int]) -> dict[str, Any]:
    """Yesterday's dinner: Sambar, planned and not answered."""
    return plan_recipe(kitchen, sambar, ago(kitchen, 1), slots["Dinner"])


# --- Cooked it --------------------------------------------------------------------------------


def fridge_id(kitchen: TestClient) -> int:
    """Packets of a fridge ingredient have a Use by date (0.8); in a cupboard it is Best before,
    which Use soon counts only once passed."""
    return next(
        p["id"] for p in kitchen.get(f"{API}/places").json()["places"] if p["kind"] == "fridge"
    )


def test_cooked_it_marks_the_meal_and_locks_it(
    kitchen: TestClient, yesterday: dict[str, Any], slots: dict[str, int]
) -> None:
    meal = yesterday["meal_id"]
    done = answer(kitchen, meal, "cooked", {})
    assert meal_status(kitchen, meal) == "cooked" and done["meal_id"] == meal
    assert done["change"]["summary"].startswith("Cooked Sambar (Dinner on ")
    assert done["change"]["can_undo"]
    # Answered once: a second answer, a change to the plan and a move are all refused.
    assert answer(kitchen, meal, "cooked", {}, 409)["code"] == "meal_done"
    assert answer(kitchen, meal, "didnt", None, 409)["code"] == "meal_done"
    to = {"date": str(ahead(kitchen, 1)), "slot_id": slots["Dinner"]}
    assert answer(kitchen, meal, "moved", to, 409)["code"] == "meal_done"
    assert kitchen.delete(f"{API}/plan/meals/{meal}").status_code == 409
    assert tubs_left(kitchen) == []  # no leftovers asked for


def test_cooked_it_takes_nothing_from_the_pantry(
    kitchen: TestClient, slots: dict[str, int]
) -> None:
    rice = new_food(kitchen, "Today rice")
    ok(
        kitchen.post(
            f"{API}/stock", json={"food_id": rice["id"], "amount": {"amount": 500, "unit": "g"}}
        ),
        201,
    )
    pot = new_recipe(kitchen, "Pot rice", line(rice["id"], 200, "g"))
    meal = plan_recipe(kitchen, pot, ago(kitchen, 1), slots["Dinner"])["meal_id"]
    answer(kitchen, meal, "cooked", {})
    group = ok(kitchen.get(f"{API}/pantry"))["places"]
    amounts = [
        lot["stock"]
        for place in group
        for g in place["groups"]
        if g["food"]["id"] == rice["id"]
        for lot in g["lots"]
    ]
    assert len(amounts) == 1 and amounts[0]["amount"] == 500  # 0.7 will take the 200 g


def test_undo_of_cooked_it_asks_about_the_meal_again(
    kitchen: TestClient, yesterday: dict[str, Any]
) -> None:
    meal = yesterday["meal_id"]
    done = answer(kitchen, meal, "cooked", {})
    assert [w["meal_id"] for w in get_today(kitchen)["waiting"]] == []
    undo(kitchen, done)
    assert meal_status(kitchen, meal) == "planned"
    assert [w["meal_id"] for w in get_today(kitchen)["waiting"]] == [meal]
    answer(kitchen, meal, "cooked", {})  # it can be answered again
    assert meal_status(kitchen, meal) == "cooked"


def test_didnt_and_move_it_wait_for_the_meals_day_cooked_it_does_not(
    kitchen: TestClient, sambar: int, slots: dict[str, int]
) -> None:
    tomorrow = plan_recipe(kitchen, sambar, ahead(kitchen, 1), slots["Dinner"])["meal_id"]
    assert answer(kitchen, tomorrow, "didnt", None, 422)["code"] == "not_yet"
    to = {"date": str(ahead(kitchen, 2)), "slot_id": slots["Dinner"]}
    assert answer(kitchen, tomorrow, "moved", to, 422)["code"] == "not_yet"
    assert meal_status(kitchen, tomorrow) == "planned"
    # Today's own meal can be answered.
    todays = plan_recipe(kitchen, sambar, ahead(kitchen, 0), slots["Lunch"])["meal_id"]
    answer(kitchen, todays, "didnt")
    assert meal_status(kitchen, todays) == "didnt"


# --- Any left over? ---------------------------------------------------------------------------


def test_leftovers_make_tubs_in_the_fridge_with_the_households_tub_life(
    kitchen: TestClient, yesterday: dict[str, Any]
) -> None:
    meal = yesterday["meal_id"]
    done = answer(kitchen, meal, "cooked", {"leftovers": {"count": 2, "place_kind": "fridge"}})
    assert done["change"]["summary"].endswith("and kept 2 tubs of leftovers")
    tubs = tubs_left(kitchen)
    assert len(tubs) == 2
    # The default is 3 days in the fridge, counted from the day of the meal.
    assert {t["use_by"] for t in tubs} == {str(ago(kitchen, 1) + timedelta(days=3))}
    assert {(t["recipe_name"], t["place_kind"], t["amount_quarters"]) for t in tubs} == {
        ("Sambar", "fridge", 4)
    }
    assert sorted(t["number"] for t in tubs) == [1, 2] and {t["tub_count"] for t in tubs} == {2}
    # The batch cook is the meal's own, and its tubs are in no meal.
    with db_of(kitchen) as db:
        batch = db.scalars(select(BatchCook)).one()
        assert batch.cook_meal_id == meal and batch.cooked_on == ago(kitchen, 1)
        assert db.scalar(select(func.count(MealItem.id)).where(MealItem.tub_id.is_not(None))) == 0


def test_leftovers_in_the_freezer_with_a_chosen_use_by(
    kitchen: TestClient, yesterday: dict[str, Any]
) -> None:
    pick = str(ahead(kitchen, 40))
    body = {"leftovers": {"count": 1, "place_kind": "freezer", "use_by": pick}}
    answer(kitchen, yesterday["meal_id"], "cooked", body)
    (tub,) = tubs_left(kitchen)
    assert tub["place_kind"] == "freezer" and tub["use_by"] == pick
    # Without a date, the freezer's life: 3 months from the day of the meal.
    other = plan_recipe(
        kitchen, new_recipe(kitchen, "Dosa"), ago(kitchen, 2), slot_ids(kitchen)["Lunch"]
    )
    answer(
        kitchen, other["meal_id"], "cooked", {"leftovers": {"count": 1, "place_kind": "freezer"}}
    )
    freezer_default = next(t for t in tubs_left(kitchen) if t["recipe_name"] == "Dosa")
    assert freezer_default["use_by"] > str(ago(kitchen, 2) + timedelta(days=80))


def test_undo_of_leftovers_takes_the_tubs_and_the_batch_back(
    kitchen: TestClient, yesterday: dict[str, Any]
) -> None:
    done = answer(
        kitchen, yesterday["meal_id"], "cooked", {"leftovers": {"count": 3, "place_kind": "fridge"}}
    )
    assert len(tubs_left(kitchen)) == 3
    undo(kitchen, done)
    assert tubs_left(kitchen) == []
    with db_of(kitchen) as db:
        assert db.scalar(select(func.count(BatchCook.id))) == 0
        assert db.scalar(select(func.count(Tub.id))) == 0
    assert meal_status(kitchen, yesterday["meal_id"]) == "planned"


def test_leftovers_join_the_meals_own_batch_cook_and_undo_keeps_its_count(
    kitchen: TestClient, yesterday: dict[str, Any]
) -> None:
    meal = yesterday["meal_id"]
    with db_of(kitchen) as db:
        item = db.scalars(select(MealItem).where(MealItem.meal_id == meal)).one()
        batch = BatchCook(
            household_id=1,
            recipe_id=item.recipe_id,
            recipe_name="Sambar",
            cook_meal_id=meal,
            cooked_on=ago(kitchen, 1),
            tub_count=2,
            pattern="pick",
        )
        db.add(batch)
        db.flush()
        for _ in range(2):
            db.add(Tub(household_id=1, batch_id=batch.id, use_by=ahead(kitchen, 2)))
        db.commit()
    done = answer(kitchen, meal, "cooked", {"leftovers": {"count": 2, "place_kind": "fridge"}})
    with db_of(kitchen) as db:
        assert db.scalars(select(BatchCook)).one().tub_count == 4
        assert db.scalar(select(func.count(Tub.id))) == 4
    undo(kitchen, done)
    with db_of(kitchen) as db:
        assert db.scalars(select(BatchCook)).one().tub_count == 2
        assert db.scalar(select(func.count(Tub.id))) == 2


def test_leftovers_refusals(
    kitchen: TestClient, sambar: int, slots: dict[str, int], yesterday: dict[str, Any]
) -> None:
    banana = add_food_named(kitchen, "Today banana")
    fruit = ok(
        kitchen.post(
            f"{API}/plan/items",
            json={"date": str(ago(kitchen, 2)), "slot_id": slots["Lunch"], "food_id": banana},
        ),
        201,
    )
    # A meal with no recipe has nothing to keep; so does naming an ingredient.
    body = {"leftovers": {"count": 1}}
    assert answer(kitchen, fruit["meal_id"], "cooked", body, 422)["code"] == "no_recipe"
    body = {"leftovers": {"count": 1, "item_id": fruit["item_id"]}}
    assert answer(kitchen, fruit["meal_id"], "cooked", body, 422)["code"] == "no_recipe"
    # An item of another meal is not this meal's.
    body = {"leftovers": {"count": 1, "item_id": fruit["item_id"]}}
    assert answer(kitchen, yesterday["meal_id"], "cooked", body, 404)["code"] == "not_found"
    # How many: 1 to 12.
    for count in (0, 13):
        body = {"leftovers": {"count": count}}
        assert answer(kitchen, yesterday["meal_id"], "cooked", body, 422)
    # Nothing was changed by any refusal.
    assert meal_status(kitchen, yesterday["meal_id"]) == "planned" and tubs_left(kitchen) == []
    assert meal_status(kitchen, fruit["meal_id"]) == "planned"


def add_food_named(kitchen: TestClient, name: str) -> int:
    with db_of(kitchen) as db:
        food = add_food(db, 1, name)
        db.commit()
        return food.id


def test_a_batch_holds_at_most_twelve_tubs(kitchen: TestClient, yesterday: dict[str, Any]) -> None:
    meal = yesterday["meal_id"]
    with db_of(kitchen) as db:
        item = db.scalars(select(MealItem).where(MealItem.meal_id == meal)).one()
        batch = BatchCook(
            household_id=1,
            recipe_id=item.recipe_id,
            recipe_name="Sambar",
            cook_meal_id=meal,
            cooked_on=ago(kitchen, 1),
            tub_count=11,
            pattern="pick",
        )
        db.add(batch)
        db.flush()
        for _ in range(11):
            db.add(Tub(household_id=1, batch_id=batch.id, use_by=ahead(kitchen, 2)))
        db.commit()
    body = {"leftovers": {"count": 2}}
    assert answer(kitchen, meal, "cooked", body, 409)["code"] == "too_many_tubs"
    assert meal_status(kitchen, meal) == "planned"


# --- Didn't -----------------------------------------------------------------------------------


def test_didnt_marks_the_meal_and_takes_nothing(
    kitchen: TestClient, yesterday: dict[str, Any]
) -> None:
    meal = yesterday["meal_id"]
    done = answer(kitchen, meal, "didnt")
    assert meal_status(kitchen, meal) == "didnt"
    assert done["change"]["summary"].startswith("Didn’t cook Sambar (Dinner on ")
    assert tubs_left(kitchen) == []
    assert [w["meal_id"] for w in get_today(kitchen)["waiting"]] == []
    undo(kitchen, done)
    assert meal_status(kitchen, meal) == "planned"


def test_didnt_and_moved_meals_leave_the_shopping_list(
    kitchen: TestClient, slots: dict[str, int]
) -> None:
    rice = new_food(kitchen, "List rice")
    pot = new_recipe(kitchen, "List pot", line(rice["id"], 100, "g"))
    later = plan_recipe(kitchen, pot, ahead(kitchen, 2), slots["Dinner"])["meal_id"]
    todays = plan_recipe(kitchen, pot, ahead(kitchen, 0), slots["Lunch"])["meal_id"]
    assert plan_lines(kitchen) == [200]
    done = answer(kitchen, todays, "didnt")
    assert plan_lines(kitchen) == [100]  # today's meal no longer needs rice
    undo(kitchen, done)
    assert plan_lines(kitchen) == [200]
    # Moving today's meal to the day after tomorrow keeps its rice on the list (alongside).
    answer(kitchen, todays, "moved", {"date": str(ahead(kitchen, 2)), "slot_id": slots["Dinner"]})
    assert plan_lines(kitchen) == [200]
    assert meal_status(kitchen, later) == "planned"


# --- Move it ----------------------------------------------------------------------------------


def test_move_it_to_a_free_meal(
    kitchen: TestClient, yesterday: dict[str, Any], slots: dict[str, int]
) -> None:
    meal = yesterday["meal_id"]
    to = {"date": str(ahead(kitchen, 0)), "slot_id": slots["Dinner"]}
    done = answer(kitchen, meal, "moved", to)
    new = done["meal_id"]
    assert new != meal and meal_status(kitchen, meal) == "moved"
    assert meal_status(kitchen, new) == "planned"
    assert done["change"]["summary"].startswith("Moved Sambar from Dinner on ")
    names = [
        i["recipe"]["name"]
        for m in ok(
            kitchen.get(
                f"{API}/plan", params={"from": str(ago(kitchen, 2)), "to": str(ahead(kitchen, 1))}
            )
        )["meals"]
        if m["id"] == new
        for i in m["items"]
    ]
    assert names == ["Sambar"]
    # The old meal still holds its slot: nothing can be planned there now.
    again = kitchen.post(
        f"{API}/plan/items",
        json={
            "date": str(ago(kitchen, 1)),
            "slot_id": slots["Dinner"],
            "recipe_id": new_recipe(kitchen, "Dosa"),
        },
    )
    assert again.status_code == 409
    # And it isn't asked about again.
    assert [w["meal_id"] for w in get_today(kitchen)["waiting"]] == []


def test_move_it_onto_a_meal_that_has_food_adds_alongside(
    kitchen: TestClient, yesterday: dict[str, Any], slots: dict[str, int]
) -> None:
    dosa = new_recipe(kitchen, "Dosa")
    target = plan_recipe(kitchen, dosa, ahead(kitchen, 1), slots["Lunch"])["meal_id"]
    to = {"date": str(ahead(kitchen, 1)), "slot_id": slots["Lunch"]}
    done = answer(kitchen, yesterday["meal_id"], "moved", to)
    assert done["meal_id"] == target
    with db_of(kitchen) as db:
        names = sorted(
            i.name or "" for i in db.scalars(select(MealItem).where(MealItem.meal_id == target))
        )
    assert names == ["Dosa", "Sambar"]
    # Undo takes only what was added, and asks about the meal again.
    undo(kitchen, done)
    with db_of(kitchen) as db:
        left = [i.name for i in db.scalars(select(MealItem).where(MealItem.meal_id == target))]
    assert left == ["Dosa"]
    assert meal_status(kitchen, yesterday["meal_id"]) == "planned"
    assert meal_status(kitchen, target) == "planned"


def test_move_it_undo_removes_the_meal_it_made(
    kitchen: TestClient, yesterday: dict[str, Any], slots: dict[str, int]
) -> None:
    to = {"date": str(ahead(kitchen, 3)), "slot_id": slots["Breakfast"]}
    done = answer(kitchen, yesterday["meal_id"], "moved", to)
    undo(kitchen, done)
    with db_of(kitchen) as db:
        assert db.get(Meal, done["meal_id"]) is None
    assert meal_status(kitchen, yesterday["meal_id"]) == "planned"


def test_move_it_takes_a_tub_with_it(
    kitchen: TestClient, sambar: int, slots: dict[str, int]
) -> None:
    # Cooked three days ago: the tub can then sit at a meal two days ago (after the cooking, F230)
    # and that meal is long past, so it can be moved at any hour.
    meal = plan_recipe(kitchen, sambar, ago(kitchen, 3), slots["Dinner"])["meal_id"]
    answer(kitchen, meal, "cooked", {"leftovers": {"count": 1}})  # a tub exists (and meal locked)
    tub_id = tubs_left(kitchen)[0]["id"]
    other = plan_recipe(kitchen, new_recipe(kitchen, "Dosa"), ago(kitchen, 2), slots["Lunch"])
    placed = kitchen.post(
        f"{API}/plan/tubs/{tub_id}/place",
        json={"date": str(ago(kitchen, 2)), "slot_id": slots["Lunch"]},
    )
    assert placed.status_code == 200, placed.text
    to = {"date": str(ahead(kitchen, 0)), "slot_id": slots["Lunch"]}
    done = answer(kitchen, other["meal_id"], "moved", to)
    with db_of(kitchen) as db:
        moved_tub = db.scalars(select(MealItem).where(MealItem.tub_id == tub_id)).one()
        assert moved_tub.meal_id == done["meal_id"]
    undo(kitchen, done)
    with db_of(kitchen) as db:
        back = db.scalars(select(MealItem).where(MealItem.tub_id == tub_id)).one()
        assert back.meal_id == other["meal_id"]


def test_move_it_refusals(
    kitchen: TestClient, yesterday: dict[str, Any], slots: dict[str, int]
) -> None:
    meal = yesterday["meal_id"]
    same = {"date": str(ago(kitchen, 1)), "slot_id": slots["Dinner"]}
    assert answer(kitchen, meal, "moved", same, 409)["code"] == "already_there"
    far = {"date": str(ahead(kitchen, 5000)), "slot_id": slots["Dinner"]}
    assert answer(kitchen, meal, "moved", far, 422)["code"] == "bad_day"
    # Not to a past day: that would only make another meal waiting for an answer.
    past = {"date": str(ago(kitchen, 2)), "slot_id": slots["Dinner"]}
    assert answer(kitchen, meal, "moved", past, 422)["code"] == "past_day"
    # A meal that is switched off.
    ok(kitchen.patch(f"{API}/meal-slots/{slots['Lunch']}", json={"enabled": False}))
    off = {"date": str(ahead(kitchen, 1)), "slot_id": slots["Lunch"]}
    assert answer(kitchen, meal, "moved", off, 422)["code"] == "slot_off"
    # A meal there that has been dealt with.
    dosa = new_recipe(kitchen, "Dosa")
    done = plan_recipe(kitchen, dosa, ahead(kitchen, 0), slots["Dinner"])["meal_id"]
    answer(kitchen, done, "didnt")
    taken = {"date": str(ahead(kitchen, 0)), "slot_id": slots["Dinner"]}
    assert answer(kitchen, meal, "moved", taken, 409)["code"] == "meal_done"
    # A full meal.
    crowd = plan_recipe(kitchen, dosa, ahead(kitchen, 2), slots["Dinner"])["meal_id"]
    with db_of(kitchen) as db:
        for _ in range(19):
            db.add(MealItem(household_id=1, meal_id=crowd, position=1, recipe_id=1))
        db.commit()
    full = {"date": str(ahead(kitchen, 2)), "slot_id": slots["Dinner"]}
    assert answer(kitchen, meal, "moved", full, 409)["code"] == "too_many_items"
    assert meal_status(kitchen, meal) == "planned"


def test_an_idempotent_retry_answers_once(kitchen: TestClient, yesterday: dict[str, Any]) -> None:
    key = {"Idempotency-Key": "answer-1"}
    first = kitchen.post(f"{API}/plan/meals/{yesterday['meal_id']}/mark-not-cooked", headers=key)
    again = kitchen.post(f"{API}/plan/meals/{yesterday['meal_id']}/mark-not-cooked", headers=key)
    assert first.status_code == again.status_code == 200
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["change"]["id"] == first.json()["change"]["id"]


# --- The read ---------------------------------------------------------------------------------


def test_waiting_meals_are_planned_days_before_today_newest_first_a_week_back(
    kitchen: TestClient, sambar: int, slots: dict[str, int]
) -> None:
    made = {
        (n, s): plan_recipe(kitchen, sambar, ago(kitchen, n), slots[s])["meal_id"]
        for n, s in ((1, "Lunch"), (1, "Dinner"), (3, "Dinner"), (7, "Dinner"), (8, "Dinner"))
    }
    todays = plan_recipe(kitchen, sambar, ahead(kitchen, 0), slots["Dinner"])["meal_id"]
    out = get_today(kitchen)
    ids = [w["meal_id"] for w in out["waiting"]]
    # Yesterday's dinner, yesterday's lunch, 3 days ago, 7 days ago; not 8 days ago, not today.
    assert ids == [
        made[(1, "Dinner")],
        made[(1, "Lunch")],
        made[(3, "Dinner")],
        made[(7, "Dinner")],
    ]
    assert todays not in ids
    first = out["waiting"][0]
    assert first["leftover_item_id"] is not None
    assert first["use_by_fridge"] == str(ago(kitchen, 1) + timedelta(days=3))
    assert first["use_by_freezer"] > first["use_by_fridge"]
    # The plan in the answer holds those meals and today's, with their items.
    in_plan = {m["id"] for m in out["plan"]["meals"]}
    assert set(ids) | {todays} <= in_plan


def test_a_meal_in_a_switched_off_slot_is_not_asked_about(
    kitchen: TestClient, sambar: int, slots: dict[str, int]
) -> None:
    plan_recipe(kitchen, sambar, ago(kitchen, 1), slots["Lunch"])
    ok(kitchen.patch(f"{API}/meal-slots/{slots['Lunch']}", json={"enabled": False}))
    out = get_today(kitchen)
    assert out["waiting"] == [] and [s["name"] for s in out["slots"]] == [
        "Breakfast",
        "Dinner",
    ]


def test_today_and_the_pantry_count_use_soon_the_same_way(kitchen: TestClient, sambar: int) -> None:
    """F203: two tubs of one batch that are both Use soon are one thing on Today, as on the
    Pantry, so the two screens give the same number."""
    with db_of(kitchen) as db:
        batch = BatchCook(
            household_id=1,
            recipe_id=sambar,
            recipe_name="Sambar",
            cooked_on=ago(kitchen, 2),
            tub_count=3,
            pattern="pick",
        )
        db.add(batch)
        db.flush()
        for days in (0, 1, 1):
            db.add(Tub(household_id=1, batch_id=batch.id, use_by=ahead(kitchen, days)))
        db.commit()
    paneer = new_food(kitchen, "Count paneer", place_id=fridge_id(kitchen))
    ok(
        kitchen.post(
            f"{API}/stock",
            json={
                "food_id": paneer["id"],
                "amount": {"amount": 200, "unit": "g"},
                "use_by": str(ahead(kitchen, 1)),
            },
        ),
        201,
    )
    out = get_today(kitchen)
    on_today = len(out["use_soon_lots"]) + len(out["use_soon_tubs"])
    assert len(out["use_soon_tubs"]) == 1 and out["use_soon_tubs"][0]["tubs"] == 3
    assert on_today == 2
    assert kitchen.get(f"{API}/pantry").json()["counts"]["use_soon"] == on_today


def test_today_reads_tubs_use_soon_and_the_next_cook(
    kitchen: TestClient, sambar: int, slots: dict[str, int]
) -> None:
    out = get_today(kitchen)
    assert out["tubs_left"] == [] and out["use_soon_lots"] == [] and out["next_cook"] is None
    # Tubs: one that goes off tomorrow, one in a month.
    with db_of(kitchen) as db:
        batch = BatchCook(
            household_id=1,
            recipe_id=sambar,
            recipe_name="Sambar",
            cooked_on=ago(kitchen, 2),
            tub_count=2,
            pattern="pick",
        )
        db.add(batch)
        db.flush()
        db.add(Tub(household_id=1, batch_id=batch.id, use_by=ahead(kitchen, 1)))
        db.add(Tub(household_id=1, batch_id=batch.id, use_by=ahead(kitchen, 30)))
        db.commit()
    # A packet of paneer that goes off today.
    paneer = new_food(kitchen, "Today paneer", place_id=fridge_id(kitchen))
    ok(
        kitchen.post(
            f"{API}/stock",
            json={
                "food_id": paneer["id"],
                "amount": {"amount": 200, "unit": "g"},
                "use_by": str(ahead(kitchen, 0)),
            },
        ),
        201,
    )
    # A cook-once planned in three days.
    biryani = new_recipe(kitchen, "Biryani")
    cook = plan_recipe(kitchen, biryani, ahead(kitchen, 3), slots["Dinner"])
    ok(kitchen.post(f"{API}/plan/items/{cook['item_id']}/batch", json={"tub_count": 4}), 201)
    out = get_today(kitchen)
    # The two made by hand, and the four of the cook-once (the pattern puts none in a meal).
    assert len(out["tubs_left"]) == 6 and out["tubs_left_next"] is None
    # One row for the batch, soonest date first, counting both of its tubs (F203).
    assert [(t["use_by"], t["tubs"], t["words"]) for t in out["use_soon_tubs"]] == [
        (str(ahead(kitchen, 1)), 2, "2 tubs")
    ]
    assert [lot["food"]["name"] for lot in out["use_soon_lots"]] == ["Today paneer"]
    assert out["next_cook"]["recipe_name"] == "Biryani" and out["next_cook"]["tub_count"] == 4
    assert out["next_cook"]["date"] == str(ahead(kitchen, 3))
    assert out["today"] == str(household_day(kitchen))


def test_first_day_is_only_for_a_household_with_nothing(
    kitchen: TestClient, slots: dict[str, int]
) -> None:
    assert get_today(kitchen)["first_day"] is True
    recipe = new_recipe(kitchen, "Sambar")
    assert get_today(kitchen)["first_day"] is False  # a recipe is enough
    ok(kitchen.delete(f"{API}/recipes/{recipe}"))
    assert get_today(kitchen)["first_day"] is True  # removed: nothing there again
    plan_recipe(kitchen, new_recipe(kitchen, "Dosa"), ahead(kitchen, 4), slots["Dinner"])
    assert get_today(kitchen)["first_day"] is False


def test_first_day_counts_pantry_stock_too(kitchen: TestClient) -> None:
    rice = new_food(kitchen, "First rice")
    assert get_today(kitchen)["first_day"] is True  # an ingredient alone is not stock
    ok(
        kitchen.post(
            f"{API}/stock", json={"food_id": rice["id"], "amount": {"amount": 1, "unit": "kg"}}
        ),
        201,
    )
    assert get_today(kitchen)["first_day"] is False


# --- The household's own day ------------------------------------------------------------------


def at(monkeypatch: pytest.MonkeyPatch, moment: datetime) -> None:
    monkeypatch.setattr(household_module, "utcnow", lambda: moment)


def set_zone(kitchen: TestClient, zone: str) -> None:
    with db_of(kitchen) as db:
        db.get(Household, 1).time_zone = zone  # type: ignore[union-attr]
        db.commit()


def test_a_household_ahead_of_utc_is_already_in_tomorrow(
    kitchen: TestClient, sambar: int, slots: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    set_zone(kitchen, "Pacific/Auckland")  # UTC+13 in the southern summer
    at(monkeypatch, datetime(2027, 1, 10, 20, 0, tzinfo=UTC))  # 11 Jan, 09:00 in Auckland
    out = get_today(kitchen)
    assert out["today"] == "2027-01-11"
    # The 10th (UTC's today) is already yesterday there: its dinner is waiting.
    meal = plan_recipe(kitchen, sambar, date(2027, 1, 10), slots["Dinner"])["meal_id"]
    assert [w["meal_id"] for w in get_today(kitchen)["waiting"]] == [meal]
    answer(kitchen, meal, "didnt")
    # A meal on the 11th is today's: not waiting, but it can be answered.
    today_meal = plan_recipe(kitchen, sambar, date(2027, 1, 11), slots["Dinner"])["meal_id"]
    assert get_today(kitchen)["waiting"] == []
    answer(kitchen, today_meal, "didnt")


def test_a_household_behind_utc_is_still_in_yesterday(
    kitchen: TestClient, sambar: int, slots: dict[str, int], monkeypatch: pytest.MonkeyPatch
) -> None:
    set_zone(kitchen, "America/Los_Angeles")  # UTC-8 in winter
    at(monkeypatch, datetime(2027, 1, 11, 3, 0, tzinfo=UTC))  # still 10 Jan, 19:00 there
    out = get_today(kitchen)
    assert out["today"] == "2027-01-10"
    meal = plan_recipe(kitchen, sambar, date(2027, 1, 10), slots["Dinner"])["meal_id"]
    assert get_today(kitchen)["waiting"] == []  # the 10th is today, not over
    # The 11th is tomorrow for them, even though UTC is there: it can't be answered yet.
    later = plan_recipe(kitchen, sambar, date(2027, 1, 11), slots["Dinner"])["meal_id"]
    assert answer(kitchen, later, "didnt", None, 422)["code"] == "not_yet"
    answer(kitchen, meal, "didnt")  # but today's can
    # An hour past their midnight the 10th has become yesterday.
    at(monkeypatch, datetime(2027, 1, 11, 8, 30, tzinfo=UTC))  # 00:30 on the 11th there
    other = plan_recipe(kitchen, sambar, date(2027, 1, 10), slots["Lunch"])["meal_id"]
    assert [w["meal_id"] for w in get_today(kitchen)["waiting"]] == [other]


def test_use_soon_follows_the_households_day(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    set_zone(kitchen, "Pacific/Auckland")
    at(monkeypatch, datetime(2027, 1, 10, 20, 0, tzinfo=UTC))  # 11 Jan there
    paneer = new_food(kitchen, "Zone paneer", place_id=fridge_id(kitchen))
    ok(
        kitchen.post(
            f"{API}/stock",
            json={
                "food_id": paneer["id"],
                "amount": {"amount": 200, "unit": "g"},
                "use_by": "2027-01-13",  # two days after their today: use soon
            },
        ),
        201,
    )
    cheese = new_food(kitchen, "Zone cheese", place_id=fridge_id(kitchen))
    ok(
        kitchen.post(
            f"{API}/stock",
            json={
                "food_id": cheese["id"],
                "amount": {"amount": 200, "unit": "g"},
                "use_by": "2027-01-14",  # three days: not yet
            },
        ),
        201,
    )
    assert [lot["food"]["name"] for lot in get_today(kitchen)["use_soon_lots"]] == ["Zone paneer"]


# --- Another household ------------------------------------------------------------------------


def test_another_households_ids_get_404_and_nothing_changes(
    kitchen: TestClient, neighbour: TestClient, yesterday: dict[str, Any], slots: dict[str, int]
) -> None:
    meal = yesterday["meal_id"]
    theirs = slot_ids(kitchen, 2)
    to = {"date": str(ahead(kitchen, 1)), "slot_id": slots["Dinner"]}
    for what, body in (("cooked", {}), ("didnt", None), ("moved", to)):
        r = neighbour.post(f"{API}/plan/meals/{meal}/{ROUTE[what]}", json=body)
        assert r.status_code == 404 and r.json()["code"] == "not_found", what
    # My meal, their slot.
    their_slot = {"date": str(ahead(kitchen, 1)), "slot_id": theirs["Dinner"]}
    assert answer(kitchen, meal, "moved", their_slot, 404)["code"] == "not_found"
    # My meal, their recipe item (the item ids of another household are never accepted).
    # My meal, their item (a recipe planned in their household).
    theirs_recipe = new_recipe(neighbour, "Their sambar")
    their_item = plan_recipe(neighbour, theirs_recipe, ago(neighbour, 1), theirs["Dinner"])
    body = {"leftovers": {"count": 1, "item_id": their_item["item_id"]}}
    assert answer(kitchen, meal, "cooked", body, 404)["code"] == "not_found"
    assert meal_status(kitchen, meal) == "planned"
    # The neighbour's Today has none of my meals, tubs or packets: only their own meal.
    out = get_today(neighbour)
    assert [w["meal_id"] for w in out["waiting"]] == [their_item["meal_id"]]
    assert [m["id"] for m in out["plan"]["meals"]] == [their_item["meal_id"]]
    assert meal not in [w["meal_id"] for w in out["waiting"]] and out["tubs_left"] == []


def test_undo_of_older_leftovers_keeps_a_tub_added_since(
    kitchen: TestClient, yesterday: dict[str, Any]
) -> None:
    """F165 (review r1 L3): Undo of an older "Any left over?" takes off only its own tubs from
    the batch's count; a tub added since stays counted."""
    meal = yesterday["meal_id"]
    with db_of(kitchen) as db:
        item = db.scalars(select(MealItem).where(MealItem.meal_id == meal)).one()
        batch = BatchCook(
            household_id=1,
            recipe_id=item.recipe_id,
            recipe_name="Sambar",
            cook_meal_id=meal,
            cooked_on=ago(kitchen, 1),
            tub_count=2,
            pattern="pick",
        )
        db.add(batch)
        db.flush()
        for _ in range(2):
            db.add(Tub(household_id=1, batch_id=batch.id, use_by=ahead(kitchen, 2)))
        db.commit()
    done = answer(kitchen, meal, "cooked", {"leftovers": {"count": 2, "place_kind": "fridge"}})
    with db_of(kitchen) as db:  # a later change adds one more tub to the same batch
        batch = db.scalars(select(BatchCook)).one()
        db.add(Tub(household_id=1, batch_id=batch.id, use_by=ahead(kitchen, 2)))
        batch.tub_count = 5
        db.commit()
    undo(kitchen, done)
    with db_of(kitchen) as db:
        assert db.scalar(select(func.count(Tub.id))) == 3
        assert db.scalars(select(BatchCook)).one().tub_count == 3


# --- Move it asks the start time again (FX5) ---------------------------------------------------


def _dosa_yesterday(kitchen: TestClient, slots: dict[str, int]) -> tuple[int, int]:
    from test_start_ahead import dosa

    written = plan_recipe(kitchen, dosa(kitchen)["id"], ago(kitchen, 1), slots["Dinner"])
    return written["meal_id"], written["item_id"]


def _starts_on(kitchen: TestClient, day: date) -> list[tuple[str | None, str | None]]:
    plan_view = ok(kitchen.get(f"{API}/plan", params={"from": str(day), "to": str(day)}))
    return [
        (i["ahead"]["start_day"], i["ahead"]["start_time"])
        for m in plan_view["meals"]
        for i in m["items"]
        if i["ahead"]
    ]


def test_move_it_takes_the_start_time_of_a_recipe_with_a_long_wait_and_undo_takes_it_away(
    kitchen: TestClient, slots: dict[str, int]
) -> None:
    meal, item = _dosa_yesterday(kitchen, slots)
    day = ahead(kitchen, 2)
    eve = {"day": str(day - timedelta(days=1)), "time": "21:00"}
    to = {"date": str(day), "slot_id": slots["Breakfast"]}
    # Refused ones change nothing: a bad day, an item that is not in the meal, one named twice.
    far = {"item_id": item, "day": "9999-12-31", "time": "23:59"}
    assert answer(kitchen, meal, "moved", {**to, "starts": [far]}, 422)["code"] == "bad_start"
    stray = {"item_id": item + 999, **eve}
    assert (
        answer(kitchen, meal, "moved", {**to, "starts": [stray]}, 422)["code"] == "start_not_moved"
    )
    twice = [{"item_id": item, **eve}, {"item_id": item, "day": eve["day"], "time": "20:00"}]
    answer(kitchen, meal, "moved", {**to, "starts": twice}, 422)
    assert meal_status(kitchen, meal) == "planned"
    done = answer(kitchen, meal, "moved", {**to, "starts": [{"item_id": item, **eve}]})
    assert _starts_on(kitchen, day) == [(eve["day"], "21:00")]
    undo(kitchen, done)
    assert _starts_on(kitchen, day) == []
    assert meal_status(kitchen, meal) == "planned"


def test_move_it_with_no_start_time_leaves_the_recipe_with_none(
    kitchen: TestClient, slots: dict[str, int]
) -> None:
    meal, _item = _dosa_yesterday(kitchen, slots)
    day = ahead(kitchen, 2)
    answer(kitchen, meal, "moved", {"date": str(day), "slot_id": slots["Breakfast"]})
    assert _starts_on(kitchen, day) == [(None, None)]


def test_move_it_refuses_a_start_for_a_recipe_with_no_wait_or_for_another_households_item(
    kitchen: TestClient,
    neighbour: TestClient,
    yesterday: dict[str, Any],
    slots: dict[str, int],
) -> None:
    from test_start_ahead import dosa

    meal, item = yesterday["meal_id"], yesterday["item_id"]
    to = {"date": str(ahead(kitchen, 2)), "slot_id": slots["Breakfast"]}
    day = str(ahead(kitchen, 1))
    no_wait = answer(
        kitchen,
        meal,
        "moved",
        {**to, "starts": [{"item_id": item, "day": day, "time": "21:00"}]},
        422,
    )
    assert no_wait["code"] == "no_wait"
    # An item of the other household is not in this meal: refused the same way, nothing leaks.
    theirs = plan_recipe(
        neighbour, dosa(neighbour)["id"], ago(neighbour, 1), slot_ids(neighbour, 2)["Dinner"]
    )["item_id"]
    other = answer(
        kitchen,
        meal,
        "moved",
        {**to, "starts": [{"item_id": theirs, "day": day, "time": "21:00"}]},
        422,
    )
    assert other["code"] == "start_not_moved"
    assert meal_status(kitchen, meal) == "planned"


# --- Whole-0.8 review fixes (RF3): H2 ------------------------------------------------------------


def test_move_it_keeps_a_long_wait_that_was_already_started(
    kitchen: TestClient, slots: dict[str, int]
) -> None:
    """H2: the batter was started on Friday night ("Done already"); Move it on a meal not cooked
    must not forget it (a move on the Plan keeps it), and Undo takes the moved meal away."""
    soaked = make(
        kitchen,
        "Moveit dosa",
        steps=[
            {
                "text": "Soak the rice and dal, grind and leave it.",
                "wait": {"kind": "ferment", "min_minutes": 480, "max_minutes": 720},
            },
            {"text": "Make the dosas."},
        ],
    )
    yesterday = ago(kitchen, 1)
    added = plan_recipe(kitchen, soaked["id"], yesterday, slots["Breakfast"])
    started = kitchen.patch(f"{API}/plan/items/{added['item_id']}", json={"started": True})
    assert started.status_code == 200, started.text
    to = {"date": str(ahead(kitchen, 1)), "slot_id": slots["Breakfast"]}
    done = answer(kitchen, added["meal_id"], "moved", to)
    plan = ok(
        kitchen.get(f"{API}/plan", params={"from": str(yesterday), "to": str(ahead(kitchen, 2))})
    )
    (copy,) = next(m for m in plan["meals"] if m["id"] == done["meal_id"])["items"]
    assert copy["ahead"]["started_time"] is not None


def test_a_wait_of_more_than_a_week_still_gets_its_start_card_on_today(
    kitchen: TestClient, slots: dict[str, int]
) -> None:
    """H6: Today read meals up to 6 days ahead, so a recipe that waits 8 or 9 days (a cure) and
    is started today for a meal 9 days on had no Start card. The rule for Today and the Plan
    alike: read as far past the edge as the longest start can reach (start_ahead.MOST_DAYS_AHEAD,
    11 days)."""
    cure = make(
        kitchen,
        "Cure lemons",
        steps=[
            {
                "text": "Pack the lemons in salt and leave them.",
                "wait": {"kind": "rest", "min_minutes": 8 * 1440, "max_minutes": 9 * 1440},
            },
            {"text": "Rinse and serve."},
        ],
    )
    meal_day = ahead(kitchen, 9)
    start = {"day": str(ahead(kitchen, 0)), "time": "23:00"}
    added = plan_recipe(kitchen, cure["id"], meal_day, slots["Dinner"], start=start)
    found = [m for m in get_today(kitchen)["plan"]["meals"] if m["id"] == added["meal_id"]]
    assert found and found[0]["items"][0]["ahead"]["start_day"] == str(ahead(kitchen, 0))
