"""Serves - N + and who's eating (0.7 P1; spec, "The Plan redesign": "Click a meal → Serves - N +
(amounts and the list follow) and who's eating, right there (F57)"; cabledrawer 31 Oct: it "must
also
work on meals planned before the update"). Plan changes are online only (spec section 2)."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sync_kit import changes, ok
from test_plan_batches import make
from test_plan_writes import D1, plan_recipe, shape, undo, view
from test_recipe_list import line
from test_recipes import food as new_food
from test_recipes import make as new_recipe

from mealwright.models import Login, MealEater, MealItem

API = "/api/v1"


@pytest.fixture
def sambar(kitchen: TestClient) -> int:
    rice = new_food(kitchen, "Rice")
    made = new_recipe(kitchen, "Sambar", lines=[line(rice["id"], 200, "g")], serves=4)
    return int(made["id"])


def list_amounts(kitchen: TestClient) -> list[Any]:
    return sorted(
        r["amount"]
        for r in changes(kitchen)["items"]
        if not r.get("deleted") and r["source"] == "plan"
    )


def item_of(kitchen: TestClient, item_id: int) -> dict[str, Any]:
    return next(i for m in view(kitchen)["meals"] for i in m["items"] if i["id"] == item_id)


# --- Serves - N + ---------------------------------------------------------------------------------


def test_serves_changes_the_number_the_amounts_and_the_list_follow(
    kitchen: TestClient, sambar: int, slots: dict[str, int]
) -> None:
    from test_shop_from_plan import day

    plan = kitchen.post(
        f"{API}/plan/items",
        json={"date": day(kitchen, 1).isoformat(), "slot_id": slots["Dinner"], "recipe_id": sambar},
    ).json()
    assert list_amounts(kitchen) == [200]
    set_to = kitchen.patch(f"{API}/plan/items/{plan['item_id']}", json={"servings": 8})
    assert set_to.status_code == 200, set_to.text
    assert set_to.json()["change"]["summary"].startswith("Set Sambar for 8 on Dinner on ")
    assert list_amounts(kitchen) == [400]  # 200 g for 4, so 400 g for 8
    again = kitchen.patch(f"{API}/plan/items/{plan['item_id']}", json={"servings": 8})
    assert again.status_code == 200 and again.json()["change"] is None
    assert undo(kitchen, set_to.json())["result"] == "done"
    assert list_amounts(kitchen) == [200]


def test_a_meal_planned_before_the_update_starts_from_the_recipes_serves(
    kitchen: TestClient, sambar: int, slots: dict[str, int]
) -> None:
    """Meals planned before 0.7 have no number (`servings` null): the answer still says how
    many are eating (the recipe's own Serves), and the first change starts from there."""
    old = plan_recipe(kitchen, sambar, D1, slots["Dinner"])
    with kitchen.app.state.sessionmaker() as db:
        db.execute(update(MealItem).values(servings=None))
        db.commit()
    shown = item_of(kitchen, old["item_id"])
    assert shown["servings"] is None and shown["eating"] == 4
    ok(kitchen.patch(f"{API}/plan/items/{old['item_id']}", json={"servings": 3}))
    assert item_of(kitchen, old["item_id"])["eating"] == 3
    # Undo puts "no number" back, so the recipe's own Serves is meant again.
    done = ok(kitchen.patch(f"{API}/plan/items/{old['item_id']}", json={"servings": 5}))
    assert undo(kitchen, done)["result"] == "done"
    assert item_of(kitchen, old["item_id"])["servings"] == 3


def test_the_cook_meal_of_a_batch_counts_one_unless_a_number_is_set(
    kitchen: TestClient, sambar: int, slots: dict[str, int]
) -> None:
    cook = plan_recipe(kitchen, sambar, D1, slots["Dinner"])
    with kitchen.app.state.sessionmaker() as db:
        db.execute(update(MealItem).values(servings=None))
        db.commit()
    make(kitchen, cook["item_id"], tub_count=2, pattern="pick")
    assert item_of(kitchen, cook["item_id"])["eating"] == 1
    ok(kitchen.patch(f"{API}/plan/items/{cook['item_id']}", json={"servings": 3}))
    batch = view(kitchen)["batch_cooks"][0]
    assert (batch["portions"], batch["tub_count"]) == (5, 2)  # 3 eating now plus 2 tubs


def test_serves_is_for_a_recipe_in_a_planned_meal_between_1_and_99(
    kitchen: TestClient, sambar: int, slots: dict[str, int]
) -> None:
    plan = plan_recipe(kitchen, sambar, D1, slots["Dinner"])
    url = f"{API}/plan/items/{plan['item_id']}"
    for bad in (0, 100, -1, None, 2.5):
        assert kitchen.patch(url, json={"servings": bad}).status_code == 422
    assert kitchen.patch(url, json={}).status_code == 422
    note = kitchen.post(
        f"{API}/plan/items",
        json={"date": D1.isoformat(), "slot_id": slots["Lunch"], "note": "Eating out"},
    ).json()
    refused = kitchen.patch(f"{API}/plan/items/{note['item_id']}", json={"servings": 2})
    assert refused.status_code == 422 and refused.json()["code"] == "not_a_recipe"
    assert item_of(kitchen, note["item_id"])["eating"] is None


def test_serves_of_a_meal_already_dealt_with_is_refused(
    kitchen: TestClient, sambar: int, slots: dict[str, int]
) -> None:
    from test_today import ago

    plan = plan_recipe(kitchen, sambar, ago(kitchen, 1), slots["Dinner"])
    ok(kitchen.post(f"{API}/plan/meals/{plan['meal_id']}/mark-not-cooked"))
    r = kitchen.patch(f"{API}/plan/items/{plan['item_id']}", json={"servings": 2})
    assert r.status_code == 409 and r.json()["code"] == "meal_done"


# --- Who's eating ---------------------------------------------------------------------------------


@pytest.fixture
def wren(kitchen: TestClient) -> int:
    with kitchen.app.state.sessionmaker() as db:
        login = Login(
            household_id=1, username="wren", name="Wren", password_hash="x", role="member"
        )
        db.add(login)
        db.commit()
        return login.member_id


def test_who_is_eating_is_ticked_read_and_undone(
    kitchen: TestClient, sambar: int, wren: int, slots: dict[str, int]
) -> None:
    plan = plan_recipe(kitchen, sambar, D1, slots["Dinner"])
    assert view(kitchen)["meals"][0]["eater_member_ids"] == []  # nobody ticked: everyone
    before = shape(kitchen)
    r = kitchen.patch(f"{API}/plan/meals/{plan['meal_id']}", json={"member_ids": [wren, 1]})
    assert r.status_code == 200, r.text
    assert r.json()["change"]["summary"].startswith("Changed who is eating Sambar (")
    assert view(kitchen)["meals"][0]["eater_member_ids"] == [1, wren]
    same = kitchen.patch(f"{API}/plan/meals/{plan['meal_id']}", json={"member_ids": [1, wren]})
    assert same.json()["change"] is None
    cleared = kitchen.patch(f"{API}/plan/meals/{plan['meal_id']}", json={"member_ids": []})
    assert view(kitchen)["meals"][0]["eater_member_ids"] == []
    assert undo(kitchen, cleared.json())["result"] == "done"
    assert view(kitchen)["meals"][0]["eater_member_ids"] == [1, wren]
    assert undo(kitchen, r.json())["result"] == "done"
    assert view(kitchen)["meals"][0]["eater_member_ids"] == []
    assert shape(kitchen) == before


def test_who_is_eating_goes_with_the_meal_and_comes_back_with_its_undo(
    kitchen: TestClient, sambar: int, wren: int, slots: dict[str, int]
) -> None:
    plan = plan_recipe(kitchen, sambar, D1, slots["Dinner"])
    ok(kitchen.patch(f"{API}/plan/meals/{plan['meal_id']}", json={"member_ids": [wren]}))
    removed = ok(kitchen.delete(f"{API}/plan/meals/{plan['meal_id']}"))
    with kitchen.app.state.sessionmaker() as db:
        assert list(db.scalars(select(MealEater))) == []
    assert undo(kitchen, removed)["result"] == "done"
    assert view(kitchen)["meals"][0]["eater_member_ids"] == [wren]


def test_a_moved_meal_keeps_who_is_eating(
    kitchen: TestClient, sambar: int, wren: int, slots: dict[str, int]
) -> None:
    plan = plan_recipe(kitchen, sambar, D1, slots["Dinner"])
    ok(kitchen.patch(f"{API}/plan/meals/{plan['meal_id']}", json={"member_ids": [wren]}))
    to = {"date": (D1 + timedelta(days=1)).isoformat(), "slot_id": slots["Lunch"], "mode": "move"}
    ok(kitchen.post(f"{API}/plan/meals/{plan['meal_id']}/move", json=to))
    assert view(kitchen)["meals"][0]["eater_member_ids"] == [wren]


def test_who_is_eating_is_refused_for_strangers_and_locked_meals(
    kitchen: TestClient, neighbour: TestClient, sambar: int, wren: int, slots: dict[str, int]
) -> None:
    from test_today import ago

    plan = plan_recipe(kitchen, sambar, D1, slots["Dinner"])
    url = f"{API}/plan/meals/{plan['meal_id']}"
    # A person of another household, and one that is not there.
    with kitchen.app.state.sessionmaker() as db:
        theirs = db.scalar(select(Login.member_id).where(Login.username == "neighbour"))
    for stranger in (theirs, 9999):
        assert kitchen.patch(url, json={"member_ids": [stranger]}).status_code == 404
    # Their meal, their reading.
    assert neighbour.patch(url, json={"member_ids": []}).status_code == 404
    assert view(neighbour)["meals"] == []
    assert kitchen.patch(url, json={"member_ids": list(range(1, 22))}).status_code == 422
    # A meal that was cooked is not changed here.
    past = plan_recipe(kitchen, int(sambar), ago(kitchen, 1), slots["Dinner"])
    ok(kitchen.post(f"{API}/plan/meals/{past['meal_id']}/mark-not-cooked"))
    locked = kitchen.patch(f"{API}/plan/meals/{past['meal_id']}", json={"member_ids": [wren]})
    assert locked.status_code == 409 and locked.json()["code"] == "meal_done"
    assert view(kitchen)["meals"][0]["eater_member_ids"] == []
    # The neighbour cannot reach my servings either.
    assert (
        neighbour.patch(f"{API}/plan/items/{plan['item_id']}", json={"servings": 2}).status_code
        == 404
    )


def test_who_is_eating_never_shows_a_person_from_another_household(
    kitchen: TestClient, sambar: int, slots: dict[str, int]
) -> None:
    plan = plan_recipe(kitchen, sambar, D1, slots["Dinner"])
    with kitchen.app.state.sessionmaker() as db:
        from mealwright.models import Household

        db.add(Household(id=2, name="Next door"))
        db.flush()
        other = Login(household_id=2, username="out", name="Out", password_hash="x", role="member")
        db.add(other)
        db.flush()
        # Not possible through the API; written straight to the database.
        db.add(MealEater(household_id=1, meal_id=plan["meal_id"], member_id=other.member_id))
        db.commit()
    assert view(kitchen)["meals"][0]["eater_member_ids"] == []


def test_the_new_routes_need_signing_in(client: TestClient) -> None:
    assert client.patch(f"{API}/plan/items/1", json={"servings": 2}).status_code == 401
    assert client.patch(f"{API}/plan/meals/1", json={"member_ids": []}).status_code == 401
