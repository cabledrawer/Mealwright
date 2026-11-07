"""Use by or Best before (cabledrawer 7 Nov, spec section 6, "Decided for 0.8.0").

Every ingredient has a date type. Unless the household chose one, it comes from the
pack-size table's `dates` column when the ingredient matches a row, else from where it is
usually kept (fridge: Use by; cupboard, freezer, spice rack or nowhere: Best before).
Meat, poultry, fish and chilled dairy are always Use by and can't be switched: the table
says so (`dates` is "use by"), or, when the table has no row for it, its aisle is Meat &
fish or Dairy. A table row that says "best before" (butter, eggs) wins over the aisle.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from mealwright.models import Food
from mealwright.pack_sizes import table

DateKind = Literal["use_by", "best_before"]
USE_BY: DateKind = "use_by"
BEST_BEFORE: DateKind = "best_before"
KINDS = (USE_BY, BEST_BEFORE)

# Aisles whose ingredients are always Use by when the pack-size table has no row for them.
LOCKED_AISLES = ("meat_fish", "dairy")


def _table_kind(names: Sequence[str]) -> DateKind | None:
    row = table().match(*names)
    if row is None:
        return None
    return USE_BY if row.dates == "use by" else BEST_BEFORE


def locked(food: Food, names: Sequence[str]) -> bool:
    """True when it is always Use by."""
    from_table = _table_kind(names)
    if from_table is not None:
        return from_table == USE_BY
    return food.aisle in LOCKED_AISLES


def default_kind(food: Food, names: Sequence[str], place_kind: str | None) -> DateKind:
    """What it is with nothing chosen: the table's, else by where it is usually kept."""
    from_table = _table_kind(names)
    if from_table is not None:
        return from_table
    return USE_BY if place_kind == "fridge" else BEST_BEFORE


def date_kind(food: Food, names: Sequence[str], place_kind: str | None) -> DateKind:
    """The date type in force: always Use by when locked, else the household's choice, else
    the default. `names` are the food's name and its other names."""
    if locked(food, names):
        return USE_BY
    if food.date_kind in KINDS:
        return food.date_kind
    return default_kind(food, names, place_kind)
