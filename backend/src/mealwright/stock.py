"""Stock: lots (each packet on its own), taking oldest first, and recording every change.

Rules (spec section 2, "Cooking — how deduction works", and section 6, "Stock"):
- take from the lot that goes off first; lots with no use-by after dated ones, oldest
  added first;
- fridge and cupboard before freezer (freezer only when asked for);
- never below zero: if there isn't enough, take everything and say how much was missing.
"""

from calendar import monthrange
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

from sqlalchemy import select

from mealwright.amounts import NBSP
from mealwright.api.v1.context import Kitchen
from mealwright.foods import amount_out
from mealwright.history import as_utc, record
from mealwright.models import Change, ChangeLine, Food, FoodSize, Place, StockLot, utcnow

FREEZER_MONTHS = 3  # "To freezer": new use-by 3 months away (spec section 6)


# --- Pure planning (tested with Hypothesis) ---------------------------------------------------


@dataclass(frozen=True)
class LotView:
    id: int
    amount: int
    use_by: date | None
    added_at: datetime
    freezer: bool
    opened: bool = False  # part used: less than the packet it was bought as


def use_order(lots: Iterable[LotView]) -> list[LotView]:
    """The order lots are used in: not frozen first, then soonest use-by, then no use-by. Two
    with the same use-by: the opened one first, else the one bought first. With no use-by:
    oldest bought first (cabledrawer 31 Oct)."""
    return sorted(
        lots,
        key=lambda lot: (
            lot.freezer,
            lot.use_by is None,
            lot.use_by or date.max,
            lot.use_by is not None and not lot.opened,
            lot.added_at,
            lot.id,
        ),
    )


def plan_take(
    lots: Sequence[LotView], amount: int, include_freezer: bool = False
) -> tuple[list[tuple[int, int]], int]:
    """Which lots to take `amount` from: [(lot id, how much)], and how much was missing.
    Never takes more than a lot holds."""
    remaining = max(amount, 0)
    plan: list[tuple[int, int]] = []
    for lot in use_order(lots):
        if remaining <= 0:
            break
        if lot.freezer and not include_freezer:
            continue
        take = min(lot.amount, remaining)
        if take > 0:
            plan.append((lot.id, take))
            remaining -= take
    return plan, remaining


def add_months(day: date, months: int) -> date:
    month_index = day.month - 1 + months
    year, month = day.year + month_index // 12, month_index % 12 + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


# --- Reading ----------------------------------------------------------------------------------


def lots_of(
    kitchen: Kitchen, food_ids: Iterable[int] | None = None, place_id: int | None = None
) -> list[StockLot]:
    """Lots with something in them."""
    query = select(StockLot).where(
        StockLot.household_id == kitchen.household_id, StockLot.amount_milli > 0
    )
    if food_ids is not None:
        query = query.where(StockLot.food_id.in_(list(food_ids)))
    if place_id is not None:
        query = query.where(StockLot.place_id == place_id)
    return list(kitchen.db.scalars(query))


def place_totals(kitchen: Kitchen, food_id: int) -> dict[int, int]:
    """How much of one ingredient is in each place right now, all its packets added up."""
    totals: dict[int, int] = {}
    for lot in lots_of(kitchen, [food_id]):
        totals[lot.place_id] = totals.get(lot.place_id, 0) + lot.amount_milli
    return totals


def place_kinds(kitchen: Kitchen) -> dict[int, str]:
    return {
        place.id: place.kind
        for place in kitchen.db.scalars(
            select(Place).where(Place.household_id == kitchen.household_id)
        )
    }


def opened_lots(kitchen: Kitchen, lots: Iterable[StockLot]) -> set[int]:
    """The lots that are part used: bought as a size, and now holding less than it."""
    lots = list(lots)
    wanted = {lot.size_id for lot in lots if lot.size_id}
    if not wanted:
        return set()
    sizes = {
        size.id: size.amount_milli
        for size in kitchen.db.scalars(select(FoodSize).where(FoodSize.id.in_(wanted)))
    }
    return {
        lot.id for lot in lots if lot.size_id in sizes and 0 < lot.amount_milli < sizes[lot.size_id]
    }


def view(lot: StockLot, kinds: dict[int, str], opened: bool = False) -> LotView:
    return LotView(
        lot.id,
        lot.amount_milli,
        lot.use_by,
        as_utc(lot.added_at),
        kinds.get(lot.place_id) == "freezer",
        opened,
    )


def ordered(kitchen: Kitchen, lots: Iterable[StockLot]) -> list[StockLot]:
    kinds = place_kinds(kitchen)
    by_id = {lot.id: lot for lot in lots}
    opened = opened_lots(kitchen, by_id.values())
    return [
        by_id[v.id] for v in use_order(view(lot, kinds, lot.id in opened) for lot in by_id.values())
    ]


def has_stock(kitchen: Kitchen, food_id: int) -> bool:
    return bool(lots_of(kitchen, [food_id]))


def first_place(kitchen: Kitchen, kind: str) -> Place | None:
    return kitchen.db.scalar(
        select(Place)
        .where(Place.household_id == kitchen.household_id, Place.kind == kind)
        .order_by(Place.position, Place.id)
        .limit(1)
    )


def default_place(kitchen: Kitchen, food: Food) -> Place:
    """The food's usual place, or Cupboard (spec section 6, "Decided for 0.3")."""
    if food.place_id is not None:
        place = kitchen.db.get(Place, food.place_id)
        if place is not None and place.household_id == kitchen.household_id:
            return place
    place = first_place(kitchen, "cupboard")
    if place is None:  # pragma: no cover (every household has a cupboard)
        raise LookupError("no cupboard")
    return place


# --- Wording for summaries --------------------------------------------------------------------


def short_text(food: Food, milli: int, size: FoodSize | None) -> str:
    """ "2 packets", "about ½ packet", "200 g", "5", "5 slices" for summaries. A count
    food's "5 left" is only for the pantry list: a summary says just "5"."""
    shown = amount_out(food, milli, size)
    text = shown.short.removesuffix(f"{NBSP}left")
    return f"about {text}" if shown.about else text


def what_text(food: Food, milli: int, size: FoodSize | None) -> str:
    """The amount and the ingredient, for summaries: "2 packets Toor dal", "200 g
    Spinach", "5 Onion", "5 slices of Bread"."""
    joiner = " "
    if food.counted_as == "count":
        joiner = " of " if food.count_word else NBSP  # "5 slices of Bread", "5 Onion"
    return f"{short_text(food, milli, size)}{joiner}{food.name}"


# --- Writing ----------------------------------------------------------------------------------


MAX_LOTS = 50  # one request can't add more than 50 packets


def lot_amounts(milli: int, size: FoodSize | None) -> list[int]:
    """How an amount is split into lots (api-0.2 section 3.5): one per whole packet, plus a
    part packet; with no size, one lot. Above MAX_LOTS packets the amount goes in as one lot,
    so a tiny size can't make a million packets."""
    if size is None or size.amount_milli <= 0:
        return [milli]
    whole, rest = divmod(milli, size.amount_milli)
    if whole > MAX_LOTS:
        return [milli]
    return [size.amount_milli] * whole + ([rest] if rest > 0 else [])


class StockEdit:
    """Remember each lot as it was before a change, then record the change with a line per
    lot (before → after):

        edit = StockEdit(kitchen)
        edit.touch(lot); lot.amount_milli -= 200_000
        change = edit.record("used", "Used 200 g spinach", food.id)
    """

    def __init__(self, kitchen: Kitchen) -> None:
        self.kitchen = kitchen
        self.lots: dict[int, StockLot] = {}
        self.before: dict[int, tuple[int, int | None, date | None]] = {}
        # Each ingredient's amount per place before anything changed, for the whole-amount
        # "before → after" in Recent changes.
        self.start: dict[int, dict[int, int]] = {}

    def _remember(self, food_id: int) -> None:
        if food_id not in self.start:
            self.start[food_id] = place_totals(self.kitchen, food_id)

    def touch(self, lot: StockLot) -> StockLot:
        if lot.id not in self.before:
            self._remember(lot.food_id)
            self.before[lot.id] = (lot.amount_milli, lot.place_id, lot.use_by)
            self.lots[lot.id] = lot
        return lot

    def new(self, lot: StockLot) -> StockLot:
        self._remember(lot.food_id)
        self.kitchen.db.add(lot)
        self.kitchen.db.flush()
        self.before[lot.id] = (0, None, None)
        self.lots[lot.id] = lot
        return lot

    def record(
        self,
        kind: str,
        summary: str,
        food_id: int | None,
        undo_data: dict[str, object] | None = None,
    ) -> Change:
        now = utcnow()
        for lot in self.lots.values():
            if lot.amount_milli <= 0:
                lot.amount_milli = 0
                lot.emptied_at = lot.emptied_at or now
            else:
                lot.emptied_at = None
        change = record(self.kitchen, kind, summary, food_id, undo_data)
        end = {food: place_totals(self.kitchen, food) for food in self.start}
        for lot_id, (amount, place_id, use_by) in self.before.items():
            lot = self.lots[lot_id]
            shown_before = place_id if place_id is not None else lot.place_id
            start, finish = self.start[lot.food_id], end[lot.food_id]
            self.kitchen.db.add(
                ChangeLine(
                    household_id=self.kitchen.household_id,
                    change_id=change.id,
                    food_id=lot.food_id,
                    lot_id=lot.id,
                    amount_before_milli=amount,
                    amount_after_milli=lot.amount_milli,
                    place_before_id=place_id,
                    place_after_id=lot.place_id,
                    use_by_before=use_by,
                    use_by_after=lot.use_by,
                    total_before_milli=start.get(shown_before, 0),
                    total_after_milli=finish.get(lot.place_id, 0),
                )
            )
        self.kitchen.db.flush()
        return change


def put_in(
    kitchen: Kitchen,
    edit: StockEdit,
    food: Food,
    place: Place,
    amounts: list[int],
    size: FoodSize | None,
    use_by: date | None = None,
    added_at: datetime | None = None,
) -> list[StockLot]:
    """New lots of these amounts in `place`, recorded in `edit`. `added_at` dates them (an
    offline purchase keeps the moment it was made); left out, it is now."""
    when = {} if added_at is None else {"added_at": added_at}
    return [
        edit.new(
            StockLot(
                household_id=kitchen.household_id,
                food_id=food.id,
                place_id=place.id,
                amount_milli=milli,
                size_id=size.id if size else None,
                use_by=use_by,
                **when,
            )
        )
        for milli in amounts
    ]


def take(
    kitchen: Kitchen,
    edit: StockEdit,
    lots: Sequence[StockLot],
    amount: int,
    include_freezer: bool = False,
) -> int:
    """Take `amount` from these lots, oldest first, never below zero. Returns how much was
    missing."""
    kinds = place_kinds(kitchen)
    by_id = {lot.id: lot for lot in lots}
    opened = opened_lots(kitchen, lots)
    plan, short = plan_take(
        [view(lot, kinds, lot.id in opened) for lot in lots], amount, include_freezer
    )
    for lot_id, taken in plan:
        lot = edit.touch(by_id[lot_id])
        lot.amount_milli -= taken
    return short
