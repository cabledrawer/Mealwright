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

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal

from fastapi import status
from pydantic import BaseModel
from sqlalchemy import select

from mealwright.amounts import MILLI, TooBig, checked, round_half_up, unit_family
from mealwright.api.v1.context import Kitchen
from mealwright.api.v1.schemas import AmountOut, Answer, Ask, Ref
from mealwright.conversions import AskOnce, UnitAmount, to_base_milli
from mealwright.errors import Problem
from mealwright.foods import amount_out, ask, find, known, usual_size, visible
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


def _rows(kitchen: Kitchen, recipe: Recipe, portions: int, answers: list[Answer]) -> list[Row]:
    """Rule 1 and 2 and 3: one row per ingredient, in the order the recipe first uses it."""
    db, hid = kitchen.db, kitchen.household_id
    lines = list(
        db.scalars(
            select(RecipeLine)
            .where(
                RecipeLine.recipe_id == recipe.id,
                RecipeLine.household_id == hid,
                RecipeLine.kind == "ingredient",
            )
            .order_by(RecipeLine.position, RecipeLine.id)
        )
    )
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
            continue
        try:
            need = _line_need(line, food, sizes, answers, kitchen)
        except AskOnce as needed:
            row.asked = needed
            continue
        except TooBig:
            continue
        if need is not None:
            row.needed = (row.needed or 0) + need
    for row in rows.values():
        if row.food is None or row.status == "staple":
            continue
        if row.asked is not None:
            row.status = "ask"
            row.needed = None
        elif row.needed is None:
            row.status, row.use_default = "no_amount", False
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

    def take(
        self, food: Food, amount: int, from_freezer: bool, stand_in: bool, tidy: bool = True
    ) -> Take | None:
        """Rule 4: the packet that goes off first. None when nothing could be taken. With `tidy`,
        a packet left with under 2 % of its size is taken whole ("Used it all", cabledrawer 31 Oct)."""
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
) -> Worked:
    """What cooking `portions` of the recipe takes from the pantry. Read-only. With `choices`
    (a confirm) the rows follow them, and a row that still needs its question answered is
    refused with the "ask once" 409; without, every row is as it would start on the review."""
    answers = answers or []
    for answer in answers:
        find(kitchen, answer.food_id)  # a food from another household is a 404
    rows = _rows(kitchen, recipe, portions, answers)
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
            if choice is not None and (
                choice.used_milli is not None or choice.left_milli is not None
            ):
                if row.status == "staple":
                    raise _refuse("staple", "Staples aren’t counted, so nothing is taken.")
                raise _refuse("no_ingredient", "There’s no ingredient to take that from.")
            continue
        food = row.food
        row.from_freezer = bool(choice and choice.from_freezer)
        own = pool.total(food.id, row.from_freezer)
        row.use_default = row.status in ("take", "ask") and own > 0
        # A row nobody chose on is tried (it takes what there is, stand-ins too); its switch is
        # settled below, once it is known whether anything could be taken.
        row.use = choice.use if choice is not None else True
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
        if row.food is None or not row.wanted or (confirming and not row.use):
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

    def would_take(row: Row, food: Food, wanted: int) -> int:
        """What this row takes, or would take with Use on: the preview's answer (its own
        packets, else a stand-in's when it has none at all), read without taking anything."""
        if row.taken or not (confirming and not row.use):
            return row.taken
        got = min(wanted, pool.total(food.id, row.from_freezer))
        if got == 0 and pool.total(food.id) == 0:
            got = min(
                wanted,
                sum(
                    pool.total(i, row.from_freezer)
                    for i in stand_ins.get(food.id, ())
                    if i in others and others[i].counted_as == food.counted_as
                ),
            )
        return got

    for row in rows:
        if row.food is None or row.wanted is None:
            continue
        # Use does not change what is offered (cabledrawer 31 Oct: the tick is its own choice): a
        # row switched off is worked out as the preview works it out, only nothing is taken.
        applied = not (confirming and not row.use)
        took = would_take(row, row.food, row.wanted)
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
            applied
            and row.takes
            and row.food.running_low_milli is not None
            and not row.food.staple
            and pool.total(row.food.id) <= row.food.running_low_milli
        ):
            row.running_low = True
            row.list_milli = smallest.get(row.food.id) or row.food.running_low_milli
        picked = choices.get(row.key)
        row.add_to_list = default
        if row.list_milli > 0 and picked is not None and picked.add_to_list is not None:
            row.add_to_list = picked.add_to_list
    for row in rows:
        if row.status in ("take", "none_in_pantry"):
            row.use_default = bool(row.takes)  # nothing to take (or only the freezer): off
        if row.food is not None and row.status != "staple" and row.key not in choices:
            row.use = row.use_default
    return Worked(recipe, portions, rows)


def settle_meal(worked: list[Worked]) -> None:
    """Across the recipes of one meal: an ingredient gets at most one running-low pack, and none
    when the same ingredient is already short somewhere in the meal (the shortfall is the bigger
    offer). Later rows give way to the first."""
    short = {
        row.food.id
        for each in worked
        for row in each.rows
        if row.food is not None and row.short > 0 and row.inner is None
    }
    seen: set[int] = set()
    for each in worked:
        for row in each.rows:
            if not row.running_low or row.food is None:
                continue
            if row.food.id in short or row.food.id in seen:
                row.running_low, row.list_milli, row.add_to_list = False, 0, False
            seen.add(row.food.id)


# --- What the API shows -------------------------------------------------------------------------


class RowLineOut(BaseModel):
    id: int
    words: str


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


class ProposalOut(BaseModel):
    recipe: Ref
    portions: int
    servings: int | None
    rows: list[RowOut]


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
        lines=[RowLineOut(id=line.id, words=line.words) for line in row.lines],
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
    )


def proposal_out(kitchen: Kitchen, worked: Worked) -> ProposalOut:
    names = {place.id: place.name for place in places(kitchen.db, kitchen.household_id)}
    return ProposalOut(
        recipe=Ref(id=worked.recipe.id, name=worked.recipe.name),
        portions=worked.portions,
        servings=worked.recipe.serves,
        rows=[row_out(kitchen, row, names) for row in worked.rows],
    )
