"""The meal plan, read only (0.6 PR 2; docs/dev/api-0.2.md section 6.7). Writing comes with
the Plan screens."""

from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query, status
from pydantic import BaseModel
from sqlalchemy import select

from mealwright.api.v1.context import Here
from mealwright.api.v1.schemas import Ref
from mealwright.auth import SameOrigin
from mealwright.errors import Problem
from mealwright.household import meal_slots
from mealwright.models import BatchCook, Food, Meal, MealItem, Recipe, Tub

router = APIRouter(tags=["plan"], dependencies=[SameOrigin])

# The longest range one call answers: two months covers the Month view with the days either
# side of it. Proposed, for cabledrawer.
MOST_DAYS = 62


class MealSlotOut(BaseModel):
    id: int
    name: str
    position: int
    enabled: bool


@router.get("/meal-slots")
def list_meal_slots(kitchen: Here) -> list[MealSlotOut]:
    """Breakfast, Lunch, Snack and Dinner (or the household's own), in order, hidden ones too."""
    return [
        MealSlotOut(id=s.id, name=s.name, position=s.position, enabled=s.enabled)
        for s in meal_slots(kitchen.db, kitchen.household_id)
    ]


class PlanRecipeRef(Ref):
    # Removed, but still inside the undo window.
    removed: bool


class PlanItemOut(BaseModel):
    id: int
    position: int
    kind: Literal["recipe", "tub", "ingredient"]
    recipe: PlanRecipeRef | None
    tub_id: int | None
    ingredient: Ref | None
    servings: int | None


class PlanMealOut(BaseModel):
    id: int
    date: date
    slot_id: int
    status: Literal["planned", "cooked", "didnt", "moved"]
    items: list[PlanItemOut]


class PlanBatchOut(BaseModel):
    id: int
    recipe_id: int | None
    recipe_name: str
    cooked_on: date
    tub_count: int
    pattern: Literal["lunches", "lunch_dinner", "dinners", "pick"]
    prep_note: str | None
    colour: str | None


class PlanTubOut(BaseModel):
    id: int
    batch_id: int
    amount_quarters: int
    place_id: int | None
    member_login_id: int | None
    use_by: date


class PlanOut(BaseModel):
    start: date
    end: date
    meals: list[PlanMealOut]
    batch_cooks: list[PlanBatchOut]
    tubs: list[PlanTubOut]


@router.get("/plan")
def get_plan(
    kitchen: Here,
    start: Annotated[date, Query(alias="from", description="First day, inclusive.")],
    end: Annotated[date, Query(alias="to", description="Last day, inclusive.")],
) -> PlanOut:
    """The meals from one day to another, with their items, and the batch cooks and tubs the
    meals use. At most 62 days at a time."""
    if end < start:
        raise Problem(status.HTTP_422_UNPROCESSABLE_CONTENT, "bad_range", "“to” is before “from”.")
    if end - start > timedelta(days=MOST_DAYS - 1):
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "range_too_long",
            f"Ask for at most {MOST_DAYS} days at a time.",
        )
    db, household_id = kitchen.db, kitchen.household_id
    meals = list(
        db.scalars(
            select(Meal)
            .where(Meal.household_id == household_id, Meal.day >= start, Meal.day <= end)
            .order_by(Meal.day, Meal.slot_id, Meal.id)
        )
    )
    items = list(
        db.scalars(
            select(MealItem)
            .where(
                MealItem.household_id == household_id,
                MealItem.meal_id.in_([m.id for m in meals]),
            )
            .order_by(MealItem.meal_id, MealItem.position, MealItem.id)
        )
    )
    recipe_ids = {i.recipe_id for i in items if i.recipe_id}
    food_ids = {i.food_id for i in items if i.food_id}
    tub_ids = {i.tub_id for i in items if i.tub_id}
    recipes = {
        r.id: r
        for r in db.scalars(
            select(Recipe).where(Recipe.household_id == household_id, Recipe.id.in_(recipe_ids))
        )
    }
    foods = {
        f.id: f
        for f in db.scalars(
            select(Food).where(Food.household_id == household_id, Food.id.in_(food_ids))
        )
    }
    tubs = list(
        db.scalars(
            select(Tub)
            .where(Tub.household_id == household_id, Tub.id.in_(tub_ids))
            .order_by(Tub.id)
        )
    )
    batches = list(
        db.scalars(
            select(BatchCook)
            .where(
                BatchCook.household_id == household_id,
                BatchCook.id.in_({t.batch_id for t in tubs}),
            )
            .order_by(BatchCook.id)
        )
    )

    def item_out(i: MealItem) -> PlanItemOut:
        recipe = recipes.get(i.recipe_id) if i.recipe_id else None
        food = foods.get(i.food_id) if i.food_id else None
        return PlanItemOut(
            id=i.id,
            position=i.position,
            kind="recipe" if i.recipe_id else "tub" if i.tub_id else "ingredient",
            recipe=PlanRecipeRef(
                id=recipe.id, name=recipe.name, removed=recipe.removed_at is not None
            )
            if recipe
            else None,
            tub_id=i.tub_id,
            ingredient=Ref(id=food.id, name=food.name) if food else None,
            servings=i.servings,
        )

    by_meal: dict[int, list[PlanItemOut]] = {}
    for i in items:
        by_meal.setdefault(i.meal_id, []).append(item_out(i))
    return PlanOut(
        start=start,
        end=end,
        meals=[
            PlanMealOut(
                id=m.id,
                date=m.day,
                slot_id=m.slot_id,
                status=m.status,  # type: ignore[arg-type]
                items=by_meal.get(m.id, []),
            )
            for m in meals
        ],
        batch_cooks=[
            PlanBatchOut(
                id=b.id,
                recipe_id=b.recipe_id,
                recipe_name=b.recipe_name,
                cooked_on=b.cooked_on,
                tub_count=b.tub_count,
                pattern=b.pattern,  # type: ignore[arg-type]
                prep_note=b.prep_note,
                colour=b.colour,
            )
            for b in batches
        ],
        tubs=[
            PlanTubOut(
                id=t.id,
                batch_id=t.batch_id,
                amount_quarters=t.amount_quarters,
                place_id=t.place_id,
                member_login_id=t.member_login_id,
                use_by=t.use_by,
            )
            for t in tubs
        ],
    )
