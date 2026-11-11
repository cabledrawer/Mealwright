"""Batch cook (Experimental) sessions (0.8 wave 6, B2; cabledrawer 28 Oct and 11 Nov): "Plan this
batch" sends each recipe through Cook once on the cook day, marked as one session.

A session is its recipes planned in one meal of the cook day (a plan item each) and one Cook once
batch each (`batch_cook.session_id`). Making, changing and removing one is **one change with one
Undo** (`undo_data["plan"]`, as the rest of the plan): the kinds are `plan_batch_session`,
`plan_batch_session_changed` and `plan_batch_session_removed`. The session's recipes are its batch
cooks, in the order they were made.

Changing a session takes the old one off and makes the new one in the same change (so Undo puts
the old one back). A session whose recipes were cooked can't be changed or removed: the cooked
record is never lost (`already_cooked`, as for a batch).
"""

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import date, time
from typing import Any

from fastapi import status
from sqlalchemy import select

from mealwright import batch_suggest, batches, cooked, cooking, plan, start_ahead
from mealwright.api.v1.context import Kitchen
from mealwright.deduction import Choice
from mealwright.errors import Problem, not_found
from mealwright.household import meal_slots
from mealwright.models import (
    BatchCook,
    BatchSession,
    Change,
    Meal,
    MealItem,
    Place,
    Recipe,
    Tub,
    utcnow,
)

FEWEST = batch_suggest.FEWEST_PICKS
MOST = batch_suggest.MOST_PICKS


@dataclass
class RecipeChoice:
    """One recipe's Cook once choices (the same fields as one Cook once sheet sends)."""

    recipe_id: int
    tub_count: int
    pattern: str = "pick"
    member_login_ids: list[int] = field(default_factory=list)
    extras_to_freezer: bool = False
    prep_note: str | None = None
    placements: list[batches.Spot | None] | None = None
    # As adding the recipe to the plan asks (RF3, C6; cabledrawer 11 Nov): the optional lines to use
    # (None: every one counts) and the way of cooking it, for a recipe with two (None: the one
    # used last).
    optional_use: list[int] | None = None
    method_id: int | None = None


def hidden_check(kitchen: Kitchen) -> None:
    """Batch cook is hidden by an admin: nothing of it works (the screens are gone too)."""
    if kitchen.household.batch_cook_hidden:
        raise Problem(
            status.HTTP_409_CONFLICT,
            "batch_cook_hidden",
            "Batch cook is switched off. An admin can switch it on in Settings.",  # proposed
        )


def find_session(kitchen: Kitchen, session_id: int) -> BatchSession:
    session = kitchen.db.get(BatchSession, session_id)
    if session is None or session.household_id != kitchen.household_id:
        raise not_found("That batch cook")
    return session


def batches_of(kitchen: Kitchen, session: BatchSession) -> list[BatchCook]:
    """The session's batch cooks, in the order they were made."""
    return list(
        kitchen.db.scalars(
            select(BatchCook)
            .where(
                BatchCook.household_id == kitchen.household_id, BatchCook.session_id == session.id
            )
            .order_by(BatchCook.id)
        )
    )


def _check(
    kitchen: Kitchen, day: date, slot_id: int, choices: list[RecipeChoice], fewest: int = FEWEST
) -> list[Recipe]:
    if not fewest <= len(choices) <= MOST:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "bad_session_size",
            f"A batch cook has {FEWEST} to {MOST} recipes.",  # proposed, for cabledrawer
        )
    ids = [c.recipe_id for c in choices]
    if len(set(ids)) != len(ids):
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "same_recipe_twice",
            "Each recipe can be in a batch cook once.",  # proposed, for cabledrawer
        )
    plan.check_day(kitchen, day)
    plan.find_slot(kitchen, slot_id)
    recipes: list[Recipe] = []
    for choice in choices:
        recipe = plan._own(kitchen, Recipe, choice.recipe_id)
        if recipe is None or recipe.removed_at is not None:
            raise not_found("That recipe")
        recipes.append(recipe)
    return recipes


def _start_tonight(
    kitchen: Kitchen, day: date, slot_id: int, recipe: Recipe, method_id: int | None = None
) -> tuple[date, time] | None:
    """A recipe with a long wait (soak, marinate overnight) is planned with wave 5's first "Start
    tonight" time, so Today shows it the day before (B3, cabledrawer 11 Nov; proposed, for cabledrawer:
    the session picks the time itself, and it can be changed on the Plan like any other). None
    when the recipe has no such wait or every time has gone by."""
    method = plan._method_for(kitchen, recipe, method_id)
    found = start_ahead.ahead_of(kitchen.db, recipe, method.id if method else None)
    if found is None:
        return None
    options = start_ahead.options(
        kitchen.household, found, day, plan.find_slot(kitchen, slot_id), utcnow()
    )
    if not options:
        return None
    local = start_ahead.local_of(kitchen.household, options[0].start)
    return local.date(), local.time().replace(second=0, microsecond=0)


def _plan_each(
    kitchen: Kitchen,
    day: date,
    slot_id: int,
    choices: list[RecipeChoice],
    recipes: list[Recipe],
    steps: list[dict[str, Any]],
    session_id: int | None,
) -> Meal | None:
    """Each recipe is planned in the cook day's meal, then cooked once. Returns that meal."""
    meal: Meal | None = None
    for choice, recipe in zip(choices, recipes, strict=True):
        start = _start_tonight(kitchen, day, slot_id, recipe, choice.method_id)
        added, meal, item, _name = plan.add_item_steps(
            kitchen,
            day,
            slot_id,
            recipe,
            None,
            None,
            optional_use=choice.optional_use,
            method_id=choice.method_id,
            start=start,
        )
        steps.extend(added)
        made, _batch, _worked = batches.make_batch_steps(
            kitchen,
            item,
            choice.tub_count,
            choice.pattern,
            choice.member_login_ids,
            choice.extras_to_freezer,
            choice.prep_note,
            choice.placements,
            session_id=session_id,
        )
        steps.extend(made)
    return meal


def _apply(
    kitchen: Kitchen,
    day: date,
    slot_id: int,
    choices: list[RecipeChoice],
    recipes: list[Recipe],
    steps: list[dict[str, Any]],
) -> tuple[BatchSession, Meal]:
    """Make the session and its recipes. The undo steps go on `steps` (the new session first, so
    Undo takes it away last)."""
    together, one_by_one = batch_suggest.times_for(kitchen, [c.recipe_id for c in choices])
    session = BatchSession(
        household_id=kitchen.household_id,
        cook_day=day,
        together_minutes=together or None,
        one_by_one_minutes=one_by_one or None,
    )
    kitchen.db.add(session)
    kitchen.db.flush()
    steps.append({"op": "new_session", "session": session.id})
    meal = _plan_each(kitchen, day, slot_id, choices, recipes, steps, session.id)
    if meal is None:  # pragma: no cover (a session has at least two recipes)
        raise not_found("That meal")
    return session, meal


def session_slot(kitchen: Kitchen, session: BatchSession) -> int | None:
    """The meal a session's recipes are planned in (its first batch's cook meal), or None."""
    for batch in batches_of(kitchen, session):
        meal = kitchen.db.get(Meal, batch.cook_meal_id) if batch.cook_meal_id else None
        if meal is not None and meal.household_id == kitchen.household_id:
            return meal.slot_id
    return None


def pick_slot(kitchen: Kitchen, day: date) -> int:
    """The meal a new session goes in when none is named: the last meal that is on and has no
    recipe planned on the cook day itself (tubs and plain ingredients don't count), else the last
    meal that is on. Read for the cook day, whatever week the screen has loaded."""
    on = [s for s in meal_slots(kitchen.db, kitchen.household_id) if s.enabled]
    if not on:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "no_meals_on",
            "Switch a meal on first.",  # proposed, for cabledrawer
        )
    busy = set(
        kitchen.db.scalars(
            select(Meal.slot_id)
            .join(MealItem, MealItem.meal_id == Meal.id)
            .where(
                Meal.household_id == kitchen.household_id,
                Meal.day == day,
                MealItem.recipe_id.is_not(None),
            )
        )
    )
    free = [s for s in on if s.id not in busy]
    return (free or on)[-1].id


def _words(kitchen: Kitchen, day: date, count: int) -> str:
    return f"{count} recipes for {day:%a} {day.day} {day:%b}"


def create(kitchen: Kitchen, day: date, slot_id: int | None, choices: list[RecipeChoice]) -> Change:
    """Plan this batch: one change, one Undo, for the whole session."""
    hidden_check(kitchen)
    if slot_id is None:
        slot_id = pick_slot(kitchen, day)
    recipes = _check(kitchen, day, slot_id, choices)
    steps: list[dict[str, Any]] = []
    session, meal = _apply(kitchen, day, slot_id, choices, recipes, steps)
    return plan._finish(
        kitchen,
        "plan_batch_session",
        f"Planned a batch cook of {_words(kitchen, day, len(choices))}",
        steps,
        meal_id=meal.id,
        session_id=session.id,
    )


def _take_off(kitchen: Kitchen, session: BatchSession, steps: list[dict[str, Any]]) -> None:
    """Take the session's recipes off the plan: their tubs, batches and the cook-day items go.
    The session goes with its last batch (`drop_empty_session`)."""
    found = batches_of(kitchen, session)
    batches.refuse_cooked(kitchen, found)
    cook_items: list[tuple[MealItem, Meal]] = []
    for batch in found:
        item = batches.cook_item_of(kitchen, batch)
        meal = kitchen.db.get(Meal, item.meal_id) if item is not None else None
        if item is not None and meal is not None:
            plan._planned(meal)
            plan.refuse_cooked_items(kitchen, [item], meal)
            cook_items.append((item, meal))
    for batch in found:
        made, _name = batches.delete_batch_steps(kitchen, batch)
        steps.extend(made)
    if not found:  # an empty session left behind: just the session
        batches.drop_empty_session(kitchen, session.id, steps)
    for item, meal in cook_items:
        steps.append({"op": "del_item", "item": plan._snapshot_item(item)})
        kitchen.db.delete(item)
        kitchen.db.flush()
        if not plan.items_of(kitchen, meal) and kitchen.db.get(Meal, meal.id) is not None:
            plan._drop_meal(kitchen, meal, steps)


def remove(kitchen: Kitchen, session: BatchSession) -> Change:
    """Take the whole session off the plan: one change, one Undo that puts all of it back. Like
    every Batch cook route it answers 409 while an admin has Batch cook hidden (cabledrawer 11 Nov)."""
    hidden_check(kitchen)
    day, count = session.cook_day, len(batches_of(kitchen, session))
    steps: list[dict[str, Any]] = []
    _take_off(kitchen, session, steps)
    return plan._finish(
        kitchen,
        "plan_batch_session_removed",
        f"Took the batch cook of {_words(kitchen, day, count)} off the plan",
        steps,
    )


def change(
    kitchen: Kitchen,
    session: BatchSession,
    day: date,
    slot_id: int | None,
    choices: list[RecipeChoice],
) -> Change:
    """Change: the session's recipes are taken off and the new ones planned, in one change. With
    no meal named the session stays in the meal it was in."""
    hidden_check(kitchen)
    if slot_id is None:
        slot_id = session_slot(kitchen, session)
    if slot_id is None:
        slot_id = pick_slot(kitchen, day)
    recipes = _check(kitchen, day, slot_id, choices)
    steps: list[dict[str, Any]] = []
    _take_off(kitchen, session, steps)
    made, meal = _apply(kitchen, day, slot_id, choices, recipes, steps)
    return plan._finish(
        kitchen,
        "plan_batch_session_changed",
        f"Changed the batch cook to {_words(kitchen, day, len(choices))}",
        steps,
        meal_id=meal.id,
        session_id=made.id,
    )


def preview[T](
    kitchen: Kitchen,
    day: date,
    slot_id: int | None,
    choices: list[RecipeChoice],
    render: Callable[[batches.Worked], T],
    session: BatchSession | None = None,
) -> T:
    """Where the last recipe's tubs would land, after the ones before it (the Cook once sheets of
    a session follow each other, so each one sees the meals the earlier ones filled). Makes
    everything in a savepoint and takes it back: nothing is saved. `render` turns the result into
    plain data while the savepoint is still open. `session` is the session being changed: it is
    taken off first inside the savepoint, as the change itself does, so the preview is what will
    be saved."""
    hidden_check(kitchen)
    if slot_id is None:
        slot_id = session_slot(kitchen, session) if session else None
    if slot_id is None:
        slot_id = pick_slot(kitchen, day)
    recipes = _check(kitchen, day, slot_id, choices, fewest=1)
    last = choices[-1]
    sub = kitchen.db.begin_nested()
    try:
        if session is not None:
            _take_off(kitchen, session, [])
        _plan_each(kitchen, day, slot_id, choices[:-1], recipes[:-1], [], None)
        _added, _meal, item, _name = plan.add_item_steps(
            kitchen, day, slot_id, recipes[-1], None, None
        )
        return render(
            batches.work_out(
                kitchen,
                item,
                last.tub_count,
                last.pattern,
                last.member_login_ids,
                last.extras_to_freezer,
                last.placements,
            )
        )
    finally:
        sub.rollback()


# --- One Cooked it for the whole session ----------------------------------------------------


def left_out(kitchen: Kitchen, batch: BatchCook) -> str | None:
    """Why a recipe of the session isn't part of its Cooked it: `cooked` (it was cooked already,
    on its own) or `removed` (its recipe is deleted). None: it is still to cook (review B3 r1,
    fix 2)."""
    if cooked.for_batch(kitchen.db, kitchen.household_id, batch.id) is not None:
        return "cooked"
    if not cooking._usable(kitchen, batch.recipe_id):
        return "removed"
    return None


def cook_entries(
    kitchen: Kitchen,
    session: BatchSession,
    wanted: dict[int, tuple[int | None, dict[str, Choice]]] | None,
) -> list[cooking.Entry]:
    """The session's recipes to take from the pantry together, as Cooked it does a meal's: one
    entry for each batch cook of the session (the batch ids in `wanted`, with their portions and
    choices, or all of them), worked out from one pool of packets so two recipes never take the
    same grams. Reuses Cooked it's own entries: nothing about the stock is done here."""
    found = batches_of(kitchen, session)
    if wanted is not None:
        by_id = {b.id for b in found}
        for batch_id in wanted:
            if batch_id not in by_id:
                raise not_found("That recipe")
        found = [b for b in found if b.id in wanted]
    else:
        # As Cooked it does for a meal (F158): what was cooked already or removed is left out,
        # not a reason to refuse the others.
        left = [b for b in found if left_out(kitchen, b) is not None]
        found = [b for b in found if b not in left]
        if not found and left:
            raise Problem(
                status.HTTP_409_CONFLICT,
                "already_cooked",
                "Everything in this batch cook was already cooked or removed.",
            )  # proposed, for cabledrawer
    if not found:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "nothing_to_cook",
            "There’s no recipe in this batch cook to cook.",  # proposed, for cabledrawer
        )
    return [
        cooking.batch_entry(kitchen, b, *(wanted[b.id] if wanted is not None else (None, {})))
        for b in found
    ]


def tubs_by_place(kitchen: Kitchen, batch: BatchCook) -> list[tuple[str | None, int]]:
    """A batch's tubs counted by where they are (Fridge, Freezer...); a tub in no place (it is in
    a meal, or left over) is counted under None. Places first in the order of their names."""
    counts: dict[str | None, int] = {}
    for tub in kitchen.db.scalars(
        select(Tub)
        .where(Tub.household_id == kitchen.household_id, Tub.batch_id == batch.id)
        .order_by(Tub.id)
    ):
        place = kitchen.db.get(Place, tub.place_id) if tub.place_id is not None else None
        name = (
            place.name if place is not None and place.household_id == kitchen.household_id else None
        )
        counts[name] = counts.get(name, 0) + 1
    return sorted(counts.items(), key=lambda c: (c[0] is None, c[0] or ""))
