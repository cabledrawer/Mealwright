"""B7 review fixes (R3, R4, R9): "Save all" keeps what another writer added to an import's
results; a Mealie undo leaves an ingredient that was merged; photo files wait for the outermost
commit."""

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_mealie_import import API, bring_in, many, zipped

from mealwright import mealie_import
from mealwright.history import purge_removed
from mealwright.models import Food, Household, MealieImport, Recipe, utcnow


def test_save_all_keeps_results_another_writer_added_between_stretches(
    kitchen: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """R3: each stretch reads the import afresh, so an entry added in a pause survives and the
    import's Undo takes that recipe out too."""
    blob = zipped(tmp_path / "many.zip", many(foods=6, recipes=6, unread=True), photo=False)
    job = bring_in(kitchen, blob)
    assert job["counts"]["drafts"] == 6
    extra = kitchen.post(f"{API}/recipes", json={"name": "Added in a pause", "lines": []})
    assert extra.status_code == 201, extra.text
    extra_id, extra_version = extra.json()["id"], extra.json()["version"]
    monkeypatch.setattr(mealie_import, "HOLD_SECONDS", 0, raising=False)
    pauses: list[int] = []

    def other_writer() -> None:
        pauses.append(1)
        if len(pauses) == 1:  # another request adds its entry while the lock is let go
            with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
                row = db.get(MealieImport, job["id"])
                assert row is not None
                row.results = [
                    *row.results,
                    {"recipe_id": extra_id, "version": extra_version, "name": "Added"},
                ]
                db.commit()

    monkeypatch.setattr(mealie_import, "_pause", other_writer)
    # SQLite's lock throws away what the session had read; Postgres's does not, so test without
    monkeypatch.setattr("mealwright.shopping.lock_household", lambda kitchen: kitchen.db.flush())
    assert kitchen.post(f"{API}/mealie-imports/drafts/save-all").json() == {"saved": 6}
    assert len(pauses) >= 2
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        row = db.get(MealieImport, job["id"])
        assert row is not None
        assert extra_id in {e.get("recipe_id") for e in row.results}
    undone = kitchen.post(f"{API}/mealie-imports/{job['id']}/undo").json()
    assert undone["recipes"] == 7
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalars(select(Recipe).where(Recipe.removed_at.is_(None))).all() == []


def _foods_by_name(kitchen: TestClient) -> dict[str, Food]:
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        return {f.name: f for f in db.scalars(select(Food))}


def _purge_a_week_on(kitchen: TestClient) -> None:
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        purge_removed(db, db.get(Household, 1), utcnow() + timedelta(days=8))  # type: ignore[arg-type]


def test_undo_leaves_a_mealie_ingredient_an_existing_one_was_merged_into(
    kitchen: TestClient, tmp_path: Path
) -> None:
    """R4: merge an existing ingredient into one the import made, then Undo the import and let
    a week pass: both ingredients are still there."""
    old = kitchen.post(f"{API}/foods", json={"name": "Masoor"})
    assert old.status_code == 201, old.text
    done = bring_in(kitchen, zipped(tmp_path / "b.zip"))
    mealie = _foods_by_name(kitchen)["Red lentils"]
    assert mealie.mealie_import_id == done["id"]
    merged = kitchen.post(f"{API}/foods/{old.json()['food']['id']}/merge", json={"into_id": mealie.id})
    assert merged.status_code == 200, merged.text
    assert kitchen.post(f"{API}/mealie-imports/{done['id']}/undo").status_code == 200
    _purge_a_week_on(kitchen)
    foods = _foods_by_name(kitchen)
    assert "Red lentils" in foods and foods["Red lentils"].removed_at is None
    assert "Masoor" in foods and foods["Masoor"].merged_into_id == foods["Red lentils"].id


def test_undo_leaves_a_mealie_ingredient_that_was_merged_into_an_existing_one(
    kitchen: TestClient, tmp_path: Path
) -> None:
    """R4, the other way round: the import's ingredient was merged away into an old one."""
    old = kitchen.post(f"{API}/foods", json={"name": "Masoor"})
    assert old.status_code == 201, old.text
    done = bring_in(kitchen, zipped(tmp_path / "b.zip"))
    mealie = _foods_by_name(kitchen)["Red lentils"]
    merged = kitchen.post(f"{API}/foods/{mealie.id}/merge", json={"into_id": old.json()["food"]["id"]})
    assert merged.status_code == 200, merged.text
    assert kitchen.post(f"{API}/mealie-imports/{done['id']}/undo").status_code == 200
    _purge_a_week_on(kitchen)
    foods = _foods_by_name(kitchen)
    assert "Masoor" in foods and foods["Masoor"].removed_at is None
    assert foods["Red lentils"].merged_into_id == foods["Masoor"].id
