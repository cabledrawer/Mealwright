"""The deduction engine (0.7 K2; spec section 2, "Cooking — how deduction works", agreed 17 Oct).

`work_out` is read-only: for a recipe cooked for some portions it works out what "Cooked it"
would take from the pantry, one row per ingredient, and what it can't decide itself:

1. Lines and stock meet by ingredient (food). Lines of one ingredient are added up.
2. Scale: needed = recipe amount x portions cooked / recipe servings (no servings: as written).
   A counted ingredient is rounded to the nearest half (spec "Count foods"; a half at least).
3. Convert only when the units differ: `mealwright.conversions` does it, with the household's
   answers over the bundled table. An unknown conversion is a question to ask once (`ask`).
4. The packet that goes off first, fridge and cupboard before the freezer (`stock.plan_take`).
   The freezer only when the person says so (`from_freezer`); the row says what is in it.
5. (The review, with Use switches and Used/Left, is the screen's: `Choice` is what it sends.)
6. A staple is never taken. Stock never goes below zero: the shortfall is `short` ("add to
   list"). A row with nothing in the pantry starts switched off.
7. Batch cooks deduct once (`mealwright.cooking`).

Also: an ingredient with no stock (or not enough) takes the rest from the ingredients it has a
"Can use instead" link to (spec "Close cousins"); a recipe used as an ingredient is taken from
the pantry when it is made ahead and has stock, and with none the row offers "Make it first?".

Proposed, for cabledrawer (one rule each, easy to change): which packet when two go off the same
day is the one added first (the pantry's own rule); a part-used packet is kept exact, never
rounded; stand-ins are used in id order and only when they are counted the same way.
"""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import status
from pydantic import BaseModel
from sqlalchemy import select

from mealwright import methods
from mealwright.amounts import MILLI, TooBig, checked, plural, round_half_up, unit_family, unit_size
from mealwright.api.v1.context import Kitchen
from mealwright.api.v1.recipe_schemas import amount_text
from mealwright.api.v1.schemas import AmountOut, Answer, Ask, Ref
from mealwright.conversions import AskOnce, UnitAmount, to_base_milli
from mealwright.errors import NOTHING_TO_TAKE_FROM, Problem
from mealwright.foods import BASE_UNITS, amount_out, ask, find, known, usual_size, visible
from mealwright.history import as_utc
from mealwright.household import cup_ml, places
from mealwright.models import (
    Food,
    FoodSize,
    FoodStandIn,
    Recipe,
    RecipeLine,
    StockLot,
)
from mealwright.recipes import live_recipes
from mealwright.stock import LotView, lots_of, opened_lots, place_kinds, plan_take

STAPLES_NOT_COUNTED = "Staples aren’t counted, so nothing is taken."

RowStatus = Literal[
    "take",  # something to take from the pantry
    "none_in_pantry",  # nothing in the pantry (and no stand-in): off to start with
    "staple",  # never taken
    "ask",  # an "ask once" question comes first
    "no_amount",  # no amount that can be worked out ("salt to taste", a pinch)
    "not_linked",  # the line points at no ingredient
    "make_first",  # a recipe used as an ingredient, with no pantry ingredient: "Make it first?"
]


# --- What the review sends back -------------------------------------------------------------


@dataclass
class Choice:
    """The person's say on one row. `used` and `left` are in thousandths of the ingredient's
    base unit; at most one of them is set (the screen's Used / Left switch)."""

    use: bool = True
    used_milli: int | None = None
    left_milli: int | None = None
    from_freezer: bool = False
    add_to_list: bool | None = None  # None: as proposed
    bought: bool = False  # "Bought some — used them": kept on the record, changes no stock


# --- Working out ------------------------------------------------------------------------------


@dataclass
class Take:
    food: Food
    stand_in: bool
    lots: list[tuple[StockLot, int]]
    before: int  # the ingredient's whole stock before this take
    amount: int
    used_all: set[int] = field(default_factory=set)  # packets left with under 2 %: taken whole


@dataclass
class Row:
    key: str
    lines: list[RecipeLine]
    food: Food | None = None
    inner: Recipe | None = None  # the recipe a made-ahead ingredient (or a make-first row) is
    status: RowStatus = "take"
    needed: int | None = None  # worked out for the portions cooked
    wanted: int | None = None  # what to take: `needed`, or what the person entered
    entered: Literal["used", "left"] | None = None
    entered_milli: int | None = None  # the amount typed: what was used, or what is left
    takes: list[Take] = field(default_factory=list)
    use_default: bool = True
    use: bool = True
    short: int = 0
    make_first: bool = False
    in_freezer: int = 0
    from_freezer: bool = False
    add_to_list: bool = False  # the offer to put something on the shopping list is ticked
    list_milli: int = 0  # what would go on: the shortfall, or for running low a small pack
    running_low: bool = False  # what is left is at or below the ingredient's running-low level
    asked: AskOnce | None = None
    estimate: bool = False  # the recipe and the pantry count it differently: `needed` is a guess
    asked_need: dict[str, int] = field(default_factory=dict)  # family -> recipe side, thousandths
    half_milli: int = 0  # about half of the packet that goes off first, in the pantry's unit
    count_note: tuple[int, str] | None = None  # "2 cloves" noted on a line with no amount
    bought: bool = False

    @property
    def taken(self) -> int:
        return sum(take.amount for take in self.takes)


@dataclass
class Worked:
    recipe: Recipe
    portions: int
    rows: list[Row]


def scaled(need: int, recipe: Recipe, portions: int) -> int:
    """Rule 2: what the recipe's amount comes to for the portions cooked."""
    if not recipe.serves:
        return need
    return round_half_up(Decimal(need) * portions / recipe.serves)


def to_halves(milli: int) -> int:
    """A counted ingredient to the nearest half (never none when some is needed)."""
    if milli <= 0:
        return 0
    return max(round_half_up(Decimal(milli) / 500) * 500, 500)


def _line_need(
    line: RecipeLine,
    food: Food,
    sizes: dict[int, FoodSize],
    answers: list[Answer],
    kitchen: Kitchen,
) -> int | None:
    """What one line asks for, in the ingredient's units (thousandths), or None when there is
    no amount to work out. Raises `AskOnce` when a conversion is not known."""
    if line.amount_milli is None:
        return None
    if line.size_id is not None:
        size = sizes.get(line.size_id)
        if size is None or size.food_id != food.id:
            return None
        return line.amount_milli * size.amount_milli // MILLI
    unit = line.unit or "count"
    if unit_family(unit) is None:  # a pinch
        return None
    return to_base_milli(
        UnitAmount(Decimal(line.amount_milli) / MILLI, unit),
        food.counted_as,  # type: ignore[arg-type]
        known(kitchen, food, answers),
        cup_ml(kitchen.household),
    )


def _note_asked(row: Row, line: RecipeLine, kitchen: Kitchen) -> None:
    """What the line asks for on the recipe's side (g, ml or items, thousandths), so the review
    can ask for the amount in the pantry's unit and work out the conversion from the answer."""
    if line.amount_milli is None:
        return
    unit = line.unit or "count"
    family = unit_family(unit)
    if family is None:
        return
    base = Decimal(line.amount_milli) * unit_size(unit, cup_ml(kitchen.household))
    row.asked_need[family] = row.asked_need.get(family, 0) + int(base)


COUNT_WORDS = re.compile(
    r"^\s*(?P<n>[0-9]{1,4}(?:\.[0-9]{1,3})?)?\s*(?P<frac>[½¼¾])?\s+(?P<word>cloves?|sprigs?)\b",
    re.IGNORECASE,
)
FRACTIONS = {"½": 500, "¼": 250, "¾": 750}


def _count_note(row: Row, recipe: Recipe, portions: int) -> tuple[int, str] | None:
    """ "2 cloves" in the note of a line with no amount (F89): how many, scaled to the portions,
    and the size word ("clove"). Only for a row of one line."""
    if len(row.lines) != 1 or not row.lines[0].note:
        return None
    found = COUNT_WORDS.match(row.lines[0].note)
    if found is None or (found["n"] is None and found["frac"] is None):
        return None
    count = int(Decimal(found["n"] or 0) * MILLI) + FRACTIONS.get(found["frac"] or "", 0)
    word = found["word"].lower().removesuffix("s")
    return (to_halves(scaled(count, recipe, portions)), word) if count > 0 else None


def _rows(
    kitchen: Kitchen,
    recipe: Recipe,
    portions: int,
    answers: list[Answer],
    skip: frozenset[int] = frozenset(),
    method_id: int | None = None,
) -> list[Row]:
    """Rule 1 and 2 and 3: one row per ingredient, in the order the recipe first uses it.
    `skip`: Optional lines the person will not use (R3), left out as if they weren't there.
    `method_id`: the way of cooking it the meal was planned with (M2); empty, the first."""
    db, hid = kitchen.db, kitchen.household_id
    all_methods = methods.methods_of(db, recipe.id)
    method = methods.named(all_methods, method_id)
    lines = [
        line
        for line in db.scalars(
            select(RecipeLine)
            .where(
                RecipeLine.recipe_id == recipe.id,
                RecipeLine.household_id == hid,
                RecipeLine.kind == "ingredient",
            )
            .order_by(RecipeLine.position, RecipeLine.id)
        )
        if line.id not in skip and methods.in_method(line, all_methods, method)
    ]
    foods = {
        food.id: food
        for food in db.scalars(select(Food).where(Food.household_id == hid))
        if visible(food)
    }
    recipes = live_recipes(kitchen)
    size_ids = {line.size_id for line in lines if line.size_id}
    sizes = {s.id: s for s in db.scalars(select(FoodSize).where(FoodSize.id.in_(size_ids)))}
    rows: dict[str, Row] = {}
    for line in lines:
        food: Food | None = None
        inner: Recipe | None = None
        if line.food_id is not None:
            food = foods.get(line.food_id)
            key = f"food:{line.food_id}"
        elif line.sub_recipe_id is not None:
            inner = recipes.get(line.sub_recipe_id)
            if inner is not None and inner.made_ahead and inner.homemade_food_id in foods:
                food = foods[inner.homemade_food_id]
                key = f"food:{food.id}"
            else:
                key = f"recipe:{line.sub_recipe_id}"
        else:
            key = f"line:{line.id}"
        if food is None and inner is None:
            key = f"line:{line.id}"
        row = rows.setdefault(key, Row(key=key, lines=[], food=food, inner=inner))
        row.lines.append(line)
        if inner is not None and row.inner is None:
            row.inner = inner
        if food is None:
            row.status = "make_first" if inner is not None else "not_linked"
            row.make_first = inner is not None
            row.use_default = False
            continue
        if food.staple:
            row.status, row.use_default = "staple", False
            continue
        if row.asked is not None:
            _note_asked(row, line, kitchen)  # every line counts in what the answer is about
            continue
        try:
            need = _line_need(line, food, sizes, answers, kitchen)
        except AskOnce as needed:
            row.asked = needed
            _note_asked(row, line, kitchen)
            continue
        except TooBig:
            continue
        if need is not None:
            row.needed = (row.needed or 0) + need
            family = unit_family(line.unit or "count")
            if line.size_id is None and family is not None and family != food.counted_as:
                row.estimate = True
    for row in rows.values():
        if row.food is None or row.status == "staple":
            continue
        if row.asked is not None:
            row.status = "ask"
            row.needed = None
            row.asked_need = {
                family: scaled(milli, recipe, portions) for family, milli in row.asked_need.items()
            }
        elif row.needed is None:
            row.status, row.use_default = "no_amount", False
            row.count_note = _count_note(row, recipe, portions)
        else:
            try:
                value = scaled(row.needed, recipe, portions)
                row.needed = checked(to_halves(value) if row.food.counted_as == "count" else value)
            except TooBig:
                row.status, row.needed, row.use_default = "no_amount", None, False
    return list(rows.values())


class Pool:
    """The packets, read once, and what each has left as the rows take from it."""

    def __init__(self, kitchen: Kitchen, food_ids: set[int] | None = None) -> None:
        self.kitchen = kitchen
        self.kinds = place_kinds(kitchen)
        self.lots: dict[int, list[StockLot]] = {}
        self.loaded: set[int] = set()
        self.opened: set[int] = set()
        self.size_milli: dict[int, int] = {}
        self.left: dict[int, int] = {}
        self.ensure(food_ids or set())

    def ensure(self, food_ids: set[int]) -> None:
        """Read the packets of these ingredients, if not read yet (one pool can serve every
        recipe of a meal, so two recipes never take the same grams)."""
        new = food_ids - self.loaded
        if not new:
            return
        self.loaded |= new
        everything = lots_of(self.kitchen, new)
        for lot in everything:
            self.lots.setdefault(lot.food_id, []).append(lot)
            self.left[lot.id] = lot.amount_milli
        self.opened |= opened_lots(self.kitchen, everything)
        wanted = {lot.size_id for lot in everything if lot.size_id}
        for size in self.kitchen.db.scalars(select(FoodSize).where(FoodSize.id.in_(wanted))):
            self.size_milli[size.id] = size.amount_milli

    def freezer(self, lot: StockLot) -> bool:
        return self.kinds.get(lot.place_id) == "freezer"

    def total(self, food_id: int, with_freezer: bool = True) -> int:
        return sum(
            self.left[lot.id]
            for lot in self.lots.get(food_id, ())
            if with_freezer or not self.freezer(lot)
        )

    def half_packet(self, food: Food) -> int:
        """About half of the packet that goes off first (its size, else what is left in it), in
        the ingredient's unit, thousandths: halves of a count, whole g or ml. 0 when there is no
        packet outside the freezer."""
        mine = self.lots.get(food.id, [])
        views = [
            LotView(
                lot.id,
                self.left[lot.id],
                lot.use_by,
                as_utc(lot.added_at),
                self.freezer(lot),
                lot.id in self.opened,
            )
            for lot in mine
            if self.left[lot.id] > 0
        ]
        plan, _ = plan_take(views, 1, False)
        if not plan:
            return 0
        lot = next(each for each in mine if each.id == plan[0][0])
        whole = (self.size_milli.get(lot.size_id) if lot.size_id else None) or self.left[lot.id]
        step = 500 if food.counted_as == "count" else MILLI
        return round_half_up(Decimal(whole) / 2 / step) * step

    def take(
        self, food: Food, amount: int, from_freezer: bool, stand_in: bool, tidy: bool = True
    ) -> Take | None:
        """Rule 4: the packet that goes off first. None when nothing could be taken. With `tidy`,
        a packet left with under 2 % of its size is taken whole ("Used it all", cabledrawer 31
        Oct)."""
        mine = self.lots.get(food.id, [])
        views = [
            LotView(
                lot.id,
                self.left[lot.id],
                lot.use_by,
                as_utc(lot.added_at),
                self.freezer(lot),
                lot.id in self.opened,
            )
            for lot in mine
            if self.left[lot.id] > 0
        ]
        plan, _ = plan_take(views, amount, from_freezer)
        if not plan:
            return None
        by_id = {lot.id: lot for lot in mine}
        before = self.total(food.id)
        used_all: set[int] = set()
        taken_lots: list[tuple[StockLot, int]] = []
        for lot_id, taken in plan:
            lot = by_id[lot_id]
            rest = self.left[lot_id] - taken
            size = self.size_milli.get(lot.size_id) if lot.size_id else None
            if tidy and size and rest > 0 and rest * 50 < size:
                taken, used_all = taken + rest, used_all | {lot_id}
            self.left[lot_id] -= taken
            taken_lots.append((lot, taken))
        return Take(food, stand_in, taken_lots, before, sum(t for _, t in taken_lots), used_all)


def _stand_ins(kitchen: Kitchen, foods: set[int]) -> dict[int, list[int]]:
    found: dict[int, list[int]] = {}
    for link in kitchen.db.scalars(
        select(FoodStandIn).where(
            FoodStandIn.household_id == kitchen.household_id, FoodStandIn.food_id.in_(foods)
        )
    ):
        found.setdefault(link.food_id, []).append(link.stand_in_id)
    return {key: sorted(ids) for key, ids in found.items()}


def _refuse(code: str, detail: str) -> Problem:
    return Problem(status.HTTP_422_UNPROCESSABLE_CONTENT, code, detail)


def work_out(
    kitchen: Kitchen,
    recipe: Recipe,
    portions: int,
    answers: list[Answer] | None = None,
    choices: dict[str, Choice] | None = None,
    pool: Pool | None = None,
    skip: frozenset[int] = frozenset(),
    method_id: int | None = None,
) -> Worked:
    """What cooking `portions` of the recipe takes from the pantry. Read-only. `skip`: the
    Optional lines the meal will not use (R3). With `choices`
    (a confirm) the rows follow them, and a row that still needs its question answered is
    refused with the "ask once" 409; without, every row is as it would start on the review."""
    answers = answers or []
    for answer in answers:
        find(kitchen, answer.food_id)  # a food from another household is a 404
    rows = _rows(kitchen, recipe, portions, answers, skip, method_id)
    confirming = choices is not None
    choices = choices or {}
    by_key = {row.key: row for row in rows}
    for key in choices:
        if key not in by_key:
            raise _refuse("unknown_row", "That ingredient isn’t in this recipe.")  # proposed

    food_ids = {row.food.id for row in rows if row.food is not None}
    stand_ins = _stand_ins(kitchen, food_ids)
    others = {
        food.id: food
        for food in kitchen.db.scalars(
            select(Food).where(
                Food.household_id == kitchen.household_id,
                Food.id.in_({i for ids in stand_ins.values() for i in ids}),
            )
        )
        if visible(food)
    }
    pool = pool or Pool(kitchen)
    pool.ensure(food_ids | set(others))
    # Pass 1: each row's own stock.
    for row in rows:
        choice = choices.get(row.key)
        if row.food is None or row.status == "staple":
            if choice is not None and choice.bought:
                if row.status == "staple":
                    raise _refuse("staple", STAPLES_NOT_COUNTED)
                raise _refuse("no_ingredient", NOTHING_TO_TAKE_FROM)
            if choice is not None and (
                choice.used_milli is not None or choice.left_milli is not None
            ):
                if row.status == "staple":
                    raise _refuse("staple", STAPLES_NOT_COUNTED)
                raise _refuse("no_ingredient", NOTHING_TO_TAKE_FROM)
            continue
        food = row.food
        row.from_freezer = bool(choice and choice.from_freezer)
        own = pool.total(food.id, row.from_freezer)
        row.use_default = row.status in ("take", "ask") and own > 0
        # A row nobody chose on is tried (it takes what there is, stand-ins too); its switch is
        # settled below, once it is known whether anything could be taken.
        row.use = choice.use if choice is not None else True
        row.bought = choice is not None and choice.bought
        if row.status in ("ask", "no_amount") and own > 0:
            row.half_milli = pool.half_packet(food)
        row.wanted = row.needed
        if choice is not None and choice.used_milli is not None:
            row.wanted, row.entered = checked(choice.used_milli), "used"
            row.entered_milli = choice.used_milli
        elif choice is not None and choice.left_milli is not None:
            if choice.left_milli > own:
                raise _refuse("left_too_much", "That’s more than there is.")  # proposed
            row.wanted, row.entered = own - choice.left_milli, "left"
            row.entered_milli = choice.left_milli
        if (
            confirming
            and row.use
            and row.asked is not None
            and row.entered is None
            and (choice is not None or row.use_default)
        ):
            raise ask(kitchen, food, row.asked.kind)
        if row.wanted is None or row.wanted <= 0:
            continue
        if confirming and not row.use:
            continue
        taken = pool.take(food, row.wanted, row.from_freezer, False, row.entered is None)
        if taken is not None:
            row.takes.append(taken)

    # Pass 2: an ingredient with none at all (not in the freezer either) is taken from its "Can
    # use instead" ingredients. With some but not enough, the rest is a shortfall, never mixed
    # with a stand-in (cabledrawer 31 Oct).
    for row in rows:
        if row.food is None or not row.wanted:
            continue
        if confirming and not row.use:
            continue
        if row.takes or pool.total(row.food.id) > 0:
            continue
        short = row.wanted
        for other_id in stand_ins.get(row.food.id, ()):
            other = others.get(other_id)
            if short <= 0 or other is None or other.counted_as != row.food.counted_as:
                continue
            taken = pool.take(other, short, row.from_freezer, True, row.entered is None)
            if taken is not None:
                row.takes.append(taken)
                short -= taken.amount

    # Rule 6, the freezer and running low: what is missing, what waits in the freezer, and what
    # the offer to add to the shopping list would add.
    low_ids = {
        row.food.id
        for row in rows
        if row.food is not None and row.food.running_low_milli is not None and not row.food.staple
    }
    smallest: dict[int, int] = {}
    if low_ids:
        for size in kitchen.db.scalars(select(FoodSize).where(FoodSize.food_id.in_(low_ids))):
            smallest[size.food_id] = min(
                smallest.get(size.food_id, size.amount_milli), size.amount_milli
            )

    for row in rows:
        if row.food is None or row.wanted is None:
            continue
        # Use does not change what is offered (cabledrawer 31 Oct: the tick is its own choice): a
        # row switched off is given the preview's answer afterwards (`offer_as_previewed`).
        took, left_after = row.taken, pool.total(row.food.id)
        row.short = max(row.wanted - took, 0)
        if row.status == "take" and not took and not row.entered:
            row.status = "none_in_pantry"
        if row.inner is not None and row.short > 0:
            row.make_first = True
        if not row.from_freezer and row.short > 0:
            row.in_freezer = sum(
                pool.left[lot.id] for lot in pool.lots.get(row.food.id, ()) if pool.freezer(lot)
            )
        # What would go on the list, and whether it starts ticked (cabledrawer 31 Oct).
        default = False
        if row.short > 0 and row.inner is None:
            row.list_milli = row.short
            default = not (row.in_freezer > 0 and not took)  # in the freezer: in the house
        elif (
            took > 0
            and row.food.running_low_milli is not None
            and not row.food.staple
            and left_after <= row.food.running_low_milli
        ):
            row.running_low = True
            row.list_milli = smallest.get(row.food.id) or row.food.running_low_milli
        picked = choices.get(row.key)
        row.add_to_list = default
        if row.list_milli > 0 and picked is not None and picked.add_to_list is not None:
            row.add_to_list = picked.add_to_list
        if picked is not None and picked.bought:
            row.add_to_list = False  # bought some: there is nothing to buy
    for row in rows:
        if row.status in ("take", "none_in_pantry"):
            row.use_default = bool(row.takes)  # nothing to take (or only the freezer): off
        if row.food is not None and row.status != "staple" and row.key not in choices:
            row.use = row.use_default
    return Worked(recipe, portions, rows)


def off_rows(worked: list[Worked], choices: list[dict[str, Choice]]) -> list[Row]:
    """The rows with Use switched off that could take something (an ingredient, not a staple,
    with an amount): only these are given the preview's answer."""
    return [
        row
        for each, picked in zip(worked, choices, strict=True)
        for row in each.rows
        if row.key in picked
        and not picked[row.key].use
        and row.food is not None
        and row.status != "staple"
        and row.wanted
    ]


def offer_as_previewed(
    kitchen: Kitchen,
    entries: list[tuple[Recipe, int, dict[str, Choice], frozenset[int], int | None]],
    worked: list[Worked],
    answers: list[Answer] | None = None,
) -> None:
    """A row with Use off is offered what the preview showed: every recipe worked out once more
    as the preview does (one fresh pool, no choices: the preview endpoints take none) and settled
    as a meal. Nothing is taken. Only the offer's fields are copied onto the off rows, with the
    person's own tick on the offer."""
    choices = [picked for _, _, picked, _, _ in entries]
    off = off_rows(worked, choices)
    if not off:
        return
    off_ids = {id(row) for row in off}
    pool = Pool(kitchen)
    shown = [
        work_out(kitchen, recipe, portions, answers, None, pool, skip, method_id)
        for recipe, portions, _, skip, method_id in entries
    ]
    settle_meal(shown)
    by_key = {(i, row.key): row for i, each in enumerate(shown) for row in each.rows}
    for i, (each, picked) in enumerate(zip(worked, choices, strict=True)):
        for row in each.rows:
            if id(row) not in off_ids:
                continue
            seen = by_key[(i, row.key)]
            row.short, row.status, row.make_first = seen.short, seen.status, seen.make_first
            row.in_freezer, row.list_milli = seen.in_freezer, seen.list_milli
            row.running_low, row.add_to_list = seen.running_low, seen.add_to_list
            tick = picked[row.key].add_to_list
            if row.list_milli > 0 and tick is not None:
                row.add_to_list = tick
            if picked[row.key].bought:
                row.add_to_list = False  # bought some: there is nothing to buy


def _short_foods(rows: Iterable[Row]) -> set[int]:
    return {
        row.food.id for row in rows if row.food is not None and row.short > 0 and row.inner is None
    }


def settle_meal(worked: list[Worked]) -> None:
    """Across the recipes of one meal: an ingredient gets at most one running-low pack, and none
    when the same ingredient is already short somewhere in the meal (the shortfall is the bigger
    offer). The pack the person ticked wins, else the first row's."""
    short = _short_foods(row for each in worked for row in each.rows)
    packs = [
        (row.food.id, row)
        for each in worked
        for row in each.rows
        if row.running_low and row.food is not None
    ]
    kept: dict[int, Row] = {}
    for food_id, row in packs:
        if food_id not in kept or (row.add_to_list and not kept[food_id].add_to_list):
            kept[food_id] = row
    for food_id, row in packs:
        if food_id in short or kept[food_id] is not row:
            row.running_low, row.list_milli, row.add_to_list = False, 0, False


# --- What the API shows -------------------------------------------------------------------------


class RowLineOut(BaseModel):
    id: int
    words: str
    amount: str | None = None  # the recipe's own amount as written: "1½"
    unit: str | None = None  # and its unit: "tbsp"


class LotTakeOut(BaseModel):
    lot_id: int
    place: Ref | None
    use_by: date | None
    amount: AmountOut
    used_all: bool  # under 2 % of the packet would be left: taken whole, "Used it all"


class TakeOut(BaseModel):
    """What is taken from one ingredient: the row's own, or a stand-in's (`stand_in`)."""

    food: Ref
    stand_in: bool
    amount: AmountOut
    before: AmountOut
    after: AmountOut
    lots: list[LotTakeOut]


class NeedOut(BaseModel):
    """What the recipe asks for on its own side, where it is not what the pantry counts."""

    amount: float
    unit: Literal["g", "ml", "item"]


class CountNoteOut(BaseModel):
    """A line with no amount whose note says how many ("2 cloves"): the count and the size word."""

    count: float
    word: str


class RowOut(BaseModel):
    """One ingredient of the review. `use` is how its Use switch starts."""

    key: str
    status: RowStatus
    lines: list[RowLineOut]
    food: Ref | None
    recipe: Ref | None  # a recipe used as an ingredient
    needed: AmountOut | None  # worked out for the portions cooked
    takes: list[TakeOut]
    use: bool
    short: AmountOut | None  # not in the pantry: "add to list" (or, for a recipe, make it)
    make_first: bool
    add_to_list: bool  # the offer to add to the shopping list is ticked
    list_amount: AmountOut | None  # what would go on: the shortfall, or for running low a pack
    running_low: bool  # what is left is at or below the running-low level: the offer is unticked
    in_freezer: AmountOut | None  # waiting in the freezer, left alone unless from_freezer
    from_freezer: bool
    ask: Ask | None
    estimate: bool = False  # `needed` came from changing units (a cup of flour in grams)
    ask_need: NeedOut | None = None  # status ask: what the recipe asks for, on its own side
    half: AmountOut | None = None  # about half of the first packet, in the pantry's unit
    count_note: CountNoteOut | None = None  # status no_amount with "2 cloves" in the note
    bought: bool = False  # "Bought some — used them" (a confirm's choice, kept on the record)
    unit: Literal["g", "ml", "count"] | None = None  # what the pantry counts the ingredient in
    unit_word: str | None = None  # a counted ingredient's word, plural: "bulbs" (else null)


class ProposalOut(BaseModel):
    recipe: Ref
    portions: int
    servings: int | None
    rows: list[RowOut]


def _unit_word(food: Food | None) -> str | None:
    if food is None or food.counted_as != "count":
        return None
    return food.count_word_plural or (plural(food.count_word) if food.count_word else None)


def _ask_need(row: Row) -> NeedOut | None:
    """One family only: with weights and cups mixed in one row nothing can be worked out from a
    single answer, so the screen asks the old way."""
    if len(row.asked_need) != 1:
        return None
    ((family, milli),) = row.asked_need.items()
    unit: Literal["g", "ml", "item"] = {"weight": "g", "volume": "ml", "count": "item"}[family]  # type: ignore[assignment]
    return NeedOut(amount=milli / MILLI, unit=unit) if milli > 0 else None


def row_out(kitchen: Kitchen, row: Row, names: dict[int, str]) -> RowOut:
    food = row.food
    size = usual_size(kitchen, food.id) if food else None
    takes = []
    for take in row.takes:
        taken_size = usual_size(kitchen, take.food.id)
        takes.append(
            TakeOut(
                food=Ref(id=take.food.id, name=take.food.name),
                stand_in=take.stand_in,
                amount=amount_out(take.food, take.amount, None),
                before=amount_out(take.food, take.before, taken_size),
                after=amount_out(take.food, take.before - take.amount, taken_size),
                lots=[
                    LotTakeOut(
                        lot_id=lot.id,
                        place=Ref(id=lot.place_id, name=names[lot.place_id])
                        if lot.place_id in names
                        else None,
                        use_by=lot.use_by,
                        amount=amount_out(take.food, amount, None),
                        used_all=lot.id in take.used_all,
                    )
                    for lot, amount in take.lots
                ],
            )
        )
    question: Ask | None = None
    if row.asked is not None and food is not None:
        problem = ask(kitchen, food, row.asked.kind)
        question = Ask.model_validate(problem.extra["ask"])
    return RowOut(
        key=row.key,
        status=row.status,
        lines=[
            RowLineOut(
                id=line.id,
                words=line.words,
                amount=amount_text(line.amount_milli),
                unit=line.unit,
            )
            for line in row.lines
        ],
        food=Ref(id=food.id, name=food.name) if food else None,
        recipe=Ref(id=row.inner.id, name=row.inner.name) if row.inner else None,
        needed=amount_out(food, row.needed, None) if food and row.needed is not None else None,
        takes=takes,
        use=row.use_default,
        short=amount_out(food, row.short, size) if food and row.short > 0 else None,
        make_first=row.make_first,
        add_to_list=row.add_to_list,
        list_amount=amount_out(food, row.list_milli, size) if food and row.list_milli > 0 else None,
        running_low=row.running_low,
        in_freezer=amount_out(food, row.in_freezer, None) if food and row.in_freezer > 0 else None,
        from_freezer=row.from_freezer,
        ask=question,
        estimate=row.estimate,
        ask_need=_ask_need(row),
        half=amount_out(food, row.half_milli, None) if food and row.half_milli > 0 else None,
        count_note=CountNoteOut(count=row.count_note[0] / MILLI, word=row.count_note[1])
        if row.count_note
        else None,
        bought=row.bought,
        unit=BASE_UNITS[food.counted_as] if food else None,
        unit_word=_unit_word(food),
    )


def proposal_out(kitchen: Kitchen, worked: Worked) -> ProposalOut:
    names = {place.id: place.name for place in places(kitchen.db, kitchen.household_id)}
    return ProposalOut(
        recipe=Ref(id=worked.recipe.id, name=worked.recipe.name),
        portions=worked.portions,
        servings=worked.recipe.serves,
        rows=[row_out(kitchen, row, names) for row in worked.rows],
    )
