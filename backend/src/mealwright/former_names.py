"""Old names, kept where they are written (beta fix5; proposed, for cabledrawer).

"Report a problem" removes a name from the log lines, and a log line can outlive the row that
had the name: a person renamed, a recipe or tag deleted, a household called something else.
Finding old names afterwards (the undo data of changes) missed a path every time, so the names
are kept where they are written instead: a hook on every database session writes a
`former_name` row

- when a row's name column changes: the old value, and
- when a row is deleted: its current value,

whatever path did it: one row through the ORM, a bulk `delete()` or `update()`, or rows that go
with a parent (a database cascade). The Scrubber reads them with the current names, and the
nightly log tidy deletes those older than the log files (mealwright.logs.KEEP_DAYS) plus a day
(`remove_expired`).

"Delete everything" keeps nothing: it removes the household's rows, former names included,
and the report leaves out every log line from before the new set-up (api/v1/report.py).
"""

from __future__ import annotations

import logging
from collections.abc import Iterable
from datetime import datetime, timedelta
from functools import cache
from typing import Any

from sqlalchemy import Column, Table, delete, event, insert, inspect, select, true, tuple_, update
from sqlalchemy.orm import ORMExecuteState, Session
from sqlalchemy.sql.elements import ColumnElement

from mealwright import models
from mealwright.db import Base
from mealwright.logs import KEEP_DAYS

log = logging.getLogger(__name__)

# The old names live one day longer than the log files that may hold them.
KEEP_FOR = timedelta(days=KEEP_DAYS + 1)

# What each kind of name is replaced with in a report; a person's every word is removed.
# "person" and a one-word "household" are looked up word by word (see Scrubber).
REPLACEMENTS: dict[str, str | None] = {
    "person": None,
    "household": "[household]",
    "recipe": "[recipe]",
    "recipe_text": "[recipe]",
    "tag": "[recipe]",
    "meal": "[meal]",
    "ingredient": "[ingredient]",
    "shop": "[shop]",
    "place": "[place]",
    "list": "[removed]",
}
# Kinds whose names may hold a person's possessive ("Granny Mabel's lasagne").
TITLE_KINDS = frozenset({"recipe", "ingredient", "meal"})

# A kind for every column of the Scrubber's lists that is not a person's.
_KINDS: dict[tuple[str, str], str] = {
    ("Household", "name"): "household",
    ("Recipe", "name"): "recipe",
    ("Recipe", "description"): "recipe_text",
    ("RecipeLine", "words"): "recipe_text",
    ("RecipeLine", "note"): "recipe_text",
    ("RecipeMethod", "name"): "recipe_text",
    ("BatchCook", "recipe_name"): "recipe",
    ("ImportDraft", "name"): "recipe",
    ("MealItem", "name"): "meal",
    ("Tag", "name"): "tag",
    ("Food", "name"): "ingredient",
    ("FoodName", "name"): "ingredient",
    ("Shop", "name"): "shop",
    ("Place", "name"): "place",
    ("ShoppingList", "name"): "list",
    ("ApiToken", "name"): "list",
    ("MealieImport", "file_name"): "list",
    ("MealSlot", "name"): "meal",
}


def kind_of(column: Any) -> str:
    """The kind of name a column of the Scrubber's lists holds."""
    return _KINDS.get((column.class_.__name__, column.key), "person")


@cache
def _columns() -> dict[type, list[tuple[str, str]]]:
    """Every column the Scrubber treats as a name, by model: (attribute, kind)."""
    from mealwright import problem_report as pr  # imported here: it imports this module

    found: dict[type, list[tuple[str, str]]] = {}
    columns = (*pr._PEOPLE_COLUMNS, *(c for _, group in pr._PHRASE_COLUMNS for c in group))
    for column in columns:
        found.setdefault(column.class_, []).append((column.key, kind_of(column)))
    return found


def _household_column(cls: type) -> Column[Any]:
    table: Table = cls.__table__  # type: ignore[attr-defined]
    return table.c["id"] if cls is models.Household else table.c["household_id"]


# Cascades: a child's name goes with its parent when the database deletes it (ON DELETE CASCADE),
# and the session never sees that child. The tables that have such children, found from the
# tables themselves.


@cache
def _cascade_children() -> dict[str, list[tuple[Table, list[Column[Any]], list[Column[Any]]]]]:
    """Parent table → [(child table, child columns, parent columns)] for every foreign key
    with ON DELETE CASCADE (the household's own aside: Delete everything keeps nothing)."""
    found: dict[str, list[tuple[Table, list[Column[Any]], list[Column[Any]]]]] = {}
    for table in Base.metadata.sorted_tables:
        for constraint in table.foreign_key_constraints:
            if constraint.ondelete != "CASCADE" or constraint.referred_table.name == "household":
                continue
            found.setdefault(constraint.referred_table.name, []).append(
                (table, list(constraint.columns), [e.column for e in constraint.elements])
            )
    return found


@cache
def _name_tables() -> dict[str, type]:
    return {cls.__table__.name: cls for cls in _columns()}  # type: ignore[attr-defined]


@cache
def _reaches(table_name: str) -> bool:
    """Whether the table holds a name, or any table that goes with it (a cascade) does."""
    seen: set[str] = set()
    stack = [table_name]
    while stack:
        name = stack.pop()
        if name in seen:
            continue
        seen.add(name)
        if name in _name_tables():
            return True
        stack.extend(child.name for child, _, _ in _cascade_children().get(name, []))
    return False


Row = tuple[int, str, str]  # household, kind, name


def _read(connection: Any, cls: type, criterion: ColumnElement[bool] | None) -> list[Row]:
    table: Table = cls.__table__  # type: ignore[attr-defined]
    fields = _columns()[cls]
    query = select(_household_column(cls), *(table.c[key] for key, _ in fields)).distinct()
    if criterion is not None:
        query = query.where(criterion)
    rows: list[Row] = []
    for household, *values in connection.execute(query):
        for (_, kind), value in zip(fields, values, strict=True):
            if isinstance(value, str):
                rows.append((household, kind, value))
    return rows


def _gather(connection: Any, table: Table, criterion: ColumnElement[bool] | None) -> list[Row]:
    """The names held by the rows of the tables that go with the rows of `table` picked by
    `criterion` (and by theirs, down the cascade)."""
    rows: list[Row] = []
    for child, child_columns, parent_columns in _cascade_children().get(table.name, []):
        if not _reaches(child.name):
            continue
        parents = select(*parent_columns)
        if criterion is not None:
            parents = parents.where(criterion)
        if len(child_columns) == 1:
            reached = child_columns[0].in_(parents)
        else:
            reached = tuple_(*child_columns).in_(parents)
        cls = _name_tables().get(child.name)
        if cls is not None:
            rows.extend(_read(connection, cls, reached))
        rows.extend(_gather(connection, child, reached))
    return rows


def _keep(connection: Any, rows: Iterable[Row]) -> None:
    """Write the names, once each: one already kept is only dated again."""
    from mealwright.problem_report import _LONGEST_PHRASE

    wanted: dict[Row, None] = {}
    for household, kind, name in rows:
        name = " ".join(name.split())
        if name and len(name) <= 500 and len(name.split()) <= _LONGEST_PHRASE:
            wanted[(household, kind, name)] = None
    if not wanted:
        return
    table: Any = models.FormerName.__table__
    now = models.utcnow()
    have = {
        (household, kind, name)
        for household, kind, name in connection.execute(
            select(table.c.household_id, table.c.kind, table.c.name).where(
                table.c.household_id.in_({r[0] for r in wanted}),
                table.c.name.in_({r[2] for r in wanted}),
            )
        )
    }
    new = [r for r in wanted if r not in have]
    old = [r for r in wanted if r in have]
    for household, kind, name in old:
        connection.execute(
            update(table)
            .where(table.c.household_id == household, table.c.kind == kind, table.c.name == name)
            .values(at=now)
        )
    if new:
        connection.execute(
            insert(table),
            [{"household_id": h, "kind": k, "name": n, "at": now} for h, k, n in new],
        )


def _old_value(session: Session, obj: Any, key: str) -> str | None:
    """The value the database holds now for a changed attribute (the old one), also when the
    attribute was expired and so its old value was never loaded."""
    state = inspect(obj)
    history = state.attrs[key].history
    if history.deleted:
        return history.deleted[0]  # type: ignore[no-any-return]
    if not history.added:
        return None
    mapper = state.mapper
    table: Table = mapper.local_table
    if state.identity is None:
        return None
    where = [
        column == value for column, value in zip(mapper.primary_key, state.identity, strict=True)
    ]
    return session.connection().execute(select(table.c[key]).where(*where)).scalar_one_or_none()


@event.listens_for(Session, "before_flush")
def _keep_changed_and_deleted(session: Session, flush_context: object, instances: object) -> None:
    """A name that changes, or a row that goes, through the session."""
    columns = _columns()
    rows: list[Row] = []
    for obj in session.dirty:
        fields = columns.get(type(obj))
        if not fields:
            continue
        state = inspect(obj)
        household = obj.id if isinstance(obj, models.Household) else obj.household_id
        for key, kind in fields:
            if not state.attrs[key].history.has_changes():
                continue
            old = _old_value(session, obj, key)
            if old and old != getattr(obj, key):
                rows.append((household, kind, old))
    gone: dict[Table, list[Any]] = {}
    for obj in session.deleted:
        cls = type(obj)
        table = getattr(cls, "__table__", None)
        if table is None or isinstance(obj, models.Household):
            continue  # a household goes through Delete everything: nothing is kept
        if not _reaches(table.name):
            continue
        gone.setdefault(table, []).append(obj)
    for table, objects in gone.items():
        mapper = inspect(objects[0]).mapper
        keys = [tuple(mapper.primary_key_from_instance(obj)) for obj in objects]
        if len(mapper.primary_key) == 1:
            criterion = mapper.primary_key[0].in_([k[0] for k in keys])
        else:
            criterion = tuple_(*mapper.primary_key).in_(keys)
        connection = session.connection()
        if table.name in _name_tables():
            rows.extend(_read(connection, _name_tables()[table.name], criterion))
        rows.extend(_gather(connection, table, criterion))
    if rows:
        _keep(session.connection(), rows)


@event.listens_for(Session, "do_orm_execute")
def _keep_bulk(state: ORMExecuteState) -> None:
    """A bulk `delete()` or `update()` of rows that hold a name (and of rows whose children do):
    on a model or on its bare table, with a WHERE or, for an update, a list of rows by key."""
    if not (state.is_delete or state.is_update):
        return
    statement: Any = state.statement
    table = getattr(statement, "table", None)
    if not isinstance(table, Table) or not _reaches(table.name):
        return
    cls = next(
        (
            m.class_
            for m in Base.registry.mappers
            if getattr(m.local_table, "name", None) == table.name
        ),
        None,
    )
    if cls is models.Household or table.name == models.Household.__tablename__:
        return
    session = state.session
    connection = session.connection()
    parameters = state.parameters
    setting: set[str] | None
    if isinstance(parameters, list | tuple) and parameters:
        # `execute(update(X), [{"id": 1, "name": ...}, ...])`: the rows are picked by key.
        if cls is None:
            raise RuntimeError(f"a bulk update by key on {table.name} can't keep its names")
        keys = [column.key for column in inspect(cls).primary_key]
        picked = []
        for row in parameters:
            if not all(key in row for key in keys):
                raise RuntimeError(f"a bulk update on {table.name} needs every row's key")
            picked.append(tuple(row[key] for key in keys))
        columns = list(inspect(cls).primary_key)
        criterion: ColumnElement[bool] = (
            columns[0].in_([k[0] for k in picked])
            if len(columns) == 1
            else tuple_(*columns).in_(picked)
        )
        setting = {key for row in parameters for key in row}
    else:
        criterion = statement.whereclause
        if criterion is None:
            criterion = true()
        values = getattr(statement, "_values", None) or {}
        setting = {getattr(key, "key", key) for key in values}
    rows: list[Row] = []
    fields = _columns().get(cls) if cls is not None else None
    if fields is None and table.name in _name_tables():
        fields = _columns().get(_name_tables()[table.name])
        cls = _name_tables()[table.name]
    # Only what the statement sets (a bulk update of anything else keeps no name).
    if fields and state.is_update and not any(key in setting for key, _ in fields):
        fields = None
    if fields and cls is not None:
        rows.extend(_read(connection, cls, criterion))
    if state.is_delete:
        rows.extend(_gather(connection, table, criterion))
    if rows:
        _keep(connection, rows)


def remove_expired(db: Session, now: datetime | None = None) -> int:
    """Delete the names kept longer than the log files that may hold them (plus a day). Run
    with the nightly log tidy. Returns how many went."""
    now = now or models.utcnow()
    result: Any = db.execute(delete(models.FormerName).where(models.FormerName.at < now - KEEP_FOR))
    db.commit()
    return int(result.rowcount or 0)
