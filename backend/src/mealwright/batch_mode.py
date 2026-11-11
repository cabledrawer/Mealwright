"""Batch cook mode (Experimental; 0.8 wave 6, B3; cabledrawer 28 Oct and 11 Nov): one session cooked
across its recipes, following the schedule `batch_schedule` makes.

**Starting** makes the schedule from the session's recipes (the steps as they are now, with
B1's timings and 0.7's step-ingredient links) and the household's kitchen, and keeps it on the
session as a snapshot (`batch_session.schedule`), so a reload, another phone or a closed tab
carries on where it was, and a recipe edited later does not move a schedule already running.
What it was made from is fingerprinted (`schedule_basis`): when a recipe or the kitchen has
changed since, the screen offers **Plan again** (proposed, for cabledrawer), which makes it afresh and
clears the progress.

**Progress** is one row for each task that is done or whose timer was started
(`batch_task_progress`). A task is:

- `done`: marked done, or a waiting task whose timer has run out;
- `running`: a waiting task whose timer was started and is still going;
- `ready`: everything before it in its recipe is done, so it can be done (hands-on) or its timer
  started (waiting);
- `later`: something before it in its recipe isn't done.

**Now** is the first hands-on task, in schedule order, that is ready: the one thing for the cook's
hands. **Next** is the one after it. The server works these out (with the time it is given), so
every phone shows the same thing.
"""

import hashlib
import json
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from mealwright import (
    batch_schedule,
    batch_sessions,
    batches,
    methods,
    plan,
    start_ahead,
    step_timings,
    step_waits,
)
from mealwright.api.v1.context import Kitchen
from mealwright.batch_schedule import KitchenIn, LineIn, RecipeIn, StepIn
from mealwright.errors import Problem
from mealwright.history import as_utc
from mealwright.models import (
    BatchCook,
    BatchSession,
    BatchTaskProgress,
    Food,
    MealItem,
    RecipeLine,
    RecipeStep,
    RecipeStepLine,
    utcnow,
)

SNAPSHOT_VERSION = 1


def not_started() -> Problem:
    return Problem(
        status.HTTP_404_NOT_FOUND,
        "schedule_not_started",
        "Batch cook mode hasn't been started for this batch cook.",  # proposed, for cabledrawer
    )


# --- Reading the session's recipes ----------------------------------------------------------------


def kitchen_in(kitchen: Kitchen) -> KitchenIn:
    household = kitchen.household
    return KitchenIn(
        hob_rings=household.kitchen_hob_rings,
        pressure_cookers=household.kitchen_pressure_cookers,
        oven=household.kitchen_oven,
    )


def recipes_in(kitchen: Kitchen, found: list[BatchCook]) -> list[RecipeIn]:
    """The session's recipes as the scheduler reads them (the recipes still there, in the order
    they were made). Each is read in the way of cooking its meal uses."""
    db = kitchen.db
    out: list[RecipeIn] = []
    for batch in found:
        if batch.recipe_id is None:
            continue
        ways = methods.methods_of(db, batch.recipe_id)
        item = batches_item(kitchen, batch)
        method = methods.named(ways, item.method_id if item is not None else None)
        in_way = [
            s
            for s in db.scalars(
                select(RecipeStep)
                .where(RecipeStep.household_id == kitchen.household_id)
                .where(RecipeStep.recipe_id == batch.recipe_id, RecipeStep.kind == "step")
                .order_by(RecipeStep.position, RecipeStep.id)
            )
            if methods.in_method(s, ways, method)
        ]
        links: dict[int, list[int]] = {}
        for link in db.scalars(
            select(RecipeStepLine)
            .where(RecipeStepLine.household_id == kitchen.household_id)
            .where(RecipeStepLine.step_id.in_([s.id for s in in_way]))
            .order_by(RecipeStepLine.id)
        ):
            links.setdefault(link.step_id, []).append(link.line_id)
        # An Optional step is cooked unless the meal left out every ingredient it uses (the picks
        # asked when the batch was planned; a step that uses none is kept). RF3, C6.
        skipped = plan.skipped_optional(kitchen, item) if item is not None else frozenset()
        steps = [
            s
            for s in in_way
            if not s.optional or not links.get(s.id) or any(i not in skipped for i in links[s.id])
        ]
        lines = [
            ln
            for ln in db.scalars(
                select(RecipeLine)
                .where(RecipeLine.household_id == kitchen.household_id)
                .where(RecipeLine.recipe_id == batch.recipe_id, RecipeLine.kind == "ingredient")
                .order_by(RecipeLine.position, RecipeLine.id)
            )
            if methods.in_method(ln, ways, method)
        ]
        food_names = _food_names(kitchen, lines)
        timed: list[StepIn] = []
        for step in steps:
            timing = step_timings.of_step(step)
            if timing is None:
                continue
            wait = step_waits.of_step(step)
            timed.append(
                StepIn(
                    id=step.id,
                    text=step.text,
                    hands=timing.hands,
                    minutes=timing.minutes,
                    equipment=timing.equipment,
                    line_ids=tuple(links.get(step.id, [])),
                    ahead=wait is not None and wait.min_minutes >= start_ahead.MIN_AHEAD_MINUTES,
                    optional=step.optional,
                )
            )
        if not timed:
            continue
        out.append(
            RecipeIn(
                id=batch.recipe_id,
                name=batch.recipe_name,
                steps=tuple(timed),
                lines=tuple(
                    LineIn(
                        id=ln.id,
                        food_id=ln.food_id,
                        food_name=food_names.get(ln.food_id or 0),
                        amount_milli=ln.amount_milli,
                        unit=ln.unit,
                    )
                    for ln in lines
                ),
            )
        )
    return out


def batches_item(kitchen: Kitchen, batch: BatchCook) -> MealItem | None:
    return batches.cook_item_of(kitchen, batch)


def _food_names(kitchen: Kitchen, lines: list[RecipeLine]) -> dict[int, str]:
    ids = {ln.food_id for ln in lines if ln.food_id is not None}
    if not ids:
        return {}
    return {
        f.id: f.name
        for f in kitchen.db.scalars(
            select(Food).where(Food.household_id == kitchen.household_id, Food.id.in_(ids))
        )
    }


def basis_of(recipes: list[RecipeIn], kit: KitchenIn) -> str:
    """What a schedule is made from, as a fingerprint: the recipes' steps, timings and lines, and
    the kitchen. The same words, timings and kitchen always give the same one."""
    text = json.dumps(
        {"recipes": [asdict(r) for r in recipes], "kitchen": asdict(kit)},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(text.encode()).hexdigest()


# --- Starting -------------------------------------------------------------------------------------


def _snapshot(found: batch_schedule.Schedule, kit: KitchenIn) -> dict[str, Any]:
    return {
        "version": SNAPSHOT_VERSION,
        "kitchen": asdict(kit),
        "total_minutes": found.total_minutes,
        "tasks": [asdict(t) for t in found.tasks],
        "before": [asdict(b) for b in found.before],
    }


def start(kitchen: Kitchen, session: BatchSession, again: bool = False) -> bool:
    """Make the session's schedule and keep it (nothing to do when it is made already, unless
    `again`, which makes it afresh and clears the progress). Returns whether it was made now."""
    batch_sessions.hidden_check(kitchen)
    if session.schedule is not None and not again:
        return False
    found = batch_sessions.batches_of(kitchen, session)
    recipes = recipes_in(kitchen, found)
    if not recipes:
        raise Problem(
            status.HTTP_409_CONFLICT,
            "nothing_to_schedule",
            "None of this batch cook's recipes has a step to cook.",  # proposed, for cabledrawer
        )
    kit = kitchen_in(kitchen)
    made = batch_schedule.schedule(recipes, kit)
    session.schedule = _snapshot(made, kit)
    session.schedule_basis = basis_of(recipes, kit)
    session.schedule_made_at = utcnow()
    for row in _progress(kitchen, session).values():
        kitchen.db.delete(row)
    kitchen.db.flush()
    return True


# --- Reading --------------------------------------------------------------------------------------


@dataclass(frozen=True)
class TaskView:
    id: str
    kind: str
    title: str
    recipe_ids: list[int]
    step_ids: list[int]
    start: int
    end: int
    minutes: int
    hands: str
    equipment: str
    slot: int | None
    lacks: bool
    optional: bool
    state: str  # done, running, ready, later
    started_at: datetime | None
    done_at: datetime | None
    ends_at: datetime | None  # a running timer's end


@dataclass(frozen=True)
class View:
    session: BatchSession
    made_at: datetime
    stale: bool
    total_minutes: int
    kitchen: KitchenIn
    tasks: list[TaskView]
    before: list[dict[str, Any]]
    now_id: str | None
    next_id: str | None
    in_use: dict[str, int]
    done_count: int
    minutes_left: int


def _progress(kitchen: Kitchen, session: BatchSession) -> dict[str, BatchTaskProgress]:
    return {
        p.task_id: p
        for p in kitchen.db.scalars(
            select(BatchTaskProgress).where(
                BatchTaskProgress.household_id == kitchen.household_id,
                BatchTaskProgress.session_id == session.id,
            )
        )
    }


def _before_ids(tasks: list[dict[str, Any]]) -> dict[str, list[str]]:
    """What each task waits for (review B3 r1, fix 1: the kitchen's equipment is never over-used):

    - the previous task in each of its recipes (the step order of a recipe);
    - the previous task in the same hob ring, pressure cooker or oven, as the schedule gave them
      out (a ring is free only when what was on it is done);
    - a task that needs equipment the kitchen has none of (`lacks`) waits for every task before
      it, and every task after it waits for it: it is done alone.

    The same rule is in `frontend/src/lib/batchModeState.ts`."""
    last: dict[int, str] = {}
    in_slot: dict[tuple[str, int], str] = {}
    lacking: str | None = None
    out: list[tuple[str, list[str]]] = []
    seen: list[str] = []
    for task in tasks:  # in the order they start, which keeps each recipe's own order
        before: list[str] = []

        def need(other: str | None, before: list[str] = before) -> None:
            if other is not None and other not in before:
                before.append(other)

        for recipe_id in task["recipes"]:
            need(last.get(recipe_id))
            last[recipe_id] = task["id"]
        slot = task["slot"]
        if task["equipment"] != "none" and slot is not None and not task["lacks"]:
            need(in_slot.get((task["equipment"], slot)))
            in_slot[(task["equipment"], slot)] = task["id"]
        if task["lacks"]:
            for other in seen:
                need(other)
            lacking = task["id"]
        else:
            need(lacking)
        out.append((task["id"], before))
        seen.append(task["id"])
    return dict(out)


def states(
    tasks: list[dict[str, Any]], rows: dict[str, BatchTaskProgress], now: datetime
) -> list[TaskView]:
    """Each task's state at `now` (see the module's words)."""
    before = _before_ids(tasks)
    views: dict[str, TaskView] = {}
    out: list[TaskView] = []
    for task in tasks:
        row = rows.get(task["id"])
        minutes = task["end"] - task["start"]
        started = as_utc(row.started_at) if row is not None and row.started_at else None
        done_at = as_utc(row.done_at) if row is not None and row.done_at else None
        ends = started + timedelta(minutes=minutes) if started is not None else None
        waiting = task["hands"] == "waiting"
        if done_at is not None or (waiting and ends is not None and ends <= now):
            state = "done"
        elif waiting and started is not None:
            state = "running"
        elif all(views[b].state == "done" for b in before[task["id"]]):
            state = "ready"
        else:
            state = "later"
        view = TaskView(
            id=task["id"],
            kind=task["kind"],
            title=task["title"],
            recipe_ids=list(task["recipes"]),
            step_ids=list(task["steps"]),
            start=task["start"],
            end=task["end"],
            minutes=minutes,
            hands=task["hands"],
            equipment=task["equipment"],
            slot=task["slot"],
            lacks=task["lacks"],
            optional=bool(task.get("optional", False)),
            state=state,
            started_at=started,
            done_at=done_at,
            ends_at=ends if state == "running" else None,
        )
        views[task["id"]] = view
        out.append(view)
    return out


def view_of(kitchen: Kitchen, session: BatchSession, now: datetime | None = None) -> View:
    if session.schedule is None or session.schedule_made_at is None:
        raise not_started()
    now = now or utcnow()
    snapshot = session.schedule
    tasks = states(list(snapshot["tasks"]), _progress(kitchen, session), as_utc(now))
    hands = [t for t in tasks if t.hands == "hands" and t.state != "done"]
    ready = [t for t in hands if t.state == "ready"]
    now_task = ready[0] if ready else None
    next_task = None
    if now_task is not None:
        later = [t for t in hands if t.id != now_task.id]
        next_task = later[0] if later else None
    else:
        waits = [t for t in tasks if t.hands == "waiting" and t.state == "ready"]
        next_task = hands[0] if hands else (waits[0] if waits else None)
    kit = KitchenIn(**snapshot["kitchen"])
    in_use = {"hob": 0, "pressure": 0, "oven": 0}
    for t in tasks:
        busy = t.state == "running" or (now_task is not None and t.id == now_task.id)
        if busy and t.equipment in in_use and not t.lacks:
            in_use[t.equipment] += 1
    done = [t for t in tasks if t.state == "done"]
    left = sum(
        t.minutes
        for t in tasks
        if t.hands == "hands" and t.state != "done"  # the cook's own time still to give
    )
    found = batch_sessions.batches_of(kitchen, session)
    stale = basis_of(recipes_in(kitchen, found), kitchen_in(kitchen)) != session.schedule_basis
    return View(
        session=session,
        made_at=as_utc(session.schedule_made_at),
        stale=stale,
        total_minutes=int(snapshot["total_minutes"]),
        kitchen=kit,
        tasks=tasks,
        before=list(snapshot.get("before", [])),
        now_id=now_task.id if now_task else None,
        next_id=next_task.id if next_task else None,
        in_use=in_use,
        done_count=len(done),
        minutes_left=left,
    )


# --- Progress -------------------------------------------------------------------------------------


def _task(session: BatchSession, task_id: str) -> dict[str, Any]:
    if session.schedule is None:
        raise not_started()
    for task in session.schedule["tasks"]:
        if task["id"] == task_id:
            return dict(task)
    raise Problem(
        status.HTTP_404_NOT_FOUND,
        "not_found",
        "That task isn’t in this schedule.",  # proposed, for cabledrawer
    )


def _row(kitchen: Kitchen, session: BatchSession, task_id: str) -> BatchTaskProgress:
    found = kitchen.db.scalar(
        select(BatchTaskProgress).where(
            BatchTaskProgress.household_id == kitchen.household_id,
            BatchTaskProgress.session_id == session.id,
            BatchTaskProgress.task_id == task_id,
        )
    )
    if found is not None:
        return found
    row = BatchTaskProgress(
        household_id=kitchen.household_id, session_id=session.id, task_id=task_id
    )
    kitchen.db.add(row)
    try:
        kitchen.db.flush()
    except IntegrityError:  # pragma: no cover (the household's lock keeps two apart)
        kitchen.db.rollback()
        raise
    return row


def when(session: BatchSession, at: datetime | None, now: datetime) -> datetime:
    """The moment a mark counts from: the time it was pressed on the phone (a phone that was
    offline sends it later) when that lies between the schedule being made and now, else now
    (review B3 r1, fix 4; proposed, for cabledrawer)."""
    if at is None or session.schedule_made_at is None:
        return now
    pressed = as_utc(at)
    return pressed if as_utc(session.schedule_made_at) <= pressed <= as_utc(now) else now


def current(session: BatchSession, made_at: datetime | None) -> None:
    """A mark made on a phone that still holds an older schedule (another phone pressed Plan
    again since; the task ids are reused for different steps) is refused, so it never lands on
    the wrong step (RF3, C8; `409 schedule_replaced`, proposed, for cabledrawer). A mark that doesn't
    say which schedule it was made on is taken as before."""
    if made_at is None or session.schedule_made_at is None:
        return
    if abs((as_utc(made_at) - as_utc(session.schedule_made_at)).total_seconds()) > 0.001:
        raise Problem(
            status.HTTP_409_CONFLICT,
            "schedule_replaced",
            # proposed, for cabledrawer
            "The schedule was made again on another phone. Opening it afresh.",
        )


def mark_done(
    kitchen: Kitchen,
    session: BatchSession,
    task_id: str,
    now: datetime,
    at: datetime | None = None,
    made_at: datetime | None = None,
) -> None:
    """Done (a second time changes nothing: the first time stays)."""
    current(session, made_at)
    _task(session, task_id)
    row = _row(kitchen, session, task_id)
    if row.done_at is None:
        row.done_at = when(session, at, now)


def undo_done(
    kitchen: Kitchen, session: BatchSession, task_id: str, made_at: datetime | None = None
) -> None:
    """Take "done" back: the task is as if untouched (a timer it had is cleared too)."""
    current(session, made_at)
    _task(session, task_id)
    row = _progress(kitchen, session).get(task_id)
    if row is not None:
        kitchen.db.delete(row)


def start_timer(
    kitchen: Kitchen,
    session: BatchSession,
    task_id: str,
    now: datetime,
    at: datetime | None = None,
    made_at: datetime | None = None,
) -> None:
    """Start a waiting task's timer (started already: the first start stays). Only when the task
    is ready: everything before it in its recipe is done and the ring, pressure cooker or oven it
    uses is free (review B3 r1, fix 1; `409 not_ready`, proposed, for cabledrawer)."""
    current(session, made_at)
    task = _task(session, task_id)
    if task["hands"] != "waiting":
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "not_a_wait",
            "Only a waiting step has a timer.",  # proposed, for cabledrawer
        )
    moment = when(session, at, now)
    progress = _progress(kitchen, session)
    row = progress.get(task_id)
    if row is not None and row.started_at is not None:
        return  # started already: the first start stays
    found = {t.id: t for t in states(list((session.schedule or {})["tasks"]), progress, moment)}
    if found[task_id].state != "ready" and not (row is not None and row.done_at is not None):
        raise Problem(
            status.HTTP_409_CONFLICT,
            "not_ready",
            "This has to wait: the step before it, or the equipment it needs, isn’t free yet.",
        )  # proposed, for cabledrawer
    _row(kitchen, session, task_id).started_at = moment
