"""F262 (hand test 20 Nov, 0.9.5-beta.3): Undo of an answer by ingredient while that answer's
completed drafts are still being moved to Recipes. The move takes drafts out of the change's
`partial` list between the Undo's stretches; the Undo went on by position and failed
(IndexError), and the drafts moved meanwhile stayed in Recipes. Now the Undo first marks the
change as being undone, the move stops at that mark, and the Undo finds each item by its draft.
No database change. Made-up recipes."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_mealie_answers import KASURI, answer, db, draft_names, file, make_food
from test_mealie_import import API, bring_in, zipped

from mealwright import mealie_answers
from mealwright.models import Change, Recipe

SOYS = {f"r{i:031d}": ["2 tbsp soya sauce"] for i in range(4)}
HERB = f"h{9:031d}"


def _recipes(client: TestClient) -> int:
    with db(client) as session:
        return int(
            session.scalar(
                select(func.count()).select_from(Recipe).where(Recipe.removed_at.is_(None))
            )
            or 0
        )


@pytest.fixture
def answered_not_moved(kitchen: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> int:
    """Four drafts hold only soya sauce, a fifth only kasuri methi. Soya sauce is answered; the
    four completed drafts are still to be moved (the move hasn't run yet). Returns the change."""
    bring_in(kitchen, zipped(tmp_path / "f.zip", file({**SOYS, HERB: [KASURI]}), photo=False))
    soy = make_food(kitchen, "Soy sauce")
    real = mealie_answers.finish
    calls: list[int] = []

    def later(kitchen: Any, done: Any) -> Any:
        calls.append(1)
        return done if len(calls) == 1 else real(kitchen, done)

    monkeypatch.setattr(mealie_answers, "finish", later)
    done = answer(kitchen, "soya sauce", "ingredient", food_id=soy)
    assert done.status_code == 200 and done.json()["moved"] == 0, done.text
    assert len(draft_names(kitchen)) == 5 and _recipes(kitchen) == 0
    return int(done.json()["change"]["id"])


def test_an_undo_while_the_answer_is_still_moving_drafts_takes_back_every_draft(
    kitchen: TestClient, answered_not_moved: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    inner: list[Any] = []

    def move_between_undo_stretches() -> None:
        # The answer's move runs while the Undo has let the lock go (here: the next answer,
        # which first finishes what the earlier one left).
        if not inner:
            inner.append(None)
            inner[0] = answer(kitchen, "kasuri methi", "text")

    monkeypatch.setattr("mealwright.mealie_import.HOLD_SECONDS", 0.0)
    monkeypatch.setattr("mealwright.mealie_answers.UNDO_BATCH", 1)
    monkeypatch.setattr("mealwright.mealie_import._pause", move_between_undo_stretches)
    undo = kitchen.post(
        f"{API}/changes/{answered_not_moved}/undo", headers={"Idempotency-Key": "u-1"}
    )
    assert undo.status_code == 200, undo.text
    assert inner and inner[0].status_code == 200, inner[0].text
    assert "“soya sauce” is unanswered again." in undo.json()["message"]
    # Every soya sauce draft is a draft again, unanswered; only the kasuri methi one moved.
    assert len(draft_names(kitchen)) == 4 and _recipes(kitchen) == 1
    soy_groups = kitchen.get(f"{API}/recipes/drafts/by-food").json()["groups"]
    soy = next(g for g in soy_groups if g["key"] == "soya sauce")
    assert soy["drafts"] == 4, soy
    with db(kitchen) as session:
        change = session.get(Change, answered_not_moved)
        assert change is not None and change.undone_by_change_id is not None
        assert not (change.undo_data or {}).get("saved")


def test_the_move_skips_a_change_marked_as_being_undone(
    kitchen: TestClient, answered_not_moved: int
) -> None:
    """An Undo stopped part-way (its mark is in, the change not yet undone): the next answer
    does not move the drafts the undone answer completed."""
    with db(kitchen) as session:
        change = session.get(Change, answered_not_moved)
        assert change is not None
        change.undo_data = {**(change.undo_data or {}), "undoing": True}
        session.commit()
    assert answer(kitchen, "kasuri methi", "text").status_code == 200
    assert len(draft_names(kitchen)) == 4 and _recipes(kitchen) == 1
    undo = kitchen.post(f"{API}/changes/{answered_not_moved}/undo")
    assert undo.status_code == 200, undo.text
    soy_groups = kitchen.get(f"{API}/recipes/drafts/by-food").json()["groups"]
    assert next(g for g in soy_groups if g["key"] == "soya sauce")["drafts"] == 4
