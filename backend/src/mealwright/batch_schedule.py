"""The schedule for a Batch cook (Experimental) session (0.8 wave 6, B3; cabledrawer 28 Oct and
11 Nov): one plan across the session's recipes, worked out from what each step needs (B1's
timings, 0.7's step-ingredient links) and the household's kitchen.

Pure: plain data in, plain data out, no database, no clock, nothing sent anywhere. The same input
always gives the same schedule.

**What it does** (spec section 6, "Batch cook (Experimental)"):

1. **Shared prep first where it saves time.** The same chopping or grinding of the same
   ingredients in two recipes becomes one task ("Chop 3 onions: 2 for Chicken chettinad, 1 for
   Sambar"), with the amounts from the ingredient lines. It takes the longest of the steps it
   replaces plus a minute for each other recipe it serves (a guess: proposed, for cabledrawer).
2. **Waiting steps start as early as possible; hands-on steps fill the waits.** Every task is put
   at the earliest time it can go (a hands-on task may sit inside a gap a wait left).
3. **Each recipe's steps keep their order.** A step starts after the one before it ends.

**Hard rules** (property-tested):

- Never two hands-on tasks at once (one pair of hands).
- Never more hob rings, pressure cookers or ovens in use at once than the kitchen has. A waiting
  step holds its hob ring, pressure cooker or oven all the time it waits.
- A step that needs equipment the kitchen has none of (no oven) still gets scheduled: **alone**,
  with nothing else going on at the same time, and marked `lacks` so the screen can say so.
- Steps that wait four hours or more at the start of a recipe (soak, marinate overnight) are
  not part of the day: they are `before`, for Today the evening before (wave 5's Start tonight).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

Hands = Literal["hands", "waiting"]
Equipment = Literal["hob", "pressure", "oven", "none"]

# A shared task takes this much longer for each other recipe it serves (proposed, for cabledrawer).
EXTRA_PER_RECIPE = 1

_PREP = re.compile(
    r"\b(chop|grind|slice|dice|mince|grate|blend|peel|crush|pound|shred|cut)\w*", re.IGNORECASE
)
_SPACES = re.compile(r"\s+")


@dataclass(frozen=True)
class LineIn:
    """An ingredient line a step uses."""

    id: int
    food_id: int | None
    food_name: str | None
    amount_milli: int | None  # thousandths of the unit; None when no amount
    unit: str | None  # None with an amount: a count


@dataclass(frozen=True)
class StepIn:
    id: int
    text: str
    hands: Hands
    minutes: int
    equipment: Equipment
    line_ids: tuple[int, ...] = ()
    ahead: bool = False  # a wait of four hours or more (soak, marinate overnight)


@dataclass(frozen=True)
class RecipeIn:
    id: int
    name: str
    steps: tuple[StepIn, ...]
    lines: tuple[LineIn, ...] = ()


@dataclass(frozen=True)
class KitchenIn:
    hob_rings: int
    pressure_cookers: int
    oven: bool

    def capacity(self, equipment: str) -> int:
        if equipment == "hob":
            return self.hob_rings
        if equipment == "pressure":
            return self.pressure_cookers
        if equipment == "oven":
            return 1 if self.oven else 0
        return 0


@dataclass(frozen=True)
class Task:
    id: str  # "t1", "t2"... in the order they start
    kind: Literal["prep", "step"]  # "prep" is shared prep (one task for several recipes' steps)
    title: str  # a step's own words, or the shared prep's sentence
    recipes: tuple[int, ...]  # the recipe(s) it is for (several for shared prep)
    steps: tuple[int, ...]  # the recipe step(s) it is
    start: int  # minutes from the start of the session
    end: int
    hands: Hands
    equipment: Equipment
    slot: int | None  # which hob ring (1...), pressure cooker or oven it uses; None for none
    lacks: bool  # needs equipment the kitchen has none of: done alone


@dataclass(frozen=True)
class Before:
    """A soaking or overnight step left for the day before: it is not part of the day."""

    recipe_id: int
    step_id: int
    text: str
    minutes: int


@dataclass(frozen=True)
class Schedule:
    tasks: tuple[Task, ...]
    before: tuple[Before, ...]
    total_minutes: int


@dataclass
class _Node:
    index: int
    kind: Literal["prep", "step"]
    title: str
    recipes: list[int]
    steps: list[int]
    minutes: int
    hands: Hands
    equipment: Equipment
    after: set[int] = field(default_factory=set)  # indexes of nodes that must end first


# --- Shared prep ------------------------------------------------------------------------------


def _amount_text(milli: int) -> str:
    whole, rest = divmod(milli, 1000)
    if rest == 0:
        return str(whole)
    return f"{milli / 1000:.2f}".rstrip("0").rstrip(".")


def _plural(name: str, milli: int) -> str:
    name = name.strip().lower()
    if milli == 1000 or name.endswith("s"):
        return name
    return name + "s"


def _prep_verb(step: StepIn) -> str | None:
    if step.hands != "hands" or step.equipment != "none" or not step.line_ids:
        return None
    found = _PREP.search(step.text)
    return found.group(1).lower() if found else None


def _shared_title(
    verb: str,
    members: list[tuple[RecipeIn, StepIn]],
) -> str:
    """ "Chop 3 onions: 2 for Chicken chettinad, 1 for Sambar" (the amounts from the lines the
    steps use); the plainer "Chop onion and tomato for A and B" when the amounts can't be added."""
    word = verb.capitalize()
    foods: dict[int, str] = {}
    per_recipe: list[tuple[str, list[LineIn]]] = []
    for recipe, step in members:
        by_id = {line.id: line for line in recipe.lines}
        used = [by_id[i] for i in step.line_ids if i in by_id and by_id[i].food_id is not None]
        for line in used:
            if line.food_id is not None:
                foods.setdefault(line.food_id, line.food_name or "")
        per_recipe.append((recipe.name, used))
    names = [n for n in foods.values() if n]
    if len(foods) == 1:
        amounts: list[tuple[str, int | None, str | None]] = []
        for name, used in per_recipe:
            units = {line.unit for line in used}
            if len(units) == 1 and all(line.amount_milli is not None for line in used) and used:
                amounts.append((name, sum(line.amount_milli or 0 for line in used), units.pop()))
            else:
                amounts.append((name, None, None))
        if all(a[1] is not None for a in amounts) and len({a[2] for a in amounts}) == 1:
            unit = amounts[0][2]
            total = sum(a[1] or 0 for a in amounts)
            label = names[0] if names else "ingredient"
            if unit is None:
                head = f"{word} {_amount_text(total)} {_plural(label, total)}"
                parts = ", ".join(f"{_amount_text(a[1] or 0)} for {a[0]}" for a in amounts)
            else:
                head = f"{word} {_amount_text(total)} {unit} {label.lower()}"
                parts = ", ".join(f"{_amount_text(a[1] or 0)} {unit} for {a[0]}" for a in amounts)
            return f"{head}: {parts}"
    things = _joined([n.lower() for n in names]) if names else "ingredients"
    return f"{word} {things} for {_joined([r.name for r, _ in members])}"


def _joined(items: list[str]) -> str:
    if len(items) <= 1:
        return "".join(items)
    return ", ".join(items[:-1]) + " and " + items[-1]


# --- The graph ----------------------------------------------------------------------------------


def _acyclic(nodes: list[_Node]) -> bool:
    waiting = {n.index: len(n.after) for n in nodes}
    after_of: dict[int, list[int]] = {n.index: [] for n in nodes}
    for n in nodes:
        for a in n.after:
            after_of[a].append(n.index)
    ready = [i for i, c in waiting.items() if c == 0]
    seen = 0
    while ready:
        i = ready.pop()
        seen += 1
        for j in after_of[i]:
            waiting[j] -= 1
            if waiting[j] == 0:
                ready.append(j)
    return seen == len(nodes)


def _build(
    recipes: list[RecipeIn], skip: set[int]
) -> tuple[list[_Node], dict[int, tuple[RecipeIn, StepIn]]]:
    """One node per step (not those left for the day before), the chain of each recipe in order,
    then shared prep merged where it can be without making a loop."""
    nodes: list[_Node] = []
    where: dict[int, tuple[RecipeIn, StepIn]] = {}
    node_of: dict[int, int] = {}  # step id -> node index
    for recipe in recipes:
        previous: int | None = None
        for step in recipe.steps:
            if step.id in skip:
                continue
            node = _Node(
                index=len(nodes),
                kind="step",
                title=_SPACES.sub(" ", step.text).strip(),
                recipes=[recipe.id],
                steps=[step.id],
                minutes=step.minutes,
                hands=step.hands,
                equipment=step.equipment,
            )
            if previous is not None:
                node.after.add(previous)
            previous = node.index
            nodes.append(node)
            node_of[step.id] = node.index
            where[step.id] = (recipe, step)
    return nodes, _merge_prep(recipes, nodes, node_of, where)


def _merge_prep(
    recipes: list[RecipeIn],
    nodes: list[_Node],
    node_of: dict[int, int],
    where: dict[int, tuple[RecipeIn, StepIn]],
) -> dict[int, tuple[RecipeIn, StepIn]]:
    groups: dict[tuple[str, frozenset[int]], list[tuple[RecipeIn, StepIn]]] = {}
    for recipe in recipes:
        seen: set[tuple[str, frozenset[int]]] = set()
        by_id = {line.id: line for line in recipe.lines}
        for step in recipe.steps:
            if step.id not in node_of:
                continue
            verb = _prep_verb(step)
            foods = frozenset(
                food
                for food in (by_id[i].food_id for i in step.line_ids if i in by_id)
                if food is not None
            )
            if verb is None or not foods:
                continue
            key = (verb, foods)
            if key in seen:  # one step of a recipe per group
                continue
            seen.add(key)
            groups.setdefault(key, []).append((recipe, step))
    for (verb, _foods), members in sorted(groups.items(), key=lambda g: (g[0][0], sorted(g[0][1]))):
        if len(members) < 2:
            continue
        indexes = [node_of[s.id] for _, s in members]
        if len(set(indexes)) < len(indexes) or any(nodes[i].kind == "prep" for i in indexes):
            continue  # a step already merged into another group
        keep = min(indexes)
        saved = [(i, set(nodes[i].after)) for i in range(len(nodes))]
        keep_node = nodes[keep]
        old = (keep_node.title, keep_node.recipes, keep_node.steps, keep_node.minutes)
        gone = [i for i in indexes if i != keep]
        for i in gone:
            keep_node.after |= nodes[i].after
        keep_node.after -= set(indexes)
        for n in nodes:
            if n.index not in indexes and any(i in n.after for i in indexes):
                n.after -= set(indexes)
                n.after.add(keep)
        keep_node.kind = "prep"
        keep_node.recipes = [r.id for r, _ in members]
        keep_node.steps = [s.id for _, s in members]
        keep_node.title = _shared_title(verb, members)
        keep_node.minutes = max(s.minutes for _, s in members) + EXTRA_PER_RECIPE * (
            len(members) - 1
        )
        live = [n for n in nodes if n.index not in gone]
        if not _acyclic(live):  # it would make one recipe wait for itself: leave them apart
            for i, after in saved:
                nodes[i].after = after
            keep_node.kind = "step"
            keep_node.title, keep_node.recipes, keep_node.steps, keep_node.minutes = old
            continue
        for i in gone:
            nodes[i].kind = "step"
            nodes[i].steps = []  # gone: no longer a task
            nodes[i].after = set()
        for n in nodes:
            n.after -= set(gone)
        for _, s in members:
            node_of[s.id] = keep
    return where


# --- Placing ------------------------------------------------------------------------------------


@dataclass
class _Placed:
    start: int
    end: int
    hands: bool
    equipment: str
    slot: int | None
    lacks: bool


def _overlap(a_start: int, a_end: int, b: _Placed) -> bool:
    return a_start < b.end and b.start < a_end


def _slot_for(
    placed: list[_Placed], equipment: str, capacity: int, start: int, end: int
) -> int | None:
    """The first slot (1...) of this kind of equipment that is free for the whole time."""
    for slot in range(1, capacity + 1):
        if not any(
            p.equipment == equipment and p.slot == slot and _overlap(start, end, p) for p in placed
        ):
            return slot
    return None


def _earliest(
    node: _Node, ready: int, placed: list[_Placed], kit: KitchenIn
) -> tuple[int, int | None, bool]:
    """The earliest start at or after `ready`, the slot it takes, and whether it lacks the
    equipment. Resources free up only when a placed task ends, so those are the only times to
    try."""
    capacity = kit.capacity(node.equipment) if node.equipment != "none" else 0
    lacks = node.equipment != "none" and capacity == 0
    hands = node.hands == "hands"
    tries = sorted({ready} | {p.end for p in placed if p.end > ready})
    for start in tries:
        end = start + node.minutes
        blockers = [p for p in placed if _overlap(start, end, p)]
        if lacks:
            if blockers:
                continue
            return start, None, True
        if any(p.lacks for p in blockers):
            continue
        if hands and any(p.hands for p in blockers):
            continue
        slot: int | None = None
        if node.equipment != "none":
            slot = _slot_for(placed, node.equipment, capacity, start, end)
            if slot is None:
                continue
        return start, slot, False
    raise AssertionError("a start after every task always fits")  # pragma: no cover


def _remaining(nodes: list[_Node]) -> dict[int, int]:
    """Each node's own minutes plus the longest chain after it (the critical path)."""
    after_of: dict[int, list[int]] = {n.index: [] for n in nodes}
    for n in nodes:
        for a in n.after:
            after_of[a].append(n.index)
    by_index = {n.index: n for n in nodes}
    memo: dict[int, int] = {}

    def rest(i: int) -> int:
        if i not in memo:
            node = by_index[i]
            memo[i] = node.minutes + max((rest(j) for j in after_of[i]), default=0)
        return memo[i]

    return {n.index: rest(n.index) for n in nodes}


def _leading(recipe: RecipeIn) -> list[StepIn]:
    """The steps at the start of a recipe that wait four hours or more: left for the day before."""
    found: list[StepIn] = []
    for step in recipe.steps:
        if not step.ahead or step.hands != "waiting" or step.equipment != "none":
            break
        found.append(step)
    # Everything is a wait: keep the last as a step, so the recipe is not empty.
    if len(found) == len(recipe.steps):
        found = found[:-1]
    return found


def schedule(recipes: list[RecipeIn], kit: KitchenIn) -> Schedule:
    """The session's schedule (see the module's words). `recipes` in the order of the session."""
    before: list[Before] = []
    skip: set[int] = set()
    for recipe in recipes:
        for step in _leading(recipe):
            skip.add(step.id)
            before.append(Before(recipe.id, step.id, step.text, step.minutes))
    nodes, _where = _build(recipes, skip)
    live = [n for n in nodes if n.steps]
    longest = _remaining(live)
    ends: dict[int, int] = {}
    placed: list[_Placed] = []
    out: list[tuple[int, int, _Node, _Placed]] = []
    left = {n.index for n in live}
    while left:
        best: tuple[tuple[int, int, int, int], _Node, int, int | None, bool] | None = None
        for n in live:
            if n.index not in left or any(a not in ends for a in n.after):
                continue
            ready = max((ends[a] for a in n.after), default=0)
            start, slot, lacks = _earliest(n, ready, placed, kit)
            key = (start, 0 if n.hands == "waiting" else 1, -longest[n.index], n.index)
            if best is None or key < best[0]:
                best = (key, n, start, slot, lacks)
        if best is None:  # pragma: no cover (a graph with no loop always has a task ready)
            raise RuntimeError("no task is ready")
        _key, node, start, slot, lacks = best
        end = start + node.minutes
        spot = _Placed(start, end, node.hands == "hands", node.equipment, slot, lacks)
        placed.append(spot)
        ends[node.index] = end
        left.discard(node.index)
        out.append((start, node.index, node, spot))
    out.sort(key=lambda o: (o[0], o[1]))
    tasks = tuple(
        Task(
            id=f"t{n}",
            kind=node.kind,
            title=node.title,
            recipes=tuple(node.recipes),
            steps=tuple(node.steps),
            start=start,
            end=spot.end,
            hands=node.hands,
            equipment=node.equipment,
            slot=spot.slot,
            lacks=spot.lacks,
        )
        for n, (start, _i, node, spot) in enumerate(out, start=1)
    )
    total = max((t.end for t in tasks), default=0)
    return Schedule(tasks=tasks, before=tuple(before), total_minutes=total)
