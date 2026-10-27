"""Today's answers (0.6 PR 6): "Did you cook Sambar yesterday?" -> Cooked it, Didn't, Move it.

A planned meal whose day has come (today or earlier) is asked about. Nothing changes in the
pantry until it is answered (spec, "Meals nobody cooked"), and **no answer touches the pantry in
0.6**: taking the ingredients out of it is 0.7's "Cooked it" review (BUILD-PLAN 0.7). What an
answer does:

- **Cooked it**: the meal becomes `cooked` and is locked. "Any left over?" (optional) makes tubs
  of one of its recipes: a batch cook (the meal's own, or a new one) with that many tubs, each in
  the fridge or the freezer with a use-by (the household's tub life from the meal's day, or the
  date the person chose). The tubs are in no meal: they are "tubs left".
- **Didn't**: the meal becomes `didnt`. Nothing else.
- **Move it**: the meal becomes `moved` and keeps its slot (cabledrawer 26 Oct: "A meal marked
  moved still holds its slot"). What it held goes to the day and meal chosen: a recipe or an
  ingredient is copied there (the old meal stays as the record of what was planned), a tub moves
  there (a tub is in one meal at a time). A meal that already has food gets it alongside.

Each is one Change with an Undo (`undo_data["plan"]`, see plan.py); the shopping list follows the
plan afterwards, so a meal that was not cooked or was moved drops off it by itself (a moved
meal's food is counted again at its new day).

Proposed, for cabledrawer (each is one rule here, easy to change later):

- A meal can be answered on its own day or after it, never before (`not_yet`).
- "Any left over?" is about one recipe: the one named by `item_id`, else the meal's first recipe.
  A meal with no recipe in it has no leftovers to keep (`no_recipe`).
- The tubs' use-by counts from the meal's day, as the mockup does ("Sat dinner … use by Tue
  27 Oct · 3 days"), not from the day it is answered.
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from fastapi import status
from sqlalchemy import func, select

from mealwright.api.v1.context import Kitchen
from mealwright.batches import (
    MOST_TUBS_IN_BATCH,
    _batches_that_day,
    next_colour,
    places_of_kind,
    tub_use_by,
)
from mealwright.errors import Problem, not_found
from mealwright.household import today
from mealwright.models import BatchCook, Change, Meal, MealItem, MealSlot, Recipe, Tub
from mealwright.plan import (
    _bring,
    _copy_of,
    _finish,
    _make_meal,
    _meal_name,
    _own,
    _planned,
    _room,
    _where,
    check_day,
    find_slot,
    items_of,
    meal_at,
)

# How far back Today looks for meals nobody answered (proposed, for cabledrawer): a week. Older
# ones are left alone; they can still be seen on the Plan.
WAITING_DAYS = 7
# How many days from today the read's plan shows (Move it's 7-day strip, This week).
DAYS_SHOWN_AHEAD = 7
# Most tubs one answer makes (a batch holds at most MOST_TUBS_IN_BATCH).
MOST_LEFTOVER_TUBS = MOST_TUBS_IN_BATCH


@dataclass
class Leftovers:
    """ "Any left over?": this many tubs, in the fridge or the freezer."""

    count: int
    place_kind: str  # fridge or freezer
    use_by: date | None = None  # left out: the household's tub life
    item_id: int | None = None  # which recipe in the meal; left out: the first one


def answerable(kitchen: Kitchen, meal: Meal) -> None:
    """A planned meal whose day has come."""
    _planned(meal)  # already answered (or moved by hand): locked
    if meal.day > today(kitchen.household):
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "not_yet",
            "That meal hasn’t happened yet.",  # proposed, for cabledrawer
        )


def _set_status(meal: Meal, new: str, steps: list[dict[str, Any]], kitchen: Kitchen) -> None:
    # Recorded last, so Undo puts the status back first (the other steps only fit a planned meal).
    steps.append({"op": "status", "meal": meal.id, "from": meal.status, "to": new})
    meal.status = new
    kitchen.db.flush()


def _leftover_item(kitchen: Kitchen, meal: Meal, item_id: int | None) -> MealItem:
    items = items_of(kitchen, meal)
    if item_id is not None:
        item = next((i for i in items if i.id == item_id), None)
        if item is None:
            raise not_found("That item")
    else:
        item = next((i for i in items if i.kind == "recipe"), None)
        if item is None:
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "no_recipe",
                "Only a recipe can have leftovers.",  # proposed, for cabledrawer
            )
    if item.kind != "recipe":
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "no_recipe",
            "Only a recipe can have leftovers.",
        )
    return item


def _make_tubs(
    kitchen: Kitchen, meal: Meal, leftovers: Leftovers, steps: list[dict[str, Any]]
) -> int:
    """The tubs of "Any left over?". The recipe's batch cook for this meal if there is one,
    else a new batch cook. Returns how many were made."""
    db = kitchen.db
    item = _leftover_item(kitchen, meal, leftovers.item_id)
    place = places_of_kind(db, kitchen.household_id, leftovers.place_kind)
    if place is None:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "no_freezer" if leftovers.place_kind == "freezer" else "no_fridge",
            "There’s no freezer in your places yet."
            if leftovers.place_kind == "freezer"
            else "There’s no fridge in your places yet.",  # proposed, for cabledrawer
        )
    use_by = leftovers.use_by
    if use_by is not None:
        check_day(kitchen, use_by)
    else:
        use_by = tub_use_by(kitchen, leftovers.place_kind, meal.day)
    recipe = _own(kitchen, Recipe, item.recipe_id) if item.recipe_id else None
    batch = db.scalar(
        select(BatchCook).where(
            BatchCook.household_id == kitchen.household_id,
            BatchCook.cook_meal_id == meal.id,
            BatchCook.recipe_id == item.recipe_id
            if item.recipe_id is not None
            else BatchCook.recipe_name == item.name,
        )
    )
    have = 0
    if batch is not None:
        have = (
            db.scalar(
                select(func.count(Tub.id)).where(
                    Tub.household_id == kitchen.household_id, Tub.batch_id == batch.id
                )
            )
            or 0
        )
    if have + leftovers.count > MOST_LEFTOVER_TUBS:
        name = batch.recipe_name if batch else (recipe.name if recipe else item.name or "it")
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "batch_full",
            f"{name} already has {have} tubs, and a batch holds at most {MOST_TUBS_IN_BATCH}.",
        )  # proposed, for cabledrawer
    new_batch = batch is None
    if batch is None:
        _batches_that_day(kitchen, meal.day)
        batch = BatchCook(
            household_id=kitchen.household_id,
            recipe_id=recipe.id if recipe else None,
            recipe_name=recipe.name if recipe else (item.name or "a recipe"),
            cook_meal_id=meal.id,
            cooked_on=meal.day,
            tub_count=leftovers.count,
            pattern="pick",
            colour=next_colour(kitchen, meal.day),
        )
        db.add(batch)
        db.flush()
        steps.append({"op": "new_batch", "batch": batch.id})
    for _ in range(leftovers.count):
        tub = Tub(
            household_id=kitchen.household_id,
            batch_id=batch.id,
            place_id=place.id,
            use_by=use_by,
        )
        db.add(tub)
        db.flush()
        before = batch.tub_count
        steps.append({"op": "new_tub", "tub": tub.id, "count": None if new_batch else before})
        if not new_batch:
            batch.tub_count = before + 1
    db.flush()
    return leftovers.count


def cooked(kitchen: Kitchen, meal: Meal, leftovers: Leftovers | None) -> Change:
    """Cooked it. The pantry is not touched (0.7)."""
    answerable(kitchen, meal)
    steps: list[dict[str, Any]] = []
    name, where = _meal_name(kitchen, meal), _where(kitchen, meal.day, meal.slot_id)
    made = _make_tubs(kitchen, meal, leftovers, steps) if leftovers else 0
    _set_status(meal, "cooked", steps, kitchen)
    summary = f"Cooked {name} ({where})"
    if made:
        summary += f" and kept {made} {'tub' if made == 1 else 'tubs'} of leftovers"
    return _finish(kitchen, "plan_cooked", summary, steps, meal_id=meal.id)


def didnt(kitchen: Kitchen, meal: Meal) -> Change:
    """Didn't cook it. Nothing is taken from the pantry."""
    answerable(kitchen, meal)
    steps: list[dict[str, Any]] = []
    name, where = _meal_name(kitchen, meal), _where(kitchen, meal.day, meal.slot_id)
    _set_status(meal, "didnt", steps, kitchen)
    return _finish(kitchen, "plan_didnt", f"Didn’t cook {name} ({where})", steps, meal_id=meal.id)


def moved(kitchen: Kitchen, meal: Meal, day: date, slot_id: int) -> Change:
    """Move it: to a day and a meal. A meal that already has food gets it alongside."""
    answerable(kitchen, meal)
    check_day(kitchen, day)
    find_slot(kitchen, slot_id)
    if (meal.day, meal.slot_id) == (day, slot_id):
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "same_place", "That meal is already there."
        )
    if day < today(kitchen.household):
        # A move is to today or later: a past day would only make another meal to answer.
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "past_day",
            "Pick today or a later day.",  # cabledrawer 27 Oct
        )
    steps: list[dict[str, Any]] = []
    name, where_from = _meal_name(kitchen, meal), _where(kitchen, meal.day, meal.slot_id)
    items = items_of(kitchen, meal)
    target = meal_at(kitchen, day, slot_id)
    if target is not None:
        _planned(target)
        _room(kitchen, target, len(items))
    else:
        target = _make_meal(kitchen, day, slot_id, steps)
        _room(kitchen, target, len(items))
    for item in items:
        if item.tub_id is not None:
            _bring(kitchen, item, target, steps)  # a tub is in one meal at a time
        else:
            _copy_of(kitchen, item, target, steps)
    _set_status(meal, "moved", steps, kitchen)
    return _finish(
        kitchen,
        "plan_moveit",
        f"Moved {name} from {where_from} to {_where(kitchen, day, slot_id)}",
        steps,
        meal_id=target.id,
    )


def waiting_meals(kitchen: Kitchen) -> list[Meal]:
    """Planned meals on days before today (back WAITING_DAYS), in a slot that is on, newest
    first: later meals of a day before earlier ones."""
    first = today(kitchen.household)
    rows = list(
        kitchen.db.execute(
            select(Meal, MealSlot.position)
            .join(
                MealSlot,
                (MealSlot.household_id == Meal.household_id) & (MealSlot.id == Meal.slot_id),
            )
            .where(
                Meal.household_id == kitchen.household_id,
                Meal.status == "planned",
                Meal.day < first,
                Meal.day >= first - timedelta(days=WAITING_DAYS),
                MealSlot.enabled.is_(True),
            )
        )
    )
    rows.sort(key=lambda r: (r[0].day, r[1], r[0].id), reverse=True)
    return [meal for meal, _ in rows]
