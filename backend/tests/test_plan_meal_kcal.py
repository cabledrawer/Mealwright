"""F233 (cabledrawer 12 Nov): after a Batch cook session's Cooked it, the cook-day meal's kcal
counts
only what is eaten at that meal (a tub eaten there), not the recipes the session cooked."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_batch_cooked import session_of
from test_plan import db_of
from test_plan_writes import D1, D2, view

from mealwright.models import BatchCook, MealItem, Recipe, Tub

API = "/api/v1"


def set_kcal(kitchen: TestClient) -> None:
    with db_of(kitchen) as db:
        for recipe in db.scalars(select(Recipe)):
            recipe.kcal_milli = 500_000 if recipe.name == "Sambar" else 700_000
        db.commit()


def add_tub_to(kitchen: TestClient, meal_id: int, kcal: int) -> None:
    """A tub of an earlier batch of Khichdi, eaten at that meal."""
    with db_of(kitchen) as db:
        khichdi = Recipe(household_id=1, name="Khichdi", kcal_milli=kcal * 1000)
        db.add(khichdi)
        db.flush()
        batch = BatchCook(
            household_id=1,
            recipe_id=khichdi.id,
            recipe_name="Khichdi",
            cooked_on=D1,
            tub_count=1,
        )
        db.add(batch)
        db.flush()
        tub = Tub(household_id=1, batch_id=batch.id, use_by=D2)
        db.add(tub)
        db.flush()
        db.add(MealItem(household_id=1, meal_id=meal_id, position=9, tub_id=tub.id))
        db.commit()


def cook_meal(kitchen: TestClient) -> dict[str, object]:
    [meal] = [m for m in view(kitchen)["meals"] if m["date"] == D1.isoformat()]
    return dict(meal)


def test_after_cooked_it_the_meal_counts_the_tub_eaten_not_the_recipes_the_session_cooked(
    kitchen: TestClient,
) -> None:
    session, _ = session_of(kitchen)
    set_kcal(kitchen)
    meal = cook_meal(kitchen)
    add_tub_to(kitchen, int(meal["id"]), 400)  # type: ignore[call-overload]
    assert cook_meal(kitchen)["kcal"] == 500 + 700 + 400  # still to cook: everything in it
    ok(kitchen.post(f"{API}/batch-cook/sessions/{session}/cook", json={}), 201)
    assert cook_meal(kitchen)["kcal"] == 400


def test_a_meal_of_only_the_sessions_recipes_still_counts_them(kitchen: TestClient) -> None:
    session, _ = session_of(kitchen)
    set_kcal(kitchen)
    ok(kitchen.post(f"{API}/batch-cook/sessions/{session}/cook", json={}), 201)
    assert cook_meal(kitchen)["kcal"] == 500 + 700


def test_a_cook_once_meal_outside_a_session_counts_as_before(kitchen: TestClient) -> None:
    from test_cook_ahead import plan_ahead

    _dal, meal, item, _day = plan_ahead(kitchen, 0)
    with db_of(kitchen) as db:
        recipe = db.scalar(select(Recipe).where(Recipe.name == "Zorba khichdi"))
        assert recipe is not None
        recipe.kcal_milli = 600_000
        db.commit()
    batch = ok(
        kitchen.post(f"{API}/plan/items/{item}/batch", json={"tub_count": 1, "pattern": "pick"}),
        201,
    )["batch_id"]
    add_tub_to(kitchen, meal, 400)
    ok(kitchen.post(f"{API}/plan/batches/{batch}/cook", json={}), 201)
    [shown] = [m for m in view(kitchen, start=_day)["meals"] if m["id"] == meal]
    assert shown["kcal"] == 600 + 400
