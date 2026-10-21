"""On screen it's always "ingredient", never "food" (cabledrawer 17 Oct).

"Food" stays the word inside the code, the data model and the API's field names and
codes. Every sentence the API sends to be shown (error details, change summaries, undo
messages, ask-once questions, as-sold text) must say "ingredient".
"""

import ast
import re
from pathlib import Path

from fastapi.testclient import TestClient

import mealwright

FOOD = re.compile(r"\bfoods?\b", re.IGNORECASE)
SOURCE = Path(mealwright.__file__).parent
API = "/api/v1"


def _docstrings(tree: ast.AST) -> set[int]:
    ids = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = node.body
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                ids.add(id(body[0].value))
    return ids


def test_no_sentence_in_the_code_says_food() -> None:
    """Every string in the app that reads like a sentence (it has a space), apart from
    docstrings, is checked. Names, paths and codes ("food_id", "/foods") have no space."""
    found = []
    for path in sorted(SOURCE.rglob("*.py")):
        if "migrations" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = _docstrings(tree)
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in skip
                and " " in node.value
                and FOOD.search(node.value)
                and not node.value.startswith(("POST ", "GET ", "PATCH ", "DELETE "))
            ):
                found.append(f"{path.relative_to(SOURCE)}:{node.lineno}: {node.value!r}")
    assert found == []


def test_error_paths_say_ingredient(kitchen: TestClient) -> None:
    """Run through the error paths and check what the person would read."""
    toor = kitchen.post(f"{API}/foods", json={"name": "Toor dal"}).json()["food"]
    other = kitchen.post(f"{API}/foods", json={"name": "Moong dal"}).json()["food"]
    responses = [
        kitchen.post(f"{API}/foods", json={"name": "toor dal"}),
        kitchen.get(f"{API}/foods/9999"),
        kitchen.post(f"{API}/foods/{toor['id']}/merge", json={"into_id": toor["id"]}),
        kitchen.post(f"{API}/foods/{toor['id']}/stand-ins", json={"food_id": toor["id"]}),
        kitchen.post(f"{API}/foods/{toor['id']}/not-the-same", json={"food_id": toor["id"]}),
        kitchen.patch(f"{API}/foods/{toor['id']}", json={"name": "Moong dal"}),
        kitchen.patch(
            f"{API}/foods/{toor['id']}", json={"running_low_at": {"amount": 1, "unit": "cup"}}
        ),
        kitchen.post(
            f"{API}/foods/{other['id']}/used", json={"amount": {"amount": 1, "unit": "g"}}
        ),
        kitchen.post(f"{API}/stock/9999/used"),
    ]
    kitchen.post(
        f"{API}/stock", json={"food_id": toor["id"], "amount": {"amount": 1, "unit": "kg"}}
    )
    responses.append(kitchen.delete(f"{API}/foods/{toor['id']}"))
    details = [r.json()["detail"] for r in responses]
    assert all(r.status_code >= 400 for r in responses)
    assert [d for d in details if FOOD.search(d)] == []
    assert "There’s already an ingredient called Toor dal." in details
    assert "That ingredient isn’t here any more." in details

    summaries = [c["summary"] for c in kitchen.get(f"{API}/changes").json()["changes"]]
    assert [s for s in summaries if FOOD.search(s)] == []
