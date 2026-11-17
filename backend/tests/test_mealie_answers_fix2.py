"""Fix round 2 of B6a: the import's own page reads an import whose drafts were answered into
Recipes. Made-up recipes."""

from pathlib import Path

from fastapi.testclient import TestClient
from test_mealie_answers import answer
from test_mealie_answers_fix1 import bring, make_food
from test_mealie_import import API

A, B = (f"a{i:031d}" for i in range(2))


def test_the_imports_page_counts_a_recipe_answered_into_recipes(
    kitchen: TestClient, tmp_path: Path
) -> None:
    bring(kitchen, tmp_path, {A: ["2 tbsp soya sauce"], B: ["1 egg"]})
    soy = make_food(kitchen, "Soy sauce")
    done = answer(kitchen, "soya sauce", "ingredient", food_id=soy)
    assert done.json()["moved"] == 1, done.text
    current = kitchen.get(f"{API}/mealie-imports/current")
    assert current.status_code == 200, current.text
    body = current.json()["current"]
    assert body["counts"]["saved"] == 1 and body["counts"]["drafts"] == 1, body["counts"]
    assert [r["name"] for r in body["to_check"]] == ["Dish b"]
    one = kitchen.get(f"{API}/mealie-imports/{body['id']}")
    assert one.status_code == 200, one.text
    assert one.json()["counts"] == body["counts"]
