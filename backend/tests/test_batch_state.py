"""Batch cook mode never over-uses the kitchen (B3 review round 1, fix 1; cabledrawer 28 Oct: "never
more hob rings or pressure cookers than the kitchen has"): a task waits for the one before it in
its recipe, for what was on its ring, pressure cooker or oven before it, and a task that needs
equipment the kitchen lacks is done alone."""

import random
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from test_batch_schedule import KIT, random_recipes

from mealwright import batch_mode
from mealwright.batch_schedule import KitchenIn, RecipeIn, StepIn, schedule

T0 = datetime(2026, 11, 15, 10, 0, tzinfo=UTC)


def tasks_of(recipes: list[RecipeIn], kit: KitchenIn) -> list[dict[str, Any]]:
    return [
        asdict(t) | {"recipes": list(t.recipes), "steps": list(t.steps)}
        for t in schedule(recipes, kit).tasks
    ]


def row(started: datetime | None = None, done: datetime | None = None) -> Any:
    return SimpleNamespace(started_at=started, done_at=done)


def dal(recipe_id: int, first: int) -> RecipeIn:
    return RecipeIn(
        recipe_id,
        f"Dal {recipe_id}",
        (
            StepIn(first, "Pressure cook the dal.", "waiting", 15, "pressure"),
            StepIn(first + 1, "Temper.", "hands", 5, "hob"),
        ),
    )


def state_of(found: list[Any], task_id: str) -> str:
    return next(t.state for t in found if t.id == task_id)


def test_two_pressure_cooks_on_one_cooker_do_not_both_start() -> None:
    kit = KitchenIn(hob_rings=4, pressure_cookers=1, oven=True)
    tasks = tasks_of([dal(1, 10), dal(2, 20)], kit)
    cooks = [t for t in tasks if t["equipment"] == "pressure"]
    assert len(cooks) == 2 and cooks[0]["slot"] == cooks[1]["slot"] == 1
    first, second = cooks[0]["id"], cooks[1]["id"]
    found = batch_mode.states(tasks, {}, T0)
    assert state_of(found, first) == "ready" and state_of(found, second) == "later"
    running = batch_mode.states(tasks, {first: row(started=T0)}, T0 + timedelta(minutes=5))
    assert state_of(running, second) == "later"  # the cooker is in use
    over = batch_mode.states(tasks, {first: row(started=T0)}, T0 + timedelta(minutes=16))
    assert state_of(over, second) == "ready"  # its time ran out: the cooker is free


def test_frying_waits_for_the_hob_ring_a_simmer_is_on() -> None:
    kit = KitchenIn(hob_rings=1, pressure_cookers=1, oven=True)
    simmer = RecipeIn(1, "A", (StepIn(1, "Simmer for 20 minutes.", "waiting", 20, "hob"),))
    fry = RecipeIn(2, "B", (StepIn(2, "Fry the onions.", "hands", 5, "hob"),))
    tasks = tasks_of([simmer, fry], kit)
    simmering = next(t["id"] for t in tasks if t["hands"] == "waiting")
    frying = next(t["id"] for t in tasks if t["hands"] == "hands")
    found = batch_mode.states(tasks, {simmering: row(started=T0)}, T0 + timedelta(minutes=1))
    assert state_of(found, frying) == "later"


def test_a_step_without_its_equipment_waits_for_everything_and_everything_waits_for_it() -> None:
    kit = KitchenIn(hob_rings=4, pressure_cookers=1, oven=False)
    cook = RecipeIn(1, "A", (StepIn(1, "Chop.", "hands", 3, "none"),))
    bake = RecipeIn(2, "B", (StepIn(2, "Bake.", "waiting", 20, "oven"),))
    late = RecipeIn(3, "C", (StepIn(3, "Chop more.", "hands", 3, "none"),))
    tasks = tasks_of([cook, bake, late], kit)
    baking = next(t for t in tasks if t["lacks"])
    before = [t for t in tasks if t["end"] <= baking["start"]]
    after = [t for t in tasks if t["start"] >= baking["end"]]
    found = batch_mode.states(tasks, {}, T0)
    if before:
        assert state_of(found, baking["id"]) == "later"
    done = {t["id"]: row(done=T0) for t in before}
    found = batch_mode.states(tasks, done, T0)
    assert state_of(found, baking["id"]) == "ready"
    assert all(state_of(found, t["id"]) == "later" for t in after)


def walk(rng: random.Random, recipes: list[RecipeIn], kit: KitchenIn) -> None:
    """Press whatever is ready, in any order, and never exceed the kitchen."""
    tasks = tasks_of(recipes, kit)
    progress: dict[str, Any] = {}
    now = T0
    for _ in range(400):
        found = batch_mode.states(tasks, progress, now)
        if all(t.state == "done" for t in found):
            return
        hands = next((t for t in found if t.hands == "hands" and t.state == "ready"), None)
        busy = [t for t in found if t.state == "running"] + ([hands] if hands else [])
        for kind, cap in (
            ("hob", kit.hob_rings),
            ("pressure", kit.pressure_cookers),
            ("oven", int(kit.oven)),
        ):
            using = [t for t in busy if t.equipment == kind and not t.lacks]
            assert len(using) <= cap, (kind, [t.id for t in using])
        if any(t.lacks for t in busy):
            assert len(busy) == 1, [t.id for t in busy]
        ready_timers = [t for t in found if t.hands == "waiting" and t.state == "ready"]
        options: list[str] = []
        if ready_timers:
            options.append("timer")
        if hands:
            options.append("done")
        if not options:
            ends = [t.ends_at for t in found if t.state == "running" and t.ends_at]
            now = max(now, min(ends)) + timedelta(seconds=1)
            continue
        if rng.choice(options) == "timer":
            pick = rng.choice(ready_timers)
            progress[pick.id] = row(started=now)
        else:
            assert hands is not None
            progress[hands.id] = row(done=now)
            now += timedelta(minutes=hands.minutes)
    raise AssertionError("the walk did not finish")


def test_pressing_whatever_is_ready_never_exceeds_the_kitchen() -> None:
    rng = random.Random(20261112)  # noqa: S311
    for _ in range(300):
        recipes = random_recipes(rng)
        kit = KitchenIn(rng.randint(0, 5), rng.randint(0, 2), rng.random() < 0.7)
        walk(rng, recipes, kit)


def test_the_example_kitchen_walks_through() -> None:
    walk(random.Random(1), [dal(1, 10), dal(2, 20), dal(3, 30)], KIT)  # noqa: S311
