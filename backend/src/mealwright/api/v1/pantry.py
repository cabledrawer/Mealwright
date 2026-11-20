"""The Pantry: stock by place, Use soon, and every stock change (docs/dev/api-endpoints.md 6.4)."""

from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select

from mealwright import batches, date_kinds, restock
from mealwright.amounts import quarters_text, round_half_up
from mealwright.api.v1.context import Here, Kitchen
from mealwright.api.v1.foods import names_by_food
from mealwright.api.v1.schemas import (
    AmountIn,
    AmountOut,
    ChangeOut,
    CountedAsName,
    Ref,
    ShortAmount,
)
from mealwright.auth import SameOrigin
from mealwright.errors import TOO_LATE_TO_FREEZE, Problem, StoredInt, already_there, not_found
from mealwright.foods import PackReads, amount_out, change_out, find, resolve, usual_of, usual_size
from mealwright.history import commit, replayed
from mealwright.household import places, today, zone
from mealwright.models import (
    Change,
    ChangeLine,
    CookedRecord,
    Food,
    FoodSize,
    Place,
    StockLot,
    as_utc,
)
from mealwright.moment import Moment
from mealwright.names import fold, search_match
from mealwright.stock import (
    FREEZER_MONTHS,
    MAX_LOTS,
    StockEdit,
    add_months,
    default_place,
    first_place,
    lots_of,
    ordered,
    put_in,
    short_text,
    take,
    what_text,
)

router = APIRouter(tags=["pantry"], dependencies=[SameOrigin])


# --- Shapes ---------------------------------------------------------------------------------


class FoodBrief(BaseModel):
    id: int
    name: str
    counted_as: CountedAsName


class PlaceRef(BaseModel):
    id: int
    name: str
    kind: Literal["fridge", "freezer", "cupboard"]


# Changes whose new lots are not bought: typed in, counted in a stocktake, found at home.
FOUND_KINDS = ("found", "added", "stocktake")

DateKindName = Literal["use_by", "best_before"]


class LotOut(BaseModel):
    id: int
    stock: AmountOut
    use_by: date | None
    days_left: int | None
    # Use by or Best before (0.8): the ingredient's date type decides the words and whether a
    # date not yet passed counts as Use soon (a Best before one only once it has passed).
    date_kind: DateKindName
    use_soon: bool
    added_on: date
    # How it got here (F201): "found" for a lot typed in, counted in a stocktake or found at home
    # while shopping; "bought" for the rest, and for anything the change record can't tell.
    how_added: Literal["bought", "found"] = "bought"
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
    date_kind: DateKindName
    use_soon: bool
    running_low: bool
    lots: list[LotOut]


class TubRow(BaseModel):
    """The tubs of one batch in one place, as one row (F131, 0.8): "Lemon rice · 2 tubs"."""

    batch_id: int
    tub_id: int  # the soonest tub of the row: the one "Eat it on…" puts in a meal
    recipe_name: str
    colour: str | None
    tubs: int  # tubs with some left
    words: str  # "2 tubs", "¾ tub"
    use_by: date  # the soonest
    days_left: int
    use_soon: bool


class PlaceOut(PlaceRef):
    items: int
    groups: list[GroupOut]
    tubs: list[TubRow]


class PantryCounts(BaseModel):
    items: int
    tubs: int
    use_soon: int
    running_low: int


class PantryStaple(Ref):
    # When it was last restocked (0.7 K5); null if never. Read-only here: see PATCH /foods/{id}.
    restocked_at: Moment | None = None
    restocked_on: date | None = None  # the household's own day of it
    restocked_days_ago: int | None = None


def pantry_staple(kitchen: Kitchen, food: Food, at: datetime | None) -> PantryStaple:
    on, days_ago = restock.day(kitchen.household, at)
    return PantryStaple(
        id=food.id, name=food.name, restocked_at=at, restocked_on=on, restocked_days_ago=days_ago
    )


class PantryOut(BaseModel):
    today: date
    counts: PantryCounts
    places: list[PlaceOut]
    staples: list[PantryStaple]


class UseSoonLot(LotOut):
    """One row per ingredient and place (0.8): `id` is its soonest packet that is Use soon,
    `stock` the total of those packets, `lots_count` how many of them ("2 packets") and
    `lot_ids` which, soonest first (Binned and To freezer with `soon` take them all)."""

    food: FoodBrief
    place: PlaceRef
    lots_count: int
    lot_ids: list[int]


class UseSoonTub(TubRow):
    """A batch's tubs in one place that are Use soon (a use-by up to the Use soon days ahead,
    or passed), as the "Eat it on…" card: "Lemon rice · Fridge · 2 tubs"."""

    place: PlaceRef


class UseSoonOut(BaseModel):
    today: date
    lots: list[UseSoonLot]
    tubs: list[UseSoonTub] = []


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
        self._other_names: dict[int, list[str]] | None = None
        self._found: set[int] | None = None
        self._reads = PackReads(kitchen)
        self._by_id: dict[int, FoodSize] = {}
        self._indexed = -1

    def load(self, food_ids: Iterable[int]) -> None:
        """Read the ingredients and their sizes for all these ids at once (a fixed number of
        statements), so describing each group asks the database nothing more. Both reads keep
        the household filter; an id that isn't found here is read the old way when asked for."""
        every = sorted(set(food_ids))
        wanted = [i for i in every if i not in self._foods]
        db = self.kitchen.db
        for start in range(0, len(wanted), PackReads.CHUNK):
            chunk = wanted[start : start + PackReads.CHUNK]
            for found in db.scalars(
                select(Food).where(
                    Food.household_id == self.kitchen.household_id, Food.id.in_(chunk)
                )
            ):
                self._foods[found.id] = found
        self._reads.load(every)

    def _size_index(self) -> dict[int, FoodSize]:
        """Every size read so far, by size id (rebuilt only when more were read)."""
        known = self._reads.known_sizes()
        if self._indexed != len(known):
            self._by_id = {size.id: size for size in known}
            self._indexed = len(known)
        return self._by_id

    def ordered(self, lots: Iterable[StockLot]) -> list[StockLot]:
        """Packets in the order they are used, from what is already read: no statement per
        group, only (for a food not read yet) its sizes once."""
        lots = list(lots)
        self._reads.load({lot.food_id for lot in lots})
        index = self._size_index()
        amounts = {
            lot.size_id: index[lot.size_id].amount_milli
            for lot in lots
            if lot.size_id is not None and lot.size_id in index
        }
        return ordered(
            self.kitchen, lots, {pid: place.kind for pid, place in self.places.items()}, amounts
        )

    def found_lots(self) -> set[int]:
        """The lots that came in as "found at home", from the change that made each one: a
        change of a found kind with a line that took the lot from nothing (F201)."""
        if self._found is None:
            rows = self.kitchen.db.scalars(
                select(ChangeLine.lot_id)
                .join(Change, Change.id == ChangeLine.change_id)
                .where(
                    ChangeLine.household_id == self.kitchen.household_id,
                    ChangeLine.lot_id.is_not(None),
                    ChangeLine.amount_before_milli == 0,
                    Change.kind.in_(FOUND_KINDS),
                )
            )
            self._found = {lot_id for lot_id in rows if lot_id is not None}
        return self._found

    def kind(self, food: Food) -> date_kinds.DateKind:
        """Use by or Best before for this ingredient."""
        if self._other_names is None:
            self._other_names = names_by_food(self.kitchen)
        place = self.places.get(food.place_id) if food.place_id is not None else None
        return date_kinds.date_kind(
            food, [food.name, *self._other_names.get(food.id, [])], place.kind if place else None
        )

    def food(self, food_id: int) -> Food:
        if food_id not in self._foods:
            found = self.kitchen.db.get(Food, food_id)
            # Never another household's ingredient, whatever row points at it.
            if found is None or found.household_id != self.kitchen.household_id:
                raise not_found("That ingredient")
            self._foods[food_id] = found
        return self._foods[food_id]

    def usual(self, food_id: int) -> FoodSize | None:
        if food_id not in self._usual:
            self._usual[food_id] = usual_of(self._reads.sizes(food_id))
        return self._usual[food_id]

    def size(self, size_id: int | None) -> FoodSize | None:
        if size_id is None:
            return None
        if size_id not in self._sizes:
            self._sizes[size_id] = self._size_index().get(size_id) or self.kitchen.db.get(
                FoodSize, size_id
            )
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

    def is_soon(self, use_by: date | None, kind: str = "use_by") -> bool:
        """A Use by date from the past up to the Use soon days ahead; a Best before date only
        once it has passed (cabledrawer 7 Nov)."""
        if use_by is None or use_by > self.soon:
            return False
        return kind == "use_by" or use_by < self.today

    def place_ref(self, place_id: int) -> PlaceRef:
        place = self.places[place_id]
        return PlaceRef(id=place.id, name=place.name, kind=place.kind)  # type: ignore[arg-type]

    def lot_size(self, lot: StockLot) -> FoodSize | None:
        size = self.size(lot.size_id)
        if size is not None:
            return size
        usual = self.usual(lot.food_id)
        # A lot with no size that holds more than one pack (a capped tick, or 2 kg added in
        # grams with a 1 kg bag) isn't a packet: no "as sold", no ¼ ½ ¾ picks (proposed, for
        # cabledrawer).
        if usual is not None and lot.amount_milli > usual.amount_milli:
            return None
        return usual

    def lot_out(self, lot: StockLot) -> LotOut:
        food = self.food(lot.food_id)
        size = self.lot_size(lot)
        kind = self.kind(food)
        return LotOut(
            id=lot.id,
            stock=amount_out(food, lot.amount_milli, size),
            use_by=lot.use_by,
            days_left=self.days_left(lot.use_by),
            date_kind=kind,
            use_soon=self.is_soon(lot.use_by, kind),
            added_on=as_utc(lot.added_at).astimezone(zone(self.kitchen.household)).date(),
            how_added="found" if lot.id in self.found_lots() else "bought",
            frozen_on=lot.frozen_on,
            size_id=lot.size_id,
            open=size is not None and 0 < lot.amount_milli < size.amount_milli,
        )

    def group(self, food_id: int, place_id: int, lots: list[StockLot]) -> GroupOut:
        food = self.food(food_id)
        lots = self.ordered([lot for lot in lots if lot.amount_milli > 0])
        dates = [lot.use_by for lot in lots if lot.use_by is not None]
        first = min(dates) if dates else None
        kind = self.kind(food)
        return GroupOut(
            food=FoodBrief(id=food.id, name=food.name, counted_as=food.counted_as),  # type: ignore[arg-type]
            place=self.place_ref(place_id),
            stock=amount_out(food, sum(lot.amount_milli for lot in lots), self.usual(food.id)),
            lots_count=len(lots),
            dates_count=len(set(dates)),
            use_by=first,
            days_left=self.days_left(first),
            date_kind=kind,
            use_soon=any(self.is_soon(d, kind) for d in dates),
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


def tub_rows(
    view: Pantry, wanted: Callable[[str], bool] = lambda _: True
) -> dict[int, list[TubRow]]:
    """Tubs left (in no meal), one row per batch and place, soonest first, keyed by place.
    A tub of a session not cooked yet is left out. A tub with no known place is shown in the
    first fridge. `wanted` keeps the recipe names a search finds."""
    found, _ = batches.tubs_left(view.kitchen, 1000)
    # A Batch cook session's tubs are listed only once its Cooked it is done (F230, cabledrawer 12
    # Nov): until then the food isn't cooked. A Cook once batch outside a session shows as before.
    cooked_ids = set(
        view.kitchen.db.scalars(
            select(CookedRecord.batch_id).where(
                CookedRecord.household_id == view.kitchen.household_id,
                CookedRecord.batch_id.is_not(None),
            )
        )
    )
    found = [t for t in found if t.batch.session_id is None or t.batch.id in cooked_ids]
    fridge = next((p for p in view.places.values() if p.kind == "fridge"), None)
    fallback = fridge or next(iter(view.places.values()), None)
    by_row: dict[tuple[int, int], list[Any]] = defaultdict(list)
    for left in found:
        place = view.places.get(left.tub.place_id) if left.tub.place_id is not None else None
        place = place or fallback
        if place is not None and wanted(left.batch.recipe_name):
            by_row[(place.id, left.batch.id)].append(left)
    rows: dict[int, list[TubRow]] = defaultdict(list)
    for (place_id, batch_id), tubs in by_row.items():
        first = min(t.tub.use_by for t in tubs)
        if len(tubs) == 1 and tubs[0].tub.amount_quarters < 4:
            words = f"{quarters_text(tubs[0].tub.amount_quarters)} tub"
        else:
            words = f"{len(tubs)} {'tub' if len(tubs) == 1 else 'tubs'}"
        rows[place_id].append(
            TubRow(
                batch_id=batch_id,
                tub_id=min(tubs, key=lambda t: (t.tub.use_by, t.tub.id)).tub.id,
                recipe_name=tubs[0].batch.recipe_name,
                colour=tubs[0].batch.colour,
                tubs=len(tubs),
                words=words,
                use_by=first,
                days_left=(first - view.today).days,
                use_soon=first <= view.soon,
            )
        )
    for place_rows in rows.values():
        place_rows.sort(key=lambda r: (r.use_by, r.recipe_name.casefold()))
    return rows


def _sort_key(group: GroupOut) -> tuple[bool, date, str]:
    return (group.use_by is None, group.use_by or date.max, group.food.name.casefold())


# --- Reading ----------------------------------------------------------------------------------


@router.get("/pantry")
def pantry(
    kitchen: Here,
    filter: Literal["all", "use_soon", "running_low", "staples"] = "all",
    q: Annotated[str, Query(max_length=100)] = "",
) -> PantryOut:
    """The whole Pantry screen in one call: places (tabs on phone, columns on desktop), each
    food's packets grouped with their dates, and the staples. `q` searches by any name the
    way Ingredients does (other names too). Each place's `items` counts what is shown, under the
    search and the filter, so it never disagrees with the card's "Nothing in the…" line."""
    view = Pantry(kitchen)
    needle = fold(q.strip())
    names = names_by_food(kitchen) if needle else {}
    by_group: dict[tuple[int, int], list[StockLot]] = defaultdict(list)
    every_lot = lots_of(kitchen)
    view.load(lot.food_id for lot in every_lot)
    for lot in every_lot:
        by_group[(lot.food_id, lot.place_id)].append(lot)
    groups: dict[int, list[GroupOut]] = defaultdict(list)
    all_groups = []
    for (food_id, place_id), lots in by_group.items():
        food = view.food(food_id)
        if food.staple or food.removed_at is not None or food.merged_into_id is not None:
            continue
        group = view.group(food_id, place_id, lots)
        all_groups.append(group)
        if needle and search_match(food.name, names.get(food.id, []), needle) is None:
            continue
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
    staple_foods = list(staples)
    dates = restock.restocked(kitchen.db, kitchen.household_id, staple_foods)
    all_tubs = tub_rows(view)
    tubs = (
        tub_rows(view, lambda name: search_match(name, [], needle) is not None)
        if needle
        else all_tubs
    )
    if filter in ("running_low", "staples"):
        tubs = {}
    elif filter == "use_soon":
        tubs = {pid: [r for r in rows if r.use_soon] for pid, rows in tubs.items()}
    return PantryOut(
        today=view.today,
        counts=PantryCounts(
            items=len(all_groups),
            tubs=sum(r.tubs for rows in all_tubs.values() for r in rows),
            use_soon=sum(any(lot.use_soon for lot in g.lots) for g in all_groups)
            + sum(1 for rows in all_tubs.values() for r in rows if r.use_soon),
            running_low=len({g.food.id for g in all_groups if g.running_low}),
        ),
        places=[
            PlaceOut(
                id=place.id,
                name=place.name,
                kind=place.kind,  # type: ignore[arg-type]
                items=len(groups.get(place.id, [])) + len(tubs.get(place.id, [])),
                groups=sorted(groups.get(place.id, []), key=_sort_key),
                tubs=tubs.get(place.id, []),
            )
            for place in view.places.values()
        ],
        staples=[pantry_staple(kitchen, f, dates.get(f.id)) for f in staple_foods],
    )


@router.get("/pantry/use-soon")
def use_soon(kitchen: Here) -> UseSoonOut:
    """What to use up: one row per ingredient and place (0.8), soonest first.
    A Use by date from the past up to the day after tomorrow (2 days, in the household's own
    time zone) counts; a Best before date only once it has passed. A row's amount is all of
    that ingredient's packets in the place that count ("2 packets"), and its date the
    soonest. Leftover tubs that are Use soon come as `tubs` (one per batch and place), soonest
    first; a passed one has no Eat it on…."""
    view = Pantry(kitchen)
    by_group: dict[tuple[int, int], list[StockLot]] = defaultdict(list)
    every_lot = lots_of(kitchen)
    view.load(lot.food_id for lot in every_lot)
    for lot in every_lot:
        food = view.food(lot.food_id)
        if not food.staple and food.removed_at is None and food.merged_into_id is None:
            by_group[(lot.food_id, lot.place_id)].append(lot)
    found = []
    for (food_id, place_id), lots in by_group.items():
        food = view.food(food_id)
        kind = view.kind(food)
        soon = [lot for lot in view.ordered(lots) if view.is_soon(lot.use_by, kind)]
        if not soon:
            continue
        soon.sort(key=lambda lot: (lot.use_by or date.max, lot.id))
        row = view.lot_out(soon[0])
        if len(soon) > 1:
            total = sum(lot.amount_milli for lot in soon)
            row.stock = amount_out(food, total, view.usual(food.id))
            row.open = False
        found.append(
            UseSoonLot(
                **row.model_dump(),
                food=FoodBrief(id=food.id, name=food.name, counted_as=food.counted_as),  # type: ignore[arg-type]
                place=view.place_ref(place_id),
                lots_count=len(soon),
                lot_ids=[lot.id for lot in soon],
            )
        )
    found.sort(key=lambda lot: (lot.use_by or date.max, lot.food.name.casefold()))
    soon_tubs = [
        UseSoonTub(**row.model_dump(), place=view.place_ref(place_id))
        for place_id, rows in tub_rows(view).items()
        for row in rows
        if row.use_soon
    ]
    soon_tubs.sort(key=lambda t: (t.use_by, t.recipe_name.casefold(), t.place.id))
    return UseSoonOut(today=view.today, lots=found, tubs=soon_tubs)


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


def _date(day: date) -> str:
    return f"{day.day} {day.strftime('%b')}"


class AddStock(BaseModel):
    food_id: StoredInt
    amount: AmountIn
    place_id: StoredInt | None = None
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
                f"{food.name} is a staple, so it isn’t counted.",
            )
        place = _place(kitchen, body.place_id) if body.place_id else default_place(kitchen, food)
        resolved = resolve(kitchen, food, body.amount)
        if resolved.milli <= 0:
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "too_small", "That’s too small to add."
            )
        edit = StockEdit(kitchen)
        amounts: list[int]
        if resolved.size is not None:
            count = body.amount.amount
            whole = int(count)
            rest = count - whole
            if whole > MAX_LOTS:
                raise Problem(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "too_many",
                    f"Add at most {MAX_LOTS} at a time.",
                )
            amounts = [resolved.size.amount_milli] * whole
            if rest > 0:
                amounts.append(round_half_up(rest * resolved.size.amount_milli))
        else:
            amounts = [resolved.milli]
        put_in(kitchen, edit, food, place, amounts, resolved.size, body.use_by)
        what = what_text(food, resolved.milli, resolved.size or usual_size(kitchen, food.id))
        summary = f"Added {what} → {place.name}"
        return edit.record("added", summary, food.id), 0

    return stock_write(kitchen, response, apply)


class SetLeft(BaseModel):
    """What's left: a quick pick (¼ ½ ¾ Full, as a fraction of the packet) or an amount."""

    fraction: (
        Annotated[Decimal, Field(ge=0, le=1, max_digits=6, decimal_places=4), ShortAmount] | None
    ) = None
    amount: AmountIn | None = None

    @model_validator(mode="after")
    def _one(self) -> SetLeft:
        if (self.fraction is None) == (self.amount is None):
            raise ValueError("Give either a fraction or an amount.")
        return self


@router.post("/stock/{stock_id}/set-left")
def set_left(stock_id: StoredInt, body: SetLeft, kitchen: Here, response: Response) -> StockWrite:
    """How much is left in this packet. Best guess is fine; it can go up too (Full)."""

    def apply() -> tuple[Change, int]:
        lot = _lot(kitchen, stock_id)
        food = find(kitchen, lot.food_id)
        size = (kitchen.db.get(FoodSize, lot.size_id) if lot.size_id else None) or usual_size(
            kitchen, food.id
        )
        if body.fraction is not None:
            too_big = (
                lot.size_id is None and size is not None and lot.amount_milli > size.amount_milli
            )
            if size is not None and too_big:  # a lot bigger than one packet (a capped tick)
                raise Problem(
                    422, "needs_amount", f"That’s more than one {size.name}: type an amount."
                )
            if size is None:
                raise Problem(
                    422, "needs_amount", f"{food.name} has no packet size: type an amount."
                )
            milli = round_half_up(body.fraction * size.amount_milli)
        else:
            typed = body.amount
            if typed is None:  # pragma: no cover (validated)
                raise Problem(
                    status.HTTP_422_UNPROCESSABLE_CONTENT, "needs_amount", "Type an amount."
                )
            milli = resolve(kitchen, food, typed).milli
        edit = StockEdit(kitchen)
        before = lot.amount_milli
        edit.touch(lot).amount_milli = milli
        summary = f"{food.name}: {short_text(food, before, size)} → {short_text(food, milli, size)}"
        return edit.record("set_left", summary, food.id), 0

    return stock_write(kitchen, response, apply)


class UsedSome(BaseModel):
    amount: AmountIn | None = None  # none: all of it


class BinnedSome(UsedSome):
    # Use soon's row (0.8): every packet of this ingredient in this place that counts for Use
    # soon, not just this one, in one change with one Undo. Only with no amount.
    soon: bool = False


def _soon_lots(kitchen: Kitchen, lot: StockLot) -> list[StockLot]:
    """The packets a Use soon row stands for: this ingredient's in this place that count as
    soon (the same rule as `use_soon`), and always the packet named."""
    view = Pantry(kitchen)
    kind = view.kind(view.food(lot.food_id))
    lots = [
        other
        for other in lots_of(kitchen, [lot.food_id], lot.place_id)
        if other.id == lot.id or view.is_soon(other.use_by, kind)
    ]
    return sorted(lots, key=lambda other: (other.use_by or date.max, other.id))


def _bin_soon(lot_id: int, kitchen: Kitchen) -> tuple[Change, int]:
    lot = _lot(kitchen, lot_id)
    food = find(kitchen, lot.food_id)
    edit = StockEdit(kitchen)
    total = 0
    for other in _soon_lots(kitchen, lot):
        total += other.amount_milli
        edit.touch(other).amount_milli = 0
    summary = f"Binned {what_text(food, total, usual_size(kitchen, food.id))}"
    return edit.record("binned", summary, food.id), 0


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
    summary = f"{word} {what_text(food, taken, size)}"
    return edit.record(kind, summary, food.id), wanted - taken


@router.post("/stock/{stock_id}/use")
def used(
    stock_id: StoredInt, kitchen: Here, response: Response, body: UsedSome | None = None
) -> StockWrite:
    """Used it (all of it, or an amount). Never below zero: `short_by` says what was missing."""
    return stock_write(
        kitchen, response, lambda: _use("used", stock_id, body or UsedSome(), kitchen)
    )


@router.post("/stock/{stock_id}/bin")
def binned(
    stock_id: StoredInt, kitchen: Here, response: Response, body: BinnedSome | None = None
) -> StockWrite:
    """Binned it (all of it, or an amount). With `soon`, every packet of the Use soon row."""
    if body and body.soon:
        if body.amount is not None:
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "soon_with_amount",
                "Bin all of a Use soon row, or an amount of one packet.",
            )
        return stock_write(kitchen, response, lambda: _bin_soon(stock_id, kitchen))
    return stock_write(
        kitchen, response, lambda: _use("binned", stock_id, body or UsedSome(), kitchen)
    )


class ToFreezer(BaseModel):
    use_by: date | None = None  # default: 3 months from today
    soon: bool = False  # every packet of the Use soon row (0.8), not just this one


@router.post("/stock/{stock_id}/freeze")
def to_freezer(
    stock_id: StoredInt, kitchen: Here, response: Response, body: ToFreezer | None = None
) -> StockWrite:
    """Move the whole packet to the Freezer, with a new use-by 3 months away. With `soon`,
    every packet of the Use soon row. A Use by packet whose date has passed (from the day after)
    is refused: `422 too_late_to_freeze`. Best before food can always be frozen."""

    def apply() -> tuple[Change, int]:
        lot = _lot(kitchen, stock_id)
        food = find(kitchen, lot.food_id)
        freezer = first_place(kitchen, "freezer")
        if freezer is None:  # pragma: no cover (every household has a freezer)
            raise not_found("The freezer")
        if lot.place_id == freezer.id:
            raise already_there("That’s already in the freezer.")
        day = today(kitchen.household)
        use_by = (body.use_by if body and body.use_by else None) or add_months(day, FREEZER_MONTHS)
        moving = _soon_lots(kitchen, lot) if body and body.soon else [lot]
        if Pantry(kitchen).kind(food) == date_kinds.USE_BY and any(
            one.use_by is not None and one.use_by < day for one in moving
        ):
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "too_late_to_freeze",
                TOO_LATE_TO_FREEZE,
            )
        edit = StockEdit(kitchen)
        for one in moving:
            edit.touch(one)
            one.place_id = freezer.id
            one.use_by = use_by
            one.frozen_on = day
        summary = f"{food.name} → {freezer.name}, use by {_date(use_by)}"
        return edit.record("to_freezer", summary, food.id), 0

    return stock_write(kitchen, response, apply)


class Move(BaseModel):
    place_id: StoredInt


@router.post("/stock/{stock_id}/move")
def move(stock_id: StoredInt, body: Move, kitchen: Here, response: Response) -> StockWrite:
    """Move the whole packet. Its use-by stays as it is."""

    def apply() -> tuple[Change, int]:
        lot = _lot(kitchen, stock_id)
        food = find(kitchen, lot.food_id)
        place = _place(kitchen, body.place_id)
        if place.id == lot.place_id:
            raise already_there(f"That’s already in {place.name}.")
        edit = StockEdit(kitchen)
        edit.touch(lot).place_id = place.id
        if place.kind != "freezer":
            lot.frozen_on = None
        summary = f"Moved {food.name} → {place.name}"
        return edit.record("moved", summary, food.id), 0

    return stock_write(kitchen, response, apply)


class LotPatch(BaseModel):
    use_by: date | None


@router.patch("/stock/{stock_id}")
def change_use_by(
    stock_id: StoredInt, body: LotPatch, kitchen: Here, response: Response
) -> StockWrite:
    """Change (or clear) the use-by date."""

    def apply() -> tuple[Change, int]:
        lot = _lot(kitchen, stock_id)
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
    place_id: StoredInt | None = None


class AmountOrNone(AmountIn):
    """Like AmountIn, but 0 is allowed: "None left"."""

    amount: Annotated[
        Decimal, Field(ge=0, le=1_000_000, max_digits=13, decimal_places=3), ShortAmount
    ]


class FoodLeft(BaseModel):
    amount: AmountOrNone
    place_id: StoredInt | None = None


def _scope(kitchen: Kitchen, food: Food, place_id: int | None) -> tuple[list[StockLot], bool]:
    if place_id is not None:
        place = _place(kitchen, place_id)
        return lots_of(kitchen, [food.id], place.id), place.kind == "freezer"
    return lots_of(kitchen, [food.id]), False


@router.post("/foods/{food_id}/use")
def food_used(
    food_id: StoredInt, body: FoodAmount, kitchen: Here, response: Response
) -> StockWrite:
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
                f"There’s no {food.name} left.",
            )
        edit = StockEdit(kitchen)
        short = take(kitchen, edit, lots, wanted, include_freezer=freezer)
        size = usual_size(kitchen, food.id)
        summary = f"Used {what_text(food, wanted - short, size)}"
        return edit.record("used", summary, food.id), short

    return stock_write(kitchen, response, apply)


@router.post("/foods/{food_id}/set-left")
def food_left(food_id: StoredInt, body: FoodLeft, kitchen: Here, response: Response) -> StockWrite:
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
            raise already_there("That’s how much there is already.")  # proposed, for cabledrawer
        size = usual_size(kitchen, food.id)
        summary = f"{food.name}: {short_text(food, total, size)} → {short_text(food, target, size)}"
        return edit.record("set_left", summary, food.id), 0

    return stock_write(kitchen, response, apply)
