"""The cooked record (0.7 K1; spec section 6, "Plan and batch cooks", cabledrawer 17 Oct: "Cooked meals
keep a record of what was actually made ... so history and pantry changes stay correct"). "Cooked
it" (K2, K3) writes it; here it is written the way they will, with `cooked.snapshot`."""

from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError
from sync_kit import db, ok
from test_plan import slot_ids
from test_recipes import food, make, save

from mealwright import cooked
from mealwright.models import BatchCook, Change, CookedRecord, Household, Recipe, utcnow
from mealwright.recipes import purge_removed_recipes

API = "/api/v1"
DAY = date.today() + timedelta(days=2)


def _planned(client: TestClient) -> tuple[dict[str, Any], int]:
    """Sambar (serves 4) with a linked line, a sub-recipe, a heading and steps, planned for
    dinner; returns the recipe and the meal item's id."""
    dal = food(client, "Toor dal")
    podi = make(client, "Sambar podi")
    recipe = make(
        client,
        "Sambar",
        lines=[
            {"words": "thuvaram paruppu", "amount": 200, "unit": "g", "food_id": dal["id"]},
            {"kind": "heading", "words": "To finish"},
            {"words": "", "amount": 2, "unit": "tbsp", "recipe_id": podi["id"], "note": "heaped"},
        ],
        steps=[{"kind": "heading", "text": "The dal"}, {"text": "Boil the dal."}],
    )
    slot = slot_ids(client)["Dinner"]
    body = {"date": DAY.isoformat(), "slot_id": slot, "recipe_id": recipe["id"], "servings": 2}
    planned = ok(client.post(f"{API}/plan/items", json=body), 201)
    return recipe, int(planned["item_id"])


def _cook(client: TestClient, recipe_id: int, portions: int = 2, **link: int | None) -> int:
    with db(client) as session:
        recipe = session.get(Recipe, recipe_id)
        assert recipe is not None
        change = Change(household_id=1, kind="cooked", login_name="Tess", summary="Cooked it")
        session.add(change)
        session.flush()
        record = CookedRecord(
            household_id=1,
            recipe_id=recipe.id,
            portions=portions,
            snapshot=cooked.stored(cooked.snapshot(session, recipe)),
            change_id=change.id,
            cooked_by_login_id=1,
            cooked_by_name="Tess",
            **link,
        )
        session.add(record)
        session.commit()
        return record.id


SNAPSHOT: dict[str, Any] = {
    "name": "Sambar",
    "version": 1,
    "servings": 4,
    "lines": [
        {
            "kind": "ingredient",
            "words": "thuvaram paruppu",
            "amount_milli": 200_000,
            "unit": "g",
            "food_name": "Toor dal",
            "recipe_id": None,
            "recipe_name": None,
            "note": None,
        },
        {
            "kind": "heading",
            "words": "To finish",
            "amount_milli": None,
            "unit": None,
            "food_id": None,
            "food_name": None,
            "recipe_id": None,
            "recipe_name": None,
            "note": None,
        },
        {
            "kind": "ingredient",
            "words": "Sambar podi",
            "amount_milli": 2000,
            "unit": "tbsp",
            "food_id": None,
            "food_name": None,
            "recipe_name": "Sambar podi",
            "note": "heaped",
        },
    ],
    "steps": [
        {"kind": "heading", "text": "The dal", "optional": False},
        {"kind": "step", "text": "Boil the dal.", "optional": False},
    ],
}


def _same(found: dict[str, Any]) -> None:
    """The snapshot as it was cooked (ids that vary per run left out of the comparison)."""
    for line, want in zip(found["lines"], SNAPSHOT["lines"], strict=True):
        assert {k: line[k] for k in want} == want
    assert {k: found[k] for k in ("name", "version", "servings", "steps")} == {
        k: SNAPSHOT[k] for k in ("name", "version", "servings", "steps")
    }


def test_a_meal_items_record_is_read_back(kitchen: TestClient) -> None:
    recipe, item_id = _planned(kitchen)
    url = f"{API}/plan/items/{item_id}/cooked"
    answer = kitchen.get(url)
    assert answer.status_code == 404 and answer.json()["code"] == "not_cooked"
    record_id = _cook(kitchen, recipe["id"], meal_item_id=item_id)
    found = ok(kitchen.get(url))
    assert found["id"] == record_id
    assert (found["meal_item_id"], found["batch_id"]) == (item_id, None)
    assert (found["recipe_id"], found["portions"]) == (recipe["id"], 2)
    assert found["cooked_by"] == {"login_id": 1, "name": "Tess", "member_id": None}
    assert found["change_id"] is not None
    _same(found["snapshot"])
    assert found["snapshot"]["lines"][0]["food_id"] == recipe["lines"][0]["food"]["id"]
    assert found["snapshot"]["lines"][2]["recipe_id"] == recipe["lines"][2]["recipe"]["id"]


def test_editing_the_recipe_later_leaves_the_record_as_it_was(kitchen: TestClient) -> None:
    recipe, item_id = _planned(kitchen)
    _cook(kitchen, recipe["id"], meal_item_id=item_id)
    edited = ok(
        save(
            kitchen,
            recipe,
            name="Sambar (less dal)",
            serves=6,
            lines=[{"words": "toor dal", "amount": 100, "unit": "g"}],
            steps=[{"text": "Boil it all."}],
        )
    )
    assert edited["version"] == 2
    _same(ok(kitchen.get(f"{API}/plan/items/{item_id}/cooked"))["snapshot"])


def test_the_record_outlives_the_recipe_and_its_change(kitchen: TestClient) -> None:
    recipe, item_id = _planned(kitchen)
    _cook(kitchen, recipe["id"], meal_item_id=item_id)
    ok(kitchen.delete(f"{API}/recipes/{recipe['id']}"))
    with db(kitchen) as session:
        household = session.get(Household, 1)
        assert household is not None
        assert purge_removed_recipes(session, household, utcnow() + timedelta(days=30)) == 1
        record = session.query(CookedRecord).one()
        assert record.change_id is not None
        session.delete(session.get(Change, record.change_id))
        session.commit()
    found = ok(kitchen.get(f"{API}/plan/items/{item_id}/cooked"))
    assert (found["recipe_id"], found["change_id"]) == (None, None)
    _same(found["snapshot"])


def test_a_batch_cooks_record_is_read_back(kitchen: TestClient) -> None:
    recipe, item_id = _planned(kitchen)
    made = ok(
        kitchen.post(
            f"{API}/plan/items/{item_id}/batch", json={"tub_count": 4, "pattern": "lunches"}
        ),
        201,
    )
    batch_id = made["batch_id"]
    url = f"{API}/plan/batches/{batch_id}/cooked"
    assert kitchen.get(url).json()["code"] == "not_cooked"
    _cook(kitchen, recipe["id"], portions=8, batch_id=batch_id)
    found = ok(kitchen.get(url))
    assert (found["batch_id"], found["meal_item_id"], found["portions"]) == (batch_id, None, 8)
    _same(found["snapshot"])


def test_another_household_cannot_read_a_record(kitchen: TestClient, neighbour: TestClient) -> None:
    recipe, item_id = _planned(kitchen)
    _cook(kitchen, recipe["id"], meal_item_id=item_id)
    answer = neighbour.get(f"{API}/plan/items/{item_id}/cooked")
    assert answer.status_code == 404 and answer.json()["code"] == "not_found"


def test_the_database_refuses_a_record_in_another_household_or_for_two_things(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    _recipe, item_id = _planned(kitchen)
    with db(kitchen) as session:
        batch = BatchCook(
            household_id=1, recipe_name="Sambar", cooked_on=DAY, tub_count=2, pattern="pick"
        )
        session.add(batch)
        session.commit()
        snap = {"name": "Sambar", "version": 1, "servings": 4, "lines": [], "steps": []}
        for household_id, link in (
            (2, {"meal_item_id": item_id}),  # household 1's meal item
            (2, {"batch_id": batch.id}),  # household 1's batch
            (1, {"meal_item_id": item_id, "batch_id": batch.id}),  # both
            (1, {}),  # neither
            (1, {"meal_item_id": item_id, "portions": 0}),
        ):
            fields: dict[str, Any] = {"portions": 2, **link}
            session.add(CookedRecord(household_id=household_id, snapshot=snap, **fields))
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()
        # One record per meal item.
        session.add(CookedRecord(household_id=1, snapshot=snap, portions=2, meal_item_id=item_id))
        session.flush()
        session.add(CookedRecord(household_id=1, snapshot=snap, portions=2, meal_item_id=item_id))
        with pytest.raises(IntegrityError):
            session.flush()


def test_a_size_line_keeps_its_size_after_the_size_is_renamed_or_deleted(
    kitchen: TestClient,
) -> None:
    """ "1 packet" is stored as 1 of the size: the snapshot keeps the size's name and amount,
    so the record still says how much that was once the size changes or goes."""
    dal = food(kitchen, "Toor dal", counted_as="weight")
    url = f"{API}/foods/{dal['id']}/sizes"
    packet = ok(kitchen.post(url, json={"name": "packet", "amount": 500}), 201)["food"]["sizes"][0]
    recipe = make(
        kitchen,
        "Dal",
        lines=[{"words": "toor dal", "amount": 1, "size_id": packet["id"], "food_id": dal["id"]}],
    )
    slot = slot_ids(kitchen)["Dinner"]
    body = {"date": DAY.isoformat(), "slot_id": slot, "recipe_id": recipe["id"], "servings": 2}
    item_id = int(ok(kitchen.post(f"{API}/plan/items", json=body), 201)["item_id"])
    _cook(kitchen, recipe["id"], meal_item_id=item_id)
    want = {
        "amount_milli": 1000,
        "unit": None,
        "size_id": packet["id"],
        "size_name": "packet",
        "size_plural": "packets",
        "size_amount_milli": 500_000,
        "size_unit": "g",
    }
    cooked_url = f"{API}/plan/items/{item_id}/cooked"

    def line() -> dict[str, Any]:
        found: dict[str, Any] = ok(kitchen.get(cooked_url))["snapshot"]["lines"][0]
        return {k: found[k] for k in want}

    assert line() == want
    ok(kitchen.patch(f"{url}/{packet['id']}", json={"name": "bag"}))
    ok(kitchen.patch(f"{url}/{packet['id']}", json={"amount": 1000}))
    assert line() == want
    ok(kitchen.delete(f"{url}/{packet['id']}"))
    assert line() == want
