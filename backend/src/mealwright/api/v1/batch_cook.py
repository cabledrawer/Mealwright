"""Batch cook (Experimental; 0.8 wave 6, B2; docs/dev/api-0.2.md section 6.3b): suggestions of
recipes to cook together, and the sessions that "Plan this batch" makes. Everything is read from
and written to the household's own recipes and plan; nothing leaves the server. Online only, like
the rest of the plan; each write has its Undo (`POST /changes/{id}/undo`). An admin can hide Batch
cook in Settings: every route here then answers 409 `batch_cook_hidden`."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel, Field

from mealwright import batch_sessions, batch_suggest, plan
from mealwright.api.v1.batches import BatchIn, BatchPreviewOut, preview_out, spots_of
from mealwright.api.v1.context import Here
from mealwright.api.v1.plan import PlanWrite, _run
from mealwright.auth import SameOrigin
from mealwright.errors import StoredInt
from mealwright.models import BatchCook

router = APIRouter(tags=["batch cook"], dependencies=[SameOrigin])

Day = date  # for a model with a field called "date" (mypy reads later "date" as that field)


# --- Suggestions --------------------------------------------------------------------------------


class PickUseSoonOut(BaseModel):
    foods: list[str]
    days_left: int  # 0 is today


class PickOut(BaseModel):
    recipe_id: int
    name: str
    minutes: int  # the recipe's steps added up
    why: str
    use_soon: PickUseSoonOut | None


class KitchenBrief(BaseModel):
    hob_rings: int
    pressure_cookers: int
    oven: bool
    asked: bool  # false until the household has answered "Your kitchen" once


class SuggestionsOut(BaseModel):
    day: Day
    count: int
    picks: list[PickOut]
    # Rough times: all the picks cooked together, and one after another.
    together_minutes: int
    one_by_one_minutes: int
    # How many recipes could be picked at all (with at least one step); fewer than `count` means
    # the set is shorter than asked.
    pool: int
    # The next days with no cooking planned, the first being the default day.
    free_days: list[Day]
    kitchen: KitchenBrief


@router.get("/batch-cook/suggestions")
def get_suggestions(
    kitchen: Here,
    day: Annotated[
        date | None, Query(description="The cook day. Left out: the next day with no cooking.")
    ] = None,
    count: Annotated[int, Query(ge=2, le=4, description="How many recipes (2 to 4).")] = 3,
    keep: Annotated[
        list[StoredInt] | None,
        Query(max_length=4, description="Recipes that stay in the set (a swap keeps the others)."),
    ] = None,
    skip: Annotated[
        list[StoredInt] | None,
        Query(
            max_length=200,
            description="Recipes not to pick: the swapped one, or the last set (Show me others).",
        ),
    ] = None,
) -> SuggestionsOut:
    """Recipes from the household's own that can be cooked together, in this order of preference:
    shared prep (the same chopping or grinding, a shared base), Use soon ingredients, not cooked
    in the last 14 days, and what fits the kitchen's equipment. Each pick says why and how long it
    takes; the set says how long all of them take together and one by one. The same data always
    gives the same picks. Changes nothing."""
    batch_sessions.hidden_check(kitchen)
    if day is not None:
        plan.check_day(kitchen, day)
    found = batch_suggest.suggest(kitchen, day, count, keep, skip)
    household = kitchen.household
    return SuggestionsOut(
        day=found.day,
        count=found.count,
        picks=[
            PickOut(
                recipe_id=p.recipe_id,
                name=p.name,
                minutes=p.minutes,
                why=p.why,
                use_soon=PickUseSoonOut(foods=p.soon_foods, days_left=p.soon_days or 0)
                if p.soon_foods
                else None,
            )
            for p in found.picks
        ],
        together_minutes=found.together_minutes,
        one_by_one_minutes=found.one_by_one_minutes,
        pool=found.pool,
        free_days=found.free_days,
        kitchen=KitchenBrief(
            hob_rings=household.kitchen_hob_rings,
            pressure_cookers=household.kitchen_pressure_cookers,
            oven=household.kitchen_oven,
            asked=household.kitchen_asked,
        ),
    )


# --- Sessions -----------------------------------------------------------------------------------


class SessionRecipeIn(BatchIn):
    """One recipe of the session, with its Cook once choices (the same as one Cook once sheet)."""

    recipe_id: StoredInt


class SessionIn(BaseModel):
    date: Day = Field(description="The cook day.")
    slot_id: StoredInt | None = Field(
        default=None,
        description="The meal of the cook day the recipes are planned in. Left out: the last meal"
        " that is on and has no recipe planned that day (a change keeps the session's own meal).",
    )
    recipes: Annotated[list[SessionRecipeIn], Field(min_length=2, max_length=4)]


class SessionPreviewIn(BaseModel):
    date: Day
    slot_id: StoredInt | None = None
    session_id: StoredInt | None = Field(
        default=None,
        description="The session being changed: it is taken off first (as the change does), so the"
        " preview is what the change will save.",
    )
    recipes: Annotated[
        list[SessionRecipeIn],
        Field(
            min_length=1,
            max_length=4,
            description="The recipes so far; the last one is previewed, after the ones before it.",
        ),
    ]


def _choices(body: SessionIn | SessionPreviewIn) -> list[batch_sessions.RecipeChoice]:
    return [
        batch_sessions.RecipeChoice(
            recipe_id=r.recipe_id,
            tub_count=r.tub_count,
            pattern=r.pattern,
            member_login_ids=list(r.member_login_ids),
            extras_to_freezer=r.extras_to_freezer,
            prep_note=r.prep_note,
            placements=spots_of(r),
        )
        for r in body.recipes
    ]


@router.post("/batch-cook/sessions/preview")
def preview_session(body: SessionPreviewIn, kitchen: Here) -> BatchPreviewOut:
    """Where the last recipe's tubs would land, with the recipes before it already planned (the
    Cook once sheets of a session follow each other). Changes nothing."""
    changing = batch_sessions.find_session(kitchen, body.session_id) if body.session_id else None
    return batch_sessions.preview(
        kitchen,
        body.date,
        body.slot_id,
        _choices(body),
        lambda worked: preview_out(worked),
        changing,
    )


@router.post("/batch-cook/sessions", status_code=status.HTTP_201_CREATED)
def make_session(body: SessionIn, kitchen: Here, response: Response) -> PlanWrite:
    """Plan this batch: each recipe is planned in the cook day's meal and cooked once (tubs,
    pattern, who, as in Cook once), marked as one session. One change, one Undo, for all of it.
    2 to 4 recipes. A retry with the same `Idempotency-Key` makes nothing more."""
    out = _run(
        kitchen,
        response,
        lambda: batch_sessions.create(kitchen, body.date, body.slot_id, _choices(body)),
    )
    if response.headers.get("Idempotent-Replayed"):
        response.status_code = status.HTTP_200_OK
    return out


class SessionRecipeOut(BaseModel):
    batch_id: int
    recipe_id: int | None
    recipe_name: str
    tub_count: int
    pattern: str
    colour: str | None


class SessionOut(BaseModel):
    id: int
    cook_day: Day
    # The meal its recipes are planned in (null when none is any more).
    slot_id: int | None
    together_minutes: int | None
    one_by_one_minutes: int | None
    recipes: list[SessionRecipeOut]


@router.get("/batch-cook/sessions/{session_id}")
def get_session(session_id: StoredInt, kitchen: Here) -> SessionOut:
    """A session and its recipes, in the order they were made."""
    batch_sessions.hidden_check(kitchen)
    session = batch_sessions.find_session(kitchen, session_id)
    found: list[BatchCook] = batch_sessions.batches_of(kitchen, session)
    return SessionOut(
        id=session.id,
        cook_day=session.cook_day,
        slot_id=batch_sessions.session_slot(kitchen, session),
        together_minutes=session.together_minutes,
        one_by_one_minutes=session.one_by_one_minutes,
        recipes=[
            SessionRecipeOut(
                batch_id=b.id,
                recipe_id=b.recipe_id,
                recipe_name=b.recipe_name,
                tub_count=b.tub_count,
                pattern=b.pattern,
                colour=b.colour,
            )
            for b in found
        ],
    )


@router.put("/batch-cook/sessions/{session_id}")
def change_session(
    session_id: StoredInt, body: SessionIn, kitchen: Here, response: Response
) -> PlanWrite:
    """Change a session: its recipes are taken off the plan and the new ones planned, in one
    change with one Undo. A session that was cooked (`409 already_cooked`) can't be changed."""
    return _run(
        kitchen,
        response,
        lambda: batch_sessions.change(
            kitchen,
            batch_sessions.find_session(kitchen, session_id),
            body.date,
            body.slot_id,
            _choices(body),
        ),
    )


@router.delete("/batch-cook/sessions/{session_id}")
def delete_session(session_id: StoredInt, kitchen: Here, response: Response) -> PlanWrite:
    """Take the whole session off the plan: its recipes, their tubs and the tubs' places in
    meals. One change, one Undo. A session that was cooked (`409 already_cooked`) stays."""
    return _run(
        kitchen,
        response,
        lambda: batch_sessions.remove(kitchen, batch_sessions.find_session(kitchen, session_id)),
    )
