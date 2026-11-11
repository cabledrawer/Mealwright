"""The "never reuse an id" counter survives the 0.8 database changes (whole-0.8 review D1).

SQLite keeps each AUTOINCREMENT table's counter in `sqlite_sequence`. Rebuilding a table (every
batch_alter_table on SQLite) used to restart it at the highest id left, so a removed meal's or
batch's id was handed out again and an old Undo hit the new row. Alembic's env.py now keeps the
counters over every upgrade and downgrade, and the newest migration raises counters that an
earlier upgrade already reset (cabledrawer's TEST install went through that one).
"""

import json
from pathlib import Path
from typing import Any

from conftest import SETUP_CODE
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sync_kit import ok
from test_plan import slot_ids
from test_plan_writes import D1, D2
from test_recipes import make

from mealwright import migrate
from mealwright.config import Settings
from mealwright.db import make_engine
from mealwright.main import create_app

API = "/api/v1"
V070 = "5fbd6d33c434"  # v0.7.0's last migration
BEFORE_REPAIR = "e7b4d9a1c628"  # the head before the counter repair
REPAIR = "a9d3f6b2c481"
# Tables made by migrations after the repair (0.9 A1's people): going back before the repair
# drops them, so their counters go with them.
AFTER_REPAIR = {"member"}
REBUILT = {"meal_item", "batch_cook", "recipe_step", "recipe_line", "recipe", "food"}
ADMIN = {
    "name": "Tess",
    "username": "tess",
    "password": "correct horse battery",
    "setup_code": SETUP_CODE,
}


def _counters(engine: Engine) -> dict[str, int]:
    with engine.connect() as connection:
        return dict(connection.exec_driver_sql("SELECT name, seq FROM sqlite_sequence").all())


def _set_counter(engine: Engine, table: str, seq: int) -> None:
    with engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE sqlite_sequence SET seq = ? WHERE name = ?", (seq, table)
        )


def _kitchen_with_removals(settings: Settings) -> dict[str, Any]:
    """On the newest layout: cook-plan a batch and remove it, then plan one more meal and
    remove it too, so the newest batch and the newest meal item are both gone. Returns what the
    old Undo buttons are called and the counters as they stand."""
    with TestClient(create_app(settings), base_url="https://testserver") as app:
        assert app.post(f"{API}/setup", json=ADMIN).status_code == 201
        recipe = make(app, "Sambar")
        slots = slot_ids(app)
        cooked = ok(
            app.post(
                f"{API}/plan/items/{_second_item(app, recipe['id'], slots)}/batch",
                json={"tub_count": 3, "pattern": "pick"},
            ),
            201,
        )
        removed_batch = ok(app.delete(f"{API}/plan/batches/{cooked['batch_id']}"))
        planned = ok(
            app.post(
                f"{API}/plan/items",
                json={
                    "date": D1.isoformat(),
                    "slot_id": slots["Dinner"],
                    "recipe_id": recipe["id"],
                },
            ),
            201,
        )
        removed_item = ok(app.delete(f"{API}/plan/items/{planned['item_id']}"))
    engine = make_engine(f"sqlite:///{settings.data_dir / 'mealwright.db'}")
    counters = _counters(engine)
    engine.dispose()
    return {
        "item": planned["item_id"],
        "planned_change": planned["change"]["id"],
        "removed_item_change": removed_item["change"]["id"],
        "batch": cooked["batch_id"],
        "removed_batch_change": removed_batch["change"]["id"],
        "counters": counters,
    }


def _second_item(app: TestClient, recipe_id: int, slots: dict[str, int]) -> int:
    made = ok(
        app.post(
            f"{API}/plan/items",
            json={"date": D2.isoformat(), "slot_id": slots["Dinner"], "recipe_id": recipe_id},
        ),
        201,
    )
    return int(made["item_id"])


def _as_v070_would_have_left_it(settings: Settings, old: dict[str, Any]) -> Engine:
    """Go back to v0.7.0's layout. v0.7.0 never rebuilt these tables, so its counters were the
    highest id ever given out: put them back to that whatever the downgrade did."""
    engine = make_engine(f"sqlite:///{settings.data_dir / 'mealwright.db'}")
    migrate.downgrade(engine, V070)
    for table in ("meal_item", "batch_cook"):
        _set_counter(engine, table, old["counters"][table])
    return engine


def test_upgrade_from_v070_with_a_removal_in_its_last_week_never_reuses_the_id(
    tmp_path: Path,
) -> None:
    """cabledrawer 11 Nov: an upgrade test from a filled v0.7.0 database with a removal in its last
    week. The newest meal item and the newest batch were removed; after the upgrade the next
    ones get new ids, and the old Undo buttons don't touch them."""
    settings = Settings(data_dir=tmp_path / "data", run_jobs=False)
    settings.data_dir.mkdir()
    old = _kitchen_with_removals(settings)
    engine = _as_v070_would_have_left_it(settings, old)
    assert migrate.current_revision(engine) == V070
    # Up to the head before the repair: only env.py keeps the counters over these rebuilds
    # (RF1 review r1).
    migrate.upgrade(engine, BEFORE_REPAIR)
    kept = _counters(engine)
    assert kept["meal_item"] >= old["item"] and kept["batch_cook"] >= old["batch"]
    engine.dispose()

    with TestClient(create_app(settings), base_url="https://testserver") as app:  # upgrades
        assert app.post(f"{API}/session", json=ADMIN).status_code == 200
        recipe = make(app, "Rice bowl")
        slots = slot_ids(app)
        new = ok(
            app.post(
                f"{API}/plan/items",
                json={
                    "date": D1.isoformat(),
                    "slot_id": slots["Dinner"],
                    "recipe_id": recipe["id"],
                },
            ),
            201,
        )
        assert new["item_id"] > old["item"]
        item = _second_item(app, recipe["id"], slots)
        batch = ok(
            app.post(f"{API}/plan/items/{item}/batch", json={"tub_count": 3, "pattern": "pick"}),
            201,
        )
        assert batch["batch_id"] > old["batch"]

        # The old Planned button, and the old Took-the-tubs-off button, change nothing here.
        app.post(f"{API}/changes/{old['planned_change']}/undo")
        app.post(f"{API}/changes/{old['removed_batch_change']}/undo")
        plan = ok(app.get(f"{API}/plan", params={"from": D1.isoformat(), "to": D2.isoformat()}))
        items = [i["id"] for m in plan["meals"] for i in m["items"]]
        assert new["item_id"] in items
        mine = [t for t in plan["tubs"] if t["batch_id"] == batch["batch_id"]]
        assert len(mine) == 3


def test_a_downgrade_keeps_the_counters(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", run_jobs=False)
    settings.data_dir.mkdir()
    old = _kitchen_with_removals(settings)
    engine = make_engine(f"sqlite:///{settings.data_dir / 'mealwright.db'}")
    before = _counters(engine)
    assert before["meal_item"] >= old["item"] and before["batch_cook"] >= old["batch"]
    for step in (BEFORE_REPAIR, V070):  # through the optional/methods/sessions rebuilds
        migrate.downgrade(engine, step)
        after = _counters(engine)
        for table in before.keys() & REBUILT:
            assert after[table] >= before[table], (step, table)
    migrate.upgrade(engine)
    after = _counters(engine)
    for table in before.keys() & REBUILT:
        assert after[table] >= before[table], table
    engine.dispose()


def test_the_repair_migration_raises_a_counter_an_earlier_upgrade_reset(tmp_path: Path) -> None:
    """The TEST install: the counters were reset by the upgrade. The repair raises each one to the
    highest id an Undo record still names, and to the highest id in the table."""
    settings = Settings(data_dir=tmp_path / "data", run_jobs=False)
    settings.data_dir.mkdir()
    old = _kitchen_with_removals(settings)
    engine = make_engine(f"sqlite:///{settings.data_dir / 'mealwright.db'}")
    healthy = _counters(engine)
    migrate.downgrade(engine, BEFORE_REPAIR)
    # What the bad upgrade left: counters at the highest id left in the table.
    with engine.connect() as connection:
        for table in ("meal_item", "batch_cook", "place", "shop"):
            top = connection.exec_driver_sql(
                "SELECT coalesce(max(id), 0) FROM " + table  # noqa: S608
            ).scalar_one()
            _set_counter(engine, table, top)
    # A removed place and a removed shop that Undo could still bring back, at ids above the tables'.
    with engine.begin() as connection:
        for kind, summary in (
            ("place_removed", "Removed the place Spice shelf"),
            ("shop_removed", "Removed the shop Corner"),
        ):
            connection.exec_driver_sql(
                "INSERT INTO change (household_id, request, kind, login_name, at, summary,"
                " undo_data)"
                " VALUES (1, 'DELETE', ?, 'Tess', '2026-11-10', ?, ?)",
                (kind, summary, json.dumps({"removed": {"id": 40}})),
            )
    assert _counters(engine)["meal_item"] < old["item"]
    assert _counters(engine)["batch_cook"] < old["batch"]
    migrate.upgrade(engine)
    counters = _counters(engine)
    assert counters["meal_item"] >= old["item"]
    assert counters["batch_cook"] >= old["batch"]
    assert counters["place"] >= 40 and counters["shop"] >= 40
    assert counters["recipe"] >= healthy["recipe"] - 1  # tables nothing names stay at their top
    # Running it again changes nothing, and going back leaves the counters alone.
    again = _counters(engine)
    migrate.downgrade(engine, BEFORE_REPAIR)
    assert _counters(engine) == {k: v for k, v in again.items() if k not in AFTER_REPAIR}
    migrate.upgrade(engine)
    assert _counters(engine) == again
    engine.dispose()


def test_the_repair_leaves_a_healthy_database_alone(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", run_jobs=False)
    settings.data_dir.mkdir()
    _kitchen_with_removals(settings)
    engine = make_engine(f"sqlite:///{settings.data_dir / 'mealwright.db'}")
    healthy = _counters(engine)
    migrate.downgrade(engine, BEFORE_REPAIR)
    migrate.upgrade(engine)
    assert _counters(engine) == healthy
    engine.dispose()


def test_the_repair_follows_the_head_it_repairs_and_every_newer_migration_follows_it() -> None:
    """It was the newest migration when it was written; later ones (0.9 A1's people, then A2's
    sign-in columns) come after it on the one line, so every upgrade still runs it."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(migrate.alembic_config())
    assert len(script.get_heads()) == 1
    line = [r.revision for r in script.walk_revisions()]  # from the head down
    assert REPAIR in line and line.index(REPAIR) < line.index(BEFORE_REPAIR)
    assert script.get_revision(REPAIR).down_revision == BEFORE_REPAIR
