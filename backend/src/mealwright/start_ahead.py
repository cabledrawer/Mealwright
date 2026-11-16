"""The plan works backwards (0.8 wave 5, M3, F124; cabledrawer 31 Oct and 9 Nov).

A recipe with a long wait (a step that waits four hours or more: soak, ferment, marinate) asks
when the wait will be started when it is added to the plan. The day before, Today and the Cook
view say "Start tonight at 21:00"; on day two Cook mode starts after the step that waited. In the
app only: nothing here sends anything and no job runs.

Times are instants (UTC) in the database. The household's own time zone turns them into a day and
a clock time and back, so a start of "Fri 21:00" is 21:00 on the wall whatever the clocks did.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from mealwright import methods, step_waits
from mealwright.history import as_utc
from mealwright.household import zone
from mealwright.models import Household, MealSlot, Recipe, RecipeMethod, RecipeStep

# A wait counts as "ahead" when even its shortest length is this long (four hours: marinate
# 4-24 h, soak overnight, ferment 8-12 h). A rest of an hour or two is part of the cooking day.
# Proposed, for cabledrawer.
MIN_AHEAD_MINUTES = 4 * 60
# The furthest back a start can be from its meal (the longest wait the recipe can hold).
MOST_BEFORE = timedelta(minutes=step_waits.MAX_WAIT_MINUTES + 24 * 60)
# How many days past a screen's last day the plan is read so that every start that falls on it is
# found (a meal that far on can have its start on the screen's last day): the same for Today
# and the Plan (RF3, H6). The frontend's `START_DAYS_AHEAD` (plan.svelte.ts) is this number.
MOST_DAYS_AHEAD = MOST_BEFORE.days + (1 if MOST_BEFORE.seconds else 0)

# The time a meal slot is eaten when nothing says (there is no setting for it yet: proposed, for
# cabledrawer). Found by the slot's own name, by whole words ("Steak night" has no "tea" in it); a
# slot with none of these words is eaten at noon. "morning", "evening" and "night" too (RF3, H7;
# cabledrawer 11 Nov).
_SLOT_TIMES = (
    ("breakfast", time(8, 0)),
    ("brunch", time(10, 30)),
    ("lunch", time(12, 30)),
    ("tiffin", time(12, 30)),
    ("snack", time(16, 0)),
    ("dinner", time(19, 0)),
    ("supper", time(19, 0)),
    ("tea", time(17, 30)),
    ("morning", time(8, 0)),
    ("evening", time(19, 0)),
    ("night", time(19, 0)),
)
_NOON = time(12, 0)


@dataclass(frozen=True)
class Ahead:
    """The step whose wait is started ahead, and what it needs."""

    step_id: int
    step_text: str
    wait: step_waits.Wait
    # The recipe's own working time for this way of cooking it (not the wait: a saved Time that
    # already holds the wait has it taken off, F228), or None.
    active_minutes: int | None


@dataclass(frozen=True)
class Option:
    start: datetime  # an instant (UTC)
    ready_by: datetime


def slot_time(slot: MealSlot | None) -> time:
    """When a slot's meal is eaten."""
    words = set(re.findall(r"[^\W_]+", (slot.name if slot else "").casefold()))
    for word, at in _SLOT_TIMES:
        if word in words:
            return at
    return _NOON


def to_instant(household: Household, day: date, at: time) -> datetime:
    """A wall-clock time on a day in the household's zone, as an instant (UTC). A time the clocks
    skipped (the hour that goes missing in spring) is the same moment read an hour on."""
    local = datetime.combine(day, at, tzinfo=zone(household))
    return local.astimezone(UTC)


def local_of(household: Household, instant: datetime) -> datetime:
    return as_utc(instant).astimezone(zone(household))


def clock_words(at: time) -> str:
    return f"{at.hour:02d}:{at.minute:02d}"


def eat_instant(household: Household, day: date, slot: MealSlot | None) -> datetime:
    return to_instant(household, day, slot_time(slot))


def of_steps(
    steps: Sequence[RecipeStep],
    active_minutes: int | None,
    minimum: int = MIN_AHEAD_MINUTES,
    work_only: bool = False,
) -> Ahead | None:
    """The first step (in order) whose wait is at least `minimum` minutes at its shortest.
    `active_minutes` is the recipe's saved Time (for the way of cooking it), and is turned into its
    work: a Time that already holds the recipe's waits (Dosa Batter: 745 min with an 8-12 h
    ferment) has them taken off, the same rule as `step_waits.active_time` (F228; proposed, for
    cabledrawer, cabledrawer 12 Nov). Give every step of the way, so that all its waits come off.
    `work_only`: the saved Time is already the work, the wait taken off at import (L6, hidden
    mark; proposed, for cabledrawer): it is left alone, never taken off twice."""
    waits = [w for w in (step_waits.of_step(step) for step in steps) if w is not None]
    work = active_minutes if work_only else step_waits.active_time(active_minutes, waits)
    for step in steps:
        wait = step_waits.of_step(step)
        if wait is not None and wait.min_minutes >= minimum:
            return Ahead(step.id, step.text, wait, work)
    return None


def ahead_of(
    db: DbSession, recipe: Recipe, method_id: int | None, ways: Sequence[RecipeMethod] | None = None
) -> Ahead | None:
    """The wait to start ahead in the way of cooking a meal uses (its own method, else the
    recipe's first), or None when no step waits that long."""
    found = list(ways) if ways is not None else methods.methods_of(db, recipe.id)
    method = methods.named(found, method_id)
    steps = [
        s
        for s in db.scalars(
            select(RecipeStep)
            .where(RecipeStep.recipe_id == recipe.id, RecipeStep.kind == "step")
            .order_by(RecipeStep.position, RecipeStep.id)
        )
        if methods.in_method(s, found, method)
    ]
    minutes = method.time_minutes if method is not None else recipe.time_minutes
    marked = method.time_is_work_only if method is not None else recipe.time_is_work_only
    return of_steps(steps, minutes, work_only=marked)


def _floor_hour(instant: datetime, household: Household) -> datetime:
    local = local_of(household, instant)
    return local.replace(minute=0, second=0, microsecond=0).astimezone(UTC)


def _ceil_five(instant: datetime) -> datetime:
    instant = instant.replace(second=0, microsecond=0)
    return instant + timedelta(minutes=(-instant.minute) % 5)


def options(
    household: Household, ahead: Ahead, day: date, slot: MealSlot | None, now: datetime
) -> list[Option]:
    """Up to two times to start, for a meal eaten at its slot's time: one that puts the wait in
    the middle of its range, and an earlier one that is ready even if the wait is the longest.
    Whole hours on the household's clock, counted back in real hours (a wait is as long as the
    clocks say it is, so a night with a clock change is an hour longer or shorter), and none that
    has already gone by. When both have gone by there is one more,
    starting at once (still offered when it is ready after the meal's time: that is the person's
    choice). A meal whose time has gone by has none: nothing can be started ahead of it. The same
    meal on the same day always gets the same options."""
    eat = eat_instant(household, day, slot)
    if eat <= now:
        return []
    active = timedelta(minutes=ahead.active_minutes or 0)
    low, high = ahead.wait.min_minutes, ahead.wait.max_minutes
    middle = timedelta(minutes=(low + high) // 2)
    longest = timedelta(minutes=high)
    found: list[Option] = []
    first = _floor_hour(eat - (middle + active), household)
    found.append(Option(first, eat))
    second = _floor_hour(eat - (longest + active), household)
    if second < first:
        found.append(Option(second, second + longest + active))
    found = [o for o in found if o.start > now]
    if not found:
        begin = _ceil_five(now)
        # Starting at once is offered only when it is still before the meal: a time the save
        # would refuse ("Pick a time before the meal.") is no option (RF3, H4). It is offered
        # even when it cannot be ready by then, saying when it would be (the sheet warns).
        if begin < eat:
            found.append(Option(begin, begin + timedelta(minutes=low) + active))
    return found


def check_start(household: Household, start: datetime, eat: datetime) -> bool:
    """A start has to be before the meal and not further back than the longest wait a recipe can
    hold (a start a year early is a slip)."""
    return start < eat and eat - start <= MOST_BEFORE


@dataclass(frozen=True)
class Shown:
    """What the plan says about one item's wait: the times as the household's wall clock."""

    ahead: Ahead
    eats_at: time
    start_day: date | None
    start_time: time | None
    started_day: date | None
    started_time: time | None
    waited_minutes: int | None


def shown(
    household: Household,
    ahead: Ahead,
    slot: MealSlot | None,
    start_at: datetime | None,
    started_at: datetime | None,
    now: datetime,
) -> Shown:
    start = local_of(household, start_at) if start_at else None
    done = local_of(household, started_at) if started_at else None
    waited = max(0, int((now - as_utc(started_at)).total_seconds() // 60)) if started_at else None
    return Shown(
        ahead=ahead,
        eats_at=slot_time(slot),
        start_day=start.date() if start else None,
        start_time=start.time().replace(second=0, microsecond=0) if start else None,
        started_day=done.date() if done else None,
        started_time=done.time().replace(second=0, microsecond=0) if done else None,
        waited_minutes=waited,
    )
