"""Two cooking methods (0.8 wave 5, M2; cabledrawer 31 Oct and 9 Nov): a recipe has one method or
two, each with its own ingredients, steps and time. The first method is the recipe as it always
was, so old clients read and save a recipe as before."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_recipe_list import line, listing, row
from test_recipes import food, make, save

from mealwright.models import MealItem, RecipeLine, RecipeMethod, RecipeStep

API = "/api/v1"


@pytest.fixture
def pantry(kitchen: TestClient) -> dict[str, dict[str, Any]]:
    return {name: food(kitchen, name) for name in ("Meth chicken", "Meth water", "Meth stock")}


def second(**fields: Any) -> dict[str, Any]:
    return {
        "name": "Instant Pot",
        "time_minutes": 30,
        "lines": [],
        "steps": [{"text": "Pressure cook for 10 minutes."}],
        **fields,
    }


def curry(kitchen: TestClient, pantry: dict[str, dict[str, Any]], **fields: Any) -> dict[str, Any]:
    """Stovetop: chicken and water, three steps. Instant Pot: chicken and stock, two steps."""
    body: dict[str, Any] = {
        "time_minutes": 45,
        "method_name": "Stovetop",
        "lines": [
            {**line(pantry["Meth chicken"]["id"], 500, "g"), "words": "chicken"},
            {**line(pantry["Meth water"]["id"], 200, "g"), "words": "water"},
        ],
        "steps": [
            {"text": "Rub the chicken."},
            {"text": "Fry the onions.", "lines": [0]},
            {"text": "Simmer for 25 minutes."},
        ],
        "second_method": second(
            lines=[
                {**line(pantry["Meth chicken"]["id"], 400, "g"), "words": "chicken"},
                {**line(pantry["Meth stock"]["id"], 100, "g"), "words": "stock"},
            ],
            steps=[{"text": "Brown the chicken."}, {"text": "Pressure cook for 10 minutes."}],
        ),
        **fields,
    }
    return make(kitchen, "Meth curry", **body)


def test_a_recipe_without_methods_reads_as_one_method_with_no_name(kitchen: TestClient) -> None:
    recipe = make(kitchen, "Meth plain", time_minutes=20)
    assert recipe["second_method"] is None
    assert len(recipe["methods"]) == 1
    only = recipe["methods"][0]
    assert only["name"] == "" and only["time_minutes"] == 20 and only["used_last"] is False


def test_a_recipe_can_have_two_methods_each_with_its_own_lines_steps_and_time(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = curry(kitchen, pantry)
    # The first method is the recipe's own lines, steps and time: old clients read it as before.
    assert [ln["words"] for ln in recipe["lines"]] == ["chicken", "water"]
    assert [s["text"] for s in recipe["steps"]] == [
        "Rub the chicken.",
        "Fry the onions.",
        "Simmer for 25 minutes.",
    ]
    assert recipe["time_minutes"] == 45
    assert [(m["name"], m["time_minutes"]) for m in recipe["methods"]] == [
        ("Stovetop", 45),
        ("Instant Pot", 30),
    ]
    other = recipe["second_method"]
    assert other["id"] == recipe["methods"][1]["id"]
    assert [ln["words"] for ln in other["lines"]] == ["chicken", "stock"]
    assert [s["text"] for s in other["steps"]] == [
        "Brown the chicken.",
        "Pressure cook for 10 minutes.",
    ]
    again = ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))
    assert again["second_method"] == other and again["methods"] == recipe["methods"]


def test_a_third_method_is_not_a_thing(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    """Two is what cabledrawer asked for: the shape holds one `second_method`, nothing more."""
    body = {"name": "Meth three", "method_name": "A", "second_method": second(), "methods": []}
    made = ok(kitchen.post(f"{API}/recipes", json=body), 201)
    assert len(made["methods"]) == 2


def test_the_two_methods_need_names_that_differ(kitchen: TestClient) -> None:
    for body in (
        {"name": "Meth n", "second_method": second()},  # the first has no name
        {"name": "Meth n", "method_name": "instant pot", "second_method": second()},  # the same
        {"name": "Meth n", "method_name": "Hob", "second_method": second(name="  ")},
    ):
        r = kitchen.post(f"{API}/recipes", json=body)
        assert r.status_code == 422, r.text


def test_a_save_that_knows_nothing_of_methods_keeps_the_second_one(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    """An old client (no `second_method` in its body) must not lose it."""
    recipe = curry(kitchen, pantry)
    after = ok(
        kitchen.put(f"{API}/recipes/{recipe['id']}", json=_body(recipe, name="Meth renamed"))
    )
    assert after["name"] == "Meth renamed"
    assert after["second_method"] is not None
    assert after["second_method"]["id"] == recipe["second_method"]["id"]
    assert [m["name"] for m in after["methods"]] == ["Stovetop", "Instant Pot"]


def _body(recipe: dict[str, Any], **changes: Any) -> dict[str, Any]:
    body = save_body(recipe)
    body.update(changes)
    return body


def save_body(recipe: dict[str, Any]) -> dict[str, Any]:
    """What an old client sends: the recipe's own fields, lines and steps, no methods."""
    return {
        "name": recipe["name"],
        "time_minutes": recipe["time_minutes"],
        "serves": recipe["serves"],
        "version": recipe["version"],
        "lines": [
            {"id": ln["id"], "kind": ln["kind"], "words": ln["words"], "amount": ln["amount"]}
            | ({"food_id": ln["food"]["id"]} if ln["food"] else {})
            | ({"unit": ln["unit"]} if ln["unit"] else {})
            for ln in recipe["lines"]
        ],
        "steps": [{"text": s["text"]} for s in recipe["steps"]],
    }


def test_the_second_method_can_be_changed_and_removed(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = curry(kitchen, pantry)
    kept = recipe["second_method"]
    changed = ok(
        kitchen.put(
            f"{API}/recipes/{recipe['id']}",
            json=_body(
                recipe,
                method_name="Hob",
                second_method=second(
                    name="Pressure cooker",
                    time_minutes=25,
                    lines=[
                        {"id": kept["lines"][0]["id"], "words": "chicken", "amount": 1},
                    ],
                    steps=[{"text": "Whistle three times."}],
                ),
            ),
        )
    )
    assert [m["name"] for m in changed["methods"]] == ["Hob", "Pressure cooker"]
    assert changed["second_method"]["id"] == kept["id"]  # the same method, renamed
    assert [ln["id"] for ln in changed["second_method"]["lines"]] == [kept["lines"][0]["id"]]
    assert [s["text"] for s in changed["second_method"]["steps"]] == ["Whistle three times."]
    assert changed["time_minutes"] == 45  # the first method is untouched
    assert [ln["words"] for ln in changed["lines"]] == ["chicken", "water"]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalars(
            select(RecipeLine.id).where(RecipeLine.method_id == kept["id"])
        ).all() == [kept["lines"][0]["id"]]
    gone = ok(
        kitchen.put(
            f"{API}/recipes/{recipe['id']}", json=_body(changed, second_method=None, method_name="")
        )
    )
    assert gone["second_method"] is None
    assert [(m["name"], m["time_minutes"]) for m in gone["methods"]] == [("", 45)]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalars(
            select(RecipeMethod.position).where(RecipeMethod.recipe_id == gone["id"])
        ).all() == [0]
        assert (
            len(db.scalars(select(RecipeLine).where(RecipeLine.recipe_id == gone["id"])).all()) == 2
        )
        assert (
            len(db.scalars(select(RecipeStep).where(RecipeStep.recipe_id == gone["id"])).all()) == 3
        )


def test_a_line_of_the_other_method_cannot_be_used_in_this_one(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = curry(kitchen, pantry)
    stray = recipe["lines"][0]["id"]
    r = kitchen.put(
        f"{API}/recipes/{recipe['id']}",
        json=_body(
            recipe,
            second_method=second(lines=[{"id": stray, "words": "chicken"}]),
            method_name="Hob",
        ),
    )
    assert r.status_code == 404, r.text


def test_a_step_links_lines_of_its_own_method(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = curry(
        kitchen,
        pantry,
        second_method=second(
            lines=[{**line(pantry["Meth stock"]["id"], 100, "g"), "words": "stock"}],
            steps=[{"text": "Add the stock.", "lines": [0]}],
        ),
    )
    other = recipe["second_method"]
    assert [(u["line_id"], u["line"]) for u in other["steps"][0]["lines"]] == [
        (other["lines"][0]["id"], 0)
    ]
    assert [(u["line_id"], u["line"]) for u in recipe["steps"][1]["lines"]] == [
        (recipe["lines"][0]["id"], 0)
    ]
    r = kitchen.post(
        f"{API}/recipes",
        json={
            "name": "Meth bad",
            "method_name": "A",
            "second_method": second(steps=[{"text": "Use it.", "lines": [3]}]),
        },
    )
    assert r.status_code == 422, r.text


def test_the_list_shows_the_first_methods_time_and_count_and_says_there_are_two(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    curry(kitchen, pantry)
    made = row(kitchen, "Meth curry")
    assert made["time_minutes"] == 45
    assert made["ingredient_count"] == 2
    assert made["method_count"] == 2
    plain = make(kitchen, "Meth one", lines=[{"words": "salt"}])
    assert row(kitchen, plain["name"])["method_count"] == 1
    assert listing(kitchen)["total"] == 2


def test_a_copy_has_both_methods(kitchen: TestClient, pantry: dict[str, dict[str, Any]]) -> None:
    recipe = curry(kitchen, pantry)
    copy = ok(kitchen.post(f"{API}/recipes/{recipe['id']}/duplicate"), 201)
    assert [(m["name"], m["time_minutes"]) for m in copy["methods"]] == [
        ("Stovetop", 45),
        ("Instant Pot", 30),
    ]
    assert copy["second_method"]["id"] != recipe["second_method"]["id"]
    assert [ln["words"] for ln in copy["second_method"]["lines"]] == ["chicken", "stock"]
    assert [s["text"] for s in copy["second_method"]["steps"]] == [
        "Brown the chicken.",
        "Pressure cook for 10 minutes.",
    ]
    assert [ln["words"] for ln in copy["lines"]] == ["chicken", "water"]
    assert ok(save(kitchen, copy))["second_method"] is not None


# --- Planning, shopping, Can cook now and Cooked it ---------------------------------------------

from test_cooking import amounts as stock_amounts  # noqa: E402
from test_cooking import cook  # noqa: E402
from test_deduction import propose  # noqa: E402
from test_plan import slot_ids  # noqa: E402
from test_plan_writes import plan_recipe, undo, view  # noqa: E402
from test_recipe_list import stock  # noqa: E402
from test_shop_from_plan import amounts, day, from_plan  # noqa: E402


def meal_item(kitchen: TestClient, item_id: int) -> dict[str, Any]:
    for meal in view(kitchen, day(kitchen, 0), 10)["meals"]:
        for item in meal["items"]:
            if item["id"] == item_id:
                return dict(item)
    raise AssertionError("not on the plan")


def plan_with(
    kitchen: TestClient, recipe: dict[str, Any], n: int = 1, **extra: Any
) -> dict[str, Any]:
    return plan_recipe(kitchen, recipe["id"], day(kitchen, n), slot_ids(kitchen)["Dinner"], **extra)


def test_adding_a_recipe_with_two_methods_stores_the_pick_and_pre_picks_the_one_used_last(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = curry(kitchen, pantry)
    first, other = recipe["methods"][0]["id"], recipe["methods"][1]["id"]
    # Nothing used yet: the first. The plan says which, and offers both.
    one = plan_with(kitchen, recipe, 1)
    item = meal_item(kitchen, one["item_id"])
    assert (item["method_id"], item["method"]) == (first, "Stovetop")
    assert [m["name"] for m in item["recipe"]["methods"]] == ["Stovetop", "Instant Pot"]
    two = plan_with(kitchen, recipe, 2, method_id=other)
    assert meal_item(kitchen, two["item_id"])["method"] == "Instant Pot"
    # The one used last (the Instant Pot, planned just now) is pre-picked when none is sent.
    three = plan_with(kitchen, recipe, 3)
    assert meal_item(kitchen, three["item_id"])["method_id"] == other
    assert ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))["methods"][1]["used_last"] is True


def test_a_method_that_is_not_the_recipes_is_refused(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = curry(kitchen, pantry)
    plain = make(kitchen, "Meth plain two")
    other = recipe["methods"][1]["id"]
    for target, method in ((plain, other), (recipe, other + 999)):
        r = kitchen.post(
            f"{API}/plan/items",
            json={
                "date": day(kitchen, 1).isoformat(),
                "slot_id": slot_ids(kitchen)["Dinner"],
                "recipe_id": target["id"],
                "method_id": method,
            },
        )
        assert (r.status_code, r.json()["code"]) == (422, "not_a_method"), r.text


def test_another_recipes_method_is_refused_too(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    """A method id belongs to one recipe: another recipe's (or another household's) is refused."""
    mine = curry(kitchen, pantry)
    theirs = make(kitchen, "Meth theirs", method_name="A", second_method=second(), time_minutes=10)
    item = plan_with(kitchen, mine, 1)["item_id"]
    stray = theirs["methods"][1]["id"]
    r = kitchen.put(f"{API}/plan/items/{item}/method", json={"method_id": stray})
    assert (r.status_code, r.json()["code"]) == (422, "not_a_method"), r.text
    r = kitchen.post(
        f"{API}/plan/items",
        json={
            "date": day(kitchen, 2).isoformat(),
            "slot_id": slot_ids(kitchen)["Dinner"],
            "recipe_id": mine["id"],
            "method_id": stray,
        },
    )
    assert (r.status_code, r.json()["code"]) == (422, "not_a_method"), r.text


def test_a_recipe_with_one_method_has_no_pick(kitchen: TestClient) -> None:
    plain = make(kitchen, "Meth solo")
    item = meal_item(kitchen, plan_with(kitchen, plain)["item_id"])
    assert (item["method_id"], item["method"], item["recipe"]["methods"]) == (None, None, [])


def test_the_shopping_list_follows_the_meals_method(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = curry(kitchen, pantry)
    chicken, water, stock_ = (pantry[n]["id"] for n in ("Meth chicken", "Meth water", "Meth stock"))
    plan_with(kitchen, recipe, 1, method_id=recipe["methods"][0]["id"])
    from_plan(kitchen)
    assert set(amounts(kitchen)) == {chicken, water}
    assert amounts(kitchen)[chicken] == 500
    # A second meal with the other method adds its own lines, not the first method's.
    plan_with(kitchen, recipe, 2, method_id=recipe["methods"][1]["id"])
    from_plan(kitchen)
    assert set(amounts(kitchen)) == {chicken, water, stock_}
    assert amounts(kitchen)[chicken] == 900  # 500 g and 400 g
    assert amounts(kitchen)[stock_] == 100 and amounts(kitchen)[water] == 200


def test_the_method_can_be_changed_from_the_meal_and_undone(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = curry(kitchen, pantry)
    chicken, water, stock_ = (pantry[n]["id"] for n in ("Meth chicken", "Meth water", "Meth stock"))
    first, other = recipe["methods"][0]["id"], recipe["methods"][1]["id"]
    item_id = plan_with(kitchen, recipe, 1, method_id=first)["item_id"]
    from_plan(kitchen)
    assert set(amounts(kitchen)) == {chicken, water}
    changed = ok(kitchen.put(f"{API}/plan/items/{item_id}/method", json={"method_id": other}))
    assert meal_item(kitchen, item_id)["method"] == "Instant Pot"
    assert set(amounts(kitchen)) == {chicken, stock_}  # the list followed, with no extra press
    assert (
        ok(kitchen.put(f"{API}/plan/items/{item_id}/method", json={"method_id": other}))["change"]
        is None
    )  # already that way
    undone = undo(kitchen, changed)
    assert undone
    assert meal_item(kitchen, item_id)["method_id"] == first
    assert set(amounts(kitchen)) == {chicken, water}
    # Only a recipe's own methods, and only on a meal not yet cooked.
    r = kitchen.put(f"{API}/plan/items/{item_id}/method", json={"method_id": other + 999})
    assert r.status_code == 422, r.text


def used_last(kitchen: TestClient, recipe: dict[str, Any]) -> str:
    ways = ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))["methods"]
    return str(next(m["name"] for m in ways if m["used_last"]))


def test_undo_of_a_planned_meal_puts_the_way_used_last_back(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = curry(kitchen, pantry)
    first, other = recipe["methods"][0]["id"], recipe["methods"][1]["id"]
    plan_with(kitchen, recipe, 1, method_id=first)
    assert used_last(kitchen, recipe) == "Stovetop"
    added = plan_with(kitchen, recipe, 2, method_id=other)
    assert used_last(kitchen, recipe) == "Instant Pot"
    assert undo(kitchen, added)
    assert used_last(kitchen, recipe) == "Stovetop"  # as it was before the Instant Pot meal
    # Planned again, and a later use stays: the Undo of the first leaves the Instant Pot alone.
    again = plan_with(kitchen, recipe, 3, method_id=first)
    plan_with(kitchen, recipe, 4, method_id=other)
    assert undo(kitchen, again)
    assert used_last(kitchen, recipe) == "Instant Pot"


def test_undo_of_a_changed_way_puts_the_way_used_last_back_and_the_toast_says_the_picks_start_again(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = curry(
        kitchen,
        pantry,
        lines=[
            {**line(pantry["Meth chicken"]["id"], 500, "g"), "words": "chicken"},
            {**line(pantry["Meth water"]["id"], 200, "g"), "words": "water", "optional": True},
        ],
    )
    water_line = recipe["lines"][1]["id"]
    first, other = recipe["methods"][0]["id"], recipe["methods"][1]["id"]
    item_id = plan_with(kitchen, recipe, 1, method_id=first, optional_use=[])["item_id"]
    assert meal_item(kitchen, item_id)["optional_skipped"] == [water_line]
    changed = ok(kitchen.put(f"{API}/plan/items/{item_id}/method", json={"method_id": other}))
    assert changed["change"]["summary"].endswith(
        "cooked to Instant Pot. Its optional ingredients start again"
    )
    assert used_last(kitchen, recipe) == "Instant Pot"
    assert undo(kitchen, changed)
    assert used_last(kitchen, recipe) == "Stovetop"
    assert meal_item(kitchen, item_id)["optional_skipped"] == [water_line]
    # With nothing skipped there was nothing to start again: the words stay as they were.
    plain_id = plan_with(kitchen, recipe, 2, method_id=first)["item_id"]
    plain = ok(kitchen.put(f"{API}/plan/items/{plain_id}/method", json={"method_id": other}))
    assert plain["change"]["summary"].endswith("cooked to Instant Pot")


def test_can_cook_now_follows_the_method_used_last_and_the_page_can_ask_for_either(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = curry(kitchen, pantry)
    first, other = recipe["methods"][0]["id"], recipe["methods"][1]["id"]
    stock(kitchen, pantry["Meth chicken"]["id"], 1000, "g")
    stock(kitchen, pantry["Meth stock"]["id"], 1000, "g")  # only the Instant Pot's ingredients
    # Never used: the first method counts, and its water is missing.
    row = next(r for r in listing(kitchen)["recipes"] if r["name"] == "Meth curry")
    assert row["stock"]["missing"] == 1 and row["stock"]["can_cook_now"] is False
    page = ok(kitchen.get(f"{API}/recipes/{recipe['id']}/stock", params={"method": other}))
    assert (page["counted"], page["missing"]) == (2, 0)
    assert [ln["line_id"] for ln in page["lines"]] == [
        ln["id"] for ln in recipe["second_method"]["lines"]
    ]
    page = ok(kitchen.get(f"{API}/recipes/{recipe['id']}/stock", params={"method": first}))
    assert (page["counted"], page["missing"]) == (2, 1)
    # No method asked for: the first, which is what an older page shows.
    assert ok(kitchen.get(f"{API}/recipes/{recipe['id']}/stock"))["missing"] == 1
    plan_with(kitchen, recipe, 1, method_id=other)  # the Instant Pot is now the one used last
    row = next(r for r in listing(kitchen)["recipes"] if r["name"] == "Meth curry")
    assert row["stock"]["missing"] == 0 and row["stock"]["can_cook_now"] is True


def test_cooked_it_proposes_and_takes_only_the_meals_method_and_undo_puts_it_back(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = curry(kitchen, pantry)
    for name, amount, unit in (
        ("Meth chicken", 1000, "g"),
        ("Meth water", 1000, "g"),
        ("Meth stock", 1000, "g"),
    ):
        stock(kitchen, pantry[name]["id"], amount, unit)
    item = plan_with(kitchen, recipe, 1, method_id=recipe["methods"][1]["id"], servings=4)[
        "item_id"
    ]
    proposal = propose(kitchen, item)
    assert sorted(r["food"]["name"] for r in proposal["rows"]) == ["Meth chicken", "Meth stock"]
    done = ok(cook(kitchen, item), 201)
    assert stock_amounts(kitchen, pantry["Meth chicken"]["id"]) == [600_000]  # 400 g, not 500 g
    assert stock_amounts(kitchen, pantry["Meth stock"]["id"]) == [900_000]
    assert stock_amounts(kitchen, pantry["Meth water"]["id"]) == [1_000_000]
    snapshot = done["cooked"]["snapshot"]
    assert snapshot["method"] == "Instant Pot"
    assert [ln["words"] for ln in snapshot["lines"]] == ["chicken", "stock"]
    assert [s["text"] for s in snapshot["steps"]] == [
        "Brown the chicken.",
        "Pressure cook for 10 minutes.",
    ]
    ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))
    assert stock_amounts(kitchen, pantry["Meth chicken"]["id"]) == [1_000_000]
    assert stock_amounts(kitchen, pantry["Meth stock"]["id"]) == [1_000_000]


def test_a_meal_cooked_with_a_method_makes_it_the_one_used_last(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = curry(kitchen, pantry)
    for name in ("Meth chicken", "Meth water", "Meth stock"):
        stock(kitchen, pantry[name]["id"], 1000, "g")
    first, other = recipe["methods"][0]["id"], recipe["methods"][1]["id"]
    planned = plan_with(kitchen, recipe, 1, method_id=other)["item_id"]
    kitchen.delete(f"{API}/plan/items/{planned}")
    item = plan_with(kitchen, recipe, 1, method_id=first)["item_id"]  # the first is now last used
    assert plan_with(kitchen, recipe, 2)["item_id"]
    cooked_it = plan_with(kitchen, recipe, 0, method_id=other)["item_id"]
    ok(cook(kitchen, cooked_it), 201)
    fresh = plan_with(kitchen, recipe, 4)["item_id"]
    assert meal_item(kitchen, fresh)["method_id"] == other
    assert item


def test_a_copy_of_a_meal_keeps_its_method_and_removing_a_method_sends_its_meals_to_the_first(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = curry(kitchen, pantry)
    other = recipe["methods"][1]["id"]
    item_id = plan_with(kitchen, recipe, 1, method_id=other)["item_id"]
    copied = ok(
        kitchen.post(
            f"{API}/plan/items/{item_id}/move",
            json={
                "date": day(kitchen, 3).isoformat(),
                "slot_id": slot_ids(kitchen)["Lunch"],
                "mode": "copy",
            },
        )
    )
    assert copied["change"]["kind"] == "plan_copied"
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        copy_id = max(db.scalars(select(MealItem.id)))
    assert meal_item(kitchen, copy_id)["method_id"] == other
    gone = ok(
        kitchen.put(
            f"{API}/recipes/{recipe['id']}", json=_body(recipe, second_method=None, method_name="")
        )
    )
    assert gone["second_method"] is None
    # The recipe has one way of cooking it now: its meals follow it, and say nothing of methods.
    for planned in (item_id, copy_id):
        assert meal_item(kitchen, planned)["method_id"] is None
        assert meal_item(kitchen, planned)["method"] is None


def test_an_optional_line_belongs_to_its_method_and_removing_a_meal_and_undo_keep_the_pick(
    kitchen: TestClient, pantry: dict[str, dict[str, Any]]
) -> None:
    recipe = curry(
        kitchen,
        pantry,
        second_method=second(
            lines=[
                {**line(pantry["Meth chicken"]["id"], 400, "g"), "words": "chicken"},
                {**line(pantry["Meth stock"]["id"], 100, "g"), "words": "stock", "optional": True},
            ],
        ),
    )
    stock_line = recipe["second_method"]["lines"][1]["id"]
    other = recipe["methods"][1]["id"]
    bad = kitchen.post(
        f"{API}/plan/items",
        json={
            "date": day(kitchen, 1).isoformat(),
            "slot_id": slot_ids(kitchen)["Dinner"],
            "recipe_id": recipe["id"],
            "method_id": recipe["methods"][0]["id"],
            "optional_use": [stock_line],  # the Instant Pot's line, asked of the Stovetop
        },
    )
    assert bad.status_code == 422 and bad.json()["code"] == "not_optional", bad.text
    made = plan_with(kitchen, recipe, 1, method_id=other, optional_use=[])
    item = meal_item(kitchen, made["item_id"])
    assert item["optional_skipped"] == [stock_line] and item["method_id"] == other
    gone = ok(kitchen.delete(f"{API}/plan/items/{made['item_id']}"))
    undo(kitchen, gone)
    back = next(
        i
        for m in view(kitchen, day(kitchen, 0), 10)["meals"]
        for i in m["items"]
        if i["recipe"] and i["recipe"]["id"] == recipe["id"]
    )
    assert (back["method_id"], back["optional_skipped"]) == (other, [stock_line])


# --- The importer ---------------------------------------------------------------------------------

from test_recipe_import import review as import_review  # noqa: E402
from test_recipe_import import save as save_import  # noqa: E402
from test_recipe_import import to_save  # noqa: E402

TWO_WAYS = (
    "Meth import curry\nIngredients\n500 g chicken\n1 onion\nMethod\nStovetop:\n"
    "1. Fry the onion until golden.\n2. Add the chicken and simmer for 25 minutes.\n\n"
    "Instant Pot:\n1. Brown the chicken on Sauté.\n2. Pressure cook for 10 minutes.\n"
)


def test_a_page_with_stovetop_and_instant_pot_sections_keeps_both_as_methods(
    kitchen: TestClient,
) -> None:
    shown = import_review(kitchen, TWO_WAYS)
    assert shown["method_name"] == "Stovetop"
    assert [s["text"] for s in shown["steps"]] == [
        "Fry the onion until golden.",
        "Add the chicken and simmer for 25 minutes.",
    ]
    assert shown["second_method"]["name"] == "Instant Pot"
    assert [s["text"] for s in shown["second_method"]["steps"]] == [
        "Brown the chicken on Sauté.",
        "Pressure cook for 10 minutes.",
    ]
    body = to_save(shown)
    body["method_name"] = shown["method_name"]
    body["second_method"] = shown["second_method"]
    saved = ok(save_import(kitchen, body), 201)
    recipe = ok(kitchen.get(f"{API}/recipes/{saved['recipe']['id']}"))
    assert [(m["name"]) for m in recipe["methods"]] == ["Stovetop", "Instant Pot"]
    # Both start with the page's ingredients and its one time.
    assert [ln["words"] for ln in recipe["lines"]] == [
        ln["words"] for ln in recipe["second_method"]["lines"]
    ]
    assert len(recipe["lines"]) == 2
    assert recipe["methods"][0]["time_minutes"] == recipe["methods"][1]["time_minutes"]
    assert [s["text"] for s in recipe["second_method"]["steps"]] == [
        "Brown the chicken on Sauté.",
        "Pressure cook for 10 minutes.",
    ]


def test_a_method_that_has_other_headings_or_non_method_names_stays_one_method(
    kitchen: TestClient,
) -> None:
    for method in (
        "Method\nFor the sauce:\n1. Mix.\nTo serve:\n1. Eat.\n",  # headings that are not ways
        # three headings
        "Method\nStovetop:\n1. Fry.\nInstant Pot:\n1. Press.\nTo serve:\n1. Eat.\n",
        # steps before the first heading
        "Method\n1. Fry.\nStovetop:\n1. Fry.\nOven:\n1. Bake.\n",
    ):
        shown = import_review(kitchen, f"Meth one way\nIngredients\n1 onion\n{method}")
        assert shown["second_method"] is None and shown["method_name"] is None
