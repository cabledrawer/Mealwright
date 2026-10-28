"""Plan helpers the screens' writes will share (0.6)."""

from datetime import date, timedelta
from typing import Any, Literal

from fastapi import status
from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from mealwright.api.v1.context import Kitchen
from mealwright.errors import Problem, not_found
from mealwright.history import UNDO_MESSAGES, Tally, as_utc, record
from mealwright.household import today
from mealwright.models import BatchCook, Change, Food, Meal, MealItem, MealSlot, Recipe, Tub


def delete_meal(db: DbSession, meal: Meal) -> None:
    """Delete a meal with its items. A batch cook that was cooked for it forgets the link
    first (the database refuses to delete a meal that one still points at, since a plain
    "set null" would also empty the household)."""
    db.execute(
        update(BatchCook)
        .where(BatchCook.household_id == meal.household_id, BatchCook.cook_meal_id == meal.id)
        .values(cook_meal_id=None)
    )
    db.delete(meal)
    db.flush()


# --- Writing the plan (0.6 PR 3) ---------------------------------------------------------------
#
# Every write is one Change with its Undo. What Undo needs is kept in `undo_data["plan"]`, a
# list of small steps, put back newest first. A step that no longer fits (a meal that has
# since been filled, a recipe that is gone for good) is skipped and the Undo says "partly".

# Hard caps, so a plan stays small (cabledrawer 26 Oct): 20 items in a meal and
# 12 meal slots (MOST_SLOTS, household.py, enforced where slots are made). GET /plan passes lists
# of ids to the database, and SQLite takes at most 32,766 of them in one query: a 62-day range
# with 12 slots of 20 items is at most 62 x 12 x 20 = 14,880, so these caps keep it well under
# (do not raise them without changing how /plan reads).
MOST_ITEMS_IN_MEAL = 20
# How far from today a day may be (cabledrawer 26 Oct).
DAYS_BACK = 366
DAYS_AHEAD = 731

Mode = Literal["move", "copy", "leftovers"]


def _words_day(day: date) -> str:
    return f"{day:%a} {day.day} {day:%b}"


def check_day(kitchen: Kitchen, day: date) -> None:
    now = today(kitchen.household)
    if day < now - timedelta(days=DAYS_BACK) or day > now + timedelta(days=DAYS_AHEAD):
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "bad_day",
            "That day is too far from today to plan.",  # proposed, for cabledrawer
        )


def check_after_cook(kitchen: Kitchen, cook: Meal, day: date, slot_id: int) -> None:
    """Leftovers and tubs only go to meals after the cook meal, and never to a past day (F50,
    cabledrawer 28 Oct: "just dont show dates befor eth cooked date")."""
    if day < today(kitchen.household):
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "not_after_cook",
            "Pick a meal after the cooking, today or later.",  # proposed, for cabledrawer
        )
    here, there = kitchen.db.get(MealSlot, cook.slot_id), kitchen.db.get(MealSlot, slot_id)
    if here is None or there is None:  # pragma: no cover (find_slot has checked the slot)
        return
    if (day, there.position, there.id) <= (cook.day, here.position, here.id):
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "not_after_cook",
            "Pick a meal after the cooking, today or later.",  # proposed, for cabledrawer
        )


def find_slot(kitchen: Kitchen, slot_id: int, *, on: bool = True) -> MealSlot:
    slot = kitchen.db.get(MealSlot, slot_id)
    if slot is None or slot.household_id != kitchen.household_id:
        raise not_found("That meal")
    if on and not slot.enabled:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "slot_off",
            f"{slot.name} is switched off. Turn it on under Meals to plan it.",  # proposed
        )
    return slot


def find_meal(kitchen: Kitchen, meal_id: int) -> Meal:
    meal = kitchen.db.get(Meal, meal_id)
    if meal is None or meal.household_id != kitchen.household_id:
        raise not_found("That meal")
    return meal


def find_item(kitchen: Kitchen, item_id: int) -> MealItem:
    item = kitchen.db.get(MealItem, item_id)
    if item is None or item.household_id != kitchen.household_id:
        raise not_found("That item")
    return item


def _planned(meal: Meal) -> None:
    if meal.status != "planned":
        # Cooked, skipped and moved meals are Today's (PR 6) and locked here (cabledrawer 26 Oct).
        raise Problem(
            status.HTTP_409_CONFLICT,
            "meal_done",
            "That meal has already been dealt with, so it can’t be changed here.",
        )


def meal_at(kitchen: Kitchen, day: date, slot_id: int) -> Meal | None:
    return kitchen.db.scalar(
        select(Meal).where(
            Meal.household_id == kitchen.household_id, Meal.day == day, Meal.slot_id == slot_id
        )
    )


def items_of(kitchen: Kitchen, meal: Meal) -> list[MealItem]:
    return list(
        kitchen.db.scalars(
            select(MealItem)
            .where(MealItem.household_id == kitchen.household_id, MealItem.meal_id == meal.id)
            .order_by(MealItem.position, MealItem.id)
        )
    )


def _room(kitchen: Kitchen, meal: Meal, more: int = 1) -> None:
    count = len(items_of(kitchen, meal))
    if count + more > MOST_ITEMS_IN_MEAL:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "meal_full",
            f"A meal holds at most {MOST_ITEMS_IN_MEAL} things.",  # proposed, for cabledrawer
        )


def _make_meal(kitchen: Kitchen, day: date, slot_id: int, steps: list[dict[str, Any]]) -> Meal:
    meal = Meal(household_id=kitchen.household_id, day=day, slot_id=slot_id)
    kitchen.db.add(meal)
    kitchen.db.flush()
    steps.append({"op": "new_meal", "meal": meal.id})
    return meal


def _end(kitchen: Kitchen, meal: Meal) -> int:
    items = items_of(kitchen, meal)
    return (items[-1].position + 1) if items else 0


def _item_name(kitchen: Kitchen, item: MealItem) -> str:
    if item.recipe_id is not None:
        recipe = kitchen.db.get(Recipe, item.recipe_id)
        return recipe.name if recipe else "a recipe"
    if item.food_id is not None:
        food = kitchen.db.get(Food, item.food_id)
        return food.name if food else "an ingredient"
    if item.kind != "tub" and item.name:
        return item.name  # deleted for good: the meal kept its name (cabledrawer 26 Oct)
    tub = kitchen.db.get(Tub, item.tub_id) if item.tub_id is not None else None
    batch = kitchen.db.get(BatchCook, tub.batch_id) if tub is not None else None
    return f"{batch.recipe_name} tub" if batch else "a tub"


def _meal_name(kitchen: Kitchen, meal: Meal) -> str:
    names = [_item_name(kitchen, i) for i in items_of(kitchen, meal)]
    if not names:
        return "an empty meal"
    return names[0] if len(names) == 1 else f"{names[0]} and {len(names) - 1} more"


def _where(kitchen: Kitchen, day: date, slot_id: int) -> str:
    slot = kitchen.db.get(MealSlot, slot_id)
    return f"{slot.name if slot else 'meal'} on {_words_day(day)}"


def _snapshot_item(item: MealItem) -> dict[str, Any]:
    return {
        "id": item.id,
        "meal_id": item.meal_id,
        "position": item.position,
        "kind": item.kind,
        "name": item.name,
        "recipe_id": item.recipe_id,
        "tub_id": item.tub_id,
        "food_id": item.food_id,
        "servings": item.servings,
    }


def _drop_meal(kitchen: Kitchen, meal: Meal, steps: list[dict[str, Any]]) -> None:
    batches = list(
        kitchen.db.scalars(
            select(BatchCook.id).where(
                BatchCook.household_id == kitchen.household_id, BatchCook.cook_meal_id == meal.id
            )
        )
    )
    steps.append(
        {
            "op": "del_meal",
            "meal": {
                "id": meal.id,
                "day": meal.day.isoformat(),
                "slot_id": meal.slot_id,
                "status": meal.status,
            },
            "batches": batches,
        }
    )
    delete_meal(kitchen.db, meal)


def list_follows_plan(kitchen: Kitchen) -> None:
    """After a plan or batch write, the shopping list is brought up to date (0.6 PR 5)."""
    from mealwright import shop_from_plan  # imported here: it needs the recipe and list code

    shop_from_plan.refresh(kitchen)


def _finish(
    kitchen: Kitchen, kind: str, summary: str, steps: list[dict[str, Any]], **extra: Any
) -> Change:
    change = record(kitchen, kind, summary, None, {"plan": steps, **extra})
    list_follows_plan(kitchen)
    return change


def add_item(
    kitchen: Kitchen,
    day: date,
    slot_id: int,
    recipe: Recipe | None,
    food: Food | None,
    servings: int | None,
) -> Change:
    """Plan a recipe or a plain ingredient. A filled meal gets it alongside."""
    check_day(kitchen, day)
    find_slot(kitchen, slot_id)
    steps: list[dict[str, Any]] = []
    meal = meal_at(kitchen, day, slot_id)
    if meal is None:
        meal = _make_meal(kitchen, day, slot_id, steps)
    else:
        _planned(meal)
        _room(kitchen, meal)
    item = MealItem(
        household_id=kitchen.household_id,
        meal_id=meal.id,
        position=_end(kitchen, meal),
        recipe_id=recipe.id if recipe else None,
        food_id=food.id if food else None,
        servings=servings if recipe else None,
    )
    kitchen.db.add(item)
    kitchen.db.flush()
    steps.append({"op": "add_item", "item": item.id})
    name = recipe.name if recipe else food.name if food else "an ingredient"
    return _finish(
        kitchen,
        "plan_added",
        f"Planned {name} for {_where(kitchen, day, slot_id)}",
        steps,
        meal_id=meal.id,
        item_id=item.id,
    )


def remove_item(kitchen: Kitchen, item: MealItem) -> Change:
    meal = kitchen.db.get(Meal, item.meal_id)
    if meal is None:  # pragma: no cover (the database keeps every item in a meal)
        raise not_found("That meal")
    _planned(meal)
    steps: list[dict[str, Any]] = []
    name, where = _item_name(kitchen, item), _where(kitchen, meal.day, meal.slot_id)
    steps.append({"op": "del_item", "item": _snapshot_item(item)})
    kitchen.db.delete(item)
    kitchen.db.flush()
    if not items_of(kitchen, meal):
        _drop_meal(kitchen, meal, steps)
    if item.kind == "tub":  # a tub is not thrown away: it goes back to "tubs left"
        return _finish(kitchen, "plan_removed", f"Put {name} back in tubs left from {where}", steps)
    return _finish(kitchen, "plan_removed", f"Removed {name} from {where}", steps)


def remove_meal(kitchen: Kitchen, meal: Meal) -> Change:
    _planned(meal)
    steps: list[dict[str, Any]] = []
    name, where = _meal_name(kitchen, meal), _where(kitchen, meal.day, meal.slot_id)
    for item in items_of(kitchen, meal):
        steps.append({"op": "del_item", "item": _snapshot_item(item)})
    _drop_meal(kitchen, meal, steps)
    return _finish(kitchen, "plan_removed", f"Removed {name} from {where}", steps)


_KINDS = {"move": "plan_moved", "copy": "plan_copied", "leftovers": "plan_leftovers"}


def _copy_of(kitchen: Kitchen, item: MealItem, meal: Meal, steps: list[dict[str, Any]]) -> None:
    clone = MealItem(
        household_id=kitchen.household_id,
        meal_id=meal.id,
        position=_end(kitchen, meal),
        kind=item.kind,
        # A linked item takes its recipe's or ingredient's name afresh; a kept name is copied.
        name=None if item.recipe_id or item.food_id else item.name,
        recipe_id=item.recipe_id,
        food_id=item.food_id,
        servings=item.servings,
    )
    kitchen.db.add(clone)
    kitchen.db.flush()
    steps.append({"op": "add_item", "item": clone.id})


def _leftovers_of(
    kitchen: Kitchen, item: MealItem, source: Meal, meal: Meal, steps: list[dict[str, Any]]
) -> None:
    """ "Leftovers here" (cabledrawer 26 Oct, PR 4): a recipe becomes a tub of its batch cook, an
    ingredient is copied. A tub is never copied (the callers leave tubs out)."""
    if item.kind == "recipe":
        from mealwright import batches

        batches.leftover_tub(kitchen, source, item, meal, steps)
    else:
        _copy_of(kitchen, item, meal, steps)


def _bring(kitchen: Kitchen, item: MealItem, meal: Meal, steps: list[dict[str, Any]]) -> None:
    steps.append(
        {"op": "move_item", "item": item.id, "from_meal": item.meal_id, "position": item.position}
    )
    item.meal_id = meal.id
    item.position = _end(kitchen, meal)
    kitchen.db.flush()


def move_meal(kitchen: Kitchen, meal: Meal, day: date, slot_id: int, mode: Mode) -> Change:
    """Move a whole meal, or copy it. "Leftovers" makes a tub of each recipe in it (from the
    batch cook cooked for this meal, made if there is none) and copies its ingredients.
    Onto a filled meal, the items go in alongside."""
    check_day(kitchen, day)
    find_slot(kitchen, slot_id)
    _planned(meal)
    if (meal.day, meal.slot_id) == (day, slot_id):
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "same_place", "That meal is already there."
        )
    if mode == "leftovers":
        check_after_cook(kitchen, meal, day, slot_id)
    steps: list[dict[str, Any]] = []
    name, source = _meal_name(kitchen, meal), meal
    target = meal_at(kitchen, day, slot_id)
    if target is not None:
        _planned(target)
    items = items_of(kitchen, meal)
    if mode != "move":
        items = [i for i in items if i.tub_id is None]  # a tub is in one meal at a time
        if not items:
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "nothing_to_copy",
                "Nothing in that meal can be copied.",  # proposed, for cabledrawer
            )
    if target is not None:
        _room(kitchen, target, len(items))
    elif mode == "move":
        # Nothing there yet: the meal itself moves, so it keeps its place in a batch cook.
        steps.append(
            {
                "op": "move_meal",
                "meal": meal.id,
                "from": [meal.day.isoformat(), meal.slot_id],
            }
        )
        verb = "Moved"
        where_from = _where(kitchen, meal.day, meal.slot_id)
        meal.day, meal.slot_id = day, slot_id
        kitchen.db.flush()
        return _finish(
            kitchen,
            "plan_moved",
            f"{verb} {name} from {where_from} to {_where(kitchen, day, slot_id)}",
            steps,
            meal_id=meal.id,
        )
    if target is None:
        target = _make_meal(kitchen, day, slot_id, steps)
    for item in items:
        if mode == "move":
            _bring(kitchen, item, target, steps)
        elif mode == "leftovers":
            _leftovers_of(kitchen, item, source, target, steps)
        else:
            _copy_of(kitchen, item, target, steps)
    if mode == "move":
        _drop_meal(kitchen, source, steps)
    verb = {"move": "Moved", "copy": "Copied", "leftovers": "Planned leftovers of"}[mode]
    prep = "to" if mode != "leftovers" else "on"
    return _finish(
        kitchen,
        _KINDS[mode],
        f"{verb} {name} {prep} {_where(kitchen, day, slot_id)}",
        steps,
        meal_id=target.id,
    )


def move_item(kitchen: Kitchen, item: MealItem, day: date, slot_id: int, mode: Mode) -> Change:
    """Move one thing from a meal to another date and slot, or copy it."""
    check_day(kitchen, day)
    find_slot(kitchen, slot_id)
    source = kitchen.db.get(Meal, item.meal_id)
    if source is None:  # pragma: no cover (the database keeps every item in a meal)
        raise not_found("That meal")
    _planned(source)
    if (source.day, source.slot_id) == (day, slot_id):
        raise Problem(status.HTTP_422_UNPROCESSABLE_CONTENT, "same_place", "That’s already there.")
    if mode != "move" and item.tub_id is not None:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "tub_once",
            "A tub can only be in one meal at a time.",  # proposed, for cabledrawer
        )
    if mode == "leftovers":
        check_after_cook(kitchen, source, day, slot_id)
    steps: list[dict[str, Any]] = []
    name = _item_name(kitchen, item)
    where_from = _where(kitchen, source.day, source.slot_id)
    target = meal_at(kitchen, day, slot_id)
    if target is None:
        target = _make_meal(kitchen, day, slot_id, steps)
    else:
        _planned(target)
        _room(kitchen, target)
    if mode == "move":
        _bring(kitchen, item, target, steps)
        if not items_of(kitchen, source):
            _drop_meal(kitchen, source, steps)
    elif mode == "leftovers":
        _leftovers_of(kitchen, item, source, target, steps)
    else:
        _copy_of(kitchen, item, target, steps)
    where_to = _where(kitchen, day, slot_id)
    summary = {
        "move": f"Moved {name} from {where_from} to {where_to}",
        "copy": f"Copied {name} to {where_to}",
        "leftovers": f"Planned leftovers of {name} on {where_to}",
    }[mode]
    return _finish(kitchen, _KINDS[mode], summary, steps, meal_id=target.id)


def set_slot(kitchen: Kitchen, slot: MealSlot, enabled: bool) -> Change | None:
    if slot.enabled == enabled:
        return None
    before = slot.enabled
    slot.enabled = enabled
    kitchen.db.flush()
    return _finish(
        kitchen,
        "plan_slot",
        f"{'Showed' if enabled else 'Hid'} {slot.name} in the plan",
        [{"op": "slot", "slot": slot.id, "enabled": before}],
    )


# --- Undo ----------------------------------------------------------------------------------------


def _own(kitchen: Kitchen, model: Any, row_id: int | None) -> Any:
    if row_id is None:
        return None
    row = kitchen.db.get(model, row_id)
    return row if row is not None and row.household_id == kitchen.household_id else None


def _open(kitchen: Kitchen, meal_id: int | None) -> Meal | None:
    """A meal of this household that is still `planned`. Undo, like a write, leaves cooked,
    skipped and moved meals alone (they are Today's, PR 6): such a step is skipped."""
    meal = _own(kitchen, Meal, meal_id)
    return meal if meal is not None and meal.status == "planned" else None


def _undo_step(
    kitchen: Kitchen, step: dict[str, Any], remap: dict[int, int], touched: set[int]
) -> bool:
    db = kitchen.db
    op = step["op"]
    if op == "add_item":
        item = _own(kitchen, MealItem, step["item"])
        if item is None or _open(kitchen, item.meal_id) is None:
            return False
        touched.add(item.meal_id)
        db.delete(item)
        db.flush()
        return True
    if op == "new_meal":
        meal = _open(kitchen, remap.get(step["meal"], step["meal"]))
        if meal is None or items_of(kitchen, meal):
            return False
        delete_meal(db, meal)
        return True
    if op == "del_meal":
        old = step["meal"]
        day = date.fromisoformat(old["day"])
        if _own(kitchen, MealSlot, old["slot_id"]) is None:
            return False
        meal = meal_at(kitchen, day, old["slot_id"])
        if meal is not None and meal.status != "planned":
            return False
        if meal is None:
            meal = Meal(
                household_id=kitchen.household_id,
                day=day,
                slot_id=old["slot_id"],
                status=old["status"],
            )
            db.add(meal)
            db.flush()
            for batch_id in step["batches"]:
                batch = _own(kitchen, BatchCook, batch_id)
                if batch is not None and batch.cook_meal_id is None:
                    batch.cook_meal_id = meal.id
        remap[old["id"]] = meal.id
        touched.add(meal.id)
        db.flush()
        return True
    if op == "del_item":
        old = step["item"]
        meal = _open(kitchen, remap.get(old["meal_id"], old["meal_id"]))
        if meal is None or len(items_of(kitchen, meal)) >= MOST_ITEMS_IN_MEAL:
            return False
        if old["recipe_id"] is not None and _own(kitchen, Recipe, old["recipe_id"]) is None:
            return False
        if old["food_id"] is not None and _own(kitchen, Food, old["food_id"]) is None:
            return False
        if old["tub_id"] is not None:
            tub = _own(kitchen, Tub, old["tub_id"])
            taken = db.scalar(select(MealItem.id).where(MealItem.tub_id == old["tub_id"]))
            if tub is None or taken is not None:
                return False
        db.add(
            MealItem(
                household_id=kitchen.household_id,
                meal_id=meal.id,
                position=old["position"],
                kind=old["kind"],
                name=old["name"],
                recipe_id=old["recipe_id"],
                tub_id=old["tub_id"],
                food_id=old["food_id"],
                servings=old["servings"],
            )
        )
        db.flush()
        return True
    if op == "move_meal":
        meal = _open(kitchen, step["meal"])
        day = date.fromisoformat(step["from"][0])
        if meal is None or meal_at(kitchen, day, step["from"][1]) is not None:
            return False
        if _own(kitchen, MealSlot, step["from"][1]) is None:
            return False
        meal.day, meal.slot_id = day, step["from"][1]
        db.flush()
        return True
    if op == "move_item":
        item = _own(kitchen, MealItem, step["item"])
        meal = _open(kitchen, remap.get(step["from_meal"], step["from_meal"]))
        if item is None or meal is None or len(items_of(kitchen, meal)) >= MOST_ITEMS_IN_MEAL:
            return False
        if _open(kitchen, item.meal_id) is None:
            return False  # the item now sits in a meal that has been dealt with
        touched.add(item.meal_id)
        item.meal_id, item.position = meal.id, step["position"]
        db.flush()
        return True
    if op == "status":
        # Today's answer (cooked, didn't, moved): the meal is asked about again, if it still
        # carries the answer this change gave it (PR 6).
        meal = _own(kitchen, Meal, step["meal"])
        if meal is None or meal.status != step["to"]:
            return False
        meal.status = step["from"]
        db.flush()
        return True
    if op == "slot":
        slot = _own(kitchen, MealSlot, step["slot"])
        if slot is None:
            return False
        slot.enabled = step["enabled"]
        db.flush()
        return True
    from mealwright import batches

    return batches.undo_step(kitchen, step, remap)


def undo(kitchen: Kitchen, change: Change) -> Change:
    """Put the plan back as the change found it, newest step first. Steps that no longer fit
    are skipped; the result then says "partly" or "nothing"."""
    steps = (change.undo_data or {}).get("plan", [])
    tally = Tally()
    remap: dict[int, int] = {}
    touched: set[int] = set()
    for step in reversed(steps):
        if _undo_step(kitchen, step, remap, touched):
            tally.done += 1
        else:
            tally.skipped += 1
    # A planned meal the Undo left with nothing in it goes (never a cooked one).
    for meal_id in touched:
        meal = _open(kitchen, meal_id)
        if meal is not None and not items_of(kitchen, meal):
            delete_meal(kitchen.db, meal)
    undone = record(
        kitchen,
        "undo",
        f"Undid: {change.summary}",
        None,
        {
            "result": tally.result,
            "message": UNDO_MESSAGES[tally.result],
            "undoes_kind": change.kind,
            "undoes_at": as_utc(change.at).isoformat(),
        },
    )
    undone.undoes_change_id = change.id
    change.undone_by_change_id = undone.id
    kitchen.db.flush()
    list_follows_plan(kitchen)
    return undone
