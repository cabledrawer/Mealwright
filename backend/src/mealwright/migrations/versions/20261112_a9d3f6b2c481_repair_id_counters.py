"""repair the "never reuse an id" counters that an earlier 0.8 upgrade reset

Revision ID: a9d3f6b2c481
Revises: e7b4d9a1c628
Create Date: 2026-11-12 09:00:00

Whole-0.8 review, D1 (cabledrawer 11 Nov). Until now every 0.8 migration that rebuilt a table on
SQLite also reset that table's "never reuse an id" counter (`sqlite_sequence`) to the highest id
left, so the id of a meal item or batch cook removed in the last days could be given out again,
and an old Undo would then hit the new row. The migrations now keep the counters (see
`migrations/counters.py`), but a database that was already upgraded still has the reset ones.

For each table 0.8 rebuilt, this raises its counter to at least the highest id in the table and at
least the highest id that any Recent-changes Undo record still names for it. Nothing else
changes. It does nothing on a database whose counters are fine, nor on Postgres.

Going back changes nothing (a higher counter only skips ids).
"""

import json
from collections.abc import Iterator, Sequence
from typing import Any

from alembic import op

from mealwright.migrations.counters import raise_counter

revision: str = "a9d3f6b2c481"
down_revision: str | Sequence[str] | None = "e7b4d9a1c628"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# The tables 0.8's migrations rebuilt (copy, drop, rename) since v0.7.0.
REBUILT = (
    "food",
    "place",
    "shop",
    "recipe",
    "recipe_line",
    "recipe_step",
    "meal_item",
    "batch_cook",
    "batch_session",
)
# An Undo step names a row by the key and table here: a number, or a snapshot with an "id".
STEP_KEYS = {"item": "meal_item", "batch": "batch_cook", "session": "batch_session"}
REMOVED_KINDS = {"place_removed": "place", "shop_removed": "shop"}


def _id_of(value: Any) -> int | None:
    if isinstance(value, dict):
        value = value.get("id")
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _named(kind: str, undo_data: Any) -> Iterator[tuple[str, int]]:
    """Every (table, id) among the rebuilt tables that one Undo record names."""
    if not isinstance(undo_data, dict):
        return
    for step in undo_data.get("plan") or []:
        if not isinstance(step, dict):
            continue
        for key, table in STEP_KEYS.items():
            if (found := _id_of(step.get(key))) is not None:
                yield table, found
        tub = step.get("tub")
        if isinstance(tub, dict) and (found := _id_of(tub.get("batch_id"))) is not None:
            yield "batch_cook", found
    removed = REMOVED_KINDS.get(kind)
    if removed is not None and (found := _id_of(undo_data.get("removed"))) is not None:
        yield removed, found


def upgrade() -> None:
    connection = op.get_bind()
    if connection.dialect.name != "sqlite":
        return
    named: dict[str, int] = {}
    for kind, raw in connection.exec_driver_sql(
        "SELECT kind, undo_data FROM change WHERE undo_data IS NOT NULL"
    ):
        try:
            data = json.loads(raw) if isinstance(raw, str) else raw
        except ValueError:
            continue
        for table, found in _named(kind, data):
            named[table] = max(named.get(table, 0), found)
    for table in REBUILT:
        raise_counter(connection, table, named.get(table, 0))


def downgrade() -> None:
    """Nothing to take back: a higher counter only skips some ids."""
