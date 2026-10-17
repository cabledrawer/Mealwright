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

from mealwright.api.v1.context import Kitchen
from mealwright.history import as_utc, record
from mealwright.models import Change, ChangeLine, Food, Place, StockLot, utcnow

FREEZER_MONTHS = 3  # "To freezer": new use-by 3 months away (spec section 6)


# --- Pure planning (tested with Hypothesis) ---------------------------------------------------


@dataclass(frozen=True)
class LotView:
    id: int
    amount: int
    use_by: date | None
    added_at: datetime
    freezer: bool


def use_order(lots: Iterable[LotView]) -> list[LotView]:
    """The order lots are used in: not frozen first, then soonest use-by, then no use-by,
    oldest added first."""
    return sorted(
        lots,
        key=lambda lot: (
            lot.freezer,
            lot.use_by is None,
            lot.use_by or date.max,
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


def place_kinds(kitchen: Kitchen) -> dict[int, str]:
    return {
        place.id: place.kind
        for place in kitchen.db.scalars(
            select(Place).where(Place.household_id == kitchen.household_id)
        )
    }


def view(lot: StockLot, kinds: dict[int, str]) -> LotView:
    return LotView(
        lot.id,
        lot.amount_milli,
        lot.use_by,
        as_utc(lot.added_at),
        kinds.get(lot.place_id) == "freezer",
    )


def ordered(kitchen: Kitchen, lots: Iterable[StockLot]) -> list[StockLot]:
    kinds = place_kinds(kitchen)
    by_id = {lot.id: lot for lot in lots}
    return [by_id[v.id] for v in use_order(view(lot, kinds) for lot in by_id.values())]


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
        if place is not None:
            return place
    place = first_place(kitchen, "cupboard")
    if place is None:  # pragma: no cover (every household has a cupboard)
        raise LookupError("no cupboard")
    return place


# --- Writing ----------------------------------------------------------------------------------


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

    def touch(self, lot: StockLot) -> StockLot:
        if lot.id not in self.before:
            self.before[lot.id] = (lot.amount_milli, lot.place_id, lot.use_by)
            self.lots[lot.id] = lot
        return lot

    def new(self, lot: StockLot) -> StockLot:
        self.kitchen.db.add(lot)
        self.kitchen.db.flush()
        self.before[lot.id] = (0, None, None)
        self.lots[lot.id] = lot
        return lot

    def record(
        self, kind: str, summary: str, food_id: int, undo_data: dict[str, object] | None = None
    ) -> Change:
        now = utcnow()
        for lot in self.lots.values():
            if lot.amount_milli <= 0:
                lot.amount_milli = 0
                lot.emptied_at = lot.emptied_at or now
            else:
                lot.emptied_at = None
        change = record(self.kitchen, kind, summary, food_id, undo_data)
        for lot_id, (amount, place_id, use_by) in self.before.items():
            lot = self.lots[lot_id]
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
                )
            )
        self.kitchen.db.flush()
        return change


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
    plan, short = plan_take([view(lot, kinds) for lot in lots], amount, include_freezer)
    for lot_id, taken in plan:
        lot = edit.touch(by_id[lot_id])
        lot.amount_milli -= taken
    return short
