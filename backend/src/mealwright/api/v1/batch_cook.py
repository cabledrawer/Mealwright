"""Batch cook (Experimental; 0.8 wave 6, B2; docs/dev/api-0.2.md section 6.3b): suggestions of
recipes to cook together, and the sessions that "Plan this batch" makes. Everything is read from
and written to the household's own recipes and plan; nothing leaves the server. Online only, like
the rest of the plan; each write has its Undo (`POST /changes/{id}/undo`). An admin can hide Batch
cook in Settings: every route here then answers 409 `batch_cook_hidden`."""

from collections.abc import Callable
from datetime import date, datetime
from typing import Annotated

from fastapi import APIRouter, Path, Query, Response, status
from pydantic import BaseModel, Field

from mealwright import batch_mode, batch_sessions, batch_suggest, cooking, deduction, plan
from mealwright.api.v1.batches import BatchIn, BatchPreviewOut, preview_out, spots_of
from mealwright.api.v1.context import Here, Kitchen
from mealwright.api.v1.cooked import (
    ChoiceIn,
    CookedMealWrite,
    _confirm,
    _written_meal,
)
from mealwright.api.v1.cooked import (
    _choices as cook_choices,
)
from mealwright.api.v1.plan import PlanWrite, _run
from mealwright.api.v1.schemas import Answer
from mealwright.auth import SameOrigin
from mealwright.errors import Problem, StoredInt
from mealwright.models import BatchCook, BatchSession, utcnow
from mealwright.shopping import lock_db

router = APIRouter(tags=["batch cook"], dependencies=[SameOrigin])

TaskId = Annotated[str, Path(pattern=r"^t[1-9][0-9]{0,3}$")]
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


# --- Batch cook mode: the schedule and where it is up to ---------------------------------------


class ScheduleStartIn(BaseModel):
    plan_again: bool = Field(
        default=False,
        description=(
            "Make the schedule afresh (a recipe or the kitchen changed since): the progress is "
            "cleared. Left out: an existing schedule is kept as it is."
        ),
    )


class TaskOut(BaseModel):
    id: str = Field(description="`t1`, `t2`... in the order the tasks start.")
    kind: str = Field(description="`step` (one recipe's step) or `prep` (shared prep).")
    title: str
    recipe_ids: list[int] = Field(description="Several for shared prep.")
    step_ids: list[int]
    start: int = Field(description="Minutes from the start of the session.")
    end: int
    minutes: int
    hands: str = Field(description="`hands` (the cook's hands are busy) or `waiting`.")
    equipment: str = Field(description="`hob`, `pressure`, `oven` or `none`.")
    slot: int | None = Field(description="Which hob ring (1...), pressure cooker or oven.")
    lacks: bool = Field(description="The kitchen has none of its equipment: done alone.")
    state: str = Field(description="`done`, `running` (a timer), `ready` or `later`.")
    started_at: datetime | None = Field(description="When its timer was started.")
    done_at: datetime | None
    ends_at: datetime | None = Field(description="When a running timer ends.")


class BeforeOut(BaseModel):
    recipe_id: int
    step_id: int
    text: str
    minutes: int


class ScheduleKitchenOut(BaseModel):
    hob_rings: int
    pressure_cookers: int
    oven: bool


class ScheduleOut(BaseModel):
    session_id: int
    cook_day: Day
    made_at: datetime
    stale: bool = Field(
        description="A recipe or the kitchen has changed since: the screen offers Plan again."
    )
    total_minutes: int
    minutes_left: int = Field(description="The hands-on minutes still to give.")
    kitchen: ScheduleKitchenOut
    recipes: list[SessionRecipeOut]
    tasks: list[TaskOut]
    before: list[BeforeOut] = Field(
        description="Soaking and overnight steps left for the day before (Today shows them)."
    )
    now_id: str | None = Field(description="The one hands-on task to do now.")
    next_id: str | None
    in_use: dict[str, int] = Field(description="Equipment in use now: `hob`, `pressure`, `oven`.")
    done_count: int
    server_time: datetime


def _schedule_out(kitchen: Here, session_id: int, now: datetime | None = None) -> ScheduleOut:
    session = batch_sessions.find_session(kitchen, session_id)
    now = now or utcnow()
    found = batch_mode.view_of(kitchen, session, now)
    return ScheduleOut(
        session_id=session.id,
        cook_day=session.cook_day,
        made_at=found.made_at,
        stale=found.stale,
        total_minutes=found.total_minutes,
        minutes_left=found.minutes_left,
        kitchen=ScheduleKitchenOut(
            hob_rings=found.kitchen.hob_rings,
            pressure_cookers=found.kitchen.pressure_cookers,
            oven=found.kitchen.oven,
        ),
        recipes=[
            SessionRecipeOut(
                batch_id=b.id,
                recipe_id=b.recipe_id,
                recipe_name=b.recipe_name,
                tub_count=b.tub_count,
                pattern=b.pattern,
                colour=b.colour,
            )
            for b in batch_sessions.batches_of(kitchen, session)
        ],
        tasks=[TaskOut(**{k: getattr(t, k) for k in TaskOut.model_fields}) for t in found.tasks],
        before=[BeforeOut(**b) for b in found.before],
        now_id=found.now_id,
        next_id=found.next_id,
        in_use=found.in_use,
        done_count=found.done_count,
        server_time=now,
    )


@router.post("/batch-cook/sessions/{session_id}/schedule")
def start_schedule(
    session_id: StoredInt, kitchen: Here, response: Response, body: ScheduleStartIn | None = None
) -> ScheduleOut:
    """Start batch cook mode: make the session's schedule from its recipes and the household's
    kitchen (shared prep first, waits filled by hands-on work; never two hands-on tasks at once,
    never more hob rings, pressure cookers or ovens than the kitchen has) and keep it on the
    session. Already made: it is returned as it is (`200`); `plan_again` makes it afresh and
    clears the progress. Not an undoable change: it plans nothing and moves no stock. Needs at
    least one recipe with a step (`409 nothing_to_schedule`)."""
    batch_sessions.hidden_check(kitchen)
    lock_db(kitchen.db, kitchen.household)
    session = batch_sessions.find_session(kitchen, session_id)
    made = batch_mode.start(kitchen, session, again=bool(body and body.plan_again))
    kitchen.db.commit()
    response.status_code = status.HTTP_201_CREATED if made else status.HTTP_200_OK
    return _schedule_out(kitchen, session_id)


@router.get("/batch-cook/sessions/{session_id}/schedule")
def get_schedule(session_id: StoredInt, kitchen: Here) -> ScheduleOut:
    """The schedule and where it is up to: each task's state, the one to do now and the next, what
    is in use, and whether a recipe or the kitchen changed since it was made. `404
    schedule_not_started` before it is started."""
    batch_sessions.hidden_check(kitchen)
    return _schedule_out(kitchen, session_id)


def _progress_write(
    kitchen: Here, session_id: int, change: Callable[[BatchSession], None]
) -> ScheduleOut:
    batch_sessions.hidden_check(kitchen)
    lock_db(kitchen.db, kitchen.household)
    session = batch_sessions.find_session(kitchen, session_id)
    change(session)
    kitchen.db.commit()
    return _schedule_out(kitchen, session_id)


@router.put("/batch-cook/sessions/{session_id}/schedule/tasks/{task_id}/done")
def mark_task_done(session_id: StoredInt, task_id: TaskId, kitchen: Here) -> ScheduleOut:
    """Mark a task done (done already: it stays as it was). Every open screen of the household
    hears `batch_cook` and asks again."""
    now = utcnow()
    return _progress_write(
        kitchen, session_id, lambda s: batch_mode.mark_done(kitchen, s, task_id, now)
    )


@router.delete("/batch-cook/sessions/{session_id}/schedule/tasks/{task_id}/done")
def undo_task_done(session_id: StoredInt, task_id: TaskId, kitchen: Here) -> ScheduleOut:
    """Take "done" back: the task is as if untouched, and a timer it had is cleared."""
    return _progress_write(kitchen, session_id, lambda s: batch_mode.undo_done(kitchen, s, task_id))


@router.put("/batch-cook/sessions/{session_id}/schedule/tasks/{task_id}/timer")
def start_task_timer(session_id: StoredInt, task_id: TaskId, kitchen: Here) -> ScheduleOut:
    """Start a waiting task's timer, on the server's clock (started already: the first start
    stays), so every phone shows the same time left. `422 not_a_wait` for a hands-on task."""
    now = utcnow()
    return _progress_write(
        kitchen, session_id, lambda s: batch_mode.start_timer(kitchen, s, task_id, now)
    )


# --- One Cooked it for the whole session --------------------------------------------------------


class SessionItemIn(BaseModel):
    batch_id: StoredInt
    portions: Annotated[int, Field(ge=1, le=cooking.MOST_PORTIONS)] | None = None
    choices: list[ChoiceIn] = Field(default_factory=list, max_length=200)


class SessionCookIn(BaseModel):
    items: Annotated[list[SessionItemIn], Field(max_length=4)] | None = Field(
        default=None,
        description="Which recipes of the session, with their portions and choices. Left out: "
        "every recipe in it, as proposed.",
    )
    answers: list[Answer] = Field(default_factory=list, max_length=20)


class TubPlaceOut(BaseModel):
    place: str | None = Field(description="Fridge, Freezer...; null: in a meal or left over.")
    count: int


class SessionItemProposalOut(BaseModel):
    batch_id: int
    recipe_name: str
    tub_count: int
    tubs: list[TubPlaceOut]
    proposal: deduction.ProposalOut


class SessionProposalOut(BaseModel):
    session_id: int
    cook_day: Day
    items: list[SessionItemProposalOut]


def _session_entries(kitchen: Kitchen, session_id: int, body: SessionCookIn) -> list[cooking.Entry]:
    batch_sessions.hidden_check(kitchen)
    session = batch_sessions.find_session(kitchen, session_id)
    wanted: dict[int, tuple[int | None, dict[str, deduction.Choice]]] | None = None
    if body.items is not None:
        wanted = {}
        for one in body.items:
            if one.batch_id in wanted:
                raise Problem(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "twice",
                    "A recipe can be chosen only once.",  # proposed, for cabledrawer
                )
            wanted[one.batch_id] = (one.portions, cook_choices(kitchen, one.choices, body.answers))
    return batch_sessions.cook_entries(kitchen, session, wanted)


@router.post("/batch-cook/sessions/{session_id}/cook/preview")
def preview_session_cook(
    session_id: StoredInt, body: SessionCookIn, kitchen: Here
) -> SessionProposalOut:
    """What one "Cooked it" for the whole session would take from the pantry: a proposal for each
    recipe, worked out from one pool of packets (so two recipes never both propose the same
    grams), and where each recipe's tubs are. Changes nothing."""
    entries = _session_entries(kitchen, session_id, body)
    session = batch_sessions.find_session(kitchen, session_id)
    proposals = [
        deduction.proposal_out(kitchen, each)
        for each in cooking.preview(kitchen, entries, body.answers)
    ]
    items: list[SessionItemProposalOut] = []
    for entry, proposal in zip(entries, proposals, strict=True):
        batch = kitchen.db.get(BatchCook, entry.link["batch_id"])
        if batch is None:  # pragma: no cover (the entry was made from it)
            continue
        items.append(
            SessionItemProposalOut(
                batch_id=batch.id,
                recipe_name=batch.recipe_name,
                tub_count=batch.tub_count,
                tubs=[
                    TubPlaceOut(place=name, count=count)
                    for name, count in batch_sessions.tubs_by_place(kitchen, batch)
                ],
                proposal=proposal,
            )
        )
    return SessionProposalOut(session_id=session.id, cook_day=session.cook_day, items=items)


@router.post("/batch-cook/sessions/{session_id}/cook", status_code=status.HTTP_201_CREATED)
def cook_session(
    session_id: StoredInt, body: SessionCookIn, kitchen: Here, response: Response
) -> CookedMealWrite:
    """Cooked it, once, for the whole session: every recipe's ingredients are taken from the pantry
    as chosen (rows not mentioned are as proposed), as ONE change with one Undo that puts back
    every recipe's stock, and a cooked record for each recipe. All or nothing: if any recipe is
    refused (`409 already_cooked`...), none is taken. A retry with the same `Idempotency-Key` takes
    nothing more. The tubs are the ones Cook once made for each recipe."""
    return _confirm(
        kitchen,
        response,
        lambda: cooking.confirm(kitchen, _session_entries(kitchen, session_id, body), body.answers),
        _written_meal,
    )
