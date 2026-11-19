"""Final (belongs to #260), round 2 L3: the answers and the change are committed first and the
completed drafts are saved after, in short stretches. A server stopped between the two left
drafts whose every line was answered still in Drafts. The next answer (or a retry of the same
one) now finishes them, once, and Undo still works. Made-up recipes."""

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_mealie_answers import (
    GALANGAL,
    SOY,
    A,
    B,
    C,
    answer,
    db,
    draft_names,
    file,
    make_food,
)
from test_mealie_import import API, bring_in, zipped

from mealwright import mealie_answers
from mealwright.models import Change, Recipe


class Stopped(Exception):
    """The server stopping between saving the answers and moving the drafts."""


@pytest.fixture
def stopped_once(monkeypatch: pytest.MonkeyPatch) -> None:
    real = mealie_answers.finish
    calls: list[int] = []

    def finish(kitchen: Any, done: Any) -> Any:
        calls.append(1)
        if len(calls) == 1:
            raise Stopped
        return real(kitchen, done)

    monkeypatch.setattr(mealie_answers, "finish", finish)


@pytest.fixture
def stuck(kitchen: TestClient, tmp_path: Path) -> tuple[TestClient, int]:
    """A and B hold only soya sauce, C holds soya sauce and galangal. Soya sauce is answered
    and the server stops before A and B are moved."""
    raw = zipped(
        tmp_path / "f.zip",
        file({A: [SOY], B: ["1 tsp soya sauce"], C: [SOY, GALANGAL]}),
        photo=False,
    )
    assert bring_in(kitchen, raw)["counts"]["drafts"] == 3
    return kitchen, make_food(kitchen, "Soy sauce")


def _recipes(client: TestClient) -> int:
    with db(client) as session:
        return int(session.scalar(select(func.count()).select_from(Recipe)) or 0)


def _stop_after_answering(client: TestClient, soy: int, **headers: str) -> None:
    with pytest.raises(Stopped):
        client.post(
            f"{API}/recipes/drafts/by-ingredient/answer",
            json={"key": "soya sauce", "kind": "ingredient", "food_id": soy},
            headers=headers,
        )
    assert draft_names(client) == ["Dish a", "Dish b", "Dish c"]  # the answers are in, not moved
    assert _recipes(client) == 0


@pytest.mark.usefixtures("stopped_once")
def test_the_next_answer_finishes_the_drafts_a_stop_left_behind(stuck: Any) -> None:
    kitchen, soy = stuck
    _stop_after_answering(kitchen, soy)
    done = answer(kitchen, "galangal", "text")
    assert done.status_code == 200, done.text
    assert draft_names(kitchen) == []  # A and B moved by the finish, C by this answer
    assert _recipes(kitchen) == 3  # none made twice
    # Undo of each answer works: the first brings back A and B, the second C.
    with db(kitchen) as session:
        answered = session.scalars(
            select(Change).where(Change.kind == "mealie_drafts_answered").order_by(Change.id)
        ).all()
    assert [len(c.undo_data["saved"]) for c in answered] == [2, 1]
    assert kitchen.post(f"{API}/changes/{answered[1].id}/undo").status_code == 200
    assert draft_names(kitchen) == ["Dish c"]
    assert kitchen.post(f"{API}/changes/{answered[0].id}/undo").status_code == 200
    assert draft_names(kitchen) == ["Dish a", "Dish b", "Dish c"]
    assert all(r.removed_at is not None for r in _all_recipes(kitchen))  # the recipes went back


def _all_recipes(client: TestClient) -> list[Recipe]:
    with db(client) as session:
        return list(session.scalars(select(Recipe)))


@pytest.mark.usefixtures("stopped_once")
def test_a_retry_of_the_same_answer_finishes_them_and_says_so(stuck: Any) -> None:
    kitchen, soy = stuck
    _stop_after_answering(kitchen, soy, **{"Idempotency-Key": "k-1"})
    again = kitchen.post(
        f"{API}/recipes/drafts/by-ingredient/answer",
        json={"key": "soya sauce", "kind": "ingredient", "food_id": soy},
        headers={"Idempotency-Key": "k-1"},
    )
    assert again.status_code == 200, again.text
    assert again.headers.get("Idempotent-Replayed") == "true"
    assert again.json()["moved"] == 2
    assert draft_names(kitchen) == ["Dish c"]
    assert _recipes(kitchen) == 2


@pytest.mark.usefixtures("stopped_once")
def test_finishing_twice_moves_nothing_twice(stuck: Any) -> None:
    kitchen, soy = stuck
    _stop_after_answering(kitchen, soy)
    assert answer(kitchen, "galangal", "text").status_code == 200
    assert _recipes(kitchen) == 3
    assert answer(kitchen, "nothing like it", "text").status_code == 404  # another answer
    assert _recipes(kitchen) == 3
    assert draft_names(kitchen) == []


def test_a_draft_the_person_has_answered_less_than_fully_is_left_alone(
    kitchen: TestClient, tmp_path: Path
) -> None:
    raw = zipped(tmp_path / "f.zip", file({A: [SOY, GALANGAL]}), photo=False)
    assert bring_in(kitchen, raw)["counts"]["drafts"] == 1
    soy = make_food(kitchen, "Soy sauce")
    assert answer(kitchen, "soya sauce", "ingredient", food_id=soy).json()["moved"] == 0
    assert answer(kitchen, "nothing like it", "text").status_code == 404
    assert draft_names(kitchen) == ["Dish a"]  # galangal is still unanswered
    assert _recipes(kitchen) == 0


@pytest.mark.usefixtures("stopped_once")
def test_a_draft_the_stopped_answer_did_not_complete_is_not_saved_later(stuck: Any) -> None:
    """C lacks galangal. The person answers it on the review screen and keeps the draft without
    pressing Save; the next answer, from anyone, must not save it under the old answer."""
    kitchen, soy = stuck
    _stop_after_answering(kitchen, soy)
    listed = kitchen.get(f"{API}/recipes/drafts").json()["drafts"]
    c = next(d["id"] for d in listed if d["name"] == "Dish c")
    opened = kitchen.get(f"{API}/recipes/drafts/{c}").json()
    choices = opened["choices"]
    choices["lines"]["1"] = {"kind": "here"}  # galangal, by hand
    body = {"text": opened["text"], "review": opened["review"], "choices": choices}
    assert kitchen.put(f"{API}/recipes/drafts/{c}", json=body).status_code == 200
    assert answer(kitchen, "nothing like it", "text").status_code == 404
    assert draft_names(kitchen) == ["Dish c"]  # A and B finished; C is the person's to save
    assert _recipes(kitchen) == 2


@pytest.mark.usefixtures("stopped_once")
def test_drafts_that_cannot_be_saved_are_looked_at_once_not_on_every_answer(
    stuck: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    kitchen, soy = stuck
    _stop_after_answering(kitchen, soy)
    looked: list[int] = []

    def cannot(kitchen_: Any, draft_id: int, *rest: Any) -> None:
        looked.append(draft_id)

    monkeypatch.setattr(mealie_answers, "_save_one", cannot)
    for _ in range(3):
        assert answer(kitchen, "nothing like it", "text").status_code == 404
    assert len(looked) == 2  # A and B, the first time only
    assert draft_names(kitchen) == ["Dish a", "Dish b", "Dish c"]
    with db(kitchen) as session:
        first = session.scalars(select(Change).where(Change.kind == "mealie_drafts_answered")).one()
        assert first.undo_data["completed"] == []
