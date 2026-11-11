"""Ticking: the pantry side of a tick, and the actions about purchases (docs/dev/
sync-protocol.md sections 7, 8 and 5.8).

A tick is a *purchase* (`list_tick`): its own lots, its own `shopped` change. A purchase's
stock is the lots named by the lines of its own changes (`change.tick_id`, 7.2). Taking a
purchase back (untick, "Just 1", Undo of a tick) is 0.2's Undo of each of its amount
changes; putting it back puts back exactly what that took out, lot by lot (7.5).
"""

import uuid
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import date
from typing import Any, NamedTuple

from sqlalchemy import Select, and_, select
from sqlalchemy.orm import aliased

from mealwright import shopping
from mealwright.amounts import NBSP, TooBig, checked
from mealwright.api.v1.context import Kitchen
from mealwright.foods import add_size, amount_out, pack_bought, sizes, usual_size
from mealwright.history import as_utc
from mealwright.models import (
    Change,
    ChangeLine,
    DoubleTick,
    Food,
    FoodSize,
    ListItem,
    ListTick,
    Place,
    StockLot,
    SyncAction,
    utcnow,
)
from mealwright.shopping import Act, Batch, Refused, who
from mealwright.stock import (
    MAX_LOTS,
    StockEdit,
    default_place,
    lot_amounts,
    put_in,
    short_text,
    take,
    what_text,
)

TICK_KINDS = (
    "tick",
    "found_at_home",
    "untick",
    "put_away",
    "different_pack",
    "answer_double_tick",
)
# Proposed, for cabledrawer (the words); the rule is his (11 Nov). Shown as a quiet note.
FOUND_TWICE = "Already found at home by the other phone."
AMOUNT_KINDS = ("shopped", "found", "repacked")  # a purchase's changes that change amounts (7.5)


# --- Reading -------------------------------------------------------------------------------------


def get_tick(kitchen: Kitchen, tick_id: str | None) -> ListTick | None:
    if not tick_id:
        return None
    return kitchen.db.get(ListTick, (kitchen.household_id, tick_id))


def is_found(kitchen: Kitchen, tick: ListTick) -> bool:
    """Was this purchase "Already have it" (found at home, not bought)? The purchase's ID is
    its action's ID, and that action's kind says so (no column needed)."""
    row = shopping.action_row(kitchen, tick.id)
    return row is not None and row.kind == "found_at_home"


def server_order(query: Select[ListTick]) -> Select[ListTick]:
    """Purchases in server order (L-3): by the counter number their tick took. The tick
    being applied has no sync_action row yet, so it comes last."""
    row = aliased(SyncAction)
    return query.outerjoin(
        row, and_(row.household_id == ListTick.household_id, row.id == ListTick.id)
    ).order_by(row.seq.is_(None), row.seq, ListTick.ticked_at, ListTick.id)


def ticks_of(kitchen: Kitchen, item_id: str, standing: bool = True) -> list[ListTick]:
    """An item's purchases in server order (the standing ones, unless asked)."""
    query = select(ListTick).where(
        ListTick.household_id == kitchen.household_id, ListTick.item_id == item_id
    )
    if standing:
        query = query.where(ListTick.reversed_at.is_(None))
    return list(kitchen.db.scalars(server_order(query)))


def _named(kitchen: Kitchen, item: ListItem, tick_ids: Iterable[str]) -> list[ListTick]:
    """The purchases an action names that belong to this item and still stand."""
    found: list[ListTick] = []
    for tick_id in dict.fromkeys(tick_ids):
        tick = get_tick(kitchen, tick_id)
        if tick is not None and tick.item_id == item.id and tick.reversed_at is None:
            found.append(tick)
    return found


def live_food(kitchen: Kitchen, food_id: int) -> Food | None:
    """The ingredient, following merges to the end of the chain (5.9)."""
    seen: set[int] = set()
    food = kitchen.db.get(Food, food_id)
    while food is not None and food.merged_into_id and food.id not in seen:
        seen.add(food.id)
        food = kitchen.db.get(Food, food.merged_into_id)
    if food is None or food.household_id != kitchen.household_id:
        return None
    return food


def get_place(kitchen: Kitchen, place_id: int | None) -> Place | None:
    if place_id is None:
        return None
    place = kitchen.db.get(Place, place_id)
    if place is None or place.household_id != kitchen.household_id:
        return None
    return place


def purchase_lots(kitchen: Kitchen, tick: ListTick) -> list[StockLot]:
    """The purchase's stock (7.2): the lots its own changes name, wherever they are now."""
    lot_ids = kitchen.db.scalars(
        select(ChangeLine.lot_id)
        .join(Change, Change.id == ChangeLine.change_id)
        .where(
            Change.household_id == kitchen.household_id,
            Change.tick_id == tick.id,
            ChangeLine.lot_id.is_not(None),
        )
        .distinct()
    )
    ids = sorted({lot_id for lot_id in lot_ids if lot_id is not None})
    lots = [kitchen.db.get(StockLot, lot_id) for lot_id in ids]
    return [lot for lot in lots if lot is not None]


def _size(kitchen: Kitchen, size_id: int | None) -> FoodSize | None:
    return kitchen.db.get(FoodSize, size_id) if size_id else None


def sync_copy(kitchen: Kitchen, item: ListItem, seq: int) -> None:
    """The item's `ticked_*` copy follows its first purchase still standing, or clears."""
    first = next(iter(ticks_of(kitchen, item.id)), None)
    item.ticked_at = first.ticked_at if first else None
    item.ticked_by_login_id = first.login_id if first else None
    item.ticked_by_name = first.login_name if first else None
    item.ticked_device_id = first.device_id if first else None
    item.version = seq


def _start(act: Act) -> tuple[ListItem, Food] | None:
    """The item an action names (following merges) and its ingredient, else `ignored gone`."""
    kitchen = act.kitchen
    item = shopping.get_item(kitchen, act.payload["item_id"])
    if item is None:
        act.ignore("gone")
        return None
    act.item_id, act.list_id = item.id, item.list_id
    food = live_food(kitchen, item.food_id)
    if food is None:
        act.ignore("gone")
        return None
    act.food_id = food.id
    return item, food


def _removed_list(act: Act, item: ListItem, ticked: bool = False) -> None:
    shopping_list = shopping.get_list(act.kitchen, item.list_id)
    if shopping_list is not None:
        shopping.in_removed_list(act, shopping_list, ticked=ticked)


def _remover(act: Act, item: ListItem) -> SyncAction | None:
    """The action that took a tombstoned item off, if this device hadn't seen it."""
    if item.deleted_at is None:
        return None
    row = shopping.action_row(act.kitchen, item.deleted_action_id)
    if row is None or not shopping.unseen(act, row) or row.device_id == act.device_id:
        return None
    return row


def _keep_the_rest(
    act: Act, item: ListItem, shown: int | None, bought: int, size: FoodSize | None
) -> None:
    """The phone ticked `shown` (and `bought` went into the pantry, whole packs maybe); the
    line has grown since (a meal planned at home while it was offline). The line being ticked
    becomes what the phone showed, and what the pantry still lacks is a line of its own, still
    to buy, at the same list and shop (RF2 Sh1, sync-protocol 7.1)."""
    if shown is None or item.amount_milli is None or item.deleted_at is not None:
        return
    if item.amount_milli <= max(shown, bought):
        return
    kitchen = act.kitchen
    kitchen.db.add(
        ListItem(
            id=str(uuid.uuid4()),
            household_id=kitchen.household_id,
            list_id=item.list_id,
            food_id=item.food_id,
            shop_id=item.shop_id,
            amount_milli=item.amount_milli - max(shown, bought),
            size_id=item.size_id,
            source=item.source,
            hand_edited=item.hand_edited,
            put_away_place_id=None,
            added_by_login_id=item.added_by_login_id,
            added_by_name=item.added_by_name,
            version=act.seq,
        )
    )
    item.amount_milli = shown
    item.size_id = size.id if size is not None else None


# --- tick (7.1) ----------------------------------------------------------------------------------


def tick(act: Act) -> None:
    """A purchase: stock into the pantry (7.1); a second purchase opens the card (L-3)."""
    kitchen = act.kitchen
    found = _start(act)
    if found is None:
        return
    item, food = found
    standing = ticks_of(kitchen, item.id)
    if any(t.device_id is not None and t.device_id == act.device_id for t in standing):
        act.ignore("already_ticked")
        return
    from mealwright import sync  # sync imports this module's callers: a late import

    when = sync.happened_at(act)  # the phone's time, else the server's (cabledrawer 2 Nov)
    listed = food
    revived: dict[str, Any] = {}
    if food.removed_at is not None and not food.staple and item.amount_milli:
        # On a tombstone only (removing is blocked otherwise), and only when stock goes in:
        # the purchase needs an ingredient in the pantry (7.1, cabledrawer 18 Oct).
        food, revived = shopping.revive(act, food)
        act.food_id = food.id  # the ingredient the stock goes to (5.4)
    # The live ingredient with that name now is counted another way: the item's amount
    # means nothing for it, so nothing goes in (7.1, cabledrawer 18 Oct).
    recount = food.counted_as != listed.counted_as
    place = get_place(kitchen, item.put_away_place_id)
    if place is None:
        item.put_away_place_id = None  # a chosen place that's gone (5.9, SY-55)
        place = default_place(kitchen, food)
    size = shopping.get_size(kitchen, food, item.size_id)
    line_milli = item.amount_milli
    shown = act.payload.get("amount")
    shown_size = None
    if shown is not None:
        # RF2 Sh1 (cabledrawer 11 Nov): the phone says what its line showed; that is what was
        # bought, even if the line has grown since (a tick made before the update has none).
        line_milli = shopping.milli_of(shown)
        size = shown_size = shopping.get_size(kitchen, food, act.payload.get("size_id"))
    milli = None if food.staple or recount else line_milli
    if milli and size is None:
        # F122 (cabledrawer 31 Oct): a line in plain grams, ml or items puts the pack bought into
        # the pantry, not the exact need: 38 g ghee with a 500 g jar is 1 jar. A line already
        # in packs, and an ingredient with no size to buy in, go in as they are.
        pack = pack_bought(kitchen, food.id)
        if pack is not None and pack.amount_milli > 0:
            packs = -(-milli // pack.amount_milli)
            if packs <= MAX_LOTS:  # a tiny size can't ask for a million packets
                milli = packs * pack.amount_milli
                size = pack
    row = ListTick(
        household_id=kitchen.household_id,
        id=act.id,
        item_id=item.id,
        login_id=kitchen.login.id,
        login_name=kitchen.login.name,
        device_id=act.device_id,
        ticked_at=when,
        place_id=place.id,
        bought_milli=milli or None,
        bought_size_id=size.id if size and milli else None,
        restock=food.staple,  # "Restocked": the staple's restock date moves on
    )
    kitchen.db.add(row)
    kitchen.db.flush()
    if row.bought_milli:
        edit = StockEdit(kitchen)
        amounts = lot_amounts(row.bought_milli, size)
        # Past the cap the amount is one big lot: it isn't a packet, so it carries no size
        # (a "¾" would otherwise be three quarters of one jar, not of the lot).
        one_big = size is not None and len(amounts) == 1 and amounts[0] > size.amount_milli
        put_in(kitchen, edit, food, place, amounts, None if one_big else size, added_at=when)
        shown = size or usual_size(kitchen, food.id)
        summary = f"Bought {what_text(food, row.bought_milli, shown)} → {place.name}"
        if food.counted_as == "count" and row.bought_size_id and shown is not None:
            # A counted ingredient bought in a pack says the pack ("1 box Eggs"), not "6 Eggs"
            # (F122, cabledrawer 31 Oct).
            n, rest = divmod(row.bought_milli, shown.amount_milli)
            if rest == 0:
                word = shown.name if n == 1 else shown.plural
                summary = f"Bought {n}\u00a0{word} {food.name} → {place.name}"
        data: dict[str, Any] = {"action": act.id}
        if revived:
            data["revived"] = revived  # an Undo of the tick removes it again (7.1)
        change = edit.record("shopped", summary, food.id, data)
        change.tick_id = row.id
        row.change_id = change.id
        act.change = change
    if shown is not None:
        _keep_the_rest(act, item, line_milli, row.bought_milli or 0, shown_size)
    sync_copy(kitchen, item, act.seq)
    _removed_list(act, item, ticked=bool(row.bought_milli))
    if recount:
        shopping.note(
            act,
            "N8",
            kitchen.login.id,
            f"{listed.name} is counted differently now, so nothing went into the pantry.",
            list_id=item.list_id,
            item_id=item.id,
            food_id=food.id,
            undo=act.id,
        )
    if not row.bought_milli:
        return
    _ask(act, item, row)
    remover = _remover(act, item)
    if remover is not None and remover.kind in ("delete", "move"):
        # N1 (L-9). A cleared item gets none: the card, if any, explains it (L-19). A move
        # that added this line to one already there takes it off the same way (M-3).
        me = kitchen.login.id
        taken = "moved" if remover.kind == "move" else "removed"
        shopping.note(
            act,
            "N1",
            me,
            f"{who(remover.login_id, remover.login_name, me)} had {taken} this."
            " Your tick still went into the pantry.",
            list_id=item.list_id,
            item_id=item.id,
            food_id=food.id,
            undo=act.id,
        )


def found_at_home(act: Act) -> None:
    """ "Already have it": the line comes off the list (it goes into the trolley as ticked) and
    the amount found goes into the pantry, recorded as found at home, not bought. Everything
    else is a tick: the same purchase row, so Undo, untick and clearing work the same."""
    kitchen = act.kitchen
    found = _start(act)
    if found is None:
        return
    item, food = found
    standing = ticks_of(kitchen, item.id)
    if any(t.device_id is not None and t.device_id == act.device_id for t in standing):
        act.ignore("already_ticked")
        return
    if any(t.bought_milli and is_found(kitchen, t) for t in standing):
        # RF2 Sh2 (cabledrawer 11 Nov): what is at home is found once, whoever says so first; the
        # second phone is told and has nothing to undo. A bought tick beside it still counts.
        act.ignore("already_found", FOUND_TWICE)
        return
    from mealwright import sync

    when = sync.happened_at(act)
    listed = food
    revived: dict[str, Any] = {}
    if food.removed_at is not None and not food.staple:
        # As a tick does (7.1): stock needs an ingredient in the pantry, so a removed one
        # comes back (or the live one with that name is used), and Undo removes it again.
        food, revived = shopping.revive(act, food)
        act.food_id = food.id
    # As a tick does: the live ingredient with that name now is counted another way, so the
    # amount found means nothing for it and nothing goes in (7.1).
    recount = food.counted_as != listed.counted_as
    milli = None if food.staple or recount else shopping.milli_of(act.payload["amount"])
    size = shopping.get_size(kitchen, food, act.payload.get("size_id"))
    place = get_place(kitchen, act.payload.get("place_id")) or get_place(
        kitchen, item.put_away_place_id
    )
    if place is None:
        place = default_place(kitchen, food)
    row = ListTick(
        household_id=kitchen.household_id,
        id=act.id,
        item_id=item.id,
        login_id=kitchen.login.id,
        login_name=kitchen.login.name,
        device_id=act.device_id,
        ticked_at=when,
        place_id=place.id,
        bought_milli=milli or None,
        bought_size_id=size.id if size and milli else None,
        restock=False,
    )
    kitchen.db.add(row)
    kitchen.db.flush()
    if row.bought_milli:
        edit = StockEdit(kitchen)
        amounts = lot_amounts(row.bought_milli, size)
        one_big = size is not None and len(amounts) == 1 and amounts[0] > size.amount_milli
        put_in(kitchen, edit, food, place, amounts, None if one_big else size, added_at=when)
        shown = size or usual_size(kitchen, food.id)
        amount = short_text(food, row.bought_milli, shown)
        summary = f"Found {food.name} at home: {amount} → {place.name}"
        data: dict[str, Any] = {"action": act.id}
        if revived:
            data["revived"] = revived  # an Undo of the find removes it again (7.1)
        change = edit.record("found", summary, food.id, data)
        change.tick_id = row.id
        row.change_id = change.id
        act.change = change
    sync_copy(kitchen, item, act.seq)
    _removed_list(act, item, ticked=bool(row.bought_milli))
    if recount:
        shopping.note(
            act,
            "N8",
            kitchen.login.id,
            f"{listed.name} is counted differently now, so nothing went into the pantry.",
            list_id=item.list_id,
            item_id=item.id,
            food_id=food.id,
            undo=act.id,
        )
    if not row.bought_milli:
        return
    remover = _remover(act, item)
    if remover is not None and remover.kind in ("delete", "move"):
        # N1, as for a tick: the line was removed or moved by someone who hadn't seen the find.
        me = kitchen.login.id
        taken = "moved" if remover.kind == "move" else "removed"
        shopping.note(
            act,
            "N1",
            me,
            f"{who(remover.login_id, remover.login_name, me)} had {taken} this."
            " Your tick still went into the pantry.",
            list_id=item.list_id,
            item_id=item.id,
            food_id=food.id,
            undo=act.id,
        )


def _ask(act: Act, item: ListItem, new: ListTick) -> None:
    """Open "Did you buy 2?", or add this purchase to the open one (3.6)."""
    kitchen = act.kitchen
    others = [
        t
        for t in ticks_of(kitchen, item.id)
        if t.bought_milli and t.id != new.id and not is_found(kitchen, t)
    ]
    if not others:
        return
    question = open_question(kitchen, item.id)
    if question is None:
        question = DoubleTick(
            household_id=kitchen.household_id,
            list_id=item.list_id,
            item_id=item.id,
            tick_ids=[t.id for t in others],
            created_at=utcnow(),
        )
        kitchen.db.add(question)
    question.tick_ids = [*question.tick_ids, new.id]
    _who_sees(kitchen, question)
    question.version = act.seq
    kitchen.db.flush()


def _who_sees(kitchen: Kitchen, question: DoubleTick) -> None:
    logins: list[int] = []
    for tick_id in question.tick_ids:
        tick = get_tick(kitchen, tick_id)
        if tick is not None and tick.login_id is not None and tick.login_id not in logins:
            logins.append(tick.login_id)
    question.login_ids = logins
    question.same_login = len(logins) <= 1


def open_question(kitchen: Kitchen, item_id: str) -> DoubleTick | None:
    return kitchen.db.scalar(
        select(DoubleTick)
        .where(
            DoubleTick.household_id == kitchen.household_id,
            DoubleTick.item_id == item_id,
            DoubleTick.answer.is_(None),
        )
        .order_by(DoubleTick.id)
        .limit(1)
    )


# --- Taking a purchase back, and putting it back (7.5) -------------------------------------------


def amount_changes(kitchen: Kitchen, tick_id: str) -> list[Change]:
    """The purchase's amount changes not yet undone, newest first."""
    return list(
        kitchen.db.scalars(
            select(Change)
            .where(
                Change.household_id == kitchen.household_id,
                Change.tick_id == tick_id,
                Change.kind.in_(AMOUNT_KINDS),
                Change.undone_by_change_id.is_(None),
            )
            .order_by(Change.id.desc())
        )
    )


def reverse(act: Act, tick: ListTick, summary: Callable[[Change], str]) -> list[Change]:
    """Take a purchase back: 0.2's Undo of each of its amount changes, newest first. Returns
    the `undo` changes."""
    from mealwright.api.v1.changes import undo_change

    kitchen = act.kitchen
    bought = [tick.bought_milli, tick.bought_size_id]
    done = [
        undo_change(
            kitchen,
            change,
            act.batch,
            act.id,
            summary=summary(change),
            tick_id=tick.id,
            extra={"action": act.id, "bought": bought},
        )
        for change in amount_changes(kitchen, tick.id)
    ]
    tick.reversed_at = utcnow()
    tick.reversed_by_action_id = act.id
    shopping.notes_gone(kitchen, tick.id, act.seq)
    close_questions(act, tick)
    return done


def close_questions(act: Act, tick: ListTick) -> None:
    """A purchase reversed some other way closes its open question as `none` (7.5)."""
    question = open_question(act.kitchen, tick.item_id)
    if question is not None and tick.id in question.tick_ids:
        _settle(act, question, "none")


def _settle(act: Act, question: DoubleTick, answer: str | None) -> None:
    question.answer = answer
    question.answered_at = utcnow() if answer else None
    question.answered_by_name = act.kitchen.login.name if answer else None
    question.answer_action_id = act.id if answer else None
    question.version = act.seq


def partial(done: Iterable[Change]) -> str | None:
    """The sentence for a take-back that couldn't take everything (0.2's partial Undo)."""
    for undo in done:
        data = undo.undo_data or {}
        if data.get("result") != "done":
            return str(data.get("message") or "") or None
    return None


def repack_back(kitchen: Kitchen, change: Change, done: list[Change]) -> str | None:
    """The sentence for an Undo of a pack change that couldn't put things exactly back,
    because some was used since (7.4 item 6, cabledrawer 18 Oct). None if it could."""
    if change.kind != "repacked" or partial(done) is None:
        return None
    ops = (change.undo_data or {}).get("shopping") or []
    old = next((op["old"] for op in ops if op.get("op") == "tick_bought"), None)
    food = kitchen.db.get(Food, change.food_id) if change.food_id is not None else None
    if not isinstance(old, list) or len(old) != 2 or food is None:
        return None
    size = _size(kitchen, old[1]) or usual_size(kitchen, food.id)
    shown = amount_out(food, old[0] or 0, size).display.removesuffix(f"{NBSP}left")
    return f"{food.name} is back to {shown}. Some had been used since, so check how much is left."


def _say(undo: Change, message: str | None) -> None:
    if message is not None:
        undo.undo_data = {**(undo.undo_data or {}), "message": message}


def took_out(kitchen: Kitchen, done: Iterable[Change]) -> int:
    """How much a reversal's `undo` changes took out of the pantry, in base units."""
    ids = [change.id for change in done]
    if not ids:
        return 0
    lines = kitchen.db.scalars(select(ChangeLine).where(ChangeLine.change_id.in_(ids)))
    return sum(max(0, line.amount_before_milli - line.amount_after_milli) for line in lines)


def put_back(act: Act, reversal: SyncAction) -> list[ListTick]:
    """Undo of an untick or "Just 1": put back exactly what the reversal took out, lot by
    lot (7.5). Returns the purchases put back."""
    kitchen = act.kitchen
    db = kitchen.db
    undos: dict[str, list[Change]] = defaultdict(list)
    for change_id in (reversal.result or {}).get("changes", []):
        change = db.get(Change, change_id)
        if change is not None and change.kind == "undo" and change.tick_id:
            undos[change.tick_id].append(change)
    back = list(
        db.scalars(
            server_order(
                select(ListTick).where(
                    ListTick.household_id == kitchen.household_id,
                    ListTick.reversed_by_action_id == reversal.id,
                )
            )
        )
    )
    for tick in back:
        _put_back_one(act, tick, undos.get(tick.id, []))
    return back


def _put_back_one(act: Act, tick: ListTick, undos: list[Change]) -> None:
    kitchen = act.kitchen
    db = kitchen.db
    took: dict[int | None, int] = defaultdict(int)  # lot → how much the reversal took out
    for undo in undos:
        for line in db.scalars(select(ChangeLine).where(ChangeLine.change_id == undo.id)):
            took[line.lot_id] += line.amount_before_milli - line.amount_after_milli
    if undos:
        bought = (undos[0].undo_data or {}).get("bought")
        if isinstance(bought, list) and len(bought) == 2:
            tick.bought_milli, tick.bought_size_id = bought
    tick.reversed_at = None
    tick.reversed_by_action_id = None
    # The ingredient the stock went to: the item's, or the one with its name now (7.1).
    item = db.get(ListItem, tick.item_id)
    stocked = next((undo.food_id for undo in undos if undo.food_id is not None), None)
    if stocked is None and item is not None:
        stocked = item.food_id
    food = live_food(kitchen, stocked) if stocked is not None else None
    total = sum(amount for amount in took.values() if amount > 0)
    if food is None or total <= 0:
        return
    size = _size(kitchen, tick.bought_size_id)
    place = get_place(kitchen, tick.place_id) or default_place(kitchen, food)
    edit = StockEdit(kitchen)
    for lot_id, amount in took.items():
        if amount <= 0:
            continue
        lot = db.get(StockLot, lot_id) if lot_id is not None else None
        if lot is None or lot.household_id != kitchen.household_id:
            put_in(kitchen, edit, food, place, [amount], size, added_at=as_utc(tick.ticked_at))
        else:
            edit.touch(lot).amount_milli += amount
    shown = size or usual_size(kitchen, food.id)
    if shown is not None and total % shown.amount_milli:
        shown = None  # part of a packet: "300 g Toor dal", as the untick said (SY-26u)
    summary = f"Ticked again: {what_text(food, total, shown)} → {place.name}"
    kind = "found" if is_found(kitchen, tick) else "shopped"
    change = edit.record(kind, summary, food.id, {"action": act.id})
    change.tick_id = tick.id
    tick.change_id = change.id
    act.change = act.change or change


# --- untick --------------------------------------------------------------------------------------


def untick(act: Act) -> None:
    """Reverse the named purchases that still stand (L-2, L-10)."""
    kitchen = act.kitchen
    found = _start(act)
    if found is None:
        return
    item, food = found
    named = _named(kitchen, item, act.payload["tick_ids"])
    if not named:
        act.ignore("not_ticked")
        return
    done: list[Change] = []
    for tick in named:
        done += reverse(act, tick, lambda change: f"Unticked: {change.summary}")
    sync_copy(kitchen, item, act.seq)
    if done:
        act.change = done[0]
    act.message = partial(done)
    _removed_list(act, item)
    remover = _remover(act, item)
    if remover is not None and took_out(kitchen, done):  # N5: only if stock came out (8)
        me = kitchen.login.id
        shopping.note(
            act,
            "N5",
            me,
            f"{who(remover.login_id, remover.login_name, me)} had"
            f" {'moved' if remover.kind == 'move' else 'removed'} this, so it isn’t"
            " back on the list. Your untick took it out of the pantry.",
            list_id=item.list_id,
            item_id=item.id,
            food_id=food.id,
            undo=act.id,
        )


# --- put_away (7.3) ------------------------------------------------------------------------------


def put_away(act: Act) -> None:
    """Record the chosen place, and move the named purchases' stock there."""
    kitchen = act.kitchen
    found = _start(act)
    if found is None:
        return
    item, food = found
    payload = act.payload
    place = get_place(kitchen, payload["place_id"])
    chosen = place.id if place is not None else None  # a place that's gone (SY-55)
    if place is None:
        place = default_place(kitchen, food)
    # The payload is the checked action as JSON, so a use-by date arrives as text.
    raw_use_by = payload.get("use_by")
    use_by = date.fromisoformat(raw_use_by) if raw_use_by is not None else None
    tombstoned = item.deleted_at is not None
    place_op: list[dict[str, Any]] = []
    if not tombstoned and item.put_away_place_id != chosen:
        place_op = [
            {"op": "item_place", "item_id": item.id, "old": item.put_away_place_id, "new": chosen}
        ]
        item.put_away_place_id = chosen
        item.version = act.seq
    list_ops: list[dict[str, Any]] = []
    moved = False
    for tick in _named(kitchen, item, payload.get("tick_ids", [])):
        lots = [
            lot
            for lot in purchase_lots(kitchen, tick)
            if lot.amount_milli > 0 and lot.place_id == tick.place_id
        ]
        if tick.place_id == place.id and (use_by is None or not lots):
            continue
        ops = [{"op": "tick_place", "tick_id": tick.id, "old": tick.place_id, "new": place.id}]
        tick.place_id = place.id
        item.version = act.seq
        if not lots:
            list_ops += ops
            continue
        edit = StockEdit(kitchen)
        for lot in lots:
            edit.touch(lot).place_id = place.id
            if use_by is not None:
                lot.use_by = use_by
        ops += place_op
        place_op = []
        change = edit.record(
            "moved",
            f"Moved {food.name} → {place.name}",
            food.id,
            {"shopping": ops, "action": act.id},
        )
        change.tick_id = tick.id
        act.change = act.change or change
        if act.main_change is None:
            act.main_change = change
        moved = True
    list_ops = place_op + list_ops
    if list_ops:
        act.done("item_place", f"Put away {food.name} → {place.name}", list_ops, food.id)
    if not moved and not list_ops:
        act.ignore("deleted" if tombstoned else "no_change")
        return
    _removed_list(act, item)
    _overwritten(act, item, food, place)


def _overwritten(act: Act, item: ListItem, food: Food, place: Place) -> None:
    """N6: a put-away from another device that this one hadn't seen is overwritten (L-32)."""
    if act.plain or act.seen is None:
        return
    kitchen = act.kitchen
    earlier = kitchen.db.scalar(
        select(SyncAction)
        .where(
            SyncAction.household_id == kitchen.household_id,
            SyncAction.item_id == item.id,
            SyncAction.kind == "put_away",
            SyncAction.status == "applied",
            SyncAction.undone_by_action_id.is_(None),
        )
        .order_by(SyncAction.seq.desc())
        .limit(1)
    )
    if (
        earlier is None
        or not shopping.unseen(act, earlier)
        or earlier.device_id == act.device_id
        or (earlier.payload or {}).get("place_id") == act.payload["place_id"]
    ):
        return
    me, my_name = kitchen.login.id, kitchen.login.name
    shopping.note(
        act,
        "N6",
        earlier.login_id,
        f"{who(me, my_name, earlier.login_id)} put {food.name} in the {place.name}",
        list_id=item.list_id,
        item_id=item.id,
        food_id=food.id,
        undo=act.id,
    )


# --- different_pack (7.4) ------------------------------------------------------------------------


def _pack_size(act: Act, food: Food, pack: int) -> FoodSize | None:
    kitchen = act.kitchen
    named = shopping.get_size(kitchen, food, act.payload.get("size_id"))
    if named is not None and named.amount_milli == pack:
        return named
    same = next((s for s in sizes(kitchen, food.id) if s.amount_milli == pack), None)
    if same is not None:
        return same
    if food.counted_as == "count":
        # Whole things ("6 onions") are not a pack: no size is made up for them (K5, fix round 1).
        return None
    usual = usual_size(kitchen, food.id)
    size = add_size(kitchen, food, usual.name if usual else "pack", pack, when_shopping=True)
    size.usual = False  # never made usual (7.4)
    shopping.bump_foods(kitchen, [food.id], act.batch)
    return size


def different_pack(act: Act) -> None:
    """ "What did you buy?": the purchase was really `count` packs of `pack`."""
    kitchen = act.kitchen
    found = _start(act)
    if found is None:
        return
    item, food = found
    tick = get_tick(kitchen, act.payload["tick_id"])
    if tick is None or tick.item_id != item.id:
        act.ignore("gone")
        return
    if tick.reversed_at is not None:
        act.ignore("not_ticked")
        return
    if food.staple or is_found(kitchen, tick):  # found at home was never "bought"
        act.ignore("no_change")
        return
    pack = shopping.milli_of(act.payload["pack"]) or 0
    count = int(act.payload["count"])
    try:
        total = checked(pack * count)
    except TooBig as err:
        raise Refused("too_big", "That amount is too big.") from err
    size = _pack_size(act, food, pack)
    size_id = size.id if size else None
    if [tick.bought_milli, tick.bought_size_id] == [total, size_id]:
        act.ignore("no_change")
        return
    lots = purchase_lots(kitchen, tick)
    left = sum(lot.amount_milli for lot in lots)
    used_since = max((tick.bought_milli or 0) - left, 0)
    edit = StockEdit(kitchen)
    for lot in lots:
        if lot.amount_milli > 0:
            edit.touch(lot).amount_milli = 0
    place = get_place(kitchen, tick.place_id) or default_place(kitchen, food)
    new_lots = put_in(
        kitchen, edit, food, place, [pack] * count, size, added_at=as_utc(tick.ticked_at)
    )
    take(kitchen, edit, new_lots, used_since, include_freezer=True)
    old_size = _size(kitchen, tick.bought_size_id) or usual_size(kitchen, food.id)
    new = amount_out(food, total, size).display.removesuffix(f"{NBSP}left")
    if tick.bought_milli:
        old = amount_out(food, tick.bought_milli, old_size).display.removesuffix(f"{NBSP}left")
        summary = f"{food.name}: bought {new} instead of {old}"
    else:
        # A purchase that had no amount gets its first one; "instead of 0 g" read oddly
        # (cabledrawer 20 Oct, hand test).
        summary = f"{food.name}: bought {new} (first amount)"
    ops = [
        {
            "op": "tick_bought",
            "tick_id": tick.id,
            "old": [tick.bought_milli, tick.bought_size_id],
            "new": [total, size_id],
        }
    ]
    change = edit.record(
        "repacked",
        summary,
        food.id,
        {"shopping": ops, "action": act.id},
    )
    change.tick_id = tick.id
    tick.bought_milli, tick.bought_size_id = total, size_id
    item.version = act.seq
    act.change = change
    _removed_list(act, item)


# --- answer_double_tick (section 8) --------------------------------------------------------------


def _just_one(what: str) -> Callable[[Change], str]:
    def summary(change: Change) -> str:
        if change.kind in ("shopped", "found"):
            return f"Just 1: took back {what}"
        return f"Just 1: {change.summary}"

    return summary


def answer_double_tick(act: Act) -> None:
    """Settle the card: "Yes, 2" keeps every purchase; "Just 1" takes back all but the
    first, in server order (L-3)."""
    kitchen = act.kitchen
    question = kitchen.db.get(DoubleTick, act.payload["question_id"])
    if question is None or question.household_id != kitchen.household_id:
        act.ignore("gone")
        return
    act.item_id, act.list_id = question.item_id, question.list_id
    if question.answer is not None:
        act.ignore("answered")
        return
    item = kitchen.db.get(ListItem, question.item_id)
    food = live_food(kitchen, item.food_id) if item is not None else None
    if item is None or food is None:  # pragma: no cover (the question goes with its item)
        act.ignore("gone")
        return
    act.food_id = food.id
    answer = act.payload["answer"]
    _settle(act, question, answer)
    standing = [
        tick
        for tick_id in question.tick_ids
        if (tick := get_tick(kitchen, tick_id)) is not None and tick.reversed_at is None
    ]
    size = next((_size(kitchen, t.bought_size_id) for t in standing if t.bought_size_id), None)
    size = size or usual_size(kitchen, food.id)
    if answer == "two":
        total = sum(t.bought_milli or 0 for t in standing)
        act.message = f"Kept {short_text(food, total, size)}"
        return
    extra = standing[1:]
    done: list[Change] = []
    for tick in extra:
        done += reverse(act, tick, _just_one(what_text(food, tick.bought_milli or 0, size)))
    sync_copy(kitchen, item, act.seq)
    if done:
        act.change = done[0]
    took = sum(t.bought_milli or 0 for t in extra)
    act.message = partial(done) or f"Took back {what_text(food, took, size)}"


HANDLERS: dict[str, Callable[[Act], None]] = {
    "tick": tick,
    "found_at_home": found_at_home,
    "untick": untick,
    "put_away": put_away,
    "different_pack": different_pack,
    "answer_double_tick": answer_double_tick,
}


# --- Undo (section 9) ----------------------------------------------------------------------------


def undo(act: Act, target: SyncAction) -> None:
    """`undo` of a tick-family action (the checks every Undo shares are already done)."""
    kitchen = act.kitchen
    kind = target.kind
    payload = target.payload or {}
    if kind in ("tick", "found_at_home"):
        tick = get_tick(kitchen, target.id)
        if tick is None:
            act.ignore("nothing_to_undo")
            return
        if tick.reversed_at is not None:
            act.ignore("already_undone")
            return
        done = reverse(act, tick, lambda change: f"Undid: {change.summary}")
        _remove_again(act, tick)
        item = kitchen.db.get(ListItem, tick.item_id)
        if item is not None:
            sync_copy(kitchen, item, act.seq)
        act.change = done[0] if done else None
        act.message = partial(done)
    elif kind == "untick" or (kind == "answer_double_tick" and payload.get("answer") == "one"):
        back = put_back(act, target)
        for tick in back:
            item = kitchen.db.get(ListItem, tick.item_id)
            if item is not None:
                sync_copy(kitchen, item, act.seq)
        if kind == "answer_double_tick":
            _reopen(act, target, back)
    elif kind == "answer_double_tick":
        if not _reopen(act, target, []):
            act.ignore("nothing_to_undo")
            return
    elif not _undo_changes(act, target):  # put_away, different_pack: 0.2's Undo of each
        act.ignore("already_undone")
        return
    target.undone_by_action_id = act.id
    shopping.notes_gone(kitchen, target.id, act.seq)


def _remove_again(act: Act, tick: ListTick) -> None:
    """A tick that brought its ingredient back (7.1): its Undo removes the ingredient again,
    as an Undo of an `add` does (5.9), unless it has stock or is on a list (0.2's rule)."""
    from mealwright.history import Tally, back_undone, undo_foods

    kitchen = act.kitchen
    for change in kitchen.db.scalars(
        select(Change).where(
            Change.household_id == kitchen.household_id,
            Change.tick_id == tick.id,
            Change.kind.in_(("shopped", "found")),
        )
    ):
        revived = (change.undo_data or {}).get("revived")
        if not revived or change.food_id is None:
            continue
        if shopping.still_needed(kitchen, change.food_id):
            continue  # it has stock or is on a list: removing it would hide that
        tally = Tally()
        touched = undo_foods(kitchen, revived, tally)
        if tally.done:
            shopping.bump_foods(kitchen, touched, act.batch)
        if change.undone_by_change_id is not None:  # the purchase's own Undo, just recorded
            back_undone(kitchen, revived, change.undone_by_change_id)


def later_repacks(kitchen: Kitchen, change: Change) -> list[Change]:
    """A purchase's `repacked` changes after this one that still stand, newest first.
    They are undone first: undoing an older repack on its own would fill its old lots
    again on top of the newer ones (7.4)."""
    if change.kind != "repacked" or not change.tick_id:
        return []
    return list(
        kitchen.db.scalars(
            select(Change)
            .where(
                Change.household_id == kitchen.household_id,
                Change.tick_id == change.tick_id,
                Change.kind == "repacked",
                Change.id > change.id,
                Change.undone_by_change_id.is_(None),
            )
            .order_by(Change.id.desc())
        )
    )


def _undo_changes(act: Act, target: SyncAction) -> bool:
    from mealwright.api.v1.changes import undo_change

    kitchen = act.kitchen
    ids = sorted((target.result or {}).get("changes", []), reverse=True)
    own = [
        change
        for change_id in ids
        if (change := kitchen.db.get(Change, change_id)) is not None
        and change.kind != "undo"
        and change.undone_by_change_id is None
    ]
    changes: list[Change] = []
    for change in own:
        for newer in [*later_repacks(kitchen, change), change]:
            if newer not in changes:
                changes.append(newer)
    for newer in changes:
        if newer in own:
            continue
        undone = shopping.action_row(kitchen, (newer.undo_data or {}).get("action"))
        if undone is not None and undone.undone_by_action_id is None:
            undone.undone_by_action_id = act.id
    done = [undo_change(kitchen, change, act.batch, act.id) for change in changes]
    if done:
        repacked = repack_back(kitchen, changes[-1], done)
        _say(done[-1], repacked)
        act.main_change = done[-1]
        act.message = repacked or partial(done)
    return bool(done)


def _reopen(act: Act, answered: SyncAction, back: list[ListTick]) -> bool:
    """Undo of an answer brings the card back (section 8)."""
    kitchen = act.kitchen
    question = kitchen.db.scalar(
        select(DoubleTick).where(
            DoubleTick.household_id == kitchen.household_id,
            DoubleTick.answer_action_id == answered.id,
        )
    )
    if question is None:
        return False
    already = open_question(kitchen, question.item_id)
    if already is not None:  # a newer card is open: the purchases join it
        added = [t.id for t in back if t.id not in already.tick_ids]
        already.tick_ids = [*already.tick_ids, *added]
        _who_sees(kitchen, already)
        already.version = act.seq
        return bool(back)
    standing = [
        tick_id
        for tick_id in question.tick_ids
        if (tick := get_tick(kitchen, tick_id)) is not None and tick.reversed_at is None
    ]
    if len(standing) < 2:
        return bool(back)
    _settle(act, question, None)
    return True


# --- Undo from Pantry → Recent changes (5.8) -----------------------------------------------------


def pantry_undo(kitchen: Kitchen, change: Change, batch: Batch) -> Change:
    """Undo from Pantry → Recent changes (api-0.2 6.5), keeping lists in step (5.8)."""
    from mealwright.api.v1.changes import undo_change

    tick = get_tick(kitchen, change.tick_id)
    if (
        tick is not None
        and change.kind in ("shopped", "found")
        and tick.change_id == change.id
        and tick.reversed_at is None
    ):
        return _untick_by_undo(kitchen, change, tick, batch)
    later = later_repacks(kitchen, change)
    first = [undo_change(kitchen, newer, batch, batch.action) for newer in later]
    done = undo_change(kitchen, change, batch, batch.action)
    _say(done, repack_back(kitchen, change, [*first, done]))
    if batch.taken or tick is not None:
        kind = "place_by_undo" if change.kind == "moved" and tick is not None else "undo"
        row = shopping.log_undo(batch, change, done, kind)
        if later:  # one Undo, as from a list (7.4): the later repacks are undone with it
            row.result = {"changes": [undo.id for undo in [*first, done]]}
            for newer in later:
                undone = shopping.action_row(kitchen, (newer.undo_data or {}).get("action"))
                if undone is not None and undone.undone_by_action_id is None:
                    undone.undone_by_action_id = row.id
    return done


def _untick_by_undo(kitchen: Kitchen, change: Change, tick: ListTick, batch: Batch) -> Change:
    """Undo of a purchase's own `shopped` change takes the whole purchase back and unticks
    it (SY-50)."""
    action = batch.action
    if shopping.action_row(kitchen, action) is not None:
        action = str(uuid.uuid4())
    act = Act(batch=batch, id=action, kind="untick_by_undo", payload={}, plain=True)
    act.seq = batch.number()
    done = reverse(act, tick, lambda each: f"Undid: {each.summary}")
    item = kitchen.db.get(ListItem, tick.item_id)
    if item is not None:
        sync_copy(kitchen, item, act.seq)
    own = next(undo for undo in done if undo.undoes_change_id == change.id)
    row = shopping.log_undo(batch, change, own, "untick_by_undo")
    row.result = {"changes": [undo.id for undo in done]}
    tick.reversed_by_action_id = row.id
    if item is not None:
        row.list_id, row.item_id = item.list_id, item.id
    return own


# --- The card (section 8) ------------------------------------------------------------------------

NUMBER_WORDS = {2: "two", 3: "three", 4: "four", 5: "five"}


class CardWords(NamedTuple):
    title: str
    text: str
    yes: str
    no: str


def _names(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def card_words(kitchen: Kitchen, question: DoubleTick, for_login_id: int) -> CardWords:
    """ "Did you buy 2?" for the login it's shown to (section 8, mockup Shop.dc.html)."""
    db = kitchen.db
    purchases = [
        tick for tick_id in question.tick_ids if (tick := get_tick(kitchen, tick_id)) is not None
    ]
    standing = [tick for tick in purchases if tick.reversed_at is None]
    shown = standing if len(standing) >= 2 else purchases
    count = len(shown)
    item = db.get(ListItem, question.item_id)
    food = db.get(Food, item.food_id) if item is not None else None
    name = food.name if food is not None else "it"
    people: list[str] = []
    seen: set[object] = set()
    for tick in shown:
        key = tick.login_id if tick.login_id is not None else tick.login_name
        if key in seen:
            continue
        seen.add(key)
        people.append("You" if tick.login_id == for_login_id else tick.login_name)
    people.sort(key=lambda person: person != "You")  # "You" first
    if len(people) <= 1:
        start = f"This was ticked on {NUMBER_WORDS.get(count, str(count))} phones"
    elif len(people) == 2:
        start = f"{_names(people)} both ticked {name}"
    else:
        start = f"{_names(people)} all ticked {name}"
    total = sum(tick.bought_milli or 0 for tick in shown)
    size_id = next((tick.bought_size_id for tick in shown if tick.bought_size_id), None)
    size = db.get(FoodSize, size_id) if size_id else None
    went = (
        amount_out(food, total, size).short.removesuffix(f"{NBSP}left")
        if food is not None and total
        else str(count)
    )
    if len(people) <= 1:
        text = f"{start}, so {went} went into the pantry."
    else:
        text = f"{start} while offline, so {went} went into the pantry."
    return CardWords(title=f"Did you buy {count}?", text=text, yes=f"Yes, {count}", no="Just 1")
