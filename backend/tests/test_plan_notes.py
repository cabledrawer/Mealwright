"""A "Note" plan item (0.7 P1; spec, "From the 28 Oct review of v0.6.0"): "Eating out",
"Takeaway", "At Tess's". It counts as a filled meal and needs nothing bought, gets no "Did you
cook?", and Cook once and Fill from freezer ignore it."""

from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import changes, ok
from test_plan import add_recipe, db_of, slot_ids
from test_plan_batches import make, where_tubs_are
from test_plan_writes import D1, plan_recipe, shape, undo, view

from mealwright.models import MealItem

API = "/api/v1"


@pytest.fixture
def slots(kitchen: TestClient) -> dict[str, int]:
    return slot_ids(kitchen)


def add_note(
    client: TestClient, day: date, slot: int, text: str = "Eating out", code: int = 201
) -> Any:
    r = client.post(
        f"{API}/plan/items", json={"date": day.isoformat(), "slot_id": slot, "note": text}
    )
    assert r.status_code == code, r.text
    return r.json()


def test_a_note_is_planned_shown_and_undone(kitchen: TestClient, slots: dict[str, int]) -> None:
    before = shape(kitchen)
    made = add_note(kitchen, D1, slots["Dinner"], "  At   Tess’s ")
    assert made["change"]["summary"].startswith("Planned At Tess’s for Dinner on ")
    meal = view(kitchen)["meals"][0]
    (item,) = meal["items"]
    assert item["kind"] == "note" and item["note"] == "At Tess’s"
    assert item["recipe"] is None and item["ingredient"] is None and item["tub_id"] is None
    assert item["kept_name"] is None and item["servings"] is None
    assert undo(kitchen, made)["result"] == "done"
    assert shape(kitchen) == before


def test_a_note_needs_text_and_nothing_else(kitchen: TestClient, slots: dict[str, int]) -> None:
    for text in ("", "   ", "x" * 201, "Eating\tout", "Eating\nout", "Out‮"):
        add_note(kitchen, D1, slots["Dinner"], text, code=422)
    both = kitchen.post(
        f"{API}/plan/items",
        json={"date": D1.isoformat(), "slot_id": slots["Dinner"], "note": "Out", "recipe_id": 1},
    )
    assert both.status_code == 422 and both.json()["code"] == "one_field"
    too_long = kitchen.post(
        f"{API}/plan/items",
        json={"date": D1.isoformat(), "slot_id": slots["Dinner"], "note": "x" * 201},
    )
    assert "A note can be up to 200 letters." in too_long.text  # cabledrawer 2 Nov
    assert view(kitchen)["meals"] == []
    assert add_note(kitchen, D1, slots["Dinner"], "x" * 200)["item_id"]


def test_a_note_sits_beside_other_things_and_moves_and_copies_like_them(
    kitchen: TestClient, slots: dict[str, int]
) -> None:
    first = add_note(kitchen, D1, slots["Lunch"], "Takeaway")
    to = {"date": (D1 + timedelta(days=1)).isoformat(), "slot_id": slots["Lunch"]}
    assert (
        kitchen.post(
            f"{API}/plan/items/{first['item_id']}/move", json={**to, "mode": "copy"}
        ).status_code
        == 200
    )
    notes = [i for m in view(kitchen)["meals"] for i in m["items"]]
    assert [(i["kind"], i["note"]) for i in notes] == [("note", "Takeaway")] * 2
    # Leftovers of a note make no sense.
    r = kitchen.post(
        f"{API}/plan/items/{first['item_id']}/move",
        json={
            "date": (D1 + timedelta(days=2)).isoformat(),
            "slot_id": slots["Lunch"],
            "mode": "leftovers",
        },
    )
    assert r.status_code == 422 and r.json()["code"] == "note_no_leftovers"
    # A meal of notes and a recipe: leftovers of the whole meal take the recipe only.
    with db_of(kitchen) as db:
        recipe = add_recipe(db, 1, "Dal")
        db.commit()
        recipe_id = recipe.id
    cook = plan_recipe(kitchen, recipe_id, D1, slots["Lunch"])
    m = kitchen.post(
        f"{API}/plan/meals/{cook['meal_id']}/move",
        json={
            "date": (D1 + timedelta(days=2)).isoformat(),
            "slot_id": slots["Dinner"],
            "mode": "leftovers",
        },
    )
    assert m.status_code == 200, m.text
    dinner = next(
        x for x in view(kitchen)["meals"] if x["date"] == (D1 + timedelta(days=2)).isoformat()
    )
    assert [i["kind"] for i in dinner["items"]] == ["tub"]


def test_a_note_needs_nothing_bought(kitchen: TestClient, slots: dict[str, int]) -> None:
    add_note(kitchen, D1, slots["Dinner"])
    ok(kitchen.post(f"{API}/shopping/add-from-plan"))
    assert [r for r in changes(kitchen)["items"] if r["source"] == "plan"] == []


def test_a_meal_of_a_note_is_never_asked_about_but_a_recipe_beside_it_is(
    kitchen: TestClient, slots: dict[str, int]
) -> None:
    yesterday = date.fromisoformat(ok(kitchen.get(f"{API}/household"))["today"]) - timedelta(days=1)
    noted = add_note(kitchen, yesterday, slots["Lunch"], "Takeaway")
    assert ok(kitchen.get(f"{API}/today"))["waiting"] == []
    with db_of(kitchen) as db:
        recipe = add_recipe(db, 1, "Dal")
        db.commit()
        recipe_id = recipe.id
    cooked = plan_recipe(kitchen, recipe_id, yesterday, slots["Dinner"])
    add_note(kitchen, yesterday, slots["Dinner"], "Then ice cream")
    waiting = ok(kitchen.get(f"{API}/today"))["waiting"]
    assert [w["meal_id"] for w in waiting] == [cooked["meal_id"]]
    assert noted["meal_id"] not in [w["meal_id"] for w in waiting]


def test_cook_once_and_fill_from_freezer_ignore_a_noted_meal(
    kitchen: TestClient, slots: dict[str, int]
) -> None:
    with db_of(kitchen) as db:
        recipe = add_recipe(db, 1, "Veg biryani")
        db.commit()
        recipe_id = recipe.id
    cook = plan_recipe(kitchen, recipe_id, D1, slots["Dinner"])
    tomorrow = D1 + timedelta(days=1)
    add_note(kitchen, tomorrow, slots["Lunch"], "At Tess’s")
    made = make(
        kitchen, cook["item_id"], tub_count=3, pattern="lunch_dinner", extras_to_freezer=True
    )
    assert made["batch_id"]
    # The noted lunch got no tub: the tubs went to the next free meals.
    assert where_tubs_are(kitchen, slots) == [
        (1, tomorrow.isoformat(), "Dinner"),
        (2, (tomorrow + timedelta(days=1)).isoformat(), "Lunch"),
        (3, (tomorrow + timedelta(days=1)).isoformat(), "Dinner"),
    ]
    # A frozen tub: a day with a note is not "empty", so Fill from freezer leaves it.
    other = plan_recipe(kitchen, recipe_id, D1 + timedelta(days=10), slots["Dinner"])
    make(kitchen, other["item_id"], tub_count=1, pattern="pick", extras_to_freezer=True)
    far = D1 + timedelta(days=12)
    add_note(kitchen, far, slots["Dinner"], "Eating out")
    r = kitchen.post(
        f"{API}/plan/fill-from-freezer", json={"from": far.isoformat(), "to": far.isoformat()}
    )
    assert r.status_code == 200 and r.json()["change"] is None
    with db_of(kitchen) as db:
        assert len(list(db.scalars(select(MealItem).where(MealItem.kind == "note")))) == 2


def test_another_household_sees_none_of_my_notes(
    kitchen: TestClient, neighbour: TestClient, slots: dict[str, int]
) -> None:
    made = add_note(kitchen, D1, slots["Dinner"])
    assert view(neighbour)["meals"] == []
    assert neighbour.delete(f"{API}/plan/items/{made['item_id']}").status_code == 404
    # My note, their meal slot.
    theirs = slot_ids(kitchen, 2)
    add_note(kitchen, D1, theirs["Dinner"], code=404)
    assert neighbour.post(f"{API}/changes/{made['change']['id']}/undo").status_code == 404
    assert len(view(kitchen)["meals"]) == 1
