"""A staple's restock date (0.7; spec section 6, "Shopping rows", cabledrawer 20 Oct: "a restock
date per staple").

A staple isn't counted, so ticking it on Shopping puts nothing into the pantry: the row says
"Restocked · staples aren't counted". That tick is marked `list_tick.restock`. The restock
date is the newest such tick that still stands, so unticking it, or Undo, puts the date back
to the one before without anything else to keep in step. When the tidy-up deletes old
purchases, the newest restock among them is kept on the ingredient (`food.restocked_at`).
"""

from collections.abc import Iterable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session as DbSession

from mealwright.models import Food, ListItem, ListTick


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


def newer(db: DbSession, household_id: int, gone: Food, into: Food) -> datetime | None:
    """For a merge of `gone` into `into`: the restock date to keep on `into`, the newer of
    the two (its own kept date, or `gone`'s restock date, ticks included, if `gone` is a
    staple). The ticks move with their shopping-list lines, so that date stays either way."""
    dates = [d for d in (_aware(into.restocked_at), _aware(gone.restocked_at)) if d]
    from_ticks = restocked(db, household_id, [gone]).get(gone.id)
    if from_ticks is not None:
        dates.append(from_ticks)
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
