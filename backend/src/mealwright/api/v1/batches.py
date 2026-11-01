"""Cook once, eat for… (docs/dev/api-0.2.md section 6.3a, 0.6 PR 4): making a batch cook from a
planned recipe, placing its tubs, whose they are, the freezer, and "tubs left". Online only, like
the rest of the plan; each write has its Undo (`POST /changes/{id}/undo`)."""

from datetime import date, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from mealwright import batches, plan
from mealwright.api.v1.context import Here
from mealwright.api.v1.plan import PlanWrite, _run
from mealwright.auth import SameOrigin
from mealwright.errors import Problem, StoredInt
from mealwright.models import Login, Recipe

router = APIRouter(tags=["plan"], dependencies=[SameOrigin])

Day = date  # for a model with a field called "date" (mypy reads later "date" as that field)
Pattern = Literal["lunches", "lunch_dinner", "dinners", "pick"]


class PersonOut(BaseModel):
    login_id: int
    name: str


@router.get("/plan/people")
def list_people(kitchen: Here) -> list[PersonOut]:
    """Who can be eating: the household's logins (member profiles replace this in 0.8)."""
    return [
        PersonOut(login_id=login.id, name=login.name)
        for login in kitchen.db.scalars(
            select(Login).where(Login.household_id == kitchen.household_id).order_by(Login.id)
        )
    ]


class SpotIn(BaseModel):
    date: date
    slot_id: StoredInt


class BatchIn(BaseModel):
    tub_count: Annotated[int, Field(ge=1, le=batches.MOST_TUBS_IN_BATCH)]
    pattern: Pattern = "pick"
    member_login_ids: Annotated[list[StoredInt], Field(max_length=20)] = Field(
        default_factory=list,
        description="Who is eating. One: all the tubs are theirs. Several: the tubs go round"
        " them in turn. None: nobody in particular.",
    )
    extras_to_freezer: bool = Field(
        default=False, description="Tubs that don't go in a meal go in the freezer."
    )
    prep_note: Annotated[str, Field(max_length=500)] | None = None
    placements: (
        Annotated[list[SpotIn | None], Field(max_length=batches.MOST_TUBS_IN_BATCH)] | None
    ) = Field(
        default=None,
        description="The person's own choice, one entry per tub, in order (null: not in a"
        " meal). Left out, the pattern picks.",
    )


def _spots(body: BatchIn) -> list[batches.Spot | None] | None:
    if body.placements is None:
        return None
    return [None if p is None else (p.date, p.slot_id) for p in body.placements]


class PreviewTubOut(BaseModel):
    number: int
    date: date | None
    slot_id: int | None
    place_kind: Literal["fridge", "freezer"]
    place_id: int | None
    member_login_id: int | None
    use_by: Day
    # The meal it lands in already has something planned (the patterns skip those, a person
    # may still add one).
    meal_has_food: bool


class PerTubOut(BaseModel):
    kcal: int | None
    protein_g: int | None
    fibre_g: int | None


class BatchPreviewOut(BaseModel):
    recipe_id: int
    recipe_name: str
    recipe_serves: int | None
    cook_date: date
    cook_meal_id: int
    colour: str
    tubs: list[PreviewTubOut]
    placed: int
    per_tub: PerTubOut


def _per_tub(recipe: Recipe) -> PerTubOut:
    def part(milli: int | None) -> int | None:
        return None if milli is None else round(milli / 1000)

    return PerTubOut(
        kcal=part(recipe.kcal_milli),
        protein_g=part(recipe.protein_milli),
        fibre_g=part(recipe.fibre_milli),
    )


@router.post("/plan/items/{plan_item_id}/batch/preview")
def preview_batch(plan_item_id: StoredInt, body: BatchIn, kitchen: Here) -> BatchPreviewOut:
    """Where the tubs would land, worked out by the server so the screen and the saved batch
    agree. Changes nothing. Send `placements` after the person adds, removes or moves a tub."""
    item = plan.find_item(kitchen, plan_item_id)
    worked = batches.work_out(
        kitchen,
        item,
        body.tub_count,
        body.pattern,
        body.member_login_ids,
        body.extras_to_freezer,
        _spots(body),
    )
    return BatchPreviewOut(
        recipe_id=worked.recipe.id,
        recipe_name=worked.recipe.name,
        recipe_serves=worked.recipe.serves,
        cook_date=worked.meal.day,
        cook_meal_id=worked.meal.id,
        colour=worked.colour,
        tubs=[
            PreviewTubOut(
                number=t.number,
                date=t.spot[0] if t.spot else None,
                slot_id=t.spot[1] if t.spot else None,
                place_kind=t.place_kind,  # type: ignore[arg-type]
                place_id=t.place_id,
                member_login_id=t.member_login_id,
                use_by=t.use_by,
                meal_has_food=t.meal_has_food,
            )
            for t in worked.tubs
        ],
        placed=sum(1 for t in worked.tubs if t.spot),
        per_tub=_per_tub(worked.recipe),
    )


@router.post("/plan/items/{plan_item_id}/batch", status_code=status.HTTP_201_CREATED)
def make_batch(
    plan_item_id: StoredInt, body: BatchIn, kitchen: Here, response: Response
) -> PlanWrite:
    """Cook once, eat for…: make a batch cook from a planned recipe, with its tubs. The
    automatic patterns fill the next matching meals that are on, after the cook meal, and skip
    meals that already have something planned; tubs with no meal are "tubs left", in the fridge or
    (extras) the freezer. Use-by is the household's tub life from the cook day. At most 12 tubs in a
    batch, 10 batches a day. A retry with the same `Idempotency-Key` makes nothing more."""
    out = _run(
        kitchen,
        response,
        lambda: batches.make_batch(
            kitchen,
            plan.find_item(kitchen, plan_item_id),
            body.tub_count,
            body.pattern,
            body.member_login_ids,
            body.extras_to_freezer,
            body.prep_note,
            _spots(body),
        ),
    )
    if response.headers.get("Idempotent-Replayed"):
        response.status_code = status.HTTP_200_OK
    return out


@router.delete("/plan/batches/{plan_batch_id}")
def delete_batch(plan_batch_id: StoredInt, kitchen: Here, response: Response) -> PlanWrite:
    """Take a batch off the plan: its tubs go, and their places in meals. Undo brings all back."""
    return _run(
        kitchen,
        response,
        lambda: batches.delete_batch(kitchen, batches.find_batch(kitchen, plan_batch_id)),
    )


class TubPlaceIn(BaseModel):
    date: date
    slot_id: StoredInt


@router.post("/plan/tubs/{plan_tub_id}/place")
def place_tub(
    plan_tub_id: StoredInt, body: TubPlaceIn, kitchen: Here, response: Response
) -> PlanWrite:
    """Put a tub in a meal ("+ Add a tub", "+ Add a tub too", a drag from tubs left). A tub
    that is in a meal already moves there: it is in one meal at a time. To send one back to
    tubs left, take it out of its meal (`DELETE /plan/items/{id}`)."""
    return _run(
        kitchen,
        response,
        lambda: batches.place_tub(
            kitchen, batches.find_tub(kitchen, plan_tub_id), body.date, body.slot_id
        ),
    )


class TubEditIn(BaseModel):
    member_login_id: StoredInt | None = Field(
        default=None, description="Whose tub. null: nobody in particular."
    )
    use_by: date | None = None


@router.patch("/plan/tubs/{plan_tub_id}")
def edit_tub(
    plan_tub_id: StoredInt, body: TubEditIn, kitchen: Here, response: Response
) -> PlanWrite:
    """ "Whose tub?" and the use-by date. Only what is sent changes. Already that way →
    `change: null`."""
    fields = {k: getattr(body, k) for k in body.model_fields_set}
    if not fields:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "nothing_to_change",
            "Say whose tub it is, or its use-by date.",  # proposed, for cabledrawer
        )
    return _run(
        kitchen,
        response,
        lambda: batches.edit_tub(kitchen, batches.find_tub(kitchen, plan_tub_id), fields),
    )


class EatIn(BaseModel):
    quarters: Annotated[int, Field(ge=1, le=4)] | None = Field(
        default=None,
        description="How many quarters of a tub were eaten (2 is half). Left out: the whole of"
        " what is left of it.",
    )


@router.post("/plan/tubs/{plan_tub_id}/eat")
def eat_tub(
    plan_tub_id: StoredInt, kitchen: Here, response: Response, body: EatIn | None = None
) -> PlanWrite:
    """Eat from a tub: the tub is used, never the ingredients it was made from. One whole tub
    by default, or a number of quarters. What is left stays where it is. Undo gives it back."""
    return _run(
        kitchen,
        response,
        lambda: batches.eat_tub(
            kitchen, batches.find_tub(kitchen, plan_tub_id), (body or EatIn()).quarters
        ),
    )


@router.post("/plan/tubs/{plan_tub_id}/freezer")
def tub_to_freezer(plan_tub_id: StoredInt, kitchen: Here, response: Response) -> PlanWrite:
    """To freezer: the tub leaves its meal, goes in the freezer and gets a use-by the
    household's freezer life from today."""
    return _run(
        kitchen,
        response,
        lambda: batches.to_freezer(kitchen, batches.find_tub(kitchen, plan_tub_id)),
    )


class FillIn(BaseModel):
    start: date = Field(alias="from")
    end: date = Field(alias="to")


@router.post("/plan/fill-from-freezer")
def fill_from_freezer(body: FillIn, kitchen: Here, response: Response) -> PlanWrite:
    """Month's "Fill from freezer first": each day in the range with nothing planned gets a
    tub from the freezer (soonest use-by first) in the last meal that is on. At most 62 days.
    Nothing to fill, or nothing to fill it with → `change: null`."""
    if body.end < body.start or body.end - body.start > timedelta(days=61):
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "bad_range",
            "Ask for 1 to 62 days at a time.",  # proposed, for cabledrawer
        )
    return _run(kitchen, response, lambda: batches.fill_from_freezer(kitchen, body.start, body.end))


class TubLeftOut(BaseModel):
    id: int
    batch_id: int
    number: int
    tub_count: int
    recipe_name: str
    colour: str | None
    cooked_on: date
    amount_quarters: int
    place_id: int | None
    place_kind: Literal["fridge", "freezer", "cupboard"] | None
    member_login_id: int | None
    use_by: date


class TubsLeftOut(BaseModel):
    tubs: list[TubLeftOut]
    more: bool  # there are more than `limit`


@router.get("/plan/tubs-left")
def get_tubs_left(kitchen: Here, limit: Annotated[int, Query(ge=1, le=200)] = 100) -> TubsLeftOut:
    """Tubs in no meal that still have some in them, soonest use-by first."""
    found, more = batches.tubs_left(kitchen, limit)
    return TubsLeftOut(
        tubs=[
            TubLeftOut(
                id=t.tub.id,
                batch_id=t.batch.id,
                number=t.number,
                tub_count=t.batch.tub_count,
                recipe_name=t.batch.recipe_name,
                colour=t.batch.colour,
                cooked_on=t.batch.cooked_on,
                amount_quarters=t.tub.amount_quarters,
                place_id=t.tub.place_id,
                place_kind=t.place_kind,  # type: ignore[arg-type]
                member_login_id=t.tub.member_login_id,
                use_by=t.tub.use_by,
            )
            for t in found
        ],
        more=more,
    )


# --- Portions and "Leftovers on…" (0.7, P1) -------------------------------------------------------


class PortionsOut(BaseModel):
    recipe_name: str
    # No batch yet: the first leftovers make one, so there is no count to show.
    has_batch: bool
    batch_id: int | None
    portions: int | None  # the tubs plus the cook-day meal
    cook_day: int | None
    tubs: int | None
    in_meals: int | None  # tubs already planned in a meal
    left: int | None  # portions left to plan
    # The last day a tub of this batch can go in a meal.
    use_by: date


@router.get("/plan/items/{plan_item_id}/portions")
def get_portions(plan_item_id: StoredInt, kitchen: Here) -> PortionsOut:
    """How many portions the batch cooked for this recipe item makes, and how many are left to
    plan. Changes nothing."""
    item = plan.find_item(kitchen, plan_item_id)
    source = batches.recipe_meal_item(kitchen, item)
    batch = batches._batch_of(kitchen, source, item)
    name = batch.recipe_name if batch else plan._item_name(kitchen, item)
    if batch is None:
        return PortionsOut(
            recipe_name=name,
            has_batch=False,
            batch_id=None,
            portions=None,
            cook_day=None,
            tubs=None,
            in_meals=None,
            left=None,
            use_by=batches.tub_use_by(kitchen, "fridge", source.day),
        )
    found = batches.portions_of(kitchen, batch)
    return PortionsOut(
        recipe_name=name,
        has_batch=True,
        batch_id=batch.id,
        portions=found.total,
        cook_day=found.cook_day,
        tubs=found.tubs,
        in_meals=found.in_meals,
        left=found.left,
        use_by=found.use_by,
    )


class PlanLeftoversIn(BaseModel):
    meals: Annotated[list[SpotIn], Field(min_length=1, max_length=batches.MOST_TUBS_IN_BATCH)]
    if_none_left: Literal["ask", "cook_more", "add_anyway"] = Field(
        default="ask",
        description="What to do for the meals the portions left don't reach. ask: change nothing"
        " and answer 409 `no_portions_left`. cook_more: a bigger batch, a tub for each. add_anyway:"
        " plan the recipe there (one serving) and leave the batch as it is.",
    )


@router.post("/plan/items/{plan_item_id}/leftovers")
def plan_leftovers(
    plan_item_id: StoredInt, body: PlanLeftoversIn, kitchen: Here, response: Response
) -> PlanWrite:
    """ "Leftovers on…": several meals at once. Only meals after the cooking and not past the
    batch's use-by are accepted. A retry with the same `Idempotency-Key` plans nothing more."""
    return _run(
        kitchen,
        response,
        lambda: batches.leftovers_on(
            kitchen,
            plan.find_item(kitchen, plan_item_id),
            [(m.date, m.slot_id) for m in body.meals],
            body.if_none_left,
        ),
    )
