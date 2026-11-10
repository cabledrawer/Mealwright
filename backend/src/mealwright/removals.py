"""Removing a shop or a place from Settings → Shops & places, and putting it back with Undo
(spec section 6, "Shops & places in Settings").

A removed shop's ingredients (and the shopping lines in it) go to "Any shop". A removed place
can only go once nothing is in it: its packets and tubs are moved to another place first.
Neither table has a "removed" mark, so the row is deleted and its old id and details are kept
in the change, for Undo to make it again (`restore`, called by `undo_change`).
"""

from typing import Any

from fastapi import status
from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from mealwright import shopping
from mealwright.api.v1.context import Kitchen
from mealwright.errors import Problem
from mealwright.history import FoodEdit
from mealwright.models import (
    Change,
    ChangeLine,
    Food,
    ListItem,
    ListTick,
    Place,
    Shop,
    StockLot,
    Tub,
)
from mealwright.names import fold

KINDS = ("shop_removed", "place_removed", "shop_added", "shop_renamed")
# Ids per statement, well under SQLite's limit of 32,766 values.
CHUNK = 500


def _chunks(ids: list[Any]) -> list[list[Any]]:
    return [ids[i : i + CHUNK] for i in range(0, len(ids), CHUNK)]


# --- Shops ------------------------------------------------------------------------------------


def remove_shop(kitchen: Kitchen, shop: Shop) -> Change:
    """Take a shop away: its ingredients' usual shop becomes none, and the lines in it move
    to "Any shop" (their Undo steps are the ones a usual-shop change makes)."""
    db = kitchen.db
    name = shop.name
    foods = list(
        db.scalars(
            select(Food).where(Food.household_id == kitchen.household_id, Food.shop_id == shop.id)
        )
    )
    with FoodEdit(kitchen, [f.id for f in foods]) as edit:
        ops: list[dict[str, Any]] = []
        for food in foods:
            food.shop_id = None
            ops += shopping.follow_shop(kitchen, food, shop.id, edit.batch)
        moved = {op["item_id"] for op in ops}
        left = [
            item
            for item in db.scalars(
                select(ListItem).where(
                    ListItem.household_id == kitchen.household_id,
                    ListItem.shop_id == shop.id,
                    ListItem.deleted_at.is_(None),
                )
            )
            if item.id not in moved
        ]
        if left:
            seq = edit.batch.number()
            for item in left:
                ops.append({"op": "item_shop", "item_id": item.id, "old": shop.id, "new": None})
                item.shop_id = None
                item.version = seq
        if ops:
            edit.extra["shopping"] = ops
        edit.extra["removed"] = {
            "id": shop.id,
            "name": shop.name,
            "position": shop.position,
            "aisle_order": shop.aisle_order,
        }
        db.flush()
        db.delete(shop)
        db.flush()
    return edit.record("shop_removed", f"Removed the shop {name}", None)


# --- Places -----------------------------------------------------------------------------------


def things_in(db: DbSession, place: Place) -> int:
    """Packets and tubs with something left in them, here."""
    lots = db.scalars(
        select(StockLot.id).where(
            StockLot.household_id == place.household_id,
            StockLot.place_id == place.id,
            StockLot.amount_milli > 0,
        )
    )
    tubs = db.scalars(
        select(Tub.id).where(
            Tub.household_id == place.household_id,
            Tub.place_id == place.id,
            Tub.amount_quarters > 0,
        )
    )
    return len(list(lots)) + len(list(tubs))


def remove_place(kitchen: Kitchen, place: Place, move_to: Place | None) -> Change:
    """Take a place away. Refused (409) while it is the household's last Fridge or last Freezer
    (`last_of_kind`), and while it has things in it and no `move_to` (`place_not_empty`, with
    how many). The packets and tubs go to `move_to`; so do the places ingredients are usually
    kept in. Whatever else points here (empty packets kept for Undo, the log lines of earlier
    changes) goes to `move_to` or, with none, another place of the same kind."""
    db = kitchen.db
    others = [
        p
        for p in db.scalars(
            select(Place)
            .where(Place.household_id == kitchen.household_id, Place.id != place.id)
            .order_by(Place.position, Place.id)
        )
    ]
    if not others:
        # Only reachable with data made outside the app: Fridge and Freezer always stay.
        raise Problem(
            status.HTTP_409_CONFLICT,
            "last_of_kind",
            f"{place.name} is your only place, so it stays.",
            kind=place.kind,
        )
    if place.kind in ("fridge", "freezer") and not any(p.kind == place.kind for p in others):
        raise Problem(
            status.HTTP_409_CONFLICT,
            "last_of_kind",
            f"Mealwright needs a {place.kind}, and {place.name} is your last one, so it stays.",
            kind=place.kind,
        )
    count = things_in(db, place)
    if count and move_to is None:
        raise Problem(
            status.HTTP_409_CONFLICT,
            "place_not_empty",
            f"{place.name} has {count} {'thing' if count == 1 else 'things'} in it. Move them to…",
            things=count,
        )
    # An empty-handed place has nowhere to send the leftovers but a place of the same kind.
    fallback = move_to or next((p for p in others if p.kind == place.kind), others[0])
    soft = move_to.id if move_to is not None else None
    hid = kitchen.household_id
    foods = list(
        db.scalars(select(Food).where(Food.household_id == hid, Food.place_id == place.id))
    )
    lots = list(db.scalars(select(StockLot.id).where(StockLot.place_id == place.id)))
    tubs = list(db.scalars(select(Tub.id).where(Tub.place_id == place.id)))
    before = list(db.scalars(select(ChangeLine.id).where(ChangeLine.place_before_id == place.id)))
    after = list(db.scalars(select(ChangeLine.id).where(ChangeLine.place_after_id == place.id)))
    ticks = list(db.scalars(select(ListTick.id).where(ListTick.place_id == place.id)))
    items = list(
        db.scalars(
            select(ListItem).where(
                ListItem.household_id == hid, ListItem.put_away_place_id == place.id
            )
        )
    )
    name = place.name
    with FoodEdit(kitchen, [f.id for f in foods]) as edit:
        for food in foods:
            food.place_id = soft
        _point(db, StockLot, "place_id", lots, fallback.id)
        _point(db, Tub, "place_id", tubs, fallback.id)
        _point(db, ChangeLine, "place_before_id", before, fallback.id)
        _point(db, ChangeLine, "place_after_id", after, fallback.id)
        _point(db, ListTick, "place_id", ticks, soft)
        if items:
            seq = edit.batch.number()
            for item in items:
                item.put_away_place_id = soft
                item.version = seq
        edit.extra["removed"] = {
            "id": place.id,
            "name": place.name,
            "kind": place.kind,
            "position": place.position,
            "to": fallback.id,
            "soft_to": soft,
            "lots": lots,
            "tubs": tubs,
            "line_before": before,
            "line_after": after,
            "ticks": ticks,
            "items": [item.id for item in items],
        }
        db.flush()
        db.delete(place)
        db.flush()
    return edit.record("place_removed", f"Removed the place {name}", None)


def _point(db: DbSession, model: Any, column: str, ids: list[Any], to: int | None) -> None:
    for chunk in _chunks(ids):
        db.execute(update(model).where(model.id.in_(chunk)).values({column: to}))
    db.flush()


# --- Undo -------------------------------------------------------------------------------------


def _cannot_undo(detail: str) -> Problem:
    return Problem(status.HTTP_409_CONFLICT, "cannot_undo", detail)


def _undo_shop_edit(kitchen: Kitchen, change: Change) -> None:
    """Undo of "Added the shop X" (takes it away again, while nothing uses it) or of "Renamed
    the shop X to Y" (puts the old name back, while it is still called Y and no other shop
    has the old name). Anything else is refused and nothing is changed (F225)."""
    db = kitchen.db
    data = (change.undo_data or {}).get("shop") or {}
    shop = db.get(Shop, data.get("id"))
    if shop is None or shop.household_id != kitchen.household_id:
        raise _cannot_undo("That can’t be undone: the shop is gone.")  # proposed, for cabledrawer
    if change.kind == "shop_added":
        in_use = db.scalar(
            select(Food.id).where(
                Food.household_id == kitchen.household_id, Food.shop_id == shop.id
            )
        ) or db.scalar(
            select(ListItem.id).where(
                ListItem.household_id == kitchen.household_id,
                ListItem.shop_id == shop.id,
                ListItem.deleted_at.is_(None),
            )
        )
        if in_use is not None:
            raise _cannot_undo("That can’t be undone: the shop is in use now.")  # proposed
        db.delete(shop)
        db.flush()
        return
    if fold(shop.name) != fold(data["new"]):
        raise _cannot_undo("That can’t be undone: the shop has been renamed again.")  # proposed
    for other in db.scalars(select(Shop).where(Shop.household_id == kitchen.household_id)):
        if other.id != shop.id and fold(other.name) == fold(data["old"]):
            raise _cannot_undo(f"That can’t be undone: there’s already a shop called {other.name}.")
    shop.name = data["old"]
    db.flush()


def restore(kitchen: Kitchen, change: Change, batch: shopping.Batch) -> None:
    """Make the removed shop or place again, with its old id, before the rest of the Undo
    (ingredients, shopping lines) is put back. Refused when a newer one has taken its id."""
    if change.kind in ("shop_added", "shop_renamed"):
        _undo_shop_edit(kitchen, change)
        return
    data = (change.undo_data or {}).get("removed")
    if data is None:
        return
    db = kitchen.db
    model: type[Shop] | type[Place] = Shop if change.kind == "shop_removed" else Place
    taken: Place | Shop | None = (
        db.get(Shop, data["id"]) if model is Shop else db.get(Place, data["id"])
    )
    if taken is not None:
        # Another household's row on that id (ids once were reused) is not told about.
        mine = taken.household_id == kitchen.household_id
        raise Problem(
            status.HTTP_409_CONFLICT,
            "cannot_undo",
            "That can’t be undone: a newer "
            f"{'shop' if model is Shop else 'place'} has taken its place."  # proposed
            if mine
            else "That can’t be undone.",
        )
    if model is Shop:
        db.add(
            Shop(
                id=data["id"],
                household_id=kitchen.household_id,
                name=data["name"],
                position=data["position"],
                aisle_order=data["aisle_order"],
            )
        )
        db.flush()
        return
    db.add(
        Place(
            id=data["id"],
            household_id=kitchen.household_id,
            name=data["name"],
            kind=data["kind"],
            position=data["position"],
        )
    )
    db.flush()
    old, to, soft = data["id"], data["to"], data["soft_to"]
    # Each row goes back only if it still points where the removal put it.
    for model_, column, key, target in (
        (StockLot, "place_id", "lots", to),
        (Tub, "place_id", "tubs", to),
        (ChangeLine, "place_before_id", "line_before", to),
        (ChangeLine, "place_after_id", "line_after", to),
        (ListTick, "place_id", "ticks", soft),
    ):
        for chunk in _chunks(data[key]):
            col = getattr(model_, column)
            db.execute(
                update(model_)
                .where(model_.id.in_(chunk), col.is_(None) if target is None else col == target)
                .values({column: old})
            )
    if data["items"]:
        seq = batch.number()
        for chunk in _chunks(data["items"]):
            for item in db.scalars(
                select(ListItem).where(
                    ListItem.household_id == kitchen.household_id,
                    ListItem.id.in_(chunk),
                    ListItem.put_away_place_id.is_(None)
                    if soft is None
                    else ListItem.put_away_place_id == soft,
                )
            ):
                item.put_away_place_id = old
                item.version = seq
    db.flush()
