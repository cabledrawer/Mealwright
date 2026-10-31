"""What was cooked (0.7 K1): the cooked record of a meal item or a batch cook, read-only. "Cooked
it" writes it (0.7 K2 and K3)."""

from datetime import datetime

from fastapi import APIRouter, status
from pydantic import BaseModel

from mealwright import batches, cooked, plan
from mealwright.api.v1.context import Here
from mealwright.api.v1.schemas import Who
from mealwright.auth import SameOrigin
from mealwright.errors import Problem, StoredInt
from mealwright.history import as_utc
from mealwright.models import CookedRecord

router = APIRouter(tags=["plan"], dependencies=[SameOrigin])


class CookedOut(BaseModel):
    """The record of what was cooked. `snapshot` is the recipe as it was then (its amounts
    are the recipe's own, for `snapshot.servings`); `portions` is how many were cooked;
    `change_id` is the change in Recent changes with its stock changes (null once the
    tidy-up has deleted that change). `recipe_id` is null once the recipe is deleted for
    good; the snapshot keeps its name."""

    id: int
    meal_item_id: int | None
    batch_id: int | None
    recipe_id: int | None
    portions: int
    snapshot: cooked.Snapshot
    change_id: int | None
    cooked_at: datetime
    cooked_by: Who


def _not_cooked() -> Problem:
    # Proposed, for cabledrawer (an API message, not shown on a screen).
    return Problem(status.HTTP_404_NOT_FOUND, "not_cooked", "It hasn’t been cooked yet.")


def cooked_out(record: CookedRecord) -> CookedOut:
    return CookedOut(
        id=record.id,
        meal_item_id=record.meal_item_id,
        batch_id=record.batch_id,
        recipe_id=record.recipe_id,
        portions=record.portions,
        snapshot=cooked.read(record),
        change_id=record.change_id,
        cooked_at=as_utc(record.cooked_at),
        cooked_by=Who(login_id=record.cooked_by_login_id, name=record.cooked_by_name),
    )


@router.get("/plan/items/{plan_item_id}/cooked")
def get_item_cooked(plan_item_id: StoredInt, kitchen: Here) -> CookedOut:
    """What was cooked for this meal item. 404 when it hasn't been cooked."""
    item = plan.find_item(kitchen, plan_item_id)
    record = cooked.for_meal_item(kitchen.db, kitchen.household_id, item.id)
    if record is None:
        raise _not_cooked()
    return cooked_out(record)


@router.get("/plan/batches/{plan_batch_id}/cooked")
def get_batch_cooked(plan_batch_id: StoredInt, kitchen: Here) -> CookedOut:
    """What was cooked for this batch cook. 404 when it hasn't been cooked."""
    batch = batches.find_batch(kitchen, plan_batch_id)
    record = cooked.for_batch(kitchen.db, kitchen.household_id, batch.id)
    if record is None:
        raise _not_cooked()
    return cooked_out(record)
