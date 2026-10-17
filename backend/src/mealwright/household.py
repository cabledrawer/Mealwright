"""The household's own settings: time zone, cup size, and the places every household has."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError, available_timezones

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from mealwright.amounts import DEFAULT_CUP_ML
from mealwright.models import DEFAULT_PLACES, Household, Place, utcnow

UTC_ZONE = ZoneInfo("UTC")


def valid_time_zone(name: str) -> bool:
    if name not in available_timezones():
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
