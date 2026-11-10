"""Common UK pack sizes and where each ingredient is usually bought (F120, F121).

Mealwright's own table, `data/pack-sizes.csv` (cabledrawer 7 Nov): suggestions only. An
ingredient matches by its name or other names; with no match, the generic sizes by kind
(the same ones the Shopping pack sheet offers). Sizes in another kind are converted with
`food-conversions.csv` when the density (or the weight of one) is known, else skipped.
"""

from __future__ import annotations

import csv
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from typing import Literal

from mealwright.aisles import AISLE_KEYS
from mealwright.conversions import TableRow
from mealwright.conversions import table as conversion_table
from mealwright.names import normalise

Where = Literal["supermarket", "world aisle", "specialist"]
CountedAs = Literal["weight", "volume", "count"]

# The generic sizes when the table has nothing (PackSheet.svelte READY_MADE), base units.
GENERIC: dict[str, tuple[int, ...]] = {
    "weight": (100, 250, 500, 1000),
    "volume": (250, 500, 1000),
    "count": (1, 2, 6, 12),
}

# Words in a shop's name that say it sells one cuisine's ingredients (cabledrawer 7 Nov).
CUISINE_WORDS: dict[str, tuple[str, ...]] = {
    "indian": (
        "indian",
        "south indian",
        "tamil",
        "desi",
        "pakistani",
        "bangladeshi",
        "sri lankan",
    ),
    "chinese": ("chinese", "oriental", "asian"),
    "japanese": ("japanese", "oriental", "asian"),
    "middle eastern": (
        "arabic",
        "lebanese",
        "turkish",
        "middle eastern",
        "persian",
        "halal",
        "mediterranean",
    ),
}
_SUPERMARKET_WORDS = (
    "supermarket",
    "tesco",
    "sainsbury",
    "asda",
    "morrisons",
    "waitrose",
    "aldi",
    "lidl",
    "ocado",
    "co-op",
    "coop",
    "m&s",
    "marks",
    "iceland",
)

_UNITS: dict[str, tuple[CountedAs, int]] = {
    "g": ("weight", 1000),
    "kg": ("weight", 1_000_000),
    "ml": ("volume", 1000),
    "l": ("volume", 1_000_000),
    "": ("count", 1000),
}
_SIZE = re.compile(r"^\s*(\d+(?:\.\d+)?)\s*([a-z]*)\s*$")


@dataclass(frozen=True)
class Size:
    """One size as written in the table: 500 g → ("weight", 500_000)."""

    counted_as: CountedAs
    amount_milli: int


@dataclass(frozen=True)
class PackRow:
    key: str
    names: tuple[str, ...]
    pack: str
    sizes: tuple[Size, ...]
    where: Where
    dates: str
    cuisine: str = ""  # indian, chinese, japanese, middle eastern, or empty
    aisle: str = ""  # an aisle key (mealwright.aisles), or empty


@dataclass(frozen=True)
class PackTable:
    rows: dict[str, PackRow]
    by_name: dict[str, str]  # normalised name → key

    def match(self, *names: str) -> PackRow | None:
        """The row for an ingredient, by its name or any of its other names."""
        for name in names:
            key = self.by_name.get(normalise(name))
            if key:
                return self.rows[key]
        return None


def parse_size(text: str) -> Size:
    found = _SIZE.match(text.lower())
    if not found or found.group(2) not in _UNITS:
        raise ValueError(f"pack size {text!r}")
    counted_as, per = _UNITS[found.group(2)]
    return Size(counted_as, round(float(found.group(1)) * per))


@cache
def table() -> PackTable:
    source = files("mealwright") / "data" / "pack-sizes.csv"
    with source.open(encoding="utf-8") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    rows: dict[str, PackRow] = {}
    by_name: dict[str, str] = {}
    for record in csv.DictReader(lines):
        where = record["where"]
        if where not in ("supermarket", "world aisle", "specialist"):
            raise ValueError(f"{record['key']}: where {where!r}")
        if (record.get("cuisine") or "") not in ("", *CUISINE_WORDS):
            raise ValueError(f"{record['key']}: cuisine {record['cuisine']!r}")
        if (record.get("aisle") or "") not in ("", *AISLE_KEYS):
            raise ValueError(f"{record['key']}: aisle {record['aisle']!r}")
        if record["key"] in rows:
            raise ValueError(f"{record['key']} twice")
        row = PackRow(
            key=record["key"],
            names=tuple(name for name in record["names"].split("|") if name),
            pack=record["pack"],
            sizes=tuple(parse_size(size) for size in record["sizes"].split("|") if size),
            where=where,  # type: ignore[arg-type]
            dates=record["dates"],
            cuisine=record.get("cuisine") or "",
            aisle=record.get("aisle") or "",
        )
        rows[row.key] = row
        for name in (row.key.replace("_", " "), *row.names):
            # The first row to name it wins: a later row can't take a name over.
            by_name.setdefault(normalise(name), row.key)
    return PackTable(rows, by_name)


@dataclass(frozen=True)
class Suggestion:
    """A common size, in the ingredient's own base unit (milli-g, milli-ml or milli-items)."""

    pack: str | None  # "jar", "bag"; None for the generic sizes
    amount_milli: int


def shop_size(amount_milli: int) -> int:
    """A converted size, rounded to one a shop would sell (F183, cabledrawer 8 Nov: no "592 ml" of
    sugar). Grams or millilitres: to the nearest 5 under 100, 25 under 250, 50 under 1000, 100
    under 2000, else 250 (382 g → 400 g, 246 ml → 250 ml, 1183 ml → 1.2 L), never below 5."""
    value = amount_milli / 1000
    if value < 100:
        step = 5
    elif value < 250:
        step = 25
    elif value < 1000:
        step = 50
    elif value < 2000:
        step = 100
    else:
        step = 250
    return max(5, round(value / step) * step) * 1000


def _convert(size: Size, counted_as: CountedAs, density: TableRow | None) -> int | None:
    """A table size in the ingredient's own kind. Weight and volume go through the density (and
    are rounded to a size a shop sells); anything to or from a count is left out, because a
    count stays a count (a banana's weight is not a pack size)."""
    if size.counted_as == counted_as:
        return size.amount_milli
    if density is None or not density.mg_per_ml:
        return None
    if size.counted_as == "weight" and counted_as == "volume":
        return shop_size(round(size.amount_milli * 1000 / density.mg_per_ml))
    if size.counted_as == "volume" and counted_as == "weight":
        return shop_size(round(size.amount_milli * density.mg_per_ml / 1000))
    return None


def suggest_sizes(
    names: Sequence[str], counted_as: CountedAs, table_key: str | None = None
) -> list[Suggestion]:
    """Common sizes for an ingredient (its name first, then its other names), most common
    first, without repeats. No table row, or none of its sizes fit the way the ingredient is
    counted → the generic sizes for its kind."""
    row = table().match(*names)
    generic = [Suggestion(None, base * 1000) for base in GENERIC[counted_as]]
    if row is None:
        return generic
    conversions = conversion_table()
    density = (conversions.rows.get(table_key) if table_key else None) or conversions.rows.get(
        row.key
    )
    if density is None:
        density = conversions.match(*names)
    out: list[Suggestion] = []
    seen: set[int] = set()
    for size in row.sizes:
        amount = _convert(size, counted_as, density)
        if amount is None or amount <= 0 or amount in seen:
            continue
        seen.add(amount)
        out.append(Suggestion(row.pack or None, amount))
    return out or generic


def where_to_buy(names: Sequence[str]) -> Where | None:
    row = table().match(*names)
    return row.where if row else None


def _mentions(name: str, words: Iterable[str]) -> bool:
    text = f" {name.lower()} "
    return any(re.search(rf"(?<![a-z]){re.escape(word)}(?![a-z])", text) for word in words)


def suggest_shop_id(
    where: Where | None, shops: Sequence[tuple[int, str]], cuisine: str = ""
) -> int | None:
    """A new ingredient's Usual shop (cabledrawer 7 Nov). `shops` are (id, name) in Settings
    order. An ingredient with a cuisine (specialist, world aisle or supermarket) → the first
    shop whose name matches it. Otherwise: specialist → the first shop that isn't a
    supermarket, else none; supermarket and world aisle → the first shop."""
    if where is None or not shops:
        return None
    words = CUISINE_WORDS.get(cuisine, ())
    for shop_id, name in shops:
        if _mentions(name, words):
            return shop_id
    if where != "specialist":
        return shops[0][0]
    for shop_id, name in shops:
        if not _mentions(name, _SUPERMARKET_WORDS):
            return shop_id
    return None


def usual_shop_id(names: Sequence[str], shops: Sequence[tuple[int, str]]) -> int | None:
    """The Usual shop to suggest for a new ingredient with these names, by the table."""
    row = table().match(*names)
    return suggest_shop_id(row.where, shops, row.cuisine) if row else None
