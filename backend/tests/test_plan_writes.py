"""Writing the plan (0.6 PR 3): planning, removing, moving, copying and leftovers, switching
a meal on or off; each with its Undo, the caps, retries, and ids from another household."""

from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_plan import add_food, add_recipe, db_of, slot_ids

from mealwright import plan as plan_module
from mealwright.household import MOST_SLOTS, add_slot
from mealwright.models import BatchCook, Meal, MealItem

API = "/api/v1"
TODAY = date.today()
D1 = TODAY + timedelta(days=3)
D2 = TODAY + timedelta(days=4)


def view(client: TestClient, start: date = D1, days: int = 7) -> dict[str, Any]:
    r = client.get(
        f"{API}/plan",
        params={"from": start.isoformat(), "to": (start + timedelta(days)).isoformat()},
    )
    assert r.status_code == 200
    return r.json()  # type: ignore[no-any-return]


def shape(client: TestClient) -> list[tuple[str, int, list[str]]]:
    """Every meal as (date, slot, its items' names), to compare before and after an Undo."""
    out = []
    for m in view(client)["meals"]:
        names = [(i["recipe"] or i["ingredient"] or {"name": "tub"})["name"] for i in m["items"]]
        out.append((m["date"], m["slot_id"], names))
    return sorted(out)


def plan_recipe(
    client: TestClient, recipe_id: int, day: date, slot_id: int, **extra: Any
) -> dict[str, Any]:
    r = client.post(
        f"{API}/plan/items",
        json={"date": day.isoformat(), "slot_id": slot_id, "recipe_id": recipe_id, **extra},
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def undo(client: TestClient, written: dict[str, Any]) -> dict[str, Any]:
    r = client.post(f"{API}/changes/{written['change']['id']}/undo")
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


@pytest.fixture
def stuff(kitchen: TestClient) -> dict[str, int]:
    with db_of(kitchen) as db:
        sambar = add_recipe(db, 1, "Sambar")
        dosa = add_recipe(db, 1, "Dosa")
        banana = add_food(db, 1, "Banana")
        db.commit()
        return {"sambar": sambar.id, "dosa": dosa.id, "banana": banana.id}


@pytest.fixture
def slots(kitchen: TestClient) -> dict[str, int]:
    return slot_ids(kitchen)


def test_planning_a_recipe_makes_the_meal_and_a_filled_meal_gets_it_alongside(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    first = plan_recipe(kitchen, stuff["sambar"], D1, slots["Dinner"], servings=2)
    assert first["change"]["can_undo"] and first["change"]["summary"].startswith("Planned Sambar")
    plan_recipe(kitchen, stuff["dosa"], D1, slots["Dinner"])
    r = kitchen.post(
        f"{API}/plan/items",
        json={"date": D1.isoformat(), "slot_id": slots["Dinner"], "ingredient_id": stuff["banana"]},
    )
    assert r.status_code == 201
    meals = view(kitchen)["meals"]
    assert len(meals) == 1 and meals[0]["id"] == first["meal_id"]
    assert [i["position"] for i in meals[0]["items"]] == [0, 1, 2]
    assert [i["kind"] for i in meals[0]["items"]] == ["recipe", "recipe", "ingredient"]
    assert meals[0]["items"][0]["servings"] == 2


def test_undo_of_planning_takes_back_just_that(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    plan_recipe(kitchen, stuff["sambar"], D1, slots["Dinner"])
    before = shape(kitchen)
    second = plan_recipe(kitchen, stuff["dosa"], D1, slots["Dinner"])
    assert undo(kitchen, second)["result"] == "done"
    assert shape(kitchen) == before
    only = plan_recipe(kitchen, stuff["dosa"], D2, slots["Lunch"])
    assert undo(kitchen, only)["result"] == "done"
    assert shape(kitchen) == before  # the meal it made is gone too
    with db_of(kitchen) as db:
        assert db.scalar(select(func.count()).select_from(Meal)) == 1


def test_planning_needs_exactly_one_of_recipe_or_ingredient_and_a_real_slot(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    day = {"date": D1.isoformat(), "slot_id": slots["Dinner"]}
    both = {**day, "recipe_id": stuff["sambar"], "ingredient_id": stuff["banana"]}
    assert kitchen.post(f"{API}/plan/items", json=both).status_code == 422
    assert kitchen.post(f"{API}/plan/items", json=day).status_code == 422
    far = {"date": "2090-01-01", "slot_id": slots["Dinner"], "recipe_id": stuff["sambar"]}
    assert kitchen.post(f"{API}/plan/items", json=far).status_code == 422
    servings = {**day, "recipe_id": stuff["sambar"], "servings": 0}
    assert kitchen.post(f"{API}/plan/items", json=servings).status_code == 422


def test_a_switched_off_meal_cannot_be_planned_and_the_switch_has_an_undo(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    off = kitchen.patch(f"{API}/meal-slots/{slots['Dinner']}", json={"enabled": False})
    assert off.status_code == 200
    body = {"date": D1.isoformat(), "slot_id": slots["Dinner"], "recipe_id": stuff["sambar"]}
    refused = kitchen.post(f"{API}/plan/items", json=body)
    assert refused.status_code == 422 and "switched off" in refused.json()["detail"]
    assert undo(kitchen, off.json())["result"] == "done"
    assert kitchen.post(f"{API}/plan/items", json=body).status_code == 201
    # Switching to what it already is changes nothing and records nothing.
    same = kitchen.patch(f"{API}/meal-slots/{slots['Dinner']}", json={"enabled": True})
    assert same.json()["change"] is None


def test_removing_an_item_and_a_whole_meal_with_undo(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    a = plan_recipe(kitchen, stuff["sambar"], D1, slots["Dinner"])
    plan_recipe(kitchen, stuff["dosa"], D1, slots["Dinner"])
    before = shape(kitchen)
    one = kitchen.delete(f"{API}/plan/items/{a['item_id']}").json()
    assert shape(kitchen) == [(D1.isoformat(), slots["Dinner"], ["Dosa"])]
    assert undo(kitchen, one)["result"] == "done"
    assert shape(kitchen) == before  # back in its old place, first
    gone = kitchen.delete(f"{API}/plan/meals/{a['meal_id']}").json()
    assert shape(kitchen) == []
    assert undo(kitchen, gone)["result"] == "done"
    assert shape(kitchen) == before


def test_removing_the_last_item_removes_the_meal_and_undo_brings_both_back(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    a = plan_recipe(kitchen, stuff["sambar"], D1, slots["Dinner"])
    with db_of(kitchen) as db:
        db.add(
            BatchCook(
                household_id=1,
                recipe_id=stuff["sambar"],
                recipe_name="Sambar",
                cooked_on=D1,
                tub_count=2,
                cook_meal_id=a["meal_id"],
            )
        )
        db.commit()
    gone = kitchen.delete(f"{API}/plan/items/{a['item_id']}").json()
    assert view(kitchen)["meals"] == []
    assert undo(kitchen, gone)["result"] == "done"
    meals = view(kitchen)
    assert [i["recipe"]["name"] for i in meals["meals"][0]["items"]] == ["Sambar"]
    assert meals["batch_cooks"][0]["cook_meal_id"] == meals["meals"][0]["id"]  # link restored


def test_moving_a_meal_to_an_empty_slot_keeps_it_and_undo_moves_it_back(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    a = plan_recipe(kitchen, stuff["sambar"], D1, slots["Dinner"])
    before = shape(kitchen)
    body = {"date": D2.isoformat(), "slot_id": slots["Lunch"]}
    moved = kitchen.post(f"{API}/plan/meals/{a['meal_id']}/move", json=body).json()
    assert shape(kitchen) == [(D2.isoformat(), slots["Lunch"], ["Sambar"])]
    assert view(kitchen)["meals"][0]["id"] == a["meal_id"]
    assert undo(kitchen, moved)["result"] == "done"
    assert shape(kitchen) == before


def test_moving_a_meal_onto_a_filled_one_adds_alongside_and_undo_splits_them_again(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    a = plan_recipe(kitchen, stuff["sambar"], D1, slots["Dinner"])
    plan_recipe(kitchen, stuff["dosa"], D2, slots["Dinner"])
    before = shape(kitchen)
    body = {"date": D2.isoformat(), "slot_id": slots["Dinner"]}
    moved = kitchen.post(f"{API}/plan/meals/{a['meal_id']}/move", json=body).json()
    assert shape(kitchen) == [(D2.isoformat(), slots["Dinner"], ["Dosa", "Sambar"])]
    assert undo(kitchen, moved)["result"] == "done"
    assert shape(kitchen) == before


def test_copy_and_leftovers_keep_the_original(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    a = plan_recipe(kitchen, stuff["sambar"], D1, slots["Dinner"])
    for mode, word in (("copy", "Copied"), ("leftovers", "Planned leftovers")):
        body = {"date": D2.isoformat(), "slot_id": slots["Dinner"], "mode": mode}
        r = kitchen.post(f"{API}/plan/meals/{a['meal_id']}/move", json=body)
        assert r.status_code == 200 and word in r.json()["change"]["summary"]
        assert shape(kitchen)[0] == (D1.isoformat(), slots["Dinner"], ["Sambar"])
        assert undo(kitchen, r.json())["result"] == "done"
        assert [m[0] for m in shape(kitchen)] == [D1.isoformat()]


def test_moving_and_copying_one_item(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    a = plan_recipe(kitchen, stuff["sambar"], D1, slots["Dinner"])
    plan_recipe(kitchen, stuff["dosa"], D1, slots["Dinner"])
    before = shape(kitchen)
    body = {"date": D2.isoformat(), "slot_id": slots["Lunch"], "mode": "copy"}
    copied = kitchen.post(f"{API}/plan/items/{a['item_id']}/move", json=body).json()
    assert shape(kitchen) == [
        (D1.isoformat(), slots["Dinner"], ["Sambar", "Dosa"]),
        (D2.isoformat(), slots["Lunch"], ["Sambar"]),
    ]
    assert undo(kitchen, copied)["result"] == "done"
    assert shape(kitchen) == before
    moved = kitchen.post(
        f"{API}/plan/items/{a['item_id']}/move", json={**body, "mode": "move"}
    ).json()
    assert shape(kitchen) == [
        (D1.isoformat(), slots["Dinner"], ["Dosa"]),
        (D2.isoformat(), slots["Lunch"], ["Sambar"]),
    ]
    assert undo(kitchen, moved)["result"] == "done"
    assert shape(kitchen) == before


def test_moving_the_only_item_of_a_meal_removes_the_meal_and_undo_restores_it(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    a = plan_recipe(kitchen, stuff["sambar"], D1, slots["Dinner"])
    before = shape(kitchen)
    body = {"date": D2.isoformat(), "slot_id": slots["Dinner"]}
    moved = kitchen.post(f"{API}/plan/items/{a['item_id']}/move", json=body).json()
    assert shape(kitchen) == [(D2.isoformat(), slots["Dinner"], ["Sambar"])]
    assert undo(kitchen, moved)["result"] == "done"
    assert shape(kitchen) == before


def test_a_move_to_where_it_already_is_is_refused(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    a = plan_recipe(kitchen, stuff["sambar"], D1, slots["Dinner"])
    body = {"date": D1.isoformat(), "slot_id": slots["Dinner"]}
    assert kitchen.post(f"{API}/plan/meals/{a['meal_id']}/move", json=body).status_code == 422
    assert kitchen.post(f"{API}/plan/items/{a['item_id']}/move", json=body).status_code == 422


def test_undo_says_partly_when_things_changed_since(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    a = plan_recipe(kitchen, stuff["sambar"], D1, slots["Dinner"])
    b = plan_recipe(kitchen, stuff["dosa"], D1, slots["Dinner"])
    # Someone removes the dosa again, then the first plan-the-dosa change is undone.
    kitchen.delete(f"{API}/plan/items/{b['item_id']}")
    result = undo(kitchen, b)
    assert result["result"] == "nothing" and "Nothing to put back" in result["message"]
    assert shape(kitchen) == [(D1.isoformat(), slots["Dinner"], ["Sambar"])]
    assert a["item_id"]


def test_the_caps(kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]) -> None:
    for _ in range(plan_module.MOST_ITEMS_IN_MEAL):
        plan_recipe(kitchen, stuff["sambar"], D1, slots["Dinner"])
    over = kitchen.post(
        f"{API}/plan/items",
        json={"date": D1.isoformat(), "slot_id": slots["Dinner"], "recipe_id": stuff["dosa"]},
    )
    assert over.status_code == 422 and "at most 20" in over.json()["detail"]
    other = plan_recipe(kitchen, stuff["dosa"], D2, slots["Dinner"])
    to_full = {"date": D1.isoformat(), "slot_id": slots["Dinner"], "mode": "copy"}
    refused = kitchen.post(f"{API}/plan/meals/{other['meal_id']}/move", json=to_full)
    assert refused.status_code == 422


def test_the_caps_keep_a_full_range_under_sqlites_variable_limit() -> None:
    assert 62 * MOST_SLOTS * plan_module.MOST_ITEMS_IN_MEAL < 32_766


def test_a_retry_with_the_same_key_plans_once(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    body = {"date": D1.isoformat(), "slot_id": slots["Dinner"], "recipe_id": stuff["sambar"]}
    first = kitchen.post(f"{API}/plan/items", json=body, headers={"Idempotency-Key": "plan-1"})
    again = kitchen.post(f"{API}/plan/items", json=body, headers={"Idempotency-Key": "plan-1"})
    assert first.status_code == 201 and again.status_code == 200
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["item_id"] == first.json()["item_id"]
    assert len(view(kitchen)["meals"][0]["items"]) == 1


def test_a_cooked_meal_cannot_be_changed_here(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    a = plan_recipe(kitchen, stuff["sambar"], D1, slots["Dinner"])
    with db_of(kitchen) as db:
        db.get(Meal, a["meal_id"]).status = "cooked"  # type: ignore[union-attr]
        db.commit()
    assert kitchen.delete(f"{API}/plan/items/{a['item_id']}").status_code == 409
    assert kitchen.delete(f"{API}/plan/meals/{a['meal_id']}").status_code == 409


def test_the_plan_cards_get_photo_time_kcal_and_tub_numbers(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    from mealwright.models import Recipe, Tub

    with db_of(kitchen) as db:
        for rid, kcal in ((stuff["sambar"], 300_000), (stuff["dosa"], 290_000)):
            recipe = db.get(Recipe, rid)
            assert recipe is not None
            recipe.kcal_milli, recipe.time_minutes = kcal, 40
        batch = BatchCook(
            household_id=1,
            recipe_id=stuff["sambar"],
            recipe_name="Sambar",
            cooked_on=D1,
            tub_count=2,
        )
        db.add(batch)
        db.flush()
        tubs = [Tub(household_id=1, batch_id=batch.id, use_by=D2) for _ in range(2)]
        db.add_all(tubs)
        db.commit()
        tub_id = tubs[1].id
    plan_recipe(kitchen, stuff["sambar"], D1, slots["Dinner"])
    plan_recipe(kitchen, stuff["dosa"], D1, slots["Dinner"])
    with db_of(kitchen) as db:
        meal = db.scalar(select(Meal))
        assert meal is not None
        db.add(MealItem(household_id=1, meal_id=meal.id, position=2, tub_id=tub_id))
        db.commit()
    plan = view(kitchen)
    assert plan["meals"][0]["kcal"] == 300 + 290 + 300
    assert plan["meals"][0]["items"][0]["recipe"]["time_minutes"] == 40
    assert plan["meals"][0]["items"][0]["recipe"]["photo_url"] is None
    assert [t["number"] for t in plan["tubs"]] == [1, 2]


# --- Another household's ids: 404, as if they weren't there ---------------------------------


def test_another_households_ids_get_404_on_every_write(
    kitchen: TestClient, neighbour: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    a = plan_recipe(kitchen, stuff["sambar"], D1, slots["Dinner"])
    theirs_slots = slot_ids(kitchen, 2)
    day = D2.isoformat()
    mine = {"date": day, "slot_id": slots["Dinner"]}
    # Their slot, my recipe / ingredient: 404.
    their_slot = {"date": day, "slot_id": theirs_slots["Dinner"]}
    assert (
        kitchen.post(
            f"{API}/plan/items", json={**their_slot, "recipe_id": stuff["sambar"]}
        ).status_code
        == 404
    )
    # My slot, their recipe / ingredient.
    with db_of(kitchen) as db:
        secret = add_recipe(db, 2, "Theirs")
        food = add_food(db, 2, "Theirs only")
        db.commit()
        secret_id, food_id = secret.id, food.id
    assert (
        kitchen.post(f"{API}/plan/items", json={**mine, "recipe_id": secret_id}).status_code == 404
    )
    assert (
        kitchen.post(f"{API}/plan/items", json={**mine, "ingredient_id": food_id}).status_code
        == 404
    )
    # Their meal and item: the neighbour is the one who does the writes.
    assert neighbour.delete(f"{API}/plan/items/{a['item_id']}").status_code == 404
    assert neighbour.delete(f"{API}/plan/meals/{a['meal_id']}").status_code == 404
    for kind, ident in (("items", a["item_id"]), ("meals", a["meal_id"])):
        r = neighbour.post(f"{API}/plan/{kind}/{ident}/move", json=their_slot)
        assert r.status_code == 404
        r = neighbour.post(f"{API}/plan/{kind}/{ident}/move", json=mine)
        assert r.status_code == 404
    # My meal, their slot.
    for kind, ident in (("items", a["item_id"]), ("meals", a["meal_id"])):
        r = kitchen.post(f"{API}/plan/{kind}/{ident}/move", json=their_slot)
        assert r.status_code == 404
    assert (
        neighbour.patch(f"{API}/meal-slots/{slots['Dinner']}", json={"enabled": False}).status_code
        == 404
    )
    assert (
        kitchen.patch(
            f"{API}/meal-slots/{theirs_slots['Dinner']}", json={"enabled": False}
        ).status_code
        == 404
    )
    # Nothing changed, in either household, and the neighbour can't undo my change.
    assert shape(kitchen) == [(D1.isoformat(), slots["Dinner"], ["Sambar"])]
    assert neighbour.post(f"{API}/changes/{a['change']['id']}/undo").status_code == 404


def test_the_plan_writes_need_signing_in(client: TestClient) -> None:
    body = {"date": D1.isoformat(), "slot_id": 1}
    assert client.post(f"{API}/plan/items", json={**body, "recipe_id": 1}).status_code == 401
    assert client.delete(f"{API}/plan/items/1").status_code == 401
    assert client.delete(f"{API}/plan/meals/1").status_code == 401
    assert client.post(f"{API}/plan/items/1/move", json=body).status_code == 401
    assert client.post(f"{API}/plan/meals/1/move", json=body).status_code == 401
    assert client.patch(f"{API}/meal-slots/1", json={"enabled": True}).status_code == 401


def test_plan_changes_are_in_recent_changes_with_their_undo(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    plan_recipe(kitchen, stuff["sambar"], D1, slots["Dinner"])
    latest = kitchen.get(f"{API}/changes", params={"mine": True, "limit": 1}).json()["changes"][0]
    assert latest["kind"] == "plan_added" and latest["can_undo"]
    assert kitchen.post(f"{API}/changes/{latest['id']}/undo").json()["result"] == "done"
    assert kitchen.post(f"{API}/changes/{latest['id']}/undo").status_code == 409


def test_the_days_allowed_follow_the_households_today(
    kitchen: TestClient,
    stuff: dict[str, int],
    slots: dict[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The household's own today (the one /plan uses), not the server's clock."""
    monkeypatch.setattr(plan_module, "today", lambda _household: date(2040, 1, 1))
    body = {"slot_id": slots["Dinner"], "recipe_id": stuff["sambar"]}
    assert (
        kitchen.post(f"{API}/plan/items", json={**body, "date": D1.isoformat()}).status_code == 422
    )
    assert kitchen.post(f"{API}/plan/items", json={**body, "date": "2040-01-03"}).status_code == 201


def test_a_household_cannot_have_more_than_the_most_slots(kitchen: TestClient) -> None:
    from mealwright.errors import Problem

    with db_of(kitchen) as db:
        for n in range(MOST_SLOTS - 4):  # the four every household starts with
            add_slot(db, 1, f"Extra {n}")
        with pytest.raises(Problem) as refused:
            add_slot(db, 1, "One too many")
        assert refused.value.status_code == 422 and refused.value.code == "too_many_slots"
        assert "at most 12" in refused.value.detail
        db.rollback()
    assert len(kitchen.get(f"{API}/meal-slots").json()) == 4


def _cook(kitchen: TestClient, meal_id: int) -> None:
    with db_of(kitchen) as db:
        meal = db.get(Meal, meal_id)
        assert meal is not None
        meal.status = "cooked"
        db.commit()


def test_undo_of_a_removal_leaves_a_meal_that_was_cooked_since(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    a = plan_recipe(kitchen, stuff["sambar"], D1, slots["Dinner"])
    plan_recipe(kitchen, stuff["dosa"], D1, slots["Dinner"])
    gone = kitchen.delete(f"{API}/plan/items/{a['item_id']}").json()  # one of two
    _cook(kitchen, a["meal_id"])
    result = undo(kitchen, gone)
    assert result["result"] == "nothing"
    assert shape(kitchen) == [(D1.isoformat(), slots["Dinner"], ["Dosa"])]

    # Removing the only thing takes the meal; a new meal planned and cooked there is left alone.
    other = plan_recipe(kitchen, stuff["sambar"], D2, slots["Dinner"])
    removed = kitchen.delete(f"{API}/plan/meals/{other['meal_id']}").json()
    again = plan_recipe(kitchen, stuff["dosa"], D2, slots["Dinner"])
    _cook(kitchen, again["meal_id"])
    assert undo(kitchen, removed)["result"] == "nothing"
    assert (D2.isoformat(), slots["Dinner"], ["Dosa"]) in shape(kitchen)


def test_undo_of_planning_leaves_a_thing_that_moved_into_a_cooked_meal(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    planned = plan_recipe(kitchen, stuff["sambar"], D1, slots["Dinner"])
    body = {"date": D2.isoformat(), "slot_id": slots["Dinner"]}
    moved = kitchen.post(f"{API}/plan/items/{planned['item_id']}/move", json=body).json()
    _cook(kitchen, moved["meal_id"])
    result = undo(kitchen, planned)
    assert result["result"] == "nothing"
    assert shape(kitchen) == [(D2.isoformat(), slots["Dinner"], ["Sambar"])]
    # Undoing the move itself can't put it back either, and leaves no empty meal behind.
    assert undo(kitchen, moved)["result"] != "done"
    assert shape(kitchen) == [(D2.isoformat(), slots["Dinner"], ["Sambar"])]


def test_undo_that_leaves_a_planned_meal_empty_removes_it(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    first = plan_recipe(kitchen, stuff["sambar"], D1, slots["Dinner"])
    # Take the item out by hand, so only an empty meal is left for the Undo to find.
    with db_of(kitchen) as db:
        db.delete(db.get(MealItem, first["item_id"]))
        db.commit()
    undo(kitchen, first)
    with db_of(kitchen) as db:
        assert db.scalar(select(func.count()).select_from(Meal)) == 0
