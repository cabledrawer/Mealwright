"""Fix round 1 of B6a (Mealie drafts fixed by ingredient): the rule for a line tied to an
ingredient is one rule for every way a draft becomes a recipe; Save all keeps the answers
already given; an answered ingredient is not removed while a draft's answer still points at it;
groups fold names as matching does; plural words; one change ID for a retry. Made-up recipes."""

from pathlib import Path
from typing import Any

import pytest
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

from mealwright.models import Change, Food, ImportDraft, MealieImport

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


# --- 3. An ingredient a draft's answer points at is in use ------------------------------------


def test_undo_keeps_an_ingredient_a_later_answer_in_a_draft_points_at(
    kitchen: TestClient, tmp_path: Path
) -> None:
    bring(
        kitchen,
        tmp_path,
        {
            A: ["2 tbsp soya sauce", "a pinch of kasuri methi"],
            B: ["1 tbsp soy sauce", "a cm of galangal"],
        },
    )
    first = answer(kitchen, "soya sauce", "new", name="Soy sauce").json()
    food_id = first["food"]["id"]
    later = answer(kitchen, "soy sauce", "ingredient", food_id=food_id)
    assert later.status_code == 200 and later.json()["moved"] == 0  # galangal still waits
    undone = kitchen.post(f"{API}/changes/{first['change']['id']}/undo")
    assert undone.status_code == 200, undone.text
    with db(kitchen) as session:
        assert session.get(Food, food_id).removed_at is None  # type: ignore[union-attr]
        draft = session.scalar(select(ImportDraft).where(ImportDraft.name == "Dish b"))
        assert draft is not None
        assert [c["food"]["id"] for c in draft.choices["lines"].values()] == [food_id]


def test_the_imports_undo_keeps_an_ingredient_a_draft_outside_it_points_at(
    kitchen: TestClient, tmp_path: Path
) -> None:
    bring(kitchen, tmp_path, {A: ["2 tbsp soya sauce", "a pinch of kasuri methi"]})
    made = answer(kitchen, "soya sauce", "new", name="Soy sauce").json()
    food_id = made["food"]["id"]
    with db(kitchen) as session:
        mine = session.scalars(select(ImportDraft)).one()
        session.add(
            ImportDraft(
                household_id=mine.household_id,
                source_kind="text",
                source_text="x",
                name="Mine",
                review={},
                choices={
                    "lines": {"0": {"kind": "ingredient", "food": {"id": food_id, "name": "S"}}}
                },
            )
        )
        import_id = mine.mealie_import_id
        session.commit()
    undone = kitchen.post(f"{API}/mealie-imports/{import_id}/undo")
    assert undone.status_code == 200, undone.text
    with db(kitchen) as session:
        assert session.get(Food, food_id).removed_at is None  # type: ignore[union-attr]


# --- 5. Groups are told apart the way matching tells names apart ------------------------------


def test_singular_plural_and_spelling_variants_are_one_group(
    kitchen: TestClient, tmp_path: Path
) -> None:
    bring(
        kitchen,
        tmp_path,
        {
            A: ["2 eggs", "1 chilli", "3 tomatoes"],
            B: ["1 egg", "2 chillies", "1 tomato"],
            C: ["Egg", "a chilli", "tomato (ripe)"],
        },
    )
    found = {g["key"]: (g["drafts"], g["lines"]) for g in groups(kitchen)["groups"]}
    assert len(found) == 3 and set(found.values()) == {(3, 3)}, found
    key = next(iter(found))
    assert answer(kitchen, key, "text").json()["drafts"] == 3  # the answer reaches all three


# --- 6. Words: singular and plural, no marker in a message ------------------------------------


def test_one_draft_and_one_recipe_are_said_in_the_singular(
    kitchen: TestClient, tmp_path: Path
) -> None:
    bring(kitchen, tmp_path, {A: ["2 tbsp soya sauce"]})
    done = answer(kitchen, "soya sauce", "new", name="Soy sauce").json()
    assert (
        done["change"]["summary"] == "Answered “soya sauce” in 1 draft · 1 recipe moved to Recipes"
    )
    undone = kitchen.post(f"{API}/changes/{done['change']['id']}/undo").json()
    assert "1 recipe is back in Drafts." in str(undone), undone
    assert "proposed" not in str(undone) and "cabledrawer" not in str(undone)


def test_undo_after_the_imports_own_undo_gives_a_true_reason(
    kitchen: TestClient, tmp_path: Path
) -> None:
    bring(kitchen, tmp_path, {A: ["2 tbsp soya sauce"], B: ["1 tsp soya sauce"]})
    done = answer(kitchen, "soya sauce", "new", name="Soy sauce").json()
    with db(kitchen) as session:
        import_id = session.scalars(select(MealieImport)).one().id
    assert kitchen.post(f"{API}/mealie-imports/{import_id}/undo").status_code == 200
    undone = kitchen.post(f"{API}/changes/{done['change']['id']}/undo")
    assert undone.status_code == 200, undone.text
    said = str(undone.json())
    assert "2 recipes were already out of Recipes" in said, said
    assert "changed, cooked or planned" not in said and "proposed" not in said


# --- 7. A save that fails is logged by the kind of error only ---------------------------------


def test_a_draft_that_cant_be_saved_stays_a_draft_and_the_log_names_only_the_error_kind(
    kitchen: TestClient,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    bring(kitchen, tmp_path, {A: ["2 tbsp soya sauce"]})
    soy = make_food(kitchen, "Soy sauce")

    def broken(*_: Any, **__: Any) -> None:
        raise ValueError("private words of the person")

    monkeypatch.setattr("mealwright.mealie_import._save", broken)
    with caplog.at_level("WARNING", logger="mealwright.mealie_answers"):
        done = answer(kitchen, "soya sauce", "ingredient", food_id=soy)
    assert done.status_code == 200 and done.json()["moved"] == 0
    assert draft_names(kitchen) == ["Dish a"]
    (record,) = [r for r in caplog.records if "couldn't be saved" in r.getMessage()]
    assert "ValueError" in record.getMessage()
    assert "private words" not in caplog.text


# --- 2. A long answer and its Undo let the lock go between short stretches --------------------


def _many_drafts(kitchen: TestClient, tmp_path: Path, n: int) -> int:
    bring(kitchen, tmp_path, {f"r{i:031d}": ["2 tbsp soya sauce"] for i in range(n)})
    return make_food(kitchen, "Soy sauce")


def _count_pauses(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    pauses: list[int] = []
    monkeypatch.setattr("mealwright.mealie_import.HOLD_SECONDS", 0.0)  # one draft per stretch
    monkeypatch.setattr("mealwright.mealie_import._pause", lambda: pauses.append(1))
    monkeypatch.setattr("mealwright.mealie_answers.UNDO_BATCH", 1)
    return pauses


def test_a_long_answer_and_its_undo_save_and_restore_in_short_stretches(
    kitchen: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    soy = _many_drafts(kitchen, tmp_path, 12)
    pauses = _count_pauses(monkeypatch)
    done = answer(kitchen, "soya sauce", "ingredient", food_id=soy)
    assert done.status_code == 200 and done.json()["moved"] == 12, done.text
    assert done.json()["change"]["summary"].endswith("in 12 drafts · 12 recipes moved to Recipes")
    assert len(pauses) == 11  # the lock was let go between the 12 stretches
    assert draft_names(kitchen) == []
    pauses.clear()
    undone = kitchen.post(f"{API}/changes/{done.json()['change']['id']}/undo")
    assert undone.status_code == 200, undone.text
    assert "12 recipes are back in Drafts." in str(undone.json())
    assert len(pauses) == 11
    assert len(draft_names(kitchen)) == 12
    assert groups(kitchen)["groups"][0]["drafts"] == 12  # unanswered again


def test_the_change_says_exactly_what_was_done_when_a_stretch_fails_part_way(
    kitchen: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    soy = _many_drafts(kitchen, tmp_path, 6)
    calls: list[int] = []

    def stops() -> None:
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("the disk went away")

    monkeypatch.setattr("mealwright.mealie_import.HOLD_SECONDS", 0.0)
    monkeypatch.setattr("mealwright.mealie_import._pause", stops)
    with pytest.raises(RuntimeError):
        answer(kitchen, "soya sauce", "ingredient", food_id=soy)
    with db(kitchen) as session:
        change = session.scalar(select(Change).where(Change.kind == "mealie_drafts_answered"))
        assert change is not None
        saved, partial = change.undo_data["saved"], change.undo_data["partial"]
        change_id = change.id
    assert len(saved) == 2 and len(partial) == 4  # two stretches were committed, no more
    assert len(draft_names(kitchen)) == 4
    monkeypatch.setattr("mealwright.mealie_import._pause", lambda: None)
    undone = kitchen.post(f"{API}/changes/{change_id}/undo")
    assert undone.status_code == 200, undone.text
    assert len(draft_names(kitchen)) == 6  # the two recipes are back, the four are unanswered
    assert groups(kitchen)["groups"][0]["drafts"] == 6


def test_an_undo_stopped_part_way_carries_on_when_asked_again(
    kitchen: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    soy = _many_drafts(kitchen, tmp_path, 6)
    done = answer(kitchen, "soya sauce", "ingredient", food_id=soy).json()
    calls: list[int] = []

    def stops() -> None:
        calls.append(1)
        if len(calls) == 2:
            raise RuntimeError("the disk went away")

    monkeypatch.setattr("mealwright.mealie_import.HOLD_SECONDS", 0.0)
    monkeypatch.setattr("mealwright.mealie_answers.UNDO_BATCH", 1)
    monkeypatch.setattr("mealwright.mealie_import._pause", stops)
    with pytest.raises(RuntimeError):
        kitchen.post(f"{API}/changes/{done['change']['id']}/undo")
    assert len(draft_names(kitchen)) == 2  # two came back; nothing was lost or doubled
    monkeypatch.setattr("mealwright.mealie_import._pause", lambda: None)
    again = kitchen.post(f"{API}/changes/{done['change']['id']}/undo")
    assert again.status_code == 200, again.text
    assert len(draft_names(kitchen)) == 6
    assert "6 recipes are back in Drafts." in str(again.json())


def test_the_change_record_keeps_only_what_undo_needs(kitchen: TestClient, tmp_path: Path) -> None:
    import json

    soy = _many_drafts(kitchen, tmp_path, 20)
    with db(kitchen) as session:
        review = session.scalars(select(ImportDraft).order_by(ImportDraft.id)).first().review  # type: ignore[union-attr]
    done = answer(kitchen, "soya sauce", "ingredient", food_id=soy).json()
    with db(kitchen) as session:
        change = session.get(Change, done["change"]["id"])
        assert change is not None
        per_draft = len(json.dumps(change.undo_data)) / 20
    assert per_draft < 1000, per_draft  # was about 1,600 bytes a draft
    undone = kitchen.post(f"{API}/changes/{done['change']['id']}/undo")
    assert undone.status_code == 200, undone.text
    with db(kitchen) as session:
        back = session.scalars(select(ImportDraft).order_by(ImportDraft.id)).first()
        assert back is not None
        assert back.review == {**review, "name": back.review["name"]}  # the review is whole
        assert back.choices.get("lines", {}) == {}  # as it was before the answer
