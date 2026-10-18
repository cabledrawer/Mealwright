"""Shopping lists: the writes (docs/dev/sync-protocol.md sections 3, 5.2, 5.7 and 9).

Every write here is one function that takes the household's lock, takes the next number
from the household's counter, stamps the rows it changes with that number (`version`),
and records one `Change` (for Undo and Recent changes) and one `SyncAction` (the sync log).

The plain online API (api/v1/shopping.py) calls these. PR 3's action path calls the same
functions, so online writes and offline actions share one write path. Where PR 3 plugs
in is marked "PR 3:" below: ticking and the pantry side, notes, the "Did you buy 2?"
question, clashes between devices (`seen`), and the endpoints that send changes since a
number.
"""

import hashlib
import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from fastapi import status
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session as DbSession

from mealwright.amounts import MILLI, checked
from mealwright.api.v1.context import Kitchen
from mealwright.errors import Problem, not_found
from mealwright.foods import find, usual_size
from mealwright.history import Tally, record
from mealwright.household import undo_window
from mealwright.models import (
    Change,
    Food,
    FoodSize,
    ListItem,
    ListTick,
    Shop,
    ShoppingList,
    SyncAction,
    utcnow,
)

MAIN_LIST_NAME = "This week"

# Change kinds, at most 20 letters (change.kind).
LIST_KINDS = (
    "list_made",
    "list_renamed",
    "list_removed",
    "item_added",
    "item_amount",
    "item_deleted",
)


# --- Lists that exist ----------------------------------------------------------------------------


def ensure_main_list(db: DbSession, household_id: int, created_by: str = "") -> ShoppingList:
    """The household's main list, "This week". Made with the household (and by the migration
    for households that already existed)."""
    found = db.scalar(
        select(ShoppingList).where(
            ShoppingList.household_id == household_id, ShoppingList.main.is_(True)
        )
    )
    if found is not None:
        return found
    main = ShoppingList(
        id=str(uuid.uuid4()),
        household_id=household_id,
        name=MAIN_LIST_NAME,
        main=True,
        position=0,
        created_by_name=created_by,
    )
    db.add(main)
    db.flush()
    return main


def live_lists(kitchen: Kitchen) -> list[ShoppingList]:
    ensure_main_list(kitchen.db, kitchen.household_id)
    return list(
        kitchen.db.scalars(
            select(ShoppingList)
            .where(ShoppingList.household_id == kitchen.household_id)
            .where(ShoppingList.removed_at.is_(None))
            .order_by(ShoppingList.main.desc(), ShoppingList.position, ShoppingList.created_at)
        )
    )


def find_list(kitchen: Kitchen, list_id: str, *, removed_ok: bool = False) -> ShoppingList:
    """A list in this household. One from another household is 'not here', like a missing one."""
    found = kitchen.db.get(ShoppingList, list_id)
    if (
        found is None
        or found.household_id != kitchen.household_id
        or (found.removed_at is not None and not removed_ok)
    ):
        raise not_found("That list")
    return found


def find_item(kitchen: Kitchen, item_id: str) -> ListItem:
    """An item in this household, on a list that isn't removed. An item that was merged into
    another line gives that line (sync protocol 3.2). Deleted items are returned too: the
    caller decides what a tombstone means."""
    seen: set[str] = set()
    item = kitchen.db.get(ListItem, item_id)
    while item is not None and item.merged_into_id and item.id not in seen:
        seen.add(item.id)
        item = kitchen.db.get(ListItem, item.merged_into_id)
    if item is None or item.household_id != kitchen.household_id:
        raise not_found("That item")
    find_list(kitchen, item.list_id)
    return item


def deleted(item: ListItem) -> Problem:
    return Problem(
        status.HTTP_409_CONFLICT,
        "item_deleted",
        "That item was taken off the list.",
    )


# --- The counter and the lock --------------------------------------------------------------------


def lock_household(kitchen: Kitchen) -> None:
    """Take the household's write lock, so list writes for one household run one at a time
    (sync protocol 5.2). On SQLite a harmless write takes the lock at once; on Postgres
    the household row is locked."""
    db, household = kitchen.db, kitchen.household
    if db.get_bind().dialect.name == "sqlite":
        db.execute(
            update(type(household))
            .where(type(household).id == household.id)
            .values(list_seq=type(household).list_seq)
        )
        db.refresh(household)
    else:  # pragma: no cover (Postgres comes later)
        db.refresh(household, with_for_update=True)


@dataclass
class Batch:
    """One locked stretch of list writing. `take()` hands out the next counter number;
    `finish()` writes the last one back. Repeats and no-ops take none, so numbers have no
    gaps (sync protocol 5.2)."""

    kitchen: Kitchen
    last: int = 0
    taken: list[int] = field(default_factory=list)
    action: str = ""

    def __post_init__(self) -> None:
        lock_household(self.kitchen)
        self.last = self.kitchen.household.list_seq
        self.action = action_id(self.kitchen)

    def take(self) -> int:
        self.last += 1
        self.taken.append(self.last)
        return self.last

    def finish(self) -> None:
        self.kitchen.household.list_seq = self.last


def action_id(kitchen: Kitchen) -> str:
    """The action's ID: the request's Idempotency-Key when there is one (so a retry is
    recognised), else a new one."""
    return kitchen.idempotency_key or str(uuid.uuid4())


def _hash(payload: dict[str, Any]) -> str:
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode()).hexdigest()


def log_action(
    batch: Batch,
    seq: int,
    action: str,
    kind: str,
    payload: dict[str, Any],
    *,
    list_id: str | None = None,
    item_id: str | None = None,
    change: Change | None = None,
    reason: str | None = None,
    status_: str = "applied",
) -> SyncAction:
    kitchen = batch.kitchen
    row = SyncAction(
        household_id=kitchen.household_id,
        id=action,
        seq=seq,
        kind=kind,
        login_id=kitchen.login.id,
        login_name=kitchen.login.name,
        device_id=None,
        list_id=list_id,
        item_id=item_id,
        applied_at=utcnow(),
        payload=payload,
        payload_hash=_hash(payload),
        status=status_,
        reason=reason,
        result={},
        change_id=change.id if change else None,
    )
    kitchen.db.add(row)
    kitchen.db.flush()
    return row


def _done(
    batch: Batch,
    seq: int,
    kind: str,
    change_kind: str,
    summary: str,
    ops: list[dict[str, Any]],
    payload: dict[str, Any],
    *,
    food_id: int | None = None,
    list_id: str | None = None,
    item_id: str | None = None,
    status_: str = "applied",
) -> Change:
    """Record the Change (for Undo) and the sync-log row for one action."""
    change = record(
        batch.kitchen, change_kind, summary, food_id, {"shopping": ops, "action": batch.action}
    )
    log_action(
        batch,
        seq,
        batch.action,
        kind,
        payload,
        list_id=list_id,
        item_id=item_id,
        change=change,
        status_=status_,
    )
    batch.finish()
    return change


# --- Lists ---------------------------------------------------------------------------------------


def _new_id(kitchen: Kitchen, wanted: str | None, model: Any) -> str:
    """A phone-made UUID, or a new one. An ID already used (by anyone) is refused."""
    new = wanted or str(uuid.uuid4())
    if kitchen.db.get(model, new) is not None:
        raise Problem(status.HTTP_409_CONFLICT, "id_taken", "That ID is already used.")
    return new


def make_list(
    kitchen: Kitchen, name: str, list_id: str | None = None
) -> tuple[ShoppingList, Change]:
    batch = Batch(kitchen)
    new_id = _new_id(kitchen, list_id, ShoppingList)
    seq = batch.take()
    position = (
        kitchen.db.scalar(
            select(func.max(ShoppingList.position)).where(
                ShoppingList.household_id == kitchen.household_id
            )
        )
        or 0
    ) + 1
    made = ShoppingList(
        id=new_id,
        household_id=kitchen.household_id,
        name=name,
        main=False,
        position=position,
        created_by_name=kitchen.login.name,
        version=seq,
    )
    kitchen.db.add(made)
    kitchen.db.flush()
    change = _done(
        batch,
        seq,
        "create_list",
        "list_made",
        f"Made the list {name}",
        [{"op": "list_made", "list_id": made.id}],
        {"list_id": made.id, "name": name},
        list_id=made.id,
    )
    return made, change


def rename_list(kitchen: Kitchen, shopping_list: ShoppingList, name: str) -> Change | None:
    """Any list can be renamed, the main list too (the last one received wins, no note)."""
    if shopping_list.name == name:
        return None
    batch = Batch(kitchen)
    seq = batch.take()
    old = shopping_list.name
    shopping_list.name = name
    shopping_list.version = seq
    return _done(
        batch,
        seq,
        "rename_list",
        "list_renamed",
        f"Renamed the list {old} to {name}",
        [{"op": "list_name", "list_id": shopping_list.id, "old": old, "new": name}],
        {"list_id": shopping_list.id, "name": name},
        list_id=shopping_list.id,
    )


def remove_list(kitchen: Kitchen, shopping_list: ShoppingList) -> Change:
    """Hide an extra list (hidden, not frozen). The main list can never be removed."""
    if shopping_list.main:
        raise Problem(
            status.HTTP_409_CONFLICT,
            "main_list",
            "The main list can be renamed, but not removed.",
        )
    batch = Batch(kitchen)
    seq = batch.take()
    shopping_list.removed_at = utcnow()
    shopping_list.removed_action_id = batch.action
    shopping_list.version = seq
    return _done(
        batch,
        seq,
        "remove_list",
        "list_removed",
        f"Removed the list {shopping_list.name}",
        [{"op": "list_removed", "list_id": shopping_list.id}],
        {"list_id": shopping_list.id},
        list_id=shopping_list.id,
    )


def merged_in(db: DbSession, household_id: int, food_id: int) -> set[int]:
    """This ingredient and every ingredient merged into it, however far back the chain goes.
    A merge repoints list items (sync protocol 5.8), so none should be left on a merged-away
    ingredient; following the chain is the safety net."""
    found = {food_id}
    frontier = {food_id}
    while frontier:
        frontier = (
            set(
                db.scalars(
                    select(Food.id).where(
                        Food.household_id == household_id, Food.merged_into_id.in_(frontier)
                    )
                )
            )
            - found
        )
        found |= frontier
    return found


def on_a_list(db: DbSession, household_id: int, food_id: int, cutoff: datetime) -> bool:
    """Is this ingredient (or one merged into it) on a list that is not removed, or removed
    after `cutoff`? Tombstones don't count."""
    rows = db.execute(
        select(ShoppingList.removed_at)
        .join(ListItem, ListItem.list_id == ShoppingList.id)
        .where(
            ListItem.household_id == household_id,
            ListItem.food_id.in_(merged_in(db, household_id, food_id)),
            ListItem.deleted_at.is_(None),
            ListItem.merged_into_id.is_(None),
        )
    ).all()
    for (removed_at,) in rows:
        if removed_at is None:
            return True
        moment = removed_at if removed_at.tzinfo else removed_at.replace(tzinfo=cutoff.tzinfo)
        if moment > cutoff:
            return True
    return False


def removed_recently(kitchen: Kitchen, food_id: int) -> bool:
    """Is this ingredient on a list that is not removed, or removed within the undo window?
    (Undo of the removal would bring it back.) Tombstones don't count."""
    cutoff = utcnow() - undo_window(kitchen.household)
    return on_a_list(kitchen.db, kitchen.household_id, food_id, cutoff)


def move_items(
    kitchen: Kitchen, from_food_id: int, to_food_id: int, batch: Batch
) -> list[dict[str, Any]]:
    """A merge: every list item of the merged-away ingredient goes to the kept one (sync
    protocol 5.8), tombstones too. Two lines that become the same ingredient stay two
    lines. Returns the Undo steps."""
    seq = batch.taken[-1] if batch.taken else batch.take()
    ops: list[dict[str, Any]] = []
    for item in kitchen.db.scalars(
        select(ListItem).where(
            ListItem.household_id == kitchen.household_id, ListItem.food_id == from_food_id
        )
    ):
        item.food_id = to_food_id
        item.version = seq
        ops.append({"op": "item_food", "item_id": item.id, "old": from_food_id, "new": to_food_id})
    kitchen.db.flush()
    return ops


def food_is_shown(kitchen: Kitchen, food_id: int) -> bool:
    """Is this ingredient in Ingredients (or merged into one that is)? Items on one that
    isn't aren't shown on lists."""
    try:
        find(kitchen, food_id)
    except Problem:
        return False
    return True


def bump_foods(kitchen: Kitchen, food_ids: Iterable[int], batch: Batch | None = None) -> None:
    """Stamp ingredients with the next counter number (sync protocol 3.7), so devices pick
    up what changed. With no `batch`, this takes the lock and the number itself."""
    ids = sorted(set(food_ids))
    if not ids:
        return
    own = batch is None
    batch = batch or Batch(kitchen)
    seq = batch.taken[-1] if batch.taken else batch.take()
    kitchen.db.execute(
        update(Food)
        .where(Food.household_id == kitchen.household_id, Food.id.in_(ids))
        .values(version=seq)
    )
    if own:
        batch.finish()


# --- Items ---------------------------------------------------------------------------------------


def default_amount(kitchen: Kitchen, food: Food) -> tuple[int | None, int | None]:
    """A blank amount: one of the usual size (with that size), or 1 if counted in items,
    otherwise no amount (spec "Decided for 0.3"; sync protocol rule L-14, decision 1)."""
    usual = usual_size(kitchen, food.id)
    if usual is not None:
        return usual.amount_milli, usual.id
    if food.counted_as == "count":
        return MILLI, None
    return None, None


def check_shop(kitchen: Kitchen, shop_id: int) -> Shop:
    shop = kitchen.db.get(Shop, shop_id)
    if shop is None or shop.household_id != kitchen.household_id:
        raise not_found("That shop")
    return shop


def check_size(kitchen: Kitchen, food: Food, size_id: int | None) -> FoodSize | None:
    if size_id is None:
        return None
    size = kitchen.db.get(FoodSize, size_id)
    if size is None or size.food_id != food.id:
        raise not_found("That size")
    return size


def matching_line(
    kitchen: Kitchen, list_id: str, food_id: int, shop_id: int | None
) -> ListItem | None:
    """The oldest live, unticked line for this ingredient and shop on this list (rule L-12)."""
    query = (
        select(ListItem)
        .where(
            ListItem.household_id == kitchen.household_id,
            ListItem.list_id == list_id,
            ListItem.food_id == food_id,
            ListItem.deleted_at.is_(None),
            ListItem.merged_into_id.is_(None),
            ListItem.ticked_at.is_(None),
        )
        .order_by(ListItem.added_at, ListItem.id)
        .limit(1)
    )
    query = query.where(
        ListItem.shop_id.is_(None) if shop_id is None else ListItem.shop_id == shop_id
    )
    return kitchen.db.scalar(query)


def add_item(
    kitchen: Kitchen,
    shopping_list: ShoppingList,
    food: Food,
    *,
    amount_milli: int | None,
    size: FoodSize | None,
    blank: bool,
    shop_id: int | None,
    item_id: str | None = None,
) -> tuple[ListItem, Change, bool]:
    """Add an ingredient to a list, or join a line that is already there.

    `blank`: no amount was given (the usual size, or 1 for items). Joining adds the amounts
    up (online, the person can see the line; PR 3: a real clash between two devices keeps
    the bigger amount and leaves notes). Returns (item, change, merged)."""
    batch = Batch(kitchen)
    new_id = _new_id(kitchen, item_id, ListItem)
    if blank:
        amount_milli, size_id = default_amount(kitchen, food)
        size = kitchen.db.get(FoodSize, size_id) if size_id else None
    payload = {
        "list_id": shopping_list.id,
        "item_id": new_id,
        "food_id": food.id,
        "amount_milli": amount_milli,
        "size_id": size.id if size else None,
        "shop_id": shop_id,
    }
    line = matching_line(kitchen, shopping_list.id, food.id, shop_id)
    seq = batch.take()
    if line is not None:
        before = _amount_state(line)
        if amount_milli is not None:
            line.amount_milli = checked((line.amount_milli or 0) + amount_milli)
            if line.size_id is None and line.amount_milli == amount_milli and size is not None:
                line.size_id = size.id
        line.version = seq
        kitchen.db.flush()
        change = _done(
            batch,
            seq,
            "add",
            "item_added",
            f"Added {food.name} to {shopping_list.name} (joined the line already there)",
            [
                {
                    "op": "item_amount",
                    "item_id": line.id,
                    "old": before,
                    "new": _amount_state(line),
                }
            ],
            payload,
            food_id=food.id,
            list_id=shopping_list.id,
            item_id=line.id,
            status_="merged",
        )
        return line, change, True
    item = ListItem(
        id=new_id,
        household_id=kitchen.household_id,
        list_id=shopping_list.id,
        food_id=food.id,
        shop_id=shop_id,
        amount_milli=amount_milli,
        size_id=size.id if size else None,
        source="typed",
        hand_edited=False,
        added_by_login_id=kitchen.login.id,
        added_by_name=kitchen.login.name,
        version=seq,
    )
    kitchen.db.add(item)
    kitchen.db.flush()
    change = _done(
        batch,
        seq,
        "add",
        "item_added",
        f"Added {food.name} to {shopping_list.name}",
        [
            {
                "op": "item_made",
                "item_id": item.id,
                "state": _amount_state(item),
                "shop_id": item.shop_id,
            }
        ],
        payload,
        food_id=food.id,
        list_id=shopping_list.id,
        item_id=item.id,
    )
    return item, change, False


def _amount_state(item: ListItem) -> list[Any]:
    return [item.amount_milli, item.size_id]


def set_amount(
    kitchen: Kitchen, item: ListItem, food: Food, amount_milli: int, size: FoodSize | None
) -> Change | None:
    """Change the amount to buy. Sets `hand_edited`, so the plan (0.6) never overwrites it.
    On a ticked item it changes only the list, never the pantry (that's "Different pack?")."""
    if item.deleted_at is not None:
        raise deleted(item)
    new_size = size.id if size else None
    if (item.amount_milli, item.size_id) == (amount_milli, new_size):
        return None
    batch = Batch(kitchen)
    seq = batch.take()
    before = _amount_state(item)
    item.amount_milli = amount_milli
    item.size_id = new_size
    item.hand_edited = True
    item.version = seq
    return _done(
        batch,
        seq,
        "set_amount",
        "item_amount",
        f"Changed {food.name} on the list",
        [{"op": "item_amount", "item_id": item.id, "old": before, "new": _amount_state(item)}],
        {"item_id": item.id, "amount_milli": amount_milli, "size_id": new_size},
        food_id=food.id,
        list_id=item.list_id,
        item_id=item.id,
    )


def delete_item(kitchen: Kitchen, item: ListItem, food: Food) -> Change | None:
    """Take an item off the list, leaving a tombstone so an old queue can't bring it back."""
    if item.deleted_at is not None:
        return None
    batch = Batch(kitchen)
    seq = batch.take()
    _tombstone(kitchen, item, seq, batch.action)
    return _done(
        batch,
        seq,
        "delete",
        "item_deleted",
        f"Took {food.name} off the list",
        [{"op": "item_deleted", "item_ids": [item.id]}],
        {"item_id": item.id},
        food_id=food.id,
        list_id=item.list_id,
        item_id=item.id,
    )


def _tombstone(kitchen: Kitchen, item: ListItem, seq: int, action: str) -> None:
    item.deleted_at = utcnow()
    item.deleted_by_name = kitchen.login.name
    item.deleted_action_id = action
    item.version = seq


def standing_ticks(kitchen: Kitchen, item_ids: Iterable[str]) -> set[str]:
    """Items with at least one tick that hasn't been reversed. PR 3 keeps `list_tick` and
    the item's `ticked_at` copy in step; this reads both so the two can't disagree here."""
    ids = list(item_ids)
    if not ids:
        return set()
    return set(
        kitchen.db.scalars(
            select(ListTick.item_id).where(
                ListTick.household_id == kitchen.household_id,
                ListTick.item_id.in_(ids),
                ListTick.reversed_at.is_(None),
            )
        )
    )


def clear_ticked(
    kitchen: Kitchen, shopping_list: ShoppingList, item_ids: list[str] | None
) -> tuple[list[ListItem], Change | None]:
    """Remove the ticked items from a list, as one action with one Undo. An item that was
    unticked meanwhile stays. Ticking itself is PR 3: here "ticked" is what the tick rows
    and the item's `ticked_at` say."""
    query = select(ListItem).where(
        ListItem.household_id == kitchen.household_id,
        ListItem.list_id == shopping_list.id,
        ListItem.deleted_at.is_(None),
        ListItem.merged_into_id.is_(None),
    )
    if item_ids is not None:
        query = query.where(ListItem.id.in_(item_ids))
    candidates = list(kitchen.db.scalars(query))
    standing = standing_ticks(kitchen, [i.id for i in candidates])
    items = [i for i in candidates if i.ticked_at is not None or i.id in standing]
    if not items:
        return [], None
    batch = Batch(kitchen)
    seq = batch.take()
    for item in items:
        _tombstone(kitchen, item, seq, batch.action)
    n = len(items)
    change = _done(
        batch,
        seq,
        "clear_ticked",
        "item_deleted",
        f"Cleared {n} ticked item{'s' if n != 1 else ''} from {shopping_list.name}",
        [{"op": "item_deleted", "item_ids": [i.id for i in items]}],
        {"list_id": shopping_list.id, "item_ids": [i.id for i in items]},
        list_id=shopping_list.id,
    )
    return items, change


# --- Undo ----------------------------------------------------------------------------------------


def undo_shopping(kitchen: Kitchen, change: Change, tally: Tally, batch: Batch) -> int:
    """Reverse a list change (api: POST /changes/{id}/undo). Each part is put back only if
    it still looks the way the change left it (like food changes). Rows touched get the
    Undo's counter number. Returns that number."""
    data = change.undo_data or {}
    seq = batch.take()
    db = kitchen.db
    undo_action = batch.action
    for op in data.get("shopping", []):
        kind = op["op"]
        if kind in ("list_made", "list_name", "list_removed"):
            row = db.get(ShoppingList, op["list_id"])
            if row is None or row.household_id != kitchen.household_id:
                tally.skipped += 1
                continue
            if kind == "list_made":
                row.removed_at = row.removed_at or utcnow()
                row.removed_action_id = undo_action
            elif kind == "list_removed":
                row.removed_at = None
                row.removed_action_id = None
            elif row.name == op["new"]:
                row.name = op["old"]
            elif row.name != op["old"]:
                tally.skipped += 1
                continue
            row.version = seq
            tally.done += 1
        elif kind == "item_made":
            item = db.get(ListItem, op["item_id"])
            if item is None or item.household_id != kitchen.household_id:
                tally.skipped += 1
                continue
            if item.deleted_at is not None:
                tally.done += 1  # already off the list
            elif (
                item.ticked_at is None
                and _amount_state(item) == op.get("state")
                and (item.shop_id == op.get("shop_id"))
            ):
                _tombstone(kitchen, item, seq, undo_action)
                tally.done += 1
            else:  # ticked, or someone changed it since: leave it
                tally.skipped += 1
        elif kind == "item_amount":
            item = db.get(ListItem, op["item_id"])
            if item is None or item.household_id != kitchen.household_id or item.deleted_at:
                tally.skipped += 1
                continue
            if _amount_state(item) == op["new"]:
                item.amount_milli, item.size_id = op["old"]
                item.version = seq
                tally.done += 1
            elif _amount_state(item) == op["old"]:
                tally.done += 1
            else:
                tally.skipped += 1
        elif kind == "item_food":  # a merge moved the item to the kept ingredient
            item = db.get(ListItem, op["item_id"])
            if item is None or item.household_id != kitchen.household_id:
                tally.skipped += 1
            elif item.food_id == op["new"]:
                item.food_id = op["old"]
                item.version = seq
                tally.done += 1
            elif item.food_id == op["old"]:
                tally.done += 1
            else:
                tally.skipped += 1
        elif kind == "item_deleted":
            for item_id in op["item_ids"]:
                item = db.get(ListItem, item_id)
                if item is None or item.household_id != kitchen.household_id:
                    tally.skipped += 1
                    continue
                if item.deleted_at is not None:
                    if not food_is_shown(kitchen, item.food_id):
                        tally.skipped += 1  # its ingredient was removed since: stay off
                        continue
                    item.deleted_at = None
                    item.deleted_by_name = None
                    item.deleted_action_id = None
                    item.version = seq
                tally.done += 1
    db.flush()
    return seq


def log_undo(batch: Batch, seq: int, original: Change, undo_change: Change) -> None:
    """The sync-log row for an Undo, and the mark on the action it undid."""
    kitchen = batch.kitchen
    undone_action = (original.undo_data or {}).get("action")
    action = batch.action
    log_action(batch, seq, action, "undo", {"undoes": undone_action}, change=undo_change)
    if undone_action:
        row = kitchen.db.get(SyncAction, (kitchen.household_id, undone_action))
        if row is not None:
            row.undone_by_action_id = action
    batch.finish()
