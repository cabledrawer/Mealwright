"""Undo of an Add ingredient or a starter pack keeps the ingredients in use (0.8, cabledrawer 7 Nov):
it takes out only the ingredients not used anywhere (a recipe, the plan, the shopping list, the
pantry, a staple); the ones in use stay, and the message says how many."""

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sync_kit import ok

from mealwright.models import Meal, MealItem

API = "/api/v1"
SOME = "Took out what could be: 3 ingredients are already in use, so they stay."
ONE = "1 ingredient is already in use, so it stays."
NONE = "Nothing to take out: these ingredients are already in use."


def pack(kitchen: TestClient) -> tuple[int, list[dict[str, Any]]]:
    keys = [
        item["key"]
        for item in next(
            p for p in ok(kitchen.get(f"{API}/starter-packs"))["packs"] if p["id"] == "baking"
        )["items"]
    ]
    body = ok(kitchen.post(f"{API}/starter-packs/baking/add", json={"keys": keys}), 201)
    foods = ok(kitchen.get(f"{API}/foods", params={"limit": 500}))["foods"]
    assert len(foods) == len(keys) and len(keys) > 4
    return body["change"]["id"], foods


def names(kitchen: TestClient) -> set[str]:
    return {f["name"] for f in ok(kitchen.get(f"{API}/foods", params={"limit": 500}))["foods"]}


def use_recipe(kitchen: TestClient, food: dict[str, Any]) -> None:
    ok(
        kitchen.post(
            f"{API}/recipes",
            json={"name": "Cake", "lines": [{"words": food["name"], "food_id": food["id"]}]},
        ),
        201,
    )


def use_plan(kitchen: TestClient, food: dict[str, Any]) -> None:
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        slot = ok(kitchen.get(f"{API}/meal-slots"))[0]["id"]
        meal = Meal(household_id=1, day=date(2026, 11, 9), slot_id=slot)
        db.add(meal)
        db.flush()
        db.add(MealItem(household_id=1, meal_id=meal.id, position=0, food_id=food["id"]))
        db.commit()


def use_shopping(kitchen: TestClient, food: dict[str, Any]) -> None:
    lists = ok(kitchen.get(f"{API}/shopping/lists"))["lists"]
    ok(
        kitchen.post(f"{API}/shopping/lists/{lists[0]['id']}/items", json={"food_id": food["id"]}),
        201,
    )


def use_pantry(kitchen: TestClient, food: dict[str, Any]) -> None:
    body = {"food_id": food["id"], "amount": {"amount": 100, "unit": "g"}}
    ok(kitchen.post(f"{API}/stock", json=body), 201)


def use_staple(kitchen: TestClient, food: dict[str, Any]) -> None:
    ok(kitchen.patch(f"{API}/foods/{food['id']}", json={"staple": True}))
    ok(kitchen.put(f"{API}/shopping/staples/{food['id']}/got-it"))


USES = [use_recipe, use_plan, use_shopping, use_pantry, use_staple]


@pytest.mark.parametrize("use", USES, ids=lambda f: f.__name__)
def test_a_pack_undo_keeps_the_one_in_use(kitchen: TestClient, use: Any) -> None:
    change_id, foods = pack(kitchen)
    kept = foods[0]
    use(kitchen, kept)
    undo = ok(kitchen.post(f"{API}/changes/{change_id}/undo"))
    assert undo["result"] == "partly"
    assert undo["message"] == f"Took out what could be: {ONE}"
    assert names(kitchen) == {kept["name"]}


def test_three_in_use_stay_and_the_rest_go(kitchen: TestClient) -> None:
    change_id, foods = pack(kitchen)
    use_recipe(kitchen, foods[0])
    use_pantry(kitchen, foods[1])
    use_shopping(kitchen, foods[2])
    undo = ok(kitchen.post(f"{API}/changes/{change_id}/undo"))
    assert undo["message"] == SOME
    assert names(kitchen) == {f["name"] for f in foods[:3]}


def test_a_single_add_that_is_in_use_says_nothing_to_take_out(kitchen: TestClient) -> None:
    made = ok(kitchen.post(f"{API}/foods", json={"name": "Tahini"}), 201)
    use_recipe(kitchen, made.get("food", made))
    change_id = ok(kitchen.get(f"{API}/changes", params={"area": "ingredients"}))["changes"][0][
        "id"
    ]
    undo = ok(kitchen.post(f"{API}/changes/{change_id}/undo"))
    assert undo["result"] == "nothing"
    assert undo["message"] == NONE
    assert names(kitchen) == {"Tahini"}


def test_a_single_add_nobody_uses_is_taken_out(kitchen: TestClient) -> None:
    ok(kitchen.post(f"{API}/foods", json={"name": "Tahini"}), 201)
    change_id = ok(kitchen.get(f"{API}/changes", params={"area": "ingredients"}))["changes"][0][
        "id"
    ]
    undo = ok(kitchen.post(f"{API}/changes/{change_id}/undo"))
    assert undo["result"] == "done"
    assert undo["message"] == "Undone."
    assert names(kitchen) == set()


def test_a_pack_nobody_uses_is_all_taken_out(kitchen: TestClient) -> None:
    change_id, _foods = pack(kitchen)
    undo = ok(kitchen.post(f"{API}/changes/{change_id}/undo"))
    assert undo["result"] == "done"
    assert names(kitchen) == set()
