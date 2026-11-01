"""Portions (0.7, P1; cabledrawer 28 Oct): a batch makes a fixed number of portions, its tubs plus the
cook-day meal. "Leftovers on…" ticks several meals at once; when none are left the server says so
and the person picks Cook more or Add anyway. Plan changes are online only (spec section 2), so
"two phones" are two requests with their own Idempotency-Keys."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_plan import add_recipe, db_of, slot_ids
from test_plan_batches import day, make, where_tubs_are
from test_plan_writes import D1, plan_recipe, shape, undo, view

from mealwright.models import MealItem, Tub

API = "/api/v1"


@pytest.fixture
def slots(kitchen: TestClient) -> dict[str, int]:
    return slot_ids(kitchen)


@pytest.fixture
def biryani(kitchen: TestClient) -> int:
    with db_of(kitchen) as db:
        recipe = add_recipe(db, 1, "Veg biryani")
        db.commit()
        return recipe.id


@pytest.fixture
def cook(kitchen: TestClient, biryani: int, slots: dict[str, int]) -> dict[str, Any]:
    """Veg biryani planned for dinner on D1."""
    return plan_recipe(kitchen, biryani, D1, slots["Dinner"])


def spot(n: int, slots: dict[str, int], slot: str = "Lunch") -> dict[str, Any]:
    return {"date": day(n), "slot_id": slots[slot]}


def leftovers(client: TestClient, item_id: int, meals: list[dict[str, Any]], **body: Any) -> Any:
    return client.post(f"{API}/plan/items/{item_id}/leftovers", json={"meals": meals, **body})


def portions(client: TestClient, item_id: int) -> dict[str, Any]:
    r = client.get(f"{API}/plan/items/{item_id}/portions")
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


# --- What a batch makes ---------------------------------------------------------------------------


def test_a_batch_makes_its_tubs_plus_the_cook_day_meal(
    kitchen: TestClient, cook: dict[str, Any]
) -> None:
    make(kitchen, cook["item_id"], tub_count=3, pattern="pick")
    batch = view(kitchen)["batch_cooks"][0]
    assert (batch["portions"], batch["portions_left"]) == (4, 3)
    got = portions(kitchen, cook["item_id"])
    assert got["has_batch"] and (got["portions"], got["cook_day"], got["tubs"]) == (4, 1, 3)
    assert (got["in_meals"], got["left"]) == (0, 3)


def test_the_cook_day_meal_counts_its_own_servings(
    kitchen: TestClient, biryani: int, slots: dict[str, int]
) -> None:
    four = plan_recipe(kitchen, biryani, D1, slots["Dinner"], servings=4)
    make(kitchen, four["item_id"], tub_count=2)
    assert view(kitchen)["batch_cooks"][0]["portions"] == 6  # 4 eating now plus 2 tubs
    assert portions(kitchen, four["item_id"])["cook_day"] == 4


def test_tubs_in_meals_are_not_left(kitchen: TestClient, cook: dict[str, Any]) -> None:
    make(kitchen, cook["item_id"], tub_count=3, pattern="lunches")
    got = portions(kitchen, cook["item_id"])
    assert (got["portions"], got["in_meals"], got["left"]) == (4, 3, 0)
    assert view(kitchen)["batch_cooks"][0]["portions_left"] == 0


def test_a_recipe_with_no_batch_yet_has_no_count(kitchen: TestClient, cook: dict[str, Any]) -> None:
    got = portions(kitchen, cook["item_id"])
    assert got["has_batch"] is False and got["portions"] is None and got["left"] is None
    assert got["use_by"] == (D1 + timedelta(days=3)).isoformat()


def test_only_a_recipe_has_portions(kitchen: TestClient, cook: dict[str, Any]) -> None:
    make(kitchen, cook["item_id"], tub_count=1, pattern="lunches")
    tub_item = next(
        i["id"] for m in view(kitchen)["meals"] for i in m["items"] if i["kind"] == "tub"
    )
    assert kitchen.get(f"{API}/plan/items/{tub_item}/portions").status_code == 422


# --- Several meals at once ------------------------------------------------------------------------


def test_leftovers_on_several_meals_takes_the_portions_left(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    make(kitchen, cook["item_id"], tub_count=3, pattern="pick")
    before = shape(kitchen)
    done = leftovers(
        kitchen,
        cook["item_id"],
        [spot(2, slots, "Dinner"), spot(1, slots), spot(1, slots, "Dinner")],
    )
    assert done.status_code == 200, done.text
    assert where_tubs_are(kitchen, slots) == [
        (1, day(1), "Lunch"),
        (2, day(1), "Dinner"),
        (3, day(2), "Dinner"),
    ]
    assert portions(kitchen, cook["item_id"])["left"] == 0
    assert "leftovers" in done.json()["change"]["summary"]
    assert undo(kitchen, done.json())["result"] == "done"
    assert shape(kitchen) == before
    assert portions(kitchen, cook["item_id"])["left"] == 3


def test_leftovers_with_no_batch_yet_make_one_tub_per_meal(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    done = leftovers(kitchen, cook["item_id"], [spot(1, slots), spot(2, slots)])
    assert done.status_code == 200, done.text
    batch = view(kitchen)["batch_cooks"][0]
    # The meal was planned for the recipe's own 4 (made explicit now, F58), plus the two tubs.
    assert (batch["tub_count"], batch["portions"], batch["portions_left"]) == (2, 6, 0)
    assert undo(kitchen, done.json())["result"] == "done"
    assert view(kitchen)["batch_cooks"] == []


def test_only_meals_after_the_cook_and_before_the_use_by_are_accepted(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    make(kitchen, cook["item_id"], tub_count=2, pattern="pick")
    # The cook day's lunch comes before the cook meal (dinner); the day after the use-by is late.
    early = leftovers(kitchen, cook["item_id"], [spot(0, slots)])
    assert early.status_code == 422 and early.json()["code"] == "not_after_cook"
    late = leftovers(kitchen, cook["item_id"], [spot(4, slots)])
    assert late.status_code == 422 and late.json()["code"] == "after_use_by"
    last = leftovers(kitchen, cook["item_id"], [spot(3, slots, "Dinner")])  # the use-by day itself
    assert last.status_code == 200, last.text
    # A refused tick changes nothing.
    assert [t for t in where_tubs_are(kitchen, slots) if t[1]] == [(1, day(3), "Dinner")]


def test_the_use_by_follows_the_households_tub_life(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    from mealwright.models import Household

    with db_of(kitchen) as db:
        household = db.get(Household, 1)
        assert household is not None
        household.tub_fridge_days = 5
        db.commit()
    make(kitchen, cook["item_id"], tub_count=1, pattern="pick")
    assert portions(kitchen, cook["item_id"])["use_by"] == day(5)
    assert leftovers(kitchen, cook["item_id"], [spot(5, slots)]).status_code == 200


def test_a_bad_tick_is_refused(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    twice = leftovers(kitchen, cook["item_id"], [spot(1, slots), spot(1, slots)])
    assert twice.status_code == 422 and twice.json()["code"] == "same_meal_twice"
    nothing = leftovers(kitchen, cook["item_id"], [])
    assert nothing.status_code == 422
    assert view(kitchen)["batch_cooks"] == []
    ingredient = kitchen.post(
        f"{API}/plan/items", json={"date": day(0), "slot_id": slots["Lunch"], "recipe_id": None}
    )
    assert ingredient.status_code == 422


# --- No portions left -----------------------------------------------------------------------------


@pytest.fixture
def used_up(kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]) -> dict[str, Any]:
    """One tub, already in tomorrow's lunch: nothing left."""
    make(kitchen, cook["item_id"], tub_count=1, pattern="lunches")
    assert portions(kitchen, cook["item_id"])["left"] == 0
    return cook


def test_with_none_left_the_answer_says_so_and_nothing_changes(
    kitchen: TestClient, used_up: dict[str, Any], slots: dict[str, int]
) -> None:
    before = (shape(kitchen), view(kitchen)["batch_cooks"])
    r = leftovers(kitchen, used_up["item_id"], [spot(2, slots)])
    assert r.status_code == 409, r.text
    body = r.json()
    assert body["code"] == "no_portions_left" and body["left"] == 0 and body["wanted"] == 1
    assert (shape(kitchen), view(kitchen)["batch_cooks"]) == before


def test_cook_more_makes_the_batch_bigger(
    kitchen: TestClient, used_up: dict[str, Any], slots: dict[str, int]
) -> None:
    done = leftovers(kitchen, used_up["item_id"], [spot(2, slots)], if_none_left="cook_more")
    assert done.status_code == 200, done.text
    batch = view(kitchen)["batch_cooks"][0]
    assert (batch["tub_count"], batch["portions"], batch["portions_left"]) == (2, 3, 0)
    assert undo(kitchen, done.json())["result"] == "done"
    assert view(kitchen)["batch_cooks"][0]["tub_count"] == 1


def test_add_anyway_plans_the_recipe_and_leaves_the_batch(
    kitchen: TestClient, used_up: dict[str, Any], slots: dict[str, int]
) -> None:
    done = leftovers(kitchen, used_up["item_id"], [spot(2, slots)], if_none_left="add_anyway")
    assert done.status_code == 200, done.text
    plan = view(kitchen)
    batch = plan["batch_cooks"][0]
    assert (batch["tub_count"], batch["portions"]) == (1, 2)
    meal = next(m for m in plan["meals"] if m["date"] == day(2))
    assert [(i["kind"], i["servings"]) for i in meal["items"]] == [("recipe", 1)]
    assert undo(kitchen, done.json())["result"] == "done"
    assert all(m["date"] != day(2) for m in view(kitchen)["meals"])


def test_some_left_some_short_the_earliest_meals_take_the_portions(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    make(kitchen, cook["item_id"], tub_count=2, pattern="pick")
    ticked = [spot(3, slots), spot(1, slots), spot(2, slots)]
    asked = leftovers(kitchen, cook["item_id"], ticked)
    assert asked.status_code == 409 and asked.json()["left"] == 2 and asked.json()["wanted"] == 3
    done = leftovers(kitchen, cook["item_id"], ticked, if_none_left="add_anyway")
    assert done.status_code == 200, done.text
    assert where_tubs_are(kitchen, slots) == [(1, day(1), "Lunch"), (2, day(2), "Lunch")]
    last = next(m for m in view(kitchen)["meals"] if m["date"] == day(3))
    assert [i["kind"] for i in last["items"]] == ["recipe"]


def test_cook_more_stops_at_a_full_batch(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    make(kitchen, cook["item_id"], tub_count=12, pattern="lunches")
    # The tubs went to 12 lunches; one more portion would be the 13th tub.
    r = leftovers(kitchen, cook["item_id"], [spot(3, slots, "Dinner")], if_none_left="cook_more")
    assert r.status_code == 422 and r.json()["code"] == "batch_full"


def test_two_phones_taking_the_last_portion(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    """Phone A and phone B both tick the last portion. The first gets it; the second is told
    there are none left (nothing is double-booked), and a retry of the first changes nothing."""
    make(kitchen, cook["item_id"], tub_count=1, pattern="pick")
    url = f"{API}/plan/items/{cook['item_id']}/leftovers"
    a = kitchen.post(url, json={"meals": [spot(1, slots)]}, headers={"Idempotency-Key": "phone-a"})
    b = kitchen.post(url, json={"meals": [spot(2, slots)]}, headers={"Idempotency-Key": "phone-b"})
    assert a.status_code == 200 and b.status_code == 409
    assert b.json()["code"] == "no_portions_left"
    again = kitchen.post(
        url, json={"meals": [spot(1, slots)]}, headers={"Idempotency-Key": "phone-a"}
    )
    assert again.status_code == 200 and again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["change"]["id"] == a.json()["change"]["id"]
    with db_of(kitchen) as db:
        assert len(list(db.scalars(select(MealItem).where(MealItem.tub_id.is_not(None))))) == 1
        assert len(list(db.scalars(select(Tub)))) == 1


# --- Another household, signed out ----------------------------------------------------------------


def test_another_households_item_is_404(
    kitchen: TestClient,
    neighbour: TestClient,
    cook: dict[str, Any],
    slots: dict[str, int],
) -> None:
    item = cook["item_id"]
    assert neighbour.get(f"{API}/plan/items/{item}/portions").status_code == 404
    r = leftovers(neighbour, item, [spot(1, slots)])
    assert r.status_code == 404
    mine_in_theirs = leftovers(
        kitchen, item, [{"date": day(1), "slot_id": slot_ids(kitchen, 2)["Lunch"]}]
    )
    assert mine_in_theirs.status_code == 404
    assert view(kitchen)["batch_cooks"] == []
    assert view(neighbour)["meals"] == []


def test_the_new_routes_need_signing_in(client: TestClient) -> None:
    assert client.get(f"{API}/plan/items/1/portions").status_code == 401
    assert client.post(f"{API}/plan/items/1/leftovers", json={"meals": []}).status_code == 401


# --- The shopping list follows -----------------------------------------------------------------


def test_cook_more_grows_what_the_list_buys_and_undo_takes_it_back(
    kitchen: TestClient, slots: dict[str, int]
) -> None:
    """Amounts and the shopping list follow a bigger batch (spec: Cook more)."""
    from sync_kit import changes
    from test_recipe_list import line
    from test_recipes import food as new_food
    from test_recipes import make as new_recipe

    rice = new_food(kitchen, "Rice")
    made = new_recipe(kitchen, "Pulao", lines=[line(rice["id"], 200, "g")], serves=4)

    def bought() -> list[Any]:
        return [
            r["amount"]
            for r in changes(kitchen)["items"]
            if not r.get("deleted") and r["source"] == "plan"
        ]

    cook = plan_recipe(kitchen, int(made["id"]), D1, slots["Dinner"])
    make(kitchen, cook["item_id"], tub_count=1, pattern="lunches")
    assert bought() == [100]  # one cook-day portion and one tub of 4: 2/4 of 200 g
    done = leftovers(kitchen, cook["item_id"], [spot(3, slots)], if_none_left="cook_more")
    assert done.status_code == 200, done.text
    assert bought() == [150]  # a third portion
    assert undo(kitchen, done.json())["result"] == "done"
    assert bought() == [100]


# --- A tub is never planned past its use-by (F50), and the one-day route asks too ----------


def two_spares(kitchen: TestClient, cook: dict[str, Any], soon: int, late: int) -> list[int]:
    """Two spare tubs: one that goes off on day `soon`, one on day `late`."""
    from datetime import date

    make(kitchen, cook["item_id"], tub_count=2, pattern="pick")
    with db_of(kitchen) as db:
        tubs = list(db.scalars(select(Tub).order_by(Tub.id)))
        tubs[0].use_by = date.fromisoformat(day(soon))
        tubs[1].use_by = date.fromisoformat(day(late))
        db.commit()
        return [t.id for t in tubs]


def meal_of_tub(kitchen: TestClient, tub_id: int) -> str | None:
    from mealwright.models import Meal

    with db_of(kitchen) as db:
        item = db.scalar(select(MealItem).where(MealItem.tub_id == tub_id))
        meal = db.get(Meal, item.meal_id) if item else None
        return meal.day.isoformat() if meal else None


def test_a_tub_past_its_use_by_is_not_planned_for_a_later_day(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    fridge, freezer = two_spares(kitchen, cook, soon=2, late=30)
    assert portions(kitchen, cook["item_id"])["spare_use_by"] == [day(2), day(30)]
    done = leftovers(kitchen, cook["item_id"], [spot(5, slots)])
    assert done.status_code == 200, done.text
    # The one that keeps goes on day 5; the one that goes off on day 2 stays spare.
    assert meal_of_tub(kitchen, freezer) == day(5)
    assert meal_of_tub(kitchen, fridge) is None


def test_two_meals_ticked_take_the_tubs_that_reach_them(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    fridge, freezer = two_spares(kitchen, cook, soon=2, late=30)
    done = leftovers(kitchen, cook["item_id"], [spot(5, slots), spot(1, slots)])
    assert done.status_code == 200, done.text
    assert (meal_of_tub(kitchen, fridge), meal_of_tub(kitchen, freezer)) == (day(1), day(5))


def test_a_meal_no_spare_tub_reaches_counts_as_none_left(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    fridge, freezer = two_spares(kitchen, cook, soon=2, late=30)
    ticked = [spot(5, slots), spot(6, slots)]
    asked = leftovers(kitchen, cook["item_id"], ticked)
    assert asked.status_code == 409 and asked.json()["left"] == 1 and asked.json()["wanted"] == 2
    assert meal_of_tub(kitchen, fridge) is None and meal_of_tub(kitchen, freezer) is None
    # Cook more makes a tub for the meal nothing reaches... but a new fridge tub can't be
    # planned past its own use-by either.
    late = leftovers(kitchen, cook["item_id"], ticked, if_none_left="cook_more")
    assert late.status_code == 422 and late.json()["code"] == "after_use_by"
    anyway = leftovers(kitchen, cook["item_id"], ticked, if_none_left="add_anyway")
    assert anyway.status_code == 200, anyway.text
    assert meal_of_tub(kitchen, freezer) == day(5)
    assert meal_of_tub(kitchen, fridge) is None


def test_the_one_day_route_asks_when_none_is_left(
    kitchen: TestClient, used_up: dict[str, Any], slots: dict[str, int]
) -> None:
    url = f"{API}/plan/items/{used_up['item_id']}/move"
    to = {"date": day(2), "slot_id": slots["Lunch"], "mode": "leftovers"}
    before = (shape(kitchen), view(kitchen)["batch_cooks"])
    asked = kitchen.post(url, json=to)
    assert asked.status_code == 409 and asked.json()["code"] == "no_portions_left"
    assert (shape(kitchen), view(kitchen)["batch_cooks"]) == before
    more = kitchen.post(url, json={**to, "if_none_left": "cook_more"})
    assert more.status_code == 200 and view(kitchen)["batch_cooks"][0]["tub_count"] == 2
    other = kitchen.post(url, json={**to, "slot_id": slots["Dinner"], "if_none_left": "add_anyway"})
    assert other.status_code == 200, other.text
    plan = view(kitchen)
    assert plan["batch_cooks"][0]["tub_count"] == 2
    dinner = next(
        m for m in plan["meals"] if m["date"] == day(2) and m["slot_id"] == slots["Dinner"]
    )
    assert [(i["kind"], i["servings"]) for i in dinner["items"]] == [("recipe", 1)]


def test_a_whole_meal_route_asks_too(
    kitchen: TestClient, used_up: dict[str, Any], slots: dict[str, int]
) -> None:
    url = f"{API}/plan/meals/{used_up['meal_id']}/move"
    to = {"date": day(2), "slot_id": slots["Lunch"], "mode": "leftovers"}
    asked = kitchen.post(url, json=to)
    assert asked.status_code == 409 and asked.json()["code"] == "no_portions_left"
    more = kitchen.post(url, json={**to, "if_none_left": "cook_more"})
    assert more.status_code == 200, more.text
