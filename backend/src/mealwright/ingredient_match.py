"""Matching a read ingredient line to the household's ingredients, and the first guess for a
new one (spec section 6, "Recipe import, decided for 0.5"; docs/dev/ingredient-reader.md).

Nothing here writes to the database. `kitchen_of` reads the household's ingredients once;
`match_line` is then pure. Learning an other name, and creating an ingredient, happen on
Save (0.5 PR 3).

The labels:

- `matched`: the line names an ingredient by its name or one of its other names, ignoring
  case, accents, plurals and prep words.
- `staple`: matched to a staple. Information only: it never counts.
- `to_confirm`: a close match it isn't sure of ("red onion" for Onions), with the best guess.
- `needs_you`: no match at all, or a line it couldn't read.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from functools import cached_property
from typing import Literal, cast

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from mealwright.amounts import DEFAULT_CUP_ML, MAX_AMOUNT, MILLI, CountedAs, unit_size
from mealwright.household import cup_ml
from mealwright.household import places as household_places
from mealwright.ingredient_reader import (
    COUNTED_AS,
    MODIFIER_WORDS,
    WEAK_WORDS,
    ReadLine,
    working_text,
)
from mealwright.models import Food, FoodName, FoodSize, Household
from mealwright.names import normalise, singular

Label = Literal["matched", "to_confirm", "needs_you", "staple"]

MAX_NAME_CHARS = 100  # a food's name
CUPBOARD = "cupboard"
FRIDGE = "fridge"
FREEZER = "freezer"

# "Kept in" for a new ingredient (cabledrawer 30 Oct): milk, cream, raw meat and the like go in the
# Fridge, not the Cupboard (cabledrawer OK'd 31 Oct). A word here puts the ingredient there; a word in
# `NOT_FRIDGE` ("coconut milk", "chicken stock", "milk powder") takes it back to the Cupboard.
FRIDGE_WORDS = frozenset(
    {"milk", "cream", "butter", "yoghurt", "yogurt", "egg", "cheese", "chicken", "beef", "pork",
     "lamb", "mince", "turkey", "duck", "bacon", "sausage", "ham", "fish", "salmon", "cod",
     "prawn", "steak", "crème", "fraîche", "creme", "fraiche", "buttermilk", "tofu", "paneer"}
)  # fmt: skip
NOT_FRIDGE = frozenset(
    {"coconut", "powder", "stock", "tinned", "canned", "dried", "tartar", "bean", "noodle",
     "sauce", "peanut", "almond", "oat", "soy", "soya", "rice", "cube", "paste", "evaporated",
     "condensed", "ghee", "flavour", "seasoning", "cracker", "biscuit", "crisp", "cashew",
     "bouillon", "corned"}  # "chicken bouillon", "corned beef": Cupboard (cabledrawer 31 Oct)
)  # fmt: skip


# --- The household's ingredients, read once ---------------------------------------------------


@dataclass(frozen=True)
class KitchenSize:
    id: int
    name: str
    plural: str
    amount_milli: int


@dataclass(frozen=True)
class KitchenFood:
    id: int
    name: str
    counted_as: CountedAs
    staple: bool
    other_names: tuple[str, ...]
    sizes: tuple[KitchenSize, ...]


@dataclass(frozen=True)
class KitchenPlace:
    id: int
    name: str


def _key(name: str) -> str:
    """The key two names must share to count as the same: `names.normalise` (lower case, no
    accents, nothing in brackets, plurals made singular), with "-y" and "-i" the same
    ("chilli", "chillies") and "leaves" and "leaf" the same."""
    words = []
    for word in normalise(name).split():
        if word == "leave":
            word = "leaf"
        elif word.endswith("y") and len(word) > 3:
            word = word[:-1] + "i"
        words.append(word)
    return " ".join(words)


@dataclass(frozen=True, eq=False)
class KnownIngredients:
    """A household's ingredients as `match_line` needs them. Make it with `kitchen_of`."""

    household_id: int
    cup_ml: int
    foods: tuple[KitchenFood, ...]
    places: tuple[KitchenPlace, ...] = ()

    @cached_property
    def by_name(self) -> dict[str, KitchenFood]:
        found: dict[str, KitchenFood] = {}
        for food in self.foods:
            found.setdefault(_key(food.name), food)
        return found

    @cached_property
    def by_other_name(self) -> dict[str, KitchenFood]:
        found: dict[str, KitchenFood] = {}
        for food in self.foods:
            for other in food.other_names:
                found.setdefault(_key(other), food)
        return found

    @cached_property
    def name_words(self) -> tuple[tuple[frozenset[str], KitchenFood], ...]:
        """The key words of every name and other name, worked out once (a big household
        would otherwise spend its time re-reading every name for every line)."""
        found = []
        for food in self.foods:
            for name in (food.name, *food.other_names):
                words = _words(_key(name))
                if words:
                    found.append((words, food))
        return tuple(found)

    @cached_property
    def word_index(self) -> dict[str, tuple[int, ...]]:
        """Each key word → which `name_words` entries hold it."""
        index: dict[str, list[int]] = {}
        for position, (words, _food) in enumerate(self.name_words):
            for word in words:
                index.setdefault(word, []).append(position)
        return {word: tuple(positions) for word, positions in index.items()}

    @cached_property
    def size_words(self) -> tuple[str, ...]:
        """Every size name the household uses, for `read_line(text, size_words=...)`."""
        words: dict[str, None] = {}
        for food in self.foods:
            for size in food.sizes:
                words[size.name.lower()] = None
                words[size.plural.lower()] = None
        return tuple(words)

    def usual_place_id(self, name: str) -> int | None:
        """The place a new ingredient called `name` is usually kept: the Fridge for milk, cream,
        raw meat and the like, else the Cupboard (None if the household has no such place)."""
        words = {singular(word) for word in _key(name).split()}
        if {"fish", "finger"} <= words:  # fish fingers: Freezer (cabledrawer 31 Oct)
            for place in self.places:
                if _key(place.name) == FREEZER:
                    return place.id
        if words & FRIDGE_WORDS and not words & NOT_FRIDGE:
            for place in self.places:
                if _key(place.name) == FRIDGE:
                    return place.id
        return self.cupboard_id

    @cached_property
    def cupboard_id(self) -> int | None:
        """The place called Cupboard (the first, if there are several), or None."""
        for place in self.places:
            if _key(place.name) == CUPBOARD:
                return place.id
        return None


def kitchen_of(db: DbSession, household_id: int) -> KnownIngredients:
    """One read of the household's ingredients (not removed, not merged away), their other
    names and sizes, and its places. Every query is limited to this household."""
    foods = list(
        db.scalars(
            select(Food)
            .where(
                Food.household_id == household_id,
                Food.removed_at.is_(None),
                Food.merged_into_id.is_(None),
            )
            .order_by(Food.id)
        )
    )
    wanted = {food.id for food in foods}
    others: dict[int, list[str]] = {}
    for other in db.scalars(
        select(FoodName).where(FoodName.household_id == household_id).order_by(FoodName.id)
    ):
        if other.food_id in wanted:
            others.setdefault(other.food_id, []).append(other.name)
    sizes: dict[int, list[KitchenSize]] = {}
    for size in db.scalars(
        select(FoodSize)
        .where(FoodSize.household_id == household_id)
        .order_by(FoodSize.position, FoodSize.id)
    ):
        if size.food_id in wanted:
            sizes.setdefault(size.food_id, []).append(
                KitchenSize(size.id, size.name, size.plural, size.amount_milli)
            )
    household = db.get(Household, household_id)
    return KnownIngredients(
        household_id=household_id,
        cup_ml=cup_ml(household) if household is not None else DEFAULT_CUP_ML,
        foods=tuple(
            KitchenFood(
                id=food.id,
                name=food.name,
                counted_as=cast(CountedAs, food.counted_as),
                staple=food.staple,
                other_names=tuple(others.get(food.id, ())),
                sizes=tuple(sizes.get(food.id, ())),
            )
            for food in foods
        ),
        places=tuple(KitchenPlace(p.id, p.name) for p in household_places(db, household_id)),
    )


# --- The first guess for a new ingredient -----------------------------------------------------


@dataclass(frozen=True)
class NewIngredient:
    """The first guess for "New ingredient" (and, with `staple`, "Treat as staple"), all
    changeable on the review screen. Nothing is created, and nothing goes into the pantry."""

    name: str
    counted_as: CountedAs
    place_id: int | None  # the household's Cupboard, or None if it has none
    staple: bool = False


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def _short(text: str) -> str:
    if len(text) <= MAX_NAME_CHARS:
        return text
    return (text[:MAX_NAME_CHARS].rsplit(" ", 1)[0] or text[:MAX_NAME_CHARS]).rstrip()


def first_guess(kitchen: KnownIngredients, read: ReadLine, staple: bool = False) -> NewIngredient:
    """Name: the line without amount, unit and prep words, with a capital ("finely chopped
    red onions" → "Red onions"). Counted as: weight for g and kg, volume for ml, l, tsp,
    tbsp and cup, count for a plain number; weight when the line has no amount. Place: the
    household's Cupboard, else none. A line that couldn't be read gets its own words."""
    name = read.name or working_text(read.text)
    counted_as: CountedAs
    if read.unit in COUNTED_AS:
        counted_as = COUNTED_AS[read.unit]
    elif read.amount is not None and read.unit is None:
        counted_as = "count"
    else:
        counted_as = "weight"
    short = _short(
        _capital(name)
    )  # never the whole of a hostile line (names.normalise is slow on it)
    return NewIngredient(short, counted_as, kitchen.usual_place_id(short), staple)


# --- The match --------------------------------------------------------------------------------


@dataclass(frozen=True)
class Match:
    """How one line fits the household's ingredients.

    - `label`: matched, staple, to_confirm or needs_you.
    - `food_id`, `food_name`: the ingredient it is (matched, staple) or the best guess
      (to_confirm); None for needs_you.
    - `matched_by`: the words of the line that matched (its name, or a name beside it).
    - `size_id`: the ingredient's size the line's size word names ("1 bunch" → "bunch").
    - `counts`: whether the line counts towards stock. A staple never does. A size word
      counts only when the ingredient has that size. Lines that aren't matched say what
      they would do without a size.
    - `amount_base`, `base_unit`: the amount in g, ml or count when it counts. A cup is the
      household's own (`amounts.unit_size`), never an assumed 250.
    - `new_ingredient`: the first guess for a new ingredient. On every line that isn't
      matched or a staple; matched lines carry it too, but it is not used.
    """

    read: ReadLine
    label: Label
    food_id: int | None
    food_name: str | None
    matched_by: str | None
    size_id: int | None
    counts: bool
    amount_base: Decimal | None
    base_unit: Literal["g", "ml", "count"] | None
    new_ingredient: NewIngredient = field(compare=False)


def _words(key: str) -> frozenset[str]:
    return frozenset(key.split())


# Words that only say what state or part of the thing it is, so a line that adds them is still
# that thing ("coriander leaves" for Coriander, "tinned chickpeas" for Chickpeas).
PART_WORDS = frozenset(
    {"leaf", "sprig", "stalk", "stem", "bulb", "tinned", "canned", "flaked", "loose", "baby"}
    # kinds of salt, which is still salt ("sea salt" for Salt)
    | {"sea", "table", "kosher", "flaky", "rock"}
    # a cut or part of an animal or an egg, which is still that meat or egg ("chicken thighs"
    # for Chicken, "beef mince" for Beef, "egg yolks" for Eggs)
    | {
        "thigh",
        "breast",
        "mince",
        "fillet",
        "shoulder",
        "leg",
        "wing",
        "drumstick",
        "yolk",
        "white",
        "belly",
        "loin",
        "chop",
        "rib",
        "steak",
        "cutlet",
        "shank",
        "neck",
        "tail",
        "rump",
        "brisket",
        "flank",
        "cheek",
        "liver",
        "kidney",
    }
)
# As they stand in a key (`_key` turns "baby" into "babi").
_DESCRIBING = frozenset(_key(word) for word in MODIFIER_WORDS | PART_WORDS)


def _is_another_thing(theirs: frozenset[str], key: str) -> bool:
    """F186 (cabledrawer 8 Nov; middle way, cabledrawer 10 Nov): a food with one word in its name
    ("Rice", "Onions", "Sugar") against a line that adds a word of its own to it.

    - The food's word is the line's main word, the last word that isn't a colour, size, state
      or part ("caster sugar", "red onion", "cheddar cheese", "olive oil"): it is still that
      thing, so it is offered.
    - The food's word is only a side word ("rice flour", "lemon juice", "tomato puree",
      "poha (flattened rice)" against Basmati rice): another thing, so it is not offered.
    - A side word that is an ingredient of its own changes nothing: "chicken stock" is offered
      Stock even when the household has Chicken, as cabledrawer's rule says (the main word decides).

    A colour, size, state or part of the thing ("red", "dried", "leaves") is not a word of its
    own. The words are keys (`_key`)."""
    line = _words(key)
    if len(theirs) != 1 or not theirs < line:
        return False
    extras = line - theirs - _DESCRIBING
    if not extras:
        return False
    main = next((w for w in reversed(key.split()) if w not in _DESCRIBING), None)
    return main not in theirs


def _candidates(read: ReadLine) -> list[tuple[str, str]]:
    """(key, name as shown) for each way the line names the ingredient, best first."""
    found: dict[str, str] = {}
    for name in (read.name_as_written, read.name, *read.other_names):
        key = _key(name)
        if key:
            found.setdefault(key, name)
    return list(found.items())


def _find_exact(
    kitchen: KnownIngredients, candidates: list[tuple[str, str]]
) -> tuple[KitchenFood, str] | None:
    for key, shown in candidates:
        food = kitchen.by_name.get(key) or kitchen.by_other_name.get(key)
        if food is not None:
            return food, shown
    return None


def _closest(
    kitchen: KnownIngredients, candidates: list[tuple[str, str]]
) -> tuple[KitchenFood, str] | None:
    """A food whose name, or other name, has all its words inside the line's name, or the
    other way round ("red onion" and "onion"). The best share of the words wins; the line's
    more specific name beats a more specific food; the oldest food breaks a tie."""
    best: tuple[tuple[float, int, int], KitchenFood, str] | None = None
    for key, shown in candidates:
        line = _words(key)
        # Only a name that shares a word with the line can be inside it or hold it.
        wanted = {index for word in line for index in kitchen.word_index.get(word, ())}
        for index in wanted:
            theirs, food = kitchen.name_words[index]
            # An equal set is the same words in another order ("dal toor").
            if not (theirs <= line or line <= theirs):
                continue
            if theirs & line <= WEAK_WORDS:
                continue  # only a colour or size word in common
            if _is_another_thing(theirs, key):
                continue  # only one word in common, and the line is another thing (F186)
            share = len(theirs & line) / len(theirs | line)
            score = (share, 1 if theirs <= line else 0, -food.id)
            if best is None or score > best[0]:
                best = (score, food, shown)
    return (best[1], best[2]) if best else None


def _size_of(food: KitchenFood, word: str | None) -> KitchenSize | None:
    if word is None:
        return None
    key = _key(word)
    for size in food.sizes:
        if key in (_key(size.name), _key(size.plural)):
            return size
    return None


_BASE: dict[str, Literal["g", "ml", "count"]] = {
    "weight": "g",
    "volume": "ml",
    "count": "count",
}


def _in_base(
    amount: Decimal, unit: str | None, size: KitchenSize | None, food: KitchenFood | None, cup: int
) -> tuple[Decimal, Literal["g", "ml", "count"]] | None:
    """The amount in g, ml or count, or None if there is none (a pinch), or if it comes to more
    than the most an amount can be (900,000 kg is 900,000,000 g): such a line doesn't count."""
    found = _in_base_unchecked(amount, unit, size, food, cup)
    return found if found is not None and found[0] <= MAX_AMOUNT else None


def _in_base_unchecked(
    amount: Decimal, unit: str | None, size: KitchenSize | None, food: KitchenFood | None, cup: int
) -> tuple[Decimal, Literal["g", "ml", "count"]] | None:
    if unit == "pinch":
        return None
    if unit is not None:
        base = amount * unit_size(unit, cup)
        return base, "g" if COUNTED_AS[unit] == "weight" else "ml"
    if size is not None and food is not None:
        return amount * Decimal(size.amount_milli) / MILLI, _BASE[food.counted_as]
    return amount, "count"


def match_line(kitchen: KnownIngredients, read: ReadLine) -> Match:
    """Label one read line. See the module's notes for the four labels."""
    guess = first_guess(kitchen, read)
    if not read.readable:
        return Match(read, "needs_you", None, None, None, None, False, None, None, guess)

    candidates = _candidates(read)
    exact = _find_exact(kitchen, candidates)
    food, by = exact if exact else (None, None)
    label: Label
    if food is not None:
        label = "staple" if food.staple else "matched"
    else:
        close = _closest(kitchen, candidates)
        if close is None:
            return _unmatched(kitchen, read, "needs_you", None, None, guess)
        return _unmatched(kitchen, read, "to_confirm", close[0], close[1], guess)

    size = _size_of(food, read.size_word) if read.unit is None else None
    counts = (
        not food.staple
        and read.amount is not None
        and read.unit != "pinch"
        and (read.unit is not None or read.size_word is None or size is not None)
    )
    base = (
        _in_base(read.amount, read.unit, size, food, kitchen.cup_ml)
        if counts and read.amount
        else None
    )
    counts = counts and (base is not None or not read.amount)
    return Match(
        read,
        label,
        food.id,
        food.name,
        by,
        size.id if size else None,
        counts,
        base[0] if base else None,
        base[1] if base else None,
        guess,
    )


def _unmatched(
    kitchen: KnownIngredients,
    read: ReadLine,
    label: Label,
    food: KitchenFood | None,
    by: str | None,
    guess: NewIngredient,
) -> Match:
    counts = read.counts
    base = (
        _in_base(read.amount, read.unit, None, None, kitchen.cup_ml)
        if counts and read.amount
        else None
    )
    counts = counts and (base is not None or not read.amount)
    return Match(
        read,
        label,
        food.id if food else None,
        food.name if food else None,
        by,
        None,
        counts,
        base[0] if base else None,
        base[1] if base else None,
        guess,
    )
