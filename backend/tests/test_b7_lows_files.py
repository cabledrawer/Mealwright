"""B7 lows, files / Mealie / history data: a Mealie upload checks the admin role after the body
is in; a file goes only after the change that lets it go is committed; Undo reads the import's
recipes afresh; and the small fixes listed with each test."""

from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import person
from test_mealie_import import API, bring_in, many, mealie_files, upload, zipped

from mealwright import mealie_import
from mealwright.mealie_file import read_now
from mealwright.api.v1 import mealie as mealie_api
from mealwright.models import MealieImport, Recipe, utcnow


def test_an_upload_checks_the_admin_role_again_after_the_body_is_in(
    kitchen: TestClient, tmp_path: Path
) -> None:
    """The first check is before the body is read; a role changed meanwhile is caught after, and
    the temporary file is still removed."""
    noor = person(kitchen, name="Noor", username="noor")
    # Stand in for "was an admin when the upload began": the first check lets her through.
    noor.app.dependency_overrides[mealie_api._signed_in] = lambda: 1  # type: ignore[attr-defined]
    try:
        sent = upload(noor, zipped(tmp_path / "b.zip"))
    finally:
        noor.app.dependency_overrides.clear()  # type: ignore[attr-defined]
    assert sent.status_code == 403 and sent.json()["code"] == "admins_only"
    assert mealie_files(kitchen) == []
    assert kitchen.get(f"{API}/mealie-imports/current").json() == {"current": None}


def test_an_earlier_file_stays_when_the_change_that_lets_it_go_fails(
    kitchen: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = zipped(tmp_path / "b.zip")
    first = upload(kitchen, raw).json()["id"]
    before = mealie_files(kitchen)
    assert len(before) == 1

    def broken(*args: Any, **kwargs: Any) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(mealie_import.shutil, "move", broken)
    with pytest.raises(OSError):
        kitchen.post(f"{API}/mealie-imports", content=raw)
    assert mealie_files(kitchen) == before  # not unlinked ahead of its commit
    assert kitchen.get(f"{API}/mealie-imports/{first}").json()["state"] == "ready"


def test_tidy_leaves_an_import_that_started_after_it_looked(
    kitchen: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = upload(kitchen, zipped(tmp_path / "b.zip")).json()["id"]
    import mealwright.shopping as shopping

    real = shopping.lock_db

    def started_first(db: Any, household: Any) -> None:
        with kitchen.app.state.sessionmaker() as other:  # type: ignore[attr-defined]
            row = other.get(MealieImport, made)
            assert row is not None
            row.state = "running"
            other.commit()
        real(db, household)

    monkeypatch.setattr(shopping, "lock_db", started_first)
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert mealie_import.tidy(db, utcnow() + timedelta(hours=25)) == 0
        row = db.get(MealieImport, made)
        assert row is not None and row.state == "running" and row.file_key is not None
    assert len(mealie_files(kitchen)) == 1


def test_undo_takes_a_recipe_added_to_the_import_while_it_ran(
    kitchen: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Undo builds its recipe list from the import as it is when it gets there, not as it was
    at the start: a recipe a "Save all" adds in a pause goes too."""
    blob = zipped(tmp_path / "many.zip", many(foods=2, recipes=2, unread=True), photo=False)
    job = bring_in(kitchen, blob)
    extra = kitchen.post(f"{API}/recipes", json={"name": "Added in a pause", "lines": []}).json()
    added: list[int] = []

    def other_writer() -> None:
        if added:
            return
        added.append(1)
        with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            row = db.get(MealieImport, job["id"])
            assert row is not None
            row.results = [
                *row.results,
                {"recipe_id": extra["id"], "version": extra["version"], "name": "Added"},
            ]
            db.commit()

    monkeypatch.setattr(mealie_import, "_pause", other_writer)
    undone = kitchen.post(f"{API}/mealie-imports/{job['id']}/undo").json()
    assert undone["recipes"] == 1
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalars(select(Recipe).where(Recipe.removed_at.is_(None))).all() == []


def test_trim_sweeps_half_written_copies_and_their_side_files(tmp_path: Path) -> None:
    from mealwright import backups

    folder = tmp_path / "backups"
    folder.mkdir()
    old = [
        "backup-20261101-030000.db.1.part",
        "backup-20261101-030000.db.1.part-wal",
        "backup-20261101-030000.db.1.part-shm",
        "backup-20261101-030000.db.1.part-journal",
        "before-delete-everything-20261101-030000.db.7.part",
    ]
    keep = ["notes.txt", "backup-20261101-040000.db.1.part.bak", "other.db.1.part"]
    for name in [*old, *keep]:
        (folder / name).write_bytes(b"x")
    backups.trim(folder, 7)
    assert sorted(p.name for p in folder.iterdir()) == sorted(keep)


def test_one_oversized_yield_quantity_does_not_make_the_file_unreadable(tmp_path: Path) -> None:
    from test_mealie_file import SOUP, make_zip, tables

    database = tables(
        recipes=[
            {
                "id": SOUP,
                "name": "Big batch",
                "recipe_yield": "loaves",
                "recipe_yield_quantity": 1e30,
            }
        ]
    )
    book = read_now(make_zip(tmp_path / "x.zip", database))
    assert [r.page.name for r in book.recipes] == ["Big batch"]
