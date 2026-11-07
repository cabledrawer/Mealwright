"""Undo of an Add ingredient, a starter pack or a typed list item's ingredient keeps the
ingredients in use (0.8, cabledrawer 7 Nov): it takes out only the ingredients not used anywhere
(a recipe, the plan, the shopping list, the pantry, a staple); the ones in use stay, and the
message says how many."""

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import counter, db, main_id, new_id, ok, one

from mealwright.models import Change, Meal, MealItem

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


# U1-b (cabledrawer 7 Nov): one rule for every Undo that would take out an ingredient, the one made
# with a new shopping-list item too.
def _list_made(kitchen: TestClient, name: str) -> tuple[str, int, int]:
    """A list item typed as a new ingredient: (the add action's id, the food, its change)."""
    add_id = new_id()
    result = one(
        kitchen,
        "add",
        id=add_id,
        list_id=main_id(kitchen),
        item_id=new_id(),
        new_food={"name": name, "counted_as": "weight"},
    )
    assert result["status"] == "applied"
    with db(kitchen) as session:
        made = session.scalars(
            select(Change).where(Change.kind == "food_created", Change.food_id == result["food_id"])
        ).one()
        return add_id, result["food_id"], made.id


def _undo_the_item(kitchen: TestClient, add_id: str) -> None:
    assert one(kitchen, "undo", counter(kitchen), undoes=add_id)["status"] == "applied"


def test_a_list_made_ingredient_still_on_the_list_stays(kitchen: TestClient) -> None:
    _add, _food, made = _list_made(kitchen, "Tahini")
    undone = ok(kitchen.post(f"{API}/changes/{made}/undo"))
    assert undone["result"] == "nothing" and undone["message"] == NONE
    assert "Tahini" in names(kitchen)


def test_undoing_the_list_item_keeps_its_ingredient_used_elsewhere(kitchen: TestClient) -> None:
    add_id, food_id, made = _list_made(kitchen, "Tahini")
    use_recipe(kitchen, {"id": food_id, "name": "Tahini"})
    _undo_the_item(kitchen, add_id)  # the list item goes
    undone = ok(kitchen.post(f"{API}/changes/{made}/undo"))
    assert undone["result"] == "nothing" and undone["message"] == NONE
    assert "Tahini" in names(kitchen)  # it is in a recipe, so it stays


def test_undoing_the_list_item_then_its_ingredient_used_nowhere_takes_it_out(
    kitchen: TestClient,
) -> None:
    add_id, _food, made = _list_made(kitchen, "Tahini")
    _undo_the_item(kitchen, add_id)
    undone = ok(kitchen.post(f"{API}/changes/{made}/undo"))
    assert undone["result"] == "done" and "Tahini" not in names(kitchen)
