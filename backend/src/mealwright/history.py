"""The change log, retries and Undo (spec section 6, "History and undo").

Every food or stock change a person makes is recorded as one `Change`: one row in Recent
changes, one Undo button. Undo reverses just that change, and later changes stay.

Food changes (names, sizes, settings, merges…) are undone with snapshots: before the
change, the affected foods are snapshotted; after it, again. Only the parts that differ
are kept. Undo puts each part back if it still looks the way the change left it; parts
someone has changed since are left alone, and the result says so ("partly").
"""

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from mealwright.api.v1.context import Kitchen
from mealwright.errors import Problem
from mealwright.household import undo_window
from mealwright.models import (
    Change,
    ChangeLine,
    ChangeMonth,
    Food,
    FoodConversion,
    FoodMerge,
    FoodName,
    FoodSize,
    FoodStandIn,
    Household,
    StockLot,
    utcnow,
)
from mealwright.names import fold

UndoResult = Literal["done", "partly", "nothing"]


def as_utc(moment: datetime) -> datetime:
    """SQLite gives times back without their zone; they're always stored in UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


# --- Retries --------------------------------------------------------------------------------


def replayed(kitchen: Kitchen) -> Change | None:
    """The change already recorded for this request's Idempotency-Key, if any."""
    if kitchen.idempotency_key is None:
        return None
    change = kitchen.db.scalar(
        select(Change).where(
            Change.household_id == kitchen.household_id,
            Change.idempotency_key == kitchen.idempotency_key,
        )
    )
    if change is not None and change.request != kitchen.request:
        raise Problem(
            status.HTTP_409_CONFLICT,
            "key_reused",
            "That change ID was already used for something else.",
        )
    return change


def commit(kitchen: Kitchen) -> Change | None:
    """Commit. If another request with the same Idempotency-Key got there first, roll back
    and return its change instead (the caller then answers as for a retry)."""
    try:
        kitchen.db.commit()
    except IntegrityError:
        kitchen.db.rollback()
        found = replayed(kitchen)
        if found is None:
            raise
        return found
    return None


# --- Recording ------------------------------------------------------------------------------


def record(
    kitchen: Kitchen,
    kind: str,
    summary: str,
    food_id: int | None = None,
    undo_data: dict[str, Any] | None = None,
) -> Change:
    change = Change(
        household_id=kitchen.household_id,
        idempotency_key=kitchen.idempotency_key,
        request=kitchen.request[:200],
        kind=kind,
        login_id=kitchen.login.id,
        login_name=kitchen.login.name,
        food_id=food_id,
        at=utcnow(),
        summary=summary[:300],
        undo_data=undo_data,
    )
    kitchen.db.add(change)
    kitchen.db.flush()
    return change


def undo_until(kitchen: Kitchen, change: Change) -> datetime:
    return as_utc(change.at) + undo_window(kitchen.household)


def can_undo(kitchen: Kitchen, change: Change) -> bool:
    return (
        change.kind != "undo"
        and change.undone_by_change_id is None
        and utcnow() < undo_until(kitchen, change)
    )


# --- Food snapshots ---------------------------------------------------------------------------

FIELDS = (
    "name",
    "counted_as",
    "staple",
    "count_word",
    "count_word_plural",
    "place_id",
    "shop_id",
    "running_low_milli",
    "merged_into_id",
)
SIZE_FIELDS = (
    "food_id",
    "name",
    "plural",
    "amount_milli",
    "usual",
    "added_when_shopping",
    "position",
)

Snapshot = dict[str, dict[str, Any]]


def snapshot(kitchen: Kitchen, food_ids: Iterable[int]) -> Snapshot:
    """Everything about these foods that a food change can touch, as plain JSON."""
    ids = sorted(set(food_ids))
    db = kitchen.db
    snap: Snapshot = {
        "fields": {},
        "names": {},
        "sizes": {},
        "stand_ins": {},
        "conversions": {},
        "lots": {},
    }
    for food in db.scalars(select(Food).where(Food.id.in_(ids))):
        # One entry per field, so undoing one field never touches another.
        snap["fields"][f"{food.id}:exists"] = True
        snap["fields"][f"{food.id}:removed"] = food.removed_at is not None
        for name in FIELDS:
            snap["fields"][f"{food.id}:{name}"] = getattr(food, name)
    for row in db.scalars(select(FoodName).where(FoodName.food_id.in_(ids))):
        snap["names"][str(row.id)] = {"food_id": row.food_id, "name": row.name}
    for size in db.scalars(select(FoodSize).where(FoodSize.food_id.in_(ids))):
        snap["sizes"][str(size.id)] = {name: getattr(size, name) for name in SIZE_FIELDS}
    for link in db.scalars(
        select(FoodStandIn).where(
            or_(FoodStandIn.food_id.in_(ids), FoodStandIn.stand_in_id.in_(ids))
        )
    ):
        snap["stand_ins"][f"{link.food_id}:{link.stand_in_id}"] = True
    for conversion in db.scalars(select(FoodConversion).where(FoodConversion.food_id.in_(ids))):
        snap["conversions"][f"{conversion.food_id}:{conversion.kind}"] = {
            "value_milli": conversion.value_milli,
            "answered_by_name": conversion.answered_by_name,
        }
    # Which food each lot belongs to (a merge moves them); amounts are stock changes.
    for lot in db.scalars(select(StockLot).where(StockLot.food_id.in_(ids))):
        snap["lots"][str(lot.id)] = {"food_id": lot.food_id, "size_id": lot.size_id}
    return snap


def diff(before: Snapshot, after: Snapshot) -> dict[str, dict[str, list[Any]]]:
    """Just the parts that changed: {collection: {key: [before, after]}} (None = absent)."""
    changed: dict[str, dict[str, list[Any]]] = {}
    for collection in before.keys() | after.keys():
        old, new = before.get(collection, {}), after.get(collection, {})
        for key in old.keys() | new.keys():
            if old.get(key) != new.get(key):
                changed.setdefault(collection, {})[key] = [old.get(key), new.get(key)]
    return changed


def foods_in(changes: dict[str, dict[str, list[Any]]]) -> set[int]:
    ids: set[int] = set()
    for collection, entries in changes.items():
        for key, (old, new) in entries.items():
            if collection in ("fields", "stand_ins", "conversions"):
                first, second = key.split(":")
                ids.add(int(first))
                if collection == "stand_ins":
                    ids.add(int(second))
            else:
                for value in (old, new):
                    if value:
                        ids.add(int(value["food_id"]))
    return ids


class FoodEdit:
    """Snapshot some foods, make a change, then record it with what changed:

    with FoodEdit(kitchen, [food.id]) as edit:
        food.staple = True
    change = edit.record("food_edited", "Turmeric is now a staple", food.id)
    """

    def __init__(self, kitchen: Kitchen, food_ids: Iterable[int]) -> None:
        self.kitchen = kitchen
        self.food_ids = set(food_ids)
        self.before: Snapshot = {}
        self.extra: dict[str, Any] = {}

    def __enter__(self) -> FoodEdit:
        self.kitchen.db.flush()
        self.before = snapshot(self.kitchen, self.food_ids)
        return self

    def __exit__(self, *_exc: object) -> None:
        return None

    def also(self, food_id: int) -> None:
        """A food that only exists once the change is made (a new or revived food)."""
        self.food_ids.add(food_id)

    def record(self, kind: str, summary: str, food_id: int | None) -> Change:
        self.kitchen.db.flush()
        after = snapshot(self.kitchen, self.food_ids)
        data: dict[str, Any] = {"foods": diff(self.before, after), **self.extra}
        return record(self.kitchen, kind, summary, food_id, data)


# --- Undo ---------------------------------------------------------------------------------------


@dataclass
class Tally:
    done: int = 0
    skipped: int = 0

    @property
    def result(self) -> UndoResult:
        if self.skipped == 0:
            return "done"
        return "partly" if self.done else "nothing"


def _name_taken(kitchen: Kitchen, name: str, food_id: int) -> bool:
    folded = fold(name)
    for other in kitchen.db.scalars(
        select(Food).where(
            Food.household_id == kitchen.household_id,
            Food.id != food_id,
            Food.removed_at.is_(None),
            Food.merged_into_id.is_(None),
        )
    ):
        if fold(other.name) == folded:
            return True
    return False


def _restore_field(kitchen: Kitchen, key: str, value: Any) -> bool:
    food_id_text, name = key.split(":")
    food = kitchen.db.get(Food, int(food_id_text))
    if food is None:
        return False
    if name == "exists":  # the food didn't exist before the change: take it away again
        food.removed_at = food.removed_at or utcnow()
        return True
    if name == "removed":
        if not value and food.merged_into_id is None and _name_taken(kitchen, food.name, food.id):
            return False
        food.removed_at = (food.removed_at or utcnow()) if value else None
        return True
    shown = food.removed_at is None
    renamed = name == "name" and shown and food.merged_into_id is None
    if renamed and _name_taken(kitchen, value, food.id):
        return False
    revived = name == "merged_into_id" and value is None and shown
    if revived and _name_taken(kitchen, food.name, food.id):
        return False
    setattr(food, name, value)
    return True


def _restore_name(kitchen: Kitchen, key: str, value: dict[str, Any] | None) -> bool:
    db = kitchen.db
    row = db.get(FoodName, int(key))
    if value is None:
        if row is not None:
            db.delete(row)
        return True
    folded = fold(value["name"])
    clash = any(
        fold(other.name) == folded and other.id != int(key)
        for other in db.scalars(select(FoodName).where(FoodName.food_id == value["food_id"]))
    )
    if clash:
        return False
    if row is None:
        db.add(
            FoodName(
                id=int(key),
                household_id=kitchen.household_id,
                food_id=value["food_id"],
                name=value["name"],
            )
        )
    else:
        row.food_id, row.name = value["food_id"], value["name"]
    return True


def _restore_size(kitchen: Kitchen, key: str, value: dict[str, Any] | None) -> bool:
    db = kitchen.db
    size = db.get(FoodSize, int(key))
    if value is None:
        if size is not None:
            db.delete(size)
        return True
    if size is None:
        size = FoodSize(id=int(key), household_id=kitchen.household_id)
        db.add(size)
    for name in SIZE_FIELDS:
        setattr(size, name, value[name])
    return True


def _restore_stand_in(kitchen: Kitchen, key: str, present: bool | None) -> bool:
    food_id, stand_in_id = (int(part) for part in key.split(":"))
    db = kitchen.db
    link = db.get(FoodStandIn, (food_id, stand_in_id))
    if not present:
        if link is not None:
            db.delete(link)
        return True
    if link is None:
        db.add(
            FoodStandIn(household_id=kitchen.household_id, food_id=food_id, stand_in_id=stand_in_id)
        )
    return True


def _restore_conversion(kitchen: Kitchen, key: str, value: dict[str, Any] | None) -> bool:
    food_id_text, kind = key.split(":")
    db = kitchen.db
    row = db.scalar(
        select(FoodConversion).where(
            FoodConversion.food_id == int(food_id_text), FoodConversion.kind == kind
        )
    )
    if value is None:
        if row is not None:
            db.delete(row)
        return True
    if row is None:
        row = FoodConversion(
            household_id=kitchen.household_id, food_id=int(food_id_text), kind=kind
        )
        db.add(row)
    row.value_milli = value["value_milli"]
    row.answered_by_name = value["answered_by_name"]
    return True


def _restore_lot(kitchen: Kitchen, key: str, value: dict[str, Any] | None) -> bool:
    lot = kitchen.db.get(StockLot, int(key))
    if lot is None or value is None:
        return value is None
    lot.food_id, lot.size_id = value["food_id"], value["size_id"]
    return True


_RESTORE: dict[str, Callable[[Kitchen, str, Any], bool]] = {
    "names": _restore_name,
    "sizes": _restore_size,
    "stand_ins": _restore_stand_in,
    "conversions": _restore_conversion,
    "lots": _restore_lot,
}


def fix_usual_sizes(kitchen: Kitchen, food_ids: Iterable[int]) -> None:
    """Exactly one Usual size for each food that has sizes."""
    db = kitchen.db
    db.flush()
    for food_id in set(food_ids):
        sizes = list(
            db.scalars(
                select(FoodSize)
                .where(FoodSize.food_id == food_id)
                .order_by(FoodSize.position, FoodSize.id)
            )
        )
        usual = [size for size in sizes if size.usual]
        if sizes and len(usual) != 1:
            keep = usual[0] if usual else sizes[0]
            for size in sizes:
                size.usual = size is keep


def undo_foods(
    kitchen: Kitchen, changes: dict[str, dict[str, list[Any]]], tally: Tally
) -> set[int]:
    """Put back each changed part that still looks the way the change left it."""
    ids = foods_in(changes)
    current = snapshot(kitchen, ids)
    fields = changes.get("fields", {})
    # Foods the change created: taking them away again is all there is to do.
    created = {
        key.split(":")[0]
        for key, (old, _new) in fields.items()
        if key.endswith(":exists") and old is None
    }
    # Foods first (a restored name or size may belong to a food that comes back).
    for collection in ("fields", "names", "sizes", "stand_ins", "conversions", "lots"):
        for key, (old, new) in sorted(changes.get(collection, {}).items()):
            if (
                collection == "fields"
                and key.split(":")[0] in created
                and not key.endswith(":exists")
            ):
                continue
            now = current.get(collection, {}).get(key)
            if now == old:
                continue  # already back the way it was
            if now != new:
                tally.skipped += 1
                continue
            if collection == "fields":
                ok = _restore_field(kitchen, key, old)
            else:
                ok = _RESTORE[collection](kitchen, key, old)
            if ok:
                tally.done += 1
            else:
                tally.skipped += 1
            kitchen.db.flush()
    fix_usual_sizes(kitchen, ids)
    return ids


def undo_lot_amounts(kitchen: Kitchen, amounts: dict[str, list[Any]]) -> None:
    """Lots whose amounts were converted (a merge, or a food counted a new way) are
    converted back, in proportion, once their food is counted the old way again. Whatever
    was used since stays used."""
    for key, (before, after, counted_as) in amounts.items():
        lot = kitchen.db.get(StockLot, int(key))
        food = kitchen.db.get(Food, lot.food_id) if lot is not None else None
        if lot is None or food is None or food.counted_as != counted_as:
            continue
        if after and before != after:
            lot.amount_milli = max(0, round(lot.amount_milli * before / after))


@dataclass
class Shortfall:
    food_id: int
    wanted: int
    applied: int


def undo_lines(kitchen: Kitchen, change: Change, tally: Tally) -> list[Shortfall]:
    """Reverse each stock line: the opposite of its amount difference (never below zero),
    and its place and use-by if nobody has changed them since."""
    short: list[Shortfall] = []
    now = utcnow()
    for line in kitchen.db.scalars(
        select(ChangeLine).where(ChangeLine.change_id == change.id).order_by(ChangeLine.id)
    ):
        lot = kitchen.db.get(StockLot, line.lot_id) if line.lot_id is not None else None
        if lot is None:
            tally.skipped += 1
            continue
        new_lot = line.place_before_id is None
        difference = line.amount_before_milli - line.amount_after_milli
        if difference:
            target = lot.amount_milli + difference
            if target < 0:
                if lot.amount_milli:
                    tally.done += 1
                tally.skipped += 1
                short.append(Shortfall(lot.food_id, -difference, lot.amount_milli))
                lot.amount_milli = 0
            else:
                lot.amount_milli = target
                tally.done += 1
        if not new_lot and line.place_before_id != line.place_after_id:
            if lot.place_id == line.place_after_id:
                lot.place_id = line.place_before_id  # type: ignore[assignment]
                if change.kind == "to_freezer":
                    lot.frozen_on = None
                tally.done += 1
            else:
                tally.skipped += 1
        if not new_lot and line.use_by_before != line.use_by_after:
            if lot.use_by == line.use_by_after:
                lot.use_by = line.use_by_before
                tally.done += 1
            else:
                tally.skipped += 1
        if lot.amount_milli > 0:
            lot.emptied_at = None
        else:
            lot.emptied_at = lot.emptied_at or now
    return short


def undo_merge_record(kitchen: Kitchen, data: dict[str, Any]) -> None:
    """A merge's history row goes when the merge is undone; a split's mark is cleared."""
    if "merge_id" in data:
        kitchen.db.execute(delete(FoodMerge).where(FoodMerge.id == data["merge_id"]))
    if "split_merge_id" in data:
        merge = kitchen.db.get(FoodMerge, data["split_merge_id"])
        if merge is not None:
            merge.split_at = None


UNDO_MESSAGES: dict[UndoResult, str] = {
    "done": "Undone.",
    "partly": "Put back what could be: some of it has changed again since.",
    "nothing": "Nothing to put back: it has all changed again since.",
}


def too_old() -> Problem:
    return Problem(
        status.HTTP_410_GONE,
        "too_old",
        "That's too long ago to undo.",
    )


def already_undone() -> Problem:
    return Problem(status.HTTP_409_CONFLICT, "already_undone", "That's already been undone.")


# --- Thinning (a daily job) -------------------------------------------------------------------


def month_cutoff(household: Household, now: datetime) -> datetime:
    """Changes before this moment are thinned: `history_months` ago (12 by default)."""
    months = household.history_months
    year, month = divmod(now.year * 12 + now.month - 1 - months, 12)
    day = min(now.day, 28)
    return now.replace(year=year, month=month + 1, day=day)


THIN_CHUNK = 1_000  # changes per transaction, so writers are never kept waiting long


def thin(db: DbSession, household: Household, now: datetime | None = None) -> int:
    """Turn changes older than the history length into monthly totals, and drop empty lots
    once they can no longer be undone. Returns how many changes were thinned. Safe to run
    more than once, and to stop half way: it works in chunks of THIN_CHUNK changes, each
    its own short transaction, with a handful of queries per chunk."""
    from mealwright.household import zone

    now = now or utcnow()
    cutoff = month_cutoff(household, now)
    local = zone(household)
    thinned = 0
    while True:
        chunk = db.execute(
            select(Change.id, Change.at, Change.kind, Change.undo_data, Change.undoes_change_id)
            .where(Change.household_id == household.id, Change.at < cutoff)
            .order_by(Change.id)
            .limit(THIN_CHUNK)
        ).all()
        if not chunk:
            break
        ids = [row.id for row in chunk]
        # An Undo is totalled with the change it undid: the same kind and the same month
        # (in the household's time zone), as the opposite amount. A full Undo also takes
        # that change back out of the count; a partial one leaves it counted. So "added
        # 500 g, then undone" leaves nothing, and there's never a separate undo row.
        month_of: dict[int, str] = {}
        kind_of: dict[int, str] = {}
        step_of: dict[int, int] = {}
        undone_ids = [item.undoes_change_id for item in chunk if item.undoes_change_id]
        undone_at = {
            change_id: as_utc(at)
            for change_id, at in db.execute(
                select(Change.id, Change.at).where(Change.id.in_(undone_ids))
            )
        }
        for item in chunk:
            data = item.undo_data or {}
            at = as_utc(item.at)
            if item.kind == "undo":
                if item.undoes_change_id in undone_at:  # the undone change is still here
                    at = undone_at[item.undoes_change_id]
                elif data.get("undoes_at"):  # already thinned: its time was kept
                    at = as_utc(datetime.fromisoformat(data["undoes_at"]))
                kind_of[item.id] = data.get("undoes_kind", "undo")
                step_of[item.id] = -1 if data.get("result") == "done" else 0
            else:
                kind_of[item.id] = item.kind
                step_of[item.id] = 1
            month_of[item.id] = at.astimezone(local).strftime("%Y-%m")

        # Each change's total per food, added up by the database.
        totals: dict[tuple[str, int, str], list[int]] = {}
        for change_id, food_id, amount in db.execute(
            select(
                ChangeLine.change_id,
                ChangeLine.food_id,
                func.sum(ChangeLine.amount_after_milli - ChangeLine.amount_before_milli),
            )
            .where(ChangeLine.change_id.in_(ids))
            .group_by(ChangeLine.change_id, ChangeLine.food_id)
        ):
            key = (month_of[change_id], food_id, kind_of[change_id])
            entry = totals.setdefault(key, [0, 0])
            entry[0] += int(amount or 0)
            entry[1] += step_of[change_id]

        if totals:
            existing = {
                (row.month, row.food_id, row.kind): row
                for row in db.scalars(
                    select(ChangeMonth).where(
                        ChangeMonth.household_id == household.id,
                        ChangeMonth.month.in_({key[0] for key in totals}),
                    )
                )
            }
            for (month, food_id, kind), (amount, changes) in totals.items():
                row = existing.get((month, food_id, kind))
                if row is None:
                    if amount == 0 and changes <= 0:
                        continue  # nothing to show (an undone move, say)
                    db.add(
                        ChangeMonth(
                            household_id=household.id,
                            month=month,
                            food_id=food_id,
                            kind=kind,
                            amount_milli=amount,
                            changes=max(0, changes),
                        )
                    )
                else:
                    row.amount_milli += amount
                    row.changes = max(0, row.changes + changes)
                    if row.amount_milli == 0 and row.changes == 0:
                        db.delete(row)  # all of it was undone

        # Newer changes that point at these (an Undo of an old change) let go first.
        db.execute(
            update(Change)
            .where(Change.undone_by_change_id.in_(ids))
            .values(undone_by_change_id=None)
        )
        db.execute(
            update(Change).where(Change.undoes_change_id.in_(ids)).values(undoes_change_id=None)
        )
        db.execute(delete(ChangeLine).where(ChangeLine.change_id.in_(ids)))
        db.execute(delete(Change).where(Change.id.in_(ids)))
        db.commit()
        thinned += len(ids)

    gone_before = now - undo_window(household)
    db.execute(
        delete(StockLot).where(
            StockLot.household_id == household.id,
            StockLot.amount_milli == 0,
            StockLot.emptied_at < gone_before,
        )
    )
    db.commit()
    return thinned
