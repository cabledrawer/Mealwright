"""What the All recipes list answers: each recipe's row, with its stock hints
(docs/dev/api-0.4-recipes.md, section 4)."""

from datetime import date
from typing import Literal

from pydantic import BaseModel

from mealwright.api.v1.recipe_schemas import RecipeBrief
from mealwright.api.v1.schemas import Ref


class StockHint(BaseModel):
    counted: int  # the ingredients that count (lines with no amount and headings never do)
    missing: int  # how many of those are not in stock
    can_cook_now: bool  # something counts, nothing is missing, and no line is left unchecked


class UseSoonHint(BaseModel):
    foods: list[Ref]  # the ingredients the recipe uses that go off first, A to Z
    use_by: date  # their use-by date
    days_left: int  # 0 is today


class RecipeRow(RecipeBrief):
    kcal: float | None  # per serving; null is unknown, never 0
    stock: StockHint | None  # null when no ingredient line counts
    use_soon: UseSoonHint | None
    # Some line uses a recipe that isn't checked (not made ahead, or no pantry ingredient yet):
    # the screen never says "all in stock" for it, and it is never Can cook now.
    stock_unchecked: bool


class RecipePage(BaseModel):
    total: int  # recipes matching the search and filters
    all_recipes: int  # every recipe the household has (the number in the title)
    recipes: list[RecipeRow]
    next: str | None


class LineStock(BaseModel):
    line_id: int
    food: Ref  # the pantry ingredient this line is checked against (a made-ahead recipe's own)
    # in_stock: the pantry holds enough (or any, when the amounts can't be compared) ·
    # staple: assumed in stock · short: some in the pantry, not enough · missing: none.
    state: Literal["in_stock", "staple", "short", "missing"]
    place: str | None  # where most of it is, when in_stock ("Cupboard")


class RecipeStock(BaseModel):
    """Where one recipe's ingredients are (the recipe page). Lines that don't count (no amount,
    a heading, nothing linked, a recipe that isn't checked) are not in `lines`."""

    lines: list[LineStock]
    counted: int  # as in the list's hint: different ingredients that count
    missing: int  # how many of those are not in stock
    stock_unchecked: bool  # some line uses a recipe that isn't checked: never "all in stock"
