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
        kitchen.post(f"{API}/foods/{toor['id']}/mark-not-same", json={"food_id": toor["id"]}),
        kitchen.patch(f"{API}/foods/{toor['id']}", json={"name": "Moong dal"}),
        kitchen.patch(
            f"{API}/foods/{toor['id']}", json={"running_low_at": {"amount": 1, "unit": "cup"}}
        ),
        kitchen.post(f"{API}/foods/{other['id']}/use", json={"amount": {"amount": 1, "unit": "g"}}),
        kitchen.post(f"{API}/stock/9999/use"),
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


def _sentences() -> list[tuple[str, str]]:
    """Every string in the app that reads like a sentence shown to a person (a capital letter,
    a space, and a full stop, question or exclamation mark at the end), docstrings apart."""
    found = []
    for path in sorted(SOURCE.rglob("*.py")):
        if "migrations" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        skip = _docstrings(tree)
        for node in ast.walk(tree):
            text = node.value if isinstance(node, ast.Constant) else None
            if (
                isinstance(text, str)
                and id(node) not in skip
                and " " in text
                and "\n" not in text
                and text[:1].isupper()
                and text.endswith((".", "?", "!"))
            ):
                found.append((f"{path.relative_to(SOURCE)}:{node.lineno}", text))
    return found


def test_each_sentence_is_written_once() -> None:
    """One constant per sentence (0.9.5-beta.3, D2, BE30): a sentence said in more than one
    place is a named constant, imported, so two copies can't drift apart."""
    places: dict[str, list[str]] = {}
    for where, text in _sentences():
        places.setdefault(text, []).append(where)
    assert {text: where for text, where in places.items() if len(where) > 1} == {}


# Words only the log or a terminal shows (the rule is for the screen): the command-line tools,
# start-up and log files, and the reasons an internal refusal gives the log.
_TERMINAL_ONLY = {
    "__main__.py",
    "forwarded.py",
    "jobs.py",
    "logs.py",
    "main.py",
    "migrate.py",
    "page_fetch.py",
    "private_files.py",
    "reset_admin.py",
    "secret_box.py",
    "setup_code.py",
}
_LOG_CALLS = {"debug", "info", "warning", "error", "exception", "critical"}
_INTERNAL = {"RuntimeError", "SystemExit", "OutboundBlocked", "WrongContentType"}
_STRAIGHT = re.compile(r"[A-Za-z]'[A-Za-z]|[A-Za-z]s' ")


def test_sentences_shown_have_curly_apostrophes() -> None:
    """words.md rule 6 (0.9.5-beta.3, D2, BE8): every sentence a person reads in the app uses
    curly apostrophes (’). Docstrings, the API page's field descriptions, log lines and the
    words of internal errors are left out: only the screen is checked."""
    found = []
    for path in sorted(SOURCE.rglob("*.py")):
        if "migrations" in path.parts or path.name in _TERMINAL_ONLY:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"))
        quiet = _docstrings(tree)
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for key, value in zip(node.keys, node.values, strict=True):
                    if isinstance(key, ast.Constant) and key.value == "description":
                        quiet |= {id(inner) for inner in ast.walk(value)}
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.attr if isinstance(func, ast.Attribute) else getattr(func, "id", "")
            if name in _LOG_CALLS or name in _INTERNAL:
                quiet |= {id(inner) for inner in ast.walk(node)}
            for keyword in node.keywords:
                if keyword.arg in {"description", "summary", "title"}:
                    quiet |= {id(inner) for inner in ast.walk(keyword.value)}
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Constant)
                and isinstance(node.value, str)
                and id(node) not in quiet
                and " " in node.value
                and _STRAIGHT.search(node.value)
            ):
                found.append(f"{path.relative_to(SOURCE)}:{node.lineno}: {node.value!r}")
    assert found == []
