""" "Cooked it" takes the ingredients out of the pantry (0.7 K2; spec section 2, "Cooking — how
deduction works", points 5 and 7).

The review is the screen's (K3). Here are the two calls behind it: `preview_*` (the engine's
proposal, nothing changes) and `cook_*` (a confirmed set of choices): one change in Recent
changes (kind `cooked`) with a line for each packet touched, so one Undo puts it all back, and
the cooked record with the recipe as cooked and each row as it was confirmed (`cooked.py`).

- A meal item (one recipe in a meal) and a batch cook each have their own record. A second
  confirm for either is refused, never doubled (the record is unique). The item that a batch
  cook was made from is cooked through the batch (rule 7: ingredients are taken once, on the cook
  day; the tubs were made when the batch was planned, and eating a tub uses the tub).
- Undo reverses the packets (the ordinary Undo of a change) and takes the record away, so the
  item or batch can be cooked again (`forget_record`).
- This does not change the meal's status or make leftover tubs: that is Today's answer, which the
  screen calls too (K3).

Proposed, for cabledrawer (one rule each): a batch cook is worked out for the cook-day eaters plus a
portion for each tub, as Cook once and the shopping list do (F58); a meal that is `cooked` already
(answered on Today before this existed) can still be given its record, one that was skipped or
moved can't.
"""

from typing import Any

from fastapi import status
from sqlalchemy import select

from mealwright import cooked, plan
from mealwright.api.v1.context import Kitchen
from mealwright.api.v1.schemas import Answer
from mealwright.deduction import Choice, Row, Worked, work_out
from mealwright.errors import Problem, not_found
from mealwright.foods import remember_answers
from mealwright.history import as_utc
from mealwright.household import today
from mealwright.models import BatchCook, Change, CookedRecord, Meal, MealItem, Recipe
from mealwright.stock import StockEdit

MOST_PORTIONS = 999


def _already(kitchen: Kitchen, record: CookedRecord) -> Problem:
    day = today(kitchen.household, as_utc(record.cooked_at))
    return Problem(
        status.HTTP_409_CONFLICT,
        "already_cooked",
        f"This was already cooked on {day:%a} {day.day} {day:%b}. Undo “Cooked it” first.",
    )  # proposed, for cabledrawer


def _recipe(kitchen: Kitchen, recipe_id: int | None) -> Recipe:
    recipe = kitchen.db.get(Recipe, recipe_id) if recipe_id is not None else None
    if recipe is None or recipe.household_id != kitchen.household_id or recipe.removed_at:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "not_a_recipe",
            "Only a recipe that is still there can be cooked.",  # proposed, for cabledrawer
        )
    return recipe


def _item_checked(kitchen: Kitchen, item: MealItem) -> tuple[Recipe, Meal]:
    """The recipe of a meal item that can be cooked now."""
    meal = kitchen.db.get(Meal, item.meal_id)
    if meal is None:  # pragma: no cover (the database keeps every item in a meal)
        raise not_found("That meal")
    if meal.status != "cooked":
        plan._planned(meal)  # skipped and moved meals are locked
    recipe = _recipe(kitchen, item.recipe_id) if item.kind == "recipe" else None
    if recipe is None:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "not_a_recipe",
            "Only a recipe that is still there can be cooked.",
        )
    record = cooked.for_meal_item(kitchen.db, kitchen.household_id, item.id)
    if record is not None:
        raise _already(kitchen, record)
    if _batch_of_item(kitchen, item) is not None:
        raise Problem(
            status.HTTP_409_CONFLICT,
            "cook_the_batch",
            "This meal is cooked once for several. Cook the batch instead.",  # proposed
        )
    return recipe, meal


def _batch_of_item(kitchen: Kitchen, item: MealItem) -> BatchCook | None:
    return kitchen.db.scalar(
        select(BatchCook).where(
            BatchCook.household_id == kitchen.household_id,
            BatchCook.cook_meal_id == item.meal_id,
            BatchCook.recipe_id == item.recipe_id,
        )
    )


def _batch_checked(kitchen: Kitchen, batch: BatchCook) -> Recipe:
    recipe = _recipe(kitchen, batch.recipe_id)
    record = cooked.for_batch(kitchen.db, kitchen.household_id, batch.id)
    if record is not None:
        raise _already(kitchen, record)
    return recipe


def item_portions(item: MealItem, recipe: Recipe) -> int:
    return item.servings or recipe.serves or 1


def batch_portions(kitchen: Kitchen, batch: BatchCook, recipe: Recipe) -> int:
    """The cook-day eaters (the meal's servings, else one) plus a portion for each tub."""
    item = kitchen.db.scalar(
        select(MealItem).where(
            MealItem.household_id == kitchen.household_id,
            MealItem.meal_id == batch.cook_meal_id,
            MealItem.recipe_id == recipe.id,
        )
    )
    eaters = (item.servings if item else None) or 1
    return min(eaters + batch.tub_count, MOST_PORTIONS)


# --- The proposal, nothing changes --------------------------------------------------------------


def preview_item(
    kitchen: Kitchen, item: MealItem, portions: int | None, answers: list[Answer]
) -> Worked:
    recipe, _ = _item_checked(kitchen, item)
    return work_out(kitchen, recipe, portions or item_portions(item, recipe), answers)


def preview_batch(
    kitchen: Kitchen, batch: BatchCook, portions: int | None, answers: list[Answer]
) -> Worked:
    recipe = _batch_checked(kitchen, batch)
    return work_out(kitchen, recipe, portions or batch_portions(kitchen, batch, recipe), answers)


# --- Confirming -----------------------------------------------------------------------------------


def cook_item(
    kitchen: Kitchen,
    item: MealItem,
    portions: int | None,
    answers: list[Answer],
    choices: dict[str, Choice],
) -> Change:
    recipe, _ = _item_checked(kitchen, item)
    return _confirm(
        kitchen,
        recipe,
        portions or item_portions(item, recipe),
        answers,
        choices,
        {"meal_item_id": item.id, "meal_id": item.meal_id, "item_id": item.id},
    )


def cook_batch(
    kitchen: Kitchen,
    batch: BatchCook,
    portions: int | None,
    answers: list[Answer],
    choices: dict[str, Choice],
) -> Change:
    recipe = _batch_checked(kitchen, batch)
    return _confirm(
        kitchen,
        recipe,
        portions or batch_portions(kitchen, batch, recipe),
        answers,
        choices,
        {"batch_id": batch.id},
    )


def choices_of(worked: Worked) -> list[cooked.SnapshotChoice]:
    return [_choice_of(row) for row in worked.rows]


def _choice_of(row: Row) -> cooked.SnapshotChoice:
    return cooked.SnapshotChoice(
        key=row.key,
        status=row.status,
        line_ids=[line.id for line in row.lines],
        food_id=row.food.id if row.food else None,
        food_name=row.food.name if row.food else None,
        recipe_id=row.inner.id if row.inner else None,
        recipe_name=row.inner.name if row.inner else None,
        use=row.use if row.food is not None and row.status != "staple" else False,
        needed_milli=row.needed,
        entered=row.entered,
        entered_milli=row.entered_milli,
        from_freezer=row.from_freezer,
        used_milli=row.taken,
        short_milli=row.short,
        takes=[
            cooked.SnapshotTake(
                food_id=take.food.id,
                food_name=take.food.name,
                stand_in=take.stand_in,
                amount_milli=take.amount,
            )
            for take in row.takes
        ],
    )


def _summary(recipe: Recipe, portions: int) -> str:
    return f"Cooked {recipe.name} ({portions} {'portion' if portions == 1 else 'portions'})"


def _confirm(
    kitchen: Kitchen,
    recipe: Recipe,
    portions: int,
    answers: list[Answer],
    choices: dict[str, Choice],
    link: dict[str, int],
) -> Change:
    """Take what the choices say from the packets, in one change, and write the record."""
    worked = work_out(kitchen, recipe, portions, answers, choices)
    remember_answers(kitchen, answers)
    edit = StockEdit(kitchen)
    for row in worked.rows:
        for take in row.takes:
            for lot, amount in take.lots:
                edit.touch(lot).amount_milli -= amount
    change = edit.record("cooked", _summary(recipe, portions), None)
    snapshot = cooked.snapshot(kitchen.db, recipe)
    snapshot.choices = choices_of(worked)
    record = CookedRecord(
        household_id=kitchen.household_id,
        meal_item_id=link.get("meal_item_id"),
        batch_id=link.get("batch_id"),
        recipe_id=recipe.id,
        portions=portions,
        snapshot=cooked.stored(snapshot),
        change_id=change.id,
        cooked_by_login_id=kitchen.login.id,
        cooked_by_name=kitchen.login.name,
    )
    kitchen.db.add(record)
    kitchen.db.flush()
    data: dict[str, Any] = {"cooked_record_id": record.id, **link}
    change.undo_data = data
    kitchen.db.flush()
    return change


def forget_record(kitchen: Kitchen, change: Change) -> None:
    """Undo of "Cooked it": the record goes, so the item or batch can be cooked again."""
    for record in kitchen.db.scalars(
        select(CookedRecord).where(
            CookedRecord.household_id == kitchen.household_id, CookedRecord.change_id == change.id
        )
    ):
        kitchen.db.delete(record)
    kitchen.db.flush()
