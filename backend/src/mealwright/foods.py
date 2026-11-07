"""Foods: finding them, converting their amounts, and describing them for the web app."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal, cast

from fastapi import status
from sqlalchemy import select

from mealwright import amounts
from mealwright.aisles import DEFAULT_AISLE
from mealwright.amounts import (
    MILLI,
    CountedAs,
    Size,
    as_sold,
    checked,
    exact_text,
    from_milli,
    to_milli,
)
from mealwright.api.v1.context import Kitchen
from mealwright.api.v1.schemas import (
    AmountIn,
    AmountOut,
    Answer,
    Ask,
    AsSoldOut,
    ChangeOut,
    PackLineOut,
    PackSuggestion,
    SizeBrief,
    SizeOut,
    Undone,
    Who,
)
from mealwright.buying import pack_line
from mealwright.conversions import (
    AskOnce,
    ConversionKind,
    Known,
    TableRow,
    UnitAmount,
    suggestion,
    table,
    to_base_milli,
)
from mealwright.errors import Problem, not_found
from mealwright.history import FoodEdit, can_undo, undo_until
from mealwright.household import cup_ml
from mealwright.models import (
    Change,
    Food,
    FoodConversion,
    FoodName,
    FoodSize,
    FoodStandIn,
    utcnow,
)
from mealwright.names import fold
from mealwright.pack_sizes import suggest_sizes

# Words people type for units, beyond the units' own names.
UNIT_WORDS = {
    "g": "g",
    "gram": "g",
    "grams": "g",
    "gm": "g",
    "gms": "g",
    "kg": "kg",
    "kilo": "kg",
    "kilos": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "mg": "mg",
    "oz": "oz",
    "ounce": "oz",
    "ounces": "oz",
    "lb": "lb",
    "lbs": "lb",
    "pound": "lb",
    "pounds": "lb",
    "ml": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "l": "l",
    "litre": "l",
    "litres": "l",
    "liter": "l",
    "liters": "l",
    "tsp": "tsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "tbsp": "tbsp",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "cup": "cup",
    "cups": "cup",
    "count": "count",
}

BASE_UNITS: dict[str, Literal["g", "ml", "count"]] = {
    "weight": "g",
    "volume": "ml",
    "count": "count",
}

# "About how many slices in a loaf? Suggested: 20" (spec section 6, "Stock").
SIZE_SUGGESTIONS = {"loaf": Decimal(20)}


# --- Finding ------------------------------------------------------------------------------


def visible(food: Food) -> bool:
    return food.removed_at is None and food.merged_into_id is None


def find(kitchen: Kitchen, food_id: int, follow_merges: bool = True) -> Food:
    """A food in this household. A merged-away id gives the food it went into."""
    food = kitchen.db.get(Food, food_id)
    seen = set()
    while (
        follow_merges
        and food is not None
        and food.merged_into_id is not None
        and food.id not in seen
    ):
        seen.add(food.id)
        food = kitchen.db.get(Food, food.merged_into_id)
    if food is None or food.household_id != kitchen.household_id or not visible(food):
        raise not_found("That ingredient")
    return food


def all_foods(kitchen: Kitchen) -> list[Food]:
    return list(
        kitchen.db.scalars(
            select(Food).where(
                Food.household_id == kitchen.household_id,
                Food.removed_at.is_(None),
                Food.merged_into_id.is_(None),
            )
        )
    )


def other_names(kitchen: Kitchen, food_id: int) -> list[FoodName]:
    return list(
        kitchen.db.scalars(
            select(FoodName).where(FoodName.food_id == food_id).order_by(FoodName.id)
        )
    )


def sizes(kitchen: Kitchen, food_id: int) -> list[FoodSize]:
    return list(
        kitchen.db.scalars(
            select(FoodSize)
            .where(FoodSize.food_id == food_id)
            .order_by(FoodSize.position, FoodSize.id)
        )
    )


def usual_size(kitchen: Kitchen, food_id: int) -> FoodSize | None:
    found = sizes(kitchen, food_id)
    return next((size for size in found if size.usual), found[0] if found else None)


def pack_bought(kitchen: Kitchen, food_id: int) -> FoodSize | None:
    """The size a list amount is bought in (F122): the ingredient's Usual size, else its only
    size. With several sizes and none Usual there is no way to know, so none."""
    found = sizes(kitchen, food_id)
    usual = next((size for size in found if size.usual), None)
    if usual is not None:
        return usual
    return found[0] if len(found) == 1 else None


def name_owner(kitchen: Kitchen, name: str, except_id: int | None = None) -> Food | None:
    """Another visible food already called this (ignoring case and accents)."""
    folded = fold(name)
    for food in all_foods(kitchen):
        if food.id != except_id and fold(food.name) == folded:
            return food
    return None


def name_taken(name: str, food: Food) -> Problem:
    return Problem(
        status.HTTP_409_CONFLICT,
        "name_taken",
        f"There’s already an ingredient called {food.name}.",
        food_id=food.id,
    )


def make_food(
    kitchen: Kitchen,
    name: str,
    *,
    counted_as: str | None = None,
    staple: bool = False,
    place_id: int | None = None,
    shop_id: int | None = None,
    aisle: str | None = None,
) -> Change:
    """Add an ingredient and record it in Recent changes (with Undo). How it's counted
    defaults from the bundled table, else by weight. The caller has checked the place and
    shop. A name another ingredient already has is a 409 `name_taken`."""
    owner = name_owner(kitchen, name)
    if owner is not None:
        raise name_taken(name, owner)
    row = table().match(name)
    with FoodEdit(kitchen, []) as edit:
        food = Food(
            household_id=kitchen.household_id,
            name=name,
            counted_as=counted_as or (row.counted_as if row else "weight"),
            staple=staple,
            place_id=place_id,
            shop_id=shop_id,
            aisle=aisle or (row.aisle if row and row.aisle else DEFAULT_AISLE),
            table_key=row.key if row else None,
        )
        kitchen.db.add(food)
        kitchen.db.flush()
        edit.also(food.id)
    return edit.record("food_created", f"Added {food.name}", food.id)


def refresh_table_key(kitchen: Kitchen, food: Food) -> None:
    """Match the food to the bundled conversion table by its name or other names."""
    row = table().match(food.name, *(n.name for n in other_names(kitchen, food.id)))
    food.table_key = row.key if row else None


def table_row(food: Food) -> TableRow | None:
    return table().rows.get(food.table_key) if food.table_key else None


# --- Conversions ----------------------------------------------------------------------------


def household_conversions(kitchen: Kitchen, food_id: int) -> dict[str, FoodConversion]:
    return {
        row.kind: row
        for row in kitchen.db.scalars(
            select(FoodConversion).where(FoodConversion.food_id == food_id)
        )
    }


def known_from(food: Food, mine: dict[str, FoodConversion]) -> Known:
    """The household's answers for this food (already loaded), else the bundled table."""
    row = table_row(food)
    mg_per_ml = mine["weight_per_ml"].value_milli if "weight_per_ml" in mine else None
    item_mg = mine["item_weight"].value_milli if "item_weight" in mine else None
    if mg_per_ml is None and row:
        mg_per_ml = row.mg_per_ml
    if item_mg is None and row:
        item_mg = row.item_weight_mg
    return Known(mg_per_ml, item_mg)


def known(kitchen: Kitchen, food: Food, answers: list[Answer] | None = None) -> Known:
    """What's known about converting this food: answers given with this request, then the
    household's own, then the bundled table."""
    base = known_from(food, household_conversions(kitchen, food.id))
    mg_per_ml, item_mg = base.mg_per_ml, base.item_mg
    for answer in answers or []:
        if answer.food_id != food.id or answer.grams is None:
            continue
        if answer.kind == "weight_per_ml":
            mg_per_ml = grams_per_cup_to_mg_per_ml(answer.grams, cup_ml(kitchen.household))
        elif answer.kind == "item_weight":
            item_mg = to_milli(answer.grams)
    return Known(mg_per_ml, item_mg)


def grams_per_cup_to_mg_per_ml(grams: Decimal, cup: int) -> int:
    return max(1, round(grams * MILLI / cup))


def set_conversion(kitchen: Kitchen, food: Food, kind: str, value_milli: int | None) -> None:
    """Save (or with None, forget) the household's own answer."""
    row = household_conversions(kitchen, food.id).get(kind)
    if value_milli is None:
        if row is not None:
            kitchen.db.delete(row)
        return
    name = kitchen.login.name  # read first: it may load the login, which flushes
    if row is None:
        row = FoodConversion(household_id=kitchen.household_id, food_id=food.id, kind=kind)
        kitchen.db.add(row)
    row.value_milli = value_milli
    row.answered_by_name = name
    row.answered_at = utcnow()


def remember_answers(kitchen: Kitchen, answers: list[Answer]) -> None:
    """Save the answers marked "Remember for next time" (sizes are always kept)."""
    for answer in answers:
        food = find(kitchen, answer.food_id)
        if answer.kind == "size":
            if answer.name is None or answer.amount is None:  # pragma: no cover (validated)
                continue
            if find_size(kitchen, food, answer.name) is None:
                add_size(kitchen, food, answer.name, checked(to_milli(answer.amount)))
        elif answer.remember and answer.grams is not None:
            if answer.kind == "weight_per_ml":
                value = grams_per_cup_to_mg_per_ml(answer.grams, cup_ml(kitchen.household))
            else:
                value = to_milli(answer.grams)
            set_conversion(kitchen, food, answer.kind, value)


def find_size(kitchen: Kitchen, food: Food, word: str) -> FoodSize | None:
    folded = fold(word)
    for size in sizes(kitchen, food.id):
        if folded in (fold(size.name), fold(size.plural)):
            return size
    return None


def add_size(
    kitchen: Kitchen, food: Food, name: str, amount_milli: int, when_shopping: bool = False
) -> FoodSize:
    existing = sizes(kitchen, food.id)
    size = FoodSize(
        household_id=kitchen.household_id,
        food_id=food.id,
        name=name,
        plural=amounts.plural(name),
        amount_milli=amount_milli,
        usual=not existing,
        added_when_shopping=when_shopping,
        position=max((s.position for s in existing), default=-1) + 1,
    )
    kitchen.db.add(size)
    kitchen.db.flush()
    return size


def _float(value: Decimal | None) -> float | None:
    return float(value) if value is not None else None


def ask(kitchen: Kitchen, food: Food, kind: ConversionKind | str, size_name: str = "") -> Problem:
    """The 409 that asks once (docs/dev/api-0.2.md section 4.4)."""
    cup = cup_ml(kitchen.household)
    name = food.name  # always exactly as the household typed it
    row = table_row(food) or table().close(food.name)
    if kind == "weight_per_ml":
        question = f"About how much does 1{amounts.NBSP}cup of {name} weigh?"
        payload = Ask(
            food_id=food.id,
            food_name=food.name,
            kind="weight_per_ml",
            question=question,
            unit="g",
            per="cup",
            cup_ml=cup,
            suggested=_float(suggestion("weight_per_ml", row, cup)),
        )
    elif kind == "item_weight":
        question = (
            f"About how much does 1{amounts.NBSP}{food.count_word} of {name} weigh?"
            if food.count_word
            else f"{name}: about how much does one weigh?"
        )
        payload = Ask(
            food_id=food.id,
            food_name=food.name,
            kind="item_weight",
            question=question,
            unit="g",
            per="item",
            cup_ml=cup,
            suggested=_float(suggestion("item_weight", row, cup)),
        )
    else:
        if food.counted_as == "count":
            things = food.count_word_plural or (
                amounts.plural(food.count_word) if food.count_word else ""
            )
            what = f"{things} " if things else ""
            one = f"{amounts.article(size_name)} {size_name}"
            question = f"About how many {what}in {one} of {name}?"
            unit = things or "count"
        else:
            question = f"About how much is in {amounts.article(size_name)} {size_name} of {name}?"
            unit = amounts.BASE_UNIT[food.counted_as]
        suggested = SIZE_SUGGESTIONS.get(fold(size_name))
        payload = Ask(
            food_id=food.id,
            food_name=food.name,
            kind="size",
            question=question,
            unit=unit,
            per=size_name,
            cup_ml=cup,
            suggested=float(suggested) if suggested is not None else None,
            name=size_name,
        )
    return Problem(status.HTTP_409_CONFLICT, "ask_once", payload.question, ask=payload.model_dump())


@dataclass
class Resolved:
    milli: int
    size: FoodSize | None = None
    answers: list[Answer] = field(default_factory=list)


def resolve(kitchen: Kitchen, food: Food, value: AmountIn) -> Resolved:
    """An AmountIn in the food's base unit (thousandths). Answers that come with it are
    used, and the ones to remember are saved. Raises the "ask once" 409 when needed."""
    answers = value.answers
    for answer in answers:
        find(kitchen, answer.food_id)  # 404 for a food from elsewhere
    if value.size_id is not None:
        size = kitchen.db.get(FoodSize, value.size_id)
        if size is None or size.food_id != food.id:
            raise not_found("That size")
        remember_answers(kitchen, answers)
        return Resolved(checked(to_milli(value.amount * size.amount_milli / MILLI)), size, answers)

    word = (value.unit or "").strip()
    unit = UNIT_WORDS.get(word.lower())
    if unit is None:
        size = find_size(kitchen, food, word)
        if size is None:
            size_answer = next(
                (
                    a
                    for a in answers
                    if a.kind == "size"
                    and a.food_id == food.id
                    and fold(a.name or "") == fold(word)
                ),
                None,
            )
            if size_answer is None:
                raise ask(kitchen, food, "size", word)
            remember_answers(kitchen, answers)
            size = find_size(kitchen, food, word)
            if size is None:  # pragma: no cover (just added)
                raise ask(kitchen, food, "size", word)
        else:
            remember_answers(kitchen, answers)
        return Resolved(checked(to_milli(value.amount * size.amount_milli / MILLI)), size, answers)

    try:
        milli = to_base_milli(
            UnitAmount(value.amount, unit),
            cast(CountedAs, food.counted_as),
            known(kitchen, food, answers),
            cup_ml(kitchen.household),
        )
    except AskOnce as needed:
        raise ask(kitchen, food, needed.kind) from None
    remember_answers(kitchen, answers)
    return Resolved(milli, None, answers)


# --- Describing ---------------------------------------------------------------------------------


def size_value(size: FoodSize | None) -> Size | None:
    if size is None:
        return None
    return Size(size.id, size.name, size.plural, size.amount_milli)


def amount_out(food: Food, milli: int, size: FoodSize | Size | None) -> AmountOut:
    shown = size_value(size) if isinstance(size, FoodSize) else size
    result = as_sold(
        milli,
        cast(CountedAs, food.counted_as),
        shown,
        food.count_word,
        food.count_word_plural,
    )
    sold = None
    if result.size is not None and result.count is not None:
        sold = AsSoldOut(
            count=float(result.count),
            size=SizeBrief(
                id=result.size.id,
                name=result.size.name,
                plural=result.size.plural,
                amount=from_milli(result.size.amount_milli),
            ),
        )
    return AmountOut(
        amount=from_milli(milli),
        unit=BASE_UNITS[food.counted_as],
        as_sold=sold,
        about=result.about,
        short=result.short,
        display=result.display,
    )


def size_text(food: Food, size: FoodSize) -> str:
    """ "Packet = 500 g", "Loaf = 20 slices", "Dozen = 12"."""
    if food.counted_as == "count":
        count = amounts.count_text(size.amount_milli, food.count_word, food.count_word_plural)
        count = count.removesuffix(f"{amounts.NBSP}left")
    else:
        count = exact_text(size.amount_milli, cast(CountedAs, food.counted_as))
    return f"{size.name[:1].upper()}{size.name[1:]} = {count}"


def pack_suggestions(
    kitchen: Kitchen, food: Food, have: list[FoodSize], names: list[str] | None = None
) -> list[PackSuggestion]:
    """Common sizes for the food from the bundled table (its name, then other names; no match
    gives the generic sizes by kind), without any size it already has (F120, F121). A staple
    isn't bought by a pack, so it has none."""
    if food.staple:
        return []
    found = names if names is not None else [n.name for n in other_names(kitchen, food.id)]
    counted = cast(CountedAs, food.counted_as)
    taken = {size.amount_milli for size in have}
    out: list[PackSuggestion] = []
    for pick in suggest_sizes([food.name, *found], counted, food.table_key):
        if pick.amount_milli in taken:
            continue
        word = pick.pack or "pack"
        amount = (
            f"{Decimal(pick.amount_milli) / MILLI:f}".rstrip("0").rstrip(".")
            if counted == "count"
            else exact_text(pick.amount_milli, counted)
        )
        out.append(
            PackSuggestion(
                pack=pick.pack,
                name=word,
                amount=from_milli(pick.amount_milli),
                display=f"{word} · {amount}",
                amount_text=amount,
            )
        )
    return out


def pack_line_out(kitchen: Kitchen, food: Food, need_milli: int | None) -> PackLineOut | None:
    """The whole-packs wording for a list line (F120), with the common sizes to pick from when
    no size is known. Used by Shopping and by the phone's sync pull."""
    usual = pack_bought(kitchen, food.id)  # F122: Usual, else the only size
    line = pack_line(food, need_milli, usual)
    if line is None:
        return None
    return PackLineOut(
        packs=line.packs,
        size_id=line.size_id,
        buy=line.buy,
        need=line.need,
        line=line.line,
        suggestions=pack_suggestions(kitchen, food, []) if usual is None else [],
    )


def size_out(food: Food, size: FoodSize) -> SizeOut:
    return SizeOut(
        id=size.id,
        name=size.name,
        plural=size.plural,
        amount=from_milli(size.amount_milli),
        display=size_text(food, size),
        usual=size.usual,
        added_when_shopping=size.added_when_shopping,
    )


def counted_as_text(food: Food, usual: FoodSize | None) -> str:
    """The "Counted as" column: "Staple", "Packets · 500 g", "Slices", "Count"."""
    if food.staple:
        return "Staple"
    if food.counted_as == "count":
        if food.count_word:
            words = food.count_word_plural or amounts.plural(food.count_word)
            return words[:1].upper() + words[1:]
        return "Count"
    if usual is not None:
        plural = usual.plural[:1].upper() + usual.plural[1:]
        return f"{plural} · {exact_text(usual.amount_milli, cast(CountedAs, food.counted_as))}"
    return food.counted_as.capitalize()


def change_out(kitchen: Kitchen, change: Change) -> ChangeOut:
    undone = None
    if change.undone_by_change_id is not None:
        undo = kitchen.db.get(Change, change.undone_by_change_id)
        if undo is not None:
            undone = Undone(at=undo.at, who=Who(login_id=undo.login_id, name=undo.login_name))
    return ChangeOut(
        id=change.id,
        kind=change.kind,
        at=change.at,
        who=Who(login_id=change.login_id, name=change.login_name),
        summary=change.summary,
        can_undo=can_undo(kitchen, change),
        undo_until=undo_until(kitchen, change),
        undone=undone,
    )


def stand_in_links(kitchen: Kitchen, food_id: int) -> tuple[list[int], list[int]]:
    """(foods that can stand in for this one, foods this one can stand in for)."""
    links = list(
        kitchen.db.scalars(
            select(FoodStandIn).where(
                (FoodStandIn.food_id == food_id) | (FoodStandIn.stand_in_id == food_id)
            )
        )
    )
    stand_ins = [link.stand_in_id for link in links if link.food_id == food_id]
    stands_in_for = [link.food_id for link in links if link.stand_in_id == food_id]
    return stand_ins, stands_in_for
