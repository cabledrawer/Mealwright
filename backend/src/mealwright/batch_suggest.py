"""Batch cook (Experimental) suggestions (0.8 wave 6, B2; cabledrawer 28 Oct, 6 Nov and 11 Nov):
recipes from the household's own that can be cooked together in one session.

Everything is worked out on the server from the household's own recipes, its pantry and its own
plan. Nothing is looked up anywhere else and no model is asked (spec: "suggestions only from the
household's own recipes; nothing leaves the server").

**What is preferred, in this order** (spec section 6, "Batch cook (Experimental)"):

1. **Shared prep:** the same chopping or grinding, or a shared base. Two recipes share prep when
   both prepare the same ingredient (a recipe prepares an ingredient when a chopping, grinding,
   slicing... step uses it, by the step's ingredient links of 0.7, or when its line says so,
   "1 onion, finely chopped"). Staples never count (salt is not chopped).
2. **Use soon items:** recipes that use an ingredient on its Use soon list (the pantry's own rule).
3. **Not cooked in the last 14 days** (never cooked counts).
4. **Fits the kitchen's equipment:** no oven step without an oven, no pressure cooker step without
   a pressure cooker.

A set is built greedily: the first two are the pair that is best by those four, in that order,
then each next one is the best given the ones already picked. Ties are broken by name, then by
id, so the same data always gives the same picks. A pick that is kept stays, a swapped one is
`skip`ped, and "Show me others" skips the whole last set (and anything skipped before).

**The times.** Each recipe's minutes are its steps' minutes added up (`step_timings`: guessed from
the words unless set by hand). "One by one" is those added across the picks. "Together" is a
rough schedule: each recipe's steps go in order; **waiting steps overlap with other work, hands-on
steps never overlap with each other** (one pair of hands), and never more hob rings, pressure
cookers or ovens at once than the kitchen has. It is rough on purpose (batch cook mode, B3, makes
the real schedule) and never longer than one by one.
"""

import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from itertools import combinations

from sqlalchemy import select

from mealwright import methods, step_timings
from mealwright.api.v1.context import Kitchen
from mealwright.household import today
from mealwright.models import (
    CookedRecord,
    Meal,
    MealItem,
    RecipeLine,
    RecipeStep,
    RecipeStepLine,
    utcnow,
)
from mealwright.names import fold
from mealwright.recipe_list import Stock, _foods
from mealwright.recipes import live_recipes

MOST_PICKS = 4
FEWEST_PICKS = 2
DEFAULT_PICKS = 3
RECENT_DAYS = 14
# A waiting step shorter than this is not worth saying a recipe "cooks while you work on others".
LONG_WAIT = 10

# What a step or an ingredient line says about preparing (chopping, grinding...).
_PREP_STEP = re.compile(
    r"\b(?:chop|grind|slice|dice|mince|grate|blend|peel|crush|pound|shred|cut)\w*", re.I
)
_PREP_LINE = re.compile(
    r"\b(?:chopped|ground|sliced|diced|minced|grated|crushed|peeled|shredded|paste|pounded)\b",
    re.I,
)


@dataclass
class Candidate:
    """One recipe, as the suggestions see it."""

    recipe_id: int
    name: str
    steps: list[step_timings.Timing]
    prep: dict[int, str]  # ingredient id -> name, the ingredients it prepares
    soon: list[tuple[str, int]]  # (ingredient name, days left) it uses that are Use soon
    fresh: bool  # not cooked in the last 14 days
    fits: bool  # the kitchen has what it needs
    minutes: int = 0
    order: tuple[str, int] = field(default=("", 0))


@dataclass(frozen=True)
class Equipment:
    hob_rings: int
    pressure_cookers: int
    oven: bool


@dataclass
class Pick:
    recipe_id: int
    name: str
    minutes: int
    why: str
    soon_foods: list[str]
    soon_days: int | None


@dataclass
class Suggestions:
    day: date
    count: int
    picks: list[Pick]
    together_minutes: int
    one_by_one_minutes: int
    pool: int  # how many recipes could be picked at all
    free_days: list[date]


def equipment_of(kitchen: Kitchen) -> Equipment:
    household = kitchen.household
    return Equipment(
        hob_rings=household.kitchen_hob_rings,
        pressure_cookers=household.kitchen_pressure_cookers,
        oven=household.kitchen_oven,
    )


# --- The rough schedule ---------------------------------------------------------------------


def together_minutes(recipes: list[list[step_timings.Timing]], kit: Equipment) -> int:
    """How long these recipes take cooked together, roughly (see the module's words). Never longer
    than one by one."""
    one_by_one = sum(s.minutes for steps in recipes for s in steps)
    hob = [0] * max(kit.hob_rings, 1)
    pools: dict[str, list[int]] = {
        "hob": hob,
        # No pressure cooker or oven: the pot goes on a hob ring instead.
        "pressure": [0] * kit.pressure_cookers if kit.pressure_cookers > 0 else hob,
        "oven": [0] if kit.oven else hob,
    }
    left = [sum(s.minutes for s in steps) for steps in recipes]
    ready = [0] * len(recipes)
    at = [0] * len(recipes)
    hands_free = 0
    finish = 0
    while any(at[i] < len(recipes[i]) for i in range(len(recipes))):
        best: tuple[tuple[int, int, int, int], int, int, list[int] | None] | None = None
        for i, steps in enumerate(recipes):
            if at[i] >= len(steps):
                continue
            step = steps[at[i]]
            pool = pools.get(step.equipment)
            start = ready[i]
            if step.hands == "hands":
                start = max(start, hands_free)
            if pool is not None:
                start = max(start, min(pool))
            # The earliest start goes first; at the same time a waiting step goes before a
            # hands-on one (it frees the hands for something else), then the recipe with the most
            # still to do, then the order they were given.
            key = (start, 0 if step.hands == "waiting" else 1, -left[i], i)
            if best is None or key < best[0]:
                best = (key, i, start, pool)
        if best is None:  # pragma: no cover (the loop only runs while a recipe has a step left)
            break
        _, i, start, pool = best
        step = recipes[i][at[i]]
        end = start + step.minutes
        if step.hands == "hands":
            hands_free = end
        if pool is not None:
            pool[pool.index(min(pool))] = end
        ready[i] = end
        left[i] -= step.minutes
        at[i] += 1
        finish = max(finish, end)
    return min(finish, one_by_one)


# --- Reading the household's recipes ----------------------------------------------------------


def _candidates(kitchen: Kitchen, kit: Equipment) -> list[Candidate]:
    db = kitchen.db
    hid = kitchen.household_id
    recipes = live_recipes(kitchen)
    if not recipes:
        return []
    foods = _foods(kitchen)
    stock = Stock(kitchen, foods)
    ms = methods.of_recipes(db, recipes)
    first = {rid: methods.named(ms.get(rid, []), None) for rid in recipes}

    steps_by: dict[int, list[RecipeStep]] = defaultdict(list)
    for step in db.scalars(
        select(RecipeStep)
        .where(RecipeStep.household_id == hid)
        .order_by(RecipeStep.recipe_id, RecipeStep.position)
    ):
        if step.recipe_id in recipes and methods.in_method(
            step, ms.get(step.recipe_id, []), first[step.recipe_id]
        ):
            steps_by[step.recipe_id].append(step)

    lines_by: dict[int, list[RecipeLine]] = defaultdict(list)
    for line in db.scalars(
        select(RecipeLine).where(RecipeLine.household_id == hid, RecipeLine.kind == "ingredient")
    ):
        if line.recipe_id in recipes and methods.in_method(
            line, ms.get(line.recipe_id, []), first[line.recipe_id]
        ):
            lines_by[line.recipe_id].append(line)

    links: dict[int, set[int]] = defaultdict(set)  # step id -> line ids
    for link in db.scalars(select(RecipeStepLine).where(RecipeStepLine.household_id == hid)):
        links[link.step_id].add(link.line_id)

    cutoff = utcnow() - timedelta(days=RECENT_DAYS)
    recent = {
        rid
        for rid in db.scalars(
            select(CookedRecord.recipe_id).where(
                CookedRecord.household_id == hid,
                CookedRecord.recipe_id.is_not(None),
                CookedRecord.cooked_at >= cutoff,
            )
        )
        if rid is not None
    }

    found: list[Candidate] = []
    for rid, recipe in recipes.items():
        steps = [s for s in steps_by.get(rid, []) if s.kind == "step" and not s.optional]
        timings = [t for t in (step_timings.of_step(s) for s in steps) if t is not None]
        if not timings:
            continue  # nothing to time: it can't be planned into a session
        lines = {line.id: line for line in lines_by.get(rid, [])}
        prep_lines: set[int] = set()
        for step in steps:
            if _PREP_STEP.search(step.text):
                prep_lines |= links.get(step.id, set()) & lines.keys()
        for line in lines.values():
            if _PREP_LINE.search(f"{line.words} {line.note or ''}"):
                prep_lines.add(line.id)
        prep: dict[int, str] = {}
        for line_id in prep_lines:
            food = foods.get(lines[line_id].food_id or 0)
            if food is not None and not food.staple:
                prep[food.id] = food.name
        soon: dict[str, int] = {}
        for line in lines.values():
            food = foods.get(line.food_id or 0)
            day = stock.soonest.get(food.id) if food is not None else None
            if food is not None and day is not None:
                soon[food.name] = (day - stock.today).days
        needs_oven = any(t.equipment == "oven" for t in timings)
        needs_pressure = any(t.equipment == "pressure" for t in timings)
        found.append(
            Candidate(
                recipe_id=rid,
                name=recipe.name,
                steps=timings,
                prep=prep,
                soon=sorted(soon.items(), key=lambda s: (s[1], fold(s[0]))),
                fresh=rid not in recent,
                fits=(kit.oven or not needs_oven)
                and (kit.pressure_cookers > 0 or not needs_pressure),
                minutes=sum(t.minutes for t in timings),
                order=(fold(recipe.name), rid),
            )
        )
    found.sort(key=lambda c: c.order)
    return found


def _shared(a: Candidate, b: Candidate) -> set[int]:
    return a.prep.keys() & b.prep.keys()


# --- Picking ----------------------------------------------------------------------------------


def _choose(pool: list[Candidate], kept: list[Candidate], count: int) -> list[Candidate]:
    """Fill the set up to `count`: the best pair first when nothing is kept, then the best next
    one each time. Every comparison is the four preferences in order, then the name, then the id."""
    picked = list(kept)
    left = [c for c in pool if c not in picked]
    if not picked and count >= FEWEST_PICKS and len(left) >= FEWEST_PICKS:
        best_pair = min(
            combinations(left, 2),
            key=lambda p: (
                -len(_shared(*p)),
                -(len(p[0].soon) + len(p[1].soon)),
                -(p[0].fresh + p[1].fresh),
                -(p[0].fits + p[1].fits),
                p[0].order,
                p[1].order,
            ),
        )
        picked.extend(best_pair)
        left = [c for c in left if c not in picked]
    while len(picked) < count and left:
        nxt = min(
            left,
            key=lambda c: (
                -sum(len(_shared(c, p)) for p in picked),
                -len(c.soon),
                -c.fresh,
                -c.fits,
                c.order,
            ),
        )
        picked.append(nxt)
        left.remove(nxt)
    return picked


def _listed(names: list[str]) -> str:
    if len(names) == 1:
        return names[0]
    return ", ".join(names[:-1]) + " and " + names[-1]


def _why(pick: Candidate, others: list[Candidate]) -> str:
    clauses: list[str] = []
    sharing = [(o, _shared(pick, o)) for o in others]
    sharing = [(o, s) for o, s in sharing if s]
    if sharing:
        foods = sorted({pick.prep[f].lower() for _, s in sharing for f in s})
        shown = _listed(foods[:3])
        clauses.append(f"Shares {shown} prep with {_listed([o.name for o, _ in sharing])}")
    if pick.soon:
        names = [name.lower() for name, _ in pick.soon[:2]]
        clauses.append(f"uses your Use soon {_listed(names)}")
    if others:
        waits = [s for s in pick.steps if s.hands == "waiting" and s.minutes >= LONG_WAIT]
        if waits:
            longest = max(waits, key=lambda s: s.minutes)
            clauses.append(
                {
                    "pressure": "pressure cooker runs while you chop for the others",
                    "oven": "the oven does the work while you cook the others",
                    "hob": "simmers while you work on the others",
                }.get(longest.equipment, "waits while you work on the others")
            )
    if pick.fresh:
        clauses.append("not cooked in the last 14 days")
    if not clauses:
        return "Fits your kitchen."
    first = clauses[0]
    return "; ".join([first[:1].upper() + first[1:], *clauses[1:]]) + "."


def next_free_day(kitchen: Kitchen, start: date, count: int = 1) -> list[date]:
    """The next days (from `start`) with no cooking planned: no meal that day has a recipe in it.
    A day with only tubs, ingredients or notes is free."""
    db = kitchen.db
    last = start + timedelta(days=90)
    busy = set(
        db.scalars(
            select(Meal.day)
            .join(MealItem, MealItem.meal_id == Meal.id)
            .where(
                Meal.household_id == kitchen.household_id,
                Meal.day >= start,
                Meal.day <= last,
                MealItem.recipe_id.is_not(None),
            )
        )
    )
    free: list[date] = []
    day = start
    while len(free) < count and day <= last:
        if day not in busy:
            free.append(day)
        day += timedelta(days=1)
    return free or [start]


def suggest(
    kitchen: Kitchen,
    day: date | None,
    count: int = DEFAULT_PICKS,
    keep: list[int] | None = None,
    skip: list[int] | None = None,
) -> Suggestions:
    """The picks for a session on `day` (default: the next day with no cooking planned).
    `keep` stays in the set (a swap keeps the others); `skip` is never picked unless there is
    nothing else to fill the set with (so "Show me others" always has an answer)."""
    count = min(max(count, FEWEST_PICKS), MOST_PICKS)
    kit = equipment_of(kitchen)
    everyone = _candidates(kitchen, kit)
    free = next_free_day(kitchen, today(kitchen.household), 3)
    if day is None:
        day = free[0]
    by_id = {c.recipe_id: c for c in everyone}
    kept: list[Candidate] = []
    for rid in dict.fromkeys(keep or []):
        if rid in by_id and len(kept) < count:
            kept.append(by_id[rid])
    skipped = set(skip or [])
    fresh_pool = [c for c in everyone if c.recipe_id not in skipped or c in kept]
    picked = _choose(fresh_pool, kept, count)
    if len(picked) < count:  # not enough that weren't skipped: bring the skipped back, best first
        picked = _choose(everyone, picked, count)
    out: list[Pick] = []
    for c in picked:
        others = [o for o in picked if o is not c]
        out.append(
            Pick(
                recipe_id=c.recipe_id,
                name=c.name,
                minutes=c.minutes,
                why=_why(c, others),
                soon_foods=[n for n, _ in c.soon],
                soon_days=min((d for _, d in c.soon), default=None),
            )
        )
    one_by_one = sum(c.minutes for c in picked)
    return Suggestions(
        day=day,
        count=count,
        picks=out,
        together_minutes=together_minutes([c.steps for c in picked], kit) if picked else 0,
        one_by_one_minutes=one_by_one,
        pool=len(everyone),
        free_days=free,
    )


def times_for(kitchen: Kitchen, recipe_ids: list[int]) -> tuple[int, int]:
    """(together, one by one) minutes for these recipes, as the kitchen is now. A recipe with no
    steps adds nothing."""
    kit = equipment_of(kitchen)
    found = {c.recipe_id: c for c in _candidates(kitchen, kit)}
    chosen = [found[r] for r in recipe_ids if r in found]
    return (
        together_minutes([c.steps for c in chosen], kit) if chosen else 0,
        sum(c.minutes for c in chosen),
    )
