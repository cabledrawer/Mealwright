"""Settings changes that are listed in Recent changes with an Undo (RF5, H8; cabledrawer 11 Nov):
adding or renaming a place, putting the shops or the places in order, the kitchen's equipment
and the Batch cook switch. Shops already were (F225, in `removals.py`).

Each change keeps what the Undo needs in `undo_data`, and the Undo is refused, with nothing
changed, when what it would put back has been changed again since (the same rule as the
shop's rename)."""

from typing import Any

from fastapi import status
from sqlalchemy import select

from mealwright.api.v1.context import Kitchen
from mealwright.errors import Problem
from mealwright.history import record
from mealwright.models import (
    Change,
    ChangeLine,
    Food,
    ListItem,
    ListTick,
    Place,
    Shop,
    StockLot,
    StocktakeEntry,
    StocktakePlace,
    Tub,
)
from mealwright.names import fold

KINDS = (
    "place_added",
    "place_renamed",
    "shops_ordered",
    "places_ordered",
    "kitchen_changed",
    "batch_cook_switch",
)


def _cannot_undo(detail: str) -> Problem:
    return Problem(status.HTTP_409_CONFLICT, "cannot_undo", detail)  # proposed, for cabledrawer


# --- Recording ----------------------------------------------------------------------------------


def place_added(kitchen: Kitchen, place: Place) -> Change:
    return record(
        kitchen,
        "place_added",
        f"Added the place {place.name}",
        None,
        {"place": {"id": place.id, "new": place.name, "kind": place.kind}},
    )


def place_renamed(kitchen: Kitchen, place: Place, old: str) -> Change:
    return record(
        kitchen,
        "place_renamed",
        f"Renamed the place {old} to {place.name}",
        None,
        {"place": {"id": place.id, "old": old, "new": place.name, "kind": place.kind}},
    )


def ordered(kitchen: Kitchen, kind: str, old: dict[int, int], new: dict[int, int]) -> Change | None:
    """A new order of the shops (`kind` shops_ordered) or the places (places_ordered), as each
    row's position before and after. Nothing is recorded when the order is the same."""
    if old == new:
        return None
    words = "shops" if kind == "shops_ordered" else "places"
    return record(
        kitchen,
        kind,
        f"Changed the order of the {words}",
        None,
        {
            "order": {
                "old": {str(k): v for k, v in old.items()},
                "new": {str(k): v for k, v in new.items()},
            }
        },
    )


def _count(n: int, one: str, many: str) -> str:
    return f"no {one}" if n == 0 else f"{n} {one if n == 1 else many}"


def kitchen_equipment(kitchen: Kitchen, old: dict[str, Any], new: dict[str, Any]) -> Change | None:
    """The kitchen's hob rings, pressure cookers and oven, before and after. Nothing is
    recorded when none of them changed (saving it for the first time still counts as asked)."""
    if old == new:
        return None
    parts: list[str] = []
    if old["hob_rings"] != new["hob_rings"]:
        parts.append(
            f"{_count(new['hob_rings'], 'hob ring', 'hob rings')} (was {old['hob_rings']})"
        )
    if old["pressure_cookers"] != new["pressure_cookers"]:
        parts.append(
            f"{_count(new['pressure_cookers'], 'pressure cooker', 'pressure cookers')} "
            f"(was {old['pressure_cookers']})"
        )
    if old["oven"] != new["oven"]:
        parts.append(
            f"{'an oven' if new['oven'] else 'no oven'} (was {'yes' if old['oven'] else 'no'})"
        )
    return record(
        kitchen,
        "kitchen_changed",
        f"Changed your kitchen: {', '.join(parts)}",
        None,
        {"kitchen": {"old": old, "new": new}},
    )


def batch_cook_switch(kitchen: Kitchen, shown: bool) -> Change:
    return record(
        kitchen,
        "batch_cook_switch",
        f"Switched Batch cook {'on' if shown else 'off'}",
        None,
        {"batch_cook": {"old": not shown, "new": shown}},
    )


# --- Undo -----------------------------------------------------------------------------------


def undo(kitchen: Kitchen, change: Change) -> None:
    """Put one of these changes back, or refuse (409 `cannot_undo`) and change nothing."""
    data = change.undo_data or {}
    if change.kind == "place_added":
        _undo_place_added(kitchen, data["place"])
    elif change.kind == "place_renamed":
        _undo_place_renamed(kitchen, data["place"])
    elif change.kind in ("shops_ordered", "places_ordered"):
        _undo_order(kitchen, change.kind, data["order"])
    elif change.kind == "kitchen_changed":
        _undo_kitchen(kitchen, data["kitchen"])
    elif change.kind == "batch_cook_switch":
        household = kitchen.household
        if (not household.batch_cook_hidden) != data["batch_cook"]["new"]:
            raise _cannot_undo("That can’t be undone: Batch cook has been switched again.")
        household.batch_cook_hidden = not data["batch_cook"]["old"]
        kitchen.db.flush()


def _my_place(kitchen: Kitchen, data: dict[str, Any]) -> Place:
    place = kitchen.db.get(Place, data["id"])
    if place is None or place.household_id != kitchen.household_id:
        raise _cannot_undo("That can’t be undone: the place is gone.")
    return place


def _undo_place_added(kitchen: Kitchen, data: dict[str, Any]) -> None:
    db = kitchen.db
    place = _my_place(kitchen, data)
    in_use = (
        db.scalar(select(StockLot.id).where(StockLot.place_id == place.id).limit(1))
        or db.scalar(select(Tub.id).where(Tub.place_id == place.id).limit(1))
        or db.scalar(select(Food.id).where(Food.place_id == place.id).limit(1))
        or db.scalar(select(ListItem.id).where(ListItem.put_away_place_id == place.id).limit(1))
        or db.scalar(select(ListTick.id).where(ListTick.place_id == place.id).limit(1))
        or db.scalar(
            select(StocktakePlace.place_id).where(StocktakePlace.place_id == place.id).limit(1)
        )
        or db.scalar(select(StocktakeEntry.id).where(StocktakeEntry.place_id == place.id).limit(1))
        or db.scalar(
            select(ChangeLine.id)
            .where(
                (ChangeLine.place_before_id == place.id) | (ChangeLine.place_after_id == place.id)
            )
            .limit(1)
        )
    )
    if in_use is not None:
        raise _cannot_undo("That can’t be undone: the place is in use now.")
    if place.kind in ("fridge", "freezer") and not db.scalar(
        select(Place.id)
        .where(
            Place.household_id == kitchen.household_id,
            Place.kind == place.kind,
            Place.id != place.id,
        )
        .limit(1)
    ):
        # The same rule as removing a place: Mealwright keeps a Fridge and a Freezer.
        raise _cannot_undo(  # proposed, for cabledrawer
            f"That can’t be undone: {place.name} is your only {place.kind} now."
        )
    db.delete(place)
    db.flush()


def _undo_place_renamed(kitchen: Kitchen, data: dict[str, Any]) -> None:
    place = _my_place(kitchen, data)
    if fold(place.name) != fold(data["new"]):
        raise _cannot_undo("That can’t be undone: the place has been renamed again.")
    for other in kitchen.db.scalars(
        select(Place).where(Place.household_id == kitchen.household_id)
    ):
        if other.id != place.id and fold(other.name) == fold(data["old"]):
            raise _cannot_undo(
                f"That can’t be undone: there’s already a place called {other.name}."
            )
    place.name = data["old"]
    kitchen.db.flush()


def _undo_order(kitchen: Kitchen, kind: str, data: dict[str, Any]) -> None:
    """Each row goes back to its old position, but only while every row still there is where
    the change put it (anything moved since, and the order isn't the one this change made)."""
    rows: dict[int, Shop | Place] = {}
    if kind == "shops_ordered":
        for shop in kitchen.db.scalars(
            select(Shop).where(Shop.household_id == kitchen.household_id)
        ):
            rows[shop.id] = shop
    else:
        for place in kitchen.db.scalars(
            select(Place).where(Place.household_id == kitchen.household_id)
        ):
            rows[place.id] = place
    here = {int(k): v for k, v in data["new"].items() if int(k) in rows}
    if any(rows[i].position != position for i, position in here.items()):
        raise _cannot_undo("That can’t be undone: the order has been changed again.")
    for key, position in data["old"].items():
        if int(key) in rows:
            rows[int(key)].position = position
    kitchen.db.flush()


def _undo_kitchen(kitchen: Kitchen, data: dict[str, Any]) -> None:
    household = kitchen.household
    now = {
        "hob_rings": household.kitchen_hob_rings,
        "pressure_cookers": household.kitchen_pressure_cookers,
        "oven": household.kitchen_oven,
    }
    changed = [k for k in now if data["old"][k] != data["new"][k]]
    if any(now[k] != data["new"][k] for k in changed):
        raise _cannot_undo("That can’t be undone: your kitchen has been changed again.")
    # `asked` stays as it is: the kitchen was asked, whatever the numbers.
    for key in changed:
        setattr(household, f"kitchen_{key}", data["old"][key])
    kitchen.db.flush()
