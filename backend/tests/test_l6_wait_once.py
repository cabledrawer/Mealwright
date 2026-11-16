"""L6 (cabledrawer 13 and 15 Nov; beta.2): an imported recipe's wait is taken off its time only
once. A recipe saved from a link or pasted text carries a hidden mark that its saved Time is
already the work; the plan then leaves it alone. A hand-made recipe, and anything from Mealie
(which keeps the page's time), has no mark and follows the plain L6 rule."""

# ruff: noqa: F811  (the web fixture comes from test_recipe_import.py and is used by name)
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_mealie_import import API as MEALIE_API
from test_mealie_import import SOUP, bring_in, database, zipped
from test_plan import db_of
from test_recipe_import import LINK, Web, review, switch, to_save, web  # noqa: F401
from test_recipe_import import save as save_import
from test_recipes import make, save
from test_start_ahead import SAT, options

from mealwright.models import Recipe, RecipeMethod
from mealwright.outbound import Connection

API = "/api/v1"
MARINATE_4H = {"kind": "marinate", "min_minutes": 240}
PASTED = "Wait pasted stew\nIngredients\n2 cups rice\nMethod\n1. Soak the rice.\n2. Cook it.\n"


def marked(kitchen: TestClient, recipe_id: int) -> tuple[bool, list[bool]]:
    """The recipe's hidden mark, and each way's."""
    with db_of(kitchen) as db:
        recipe = db.get(Recipe, recipe_id)
        assert recipe is not None
        ways = db.scalars(
            select(RecipeMethod)
            .where(RecipeMethod.recipe_id == recipe_id)
            .order_by(RecipeMethod.position)
        )
        return recipe.time_is_work_only, [w.time_is_work_only for w in ways]


def imported(kitchen: TestClient, minutes: int | None = 360, wait: bool = True) -> dict[str, Any]:
    """A pasted import, saved with `minutes` of work and a 4 h marinade on its first step."""
    body = to_save(review(kitchen, PASTED))
    body["name"] = "Wait stew"
    body["time_minutes"] = minutes
    body["steps"][0]["wait"] = MARINATE_4H if wait else None
    saved: dict[str, Any] = ok(save_import(kitchen, body), 201)
    return saved


def test_an_import_with_six_hours_of_work_and_a_four_hour_marinade_keeps_the_six_hours(
    kitchen: TestClient,
) -> None:
    recipe = imported(kitchen)["recipe"]
    assert marked(kitchen, recipe["id"]) == (True, [True])
    assert options(kitchen, recipe, SAT)["active_minutes"] == 360  # not 120


def test_the_same_numbers_made_by_hand_keep_todays_rule(kitchen: TestClient) -> None:
    recipe = make(
        kitchen,
        "Hand stew",
        time_minutes=360,
        steps=[{"text": "Marinate.", "wait": MARINATE_4H}, {"text": "Cook."}],
    )
    assert marked(kitchen, recipe["id"]) == (False, [False])
    assert options(kitchen, recipe, SAT)["active_minutes"] == 120


def test_a_link_import_is_marked_too(kitchen: TestClient, web: Web) -> None:
    switch(kitchen, Connection.RECIPE_IMPORT)
    web.pages[LINK] = (
        "<html><head><script type='application/ld+json'>"
        '{"@type":"Recipe","name":"Link stew","totalTime":"PT10H",'
        '"recipeIngredient":["2 cups rice"],"recipeInstructions":['
        '{"@type":"HowToStep","text":"Marinate the rice for 4 hours."},'
        '{"@type":"HowToStep","text":"Cook it."}]}</script></head><body></body></html>'
    )
    shown = review(kitchen, LINK)
    assert shown["time_minutes"] == 360 and shown["page_time_minutes"] == 600
    recipe = ok(save_import(kitchen, to_save(shown)), 201)["recipe"]
    assert marked(kitchen, recipe["id"]) == (True, [True])
    assert options(kitchen, recipe, SAT)["active_minutes"] == 360


def test_an_import_with_no_wait_is_not_marked(kitchen: TestClient) -> None:
    recipe = imported(kitchen, 360, wait=False)["recipe"]
    assert marked(kitchen, recipe["id"]) == (False, [False])


def test_two_ways_are_each_marked_by_their_own_steps(kitchen: TestClient) -> None:
    body = to_save(review(kitchen, PASTED))
    body["name"] = "Two way stew"
    body["time_minutes"] = 360
    body["steps"][0]["wait"] = MARINATE_4H
    body["method_name"] = "Stovetop"
    body["second_method"] = {"name": "Oven", "steps": [{"kind": "step", "text": "Bake."}]}
    recipe = ok(save_import(kitchen, body), 201)["recipe"]
    assert marked(kitchen, recipe["id"]) == (True, [True, False])


def test_a_mealie_recipe_is_not_marked_and_keeps_the_pages_time(
    kitchen: TestClient, tmp_path: Path
) -> None:
    data = database()
    data["recipes"][0]["total_time"] = "10 hours"
    data["recipe_instructions"][0]["text"] = "Marinate the lentils for 4 hours."
    bring_in(kitchen, zipped(tmp_path / "m.zip", data))
    with db_of(kitchen) as db:
        dal = db.scalars(select(Recipe).where(Recipe.name == "Red lentil dal")).one()
        assert dal.time_minutes == 600  # the page's own time, as Mealie gave it
        assert dal.time_is_work_only is False
        assert not any(w.time_is_work_only for w in db.scalars(select(RecipeMethod)))


def test_a_mealie_draft_saved_from_drafts_is_not_marked_but_the_same_save_without_it_is(
    kitchen: TestClient, tmp_path: Path
) -> None:
    data = database()
    data["recipes"][1]["total_time"] = "6 hours"
    data["recipe_instructions"][1]["text"] = "Marinate the stock for 4 hours."
    bring_in(kitchen, zipped(tmp_path / "m.zip", data))
    (draft,) = kitchen.get(f"{MEALIE_API}/recipes/drafts").json()["drafts"]
    opened = kitchen.get(f"{MEALIE_API}/recipes/drafts/{draft['id']}").json()
    body = to_save(opened["review"])
    body["time_minutes"] = 360
    body["steps"][0]["wait"] = MARINATE_4H
    body["draft_id"] = draft["id"]
    made = ok(save_import(kitchen, body), 201)["recipe"]
    assert marked(kitchen, made["id"]) == (False, [False])
    body.pop("draft_id")
    body["name"] = "Soup again"
    again = ok(save_import(kitchen, body), 201)["recipe"]
    assert marked(kitchen, again["id"]) == (True, [True])
    assert SOUP  # the file's own soup is the draft above


def test_changing_the_time_by_hand_clears_the_mark_and_the_same_time_keeps_it(
    kitchen: TestClient,
) -> None:
    recipe = imported(kitchen)["recipe"]
    full = ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))
    again = ok(save(kitchen, full, time_minutes=360))  # Save with the Time as it was
    assert again["time_minutes"] == 360
    assert marked(kitchen, recipe["id"]) == (True, [True])
    changed = ok(save(kitchen, again, time_minutes=400))
    assert changed["time_minutes"] == 400
    assert marked(kitchen, recipe["id"]) == (False, [False])
    assert options(kitchen, changed, SAT)["active_minutes"] == 160  # the plain L6 rule


def test_a_copy_keeps_the_mark(kitchen: TestClient) -> None:
    recipe = imported(kitchen)["recipe"]
    copy = ok(kitchen.post(f"{API}/recipes/{recipe['id']}/duplicate"), 201)
    assert marked(kitchen, copy["id"]) == (True, [True])
