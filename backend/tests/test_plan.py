"""The plan's data and its read-only API (0.6 PR 2): default slots, the household's plan
settings, the plan for a date range, the range cap, the one-of rule on meal items, links that
cannot cross households, and what happens to meals when things are deleted."""

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from mealwright.models import (
    BatchCook,
    Food,
    Household,
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
    slots = kitchen.get(f"{API}/meal-slots").json()["meal_slots"]
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


def test_a_recipe_without_serves_sends_null(kitchen: TestClient) -> None:
    ids = plan_one_day(kitchen)
    with db_of(kitchen) as session:
        session.get(Recipe, ids["recipe"]).serves = None
        session.commit()
    plan = kitchen.get(f"{API}/plan", params={"from": "2026-11-02", "to": "2026-11-08"}).json()
    assert plan["meals"][0]["items"][0]["recipe"]["serves"] is None


def test_the_plan_lists_meals_items_batches_and_tubs(kitchen: TestClient) -> None:
    ids = plan_one_day(kitchen)
    plan = kitchen.get(f"{API}/plan", params={"from": "2026-11-02", "to": "2026-11-08"}).json()
    assert plan["start"] == "2026-11-02"
    [meal] = plan["meals"]
    assert (meal["id"], meal["date"], meal["status"]) == (ids["meal"], "2026-11-02", "planned")
    kinds = [(i["kind"], i["servings"]) for i in meal["items"]]
    assert kinds == [("recipe", 2), ("tub", None), ("ingredient", None)]
    assert meal["items"][0]["recipe"] == {
        "id": ids["recipe"],
        "name": "Sambar",
        "removed": False,
        # What a meal card shows (PR 3): none of it is known for this bare recipe.
        "photo_url": None,
        "time_minutes": None,
        "kcal": None,
        # The recipe's own servings (F116): a meal planned without Serves shows these.
        "serves": 4,
        # R3: none of its lines is Optional.
        "optional_count": 0,
        "methods": [],
        "wait": None,
    }
    assert meal["items"][0]["optional_skipped"] == []
    assert meal["items"][2]["ingredient"] == {
        "id": ids["food"],
        "name": "Banana",
        "removed": False,
    }
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


def test_another_household_cannot_read_my_plan(kitchen: TestClient, neighbour: TestClient) -> None:
    plan_one_day(kitchen)
    plan = neighbour.get(f"{API}/plan", params={"from": "2026-11-02", "to": "2026-11-08"}).json()
    assert plan["meals"] == [] and plan["tubs"] == [] and plan["batch_cooks"] == []
    mine = {s["id"] for s in kitchen.get(f"{API}/meal-slots").json()["meal_slots"]}
    theirs = {s["id"] for s in neighbour.get(f"{API}/meal-slots").json()["meal_slots"]}
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
        {"kind": "tub", "name": "Sambar"},  # only a recipe or ingredient keeps a name
        {"kind": "recipe", "food_id": ids["food"]},
        {"kind": "salad", "name": "Sambar"},
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


def test_a_kept_name_never_comes_from_or_shows_to_another_household(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    """cabledrawer 26 Oct: deleted names must never show to another household (PR 71 round 3)."""
    from datetime import timedelta

    from mealwright.history import purge_removed
    from mealwright.models import utcnow
    from mealwright.recipes import purge_removed_recipes

    ids = plan_one_day(kitchen)
    theirs = slot_ids(kitchen, 2)
    with db_of(kitchen) as db:
        # A bad link from next door's meal to my recipe and my ingredient: the database allows
        # the single-column keys, but neither of my names is copied in.
        meal = Meal(household_id=2, day=DAY, slot_id=theirs["Lunch"])
        db.add(meal)
        db.flush()
        bad = [
            MealItem(household_id=2, meal_id=meal.id, position=0, recipe_id=ids["recipe"]),
            MealItem(household_id=2, meal_id=meal.id, position=1, food_id=ids["food"]),
        ]
        db.add_all(bad)
        db.commit()
        assert [i.name for i in bad] == [None, None]
        old = utcnow() - timedelta(days=30)
        db.get(Recipe, ids["recipe"]).removed_at = old  # type: ignore[union-attr]
        db.get(Food, ids["food"]).removed_at = old  # type: ignore[union-attr]
        db.commit()
        household = db.get(Household, 1)
        assert purge_removed_recipes(db, household) == 1  # type: ignore[arg-type]
        assert purge_removed(db, household, utcnow()) >= 1  # type: ignore[arg-type]
        db.commit()
        # The bad links went, rather than carry my names next door.
        assert db.scalars(select(MealItem).where(MealItem.household_id == 2)).all() == []
    mine = kitchen.get(f"{API}/plan", params={"from": DAY.isoformat(), "to": DAY.isoformat()}).text
    assert "Sambar" in mine and "Banana" in mine
    next_door = neighbour.get(
        f"{API}/plan", params={"from": DAY.isoformat(), "to": DAY.isoformat()}
    ).text
    assert "Sambar" not in next_door and "Banana" not in next_door


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
    """cabledrawer 26 Oct: a recipe or ingredient deleted for good leaves its item with its name,
    as a batch cook keeps its recipe's name; a tub deleted for good takes its item."""
    ids = plan_one_day(kitchen)
    with db_of(kitchen) as db:
        db.execute(text("DELETE FROM recipe WHERE id = :i"), {"i": ids["recipe"]})
        db.execute(text("DELETE FROM food WHERE id = :i"), {"i": ids["food"]})
        db.commit()
        assert db.get(Meal, ids["meal"]) is not None
        batch = db.get(BatchCook, ids["batch"])
        assert batch is not None and batch.recipe_id is None and batch.recipe_name == "Sambar"
        items = list(db.scalars(select(MealItem).order_by(MealItem.position)))
        kept = [(i.kind, i.recipe_id, i.tub_id, i.food_id, i.name, i.servings) for i in items]
        assert kept == [
            ("recipe", None, None, None, "Sambar", 2),
            ("tub", None, ids["tub"], None, None, None),
            ("ingredient", None, None, None, "Banana", None),
        ]
    meal = kitchen.get(f"{API}/plan", params={"from": str(DAY), "to": str(DAY)}).json()["meals"][0]
    assert [(i["kind"], i["recipe"], i["ingredient"], i["kept_name"]) for i in meal["items"]] == [
        ("recipe", None, None, "Sambar"),
        ("tub", None, None, None),
        ("ingredient", None, None, "Banana"),
    ]
    with db_of(kitchen) as db:
        db.execute(text("DELETE FROM batch_cook WHERE id = :i"), {"i": ids["batch"]})
        db.commit()
        assert list(db.scalars(select(Tub))) == []
        assert [i.name for i in db.scalars(select(MealItem))] == ["Sambar", "Banana"]


def test_removing_a_household_removes_its_plan(kitchen: TestClient, neighbour: TestClient) -> None:
    ids = plan_one_day(kitchen)
    with db_of(kitchen) as db:
        # The batch points at its cook-day meal (no ON DELETE): removing the household still works.
        db.get(BatchCook, ids["batch"]).cook_meal_id = ids["meal"]
        db.commit()
        db.execute(text("DELETE FROM household WHERE id = 1"))
        db.commit()
        for table in ("meal_slot", "meal", "meal_item", "batch_cook", "tub"):
            query = f"SELECT count(*) FROM {table} WHERE household_id = 1"  # noqa: S608
            count = db.execute(text(query)).scalar_one()
            assert count == 0


# --- Round 1 fixes ---------------------------------------------------------------------------


def test_the_plan_shows_a_batch_cooked_for_a_meal_or_on_a_day_in_range(
    kitchen: TestClient,
) -> None:
    ids = plan_one_day(kitchen)
    slots = slot_ids(kitchen)
    with db_of(kitchen) as db:
        cook = Meal(household_id=1, day=date(2026, 11, 20), slot_id=slots["Dinner"])
        db.add(cook)
        db.flush()
        # Cooked for a meal in range, on a day outside it, with no tub in any meal.
        linked = BatchCook(
            household_id=1,
            recipe_name="Rasam",
            cooked_on=date(2026, 12, 1),
            tub_count=1,
            cook_meal_id=ids["meal"],
        )
        # Cooked on a day in range, linked to nothing.
        on_day = BatchCook(
            household_id=1, recipe_name="Kootu", cooked_on=date(2026, 11, 4), tub_count=1
        )
        outside = BatchCook(
            household_id=1,
            recipe_name="Elsewhere",
            cooked_on=date(2026, 12, 2),
            tub_count=1,
            cook_meal_id=cook.id,
        )
        db.add_all([linked, on_day, outside])
        db.flush()
        db.add(Tub(household_id=1, batch_id=on_day.id, use_by=DAY))
        db.commit()
        linked_id, on_day_id = linked.id, on_day.id
    plan = kitchen.get(f"{API}/plan", params={"from": "2026-11-02", "to": "2026-11-08"}).json()
    by_id = {b["id"]: b for b in plan["batch_cooks"]}
    assert set(by_id) == {ids["batch"], linked_id, on_day_id}
    assert by_id[linked_id]["cook_meal_id"] == ids["meal"]
    assert by_id[on_day_id]["cook_meal_id"] is None
    assert {t["batch_id"] for t in plan["tubs"]} == {ids["batch"], on_day_id}


def test_a_batch_can_only_point_at_a_meal_of_its_own_household(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    ids = plan_one_day(kitchen)
    with db_of(kitchen) as db:
        db.add(
            BatchCook(
                household_id=2,
                recipe_name="Theirs",
                cooked_on=DAY,
                tub_count=1,
                cook_meal_id=ids["meal"],
            )
        )
        with pytest.raises(IntegrityError):
            db.commit()


def test_deleting_a_meal_clears_the_batch_link_and_the_database_refuses_otherwise(
    kitchen: TestClient,
) -> None:
    from mealwright.plan import delete_meal

    ids = plan_one_day(kitchen)
    with db_of(kitchen) as db:
        db.get(BatchCook, ids["batch"]).cook_meal_id = ids["meal"]  # type: ignore[union-attr]
        db.commit()
    with db_of(kitchen) as db, pytest.raises(IntegrityError):
        db.execute(text("DELETE FROM meal WHERE id = :i"), {"i": ids["meal"]})
    with db_of(kitchen) as db:
        delete_meal(db, db.get(Meal, ids["meal"]))  # type: ignore[arg-type]
        db.commit()
        batch = db.get(BatchCook, ids["batch"])
        assert batch is not None and batch.cook_meal_id is None and batch.household_id == 1
        assert db.get(Meal, ids["meal"]) is None
        assert list(db.scalars(select(MealItem))) == []


def test_the_plan_hides_links_that_reach_into_another_household(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    """A planted row in household 2 pointing at household 1's recipe, place and person: the
    plan never shows those ids to household 2."""
    slots = slot_ids(kitchen, 2)
    with db_of(kitchen) as db:
        recipe = add_recipe(db, 1, "Mine alone")
        mine_place = (
            db.execute(text("SELECT id FROM place WHERE household_id = 1")).scalars().first()
        )
        mine_member = (
            db.execute(text("SELECT id FROM member WHERE household_id = 1")).scalars().first()
        )
        batch = BatchCook(
            household_id=2, recipe_id=recipe.id, recipe_name="Theirs", cooked_on=DAY, tub_count=1
        )
        db.add(batch)
        db.flush()
        tub = Tub(
            household_id=2,
            batch_id=batch.id,
            use_by=DAY,
            place_id=mine_place,
            member_id=mine_member,
        )
        meal = Meal(household_id=2, day=DAY, slot_id=slots["Dinner"])
        db.add_all([tub, meal])
        db.flush()
        db.add(MealItem(household_id=2, meal_id=meal.id, position=0, tub_id=tub.id))
        db.commit()
    plan = neighbour.get(f"{API}/plan", params={"from": "2026-11-02", "to": "2026-11-02"}).json()
    assert plan["batch_cooks"][0]["recipe_id"] is None
    assert plan["tubs"][0]["place_id"] is None
    assert plan["tubs"][0]["member_id"] is None


def test_an_ingredient_item_says_when_it_is_removed(kitchen: TestClient) -> None:
    ids = plan_one_day(kitchen)
    from mealwright.models import utcnow

    with db_of(kitchen) as db:
        db.get(Food, ids["food"]).removed_at = utcnow()  # type: ignore[union-attr]
        db.commit()
    plan = kitchen.get(f"{API}/plan", params={"from": "2026-11-02", "to": "2026-11-02"}).json()
    assert plan["meals"][0]["items"][2]["ingredient"]["removed"] is True


def _food_of_item(client: TestClient, item_id: int) -> int | None:
    with db_of(client) as db:
        return db.get(MealItem, item_id).food_id  # type: ignore[union-attr, no-any-return]


def test_merging_ingredients_moves_planned_meals_and_undo_and_split_move_them_back(
    kitchen: TestClient,
) -> None:
    ids = plan_one_day(kitchen)  # Banana is in the meal
    with db_of(kitchen) as db:
        item = db.scalars(select(MealItem).where(MealItem.food_id == ids["food"])).one()
        item_id = item.id
        plantain = add_food(db, 1, "Plantain")
        db.commit()
        plantain_id = plantain.id
    merged = kitchen.post(f"{API}/foods/{ids['food']}/merge", json={"into_id": plantain_id}).json()
    assert _food_of_item(kitchen, item_id) == plantain_id
    undo = kitchen.post(f"{API}/changes/{merged['change']['id']}/undo").json()
    assert undo["result"] == "done"
    assert _food_of_item(kitchen, item_id) == ids["food"]
    # And "make it its own ingredient again".
    merged = kitchen.post(f"{API}/foods/{ids['food']}/merge", json={"into_id": plantain_id}).json()
    assert _food_of_item(kitchen, item_id) == plantain_id
    name_id = merged["food"]["other_names"][0]["id"]
    split = kitchen.post(f"{API}/foods/{plantain_id}/split", json={"other_name_id": name_id})
    assert split.status_code == 201
    assert _food_of_item(kitchen, item_id) == ids["food"]


def test_the_real_purge_jobs_keep_planned_items_by_name(kitchen: TestClient) -> None:
    from datetime import timedelta

    from mealwright.history import purge_removed
    from mealwright.models import utcnow
    from mealwright.recipes import purge_removed_recipes

    ids = plan_one_day(kitchen)
    old = utcnow() - timedelta(days=30)
    with db_of(kitchen) as db:
        # Renamed after it was planned: the meal keeps the name it had when it went.
        db.get(Recipe, ids["recipe"]).name = "Drumstick sambar"  # type: ignore[union-attr]
        db.get(Recipe, ids["recipe"]).removed_at = old  # type: ignore[union-attr]
        db.get(Food, ids["food"]).name = "Bananas"  # type: ignore[union-attr]
        db.get(Food, ids["food"]).removed_at = old  # type: ignore[union-attr]
        db.commit()
        household = db.get(Household, 1)
        assert purge_removed_recipes(db, household) == 1  # type: ignore[arg-type]
        assert purge_removed(db, household, utcnow()) >= 1  # type: ignore[arg-type]
        db.commit()
        assert db.get(Meal, ids["meal"]) is not None
        items = db.scalars(select(MealItem).order_by(MealItem.position))
        assert [(i.recipe_id, i.food_id, i.name) for i in items] == [
            (None, None, "Drumstick sambar"),
            (None, None, None),
            (None, None, "Bananas"),
        ]
        batch = db.get(BatchCook, ids["batch"])
        assert batch is not None and batch.recipe_id is None and batch.recipe_name == "Sambar"
