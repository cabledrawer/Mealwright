"""Offline sync: a batch of list actions, and catching up (docs/dev/sync-protocol.md 4 and 5).

`POST /shopping/actions` applies a phone's queued actions in order, under the household's
lock, and answers with a result for each plus everything that changed since the phone's
cursor. `GET /shopping/sync?since=N` is the catching-up half on its own.
"""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, status
from pydantic import BaseModel, Field, SkipValidation
from sqlalchemy import false, select, true

from mealwright import sync, ticks
from mealwright.aisles import AISLE_KEYS, AISLE_LABELS, AISLES, DEFAULT_AISLE
from mealwright.amounts import MILLI, NBSP
from mealwright.api.v1.context import Here, Kitchen
from mealwright.api.v1.schemas import ChangeOut, PackLineOut, Who
from mealwright.auth import SameOrigin
from mealwright.errors import Problem, StoredInt
from mealwright.foods import PackReads, amount_out, change_out, pack_line_out
from mealwright.models import (
    Change,
    DoubleTick,
    Food,
    FoodSize,
    ListItem,
    ListNote,
    ListTick,
    Login,
    Member,
    Place,
    Shop,
    ShoppingList,
    SyncAction,
)
from mealwright.people import can_sign_in
from mealwright.shopping import OTHER_PHONE

router = APIRouter(tags=["shopping"], dependencies=[SameOrigin])

# The device ID is a random UUID (3.8), checked as the actions' own `device_id` is.
DeviceId = Annotated[str, Field(pattern=sync.UUID_PATTERN)]


class Refusal(BaseModel):
    """A whole batch turned away (5.6): nothing in it was applied."""

    detail: str  # a plain sentence
    code: str


# --- The batch (4.1, 5.4) ------------------------------------------------------------------------


class Envelope(BaseModel):
    protocol: StoredInt  # always 1 in /api/v1
    device_id: DeviceId
    login_id: StoredInt  # the login that queued these actions
    since: StoredInt = Field(ge=0)  # the device's cursor
    sent_at: datetime  # the device's clock when it sent the batch (Undo's window, section 9)
    # Each action is checked on its own: a malformed one is refused, the rest still apply.
    actions: list[SkipValidation[sync.Action]]


class ResultOut(BaseModel):
    id: str
    seq: int | None  # the counter number it took; null if refused
    status: Literal["applied", "merged", "ignored", "refused"]
    reason: str | None
    repeat: bool  # this ID was already recorded: the stored result, nothing applied again
    item_id: str | None  # for `merged`, the line it joined
    food_id: int | None  # for `add`, the ingredient the item is for
    change: ChangeOut | None  # the pantry or list change, for Undo from Recent changes
    message: str | None  # a sentence to show (partial Undo, brought back, refusal)


# --- Catching up (5.5) ---------------------------------------------------------------------------


class ListRow(BaseModel):
    id: str
    name: str
    main: bool
    position: int
    removed: bool
    version: int


class Bought(BaseModel):
    amount: int | float  # base amount: g, ml or items
    display: str  # as-sold wording, "1 bunch"


class TickRow(BaseModel):
    id: str  # the tick action's ID
    by: Who
    at: datetime
    place_id: int | None
    bought: Bought | None  # null: a staple or an item with no amount (no stock)
    standing: bool  # false once reversed (untick, "Just 1", Undo)
    found: bool  # "Already have it": found at home, not bought


class ItemRow(BaseModel):
    id: str
    list_id: str
    food_id: int
    shop_id: int | None
    amount: int | float | None  # base amount: g, ml or items
    size_id: int | None
    display: str | None  # as-sold wording, "1 bunch"
    pack: PackLineOut | None  # whole packs to buy and the need (F120); null: nothing to say
    source: str
    hand_edited: bool
    put_away_place_id: int | None
    ticks: list[TickRow]
    added_by: Who
    deleted: Literal[False]
    merged_into_id: str | None  # an add that joined this line (hidden; follow it)
    version: int


class Tombstone(BaseModel):
    """A deleted item. Shown faintly in its shop: "Paneer · removed by Remy" (16.10)."""

    id: str
    list_id: str
    deleted: Literal[True]
    version: int
    food_id: int
    shop_id: int | None
    # The login's name, or "Your other phone" for your own login on another device.
    removed_by: str | None


class NoteRow(BaseModel):
    id: int
    list_id: str
    item_id: str | None
    food_id: int | None
    text: str
    undo: str | None  # the action ID its Undo undoes
    gone: bool
    version: int


class QuestionRow(BaseModel):
    id: int
    list_id: str
    item_id: str
    title: str  # "Did you buy 2?"
    text: str
    yes: str  # "Yes, 2"
    no: str  # "Just 1"
    open: bool
    version: int


class SizeRow(BaseModel):
    id: int
    name: str
    plural: str
    amount: int | float  # base amount: g, ml or items
    usual: bool
    added_when_shopping: bool


class FoodRow(BaseModel):
    id: int
    name: str
    other_names: list[str]
    counted_as: str
    staple: bool
    aisle: str
    shop_id: int | None
    place_id: int | None
    count_word: str | None
    count_word_plural: str | None
    sizes: list[SizeRow]
    removed: bool
    merged_into_id: int | None
    version: int


class ShopRow(BaseModel):
    id: int
    name: str
    position: int
    aisle_order: list[str] | None


class PlaceRow(BaseModel):
    id: int
    name: str
    kind: str
    position: int


class Person(BaseModel):
    login_id: int
    name: str


class AisleRow(BaseModel):
    key: str
    name: str


class ChangesOut(BaseModel):
    cursor: int  # the household's counter: send it as `since` next time
    reset: bool  # a full copy without tombstones: replace the device's copy
    lists: list[ListRow]
    items: list[ItemRow | Tombstone]
    notes: list[NoteRow]  # every note for you that isn't gone, whatever `since` is
    questions: list[QuestionRow]  # every open question for you, plus any closed since
    foods: list[FoodRow]
    shops: list[ShopRow]
    places: list[PlaceRow]
    people: list[Person]
    aisles: list[AisleRow]


class BatchOut(BaseModel):
    results: list[ResultOut]  # one per action, in the order sent
    changes: ChangesOut


def list_text(food: Food, milli: int, size: FoodSize | None) -> str:
    """A list line's amount as it's bought: "1 packet", "2 boxes" (12 eggs, bought by the
    box), "1 bunch", "5" (five onions), "600 g". Count foods show the size when it's a
    whole number of them; the pantry's "left" never shows on a list."""
    if (
        size is not None
        and food.counted_as == "count"
        and size.amount_milli not in (0, MILLI)
        and milli % size.amount_milli == 0
    ):
        whole = milli // size.amount_milli
        return f"{whole}{NBSP}{size.name if whole == 1 else size.plural}"
    return amount_out(food, milli, size).short.removesuffix(f"{NBSP}left")


def _number(milli: int) -> int | float:
    return sync.number(Decimal(milli) / MILLI)


def _removed_by(kitchen: Kitchen, item: ListItem, device_id: str | None) -> str | None:
    action = (
        kitchen.db.get(SyncAction, (kitchen.household_id, item.deleted_action_id))
        if item.deleted_action_id
        else None
    )
    if action is None:
        return item.deleted_by_name
    if (
        action.login_id == kitchen.login.id
        and device_id is not None
        and action.device_id is not None
        and action.device_id != device_id
    ):
        return OTHER_PHONE
    return action.login_name


def _ticks_by_item(
    kitchen: Kitchen, items: list[ListItem], foods: dict[int, Food | None]
) -> dict[str, list[TickRow]]:
    """The purchases of all these lines, in server order, in a fixed number of statements (one
    for the purchases, one for which of them were "Already have it") and not one per line.
    Both reads keep the household filter."""
    hid = kitchen.household_id
    db = kitchen.db
    by_item: dict[str, list[ListTick]] = {}
    ids = [item.id for item in items]
    for start in range(0, len(ids), PackReads.CHUNK):
        chunk = ids[start : start + PackReads.CHUNK]
        for tick in db.scalars(
            ticks.server_order(
                select(ListTick).where(ListTick.household_id == hid, ListTick.item_id.in_(chunk))
            )
        ):
            by_item.setdefault(tick.item_id, []).append(tick)
    every = [tick for found in by_item.values() for tick in found]
    found_at_home: set[str] = set()
    tick_ids = [tick.id for tick in every]
    for start in range(0, len(tick_ids), PackReads.CHUNK):
        chunk = tick_ids[start : start + PackReads.CHUNK]
        found_at_home.update(
            db.scalars(
                select(SyncAction.id).where(
                    SyncAction.household_id == hid,
                    SyncAction.id.in_(chunk),
                    SyncAction.kind == "found_at_home",
                )
            )
        )
    out: dict[str, list[TickRow]] = {}
    for item in items:
        food = foods.get(item.food_id)
        rows = []
        for tick in by_item.get(item.id, []):
            bought = None
            if tick.bought_milli is not None and food is not None:
                size = db.get(FoodSize, tick.bought_size_id) if tick.bought_size_id else None
                bought = Bought(
                    amount=_number(tick.bought_milli),
                    display=list_text(food, tick.bought_milli, size),
                )
            rows.append(
                TickRow(
                    id=tick.id,
                    by=Who(login_id=tick.login_id, name=tick.login_name),
                    at=tick.ticked_at,
                    place_id=tick.place_id,
                    bought=bought,
                    standing=tick.reversed_at is None,
                    found=tick.id in found_at_home,
                )
            )
        out[item.id] = rows
    return out


def _item(
    kitchen: Kitchen,
    item: ListItem,
    foods: dict[int, Food | None],
    reads: PackReads,
    purchases: dict[str, list[TickRow]],
) -> ItemRow:
    if item.food_id not in foods:
        foods[item.food_id] = kitchen.db.get(Food, item.food_id)
    food = foods[item.food_id]
    display = None
    size = kitchen.db.get(FoodSize, item.size_id) if item.size_id else None
    if item.amount_milli is not None and food is not None:
        display = list_text(food, item.amount_milli, size)
    return ItemRow(
        id=item.id,
        list_id=item.list_id,
        food_id=item.food_id,
        shop_id=item.shop_id,
        amount=_number(item.amount_milli) if item.amount_milli is not None else None,
        size_id=item.size_id,
        display=display,
        pack=(
            pack_line_out(kitchen, food, item.amount_milli, size, reads)
            if food is not None
            else None
        ),
        source=item.source,
        hand_edited=item.hand_edited,
        put_away_place_id=item.put_away_place_id,
        ticks=purchases.get(item.id, []),
        added_by=Who(login_id=item.added_by_login_id, name=item.added_by_name),
        deleted=False,
        merged_into_id=item.merged_into_id,
        version=item.version,
    )


def _food(food: Food, reads: PackReads) -> FoodRow:
    names = [name.name for name in reads.names(food.id)]
    sizes = reads.sizes(food.id)
    return FoodRow(
        id=food.id,
        name=food.name,
        other_names=names,
        counted_as=food.counted_as,
        staple=food.staple,
        aisle=food.aisle if food.aisle in AISLE_KEYS else DEFAULT_AISLE,
        shop_id=food.shop_id,
        place_id=food.place_id,
        count_word=food.count_word,
        count_word_plural=food.count_word_plural,
        sizes=[
            SizeRow(
                id=size.id,
                name=size.name,
                plural=size.plural,
                amount=_number(size.amount_milli),
                usual=size.usual,
                added_when_shopping=size.added_when_shopping,
            )
            for size in sizes
        ],
        removed=food.removed_at is not None,
        merged_into_id=food.merged_into_id,
        version=food.version,
    )


def changes_since(kitchen: Kitchen, since: int, device_id: str | None = None) -> ChangesOut:
    """Everything that changed after counter `since` (5.5)."""
    db = kitchen.db
    hid = kitchen.household_id
    me = kitchen.login.id
    household = kitchen.household
    # A full copy when asked for, when the phone is behind a tidy-up (3.9), or when it is
    # ahead of the server (a restore from a backup, 5.5): its copy can't be trusted.
    reset = since == 0 or since < household.list_purged_seq or since > household.list_seq
    after = since

    def newer(version: Any) -> Any:
        """Rows changed after `since`; on a full copy every row, version 0 too (rows made
        before the counter existed, like the main list)."""
        return true() if reset else version > after

    lists = [
        ListRow(
            id=row.id,
            name=row.name,
            main=row.main,
            position=row.position,
            removed=row.removed_at is not None,
            version=row.version,
        )
        for row in db.scalars(
            select(ShoppingList)
            .where(ShoppingList.household_id == hid, newer(ShoppingList.version))
            .order_by(ShoppingList.position, ShoppingList.created_at, ShoppingList.id)
        )
    ]

    foods: dict[int, Food | None] = {}
    items: list[ItemRow | Tombstone] = []
    changed = list(
        db.scalars(
            select(ListItem)
            .where(ListItem.household_id == hid, newer(ListItem.version))
            .order_by(ListItem.version, ListItem.id)
        )
    )
    # The sizes and other names of every line's ingredient, read once for the whole answer.
    live = [i for i in changed if i.deleted_at is None]
    reads = PackReads(kitchen, {i.food_id for i in live})
    # The lines' ingredients and purchases, each read once too (not one statement per line).
    wanted = sorted({i.food_id for i in live})
    for start in range(0, len(wanted), PackReads.CHUNK):
        chunk = wanted[start : start + PackReads.CHUNK]
        for food in db.scalars(select(Food).where(Food.household_id == hid, Food.id.in_(chunk))):
            foods[food.id] = food
    for food_id in wanted:
        foods.setdefault(food_id, None)
    purchases = _ticks_by_item(kitchen, live, foods)
    for item in changed:
        if item.deleted_at is None:
            items.append(_item(kitchen, item, foods, reads, purchases))
        elif not reset:
            items.append(
                Tombstone(
                    id=item.id,
                    list_id=item.list_id,
                    deleted=True,
                    version=item.version,
                    food_id=item.food_id,
                    shop_id=item.shop_id,
                    removed_by=_removed_by(kitchen, item, device_id),
                )
            )

    notes = [
        NoteRow(
            id=row.id,
            list_id=row.list_id,
            item_id=row.item_id,
            food_id=row.food_id,
            text=row.text,
            undo=row.undo_action_id,
            gone=False,
            version=row.version,
        )
        for row in db.scalars(
            select(ListNote)
            .where(
                ListNote.household_id == hid,
                ListNote.for_login_id == me,
                ListNote.gone_at.is_(None),
            )
            .order_by(ListNote.id)
        )
    ]

    questions = []
    for question in db.scalars(
        select(DoubleTick)
        .where(DoubleTick.household_id == hid)
        .where(DoubleTick.answer.is_(None) | (false() if reset else DoubleTick.version > after))
        .order_by(DoubleTick.id)
    ):
        if me not in (question.login_ids or []):
            continue
        words = ticks.card_words(kitchen, question, me)
        questions.append(
            QuestionRow(
                id=question.id,
                list_id=question.list_id,
                item_id=question.item_id,
                title=words.title,
                text=words.text,
                yes=words.yes,
                no=words.no,
                open=question.answer is None,
                version=question.version,
            )
        )

    food_rows = select(Food).where(Food.household_id == hid, newer(Food.version))
    if reset:
        food_rows = food_rows.where(Food.removed_at.is_(None), Food.merged_into_id.is_(None))
    food_list = list(db.scalars(food_rows.order_by(Food.id)))
    reads.load(f.id for f in food_list)
    food_out = [_food(food, reads) for food in food_list]

    shops = [
        ShopRow(id=s.id, name=s.name, position=s.position, aisle_order=s.aisle_order)
        for s in db.scalars(
            select(Shop).where(Shop.household_id == hid).order_by(Shop.position, Shop.id)
        )
    ]
    places = [
        PlaceRow(id=p.id, name=p.name, kind=p.kind, position=p.position)
        for p in db.scalars(
            select(Place).where(Place.household_id == hid).order_by(Place.position, Place.id)
        )
    ]
    # Who the list is shared with ("Synced with Wren"): the people who sign in, not removed, not
    # waiting for their sign-in link, and not a shared login (it is a device, not a person).
    people = [
        Person(login_id=login.id, name=member.name)
        for login, member in db.execute(
            select(Login, Member)
            .join(Member, Member.id == Login.member_id)
            .where(Login.household_id == hid, Login.shared.is_(False), can_sign_in())
            .order_by(Login.id)
        ).tuples()
    ]
    return ChangesOut(
        cursor=household.list_seq,
        reset=reset,
        lists=lists,
        items=items,
        notes=notes,
        questions=questions,
        foods=food_out,
        shops=shops,
        places=places,
        people=people,
        aisles=[AisleRow(key=key, name=AISLE_LABELS[key]) for key, _ in AISLES],
    )


def _result(kitchen: Kitchen, raw: dict[str, Any]) -> ResultOut:
    found = kitchen.db.get(Change, raw["change_id"]) if raw.get("change_id") else None
    return ResultOut(
        id=raw["id"],
        seq=raw.get("seq"),
        status=raw["status"],
        reason=raw.get("reason"),
        repeat=bool(raw.get("repeat")),
        item_id=raw.get("item_id"),
        food_id=raw.get("food_id"),
        change=change_out(kitchen, found) if found is not None else None,
        message=raw.get("message"),
    )


@router.post(
    "/shopping/actions",
    responses={
        409: {"model": Refusal, "description": "`other_login`: queued by another login (5.6)."},
        413: {
            "model": Refusal,
            "description": f"`too_many`: more than {sync.MAX_ACTIONS} actions in one batch.",
        },
    },
)
def apply_actions(body: Envelope, kitchen: Here) -> BatchOut:
    """Apply a batch of queued list actions, in order (sync protocol 4.1 and 5)."""
    if body.protocol != 1:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "bad_protocol",
            "This app version speaks a sync protocol the server doesn’t know.",
        )
    if body.login_id != kitchen.login.id:
        raise Problem(
            status.HTTP_409_CONFLICT, "other_login", "These changes were made by another login."
        )
    if len(body.actions) > sync.MAX_ACTIONS:
        raise Problem(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "too_many",
            f"A batch can hold at most {sync.MAX_ACTIONS} changes.",
        )
    raw = sync.apply_batch(kitchen, body.device_id, body.sent_at, list(body.actions))
    results = [_result(kitchen, one) for one in raw]
    changes = changes_since(kitchen, body.since, body.device_id)
    kitchen.db.commit()
    return BatchOut(results=results, changes=changes)


@router.get("/shopping/sync")
def get_changes(
    kitchen: Here,
    since: Annotated[StoredInt, Query(ge=0)] = 0,
    device_id: Annotated[str | None, Query(pattern=sync.UUID_PATTERN)] = None,
) -> ChangesOut:
    """Everything that changed after counter `since`; `since=0` is a full copy (5.5).
    `device_id` (optional) lets a removal from your own other phone say so."""
    return changes_since(kitchen, since, device_id)
