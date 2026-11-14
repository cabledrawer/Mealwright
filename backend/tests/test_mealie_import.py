"""Import from Mealie (0.9.5; cabledrawer 13 Nov): the preview, the server's job, the one Undo, Save
all as they are, and the API. Every file is made up here (made-up recipes and people, Sam and
Lorna); nothing goes online.
"""

import json
import zipfile
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_mealie_file import jpeg

from mealwright import drafts, mealie_import
from mealwright.models import (
    Food,
    ImportDraft,
    MealieImport,
    Recipe,
    RecipeLine,
    RecipePhoto,
    utcnow,
)

API = "/api/v1"
DAL = "1b4e28ba2fa111d2883f0016d3cca427"
SOUP = "2c5f39cb3fb211d2883f0016d3cca428"
CURRY = "3d6f39cb3fb211d2883f0016d3cca429"
LENTILS = "9a0e7c1a000040008000000000000002"
STOCK = "9a0e7c1a000040008000000000000003"
GRAM = "7b1d6e2f000040008000000000000003"
TAG = "5d6c4b3a000040008000000000000004"


def recipe(key: str, name: str, url: str | None = None) -> dict[str, Any]:
    return {"id": key, "slug": key, "name": name, "recipe_yield": "4", "org_url": url}


def line(key: str, at: int, text: str, food: str | None = None, qty: float = 0) -> dict[str, Any]:
    return {
        "recipe_id": key,
        "position": at,
        "quantity": qty,
        "unit_id": GRAM if food and qty else None,
        "food_id": food,
        "note": "" if food else text,
        "original_text": None if food else text,
    }


def database() -> dict[str, Any]:
    """Three recipes: the dal's every line names a Mealie food (read), the soup has a line
    nobody could read, the curry is the dal's source again under its own name."""
    return {
        "recipes": [
            recipe(DAL, "Red lentil dal", "https://kitchen.example/dal"),
            recipe(SOUP, "Lorna's soup"),
            recipe(CURRY, "Sam's curry", "https://kitchen.example/curry"),
        ],
        "recipes_ingredients": [
            line(DAL, 0, "", LENTILS, 200),
            line(DAL, 1, "", STOCK, 500),
            line(SOUP, 0, "", STOCK, 1000),
            line(SOUP, 1, "a handful of whatever is in the garden"),
            line(CURRY, 0, "", LENTILS, 100),
        ],
        "recipe_instructions": [
            {"recipe_id": DAL, "position": 0, "title": "", "text": "Simmer the lentils."},
            {"recipe_id": SOUP, "position": 0, "title": "", "text": "Cook it all."},
            {"recipe_id": CURRY, "position": 0, "title": "", "text": "Fry, then simmer."},
        ],
        "ingredient_foods": [
            {"id": LENTILS, "name": "Red lentils"},
            {"id": STOCK, "name": "Vegetable stock"},
        ],
        "ingredient_units": [
            {"id": GRAM, "name": "gram", "abbreviation": "g", "use_abbreviation": True}
        ],
        "tags": [{"id": TAG, "name": "Weeknight"}],
        "recipes_to_tags": [{"recipe_id": DAL, "tag_id": TAG}],
        "group_meal_plans": [{}, {}],
        "shopping_lists": [{}],
        "users": [{"username": "sam"}],
        "cookbooks": [],
    }


def zipped(path: Path, data: dict[str, Any] | None = None, photo: bool = True) -> bytes:
    with zipfile.ZipFile(path, "w") as out:
        out.writestr("database.json", json.dumps(data or database()))
        if photo:
            out.writestr(f"data/recipes/{DAL}/images/original.webp", jpeg())
    return path.read_bytes()


def upload(client: TestClient, raw: bytes, name: str = "mealie_backup.zip") -> Any:
    return client.post(
        f"{API}/mealie-imports",
        params={"file_name": name},
        content=raw,
        headers={"Content-Type": "application/zip"},
    )


def bring_in(client: TestClient, raw: bytes, **choices: Any) -> dict[str, Any]:
    made = upload(client, raw)
    assert made.status_code == 201, made.text
    started = client.post(f"{API}/mealie-imports/{made.json()['id']}/start", json=choices)
    assert started.status_code == 202, started.text
    client.app.state.mealie.wait()  # type: ignore[attr-defined]
    done = client.get(f"{API}/mealie-imports/{made.json()['id']}")
    assert done.status_code == 200
    return done.json()  # type: ignore[no-any-return]


@pytest.fixture
def raw(tmp_path: Path) -> bytes:
    return zipped(tmp_path / "backup.zip")


def mealie_files(client: TestClient) -> list[Path]:
    home = client.app.state.settings.data_dir / "mealie"  # type: ignore[attr-defined]
    return sorted(p for p in home.rglob("*") if p.is_file()) if home.is_dir() else []


# --- The preview ------------------------------------------------------------------------------


def test_the_preview_says_what_is_in_the_file_and_adds_nothing(
    kitchen: TestClient, raw: bytes
) -> None:
    answer = upload(kitchen, raw)
    assert answer.status_code == 201, answer.text
    body = answer.json()
    assert body["state"] == "ready"
    assert body["file_name"] == "mealie_backup.zip"
    preview = body["preview"]
    assert [r["name"] for r in preview["recipes"]] == [
        "Red lentil dal",
        "Lorna's soup",
        "Sam's curry",
    ]
    assert preview["recipes"][0]["tags"] == ["Weeknight"]
    assert preview["recipes"][0]["photo"] is True
    assert preview["new"] == 3 and preview["already"] == 0
    assert preview["with_photo"] == 1 and preview["photo_bytes"] > 0
    assert preview["foods_new"] == 2 and preview["foods_matching"] == 0
    assert preview["left_out"] == {"meal_plans": 2, "shopping_lists": 1, "users": 1, "cookbooks": 0}
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalars(select(Recipe)).all() == []
        assert db.scalars(select(Food).where(Food.name == "Red lentils")).all() == []
    assert len(mealie_files(kitchen)) == 1  # kept for "Bring in"


def test_the_preview_finds_recipes_already_here(kitchen: TestClient, raw: bytes) -> None:
    bring_in(kitchen, raw)
    again = upload(kitchen, raw).json()["preview"]
    assert again["new"] == 0 and again["already"] == 3
    assert all(r["already"] for r in again["recipes"])
    assert again["foods_matching"] == 2 and again["foods_new"] == 0


def test_a_file_that_is_not_mealies_is_refused_and_deleted(
    kitchen: TestClient, tmp_path: Path
) -> None:
    answer = upload(kitchen, b"not a zip at all")
    assert answer.status_code == 422
    assert answer.json()["code"] == "mealie_not_zip"
    assert upload(kitchen, b"").json()["code"] == "mealie_no_file"
    assert mealie_files(kitchen) == []


def test_sending_another_file_lets_the_earlier_one_go(kitchen: TestClient, raw: bytes) -> None:
    first = upload(kitchen, raw).json()["id"]
    upload(kitchen, raw)
    assert len(mealie_files(kitchen)) == 1
    assert kitchen.get(f"{API}/mealie-imports/{first}").status_code == 404


def test_cancel_deletes_the_file(kitchen: TestClient, raw: bytes) -> None:
    made = upload(kitchen, raw).json()["id"]
    assert kitchen.delete(f"{API}/mealie-imports/{made}").status_code == 204
    assert mealie_files(kitchen) == []
    assert kitchen.get(f"{API}/mealie-imports/current").json() == {"current": None}


def test_the_file_limit_is_1_gb(kitchen: TestClient) -> None:
    answer = kitchen.post(
        f"{API}/mealie-imports",
        content=b"x",
        headers={"Content-Type": "application/zip", "Content-Length": str(1024**3 + 1)},
    )
    assert answer.status_code == 413
    assert answer.json()["code"] == "mealie_too_big"


# --- Bringing in --------------------------------------------------------------------------------


def test_read_recipes_are_saved_and_unread_ones_wait_in_drafts(
    kitchen: TestClient, raw: bytes
) -> None:
    done = bring_in(kitchen, raw)
    assert done["state"] == "done"
    assert done["total"] == 3 and done["done"] == 3
    states = {r["name"]: r["state"] for r in done["recent"]}
    assert states == {"Red lentil dal": "saved", "Lorna's soup": "draft", "Sam's curry": "saved"}
    assert done["counts"]["saved"] == 2 and done["counts"]["drafts"] == 1
    assert done["counts"]["new_foods"] == 2
    (soup,) = done["to_check"]
    assert soup["unread"] == ["a handful of whatever is in the garden"]
    assert soup["unread_count"] == 1
    assert done["undo_until"] is not None
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        dal = db.scalar(select(Recipe).where(Recipe.name == "Red lentil dal"))
        assert dal is not None
        assert dal.source_url == "https://kitchen.example/dal"
        assert db.scalar(select(RecipePhoto).where(RecipePhoto.recipe_id == dal.id)) is not None
        lentils = db.scalar(select(Food).where(Food.name == "Red lentils"))
        assert lentils is not None and lentils.mealie_import_id == done["id"]
        draft = db.scalar(select(ImportDraft))
        assert draft is not None
        assert draft.source_kind == "mealie" and draft.mealie_import_id == done["id"]
    # The file is gone once it's done.
    assert mealie_files(kitchen) == []
    # The Drafts list says where it came from, and the 50-draft count leaves it out.
    listed = kitchen.get(f"{API}/recipes/drafts").json()
    assert [d["source"]["kind"] for d in listed["drafts"]] == ["mealie"]
    assert listed["drafts"][0]["waiting"] == ["a handful of whatever is in the garden"]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert drafts.count(db, 1) == 0


def test_photos_can_be_left_out_and_recipes_untocked(kitchen: TestClient, raw: bytes) -> None:
    done = bring_in(kitchen, raw, photos=False, leave_out=[CURRY])
    assert done["total"] == 2
    assert {r["name"] for r in done["recent"]} == {"Red lentil dal", "Lorna's soup"}
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalars(select(RecipePhoto)).all() == []
        assert db.scalar(select(Recipe).where(Recipe.name == "Sam's curry")) is None


def test_a_second_import_is_refused_while_one_runs(kitchen: TestClient, raw: bytes) -> None:
    made = upload(kitchen, raw).json()["id"]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        row = db.get(MealieImport, made)
        assert row is not None
        row.state = "running"
        db.commit()
    answer = upload(kitchen, raw)
    assert answer.status_code == 409
    assert answer.json()["code"] == "mealie_busy"
    assert len(mealie_files(kitchen)) == 1  # the refused upload isn't kept


def test_start_twice_is_refused(kitchen: TestClient, raw: bytes) -> None:
    done = bring_in(kitchen, raw)
    again = kitchen.post(f"{API}/mealie-imports/{done['id']}/start", json={})
    assert again.status_code == 409


def test_another_household_cannot_see_or_touch_it(
    kitchen: TestClient, neighbour: TestClient, raw: bytes
) -> None:
    made = upload(kitchen, raw).json()["id"]
    assert neighbour.get(f"{API}/mealie-imports/{made}").status_code == 404
    assert neighbour.post(f"{API}/mealie-imports/{made}/start", json={}).status_code == 404
    assert neighbour.delete(f"{API}/mealie-imports/{made}").status_code == 404
    assert neighbour.post(f"{API}/mealie-imports/{made}/undo").status_code == 404
    assert neighbour.get(f"{API}/mealie-imports/current").json() == {"current": None}
    # Next door may run its own at the same time.
    assert upload(neighbour, raw).status_code == 201


def test_signed_out_uploads_are_refused_before_reading(client: TestClient, raw: bytes) -> None:
    assert upload(client, raw).status_code == 401
    assert mealie_files(client) == []


def test_today_shows_a_note_for_a_day(kitchen: TestClient, raw: bytes) -> None:
    assert kitchen.get(f"{API}/today").json()["mealie"] is None
    done = bring_in(kitchen, raw)
    note = kitchen.get(f"{API}/today").json()["mealie"]
    assert note == {"id": done["id"], "state": "done", "recipes": 3, "to_check": 1}
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        row = db.get(MealieImport, done["id"])
        assert row is not None
        row.finished_at = utcnow() - timedelta(hours=25)
        db.commit()
    assert kitchen.get(f"{API}/today").json()["mealie"] is None


def test_a_broken_job_ends_failed_and_deletes_the_file(
    kitchen: TestClient, raw: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_: object) -> None:
        raise RuntimeError("made-up failure")

    monkeypatch.setattr(mealie_import, "_carry_on", broken)
    done = bring_in(kitchen, raw)
    assert done["state"] == "failed"
    assert mealie_files(kitchen) == []


# --- Undo ---------------------------------------------------------------------------------------


def test_undo_takes_the_whole_import_out(kitchen: TestClient, raw: bytes) -> None:
    done = bring_in(kitchen, raw)
    answer = kitchen.post(f"{API}/mealie-imports/{done['id']}/undo")
    assert answer.status_code == 200, answer.text
    assert answer.json() == {"recipes": 2, "kept": 0, "foods": 2, "drafts": 1}
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalars(select(Recipe).where(Recipe.removed_at.is_(None))).all() == []
        assert db.scalars(select(ImportDraft)).all() == []
        assert (
            db.scalar(select(Food).where(Food.name == "Red lentils", Food.removed_at.is_(None)))
            is None
        )
    assert kitchen.get(f"{API}/mealie-imports/{done['id']}").json()["state"] == "undone"
    assert kitchen.post(f"{API}/mealie-imports/{done['id']}/undo").status_code == 409


def test_undo_keeps_recipes_changed_since_and_their_ingredients(
    kitchen: TestClient, raw: bytes
) -> None:
    done = bring_in(kitchen, raw)
    dal_id = next(r["recipe_id"] for r in done["recent"] if r["name"] == "Red lentil dal")
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        dal = db.get(Recipe, dal_id)
        assert dal is not None
        dal.version += 1  # changed since (as any save does)
        db.commit()
    answer = kitchen.post(f"{API}/mealie-imports/{done['id']}/undo").json()
    assert answer["recipes"] == 1 and answer["kept"] == 1
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        kept = db.get(Recipe, dal_id)
        assert kept is not None and kept.removed_at is None
        # The dal still uses both new ingredients, so they stay.
        assert answer["foods"] == 0


def test_undo_stops_after_7_days(kitchen: TestClient, raw: bytes) -> None:
    done = bring_in(kitchen, raw)
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        row = db.get(MealieImport, done["id"])
        assert row is not None
        row.finished_at = utcnow() - timedelta(days=7, minutes=1)
        db.commit()
    answer = kitchen.post(f"{API}/mealie-imports/{done['id']}/undo")
    assert answer.status_code == 410
    assert answer.json()["code"] == "too_old"


# --- Save all as they are -----------------------------------------------------------------------


def test_save_all_keeps_unread_lines_as_plain_text(kitchen: TestClient, raw: bytes) -> None:
    done = bring_in(kitchen, raw)
    answer = kitchen.post(f"{API}/mealie-imports/drafts/save-all")
    assert answer.status_code == 200, answer.text
    assert answer.json() == {"saved": 1}
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalars(select(ImportDraft)).all() == []
        soup = db.scalar(select(Recipe).where(Recipe.name == "Lorna's soup"))
        assert soup is not None
        lines = {
            ln.words: ln.food_id
            for ln in db.scalars(select(RecipeLine).where(RecipeLine.recipe_id == soup.id))
        }
        assert lines["a handful of whatever is in the garden"] is None
        assert all(food is not None for words, food in lines.items() if "garden" not in words)
    after = kitchen.get(f"{API}/mealie-imports/{done['id']}").json()
    assert after["counts"]["drafts"] == 0 and after["counts"]["saved"] == 3
    # Saved this way, they join the import's Undo.
    undone = kitchen.post(f"{API}/mealie-imports/{done['id']}/undo").json()
    assert undone["recipes"] == 3


def test_tidy_lets_an_unused_file_go_after_a_day(kitchen: TestClient, raw: bytes) -> None:
    made = upload(kitchen, raw).json()["id"]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert mealie_import.tidy(db) == 0
        assert mealie_import.tidy(db, utcnow() + timedelta(hours=25)) == 1
        row = db.get(MealieImport, made)
        assert row is not None and row.state == "gone"
    assert mealie_files(kitchen) == []
