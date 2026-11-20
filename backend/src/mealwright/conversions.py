"""Converting between units: the bundled table, and the maths that asks once when it must.

Two layers (spec section 6): the table shipped with the app (USDA FoodData Central, see
docs/dev/conversions.md), with the household's own "ask once" answers on top. Household
answers always win; they're passed in here as `Known` values.
"""

import csv
from dataclasses import dataclass
from decimal import Decimal
from functools import cache
from importlib.resources import files
from typing import Literal

from mealwright.aisles import AISLE_KEYS, DEFAULT_AISLE
from mealwright.amounts import (
    MILLI,
    CountedAs,
    checked,
    significant,
    to_milli,
    unit_family,
    unit_size,
)
from mealwright.names import normalise

ConversionKind = Literal["weight_per_ml", "item_weight"]

# Suggestions when nothing better is known (docs/dev/api-endpoints.md section 4.4).
GENERIC_MG_PER_ML = 800


@dataclass(frozen=True)
class TableRow:
    key: str
    names: tuple[str, ...]
    counted_as: CountedAs
    mg_per_ml: int | None
    item_weight_mg: int | None
    aisle: str | None = None  # the starting aisle (mealwright.aisles), if the table has one


@dataclass(frozen=True)
class Table:
    rows: dict[str, TableRow]
    by_name: dict[str, str]  # normalised name → key

    def match(self, *names: str) -> TableRow | None:
        """The row for a food, by its name or any of its other names."""
        for name in names:
            key = self.by_name.get(normalise(name))
            if key:
                return self.rows[key]
        return None

    def close(self, name: str) -> TableRow | None:
        """A row whose name appears, as whole words, inside this name ("organic basmati
        rice" → basmati rice). The longest such name wins. Used only for suggestions."""
        words = f" {normalise(name)} "
        best: tuple[int, str] | None = None
        for table_name, key in self.by_name.items():
            if f" {table_name} " in words and (best is None or len(table_name) > best[0]):
                best = (len(table_name), key)
        return self.rows[best[1]] if best else None

    def ending(self, name: str) -> TableRow | None:
        """A row whose name is the end of this name, as whole words ("Alpha2 lemons" → lemon,
        "free range eggs" → eggs): the thing named is what the last words say. Not "mango
        chutney", which is not a mango. The longest such name wins. Used only for guesses."""
        words = f" {normalise(name)}"
        # "cheese and onion", "bag of onions", "eggs with bacon": a name of several things is not
        # the last one.
        if any(joiner in f"{words} " for joiner in (" and ", " of ", " with ")):
            return None
        best: tuple[int, str] | None = None
        for table_name, key in self.by_name.items():
            if words.endswith(f" {table_name}") and (best is None or len(table_name) > best[0]):
                best = (len(table_name), key)
        return self.rows[best[1]] if best else None


@cache
def table() -> Table:
    source = files("mealwright") / "data" / "food-conversions.csv"
    with source.open(encoding="utf-8") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    rows: dict[str, TableRow] = {}
    by_name: dict[str, str] = {}
    for record in csv.DictReader(lines):
        counted_as = record["counted_as"]
        if counted_as not in ("weight", "volume", "count"):
            raise ValueError(f"{record['key']}: counted_as {counted_as!r}")
        row = TableRow(
            key=record["key"],
            names=tuple(record["names"].split("|")),
            counted_as=counted_as,  # type: ignore[arg-type]
            mg_per_ml=int(record["mg_per_ml"]) if record["mg_per_ml"] else None,
            item_weight_mg=int(record["item_weight_mg"]) if record["item_weight_mg"] else None,
            aisle=record.get("aisle") or None,
        )
        if row.aisle is not None and row.aisle not in AISLE_KEYS:
            raise ValueError(f"{record['key']}: aisle {row.aisle!r}")
        rows[row.key] = row
        for name in row.names:
            other = by_name.setdefault(normalise(name), row.key)
            if other != row.key:
                raise ValueError(f"{name!r} is in both {other} and {row.key}")
    return Table(rows, by_name)


def guess_aisle(name: str, row: TableRow | None = None) -> str:
    """The starting aisle for a new ingredient (F54, cabledrawer 6 Nov): the bundled table's aisle
    for its name, else for a table name inside it as whole words ("organic basmati rice" →
    basmati rice), else "other". `row` is the table row already matched by the name, if any."""
    found = row if row is not None else table().match(name)
    if found is None or not found.aisle:
        found = table().close(name)
    return found.aisle if found is not None and found.aisle else DEFAULT_AISLE


# --- Converting -----------------------------------------------------------------------------


@dataclass(frozen=True)
class Known:
    """What's known about converting one food: the household's answer, else the table."""

    mg_per_ml: int | None
    item_mg: int | None


@dataclass
class AskOnce(Exception):
    """A conversion nobody knows yet: the person is asked once (spec section 2)."""

    kind: ConversionKind


@dataclass(frozen=True)
class UnitAmount:
    amount: Decimal
    unit: str  # g, kg, ml, cup, count…


def to_base_milli(value: UnitAmount, counted_as: CountedAs, known: Known, cup_ml: int) -> int:
    """`value` in the food's base unit, in thousandths. Raises AskOnce when a weight per ml
    or an item weight is needed and not known, and TooBig when the result is over the
    limit."""
    return checked(_to_base_milli(value, counted_as, known, cup_ml))


def _to_base_milli(value: UnitAmount, counted_as: CountedAs, known: Known, cup_ml: int) -> int:
    family = unit_family(value.unit)
    if family is None:
        raise ValueError(value.unit)
    base = value.amount * unit_size(value.unit, cup_ml)  # in g, ml or items
    if family == counted_as:
        return to_milli(base)

    # Go through grams.
    if family == "weight":
        grams = base
    elif family == "volume":
        if known.mg_per_ml is None:
            raise AskOnce("weight_per_ml")
        grams = base * known.mg_per_ml / MILLI
    else:
        if known.item_mg is None:
            raise AskOnce("item_weight")
        grams = base * known.item_mg / MILLI

    if counted_as == "weight":
        return to_milli(grams)
    if counted_as == "volume":
        if known.mg_per_ml is None:
            raise AskOnce("weight_per_ml")
        return to_milli(grams * MILLI / known.mg_per_ml)
    if known.item_mg is None:
        raise AskOnce("item_weight")
    return to_milli(grams * MILLI / known.item_mg)


def convert_milli(
    milli: int, source: CountedAs, target: CountedAs, known: Known, cup_ml: int
) -> int:
    """An amount in one base unit (thousandths) in another, e.g. when a food changes how
    it's counted or two foods are merged."""
    if source == target:
        return milli
    unit = {"weight": "g", "volume": "ml", "count": "count"}[source]
    return to_base_milli(UnitAmount(Decimal(milli) / MILLI, unit), target, known, cup_ml)


def suggestion(kind: ConversionKind, row: TableRow | None, cup_ml: int) -> Decimal | None:
    """The suggested answer in grams: per household cup, or per item.

    A cup always gets one (the spec's "Suggested: 200 g": dry goods are about 0.8 g/ml).
    One item doesn't unless the table knows a close food: items range from a garlic clove
    to a cabbage, so any fixed number would be a guess."""
    if kind == "weight_per_ml":
        mg_per_ml = (row.mg_per_ml if row else None) or GENERIC_MG_PER_ML
        return significant(Decimal(mg_per_ml) * cup_ml / MILLI)
    if row is None or row.item_weight_mg is None:
        return None
    return significant(Decimal(row.item_weight_mg) / MILLI)
