"""Foods: the Ingredients screen and the ingredient editor (docs/dev/api-0.2.md 6.2)."""

from collections import defaultdict
from collections.abc import Callable
from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated, Literal, cast

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from mealwright import amounts
from mealwright.amounts import MILLI, CountedAs, exact_text, from_milli
from mealwright.api.v1.context import Here, Kitchen
from mealwright.api.v1.schemas import (
    AmountIn,
    AmountOut,
    Answer,
    ChangeOut,
    CountedAsName,
    CupGrams,
    ItemGrams,
    PositiveNumber,
    Ref,
    SizeOut,
)
from mealwright.auth import SameOrigin
from mealwright.conversions import AskOnce, Known, UnitAmount, convert_milli, table, to_base_milli
from mealwright.errors import Problem, not_found
from mealwright.foods import (
    UNIT_WORDS,
    add_size,
    all_foods,
    amount_out,
    ask,
    change_out,
    counted_as_text,
    find,
    find_size,
    grams_per_cup_to_mg_per_ml,
    household_conversions,
    known,
    name_owner,
    name_taken,
    other_names,
    refresh_table_key,
    remember_answers,
    resolve,
    set_conversion,
    size_out,
    sizes,
    stand_in_links,
    table_row,
    usual_size,
)
from mealwright.history import (
    FoodEdit,
    can_undo,
    commit,
    fix_usual_sizes,
    replayed,
)
from mealwright.household import cup_ml
from mealwright.models import (
    Change,
    Food,
    FoodMerge,
    FoodName,
    FoodNotSame,
    FoodSize,
    FoodStandIn,
    Place,
    Shop,
    utcnow,
)
from mealwright.names import clean, fold, normalise

router = APIRouter(tags=["foods"], dependencies=[SameOrigin])

Name = Annotated[str, Field(min_length=1, max_length=100)]


def _name(value: str) -> str:
    value = clean(value)
    if not value:
        raise ValueError("Please type a name.")
    return value


# --- Shapes ---------------------------------------------------------------------------------


class Conversion(BaseModel):
    grams: float
    source: Literal["you", "table"] = Field(serialization_alias="from")
    cup_ml: int | None = None


class StandIn(BaseModel):
    id: int
    name: str
    both_ways: bool


class LastChange(BaseModel):
    id: int
    summary: str
    can_undo: bool


class FoodOut(BaseModel):
    id: int
    name: str
    other_names: list[Ref]
    counted_as: CountedAsName
    staple: bool
    count_word: str | None
    count_word_plural: str | None
    counted_as_display: str
    place: Ref | None
    shop: Ref | None
    sizes: list[SizeOut]
    cup_weight: Conversion | None
    item_weight: Conversion | None
    running_low_at: AmountOut | None
    stand_ins: list[StandIn]
    stands_in_for: list[StandIn]
    maybe_same: list[Ref]
    stock: AmountOut | None  # filled in once stock arrives (0.2, stock PR)
    last_change: LastChange | None
    merged_from: Ref | None = None


class FoodWrite(BaseModel):
    food: FoodOut | None
    change: ChangeOut | None


class FoodListItem(BaseModel):
    id: int
    name: str
    other_names: list[str]
    matched_name: str | None
    counted_as: CountedAsName
    staple: bool
    counted_as_display: str
    place: Ref | None
    stand_ins: list[Ref]
    maybe_same: list[Ref]


class FoodCounts(BaseModel):
    all: int
    staples: int
    maybe_same: int


class FoodList(BaseModel):
    total: int
    counts: FoodCounts
    foods: list[FoodListItem]
    next: str | None


# --- Maybe the same -------------------------------------------------------------------------


def maybe_same(
    kitchen: Kitchen, foods: list[Food], names: dict[int, list[str]]
) -> dict[int, set[int]]:
    """Foods that may be the same: equal names (ignoring case, plurals and brackets), or a
    name matching another food's other name. Pairs marked "Not the same" are left out."""
    by_name: dict[str, set[int]] = defaultdict(set)
    by_other: dict[str, set[int]] = defaultdict(set)
    for food in foods:
        by_name[normalise(food.name)].add(food.id)
        for other in names.get(food.id, []):
            by_other[normalise(other)].add(food.id)
    pairs: dict[int, set[int]] = defaultdict(set)
    for key, ids in by_name.items():
        for food_id in ids:
            pairs[food_id] |= ids - {food_id}
            for other_id in by_other.get(key, set()) - {food_id}:
                pairs[food_id].add(other_id)
                pairs[other_id].add(food_id)
    dismissed = {
        (row.food_a_id, row.food_b_id)
        for row in kitchen.db.scalars(
            select(FoodNotSame).where(FoodNotSame.household_id == kitchen.household_id)
        )
    }
    result: dict[int, set[int]] = {}
    for food_id, others in pairs.items():
        keep = {o for o in others if (min(food_id, o), max(food_id, o)) not in dismissed}
        if keep:
            result[food_id] = keep
    return result


def _names_by_food(kitchen: Kitchen) -> dict[int, list[str]]:
    names: dict[int, list[str]] = defaultdict(list)
    for row in kitchen.db.scalars(
        select(FoodName).where(FoodName.household_id == kitchen.household_id).order_by(FoodName.id)
    ):
        names[row.food_id].append(row.name)
    return names


# --- Describing -----------------------------------------------------------------------------


def _place_ref(kitchen: Kitchen, place_id: int | None) -> Ref | None:
    place = kitchen.db.get(Place, place_id) if place_id is not None else None
    return Ref(id=place.id, name=place.name) if place is not None else None


def _shop_ref(kitchen: Kitchen, shop_id: int | None) -> Ref | None:
    shop = kitchen.db.get(Shop, shop_id) if shop_id is not None else None
    return Ref(id=shop.id, name=shop.name) if shop is not None else None


def _conversion(kitchen: Kitchen, food: Food) -> tuple[Conversion | None, Conversion | None]:
    """Weight of 1 cup and of one item: the household's own answer, else the table."""
    mine = household_conversions(kitchen, food.id)
    row = table_row(food)
    cup = cup_ml(kitchen.household)

    def pick(kind: str, from_table: int | None, per: int) -> Conversion | None:
        source: Literal["you", "table"]
        if kind in mine:
            mg, source = mine[kind].value_milli, "you"
        elif from_table:
            mg, source = from_table, "table"
        else:
            return None
        grams = (Decimal(mg) * per / MILLI).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
        return Conversion(
            grams=float(grams), source=source, cup_ml=cup if kind == "weight_per_ml" else None
        )

    return (
        pick("weight_per_ml", row.mg_per_ml if row else None, cup),
        pick("item_weight", row.item_weight_mg if row else None, 1),
    )


def food_out(kitchen: Kitchen, food: Food, merged_from: Food | None = None) -> FoodOut:
    db = kitchen.db
    food_sizes = sizes(kitchen, food.id)
    usual = next((s for s in food_sizes if s.usual), None)
    stand_ins, stands_in_for = stand_in_links(kitchen, food.id)
    both = set(stand_ins) & set(stands_in_for)

    def refs(ids: list[int]) -> list[StandIn]:
        foods = [db.get(Food, i) for i in ids]
        return sorted(
            (
                StandIn(id=f.id, name=f.name, both_ways=f.id in both)
                for f in foods
                if f is not None and f.removed_at is None and f.merged_into_id is None
            ),
            key=lambda s: fold(s.name),
        )

    foods = all_foods(kitchen)
    same = maybe_same(kitchen, foods, _names_by_food(kitchen)).get(food.id, set())
    by_id = {f.id: f for f in foods}
    cup_weight, item_weight = _conversion(kitchen, food)
    last = db.scalar(
        select(Change)
        .where(
            Change.household_id == kitchen.household_id,
            Change.food_id == food.id,
            Change.kind != "undo",
            Change.undone_by_change_id.is_(None),
        )
        .order_by(Change.id.desc())
        .limit(1)
    )
    return FoodOut(
        id=food.id,
        name=food.name,
        other_names=[Ref(id=n.id, name=n.name) for n in other_names(kitchen, food.id)],
        counted_as=cast(CountedAsName, food.counted_as),
        staple=food.staple,
        count_word=food.count_word,
        count_word_plural=food.count_word_plural,
        counted_as_display=counted_as_text(food, usual),
        place=_place_ref(kitchen, food.place_id),
        shop=_shop_ref(kitchen, food.shop_id),
        sizes=[size_out(food, s) for s in food_sizes],
        cup_weight=cup_weight,
        item_weight=item_weight,
        running_low_at=(
            amount_out(food, food.running_low_milli, usual)
            if food.running_low_milli is not None
            else None
        ),
        stand_ins=refs(stand_ins),
        stands_in_for=refs(stands_in_for),
        maybe_same=sorted(
            (Ref(id=i, name=by_id[i].name) for i in same if i in by_id), key=lambda r: fold(r.name)
        ),
        stock=None,
        last_change=(
            LastChange(id=last.id, summary=last.summary, can_undo=can_undo(kitchen, last))
            if last is not None and can_undo(kitchen, last)
            else None
        ),
        merged_from=Ref(id=merged_from.id, name=merged_from.name) if merged_from else None,
    )


# --- Writing --------------------------------------------------------------------------------


def _written(kitchen: Kitchen, change: Change | None, food: Food | None = None) -> FoodWrite:
    if food is None and change is not None and change.food_id is not None:
        found = kitchen.db.get(Food, change.food_id)
        food = found if found is not None and found.removed_at is None else None
        if food is not None and food.merged_into_id is not None:
            food = find(kitchen, food.id)
    return FoodWrite(
        food=food_out(kitchen, food) if food is not None else None,
        change=change_out(kitchen, change) if change is not None else None,
    )


def write(kitchen: Kitchen, response: Response, apply: Callable[[], Change | None]) -> FoodWrite:
    """Apply a change once: a retry with the same Idempotency-Key gets the original change
    and the food as it is now (docs/dev/api-0.2.md section 1.2)."""
    earlier = replayed(kitchen)
    if earlier is None:
        change = apply()
        earlier = commit(kitchen)
        if earlier is None:
            return _written(kitchen, change)
    response.status_code = status.HTTP_200_OK
    response.headers["Idempotent-Replayed"] = "true"
    return _written(kitchen, earlier)


def _place(kitchen: Kitchen, place_id: int) -> Place:
    place = kitchen.db.get(Place, place_id)
    if place is None or place.household_id != kitchen.household_id:
        raise not_found("That place")
    return place


def _shop(kitchen: Kitchen, shop_id: int) -> Shop:
    shop = kitchen.db.get(Shop, shop_id)
    if shop is None or shop.household_id != kitchen.household_id:
        raise not_found("That shop")
    return shop


# --- List and search ------------------------------------------------------------------------


@router.get("/foods")
def list_foods(
    kitchen: Here,
    q: Annotated[str, Query(max_length=100)] = "",
    filter: Literal["all", "staples", "maybe_same"] = "all",
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    after: Annotated[str | None, Query(pattern=r"^\d{1,9}$")] = None,
) -> FoodList:
    """Every food, searchable by any of its names. Filters: All · Staples · Maybe the same
    ("Not in any recipe" arrives with recipes in 0.4)."""
    foods = all_foods(kitchen)
    names = _names_by_food(kitchen)
    same = maybe_same(kitchen, foods, names)
    usual: dict[int, FoodSize] = {}
    for size in kitchen.db.scalars(
        select(FoodSize)
        .where(FoodSize.household_id == kitchen.household_id)
        .order_by(FoodSize.position, FoodSize.id)
    ):
        if size.usual or size.food_id not in usual:
            usual[size.food_id] = size
    links: dict[int, list[int]] = defaultdict(list)
    for link in kitchen.db.scalars(
        select(FoodStandIn).where(FoodStandIn.household_id == kitchen.household_id)
    ):
        links[link.food_id].append(link.stand_in_id)
    by_id = {f.id: f for f in foods}
    places = {
        p.id: p
        for p in kitchen.db.scalars(select(Place).where(Place.household_id == kitchen.household_id))
    }
    counts = FoodCounts(all=len(foods), staples=sum(f.staple for f in foods), maybe_same=len(same))

    needle = fold(q.strip())
    scored: list[tuple[int, str, Food, str | None]] = []
    for food in foods:
        if filter == "staples" and not food.staple:
            continue
        if filter == "maybe_same" and food.id not in same:
            continue
        matched: str | None = None
        rank = 2
        if needle:
            folded = fold(food.name)
            if folded.startswith(needle):
                rank = 0
            elif needle in folded:
                rank = 1
            else:
                rank = 3
                for other in names.get(food.id, []):
                    other_folded = fold(other)
                    if needle in other_folded:
                        option = 0 if other_folded.startswith(needle) else 1
                        if option < rank:
                            rank, matched = option, other
                if rank == 3:
                    continue
        scored.append((rank, fold(food.name), food, matched))
    scored.sort(key=lambda item: (item[0], item[1]))

    start = int(after) if after else 0
    page = scored[start : start + limit]
    items = []
    for _rank, _key, food, matched in page:
        place = places.get(food.place_id) if food.place_id else None
        items.append(
            FoodListItem(
                id=food.id,
                name=food.name,
                other_names=names.get(food.id, []),
                matched_name=matched,
                counted_as=cast(CountedAsName, food.counted_as),
                staple=food.staple,
                counted_as_display=counted_as_text(food, usual.get(food.id)),
                place=Ref(id=place.id, name=place.name) if place else None,
                stand_ins=sorted(
                    (Ref(id=i, name=by_id[i].name) for i in links.get(food.id, []) if i in by_id),
                    key=lambda r: fold(r.name),
                ),
                maybe_same=sorted(
                    (Ref(id=i, name=by_id[i].name) for i in same.get(food.id, set()) if i in by_id),
                    key=lambda r: fold(r.name),
                ),
            )
        )
    more = start + limit < len(scored)
    return FoodList(
        total=len(scored), counts=counts, foods=items, next=str(start + limit) if more else None
    )


@router.get("/foods/{food_id}")
def get_food(food_id: int, kitchen: Here) -> FoodOut:
    """The ingredient editor. A merged-away id gives the food it was merged into."""
    asked = kitchen.db.get(Food, food_id)
    food = find(kitchen, food_id)
    merged_from = asked if asked is not None and asked.id != food.id else None
    return food_out(kitchen, food, merged_from)


# --- Create, edit, remove -------------------------------------------------------------------


class NewFood(BaseModel):
    name: Name
    counted_as: CountedAsName | None = None
    staple: bool = False
    place_id: int | None = None
    shop_id: int | None = None

    _clean = field_validator("name")(_name)


@router.post("/foods", status_code=status.HTTP_201_CREATED)
def create_food(body: NewFood, kitchen: Here, response: Response) -> FoodWrite:
    """Add a food. How it's counted defaults from the bundled table, else by weight."""

    def apply() -> Change:
        owner = name_owner(kitchen, body.name)
        if owner is not None:
            raise name_taken(body.name, owner)
        if body.place_id is not None:
            _place(kitchen, body.place_id)
        if body.shop_id is not None:
            _shop(kitchen, body.shop_id)
        row = table().match(body.name)
        with FoodEdit(kitchen, []) as edit:
            food = Food(
                household_id=kitchen.household_id,
                name=body.name,
                counted_as=body.counted_as or (row.counted_as if row else "weight"),
                staple=body.staple,
                place_id=body.place_id,
                shop_id=body.shop_id,
                table_key=row.key if row else None,
            )
            kitchen.db.add(food)
            kitchen.db.flush()
            edit.also(food.id)
        return edit.record("food_created", f"Added {food.name}", food.id)

    return write(kitchen, response, apply)


class FoodPatch(BaseModel):
    """One field per request: the editor saves as you go."""

    name: Name | None = None
    counted_as: CountedAsName | None = None
    staple: bool | None = None
    count_word: Annotated[str, Field(max_length=30)] | None = None
    place_id: int | None = None
    shop_id: int | None = None
    running_low_at: AmountIn | None = None
    cup_weight: CupGrams | None = None  # grams in one household cup
    item_weight: ItemGrams | None = None  # grams in one item
    answers: list[Answer] = Field(default_factory=list, max_length=5)


FIELD_NAMES = (
    "name",
    "counted_as",
    "staple",
    "count_word",
    "place_id",
    "shop_id",
    "running_low_at",
    "cup_weight",
    "item_weight",
)
COUNTED_WORDS = {"weight": "by weight", "volume": "by volume", "count": "by number"}


def _change_counted_as(kitchen: Kitchen, food: Food, target: str, answers: list[Answer]) -> None:
    """Convert the food's sizes and running-low level to the new base unit."""
    source = cast(CountedAs, food.counted_as)
    goal = cast(CountedAs, target)
    knowledge = known(kitchen, food, answers)
    cup = cup_ml(kitchen.household)
    try:
        converted = [
            (size, convert_milli(size.amount_milli, source, goal, knowledge, cup))
            for size in sizes(kitchen, food.id)
        ]
        low = (
            convert_milli(food.running_low_milli, source, goal, knowledge, cup)
            if food.running_low_milli is not None
            else None
        )
    except AskOnce as needed:
        raise ask(kitchen, food, needed.kind) from None
    remember_answers(kitchen, answers)
    for size, milli in converted:
        size.amount_milli = max(milli, 1)
    food.running_low_milli = low
    food.counted_as = target


@router.patch("/foods/{food_id}")
def edit_food(food_id: int, body: FoodPatch, kitchen: Here, response: Response) -> FoodWrite:
    """Change one thing about a food. Each change can be undone."""
    given = [name for name in FIELD_NAMES if name in body.model_fields_set]
    if len(given) != 1:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "one_field",
            "Send one field at a time.",
        )
    field_name = given[0]

    def apply() -> Change | None:
        food = find(kitchen, food_id)
        name = food.name
        with FoodEdit(kitchen, [food.id]) as edit:
            if field_name == "name":
                if body.name is None:
                    raise Problem(422, "name_needed", "Please type a name.")
                new_name = _name(body.name)
                owner = name_owner(kitchen, new_name, except_id=food.id)
                if owner is not None:
                    raise name_taken(new_name, owner)
                if new_name == food.name:
                    return None
                food.name = new_name
                for other in other_names(kitchen, food.id):
                    if fold(other.name) == fold(new_name):
                        kitchen.db.delete(other)
                refresh_table_key(kitchen, food)
                summary = f"Renamed {name} to {new_name}"
            elif field_name == "counted_as":
                if body.counted_as is None:
                    raise Problem(422, "counted_as_needed", "Choose how it's counted.")
                if body.counted_as == food.counted_as:
                    return None
                _change_counted_as(kitchen, food, body.counted_as, body.answers)
                summary = f"{name} is now counted {COUNTED_WORDS[body.counted_as]}"
            elif field_name == "staple":
                if body.staple is None or body.staple == food.staple:
                    return None
                food.staple = body.staple
                summary = f"{name} is {'now' if body.staple else 'no longer'} a staple"
            elif field_name == "count_word":
                word = clean(body.count_word or "") or None
                if word == food.count_word:
                    return None
                food.count_word = word
                food.count_word_plural = amounts.plural(word) if word else None
                summary = (
                    f"{name} is now counted in {food.count_word_plural}"
                    if word
                    else f"{name} is now just counted"
                )
            elif field_name == "place_id":
                if body.place_id == food.place_id:
                    return None
                place = _place(kitchen, body.place_id) if body.place_id is not None else None
                food.place_id = place.id if place else None
                summary = (
                    f"{name} now lives in {place.name}" if place else f"{name} has no usual place"
                )
            elif field_name == "shop_id":
                if body.shop_id == food.shop_id:
                    return None
                shop = _shop(kitchen, body.shop_id) if body.shop_id is not None else None
                food.shop_id = shop.id if shop else None
                summary = (
                    f"Usual shop for {name} is now {shop.name}"
                    if shop
                    else f"{name} has no usual shop"
                )
            elif field_name == "running_low_at":
                if body.running_low_at is None:
                    if food.running_low_milli is None:
                        return None
                    food.running_low_milli = None
                    summary = f"{name} no longer has a running-low level"
                else:
                    milli = resolve(kitchen, food, body.running_low_at).milli
                    if milli == food.running_low_milli:
                        return None
                    food.running_low_milli = milli
                    shown = amount_out(food, milli, usual_size(kitchen, food.id))
                    summary = f"{name} runs low at {shown.short}"
            elif field_name == "cup_weight":
                cup = cup_ml(kitchen.household)
                if body.cup_weight is None:
                    if "weight_per_ml" not in household_conversions(kitchen, food.id):
                        return None
                    set_conversion(kitchen, food, "weight_per_ml", None)
                    summary = f"Forgot your weight of 1 cup of {name}"
                else:
                    set_conversion(
                        kitchen,
                        food,
                        "weight_per_ml",
                        grams_per_cup_to_mg_per_ml(body.cup_weight, cup),
                    )
                    grams = exact_text(amounts.to_milli(body.cup_weight), "weight")
                    summary = f"Weight of 1 cup of {name} is now {grams}"
            else:  # item_weight
                if body.item_weight is None:
                    if "item_weight" not in household_conversions(kitchen, food.id):
                        return None
                    set_conversion(kitchen, food, "item_weight", None)
                    summary = f"Forgot your weight of one {name}"
                else:
                    set_conversion(kitchen, food, "item_weight", amounts.to_milli(body.item_weight))
                    grams = exact_text(amounts.to_milli(body.item_weight), "weight")
                    summary = f"Weight of one {name} is now {grams}"
        return edit.record("food_edited", summary, food.id)

    result = write(kitchen, response, apply)
    if result.food is None:  # nothing changed: still show the food
        result.food = food_out(kitchen, find(kitchen, food_id))
    return result


@router.delete("/foods/{food_id}")
def remove_food(food_id: int, kitchen: Here, response: Response) -> FoodWrite:
    """Remove a food that nothing uses (proposed, see spec section 6). Can be undone."""

    def apply() -> Change:
        food = find(kitchen, food_id)
        with FoodEdit(kitchen, [food.id]) as edit:
            food.removed_at = utcnow()
        return edit.record("food_removed", f"Removed {food.name}", food.id)

    return write(kitchen, response, apply)


# --- Other names ----------------------------------------------------------------------------


class NewName(BaseModel):
    name: Name

    _clean = field_validator("name")(_name)


@router.post("/foods/{food_id}/other-names", status_code=status.HTTP_201_CREATED)
def add_other_name(food_id: int, body: NewName, kitchen: Here, response: Response) -> FoodWrite:
    """Another name for the food. Recipe imports match any of them."""

    def apply() -> Change:
        food = find(kitchen, food_id)
        folded = fold(body.name)
        if folded == fold(food.name) or any(
            fold(n.name) == folded for n in other_names(kitchen, food.id)
        ):
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "name_already_here",
                f"{food.name} already has that name.",
            )
        with FoodEdit(kitchen, [food.id]) as edit:
            kitchen.db.add(
                FoodName(household_id=kitchen.household_id, food_id=food.id, name=body.name)
            )
            kitchen.db.flush()
            refresh_table_key(kitchen, food)
        return edit.record("food_edited", f"Added other name {body.name} to {food.name}", food.id)

    return write(kitchen, response, apply)


@router.delete("/foods/{food_id}/other-names/{name_id}")
def remove_other_name(food_id: int, name_id: int, kitchen: Here, response: Response) -> FoodWrite:
    def apply() -> Change:
        food = find(kitchen, food_id)
        row = kitchen.db.get(FoodName, name_id)
        if row is None or row.food_id != food.id:
            raise not_found("That name")
        with FoodEdit(kitchen, [food.id]) as edit:
            kitchen.db.delete(row)
            kitchen.db.flush()
            refresh_table_key(kitchen, food)
        return edit.record(
            "food_edited", f"Removed other name {row.name} from {food.name}", food.id
        )

    return write(kitchen, response, apply)


# --- Sizes ("How it's sold") ----------------------------------------------------------------


class NewSize(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=40)]
    # In base units (500 for 500 g), or typed with a unit ({"amount": 1, "unit": "kg"}).
    amount: PositiveNumber | AmountIn

    _clean = field_validator("name")(_name)


class SizePatch(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=40)] | None = None
    amount: PositiveNumber | None = None
    usual: Literal[True] | None = None


def _size_amount(kitchen: Kitchen, food: Food, amount: Decimal | AmountIn) -> int:
    if isinstance(amount, AmountIn):
        if amount.size_id is not None or UNIT_WORDS.get((amount.unit or "").lower()) is None:
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "plain_unit",
                "Give the size in g, ml or a count.",
            )
        return resolve(kitchen, food, amount).milli
    return amounts.checked(amounts.to_milli(amount))


@router.post("/foods/{food_id}/sizes", status_code=status.HTTP_201_CREATED)
def add_food_size(food_id: int, body: NewSize, kitchen: Here, response: Response) -> FoodWrite:
    """A way the food is sold (packet = 500 g). The first one becomes Usual."""

    def apply() -> Change:
        food = find(kitchen, food_id)
        milli = _size_amount(kitchen, food, body.amount)
        if milli <= 0:
            raise Problem(422, "too_small", "That size is too small.")
        with FoodEdit(kitchen, [food.id]) as edit:
            size = add_size(kitchen, food, body.name, milli)
        return edit.record(
            "food_edited", f"{food.name}: added {size_out(food, size).display}", food.id
        )

    return write(kitchen, response, apply)


@router.patch("/foods/{food_id}/sizes/{size_id}")
def edit_food_size(
    food_id: int, size_id: int, body: SizePatch, kitchen: Here, response: Response
) -> FoodWrite:
    """Rename a size, change how much it holds, or make it the Usual one."""
    if len(body.model_fields_set) != 1:
        raise Problem(422, "one_field", "Send one field at a time.")

    def apply() -> Change | None:
        food = find(kitchen, food_id)
        size = kitchen.db.get(FoodSize, size_id)
        if size is None or size.food_id != food.id:
            raise not_found("That size")
        with FoodEdit(kitchen, [food.id]) as edit:
            if body.name is not None:
                name = _name(body.name)
                if name == size.name:
                    return None
                old = size.name
                size.name, size.plural = name, amounts.plural(name)
                summary = f"{food.name}: renamed {old} to {name}"
            elif body.amount is not None:
                milli = amounts.checked(amounts.to_milli(body.amount))
                if milli == size.amount_milli:
                    return None
                size.amount_milli = milli
                summary = f"{food.name}: {size_out(food, size).display}"
            else:
                if size.usual:
                    return None
                for other in sizes(kitchen, food.id):
                    other.usual = other.id == size.id
                summary = f"{food.name} is usually bought by the {size.name}"
        return edit.record("food_edited", summary, food.id)

    result = write(kitchen, response, apply)
    if result.food is None:
        result.food = food_out(kitchen, find(kitchen, food_id))
    return result


@router.delete("/foods/{food_id}/sizes/{size_id}")
def remove_food_size(food_id: int, size_id: int, kitchen: Here, response: Response) -> FoodWrite:
    def apply() -> Change:
        food = find(kitchen, food_id)
        size = kitchen.db.get(FoodSize, size_id)
        if size is None or size.food_id != food.id:
            raise not_found("That size")
        with FoodEdit(kitchen, [food.id]) as edit:
            text = size_out(food, size).display
            kitchen.db.delete(size)
            fix_usual_sizes(kitchen, [food.id])
        return edit.record("food_edited", f"{food.name}: removed {text}", food.id)

    return write(kitchen, response, apply)


# --- Can use instead ------------------------------------------------------------------------


class NewStandIn(BaseModel):
    food_id: int
    both_ways: bool = False


@router.post("/foods/{food_id}/stand-ins", status_code=status.HTTP_201_CREATED)
def add_stand_in(food_id: int, body: NewStandIn, kitchen: Here, response: Response) -> FoodWrite:
    """`body.food_id` can be used instead of this food (and the other way too, if asked)."""

    def apply() -> Change | None:
        food = find(kitchen, food_id)
        other = find(kitchen, body.food_id)
        if other.id == food.id:
            raise Problem(422, "same_food", "A food can't stand in for itself.")
        pairs = [(food.id, other.id)] + ([(other.id, food.id)] if body.both_ways else [])
        missing = [p for p in pairs if kitchen.db.get(FoodStandIn, p) is None]
        if not missing:
            return None
        with FoodEdit(kitchen, [food.id, other.id]) as edit:
            for main, stand_in in missing:
                kitchen.db.add(
                    FoodStandIn(
                        household_id=kitchen.household_id, food_id=main, stand_in_id=stand_in
                    )
                )
        both = " (and the other way round)" if body.both_ways else ""
        return edit.record(
            "food_edited", f"{other.name} can be used instead of {food.name}{both}", food.id
        )

    result = write(kitchen, response, apply)
    if result.food is None:
        result.food = food_out(kitchen, find(kitchen, food_id))
    return result


@router.delete("/foods/{food_id}/stand-ins/{stand_in_id}")
def remove_stand_in(food_id: int, stand_in_id: int, kitchen: Here, response: Response) -> FoodWrite:
    def apply() -> Change:
        food = find(kitchen, food_id)
        link = kitchen.db.get(FoodStandIn, (food.id, stand_in_id))
        if link is None:
            raise not_found("That link")
        other = kitchen.db.get(Food, stand_in_id)
        with FoodEdit(kitchen, [food.id, stand_in_id]) as edit:
            kitchen.db.delete(link)
        other_name = other.name if other else "That food"
        return edit.record(
            "food_edited", f"{other_name} is no longer used instead of {food.name}", food.id
        )

    return write(kitchen, response, apply)


# --- Maybe the same -------------------------------------------------------------------------


class NotSame(BaseModel):
    food_id: int


@router.post("/foods/{food_id}/not-the-same", status_code=status.HTTP_204_NO_CONTENT)
def not_the_same(food_id: int, body: NotSame, kitchen: Here) -> None:
    """Never suggest these two as "Maybe the same" again. Quiet: no Undo."""
    food = find(kitchen, food_id)
    other = find(kitchen, body.food_id)
    if food.id == other.id:
        raise Problem(422, "same_food", "That's the same food.")
    pair = (min(food.id, other.id), max(food.id, other.id))
    if kitchen.db.get(FoodNotSame, pair) is None:
        kitchen.db.add(
            FoodNotSame(household_id=kitchen.household_id, food_a_id=pair[0], food_b_id=pair[1])
        )
        kitchen.db.commit()


# --- Merge and split ------------------------------------------------------------------------


class Merge(BaseModel):
    into_id: int
    answers: list[Answer] = Field(default_factory=list, max_length=5)


def merge_foods(kitchen: Kitchen, gone: Food, into: Food, answers: list[Answer]) -> None:
    """Move everything from `gone` into `into` (spec section 6, "Decided for 0.2")."""
    db = kitchen.db
    cup = cup_ml(kitchen.household)
    into_known, gone_known = known(kitchen, into, answers), known(kitchen, gone, answers)
    knowledge = Known(
        into_known.mg_per_ml or gone_known.mg_per_ml, into_known.item_mg or gone_known.item_mg
    )
    source, target = cast(CountedAs, gone.counted_as), cast(CountedAs, into.counted_as)
    try:
        moved_sizes = [
            (size, convert_milli(size.amount_milli, source, target, knowledge, cup))
            for size in sizes(kitchen, gone.id)
        ]
    except AskOnce as needed:
        raise ask(kitchen, into, needed.kind) from None
    remember_answers(kitchen, answers)

    # Names: the merged-away name becomes another name of the food it went into.
    taken = {fold(into.name)} | {fold(n.name) for n in other_names(kitchen, into.id)}
    for row in other_names(kitchen, gone.id):
        if fold(row.name) in taken:
            db.delete(row)
        else:
            row.food_id = into.id
            taken.add(fold(row.name))
    if fold(gone.name) not in taken:
        db.add(FoodName(household_id=kitchen.household_id, food_id=into.id, name=gone.name))

    # Sizes move across (the same size twice becomes one).
    existing = {(fold(s.name), s.amount_milli) for s in sizes(kitchen, into.id)}
    position = max((s.position for s in sizes(kitchen, into.id)), default=-1)
    for size, milli in moved_sizes:
        if (fold(size.name), milli) in existing:
            db.delete(size)
            continue
        position += 1
        size.food_id, size.amount_milli, size.usual, size.position = (
            into.id,
            max(milli, 1),
            False,
            position,
        )
        existing.add((fold(size.name), milli))

    # "Can use instead" links follow the food.
    for link in list(
        db.scalars(
            select(FoodStandIn).where(
                (FoodStandIn.food_id == gone.id) | (FoodStandIn.stand_in_id == gone.id)
            )
        )
    ):
        main = into.id if link.food_id == gone.id else link.food_id
        stand_in = into.id if link.stand_in_id == gone.id else link.stand_in_id
        db.delete(link)
        db.flush()
        if main != stand_in and db.get(FoodStandIn, (main, stand_in)) is None:
            db.add(
                FoodStandIn(household_id=kitchen.household_id, food_id=main, stand_in_id=stand_in)
            )
            db.flush()

    # The household's own answers fill any the other food doesn't have.
    into_answers = household_conversions(kitchen, into.id)
    for kind, answer in household_conversions(kitchen, gone.id).items():
        if kind not in into_answers and gone.counted_as == into.counted_as:
            answer.food_id = into.id

    into.place_id = into.place_id or gone.place_id
    into.shop_id = into.shop_id or gone.shop_id
    gone.merged_into_id = into.id
    db.flush()
    fix_usual_sizes(kitchen, [into.id])
    refresh_table_key(kitchen, into)


@router.post("/foods/{food_id}/merge")
def merge(food_id: int, body: Merge, kitchen: Here, response: Response) -> FoodWrite:
    """Merge this food into another. Undo (within the undo window) restores both."""

    def apply() -> Change:
        gone = find(kitchen, food_id)
        into = find(kitchen, body.into_id)
        if gone.id == into.id:
            raise Problem(422, "same_food", "That's the same food.")
        with FoodEdit(kitchen, [gone.id, into.id]) as edit:
            merge_foods(kitchen, gone, into, body.answers)
            record = FoodMerge(
                household_id=kitchen.household_id, from_food_id=gone.id, into_food_id=into.id
            )
            kitchen.db.add(record)
            kitchen.db.flush()
            edit.extra["merge_id"] = record.id
        change = edit.record("merged", f"Merged {gone.name} into {into.name}", into.id)
        record.change_id = change.id
        return change

    return write(kitchen, response, apply)


class Split(BaseModel):
    other_name_id: int


@router.post("/foods/{food_id}/split", status_code=status.HTTP_201_CREATED)
def split(food_id: int, body: Split, kitchen: Here, response: Response) -> FoodWrite:
    """Turn one of a food's other names back into its own food."""

    def apply() -> Change:
        db = kitchen.db
        food = find(kitchen, food_id)
        row = db.get(FoodName, body.other_name_id)
        if row is None or row.food_id != food.id:
            raise not_found("That name")
        owner = name_owner(kitchen, row.name)
        if owner is not None:
            raise name_taken(row.name, owner)
        earlier = None
        for merge_row in db.scalars(
            select(FoodMerge)
            .where(FoodMerge.into_food_id == food.id, FoodMerge.split_at.is_(None))
            .order_by(FoodMerge.id.desc())
        ):
            old = db.get(Food, merge_row.from_food_id)
            if old is not None and fold(old.name) == fold(row.name):
                earlier = merge_row
                break
        ids = [food.id] + ([earlier.from_food_id] if earlier else [])
        with FoodEdit(kitchen, ids) as edit:
            name = row.name
            db.delete(row)
            db.flush()
            if earlier is not None:
                revived = db.get(Food, earlier.from_food_id)
                if revived is None:  # pragma: no cover (found above)
                    raise not_found("That food")
                new = revived
                new.merged_into_id = None
                new.removed_at = None
                earlier.split_at = utcnow()
                edit.extra["split_merge_id"] = earlier.id
            else:
                new = Food(
                    household_id=kitchen.household_id,
                    name=name,
                    counted_as=food.counted_as,
                    staple=food.staple,
                    count_word=food.count_word,
                    count_word_plural=food.count_word_plural,
                    place_id=food.place_id,
                    shop_id=food.shop_id,
                )
                db.add(new)
                db.flush()
                edit.also(new.id)
            refresh_table_key(kitchen, new)
            refresh_table_key(kitchen, food)
        return edit.record("split", f"Made {name} its own food again", new.id)

    return write(kitchen, response, apply)


# --- Conversion lookup ----------------------------------------------------------------------


class Converted(BaseModel):
    amount: float | None
    unit: str
    source: Literal["you", "table", "fixed"] | None = Field(
        default=None, serialization_alias="from"
    )
    display: str | None = None
    ask: dict[str, object] | None = None


@router.get("/foods/{food_id}/convert", response_model_by_alias=True)
def convert(
    food_id: int,
    kitchen: Here,
    amount: Annotated[Decimal, Query(gt=0, max_digits=15, decimal_places=3)],
    unit: Annotated[str, Query(min_length=1, max_length=40)],
) -> Converted:
    """ "What's 1 cup of toor dal?" in the food's base unit. When nobody knows yet, the
    answer carries the "ask once" question instead (a lookup isn't an error)."""
    food = find(kitchen, food_id)
    base = amounts.BASE_UNIT[food.counted_as]
    code = UNIT_WORDS.get(unit.strip().lower())
    if code is None:
        size = find_size(kitchen, food, unit)
        if size is None:
            problem = ask(kitchen, food, "size", unit.strip())
            return Converted(amount=None, unit=base, ask=problem.extra["ask"])
        milli = amounts.checked(amounts.to_milli(amount * size.amount_milli / MILLI))
        source: Literal["you", "table", "fixed"] = "you"
    else:
        family = amounts.unit_family(code)
        try:
            milli = to_base_milli(
                UnitAmount(amount, code),
                cast(CountedAs, food.counted_as),
                known(kitchen, food),
                cup_ml(kitchen.household),
            )
        except AskOnce as needed:
            problem = ask(kitchen, food, needed.kind)
            return Converted(amount=None, unit=base, ask=problem.extra["ask"])
        if family == food.counted_as:
            source = "fixed"
        else:
            mine = household_conversions(kitchen, food.id)
            needed_kinds = {"weight_per_ml", "item_weight"} & {
                "weight_per_ml" if "volume" in (family, food.counted_as) else "",
                "item_weight" if "count" in (family, food.counted_as) else "",
            }
            source = "you" if needed_kinds and needed_kinds <= mine.keys() else "table"
    shown = amount_out(food, milli, None)
    return Converted(amount=from_milli(milli), unit=base, source=source, display=shown.display)
