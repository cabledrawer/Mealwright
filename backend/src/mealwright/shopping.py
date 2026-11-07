"""Shopping lists: the writes (docs/dev/sync-protocol.md sections 3, 4, 5, 6, 8 and 9).

Every list write is an *action*, handled the same way whether it came from a phone's
offline queue (POST /shopping/actions) or from one of the plain one-at-a-time requests
(api/v1/shopping.py): mealwright.sync runs it under the household's lock, gives it the
next number from the household's counter, and records one `SyncAction` (the sync log)
plus its `Change`s (for Undo and Recent changes). The handlers here do the work of one
action each; they read the action's payload and say what happened on the `Act`.

The pantry side of a tick lives in mealwright.ticks.
"""

import hashlib
import json
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, TypeIs

from fastapi import status
from sqlalchemy import and_, func, or_, select, text, update
from sqlalchemy.orm import Session as DbSession

from mealwright.amounts import MILLI, NBSP, TooBig, checked, to_milli
from mealwright.api.v1.context import Kitchen
from mealwright.conversions import guess_aisle, table
from mealwright.errors import Problem, not_found
from mealwright.foods import add_size, find, name_owner, suggested_shop, usual_size
from mealwright.history import Tally, diff, record, record_back, snapshot
from mealwright.household import undo_window
from mealwright.models import (
    Change,
    Food,
    FoodName,
    FoodSize,
    Household,
    ListItem,
    ListNote,
    ListTick,
    Shop,
    ShoppingList,
    SyncAction,
    utcnow,
)
from mealwright.names import clean, fold
from mealwright.stock import has_stock

MAIN_LIST_NAME = "This week"
OTHER_PHONE = "Your other phone"  # {who} for the same login on another phone (section 8)

# Change kinds, at most 20 letters (change.kind).
LIST_KINDS = (
    "list_made",
    "list_renamed",
    "list_removed",
    "item_added",
    "item_amount",
    "item_deleted",
    "item_place",
    "item_moved",
)

LOCKED = "mealwright.household_locked"


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
    found = get_list(kitchen, list_id)
    if found is None or (found.removed_at is not None and not removed_ok):
        raise not_found("That list")
    return found


def get_list(kitchen: Kitchen, list_id: str) -> ShoppingList | None:
    """A list in this household (removed ones too), or None."""
    found = kitchen.db.get(ShoppingList, list_id)
    if found is None or found.household_id != kitchen.household_id:
        return None
    return found


def get_item(kitchen: Kitchen, item_id: str) -> ListItem | None:
    """An item in this household, or None. An item that was merged into another line gives
    that line (sync protocol 3.2). Tombstones are returned too: the caller decides what a
    tombstone means."""
    seen: set[str] = set()
    item = kitchen.db.get(ListItem, item_id)
    while item is not None and item.merged_into_id and item.id not in seen:
        seen.add(item.id)
        item = kitchen.db.get(ListItem, item.merged_into_id)
    if item is None or item.household_id != kitchen.household_id:
        return None
    return item


def find_item(kitchen: Kitchen, item_id: str) -> ListItem:
    """An item in this household, on a list that isn't removed (else 404)."""
    item = get_item(kitchen, item_id)
    if item is None:
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
    lock_db(kitchen.db, kitchen.household)


def lock_db(db: DbSession, household: Household) -> None:
    """Take the household's write lock, so list writes for one household run one at a time
    (sync protocol 5.2). Taken once per transaction.

    SQLite: a transaction that hasn't written yet is started with BEGIN IMMEDIATE, which
    holds the write lock until commit (a deferred one could fail later with "busy"). One
    that has already written holds the lock already; a harmless write makes sure of it.
    Postgres (later): the household row is locked."""
    db.flush()
    if db.info.get(LOCKED) is not None and db.info.get(LOCKED) is db.get_transaction():
        return
    if db.get_bind().dialect.name == "sqlite":
        raw = db.connection().connection.dbapi_connection
        if raw is not None and not raw.in_transaction:
            db.execute(text("BEGIN IMMEDIATE"))
            db.expire_all()  # what was read before the lock may be out of date
        else:
            db.execute(
                update(Household)
                .where(Household.id == household.id)
                .values(list_seq=Household.list_seq)
            )
        db.refresh(household)
    else:  # pragma: no cover (Postgres comes later)
        db.refresh(household, with_for_update=True)
    db.info[LOCKED] = db.get_transaction()


@dataclass
class Batch:
    """One locked stretch of list writing. `take()` hands out the next counter number;
    `finish()` writes the last one back. Repeats, refusals and no-ops take none, so numbers
    have no gaps (sync protocol 5.2)."""

    kitchen: Kitchen
    last: int = 0
    taken: list[int] = field(default_factory=list)
    action: str = ""
    locked: bool = False

    def __post_init__(self) -> None:
        self.action = self.action or action_id(self.kitchen)
        self.lock()

    def lock(self) -> None:
        if not self.locked:
            lock_household(self.kitchen)
            self.last = self.kitchen.household.list_seq
            self.locked = True

    def take(self) -> int:
        # Another Batch in this same transaction (a plan Undo updates the list inside the
        # Undo's own) may have used numbers since this one began: start from the household's
        # counter as it stands, so a number is never used twice.
        #
        # The household's counter is written at once (follow-up 7, PR 74 security round 2), so a
        # second Batch started in this transaction can't start from a stale number.
        household = self.kitchen.household
        self.last = max(self.last, household.list_seq) + 1
        household.list_seq = self.last
        self.taken.append(self.last)
        return self.last

    def give_back(self) -> None:
        """A refused action hands its number back (it is always the last one taken)."""
        household = self.kitchen.household
        if household.list_seq == self.taken.pop():
            household.list_seq = self.last - 1
        self.last -= 1

    def number(self) -> int:
        """The number this write uses: the one already taken, else the next."""
        return self.taken[-1] if self.taken else self.take()

    def finish(self) -> None:
        # Never lower the counter (an inner Batch may have raised it past this one).
        household = self.kitchen.household
        household.list_seq = max(self.last, household.list_seq)


def action_id(kitchen: Kitchen) -> str:
    """The action's ID: the request's Idempotency-Key when there is one (so a retry is
    recognised), else a new one."""
    return kitchen.idempotency_key or str(uuid.uuid4())


def payload_hash(payload: dict[str, Any]) -> str:
    text_ = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text_.encode()).hexdigest()


def server_action(
    batch: Batch,
    kind: str,
    payload: dict[str, Any],
    change: Change | None = None,
    *,
    list_id: str | None = None,
    item_id: str | None = None,
) -> SyncAction:
    """The sync-log row for a server-made list change (sync protocol 5.8): an Undo from
    Pantry, an ingredient edit that lists show, a merge, the tidy-up. `device_id` is null."""
    kitchen = batch.kitchen
    action = batch.action
    if kitchen.db.get(SyncAction, (kitchen.household_id, action)) is not None:
        action = str(uuid.uuid4())
    row = SyncAction(
        household_id=kitchen.household_id,
        id=action,
        seq=batch.number(),
        kind=kind,
        login_id=kitchen.login.id,
        login_name=kitchen.login.name,
        device_id=None,
        list_id=list_id,
        item_id=item_id,
        applied_at=utcnow(),
        payload=payload,
        payload_hash=payload_hash(payload),
        status="applied",
        reason=None,
        result={},
        change_id=change.id if change else None,
    )
    kitchen.db.add(row)
    kitchen.db.flush()
    return row


def action_row(kitchen: Kitchen, action: str | None) -> SyncAction | None:
    if not action:
        return None
    return kitchen.db.get(SyncAction, (kitchen.household_id, action))


# --- One action ----------------------------------------------------------------------------------


class Refused(Exception):
    """The action is not valid (sync protocol 5.4): nothing of it is recorded."""

    def __init__(self, reason: str, message: str) -> None:
        super().__init__(message)
        self.reason = reason
        self.message = message


@dataclass
class Act:
    """One action being applied: what it says, and what happened."""

    batch: Batch
    id: str
    kind: str
    payload: dict[str, Any]
    device_id: str | None = None
    seen: int | None = None
    made_at: datetime | None = None
    sent_at: datetime | None = None
    plain: bool = False  # one of the plain one-at-a-time requests
    seq: int = 0
    status: str = "applied"  # applied, merged, ignored
    reason: str | None = None
    message: str | None = None
    list_id: str | None = None
    item_id: str | None = None
    food_id: int | None = None
    main_change: Change | None = None  # the list change, for Undo
    change: Change | None = None  # the pantry change, if any (sync protocol 5.4)
    out: dict[str, Any] = field(default_factory=dict)  # for the plain requests' answers

    @property
    def kitchen(self) -> Kitchen:
        return self.batch.kitchen

    def ignore(self, reason: str, message: str | None = None) -> None:
        self.status = "ignored"
        self.reason = reason
        self.message = message

    def done(
        self,
        change_kind: str,
        summary: str,
        ops: list[dict[str, Any]],
        food_id: int | None = None,
        **extra: Any,
    ) -> Change:
        """Record the list Change (for Undo and Recent changes)."""
        change = record(
            self.kitchen,
            change_kind,
            summary,
            food_id,
            {"shopping": ops, "action": self.id, **extra},
        )
        if self.main_change is None:
            self.main_change = change
        return change


def new_id(kitchen: Kitchen, wanted: str | None, model: Any) -> str:
    """A phone-made UUID, or a new one. An ID already used (by anyone) is refused."""
    made = wanted or str(uuid.uuid4())
    if kitchen.db.get(model, made) is not None:
        raise Refused("id_taken", "That ID is already used.")
    return made


def milli_of(amount: Any) -> int | None:
    """An action's base amount → thousandths; over 1,000,000 → refused too_big."""
    if amount is None:
        return None
    try:
        return checked(to_milli(amount))
    except TooBig as err:
        raise Refused("too_big", "That amount is too big.") from err


# --- Notes (section 8) ---------------------------------------------------------------------------


def who(login_id: int | None, name: str, for_login_id: int | None) -> str:
    """{who}: the other person's name, or "Your other phone" for the same login."""
    return OTHER_PHONE if login_id is not None and login_id == for_login_id else name


def note(
    act: Act,
    kind: str,
    for_login_id: int | None,
    words: str,
    *,
    list_id: str,
    item_id: str | None = None,
    food_id: int | None = None,
    undo: str | None = None,
) -> ListNote | None:
    if for_login_id is None:
        return None
    if undo is not None and _is_undo(act, undo):
        undo = None  # an Undo can't be undone (no redo, 9): the note has only its close button
    row = ListNote(
        household_id=act.kitchen.household_id,
        list_id=list_id,
        item_id=item_id,
        food_id=food_id,
        for_login_id=for_login_id,
        kind=kind,
        text=words[:300],
        undo_action_id=undo,
        created_at=utcnow(),
        version=act.seq,
    )
    act.kitchen.db.add(row)
    act.kitchen.db.flush()
    return row


UNDO_KINDS = ("undo", "untick_by_undo", "place_by_undo")


def _is_undo(act: Act, action_id: str) -> bool:
    if action_id == act.id:
        return act.kind in UNDO_KINDS
    row = action_row(act.kitchen, action_id)
    return row is not None and row.kind in UNDO_KINDS


def notes_gone(kitchen: Kitchen, undone_action: str | None, seq: int) -> None:
    """A note goes away when what it describes is undone (section 8)."""
    if not undone_action:
        return
    for row in kitchen.db.scalars(
        select(ListNote).where(
            ListNote.household_id == kitchen.household_id,
            ListNote.undo_action_id == undone_action,
            ListNote.gone_at.is_(None),
        )
    ):
        row.gone_at = utcnow()
        row.version = seq


def unseen(act: Act, row: SyncAction | None) -> bool:
    """Was `row` recorded after the device last caught up (it hadn't seen it)?"""
    return row is not None and not act.plain and act.seen is not None and row.seq > act.seen


def in_removed_list(act: Act, shopping_list: ShoppingList, ticked: bool = False) -> None:
    """N7: queued actions that hit a removed list still apply; the person whose queue hit
    it gets one list-wide note (rule L-7)."""
    if shopping_list.removed_at is None or act.plain:
        return
    removal = action_row(act.kitchen, shopping_list.removed_action_id)
    if removal is None or not unseen(act, removal):
        return
    me = act.kitchen.login.id
    words = (
        f"{who(removal.login_id, removal.login_name, me)} had removed {shopping_list.name}."
        " Your changes are kept with it."
    )
    existing = act.kitchen.db.scalar(
        select(ListNote).where(
            ListNote.household_id == act.kitchen.household_id,
            ListNote.list_id == shopping_list.id,
            ListNote.kind == "N7",
            ListNote.for_login_id == me,
            ListNote.gone_at.is_(None),
        )
    )
    if existing is not None:
        if ticked and not existing.text.endswith("pantry."):
            existing.text = existing.text + " Your ticks still went into the pantry."
            existing.version = act.seq
        return
    if ticked:
        words += " Your ticks still went into the pantry."
    note(act, "N7", me, words, list_id=shopping_list.id, undo=removal.id)


# --- Lists ---------------------------------------------------------------------------------------


def make_list(act: Act) -> None:
    kitchen = act.kitchen
    ensure_main_list(kitchen.db, kitchen.household_id)
    list_id = new_id(kitchen, act.payload["list_id"], ShoppingList)
    name = act.payload["name"]
    position = (
        kitchen.db.scalar(
            select(func.max(ShoppingList.position)).where(
                ShoppingList.household_id == kitchen.household_id
            )
        )
        or 0
    ) + 1
    made = ShoppingList(
        id=list_id,
        household_id=kitchen.household_id,
        name=name,
        main=False,
        position=position,
        created_by_name=kitchen.login.name,
        version=act.seq,
    )
    kitchen.db.add(made)
    kitchen.db.flush()
    act.list_id = made.id
    act.out["list"] = made
    act.done("list_made", f"Made the list {name}", [{"op": "list_made", "list_id": made.id}])


def rename_list(act: Act) -> None:
    """Any list can be renamed, the main list too (the last one received wins, no note)."""
    shopping_list = get_list(act.kitchen, act.payload["list_id"])
    if shopping_list is None:
        act.ignore("gone")
        return
    act.list_id = shopping_list.id
    act.out["list"] = shopping_list
    name = act.payload["name"]
    if shopping_list.name == name:
        act.ignore("no_change")
        return
    in_removed_list(act, shopping_list)
    old = shopping_list.name
    shopping_list.name = name
    shopping_list.version = act.seq
    act.done(
        "list_renamed",
        f"Renamed the list {old} to {name}",
        [{"op": "list_name", "list_id": shopping_list.id, "old": old, "new": name}],
    )


def remove_list(act: Act) -> None:
    """Hide an extra list (hidden, not frozen). The main list can never be removed."""
    shopping_list = get_list(act.kitchen, act.payload["list_id"])
    if shopping_list is None:
        act.ignore("gone")
        return
    act.list_id = shopping_list.id
    if shopping_list.main:
        raise Refused("main_list", "The main list can be renamed, but not removed.")
    if shopping_list.removed_at is not None:
        act.ignore("no_change")
        return
    shopping_list.removed_at = utcnow()
    shopping_list.removed_action_id = act.id
    shopping_list.version = act.seq
    act.done(
        "list_removed",
        f"Removed the list {shopping_list.name}",
        [{"op": "list_removed", "list_id": shopping_list.id}],
    )


# --- Ingredients and lists -----------------------------------------------------------------------


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


def still_needed(kitchen: Kitchen, food_id: int) -> bool:
    """0.2's rule for removing an ingredient (`cannot_remove` in api/v1/foods.py): not while
    it has stock, nor while it is on a list (merges followed). An Undo that would remove a
    brought-back ingredient again (5.9, 7.1) leaves it in Ingredients while this holds."""
    return has_stock(kitchen, food_id) or removed_recently(kitchen, food_id)


def move_items(
    kitchen: Kitchen, from_food_id: int, to_food_id: int, batch: Batch
) -> list[dict[str, Any]]:
    """A merge: every list item of the merged-away ingredient goes to the kept one (sync
    protocol 5.8), tombstones too. Two lines that become the same ingredient stay two
    lines. Returns the Undo steps."""
    seq = batch.number()
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


def follow_shop(
    kitchen: Kitchen, food: Food, old_shop_id: int | None, batch: Batch
) -> list[dict[str, Any]]:
    """A usual-shop change moves the ingredient's unticked items that were in the old shop
    (or Any shop) to the new one (sync protocol 3.2, 5.8). Returns the Undo steps."""
    if food.shop_id == old_shop_id:
        return []
    items = list(
        kitchen.db.scalars(
            select(ListItem).where(
                ListItem.household_id == kitchen.household_id,
                ListItem.food_id == food.id,
                ListItem.deleted_at.is_(None),
                ListItem.merged_into_id.is_(None),
                ListItem.ticked_at.is_(None),
            )
        )
    )
    moving = [i for i in items if i.shop_id in (old_shop_id, None) and i.shop_id != food.shop_id]
    if not moving:
        return []
    seq = batch.number()
    ops: list[dict[str, Any]] = []
    for item in moving:
        ops.append(
            {"op": "item_shop", "item_id": item.id, "old": item.shop_id, "new": food.shop_id}
        )
        item.shop_id = food.shop_id
        item.version = seq
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
    seq = batch.number()
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
    shop = get_shop(kitchen, shop_id)
    if shop is None:
        raise not_found("That shop")
    return shop


def get_shop(kitchen: Kitchen, shop_id: int) -> Shop | None:
    shop = kitchen.db.get(Shop, shop_id)
    if shop is None or shop.household_id != kitchen.household_id:
        return None
    return shop


def check_size(kitchen: Kitchen, food: Food, size_id: int | None) -> FoodSize | None:
    if size_id is None:
        return None
    size = get_size(kitchen, food, size_id)
    if size is None:
        raise not_found("That size")
    return size


def get_size(kitchen: Kitchen, food: Food, size_id: int | None) -> FoodSize | None:
    if size_id is None:
        return None
    size = kitchen.db.get(FoodSize, size_id)
    if size is None or size.food_id != food.id:
        return None
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


def made_by(kitchen: Kitchen, item_id: str) -> SyncAction | None:
    """The action that made this line."""
    return kitchen.db.scalar(
        select(SyncAction)
        .where(
            SyncAction.household_id == kitchen.household_id,
            SyncAction.kind == "add",
            SyncAction.item_id == item_id,
            SyncAction.status == "applied",
        )
        .order_by(SyncAction.seq)
        .limit(1)
    )


def _gone_name(kitchen: Kitchen, food_id: Any) -> str | None:
    """The name of an ingredient deleted for good, from the tidy-up's log row."""
    for payload in kitchen.db.scalars(
        select(SyncAction.payload).where(
            SyncAction.household_id == kitchen.household_id, SyncAction.kind == "purge"
        )
    ):
        name = (payload or {}).get("foods", {}).get(str(food_id))
        if name:
            return str(name)
    return None


def _named(kitchen: Kitchen, name: str) -> Food | None:
    """A visible ingredient with this name or other name (ignoring case and accents)."""
    owner = name_owner(kitchen, name)
    if owner is not None:
        return owner
    folded = fold(name)
    for other, food in kitchen.db.execute(
        select(FoodName, Food)
        .join(Food, Food.id == FoodName.food_id)
        .where(
            Food.household_id == kitchen.household_id,
            Food.removed_at.is_(None),
            Food.merged_into_id.is_(None),
        )
    ).all():
        if fold(other.name) == folded:
            return food
    return None


def _bring_back(act: Act, food: Food) -> dict[str, Any]:
    """An `add` of an ingredient removed while the phone was offline brings it back
    (sync protocol 5.9). Returns its Undo snapshot."""
    kitchen = act.kitchen
    before = snapshot(kitchen, [food.id])
    food.removed_at = None
    kitchen.db.flush()
    record_back(kitchen, food)
    bump_foods(kitchen, [food.id], act.batch)
    act.message = f"{food.name} is back in Ingredients."
    return diff(before, snapshot(kitchen, [food.id]))


def _new_food(act: Act, wanted: dict[str, Any]) -> tuple[Food, dict[str, Any], bool]:
    """`new_food` (sync protocol 4.4): the ingredient of that name if there is one, an
    ingredient of that name removed while offline brought back, else a new one. The last
    part is True when the one it gives is counted another way than the phone said, so the
    action's amount means nothing for it (4.4, cabledrawer 18 Oct)."""
    kitchen = act.kitchen
    name = clean(wanted["name"])
    counted_as = wanted.get("counted_as")

    def other_way(food: Food) -> bool:
        return counted_as is not None and food.counted_as != counted_as

    found = _named(kitchen, name)
    if found is not None:
        return found, {}, other_way(found)
    folded = fold(name)
    for removed in kitchen.db.scalars(
        select(Food)
        .where(
            Food.household_id == kitchen.household_id,
            Food.removed_at.is_not(None),
            Food.merged_into_id.is_(None),
        )
        .order_by(Food.removed_at.desc())
    ):
        if fold(removed.name) == folded:
            return removed, _bring_back(act, removed), other_way(removed)
    # Imported here: FoodEdit needs this module.
    from mealwright.history import FoodEdit

    row = table().match(name)
    with FoodEdit(kitchen, [], batch=act.batch) as edit:
        food = Food(
            household_id=kitchen.household_id,
            name=name,
            counted_as=wanted.get("counted_as") or (row.counted_as if row else "weight"),
            staple=bool(wanted.get("staple", False)),
            shop_id=suggested_shop(kitchen, name),
            aisle=guess_aisle(name, row),
            table_key=row.key if row else None,
        )
        kitchen.db.add(food)
        kitchen.db.flush()
        edit.also(food.id)
        # The packet sizes chosen with it (4.4), in the same change, so its Undo takes them too.
        made: set[tuple[str, int]] = set()
        for size in wanted.get("sizes") or []:
            milli = milli_of(size["amount"])
            key = (fold(size["name"]), milli or 0)
            if not milli or milli <= 0 or key in made:
                continue
            made.add(key)
            add_size(kitchen, food, size["name"], milli)
    edit.record("food_created", f"Added {food.name}", food.id)
    return food, {}, False


def _food_for(act: Act, food_id: int) -> tuple[Food | None, dict[str, Any], bool]:
    """The ingredient an `add` names (sync protocol 5.9): merges are followed; one removed
    while offline is brought back (unless its name is someone else's now: then that one);
    one deleted for good gives None. The last part is True when the one it gives is
    counted another way than the one named, so the action's amount means nothing for it."""
    kitchen = act.kitchen
    food = kitchen.db.get(Food, food_id)
    seen: set[int] = set()
    while food is not None and food.merged_into_id is not None and food.id not in seen:
        seen.add(food.id)
        food = kitchen.db.get(Food, food.merged_into_id)
    if food is None or food.household_id != kitchen.household_id:
        return None, {}, False
    if food.removed_at is None:
        return food, {}, False
    live, foods = revive(act, food)
    return live, foods, live.counted_as != food.counted_as


def revive(act: Act, food: Food) -> tuple[Food, dict[str, Any]]:
    """An ingredient removed while the phone was offline, wanted again by an `add` or a
    tick (5.9): if its name (or another of its names) is a live ingredient's now, that
    one; else it is brought back. Returns the ingredient and the Undo snapshot."""
    kitchen = act.kitchen
    taken = _named(kitchen, food.name)
    if taken is None:
        for other in kitchen.db.scalars(select(FoodName).where(FoodName.food_id == food.id)):
            taken = _named(kitchen, other.name)
            if taken is not None:
                break
    if taken is not None:
        return taken, {}
    return food, _bring_back(act, food)


def _amount_state(item: ListItem) -> list[Any]:
    return [item.amount_milli, item.size_id]


def add_item(act: Act) -> None:
    """Add an ingredient to a list, or join a line that is already there (rule L-12).

    A blank amount: the usual size, or 1 for items. Joining adds the amounts up, unless it
    is a real clash between two devices (the adder hadn't seen the line): then the line
    keeps the bigger amount and both adders get note N2."""
    kitchen, payload = act.kitchen, act.payload
    shopping_list = get_list(kitchen, payload["list_id"])
    if shopping_list is None:
        act.ignore("gone")
        return
    act.list_id = shopping_list.id
    item_id = new_id(kitchen, payload.get("item_id"), ListItem)
    foods: dict[str, Any] = {}
    if payload.get("new_food") is not None:
        food, foods, recount = _new_food(act, payload["new_food"])
    else:
        found, foods, recount = _food_for(act, payload["food_id"])
        if found is None:
            name = _gone_name(kitchen, payload["food_id"]) or "That ingredient"
            act.ignore("gone", f"{name} was removed from Ingredients, so it wasn’t added.")
            return
        food = found
    act.food_id = food.id
    typed = recount and payload.get("amount") is not None  # the adder gets N9
    if "shop_id" in payload:
        wanted_shop = payload["shop_id"]
        shop = get_shop(kitchen, wanted_shop) if wanted_shop is not None else None
        shop_id = shop.id if shop else (food.shop_id if wanted_shop is not None else None)
    else:
        shop_id = food.shop_id
    # Counted another way (7.1, 4.4, cabledrawer 18 Oct): never the phone's amount, a blank add's.
    amount_milli = None if recount else milli_of(payload.get("amount"))
    size = None if recount else get_size(kitchen, food, payload.get("size_id"))
    if amount_milli is None:
        amount_milli, size_id = default_amount(kitchen, food)
        size = kitchen.db.get(FoodSize, size_id) if size_id else None
    in_removed_list(act, shopping_list)
    extra = {"foods": foods} if foods else {}
    line = matching_line(kitchen, shopping_list.id, food.id, shop_id)
    if line is not None:
        _join(act, shopping_list, line, food, amount_milli, size, item_id, extra)
        if typed:
            _counted_another_way(act, food, line)
        return
    item = ListItem(
        id=item_id,
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
        version=act.seq,
    )
    kitchen.db.add(item)
    kitchen.db.flush()
    act.item_id = item.id
    act.out["item"] = item
    act.done(
        "item_added",
        f"Added {food.name} to {shopping_list.name}",
        [{"op": "item_made", "item_id": item.id, "state": _amount_state(item), "shop_id": shop_id}],
        food.id,
        **extra,
    )
    if typed:
        _counted_another_way(act, food, item)


def _counted_another_way(act: Act, food: Food, line: ListItem) -> None:
    """N9: the adder's amount was for another way of counting (4.4, 7.1, cabledrawer 18 Oct)."""
    note(
        act,
        "N9",
        act.kitchen.login.id,
        f"{food.name} was already in Ingredients, counted another way, so check the amount.",
        list_id=line.list_id,
        item_id=line.id,
        food_id=food.id,
        undo=act.id,
    )


def _join(
    act: Act,
    shopping_list: ShoppingList,
    line: ListItem,
    food: Food,
    amount_milli: int | None,
    size: FoodSize | None,
    item_id: str,
    extra: dict[str, Any],
) -> None:
    kitchen = act.kitchen
    before = _amount_state(line)
    maker = made_by(kitchen, line.id)
    clash = maker is not None and maker.device_id != act.device_id and unseen(act, maker)
    if clash:
        # The bigger amount stays, with its size (no amount counts as smallest).
        if amount_milli is not None and amount_milli > (line.amount_milli or 0):
            line.amount_milli = amount_milli
            line.size_id = size.id if size else None
        line.hand_edited = True
    elif amount_milli is not None:
        try:
            line.amount_milli = checked((line.amount_milli or 0) + amount_milli)
        except TooBig as err:
            raise Refused("too_big", "That amount is too big.") from err
        if line.size_id is None and line.amount_milli == amount_milli and size is not None:
            line.size_id = size.id
    if line.source == "plan":
        line.hand_edited = True  # typing beside a plan-made line is a hand edit (rule L-5)
    line.version = act.seq
    if act.payload.get("item_id"):
        # The phone's own ID for the item leads to the line it joined (sync protocol 3.2).
        kitchen.db.add(
            ListItem(
                id=item_id,
                household_id=kitchen.household_id,
                list_id=shopping_list.id,
                food_id=food.id,
                shop_id=line.shop_id,
                source="typed",
                added_by_login_id=kitchen.login.id,
                added_by_name=kitchen.login.name,
                merged_into_id=line.id,
                version=act.seq,
            )
        )
    kitchen.db.flush()
    act.status = "merged"
    act.item_id = line.id
    act.out["item"] = line
    act.done(
        "item_added",
        f"Added {food.name} to {shopping_list.name} (joined the line already there)",
        [
            {
                "op": "item_amount",
                "item_id": line.id,
                "old": before,
                "new": _amount_state(line),
                "joined": True,  # Undo leaves the line alone once it is ticked (rule M-1)
            }
        ],
        food.id,
        **extra,
    )
    if clash and maker is not None:
        me = kitchen.login.id
        to = {me: who(maker.login_id, maker.login_name, me)}
        if maker.login_id is not None and maker.login_id != me:
            to[maker.login_id] = who(me, kitchen.login.name, maker.login_id)
        elif maker.login_id == me:
            to[me] = OTHER_PHONE
        for login_id, name in to.items():
            note(
                act,
                "N2",
                login_id,
                f"{name} added {food.name} too",
                list_id=line.list_id,
                item_id=line.id,
                food_id=food.id,
                undo=act.id,
            )


def _last_amount_action(kitchen: Kitchen, item_id: str) -> SyncAction | None:
    return kitchen.db.scalar(
        select(SyncAction)
        .where(
            SyncAction.household_id == kitchen.household_id,
            SyncAction.item_id == item_id,
            or_(
                and_(SyncAction.kind == "set_amount", SyncAction.status == "applied"),
                and_(SyncAction.kind == "move", SyncAction.status == "merged"),
            ),
            SyncAction.undone_by_action_id.is_(None),
        )
        .order_by(SyncAction.seq.desc())
        .limit(1)
    )


def _edit_against_delete(act: Act, item: ListItem, food: Food) -> None:
    """N4 to the editor whose change wasn't kept, because the item was off the list."""
    removal = action_row(act.kitchen, item.deleted_action_id)
    if removal is None or act.plain:
        return
    me = act.kitchen.login.id
    taken = "moved" if removal.kind == "move" else "removed"  # a move can merge a line away
    note(
        act,
        "N4",
        me,
        f"{who(removal.login_id, removal.login_name, me)} had {taken} {food.name},"
        " so your change wasn’t kept.",
        list_id=item.list_id,
        item_id=item.id,
        food_id=food.id,
        undo=removal.id,
    )


def set_amount(act: Act) -> None:
    """Change the amount to buy (the last one received wins). Sets `hand_edited`, so the
    plan (0.6) never overwrites it. On a ticked item it changes only the list, never the
    pantry (that's "Different pack?")."""
    from mealwright.foods import amount_out

    kitchen, payload = act.kitchen, act.payload
    item = get_item(kitchen, payload["item_id"])
    if item is None:
        act.ignore("gone")
        return
    act.item_id, act.list_id, act.food_id = item.id, item.list_id, item.food_id
    food = kitchen.db.get(Food, item.food_id)
    if food is None:  # pragma: no cover (an ingredient's items go with it)
        act.ignore("gone")
        return
    shopping_list = get_list(kitchen, item.list_id)
    amount_milli = milli_of(payload["amount"])
    size = get_size(kitchen, food, payload.get("size_id"))
    act.out["item"] = item
    if item.deleted_at is not None:
        act.ignore("deleted")
        _edit_against_delete(act, item, food)
        return
    new_size = size.id if size else None
    if (item.amount_milli, item.size_id) == (amount_milli, new_size):
        act.ignore("no_change")
        return
    if shopping_list is not None:
        in_removed_list(act, shopping_list)
    overwritten = _last_amount_action(kitchen, item.id)
    before = _amount_state(item)
    item.amount_milli = amount_milli
    item.size_id = new_size
    item.hand_edited = True
    item.version = act.seq
    act.done(
        "item_amount",
        f"Changed {food.name} on the list",
        [{"op": "item_amount", "item_id": item.id, "old": before, "new": _amount_state(item)}],
        food.id,
    )
    if (
        overwritten is not None
        and overwritten.device_id != act.device_id
        and unseen(act, overwritten)
        and amount_milli is not None
    ):
        short = amount_out(food, amount_milli, size).short.removesuffix(f"{NBSP}left")
        note(
            act,
            "N3",
            overwritten.login_id,
            f"{who(kitchen.login.id, kitchen.login.name, overwritten.login_id)}"
            f" changed {food.name} to {short}",
            list_id=item.list_id,
            item_id=item.id,
            food_id=food.id,
            undo=act.id,
        )


def tombstone(kitchen: Kitchen, item: ListItem, seq: int, action: str) -> None:
    item.deleted_at = utcnow()
    item.deleted_by_name = kitchen.login.name
    item.deleted_action_id = action
    item.version = seq


def _lost_to_delete(act: Act, item: ListItem, food: Food) -> None:
    """A delete from someone who hadn't seen later edits or ticks: N4 to the editors, N1
    to the tickers whose purchase put stock in (rules L-6, L-9)."""
    if act.plain or act.seen is None:
        return
    kitchen = act.kitchen
    me, my_name = kitchen.login.id, kitchen.login.name
    later = kitchen.db.scalars(
        select(SyncAction).where(
            SyncAction.household_id == kitchen.household_id,
            SyncAction.item_id == item.id,
            SyncAction.seq > act.seen,
            SyncAction.kind.in_(("set_amount", "tick", "found_at_home")),
            SyncAction.status == "applied",
            SyncAction.undone_by_action_id.is_(None),
        )
    ).all()
    told: set[tuple[str, int | None]] = set()
    for row in later:
        if row.device_id == act.device_id or (row.kind, row.login_id) in told:
            continue
        if row.kind == "set_amount":
            told.add((row.kind, row.login_id))
            note(
                act,
                "N4",
                row.login_id,
                f"{who(me, my_name, row.login_id)} had removed {food.name},"
                " so your change wasn’t kept.",
                list_id=item.list_id,
                item_id=item.id,
                food_id=food.id,
                undo=act.id,
            )
            continue
        tick = kitchen.db.get(ListTick, (kitchen.household_id, row.id))
        if tick is None or tick.reversed_at is not None or tick.change_id is None:
            continue
        told.add((row.kind, row.login_id))
        note(
            act,
            "N1",
            row.login_id,
            f"{who(me, my_name, row.login_id)} had removed this."
            " Your tick still went into the pantry.",
            list_id=item.list_id,
            item_id=item.id,
            food_id=food.id,
            undo=row.id,
        )


def delete_item(act: Act) -> None:
    """Take an item off the list, leaving a tombstone so an old queue can't bring it back."""
    kitchen = act.kitchen
    item = get_item(kitchen, act.payload["item_id"])
    if item is None:
        act.ignore("gone")
        return
    act.item_id, act.list_id, act.food_id = item.id, item.list_id, item.food_id
    if item.deleted_at is not None:
        act.ignore("deleted")
        return
    food = kitchen.db.get(Food, item.food_id)
    name = food.name if food else ""
    shopping_list = get_list(kitchen, item.list_id)
    if shopping_list is not None:
        in_removed_list(act, shopping_list)
    tombstone(kitchen, item, act.seq, act.id)
    act.done(
        "item_deleted",
        f"Took {name} off the list",
        [{"op": "item_deleted", "item_ids": [item.id]}],
        item.food_id,
    )
    if food is not None:
        _lost_to_delete(act, item, food)


def _where_to(kitchen: Kitchen, list_id: str, shop_id: int | None, moved_list: bool) -> str:
    """The words for where a line went: the list when the list changed, else the shop."""
    if moved_list:
        found = get_list(kitchen, list_id)
        return found.name if found else "the list"
    shop = get_shop(kitchen, shop_id) if shop_id is not None else None
    return shop.name if shop else "Any shop"


def _ticked_first(act: Act, item: ListItem, food: Food) -> None:
    """N10: a move that came after someone's tick is not made (only unticked lines move)."""
    from mealwright.ticks import ticks_of  # ticks.py imports this module

    kitchen = act.kitchen
    # The first in server order, not by the phone's time: a back-dated tick synced later
    # must not become "who ticked first".
    standing = ticks_of(kitchen, item.id)
    tick = standing[0] if standing else None
    if tick is None or tick.device_id == act.device_id or act.plain:
        return
    me = kitchen.login.id
    note(
        act,
        "N10",
        me,
        f"{who(tick.login_id, tick.login_name, me)} had ticked {food.name}, so it wasn’t moved.",
        list_id=item.list_id,
        item_id=item.id,
        food_id=food.id,
    )


def _last_move(kitchen: Kitchen, item_id: str) -> SyncAction | None:
    return kitchen.db.scalar(
        select(SyncAction)
        .where(
            SyncAction.household_id == kitchen.household_id,
            SyncAction.item_id == item_id,
            SyncAction.kind == "move",
            SyncAction.status == "applied",
            SyncAction.undone_by_action_id.is_(None),
        )
        .order_by(SyncAction.seq.desc())
        .limit(1)
    )


def move_item(act: Act) -> None:
    """Move an unticked line to another shop or list (docs/dev/sync-protocol.md 4.2, rules
    M-1 to M-7). If the ingredient is already on the other shop or list, the amounts add up
    and the moved line is taken off (its tombstone says the move did it). Anyone can Undo."""
    kitchen, payload = act.kitchen, act.payload
    item = get_item(kitchen, payload["item_id"])
    if item is None:
        act.ignore("gone")
        return
    act.item_id, act.list_id, act.food_id = item.id, item.list_id, item.food_id
    food = kitchen.db.get(Food, item.food_id)
    if food is None or not food_is_shown(kitchen, item.food_id):
        act.ignore("gone")
        return
    act.out["item"] = item
    if item.deleted_at is not None:
        act.ignore("deleted")
        _edit_against_delete(act, item, food)
        return
    target = get_list(kitchen, payload["list_id"])
    if target is None or target.removed_at is not None:
        act.ignore("gone", f"That list was removed, so {food.name} wasn’t moved.")
        return
    shop_id: int | None = payload["shop_id"]
    if shop_id is not None and get_shop(kitchen, shop_id) is None:
        act.ignore("gone", f"That shop was removed, so {food.name} wasn’t moved.")
        return
    if standing_ticks(kitchen, [item.id]):
        act.ignore("ticked")
        _ticked_first(act, item, food)
        return
    if (item.list_id, item.shop_id) == (target.id, shop_id):
        act.ignore("no_change")
        return
    source = get_list(kitchen, item.list_id)
    if source is not None:
        in_removed_list(act, source)
    moved_list = item.list_id != target.id
    where = _where_to(kitchen, target.id, shop_id, moved_list)
    overwritten = _last_move(kitchen, item.id)
    line = matching_line(kitchen, target.id, item.food_id, shop_id)
    act.list_id = target.id
    if line is not None and line.id != item.id:
        ops: list[dict[str, Any]] = []
        before = _amount_state(line)
        if item.amount_milli is not None:
            had = line.amount_milli
            try:
                line.amount_milli = checked((had or 0) + item.amount_milli)
            except TooBig as err:
                raise Refused("too_big", "That amount is too big.") from err
            if had is None:
                line.size_id = item.size_id
            line.hand_edited = True
            line.version = act.seq
            ops.append(
                {
                    "op": "item_amount",
                    "item_id": line.id,
                    "old": before,
                    "new": _amount_state(line),
                    "joined": True,
                }
            )
        tombstone(kitchen, item, act.seq, act.id)
        ops.append({"op": "item_deleted", "item_ids": [item.id], "joined_into": line.id})
        kitchen.db.flush()
        act.status = "merged"
        act.item_id = line.id
        act.out["item"] = line
        act.done("item_moved", f"Moved {food.name} to {where}", ops, food.id)
        return
    old = [item.list_id, item.shop_id]
    item.list_id, item.shop_id = target.id, shop_id
    if item.source == "plan":
        item.hand_edited = True  # a plan-made line a person moved is theirs now (rule L-5)
    item.version = act.seq
    kitchen.db.flush()
    act.done(
        "item_moved",
        f"Moved {food.name} to {where}",
        [{"op": "item_moved", "item_id": item.id, "old": old, "new": [target.id, shop_id]}],
        food.id,
    )
    if (
        overwritten is not None
        and overwritten.device_id != act.device_id
        and unseen(act, overwritten)
    ):
        me = kitchen.login.id
        note(
            act,
            "N10",
            overwritten.login_id,
            f"{who(me, kitchen.login.name, overwritten.login_id)} moved {food.name} to {where}",
            list_id=target.id,
            item_id=item.id,
            food_id=food.id,
            undo=act.id,
        )


def standing_ticks(kitchen: Kitchen, item_ids: Iterable[str]) -> set[str]:
    """Items with at least one tick that hasn't been reversed. The item's `ticked_at` copy
    is kept in step with `list_tick`; this reads both so the two can't disagree here."""
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


def ticked_items(
    kitchen: Kitchen, shopping_list: ShoppingList, item_ids: list[str] | None
) -> list[ListItem]:
    """The live items on a list with a standing tick (only those named, if named)."""
    query = select(ListItem).where(
        ListItem.household_id == kitchen.household_id,
        ListItem.list_id == shopping_list.id,
        ListItem.deleted_at.is_(None),
        ListItem.merged_into_id.is_(None),
    )
    if item_ids is not None:
        query = query.where(ListItem.id.in_(item_ids))
    candidates = list(kitchen.db.scalars(query.order_by(ListItem.added_at, ListItem.id)))
    standing = standing_ticks(kitchen, [i.id for i in candidates])
    return [i for i in candidates if i.ticked_at is not None or i.id in standing]


def clear_ticked(act: Act) -> None:
    """Remove the listed ticked items from a list, as one action with one Undo. An item
    that was unticked meanwhile stays (rule L-19)."""
    kitchen = act.kitchen
    shopping_list = get_list(kitchen, act.payload["list_id"])
    if shopping_list is None:
        act.ignore("gone")
        return
    act.list_id = shopping_list.id
    items = ticked_items(kitchen, shopping_list, act.payload["item_ids"])
    act.out["cleared"] = items
    if not items:
        act.ignore("not_ticked")
        return
    in_removed_list(act, shopping_list)
    for item in items:
        tombstone(kitchen, item, act.seq, act.id)
    n = len(items)
    act.done(
        "item_deleted",
        f"Cleared {n} ticked item{'s' if n != 1 else ''} from {shopping_list.name}",
        [{"op": "item_deleted", "item_ids": [i.id for i in items]}],
    )


def dismiss_note(act: Act) -> None:
    """Hide a note (its close button). Someone else's note, or one that's gone → ignored
    gone, quietly."""
    kitchen = act.kitchen
    row = kitchen.db.get(ListNote, act.payload["note_id"])
    if (
        row is None
        or row.household_id != kitchen.household_id
        or row.for_login_id != kitchen.login.id
        or row.gone_at is not None
    ):
        act.ignore("gone")
        return
    act.list_id, act.item_id = row.list_id, row.item_id
    row.gone_at = utcnow()
    row.version = act.seq


# --- Undo ----------------------------------------------------------------------------------------


def _same[T: (ShoppingList, ListItem)](row: T | None, kitchen: Kitchen) -> TypeIs[T]:
    return row is not None and row.household_id == kitchen.household_id


def _ticked_since(kitchen: Kitchen, item: ListItem) -> bool:
    return item.ticked_at is not None or bool(standing_ticks(kitchen, [item.id]))


def undo_shopping(kitchen: Kitchen, change: Change, tally: Tally, batch: Batch, action: str) -> int:
    """Reverse a list change's list part. Each part is put back only if it still looks the
    way the change left it (like food changes). Rows touched get the Undo's counter number,
    which is returned. `action` is the Undo's action ID."""
    data = change.undo_data or {}
    seq = batch.number()
    db = kitchen.db
    for op in data.get("shopping", []):
        kind = op["op"]
        if kind in ("list_made", "list_name", "list_removed"):
            row = db.get(ShoppingList, op["list_id"])
            if not _same(row, kitchen):
                tally.skipped += 1
                continue
            if kind == "list_made":
                row.removed_at = row.removed_at or utcnow()
                row.removed_action_id = action
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
            if not _same(item, kitchen):
                tally.skipped += 1
                continue
            if item.deleted_at is not None:
                tally.done += 1  # already off the list
            elif (
                item.ticked_at is None
                and _amount_state(item) == op.get("state")
                and (item.shop_id == op.get("shop_id"))
            ):
                tombstone(kitchen, item, seq, action)
                tally.done += 1
            else:  # ticked, or someone changed it since: leave it
                tally.skipped += 1
        elif kind == "item_amount":
            item = db.get(ListItem, op["item_id"])
            if not _same(item, kitchen) or item.deleted_at:
                tally.skipped += 1
                continue
            if op.get("joined") and _ticked_since(kitchen, item):
                tally.skipped += 1  # the line a move joined was bought since (rule M-1)
                tally.joined_bought = True
                continue
            if _amount_state(item) == op["new"]:
                item.amount_milli, item.size_id = op["old"]
                item.version = seq
                tally.done += 1
            elif _amount_state(item) == op["old"]:
                tally.done += 1
            else:
                tally.skipped += 1
        elif kind in ("item_food", "item_shop", "item_place"):
            # A merge moved the item to the kept ingredient; a usual-shop change moved it
            # to the new shop; a put-away chose its place.
            column = {"item_food": "food_id", "item_shop": "shop_id"}.get(kind, "put_away_place_id")
            item = db.get(ListItem, op["item_id"])
            if not _same(item, kitchen):
                tally.skipped += 1
            elif getattr(item, column) == op["new"]:
                setattr(item, column, op["old"])
                item.version = seq
                tally.done += 1
            elif getattr(item, column) == op["old"]:
                tally.done += 1
            else:
                tally.skipped += 1
        elif kind == "tick_place":
            tick = db.get(ListTick, (kitchen.household_id, op["tick_id"]))
            if tick is None:
                tally.skipped += 1
            elif tick.place_id == op["new"]:
                tick.place_id = op["old"]
                _touch_item(kitchen, tick.item_id, seq)
                tally.done += 1
            else:
                tally.done += tick.place_id == op["old"]
                tally.skipped += tick.place_id != op["old"]
        elif kind == "tick_bought":
            tick = db.get(ListTick, (kitchen.household_id, op["tick_id"]))
            if tick is None:
                tally.skipped += 1
            elif [tick.bought_milli, tick.bought_size_id] == op["new"]:
                tick.bought_milli, tick.bought_size_id = op["old"]
                _touch_item(kitchen, tick.item_id, seq)
                tally.done += 1
            else:  # already as it was (the put-back restored it, 7.5): nothing skipped
                at_old = [tick.bought_milli, tick.bought_size_id] == op["old"]
                tally.done += at_old
                tally.skipped += not at_old
        elif kind == "item_moved":
            item = db.get(ListItem, op["item_id"])
            back = get_list(kitchen, op["old"][0])
            if (
                not _same(item, kitchen)
                or item.deleted_at is not None
                or item.ticked_at is not None  # only unticked lines move (rule M-1)
                or back is None
                or back.removed_at is not None
            ):
                tally.skipped += 1
            elif [item.list_id, item.shop_id] == op["new"]:
                item.list_id, item.shop_id = op["old"]
                item.version = seq
                tally.done += 1
            elif [item.list_id, item.shop_id] == op["old"]:
                tally.done += 1
            else:
                tally.skipped += 1
        elif kind == "item_deleted":
            joined = db.get(ListItem, op["joined_into"]) if op.get("joined_into") else None
            if _same(joined, kitchen) and _ticked_since(kitchen, joined):
                tally.skipped += len(op["item_ids"])  # its amount was bought: stay joined
                tally.joined_bought = True
                continue
            for item_id in op["item_ids"]:
                item = db.get(ListItem, item_id)
                if not _same(item, kitchen):
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
    notes_gone(kitchen, data.get("action"), seq)
    return seq


def _touch_item(kitchen: Kitchen, item_id: str, seq: int) -> None:
    item = kitchen.db.get(ListItem, item_id)
    if item is not None:
        item.version = seq


def log_undo(batch: Batch, original: Change, undo_change: Change, kind: str = "undo") -> SyncAction:
    """The sync-log row for an Undo from Pantry → Recent changes, and the mark on the
    action it undid (sync protocol 5.8)."""
    kitchen = batch.kitchen
    undone_action = (original.undo_data or {}).get("action")
    row = server_action(batch, kind, {"undoes": undone_action}, undo_change)
    if undone_action:
        undone = action_row(kitchen, undone_action)
        if undone is not None:
            undone.undone_by_action_id = row.id
            row.list_id, row.item_id = undone.list_id, undone.item_id
    return row
