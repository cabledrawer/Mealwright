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

from mealwright.models import RecipeLine, RecipeMethod, RecipeStep

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
            {**line(pantry["Meth water"]["id"], 200, "ml"), "words": "water"},
        ],
        "steps": [
            {"text": "Rub the chicken."},
            {"text": "Fry the onions.", "lines": [0]},
            {"text": "Simmer for 25 minutes."},
        ],
        "second_method": second(
            lines=[
                {**line(pantry["Meth chicken"]["id"], 400, "g"), "words": "chicken"},
                {**line(pantry["Meth stock"]["id"], 100, "ml"), "words": "stock"},
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
            lines=[{**line(pantry["Meth stock"]["id"], 100, "ml"), "words": "stock"}],
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
