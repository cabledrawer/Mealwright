"""Amounts: storing them exactly, converting units, and showing them the way they're sold.

Every amount is stored as a whole number of thousandths of the food's base unit
("milli"): milligrams, microlitres or thousandths of an item. 750 g is 750_000; 1½ onions
is 1_500. Whole numbers are exact on SQLite and Postgres alike, and quarters, halves and
whole grams never drift. See docs/dev/api-0.2.md section 2.

Display rules (spec section 6, "Decided for 0.2"): as sold to the nearest ¼; count foods
to the nearest ½; "about" figures to 2 significant figures. Halfway rounds up.
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

CountedAs = Literal["weight", "volume", "count"]
MILLI = 1000

BASE_UNIT: dict[str, str] = {"weight": "g", "volume": "ml", "count": "count"}

# Units people type, in base units (g, ml or items). The cup is the household's own.
WEIGHT_UNITS: dict[str, Decimal] = {
    "mg": Decimal("0.001"),
    "g": Decimal(1),
    "kg": Decimal(1000),
    "oz": Decimal("28.349523125"),
    "lb": Decimal("453.59237"),
}
VOLUME_UNITS: dict[str, Decimal] = {
    "ml": Decimal(1),
    "l": Decimal(1000),
    "tsp": Decimal(5),
    "tbsp": Decimal(15),
}
CUP_SIZES = (240, 250)
DEFAULT_CUP_ML = 250


def unit_family(unit: str) -> CountedAs | None:
    if unit in WEIGHT_UNITS:
        return "weight"
    if unit in VOLUME_UNITS or unit == "cup":
        return "volume"
    if unit == "count":
        return "count"
    return None


def unit_size(unit: str, cup_ml: int) -> Decimal:
    """How many g, ml or items one of `unit` is."""
    if unit in WEIGHT_UNITS:
        return WEIGHT_UNITS[unit]
    if unit in VOLUME_UNITS:
        return VOLUME_UNITS[unit]
    if unit == "cup":
        return Decimal(cup_ml)
    if unit == "count":
        return Decimal(1)
    raise ValueError(unit)


def to_milli(value: Decimal | float | int | str) -> int:
    """A number in base units → whole thousandths (rounded half up)."""
    return int((Decimal(str(value)) * MILLI).quantize(Decimal(1), rounding=ROUND_HALF_UP))


def from_milli(milli: int) -> float:
    """Thousandths → a plain number for JSON (at most 3 decimal places)."""
    return float(Decimal(milli) / MILLI)


def round_half_up(value: Decimal) -> int:
    return int(value.quantize(Decimal(1), rounding=ROUND_HALF_UP))


# --- Words ------------------------------------------------------------------------------

_IRREGULAR = {
    "loaf": "loaves",
    "leaf": "leaves",
    "half": "halves",
    "knife": "knives",
    "dozen": "dozen",
    "fish": "fish",
    "sheep": "sheep",
    "potato": "potatoes",
    "tomato": "tomatoes",
}


def plural(word: str) -> str:
    """A simple English plural for size names and count words ("packet" → "packets")."""
    word = word.strip()
    if not word:
        return word
    head, _, last = word.rpartition(" ")
    lower = last.lower()
    if lower in _IRREGULAR:
        result = _IRREGULAR[lower]
        if last[:1].isupper():
            result = result.capitalize()
    elif lower.endswith(("s", "x", "z", "ch", "sh")):
        result = last + "es"
    elif lower.endswith("y") and len(lower) > 1 and lower[-2] not in "aeiou":
        result = last[:-1] + "ies"
    else:
        result = last + "s"
    return f"{head} {result}" if head else result


def article(word: str) -> str:
    return "an" if word[:1].lower() in "aeiou" else "a"


# --- Numbers ------------------------------------------------------------------------------

_FRACTIONS = {0: "", 1: "¼", 2: "½", 3: "¾"}


def quarters_text(quarters: int) -> str:
    """7 → "1¾", 2 → "½", 8 → "2"."""
    whole, part = divmod(quarters, 4)
    if whole and part:
        return f"{whole}{_FRACTIONS[part]}"
    if part:
        return _FRACTIONS[part]
    return str(whole)


def _trim(value: Decimal) -> str:
    text = format(value, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"


def significant(value: Decimal, figures: int = 2) -> Decimal:
    """Round to significant figures, halfway up: 1490 → 1500, 7.34 → 7.3, 0.256 → 0.26."""
    if value == 0:
        return Decimal(0)
    exponent = value.adjusted() - figures + 1
    step = Decimal(1).scaleb(exponent)
    return (value / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step


def _with_unit(value: Decimal, counted_as: CountedAs) -> str:
    small, big = ("g", "kg") if counted_as == "weight" else ("ml", "L")
    if value >= 1000:
        return f"{_trim(value / 1000)} {big}"
    return f"{_trim(value)} {small}"


def exact_text(milli: int, counted_as: CountedAs) -> str:
    """An amount as typed or bought: "200 g", "7.5 g", "1 kg", "1.25 kg", "1.5 L"."""
    value = Decimal(milli) / MILLI
    if value >= 10:
        return _with_unit(value.quantize(Decimal(1), rounding=ROUND_HALF_UP), counted_as)
    return _with_unit(value.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP), counted_as)


def about_text(milli: int, counted_as: CountedAs) -> str:
    """A rounded figure, 2 significant figures: "about 750 g", "about 1.5 L"."""
    return "about " + _with_unit(significant(Decimal(milli) / MILLI), counted_as)


def count_text(milli: int, word: str | None, word_plural: str | None) -> str:
    """Count foods, to the nearest ½: "1½ onions" style, or "9 left" with no count word."""
    halves = round_half_up(Decimal(milli) / 500)
    number = quarters_text(halves * 2)
    if word:
        many = halves not in (1, 2)  # "½ slice", "1 slice", "0 slices", "1½ slices"
        return f"{number} {(word_plural or plural(word)) if many else word}"
    return f"{number} left"


# --- As sold ------------------------------------------------------------------------------


@dataclass(frozen=True)
class Size:
    id: int | None
    name: str
    plural: str
    amount_milli: int


@dataclass(frozen=True)
class AsSold:
    """An amount ready to show, with the numbers it was made from."""

    amount_milli: int
    counted_as: CountedAs
    size: Size | None  # the size it's shown in, if any
    count: Decimal | None  # how many of that size, rounded (¼ steps, or ½ for count foods)
    about: bool
    short: str  # the first part only: "1½ packets", "200 g", "9 left"
    display: str  # "1½ packets · about 750 g"


def as_sold(
    milli: int,
    counted_as: CountedAs,
    size: Size | None = None,
    count_word: str | None = None,
    count_word_plural: str | None = None,
) -> AsSold:
    """Show an amount the way it's sold (docs/dev/api-0.2.md section 5).

    - Count foods: a count to the nearest ½, plus "bought as a dozen" when the size isn't 1.
    - Weight and volume foods with a size: that size to the nearest ¼, then the amount. A
      whole number of sizes is exact ("2 packets · 1 kg"); anything else is "about".
    - No size: just the amount ("200 g").
    """
    milli = max(milli, 0)
    if counted_as == "count":
        short = count_text(milli, count_word, count_word_plural)
        display = short
        if size is not None and size.amount_milli != MILLI:
            display = f"{short} · bought as {article(size.name)} {size.name}"
        count = Decimal(round_half_up(Decimal(milli) / 500)) / 2
        return AsSold(milli, counted_as, size, count, False, short, display)

    if size is None or size.amount_milli <= 0 or milli == 0:
        text = exact_text(milli, counted_as)
        return AsSold(milli, counted_as, None, None, False, text, text)

    if milli % size.amount_milli == 0:
        whole = milli // size.amount_milli
        name = size.name if whole == 1 else size.plural
        short = f"{whole} {name}"
        return AsSold(
            milli,
            counted_as,
            size,
            Decimal(whole),
            False,
            short,
            f"{short} · {exact_text(milli, counted_as)}",
        )

    quarters = round_half_up(Decimal(milli) * 4 / size.amount_milli)
    if quarters == 0:
        short = f"under ¼ {size.name}"
    else:
        short = f"{quarters_text(quarters)} {size.name if quarters <= 4 else size.plural}"
    return AsSold(
        milli,
        counted_as,
        size,
        Decimal(quarters) / 4,
        True,
        short,
        f"{short} · {about_text(milli, counted_as)}",
    )
