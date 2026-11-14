"""Import from Mealie (0.9.5; cabledrawer 13 Nov): the preview, the server's job, the one Undo, Save
all as they are, and the API. Every file is made up here (made-up recipes and people, Sam and
Lorna); nothing goes online.
"""

import contextlib
import json
import threading
import zipfile
from collections import Counter
from collections.abc import Iterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sync_kit import person
from test_mealie_file import jpeg
from test_plan import add_recipe, slot_ids

from mealwright import drafts, mealie_file, mealie_import
from mealwright.api.v1 import mealie as mealie_api
from mealwright.mealie_file import MealieFileProblem
from mealwright.models import (
    BatchCook,
    CookedRecord,
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
    assert body["file_bytes"] == len(raw)
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
    assert preview["foods_new_names"] == ["Red lentils", "Vegetable stock"]
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
    # Nothing is coming, so no ingredient is counted (round 1, review 1).
    assert again["foods_matching"] == 0 and again["foods_new"] == 0
    assert again["foods_new_names"] == []


def test_the_preview_names_the_new_ingredients_a_to_z_once_each_and_at_most_200(
    kitchen: TestClient, tmp_path: Path
) -> None:
    """The phone's "See" under New ingredients lists them: A to Z, a name written twice in
    Mealie once, and the first 200 of a long list (the count says how many in all)."""
    data = database()
    foods = [{"id": f"f{n:03d}", "name": f"Spice {n:03d}"} for n in range(205)]
    foods.append({"id": "twice", "name": "red lentils"})  # Red lentils again, in small letters
    data["ingredient_foods"] += foods
    for at in range(0, len(foods), 5):
        key = f"r{at:03d}"
        data["recipes"].append(recipe(key, f"Spice mix {at}"))
        data["recipes_ingredients"] += [
            line(key, n, "", food["id"], 10) for n, food in enumerate(foods[at : at + 5])
        ]
    preview = upload(kitchen, zipped(tmp_path / "many.zip", data)).json()["preview"]
    assert preview["foods_new"] == 207  # Red lentils, Vegetable stock and the 205 spices
    names = preview["foods_new_names"]
    assert len(names) == 200
    assert names[0] == "Red lentils" and names[1:3] == ["Spice 000", "Spice 001"]
    assert names[-1] == "Spice 198"  # Red lentils, then Spice 000 to 198
    assert len({name.casefold() for name in names}) == 200


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


def test_a_failed_tidy_logs_the_kind_of_failure_not_a_traceback(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    # Round 2, S5: a traceback could carry the stored file's path.
    from mealwright import jobs

    def broken(db: Any, now: Any = None) -> int:
        raise OSError("/data/mealie/secret-path/abc.zip")

    monkeypatch.setattr(mealie_import, "tidy", broken)
    with caplog.at_level("WARNING", logger="mealwright.jobs"):
        jobs.purge_removed_ingredients(kitchen.app.state.sessionmaker)  # type: ignore[attr-defined]
    (record,) = [r for r in caplog.records if "tidy Mealie" in r.getMessage()]
    assert record.exc_info is None and "OSError" in record.getMessage()
    assert "secret-path" not in caplog.text


def test_the_hourly_tidy_looks_at_mealie_files_once(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mealwright import jobs

    calls: list[datetime] = []
    monkeypatch.setattr(mealie_import, "tidy", lambda db, now=None: calls.append(now) or 0)
    jobs.purge_removed_ingredients(kitchen.app.state.sessionmaker)  # type: ignore[attr-defined]
    assert len(calls) == 1  # before round 1: twice (the block was pasted twice)


# --- Short stretches of the write lock (round 1: S-H1, S-M2, S-M3, S-L6) ------------------------


def many(foods: int, recipes: int, unread: bool = False) -> dict[str, Any]:
    """A made-up file: `foods` Mealie foods, used in turn by `recipes` recipes (each with one
    line nobody can read, if `unread`)."""
    food_keys = [f"f{i:031d}" for i in range(foods)]
    recipe_keys = [f"r{i:031d}" for i in range(recipes)]
    lines = [line(recipe_keys[i % recipes], i, "", key, 100) for i, key in enumerate(food_keys)]
    if unread:
        lines += [line(key, 10_000, "a pinch of Noor's secret") for key in recipe_keys]
    return {
        **database(),
        "recipes": [recipe(key, f"Sam's dish {i}") for i, key in enumerate(recipe_keys)],
        "recipes_ingredients": lines,
        "recipe_instructions": [],
        "ingredient_foods": [
            {"id": key, "name": f"Lorna's spice {i}"} for i, key in enumerate(food_keys)
        ],
        "recipes_to_tags": [],
    }


class Seen:
    """What the database was asked, by thread: write transactions ended (`stretches`),
    reads of the ingredient table, and which threads hold the write lock now."""

    def __init__(self) -> None:
        self.stretches: Counter[str] = Counter()
        self.food_reads: Counter[str] = Counter()
        self.writing: dict[int, str] = {}

    def holding(self, thread: str) -> bool:
        return thread in self.writing.values()


@contextlib.contextmanager
def seen(engine: Engine) -> Iterator[Seen]:
    found = Seen()

    def ran(conn: Any, cursor: Any, statement: str, *_: Any) -> None:
        name = threading.current_thread().name
        word = statement.lstrip()[:16].upper()
        if word.startswith(("BEGIN IMMEDIATE", "INSERT", "UPDATE", "DELETE")):
            found.writing.setdefault(id(conn.connection.dbapi_connection), name)
        flat = f"{statement} ".replace("\n", " ")
        where = flat.partition(" WHERE ")[2]
        # A read of every ingredient (not one by its id).
        if word.startswith("SELECT") and " FROM food " in flat and "food.id " not in where:
            found.food_reads[name] += 1

    def ended(conn: Any) -> None:
        name = found.writing.pop(id(conn.connection.dbapi_connection), None)
        if name is not None:
            found.stretches[name] += 1

    event.listen(engine, "after_cursor_execute", ran)
    event.listen(engine, "commit", ended)
    event.listen(engine, "rollback", ended)
    try:
        yield found
    finally:
        event.remove(engine, "after_cursor_execute", ran)
        event.remove(engine, "commit", ended)
        event.remove(engine, "rollback", ended)


def engine_of(client: TestClient) -> Engine:
    return client.app.state.engine  # type: ignore[attr-defined,no-any-return]


def test_the_ingredients_are_read_once_not_once_per_mealie_food(
    kitchen: TestClient, tmp_path: Path
) -> None:
    raw = zipped(tmp_path / "many.zip", many(foods=300, recipes=3), photo=False)
    with seen(engine_of(kitchen)) as asked:
        job = bring_in(kitchen, raw)
    assert job["state"] == "done" and job["counts"]["saved"] == 3
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        made = db.scalars(select(Food).where(Food.mealie_import_id == job["id"])).all()
    assert len(made) == 300
    # Before round 1: every Mealie food read every ingredient, in the preview and again in
    # the import, under the lock.
    assert sum(asked.food_reads.values()) < 40, asked.food_reads


def test_new_ingredients_and_recipes_go_in_short_stretches(
    kitchen: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # No time at all for a stretch: one ingredient or recipe each.
    monkeypatch.setattr(mealie_import, "HOLD_SECONDS", 0, raising=False)
    monkeypatch.setattr(mealie_import, "PAUSE_SECONDS", 0, raising=False)
    raw = zipped(tmp_path / "many.zip", many(foods=30, recipes=10), photo=False)
    with seen(engine_of(kitchen)) as asked:
        job = bring_in(kitchen, raw)
    assert job["state"] == "done" and job["counts"]["saved"] == 10
    # 30 ingredients and 10 recipes, each its own stretch (before: all the ingredients in
    # one transaction, then one a recipe).
    assert asked.stretches["mealie-import"] >= 40, asked.stretches


def test_photos_are_cleaned_with_no_lock_held(
    kitchen: TestClient, raw: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    held: list[bool] = []
    cleaned = mealie_import.MealiePhotos.cleaned

    with seen(engine_of(kitchen)) as asked:

        def watched(self: Any, member: str | None) -> Any:
            held.append(asked.holding(threading.current_thread().name))
            return cleaned(self, member)

        monkeypatch.setattr(mealie_import.MealiePhotos, "cleaned", watched)
        job = bring_in(kitchen, raw)
    assert job["state"] == "done"
    assert held == [False]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalars(select(RecipePhoto)).one().recipe_id is not None


def test_save_all_and_undo_go_in_short_stretches(
    kitchen: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = zipped(tmp_path / "many.zip", many(foods=12, recipes=6, unread=True), photo=False)
    job = bring_in(kitchen, raw)
    assert job["counts"]["drafts"] == 6
    monkeypatch.setattr(mealie_import, "HOLD_SECONDS", 0, raising=False)
    monkeypatch.setattr(mealie_import, "PAUSE_SECONDS", 0, raising=False)
    monkeypatch.setattr(mealie_import, "CHUNK", 2, raising=False)
    with seen(engine_of(kitchen)) as asked:
        answer = kitchen.post(f"{API}/mealie-imports/drafts/save-all")
    assert answer.json() == {"saved": 6}
    assert sum(asked.stretches.values()) >= 6, asked.stretches  # before: 1
    with seen(engine_of(kitchen)) as asked:
        undone = kitchen.post(f"{API}/mealie-imports/{job['id']}/undo").json()
    assert undone == {"recipes": 6, "kept": 0, "foods": 12, "drafts": 0}
    assert sum(asked.stretches.values()) >= 6, asked.stretches  # before: 1
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalars(select(Recipe).where(Recipe.removed_at.is_(None))).all() == []
        assert db.get(MealieImport, job["id"]).state == "undone"  # type: ignore[union-attr]


class Stopped(BaseException):
    """The server stopping part-way (not an error the job would catch)."""


def started(kitchen: TestClient, raw: bytes, monkeypatch: pytest.MonkeyPatch) -> int:
    """An import started, with the runner held back so the test runs it itself."""
    monkeypatch.setattr(kitchen.app.state.mealie, "kick", lambda _id: None)  # type: ignore[attr-defined]
    made = upload(kitchen, raw).json()["id"]
    assert kitchen.post(f"{API}/mealie-imports/{made}/start", json={}).status_code == 202
    return made  # type: ignore[no-any-return]


def test_a_restart_carries_on_from_where_it_stopped(
    kitchen: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = zipped(tmp_path / "many.zip", many(foods=8, recipes=8), photo=False)
    import_id = started(kitchen, raw, monkeypatch)
    monkeypatch.setattr(mealie_import, "PREPARE", 3, raising=False)
    prepare = mealie_import._prepare
    calls: list[int] = []

    def stops_second_time(*args: Any) -> Any:
        calls.append(1)
        if len(calls) == 2:
            raise Stopped
        return prepare(*args)

    monkeypatch.setattr(mealie_import, "_prepare", stops_second_time)
    factory = kitchen.app.state.sessionmaker  # type: ignore[attr-defined]
    with pytest.raises(Stopped):
        mealie_import.run(factory, import_id)
    with factory() as db:
        row = db.get(MealieImport, import_id)
        assert row is not None and row.state == "running" and row.done == 3
        foods_before = len(db.scalars(select(Food).where(Food.mealie_import_id == import_id)).all())
    assert foods_before == 8
    # The server starts again: what was saved isn't saved twice, the ingredients aren't made
    # again.
    monkeypatch.setattr(mealie_import, "_prepare", prepare)
    mealie_import.run(factory, import_id)
    with factory() as db:
        row = db.get(MealieImport, import_id)
        assert row is not None and row.state == "done" and row.done == 8
        assert sorted(entry["key"] for entry in row.results) == sorted(
            f"r{i:031d}" for i in range(8)
        )
        assert len(db.scalars(select(Recipe)).all()) == 8
        assert len(db.scalars(select(Food).where(Food.mealie_import_id == import_id)).all()) == 8


def test_cancel_stops_a_running_import_between_stretches(
    kitchen: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = zipped(tmp_path / "many.zip", many(foods=8, recipes=8), photo=False)
    import_id = started(kitchen, raw, monkeypatch)
    monkeypatch.setattr(mealie_import, "PREPARE", 3, raising=False)
    prepare = mealie_import._prepare
    calls: list[int] = []
    answers: list[Any] = []

    def cancels_second_time(*args: Any) -> Any:
        calls.append(1)
        if len(calls) == 2:
            answers.append(kitchen.delete(f"{API}/mealie-imports/{import_id}"))
        return prepare(*args)

    monkeypatch.setattr(mealie_import, "_prepare", cancels_second_time)
    factory = kitchen.app.state.sessionmaker  # type: ignore[attr-defined]
    mealie_import.run(factory, import_id)
    assert [answer.status_code for answer in answers] == [204], answers[0].text
    with factory() as db:
        row = db.get(MealieImport, import_id)
        assert row is not None and row.state == "done" and row.choices["stopped"] is True
        assert row.done == 3 and row.file_key is None
        assert len(db.scalars(select(Recipe)).all()) == 3
        assert db.scalars(select(RecipePhoto)).all() == []
    assert mealie_files(kitchen) == []
    # What came in has the import's Undo.
    undone = kitchen.post(f"{API}/mealie-imports/{import_id}/undo").json()
    assert undone["recipes"] == 3


def test_one_import_adds_at_most_5000_new_ingredients(
    kitchen: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert mealie_import.MAX_NEW_FOODS == 5_000
    monkeypatch.setattr(mealie_import, "MAX_NEW_FOODS", 5)
    raw = zipped(tmp_path / "many.zip", many(foods=8, recipes=8), photo=False)
    made = upload(kitchen, raw).json()
    # The preview says how many aren't added.
    assert made["preview"]["foods_new"] == 8 and made["preview"]["foods_left_out"] == 3
    import_id = made["id"]
    monkeypatch.setattr(kitchen.app.state.mealie, "kick", lambda _id: None)  # type: ignore[attr-defined]
    assert kitchen.post(f"{API}/mealie-imports/{import_id}/start", json={}).status_code == 202
    # The server stops just after making the ingredients, before noting it had: the restart
    # doesn't add more than the most.
    make = mealie_import._make_foods

    def stops_after(*args: Any) -> Any:
        make(*args)
        raise Stopped

    monkeypatch.setattr(mealie_import, "_make_foods", stops_after)
    factory = kitchen.app.state.sessionmaker  # type: ignore[attr-defined]
    with pytest.raises(Stopped):
        mealie_import.run(factory, import_id)
    monkeypatch.setattr(mealie_import, "_make_foods", make)
    mealie_import.run(factory, import_id)
    job = kitchen.get(f"{API}/mealie-imports/{import_id}").json()
    assert job["state"] == "done"
    # The other 3 recipes' lines name an ingredient that wasn't added: they wait in Drafts.
    assert job["counts"]["new_foods"] == 5
    assert job["counts"]["saved"] == 5 and job["counts"]["drafts"] == 3
    with factory() as db:
        assert len(db.scalars(select(Food).where(Food.mealie_import_id == import_id)).all()) == 5


def test_a_mealie_draft_can_be_kept_again_and_comes_back_still_from_mealie(
    kitchen: TestClient, raw: bytes
) -> None:
    # Round 1, S-M4: only the server's import makes Mealie drafts, but one it made can be
    # opened and kept again, and an Undo of its delete brings it back as the import's.
    done = bring_in(kitchen, raw)
    (draft,) = kitchen.get(f"{API}/recipes/drafts").json()["drafts"]
    opened = kitchen.get(f"{API}/recipes/drafts/{draft['id']}").json()
    body = {"text": opened["text"], "review": opened["review"], "choices": opened["choices"]}
    assert kitchen.put(f"{API}/recipes/drafts/{draft['id']}", json=body).status_code == 200
    change = kitchen.delete(f"{API}/recipes/drafts/{draft['id']}").json()["change"]
    assert kitchen.post(f"{API}/changes/{change['id']}/undo").status_code == 200
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        back = db.get(ImportDraft, draft["id"])
        assert back is not None and back.mealie_import_id == done["id"]
        assert drafts.count(db, 1) == 0


def test_a_file_being_sent_holds_up_only_its_own_household(
    kitchen: TestClient, neighbour: TestClient, raw: bytes
) -> None:
    # Round 1, review 12: one upload at a time for the whole server, with no time limit, so a
    # stalled one held up everyone's.
    mine = 1  # the kitchen's household
    mealie_api._UPLOADING.add(mine)
    try:
        busy = upload(kitchen, raw)
        assert busy.status_code == 503 and busy.json()["code"] == "mealie_upload_busy"
        assert upload(neighbour, raw).status_code == 201
    finally:
        mealie_api._UPLOADING.discard(mine)
    assert upload(kitchen, raw).status_code == 201
    assert set() == mealie_api._UPLOADING


class _TimedReader:
    """The server's one reader, held by someone else; it notes how long a caller would wait."""

    def __init__(self) -> None:
        self.waits: list[float | None] = []

    def acquire(self, blocking: bool = True, timeout: float | None = None) -> bool:
        self.waits.append(timeout)
        return False

    def release(self) -> None:  # never reached: nobody gets it
        raise AssertionError("released a reader nobody held")


def test_an_upload_never_waits_for_a_busy_reader(
    kitchen: TestClient, neighbour: TestClient, raw: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Round 2, S1: 45 small uploads each waited up to 60 s for the reader in a worker thread,
    # and all 40 threads were busy. Now a request answers 503 at once, with no wait.
    held = _TimedReader()
    monkeypatch.setattr(mealie_file, "_one_at_a_time", held)
    for client in (kitchen, neighbour):
        busy = upload(client, raw)
        assert busy.status_code == 503 and busy.json()["code"] == "mealie_busy"
    assert held.waits == [0.0, 0.0]
    # Nobody else's ordinary request is held up, and the guard is let go each time.
    assert kitchen.get(f"{API}/mealie-imports/current").status_code == 200
    assert set() == mealie_api._UPLOADING
    monkeypatch.undo()
    assert upload(kitchen, raw).status_code == 201


def test_a_household_s_upload_is_guarded_while_its_file_is_read(
    kitchen: TestClient, raw: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Round 2, S1: the guard covered only the sending; now also the reading and the preview.
    read = mealie_file.read_file
    seen: list[Any] = []

    def second_upload_meanwhile(path: Path, **kwargs: Any) -> Any:
        again = upload(kitchen, raw)
        seen.append((again.status_code, again.json()["code"]))
        return read(path, **kwargs)

    monkeypatch.setattr(mealie_file, "read_file", second_upload_meanwhile)
    assert upload(kitchen, raw).status_code == 201
    assert seen == [(503, "mealie_upload_busy")]
    assert set() == mealie_api._UPLOADING


def test_the_job_waits_while_the_file_reader_is_busy(
    kitchen: TestClient, raw: bytes, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Round 1, review 2: a busy reader failed the whole import and deleted its file.
    import_id = started(kitchen, raw, monkeypatch)
    read = mealie_file.read_file
    tries: list[int] = []

    def busy_twice(path: Path) -> Any:
        tries.append(1)
        if len(tries) <= 2:
            raise MealieFileProblem("busy")
        return read(path)

    monkeypatch.setattr(mealie_file, "read_file", busy_twice)
    factory = kitchen.app.state.sessionmaker  # type: ignore[attr-defined]
    mealie_import.run(factory, import_id)
    assert len(tries) == 3
    job = kitchen.get(f"{API}/mealie-imports/{import_id}").json()
    assert job["state"] == "done" and job["counts"]["saved"] == 2, job["counts"]


def test_the_job_gives_up_on_a_reader_that_stays_busy_and_stops_if_cancelled(
    kitchen: TestClient, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(mealie_import, "BUSY_TRIES", 3)
    tries: list[int] = []

    def always_busy(path: Path) -> Any:
        tries.append(1)
        raise MealieFileProblem("busy")

    factory = kitchen.app.state.sessionmaker  # type: ignore[attr-defined]
    first = started(kitchen, zipped(tmp_path / "a.zip"), monkeypatch)
    monkeypatch.setattr(mealie_file, "read_file", always_busy)
    mealie_import.run(factory, first)
    assert len(tries) == 3
    assert kitchen.get(f"{API}/mealie-imports/{first}").json()["state"] == "failed"
    # Cancelled while it waits: it stops, and doesn't fail.
    tries.clear()
    monkeypatch.undo()
    second = started(kitchen, zipped(tmp_path / "b.zip"), monkeypatch)

    def busy_then_cancelled(path: Path) -> Any:
        tries.append(1)
        assert kitchen.delete(f"{API}/mealie-imports/{second}").status_code == 204
        raise MealieFileProblem("busy")

    monkeypatch.setattr(mealie_file, "read_file", busy_then_cancelled)
    mealie_import.run(factory, second)
    assert len(tries) == 1
    job = kitchen.get(f"{API}/mealie-imports/{second}").json()
    assert job["state"] == "done" and job["done"] == 0


def mealie_writes(import_id: int) -> list[tuple[str, str]]:
    return [
        ("POST", f"{API}/mealie-imports/{import_id}/start"),
        ("DELETE", f"{API}/mealie-imports/{import_id}"),
        ("POST", f"{API}/mealie-imports/{import_id}/undo"),
        ("POST", f"{API}/mealie-imports/drafts/save-all"),
    ]


def test_only_the_households_admin_may_import(kitchen: TestClient, raw: bytes) -> None:
    # Round 1, review 9 (cabledrawer 14 Nov): like the other Your data actions.
    noor = person(kitchen, name="Noor", username="noor")
    sent = upload(noor, raw)
    assert sent.status_code == 403 and sent.json()["code"] == "admins_only"
    assert mealie_files(kitchen) == []  # refused before a byte was kept
    import_id = upload(kitchen, raw).json()["id"]
    for method, path in mealie_writes(import_id):
        answer = noor.request(method, path, json={})
        assert answer.status_code == 403, (method, path, answer.text)
        assert answer.json()["code"] == "admins_only"
    # Looking is fine: the screen's state, and nothing changed.
    assert noor.get(f"{API}/mealie-imports/current").json()["current"]["state"] == "ready"


def test_an_api_token_may_not_import(kitchen: TestClient, raw: bytes) -> None:
    made = kitchen.post(f"{API}/api-tokens", json={"name": "Sam's script", "scope": "full"})
    app = TestClient(kitchen.app, base_url="https://testserver")
    app.headers["Authorization"] = f"Bearer {made.json()['token']}"
    sent = upload(app, raw)
    assert sent.status_code == 403 and sent.json()["code"] == "not_for_tokens"
    assert mealie_files(kitchen) == []
    import_id = upload(kitchen, raw).json()["id"]
    for method, path in mealie_writes(import_id):
        answer = app.request(method, path, json={})
        assert answer.status_code == 403, (method, path, answer.text)
        assert answer.json()["code"] == "not_for_tokens"


# --- Round 1: the rest (review 1, 5, 6, 11) ---------------------------------------------------


def keyed(job: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {entry["key"]: entry for entry in job["recent"]}


def test_recipes_left_out_add_no_ingredients_and_the_preview_counts_the_same(
    kitchen: TestClient, tmp_path: Path
) -> None:
    raw = zipped(tmp_path / "many.zip", many(foods=4, recipes=4), photo=False)
    first = bring_in(kitchen, raw, leave_out=["r" + "0" * 31])  # unticked
    assert first["counts"]["saved"] == 3 and first["counts"]["new_foods"] == 3
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        names = set(db.scalars(select(Food.name).where(Food.mealie_import_id.is_not(None))))
    assert len(names) == 3 and not any(name.endswith("spice 0") for name in names)
    # The same file again: three recipes are already here, so only the fourth's ingredient
    # is counted, as new (before: every recipe's, so 1 new and 3 matching).
    preview = upload(kitchen, raw).json()["preview"]
    assert preview["already"] == 3 and preview["new"] == 1
    assert preview["foods_new"] == 1 and preview["foods_matching"] == 0
    assert preview["foods_new_names"][0].endswith("spice 0")


def test_a_second_import_of_the_same_file_adds_nothing(kitchen: TestClient, tmp_path: Path) -> None:
    raw = zipped(tmp_path / "many.zip", many(foods=4, recipes=4, unread=True), photo=False)
    first = bring_in(kitchen, raw)
    assert first["counts"]["drafts"] == 4 and first["counts"]["new_foods"] == 4
    again = bring_in(kitchen, raw)
    assert again["state"] == "done"
    assert again["counts"]["saved"] == 0 and again["counts"]["drafts"] == 0
    assert again["counts"]["already"] == 4 and again["counts"]["new_foods"] == 0
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert len(db.scalars(select(ImportDraft)).all()) == 4
        assert len(db.scalars(select(Food).where(Food.mealie_import_id.is_not(None))).all()) == 4


def test_a_deleted_mealie_draft_is_not_already_here(kitchen: TestClient, raw: bytes) -> None:
    bring_in(kitchen, raw)
    (draft,) = kitchen.get(f"{API}/recipes/drafts").json()["drafts"]
    assert kitchen.delete(f"{API}/recipes/drafts/{draft['id']}").status_code == 200
    preview = upload(kitchen, raw).json()["preview"]
    soup = next(entry for entry in preview["recipes"] if entry["key"] == SOUP)
    assert soup["already"] is False  # before round 1: still "already here"
    assert preview["already"] == 2 and preview["new"] == 1


def test_a_recipe_with_no_name_is_brought_in_not_dropped(
    kitchen: TestClient, tmp_path: Path
) -> None:
    data = database()
    data["recipes"].append(recipe("4" * 32, "   "))
    data["recipes"].append(recipe("5" * 32, ""))
    data["recipes_ingredients"].append(line("5" * 32, 0, "a pinch of Noor's secret"))
    raw = zipped(tmp_path / "nameless.zip", data, photo=False)
    preview = upload(kitchen, raw).json()["preview"]
    assert preview["new"] == 5
    assert [entry["name"] for entry in preview["recipes"][3:]] == [drafts.NO_NAME] * 2
    job = bring_in(kitchen, raw)
    assert job["total"] == 5 and job["done"] == 5
    rows = keyed(job)
    assert rows["4" * 32]["state"] == "saved" and rows["4" * 32]["name"] == drafts.NO_NAME
    assert rows["5" * 32]["state"] == "draft" and rows["5" * 32]["name"] == drafts.NO_NAME


def test_a_nameless_recipe_is_not_doubled_by_a_second_import(
    kitchen: TestClient, tmp_path: Path
) -> None:
    data = database()
    data["recipes"].append(recipe("4" * 32, "   "))
    data["recipes"].append(recipe("5" * 32, ""))
    data["recipes_ingredients"].append(line("5" * 32, 0, "a pinch of Noor's secret"))
    raw = zipped(tmp_path / "nameless.zip", data, photo=False)
    first = bring_in(kitchen, raw)
    assert first["counts"]["saved"] + first["counts"]["drafts"] == 5
    preview = upload(kitchen, raw).json()["preview"]
    assert preview["new"] == 0 and preview["already"] == 5
    again = bring_in(kitchen, raw)
    assert again["counts"]["saved"] == 0 and again["counts"]["drafts"] == 0
    assert again["counts"]["already"] == 5
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        untitled = Recipe.name == drafts.NO_NAME
        assert len(db.scalars(select(Recipe).where(untitled)).all()) == 1
        assert (
            len(db.scalars(select(ImportDraft).where(ImportDraft.name == drafts.NO_NAME)).all())
            == 1
        )


def test_only_the_ingredients_of_the_kept_lines_are_counted_and_added(
    kitchen: TestClient, tmp_path: Path
) -> None:
    # Round 2, S2: a recipe of 250 lines, each with its own food, keeps 200; the preview and the
    # import count and add only those 200 ingredients (it said 250).
    foods = [f"{i:032x}" for i in range(1, 251)]
    data = {
        **database(),
        "recipes": [recipe("a" * 32, "Noor's long list")],
        "recipes_ingredients": [line("a" * 32, i, "", key, 100) for i, key in enumerate(foods)],
        "recipe_instructions": [],
        "ingredient_foods": [
            {"id": key, "name": f"Lorna's food {i}"} for i, key in enumerate(foods)
        ],
        "recipes_to_tags": [],
    }
    raw = zipped(tmp_path / "long.zip", data, photo=False)
    assert upload(kitchen, raw).json()["preview"]["foods_new"] == 200
    assert bring_in(kitchen, raw)["counts"]["new_foods"] == 200


def test_odd_names_come_in_tidied_and_match_what_is_here(
    kitchen: TestClient, tmp_path: Path
) -> None:
    assert kitchen.post(f"{API}/foods", json={"name": "Café crème"}).status_code == 201
    foods = {
        "a" * 32: "  café CRÈME ",
        "b" * 32: "<b>Noor's</b> chilli",
        "c" * 32: "\U0001f336 Lorna's chilli",
        "d" * 32: "Sam's " + "long " * 80,
        "e" * 32: "   ",
    }
    keys = [f"{i}" * 32 for i in range(6, 10)]
    names = ["  Sam's   stew  ", "<script>Noor</script>", "Ünïcödé dal", "Lorna's ' \" quote"]
    data = {
        **database(),
        "recipes": [recipe(key, name) for key, name in zip(keys, names, strict=True)],
        "recipes_ingredients": [
            line(keys[i % 4], i, "", food, 100) for i, food in enumerate(foods)
        ],
        "recipe_instructions": [],
        "ingredient_foods": [{"id": key, "name": name} for key, name in foods.items()],
        "recipes_to_tags": [],
    }
    job = bring_in(kitchen, zipped(tmp_path / "odd.zip", data, photo=False))
    assert job["state"] == "done" and job["done"] == 4
    rows = keyed(job)
    # A name that is only markup is nameless, so it comes in as "Untitled recipe".
    assert rows["7" * 32]["name"] == drafts.NO_NAME and rows["7" * 32]["state"] == "saved"
    assert rows["8" * 32]["name"] == "Ünïcödé dal" and rows["8" * 32]["state"] == "saved"
    # Spaces tidied; the blank ingredient leaves a line to check, so a draft.
    assert rows["6" * 32] | {"draft_id": 0} == rows["6" * 32] | {
        "name": "Sam's stew", "state": "draft", "unread": ["100 g"], "draft_id": 0
    }  # fmt: skip
    # Too long for an ingredient: cut to 100 characters, and the line uses the cut name
    # (before: an ingredient made that no line used, and the line left to check).
    assert rows["9" * 32]["name"] == "Lorna's ' \" quote" and rows["9" * 32]["state"] == "saved"
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        made = set(db.scalars(select(Food.name).where(Food.mealie_import_id == job["id"])))
        cafe = list(db.scalars(select(Food).where(Food.name == "Café crème")))
    # The café matched the one already here (accents and case), the markup was taken out.
    long = "Sam's" + " long" * 18 + "…"
    assert len(long) <= 100 and made == {"Noor's chilli", "\U0001f336 Lorna's chilli", long}
    assert len(cafe) == 1 and cafe[0].mealie_import_id is None
    assert not any("<" in name or "café" in name.lower() for name in made)


def test_undo_keeps_what_was_cooked_planned_or_used_since(
    kitchen: TestClient, tmp_path: Path
) -> None:
    raw = zipped(tmp_path / "many.zip", many(foods=4, recipes=4), photo=False)
    job = bring_in(kitchen, raw)
    ids = {key: entry["recipe_id"] for key, entry in keyed(job).items()}
    cooked, planned, used, plain = (ids[f"r{i:031d}"] for i in range(4))
    day = utcnow().date()
    answer = kitchen.post(
        f"{API}/plan/items",
        json={
            "date": day.isoformat(),
            "slot_id": slot_ids(kitchen)["Dinner"],
            "recipe_id": planned,
        },
    )
    assert answer.status_code == 201, answer.text
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        batch = BatchCook(
            household_id=1, recipe_id=cooked, recipe_name="x", cooked_on=day, tub_count=1
        )
        db.add(batch)
        db.flush()
        db.add(
            CookedRecord(
                household_id=1,
                batch_id=batch.id,
                recipe_id=cooked,
                portions=1,
                snapshot={},
                cooked_at=utcnow(),
            )
        )
        thali = add_recipe(db, 1, "Noor's thali")
        db.flush()
        plain_food = db.scalar(select(Food.id).where(Food.name.endswith("spice 3")))
        db.add(RecipeLine(household_id=1, recipe_id=thali.id, position=0, words="dish",
                          sub_recipe_id=used))  # fmt: skip
        db.add(RecipeLine(household_id=1, recipe_id=thali.id, position=1, words="spice",
                          food_id=plain_food))  # fmt: skip
        db.commit()
    undone = kitchen.post(f"{API}/mealie-imports/{job['id']}/undo").json()
    assert undone["recipes"] == 1 and undone["kept"] == 3
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        live = set(db.scalars(select(Recipe.id).where(Recipe.removed_at.is_(None))))
        assert {cooked, planned, used} <= live and plain not in live
        # The plain recipe's ingredient is used by the thali, so it stays.
        assert db.get(Food, plain_food).removed_at is None  # type: ignore[union-attr]
    assert undone["foods"] == 0
