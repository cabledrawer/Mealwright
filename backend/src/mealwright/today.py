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

- Didn't it and Move it can be answered on the meal's own day or after it, never before
  (`not_yet`). Cooked it can be answered before too: cooking ahead (cabledrawer 6 Nov, F159); the
  meal stays on its day.
- "Any left over?" is about one recipe: the one named by `item_id`, else the meal's first recipe.
  A meal with no recipe in it has no leftovers to keep (`no_recipe`).
- The tubs' use-by counts from the meal's day, as the mockup does ("Sat dinner … use by Tue
  27 Oct · 3 days"), not from the day it is answered, except that a meal cooked ahead counts
  from the day it was really cooked: `min(meal day, today)` (cabledrawer 6 Nov, F159).
"""

from dataclasses import dataclass
from datetime import date, time, timedelta
from typing import Any

from fastapi import status
from sqlalchemy import exists, func, select

from mealwright import batches, cooking, together
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
from mealwright.models import (
    BatchCook,
    Change,
    CookedRecord,
    Meal,
    MealItem,
    MealSlot,
    Place,
    Recipe,
    Tub,
)
from mealwright.plan import (
    _bring,
    _copy_of,
    _finish,
    _make_meal,
    _meal_name,
    _moved_starts,
    _own,
    _planned,
    _room,
    _where,
    check_day,
    cooked_record_of,
    find_slot,
    items_of,
    meal_at,
)
from mealwright.plan import (
    _item_name as plan_item_name,
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


def answerable(kitchen: Kitchen, meal: Meal, ahead: bool = False) -> None:
    """A planned meal whose day has come (Cooked it, `ahead`, may also be on an earlier day)."""
    _planned(meal)  # already answered (or moved by hand): locked
    if not ahead and meal.day > today(kitchen.household):
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "not_yet",
            "That meal hasn’t happened yet.",  # proposed, for cabledrawer
        )


def cooking_day(kitchen: Kitchen, meal: Meal) -> date:
    """The day a meal's tubs count from: its own day, or today when it is cooked ahead."""
    return min(meal.day, today(kitchen.household))


def _early_tubs(
    kitchen: Kitchen, meal: Meal, batch_ids: set[int], steps: list[dict[str, Any]]
) -> None:
    """A Cook once batch cooked before its day: its tubs, still on the household's tub life from
    the planned day, count from today instead (a tub the person gave another date is left)."""
    cooked_on = cooking_day(kitchen, meal)
    if cooked_on == meal.day or not batch_ids:
        return
    changed: list[list[Any]] = []
    for tub in kitchen.db.scalars(
        select(Tub).where(Tub.household_id == kitchen.household_id, Tub.batch_id.in_(batch_ids))
    ):
        place = kitchen.db.get(Place, tub.place_id) if tub.place_id else None
        if place is not None and place.household_id != kitchen.household_id:
            place = None
        kind = place.kind if place is not None and place.kind == "freezer" else "fridge"
        if tub.use_by == tub_use_by(kitchen, kind, meal.day):
            new_use_by = tub_use_by(kitchen, kind, cooked_on)
            changed.append([tub.id, tub.use_by.isoformat(), new_use_by.isoformat()])
            tub.use_by = new_use_by
    if changed:
        kitchen.db.flush()
        steps.append({"op": "tub_early", "tubs": changed})


def _set_status(meal: Meal, new: str, steps: list[dict[str, Any]], kitchen: Kitchen) -> None:
    # Recorded last, so Undo puts the status back first (the other steps only fit a planned meal).
    steps.append({"op": "status", "meal": meal.id, "from": meal.status, "to": new})
    meal.status = new
    kitchen.db.flush()


def _leftover_item(
    kitchen: Kitchen, meal: Meal, item_id: int | None, press_items: list[int] | None = None
) -> MealItem:
    items = items_of(kitchen, meal)
    if item_id is not None:
        item = next((i for i in items if i.id == item_id), None)
        if item is None:
            raise not_found("That item")
    else:
        recipes = [i for i in items if i.kind == "recipe"]
        # The recipe this press cooked (its records, in order), else the first not cooked yet,
        # never another press's (F157 review); nothing to tell them apart: the first.
        by_id = {i.id: i for i in recipes}
        pressed = [by_id[i] for i in (press_items or []) if i in by_id]
        uncooked = [i for i in recipes if cooked_record_of(kitchen, i, meal) is None]
        item = next(iter(pressed or uncooked or recipes), None)
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
    kitchen: Kitchen,
    meal: Meal,
    leftovers: Leftovers,
    steps: list[dict[str, Any]],
    press_items: list[int] | None = None,
) -> int:
    """The tubs of "Any left over?". The recipe's batch cook for this meal if there is one,
    else a new batch cook. Returns how many were made."""
    db = kitchen.db
    item = _leftover_item(kitchen, meal, leftovers.item_id, press_items)
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
        use_by = tub_use_by(kitchen, leftovers.place_kind, cooking_day(kitchen, meal))
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
        step: dict[str, Any] = {
            "op": "new_tub",
            "tub": tub.id,
            "count": None if new_batch else before,
        }
        steps.append(step)
        if not new_batch:
            batch.tub_count = before + 1
            step["to"] = batch.tub_count  # F165
    db.flush()
    return leftovers.count


def _joined(names: list[str]) -> str:
    """ "A", "A and B", "A, B and C" (as the screens' `cookedTitle`)."""
    return names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"


def _refuse_nothing_reviewed(kitchen: Kitchen, meal: Meal) -> None:
    """A "Cooked it" that reviews no recipe, on a meal where one is cooked and others can still
    be: it would cook them all unseen. Refused, naming them (cabledrawer 7 Nov)."""
    left = cooking.recipes_left(kitchen, meal)
    if not left:
        return
    items = items_of(kitchen, meal)
    if not any(i.kind == "recipe" and cooked_record_of(kitchen, i, meal) for i in items):
        return
    names = [plan_item_name(kitchen, i) for i in left]
    verb = "needs" if len(names) == 1 else "need"
    raise Problem(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "recipes_still_to_cook",  # proposed, for cabledrawer
        f"{_joined(names)} still {verb} Cooked it.",
    )


def cooked(
    kitchen: Kitchen,
    meal: Meal,
    leftovers: Leftovers | None,
    press_given: list[Change] | None = None,
) -> Change:
    """Cooked it. The meal becomes cooked when every recipe in it has been (F157): one press
    of a meal with several recipes cooks only the ones it reviewed. An answer with no pantry
    change of its own (nothing was reviewed) cooks the whole meal, unless a recipe of it is
    cooked already and others are left: then it is refused (cabledrawer 7 Nov). `press_given`: the
    pantry changes of this press when the caller made them itself (a session's Cooked it), so an
    earlier separate "Cooked it" is not joined to it."""
    answerable(kitchen, meal, ahead=True)
    steps: list[dict[str, Any]] = []
    where = _where(kitchen, meal.day, meal.slot_id)
    press = press_given if press_given is not None else together.press_changes(kitchen, meal)
    if not press:
        _refuse_nothing_reviewed(kitchen, meal)
    names = together.cooked_names(kitchen, press, meal) if press else []
    name = _joined(names) if names else _meal_name(kitchen, meal)
    whole = not press or cooking.meal_all_cooked(kitchen, meal)  # before any new batch of leftovers
    records = [
        r
        for change in press
        for r in kitchen.db.scalars(
            select(CookedRecord)
            .where(
                CookedRecord.household_id == kitchen.household_id,
                CookedRecord.change_id == change.id,
            )
            .order_by(CookedRecord.id)
        )
    ]
    # The recipes this press cooked: by their own record, or as the cook item of a batch it cooked.
    batch_ids = {r.batch_id for r in records if r.batch_id is not None}
    pressed = [r.meal_item_id for r in records if r.meal_item_id is not None]
    if batch_ids:
        for item in items_of(kitchen, meal):
            if any(b.id in batch_ids for b in batches.cook_batches_of(kitchen, item, meal)):
                pressed.append(item.id)
    _early_tubs(kitchen, meal, batch_ids, steps)
    made = _make_tubs(kitchen, meal, leftovers, steps, pressed) if leftovers else 0
    if whole:
        _set_status(meal, "cooked", steps, kitchen)
    summary = f"Cooked {name} ({where})"
    if made:
        summary += f" and kept {made} {'tub' if made == 1 else 'tubs'} of leftovers"
    change = _finish(kitchen, "plan_cooked", summary, steps, meal_id=meal.id)
    together.join_answer(kitchen, meal, change, press_given)  # one "Cooked it", one Undo (F125)
    return change


def didnt(kitchen: Kitchen, meal: Meal) -> Change:
    """Didn't cook it. Nothing is taken from the pantry."""
    answerable(kitchen, meal)
    steps: list[dict[str, Any]] = []
    name, where = _meal_name(kitchen, meal), _where(kitchen, meal.day, meal.slot_id)
    _set_status(meal, "didnt", steps, kitchen)
    return _finish(kitchen, "plan_didnt", f"Didn’t cook {name} ({where})", steps, meal_id=meal.id)


def moved(
    kitchen: Kitchen,
    meal: Meal,
    day: date,
    slot_id: int,
    starts: dict[int, tuple[date, time]] | None = None,
) -> Change:
    """Move it: to a day and a meal. A meal that already has food gets it alongside. `starts`: the
    new start time of each recipe with a long wait, by item id, asked again for the new day; a
    recipe left out has no time yet. Undo takes the copies away, so no time is left behind."""
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
    where_from = _where(kitchen, meal.day, meal.slot_id)
    items = items_of(kitchen, meal)
    new_starts = _moved_starts(kitchen, items, day, slot_id, starts or {})  # before any change
    # Only what moves is named: a recipe cooked already stays (F162, cabledrawer 6 Nov).
    left = [i for i in items if i.tub_id is not None or cooked_record_of(kitchen, i, meal) is None]
    names = [plan_item_name(kitchen, i) for i in left or items]
    name = names[0] if len(names) == 1 else f"{names[0]} and {len(names) - 1} more"
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
        elif cooked_record_of(kitchen, item, meal) is None:
            # An already-cooked recipe is not copied: it was eaten (proposed, for cabledrawer).
            _copy_of(kitchen, item, target, steps, new_starts.get(item.id), keep_started=True)
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
                # A meal of only notes ("Eating out") is never asked about (0.7 P1).
                exists().where(
                    MealItem.household_id == Meal.household_id,
                    MealItem.meal_id == Meal.id,
                    MealItem.kind != "note",
                ),
            )
        )
    )
    rows.sort(key=lambda r: (r[0].day, r[1], r[0].id), reverse=True)
    return [meal for meal, _ in rows]
