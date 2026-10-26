"""The household's own settings: time zone, cup size, and the places every household has."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from mealwright.amounts import DEFAULT_CUP_ML
from mealwright.errors import Problem
from mealwright.models import DEFAULT_PLACES, DEFAULT_SLOTS, Household, MealSlot, Place, utcnow

UTC_ZONE = ZoneInfo("UTC")


_NOT_A_PLACE = {"localtime", "Factory", "posixrules"}


def valid_time_zone(name: str) -> bool:
    """UTC or an Area/City name from the time-zone database ("Europe/London"). Not
    "localtime" (that's the server's own zone), "Factory" or "posixrules"."""
    if name in _NOT_A_PLACE or name not in available_timezones():
        return False
    if name != "UTC" and "/" not in name:
        return False
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError, ValueError:
        return False
    return True


def zone(household: Household) -> ZoneInfo:
    """The household's local time zone (spec section 6: "the household's local time, not
    UTC"). Until the admin's browser has sent it, UTC."""
    if household.time_zone:
        try:
            return ZoneInfo(household.time_zone)
        except ZoneInfoNotFoundError, ValueError:
            pass
    return UTC_ZONE


def today(household: Household, at: datetime | None = None) -> date:
    return (at or utcnow()).astimezone(zone(household)).date()


def cup_ml(household: Household) -> int:
    return household.cup_ml or DEFAULT_CUP_ML


def undo_window(household: Household) -> timedelta:
    return timedelta(days=household.undo_days)


def add_default_places(db: DbSession, household_id: int) -> None:
    """Fridge, Freezer, Cupboard and Spice rack (renameable from 0.8)."""
    for position, (name, kind) in enumerate(DEFAULT_PLACES):
        db.add(Place(household_id=household_id, name=name, kind=kind, position=position))


def places(db: DbSession, household_id: int) -> list[Place]:
    return list(
        db.scalars(
            select(Place)
            .where(Place.household_id == household_id)
            .order_by(Place.position, Place.id)
        )
    )


# At most this many meal slots a household can have. Proposed, for cabledrawer. GET /plan passes lists
# of ids to the database, and SQLite takes at most 32,766 values in one query: a 62-day range
# with 12 slots of 20 items is at most 62 x 12 x 20 = 14,880 (see MOST_ITEMS_IN_MEAL, plan.py).
MOST_SLOTS = 12


def add_slot(db: DbSession, household_id: int, name: str, enabled: bool = True) -> MealSlot:
    """Make a meal slot (the later Settings screen uses this too). Refused past MOST_SLOTS."""
    have = list(meal_slots(db, household_id))
    if len(have) >= MOST_SLOTS:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "too_many_slots",
            f"A household can have at most {MOST_SLOTS} meals.",  # proposed, for cabledrawer
        )
    slot = MealSlot(
        household_id=household_id,
        name=name,
        position=(have[-1].position + 1) if have else 0,
        enabled=enabled,
    )
    db.add(slot)
    db.flush()
    return slot


def add_default_slots(db: DbSession, household_id: int) -> None:
    """Breakfast, Lunch, Snack (off) and Dinner (renameable and reorderable from 0.6)."""
    for name, enabled in DEFAULT_SLOTS:
        add_slot(db, household_id, name, enabled)


def meal_slots(db: DbSession, household_id: int) -> list[MealSlot]:
    return list(
        db.scalars(
            select(MealSlot)
            .where(MealSlot.household_id == household_id)
            .order_by(MealSlot.position, MealSlot.id)
        )
    )
