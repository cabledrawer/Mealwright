"""Fix round 2 of B6a: the import's own page reads an import whose drafts were answered into
Recipes; two Undos of one answer at once record one Undo, and a retry gets the first's result.
Made-up recipes."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_mealie_answers import answer, db, draft_names
from test_mealie_answers_fix1 import _many_drafts, bring, make_food
from test_mealie_import import API

from mealwright.models import Change

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


def _undos(kitchen: TestClient) -> int:
    with db(kitchen) as session:
        return int(session.scalar(select(func.count()).where(Change.kind == "undo")) or 0)


@pytest.mark.parametrize("same_key", [True, False])
def test_two_undos_of_one_answer_at_once_record_one(
    kitchen: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, same_key: bool
) -> None:
    soy = _many_drafts(kitchen, tmp_path, 4)
    done = answer(kitchen, "soya sauce", "ingredient", food_id=soy).json()
    path = f"{API}/changes/{done['change']['id']}/undo"
    inner: list[Any] = []

    def second_undo_between_stretches() -> None:
        if not inner:  # the second request runs while the first has let the lock go
            key = "u-1" if same_key else "u-2"
            inner.append(kitchen.post(path, headers={"Idempotency-Key": key}))

    monkeypatch.setattr("mealwright.mealie_import.HOLD_SECONDS", 0.0)
    monkeypatch.setattr("mealwright.mealie_answers.UNDO_BATCH", 1)
    monkeypatch.setattr("mealwright.mealie_import._pause", second_undo_between_stretches)
    first = kitchen.post(path, headers={"Idempotency-Key": "u-1"})
    assert inner and inner[0].status_code == 200, inner[0].text
    assert "4 recipes are back in Drafts." in str(inner[0].json())
    if same_key:
        assert first.status_code == 200, first.text  # the retry gets the first result
        assert first.headers.get("Idempotent-Replayed") == "true"
        assert first.json()["change"]["id"] == inner[0].json()["change"]["id"]
        assert first.json()["message"] == inner[0].json()["message"]
    else:
        assert first.status_code == 409 and first.json()["code"] == "already_undone", first.text
    assert _undos(kitchen) == 1
    assert len(draft_names(kitchen)) == 4  # each recipe came back once
