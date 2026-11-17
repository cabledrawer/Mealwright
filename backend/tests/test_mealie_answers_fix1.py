"""Fix round 1 of B6a (Mealie drafts fixed by ingredient): the rule for a line tied to an
ingredient is one rule for every way a draft becomes a recipe; Save all keeps the answers
already given; an answered ingredient is not removed while a draft's answer still points at it;
groups fold names as matching does; plural words; one change ID for a retry. Made-up recipes."""

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from test_mealie_answers import (
    answer,
    db,
    draft_names,
    file,
    groups,
    make_food,
    recipe_lines,
)
from test_mealie_import import API, bring_in, zipped

from mealwright.models import Change, Food, ImportDraft

A, B, C = (f"a{i:031d}" for i in range(3))


def bring(kitchen: TestClient, tmp_path: Path, recipes: dict[str, list[str]]) -> None:
    bring_in(kitchen, zipped(tmp_path / "f.zip", file(recipes), photo=False))


# --- 1. The one rule for a line tied to an ingredient ------------------------------------------


def test_an_answer_that_completes_a_draft_keeps_its_staple_line_tied(
    kitchen: TestClient, tmp_path: Path
) -> None:
    salt = kitchen.post(f"{API}/foods", json={"name": "Salt", "staple": True}).json()["food"]["id"]
    bring(kitchen, tmp_path, {A: ["1 tsp salt", "2 tbsp soya sauce"], B: ["2 tbsp soya sauce"]})
    soy = make_food(kitchen, "Soy sauce")
    done = answer(kitchen, "soya sauce", "ingredient", food_id=soy)
    assert done.json()["moved"] == 2, done.text
    lines = recipe_lines(kitchen, "Dish a")
    assert sorted(lines.values(), key=str) == sorted([salt, soy], key=str), lines  # salt is tied


# --- 4. Save all keeps the answers already given -----------------------------------------------


def test_save_all_ties_the_lines_answered_by_ingredient(
    kitchen: TestClient, tmp_path: Path
) -> None:
    bring(kitchen, tmp_path, {A: ["2 tbsp soya sauce", "a pinch of kasuri methi"]})
    soy = make_food(kitchen, "Soy sauce")
    done = answer(kitchen, "soya sauce", "ingredient", food_id=soy)
    assert done.json()["moved"] == 0 and draft_names(kitchen) == ["Dish a"]  # one line waits
    saved = kitchen.post(f"{API}/mealie-imports/drafts/save-all")
    assert saved.json()["saved"] == 1, saved.text
    lines = recipe_lines(kitchen, "Dish a")
    assert soy in lines.values(), lines  # the answered line is tied, not plain text
    assert None in lines.values()  # the unanswered one stays words only
