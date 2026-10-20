"""The All recipes list: search, tag, "Can cook now" and the stock hints
(docs/dev/api-0.4-recipes.md, section 4).

Everything is read in a fixed number of queries, however many recipes there are (never one
query per recipe): the recipes, their lines, the ingredients, sizes, the household's own
conversions, stock, tags and other names are each read once for the whole household, then
worked out here. Every query is limited to the signed-in household.

The stock rules. cabledrawer's answers (19 Oct, questions 21 and 22): only ingredient lines with an
amount count, and any other ingredient is in stock when the pantry covers what the recipe
needs at its own servings, if the two amounts can be compared; if not, any stock counts.
Everything else below is the spec's or a lead's note, as marked:
- Only ingredient lines with an amount count. Headings, lines with no amount ("salt to
  taste") and lines that link to nothing never do (cabledrawer, Q21 and Q22). A recipe whose lines
  all lack amounts gets no hint and is not "Can cook now" (lead's note, waiting for cabledrawer).
- A staple counts as in stock, always (spec, Stock section: "Staples: assumed in stock,
  not quantity-tracked").
- Any other ingredient is in stock when the amount in the pantry covers what the recipe needs
  at its own servings, if the two can be compared; if they can't ("1 cup" of something with
  no known weight, a pinch), any stock counts (cabledrawer, Q22).
- Stock in every place counts, the freezer too (lead's note, waiting for cabledrawer).
- A line that uses a made-ahead recipe is checked against that recipe's own pantry
  ingredient. A line that uses any other recipe is not checked and doesn't count (shopping
  through it comes with 0.6). Both lead's notes, waiting for cabledrawer.
- "Can cook now" is: something counts and nothing is missing (lead's note, waiting for cabledrawer).
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import select

from mealwright.amounts import MILLI, TooBig, unit_family
from mealwright.api.v1.context import Kitchen
from mealwright.api.v1.recipe_list_schemas import (
    RecipePage,
    RecipeRow,
    StockHint,
    UseSoonHint,
)
from mealwright.api.v1.schemas import Ref
from mealwright.conversions import AskOnce, Known, UnitAmount, to_base_milli
from mealwright.foods import known_from, visible
from mealwright.household import cup_ml, today
from mealwright.models import (
    Food,
    FoodConversion,
    FoodName,
    FoodSize,
    Recipe,
    RecipeLine,
    RecipeTag,
    StockLot,
    Tag,
)
from mealwright.names import fold
from mealwright.recipes import brief_list, live_recipes


@dataclass(frozen=True)
class Line:
    recipe_id: int
    words: str
    food_id: int | None
    sub_recipe_id: int | None
    amount_milli: int | None
    unit: str | None
    size_id: int | None


def _lines(kitchen: Kitchen, live: set[int]) -> list[Line]:
    """Every ingredient line (not headings) of the household's recipes."""
    rows = kitchen.db.execute(
        select(
            RecipeLine.recipe_id,
            RecipeLine.words,
            RecipeLine.food_id,
            RecipeLine.sub_recipe_id,
            RecipeLine.amount_milli,
            RecipeLine.unit,
            RecipeLine.size_id,
        ).where(RecipeLine.household_id == kitchen.household_id, RecipeLine.kind == "ingredient")
    )
    return [Line(*row) for row in rows if row[0] in live]


def _foods(kitchen: Kitchen) -> dict[int, Food]:
    return {
        food.id: food
        for food in kitchen.db.scalars(
            select(Food).where(Food.household_id == kitchen.household_id)
        )
        if visible(food)
    }


class Stock:
    """What the pantry holds, read once: how much of each ingredient, and the soonest
    use-soon date among its packets."""

    def __init__(self, kitchen: Kitchen, foods: dict[int, Food]) -> None:
        household = kitchen.household
        self.today = today(household)
        soon = self.today + timedelta(days=household.use_soon_days)
        self.total: dict[int, int] = defaultdict(int)
        self.soonest: dict[int, date] = {}
        for lot in kitchen.db.scalars(
            select(StockLot).where(
                StockLot.household_id == kitchen.household_id, StockLot.amount_milli > 0
            )
        ):
            self.total[lot.food_id] += lot.amount_milli
            # A packet whose date has passed is not a nudge to cook: the Pantry shows it.
            if lot.use_by is not None and self.today <= lot.use_by <= soon:
                best = self.soonest.get(lot.food_id)
                if best is None or lot.use_by < best:
                    self.soonest[lot.food_id] = lot.use_by
        self.cup = cup_ml(household)
        self.sizes = {
            size.id: size
            for size in kitchen.db.scalars(
                select(FoodSize).where(FoodSize.household_id == kitchen.household_id)
            )
        }
        mine: dict[int, dict[str, FoodConversion]] = defaultdict(dict)
        for conversion in kitchen.db.scalars(
            select(FoodConversion).where(FoodConversion.household_id == kitchen.household_id)
        ):
            mine[conversion.food_id][conversion.kind] = conversion
        self._known = {food.id: known_from(food, mine[food.id]) for food in foods.values()}
        self.foods = foods

    def need(self, line: Line, food: Food) -> int | None:
        """What the line asks for, in the ingredient's own units (thousandths), or None
        when it can't be compared with what's in the pantry."""
        if line.amount_milli is None:
            return None
        if line.size_id is not None:
            size = self.sizes.get(line.size_id)
            if size is None or size.food_id != food.id:
                return None
            return line.amount_milli * size.amount_milli // MILLI
        unit = line.unit or "count"
        if unit_family(unit) is None:  # a pinch
            return None
        known: Known = self._known[food.id]
        try:
            return to_base_milli(
                UnitAmount(Decimal(line.amount_milli) / MILLI, unit),
                food.counted_as,  # type: ignore[arg-type]
                known,
                self.cup,
            )
        except AskOnce, TooBig:
            return None

    def has_enough(self, food: Food, needed: int) -> bool:
        if food.staple:
            return True
        have = self.total.get(food.id, 0)
        return have > 0 and have >= needed


def _ingredient_of(line: Line, foods: dict[int, Food], recipes: dict[int, Recipe]) -> Food | None:
    """The pantry ingredient a line is about: its own, or a made-ahead recipe's."""
    if line.food_id is not None:
        return foods.get(line.food_id)
    if line.sub_recipe_id is not None:
        sub = recipes.get(line.sub_recipe_id)
        if sub is not None and sub.made_ahead and sub.homemade_food_id is not None:
            return foods.get(sub.homemade_food_id)
    return None


def hints(
    lines: list[Line], recipes: dict[int, Recipe], stock: Stock
) -> dict[int, tuple[StockHint | None, UseSoonHint | None]]:
    """For every recipe: whether its ingredients are in stock, and what it uses that is
    about to go off."""
    by_recipe: dict[int, list[Line]] = defaultdict(list)
    for line in lines:
        if line.amount_milli is not None:
            by_recipe[line.recipe_id].append(line)
    found: dict[int, tuple[StockHint | None, UseSoonHint | None]] = {}
    for recipe_id in recipes:
        needs: dict[int, int] = {}
        for line in by_recipe.get(recipe_id, ()):
            food = _ingredient_of(line, stock.foods, recipes)
            if food is None:
                continue
            needs[food.id] = needs.get(food.id, 0) + (stock.need(line, food) or 0)
        if not needs:
            found[recipe_id] = (None, None)
            continue
        missing = sum(
            not stock.has_enough(stock.foods[food_id], needed) for food_id, needed in needs.items()
        )
        dates = {f: stock.soonest[f] for f in needs if f in stock.soonest}
        soon: UseSoonHint | None = None
        if dates:
            first = min(dates.values())
            names = sorted(
                (stock.foods[f] for f, day in dates.items() if day == first),
                key=lambda food: (fold(food.name), food.id),
            )
            soon = UseSoonHint(
                foods=[Ref(id=f.id, name=f.name) for f in names],
                use_by=first,
                days_left=(first - stock.today).days,
            )
        found[recipe_id] = (
            StockHint(counted=len(needs), missing=missing, can_cook_now=missing == 0),
            soon,
        )
    return found


def _search_text(
    kitchen: Kitchen,
    recipes: dict[int, Recipe],
    lines: list[Line],
    foods: dict[int, Food],
    tags: dict[int, list[str]],
) -> dict[int, str]:
    """Everything a typed search looks in, per recipe: its name, tags, and ingredient names
    (the ingredient's name and other names, the words typed on the line, and the name of a
    recipe used as an ingredient). Never the method."""
    other: dict[int, list[str]] = defaultdict(list)
    for food_id, name in kitchen.db.execute(
        select(FoodName.food_id, FoodName.name).where(FoodName.household_id == kitchen.household_id)
    ):
        other[food_id].append(name)
    parts: dict[int, list[str]] = {
        recipe_id: [recipe.name, *tags.get(recipe_id, [])] for recipe_id, recipe in recipes.items()
    }
    for line in lines:
        mine = parts[line.recipe_id]
        mine.append(line.words)
        if line.food_id is not None and line.food_id in foods:
            mine.append(foods[line.food_id].name)
            mine.extend(other.get(line.food_id, ()))
        if line.sub_recipe_id is not None and line.sub_recipe_id in recipes:
            mine.append(recipes[line.sub_recipe_id].name)
    return {recipe_id: "\n".join(fold(p) for p in found) for recipe_id, found in parts.items()}


def _tags(kitchen: Kitchen, live: set[int]) -> dict[int, list[str]]:
    found: dict[int, list[str]] = defaultdict(list)
    for recipe_id, name in kitchen.db.execute(
        select(RecipeTag.recipe_id, Tag.name)
        .join(Tag, Tag.id == RecipeTag.tag_id)
        .where(
            Tag.household_id == kitchen.household_id, RecipeTag.household_id == kitchen.household_id
        )
    ):
        if recipe_id in live:
            found[recipe_id].append(name)
    return found


def page(
    kitchen: Kitchen,
    *,
    q: str,
    tag: str | None,
    can_cook_now: bool,
    start: int,
    limit: int,
) -> RecipePage:
    """One page of the household's recipes, A to Z, that match the search, the tag and
    "Can cook now" (all three together)."""
    recipes = live_recipes(kitchen)
    ordered = sorted(recipes.values(), key=lambda r: (fold(r.name), r.id))
    lines = _lines(kitchen, set(recipes))
    foods = _foods(kitchen)
    found = hints(lines, recipes, Stock(kitchen, foods))
    kept = ordered
    if can_cook_now:
        kept = [r for r in kept if (found[r.id][0] and found[r.id][0].can_cook_now)]  # type: ignore[union-attr]
    terms = fold(q).split()
    wanted = fold(tag) if tag and tag.strip() else None
    if terms or wanted:
        tags = _tags(kitchen, set(recipes))
        if wanted:
            kept = [r for r in kept if wanted in {fold(t) for t in tags.get(r.id, ())}]
        if terms:
            text = _search_text(kitchen, recipes, lines, foods, tags)
            kept = [r for r in kept if all(term in text[r.id] for term in terms)]
    shown = kept[start : start + limit]
    briefs = brief_list(kitchen, shown)
    rows = [
        RecipeRow(
            **brief.model_dump(),
            kcal=None if recipe.kcal_milli is None else recipe.kcal_milli / 1000,
            stock=found[recipe.id][0],
            use_soon=found[recipe.id][1],
        )
        for recipe, brief in zip(shown, briefs, strict=True)
    ]
    more = start + limit < len(kept)
    return RecipePage(
        total=len(kept),
        all_recipes=len(recipes),
        recipes=rows,
        next=str(start + limit) if more else None,
    )
