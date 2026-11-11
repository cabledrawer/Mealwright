"""The change log, retries and Undo (spec section 6, "History and undo").

Every food or stock change a person makes is recorded as one `Change`: one row in Recent
changes, one Undo button. Undo reverses just that change, and later changes stay.

Food changes (names, sizes, settings, merges…) are undone with snapshots: before the
change, the affected foods are snapshotted; after it, again. Only the parts that differ
are kept. Undo puts each part back if it still looks the way the change left it; parts
someone has changed since are left alone, and the result says so ("partly").
"""

import logging
import uuid
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Literal

from fastapi import status
from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from mealwright import events, restock
from mealwright.api.v1.context import Kitchen
from mealwright.errors import Problem
from mealwright.household import undo_window
from mealwright.models import (
    Change,
    ChangeLine,
    ChangeMonth,
    DoubleTick,
    Food,
    FoodConversion,
    FoodMerge,
    FoodName,
    FoodNotSame,
    FoodSize,
    FoodStandIn,
    Household,
    ListItem,
    ListNote,
    ListTick,
    MealItem,
    Place,
    Recipe,
    RecipeLine,
    Shop,
    ShoppingList,
    StockLot,
    SyncAction,
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
    if change is None:
        # Action IDs and Idempotency-Keys share one uniqueness (sync protocol 5.7): a key
        # that is already a shopping action's ID was used for something else.
        action = kitchen.db.get(SyncAction, (kitchen.household_id, kitchen.idempotency_key))
        if action is not None:
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
    key = kitchen.idempotency_key
    if kitchen.key_once:
        kitchen.idempotency_key = None
    change = Change(
        household_id=kitchen.household_id,
        idempotency_key=key,
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


# Changes that only remember a request's Idempotency-Key (a recipe made or saved, a draft
# kept): there is nothing to undo, and they are not listed in Recent changes.
KEY_ONLY_KINDS = ("recipe_created", "recipe_saved", "draft_saved", "setting_kept")

# Changes that are only there to be read in Recent changes, with no Undo of their own: a
# removed ingredient that came back ("Lemon is back in Ingredients").
NOTE_KINDS = ("food_back",)


# Changes only the household's admin can undo, as only an admin can make them (meal slots, the
# Batch cook switch and the pint).
ADMIN_ONLY_KINDS = ("plan_slot", "batch_cook_switch", "pints_changed")


def can_undo(kitchen: Kitchen, change: Change) -> bool:
    return (
        (change.kind not in ADMIN_ONLY_KINDS or kitchen.login.role == "admin")
        and change.kind != "undo"
        and change.kind not in KEY_ONLY_KINDS
        and change.kind not in NOTE_KINDS
        and change.undone_by_change_id is None
        and utcnow() < undo_until(kitchen, change)
        and (change.kind != "food_removed" or removal_stands(kitchen, change))
    )


def removal_stands(kitchen: Kitchen, change: Change) -> bool:
    """A "Removed Lemon from Ingredients" keeps its Undo only while Lemon is still removed,
    and only the newest removal of it: once Lemon is back (an Undo that put stock back into
    it, or an offline add) that removal no longer stands. Worked out when it is read."""
    food = kitchen.db.get(Food, change.food_id) if change.food_id is not None else None
    if food is None or food.household_id != kitchen.household_id or food.removed_at is None:
        return False
    newer = kitchen.db.scalar(
        select(Change.id).where(
            Change.household_id == kitchen.household_id,
            Change.kind == "food_removed",
            Change.food_id == food.id,
            Change.id > change.id,
        )
    )
    return newer is None


def record_back(kitchen: Kitchen, food: Food) -> Change:
    """A removed ingredient came back by a way other than undoing its removal (an Undo that
    put stock back into it, or an offline add): Ingredients' Recent changes says so. It has
    no Undo, and never takes the request's Idempotency-Key, which belongs to the change that
    brought it back."""
    change = Change(
        household_id=kitchen.household_id,
        idempotency_key=None,
        request=kitchen.request[:200],
        kind="food_back",
        login_id=kitchen.login.id,
        login_name=kitchen.login.name,
        food_id=food.id,
        at=utcnow(),
        summary=f"{food.name} is back in Ingredients"[:300],
        undo_data=None,
    )
    kitchen.db.add(change)
    kitchen.db.flush()
    return change


def back_undone(kitchen: Kitchen, foods: dict[str, Any], undo_id: int) -> None:
    """An Undo removed again an ingredient the undone change had brought back (`foods` is
    that change's food snapshot): its "Lemon is back in Ingredients" line shows as undone,
    the same way any other undone line looks (cabledrawer 21 Oct)."""
    for key, (old, new) in foods.get("fields", {}).items():
        if not (key.endswith(":removed") and old is True and new is False):
            continue
        food = kitchen.db.get(Food, int(key.split(":")[0]))
        if food is None or food.household_id != kitchen.household_id or food.removed_at is None:
            continue  # still in Ingredients (it has stock or is on a list): the line stands
        back = kitchen.db.scalar(
            select(Change)
            .where(
                Change.household_id == kitchen.household_id,
                Change.kind == "food_back",
                Change.food_id == food.id,
                Change.undone_by_change_id.is_(None),
            )
            .order_by(Change.id.desc())
            .limit(1)
        )
        if back is not None:
            back.undone_by_change_id = undo_id


# --- Recipes changed behind the editor's back ---------------------------------------------------


def bump_recipes(
    db: DbSession, household_id: int, recipe_ids: Iterable[int], login_id: int | None, name: str
) -> None:
    """A merge, a removal, a delete or an Undo changed some recipes' links without anyone
    editing them: each gets the next version, and is marked as changed by whoever did it, so
    an editor that was open on one is stopped ("Wren changed this recipe after you opened
    it") instead of saving the old links back."""
    ids = set(recipe_ids)
    if ids:
        db.execute(
            update(Recipe)
            .where(Recipe.household_id == household_id, Recipe.id.in_(ids))
            .values(
                version=Recipe.version + 1,
                updated_at=utcnow(),
                updated_by_login_id=login_id,
                updated_by_name=name,
            )
        )


def bump_recipes_by(kitchen: Kitchen, recipe_ids: Iterable[int]) -> None:
    bump_recipes(kitchen.db, kitchen.household_id, recipe_ids, kitchen.login.id, kitchen.login.name)


# --- Food snapshots ---------------------------------------------------------------------------

FIELDS = (
    "name",
    "counted_as",
    "staple",
    "count_word",
    "count_word_plural",
    "place_id",
    "shop_id",
    "aisle",
    "running_low_milli",
    "merged_into_id",
    "restocked_at",  # kept as text in the snapshot (0.7 K1: a merge can move it on)
    "restock_typed_at",  # the moment it was typed, as text too (0.7 K5, cabledrawer 2 Nov)
    "date_kind",
)
RESTOCK_FIELDS = ("restocked_at", "restock_typed_at")
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
        "recipe_lines": {},
        "recipe_homes": {},
        "meal_items": {},
    }
    for food in db.scalars(select(Food).where(Food.id.in_(ids))):
        # One entry per field, so undoing one field never touches another.
        snap["fields"][f"{food.id}:exists"] = True
        snap["fields"][f"{food.id}:removed"] = food.removed_at is not None
        for name in FIELDS:
            value = getattr(food, name)
            if isinstance(value, datetime):
                value = as_utc(value).isoformat()
            snap["fields"][f"{food.id}:{name}"] = value
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
    # The recipe lines that use these foods (a merge moves them, removing a food unlinks
    # them; a line that has lost its food is no longer found here, so it shows as gone), and
    # the recipes whose own pantry ingredient this is.
    for line in db.scalars(select(RecipeLine).where(RecipeLine.food_id.in_(ids))):
        snap["recipe_lines"][str(line.id)] = {"food_id": line.food_id, "size_id": line.size_id}
    for recipe in db.scalars(select(Recipe).where(Recipe.homemade_food_id.in_(ids))):
        snap["recipe_homes"][str(recipe.id)] = {"food_id": recipe.homemade_food_id}
    # Plain ingredients in planned meals (a merge moves them).
    for item in db.scalars(select(MealItem).where(MealItem.food_id.in_(ids))):
        snap["meal_items"][str(item.id)] = {"food_id": item.food_id}
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

    def __init__(self, kitchen: Kitchen, food_ids: Iterable[int], batch: Any = None) -> None:
        self.kitchen = kitchen
        self.food_ids = set(food_ids)
        self.before: Snapshot = {}
        self.extra: dict[str, Any] = {}
        self.batch: Any = batch
        self.own = batch is None  # its own lock and number, or part of a list action's
        # The sync-log row for an edit that lists show (sync protocol 5.8).
        self.sync_kind: str | None = None
        self.sync_payload: dict[str, Any] | None = None

    def __enter__(self) -> FoodEdit:
        # The household's lock and counter come first (sync protocol 5.2), so what the
        # change touches gets the next number (3.7). Imported here: shopping needs history.
        from mealwright.shopping import Batch

        self.kitchen.db.flush()
        if self.batch is None:
            self.batch = Batch(self.kitchen)
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
        changes = diff(self.before, after)
        data: dict[str, Any] = {"foods": changes, **self.extra}
        from mealwright.shopping import bump_foods, server_action

        touched = foods_in(changes)
        bump_foods(self.kitchen, touched, self.batch)
        logs = self.own and bool(self.batch.taken)
        if logs:
            data["action"] = self.batch.action
        change = record(self.kitchen, kind, summary, food_id, data)
        if logs:
            server_action(
                self.batch,
                self.sync_kind or "food_edit",
                self.sync_payload or {"food_ids": sorted(touched)},
                change,
            )
        if self.own:
            self.batch.finish()
        return change


# --- Undo ---------------------------------------------------------------------------------------


@dataclass
class Tally:
    done: int = 0
    skipped: int = 0
    # Something was left alone because the shopping line it joined has been bought since.
    joined_bought: bool = False
    # Why something was left alone, when the generic words need adding to (proposed, for cabledrawer).
    sentence: str | None = None
    # The whole answer, when the generic words don't fit (an Undo that left ingredients in use).
    message: str | None = None
    # Ingredients an import's Undo left in place because another recipe (or the plan, the list,
    # the pantry) uses them now (RF4 I2): their names, and whether a recipe is what uses them.
    stays: list[str] = field(default_factory=list)
    stays_for_recipe: bool = True

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


def _mine_food(kitchen: Kitchen, food_id: int | None) -> Food | None:
    """An ingredient of this household, else None. An Undo record is the household's own, but
    every restore step checks for itself, as `_restore_recipe_line` does."""
    if food_id is None:
        return None
    food = kitchen.db.get(Food, food_id)
    return food if food is not None and food.household_id == kitchen.household_id else None


def _restore_field(kitchen: Kitchen, key: str, value: Any) -> bool:
    food_id_text, name = key.split(":")
    food = _mine_food(kitchen, int(food_id_text))
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
    if name in RESTOCK_FIELDS and value is not None:
        value = datetime.fromisoformat(value)
    if name in ("place_id", "shop_id") and value is not None:
        # A place or shop id from the record may be gone, or (ids once were reused) another
        # household's: it goes back as none, never as someone else's.
        row: Place | Shop | None = (
            kitchen.db.get(Place, value) if name == "place_id" else kitchen.db.get(Shop, value)
        )
        if row is None or row.household_id != kitchen.household_id:
            value = None
    setattr(food, name, value)
    return True


def _restore_name(kitchen: Kitchen, key: str, value: dict[str, Any] | None) -> bool:
    db = kitchen.db
    row = db.get(FoodName, int(key))
    if row is not None and row.household_id != kitchen.household_id:
        return False
    if value is None:
        if row is not None:
            db.delete(row)
        return True
    if _mine_food(kitchen, value["food_id"]) is None:
        return False
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
    if size is not None and size.household_id != kitchen.household_id:
        return False
    if value is None:
        if size is not None:
            db.delete(size)
        return True
    if "food_id" in value and _mine_food(kitchen, value["food_id"]) is None:
        return False
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
    if link is not None and link.household_id != kitchen.household_id:
        return False
    if present and (
        _mine_food(kitchen, food_id) is None or _mine_food(kitchen, stand_in_id) is None
    ):
        return False
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
    if _mine_food(kitchen, int(food_id_text)) is None:
        return False
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
    if lot is not None and lot.household_id != kitchen.household_id:
        return False
    if lot is None or value is None:
        return value is None
    food = _mine_food(kitchen, value["food_id"])
    size = kitchen.db.get(FoodSize, value["size_id"]) if value["size_id"] else None
    if food is None or (size is not None and size.household_id != kitchen.household_id):
        return False
    lot.food_id, lot.size_id = value["food_id"], value["size_id"]
    return True


def _line_as_left(kitchen: Kitchen, key: str, new: dict[str, Any] | None) -> bool:
    """Is this recipe line still the way the change left it? Moved to the other ingredient
    (a merge), or unlinked (an ingredient removed) and not linked to anything else since.
    A line taken out of its recipe meanwhile is gone, so it can't be put back."""
    line = kitchen.db.get(RecipeLine, int(key))
    if line is None or line.household_id != kitchen.household_id:
        return False
    return line.food_id is None if new is None else line.food_id == new["food_id"]


def _restore_recipe_line(kitchen: Kitchen, key: str, value: dict[str, Any] | None) -> bool:
    """Put a recipe line back on its ingredient (and its size, if that still belongs to it)."""
    line = kitchen.db.get(RecipeLine, int(key))
    if line is None or line.household_id != kitchen.household_id or value is None:
        return value is None
    line.food_id = value["food_id"]
    size = kitchen.db.get(FoodSize, value["size_id"]) if value["size_id"] else None
    line.size_id = size.id if size is not None and size.food_id == value["food_id"] else None
    bump_recipes_by(kitchen, [line.recipe_id])
    return True


def _restore_recipe_home(kitchen: Kitchen, key: str, value: dict[str, Any] | None) -> bool:
    recipe = kitchen.db.get(Recipe, int(key))
    if recipe is None or recipe.household_id != kitchen.household_id or value is None:
        return value is None
    recipe.homemade_food_id = value["food_id"]
    bump_recipes_by(kitchen, [recipe.id])
    return True


def _restore_meal_item(kitchen: Kitchen, key: str, value: dict[str, Any] | None) -> bool:
    item = kitchen.db.get(MealItem, int(key))
    if item is None or item.household_id != kitchen.household_id or value is None:
        return value is None
    if _mine_food(kitchen, value["food_id"]) is None:
        return False
    item.food_id = value["food_id"]
    return True


_RESTORE: dict[str, Callable[[Kitchen, str, Any], bool]] = {
    "names": _restore_name,
    "sizes": _restore_size,
    "stand_ins": _restore_stand_in,
    "conversions": _restore_conversion,
    "lots": _restore_lot,
    "recipe_lines": _restore_recipe_line,
    "recipe_homes": _restore_recipe_home,
    "meal_items": _restore_meal_item,
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


def _food_of(collection: str, key: str, old: Any, new: Any) -> int | None:
    """The food one entry of a food change belongs to."""
    if collection == "fields":
        return int(key.split(":")[0])
    for value in (new, old):
        if isinstance(value, dict) and value.get("food_id") is not None:
            return int(value["food_id"])
    return None


def undo_foods(
    kitchen: Kitchen,
    changes: dict[str, dict[str, list[Any]]],
    tally: Tally,
    keep: frozenset[int] = frozenset(),
) -> set[int]:
    """Put back each changed part that still looks the way the change left it. Nothing of the
    foods in `keep` is touched (ingredients in use, when an Undo takes out new ones)."""
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
    for collection in (
        "fields",
        "names",
        "sizes",
        "stand_ins",
        "conversions",
        "lots",
        "recipe_lines",
        "recipe_homes",
        "meal_items",
    ):
        for key, (old, new) in sorted(changes.get(collection, {}).items()):
            if keep and _food_of(collection, key, old, new) in keep:
                continue
            if (
                collection == "fields"
                and key.split(":")[0] in created
                and not key.endswith(":exists")
            ):
                continue
            now = current.get(collection, {}).get(key)
            if now == old:
                continue  # already back the way it was
            restock_field = key.split(":")[-1] in RESTOCK_FIELDS
            if collection == "fields" and restock_field and now != new:
                # Raised since (a restock kept by the tidy-up): it still goes back to the date
                # before the merge, and isn't counted as something left alone (0.7 K1). The
                # typed moment goes back with it (0.7 K5).
                _restore_field(kitchen, key, old)
                kitchen.db.flush()
                continue
            if now != new or (
                collection == "recipe_lines" and not _line_as_left(kitchen, key, new)
            ):
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


def undo_message(result: UndoResult, thing: str | None = None, name_partly: bool = False) -> str:
    """What an Undo says. When it did nothing it names the thing: "Nothing to put back for
    Banana bread (Mon breakfast): it has changed again since." (F44; proposed, for cabledrawer).
    A plan change also names the meal when only some of it was put back (F140, `name_partly`)."""
    if result == "nothing" and thing:
        return f"Nothing to put back for {thing}: it has changed again since."
    if name_partly and result == "partly" and thing:
        return f"Put back what could be for {thing}: some of it has changed again since."
    return UNDO_MESSAGES[result]


# What an Undo says when a line was left joined because the line it joined was bought since
# (proposed, for cabledrawer).
JOINED_BOUGHT_MESSAGES: dict[UndoResult, str] = {
    "partly": "Put back what could be: the line it joined has been bought, so that part stays.",
    "nothing": "Nothing to put back: the line it joined has been bought, so it stays as it is.",
}


def too_old() -> Problem:
    return Problem(
        status.HTTP_410_GONE,
        "too_old",
        "That’s too long ago to undo.",
    )


def already_undone() -> Problem:
    return Problem(status.HTTP_409_CONFLICT, "already_undone", "That’s already been undone.")


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


# --- Removed ingredients (a scheduled job) ------------------------------------------------------

# A little past the undo window, so a removal can't vanish while its Undo is still offered.
PURGE_MARGIN = timedelta(hours=1)


def purge_removed(db: DbSession, household: Household, now: datetime | None = None) -> int:
    """Delete ingredients removed longer ago than the undo window, entirely (spec section
    6: "Remove from Ingredients" deletes that food's record). Returns how many went.

    - Its own records go: other names, sizes, "can use instead" links both ways, ask-once
      answers, "not the same" pairs, emptied packets, and its per-packet history lines
      and monthly totals.
    - Ingredients merged into it go too: they only existed so old links would lead to it.
      Their merge history goes with them.
    - The history stays readable: every change keeps its sentence ("Used 200 g Toor dal",
      "Removed Toor dal from Ingredients") and who did it; only its link to the
      ingredient is cleared. Changes to other ingredients are untouched.
    - Planned meals keep its name (cabledrawer 26 Oct), so past meals still show what was eaten.
    """
    from mealwright.shopping import lock_db, on_a_list

    now = now or utcnow()
    cutoff = now - undo_window(household) - PURGE_MARGIN
    # The household's lock first (sync protocol 5.2): an Undo or a phone's queue can't
    # bring one of these back half way through, and the purge takes a counter number.
    lock_db(db, household)
    removed = set(
        db.scalars(
            select(Food.id).where(
                Food.household_id == household.id,
                Food.removed_at.is_not(None),
                Food.removed_at < cutoff,
            )
        )
    )
    if not removed:
        db.commit()
        return 0
    # Safety net: never delete stock. A removed ingredient that holds some again (an Undo
    # that put stock back should already have brought it back) is brought back instead.
    stocked = set(
        db.scalars(
            select(StockLot.food_id).where(
                StockLot.food_id.in_(list(removed)), StockLot.amount_milli > 0
            )
        )
    )
    if stocked:
        db.execute(update(Food).where(Food.id.in_(list(stocked))).values(removed_at=None))
        logging.getLogger(__name__).warning(
            "Brought back %d removed ingredient(s) that still had stock, instead of deleting them",
            len(stocked),
        )
        removed -= stocked
        if not removed:
            db.commit()
            return 0
    # Likewise never delete a live list item: an ingredient that is somehow on a list is
    # brought back instead (a merge repoints items, so this shouldn't happen).
    listed = {
        food_id
        for food_id in removed
        if on_a_list(db, household.id, food_id, now - undo_window(household))
    }
    if listed:
        db.execute(update(Food).where(Food.id.in_(list(listed))).values(removed_at=None))
        logging.getLogger(__name__).warning(
            "Brought back %d removed ingredient(s) that were still on a list, "
            "instead of deleting them",
            len(listed),
        )
        removed -= listed
        if not removed:
            db.commit()
            return 0
    gone = set(removed)
    frontier = set(removed)
    while frontier:
        merged_in = set(
            db.scalars(
                select(Food.id).where(
                    Food.household_id == household.id, Food.merged_into_id.in_(frontier)
                )
            )
        )
        frontier = merged_in - gone
        gone |= frontier

    ids = sorted(gone)
    _purge_action(db, household, ids)
    db.execute(update(Change).where(Change.food_id.in_(ids)).values(food_id=None))
    db.execute(delete(ChangeLine).where(ChangeLine.food_id.in_(ids)))
    db.execute(delete(ChangeMonth).where(ChangeMonth.food_id.in_(ids)))
    db.execute(delete(StockLot).where(StockLot.food_id.in_(ids)))
    db.execute(
        delete(FoodNotSame).where(
            or_(FoodNotSame.food_a_id.in_(ids), FoodNotSame.food_b_id.in_(ids))
        )
    )
    db.execute(
        delete(FoodStandIn).where(
            or_(FoodStandIn.food_id.in_(ids), FoodStandIn.stand_in_id.in_(ids))
        )
    )
    db.execute(delete(FoodConversion).where(FoodConversion.food_id.in_(ids)))
    behind = set(db.scalars(select(RecipeLine.recipe_id).where(RecipeLine.food_id.in_(ids))))
    behind |= set(db.scalars(select(Recipe.id).where(Recipe.homemade_food_id.in_(ids))))
    bump_recipes(db, household.id, behind, None, "Mealwright")
    db.execute(update(RecipeLine).where(RecipeLine.food_id.in_(ids)).values(food_id=None))
    # Planned meals keep the ingredient's name as it is now (cabledrawer 26 Oct).
    db.execute(
        update(MealItem)
        .where(MealItem.food_id.in_(ids), MealItem.household_id == household.id)
        .values(
            name=select(Food.name).where(Food.id == MealItem.food_id).scalar_subquery(),
            food_id=None,
        )
    )
    # A link from another household's meal was never valid: it goes, and takes no name with it.
    db.execute(delete(MealItem).where(MealItem.food_id.in_(ids)))
    events.note_plan(db, household.id)  # planned meals keep the ingredient's name only now
    db.execute(
        update(RecipeLine)
        .where(RecipeLine.size_id.in_(select(FoodSize.id).where(FoodSize.food_id.in_(ids))))
        .values(size_id=None)
    )
    db.execute(update(Recipe).where(Recipe.homemade_food_id.in_(ids)).values(homemade_food_id=None))
    db.execute(delete(FoodSize).where(FoodSize.food_id.in_(ids)))
    db.execute(delete(FoodName).where(FoodName.food_id.in_(ids)))
    db.execute(
        delete(FoodMerge).where(
            or_(FoodMerge.from_food_id.in_(ids), FoodMerge.into_food_id.in_(ids))
        )
    )
    # Shopping lists: items for these ingredients go with their purchases. They are
    # tombstones, or on a list removed longer ago than the undo window: removal is blocked
    # while an ingredient is on a live list (a merge moves its items to the kept
    # ingredient), and the safety net above brings back any that somehow still is. A
    # purchase's changes lose the
    # link first (sync protocol 3.7, 3.9).
    item_ids = select(ListItem.id).where(ListItem.food_id.in_(ids))
    tick_ids = select(ListTick.id).where(
        ListTick.household_id == household.id, ListTick.item_id.in_(item_ids)
    )
    db.execute(
        update(Change)
        .where(Change.household_id == household.id, Change.tick_id.in_(tick_ids))
        .values(tick_id=None)
    )
    db.execute(
        delete(ListTick).where(
            ListTick.household_id == household.id, ListTick.item_id.in_(item_ids)
        )
    )
    db.execute(delete(ListItem).where(ListItem.food_id.in_(ids)))
    db.execute(update(Food).where(Food.id.in_(ids)).values(merged_into_id=None))
    db.execute(delete(Food).where(Food.id.in_(ids)))
    db.commit()
    return len(ids)


def _purge_action(db: DbSession, household: Household, ids: list[int]) -> None:
    """The server-made `purge` action (sync protocol 3.9): it takes the next counter number
    N and sets `list_purged_seq = N`, so every phone that's behind gets a fresh full copy
    (`reset`) instead of keeping an ingredient that no longer exists. Under the lock."""
    from mealwright.shopping import payload_hash

    names = {
        row.id: row.name for row in db.execute(select(Food.id, Food.name).where(Food.id.in_(ids)))
    }
    payload: dict[str, Any] = {"foods": {str(food_id): names[food_id] for food_id in ids}}
    seq = household.list_seq + 1
    household.list_seq = seq
    household.list_purged_seq = seq
    db.add(
        SyncAction(
            household_id=household.id,
            id=str(uuid.uuid4()),
            seq=seq,
            kind="purge",
            login_id=None,
            login_name="",
            device_id=None,
            applied_at=utcnow(),
            payload=payload,
            payload_hash=payload_hash(payload),
            status="applied",
            reason=None,
            result={},
        )
    )
    db.flush()


# --- Shopping lists (part of the history job, sync protocol 3.9) -------------------------------


def tidy_lists(db: DbSession, household: Household, now: datetime | None = None) -> int:
    """Tidy the shopping lists' records. Returns how many rows went. Safe to repeat.

    - Notes, 7 days (the undo window) after they're made; answered or closed "Did you buy
      2?" questions, the undo window after they closed. Neither needs a tombstone: open
      ones are always sent in full, so a phone simply drops one that's gone.
    - Removed (tombstoned) items, merged-away items and removed lists, with their ticks,
      after the history length (12 months). A purchase's changes lose the link to its tick
      first; the changes stay in the history. `list_purged_seq` goes up to the highest
      version deleted, so a phone further behind than that gets a fresh copy.
    - The sync log keeps every row for good (a repeat is always caught), but after the
      history length its `payload` and `result` are emptied.
    """
    from mealwright.shopping import lock_db

    now = now or utcnow()
    soon = now - undo_window(household)
    old = month_cutoff(household, now)
    lock_db(db, household)
    hid = household.id
    went = 0
    went += _deleted(
        db, delete(ListNote).where(ListNote.household_id == hid, ListNote.created_at < soon)
    )
    went += _deleted(
        db,
        delete(DoubleTick).where(
            DoubleTick.household_id == hid,
            DoubleTick.answer.is_not(None),
            DoubleTick.answered_at < soon,
        ),
    )
    lists = [
        (row.id, row.version)
        for row in db.execute(
            select(ShoppingList.id, ShoppingList.version).where(
                ShoppingList.household_id == hid,
                ShoppingList.main.is_(False),
                ShoppingList.removed_at.is_not(None),
                ShoppingList.removed_at < old,
            )
        )
    ]
    list_ids = [list_id for list_id, _ in lists]
    items = [
        (row.id, row.version)
        for row in db.execute(
            select(ListItem.id, ListItem.version).where(
                ListItem.household_id == hid,
                or_(
                    ListItem.list_id.in_(list_ids),
                    ListItem.deleted_at < old,
                    (ListItem.merged_into_id.is_not(None)) & (ListItem.added_at < old),
                ),
            )
        )
    ]
    item_ids = [item_id for item_id, _ in items]
    highest = max([version for _, version in lists + items], default=0)
    if item_ids:
        restock.keep_before_tidy_up(db, hid, item_ids)
        ticks = select(ListTick.id).where(
            ListTick.household_id == hid, ListTick.item_id.in_(item_ids)
        )
        db.execute(
            update(Change)
            .where(Change.household_id == hid, Change.tick_id.in_(ticks))
            .values(tick_id=None)
        )
        db.execute(
            delete(ListTick).where(ListTick.household_id == hid, ListTick.item_id.in_(item_ids))
        )
        db.execute(delete(ListNote).where(ListNote.item_id.in_(item_ids)))
        db.execute(delete(DoubleTick).where(DoubleTick.item_id.in_(item_ids)))
        went += _deleted(db, delete(ListItem).where(ListItem.id.in_(item_ids)))
    if list_ids:
        db.execute(delete(ListNote).where(ListNote.list_id.in_(list_ids)))
        db.execute(delete(DoubleTick).where(DoubleTick.list_id.in_(list_ids)))
        went += _deleted(db, delete(ShoppingList).where(ShoppingList.id.in_(list_ids)))
    if highest > household.list_purged_seq:
        household.list_purged_seq = highest
    db.execute(
        update(SyncAction)
        .where(
            SyncAction.household_id == hid,
            SyncAction.applied_at < old,
            or_(SyncAction.payload != {}, SyncAction.result != {}),
        )
        .values(payload={}, result={})
    )
    db.commit()
    return went


def _deleted(db: DbSession, statement: Any) -> int:
    return int(getattr(db.execute(statement), "rowcount", 0) or 0)
