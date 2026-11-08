"""Cook once, eat for… (0.6 PR 4): batch cooks and their tubs, written to the plan.

A batch cook is one recipe cooked on one day into several tubs. A tub is in a place (fridge or
freezer) and, if it is going to be eaten at a planned meal, in that meal too (a meal item points
at it). A tub in no meal is a "tub left". Every write is one Change with its Undo, kept in
`undo_data["plan"]` like the rest of the plan (see `mealwright/plan.py`).
"""

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from fastapi import status
from sqlalchemy import and_, exists, func, select
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import aliased

from mealwright import cooked, together
from mealwright.amounts import quarters_text
from mealwright.api.v1.context import Kitchen
from mealwright.errors import Problem, not_found
from mealwright.history import as_utc
from mealwright.household import meal_slots, today
from mealwright.models import (
    SPREAD_PATTERNS,
    BatchCook,
    Change,
    Login,
    Meal,
    MealItem,
    MealSlot,
    Place,
    Recipe,
    Tub,
)
from mealwright.plan import (
    _KINDS,
    DAYS_AHEAD,
    DAYS_BACK,
    MOST_ITEMS_IN_MEAL,
    _drop_meal,
    _end,
    _finish,
    _item_name,
    _make_meal,
    _own,
    _planned,
    _room,
    _snapshot_item,
    _where,
    check_after_cook,
    check_day,
    find_slot,
    items_of,
    meal_at,
    shifted,
)
from mealwright.stock import add_months

# --- Caps (proposed, for cabledrawer) ---------------------------------------------------------------
#
# A batch holds at most 12 tubs and a day at most 10 batches. With the rest of the plan's caps
# (20 things in a meal, 12 slots) these keep GET /plan, which asks the database about the batches
# and tubs of a range, well under SQLite's 32,766 values in a query: tubs in meals are at most
# 62 x 12 x 20 = 14,880 (and so are the batches they come from), batches cooked for those meals
# at most that again, and batches cooked on a day in the range at most 62 x 10 = 620. The
# queries use subqueries, not lists of ids, for the batches and their tubs; a test keeps the sum
# honest.
MOST_TUBS_IN_BATCH = 12
MOST_BATCHES_A_DAY = 10
# How far ahead the automatic patterns look for a free meal.
SEARCH_DAYS = 28

# One colour per batch. The names go with the design's tokens --batch-1 … --batch-6, in order.
PALETTE = ("purple", "amber", "green", "blue", "rose", "teal")

Spot = tuple[date, int]  # a day and a meal slot


def places_of_kind(db: DbSession, household_id: int, kind: str) -> Place | None:
    return db.scalar(
        select(Place)
        .where(Place.household_id == household_id, Place.kind == kind)
        .order_by(Place.position, Place.id)
        .limit(1)
    )


def tub_use_by(kitchen: Kitchen, kind: str, from_day: date) -> date:
    """The household's tub life: days in the fridge, months in the freezer (cabledrawer 17 Oct)."""
    household = kitchen.household
    if kind == "freezer":
        return add_months(from_day, household.tub_freezer_months)
    return from_day + timedelta(days=household.tub_fridge_days)


def really_cooked_on(kitchen: Kitchen, batch: BatchCook) -> date:
    """The day a batch's tubs count from: its cook day, or the earlier day it was really cooked
    on (cooked ahead, F159)."""
    record = cooked.for_batch(kitchen.db, kitchen.household_id, batch.id)
    if record is None:
        return batch.cooked_on
    return min(batch.cooked_on, today(kitchen.household, as_utc(record.cooked_at)))


def next_colour(kitchen: Kitchen, day: date) -> str:
    """The first palette name no batch cooked within two weeks of this day is using."""
    used = set(
        kitchen.db.scalars(
            select(BatchCook.colour).where(
                BatchCook.household_id == kitchen.household_id,
                BatchCook.cooked_on >= day - timedelta(days=14),
                BatchCook.cooked_on <= day + timedelta(days=14),
            )
        )
    )
    for name in PALETTE:
        if name not in used:
            return name
    return PALETTE[len(used) % len(PALETTE)]


def tub_name(kitchen: Kitchen, tub: Tub) -> str:
    batch = kitchen.db.get(BatchCook, tub.batch_id)
    return f"{batch.recipe_name} tub" if batch else "a tub"


# --- Working out where the tubs go -------------------------------------------------------------


@dataclass
class TubPlan:
    number: int
    spot: Spot | None
    place_kind: str  # fridge or freezer
    place_id: int | None
    member_login_id: int | None
    use_by: date
    meal_has_food: (
        bool  # the meal it lands in already had something planned (the patterns skip those)
    )


@dataclass
class Worked:
    recipe: Recipe
    meal: Meal
    tubs: list[TubPlan]
    colour: str


def _word_slots(kitchen: Kitchen, pattern: str) -> list[MealSlot]:
    """The meals a pattern spreads over, found by name: a slot whose name has "lunch" in it, or
    "dinner" (proposed, for cabledrawer: slots are the household's own words, so the pattern goes by
    the word)."""
    words = {"lunches": ("lunch",), "dinners": ("dinner",), "lunch_dinner": ("lunch", "dinner")}[
        pattern
    ]
    return [
        s
        for s in meal_slots(kitchen.db, kitchen.household_id)
        if s.enabled and any(w in s.name.lower() for w in words)
    ]


def _taken(kitchen: Kitchen, first: date, last: date) -> set[Spot]:
    """Meals in a range that already have something planned, or that were dealt with."""
    rows = kitchen.db.execute(
        select(Meal.day, Meal.slot_id, Meal.status, func.count(MealItem.id))
        .outerjoin(MealItem, MealItem.meal_id == Meal.id)
        .where(Meal.household_id == kitchen.household_id, Meal.day >= first, Meal.day <= last)
        .group_by(Meal.id)
    )
    return {(day, slot_id) for day, slot_id, state, count in rows if count or state != "planned"}


def auto_spots(kitchen: Kitchen, meal: Meal, count: int, pattern: str) -> list[Spot | None]:
    """The next matching meals that are on, after the cook meal, skipping the ones that
    already have something planned. Tubs with no meal left to go to are None ("tubs left"). The
    cook meal itself is never filled (proposed, for cabledrawer: the spec says "following slots";
    add a tub there by hand if you want one)."""
    if pattern == "pick":
        return [None] * count
    wanted = _word_slots(kitchen, pattern)
    cook_slot = kitchen.db.get(MealSlot, meal.slot_id)
    cook_key = (cook_slot.position, cook_slot.id) if cook_slot else (0, 0)
    last = min(
        meal.day + timedelta(days=SEARCH_DAYS),
        today(kitchen.household) + timedelta(DAYS_AHEAD),
        # A tub is no good past its own use-by: the tubs that don't fit wait in Tubs left.
        tub_use_by(kitchen, "fridge", meal.day),
    )
    busy = _taken(kitchen, meal.day, last)
    out: list[Spot | None] = []
    day = meal.day
    while day <= last and len(out) < count:
        for slot in wanted:
            if day == meal.day and (slot.position, slot.id) <= cook_key:
                continue
            if (day, slot.id) in busy:
                continue
            out.append((day, slot.id))
            if len(out) == count:
                break
        day += timedelta(days=1)
    return out + [None] * (count - len(out))


def _own_logins(kitchen: Kitchen, ids: list[int]) -> list[int]:
    for login_id in ids:
        login = kitchen.db.get(Login, login_id)
        if login is None or login.household_id != kitchen.household_id:
            raise not_found("That person")
    return ids


def recipe_item(kitchen: Kitchen, item: MealItem) -> tuple[Recipe, Meal]:
    """The recipe and the planned meal a batch cook can be made from."""
    meal = kitchen.db.get(Meal, item.meal_id)
    if meal is None:  # pragma: no cover (the database keeps every item in a meal)
        raise not_found("That meal")
    _planned(meal)
    recipe = _own(kitchen, Recipe, item.recipe_id) if item.recipe_id else None
    if recipe is None or recipe.removed_at is not None:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "not_a_recipe",
            "Only a recipe that is still there can be cooked once for several meals.",  # proposed
        )
    return recipe, meal


def _no_batch_yet(kitchen: Kitchen, meal: Meal, recipe: Recipe) -> None:
    found = kitchen.db.scalar(
        select(BatchCook.id).where(
            BatchCook.household_id == kitchen.household_id,
            BatchCook.cook_meal_id == meal.id,
            BatchCook.recipe_id == recipe.id,
        )
    )
    if found is not None:
        raise Problem(
            status.HTTP_409_CONFLICT,
            "batch_exists",
            f"{recipe.name} already has tubs from this meal. Add or move them from the plan.",
        )  # proposed, for cabledrawer


def _batches_that_day(kitchen: Kitchen, day: date) -> None:
    count = kitchen.db.scalar(
        select(func.count(BatchCook.id)).where(
            BatchCook.household_id == kitchen.household_id, BatchCook.cooked_on == day
        )
    )
    if (count or 0) >= MOST_BATCHES_A_DAY:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "too_many_batches",
            f"At most {MOST_BATCHES_A_DAY} batches can be cooked on one day.",  # proposed
        )


def work_out(
    kitchen: Kitchen,
    item: MealItem,
    tub_count: int,
    pattern: str,
    member_login_ids: list[int],
    extras_to_freezer: bool,
    placements: list[Spot | None] | None,
) -> Worked:
    """Where each tub goes, for the preview and for saving: both call this, so the screen and
    the server agree. `placements` is the person's own choice, one entry per tub (None: not in
    a meal); left out, the pattern picks."""
    if pattern not in SPREAD_PATTERNS:  # pragma: no cover (the request model checks it)
        raise Problem(status.HTTP_422_UNPROCESSABLE_CONTENT, "bad_pattern", "Unknown pattern.")
    if not 1 <= tub_count <= MOST_TUBS_IN_BATCH:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "too_many_tubs",
            f"A batch can have 1 to {MOST_TUBS_IN_BATCH} tubs.",  # proposed, for cabledrawer
        )
    recipe, meal = recipe_item(kitchen, item)
    _no_batch_yet(kitchen, meal, recipe)
    _batches_that_day(kitchen, meal.day)
    eaters = _own_logins(kitchen, member_login_ids)
    if placements is not None and len(placements) != tub_count:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "bad_placements",
            "Say where each tub goes, or leave it to the pattern.",  # proposed, for cabledrawer
        )
    spots = placements if placements is not None else auto_spots(kitchen, meal, tub_count, pattern)
    fridge = places_of_kind(kitchen.db, kitchen.household_id, "fridge")
    freezer = places_of_kind(kitchen.db, kitchen.household_id, "freezer")
    # Tubs that were given a meal check their meals as they go, counting what this batch adds.
    adding: dict[Spot, int] = {}
    taken_cache: dict[Spot, bool] = {}
    out: list[TubPlan] = []
    for index, spot in enumerate(spots):
        has_food = False
        if spot is not None:
            check_day(kitchen, spot[0])
            find_slot(kitchen, spot[1])
            check_after_cook(kitchen, meal, spot[0], spot[1])
            if spot[0] > tub_use_by(kitchen, "fridge", meal.day):
                raise Problem(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "after_use_by",
                    "That’s after this batch’s use-by date.",  # cabledrawer 2 Nov
                )
            target = meal_at(kitchen, spot[0], spot[1])
            if target is not None:
                _planned(target)
                if spot not in taken_cache:
                    taken_cache[spot] = bool(items_of(kitchen, target))
                has_food = taken_cache[spot]
                _room(kitchen, target, adding.get(spot, 0) + 1)
            elif adding.get(spot, 0) + 1 > MOST_ITEMS_IN_MEAL:
                raise Problem(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "meal_full",
                    f"A meal holds at most {MOST_ITEMS_IN_MEAL} things.",
                )
            adding[spot] = adding.get(spot, 0) + 1
        frozen = spot is None and extras_to_freezer
        if frozen and freezer is None:
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "no_freezer",
                "There’s no freezer in your places yet.",  # proposed, for cabledrawer
            )
        place = freezer if frozen else fridge
        kind = "freezer" if frozen else "fridge"
        out.append(
            TubPlan(
                number=index + 1,
                spot=spot,
                place_kind=kind,
                place_id=place.id if place else None,
                member_login_id=eaters[index % len(eaters)] if eaters else None,
                use_by=tub_use_by(kitchen, kind, meal.day),
                meal_has_food=has_food,
            )
        )
    return Worked(recipe=recipe, meal=meal, tubs=out, colour=next_colour(kitchen, meal.day))


def make_batch(
    kitchen: Kitchen,
    item: MealItem,
    tub_count: int,
    pattern: str,
    member_login_ids: list[int],
    extras_to_freezer: bool,
    prep_note: str | None,
    placements: list[Spot | None] | None,
) -> Change:
    worked = work_out(
        kitchen, item, tub_count, pattern, member_login_ids, extras_to_freezer, placements
    )
    db = kitchen.db
    steps: list[dict[str, Any]] = []
    batch = BatchCook(
        household_id=kitchen.household_id,
        recipe_id=worked.recipe.id,
        recipe_name=worked.recipe.name,
        cook_meal_id=worked.meal.id,
        cooked_on=worked.meal.day,
        tub_count=tub_count,
        pattern=pattern,
        prep_note=prep_note or None,
        colour=worked.colour,
    )
    db.add(batch)
    db.flush()
    steps.append({"op": "new_batch", "batch": batch.id})
    for plan_tub in worked.tubs:
        tub = Tub(
            household_id=kitchen.household_id,
            batch_id=batch.id,
            place_id=plan_tub.place_id,
            member_login_id=plan_tub.member_login_id,
            use_by=plan_tub.use_by,
        )
        db.add(tub)
        db.flush()
        steps.append({"op": "new_tub", "tub": tub.id, "count": None})
        if plan_tub.spot is not None:
            _put_tub_in_meal(kitchen, tub, plan_tub.spot, steps)
    placed = sum(1 for t in worked.tubs if t.spot is not None)
    word = "tub" if tub_count == 1 else "tubs"
    return _finish(
        kitchen,
        "plan_batch",
        f"Planned {worked.recipe.name} once for {tub_count} {word} ({placed} in the plan)",
        steps,
        meal_id=worked.meal.id,
        batch_id=batch.id,
    )


def _put_tub_in_meal(
    kitchen: Kitchen, tub: Tub, spot: Spot, steps: list[dict[str, Any]]
) -> MealItem:
    """A meal item for a tub, in the meal on that day and slot (made if there is none)."""
    meal = meal_at(kitchen, spot[0], spot[1])
    if meal is None:
        meal = _make_meal(kitchen, spot[0], spot[1], steps)
    else:
        _planned(meal)
        _room(kitchen, meal)
    item = MealItem(
        household_id=kitchen.household_id,
        meal_id=meal.id,
        position=_end(kitchen, meal),
        kind="tub",
        tub_id=tub.id,
    )
    kitchen.db.add(item)
    kitchen.db.flush()
    steps.append({"op": "add_item", "item": item.id})
    return item


# --- Tubs ----------------------------------------------------------------------------------------


def find_tub(kitchen: Kitchen, tub_id: int) -> Tub:
    tub = kitchen.db.get(Tub, tub_id)
    if tub is None or tub.household_id != kitchen.household_id:
        raise not_found("That tub")
    return tub


def find_batch(kitchen: Kitchen, batch_id: int) -> BatchCook:
    batch = kitchen.db.get(BatchCook, batch_id)
    if batch is None or batch.household_id != kitchen.household_id:
        raise not_found("That batch")
    return batch


def item_of_tub(kitchen: Kitchen, tub: Tub) -> MealItem | None:
    return kitchen.db.scalar(
        select(MealItem).where(
            MealItem.household_id == kitchen.household_id, MealItem.tub_id == tub.id
        )
    )


def place_tub(
    kitchen: Kitchen, tub: Tub, day: date, slot_id: int, *, only_if_left: bool = False
) -> Change:
    """Put a tub into a meal ("+ Add a tub", "+ Add a tub too", or a drag from tubs left). A
    tub already in a meal moves there instead: it is in one meal at a time."""
    from mealwright import plan

    existing = item_of_tub(kitchen, tub)
    if existing is not None and only_if_left:
        raise Problem(
            status.HTTP_409_CONFLICT,
            "tub_taken",
            "That tub is already planned for another meal.",  # cabledrawer 8 Nov
        )
    if existing is not None:
        return plan.move_item(kitchen, existing, day, slot_id, "move")
    check_day(kitchen, day)
    find_slot(kitchen, slot_id)
    if tub.amount_quarters == 0:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "tub_eaten",
            "That tub has been eaten.",  # proposed, for cabledrawer
        )
    if day > tub.use_by:  # a tub is no good past its own use-by
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "after_use_by",
            "That’s after this batch’s use-by date.",  # cabledrawer 2 Nov
        )
    steps: list[dict[str, Any]] = []
    _put_tub_in_meal(kitchen, tub, (day, slot_id), steps)
    change = _finish(
        kitchen,
        "plan_tub",
        f"Put {tub_name(kitchen, tub)} in {_where(kitchen, day, slot_id)}",
        steps,
        meal_id=meal_at(kitchen, day, slot_id).id,  # type: ignore[union-attr]
    )
    together.follow(kitchen, tub, change)  # "Eat it on…" goes with the Undo of Cooked it (F125)
    return change


def _tub_fields(tub: Tub) -> dict[str, Any]:
    return {
        "op": "tub",
        "tub": tub.id,
        "member_login_id": tub.member_login_id,
        "use_by": tub.use_by.isoformat(),
        "place_id": tub.place_id,
    }


def edit_tub(kitchen: Kitchen, tub: Tub, fields: dict[str, Any]) -> Change | None:
    """Whose tub it is, or its use-by date. `fields` holds only what was sent."""
    steps = [_tub_fields(tub)]
    left: dict[str, Any] = {}  # what each changed field now holds (F165)
    changed = False
    if "member_login_id" in fields:
        new = fields["member_login_id"]
        if new is not None:
            _own_logins(kitchen, [new])
        changed = changed or new != tub.member_login_id
        if new != tub.member_login_id:
            left["member_login_id"] = new
        tub.member_login_id = new
    if "use_by" in fields and fields["use_by"] is not None:
        new_day = fields["use_by"]
        check_day(kitchen, new_day)  # as Leftovers' use-by: never year 1 or 9999
        batch = kitchen.db.get(BatchCook, tub.batch_id)
        # Not before the cook day (cabledrawer 29 Oct).
        if batch is not None and new_day < batch.cooked_on:
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "use_by_before_cook_day",
                "A tub’s use-by can’t be before the day it was cooked.",  # proposed, for cabledrawer
            )
        changed = changed or new_day != tub.use_by
        if new_day != tub.use_by:
            left["use_by"] = new_day.isoformat()
        tub.use_by = new_day
    if not changed:
        return None
    # One step per changed field, so Undo can put back one and say "partly" (F165).
    steps = [{**steps[0], "to": {field: value}} for field, value in left.items()]
    kitchen.db.flush()
    name = tub_name(kitchen, tub)
    if set(fields) == {"member_login_id"}:
        login = kitchen.db.get(Login, tub.member_login_id) if tub.member_login_id else None
        summary = f"{name} is {login.name}’s" if login else f"{name} is nobody’s in particular"
    else:
        summary = f"{name}: use by {tub.use_by:%a} {tub.use_by.day} {tub.use_by:%b}"
    return _finish(kitchen, "plan_tub", summary, steps)


def eat_tub(kitchen: Kitchen, tub: Tub, quarters: int | None) -> Change:
    """Eat from a tub (0.7 K2; spec "Stock", Tubs; "Cooking" point 7): a tub is used, not the
    ingredients again. One whole tub by default (what is left of it); a quarter-step number says
    "used ½". Whatever is left stays where it is, in its meal or place. Proposed, for cabledrawer:
    an empty tub stays (0 left) for its Undo window like any other tub, and can't be eaten."""
    if tub.amount_quarters <= 0:
        raise Problem(
            status.HTTP_409_CONFLICT,
            "tub_eaten",
            "That tub is all eaten.",  # proposed, for cabledrawer
        )
    used = tub.amount_quarters if quarters is None else quarters
    if used < 1 or used > tub.amount_quarters:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "too_much",
            f"There’s only {quarters_text(tub.amount_quarters)} of that tub left.",  # proposed
        )
    steps = [
        {
            "op": "tub_eat",
            "tub": tub.id,
            "from": tub.amount_quarters,
            "to": tub.amount_quarters - used,
        }
    ]
    tub.amount_quarters -= used
    kitchen.db.flush()
    name = tub_name(kitchen, tub)
    summary = f"Ate {name}" if tub.amount_quarters == 0 else f"Ate {quarters_text(used)} of {name}"
    return _finish(kitchen, "plan_tub", summary, steps)


def bin_tub(kitchen: Kitchen, tub: Tub) -> Change:
    """Binned on a tub (cabledrawer 8 Nov): the whole of what is left of it is thrown away, as
    packet Binned does. Same record as eating a tub (`tub_eat`), so its Undo gives back what was
    binned, and the Recent changes line says "Binned Veg biryani tub". Proposed, for cabledrawer: a
    tub planned for a meal is refused (take it out of the meal first), so a meal never holds a
    tub that is gone."""
    if tub.amount_quarters <= 0:
        raise Problem(
            status.HTTP_409_CONFLICT,
            "tub_eaten",
            "That tub is all eaten.",  # proposed, for cabledrawer
        )
    if item_of_tub(kitchen, tub) is not None:
        raise Problem(
            status.HTTP_409_CONFLICT,
            "tub_in_meal",
            "That tub is planned for a meal. Take it out of the meal first.",  # cabledrawer 8 Nov
        )
    steps = [{"op": "tub_eat", "tub": tub.id, "from": tub.amount_quarters, "to": 0}]
    tub.amount_quarters = 0
    kitchen.db.flush()
    return _finish(kitchen, "plan_tub", f"Binned {tub_name(kitchen, tub)}", steps)


def to_freezer(kitchen: Kitchen, tub: Tub) -> Change:
    """Freeze a tub: it leaves its meal (back to tubs left, in the freezer) and gets a use-by
    the household's freezer life from today (as the pantry's To freezer does). Proposed, for
    cabledrawer: a tub that goes in the freezer is not going to be eaten at that meal."""
    freezer = places_of_kind(kitchen.db, kitchen.household_id, "freezer")
    if freezer is None:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "no_freezer",
            "There’s no freezer in your places yet.",  # proposed, for cabledrawer
        )
    if tub.place_id == freezer.id:
        raise Problem(
            status.HTTP_409_CONFLICT, "already_frozen", "That tub is already in the freezer."
        )
    if tub.use_by < today(kitchen.household):  # as a packet: the use-by day itself still works
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "too_late_to_freeze",
            "Too late to freeze: the use by date has passed.",  # cabledrawer 7 Nov, tubs 8 Nov
        )
    steps: list[dict[str, Any]] = []
    name = tub_name(kitchen, tub)
    item = item_of_tub(kitchen, tub)
    if item is not None:
        meal = kitchen.db.get(Meal, item.meal_id)
        if meal is not None:
            _planned(meal)
        steps.append({"op": "del_item", "item": _snapshot_item(item)})
        kitchen.db.delete(item)
        kitchen.db.flush()
        if meal is not None and not items_of(kitchen, meal):
            _drop_meal(kitchen, meal, steps)
    before = _tub_fields(tub)
    tub.place_id = freezer.id
    tub.use_by = tub_use_by(kitchen, "freezer", today(kitchen.household))
    # What it left, one step per field, so Undo can say "partly" (F165).
    steps.append({**before, "to": {"place_id": freezer.id}})
    steps.append({**before, "to": {"use_by": tub.use_by.isoformat()}})
    kitchen.db.flush()
    return _finish(kitchen, "plan_tub", f"{name} to the freezer", steps)


def batches_cooked_at(kitchen: Kitchen, meal: Meal) -> list[BatchCook]:
    """The batches whose cook meal this is."""
    return list(
        kitchen.db.scalars(
            select(BatchCook).where(
                BatchCook.household_id == kitchen.household_id, BatchCook.cook_meal_id == meal.id
            )
        )
    )


def refuse_cooked(kitchen: Kitchen, batches: list[BatchCook]) -> None:
    """A batch that was cooked keeps its cook day while its cooked record stands."""
    for batch in batches:
        record = cooked.for_batch(kitchen.db, kitchen.household_id, batch.id)
        if record is not None:
            day = today(kitchen.household, as_utc(record.cooked_at))
            raise Problem(
                status.HTTP_409_CONFLICT,
                "already_cooked",
                f"This was cooked on {day:%a} {day.day} {day:%b}. Undo “Cooked it” first.",
            )  # proposed, for cabledrawer


def cooks_item(batch: BatchCook, item: MealItem) -> bool:
    """Whether this item is the recipe the batch was cooked for."""
    if item.kind != "recipe":
        return False
    if item.recipe_id is not None:
        return batch.recipe_id == item.recipe_id
    return batch.recipe_name == item.name


def cook_batches_of(kitchen: Kitchen, item: MealItem, meal: Meal) -> list[BatchCook]:
    """The batches this item is the cook item of. Only one item per batch is: the first (by
    position, then id) of the recipe in the batch's cook meal, so a second copy of the same
    recipe in that meal is an ordinary item."""
    if item.kind != "recipe":
        return []
    found = []
    for batch in batches_cooked_at(kitchen, meal):
        first = next((i for i in items_of(kitchen, meal) if cooks_item(batch, i)), None)
        if first is not None and first.id == item.id:
            found.append(batch)
    return found


def is_cook_item(kitchen: Kitchen, item: MealItem, meal: Meal) -> bool:
    """Whether this item is the recipe a batch was cooked for, in that batch's cook meal."""
    return bool(cook_batches_of(kitchen, item, meal))


def release_cook_link(
    kitchen: Kitchen, cooking: list[BatchCook], meal: Meal, steps: list[dict[str, Any]]
) -> None:
    """A cook item was taken out of a meal that keeps other items: a batch with no other copy of
    its recipe left in the meal forgets the meal (its cook day stays as it is). The step lets
    Undo put the link back."""
    left = items_of(kitchen, meal)
    for batch in cooking:
        if any(cooks_item(batch, i) for i in left):
            continue  # a second copy of the recipe is the cook item now
        steps.append({"op": "batch_link", "batch": batch.id, "meal": meal.id})
        batch.cook_meal_id = None
    kitchen.db.flush()


def move_cook_day(
    kitchen: Kitchen, batches: list[BatchCook], meal: Meal, day: date, steps: list[dict[str, Any]]
) -> None:
    """The cook meal moves to `day` (spec: dragging a COOK card moves the cooking): the batch is
    cooked on that day now, and its tubs' use-by dates keep their distance from it. What is
    changed is kept in the steps, so Undo puts every date back exactly, as long as the meal is
    back where it was (and nothing was cooked since)."""
    db = kitchen.db
    if batches:
        ids = [b.id for b in batches]
        there = db.scalar(
            select(func.count(BatchCook.id)).where(
                BatchCook.household_id == kitchen.household_id,
                BatchCook.cooked_on == day,
                BatchCook.id.not_in(ids),
            )
        )
        if (there or 0) + len(batches) > MOST_BATCHES_A_DAY:
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "too_many_batches",
                f"At most {MOST_BATCHES_A_DAY} batches can be cooked on one day.",  # proposed
            )
    for batch in batches:
        # A tub in a meal can't be left past its new use-by (same rule as placing a tub).
        for tub in db.scalars(
            select(Tub).where(Tub.household_id == kitchen.household_id, Tub.batch_id == batch.id)
        ):
            eaten = item_of_tub(kitchen, tub)
            eaten_meal = db.get(Meal, eaten.meal_id) if eaten is not None else None
            if eaten_meal is None:
                continue
            eaten_on = day if eaten_meal.id == meal.id else eaten_meal.day
            if eaten_on > shifted(tub.use_by, day - batch.cooked_on):
                raise Problem(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "after_use_by",
                    # cabledrawer 2 Nov
                    "Can’t move it earlier: a tub planned later would be past its use-by.",
                )
    for batch in batches:
        tubs = list(
            db.scalars(
                select(Tub).where(
                    Tub.household_id == kitchen.household_id, Tub.batch_id == batch.id
                )
            )
        )
        steps.append(
            {
                "op": "batch_day",
                "batch": batch.id,
                "meal": meal.id,
                "meal_day": meal.day.isoformat(),
                "from": batch.cooked_on.isoformat(),
                "tubs": [[t.id, t.use_by.isoformat()] for t in tubs],
            }
        )
        shift = day - batch.cooked_on
        moved = [shifted(tub.use_by, shift) for tub in tubs]  # all checked before any moves
        steps[-1]["to_day"] = day.isoformat()
        steps[-1]["to_tubs"] = [[t.id, u.isoformat()] for t, u in zip(tubs, moved, strict=True)]
        batch.cooked_on = day
        for tub, use_by in zip(tubs, moved, strict=True):
            tub.use_by = use_by
    db.flush()


def delete_batch(kitchen: Kitchen, batch: BatchCook) -> Change:
    """Take a batch off: its tubs go, and their meal items. Undo brings all back. A batch that
    was cooked can't be taken off while its cooked record stands (the record is never lost)."""
    db = kitchen.db
    record = cooked.for_batch(db, kitchen.household_id, batch.id)
    if record is not None:
        day = today(kitchen.household, as_utc(record.cooked_at))
        raise Problem(
            status.HTTP_409_CONFLICT,
            "already_cooked",
            f"This was cooked on {day:%a} {day.day} {day:%b}. Undo “Cooked it” first.",
        )  # proposed, for cabledrawer
    steps: list[dict[str, Any]] = []
    tubs = list(
        db.scalars(
            select(Tub).where(Tub.household_id == kitchen.household_id, Tub.batch_id == batch.id)
        )
    )
    items = []
    for tub in tubs:
        item = item_of_tub(kitchen, tub)
        if item is not None:
            meal = db.get(Meal, item.meal_id)
            if meal is not None:
                _planned(meal)
            items.append((item, meal))
    for item, meal in items:
        steps.append({"op": "del_item", "item": _snapshot_item(item)})
        db.delete(item)
        db.flush()
        if meal is not None and not items_of(kitchen, meal):
            _drop_meal(kitchen, meal, steps)
    for tub in tubs:
        steps.append(
            {
                "op": "del_tub",
                "tub": {
                    "id": tub.id,
                    "batch_id": tub.batch_id,
                    "amount_quarters": tub.amount_quarters,
                    "place_id": tub.place_id,
                    "member_login_id": tub.member_login_id,
                    "use_by": tub.use_by.isoformat(),
                },
            }
        )
        db.delete(tub)
    db.flush()
    steps.append(
        {
            "op": "del_batch",
            "batch": {
                "id": batch.id,
                "recipe_id": batch.recipe_id,
                "recipe_name": batch.recipe_name,
                "cook_meal_id": batch.cook_meal_id,
                "cooked_on": batch.cooked_on.isoformat(),
                "tub_count": batch.tub_count,
                "pattern": batch.pattern,
                "prep_note": batch.prep_note,
                "colour": batch.colour,
            },
        }
    )
    name = batch.recipe_name
    db.delete(batch)
    db.flush()
    return _finish(kitchen, "plan_batch_removed", f"Took {name}’s tubs off the plan", steps)


# --- "Leftovers here" makes a tub ----------------------------------------------------------------


def leftover_tub(
    kitchen: Kitchen,
    source: Meal,
    item: MealItem,
    target: Meal,
    steps: list[dict[str, Any]],
    *,
    grow: bool = False,
) -> None:
    """A recipe's leftovers in another meal: a tub of the batch cooked for the source meal (the
    batch is made now if there is none), taken from the tubs left if one is spare, else a new
    one. Proposed, for cabledrawer: a meal with several recipes makes a tub of each recipe (and
    copies its plain ingredients); a tub is never copied. A spare tub is used only if its use-by is
    the target's day or later, the earliest use-by first (F50); `grow` always makes a new one."""
    db = kitchen.db
    batch = db.scalar(
        select(BatchCook).where(
            BatchCook.household_id == kitchen.household_id,
            BatchCook.cook_meal_id == source.id,
            BatchCook.recipe_id == item.recipe_id
            if item.recipe_id is not None
            else BatchCook.recipe_name == item.name,
        )
    )
    if batch is None:
        _batches_that_day(kitchen, source.day)
        recipe = _own(kitchen, Recipe, item.recipe_id) if item.recipe_id else None
        batch = BatchCook(
            household_id=kitchen.household_id,
            recipe_id=recipe.id if recipe else None,
            recipe_name=recipe.name if recipe else (item.name or "a recipe"),
            cook_meal_id=source.id,
            cooked_on=source.day,
            tub_count=0,
            pattern="pick",
            colour=next_colour(kitchen, source.day),
        )
        # tub_count is 1 or more in the database: the first tub is made just below.
        batch.tub_count = 1
        if item.servings is None and recipe is not None and recipe.serves:
            # The meal was planned for the recipe's own servings; say so, so the tub added now
            # is bought on top of those and not in place of them (F58). Same amounts as before.
            item.servings = recipe.serves
        db.add(batch)
        db.flush()
        steps.append({"op": "new_batch", "batch": batch.id})
        made = 0
    else:
        made = (
            db.scalar(
                select(func.count(Tub.id)).where(
                    Tub.household_id == kitchen.household_id, Tub.batch_id == batch.id
                )
            )
            or 0
        )
    spare = (
        None
        if grow
        else db.scalar(
            select(Tub)
            .where(
                Tub.household_id == kitchen.household_id,
                Tub.batch_id == batch.id,
                Tub.amount_quarters > 0,
                Tub.use_by >= target.day,
                ~exists().where(MealItem.tub_id == Tub.id),
            )
            .order_by(Tub.use_by, Tub.id)
            .limit(1)
        )
    )
    if spare is None:
        if made >= MOST_TUBS_IN_BATCH:
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "batch_full",
                f"{batch.recipe_name} already has {MOST_TUBS_IN_BATCH} tubs.",  # proposed
            )
        fridge = places_of_kind(db, kitchen.household_id, "fridge")
        use_by = tub_use_by(kitchen, "fridge", really_cooked_on(kitchen, batch))
        if target.day > use_by:  # a new fridge tub is no good past its own use-by
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "after_use_by",
                "That’s after this batch’s use-by date.",  # cabledrawer 2 Nov
            )
        spare = Tub(
            household_id=kitchen.household_id,
            batch_id=batch.id,
            place_id=fridge.id if fridge else None,
            use_by=use_by,
        )
        db.add(spare)
        db.flush()
        before = batch.tub_count
        batch.tub_count = max(made + 1, 1)
        steps.append({"op": "new_tub", "tub": spare.id, "count": before, "to": batch.tub_count})
    clone = MealItem(
        household_id=kitchen.household_id,
        meal_id=target.id,
        position=_end(kitchen, target),
        kind="tub",
        tub_id=spare.id,
    )
    db.add(clone)
    db.flush()
    steps.append({"op": "add_item", "item": clone.id})


# --- Portions (0.7, P1; cabledrawer 28 Oct) ----------------------------------------------------------
#
# A batch makes a fixed number of portions: its tubs plus the cook-day meal (the people eating
# the cooking on the day; one when the meal has no number of its own, as Cook once and the
# shopping list already count it). A portion is "left" while its tub is in no meal and not eaten.


@dataclass
class Portions:
    cook_day: int
    tubs: int
    in_meals: int
    left: int
    # The last day a tub of this batch can go in a meal: the latest use-by of a tub still
    # to place, else the household's fridge life from the cook day.
    use_by: date
    # The use-by of each spare tub, soonest first: a tub can only go in a meal on or before it.
    spare: list[date]

    @property
    def total(self) -> int:
        return self.cook_day + self.tubs


def cook_item_of(kitchen: Kitchen, batch: BatchCook) -> MealItem | None:
    if batch.cook_meal_id is None or batch.recipe_id is None:
        return None
    return kitchen.db.scalar(
        select(MealItem)
        .where(
            MealItem.household_id == kitchen.household_id,
            MealItem.meal_id == batch.cook_meal_id,
            MealItem.recipe_id == batch.recipe_id,
        )
        .order_by(MealItem.position, MealItem.id)  # the first copy, as is_cook_item
        .limit(1)
    )


def portions_of(kitchen: Kitchen, batch: BatchCook) -> Portions:
    db = kitchen.db
    item = cook_item_of(kitchen, batch)
    cook_day = (item.servings if item else None) or 1
    tubs = list(
        db.execute(
            select(
                Tub.amount_quarters, Tub.use_by, exists().where(MealItem.tub_id == Tub.id)
            ).where(Tub.household_id == kitchen.household_id, Tub.batch_id == batch.id)
        )
    )
    spare = [use_by for quarters, use_by, in_meal in tubs if quarters > 0 and not in_meal]
    fridge = tub_use_by(kitchen, "fridge", really_cooked_on(kitchen, batch))
    return Portions(
        cook_day=cook_day,
        tubs=batch.tub_count,
        in_meals=sum(1 for _q, _u, in_meal in tubs if in_meal),
        left=len(spare),
        use_by=max(spare) if spare else fridge,
        spare=sorted(spare),
    )


def reach(spare: list[date], days: list[date]) -> int:
    """How many of the meals (days, soonest first) the spare tubs reach: each meal takes the
    spare tub with the earliest use-by that is on or after its day (F50: never a tub past its
    use-by). The same rule the sheet uses (portions.ts) and `leftover_tub` follows."""
    free = sorted(spare)
    taken = 0
    for day in days:
        for index, use_by in enumerate(free):
            if use_by >= day:
                del free[index]
                taken += 1
                break
    return taken


def portions_by_batch(kitchen: Kitchen, found: list[BatchCook]) -> dict[int, Portions]:
    """`portions_of` for the batches a plan read answers (a few queries each; a plan read has
    at most the batches of 62 days)."""
    return {b.id: portions_of(kitchen, b) for b in found}


def _batch_of(kitchen: Kitchen, source: Meal, item: MealItem) -> BatchCook | None:
    return kitchen.db.scalar(
        select(BatchCook).where(
            BatchCook.household_id == kitchen.household_id,
            BatchCook.cook_meal_id == source.id,
            BatchCook.recipe_id == item.recipe_id
            if item.recipe_id is not None
            else BatchCook.recipe_name == item.name,
        )
    )


def _no_portions(left: int, wanted: int) -> Problem:
    return Problem(
        status.HTTP_409_CONFLICT,
        "no_portions_left",
        "No portions left.",
        left=left,
        wanted=wanted,
    )


def leftover_one(
    kitchen: Kitchen,
    source: Meal,
    item: MealItem,
    target: Meal,
    steps: list[dict[str, Any]],
    if_none_left: str,
) -> None:
    """One meal's leftovers (cabledrawer 28 Oct: "No portions left"). A batch that exists and has no
    spare tub reaching this meal: `ask` refuses with `no_portions_left`, `cook_more` makes a new
    tub (a bigger batch), `add_anyway` plans the recipe there for one serving and leaves the
    batch. No batch yet: it is made, as before."""
    batch = _batch_of(kitchen, source, item)
    if batch is None:
        leftover_tub(kitchen, source, item, target, steps)
        return
    if reach(portions_of(kitchen, batch).spare, [target.day]):
        leftover_tub(kitchen, source, item, target, steps)
    elif if_none_left == "cook_more":
        leftover_tub(kitchen, source, item, target, steps, grow=True)
    elif if_none_left == "add_anyway":
        anyway = MealItem(
            household_id=kitchen.household_id,
            meal_id=target.id,
            position=_end(kitchen, target),
            kind="recipe",
            recipe_id=item.recipe_id,
            name=None if item.recipe_id else item.name,
            servings=1,
        )
        kitchen.db.add(anyway)
        kitchen.db.flush()
        steps.append({"op": "add_item", "item": anyway.id})
    else:
        raise _no_portions(0, 1)


def recipe_meal_item(kitchen: Kitchen, item: MealItem) -> Meal:
    """The planned meal of a recipe item that can have leftovers (a tub, a plain ingredient or
    a note can't)."""
    meal = kitchen.db.get(Meal, item.meal_id)
    if meal is None:  # pragma: no cover (the database keeps every item in a meal)
        raise not_found("That meal")
    _planned(meal)
    if item.kind != "recipe":
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "not_a_recipe",
            "Only a recipe can have leftovers.",  # proposed, for cabledrawer
        )
    return meal


def leftovers_on(kitchen: Kitchen, item: MealItem, spots: list[Spot], if_none_left: str) -> Change:
    """ "Leftovers on…" with several meals ticked at once. Each meal gets a portion of the
    batch cooked for the item's meal (the batch is made now if there is none). The earliest
    meals take the portions left; for the rest, `ask` refuses with `no_portions_left` and
    changes nothing, `cook_more` grows the batch by a tub each, and `add_anyway` plans the
    recipe in those meals (one serving) and leaves the batch as it is."""
    source = recipe_meal_item(kitchen, item)
    if not spots:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "no_meals",
            "Tick at least one meal.",  # proposed, for cabledrawer
        )
    if len(set(spots)) != len(spots):
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "same_meal_twice",
            "A meal is ticked twice.",  # proposed, for cabledrawer
        )
    slot_order = {s.id: (s.position, s.id) for s in meal_slots(kitchen.db, kitchen.household_id)}
    batch = _batch_of(kitchen, source, item)
    portions = portions_of(kitchen, batch) if batch else None
    use_by = portions.use_by if portions else tub_use_by(kitchen, "fridge", source.day)
    for day, slot_id in spots:
        check_day(kitchen, day)
        find_slot(kitchen, slot_id)
        check_after_cook(kitchen, source, day, slot_id)
        if day > use_by:
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "after_use_by",
                "That’s after this batch’s use-by date.",  # cabledrawer 2 Nov
            )
        target = meal_at(kitchen, day, slot_id)
        if target is not None:
            _planned(target)
            _room(kitchen, target)
    ordered = sorted(spots, key=lambda s: (s[0], slot_order.get(s[1], (0, s[1]))))
    left = reach(portions.spare, [d for d, _ in ordered]) if portions else len(ordered)
    if batch is not None and left < len(ordered) and if_none_left == "ask":
        raise _no_portions(left, len(ordered))
    # No batch yet: the first meal makes it and the rest are more tubs of it, not "none left".
    choice = "cook_more" if batch is None else if_none_left
    steps: list[dict[str, Any]] = []
    first: Meal | None = None
    for day, slot_id in ordered:
        target = meal_at(kitchen, day, slot_id)
        if target is None:
            target = _make_meal(kitchen, day, slot_id, steps)
        first = first or target
        leftover_one(kitchen, source, item, target, steps, choice)
    name = _item_name(kitchen, item)
    where = ", ".join(_where(kitchen, d, s) for d, s in ordered)
    return _finish(
        kitchen,
        _KINDS["leftovers"],
        f"Planned leftovers of {name} on {where}",
        steps,
        meal_id=first.id if first else None,
    )


# --- Fill from freezer first ---------------------------------------------------------------------


def fill_from_freezer(kitchen: Kitchen, first: date, last: date) -> Change | None:
    """Month's "Fill from freezer first": every day in the range with nothing planned gets a
    tub from the freezer, oldest use-by first, in the last meal that is switched on (as a
    recipe dropped on a Month day does). None when there is nothing to fill or nothing to fill
    it with. Days too far from today to plan are left out (Month's grid runs into next
    month)."""
    db = kitchen.db
    now = today(kitchen.household)
    first = max(first, now - timedelta(days=DAYS_BACK))
    last = min(last, now + timedelta(days=DAYS_AHEAD))
    if first > last:
        return None
    slots = [s for s in meal_slots(db, kitchen.household_id) if s.enabled]
    if not slots:
        return None
    slot = slots[-1]
    freezer = places_of_kind(db, kitchen.household_id, "freezer")
    if freezer is None:
        return None
    tubs = list(
        db.scalars(
            select(Tub)
            .where(
                Tub.household_id == kitchen.household_id,
                Tub.place_id == freezer.id,
                Tub.amount_quarters > 0,
                Tub.use_by >= first,
                ~exists().where(MealItem.tub_id == Tub.id),
            )
            .order_by(Tub.use_by, Tub.id)
        )
    )
    busy = {
        day
        for (day,) in db.execute(
            select(Meal.day)
            .join(MealItem, MealItem.meal_id == Meal.id)
            .where(Meal.household_id == kitchen.household_id, Meal.day >= first, Meal.day <= last)
        )
    }
    held = {
        day
        for (day,) in db.execute(
            select(Meal.day).where(
                Meal.household_id == kitchen.household_id,
                Meal.day >= first,
                Meal.day <= last,
                Meal.status != "planned",
            )
        )
    }
    steps: list[dict[str, Any]] = []
    filled: list[date] = []
    day = first
    while day <= last and tubs:
        if day not in busy and day not in held:
            # The tubs are in use-by order: the first one still in date on this day (a tub is no
            # good past its own use-by, as place_tub says).
            pick = next((i for i, t in enumerate(tubs) if t.use_by >= day), None)
            if pick is not None:
                check_day(kitchen, day)
                tub = tubs.pop(pick)
                _put_tub_in_meal(kitchen, tub, (day, slot.id), steps)
                filled.append(day)
        day += timedelta(days=1)
    if not filled:
        return None
    # Which meals, and why (cabledrawer 28 Oct): the soonest use-by goes first, so the tubs that run
    # out soonest are eaten first.
    named = [f"{_WEEKDAYS[d.weekday()]} {d.day} {slot.name.lower()}" for d in filled]
    summary = _fill_summary(named)
    return _finish(kitchen, "plan_tub", summary, steps)


def _fill_summary(named: list[str]) -> str:
    """The Fill message. It is kept to 300 characters (the history keeps no more) by naming
    fewer meals and counting the rest as "N more", so the reason always stays."""
    for shown in range(min(len(named), _MOST_NAMED), -1, -1):
        names = named[:shown]
        if shown < len(named):
            names = [*names, f"{len(named) - shown} more"]
        meals = ", ".join(names)
        if len(named) == 1:
            summary = (
                f"Filled {meals} from a freezer tub (it runs out soonest)"  # proposed, for cabledrawer
            )
        else:
            summary = f"Filled {meals} from freezer tubs (they run out soonest)"
        if len(summary) <= 300:
            break
    return summary


_MOST_NAMED = 6
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


# --- Reading -----------------------------------------------------------------------------------


@dataclass
class TubLeft:
    tub: Tub
    batch: BatchCook
    number: int
    place_kind: str | None


def tubs_left(kitchen: Kitchen, limit: int) -> tuple[list[TubLeft], bool]:
    """Tubs in no meal that still have some in them, soonest use-by first. One more than
    `limit` is read, to say whether there are more."""
    db = kitchen.db
    other = aliased(Tub)
    number = (
        select(func.count(other.id))
        .where(other.batch_id == Tub.batch_id, other.id <= Tub.id)
        .scalar_subquery()
    )
    rows = db.execute(
        select(Tub, BatchCook, number, Place.kind)
        .join(
            BatchCook,
            and_(BatchCook.id == Tub.batch_id, BatchCook.household_id == Tub.household_id),
        )
        .outerjoin(Place, and_(Place.id == Tub.place_id, Place.household_id == Tub.household_id))
        .where(
            Tub.household_id == kitchen.household_id,
            Tub.amount_quarters > 0,
            ~exists().where(MealItem.tub_id == Tub.id),
        )
        .order_by(Tub.use_by, Tub.id)
        .limit(limit + 1)
    ).all()
    out = [TubLeft(tub=t, batch=b, number=n, place_kind=k) for t, b, n, k in rows[:limit]]
    return out, len(rows) > limit


# --- Undo ----------------------------------------------------------------------------------------


def undo_step(kitchen: Kitchen, step: dict[str, Any], remap: dict[int, int]) -> bool:
    """Undo one batch or tub step of a change (plan.py hands over the ones it doesn't know).
    A step that no longer fits is skipped (False)."""
    db = kitchen.db
    op = step["op"]
    if op == "new_batch":
        batch = _own(kitchen, BatchCook, step["batch"])
        if batch is None or db.scalar(select(Tub.id).where(Tub.batch_id == batch.id).limit(1)):
            return False  # tubs of it are still about (one sits in a meal that was dealt with)
        if cooked.for_batch(db, kitchen.household_id, batch.id) is not None:
            return False  # cooked since: its record stays (the pantry was taken from)
        db.delete(batch)
        db.flush()
        return True
    if op == "batch_link":
        batch = _own(kitchen, BatchCook, step["batch"])
        linked = _own(kitchen, Meal, remap.get(step["meal"], step["meal"]))
        if batch is None or linked is None or batch.cook_meal_id is not None:
            return False
        if linked.day != batch.cooked_on:
            return False  # the meal moved on since: it would be split from its cook day
        batch.cook_meal_id = linked.id
        db.flush()
        return True
    if op == "batch_day":
        batch = _own(kitchen, BatchCook, step["batch"])
        meal = _own(kitchen, Meal, step["meal"])
        if batch is None or meal is None:
            return False
        # The dates follow the meal: only when it is back where it was, and the batch has not
        # been cooked since (a cooked batch keeps its cook day).
        if meal.day != date.fromisoformat(step["meal_day"]):
            return False
        if cooked.for_batch(db, kitchen.household_id, batch.id) is not None:
            return False
        left_tubs = dict(step.get("to_tubs", []))
        if "to_day" in step and batch.cooked_on.isoformat() != step["to_day"]:
            return False  # the cook day was changed again since (F165)
        batch.cooked_on = date.fromisoformat(step["from"])
        complete = True
        for tub_id, use_by in step["tubs"]:
            tub = _own(kitchen, Tub, tub_id)
            if tub is None or (tub_id in left_tubs and tub.use_by.isoformat() != left_tubs[tub_id]):
                complete = False  # gone, or given another date since (F165)
                continue
            tub.use_by = date.fromisoformat(use_by)
        db.flush()
        return complete
    if op == "tub_early":
        done = True
        for tub_id, use_by, *left in step["tubs"]:
            tub = _own(kitchen, Tub, tub_id)
            if tub is None or (left and tub.use_by.isoformat() != left[0]):
                done = False  # gone, or given another date since (F165)
                continue
            tub.use_by = date.fromisoformat(use_by)
        db.flush()
        return done
    if op == "new_tub":
        tub = _own(kitchen, Tub, step["tub"])
        if tub is None or item_of_tub(kitchen, tub) is not None:
            return False
        batch = db.get(BatchCook, tub.batch_id)
        if step["count"] is None and cooked.for_batch(db, kitchen.household_id, tub.batch_id):
            return False  # a cooked batch keeps the tubs it was made with (later ones go)
        db.delete(tub)
        db.flush()
        if batch is not None and step["count"] is not None:
            if "to" not in step or batch.tub_count == step["to"]:
                batch.tub_count = step["count"]
            else:  # the count has changed again since (F165): take off just this tub
                batch.tub_count = max(batch.tub_count - 1, 1)
        return True
    if op == "tub_eat":
        tub = _own(kitchen, Tub, step["tub"])
        if tub is None:
            return False
        # As a stock Undo does: give back what this change ate, on top of what is there now, up
        # to a whole tub; what can't be given back makes it "partly".
        back = step["from"] - step["to"]
        # The cap is unreachable today (eating only lowers a tub); it guards a later refill.
        whole: bool = tub.amount_quarters + back <= 4
        tub.amount_quarters = min(tub.amount_quarters + back, 4)
        db.flush()
        return whole
    if op == "tub":
        tub = _own(kitchen, Tub, step["tub"])
        if tub is None:
            return False
        left = step.get("to")  # the fields this change set, with what they were set to (F165)
        whole = True
        if left is None or "member_login_id" in left:
            if left is None or tub.member_login_id == left["member_login_id"]:
                tub.member_login_id = (
                    step["member_login_id"]
                    if _own(kitchen, Login, step["member_login_id"])
                    else None
                )
            else:
                whole = False
        if left is None or "use_by" in left:
            if left is None or tub.use_by.isoformat() == left["use_by"]:
                tub.use_by = date.fromisoformat(step["use_by"])
            else:
                whole = False
        if left is None or "place_id" in left:
            if left is None or tub.place_id == left["place_id"]:
                tub.place_id = step["place_id"] if _own(kitchen, Place, step["place_id"]) else None
            else:
                whole = False
        db.flush()
        return whole
    if op == "del_tub":
        old = step["tub"]
        if _own(kitchen, BatchCook, old["batch_id"]) is None:
            return False
        if db.get(Tub, old["id"]) is not None:
            return False
        db.add(
            Tub(
                id=old["id"],
                household_id=kitchen.household_id,
                batch_id=old["batch_id"],
                amount_quarters=old["amount_quarters"],
                place_id=old["place_id"] if _own(kitchen, Place, old["place_id"]) else None,
                member_login_id=old["member_login_id"]
                if _own(kitchen, Login, old["member_login_id"])
                else None,
                use_by=date.fromisoformat(old["use_by"]),
            )
        )
        db.flush()
        return True
    if op == "del_batch":
        old = step["batch"]
        if db.get(BatchCook, old["id"]) is not None:
            return False
        # The day's cap holds for Undo too (delete, make another, then Undo would get round it).
        _batches_that_day(kitchen, date.fromisoformat(old["cooked_on"]))
        cook_meal = _own(kitchen, Meal, remap.get(old["cook_meal_id"], old["cook_meal_id"]))
        db.add(
            BatchCook(
                id=old["id"],
                household_id=kitchen.household_id,
                recipe_id=old["recipe_id"] if _own(kitchen, Recipe, old["recipe_id"]) else None,
                recipe_name=old["recipe_name"],
                cook_meal_id=cook_meal.id if cook_meal else None,
                cooked_on=date.fromisoformat(old["cooked_on"]),
                tub_count=old["tub_count"],
                pattern=old["pattern"],
                prep_note=old["prep_note"],
                colour=old["colour"],
            )
        )
        db.flush()
        return True
    return False  # pragma: no cover (every step the plan writes is handled)
