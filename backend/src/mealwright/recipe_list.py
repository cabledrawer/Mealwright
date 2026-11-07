"""The All recipes list: search, tag, "Can cook now" and the stock hints
(docs/dev/api-0.4-recipes.md, section 4).

Everything is read in a fixed number of queries, however many recipes there are (never one
query per recipe): the recipes, their lines, the ingredients, sizes, the household's own
conversions, stock, tags and other names are each read once for the whole household, then
worked out here. Every query is limited to the signed-in household.

The stock rules. cabledrawer's answer (19 Oct, question 22): an ingredient is in stock when the
pantry covers what the recipe needs at its own servings, if the two amounts can be compared;
if not, any stock counts. cabledrawer's answers of 20 Oct (1 to 5) are marked below.
Everything else below is the spec's or cabledrawer's, as marked:
- Only ingredient lines with an amount count. A line with no amount ("salt to taste") never
  counts towards stock (cabledrawer 19 Oct, question 13); headings don't count (cabledrawer 20 Oct);
  a line that links to nothing has nothing to check. A recipe where no line counts gets no
  hint and is not "Can cook now" (cabledrawer 20 Oct).
- A staple counts as in stock, always (spec, Stock section: "Staples: assumed in stock,
  not quantity-tracked").
- Any other ingredient is in stock when the amount in the pantry covers what the recipe needs
  at its own servings, if the two can be compared; if they can't ("1 cup" of something with
  no known weight, a pinch), any stock counts (cabledrawer, Q22).
- Stock in every place counts, the freezer too (cabledrawer 20 Oct).
- A line that uses a made-ahead recipe is checked against that recipe's own pantry
  ingredient (cabledrawer 20 Oct).
- A line that uses any other recipe (not made ahead) is not checked (cabledrawer 20 Oct: inner
  recipes are checked in a later version). So is one using a made-ahead recipe with no pantry
  ingredient yet, or a recipe since deleted (cabledrawer 20 Oct). A line with no amount is
  ignored, whatever it points at (cabledrawer 20 Oct, question 13). Such a recipe is never
  "Can cook now" and its hint never says "all in stock" or "all in stock but 1": the row
  says `stock_unchecked`, and the screen says "N missing" when something that was checked
  is missing, and no stock words otherwise (cabledrawer 20 Oct).
- "Can cook now" is: something counts, nothing is missing, and no line is left unchecked
  (cabledrawer 20 Oct).
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Literal

from sqlalchemy import select

from mealwright.amounts import MILLI, TooBig, unit_family
from mealwright.api.v1.context import Kitchen
from mealwright.api.v1.recipe_list_schemas import (
    LineStock,
    RecipePage,
    RecipeRow,
    RecipeStock,
    StockHint,
    UseSoonHint,
)
from mealwright.api.v1.schemas import Ref
from mealwright.conversions import AskOnce, Known, UnitAmount, to_base_milli
from mealwright.date_kinds import date_kind
from mealwright.foods import known_from, visible
from mealwright.household import cup_ml, today
from mealwright.models import (
    Food,
    FoodConversion,
    FoodName,
    FoodSize,
    Place,
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
    id: int
    recipe_id: int
    words: str
    food_id: int | None
    sub_recipe_id: int | None
    amount_milli: int | None
    unit: str | None
    size_id: int | None


def _lines(kitchen: Kitchen, live: set[int], only: int | set[int] | None = None) -> list[Line]:
    """Every ingredient line (not headings) of the household's recipes, or of recipe `only`."""
    query = select(
        RecipeLine.id,
        RecipeLine.recipe_id,
        RecipeLine.words,
        RecipeLine.food_id,
        RecipeLine.sub_recipe_id,
        RecipeLine.amount_milli,
        RecipeLine.unit,
        RecipeLine.size_id,
    ).where(RecipeLine.household_id == kitchen.household_id, RecipeLine.kind == "ingredient")
    if isinstance(only, int):
        query = query.where(RecipeLine.recipe_id == only)
    elif only is not None:
        query = query.where(RecipeLine.recipe_id.in_(only))
    return [Line(*row) for row in kitchen.db.execute(query) if row[1] in live]


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
        # How much of each ingredient is in each place (place id → thousandths).
        self.in_place: dict[int, dict[int, int]] = defaultdict(lambda: defaultdict(int))
        self.soonest: dict[int, date] = {}
        # A Best before date is not a nudge to cook (Use soon counts it only once passed, and a
        # passed one isn't a nudge either): only an ingredient's Use by dates are.
        place_kinds = {
            p.id: p.kind
            for p in kitchen.db.scalars(
                select(Place).where(Place.household_id == kitchen.household_id)
            )
        }
        other: dict[int, list[str]] = defaultdict(list)
        for name in kitchen.db.scalars(
            select(FoodName).where(FoodName.household_id == kitchen.household_id)
        ):
            other[name.food_id].append(name.name)
        use_by_foods = {
            food.id
            for food in foods.values()
            if date_kind(food, [food.name, *other[food.id]], place_kinds.get(food.place_id or 0))
            == "use_by"
        }
        for lot in kitchen.db.scalars(
            select(StockLot).where(
                StockLot.household_id == kitchen.household_id, StockLot.amount_milli > 0
            )
        ):
            self.total[lot.food_id] += lot.amount_milli
            self.in_place[lot.food_id][lot.place_id] += lot.amount_milli
            # A packet whose date has passed is not a nudge to cook: the Pantry shows it.
            if (
                lot.use_by is not None
                and lot.food_id in use_by_foods
                and self.today <= lot.use_by <= soon
            ):
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


def _scaled(need: int, recipe: Recipe, servings: int | None) -> int:
    """What a recipe needs at `servings` instead of its own Serves (rounded up, so a short
    pantry is never called enough). With no Serves set, or no `servings`, nothing changes."""
    if servings is None or not recipe.serves:
        return need
    return -(-need * servings // recipe.serves)


def hints(
    lines: list[Line], recipes: dict[int, Recipe], stock: Stock, servings: int | None = None
) -> dict[int, tuple[StockHint | None, UseSoonHint | None, bool]]:
    """For every recipe: whether its ingredients are in stock, what it uses that is about to
    go off, and whether some line uses a recipe that can't be checked (so "all in stock" and
    "Can cook now" would claim too much). `servings` (the recipe page's minus and plus buttons)
    replaces each recipe's own Serves; the list leaves it out."""
    by_recipe: dict[int, list[Line]] = defaultdict(list)
    unchecked: set[int] = set()
    for line in lines:
        # A line with no amount is ignored, whatever it points at (cabledrawer 20 Oct).
        if line.amount_milli is None:
            continue
        by_recipe[line.recipe_id].append(line)
        if line.sub_recipe_id is not None and _ingredient_of(line, stock.foods, recipes) is None:
            unchecked.add(line.recipe_id)
    found: dict[int, tuple[StockHint | None, UseSoonHint | None, bool]] = {}
    for recipe_id in recipes:
        left = recipe_id in unchecked
        needs: dict[int, int] = {}
        for line in by_recipe.get(recipe_id, ()):
            food = _ingredient_of(line, stock.foods, recipes)
            if food is None:
                continue
            needs[food.id] = needs.get(food.id, 0) + (stock.need(line, food) or 0)
        needs = {
            food_id: _scaled(needed, recipes[recipe_id], servings)
            for food_id, needed in needs.items()
        }
        if not needs:
            found[recipe_id] = (None, None, left)
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
            StockHint(counted=len(needs), missing=missing, can_cook_now=missing == 0 and not left),
            soon,
            left,
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
    use_soon: bool = False,
    start: int,
    limit: int,
) -> RecipePage:
    """One page of the household's recipes, A to Z, that match the search, the tag, "Can cook
    now" and "uses something to use soon" (all together). The last keeps exactly the recipes
    whose row has a `use_soon` hint: it is the same answer, not a second rule."""
    recipes = live_recipes(kitchen)
    ordered = sorted(recipes.values(), key=lambda r: (fold(r.name), r.id))
    lines = _lines(kitchen, set(recipes))
    foods = _foods(kitchen)
    found = hints(lines, recipes, Stock(kitchen, foods))
    kept = ordered
    if can_cook_now:
        kept = [r for r in kept if (found[r.id][0] and found[r.id][0].can_cook_now)]  # type: ignore[union-attr]
    if use_soon:
        kept = [r for r in kept if found[r.id][1] is not None]
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
            stock_unchecked=found[recipe.id][2],
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


def stock_of(kitchen: Kitchen, recipe: Recipe, servings: int | None = None) -> RecipeStock:
    """Where each ingredient of one recipe is, for the recipe page: the same rules as the
    list's hints (this file's docstring), line by line. Only lines that count are answered
    (a heading, an unlinked line, or a recipe that isn't checked has no state). Several lines
    for one ingredient share its state. A line with no amount still never counts, but it gets
    a mark when there is one to give (0.5.1, cabledrawer's hand test: "salt to taste" showed no
    "Staple"): `staple`, or `in_stock` with its place when there is any stock, as when amounts
    can't be compared (Q22); otherwise it is left out, never "missing". Read-only, a fixed number of
    queries, limited to the signed-in household. The amounts needed are those for `servings`
    (cabledrawer, 19 Oct, Q22: enough for the recipe at the chosen servings); left out, the
    recipe's own Serves, and with no Serves set `servings` is ignored."""
    recipes = live_recipes(kitchen)
    lines = _lines(kitchen, set(recipes), only=recipe.id)
    foods = _foods(kitchen)
    stock = Stock(kitchen, foods)
    hint, _soon, unchecked = hints(lines, recipes, stock, servings)[recipe.id]

    counted = [
        (line, food)
        for line in lines
        if line.amount_milli is not None
        and (food := _ingredient_of(line, foods, recipes)) is not None
    ]
    needs: dict[int, int] = defaultdict(int)
    for line, food in counted:
        needs[food.id] += stock.need(line, food) or 0
    needs = defaultdict(int, {f: _scaled(n, recipe, servings) for f, n in needs.items()})

    places = {
        place.id: place
        for place in kitchen.db.scalars(
            select(Place).where(Place.household_id == kitchen.household_id)
        )
    }

    def where(food_id: int) -> str | None:
        """The place holding most of it (the first of equals, in the order of the places)."""
        held = [(place_id, amount) for place_id, amount in stock.in_place[food_id].items()]
        held = [(p, a) for p, a in held if p in places]
        if not held:
            return None
        best = min(held, key=lambda h: (-h[1], places[h[0]].position, h[0]))
        return places[best[0]].name

    answered: list[LineStock] = []
    for line in lines:
        food = _ingredient_of(line, foods, recipes)
        if food is None:
            continue
        state: Literal["in_stock", "staple", "short", "missing"]
        if food.staple:
            state = "staple"
        elif line.amount_milli is None and food.id not in needs:
            if stock.total.get(food.id, 0) <= 0:
                continue
            state = "in_stock"
        elif stock.has_enough(food, needs[food.id]):
            state = "in_stock"
        else:
            state = "short" if stock.total.get(food.id, 0) > 0 else "missing"
        answered.append(
            LineStock(
                line_id=line.id,
                food=Ref(id=food.id, name=food.name),
                state=state,
                place=where(food.id) if state == "in_stock" else None,
            )
        )
    return RecipeStock(
        lines=answered,
        counted=hint.counted if hint else 0,
        missing=hint.missing if hint else 0,
        stock_unchecked=unchecked,
    )
