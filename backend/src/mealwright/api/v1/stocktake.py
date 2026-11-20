"""The Stocktake: go through the home place by place and say how much of each ingredient there
is (F118, 0.8; docs/dev/api-endpoints.md 6.5a).

Each answer is saved as it is tapped, as its own stock change (kind `stocktake`) with Undo. The
progress is kept on the server for the household (`stocktake_place`, `stocktake_entry`), so it
carries on from any phone and anyone can finish it. It is online-only (not carried by the
offline queue): a stocktake is a sit-down count that needs the server's progress and the stock
as it is now (docs/dev/sync-protocol.md 4.5).
"""

from collections import defaultdict
from collections.abc import Callable
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from mealwright import restock
from mealwright.amounts import NBSP, exact_text
from mealwright.api.v1.context import Here, Kitchen
from mealwright.api.v1.foods import NewSize, _size_amount, names_by_food
from mealwright.api.v1.pantry import FoodBrief, PlaceRef
from mealwright.api.v1.schemas import (
    AmountOut,
    ChangeOut,
    PackSuggestion,
    ShortAmount,
    SizeOut,
)
from mealwright.auth import SameOrigin
from mealwright.errors import Problem, StoredInt, not_found
from mealwright.events import note_pantry
from mealwright.foods import (
    add_size,
    all_foods,
    amount_out,
    change_out,
    find,
    pack_suggestions,
    size_out,
)
from mealwright.history import FoodEdit, commit, replayed
from mealwright.household import places
from mealwright.models import (
    Change,
    Food,
    FoodSize,
    Place,
    StockLot,
    StocktakeEntry,
    StocktakePlace,
    utcnow,
)
from mealwright.removals import mark_earlier_stocktake
from mealwright.stock import StockEdit, lot_amounts, lots_of, put_in, take

router = APIRouter(tags=["stocktake"], dependencies=[SameOrigin])

# The picks on a packet: None · ¼ · ½ · ¾ · Full.
QUARTERS = (Decimal(0), Decimal("0.25"), Decimal("0.5"), Decimal("0.75"), Decimal(1))
MORE_MOST = 20  # "more packets" besides the open one
# A pack word that is counted whole ("2 tins", minus and plus; cabledrawer 7 Nov; "can", "cans"
# and the plural too, cabledrawer 11 Nov). Jars, bags, bottles and the rest keep the picks. The one
# rule: kept here (compared without case), sent to the screen on each row.
COUNTED_WHOLE = frozenset({"tin", "tins", "can", "cans"})


# --- Shapes ---------------------------------------------------------------------------------


def _counting(food: Food, size: FoodSize | None) -> tuple[int, str | None, str | None] | None:
    """How the ingredient is counted whole, or None (it has the picks): (the amount of one,
    its word, its plural). An ingredient counted as a count: one is 1; one whose pack word is
    "tin": the tin's size."""
    if food.counted_as == "count":
        return 1000, food.count_word, food.count_word_plural
    if size is not None and size.amount_milli > 0 and size.name.casefold() in COUNTED_WHOLE:
        return size.amount_milli, size.name, size.plural
    return None


class StocktakeAnswerOut(BaseModel):
    """What was answered, as the screen shows it: a pick (`fraction` 0 to 1 of the open
    packet, `more` whole packets besides it) or, for an ingredient counted one by one, `count`."""

    fraction: Decimal | None
    more: int
    count: Decimal | None


class StocktakeRow(BaseModel):
    food: FoodBrief
    staple: bool
    restocked_on: date | None  # a staple's Restocked date (null: never)
    restocked_days_ago: int | None
    added: bool  # put here with "+ Something else", not kept here
    answered: bool
    stock: AmountOut  # all of it in this place now
    pack: SizeOut | None  # its Usual size; null: ask once (not for a staple or a counted one)
    pack_suggestions: list[PackSuggestion]  # the common sizes to ask with
    answer: StocktakeAnswerOut | None  # null until answered (and again after an Undo)
    # What is there now, as the picks read it (answered or not): the open packet's share and
    # the whole packets besides it, so the count shows before a pick and a pick keeps it.
    fraction_now: Decimal | None
    more_now: int
    # Counted one by one (an ingredient counted as a count, or one whose pack is a tin): the
    # screen shows minus and plus buttons with `count_now` and the word, and no fractions.
    counted: bool
    count_now: Decimal | None
    count_word: str | None  # "tin", "slice": for "2 tins"; null: none
    count_word_plural: str | None


class StocktakePlaceStep(PlaceRef):
    finished: bool
    answered: int
    total: int


class StocktakeOut(BaseModel):
    """The places in the Settings order, and where to carry on: the first not finished."""

    places: list[StocktakePlaceStep]
    current_place_id: int | None
    started: bool
    complete: bool


class PlaceStocktake(BaseModel):
    place: PlaceRef
    number: int  # "Place 3 of 5"
    of: int
    finished: bool
    answered: int
    total: int
    previous: PlaceRef | None
    next: PlaceRef | None
    rows: list[StocktakeRow]


class StocktakeWrite(BaseModel):
    change: ChangeOut | None  # null when nothing changed (it was already so)
    row: StocktakeRow
    answered: int
    total: int


# --- Reading --------------------------------------------------------------------------------


def _place(kitchen: Kitchen, place_id: int) -> Place:
    place = kitchen.db.get(Place, place_id)
    if place is None or place.household_id != kitchen.household_id:
        raise not_found("That place")
    return place


def _ref(place: Place) -> PlaceRef:
    return PlaceRef(id=place.id, name=place.name, kind=place.kind)  # type: ignore[arg-type]


class Stocktake:
    """What the stocktake knows, loaded once per request."""

    def __init__(self, kitchen: Kitchen) -> None:
        self.kitchen = kitchen
        self.db = kitchen.db
        self.places = places(self.db, kitchen.household_id)
        self.foods = {f.id: f for f in all_foods(kitchen)}
        self.entries: dict[tuple[int, int], StocktakeEntry] = {
            (e.place_id, e.food_id): e
            for e in self.db.scalars(
                select(StocktakeEntry).where(StocktakeEntry.household_id == kitchen.household_id)
            )
        }
        self.finished = set(
            self.db.scalars(
                select(StocktakePlace.place_id).where(
                    StocktakePlace.household_id == kitchen.household_id
                )
            )
        )
        self.lots: dict[int, dict[int, list[StockLot]]] = defaultdict(lambda: defaultdict(list))
        for lot in lots_of(kitchen):
            self.lots[lot.place_id][lot.food_id].append(lot)
        wanted = [e.change_id for e in self.entries.values() if e.change_id is not None]
        self.undone: set[int] = set()
        if wanted:
            self.undone = set(
                self.db.scalars(
                    select(Change.id).where(
                        Change.id.in_(wanted), Change.undone_by_change_id.is_not(None)
                    )
                )
            )
        self._sizes: dict[int, list[FoodSize]] | None = None
        self._other_names: dict[int, list[str]] | None = None

    # -- who is in a place --

    def members(self, place_id: int) -> list[Food]:
        """Every ingredient usually kept in the place or with stock there, and those added
        there with "+ Something else", A to Z."""
        ids = {f.id for f in self.foods.values() if f.place_id == place_id}
        ids |= set(self.lots.get(place_id, {}))
        ids |= {food_id for (pid, food_id) in self.entries if pid == place_id}
        found = [self.foods[i] for i in ids if i in self.foods]
        return sorted(found, key=lambda f: (f.name.casefold(), f.id))

    def is_answered(self, place_id: int, food_id: int) -> bool:
        entry = self.entries.get((place_id, food_id))
        return bool(
            entry
            and entry.answered
            and (entry.change_id is None or entry.change_id not in self.undone)
        )

    def progress(self, place_id: int) -> tuple[int, int]:
        # A staple isn't counted, so it is neither done nor still to do ("N of N" can be reached).
        found = [f for f in self.members(place_id) if not f.staple]
        return sum(self.is_answered(place_id, f.id) for f in found), len(found)

    # -- sizes --

    def usual(self, food_id: int) -> FoodSize | None:
        if self._sizes is None:
            self._sizes = defaultdict(list)
            for size in self.db.scalars(
                select(FoodSize)
                .where(FoodSize.household_id == self.kitchen.household_id)
                .order_by(FoodSize.position, FoodSize.id)
            ):
                self._sizes[size.food_id].append(size)
        found = self._sizes.get(food_id, [])
        return next((s for s in found if s.usual), found[0] if found else None)

    def names(self, food: Food) -> list[str]:
        if self._other_names is None:
            self._other_names = names_by_food(self.kitchen)
        return self._other_names.get(food.id, [])

    # -- a row --

    def stock_in(self, place_id: int, food_id: int) -> int:
        return sum(lot.amount_milli for lot in self.lots.get(place_id, {}).get(food_id, []))

    def counting(self, food: Food) -> tuple[int, str | None, str | None] | None:
        return _counting(food, self.usual(food.id))

    def count_now(self, food: Food, place_id: int) -> Decimal | None:
        """How many there are now, for a counted row (tins to the nearest whole one)."""
        unit = self.counting(food)
        if unit is None:
            return None
        total = self.stock_in(place_id, food.id)
        if food.counted_as == "count":
            return Decimal(total) / 1000
        return Decimal((2 * total + unit[0]) // (2 * unit[0]))

    def reading(self, food: Food, place_id: int) -> tuple[Decimal | None, int]:
        """What is in the place as the picks read it: (the open packet's share, whole packets
        besides it), to the nearest quarter. Unknown (no pack size, or counted one by one):
        (None, 0). 1.1 bags is Full, 2.7 bags is ¾ and 2 more."""
        total = self.stock_in(place_id, food.id)
        size = self.usual(food.id)
        if self.counting(food) is not None or size is None or size.amount_milli <= 0:
            return None, 0
        if total <= 0:
            return Decimal(0), 0
        whole, rest = divmod(total, size.amount_milli)
        quarters = round(rest * 4 / size.amount_milli)
        if quarters == 4:
            whole, quarters = whole + 1, 0
        if quarters == 0:
            return (Decimal(1), whole - 1) if whole > 0 else (Decimal(0), 0)
        return QUARTERS[quarters], whole

    def answer_of(self, food: Food, place_id: int) -> StocktakeAnswerOut | None:
        if self.counting(food) is not None:
            return StocktakeAnswerOut(fraction=None, more=0, count=self.count_now(food, place_id))
        fraction, more = self.reading(food, place_id)
        return StocktakeAnswerOut(fraction=fraction, more=more, count=None)

    def row(self, food: Food, place_id: int) -> StocktakeRow:
        answered = self.is_answered(place_id, food.id)
        usual = self.usual(food.id)
        total = self.stock_in(place_id, food.id)
        on, days_ago = None, None
        if food.staple:
            on, days_ago = restock.day(
                self.kitchen.household,
                restock.restocked(self.db, self.kitchen.household_id, [food]).get(food.id),
            )
        unit = self.counting(food)
        counted = unit is not None
        now = self.reading(food, place_id)
        return StocktakeRow(
            food=FoodBrief(id=food.id, name=food.name, counted_as=food.counted_as),  # type: ignore[arg-type]
            staple=food.staple,
            restocked_on=on,
            restocked_days_ago=days_ago,
            added=food.place_id != place_id and not self.lots.get(place_id, {}).get(food.id),
            answered=answered,
            stock=amount_out(food, total, usual),
            pack=(
                size_out(food, usual) if usual is not None and food.counted_as != "count" else None
            ),
            pack_suggestions=(
                pack_suggestions(self.kitchen, food, [], self.names(food))
                if usual is None and not counted and not food.staple
                else []
            ),
            answer=self.answer_of(food, place_id) if answered and not food.staple else None,
            fraction_now=now[0],
            more_now=now[1],
            counted=counted,
            count_now=self.count_now(food, place_id),
            count_word=unit[1] if unit else None,
            count_word_plural=unit[2] if unit else None,
        )


def _step(view: Stocktake, place: Place) -> StocktakePlaceStep:
    answered, total = view.progress(place.id)
    return StocktakePlaceStep(
        **_ref(place).model_dump(),
        finished=place.id in view.finished,
        answered=answered,
        total=total,
    )


def _current(view: Stocktake) -> int | None:
    return next((p.id for p in view.places if p.id not in view.finished), None)


@router.get("/stocktake")
def stocktake(kitchen: Here) -> StocktakeOut:
    """The places in the Settings order, and where to carry on: the first one not finished.
    Everything is saved as it is tapped, so there is nothing to "resume"."""
    view = Stocktake(kitchen)
    steps = [_step(view, place) for place in view.places]
    return StocktakeOut(
        places=steps,
        current_place_id=_current(view),
        started=bool(view.finished or any(e.answered for e in view.entries.values())),
        complete=bool(view.places) and all(p.finished for p in steps),
    )


@router.get("/stocktake/places/{place_id}")
def stocktake_place(place_id: StoredInt, kitchen: Here) -> PlaceStocktake:
    """One place and every ingredient in it, with the answers so far."""
    place = _place(kitchen, place_id)
    view = Stocktake(kitchen)
    return _place_out(view, place)


def _place_out(view: Stocktake, place: Place) -> PlaceStocktake:
    order = [p.id for p in view.places]
    index = order.index(place.id)
    answered, total = view.progress(place.id)
    return PlaceStocktake(
        place=_ref(place),
        number=index + 1,
        of=len(order),
        finished=place.id in view.finished,
        answered=answered,
        total=total,
        previous=_ref(view.places[index - 1]) if index > 0 else None,
        next=_ref(view.places[index + 1]) if index + 1 < len(order) else None,
        rows=[view.row(food, place.id) for food in view.members(place.id)],
    )


# --- Writing --------------------------------------------------------------------------------


def _entry(kitchen: Kitchen, place_id: int, food_id: int) -> StocktakeEntry:
    """The ingredient's row in this place, made if it isn't there. Two phones making it at
    once end with one."""
    query = select(StocktakeEntry).where(
        StocktakeEntry.place_id == place_id, StocktakeEntry.food_id == food_id
    )
    found = kitchen.db.scalar(query)
    if found is not None:
        return found
    try:
        with kitchen.db.begin_nested():
            found = StocktakeEntry(
                household_id=kitchen.household_id, place_id=place_id, food_id=food_id
            )
            kitchen.db.add(found)
    except IntegrityError:  # pragma: no cover (two phones at the same moment)
        found = None
    return found or kitchen.db.scalars(query).one()


def _written(kitchen: Kitchen, change: Change | None, place: Place, food: Food) -> StocktakeWrite:
    view = Stocktake(kitchen)
    answered, total = view.progress(place.id)
    return StocktakeWrite(
        change=change_out(kitchen, change) if change is not None else None,
        row=view.row(food, place.id),
        answered=answered,
        total=total,
    )


def _write(
    kitchen: Kitchen,
    response: Response,
    place: Place,
    food: Food,
    apply: Callable[[], Change | None],
) -> StocktakeWrite:
    """Apply once: a retry with the same Idempotency-Key gets the original change and the row
    as it is now."""
    earlier = replayed(kitchen)
    if earlier is None:
        change = apply()
        note_pantry(kitchen.db, kitchen.household_id)  # other phones' counts
        earlier = commit(kitchen)
        if earlier is None:
            return _written(kitchen, change, place, food)
    response.status_code = status.HTTP_200_OK
    response.headers["Idempotent-Replayed"] = "true"
    return _written(kitchen, earlier, place, food)


def _fractions(value: Decimal | None) -> Decimal | None:
    if value is not None and value not in QUARTERS:
        raise ValueError("Pick None, ¼, ½, ¾ or Full.")
    return value


class StocktakeAnswer(BaseModel):
    """None · ¼ · ½ · ¾ · Full (`fraction` 0, 0.25, 0.5, 0.75, 1 of the open packet, `more`
    whole packets besides it), or `count` for an ingredient counted one by one."""

    fraction: (
        Annotated[Decimal, Field(ge=0, le=1, max_digits=6, decimal_places=4), ShortAmount] | None
    ) = None
    more: Annotated[int, Field(ge=0, le=MORE_MOST)] = 0
    count: (
        Annotated[Decimal, Field(ge=0, le=100_000, max_digits=9, decimal_places=3), ShortAmount]
        | None
    ) = None

    _quarters = field_validator("fraction")(_fractions)

    @model_validator(mode="after")
    def _one(self) -> StocktakeAnswer:
        if (self.fraction is None) == (self.count is None):
            raise ValueError("Give either a fraction or a count.")
        if self.count is not None and self.more:
            raise ValueError("A count has no more packets.")
        return self


def _amount_words(food: Food, milli: int, size: FoodSize | None) -> str:
    """ "½ bag", "6", "400 g": the answer as given, without "about" (it was the person's guess,
    not ours)."""
    return amount_out(food, milli, size).short.removesuffix(f"{NBSP}left")


def _words(food: Food, place: Place, text: str) -> str:
    return f"Stocktake: {food.name} {text} in the {place.name}"


@router.post("/stocktake/places/{place_id}/foods/{food_id}/answer")
def answer(
    place_id: StoredInt,
    food_id: StoredInt,
    body: StocktakeAnswer,
    kitchen: Here,
    response: Response,
) -> StocktakeWrite:
    """How much there is in this place: sets what is there to the answer (taking from the
    packets that go off first, or topping up the newest), as one change with Undo."""
    place = _place(kitchen, place_id)
    food = find(kitchen, food_id)

    def apply() -> Change | None:
        if food.staple:
            raise Problem(
                status.HTTP_409_CONFLICT, "staple", f"{food.name} is a staple, so it isn’t counted."
            )
        size = _usual(kitchen, food.id)
        unit = _counting(food, size)
        if body.count is not None:
            if unit is None:
                raise Problem(422, "not_counted", f"{food.name} isn’t counted one by one.")
            # Tins are whole ones; an ingredient counted as a count keeps its fractions.
            count = (
                body.count
                if food.counted_as == "count"
                else body.count.quantize(Decimal(1), ROUND_HALF_UP)
            )
            target = round(count * unit[0])
        else:
            if unit is not None:
                raise Problem(422, "counted", f"{food.name} is counted one by one: give a count.")
            fraction = body.fraction or Decimal(0)
            if size is None and (fraction > 0 or body.more):
                raise Problem(
                    422,
                    "needs_size",
                    f"{food.name} has no pack size yet: pick one first.",
                )
            target = round((fraction + body.more) * size.amount_milli) if size else 0
        entry = _entry(kitchen, place.id, food.id)
        lots = lots_of(kitchen, [food.id], place.id)
        total = sum(lot.amount_milli for lot in lots)
        change: Change | None = None
        if target != total:
            edit = StockEdit(kitchen)
            if target < total:
                take(kitchen, edit, lots, total - target, include_freezer=True)
            else:
                _top_up(kitchen, edit, food, place, lots, target - total, size)
            if target == 0:
                text = "none"
                summary = f"Stocktake: no {food.name} in the {place.name}"
            else:
                text = _amount_words(food, target, size)
                summary = _words(food, place, text)
            change = edit.record("stocktake", summary, food.id)
        _mark_answered(kitchen, entry, change)
        return change

    return _write(kitchen, response, place, food, apply)


def _mark_answered(kitchen: Kitchen, entry: StocktakeEntry, change: Change | None) -> None:
    """The row is answered. An answer that changed nothing keeps the change of the answer that
    stands, so an Undo of that one still makes the row unanswered again."""
    if change is None and entry.answered and entry.change_id is not None:
        undone = kitchen.db.scalar(
            select(Change.undone_by_change_id).where(Change.id == entry.change_id)
        )
        if undone is None:
            entry.at = utcnow()
            return
    entry.answered = True
    entry.change_id = change.id if change is not None else None
    entry.at = utcnow()


def _usual(kitchen: Kitchen, food_id: int) -> FoodSize | None:
    found = list(
        kitchen.db.scalars(
            select(FoodSize)
            .where(FoodSize.food_id == food_id)
            .order_by(FoodSize.position, FoodSize.id)
        )
    )
    return next((s for s in found if s.usual), found[0] if found else None)


def _top_up(
    kitchen: Kitchen,
    edit: StockEdit,
    food: Food,
    place: Place,
    lots: list[StockLot],
    more: int,
    size: FoodSize | None,
) -> None:
    """Put `more` into the place: fill a part-used packet up to its size first (the one that
    goes off first, so no undated part-packet is made beside it; else the newest), then new
    packets (each its own, as bought). An ingredient with no packet gets one lot."""
    if size is None or food.counted_as == "count":
        if lots:
            newest = max(lots, key=lambda lot: (lot.added_at, lot.id))
            edit.touch(newest).amount_milli += more
        else:
            put_in(kitchen, edit, food, place, [more], None)
        return
    if lots:
        part = [lot for lot in lots if lot.amount_milli < size.amount_milli]
        if part:
            target = min(part, key=lambda lot: (lot.use_by is None, lot.use_by, lot.id))
        else:
            target = max(lots, key=lambda lot: (lot.added_at, lot.id))
        room = max(size.amount_milli - target.amount_milli, 0)
        fill = min(room, more)
        if fill > 0:
            edit.touch(target).amount_milli += fill
            more -= fill
    if more > 0:
        # The answer is stored as given: a very large one goes in as one lot (as an
        # ordinary add does), never cut short (RF3, S2).
        put_in(kitchen, edit, food, place, lot_amounts(more, size), size)


@router.post("/stocktake/places/{place_id}/foods/{food_id}/staple")
def make_staple(
    place_id: StoredInt, food_id: StoredInt, kitchen: Here, response: Response
) -> StocktakeWrite:
    """ "It's a staple": always assumed in stock, not counted. Recorded as a stocktake change
    with Undo."""
    place = _place(kitchen, place_id)
    food = find(kitchen, food_id)

    def apply() -> Change | None:
        if food.staple:
            raise Problem(
                status.HTTP_409_CONFLICT, "already_staple", f"{food.name} is a staple already."
            )
        entry = _entry(kitchen, place.id, food.id)
        with FoodEdit(kitchen, [food.id]) as edit:
            food.staple = True
        change = edit.record(
            "stocktake", f"Stocktake: {food.name} is a staple in the {place.name}", food.id
        )
        entry.answered = True
        entry.change_id = change.id
        entry.at = utcnow()
        return change

    return _write(kitchen, response, place, food, apply)


@router.post("/stocktake/places/{place_id}/foods/{food_id}/size")
def set_pack_size(
    place_id: StoredInt, food_id: StoredInt, body: NewSize, kitchen: Here, response: Response
) -> StocktakeWrite:
    """Asked once: what the ingredient comes in. It becomes the Usual size (a pack size the
    ingredient has already is left alone: 409). One change with Undo."""
    place = _place(kitchen, place_id)
    food = find(kitchen, food_id)

    def apply() -> Change | None:
        if food.staple or food.counted_as == "count":
            raise Problem(422, "no_pack", f"{food.name} isn’t counted by the pack.")
        if _usual(kitchen, food.id) is not None:
            raise Problem(
                status.HTTP_409_CONFLICT,
                "has_size",
                f"{food.name} has a pack size already.",
            )
        milli = _size_amount(kitchen, food, body.amount)
        if milli <= 0:
            raise Problem(422, "too_small", "That size is too small.")
        _entry(kitchen, place.id, food.id)
        with FoodEdit(kitchen, [food.id]) as edit:
            size = add_size(kitchen, food, body.name, milli)
            size.usual = True
        return edit.record(
            "stocktake",
            f"Stocktake: {food.name} {size.name} is "
            f"{exact_text(size.amount_milli, food.counted_as)}",  # type: ignore[arg-type]
            food.id,
        )

    return _write(kitchen, response, place, food, apply)


class StocktakeNewFood(BaseModel):
    food_id: StoredInt


@router.post("/stocktake/places/{place_id}/foods", status_code=status.HTTP_201_CREATED)
def add_something_else(
    place_id: StoredInt, body: StocktakeNewFood, kitchen: Here, response: Response
) -> StocktakeWrite:
    """ "+ Something else in the Cupboard": an ingredient to count in this place too (it is
    made first with POST /foods, or picked from the ingredients). No stock change; sending it
    again changes nothing."""
    place = _place(kitchen, place_id)
    food = find(kitchen, body.food_id)
    _entry(kitchen, place.id, food.id)
    note_pantry(kitchen.db, kitchen.household_id)
    kitchen.db.commit()
    view = Stocktake(kitchen)
    answered, total = view.progress(place.id)
    return StocktakeWrite(change=None, row=view.row(food, place.id), answered=answered, total=total)


@router.post("/stocktake/places/{place_id}/finish")
def finish_place(place_id: StoredInt, kitchen: Here) -> StocktakeOut:
    """ "Next: Spice rack →" (or Finish): this place is finished, and every ingredient in it not
    answered yet counts as checked and correct (stock untouched). The stocktake reopens at the
    first place not finished. Sending it again changes nothing."""
    place = _place(kitchen, place_id)
    _check_the_rest(kitchen, place)
    if kitchen.db.get(StocktakePlace, (kitchen.household_id, place.id)) is None:
        try:
            with kitchen.db.begin_nested():
                kitchen.db.add(StocktakePlace(household_id=kitchen.household_id, place_id=place.id))
        except IntegrityError:  # pragma: no cover (two phones at the same moment)
            pass
    note_pantry(kitchen.db, kitchen.household_id)
    kitchen.db.commit()
    return stocktake(kitchen)


def _check_the_rest(kitchen: Kitchen, place: Place) -> None:
    """Next means right (cabledrawer 7 Nov): every ingredient not answered yet is recorded as
    checked
    and correct. No stock change and no change in Recent changes; the row counts as done."""
    view = Stocktake(kitchen)
    for food in view.members(place.id):
        if food.staple or view.is_answered(place.id, food.id):
            continue
        entry = _entry(kitchen, place.id, food.id)
        entry.answered = True
        entry.change_id = None  # nothing was changed, so there is nothing to undo
        entry.at = utcnow()


@router.post("/stocktake/restart")
def restart(kitchen: Here) -> StocktakeOut:
    """Start a new stocktake: forgets the progress (the stock counted stays as it is)."""
    kitchen.db.execute(
        delete(StocktakeEntry).where(StocktakeEntry.household_id == kitchen.household_id)
    )
    kitchen.db.execute(
        delete(StocktakePlace).where(StocktakePlace.household_id == kitchen.household_id)
    )
    mark_earlier_stocktake(kitchen.db, kitchen.household_id)
    note_pantry(kitchen.db, kitchen.household_id)
    kitchen.db.commit()
    return stocktake(kitchen)
