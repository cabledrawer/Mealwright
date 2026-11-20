# ruff: noqa: F811  (the fixtures come from test_recipe_import.py and are used by name)
"""A section made its own recipe (0.8 W4e, F190, cabledrawer 8 Nov): the section's lines and steps
become a new Made ahead recipe, the main recipe uses it as one line, and both are saved together
(all or nothing), with one entry in Recent changes and one Undo."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_drafts import kept
from test_recipe_import import API, Web, counts, cupboard, review, web  # noqa: F401
from test_recipe_import import save as save_import
from test_recipes import make

from mealwright import recipes
from mealwright.errors import Problem
from mealwright.models import Food, Recipe


def line(words: str, amount: float | None = None, unit: str | None = None, **more: Any) -> dict:
    return {"kind": "ingredient", "words": words, "amount": amount, "unit": unit, **more}


def body(**more: Any) -> dict[str, Any]:
    """Masala dosa, with its batter as its own recipe: the batter's lines and steps are the
    section's, the dosa uses it as one line "Dosa batter · 4 cups"."""
    base: dict[str, Any] = {
        "name": "Masala dosa",
        "serves": 4,
        "lines": [
            line("Dosa batter", 4, "cup", link={"kind": "own_recipe", "own_recipe": 0}),
            line("Ghee", link={"kind": "new", "name": "Ghee", "counted_as": "weight"}),
        ],
        "steps": [{"kind": "step", "text": "Spread and fry."}],
        "own_recipes": [
            {
                "name": "Dosa batter",
                "makes": {"amount": 4, "unit": "cup"},
                "lines": [
                    line("Urad dal", 1, "cup", link={"kind": "new", "name": "Urad dal"}),
                    line("Idli rice", 3, "cup", link={"kind": "new", "name": "Idli rice"}),
                    line("Ghee", link={"kind": "new", "name": "Ghee"}),
                ],
                "steps": [
                    {"kind": "step", "text": "Soak the dal."},
                    {"kind": "step", "text": "Grind and ferment."},
                ],
            }
        ],
    }
    return {**base, **more}


def recipes_named(client: TestClient) -> dict[str, Recipe]:
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        rows = db.scalars(select(Recipe).where(Recipe.removed_at.is_(None))).all()
        for row in rows:
            db.expunge(row)
        return {row.name: row for row in rows}


def test_both_recipes_are_saved_together_and_the_main_one_uses_the_other(
    kitchen: TestClient, web: Web
) -> None:
    saved = ok(save_import(kitchen, body()), 201)
    both = recipes_named(kitchen)
    assert set(both) == {"Masala dosa", "Dosa batter"}
    batter = both["Dosa batter"]
    assert batter.made_ahead and batter.homemade_food_id is not None
    shown = ok(kitchen.get(f"{API}/recipes/{batter.id}"))
    assert [step["text"] for step in shown["steps"]] == ["Soak the dal.", "Grind and ferment."]
    assert [item["words"] for item in shown["lines"]] == ["Urad dal", "Idli rice", "Ghee"]
    assert shown["makes"]["unit"] == "cup" and shown["made_ahead"] is True
    dosa = ok(kitchen.get(f"{API}/recipes/{saved['recipe']['id']}"))
    first = dosa["lines"][0]
    assert first["link"] == "recipe" and first["recipe"]["name"] == "Dosa batter"
    assert (first["amount"], first["unit"]) == (4, "cup")
    # An ingredient both used is made once.
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        ghee = db.scalars(select(Food).where(Food.name == "Ghee")).all()
    assert len(ghee) == 1


def test_one_entry_in_recent_changes_names_both(kitchen: TestClient, web: Web) -> None:
    saved = ok(save_import(kitchen, body()), 201)
    assert saved["change"]["summary"].startswith("Imported Masala dosa and Dosa batter")
    entries = ok(kitchen.get(f"{API}/changes"))["changes"]
    assert [c["kind"] for c in entries if c["kind"] != "undo"] == ["recipe_imported"]


def test_if_the_section_recipe_fails_nothing_is_saved(kitchen: TestClient, web: Web) -> None:
    # Another recipe already holds the name "Dosa batter" as its Made ahead ingredient.
    make(kitchen, "Dosa batter", made_ahead=True, makes={"amount": 1, "unit": "l"})
    before = counts(kitchen)
    refused = save_import(kitchen, body())
    assert refused.status_code == 409
    assert refused.json()["own_recipe"] == 0
    assert counts(kitchen) == before  # not even the new ingredients made before it


def test_if_the_main_recipe_fails_after_the_section_neither_is_saved(
    kitchen: TestClient, web: Web, monkeypatch: pytest.MonkeyPatch
) -> None:
    before = counts(kitchen)
    real = recipes.save
    calls: list[str] = []

    def second_one_fails(*args: Any, **kwargs: Any) -> Any:
        calls.append(args[2].name)
        if len(calls) == 2:
            raise Problem(422, "invalid_recipe", "Couldn’t save that.")
        return real(*args, **kwargs)

    monkeypatch.setattr(recipes, "save", second_one_fails)
    assert save_import(kitchen, body()).status_code == 422
    assert calls == ["Dosa batter", "Masala dosa"]  # the section was made first, then undone
    monkeypatch.undo()
    assert counts(kitchen) == before
    assert recipes_named(kitchen) == {}


def test_a_new_ingredient_name_already_taken_saves_nothing(kitchen: TestClient, web: Web) -> None:
    ok(save_import(kitchen, body()), 201)
    before = counts(kitchen)
    again = save_import(kitchen, body(name="Another dosa"))
    assert again.status_code in (409, 422)
    assert counts(kitchen) == before


def test_a_section_with_no_line_or_a_bad_place_is_refused(kitchen: TestClient, web: Web) -> None:
    orphan = body()
    orphan["lines"] = [line("Ghee", link={"kind": "new", "name": "Ghee"})]
    assert save_import(kitchen, orphan).status_code == 422
    far = body()
    far["lines"][0]["link"] = {"kind": "own_recipe", "own_recipe": 3}
    assert save_import(kitchen, far).status_code == 422
    nested = body()
    nested["own_recipes"][0]["lines"][0]["link"] = {"kind": "own_recipe", "own_recipe": 0}
    assert save_import(kitchen, nested).status_code == 422
    assert recipes_named(kitchen) == {}


def test_one_undo_takes_both_recipes_and_the_new_ingredients_back(
    kitchen: TestClient, web: Web
) -> None:
    before = counts(kitchen)
    saved = ok(save_import(kitchen, body()), 201)
    assert counts(kitchen)[0] == before[0] + 2
    ok(kitchen.post(f"{API}/changes/{saved['change']['id']}/undo"))
    assert recipes_named(kitchen) == {}
    names = [r["name"] for r in ok(kitchen.get(f"{API}/recipes"))["recipes"]]
    assert "Dosa batter" not in names and "Masala dosa" not in names
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        left = db.scalars(select(Food.name).where(Food.removed_at.is_(None))).all()
    assert "Dosa batter" not in left and "Urad dal" not in left


def test_the_save_can_be_retried_without_making_a_second_pair(
    kitchen: TestClient, web: Web
) -> None:
    key = {"Idempotency-Key": "own-recipe-1"}
    first = ok(save_import(kitchen, body(), **key), 201)
    again = save_import(kitchen, body(), **key)
    assert again.status_code == 200 and again.json()["recipe"] == first["recipe"]
    assert len(recipes_named(kitchen)) == 2


def test_the_openapi_describes_the_section_recipes(kitchen: TestClient) -> None:
    schemas = ok(kitchen.get("/api/v1/openapi.json"))["components"]["schemas"]
    assert "own_recipes" in schemas["ImportSave"]["properties"]
    assert "own_recipe" in schemas["ImportLinkIn"]["properties"]


def test_a_draft_keeps_a_section_made_its_own_recipe(kitchen: TestClient, web: Web) -> None:
    text = (
        "Masala dosa\nIngredients\nFor the batter\n1 cup urad dal\nFor the dosa\n1 tsp ghee\n"
        "Method\n1. Fry.\n"
    )
    shown = review(kitchen, text)
    heading = next(i for i, ln in enumerate(shown["lines"]) if ln["kind"] == "heading")
    assert "own" not in shown["lines"][heading] or shown["lines"][heading]["own"] is None
    shown["lines"][heading]["own"] = {"name": "Dosa batter", "amount": 4, "unit": "cup"}
    made = kept(kitchen, shown, text_=text)
    back = ok(kitchen.get(f"{API}/recipes/drafts/{made['id']}"))
    assert back["review"]["lines"][heading]["own"] == {
        "name": "Dosa batter",
        "amount": 4,
        "unit": "cup",
    }
    # The server's own reading never sets it.
    assert all(ln.get("own") is None for ln in review(kitchen, text)["lines"])


def test_another_households_ids_inside_a_section_recipe_are_refused_and_nothing_is_saved(
    kitchen: TestClient, neighbour: TestClient, web: Web
) -> None:
    from sync_kit import food

    onions = food(kitchen, "Onions")
    batter = ok(kitchen.post(f"{API}/recipes", json={"name": "Batter", "made_ahead": True}), 201)
    home = cupboard(kitchen)
    foreign = [
        {"kind": "ingredient", "food_id": onions["id"]},
        {"kind": "recipe", "recipe_id": batter["id"]},
        {"kind": "new", "name": "Rice", "place_id": home},
        {"kind": "recipe", "recipe_id": batter["id"], "place_id": home},
    ]
    before = counts(neighbour)
    for link in foreign:
        attempt = body()
        attempt["own_recipes"][0]["lines"][0]["link"] = link
        response = save_import(neighbour, attempt)
        assert response.status_code == 404, link
        assert ok(neighbour.get(f"{API}/recipes"))["recipes"] == []
        assert counts(neighbour) == before


def test_undo_after_the_main_recipe_was_deleted_still_takes_the_section_recipe_back(
    kitchen: TestClient, web: Web
) -> None:
    saved = ok(save_import(kitchen, body()), 201)
    assert kitchen.delete(f"{API}/recipes/{saved['recipe']['id']}").status_code == 200
    ok(kitchen.post(f"{API}/changes/{saved['change']['id']}/undo"))
    assert recipes_named(kitchen) == {}


@pytest.mark.parametrize(
    "amount", [float("nan"), float("inf"), -1, 0, 1_000_001], ids=lambda v: str(v)
)
def test_a_draft_refuses_a_section_amount_that_makes_no_sense(
    kitchen: TestClient, web: Web, amount: float
) -> None:
    from mealwright.api.v1.import_schemas import OwnRecipeNote

    with pytest.raises(ValueError):
        OwnRecipeNote(name="Batter", amount=amount, unit="cup")
    with pytest.raises(ValueError):
        OwnRecipeNote(name="\u200b \u200d", amount=1, unit="cup")


def test_a_section_recipes_name_with_a_hidden_character_is_refused(
    kitchen: TestClient, web: Web
) -> None:
    from mealwright.api.v1.import_schemas import OwnRecipeNote

    with pytest.raises(ValueError):
        OwnRecipeNote(name="Dosa\u200b batter", amount=4, unit="cup")
    assert OwnRecipeNote(name="  Dosa   batter ", amount=4, unit="cup").name == "Dosa batter"
    attempt = body()
    attempt["own_recipes"][0]["name"] = "Dosa\u200b batter"
    before = counts(kitchen)
    assert save_import(kitchen, attempt).status_code == 422
    assert counts(kitchen) == before
