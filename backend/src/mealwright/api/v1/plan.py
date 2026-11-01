"""The meal plan (docs/dev/api-0.2.md section 6.3a): read in 0.6 PR 2, written in PR 3
(planning, moving, copying, removing, switching a meal on or off), each write with its Undo.
Online only, like the Pantry."""

from collections.abc import Callable
from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import and_, or_, select

from mealwright import batches as batch_service
from mealwright import plan
from mealwright import recipes as recipe_service
from mealwright.api.v1.context import Here, Kitchen
from mealwright.api.v1.schemas import ChangeOut, Ref
from mealwright.auth import SameOrigin
from mealwright.errors import Problem, StoredInt, not_found
from mealwright.foods import change_out
from mealwright.history import commit, replayed
from mealwright.household import meal_slots
from mealwright.models import (
    BatchCook,
    Change,
    Food,
    Login,
    Meal,
    MealEater,
    MealItem,
    MealSlot,
    Place,
    Recipe,
    RecipePhoto,
    Tub,
)
from mealwright.names import clean, one_line
from mealwright.shopping import lock_household

router = APIRouter(tags=["plan"], dependencies=[SameOrigin])

# The longest range one call answers: two months covers the Month view with the days either
# side of it (cabledrawer 26 Oct).
MOST_DAYS = 62
# The longest note ('Eating out'): the column holds 200.
MOST_NOTE = 200


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
    # What a meal card shows (PR 3): the small photo, the time, and kcal per serving.
    photo_url: str | None = None
    time_minutes: int | None = None
    kcal: int | None = None
    # The recipe's own default servings (F116); null when it has none.
    serves: int | None = None


class PlanIngredientRef(Ref):
    # Removed, but still inside the undo window.
    removed: bool


class PlanItemOut(BaseModel):
    id: int
    position: int
    kind: Literal["recipe", "tub", "ingredient", "note"]
    recipe: PlanRecipeRef | None
    tub_id: int | None
    ingredient: PlanIngredientRef | None
    # Set only when the recipe or ingredient was deleted for good (recipe and ingredient are
    # then null): its name, so past meals still show what was eaten.
    kept_name: str | None
    servings: int | None
    # A note's text ("Eating out"); null for everything else.
    note: str | None = None
    # Serves - N +: how many people this recipe is for now. Its own `servings` once set; else the
    # recipe's Serves (a meal planned before 0.7 has none set), or one for the cook meal of a
    # batch (how Cook once and the list count it); null for anything but a recipe, and for a
    # recipe with no Serves.
    eating: int | None = None


class PlanMealOut(BaseModel):
    id: int
    date: date
    slot_id: int
    status: Literal["planned", "cooked", "didnt", "moved"]
    items: list[PlanItemOut]
    # One serving of each recipe and tub added up; null when none of them has kcal (PR 3;
    # cabledrawer 26 Oct).
    kcal: int | None = None
    # Who is eating (0.7 P1): the logins ticked, by sign-in until member profiles (0.8). Empty:
    # everyone.
    eater_login_ids: list[int] = Field(default_factory=list)


class PlanBatchOut(BaseModel):
    id: int
    recipe_id: int | None
    recipe_name: str
    cook_meal_id: int | None
    cooked_on: date
    tub_count: int
    pattern: Literal["lunches", "lunch_dinner", "dinners", "pick"]
    prep_note: str | None
    colour: str | None
    # Portions (0.7): the tubs plus the cook-day meal, and how many of them are not planned yet.
    portions: int
    portions_left: int


class PlanTubOut(BaseModel):
    id: int
    batch_id: int
    amount_quarters: int
    number: int  # "tub 2 of 4": 2 (its place among its batch's tubs, in date order)
    place_id: int | None
    # Fridge, freezer or cupboard, for the place above (null: no place, or not the household's).
    place_kind: Literal["fridge", "freezer", "cupboard"] | None = None
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
    """The meals from one day to another, with their items, and the batch cooks and tubs they
    use: tubs in those meals, batches cooked for those meals or on those days, and the tubs
    of those batches. At most 62 days at a time."""
    if end < start:
        # Error texts: proposed, for cabledrawer.
        raise Problem(status.HTTP_422_UNPROCESSABLE_CONTENT, "bad_range", "“to” is before “from”.")
    if end - start > timedelta(days=MOST_DAYS - 1):
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "range_too_long",
            f"Ask for at most {MOST_DAYS} days at a time.",  # proposed, for cabledrawer
        )
    db, household_id = kitchen.db, kitchen.household_id
    in_range = (Meal.household_id == household_id, Meal.day >= start, Meal.day <= end)
    meals = list(
        db.scalars(select(Meal).where(*in_range).order_by(Meal.day, Meal.slot_id, Meal.id))
    )
    items = list(
        db.scalars(
            select(MealItem)
            .where(
                MealItem.household_id == household_id,
                MealItem.meal_id.in_(select(Meal.id).where(*in_range)),
            )
            .order_by(MealItem.meal_id, MealItem.position, MealItem.id)
        )
    )
    # The ids the meals link to, as subqueries too (a list of them, used more than once, could
    # push a query over SQLite's 32,766 values).
    in_meals = (
        MealItem.household_id == household_id,
        MealItem.meal_id.in_(select(Meal.id).where(*in_range)),
    )
    recipe_ids = select(MealItem.recipe_id).where(*in_meals, MealItem.recipe_id.is_not(None))
    food_ids = select(MealItem.food_id).where(*in_meals, MealItem.food_id.is_not(None))
    tub_ids = select(MealItem.tub_id).where(*in_meals, MealItem.tub_id.is_not(None))
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
    # Which batches matter, as a subquery (never a list of ids, so the number of batches and tubs
    # can't push a query over SQLite's 32,766 values; see batches.MOST_TUBS_IN_BATCH).
    batch_ids = select(BatchCook.id).where(
        BatchCook.household_id == household_id,
        or_(
            BatchCook.id.in_(
                select(Tub.batch_id).where(Tub.household_id == household_id, Tub.id.in_(tub_ids))
            ),
            BatchCook.cook_meal_id.in_(select(Meal.id).where(*in_range)),
            and_(BatchCook.cooked_on >= start, BatchCook.cooked_on <= end),
        ),
    )
    batches = list(
        db.scalars(
            select(BatchCook)
            .where(BatchCook.household_id == household_id, BatchCook.id.in_(batch_ids))
            .order_by(BatchCook.id)
        )
    )
    tubs = list(
        db.scalars(
            select(Tub)
            .where(
                Tub.household_id == household_id,
                or_(Tub.id.in_(tub_ids), Tub.batch_id.in_(batch_ids)),
            )
            .order_by(Tub.id)
        )
    )
    # Links to rows outside the household are never shown (they can't be made through the
    # API, and the database doesn't stop a plain key reaching across).
    mine_recipes = set(
        db.scalars(
            select(Recipe.id).where(
                Recipe.household_id == household_id,
                Recipe.id.in_(
                    select(BatchCook.recipe_id).where(
                        BatchCook.household_id == household_id, BatchCook.id.in_(batch_ids)
                    )
                ),
            )
        )
    )
    mine_places = {
        p.id: p.kind
        for p in db.scalars(
            select(Place).where(
                Place.household_id == household_id,
                Place.id.in_(
                    select(Tub.place_id).where(
                        Tub.household_id == household_id,
                        or_(Tub.id.in_(tub_ids), Tub.batch_id.in_(batch_ids)),
                    )
                ),
            )
        )
    }
    mine_logins = set(
        db.scalars(
            select(Login.id).where(
                Login.household_id == household_id,
                Login.id.in_(
                    select(Tub.member_login_id).where(
                        Tub.household_id == household_id,
                        or_(Tub.id.in_(tub_ids), Tub.batch_id.in_(batch_ids)),
                    )
                ),
            )
        )
    )

    photos = {
        p.recipe_id: p
        for p in db.scalars(select(RecipePhoto).where(RecipePhoto.recipe_id.in_(recipe_ids)))
    }
    # A batch cook's recipe, for the kcal of its tubs.
    batch_recipes = {
        r.id: r
        for r in db.scalars(select(Recipe).where(Recipe.id.in_(mine_recipes)))
        if r.household_id == household_id
    }
    batch_recipe = {b.id: batch_recipes.get(b.recipe_id or 0) for b in batches}
    tub_batch = {t.id: t.batch_id for t in tubs}
    # Every tub of a listed batch is in `tubs`. "Tub 2 of 4" is its place in date order (F50,
    # cabledrawer 28 Oct): tubs in meals by the meal's day and slot, then tubs left in the order made.
    when: dict[int, tuple[date, int, int]] = {}
    for tub_id, tub_day, position, slot_id in db.execute(
        select(MealItem.tub_id, Meal.day, MealSlot.position, MealSlot.id)
        .join(Meal, and_(Meal.household_id == MealItem.household_id, Meal.id == MealItem.meal_id))
        .join(
            MealSlot, and_(MealSlot.household_id == Meal.household_id, MealSlot.id == Meal.slot_id)
        )
        .where(
            MealItem.household_id == household_id,
            MealItem.tub_id.in_(
                select(Tub.id).where(
                    Tub.household_id == household_id,
                    or_(Tub.id.in_(tub_ids), Tub.batch_id.in_(batch_ids)),
                )
            ),
        )
    ):
        if tub_id is not None:
            when[tub_id] = (tub_day, position, slot_id)
    number: dict[int, int] = {}
    seen: dict[int, int] = {}
    for tub in sorted(
        tubs, key=lambda t: (t.id not in when, when.get(t.id, (date.min, 0, 0)), t.id)
    ):
        seen[tub.batch_id] = seen.get(tub.batch_id, 0) + 1
        number[tub.id] = seen[tub.batch_id]

    def kcal_of(recipe: Recipe | None) -> int | None:
        return round(recipe.kcal_milli / 1000) if recipe and recipe.kcal_milli is not None else None

    def item_kcal(i: MealItem) -> int | None:
        if i.recipe_id and i.recipe_id in recipes:
            return kcal_of(recipes[i.recipe_id])
        if i.tub_id and i.tub_id in tub_batch:
            return kcal_of(batch_recipe.get(tub_batch[i.tub_id]))
        return None

    cook_meals = {(b.cook_meal_id, b.recipe_id) for b in batches if b.cook_meal_id is not None}

    def eating_of(i: MealItem, recipe: Recipe | None) -> int | None:
        if i.kind != "recipe":
            return None
        if i.servings is not None:
            return i.servings
        if (i.meal_id, i.recipe_id) in cook_meals:
            return 1
        return recipe.serves if recipe else None

    def item_out(i: MealItem) -> PlanItemOut:
        recipe = recipes.get(i.recipe_id) if i.recipe_id else None
        food = foods.get(i.food_id) if i.food_id else None
        return PlanItemOut(
            id=i.id,
            position=i.position,
            kind=i.kind,  # type: ignore[arg-type]
            recipe=PlanRecipeRef(
                id=recipe.id,
                name=recipe.name,
                removed=recipe.removed_at is not None,
                photo_url=f"/api/v1/recipes/photos/{photos[recipe.id].id}/list"
                if recipe.id in photos
                else None,
                time_minutes=recipe.time_minutes,
                kcal=kcal_of(recipe),
                serves=recipe.serves,
            )
            if recipe
            else None,
            tub_id=i.tub_id,
            ingredient=PlanIngredientRef(
                id=food.id, name=food.name, removed=food.removed_at is not None
            )
            if food
            else None,
            kept_name=i.name
            if i.kind not in ("tub", "note") and not (i.recipe_id or i.food_id)
            else None,
            servings=i.servings,
            note=i.name if i.kind == "note" else None,
            eating=eating_of(i, recipe),
        )

    by_meal: dict[int, list[PlanItemOut]] = {}
    kcal_by_meal: dict[int, int] = {}
    portions = batch_service.portions_by_batch(kitchen, batches)
    eaters: dict[int, list[int]] = {}
    for meal_id, login_id in db.execute(
        select(MealEater.meal_id, MealEater.login_id)
        .join(Login, Login.id == MealEater.login_id)
        .where(
            MealEater.household_id == household_id,
            Login.household_id == household_id,
            MealEater.meal_id.in_(select(Meal.id).where(*in_range)),
        )
        .order_by(MealEater.login_id)
    ):
        eaters.setdefault(meal_id, []).append(login_id)
    for i in items:
        by_meal.setdefault(i.meal_id, []).append(item_out(i))
        kcal = item_kcal(i)
        if kcal is not None:
            kcal_by_meal[i.meal_id] = kcal_by_meal.get(i.meal_id, 0) + kcal
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
                kcal=kcal_by_meal.get(m.id),
                eater_login_ids=eaters.get(m.id, []),
            )
            for m in meals
        ],
        batch_cooks=[
            PlanBatchOut(
                id=b.id,
                recipe_id=b.recipe_id if b.recipe_id in mine_recipes else None,
                cook_meal_id=b.cook_meal_id,
                recipe_name=b.recipe_name,
                cooked_on=b.cooked_on,
                tub_count=b.tub_count,
                pattern=b.pattern,  # type: ignore[arg-type]
                prep_note=b.prep_note,
                colour=b.colour,
                portions=portions[b.id].total,
                portions_left=portions[b.id].left,
            )
            for b in batches
        ],
        tubs=[
            PlanTubOut(
                id=t.id,
                batch_id=t.batch_id,
                amount_quarters=t.amount_quarters,
                number=number.get(t.id, 1),
                place_id=t.place_id if t.place_id in mine_places else None,
                place_kind=mine_places.get(t.place_id) if t.place_id else None,  # type: ignore[arg-type]
                member_login_id=t.member_login_id if t.member_login_id in mine_logins else None,
                use_by=t.use_by,
            )
            for t in tubs
        ],
    )


# --- Writing the plan (PR 3) -----------------------------------------------------------------


class PlanWrite(BaseModel):
    """What a plan write answers: the change (it carries the Undo) and the meal it ended in.
    Read the plan again to draw it."""

    change: ChangeOut | None  # null when nothing needed changing (a switch already that way)
    meal_id: int | None = None
    item_id: int | None = None
    # Cook once (PR 4): the batch cook that was made.
    batch_id: int | None = None


def _written(kitchen: Kitchen, change: Change | None) -> PlanWrite:
    if change is None:
        return PlanWrite(change=None)
    data = change.undo_data or {}
    return PlanWrite(
        change=change_out(kitchen, change),
        meal_id=data.get("meal_id"),
        item_id=data.get("item_id"),
        batch_id=data.get("batch_id"),
    )


def _run(kitchen: Kitchen, response: Response, make: Callable[[], Change | None]) -> PlanWrite:
    """The shared shape of a write: the household's lock, a retry with the same
    Idempotency-Key answers from the first change, and the commit."""
    lock_household(kitchen)
    earlier = replayed(kitchen)
    if earlier is None:
        change = make()
        earlier = commit(kitchen)
        if earlier is None:
            return _written(kitchen, change)
    response.headers["Idempotent-Replayed"] = "true"
    return _written(kitchen, earlier)


class PlanItemIn(BaseModel):
    date: date
    slot_id: StoredInt
    # Exactly one of these three.
    recipe_id: StoredInt | None = None
    ingredient_id: StoredInt | None = None
    note: str | None = Field(
        default=None,
        description="A note instead of a recipe or ingredient: 'Eating out', 'Takeaway', 'At"
        " Amma's' (1 to 200 letters, one line). It counts as a filled meal and needs nothing"
        " bought.",
    )
    servings: Annotated[int, Field(ge=1, le=99)] | None = Field(
        default=None, description="Recipes only. Left out: the recipe's own Serves."
    )

    @field_validator("note")
    @classmethod
    def _checked_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = clean(one_line(value))
        if not 1 <= len(text) <= MOST_NOTE:
            raise ValueError(f"A note is 1 to {MOST_NOTE} letters.")  # proposed, for cabledrawer
        return text


@router.post("/plan/items", status_code=status.HTTP_201_CREATED)
def add_plan_item(body: PlanItemIn, kitchen: Here, response: Response) -> PlanWrite:
    """Plan a recipe or a plain ingredient on a date and slot. An empty slot gets a new meal;
    a filled one gets it alongside (at most 20 things in a meal). A retry with the same
    `Idempotency-Key` plans nothing more."""
    if sum(x is not None for x in (body.recipe_id, body.ingredient_id, body.note)) != 1:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "one_of",
            "Pick a recipe, an ingredient or a note to plan.",  # proposed, for cabledrawer
        )

    def make() -> Change:
        recipe = recipe_service.find(kitchen, body.recipe_id) if body.recipe_id else None
        food = None
        if body.ingredient_id is not None:
            food = kitchen.db.get(Food, body.ingredient_id)
            if (
                food is None
                or food.household_id != kitchen.household_id
                or food.removed_at is not None
                or food.merged_into_id is not None
            ):
                raise not_found("That ingredient")
        return plan.add_item(
            kitchen, body.date, body.slot_id, recipe, food, body.servings, body.note
        )

    out = _run(kitchen, response, make)
    if response.headers.get("Idempotent-Replayed"):
        response.status_code = status.HTTP_200_OK
    return out


class ServingsIn(BaseModel):
    servings: Annotated[int, Field(ge=1, le=99)]


@router.patch("/plan/items/{plan_item_id}")
def set_plan_item_servings(
    plan_item_id: StoredInt, body: ServingsIn, kitchen: Here, response: Response
) -> PlanWrite:
    """Serves - N +: how many people a planned recipe is for. Amounts and the shopping list
    follow. Already that number → `change: null`. Works on meals planned before 0.7 (no number
    set) too. Only a recipe (`422 not_a_recipe`) in a planned meal (`409 meal_done`)."""
    return _run(
        kitchen,
        response,
        lambda: plan.set_servings(kitchen, plan.find_item(kitchen, plan_item_id), body.servings),
    )


class EatersIn(BaseModel):
    login_ids: Annotated[list[StoredInt], Field(max_length=20)] = Field(
        description="Who is eating, by sign-in (proposed; member profiles come in"
        " 0.8). Empty: everyone."
    )


@router.put("/plan/meals/{plan_meal_id}/eaters")
def set_plan_meal_eaters(
    plan_meal_id: StoredInt, body: EatersIn, kitchen: Here, response: Response
) -> PlanWrite:
    """Who is eating a meal. Replaces the whole list; already that way → `change: null`. A
    login of another household → `404`."""
    return _run(
        kitchen,
        response,
        lambda: plan.set_eaters(kitchen, plan.find_meal(kitchen, plan_meal_id), body.login_ids),
    )


@router.delete("/plan/items/{plan_item_id}")
def remove_plan_item(plan_item_id: StoredInt, kitchen: Here, response: Response) -> PlanWrite:
    """Take one thing out of a meal. A meal left empty goes too. Undo puts it back."""
    return _run(
        kitchen, response, lambda: plan.remove_item(kitchen, plan.find_item(kitchen, plan_item_id))
    )


@router.delete("/plan/meals/{plan_meal_id}")
def remove_plan_meal(plan_meal_id: StoredInt, kitchen: Here, response: Response) -> PlanWrite:
    """Take a whole meal off the plan. Undo puts it back."""
    return _run(
        kitchen, response, lambda: plan.remove_meal(kitchen, plan.find_meal(kitchen, plan_meal_id))
    )


class PlanMoveIn(BaseModel):
    date: date
    slot_id: StoredInt
    mode: Literal["move", "copy", "leftovers"] = Field(
        default="move",
        description="move: it leaves where it was. copy: it stays too. leftovers: a tub of the"
        " recipe's batch cook (see `if_none_left`).",
    )
    if_none_left: Literal["ask", "cook_more", "add_anyway"] = Field(
        default="ask",
        description="leftovers only: what to do when the batch has no portion left for that"
        " meal. ask: change nothing and answer 409 `no_portions_left`. cook_more: a bigger"
        " batch. add_anyway: plan the recipe there for one serving; the batch stays the same.",
    )


@router.post("/plan/items/{plan_item_id}/move")
def move_plan_item(
    plan_item_id: StoredInt, body: PlanMoveIn, kitchen: Here, response: Response
) -> PlanWrite:
    """Move or copy one thing to another date and slot. Onto a filled meal it goes in
    alongside."""
    return _run(
        kitchen,
        response,
        lambda: plan.move_item(
            kitchen,
            plan.find_item(kitchen, plan_item_id),
            body.date,
            body.slot_id,
            body.mode,
            body.if_none_left,
        ),
    )


@router.post("/plan/meals/{plan_meal_id}/move")
def move_plan_meal(
    plan_meal_id: StoredInt, body: PlanMoveIn, kitchen: Here, response: Response
) -> PlanWrite:
    """Move or copy a whole meal to another date and slot. Onto a filled meal its things go
    in alongside."""
    return _run(
        kitchen,
        response,
        lambda: plan.move_meal(
            kitchen,
            plan.find_meal(kitchen, plan_meal_id),
            body.date,
            body.slot_id,
            body.mode,
            body.if_none_left,
        ),
    )


class SlotSwitchIn(BaseModel):
    enabled: bool


@router.patch("/meal-slots/{plan_slot_id}")
def switch_meal_slot(
    plan_slot_id: StoredInt, body: SlotSwitchIn, kitchen: Here, response: Response
) -> PlanWrite:
    """Turn a meal (Breakfast, Lunch…) on or off for the household. Its planned meals are
    kept while it is off."""
    return _run(
        kitchen,
        response,
        lambda: plan.set_slot(
            kitchen, plan.find_slot(kitchen, plan_slot_id, on=False), body.enabled
        ),
    )
