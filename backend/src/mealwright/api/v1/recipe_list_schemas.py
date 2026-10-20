"""What the All recipes list answers: each recipe's row, with its stock hints
(docs/dev/api-0.4-recipes.md, section 4)."""

from datetime import date

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
