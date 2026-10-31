"""The cooked record (0.7; spec section 6, "Plan and batch cooks", cabledrawer 17 Oct: "Cooked meals
keep a record of what was actually made (recipe version, amounts, deductions), so history and
pantry changes stay correct"; data model: "a cooked record per meal or batch (a snapshot of the
recipe as cooked plus its stock changes)").

One record per meal item, or per batch cook. "Cooked it" writes it (0.7 K2 and K3) with
`snapshot()`; this module also reads it. The snapshot is a copy, so editing the recipe later, or
deleting it for good, never changes what the record says was cooked.
"""

from typing import Any, Literal

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from mealwright.models import CookedRecord, Food, FoodSize, Recipe, RecipeLine, RecipeStep

_SIZE_UNIT: dict[str, Literal["g", "ml"]] = {"weight": "g", "volume": "ml"}


class SnapshotLine(BaseModel):
    kind: Literal["ingredient", "heading"]
    words: str
    amount_milli: int | None  # the recipe's own amount, for its `servings` (1½ is 1500)
    unit: str | None  # null: a count, or a number of the size below
    # One of the ingredient's own sizes ("1 packet"), as it was: its name, plural and amount
    # (in g for an ingredient weighed, ml for one measured by volume, null unit for a count).
    size_id: int | None = None
    size_name: str | None = None
    size_plural: str | None = None
    size_amount_milli: int | None = None
    size_unit: Literal["g", "ml"] | None = None
    food_id: int | None
    food_name: str | None
    recipe_id: int | None  # another recipe used as an ingredient
    recipe_name: str | None
    note: str | None


class SnapshotStep(BaseModel):
    kind: Literal["step", "heading"]
    text: str


class Snapshot(BaseModel):
    """The recipe as it was when it was cooked. Amounts are the recipe's own, for `servings`;
    the record's `portions` says how many were cooked."""

    name: str
    version: int
    servings: int | None
    lines: list[SnapshotLine]
    steps: list[SnapshotStep]


def snapshot(db: DbSession, recipe: Recipe) -> Snapshot:
    """A copy of the recipe as it is now, with the names of what its lines link to."""
    rows = list(
        db.scalars(
            select(RecipeLine)
            .where(RecipeLine.recipe_id == recipe.id)
            .order_by(RecipeLine.position, RecipeLine.id)
        )
    )
    food_ids = {row.food_id for row in rows if row.food_id}
    foods = {food.id: food for food in db.scalars(select(Food).where(Food.id.in_(food_ids)))}
    size_ids = {row.size_id for row in rows if row.size_id}
    sizes = {s.id: s for s in db.scalars(select(FoodSize).where(FoodSize.id.in_(size_ids)))}
    used_ids = {row.sub_recipe_id for row in rows if row.sub_recipe_id}
    used = {
        other.id: other.name for other in db.scalars(select(Recipe).where(Recipe.id.in_(used_ids)))
    }
    steps = db.scalars(
        select(RecipeStep)
        .where(RecipeStep.recipe_id == recipe.id)
        .order_by(RecipeStep.position, RecipeStep.id)
    )
    return Snapshot(
        name=recipe.name,
        version=recipe.version,
        servings=recipe.serves,
        lines=[
            SnapshotLine(
                kind="heading" if row.kind == "heading" else "ingredient",
                words=row.words,
                amount_milli=row.amount_milli,
                unit=row.unit,
                food_id=row.food_id,
                food_name=foods[row.food_id].name if row.food_id in foods else None,
                recipe_id=row.sub_recipe_id,
                recipe_name=used.get(row.sub_recipe_id) if row.sub_recipe_id else None,
                note=row.note,
                **_size(sizes.get(row.size_id) if row.size_id else None, foods),
            )
            for row in rows
        ],
        steps=[
            SnapshotStep(kind="heading" if step.kind == "heading" else "step", text=step.text)
            for step in steps
        ],
    )


def _size(size: FoodSize | None, foods: dict[int, Food]) -> dict[str, Any]:
    if size is None:
        return {}
    food = foods.get(size.food_id)
    return {
        "size_id": size.id,
        "size_name": size.name,
        "size_plural": size.plural,
        "size_amount_milli": size.amount_milli,
        "size_unit": _SIZE_UNIT.get(food.counted_as) if food else None,
    }


def read(record: CookedRecord) -> Snapshot:
    return Snapshot.model_validate(record.snapshot)


def stored(value: Snapshot) -> dict[str, Any]:
    return value.model_dump(mode="json")


def for_meal_item(db: DbSession, household_id: int, item_id: int) -> CookedRecord | None:
    return db.scalar(
        select(CookedRecord).where(
            CookedRecord.household_id == household_id, CookedRecord.meal_item_id == item_id
        )
    )


def for_batch(db: DbSession, household_id: int, batch_id: int) -> CookedRecord | None:
    return db.scalar(
        select(CookedRecord).where(
            CookedRecord.household_id == household_id, CookedRecord.batch_id == batch_id
        )
    )
