"""The plan's data and its read-only API (0.6 PR 2): default slots, the household's plan
settings, the plan for a date range, the range cap, the one-of rule on meal items, links that
cannot cross households, and what happens to meals when things are deleted."""

from collections.abc import Iterator
from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mealwright.auth import hash_password
from mealwright.household import add_default_places, add_default_slots
from mealwright.models import (
    BatchCook,
    Food,
    Household,
    Login,
    Meal,
    MealItem,
    MealSlot,
    Recipe,
    Tub,
)

API = "/api/v1"
DAY = date(2026, 11, 2)


def db_of(client: TestClient) -> Session:
    return client.app.state.sessionmaker()  # type: ignore[attr-defined, no-any-return]


def slot_ids(client: TestClient, household_id: int = 1) -> dict[str, int]:
    with db_of(client) as db:
        return {
            s.name: s.id
            for s in db.scalars(select(MealSlot).where(MealSlot.household_id == household_id))
        }


def add_recipe(db: Session, household_id: int, name: str = "Sambar") -> Recipe:
    recipe = Recipe(household_id=household_id, name=name, serves=4)
    db.add(recipe)
    db.flush()
    return recipe


def add_food(db: Session, household_id: int, name: str = "Banana") -> Food:
    food = Food(household_id=household_id, name=name, counted_as="count")
    db.add(food)
    db.flush()
    return food


def plan_one_day(client: TestClient) -> dict[str, int]:
    """Household 1: dinner on DAY with a recipe (2 servings), a tub and Banana."""
    slots = slot_ids(client)
    with db_of(client) as db:
        recipe = add_recipe(db, 1)
        food = add_food(db, 1)
        batch = BatchCook(
            household_id=1,
            recipe_id=recipe.id,
            recipe_name="Sambar",
            cooked_on=DAY,
            tub_count=2,
            pattern="dinners",
        )
        db.add(batch)
        db.flush()
        tub = Tub(household_id=1, batch_id=batch.id, use_by=date(2026, 11, 5))
        db.add(tub)
        meal = Meal(household_id=1, day=DAY, slot_id=slots["Dinner"])
        db.add(meal)
        db.flush()
        db.add_all(
            [
                MealItem(
                    household_id=1, meal_id=meal.id, position=0, recipe_id=recipe.id, servings=2
                ),
                MealItem(household_id=1, meal_id=meal.id, position=1, tub_id=tub.id),
                MealItem(household_id=1, meal_id=meal.id, position=2, food_id=food.id),
            ]
        )
        db.commit()
        return {
            "recipe": recipe.id,
            "food": food.id,
            "batch": batch.id,
            "tub": tub.id,
            "meal": meal.id,
        }


def test_a_new_household_has_the_default_slots(kitchen: TestClient) -> None:
    slots = kitchen.get(f"{API}/meal-slots").json()
    assert [(s["name"], s["position"], s["enabled"]) for s in slots] == [
        ("Breakfast", 0, True),
        ("Lunch", 1, True),
        ("Snack", 2, False),
        ("Dinner", 3, True),
    ]


def test_household_plan_settings_default(kitchen: TestClient) -> None:
    household = kitchen.get(f"{API}/household").json()
    assert household["tub_fridge_days"] == 3
    assert household["tub_freezer_months"] == 3
    assert household["plan_ahead_days"] == 7
    assert household["week_starts_on"] == 1


def test_the_plan_lists_meals_items_batches_and_tubs(kitchen: TestClient) -> None:
    ids = plan_one_day(kitchen)
    plan = kitchen.get(f"{API}/plan", params={"from": "2026-11-02", "to": "2026-11-08"}).json()
    assert plan["start"] == "2026-11-02"
    [meal] = plan["meals"]
    assert (meal["id"], meal["date"], meal["status"]) == (ids["meal"], "2026-11-02", "planned")
    kinds = [(i["kind"], i["servings"]) for i in meal["items"]]
    assert kinds == [("recipe", 2), ("tub", None), ("ingredient", None)]
    assert meal["items"][0]["recipe"] == {"id": ids["recipe"], "name": "Sambar", "removed": False}
    assert meal["items"][2]["ingredient"] == {"id": ids["food"], "name": "Banana"}
    assert [b["id"] for b in plan["batch_cooks"]] == [ids["batch"]]
    assert plan["batch_cooks"][0]["pattern"] == "dinners"
    [tub] = plan["tubs"]
    assert (tub["id"], tub["amount_quarters"], tub["use_by"]) == (ids["tub"], 4, "2026-11-05")


def test_the_plan_leaves_out_days_outside_the_range(kitchen: TestClient) -> None:
    plan_one_day(kitchen)
    plan = kitchen.get(f"{API}/plan", params={"from": "2026-11-03", "to": "2026-11-09"}).json()
    assert plan["meals"] == [] and plan["tubs"] == [] and plan["batch_cooks"] == []


def test_the_range_is_capped(kitchen: TestClient) -> None:
    ok = kitchen.get(f"{API}/plan", params={"from": "2026-11-01", "to": "2027-01-01"})
    assert ok.status_code == 200  # 62 days
    long = kitchen.get(f"{API}/plan", params={"from": "2026-11-01", "to": "2027-01-02"})
    assert long.status_code == 422 and long.json()["code"] == "range_too_long"
    backwards = kitchen.get(f"{API}/plan", params={"from": "2026-11-05", "to": "2026-11-01"})
    assert backwards.status_code == 422 and backwards.json()["code"] == "bad_range"
    assert kitchen.get(f"{API}/plan").status_code == 422


def test_the_plan_needs_signing_in(client: TestClient) -> None:
    assert (
        client.get(f"{API}/plan", params={"from": "2026-11-01", "to": "2026-11-02"}).status_code
        == 401
    )
    assert client.get(f"{API}/meal-slots").status_code == 401


@pytest.fixture
def neighbour(kitchen: TestClient) -> Iterator[TestClient]:
    with db_of(kitchen) as db:
        db.add(Household(id=2, name="Next door"))
        db.flush()
        add_default_places(db, 2)
        add_default_slots(db, 2)
        db.add(
            Login(
                household_id=2,
                username="neighbour",
                name="Neighbour",
                password_hash=hash_password("next door's own password"),
                role="admin",
            )
        )
        db.commit()
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        body = {"username": "neighbour", "password": "next door's own password"}
        assert other.post(f"{API}/session", json=body).status_code == 200
        yield other


def test_another_household_cannot_read_my_plan(kitchen: TestClient, neighbour: TestClient) -> None:
    plan_one_day(kitchen)
    plan = neighbour.get(f"{API}/plan", params={"from": "2026-11-02", "to": "2026-11-08"}).json()
    assert plan["meals"] == [] and plan["tubs"] == [] and plan["batch_cooks"] == []
    mine = {s["id"] for s in kitchen.get(f"{API}/meal-slots").json()}
    theirs = {s["id"] for s in neighbour.get(f"{API}/meal-slots").json()}
    assert mine and theirs and not mine & theirs


def test_the_plan_never_shows_a_name_from_another_household(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    """Even if a bad link got in (the database lets a recipe link across), its name stays out."""
    slots = slot_ids(kitchen, 2)
    with db_of(kitchen) as db:
        secret = add_recipe(db, 1, "Mine alone")
        meal = Meal(household_id=2, day=DAY, slot_id=slots["Dinner"])
        db.add(meal)
        db.flush()
        db.add(MealItem(household_id=2, meal_id=meal.id, position=0, recipe_id=secret.id))
        db.commit()
    text_ = neighbour.get(f"{API}/plan", params={"from": "2026-11-02", "to": "2026-11-02"}).text
    assert "Mine alone" not in text_


def test_a_meal_item_holds_exactly_one_of_recipe_tub_or_ingredient(kitchen: TestClient) -> None:
    ids = plan_one_day(kitchen)
    for fields in (
        {},
        {"recipe_id": ids["recipe"], "food_id": ids["food"]},
        {"recipe_id": ids["recipe"], "tub_id": ids["tub"]},
        {"servings": 2, "food_id": ids["food"]},  # servings belong to a recipe
        {"servings": 0, "recipe_id": ids["recipe"]},
    ):
        with db_of(kitchen) as db:
            db.add(MealItem(household_id=1, meal_id=ids["meal"], position=9, **fields))
            with pytest.raises(IntegrityError):
                db.commit()


def test_one_meal_per_date_and_slot_and_a_tub_in_one_meal(kitchen: TestClient) -> None:
    ids = plan_one_day(kitchen)
    slots = slot_ids(kitchen)
    with db_of(kitchen) as db:
        db.add(Meal(household_id=1, day=DAY, slot_id=slots["Dinner"]))
        with pytest.raises(IntegrityError):
            db.commit()
    with db_of(kitchen) as db:
        db.add(Meal(household_id=1, day=DAY, slot_id=slots["Lunch"], status="eaten"))
        with pytest.raises(IntegrityError):
            db.commit()
    with db_of(kitchen) as db:
        other = Meal(household_id=1, day=DAY, slot_id=slots["Lunch"])
        db.add(other)
        db.flush()
        db.add(MealItem(household_id=1, meal_id=other.id, position=0, tub_id=ids["tub"]))
        with pytest.raises(IntegrityError):
            db.commit()


def test_plan_links_cannot_cross_households(kitchen: TestClient, neighbour: TestClient) -> None:
    ids = plan_one_day(kitchen)
    theirs = slot_ids(kitchen, 2)
    mine = slot_ids(kitchen)
    cases = (
        Meal(household_id=2, day=DAY, slot_id=mine["Lunch"]),  # my slot
        MealItem(household_id=2, meal_id=ids["meal"], position=5, food_id=ids["food"]),  # my meal
        Tub(household_id=2, batch_id=ids["batch"], use_by=DAY),  # my batch
    )
    for row in cases:
        with db_of(kitchen) as db:
            db.add(row)
            with pytest.raises(IntegrityError):
                db.commit()
    with db_of(kitchen) as db:
        meal = Meal(household_id=2, day=DAY, slot_id=theirs["Lunch"])
        db.add(meal)
        db.flush()
        db.add(MealItem(household_id=2, meal_id=meal.id, position=0, tub_id=ids["tub"]))  # my tub
        with pytest.raises(IntegrityError):
            db.commit()


def test_hiding_a_slot_keeps_its_meals_and_a_slot_with_meals_cannot_be_deleted(
    kitchen: TestClient,
) -> None:
    plan_one_day(kitchen)
    dinner = slot_ids(kitchen)["Dinner"]
    with db_of(kitchen) as db:
        db.get(MealSlot, dinner).enabled = False  # type: ignore[union-attr]
        db.commit()
    plan = kitchen.get(f"{API}/plan", params={"from": "2026-11-02", "to": "2026-11-02"}).json()
    assert len(plan["meals"]) == 1
    with db_of(kitchen) as db:
        db.delete(db.get(MealSlot, dinner))
        with pytest.raises(IntegrityError):
            db.commit()


def test_deleting_for_good_what_a_meal_holds(kitchen: TestClient) -> None:
    """Proposed, for cabledrawer: a recipe, ingredient or tub that is deleted for good takes its
    item with it, and the meal stays. A batch cook outlives its recipe, by name."""
    ids = plan_one_day(kitchen)
    with db_of(kitchen) as db:
        db.execute(text("DELETE FROM recipe WHERE id = :i"), {"i": ids["recipe"]})
        db.execute(text("DELETE FROM food WHERE id = :i"), {"i": ids["food"]})
        db.commit()
        assert db.get(Meal, ids["meal"]) is not None
        batch = db.get(BatchCook, ids["batch"])
        assert batch is not None and batch.recipe_id is None and batch.recipe_name == "Sambar"
        items = list(db.scalars(select(MealItem)))
        assert [i.tub_id for i in items] == [ids["tub"]]
        db.execute(text("DELETE FROM batch_cook WHERE id = :i"), {"i": ids["batch"]})
        db.commit()
        assert list(db.scalars(select(Tub))) == [] and list(db.scalars(select(MealItem))) == []


def test_removing_a_household_removes_its_plan(kitchen: TestClient, neighbour: TestClient) -> None:
    plan_one_day(kitchen)
    with db_of(kitchen) as db:
        db.execute(text("DELETE FROM household WHERE id = 1"))
        db.commit()
        for table in ("meal_slot", "meal", "meal_item", "batch_cook", "tub"):
            query = f"SELECT count(*) FROM {table} WHERE household_id = 1"  # noqa: S608
            count = db.execute(text(query)).scalar_one()
            assert count == 0
