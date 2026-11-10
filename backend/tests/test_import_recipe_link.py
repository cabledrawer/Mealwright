# ruff: noqa: F811  (the fixtures come from test_recipe_import.py and are used by name)
"""A line on Check made in another recipe (0.8 W4d, F188, cabledrawer 8 Nov): the line is saved with
the same recipe-in-recipe link as a recipe line made in the editor, no new data model. Where the
pantry keeps it goes on that recipe's own made-ahead ingredient when that has no usual place yet.
The web is faked as in test_recipe_import.py: no test goes online."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_drafts import kept
from test_recipe_import import API, PASTED, Web, review, to_save, web  # noqa: F401
from test_recipe_import import save as save_import
from test_recipes import make

from mealwright.models import Food, Place

TEXT = "Masala dosa\nIngredients\n1 cup flour\n4 cups dosa batter, as above\nMethod\n1. Fry.\n"


def place(client: TestClient, name: str) -> int:
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        return db.scalars(select(Place.id).where(Place.name == name)).one()


def batter_line(shown: dict[str, Any]) -> int:
    return next(i for i, line in enumerate(shown["lines"]) if "batter" in line["words"])


def test_a_line_made_in_another_recipe_is_saved_as_the_recipe_in_recipe_link(
    kitchen: TestClient, web: Web
) -> None:
    batter = make(kitchen, "Dosa batter", made_ahead=True, makes={"amount": 1.5, "unit": "l"})
    shown = review(kitchen, TEXT)
    at = batter_line(shown)
    body = to_save(shown, {at: {"kind": "recipe", "recipe_id": batter["id"]}})
    saved = ok(save_import(kitchen, body), 201)
    recipe = ok(kitchen.get(f"{API}/recipes/{saved['recipe']['id']}"))
    line = recipe["lines"][at]
    assert line["link"] == "recipe" and line["recipe"] == {
        "id": batter["id"],
        "name": "Dosa batter",
    }
    assert line["food"] is None
    assert (line["amount"], line["unit"]) == (4, "cup")
    # The batter now says it is used by the new recipe, as for a line made in the editor.
    used = ok(kitchen.get(f"{API}/recipes/{batter['id']}"))["used_by"]
    assert [r["name"] for r in used] == ["Masala dosa"]


def test_the_place_goes_on_the_made_ahead_ingredient_that_has_none_and_undo_takes_it_back(
    kitchen: TestClient, web: Web
) -> None:
    batter = make(kitchen, "Dosa batter", made_ahead=True, makes={"amount": 1.5, "unit": "l"})
    fridge = place(kitchen, "Fridge")
    shown = review(kitchen, TEXT)
    at = batter_line(shown)
    link = {"kind": "recipe", "recipe_id": batter["id"], "place_id": fridge}
    saved = ok(save_import(kitchen, to_save(shown, {at: link})), 201)
    food = ok(kitchen.get(f"{API}/foods/{batter['homemade']['id']}"))
    assert food["place"]["name"] == "Fridge"
    ok(kitchen.post(f"{API}/changes/{saved['change']['id']}/undo"))
    food = ok(kitchen.get(f"{API}/foods/{batter['homemade']['id']}"))
    assert food["place"] is None


def test_a_place_the_ingredient_already_has_is_left_alone(kitchen: TestClient, web: Web) -> None:
    batter = make(kitchen, "Dosa batter", made_ahead=True, makes={"amount": 1.5, "unit": "l"})
    freezer = place(kitchen, "Freezer")
    ok(kitchen.patch(f"{API}/foods/{batter['homemade']['id']}", json={"place_id": freezer}))
    shown = review(kitchen, TEXT)
    link = {"kind": "recipe", "recipe_id": batter["id"], "place_id": place(kitchen, "Fridge")}
    ok(save_import(kitchen, to_save(shown, {batter_line(shown): link})), 201)
    food = ok(kitchen.get(f"{API}/foods/{batter['homemade']['id']}"))
    assert food["place"]["name"] == "Freezer"


def test_a_recipe_that_is_not_made_ahead_just_links(kitchen: TestClient, web: Web) -> None:
    chutney = make(kitchen, "Coconut chutney")
    shown = review(kitchen, TEXT)
    link = {"kind": "recipe", "recipe_id": chutney["id"], "place_id": place(kitchen, "Fridge")}
    saved = ok(save_import(kitchen, to_save(shown, {batter_line(shown): link})), 201)
    line = ok(kitchen.get(f"{API}/recipes/{saved['recipe']['id']}"))["lines"][batter_line(shown)]
    assert line["link"] == "recipe"
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalars(select(Food).where(Food.name == "Coconut chutney")).first() is None


def test_a_recipe_that_is_gone_or_not_yours_is_refused_at_that_line(
    kitchen: TestClient, web: Web
) -> None:
    shown = review(kitchen, TEXT)
    at = batter_line(shown)
    for missing in (987654, 0):
        link = {"kind": "recipe", "recipe_id": missing}
        refused = save_import(kitchen, to_save(shown, {at: link}))
        assert refused.status_code in (404, 422)
    gone = make(kitchen, "Old batter")
    ok(kitchen.delete(f"{API}/recipes/{gone['id']}"))
    refused = save_import(
        kitchen, to_save(shown, {at: {"kind": "recipe", "recipe_id": gone["id"]}})
    )
    assert refused.status_code == 404
    assert refused.json()["line"] == at


def test_a_recipe_link_needs_the_recipe(kitchen: TestClient, web: Web) -> None:
    shown = review(kitchen, TEXT)
    refused = save_import(kitchen, to_save(shown, {batter_line(shown): {"kind": "recipe"}}))
    assert refused.status_code == 422


def test_a_draft_keeps_the_recipe_choice_and_shows_the_recipes_new_name(
    kitchen: TestClient, web: Web
) -> None:
    from test_drafts import put

    batter = make(kitchen, "Dosa batter", made_ahead=True)
    shown = review(kitchen, TEXT)
    at = batter_line(shown)
    choice = {"kind": "recipe", "recipe": {"id": batter["id"], "name": "Dosa batter"}}
    draft = kept(kitchen, shown, text_=TEXT, choices={"lines": {str(at): choice}})
    again = ok(kitchen.get(f"{API}/recipes/drafts/{draft['id']}"))
    assert again["choices"]["lines"][str(at)]["recipe"]["name"] == "Dosa batter"
    # Renamed since: the draft shows the new name. Deleted since: no choice, pick again.
    renamed = {**batter, "name": "Idli and dosa batter"}
    from test_recipes import save as save_recipe

    ok(save_recipe(kitchen, renamed))
    again = ok(kitchen.get(f"{API}/recipes/drafts/{draft['id']}"))
    assert again["choices"]["lines"][str(at)]["recipe"]["name"] == "Idli and dosa batter"
    ok(kitchen.delete(f"{API}/recipes/{batter['id']}"))
    again = ok(kitchen.get(f"{API}/recipes/drafts/{draft['id']}"))
    assert again["choices"]["lines"] == {}
    assert put(kitchen, draft["id"], shown, text_=TEXT).status_code == 200


def test_a_recipe_choice_with_no_recipe_is_refused_in_a_draft(
    kitchen: TestClient, web: Web
) -> None:
    shown = review(kitchen, TEXT)
    refused = kitchen.post(
        f"{API}/recipes/drafts",
        json={"text": TEXT, "review": shown, "choices": {"lines": {"1": {"kind": "recipe"}}}},
    )
    assert refused.status_code == 422


def test_a_line_added_on_check_and_never_named_does_not_count_in_the_drafts_progress(
    kitchen: TestClient, web: Web
) -> None:
    shown = review(kitchen, TEXT)
    blank = {**shown["lines"][0], "written": "", "words": "", "label": "needs_you", "food": None}
    shown = {**shown, "lines": [*shown["lines"], blank]}
    draft = kept(kitchen, shown, text_=TEXT)
    assert draft["lines_total"] == 2
