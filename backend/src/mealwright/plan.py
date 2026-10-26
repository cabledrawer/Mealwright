"""Plan helpers the screens' writes will share (0.6)."""

from sqlalchemy import update
from sqlalchemy.orm import Session as DbSession

from mealwright.models import BatchCook, Meal


def delete_meal(db: DbSession, meal: Meal) -> None:
    """Delete a meal with its items. A batch cook that was cooked for it forgets the link
    first (the database refuses to delete a meal that one still points at, since a plain
    "set null" would also empty the household)."""
    db.execute(
        update(BatchCook)
        .where(BatchCook.household_id == meal.household_id, BatchCook.cook_meal_id == meal.id)
        .values(cook_meal_id=None)
    )
    db.delete(meal)
    db.flush()
