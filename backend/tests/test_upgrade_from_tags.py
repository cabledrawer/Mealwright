"""A saved database from each earlier release upgrades cleanly to the newest layout (BUILD-PLAN
0.9.5, "upgrade tests"; cabledrawer 2 Nov).

The databases in `tests/upgrade/databases/` were made by each release's own code through its
own API (`tests/upgrade/README.md`). Each test here takes a copy, upgrades it the way a
start-up does, then checks the file is sound, nothing the person made was lost, and the app
runs on it. The test's name carries the tag: a failure says which release broke.
"""

import sqlite3
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory
from fastapi.testclient import TestClient
from upgrade_kit import ADMIN, TAGS, copy_of, settings_for, upgrade_copy

from mealwright import migrate
from mealwright.main import create_app

# What a person made, as tables, and the first release that had it. The counts before and
# after must match; a database from a release that had the table must hold something in it
# (so a database that came out empty can't make the test pass for nothing).
THEIR_THINGS = {
    "household": "v0.1.0",
    "login": "v0.1.0",
    "food": "v0.2.0",
    "shop": "v0.2.0",
    "stock_lot": "v0.2.0",
    "shopping_list": "v0.3.0",
    "list_item": "v0.3.0",
    "recipe": "v0.4.0",
    "recipe_line": "v0.4.0",
    "recipe_step": "v0.4.0",
    "meal": "v0.6.0",
    "meal_item": "v0.6.0",
    "tub": "v0.6.0",
    "batch_session": "v0.8.0",
    "member": "v0.9.0-beta.1",
}


def _order(tag: str) -> int:
    return TAGS.index(tag)


def _tables(path: Path) -> list[str]:
    with sqlite3.connect(path) as db:
        return [
            row[0]
            for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        ]


def _count(path: Path, table: str) -> int:
    with sqlite3.connect(path) as db:
        return int(db.execute(f"SELECT count(*) FROM {table}").fetchone()[0])  # noqa: S608


def test_there_is_a_database_for_every_earlier_release() -> None:
    assert TAGS[0] == "v0.1.0"
    assert set(TAGS) >= {
        "v0.1.0",
        "v0.1.1",
        "v0.2.0",
        "v0.2.1",
        "v0.3.0",
        "v0.4.0",
        "v0.5.0",
        "v0.5.1",
        "v0.6.0",
        "v0.7.0",
        "v0.8.0",
        "v0.9.0-beta.1",
    }


@pytest.mark.parametrize("tag", TAGS)
def test_database_from_release_upgrades_cleanly(tag: str, tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    before = copy_of(tag, data_dir)
    tables_before = _tables(before)
    counts_before = {
        table: _count(before, table) for table in THEIR_THINGS if table in tables_before
    }
    for table, first in THEIR_THINGS.items():
        if _order(tag) >= _order(first):
            assert counts_before.get(table, 0) > 0, f"{tag}'s saved database has no {table} rows"
    with sqlite3.connect(before) as db:
        was_at = db.execute("SELECT version_num FROM alembic_version").fetchone()[0]
    before.unlink()

    path = upgrade_copy(tag, data_dir)

    with sqlite3.connect(path) as db:
        assert db.execute("PRAGMA integrity_check").fetchall() == [("ok",)], f"{tag}: integrity"
        assert db.execute("PRAGMA foreign_key_check").fetchall() == [], f"{tag}: foreign keys"
        head = ScriptDirectory.from_config(migrate.alembic_config()).get_current_head()
        assert db.execute("SELECT version_num FROM alembic_version").fetchall() == [(head,)]
        for table in _tables(path):
            if table in ("household", "alembic_version"):
                continue
            columns = [row[1] for row in db.execute(f"PRAGMA table_info({table})")]
            assert "household_id" in columns, f"{tag}: {table} has no household_id"
            empty = db.execute(
                f"SELECT count(*) FROM {table} WHERE household_id IS NULL"  # noqa: S608
            ).fetchone()[0]
            assert empty == 0, f"{tag}: {table} has {empty} rows with no household_id"
    for table, count in counts_before.items():
        assert _count(path, table) == count, f"{tag}: {table} rows changed in the upgrade"
    # A start-up copies the database aside before it changes anything.
    assert (data_dir / "backups").is_dir() == (was_at != head), f"{tag}: safety copy"

    # The app starts on it (its own start-up finds nothing left to do) and the admin's
    # everyday screens answer.
    with TestClient(create_app(settings_for(data_dir)), base_url="https://testserver") as client:
        signed_in = client.post("/api/v1/session", json=ADMIN)
        assert signed_in.status_code == 200, f"{tag}: sign-in {signed_in.text}"
        for url in (
            "/api/v1/recipes",
            "/api/v1/plan?from=2026-11-01&to=2026-11-30",
            "/api/v1/shopping/lists",
            "/api/v1/pantry",
            "/api/v1/export",
        ):
            answer = client.get(url)
            assert answer.status_code == 200, f"{tag}: GET {url} gave {answer.status_code}"
        main_list = next(
            row for row in client.get("/api/v1/shopping/lists").json()["lists"] if row["main"]
        )
        assert client.get(f"/api/v1/shopping/lists/{main_list['id']}").status_code == 200


def test_the_upgraded_09_fixture_is_a_private_copy_at_the_newest_layout(
    upgraded_09_db: Path, _upgraded_09_template: Path
) -> None:
    head = ScriptDirectory.from_config(migrate.alembic_config()).get_current_head()
    with sqlite3.connect(upgraded_09_db) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchall() == [(head,)]
        db.execute("DELETE FROM recipe_step")
    assert _count(upgraded_09_db, "recipe_step") == 0
    assert _count(_upgraded_09_template, "recipe_step") > 0  # the shared copy is untouched
    with TestClient(
        create_app(settings_for(upgraded_09_db.parent)), base_url="https://testserver"
    ) as client:
        assert client.post("/api/v1/session", json=ADMIN).status_code == 200
