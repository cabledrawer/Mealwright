"""Batch cook's schedule (0.8 wave 6, B3; cabledrawer 28 Oct and 11 Nov): shared prep, waits filled
by
hands-on work, and the hard rules over random recipe sets and kitchens."""

import random
from itertools import pairwise

from hypothesis import given, settings
from hypothesis import strategies as st

from mealwright.batch_schedule import (
    KitchenIn,
    LineIn,
    RecipeIn,
    Schedule,
    StepIn,
    schedule,
)

KIT = KitchenIn(hob_rings=4, pressure_cookers=1, oven=True)


def line(i: int, food_id: int, name: str, milli: int | None, unit: str | None = None) -> LineIn:
    return LineIn(id=i, food_id=food_id, food_name=name, amount_milli=milli, unit=unit)


def sambar() -> RecipeIn:
    return RecipeIn(
        id=1,
        name="Sambar",
        lines=(line(11, 100, "Onion", 1000), line(12, 101, "Toor dal", 200_000, "g")),
        steps=(
            StepIn(101, "Chop the onion.", "hands", 5, "none", (11,)),
            StepIn(102, "Pressure cook the dal for 3 whistles.", "waiting", 15, "pressure", (12,)),
            StepIn(103, "Fry the onion and temper.", "hands", 5, "hob", (11,)),
            StepIn(104, "Simmer the sambar for 10 minutes.", "waiting", 10, "hob"),
        ),
    )


def chettinad() -> RecipeIn:
    return RecipeIn(
        id=2,
        name="Chicken chettinad",
        lines=(line(21, 100, "Onion", 2000), line(22, 102, "Chicken", 500_000, "g")),
        steps=(
            StepIn(201, "Chop the onions finely.", "hands", 6, "none", (21,)),
            StepIn(202, "Fry the onions and chicken for 8 minutes.", "hands", 8, "hob", (21, 22)),
            StepIn(203, "Simmer for 25 minutes.", "waiting", 25, "hob"),
        ),
    )


def sweet() -> RecipeIn:
    return RecipeIn(
        id=3,
        name="Kesari",
        steps=(
            StepIn(301, "Roast the rava in ghee.", "hands", 5, "hob"),
            StepIn(302, "Boil the water with sugar.", "waiting", 5, "hob"),
            StepIn(303, "Bake for 10 minutes.", "waiting", 10, "oven"),
        ),
    )


def by_step(found: Schedule) -> dict[int, tuple[int, int]]:
    return {s: (t.start, t.end) for t in found.tasks for s in t.steps}


def test_the_same_chopping_in_two_recipes_is_one_task_with_the_amounts() -> None:
    found = schedule([sambar(), chettinad()], KIT)
    prep = [t for t in found.tasks if t.kind == "prep"]
    assert len(prep) == 1
    assert prep[0].title == "Chop 3 onions: 1 for Sambar, 2 for Chicken chettinad"
    assert prep[0].recipes == (1, 2)
    assert prep[0].steps == (101, 201)
    assert prep[0].start == 0  # shared prep goes first
    assert prep[0].end - prep[0].start == 6 + 1  # the longest chop plus a minute for the other


def test_sambar_chettinad_and_kesari_waits_are_filled_by_hands_on_work() -> None:
    found = schedule([sambar(), chettinad(), sweet()], KIT)
    times = by_step(found)
    # Every step once.
    assert sorted(times) == [101, 102, 103, 104, 201, 202, 203, 301, 302, 303]
    # The dal goes in the pressure cooker the moment the shared chop ends, and the simmer of the
    # chicken overlaps hands-on work for the other recipes.
    assert times[102][0] == times[101][1]
    assert times[203][0] < times[103][1] or times[203][1] > times[103][0]
    # It is quicker than one after another, and the oven bake overlaps other work.
    one_by_one = sum(s.minutes for r in (sambar(), chettinad(), sweet()) for s in r.steps)
    assert found.total_minutes < one_by_one
    assert times[303][0] < times[203][1]  # the bake runs while the chicken simmers
    # Order within each recipe.
    for r in (sambar(), chettinad(), sweet()):
        ends = [times[s.id] for s in r.steps]
        for a, b in pairwise(ends):
            assert a[1] <= b[0]


def test_two_hands_on_tasks_never_overlap_in_the_example() -> None:
    found = schedule([sambar(), chettinad(), sweet()], KIT)
    check_rules(found, KIT)


def test_without_an_oven_the_baking_step_is_done_alone_and_flagged() -> None:
    kit = KitchenIn(hob_rings=4, pressure_cookers=1, oven=False)
    found = schedule([sambar(), chettinad(), sweet()], kit)
    bake = next(t for t in found.tasks if t.steps == (303,))
    assert bake.lacks and bake.slot is None
    for other in found.tasks:
        if other is not bake:
            assert other.end <= bake.start or bake.end <= other.start
    check_rules(found, kit)


def test_one_hob_ring_keeps_two_simmers_apart() -> None:
    kit = KitchenIn(hob_rings=1, pressure_cookers=1, oven=True)
    found = schedule([sambar(), chettinad()], kit)
    simmers = [t for t in found.tasks if t.steps in ((104,), (203,))]
    a, b = simmers
    assert a.end <= b.start or b.end <= a.start
    check_rules(found, kit)


def test_a_long_soak_at_the_start_is_left_for_the_day_before() -> None:
    soaked = RecipeIn(
        id=4,
        name="Idli",
        steps=(
            StepIn(401, "Soak the rice overnight.", "waiting", 720, "none", ahead=True),
            StepIn(402, "Grind the batter.", "hands", 20, "none"),
        ),
    )
    found = schedule([soaked, sambar()], KIT)
    assert [(b.recipe_id, b.step_id) for b in found.before] == [(4, 401)]
    assert 401 not in by_step(found)
    assert by_step(found)[402][0] < 60  # no twelve-hour wait in the day


def test_a_long_wait_in_the_middle_of_a_recipe_leaves_the_steps_up_to_it_for_the_day_before() -> (
    None
):
    """C4: mix, marinate overnight, grill: Today says Start tonight, so the day's schedule has the
    grill only, not a twelve-hour timer (the same step Today's start uses: the first long wait)."""
    tandoori = RecipeIn(
        id=5,
        name="Tandoori",
        steps=(
            StepIn(501, "Mix the yoghurt and spices and coat the chicken.", "hands", 10, "none"),
            StepIn(502, "Leave to marinate (overnight).", "waiting", 720, "none", ahead=True),
            StepIn(503, "Grill for 20 minutes.", "waiting", 20, "oven"),
        ),
    )
    found = schedule([tandoori, sambar()], KIT)
    assert [(b.recipe_id, b.step_id) for b in found.before] == [(5, 501), (5, 502)]
    assert set(by_step(found)) >= {503} and not {501, 502} & set(by_step(found))
    assert found.total_minutes < 120


def test_a_long_wait_that_names_the_hob_is_left_for_the_day_before_too() -> None:
    curd = RecipeIn(
        id=6,
        name="Curd",
        steps=(
            StepIn(601, "Boil the milk and cool it.", "hands", 10, "hob"),
            StepIn(
                602,
                "Set with a spoon of curd and ferment for 8 hours.",
                "waiting",
                480,
                "hob",
                ahead=True,
            ),
            StepIn(603, "Chill and serve.", "hands", 2, "none"),
        ),
    )
    found = schedule([curd], KIT)
    assert [b.step_id for b in found.before] == [601, 602]
    assert found.total_minutes == 2


def test_the_same_input_gives_the_same_schedule() -> None:
    assert schedule([sambar(), chettinad(), sweet()], KIT) == schedule(
        [sambar(), chettinad(), sweet()], KIT
    )


def test_a_shared_chop_that_would_make_a_recipe_wait_for_itself_stays_apart() -> None:
    # A chops onion first, then garlic; B chops garlic first, then onion: merging both would loop.
    a = RecipeIn(
        1,
        "A",
        (
            StepIn(1, "Chop the onion.", "hands", 3, "none", (1,)),
            StepIn(2, "Chop the garlic.", "hands", 3, "none", (2,)),
        ),
        (line(1, 10, "Onion", 1000), line(2, 11, "Garlic", 1000)),
    )
    b = RecipeIn(
        2,
        "B",
        (
            StepIn(3, "Chop the garlic.", "hands", 3, "none", (4,)),
            StepIn(4, "Chop the onion.", "hands", 3, "none", (3,)),
        ),
        (line(3, 10, "Onion", 1000), line(4, 11, "Garlic", 1000)),
    )
    found = schedule([a, b], KIT)
    assert sorted(s for t in found.tasks for s in t.steps) == [1, 2, 3, 4]
    check_rules(found, KIT)


# --- The hard rules, over random recipes and kitchens ---------------------------------------------


def check_rules(found: Schedule, kit: KitchenIn, recipes: list[RecipeIn] | None = None) -> None:
    tasks = found.tasks
    for a in tasks:
        assert a.end > a.start >= 0
        for b in tasks:
            if a is b:
                continue
            overlap = a.start < b.end and b.start < a.end
            if overlap:
                assert not (a.hands == "hands" and b.hands == "hands"), "two hands-on tasks at once"
                assert not a.lacks and not b.lacks, "a task without its equipment is alone"
                if a.slot is not None and b.slot is not None and a.equipment == b.equipment:
                    assert a.slot != b.slot, "one ring used twice"
    for kind, cap in (
        ("hob", kit.hob_rings),
        ("pressure", kit.pressure_cookers),
        ("oven", int(kit.oven)),
    ):
        used = [t for t in tasks if t.equipment == kind and not t.lacks]
        for t in used:
            assert t.slot is not None and 1 <= t.slot <= cap
            at_once = sum(1 for u in used if u.start <= t.start < u.end)
            assert at_once <= cap
        for t in tasks:
            if t.equipment == kind and t.lacks:
                assert cap == 0
    if recipes is not None:
        times = by_step(found)
        wanted = {s.id for r in recipes for s in r.steps}
        before = {b.step_id for b in found.before}
        assert sorted(list(times) + sorted(before)) == sorted(wanted)
        assert len(list(times)) == len(set(times))
        for r in recipes:
            seen = [times[s.id] for s in r.steps if s.id in times]
            for x, y in pairwise(seen):
                assert x[1] <= y[0], "a recipe's steps keep their order"


def random_recipes(rng: random.Random) -> list[RecipeIn]:
    foods = [(100 + i, name) for i, name in enumerate(["Onion", "Tomato", "Coriander", "Coconut"])]
    recipes: list[RecipeIn] = []
    step_id = 1
    line_id = 1
    for r in range(rng.randint(1, 4)):
        lines = []
        for food_id, name in rng.sample(foods, rng.randint(1, 3)):
            lines.append(
                LineIn(
                    line_id,
                    food_id,
                    name,
                    rng.choice([None, 1000, 2000, 150_000]),
                    None if rng.random() < 0.5 else "g",
                )
            )
            line_id += 1
        steps: list[StepIn] = []
        for _ in range(rng.randint(1, 7)):
            kind = rng.choice(["prep", "prep", "fry", "simmer", "pressure", "oven", "wait"])
            linked = tuple(
                ln.id for ln in rng.sample(lines, rng.randint(0, len(lines))) if kind == "prep"
            )
            if kind == "prep":
                step = StepIn(
                    step_id,
                    rng.choice(["Chop", "Grind", "Slice"]) + " it.",
                    "hands",
                    rng.randint(1, 15),
                    "none",
                    linked,
                )
            elif kind == "fry":
                step = StepIn(step_id, "Fry.", "hands", rng.randint(1, 15), "hob")
            elif kind == "simmer":
                step = StepIn(step_id, "Simmer.", "waiting", rng.randint(1, 40), "hob")
            elif kind == "pressure":
                step = StepIn(step_id, "Pressure cook.", "waiting", rng.randint(1, 30), "pressure")
            elif kind == "oven":
                step = StepIn(step_id, "Bake.", "waiting", rng.randint(1, 40), "oven")
            else:
                step = StepIn(
                    step_id,
                    "Rest.",
                    "waiting",
                    rng.randint(1, 30),
                    "none",
                    ahead=rng.random() < 0.2 and not steps,
                )
            steps.append(step)
            step_id += 1
        recipes.append(RecipeIn(r + 1, f"Recipe {r + 1}", tuple(steps), tuple(lines)))
    return recipes


def test_hard_rules_hold_over_a_thousand_random_sessions() -> None:
    rng = random.Random(20261111)  # noqa: S311
    for _ in range(1000):
        recipes = random_recipes(rng)
        kit = KitchenIn(rng.randint(0, 6), rng.randint(0, 2), rng.random() < 0.7)
        found = schedule(recipes, kit)
        check_rules(found, kit, recipes)
        assert found == schedule(recipes, kit)


@settings(max_examples=150, deadline=None)
@given(
    seed=st.integers(0, 2**32), rings=st.integers(0, 5), pots=st.integers(0, 2), oven=st.booleans()
)
def test_hard_rules_hold_for_any_seed(seed: int, rings: int, pots: int, oven: bool) -> None:
    recipes = random_recipes(random.Random(seed))  # noqa: S311
    kit = KitchenIn(rings, pots, oven)
    check_rules(schedule(recipes, kit), kit, recipes)
