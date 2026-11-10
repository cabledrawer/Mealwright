"""Optional ingredients and steps (0.8 wave 4, R3; cabledrawer 6 and 9 Nov): a recipe's line or step
can be Optional; adding the recipe to the plan says which optional lines the meal will use; the
shopping list, "Can cook now", "Cooked it" and its Undo follow that; the nutrition note says
when the lines changed after the figures were set."""

from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_cooking import amounts as stock_amounts
from test_cooking import cook
from test_deduction import plan_item, propose, row_of
from test_plan import db_of, slot_ids
from test_plan_writes import D1, D2, plan_recipe, undo, view
from test_recipe_list import line, listing, row, stock
from test_recipes import food, make, save
from test_shop_from_plan import amounts, day, from_plan, plan

from mealwright.models import CookedRecord, MealItem

API = "/api/v1"


def lines_of(recipe: dict[str, Any]) -> dict[str, int]:
    """Each ingredient line's id by its words."""
    return {ln["words"]: ln["id"] for ln in recipe["lines"] if ln["kind"] == "ingredient"}


@pytest.fixture
def pantry(kitchen: TestClient) -> dict[str, dict[str, Any]]:
    return {name: food(kitchen, name) for name in ("Opt rice", "Opt papaya", "Opt kewra")}


def biryani(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]], **fields: Any
) -> dict[str, Any]:
    """Rice, and two optional lines: papaya paste and kewra water."""
    return make(
        kitchen,
        "Opt biryani",
        serves=4,
        lines=[
            {**line(pantry["Opt rice"]["id"], 500, "g"), "words": "rice"},
            {**line(pantry["Opt papaya"]["id"], 100, "g"), "words": "papaya", "optional": True},
            {**line(pantry["Opt kewra"]["id"], 50, "g"), "words": "kewra", "optional": True},
        ],
        **fields,
    )


# --- The data ------------------------------------------------------------------------------------


def test_a_line_and_a_step_keep_their_optional_flag(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = biryani(
        kitchen,
        pantry,
        steps=[{"text": "Cook the rice."}, {"text": "Fry onions for the top.", "optional": True}],
    )
    assert [ln["optional"] for ln in recipe["lines"]] == [False, True, True]
    assert [s["optional"] for s in recipe["steps"]] == [False, True]
    again = ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))
    assert [ln["optional"] for ln in again["lines"]] == [False, True, True]
    assert [s["optional"] for s in again["steps"]] == [False, True]
    saved = ok(save(kitchen, again))  # sent back whole, as the editor does
    assert [ln["optional"] for ln in saved["lines"]] == [False, True, True]
    assert [s["optional"] for s in saved["steps"]] == [False, True]


def test_a_save_that_leaves_the_flag_out_makes_the_line_ordinary(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = biryani(kitchen, pantry)
    body = {
        "name": recipe["name"],
        "version": recipe["version"],
        "lines": [{"id": ln["id"], "words": ln["words"]} for ln in recipe["lines"]],
    }
    saved = ok(kitchen.put(f"{API}/recipes/{recipe['id']}", json=body))
    assert [ln["optional"] for ln in saved["lines"]] == [False, False, False]


def test_a_heading_is_never_optional(kitchen: TestClient) -> None:
    refused = kitchen.post(
        f"{API}/recipes",
        json={
            "name": "Heads",
            "lines": [{"kind": "heading", "words": "To serve", "optional": True}],
        },
    )
    assert refused.status_code == 422
    refused = kitchen.post(
        f"{API}/recipes",
        json={"name": "Heads", "steps": [{"kind": "heading", "text": "Later", "optional": True}]},
    )
    assert refused.status_code == 422


def test_a_copy_of_a_recipe_keeps_its_optional_lines_and_steps(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = biryani(kitchen, pantry, steps=[{"text": "Top it.", "optional": True}])
    copy = ok(kitchen.post(f"{API}/recipes/{recipe['id']}/duplicate"), 201)
    assert [ln["optional"] for ln in copy["lines"]] == [False, True, True]
    assert [s["optional"] for s in copy["steps"]] == [True]


def test_the_list_says_how_many_lines_are_optional(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    biryani(kitchen, pantry)
    make(kitchen, "Opt plain", lines=[line(pantry["Opt rice"]["id"], 1, "kg")])
    assert row(kitchen, "Opt biryani")["optional_count"] == 2
    assert row(kitchen, "Opt plain")["optional_count"] == 0


def test_a_recipe_is_can_cook_now_without_its_optional_ingredients(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    stock(kitchen, pantry["Opt rice"]["id"], 600, "g")  # no papaya, no kewra
    biryani(kitchen, pantry)
    assert row(kitchen, "Opt biryani")["stock"] == {
        "counted": 1,
        "missing": 0,
        "can_cook_now": True,
    }
    assert "Opt biryani" in [r["name"] for r in listing(kitchen, can_cook_now=True)["recipes"]]


# --- The nutrition note --------------------------------------------------------------------------


def out_of_date(recipe: dict[str, Any]) -> bool:
    return bool(recipe["nutrition"]["possibly_out_of_date"])


def test_the_note_comes_when_a_line_changes_after_the_figures_were_set(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = biryani(kitchen, pantry, nutrition={"kcal": 610})
    assert out_of_date(recipe) is False
    changed = ok(
        save(
            kitchen,
            recipe,
            lines=[
                {
                    "id": ln["id"],
                    "words": ln["words"],
                    "amount": 600 if ln["words"] == "rice" else 1,
                }
                for ln in recipe["lines"]
            ],
        )
    )
    assert out_of_date(changed) is True
    assert out_of_date(ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))) is True


def test_typing_the_figures_again_or_checking_them_clears_the_note(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = biryani(kitchen, pantry, nutrition={"kcal": 610})
    lines = [{"id": ln["id"], "words": ln["words"], "amount": 7} for ln in recipe["lines"]]
    stale = ok(save(kitchen, recipe, lines=lines))
    assert out_of_date(stale) is True
    # Saved again with the same figures: still out of date.
    stale = ok(save(kitchen, stale))
    assert out_of_date(stale) is True
    # A different figure counts as set now.
    typed = ok(save(kitchen, stale, nutrition={**stale["nutrition"], "kcal": 590}))
    assert out_of_date(typed) is False
    # Changed lines again, then the person looked at the figures and kept them.
    again = ok(save(kitchen, typed, lines=[{**ln, "amount": 9} for ln in lines]))
    assert out_of_date(again) is True
    kept = ok(save(kitchen, again, nutrition_checked=True))
    assert out_of_date(kept) is False


def test_a_note_or_an_optional_switch_is_not_a_change_in_the_ingredients(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = biryani(kitchen, pantry, nutrition={"kcal": 610})
    edited = [
        {
            "id": ln["id"],
            "words": ln["words"],
            "amount": ln["amount"],
            "unit": ln["unit"],
            "food_id": ln["food"]["id"],
            "note": "chopped",
            "optional": not ln["optional"],
        }
        for ln in recipe["lines"]
    ]
    assert out_of_date(ok(save(kitchen, recipe, lines=edited))) is False


def test_no_figures_means_no_note(kitchen: TestClient, pantry: dict[str, dict[str, Any]]) -> None:
    recipe = biryani(kitchen, pantry)
    changed = ok(
        save(kitchen, recipe, lines=[{"id": ln["id"], "words": "x"} for ln in recipe["lines"]])
    )
    assert out_of_date(changed) is False


def test_a_copy_has_the_note_its_original_has(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = biryani(kitchen, pantry, nutrition={"kcal": 610})
    stale = ok(save(kitchen, recipe, lines=[{"id": recipe["lines"][0]["id"], "words": "rice"}]))
    copy = ok(kitchen.post(f"{API}/recipes/{stale['id']}/duplicate"), 201)
    assert out_of_date(stale) and out_of_date(copy)


# --- Adding to the plan --------------------------------------------------------------------------


def test_the_plan_says_how_many_lines_are_optional_and_which_the_meal_leaves_out(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = biryani(kitchen, pantry)
    ids = lines_of(recipe)
    slot = slot_ids(kitchen)["Dinner"]
    asked = plan_recipe(kitchen, recipe["id"], D1, slot, optional_use=[ids["papaya"]])
    unasked = plan_recipe(kitchen, recipe["id"], D2, slot)
    items = {i["id"]: i for m in view(kitchen, days=14)["meals"] for i in m["items"] if i["recipe"]}
    assert items[asked["item_id"]]["recipe"]["optional_count"] == 2
    assert items[asked["item_id"]]["optional_skipped"] == [ids["kewra"]]
    assert items[unasked["item_id"]]["optional_skipped"] == []  # not asked: every line counts


def test_an_id_that_is_not_an_optional_line_is_refused(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = biryani(kitchen, pantry)
    ids = lines_of(recipe)
    slot = slot_ids(kitchen)["Dinner"]
    for use in ([ids["rice"]], [999_999]):
        refused = kitchen.post(
            f"{API}/plan/items",
            json={
                "date": D1.isoformat(),
                "slot_id": slot,
                "recipe_id": recipe["id"],
                "optional_use": use,
            },
        )
        assert refused.status_code == 422 and refused.json()["code"] == "not_optional"
    note = kitchen.post(
        f"{API}/plan/items",
        json={"date": D1.isoformat(), "slot_id": slot, "note": "Out", "optional_use": []},
    )
    assert note.status_code == 422 and note.json()["code"] == "not_a_recipe"
    assert view(kitchen)["meals"] == []  # nothing was planned by the refused ones


def test_the_shopping_list_has_only_the_optional_ingredients_the_meal_will_use(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = biryani(kitchen, pantry)
    ids = lines_of(recipe)
    plan(kitchen, recipe["id"], 1, optional_use=[ids["papaya"]])
    assert amounts(kitchen) == {pantry["Opt rice"]["id"]: 500, pantry["Opt papaya"]["id"]: 100}


def test_a_meal_planned_without_an_answer_counts_every_line(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = biryani(kitchen, pantry)
    plan(kitchen, recipe["id"], 1)
    assert amounts(kitchen) == {
        pantry["Opt rice"]["id"]: 500,
        pantry["Opt papaya"]["id"]: 100,
        pantry["Opt kewra"]["id"]: 50,
    }


def test_two_meals_of_one_recipe_each_follow_their_own_pick(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = biryani(kitchen, pantry)
    ids = lines_of(recipe)
    plan(kitchen, recipe["id"], 1, optional_use=[ids["papaya"]])
    plan(kitchen, recipe["id"], 2, "Lunch", optional_use=[ids["kewra"]])
    assert amounts(kitchen) == {
        pantry["Opt rice"]["id"]: 1000,
        pantry["Opt papaya"]["id"]: 100,
        pantry["Opt kewra"]["id"]: 50,
    }


def test_the_pick_can_be_changed_from_the_meal_and_undone(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = biryani(kitchen, pantry)
    ids = lines_of(recipe)
    planned = plan(kitchen, recipe["id"], 1, optional_use=[])
    assert amounts(kitchen) == {pantry["Opt rice"]["id"]: 500}
    changed = ok(
        kitchen.put(f"{API}/plan/items/{planned['item_id']}/optional", json={"use": [ids["kewra"]]})
    )
    assert changed["change"]["kind"] == "plan_optional"
    assert amounts(kitchen) == {pantry["Opt rice"]["id"]: 500, pantry["Opt kewra"]["id"]: 50}
    # The same pick again changes nothing.
    same = ok(
        kitchen.put(f"{API}/plan/items/{planned['item_id']}/optional", json={"use": [ids["kewra"]]})
    )
    assert same["change"] is None
    assert undo(kitchen, changed)["result"] == "done"
    assert amounts(kitchen) == {pantry["Opt rice"]["id"]: 500}


def test_undoing_a_pick_that_was_changed_again_leaves_the_later_pick(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = biryani(kitchen, pantry)
    ids = lines_of(recipe)
    planned = plan(kitchen, recipe["id"], 1, optional_use=[])
    url = f"{API}/plan/items/{planned['item_id']}/optional"
    first = ok(kitchen.put(url, json={"use": [ids["kewra"]]}))
    ok(kitchen.put(url, json={"use": [ids["kewra"], ids["papaya"]]}))
    assert undo(kitchen, first)["result"] != "done"
    assert set(amounts(kitchen)) == set(pantry[n]["id"] for n in pantry)


def test_only_a_recipe_in_a_planned_meal_has_a_pick_to_change(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    slot = slot_ids(kitchen)["Dinner"]
    note = ok(
        kitchen.post(
            f"{API}/plan/items", json={"date": D1.isoformat(), "slot_id": slot, "note": "Out"}
        ),
        201,
    )
    refused = kitchen.put(f"{API}/plan/items/{note['item_id']}/optional", json={"use": []})
    assert refused.status_code == 422 and refused.json()["code"] == "not_a_recipe"
    recipe = biryani(kitchen, pantry)
    other = plan_recipe(kitchen, recipe["id"], D2, slot)
    refused = kitchen.put(
        f"{API}/plan/items/{other['item_id']}/optional", json={"use": [lines_of(recipe)["rice"]]}
    )
    assert refused.status_code == 422 and refused.json()["code"] == "not_optional"


def test_a_copy_of_a_meal_keeps_its_pick_and_so_does_undoing_its_removal(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = biryani(kitchen, pantry)
    ids = lines_of(recipe)
    slots = slot_ids(kitchen)
    planned = plan_recipe(kitchen, recipe["id"], D1, slots["Dinner"], optional_use=[ids["papaya"]])
    body = {"date": D2.isoformat(), "slot_id": slots["Lunch"], "mode": "copy"}
    copied = ok(kitchen.post(f"{API}/plan/items/{planned['item_id']}/move", json=body))
    with db_of(kitchen) as db:
        picks = [i.optional_skipped for i in db.scalars(select(MealItem).order_by(MealItem.id))]
    assert picks == [[ids["kewra"]], [ids["kewra"]]]
    assert copied["change"] is not None
    removed = ok(kitchen.delete(f"{API}/plan/items/{planned['item_id']}"))
    assert undo(kitchen, removed)["result"] == "done"
    with db_of(kitchen) as db:
        picks = [i.optional_skipped for i in db.scalars(select(MealItem).order_by(MealItem.id))]
    assert picks.count([ids["kewra"]]) == 2 and len(picks) == 2


def test_a_line_made_ordinary_again_counts_whatever_the_pick_was(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = biryani(kitchen, pantry)
    plan(kitchen, recipe["id"], 1, optional_use=[])
    assert amounts(kitchen) == {pantry["Opt rice"]["id"]: 500}
    ok(
        save(
            kitchen,
            recipe,
            lines=[
                {**ln_in, "optional": False}
                for ln_in in (
                    {
                        "id": ln["id"],
                        "words": ln["words"],
                        "amount": ln["amount"],
                        "unit": ln["unit"],
                        "food_id": ln["food"]["id"],
                    }
                    for ln in recipe["lines"]
                )
            ],
        )
    )
    from_plan(kitchen)  # the list follows a recipe edit when it is brought up to date
    assert set(amounts(kitchen)) == {pantry[n]["id"] for n in pantry}


# --- Cooked it -----------------------------------------------------------------------------------


def curry(kitchen: TestClient, pantry: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], int]:
    for name in pantry:
        stock(kitchen, pantry[name]["id"], 1000, "g")
    recipe = biryani(kitchen, pantry, steps=[{"text": "Top it.", "optional": True}])
    return recipe, int(plan_item(kitchen, recipe, servings=4, day=day(kitchen, 1)))


def test_cooked_it_takes_only_the_optional_ingredients_the_meal_will_use(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = biryani(kitchen, pantry)
    ids = lines_of(recipe)
    for name in pantry:
        stock(kitchen, pantry[name]["id"], 1000, "g")
    item = int(
        ok(
            kitchen.post(
                f"{API}/plan/items",
                json={
                    "date": day(kitchen, 1).isoformat(),
                    "slot_id": slot_ids(kitchen)["Dinner"],
                    "recipe_id": recipe["id"],
                    "servings": 4,
                    "optional_use": [ids["papaya"]],
                },
            ),
            201,
        )["item_id"]
    )
    proposal = propose(kitchen, item)
    assert sorted(r["food"]["name"] for r in proposal["rows"]) == ["Opt papaya", "Opt rice"]
    done = ok(cook(kitchen, item), 201)
    assert stock_amounts(kitchen, pantry["Opt rice"]["id"]) == [500_000]
    assert stock_amounts(kitchen, pantry["Opt papaya"]["id"]) == [900_000]
    assert stock_amounts(kitchen, pantry["Opt kewra"]["id"]) == [1_000_000]  # not used: left alone
    assert [c["food_name"] for c in done["cooked"]["snapshot"]["choices"]] == [
        "Opt rice",
        "Opt papaya",
    ]
    # The record keeps which lines and steps were optional.
    assert [ln["optional"] for ln in done["cooked"]["snapshot"]["lines"]] == [False, True, True]
    ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))
    assert stock_amounts(kitchen, pantry["Opt rice"]["id"]) == [1_000_000]
    assert stock_amounts(kitchen, pantry["Opt papaya"]["id"]) == [1_000_000]
    assert stock_amounts(kitchen, pantry["Opt kewra"]["id"]) == [1_000_000]
    with db_of(kitchen) as db:
        assert db.scalars(select(CookedRecord)).first() is None


def test_a_meal_with_no_answer_takes_every_line_when_cooked(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe, item = curry(kitchen, pantry)
    proposal = propose(kitchen, item)
    assert row_of(proposal, "Opt kewra")["use"] is True
    ok(cook(kitchen, item), 201)
    assert stock_amounts(kitchen, pantry["Opt kewra"]["id"]) == [950_000]
    assert recipe["steps"][0]["optional"] is True


def test_changing_the_pick_changes_what_cooked_it_proposes(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe, item = curry(kitchen, pantry)
    ok(kitchen.put(f"{API}/plan/items/{item}/optional", json={"use": []}))
    assert [r["food"]["name"] for r in propose(kitchen, item)["rows"]] == ["Opt rice"]
    ok(kitchen.put(f"{API}/plan/items/{item}/optional", json={"use": [lines_of(recipe)["kewra"]]}))
    assert sorted(r["food"]["name"] for r in propose(kitchen, item)["rows"]) == [
        "Opt kewra",
        "Opt rice",
    ]


def test_a_batch_is_cooked_with_the_picks_of_its_cook_day(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = biryani(kitchen, pantry)
    ids = lines_of(recipe)
    for name in pantry:
        stock(kitchen, pantry[name]["id"], 1000, "g")
    planned = plan_recipe(
        kitchen,
        recipe["id"],
        date.today() + timedelta(days=2),
        slot_ids(kitchen)["Dinner"],
        optional_use=[ids["kewra"]],
    )
    made = ok(
        kitchen.post(
            f"{API}/plan/items/{planned['item_id']}/batch",
            json={"tub_count": 2, "pattern": "pick"},
        ),
        201,
    )
    batch_id = made["batch_id"]
    proposal = ok(kitchen.post(f"{API}/plan/batches/{batch_id}/cook/preview", json={}))
    assert sorted(r["food"]["name"] for r in proposal["rows"]) == ["Opt kewra", "Opt rice"]


# --- Fix round 1 ---------------------------------------------------------------------------------


def test_cooked_it_with_use_off_offers_what_the_meal_needs_without_the_skipped_line(
    kitchen: TestClient,
) -> None:
    from test_cooking import FAR, _listed

    onion = food(kitchen, "Opt use-off onion")
    stock(kitchen, onion["id"], 150, "g")
    recipe = make(
        kitchen,
        "Opt onion curry",
        serves=4,
        lines=[
            {**line(onion["id"], 200, "g"), "words": "onion"},
            {**line(onion["id"], 100, "g"), "words": "more onion", "optional": True},
        ],
    )
    planned = plan_recipe(
        kitchen,
        recipe["id"],
        FAR,
        slot_ids(kitchen)["Dinner"],
        servings=4,
        optional_use=[],
    )
    done = ok(
        cook(kitchen, planned["item_id"], [{"key": f"food:{onion['id']}", "use": False}]), 201
    )
    assert stock_amounts(kitchen, onion["id"]) == [150_000]  # Use off: nothing taken
    choice = done["cooked"]["snapshot"]["choices"][0]
    assert choice["short_milli"] == 50_000  # 200 g needed, not 300 g
    assert _listed(kitchen, onion["id"]) == [50_000]


def test_the_skip_list_is_sorted_whatever_order_the_lines_are_in(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = biryani(kitchen, pantry)
    ids = lines_of(recipe)
    flipped = [recipe["lines"][0], recipe["lines"][2], recipe["lines"][1]]
    saved = ok(
        save(
            kitchen,
            recipe,
            lines=[
                {
                    "id": ln["id"],
                    "words": ln["words"],
                    "amount": ln["amount"],
                    "unit": ln["unit"],
                    "food_id": ln["food"]["id"] if ln["food"] else None,
                    "optional": ln["optional"],
                }
                for ln in flipped
            ],
        )
    )
    assert lines_of(saved) == ids
    planned = plan_recipe(kitchen, recipe["id"], D1, slot_ids(kitchen)["Dinner"], optional_use=[])
    with db_of(kitchen) as db:
        stored = db.get(MealItem, planned["item_id"]).optional_skipped  # type: ignore[union-attr]
    assert stored == sorted([ids["papaya"], ids["kewra"]])
    # The same answer again is no change, and Undo of a real change puts the sorted list back.
    url = f"{API}/plan/items/{planned['item_id']}/optional"
    assert ok(kitchen.put(url, json={"use": []}))["change"] is None
    changed = ok(kitchen.put(url, json={"use": [ids["kewra"]]}))
    assert undo(kitchen, changed)["result"] == "done"
    with db_of(kitchen) as db:
        assert db.get(MealItem, planned["item_id"]).optional_skipped == stored  # type: ignore[union-attr]
