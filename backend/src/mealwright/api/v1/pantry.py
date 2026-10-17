"""The Pantry: stock by place, Use soon, and every stock change (docs/dev/api-0.2.md 6.4)."""

from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import date, timedelta
from decimal import Decimal
from typing import Annotated, Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from mealwright.amounts import NBSP
from mealwright.api.v1.context import Here, Kitchen
from mealwright.api.v1.schemas import AmountIn, AmountOut, ChangeOut, CountedAsName, Ref
from mealwright.auth import SameOrigin
from mealwright.errors import Problem, not_found
from mealwright.foods import amount_out, change_out, find, resolve, usual_size
from mealwright.history import as_utc, commit, replayed
from mealwright.household import places, today, zone
from mealwright.models import Change, ChangeLine, Food, FoodSize, Place, StockLot
from mealwright.stock import (
    FREEZER_MONTHS,
    StockEdit,
    add_months,
    default_place,
    first_place,
    lots_of,
    ordered,
    take,
)

router = APIRouter(tags=["pantry"], dependencies=[SameOrigin])

MAX_LOTS = 50  # one request can't add more than 50 packets


# --- Shapes ---------------------------------------------------------------------------------


class FoodBrief(BaseModel):
    id: int
    name: str
    counted_as: CountedAsName


class PlaceRef(BaseModel):
    id: int
    name: str
    kind: Literal["fridge", "freezer", "cupboard"]


class LotOut(BaseModel):
    id: int
    stock: AmountOut
    use_by: date | None
    days_left: int | None
    use_soon: bool
    added_on: date
    frozen_on: date | None
    size_id: int | None
    open: bool  # holds less than its size: show the ¼ ½ ¾ Full picker


class GroupOut(BaseModel):
    """One food in one place."""

    food: FoodBrief
    place: PlaceRef
    stock: AmountOut
    lots_count: int
    dates_count: int
    use_by: date | None
    days_left: int | None
    use_soon: bool
    running_low: bool
    lots: list[LotOut]


class PlaceOut(PlaceRef):
    items: int
    groups: list[GroupOut]


class PantryCounts(BaseModel):
    items: int
    tubs: int
    use_soon: int
    running_low: int


class PantryOut(BaseModel):
    today: date
    counts: PantryCounts
    places: list[PlaceOut]
    staples: list[Ref]


class UseSoonLot(LotOut):
    food: FoodBrief
    place: PlaceRef
    position: int  # "Paneer · 1 of 2 packs"
    of: int


class UseSoonOut(BaseModel):
    today: date
    lots: list[UseSoonLot]


class StockWrite(BaseModel):
    change: ChangeOut
    groups: list[GroupOut]  # the food's groups in the places touched (empty ones too)
    short_by: AmountOut | None  # how much more was asked for than there was


# --- Describing -----------------------------------------------------------------------------


class Pantry:
    """Everything needed to describe stock, loaded once per request."""

    def __init__(self, kitchen: Kitchen) -> None:
        self.kitchen = kitchen
        self.today = today(kitchen.household)
        self.soon = self.today + timedelta(days=kitchen.household.use_soon_days)
        self.places = {p.id: p for p in places(kitchen.db, kitchen.household_id)}
        self._foods: dict[int, Food] = {}
        self._sizes: dict[int, FoodSize | None] = {}
        self._usual: dict[int, FoodSize | None] = {}
        self._totals: dict[int, int] | None = None

    def food(self, food_id: int) -> Food:
        if food_id not in self._foods:
            found = self.kitchen.db.get(Food, food_id)
            if found is None:  # pragma: no cover (foods are never deleted)
                raise not_found("That ingredient")
            self._foods[food_id] = found
        return self._foods[food_id]

    def usual(self, food_id: int) -> FoodSize | None:
        if food_id not in self._usual:
            self._usual[food_id] = usual_size(self.kitchen, food_id)
        return self._usual[food_id]

    def size(self, size_id: int | None) -> FoodSize | None:
        if size_id is None:
            return None
        if size_id not in self._sizes:
            self._sizes[size_id] = self.kitchen.db.get(FoodSize, size_id)
        return self._sizes[size_id]

    def totals(self) -> dict[int, int]:
        if self._totals is None:
            self._totals = defaultdict(int)
            for lot in lots_of(self.kitchen):
                self._totals[lot.food_id] += lot.amount_milli
        return self._totals

    def running_low(self, food: Food) -> bool:
        return (
            food.running_low_milli is not None
            and not food.staple
            and self.totals().get(food.id, 0) <= food.running_low_milli
        )

    def days_left(self, use_by: date | None) -> int | None:
        return (use_by - self.today).days if use_by is not None else None

    def is_soon(self, use_by: date | None) -> bool:
        return use_by is not None and use_by <= self.soon

    def place_ref(self, place_id: int) -> PlaceRef:
        place = self.places[place_id]
        return PlaceRef(id=place.id, name=place.name, kind=place.kind)  # type: ignore[arg-type]

    def lot_size(self, lot: StockLot) -> FoodSize | None:
        return self.size(lot.size_id) or self.usual(lot.food_id)

    def lot_out(self, lot: StockLot) -> LotOut:
        food = self.food(lot.food_id)
        size = self.lot_size(lot)
        return LotOut(
            id=lot.id,
            stock=amount_out(food, lot.amount_milli, size),
            use_by=lot.use_by,
            days_left=self.days_left(lot.use_by),
            use_soon=self.is_soon(lot.use_by),
            added_on=as_utc(lot.added_at).astimezone(zone(self.kitchen.household)).date(),
            frozen_on=lot.frozen_on,
            size_id=lot.size_id,
            open=size is not None and 0 < lot.amount_milli < size.amount_milli,
        )

    def group(self, food_id: int, place_id: int, lots: list[StockLot]) -> GroupOut:
        food = self.food(food_id)
        lots = ordered(self.kitchen, [lot for lot in lots if lot.amount_milli > 0])
        dates = [lot.use_by for lot in lots if lot.use_by is not None]
        first = min(dates) if dates else None
        return GroupOut(
            food=FoodBrief(id=food.id, name=food.name, counted_as=food.counted_as),  # type: ignore[arg-type]
            place=self.place_ref(place_id),
            stock=amount_out(food, sum(lot.amount_milli for lot in lots), self.usual(food.id)),
            lots_count=len(lots),
            dates_count=len(set(dates)),
            use_by=first,
            days_left=self.days_left(first),
            use_soon=self.is_soon(first),
            running_low=self.running_low(food),
            lots=[self.lot_out(lot) for lot in lots],
        )

    def groups_for(self, pairs: Iterable[tuple[int, int]]) -> list[GroupOut]:
        """The groups for these (food, place) pairs, as they are now; empty ones too."""
        result = []
        for food_id, place_id in sorted(set(pairs), key=lambda p: (p[1], p[0])):
            lots = lots_of(self.kitchen, [food_id], place_id)
            result.append(self.group(food_id, place_id, lots))
        return result


def _sort_key(group: GroupOut) -> tuple[bool, date, str]:
    return (group.use_by is None, group.use_by or date.max, group.food.name.casefold())


# --- Reading ----------------------------------------------------------------------------------


@router.get("/pantry")
def pantry(
    kitchen: Here,
    filter: Literal["all", "use_soon", "running_low", "staples"] = "all",
) -> PantryOut:
    """The whole Pantry screen in one call: places (tabs on phone, columns on desktop), each
    food's packets grouped with their dates, and the staples."""
    view = Pantry(kitchen)
    by_group: dict[tuple[int, int], list[StockLot]] = defaultdict(list)
    for lot in lots_of(kitchen):
        by_group[(lot.food_id, lot.place_id)].append(lot)
    groups: dict[int, list[GroupOut]] = defaultdict(list)
    all_groups = []
    for (food_id, place_id), lots in by_group.items():
        food = view.food(food_id)
        if food.staple or food.removed_at is not None or food.merged_into_id is not None:
            continue
        group = view.group(food_id, place_id, lots)
        all_groups.append(group)
        if filter == "use_soon" and not any(lot.use_soon for lot in group.lots):
            continue
        if filter in ("running_low", "staples") and not (
            filter == "running_low" and group.running_low
        ):
            continue
        groups[place_id].append(group)
    staples = kitchen.db.scalars(
        select(Food)
        .where(
            Food.household_id == kitchen.household_id,
            Food.staple.is_(True),
            Food.removed_at.is_(None),
            Food.merged_into_id.is_(None),
        )
        .order_by(Food.name)
    )
    return PantryOut(
        today=view.today,
        counts=PantryCounts(
            items=len(all_groups),
            tubs=0,
            use_soon=sum(lot.use_soon for g in all_groups for lot in g.lots),
            running_low=len({g.food.id for g in all_groups if g.running_low}),
        ),
        places=[
            PlaceOut(
                id=place.id,
                name=place.name,
                kind=place.kind,  # type: ignore[arg-type]
                items=sum(1 for g in all_groups if g.place.id == place.id),
                groups=sorted(groups.get(place.id, []), key=_sort_key),
            )
            for place in view.places.values()
        ],
        staples=[Ref(id=f.id, name=f.name) for f in staples],
    )


@router.get("/pantry/use-soon")
def use_soon(kitchen: Here) -> UseSoonOut:
    """Packets with a use-by from the past up to the day after tomorrow (2 days, in the
    household's own time zone), soonest first."""
    view = Pantry(kitchen)
    by_group: dict[tuple[int, int], list[StockLot]] = defaultdict(list)
    for lot in lots_of(kitchen):
        food = view.food(lot.food_id)
        if not food.staple and food.removed_at is None and food.merged_into_id is None:
            by_group[(lot.food_id, lot.place_id)].append(lot)
    found = []
    for (food_id, place_id), lots in by_group.items():
        food = view.food(food_id)
        group = ordered(kitchen, lots)
        for position, lot in enumerate(group, start=1):
            if view.is_soon(lot.use_by):
                found.append(
                    UseSoonLot(
                        **view.lot_out(lot).model_dump(),
                        food=FoodBrief(id=food.id, name=food.name, counted_as=food.counted_as),  # type: ignore[arg-type]
                        place=view.place_ref(place_id),
                        position=position,
                        of=len(group),
                    )
                )
    found.sort(key=lambda lot: (lot.use_by or date.max, lot.food.name.casefold()))
    return UseSoonOut(today=view.today, lots=found)


# --- Writing ----------------------------------------------------------------------------------


def _written(kitchen: Kitchen, change: Change, short_by: int = 0) -> StockWrite:
    view = Pantry(kitchen)
    pairs: set[tuple[int, int]] = set()
    for line in kitchen.db.scalars(select(ChangeLine).where(ChangeLine.change_id == change.id)):
        for place_id in (line.place_before_id, line.place_after_id):
            if place_id is not None:
                pairs.add((line.food_id, place_id))
    short = None
    if short_by > 0 and change.food_id is not None:
        short = amount_out(view.food(change.food_id), short_by, view.usual(change.food_id))
    return StockWrite(
        change=change_out(kitchen, change), groups=view.groups_for(pairs), short_by=short
    )


def stock_write(
    kitchen: Kitchen, response: Response, apply: Callable[[], tuple[Change, int]]
) -> StockWrite:
    """Apply once: a retry with the same Idempotency-Key gets the original change and the
    stock as it is now."""
    earlier = replayed(kitchen)
    if earlier is None:
        change, short_by = apply()
        earlier = commit(kitchen)
        if earlier is None:
            return _written(kitchen, change, short_by)
    response.status_code = status.HTTP_200_OK
    response.headers["Idempotent-Replayed"] = "true"
    return _written(kitchen, earlier)


def _lot(kitchen: Kitchen, lot_id: int) -> StockLot:
    lot = kitchen.db.get(StockLot, lot_id)
    if lot is None or lot.household_id != kitchen.household_id or lot.amount_milli <= 0:
        raise not_found("That packet")
    find(kitchen, lot.food_id)  # a food that's been removed or merged away
    return lot


def _place(kitchen: Kitchen, place_id: int) -> Place:
    place = kitchen.db.get(Place, place_id)
    if place is None or place.household_id != kitchen.household_id:
        raise not_found("That place")
    return place


def _short(food: Food, milli: int, size: FoodSize | None) -> str:
    """ "2 packets", "about ½ packet", "200 g", "5", "5 slices" for summaries. A count
    food's "5 left" is only for the pantry list: a summary says just "5"."""
    shown = amount_out(food, milli, size)
    text = shown.short.removesuffix(f"{NBSP}left")
    return f"about {text}" if shown.about else text


def _what(food: Food, milli: int, size: FoodSize | None) -> str:
    """The amount and the ingredient, for summaries: "2 packets Toor dal", "200 g
    Spinach", "5 Onion", "5 slices of Bread"."""
    joiner = " "
    if food.counted_as == "count":
        joiner = " of " if food.count_word else NBSP  # "5 slices of Bread", "5 Onion"
    return f"{_short(food, milli, size)}{joiner}{food.name}"


def _date(day: date) -> str:
    return f"{day.day} {day.strftime('%b')}"


class AddStock(BaseModel):
    food_id: int
    amount: AmountIn
    place_id: int | None = None
    use_by: date | None = None


@router.post("/stock", status_code=status.HTTP_201_CREATED)
def add_stock(body: AddStock, kitchen: Here, response: Response) -> StockWrite:
    """Add to the pantry. "2 packets" makes two packets, each with its own date."""

    def apply() -> tuple[Change, int]:
        food = find(kitchen, body.food_id)
        if food.staple:
            raise Problem(
                status.HTTP_409_CONFLICT,
                "staple",
                f"{food.name} is a staple, so it isn't counted.",
            )
        place = _place(kitchen, body.place_id) if body.place_id else default_place(kitchen, food)
        resolved = resolve(kitchen, food, body.amount)
        if resolved.milli <= 0:
            raise Problem(422, "too_small", "That's too small to add.")
        edit = StockEdit(kitchen)
        amounts: list[int]
        if resolved.size is not None:
            count = body.amount.amount
            whole = int(count)
            rest = count - whole
            if whole > MAX_LOTS:
                raise Problem(422, "too_many", f"Add at most {MAX_LOTS} at a time.")
            amounts = [resolved.size.amount_milli] * whole
            if rest > 0:
                amounts.append(round(rest * resolved.size.amount_milli))
        else:
            amounts = [resolved.milli]
        for milli in amounts:
            edit.new(
                StockLot(
                    household_id=kitchen.household_id,
                    food_id=food.id,
                    place_id=place.id,
                    amount_milli=milli,
                    size_id=resolved.size.id if resolved.size else None,
                    use_by=body.use_by,
                )
            )
        what = _what(food, resolved.milli, resolved.size or usual_size(kitchen, food.id))
        summary = f"Added {what} → {place.name}"
        return edit.record("added", summary, food.id), 0

    return stock_write(kitchen, response, apply)


class SetLeft(BaseModel):
    """What's left: a quick pick (¼ ½ ¾ Full, as a fraction of the packet) or an amount."""

    fraction: Annotated[Decimal, Field(ge=0, le=1, max_digits=6, decimal_places=4)] | None = None
    amount: AmountIn | None = None

    @model_validator(mode="after")
    def _one(self) -> SetLeft:
        if (self.fraction is None) == (self.amount is None):
            raise ValueError("Give either a fraction or an amount.")
        return self


@router.post("/stock/{lot_id}/left")
def set_left(lot_id: int, body: SetLeft, kitchen: Here, response: Response) -> StockWrite:
    """How much is left in this packet. Best guess is fine; it can go up too (Full)."""

    def apply() -> tuple[Change, int]:
        lot = _lot(kitchen, lot_id)
        food = find(kitchen, lot.food_id)
        size = (kitchen.db.get(FoodSize, lot.size_id) if lot.size_id else None) or usual_size(
            kitchen, food.id
        )
        if body.fraction is not None:
            if size is None:
                raise Problem(
                    422, "needs_amount", f"{food.name} has no packet size: type an amount."
                )
            milli = round(body.fraction * size.amount_milli)
        else:
            typed = body.amount
            if typed is None:  # pragma: no cover (validated)
                raise Problem(422, "needs_amount", "Type an amount.")
            milli = resolve(kitchen, food, typed).milli
        edit = StockEdit(kitchen)
        before = lot.amount_milli
        edit.touch(lot).amount_milli = milli
        summary = f"{food.name}: {_short(food, before, size)} → {_short(food, milli, size)}"
        return edit.record("set_left", summary, food.id), 0

    return stock_write(kitchen, response, apply)


class UsedSome(BaseModel):
    amount: AmountIn | None = None  # none: all of it


def _use(
    kind: Literal["used", "binned"], lot_id: int, body: UsedSome, kitchen: Kitchen
) -> tuple[Change, int]:
    lot = _lot(kitchen, lot_id)
    food = find(kitchen, lot.food_id)
    wanted = resolve(kitchen, food, body.amount).milli if body.amount else lot.amount_milli
    taken = min(wanted, lot.amount_milli)
    edit = StockEdit(kitchen)
    edit.touch(lot).amount_milli -= taken
    size = (kitchen.db.get(FoodSize, lot.size_id) if lot.size_id else None) or usual_size(
        kitchen, food.id
    )
    word = "Used" if kind == "used" else "Binned"
    summary = f"{word} {_what(food, taken, size)}"
    return edit.record(kind, summary, food.id), wanted - taken


@router.post("/stock/{lot_id}/used")
def used(
    lot_id: int, kitchen: Here, response: Response, body: UsedSome | None = None
) -> StockWrite:
    """Used it (all of it, or an amount). Never below zero: `short_by` says what was missing."""
    return stock_write(kitchen, response, lambda: _use("used", lot_id, body or UsedSome(), kitchen))


@router.post("/stock/{lot_id}/binned")
def binned(
    lot_id: int, kitchen: Here, response: Response, body: UsedSome | None = None
) -> StockWrite:
    return stock_write(
        kitchen, response, lambda: _use("binned", lot_id, body or UsedSome(), kitchen)
    )


class ToFreezer(BaseModel):
    use_by: date | None = None  # default: 3 months from today


@router.post("/stock/{lot_id}/to-freezer")
def to_freezer(
    lot_id: int, kitchen: Here, response: Response, body: ToFreezer | None = None
) -> StockWrite:
    """Move the whole packet to the Freezer, with a new use-by 3 months away."""

    def apply() -> tuple[Change, int]:
        lot = _lot(kitchen, lot_id)
        food = find(kitchen, lot.food_id)
        freezer = first_place(kitchen, "freezer")
        if freezer is None:  # pragma: no cover (every household has a freezer)
            raise not_found("The freezer")
        if lot.place_id == freezer.id:
            raise Problem(
                status.HTTP_409_CONFLICT, "already_frozen", "That's already in the freezer."
            )
        day = today(kitchen.household)
        edit = StockEdit(kitchen)
        edit.touch(lot)
        lot.place_id = freezer.id
        lot.use_by = (body.use_by if body and body.use_by else None) or add_months(
            day, FREEZER_MONTHS
        )
        lot.frozen_on = day
        summary = f"{food.name} → {freezer.name}, use by {_date(lot.use_by)}"
        return edit.record("to_freezer", summary, food.id), 0

    return stock_write(kitchen, response, apply)


class Move(BaseModel):
    place_id: int


@router.post("/stock/{lot_id}/move")
def move(lot_id: int, body: Move, kitchen: Here, response: Response) -> StockWrite:
    """Move the whole packet. Its use-by stays as it is."""

    def apply() -> tuple[Change, int]:
        lot = _lot(kitchen, lot_id)
        food = find(kitchen, lot.food_id)
        place = _place(kitchen, body.place_id)
        if place.id == lot.place_id:
            raise Problem(
                status.HTTP_409_CONFLICT, "already_there", f"That's already in {place.name}."
            )
        edit = StockEdit(kitchen)
        edit.touch(lot).place_id = place.id
        if place.kind != "freezer":
            lot.frozen_on = None
        summary = f"Moved {food.name} → {place.name}"
        return edit.record("moved", summary, food.id), 0

    return stock_write(kitchen, response, apply)


class LotPatch(BaseModel):
    use_by: date | None


@router.patch("/stock/{lot_id}")
def change_use_by(lot_id: int, body: LotPatch, kitchen: Here, response: Response) -> StockWrite:
    """Change (or clear) the use-by date."""

    def apply() -> tuple[Change, int]:
        lot = _lot(kitchen, lot_id)
        food = find(kitchen, lot.food_id)
        edit = StockEdit(kitchen)
        edit.touch(lot).use_by = body.use_by
        summary = (
            f"{food.name}: use by {_date(body.use_by)}"
            if body.use_by
            else f"{food.name}: no use-by date"
        )
        return edit.record("use_by", summary, food.id), 0

    return stock_write(kitchen, response, apply)


class FoodAmount(BaseModel):
    amount: AmountIn
    place_id: int | None = None


class AmountOrNone(AmountIn):
    """Like AmountIn, but 0 is allowed: "None left"."""

    amount: Annotated[Decimal, Field(ge=0, le=1_000_000, max_digits=13, decimal_places=3)]


class FoodLeft(BaseModel):
    amount: AmountOrNone
    place_id: int | None = None


def _scope(kitchen: Kitchen, food: Food, place_id: int | None) -> tuple[list[StockLot], bool]:
    if place_id is not None:
        place = _place(kitchen, place_id)
        return lots_of(kitchen, [food.id], place.id), place.kind == "freezer"
    return lots_of(kitchen, [food.id]), False


@router.post("/foods/{food_id}/used")
def food_used(food_id: int, body: FoodAmount, kitchen: Here, response: Response) -> StockWrite:
    """ "How much did you use?" on a group: taken from the packet that goes off first.
    Without a place, the freezer is left alone."""

    def apply() -> tuple[Change, int]:
        food = find(kitchen, food_id)
        wanted = resolve(kitchen, food, body.amount).milli
        lots, freezer = _scope(kitchen, food, body.place_id)
        kinds = {p.id: p.kind for p in places(kitchen.db, kitchen.household_id)}
        if not any(freezer or kinds.get(lot.place_id) != "freezer" for lot in lots):
            raise Problem(
                status.HTTP_409_CONFLICT,
                "nothing_left",
                f"There's no {food.name} left.",
            )
        edit = StockEdit(kitchen)
        short = take(kitchen, edit, lots, wanted, include_freezer=freezer)
        size = usual_size(kitchen, food.id)
        summary = f"Used {_what(food, wanted - short, size)}"
        return edit.record("used", summary, food.id), short

    return stock_write(kitchen, response, apply)


@router.post("/foods/{food_id}/left")
def food_left(food_id: int, body: FoodLeft, kitchen: Here, response: Response) -> StockWrite:
    """ "3 left" on a group: takes from the packets that go off first, or tops up the
    newest one if the number is higher. 0 is "None left": every packet is emptied
    (outside the freezer, unless the freezer is named)."""

    def apply() -> tuple[Change, int]:
        food = find(kitchen, food_id)
        target = resolve(kitchen, food, body.amount).milli
        lots, freezer = _scope(kitchen, food, body.place_id)
        if not freezer:
            kinds = {p.id: p.kind for p in places(kitchen.db, kitchen.household_id)}
            lots = [lot for lot in lots if kinds.get(lot.place_id) != "freezer"]
        total = sum(lot.amount_milli for lot in lots)
        edit = StockEdit(kitchen)
        if target < total:
            take(kitchen, edit, lots, total - target, include_freezer=freezer)
        elif target > total:
            if lots:
                newest = max(lots, key=lambda lot: (as_utc(lot.added_at), lot.id))
                edit.touch(newest).amount_milli += target - total
            else:
                place = (
                    _place(kitchen, body.place_id)
                    if body.place_id
                    else default_place(kitchen, food)
                )
                edit.new(
                    StockLot(
                        household_id=kitchen.household_id,
                        food_id=food.id,
                        place_id=place.id,
                        amount_milli=target,
                    )
                )
        else:
            raise Problem(
                status.HTTP_409_CONFLICT, "no_change", "That's how much there is already."
            )
        size = usual_size(kitchen, food.id)
        summary = f"{food.name}: {_short(food, total, size)} → {_short(food, target, size)}"
        return edit.record("set_left", summary, food.id), 0

    return stock_write(kitchen, response, apply)
