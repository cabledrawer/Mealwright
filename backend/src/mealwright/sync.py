"""Applying list actions (docs/dev/sync-protocol.md sections 4, 5 and 9).

`run` applies one action: the repeat check (5.3), its own savepoint (so a refused action
never undoes the others in its batch), the next counter number, the handler, and the
`sync_action` row with the stored result. `plain` does the same for one of the plain
one-at-a-time list requests, so online and offline writes share one path (5.1).
"""

import uuid
from collections.abc import Callable
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import status
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    TypeAdapter,
    ValidationError,
    field_validator,
    model_validator,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from mealwright import shopping
from mealwright.api.v1.context import Kitchen
from mealwright.errors import Problem
from mealwright.history import as_utc
from mealwright.household import undo_window
from mealwright.models import Change, ListItem, ShoppingList, SyncAction, utcnow
from mealwright.names import clean, size_name
from mealwright.shopping import Act, Batch, Refused

KEY_REUSED = "That change ID was already used for something else."
TOO_OLD = "Too late to undo: changes can be undone for 7 days."
MAX_ACTIONS = 100

UUID_PATTERN = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
NewId = Annotated[str, Field(pattern=UUID_PATTERN)]  # a new phone-made list or item ID
ActionId = Annotated[str, Field(pattern=r"^[A-Za-z0-9._:-]{1,64}$")]
RowId = Annotated[str, Field(min_length=1, max_length=64)]
# A base amount (g, ml or items), up to 3 decimal places. Over 1,000,000 → refused too_big.
Amount = Annotated[Decimal, Field(gt=0, decimal_places=3, max_digits=20)]
ListName = Annotated[str, Field(min_length=1, max_length=60)]


def _name(value: str) -> str:
    cleaned = clean(value)
    if not cleaned:
        raise ValueError("Please type a name.")
    return cleaned


# --- The action kinds (4.2) ----------------------------------------------------------------------


class ActionBase(BaseModel):
    """Every action has these. A field a kind doesn't take → refused bad_action."""

    model_config = ConfigDict(extra="forbid")

    id: ActionId
    made_at: datetime
    seen: int = Field(ge=0)  # the device's cursor when the action was made
    device_id: NewId | None = None  # default: the batch's


class CreateList(ActionBase):
    kind: Literal["create_list"]
    list_id: NewId
    name: ListName

    _clean = field_validator("name")(_name)


class RenameListAction(ActionBase):
    kind: Literal["rename_list"]
    list_id: RowId
    name: ListName

    _clean = field_validator("name")(_name)


class RemoveList(ActionBase):
    kind: Literal["remove_list"]
    list_id: RowId


class NewSizeAction(BaseModel):
    """A packet size chosen in "How do you count it?": packet = 500 g (4.4). The name needs
    letters in it, like the editor's "Add a size"; the amount is in base units."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=40)]
    amount: Amount

    _clean = field_validator("name")(size_name)


class NewFoodAction(BaseModel):
    """A new ingredient typed in the add box ("How do you count it?")."""

    model_config = ConfigDict(extra="forbid")

    name: Annotated[str, Field(min_length=1, max_length=100)]
    counted_as: Literal["weight", "volume", "count"]
    staple: bool = False
    # Used only when this action makes the ingredient; ignored when the name is taken.
    sizes: Annotated[list[NewSizeAction], Field(max_length=10)] = Field(default_factory=list)

    _clean = field_validator("name")(_name)


class Add(ActionBase):
    """`food_id` or `new_food`. `amount` omitted or null = blank. `shop_id` omitted = the
    ingredient's usual shop; null = Any shop."""

    kind: Literal["add"]
    list_id: RowId
    item_id: NewId
    food_id: int | None = None
    new_food: NewFoodAction | None = None
    amount: Amount | None = None
    size_id: int | None = None
    shop_id: int | None = None

    @model_validator(mode="after")
    def _one_food(self) -> Add:
        if (self.food_id is None) == (self.new_food is None):
            raise ValueError("An add needs food_id or new_food.")
        return self


class SetAmount(ActionBase):
    kind: Literal["set_amount"]
    item_id: RowId
    amount: Amount
    size_id: int | None = None


class Delete(ActionBase):
    kind: Literal["delete"]
    item_id: RowId


class Tick(ActionBase):
    kind: Literal["tick"]
    item_id: RowId


class Untick(ActionBase):
    kind: Literal["untick"]
    item_id: RowId
    tick_ids: list[ActionId] = Field(max_length=100)


class PutAway(ActionBase):
    kind: Literal["put_away"]
    item_id: RowId
    place_id: int
    tick_ids: list[ActionId] = Field(max_length=100)
    use_by: date | None = None


class DifferentPack(ActionBase):
    kind: Literal["different_pack"]
    item_id: RowId
    tick_id: ActionId
    count: int = Field(ge=1, le=99)
    pack: Amount
    size_id: int | None = None


class ClearTickedAction(ActionBase):
    kind: Literal["clear_ticked"]
    list_id: RowId
    item_ids: list[RowId] = Field(max_length=500)


class AnswerDoubleTick(ActionBase):
    kind: Literal["answer_double_tick"]
    question_id: int
    answer: Literal["two", "one"]


class DismissNote(ActionBase):
    kind: Literal["dismiss_note"]
    note_id: int


class UndoAction(ActionBase):
    kind: Literal["undo"]
    undoes: ActionId


Action = Annotated[
    CreateList
    | RenameListAction
    | RemoveList
    | Add
    | SetAmount
    | Delete
    | Tick
    | Untick
    | PutAway
    | DifferentPack
    | ClearTickedAction
    | AnswerDoubleTick
    | DismissNote
    | UndoAction,
    Field(discriminator="kind"),
]
ACTION = TypeAdapter(Action)


def number(value: Decimal) -> int | float:
    """A base amount for the stored payload: whole numbers as int."""
    return int(value) if value == value.to_integral_value() else float(value)


def payload_of(action: ActionBase) -> dict[str, Any]:
    """The stored payload: the kind's own fields, JSON-ready (what the repeat check hashes)."""
    data = action.model_dump(
        mode="json", exclude={"id", "kind", "made_at", "seen", "device_id"}, exclude_unset=True
    )
    for key in ("amount", "pack"):
        value = getattr(action, key, None)
        if isinstance(value, Decimal):
            data[key] = number(value)
    return data


# --- Applying one action -------------------------------------------------------------------------


class Repeat(Exception):
    """A plain request that turned out to be a repeat (another request recorded it first)."""

    def __init__(self, change: Change | None) -> None:
        super().__init__("repeat")
        self.change = change


def refused(action_id: str, reason: str, message: str) -> dict[str, Any]:
    return {
        "id": action_id,
        "seq": None,
        "status": "refused",
        "reason": reason,
        "repeat": False,
        "item_id": None,
        "change_id": None,
        "message": message,
        "food_id": None,
    }


def _repeat(act: Act, stored: SyncAction, hashed: str) -> dict[str, Any]:
    if stored.kind == act.kind and stored.payload_hash == hashed:
        result = dict(stored.result or {})  # emptied after the history length (3.9)
        result.setdefault("id", stored.id)
        result.setdefault("seq", stored.seq)
        result.setdefault("status", stored.status)
        result.setdefault("reason", stored.reason)
        result.setdefault("item_id", stored.item_id)
        result.setdefault("change_id", stored.change_id)
        result.setdefault("message", None)
        result.setdefault("food_id", None)
        return {**result, "repeat": True}
    return refused(act.id, "key_reused", KEY_REUSED)


def run(act: Act, handler: Callable[[Act], None]) -> dict[str, Any]:
    """Apply one action (5.2, 5.3). Returns its result (5.4)."""
    kitchen = act.kitchen
    db = kitchen.db
    hid = kitchen.household_id
    hashed = shopping.payload_hash(act.payload)
    stored = shopping.action_row(kitchen, act.id)
    if stored is not None:
        return _repeat(act, stored, hashed)
    used = db.scalar(
        select(Change.id).where(Change.household_id == hid, Change.idempotency_key == act.id)
    )
    if used is not None:
        return refused(act.id, "key_reused", KEY_REUSED)
    before = db.scalar(select(func.max(Change.id)).where(Change.household_id == hid)) or 0
    savepoint = db.begin_nested()
    act.seq = act.batch.take()
    old_key, old_once = kitchen.idempotency_key, kitchen.key_once
    kitchen.idempotency_key, kitchen.key_once = act.id, True
    try:
        handler(act)
        db.flush()
        made = list(
            db.scalars(
                select(Change.id)
                .where(Change.household_id == hid, Change.id > before)
                .order_by(Change.id)
            )
        )
        shown = act.change or act.main_change
        result = {
            "id": act.id,
            "seq": act.seq,
            "status": act.status,
            "reason": act.reason,
            "item_id": act.item_id,
            "change_id": shown.id if shown else None,
            "message": act.message,
            "food_id": act.food_id,
            "changes": made,
        }
        main = act.main_change or act.change
        db.add(
            SyncAction(
                household_id=hid,
                id=act.id,
                seq=act.seq,
                kind=act.kind,
                login_id=kitchen.login.id,
                login_name=kitchen.login.name,
                device_id=act.device_id,
                list_id=act.list_id,
                item_id=act.item_id,
                seen=act.seen,
                made_at=act.made_at,
                applied_at=utcnow(),
                payload=act.payload,
                payload_hash=hashed,
                status=act.status,
                reason=act.reason,
                result=result,
                change_id=main.id if main else None,
            )
        )
        db.flush()
        savepoint.commit()
        return {**result, "repeat": False}
    except Refused as no:
        savepoint.rollback()
        act.batch.give_back()
        if act.plain:
            raise Problem(status.HTTP_409_CONFLICT, no.reason, no.message) from no
        return refused(act.id, no.reason, no.message)
    except IntegrityError:
        # Someone else recorded this ID in between (the lock should prevent it).
        savepoint.rollback()
        act.batch.give_back()
        stored = shopping.action_row(kitchen, act.id)
        if stored is None:
            raise
        return _repeat(act, stored, hashed)
    except Problem as problem:
        savepoint.rollback()
        act.batch.give_back()
        if act.plain:
            raise
        return refused(act.id, "bad_action", problem.detail)
    finally:
        kitchen.idempotency_key, kitchen.key_once = old_key, old_once


def plain(
    kitchen: Kitchen, kind: str, payload: dict[str, Any], handler: Callable[[Act], None]
) -> Act:
    """One of the plain one-at-a-time list requests, handled as an action (5.1): its ID is
    the request's Idempotency-Key, or a new one."""
    batch = Batch(kitchen)
    act = Act(batch=batch, id=batch.action, kind=kind, payload=payload, plain=True)
    result = run(act, handler)
    if result["status"] == "refused":
        raise Problem(status.HTTP_409_CONFLICT, result["reason"], result["message"])
    if result.get("repeat"):
        found = kitchen.db.get(Change, result.get("change_id") or 0)
        raise Repeat(found)
    batch.finish()
    return act


# --- Undo (section 9) ----------------------------------------------------------------------------

CANNOT_UNDO = ("undo", "dismiss_note", "untick_by_undo", "place_by_undo", "purge")


def pressed_at(act: Act, applied_at: datetime) -> datetime:
    """When the person pressed Undo, corrected for the phone's clock (section 9)."""
    now = utcnow()
    if act.made_at is None or act.sent_at is None:
        return now
    moment = as_utc(act.made_at) + (now - as_utc(act.sent_at))
    return min(max(moment, as_utc(applied_at)), now)


def undo(act: Act) -> None:
    """`undo {undoes}`: reverse that action, by anyone in the household (section 9)."""
    from mealwright.api.v1.changes import undo_change

    kitchen = act.kitchen
    target = shopping.action_row(kitchen, act.payload["undoes"])
    if target is None:
        act.ignore("nothing_to_undo")
        return
    act.list_id, act.item_id = target.list_id, target.item_id
    if target.kind in CANNOT_UNDO:
        act.ignore("cannot_undo")
        return
    if target.status == "ignored":
        act.ignore("nothing_to_undo")
        return
    if target.undone_by_action_id is not None:
        act.ignore("already_undone")
        return
    window: timedelta = undo_window(kitchen.household)
    if pressed_at(act, target.applied_at) >= as_utc(target.applied_at) + window:
        act.ignore("too_old", TOO_OLD)
        return
    if _tidied(kitchen, target):
        act.ignore("gone")  # its list or item was tidied away for good (5.9)
        return
    from mealwright import ticks

    if target.kind in ticks.TICK_KINDS:
        ticks.undo(act, target)
        return
    change = kitchen.db.get(Change, target.change_id) if target.change_id else None
    if change is None:
        act.ignore("nothing_to_undo")
        return
    if change.undone_by_change_id is not None:
        act.ignore("already_undone")
        return
    done = undo_change(kitchen, change, act.batch, act.id)
    act.main_change = done
    act.food_id = change.food_id
    target.undone_by_action_id = act.id
    data = done.undo_data or {}
    if data.get("result") != "done":
        act.message = data.get("message")


def _tidied(kitchen: Kitchen, target: SyncAction) -> bool:
    """Is the list or item the action named gone for good (tidied away, 3.9)?"""
    hid = kitchen.household_id
    if target.list_id is not None:
        found = kitchen.db.get(ShoppingList, target.list_id)
        if found is None or found.household_id != hid:
            return True
    if target.item_id is not None:
        item = kitchen.db.get(ListItem, target.item_id)
        if item is None or item.household_id != hid:
            return True
    return False


HANDLERS: dict[str, Callable[[Act], None]] = {
    "create_list": shopping.make_list,
    "rename_list": shopping.rename_list,
    "remove_list": shopping.remove_list,
    "add": shopping.add_item,
    "set_amount": shopping.set_amount,
    "delete": shopping.delete_item,
    "clear_ticked": shopping.clear_ticked,
    "dismiss_note": shopping.dismiss_note,
    "undo": undo,
}


def _handlers() -> dict[str, Callable[[Act], None]]:
    from mealwright import ticks

    return {**HANDLERS, **ticks.HANDLERS}


# --- A batch (4.1) -------------------------------------------------------------------------------


def apply_batch(
    kitchen: Kitchen, device_id: str, sent_at: datetime, actions: list[Any]
) -> list[dict[str, Any]]:
    """Apply a batch's actions in order, under one lock. Returns a result for each."""
    batch = Batch(kitchen, action=str(uuid.uuid4()))
    handlers = _handlers()
    results = []
    for raw in actions:
        given = raw.get("id") if isinstance(raw, dict) else None
        action_id = given if isinstance(given, str) else ""
        try:
            action = ACTION.validate_python(raw)
        except ValidationError as err:
            first = err.errors()[0]
            where = ".".join(str(part) for part in first["loc"])
            message = f"That change isn't valid ({where}: {first['msg']})."
            results.append(refused(action_id[:64], "bad_action", message[:300]))
            continue
        act = Act(
            batch=batch,
            id=action.id,
            kind=action.kind,
            payload=payload_of(action),
            device_id=action.device_id or device_id,
            seen=action.seen,
            made_at=action.made_at,
            sent_at=sent_at,
        )
        handler = handlers.get(action.kind)
        if handler is None:  # pragma: no cover (every kind has a handler)
            results.append(refused(action.id, "bad_action", "That kind of change isn't known."))
            continue
        results.append(run(act, handler))
    batch.finish()
    return results
