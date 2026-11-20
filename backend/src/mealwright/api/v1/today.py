"""Today (docs/dev/api-endpoints.md section 6.3c, 0.6 PR 6): what we're eating, the tubs left, what to
use soon, the next cook, and the meals nobody has answered yet ("Did you cook Sambar?" →
Cooked it · Didn't · Move it). Online only, like the Plan."""

from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, exists, select

from mealwright import plan, start_ahead
from mealwright import today as answers
from mealwright.api.v1.batches import PersonOut, TubLeftOut, get_tubs_left, list_people
from mealwright.api.v1.context import Here
from mealwright.api.v1.mealie import MealieNote, today_note
from mealwright.api.v1.pantry import UseSoonLot, UseSoonTub, use_soon
from mealwright.api.v1.plan import ItemStartIn, MealSlotOut, PlanOut, PlanWrite, _run, get_plan
from mealwright.auth import SameOrigin
from mealwright.batches import tub_use_by
from mealwright.errors import StoredInt
from mealwright.household import meal_slots
from mealwright.household import today as household_today
from mealwright.models import BatchCook, Meal, MealItem, Recipe, StockLot
from mealwright.plan import cooked_record_of

router = APIRouter(tags=["today"], dependencies=[SameOrigin])

Day = date  # for a model with a field called "date" (mypy reads later "date" as that field)


class WaitingOut(BaseModel):
    """A planned meal whose day has come, waiting for Cooked it, Didn't or Move it."""

    meal_id: int
    date: Day
    slot_id: int
    # The recipe "Any left over?" is about (the meal's first recipe), or null: the meal has no
    # recipe, so the sheet doesn't ask.
    leftover_item_id: int | None
    # The use-by a tub would get (the household's tub life from the meal's day).
    use_by_fridge: Day
    use_by_freezer: Day


class NextCookOut(BaseModel):
    date: Day
    slot_id: int
    meal_id: int
    batch_id: int
    recipe_name: str
    tub_count: int


class TodayOut(BaseModel):
    today: date
    # Nothing here yet: no recipes, no ingredients in the pantry, nothing ever planned.
    first_day: bool
    slots: list[MealSlotOut]  # the meals that are on, in order
    # The meals from WAITING_DAYS ago to the end of the week ahead, with their items, and the
    # batch cooks and tubs they use.
    plan: PlanOut
    people: list[PersonOut]
    waiting: list[WaitingOut]  # newest first
    tubs_left: list[TubLeftOut]
    tubs_left_more: bool
    use_soon_lots: list[UseSoonLot]  # packets, soonest first
    # One row per batch and place, the way the Pantry counts them (F203): the batch's tubs in
    # that place when its soonest is within the Use soon days (or passed).
    use_soon_tubs: list[UseSoonTub]
    next_cook: NextCookOut | None
    # An import from Mealie that finished in the last day (0.9.5; proposed, for cabledrawer).
    mealie: MealieNote | None = None


@router.get("/today")
def get_today(kitchen: Here) -> TodayOut:
    """Everything Today shows, in the household's own day."""
    db, hid, household = kitchen.db, kitchen.household_id, kitchen.household
    first = household_today(household)
    slots = [s for s in meal_slots(db, hid) if s.enabled]
    plan_out = get_plan(
        kitchen,
        start=first - timedelta(days=answers.WAITING_DAYS),
        # As far on as a start can reach, so a long wait (up to ten days) is found on the day
        # it is to be started (RF3, H6; the Plan reads the same number of days past its edge).
        end=first + timedelta(days=max(answers.DAYS_SHOWN_AHEAD - 1, start_ahead.MOST_DAYS_AHEAD)),
    )
    left = get_tubs_left(kitchen, limit=200)
    lots = use_soon(kitchen)
    waiting = []
    for meal in answers.waiting_meals(kitchen):
        recipes = list(
            db.scalars(
                select(MealItem)
                .where(
                    MealItem.household_id == hid,
                    MealItem.meal_id == meal.id,
                    MealItem.kind == "recipe",
                )
                .order_by(MealItem.position, MealItem.id)
            )
        )
        # The first recipe not cooked yet: a part-cooked meal's leftovers are not an
        # already-cooked recipe's (F157 review).
        recipe = next(
            (r for r in recipes if cooked_record_of(kitchen, r, meal) is None),
            recipes[0] if recipes else None,
        )
        waiting.append(
            WaitingOut(
                meal_id=meal.id,
                date=meal.day,
                slot_id=meal.slot_id,
                leftover_item_id=recipe.id if recipe else None,
                use_by_fridge=tub_use_by(kitchen, "fridge", answers.cooking_day(kitchen, meal)),
                use_by_freezer=tub_use_by(kitchen, "freezer", answers.cooking_day(kitchen, meal)),
            )
        )
    cook = db.execute(
        select(BatchCook, Meal)
        .join(
            Meal,
            and_(Meal.household_id == BatchCook.household_id, Meal.id == BatchCook.cook_meal_id),
        )
        .where(
            BatchCook.household_id == hid,
            BatchCook.cooked_on >= first,
            Meal.status == "planned",
        )
        .order_by(BatchCook.cooked_on, Meal.slot_id, BatchCook.id)
        .limit(1)
    ).first()
    has_recipes = db.scalar(
        select(exists().where(Recipe.household_id == hid, Recipe.removed_at.is_(None)))
    )
    has_stock = db.scalar(select(exists().where(StockLot.household_id == hid)))
    has_meals = db.scalar(select(exists().where(Meal.household_id == hid)))
    next_cook = None
    if cook:
        batch, cook_meal = cook
        next_cook = NextCookOut(
            date=batch.cooked_on,
            slot_id=cook_meal.slot_id,
            meal_id=cook_meal.id,
            batch_id=batch.id,
            recipe_name=batch.recipe_name,
            tub_count=batch.tub_count,
        )
    return TodayOut(
        today=first,
        first_day=not (has_recipes or has_stock or has_meals),
        slots=[MealSlotOut(id=s.id, name=s.name, position=s.position, enabled=True) for s in slots],
        plan=plan_out,
        people=list_people(kitchen),
        waiting=waiting,
        tubs_left=left.tubs,
        tubs_left_more=left.more,
        use_soon_lots=lots.lots,
        use_soon_tubs=lots.tubs,
        next_cook=next_cook,
        mealie=today_note(kitchen),
    )


# --- Answering a meal -------------------------------------------------------------------------


class LeftoversIn(BaseModel):
    count: Annotated[int, Field(ge=1, le=answers.MOST_LEFTOVER_TUBS)]
    place_kind: Literal["fridge", "freezer"] = "fridge"
    use_by: date | None = Field(
        default=None, description="Left out: the household's tub life from the meal's day."
    )
    item_id: StoredInt | None = Field(
        default=None, description="The recipe in the meal. Left out: its first recipe."
    )


class CookedIn(BaseModel):
    leftovers: LeftoversIn | None = Field(
        default=None, description="“Any left over?”: tubs, in the fridge or the freezer."
    )


class MovedIn(BaseModel):
    date: date
    slot_id: StoredInt
    starts: list[ItemStartIn] = Field(
        default_factory=list,
        max_length=50,
        description="the new start time of each recipe in the meal with a long wait, by"
        " `item_id`, asked again for the new day, as when a planned meal is moved. A recipe left"
        " out has no time yet. Same refusals as planning it (`422 bad_start`, `no_wait`,"
        " `not_a_recipe`); `422 start_not_moved` for an item not in the meal; an item named"
        " twice is refused (422).",
    )

    @field_validator("starts")
    @classmethod
    def _one_start_each(cls, starts: list[ItemStartIn]) -> list[ItemStartIn]:
        if len({s.item_id for s in starts}) != len(starts):
            raise ValueError("One start time for each recipe.")  # accepted, cabledrawer 11 Nov
        return starts


@router.post("/plan/meals/{plan_meal_id}/cooked")
def cooked_it(
    plan_meal_id: StoredInt, body: CookedIn, kitchen: Here, response: Response
) -> PlanWrite:
    """“Cooked it”: the meal is done and locked. Optional leftovers make tubs. Nothing is taken
    from the pantry (that is the “Cooked it” review, 0.7). Undo asks about the meal again."""
    leftovers = (
        answers.Leftovers(
            count=body.leftovers.count,
            place_kind=body.leftovers.place_kind,
            use_by=body.leftovers.use_by,
            item_id=body.leftovers.item_id,
        )
        if body.leftovers
        else None
    )
    return _run(
        kitchen,
        response,
        lambda: answers.cooked(kitchen, plan.find_meal(kitchen, plan_meal_id), leftovers),
    )


@router.post("/plan/meals/{plan_meal_id}/didnt")
def didnt_cook(plan_meal_id: StoredInt, kitchen: Here, response: Response) -> PlanWrite:
    """“Didn't”: the meal was not cooked. Nothing is taken from the pantry, and the meal's
    ingredients leave the shopping list."""
    return _run(
        kitchen,
        response,
        lambda: answers.didnt(kitchen, plan.find_meal(kitchen, plan_meal_id)),
    )


@router.post("/plan/meals/{plan_meal_id}/moved")
def move_it(plan_meal_id: StoredInt, body: MovedIn, kitchen: Here, response: Response) -> PlanWrite:
    """“Move it”: to a day and a meal. The old meal is marked moved and keeps its place; a
    meal that already has food gets it alongside. `meal_id` is the meal it went to."""
    return _run(
        kitchen,
        response,
        lambda: answers.moved(
            kitchen,
            plan.find_meal(kitchen, plan_meal_id),
            body.date,
            body.slot_id,
            {s.item_id: s.at() for s in body.starts} or None,
        ),
    )
