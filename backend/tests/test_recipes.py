"""Recipes: the data and the API (docs/dev/api-0.4-recipes.md). Create, read, save as a
whole, delete with Undo, the limits, fractions, nutrition that stays unknown, two people
editing, made ahead, and tag suggestions. The loop guard is in test_recipe_loops.py, how
ingredients and recipes work together in test_recipe_ingredients.py, and the other
household in test_recipes_isolation.py."""

import time
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok, person

from mealwright.api.v1.recipe_schemas import BAD_AMOUNT
from mealwright.models import Change, Food, Household, Recipe, RecipeLine, Tag, utcnow

API = "/api/v1"


def make(client: TestClient, name: str = "Sambar", **fields: Any) -> dict[str, Any]:
    body: dict[str, Any] = {"name": name, **fields}
    created: dict[str, Any] = ok(client.post(f"{API}/recipes", json=body), 201)
    return created


def save(client: TestClient, recipe: dict[str, Any], **changes: Any) -> Any:
    """Send the recipe back whole, as the editor does, with some things changed."""
    body = {
        "name": recipe["name"],
        "description": recipe["description"],
        "time_minutes": recipe["time_minutes"],
        "serves": recipe["serves"],
        "makes": (
            {"amount": recipe["makes"]["amount"], "unit": recipe["makes"]["unit"]}
            if recipe["makes"]
            else None
        ),
        "made_ahead": recipe["made_ahead"],
        "tags": recipe["tags"],
        "nutrition": recipe["nutrition"],
        "lines": [
            {
                "id": line["id"],
                "kind": line["kind"],
                "words": line["words"],
                "amount": line["amount"],
                "unit": line["unit"],
                "size_id": line["size"]["id"] if line["size"] else None,
                "food_id": line["food"]["id"] if line["food"] else None,
                "recipe_id": line["recipe"]["id"] if line["recipe"] else None,
                "note": line["note"],
            }
            for line in recipe["lines"]
        ],
        "steps": [{"kind": s["kind"], "text": s["text"]} for s in recipe["steps"]],
        "source_note": recipe["source_note"],
        "photo_id": recipe["photo"]["id"] if recipe["photo"] else None,
        "version": recipe["version"],
        **changes,
    }
    return client.put(f"{API}/recipes/{recipe['id']}", json=body)


def food(client: TestClient, name: str, **fields: Any) -> dict[str, Any]:
    made: dict[str, Any] = ok(client.post(f"{API}/foods", json={"name": name, **fields}), 201)
    return dict(made["food"])


# --- Make, read, list --------------------------------------------------------------------------


def test_a_recipe_needs_only_a_name_and_starts_at_serves_4(kitchen: TestClient) -> None:
    recipe = make(kitchen)
    assert recipe["name"] == "Sambar"
    assert recipe["serves"] == 4
    assert recipe["version"] == 1
    assert recipe["updated_by"]["name"] == "Tess"
    assert recipe["lines"] == [] and recipe["steps"] == [] and recipe["tags"] == []
    assert recipe["makes"] is None and recipe["made_ahead"] is False
    assert recipe["homemade"] is None and recipe["photo"] is None and recipe["used_by"] == []
    assert recipe["nutrition"] == {
        "kcal": None,
        "protein": None,
        "carbs": None,
        "fat": None,
        "fibre": None,
    }
    assert ok(kitchen.get(f"{API}/recipes/{recipe['id']}")) == recipe


def test_serves_can_be_empty_for_a_batter(kitchen: TestClient) -> None:
    assert make(kitchen, "Dosa batter", serves=None)["serves"] is None


def test_a_whole_recipe_round_trips(kitchen: TestClient) -> None:
    toor = food(kitchen, "Toor dal")
    packet = ok(
        kitchen.post(f"{API}/foods/{toor['id']}/sizes", json={"name": "packet", "amount": 500}),
        201,
    )["food"]["sizes"][0]
    recipe = make(
        kitchen,
        "Sambar",
        description="Lentil & vegetable stew",
        time_minutes=50,
        serves=6,
        makes={"amount": 1.5, "unit": "litres"},
        tags=["Batch-friendly", "Quick"],
        nutrition={"kcal": 320, "protein": 14.5, "carbs": 41, "fat": 9, "fibre": 11},
        source_note="Amma's",
        lines=[
            {"kind": "heading", "words": "For the dal"},
            {
                "words": "thuvaram paruppu",
                "amount": "1½",
                "unit": "cup",
                "food_id": toor["id"],
                "note": "rinsed",
            },
            {
                "words": "toor dal, spare",
                "amount": 1,
                "size_id": packet["id"],
                "food_id": toor["id"],
            },
            {"words": "salt to taste"},
        ],
        steps=[
            {"kind": "heading", "text": "The dal"},
            {"text": "Boil the dal.\nMash it."},
            {"text": "Temper the spices."},
        ],
    )
    assert recipe["description"] == "Lentil & vegetable stew"
    assert (recipe["time_minutes"], recipe["serves"]) == (50, 6)
    assert recipe["makes"] == {"amount": 1.5, "amount_text": "1½", "unit": "l"}
    assert recipe["tags"] == ["Batch-friendly", "Quick"]
    assert recipe["nutrition"] == {
        "kcal": 320.0,
        "protein": 14.5,
        "carbs": 41.0,
        "fat": 9.0,
        "fibre": 11.0,
    }
    assert recipe["source_note"] == "Amma's"
    heading, dal, spare, salt = recipe["lines"]
    assert heading["kind"] == "heading" and heading["link"] is None
    assert dal["words"] == "thuvaram paruppu" and dal["food"]["name"] == "Toor dal"
    assert (dal["amount"], dal["amount_text"], dal["unit"]) == (1.5, "1½", "cup")
    assert dal["link"] == "ingredient" and dal["note"] == "rinsed"
    assert spare["size"]["name"] == "packet" and spare["unit"] is None
    assert salt["link"] == "none" and salt["amount"] is None and salt["food"] is None
    assert [s["text"] for s in recipe["steps"]] == [
        "The dal",
        "Boil the dal.\nMash it.",
        "Temper the spices.",
    ]
    assert [s["kind"] for s in recipe["steps"]] == ["heading", "step", "step"]


def test_a_linked_line_sends_its_ingredients_other_names(kitchen: TestClient) -> None:
    # So the screen can show "thu" as Toor Dal (cabledrawer 25 Oct); the words stay as saved.
    toor = food(kitchen, "Toor Dal")
    for other in ("thuvaram paruppu", "arhar dal"):
        ok(kitchen.post(f"{API}/foods/{toor['id']}/other-names", json={"name": other}), 201)
    salt = food(kitchen, "Salt")
    recipe = make(
        kitchen,
        lines=[
            {"words": "thu", "amount": 100, "unit": "g", "food_id": toor["id"]},
            {"words": "salt", "food_id": salt["id"]},
            {"words": "tamarind"},
        ],
    )
    lines = ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))["lines"]
    assert [line["words"] for line in lines] == ["thu", "salt", "tamarind"]
    assert [line["food"] for line in lines] == [
        {"id": toor["id"], "name": "Toor Dal", "other_names": ["arhar dal", "thuvaram paruppu"]},
        {"id": salt["id"], "name": "Salt", "other_names": []},
        None,
    ]


def test_the_list_is_a_to_z_and_pages(kitchen: TestClient) -> None:
    for name in ["sambar", "Dosa", "Éclair", "Rasam", "Aloo"]:
        make(kitchen, name, tags=["Quick"] if name == "Rasam" else [])
    listed = ok(kitchen.get(f"{API}/recipes"))
    assert listed["total"] == 5 and listed["next"] is None
    assert [r["name"] for r in listed["recipes"]] == ["Aloo", "Dosa", "Éclair", "Rasam", "sambar"]
    assert listed["recipes"][3]["tags"] == ["Quick"]
    first = ok(kitchen.get(f"{API}/recipes", params={"limit": 2}))
    assert [r["name"] for r in first["recipes"]] == ["Aloo", "Dosa"] and first["next"] == "2"
    second = ok(kitchen.get(f"{API}/recipes", params={"limit": 2, "after": first["next"]}))
    assert [r["name"] for r in second["recipes"]] == ["Éclair", "Rasam"]
    assert ok(kitchen.get(f"{API}/recipes", params={"limit": 2, "after": "4"}))["next"] is None


def test_the_list_counts_ingredients_but_not_headings(kitchen: TestClient) -> None:
    make(
        kitchen,
        lines=[{"kind": "heading", "words": "Dal"}, {"words": "salt"}, {"words": "water"}],
    )
    assert ok(kitchen.get(f"{API}/recipes"))["recipes"][0]["ingredient_count"] == 2


def test_a_recipe_that_is_not_there_is_a_404(kitchen: TestClient) -> None:
    for response in (
        kitchen.get(f"{API}/recipes/999"),
        kitchen.delete(f"{API}/recipes/999"),
        kitchen.get(f"{API}/recipes/999/cannot-use"),
    ):
        assert response.status_code == 404
        assert response.json()["code"] == "not_found"


# --- Limits ------------------------------------------------------------------------------------


def bad(client: TestClient, **fields: Any) -> Any:
    response = client.post(f"{API}/recipes", json={"name": "Sambar", **fields})
    assert response.status_code == 422, response.text
    return response.json()


def where(problem: Any) -> list[str]:
    return [".".join(str(part) for part in e["loc"][1:]) for e in problem["detail"]]


def test_the_name_and_text_limits(kitchen: TestClient) -> None:
    assert make(kitchen, "x" * 200)["name"] == "x" * 200
    assert where(bad(kitchen, name="x" * 201)) == ["name"]
    assert where(bad(kitchen, name="")) == ["name"]
    assert where(bad(kitchen, name="   ")) == ["name"]
    assert make(kitchen, "Long", description="d" * 200)["description"] == "d" * 200
    assert where(bad(kitchen, description="d" * 201)) == ["description"]
    assert where(bad(kitchen, source_note="s" * 501)) == ["source_note"]
    assert where(bad(kitchen, time_minutes=0)) == ["time_minutes"]
    assert where(bad(kitchen, time_minutes=1.5)) == ["time_minutes"]
    assert make(kitchen, "Slow", time_minutes=90)["time_minutes"] == 90


def test_time_is_at_most_14400_minutes(kitchen: TestClient) -> None:
    assert make(kitchen, "Cured", time_minutes=14_400)["time_minutes"] == 14_400
    assert where(bad(kitchen, time_minutes=14_401)) == ["time_minutes"]


def test_serves_is_1_to_99(kitchen: TestClient) -> None:
    assert make(kitchen, "One", serves=1)["serves"] == 1
    assert make(kitchen, "Many", serves=99)["serves"] == 99
    assert where(bad(kitchen, serves=0)) == ["serves"]
    assert where(bad(kitchen, serves=100)) == ["serves"]


def test_at_most_200_lines_with_headings_and_100_steps(kitchen: TestClient) -> None:
    lines = [{"words": f"item {i}"} for i in range(199)] + [{"kind": "heading", "words": "End"}]
    assert len(make(kitchen, "Big", lines=lines)["lines"]) == 200
    assert where(bad(kitchen, lines=[*lines, {"words": "one too many"}])) == ["lines"]
    steps = [{"text": f"Step {i}"} for i in range(99)] + [{"kind": "heading", "text": "End"}]
    assert len(make(kitchen, "Long", steps=steps)["steps"]) == 100
    assert where(bad(kitchen, steps=[*steps, {"text": "one too many"}])) == ["steps"]


def test_a_step_is_at_most_5000_characters(kitchen: TestClient) -> None:
    assert len(make(kitchen, "Wordy", steps=[{"text": "w" * 5000}])["steps"][0]["text"]) == 5000
    assert where(bad(kitchen, steps=[{"text": "w" * 5001}])) == ["steps.0.text"]
    assert where(bad(kitchen, steps=[{"text": "   "}])) == ["steps.0"]


def test_lines_and_steps_must_make_sense(kitchen: TestClient) -> None:
    toor = food(kitchen, "Toor dal")
    other = make(kitchen, "Powder")
    cases = [
        {"kind": "heading", "words": ""},
        {"kind": "heading", "words": "For the dal", "amount": 1},
        {"words": ""},
        {"words": "x", "food_id": toor["id"], "recipe_id": other["id"]},
        {"words": "x", "unit": "cup", "size_id": 1, "food_id": toor["id"]},
        {"words": "x", "size_id": 1},
        {"words": "x", "unit": "bunch"},
        {"words": "x", "amount": 0},
        {"words": "x", "amount": -1},
        {"words": "x", "amount": "lots"},
        {"words": "x", "amount": 2_000_000},
        {"words": "x" * 201},
        {"words": "x", "note": "n" * 201},
    ]
    for line in cases:
        assert where(bad(kitchen, lines=[line]))[0].startswith("lines.0"), line


def test_nutrition_limits(kitchen: TestClient) -> None:
    assert where(bad(kitchen, nutrition={"kcal": -1})) == ["nutrition.kcal"]
    assert where(bad(kitchen, nutrition={"fat": 100_001})) == ["nutrition.fat"]
    assert where(bad(kitchen, nutrition={"fibre": "lots"})) == ["nutrition.fibre"]


# --- Fractions ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("typed", "amount", "shown"),
    [
        ("½", 0.5, "½"),
        ("1½", 1.5, "1½"),
        ("1 ½", 1.5, "1½"),
        ("1/2", 0.5, "½"),
        ("1 1/2", 1.5, "1½"),
        ("¾", 0.75, "¾"),
        ("2¼", 2.25, "2¼"),
        ("⅓", 0.333, "⅓"),
        ("200", 200, "200"),
        ("1.5", 1.5, "1½"),
        ("0.125", 0.125, "⅛"),
        ("1.2", 1.2, "1.2"),
        (1.5, 1.5, "1½"),
        (200, 200, "200"),
        (" 3 ", 3, "3"),
    ],
)
def test_amounts_with_fractions(kitchen: TestClient, typed: Any, amount: float, shown: str) -> None:
    recipe = make(kitchen, lines=[{"words": "x", "amount": typed, "unit": "tsp"}])
    line = recipe["lines"][0]
    assert line["amount"] == amount and line["amount_text"] == shown


def test_an_empty_amount_is_no_amount(kitchen: TestClient) -> None:
    for typed in (None, "", "  "):
        line = make(kitchen, lines=[{"words": "salt", "amount": typed}])["lines"][0]
        assert line["amount"] is None and line["amount_text"] is None


def test_a_very_long_amount_is_refused_before_it_is_read(kitchen: TestClient) -> None:
    """Turning a long run of digits into a number takes time that grows with the square of
    its length: 200,000 digits took a third of a second, so a 4 MB body could hold the
    server for minutes. Text over 20 characters is refused before it is read (security
    pass, 0.4), with the words any other text that isn't an amount gets."""
    huge = "1" * 200_000
    for fields, place in [
        ({"lines": [{"words": "x", "amount": huge}]}, "lines.0.amount"),
        ({"makes": {"amount": huge, "unit": "g"}}, "makes.amount"),
    ]:
        started = time.monotonic()
        problem = bad(kitchen, **fields)
        assert time.monotonic() - started < 1
        assert where(problem) == [place]
        assert BAD_AMOUNT in problem["detail"][0]["msg"]


@pytest.mark.parametrize(
    ("typed", "allowed"),
    [
        ("0" * 18 + "1½", True),  # 20 characters
        ("0" * 19 + "1½", False),
        (" " * 17 + "1/2", True),  # spaces count
        (" " * 18 + "1/2", False),
    ],
)
def test_an_amount_is_at_most_20_characters(kitchen: TestClient, typed: str, allowed: bool) -> None:
    for fields, place in [
        ({"lines": [{"words": "x", "amount": typed}]}, "lines.0.amount"),
        ({"makes": {"amount": typed, "unit": "l"}}, "makes.amount"),
    ]:
        if allowed:
            make(kitchen, **fields)
        else:
            problem = bad(kitchen, **fields)
            assert where(problem) == [place]
            assert BAD_AMOUNT in problem["detail"][0]["msg"]


def test_units_have_other_spellings(kitchen: TestClient) -> None:
    typed = ["Grams", "kilos", "Litres", "tablespoons", "pinches", "CUPS", "", "count", None]
    lines = [{"words": "x", "amount": 1, "unit": unit} for unit in typed]
    units = [line["unit"] for line in make(kitchen, lines=lines)["lines"]]
    assert units == ["g", "kg", "l", "tbsp", "pinch", "cup", None, None, None]


def test_makes_units(kitchen: TestClient) -> None:
    assert make(kitchen, "A", makes={"amount": "½", "unit": "Litres"})["makes"] == {
        "amount": 0.5,
        "amount_text": "½",
        "unit": "l",
    }
    dosas = make(kitchen, "B", makes={"amount": 12, "unit": "dosas"})["makes"]
    assert (dosas["amount"], dosas["unit"]) == (12, "dosas")
    assert where(bad(kitchen, makes={"amount": None, "unit": "g"})) == ["makes"]
    assert where(bad(kitchen, makes={"amount": 5, "unit": ""})) == ["makes.unit"]


# --- Nutrition: unknown is never 0 -------------------------------------------------------------


def test_nutrition_that_is_left_empty_stays_unknown_never_zero(kitchen: TestClient) -> None:
    recipe = make(kitchen, nutrition={"kcal": 250, "protein": 0, "fat": None})
    assert recipe["nutrition"] == {
        "kcal": 250.0,
        "protein": 0.0,  # typing 0 means zero
        "carbs": None,
        "fat": None,
        "fibre": None,
    }
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        row = db.get(Recipe, recipe["id"])
        assert (row.kcal_milli, row.protein_milli) == (250000, 0)  # type: ignore[union-attr]
        assert (row.carbs_milli, row.fat_milli, row.fibre_milli) == (None, None, None)  # type: ignore[union-attr]
    # Saving again with the boxes emptied makes them unknown again, not 0.
    saved = ok(save(kitchen, recipe, nutrition={}))
    assert saved["nutrition"] == {k: None for k in ("kcal", "protein", "carbs", "fat", "fibre")}


def test_a_recipe_with_no_nutrition_stores_no_zeros(kitchen: TestClient) -> None:
    recipe = make(kitchen)
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        row = db.get(Recipe, recipe["id"])
        assert row is not None
        stored = [
            row.kcal_milli,
            row.protein_milli,
            row.carbs_milli,
            row.fat_milli,
            row.fibre_milli,
        ]
    assert stored == [None] * 5


# --- Saving the whole recipe -------------------------------------------------------------------


def test_a_save_replaces_everything_and_adds_1_to_the_version(kitchen: TestClient) -> None:
    recipe = make(
        kitchen,
        tags=["Quick"],
        lines=[{"words": "salt"}, {"words": "water"}],
        steps=[{"text": "Mix."}],
        time_minutes=10,
    )
    saved = ok(
        save(
            kitchen,
            recipe,
            name="Sambar 2",
            time_minutes=None,
            tags=["Kids"],
            steps=[{"text": "Boil."}, {"text": "Serve."}],
            lines=[
                {"id": recipe["lines"][1]["id"], "words": "cold water"},
                {"words": "pepper", "amount": "¼", "unit": "tsp"},
            ],
        )
    )
    assert saved["version"] == 2 and saved["name"] == "Sambar 2" and saved["time_minutes"] is None
    assert saved["tags"] == ["Kids"]
    assert [s["text"] for s in saved["steps"]] == ["Boil.", "Serve."]
    assert [line["words"] for line in saved["lines"]] == ["cold water", "pepper"]
    # The line that was sent back with its id kept it; the new one is new; the other went.
    assert saved["lines"][0]["id"] == recipe["lines"][1]["id"]
    assert saved["lines"][1]["id"] not in {line["id"] for line in recipe["lines"]}
    assert ok(kitchen.get(f"{API}/recipes/{recipe['id']}")) == saved
    assert ok(save(kitchen, saved))["version"] == 3


def test_lines_and_steps_keep_the_order_they_are_sent(kitchen: TestClient) -> None:
    recipe = make(kitchen, lines=[{"words": "a"}, {"words": "b"}, {"words": "c"}])
    a, b, c = (line["id"] for line in recipe["lines"])
    saved = ok(
        save(
            kitchen,
            recipe,
            lines=[{"id": c, "words": "c"}, {"id": a, "words": "a"}, {"id": b, "words": "b"}],
        )
    )
    assert [line["id"] for line in saved["lines"]] == [c, a, b]


def test_a_line_that_is_not_in_the_recipe_is_a_404(kitchen: TestClient) -> None:
    one = make(kitchen, "One", lines=[{"words": "a"}])
    two = make(kitchen, "Two", lines=[{"words": "b"}])
    response = save(kitchen, one, lines=[{"id": two["lines"][0]["id"], "words": "stolen"}])
    assert response.status_code == 404 and response.json()["line"] == 0
    assert ok(kitchen.get(f"{API}/recipes/{two['id']}"))["lines"][0]["words"] == "b"


def test_a_link_to_something_that_is_not_there_says_which_line(kitchen: TestClient) -> None:
    recipe = make(kitchen)
    response = save(kitchen, recipe, lines=[{"words": "ok"}, {"words": "dal", "food_id": 12345}])
    assert response.status_code == 404 and response.json()["line"] == 1
    assert response.json()["detail"] == "That ingredient isn’t here any more."
    response = save(kitchen, recipe, lines=[{"words": "sub", "recipe_id": 12345}])
    assert response.status_code == 404 and response.json()["detail"].startswith("That recipe")
    assert ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))["version"] == 1


def test_a_size_must_belong_to_the_linked_ingredient(kitchen: TestClient) -> None:
    toor = food(kitchen, "Toor dal")
    moong = food(kitchen, "Moong dal")
    size = ok(
        kitchen.post(f"{API}/foods/{toor['id']}/sizes", json={"name": "packet", "amount": 500}),
        201,
    )["food"]["sizes"][0]
    recipe = make(kitchen)
    response = save(
        kitchen, recipe, lines=[{"words": "x", "size_id": size["id"], "food_id": moong["id"]}]
    )
    assert response.status_code == 404 and response.json()["detail"].startswith("That size")


def test_a_linked_line_without_words_takes_the_name(kitchen: TestClient) -> None:
    toor = food(kitchen, "Toor dal")
    powder = make(kitchen, "Sambar powder")
    recipe = make(
        kitchen,
        "Sambar",
        lines=[{"food_id": toor["id"]}, {"recipe_id": powder["id"], "amount": 2, "unit": "tbsp"}],
    )
    assert [line["words"] for line in recipe["lines"]] == ["Toor dal", "Sambar powder"]
    assert recipe["lines"][1]["link"] == "recipe"


def test_words_are_kept_as_typed_even_when_the_ingredient_has_another_name(
    kitchen: TestClient,
) -> None:
    toor = food(kitchen, "Toor dal")
    line = make(kitchen, lines=[{"words": "  thuvaram   paruppu ", "food_id": toor["id"]}])[
        "lines"
    ][0]
    assert line["words"] == "thuvaram paruppu" and line["food"]["name"] == "Toor dal"


# --- Control characters ------------------------------------------------------------------------


def test_recipe_text_refuses_hidden_characters(kitchen: TestClient) -> None:
    for field, value in [
        ("name", "Sam\tbar"),
        ("name", "Sam\nbar"),
        ("description", "a\u200bb"),
        ("source_note", "Amma\u202es"),
        ("tags", ["Qui\tck"]),
        ("lines", [{"words": "sal\nt"}]),
        ("lines", [{"words": "salt", "note": "a\tb"}]),
        ("lines", [{"kind": "heading", "words": "a\u2028b"}]),
        ("steps", [{"text": "Boil\x00"}]),
        ("steps", [{"text": "Boil\ttabbed"}]),
        ("steps", [{"kind": "heading", "text": "Two\nlines"}]),
        ("makes", {"amount": 1, "unit": "do\tsas"}),
        ("homemade_name", "Batt\ter"),
    ]:
        problem = bad(kitchen, **{field: value})
        assert "hidden character" in str(problem) or "tab" in str(problem), (field, value)


def test_a_step_may_have_line_breaks(kitchen: TestClient) -> None:
    step = make(kitchen, steps=[{"text": "One.\r\nTwo.\nThree."}])["steps"][0]
    assert step["text"] == "One.\nTwo.\nThree."


# --- Two people editing the same recipe --------------------------------------------------------


def test_the_second_save_is_stopped_and_says_who_changed_it(kitchen: TestClient) -> None:
    wren = person(kitchen)
    recipe = make(kitchen, lines=[{"words": "salt"}])
    # Both open version 1. Wren saves first.
    first = ok(save(wren, recipe, name="Wren's sambar", time_minutes=40))
    assert first["version"] == 2 and first["updated_by"]["name"] == "Wren"
    # Tess's save (from version 1) is refused, and nothing is changed.
    stopped = save(kitchen, recipe, name="Tess's sambar")
    assert stopped.status_code == 409
    problem = stopped.json()
    assert problem["code"] == "recipe_changed"
    assert problem["detail"] == "Wren changed this recipe after you opened it."
    assert problem["version"] == 2
    assert problem["changed_by"]["name"] == "Wren"
    assert problem["changed_at"].startswith("20")
    now = ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))
    assert (now["name"], now["version"], now["time_minutes"]) == ("Wren's sambar", 2, 40)
    # "See Wren's version" is just a read of the recipe.
    assert now["updated_by"]["name"] == "Wren"


def test_save_mine_anyway_is_an_update_from_the_newer_version(kitchen: TestClient) -> None:
    wren = person(kitchen)
    recipe = make(kitchen)
    ok(save(wren, recipe, name="Wren's"))
    stopped = save(kitchen, recipe, name="Tess's").json()
    mine = ok(save(kitchen, recipe, name="Tess's", version=stopped["version"], overwrite=True))
    assert mine["name"] == "Tess's" and mine["version"] == 3
    assert mine["updated_by"]["name"] == "Tess"


def test_save_mine_anyway_is_refused_if_a_third_save_came_in(kitchen: TestClient) -> None:
    """cabledrawer 19 Oct, R4: a third person's save in between stops "Save mine anyway" again,
    naming them, so nobody overwrites a version they haven't seen."""
    wren = person(kitchen)
    arlo = person(kitchen, "Arlo", "arlo")
    recipe = make(kitchen)
    ok(save(wren, recipe, name="Wren's"))
    stopped = save(kitchen, recipe, name="Tess's").json()
    again = ok(save(arlo, {**recipe, "version": 2}, name="Arlo's"))
    assert again["version"] == 3
    response = save(kitchen, recipe, name="Tess's", version=stopped["version"], overwrite=True)
    assert response.status_code == 409
    problem = response.json()
    assert problem["code"] == "recipe_changed" and problem["version"] == 3
    assert problem["detail"] == "Arlo changed this recipe after you opened it."
    assert problem["changed_by"]["name"] == "Arlo"
    assert ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))["name"] == "Arlo's"


def test_a_version_from_the_future_is_refused_too(kitchen: TestClient) -> None:
    recipe = make(kitchen)
    assert save(kitchen, recipe, version=7).status_code == 409


def test_your_own_second_phone_is_stopped_the_same_way(kitchen: TestClient) -> None:
    recipe = make(kitchen)
    ok(save(kitchen, recipe, name="First"))
    stopped = save(kitchen, recipe, name="Second")
    assert stopped.status_code == 409
    assert stopped.json()["detail"] == "Tess changed this recipe after you opened it."


# --- Delete and Undo ---------------------------------------------------------------------------


def test_delete_hides_the_recipe_at_once_and_undo_brings_it_back(kitchen: TestClient) -> None:
    recipe = make(kitchen, tags=["Quick"], lines=[{"words": "salt"}], steps=[{"text": "Mix."}])
    removed = ok(kitchen.delete(f"{API}/recipes/{recipe['id']}"))
    change = removed["change"]
    assert change["summary"] == "Deleted Sambar" and change["can_undo"] is True
    assert kitchen.get(f"{API}/recipes/{recipe['id']}").status_code == 404
    assert ok(kitchen.get(f"{API}/recipes"))["recipes"] == []
    assert ok(kitchen.get(f"{API}/recipes/tags"))["tags"] == []
    undone = ok(kitchen.post(f"{API}/changes/{change['id']}/undo"))
    assert undone["result"] == "done"
    assert undone["message"] == "Sambar is back in Recipes."
    assert undone["recipe"] == {"id": recipe["id"], "name": "Sambar"}
    assert ok(kitchen.get(f"{API}/recipes/{recipe['id']}")) == recipe
    assert [t["name"] for t in ok(kitchen.get(f"{API}/recipes/tags"))["tags"]] == ["Quick"]
    again = kitchen.post(f"{API}/changes/{change['id']}/undo")
    assert again.status_code == 409 and again.json()["code"] == "already_undone"


def test_a_deleted_recipe_is_in_recent_changes_and_ctrl_z_finds_it(kitchen: TestClient) -> None:
    recipe = make(kitchen)
    removed = ok(kitchen.delete(f"{API}/recipes/{recipe['id']}"))
    mine = ok(kitchen.get(f"{API}/changes", params={"mine": True, "limit": 1}))["changes"][0]
    assert mine["id"] == removed["change"]["id"] and mine["can_undo"]
    ok(kitchen.post(f"{API}/changes/{mine['id']}/undo"))
    assert kitchen.get(f"{API}/recipes/{recipe['id']}").status_code == 200


def test_delete_cannot_be_undone_after_7_days_and_then_the_recipe_goes_for_good(
    kitchen: TestClient,
) -> None:
    from mealwright.recipes import purge_removed_recipes

    recipe = make(kitchen, tags=["Quick"], lines=[{"words": "salt"}], steps=[{"text": "Mix."}])
    change = ok(kitchen.delete(f"{API}/recipes/{recipe['id']}"))["change"]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        # Still inside the window: the purge leaves it.
        assert purge_removed_recipes(db, db.get(Household, 1)) == 0
        row = db.get(Recipe, recipe["id"])
        assert row is not None
        row.removed_at = utcnow() - timedelta(days=8)
        db.get(Change, change["id"]).at = utcnow() - timedelta(days=8)  # type: ignore[union-attr]
        db.commit()
        assert purge_removed_recipes(db, db.get(Household, 1)) == 1
        assert db.get(Recipe, recipe["id"]) is None
        assert db.scalars(select(RecipeLine)).all() == []
        assert db.scalars(select(Tag)).all() == []
    late = kitchen.post(f"{API}/changes/{change['id']}/undo")
    assert late.status_code == 410 and late.json()["code"] == "too_old"


def test_delete_with_the_same_change_id_twice_deletes_once(kitchen: TestClient) -> None:
    recipe = make(kitchen)
    headers = {"Idempotency-Key": "delete-sambar-1"}
    first = ok(kitchen.delete(f"{API}/recipes/{recipe['id']}", headers=headers))
    second = kitchen.delete(f"{API}/recipes/{recipe['id']}", headers=headers)
    assert second.status_code == 200 and second.headers["Idempotent-Replayed"] == "true"
    assert second.json()["change"]["id"] == first["change"]["id"]


def test_a_deleted_recipe_cannot_be_saved(kitchen: TestClient) -> None:
    recipe = make(kitchen)
    kitchen.delete(f"{API}/recipes/{recipe['id']}")
    assert save(kitchen, recipe).status_code == 404


# --- Tag suggestions ---------------------------------------------------------------------------


def test_tag_suggestions_are_the_tags_the_household_uses(kitchen: TestClient) -> None:
    a = make(kitchen, "A", tags=["Quick", "Kids"])
    make(kitchen, "B", tags=["quick", "Batch-friendly"])
    tags = ok(kitchen.get(f"{API}/recipes/tags"))["tags"]
    assert tags == [
        {"name": "Batch-friendly", "recipes": 1},
        {"name": "Kids", "recipes": 1},
        {"name": "Quick", "recipes": 2},  # "quick" is the same tag
    ]
    typed = ok(kitchen.get(f"{API}/recipes/tags", params={"q": "ki"}))["tags"]
    assert [t["name"] for t in typed] == ["Kids"]
    inside = ok(kitchen.get(f"{API}/recipes/tags", params={"q": "ick"}))["tags"]
    assert [t["name"] for t in inside] == ["Quick"]
    # A tag no recipe has any more no longer shows.
    ok(save(kitchen, a, tags=["Quick"]))
    names = [t["name"] for t in ok(kitchen.get(f"{API}/recipes/tags"))["tags"]]
    assert names == ["Batch-friendly", "Quick"]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert sorted(t.name for t in db.scalars(select(Tag))) == ["Batch-friendly", "Quick"]


def test_tags_are_tidied(kitchen: TestClient) -> None:
    recipe = make(kitchen, tags=["  Quick   dinner ", "quick dinner", "Kids"])
    assert recipe["tags"] == ["Kids", "Quick dinner"]
    assert where(bad(kitchen, tags=["x" * 41])) == ["tags.0"]
    assert where(bad(kitchen, tags=["   "])) == ["tags"]
    assert where(bad(kitchen, tags=[f"t{i}" for i in range(21)])) == ["tags"]
    make(kitchen, "Tags", tags=[f"t{i}" for i in range(20)])


def test_a_new_spelling_of_a_tag_uses_the_one_the_household_already_has(
    kitchen: TestClient,
) -> None:
    make(kitchen, "A", tags=["Batch-friendly"])
    assert make(kitchen, "B", tags=["BATCH-FRIENDLY"])["tags"] == ["Batch-friendly"]


# --- Made ahead --------------------------------------------------------------------------------


def foods_named(client: TestClient, name: str) -> list[Food]:
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        return list(db.scalars(select(Food).where(Food.name == name)))


def test_made_ahead_on_makes_a_homemade_ingredient_linked_to_the_recipe(
    kitchen: TestClient,
) -> None:
    recipe = make(kitchen, "Dosa batter", made_ahead=True, makes={"amount": 1.5, "unit": "l"})
    assert recipe["made_ahead"] is True
    assert recipe["homemade"]["name"] == "Dosa batter"
    ingredient = ok(kitchen.get(f"{API}/foods/{recipe['homemade']['id']}"))
    assert ingredient["name"] == "Dosa batter" and ingredient["counted_as"] == "volume"
    # It shows in Ingredients' Recent changes like any new ingredient, with Undo.
    changes = ok(kitchen.get(f"{API}/changes", params={"area": "ingredients"}))["changes"]
    assert [(c["kind"], c["summary"], c["can_undo"]) for c in changes] == [
        ("food_created", "Added Dosa batter", True)
    ]


def test_the_homemade_ingredient_can_have_its_own_name(kitchen: TestClient) -> None:
    recipe = make(kitchen, "Dosa batter", made_ahead=True, homemade_name="Batter (fermented)")
    assert recipe["homemade"]["name"] == "Batter (fermented)"


def test_the_homemade_ingredient_is_counted_to_match_what_the_recipe_makes(
    kitchen: TestClient,
) -> None:
    cases = {"g": "weight", "kg": "weight", "ml": "volume", "l": "volume", "dosas": "count"}
    for unit, counted in cases.items():
        recipe = make(kitchen, f"Batch {unit}", made_ahead=True, makes={"amount": 2, "unit": unit})
        food_ = ok(kitchen.get(f"{API}/foods/{recipe['homemade']['id']}"))
        assert food_["counted_as"] == counted, unit
    plain = make(kitchen, "Plain batch", made_ahead=True)
    assert ok(kitchen.get(f"{API}/foods/{plain['homemade']['id']}"))["counted_as"] == "weight"


def test_saving_again_does_not_make_a_second_ingredient(kitchen: TestClient) -> None:
    recipe = make(kitchen, "Dosa batter", made_ahead=True)
    again = ok(save(kitchen, recipe, time_minutes=30))
    assert again["homemade"] == recipe["homemade"]
    assert len(foods_named(kitchen, "Dosa batter")) == 1


def test_made_ahead_off_unlinks_the_ingredient_and_keeps_it(kitchen: TestClient) -> None:
    recipe = make(kitchen, "Dosa batter", made_ahead=True)
    food_id = recipe["homemade"]["id"]
    off = ok(save(kitchen, recipe, made_ahead=False))
    assert off["made_ahead"] is False and off["homemade"] is None
    assert ok(kitchen.get(f"{API}/foods/{food_id}"))["name"] == "Dosa batter"
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.get(Recipe, recipe["id"]).homemade_food_id is None  # type: ignore[union-attr]


def test_made_ahead_on_again_links_the_kept_ingredient_back_with_its_stock(
    kitchen: TestClient,
) -> None:
    """cabledrawer 19 Oct, R3: off, then on again with the same name, relinks the ingredient
    that was kept, pantry stock and all, instead of making a second one."""
    recipe = make(kitchen, "Dosa batter", made_ahead=True, makes={"amount": 2, "unit": "l"})
    food_id = recipe["homemade"]["id"]
    ok(
        kitchen.post(
            f"{API}/stock", json={"food_id": food_id, "amount": {"amount": 1500, "unit": "ml"}}
        ),
        201,
    )
    off = ok(save(kitchen, recipe, made_ahead=False))
    assert off["homemade"] is None
    again = ok(save(kitchen, off, made_ahead=True))
    assert again["made_ahead"] is True
    assert again["homemade"] == {"id": food_id, "name": "Dosa batter"}
    assert len(foods_named(kitchen, "Dosa batter")) == 1
    assert ok(kitchen.get(f"{API}/foods/{food_id}"))["stock"]["amount"] == 1500


def test_made_ahead_can_be_given_a_different_name_when_switched_on_again(
    kitchen: TestClient,
) -> None:
    recipe = make(kitchen, "Dosa batter", made_ahead=True)
    off = ok(save(kitchen, recipe, made_ahead=False))
    renamed = ok(save(kitchen, off, made_ahead=True, homemade_name="Dosa batter 2"))
    assert renamed["homemade"]["name"] == "Dosa batter 2"
    assert len(foods_named(kitchen, "Dosa batter")) == 1  # the old one is still there


def test_made_ahead_on_again_is_refused_when_another_recipe_holds_the_ingredient(
    kitchen: TestClient,
) -> None:
    first = make(kitchen, "Dosa batter", made_ahead=True)
    second = make(kitchen, "Batter 2")
    response = save(kitchen, second, made_ahead=True, homemade_name="Dosa batter")
    assert response.status_code == 409 and response.json()["code"] == "name_taken"
    assert response.json()["food_id"] == first["homemade"]["id"]
    assert ok(kitchen.get(f"{API}/recipes/{second['id']}"))["made_ahead"] is False
    # And once the first lets it go, the second can have it.
    ok(save(kitchen, first, made_ahead=False))
    taken = ok(save(kitchen, second, made_ahead=True, homemade_name="Dosa batter"))
    assert taken["homemade"]["id"] == first["homemade"]["id"]


def test_an_ordinary_ingredient_with_that_name_is_linked_not_duplicated(
    kitchen: TestClient,
) -> None:
    plain = food(kitchen, "Dosa batter")
    recipe = make(kitchen, "Dosa batter", made_ahead=True)
    assert recipe["homemade"]["id"] == plain["id"]
    assert len(foods_named(kitchen, "Dosa batter")) == 1


def test_a_long_recipe_name_gives_a_homemade_name_that_fits(kitchen: TestClient) -> None:
    recipe = make(kitchen, "b" * 150, made_ahead=True)
    assert recipe["homemade"]["name"] == "b" * 100


# --- Retries: the Idempotency-Key ---------------------------------------------------------------


def test_the_same_create_twice_makes_one_recipe_and_answers_the_same(kitchen: TestClient) -> None:
    headers = {"Idempotency-Key": "make-sambar-1"}
    body = {"name": "Sambar", "tags": ["Quick"], "lines": [{"words": "salt"}]}
    first = kitchen.post(f"{API}/recipes", json=body, headers=headers)
    second = kitchen.post(f"{API}/recipes", json=body, headers=headers)
    assert first.status_code == 201 and second.status_code == 200
    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.json() == first.json()
    assert ok(kitchen.get(f"{API}/recipes"))["total"] == 1


def test_the_same_create_twice_with_made_ahead_does_not_clash_with_itself(
    kitchen: TestClient,
) -> None:
    headers = {"Idempotency-Key": "make-batter-1"}
    body = {"name": "Dosa batter", "made_ahead": True}
    first = kitchen.post(f"{API}/recipes", json=body, headers=headers)
    second = kitchen.post(f"{API}/recipes", json=body, headers=headers)
    assert first.status_code == 201, first.text
    assert second.status_code == 200, second.text  # not 409 name_taken
    assert second.json() == first.json()
    assert len(foods_named(kitchen, "Dosa batter")) == 1
    assert ok(kitchen.get(f"{API}/recipes"))["total"] == 1


def test_the_same_save_twice_is_not_a_conflict_with_yourself(kitchen: TestClient) -> None:
    recipe = make(kitchen)
    headers = {"Idempotency-Key": "save-sambar-1"}
    first = save(kitchen, recipe, name="Sambar 2")
    assert first.status_code == 200
    recipe = ok(first)
    one = kitchen.put(
        f"{API}/recipes/{recipe['id']}",
        json={"name": "Sambar 3", "version": recipe["version"]},
        headers=headers,
    )
    two = kitchen.put(
        f"{API}/recipes/{recipe['id']}",
        json={"name": "Sambar 3", "version": recipe["version"]},
        headers=headers,
    )
    assert one.status_code == 200 and two.status_code == 200, two.text
    assert two.headers["Idempotent-Replayed"] == "true"
    assert one.json()["version"] == two.json()["version"] == recipe["version"] + 1


def test_a_key_reused_for_something_else_is_refused(kitchen: TestClient) -> None:
    headers = {"Idempotency-Key": "one-key"}
    first = ok(kitchen.post(f"{API}/recipes", json={"name": "A"}, headers=headers), 201)
    other = kitchen.put(
        f"{API}/recipes/{first['id']}",
        json={"name": "B", "version": 1},
        headers=headers,
    )
    assert other.status_code == 409 and other.json()["code"] == "key_reused"


def test_saves_are_not_listed_in_recent_changes_and_cannot_be_undone(kitchen: TestClient) -> None:
    made = kitchen.post(f"{API}/recipes", json={"name": "Sambar"}, headers={"Idempotency-Key": "a"})
    recipe = ok(made, 201)
    body = {"name": "Sambar 2", "version": recipe["version"]}
    ok(kitchen.put(f"{API}/recipes/{recipe['id']}", json=body, headers={"Idempotency-Key": "b"}))
    assert ok(kitchen.get(f"{API}/changes"))["changes"] == []
    assert ok(kitchen.get(f"{API}/changes", params={"mine": True, "limit": 1}))["changes"] == []
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        kept = db.scalars(select(Change).where(Change.kind.like("recipe_%"))).all()
        assert sorted(c.kind for c in kept) == ["recipe_created", "recipe_saved"]
        change_id = kept[0].id
    response = kitchen.post(f"{API}/changes/{change_id}/undo")
    assert response.status_code == 409 and response.json()["code"] == "cannot_undo"


def test_without_a_key_nothing_is_remembered(kitchen: TestClient) -> None:
    """The quiet record is only for retries: a request with no Idempotency-Key leaves none."""
    recipe = make(kitchen)
    ok(save(kitchen, recipe, name="Sambar 2"))
    made = make(kitchen, "Dosa batter", made_ahead=True)
    assert made["homemade"] is not None
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        kinds = sorted(c.kind for c in db.scalars(select(Change)))
    assert kinds == ["food_created"]  # only the made-ahead ingredient, which Recent changes shows


def test_a_retried_create_after_the_recipe_was_deleted_is_a_404(kitchen: TestClient) -> None:
    headers = {"Idempotency-Key": "make-then-delete"}
    first = ok(kitchen.post(f"{API}/recipes", json={"name": "Sambar"}, headers=headers), 201)
    ok(kitchen.delete(f"{API}/recipes/{first['id']}"))
    again = kitchen.post(f"{API}/recipes", json={"name": "Sambar"}, headers=headers)
    assert again.status_code == 404 and again.json()["code"] == "not_found"
    assert ok(kitchen.get(f"{API}/recipes"))["total"] == 0


def test_bumping_versions_never_reaches_another_household(kitchen: TestClient) -> None:
    from mealwright.history import bump_recipes

    recipe = make(kitchen)
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        bump_recipes(db, 2, [recipe["id"]], None, "Next door")  # household 2 asks for it
        db.commit()
        assert db.get(Recipe, recipe["id"]).version == 1  # type: ignore[union-attr]
        bump_recipes(db, 1, [recipe["id"]], None, "Mealwright")
        db.commit()
        assert db.get(Recipe, recipe["id"]).version == 2  # type: ignore[union-attr]


# --- Next to the 4 MiB limit and the number-too-big handler ---------------------------------------


def test_a_request_over_4_mib_is_refused_before_it_is_read(kitchen: TestClient) -> None:
    big = "x" * (4 * 1024 * 1024 + 10)
    response = kitchen.post(f"{API}/recipes", json={"name": "Sambar", "source_note": big})
    assert response.status_code == 413, response.text[:200]
    assert response.json()["detail"] == "That’s too much to send in one go."
    assert ok(kitchen.get(f"{API}/recipes"))["total"] == 0


def test_the_biggest_allowed_recipe_is_well_under_that_limit(kitchen: TestClient) -> None:
    lines = [{"words": "w" * 200, "note": "n" * 200} for _ in range(200)]
    steps = [{"text": "s" * 5000} for _ in range(100)]
    body = {"name": "n" * 200, "lines": lines, "steps": steps, "description": "d" * 200}
    assert len(str(body)) < 4 * 1024 * 1024
    assert kitchen.post(f"{API}/recipes", json=body).status_code == 201


def test_absurd_numbers_are_a_422_never_a_server_error(kitchen: TestClient) -> None:
    huge = 10**400
    for body in [
        {"name": "A", "time_minutes": huge},
        {"name": "A", "serves": huge},
        {"name": "A", "nutrition": {"kcal": huge}},
        {"name": "A", "makes": {"amount": huge, "unit": "g"}},
        {"name": "A", "lines": [{"words": "x", "amount": huge}]},
        {"name": "A", "lines": [{"words": "x", "food_id": huge}]},
        {"name": "A", "lines": [{"words": "x", "recipe_id": huge}]},
    ]:
        response = kitchen.post(f"{API}/recipes", json=body)
        assert response.status_code in (404, 422), (body, response.status_code, response.text[:200])
    assert kitchen.get(f"{API}/recipes/{huge}").status_code in (404, 422)
    assert kitchen.put(
        f"{API}/recipes/{huge}", json={"name": "A", "version": huge}
    ).status_code in (
        404,
        422,
    )
