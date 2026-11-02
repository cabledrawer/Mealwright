"""A staple's restock date (0.7; spec section 6, "Shopping rows", cabledrawer 20 Oct: "a restock
date per staple").

A staple isn't counted, so ticking it on Shopping puts nothing into the pantry: the row says
"Restocked · staples aren't counted". That tick is marked `list_tick.restock`. The restock
date is the newest such tick that still stands, so unticking it, or Undo, puts the date back
to the one before without anything else to keep in step. When the tidy-up deletes old
purchases, the newest restock among them is kept on the ingredient (`food.restocked_at`).
"""

from collections.abc import Iterable
from datetime import UTC, date, datetime, time

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from mealwright.household import today, zone
from mealwright.models import Food, Household, ListItem, ListTick


def _aware(value: datetime | None) -> datetime | None:
    # SQLite gives back naive datetimes; every time Mealwright stores is UTC.
    if value is None or value.tzinfo is not None:
        return value
    return value.replace(tzinfo=UTC)


def _ticked(db: DbSession, household_id: int, food_ids: list[int]) -> dict[int, datetime]:
    rows = db.execute(
        select(ListItem.food_id, func.max(ListTick.ticked_at))
        .join(ListItem, ListItem.id == ListTick.item_id)
        .where(
            ListTick.household_id == household_id,
            ListItem.household_id == household_id,
            ListItem.food_id.in_(food_ids),
            ListTick.restock.is_(True),
            ListTick.reversed_at.is_(None),
        )
        .group_by(ListItem.food_id)
    )
    return {food_id: at for food_id, at in rows if at is not None}


def restocked(db: DbSession, household_id: int, foods: Iterable[Food]) -> dict[int, datetime]:
    """When each staple among `foods` was last restocked; a food never restocked, or not a
    staple, is left out."""
    staples = {f.id: f for f in foods if f.staple and f.household_id == household_id}
    if not staples:
        return {}
    found: dict[int, datetime] = {}
    ticked = _ticked(db, household_id, list(staples))
    for food_id, food in staples.items():
        dates = [d for d in (_aware(food.restocked_at), _aware(ticked.get(food_id))) if d]
        if dates:
            found[food_id] = max(dates)
    return found


def ticked_at(db: DbSession, household_id: int, food_id: int) -> datetime | None:
    """The newest "Restocked" tick on Shopping that still stands for this food, if any."""
    return _aware(_ticked(db, household_id, [food_id]).get(food_id))


def day(household: Household, when: datetime | None) -> tuple[date | None, int | None]:
    """The household's own day of a restock, and how many days ago that was ("Restocked
    3 weeks ago"), so the screens never depend on the device's clock or time zone."""
    if when is None:
        return None, None
    try:
        on = _aware(when).astimezone(zone(household)).date()  # type: ignore[union-attr]
    except OverflowError:  # a stored value near year 1 or 9999 can't be shown: no date, no break
        return None, None
    return on, max((today(household) - on).days, 0)


def noon_on(household: Household, on: date) -> datetime:
    """A day picked in the editor, as a moment: the household's noon that day (it can't
    slip into the day before or after), or right now if the day is today."""
    if on == today(household):
        return datetime.now(UTC)
    return datetime.combine(on, time(12), tzinfo=zone(household)).astimezone(UTC)


def newer(into: Food, gone: Food) -> datetime | None:
    """For a merge of `gone` into `into`: the restock date to keep on `into`, the newer of
    the two kept dates. Live ticks aren't copied: they move with their shopping-list lines to
    `into` and speak for themselves, so unticking one still puts the date back."""
    dates = [d for d in (_aware(into.restocked_at), _aware(gone.restocked_at)) if d]
    return max(dates) if dates else None


def keep_before_tidy_up(db: DbSession, household_id: int, item_ids: list[str]) -> None:
    """The tidy-up is about to delete these items' purchases: keep each staple's newest
    standing restock among them on the ingredient."""
    rows = db.execute(
        select(ListItem.food_id, func.max(ListTick.ticked_at))
        .join(ListItem, ListItem.id == ListTick.item_id)
        .where(
            ListTick.household_id == household_id,
            ListTick.item_id.in_(item_ids),
            ListTick.restock.is_(True),
            ListTick.reversed_at.is_(None),
        )
        .group_by(ListItem.food_id)
    )
    for food_id, at in rows:
        food = db.get(Food, food_id)
        if food is None or food.household_id != household_id or at is None:
            continue
        at = at if at.tzinfo is not None else at.replace(tzinfo=UTC)
        kept = _aware(food.restocked_at)
        if kept is None or kept < at:
            food.restocked_at = at
