"""A staple's restock date (0.7; spec section 6, "Shopping rows", cabledrawer 20 Oct: "a restock
date per staple").

A staple isn't counted, so ticking it on Shopping puts nothing into the pantry: the row says
"Restocked · staples aren't counted". That tick is marked `list_tick.restock`. The restock
date is the newest such tick that still stands, so unticking it, or Undo, puts the date back
to the one before without anything else to keep in step. When the tidy-up deletes old
purchases, the newest restock among them is kept on the ingredient (`food.restocked_at`).

A date typed in the editor (or Restocked pressed there) wins (0.7 K5; cabledrawer 2 Nov: "when I
type a restock date, the pantry shows that date even if a Shopping tick is newer"): it is kept
in `food.restocked_at`, with the moment it was typed in `food.restock_typed_at`, and a tick
counts only if it was ticked after that moment. So a newer purchase wins again, and unticking
it, or Undo, brings the typed date back."""

from collections.abc import Iterable
from datetime import UTC, date, datetime, time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from mealwright.household import today, zone
from mealwright.models import Change, Food, Household, ListItem, ListTick, as_utc, utcnow


def aware(value: datetime | None) -> datetime | None:
    """`as_utc` that lets None through (D4, BE23: one rule for a stored time's zone)."""
    return None if value is None else as_utc(value)


def _ticks(db: DbSession, household_id: int, food_ids: list[int]) -> list[tuple[int, datetime]]:
    """Every standing "Restocked" tick of these foods, as (food id, when ticked)."""
    rows = db.execute(
        select(ListItem.food_id, ListTick.ticked_at)
        .join(ListItem, ListItem.id == ListTick.item_id)
        .where(
            ListTick.household_id == household_id,
            ListItem.household_id == household_id,
            ListItem.food_id.in_(food_ids),
            ListTick.restock.is_(True),
            ListTick.reversed_at.is_(None),
        )
    )
    return [(food_id, at) for food_id, at in rows if food_id is not None and at is not None]


def _counted(db: DbSession, household_id: int, foods: dict[int, Food]) -> dict[int, datetime]:
    """Each food's newest standing tick that counts: any, or with a typed date, only one
    ticked after the moment it was typed (cabledrawer 2 Nov)."""
    found: dict[int, datetime] = {}
    for food_id, at in _ticks(db, household_id, list(foods)):
        when = aware(at)
        moment = aware(foods[food_id].restock_typed_at)
        if when is None or (moment is not None and when <= moment):
            continue
        if food_id not in found or found[food_id] < when:
            found[food_id] = when
    return found


def restocked(db: DbSession, household_id: int, foods: Iterable[Food]) -> dict[int, datetime]:
    """When each staple among `foods` was last restocked; a food never restocked, or not a
    staple, is left out. The newer of the kept date and the newest tick that counts."""
    staples = {f.id: f for f in foods if f.staple and f.household_id == household_id}
    if not staples:
        return {}
    found: dict[int, datetime] = {}
    ticked = _counted(db, household_id, staples)
    for food_id, food in staples.items():
        dates = [d for d in (aware(food.restocked_at), ticked.get(food_id)) if d]
        if dates:
            found[food_id] = max(dates)
    return found


def typed(food: Food, when: datetime) -> None:
    """A date typed (or Restocked pressed) in the editor: it is shown from now on, until a
    tick made after this moment (cabledrawer 2 Nov: "the date I type wins")."""
    food.restocked_at = when
    food.restock_typed_at = utcnow()


def day(household: Household, when: datetime | None) -> tuple[date | None, int | None]:
    """The household's own day of a restock, and how many days ago that was ("Restocked
    3 weeks ago"), so the screens never depend on the device's clock or time zone."""
    if when is None:
        return None, None
    try:
        on = aware(when).astimezone(zone(household)).date()  # type: ignore[union-attr]
    except OverflowError:  # a stored value near year 1 or 9999 can't be shown: no date, no break
        return None, None
    return on, max((today(household) - on).days, 0)


def noon_on(household: Household, on: date) -> datetime:
    """A day picked in the editor, as a moment: the household's noon that day (it can't
    slip into the day before or after), or right now if the day is today."""
    if on == today(household):
        return utcnow()
    return datetime.combine(on, time(12), tzinfo=zone(household)).astimezone(UTC)


def merged(db: DbSession, household_id: int, into: Food, gone: Food) -> None:
    """For a merge of `gone` into `into`: the kept one shows the newer of the two dates shown.

    Live ticks aren't copied: they move with their shopping-list lines to `into` and speak for
    themselves, so unticking one still puts the date back. With a typed date on either, the
    later typed moment is kept, and a tick that counted but was ticked before it is folded into
    the kept date (it would no longer count by itself)."""
    moments = [m for m in (aware(into.restock_typed_at), aware(gone.restock_typed_at)) if m]
    moment = max(moments) if moments else None
    dates = [d for d in (aware(into.restocked_at), aware(gone.restocked_at)) if d]
    if moment is not None:
        foods = {into.id: into, gone.id: gone}
        for food_id, at in _ticks(db, household_id, list(foods)):
            when = aware(at)
            own = aware(foods[food_id].restock_typed_at)
            if when is None or (own is not None and when <= own):
                continue  # it didn't count before the merge either
            if when <= moment:
                dates.append(when)
    into.restocked_at = max(dates) if dates else None
    into.restock_typed_at = moment


def keep_before_tidy_up(db: DbSession, household_id: int, item_ids: list[str]) -> None:
    """The tidy-up is about to delete these items' purchases: keep each staple's newest
    standing restock among them that counts on the ingredient, so the date shown never
    changes. A tick at or before a typed date's moment doesn't count and is let go; one after
    it beats the typed date for good, so the kept date is no longer a typed one."""
    rows = db.execute(
        select(ListItem.food_id, ListTick.ticked_at)
        .join(ListItem, ListItem.id == ListTick.item_id)
        .where(
            ListTick.household_id == household_id,
            ListTick.item_id.in_(item_ids),
            ListTick.restock.is_(True),
            ListTick.reversed_at.is_(None),
        )
    )
    newest: dict[int, datetime] = {}
    for food_id, at in rows:
        when = aware(at)
        if food_id is None or when is None:
            continue
        if food_id not in newest or newest[food_id] < when:
            newest[food_id] = when
    _fold_into_undo(db, household_id, newest)
    for food_id, at in newest.items():
        food = db.get(Food, food_id)
        if food is None or food.household_id != household_id:
            continue
        moment = aware(food.restock_typed_at)
        if moment is not None:
            if at <= moment:
                continue
            food.restock_typed_at = None
        kept = aware(food.restocked_at)
        if kept is None or kept < at:
            food.restocked_at = at


def _parsed(value: Any) -> datetime | None:
    return aware(datetime.fromisoformat(value)) if isinstance(value, str) else None


def _fold_into_undo(db: DbSession, household_id: int, newest: dict[int, datetime]) -> None:
    """The purchases the tidy-up deletes can't speak for themselves any more, so an Undo
    that puts back a restock date from before a change (a typed date, a merge) would forget
    them. Each such Undo's date-before is raised to the newest deleted purchase that counted
    then (no typed moment then, or ticked after it), so an Undo never shows an older date
    than a real purchase (fix round 1)."""
    if not newest:
        return
    pending = db.scalars(
        select(Change).where(
            Change.household_id == household_id,
            Change.undone_by_change_id.is_(None),
            Change.undo_data.is_not(None),
        )
    )
    for change in pending:
        data = change.undo_data or {}
        foods = data.get("foods")
        if not isinstance(foods, dict) or not isinstance(foods.get("fields"), dict):
            continue
        fields: dict[str, Any] = foods["fields"]
        raised = dict(fields)
        for food_id, at in newest.items():
            pair = fields.get(f"{food_id}:restocked_at")
            if not isinstance(pair, list) or len(pair) != 2:
                continue
            moment_pair = fields.get(f"{food_id}:restock_typed_at")
            if isinstance(moment_pair, list) and len(moment_pair) == 2:
                moment_then = _parsed(moment_pair[0])
            else:  # not changed by it: as it is now
                food = db.get(Food, food_id)
                moment_then = aware(food.restock_typed_at) if food is not None else None
            if moment_then is not None and at <= moment_then:
                continue  # it didn't count before the change either
            before = _parsed(pair[0])
            if before is None or before < at:
                raised[f"{food_id}:restocked_at"] = [at.isoformat(), pair[1]]
        if raised != fields:
            change.undo_data = {**data, "foods": {**foods, "fields": raised}}
