"""Use by or Best before (cabledrawer 7 Nov, spec section 6, "Decided for 0.8.0").

Every ingredient has a date type. Unless the household chose one, it comes from the
pack-size table's `dates` column when the ingredient matches a row, else from where it is
usually kept (fridge: Use by; cupboard, freezer, spice rack or nowhere: Best before).
Only meat, fish and chilled dairy are locked to Use by (cabledrawer 7 Nov): the food has a table
row that says "use by" and is meat or fish (the row's aisle) or one of the chilled dairy keys
below (milk, cream, yoghurt, cheese, paneer). It goes by what the food is, not by shop aisle:
idli batter sits in the Dairy aisle but can be switched, and so can tofu or spinach. A food
with no table row is never locked. Every other "use by" row starts as Use by and can be
switched; a row that says "best before" (butter, eggs) starts as Best before.
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

# Pack-size table keys of chilled dairy, which is always Use by (with meat and fish).
CHILLED_DAIRY = (
    "akkawi",
    "cream_cheese",
    "creme_fraiche",
    "double_cream",
    "feta",
    "greek_yoghurt",
    "halloumi",
    "khoya",
    "labneh",
    "milk",
    "mozzarella",
    "paneer",
    "semi_skimmed_milk",
    "single_cream",
    "skimmed_milk",
    "sour_cream",
    "whipping_cream",
    "yoghurt",
)


def _table_kind(names: Sequence[str]) -> DateKind | None:
    row = table().match(*names)
    if row is None:
        return None
    return USE_BY if row.dates == "use by" else BEST_BEFORE


def locked(food: Food, names: Sequence[str]) -> bool:
    """True when it is always Use by: meat, fish or chilled dairy with a "use by" table row."""
    row = table().match(*names)
    if row is None or row.dates != "use by":
        return False
    return row.aisle == "meat_fish" or row.key in CHILLED_DAIRY


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
