"""F157 (cabledrawer 6 Nov): cooking ONE recipe of a meal with several recipes must not mark the
whole meal cooked. The meal is Cooked when every recipe in it (and every Cook once batch it
uses) has been cooked; each press marks, takes and undoes only what it cooked."""

from datetime import UTC, date, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_cooked_undo import (
    API,
    answer_cooked,
    pantry_list,
    status_of,
    undo,
    undone,
)
from test_cooking import amounts, cook
from test_history import wren  # noqa: F401 (a fixture)
from test_plan import db_of, slot_ids
from test_recipe_list import line, stock
from test_recipes import food, make

from mealwright.models import CookedRecord, Meal, MealItem, Recipe


def two_in_a_meal(client: TestClient, extra: int = 0) -> tuple[dict[str, Any], int, int, int]:
    """Zorba khichdi and Zorba soup planned together for today's dinner."""
    dal = food(client, "Zorba dal")
    stock(client, dal["id"], 900, "g")
    ids = []
    for name in ("Zorba khichdi", "Zorba soup"):
        planned = ok(
            client.post(
                f"{API}/plan/items",
                json={
                    "date": date.today().isoformat(),
                    "slot_id": slot_ids(client)["Dinner"],
                    "recipe_id": make(client, name, serves=2, lines=[line(dal["id"], 100, "g")])[
                        "id"
                    ],
                    "servings": 2,
                },
            ),
            201,
        )
        ids.append(planned["item_id"])
    return dal, int(planned["meal_id"]), ids[0], ids[1]


def press(client: TestClient, meal: int, item: int) -> tuple[dict[str, Any], dict[str, Any]]:
    """One "Cooked it": the review's confirm of one recipe, then the meal's answer."""
    pantry = ok(cook(client, item), 201)["change"]
    return pantry, answer_cooked(client, meal)["change"]


def cooked_flags(client: TestClient) -> dict[int, bool]:
    today = date.today().isoformat()
    plan = ok(client.get(f"{API}/plan", params={"from": today, "to": today}))
    return {i["id"]: i["cooked"] for m in plan["meals"] for i in m["items"]}


def records(client: TestClient) -> set[int | None]:
    with db_of(client) as db:
        return {r.meal_item_id for r in db.scalars(select(CookedRecord))}


def test_cooking_one_recipe_leaves_the_meal_planned(kitchen: TestClient) -> None:
    _dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    _pantry, answer = press(kitchen, meal, soup)
    assert status_of(kitchen, meal) == "planned"
    assert records(kitchen) == {soup}
    assert cooked_flags(kitchen) == {khichdi: False, soup: True}
    # Only the soup is named: the toast's summary and Recent changes.
    assert answer["summary"].startswith("Cooked Zorba soup (Dinner on ")
    assert "more" not in answer["summary"] and "khichdi" not in answer["summary"]
    rows = [c for c in pantry_list(kitchen) if c["kind"] == "cooked"]
    assert [r["summary"] for r in rows] == ["Cooked Zorba soup (2 portions)"]


def test_the_second_recipe_makes_the_meal_cooked(kitchen: TestClient) -> None:
    _dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    press(kitchen, meal, soup)
    _p, answer = press(kitchen, meal, khichdi)
    assert answer["summary"].startswith("Cooked Zorba khichdi (")
    assert status_of(kitchen, meal) == "cooked"
    assert cooked_flags(kitchen) == {khichdi: True, soup: True}


def test_undo_of_the_last_press_keeps_the_first(kitchen: TestClient) -> None:
    dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    press(kitchen, meal, soup)
    pantry, _answer = press(kitchen, meal, khichdi)
    assert ok(undo(kitchen, pantry["id"]))["result"] == "done"
    assert status_of(kitchen, meal) == "planned"
    assert records(kitchen) == {soup}
    assert cooked_flags(kitchen) == {khichdi: False, soup: True}
    assert sum(amounts(kitchen, dal["id"])) == 800_000


def test_undo_of_a_partial_press_alone_is_clean(kitchen: TestClient) -> None:
    dal, meal, _khichdi, soup = two_in_a_meal(kitchen)
    pantry, answer = press(kitchen, meal, soup)
    # The toast's Undo is the answer's: it has no plan step, and still takes the pantry back.
    said = ok(undo(kitchen, answer["id"]))
    assert said["result"] == "done" and "nothing" not in said["message"].lower()
    assert undone(kitchen, pantry["id"])
    assert records(kitchen) == set() and status_of(kitchen, meal) == "planned"
    assert sum(amounts(kitchen, dal["id"])) == 900_000


def test_undo_of_the_earlier_press_while_the_meal_is_cooked(kitchen: TestClient) -> None:
    dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    first, _ = press(kitchen, meal, soup)
    second, _ = press(kitchen, meal, khichdi)
    assert status_of(kitchen, meal) == "cooked"
    assert ok(undo(kitchen, first["id"]))["result"] == "done"
    assert status_of(kitchen, meal) == "planned"
    assert records(kitchen) == {khichdi}
    assert cooked_flags(kitchen) == {khichdi: True, soup: False}
    # The later press's own Undo still works, and counts as done.
    assert ok(undo(kitchen, second["id"]))["result"] == "done"
    assert records(kitchen) == set() and status_of(kitchen, meal) == "planned"
    assert sum(amounts(kitchen, dal["id"])) == 900_000


def test_an_answer_with_no_pantry_change_cooks_the_whole_meal(kitchen: TestClient) -> None:
    _dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    answer = answer_cooked(kitchen, meal)["change"]
    assert status_of(kitchen, meal) == "cooked"
    assert "and 1 more" in answer["summary"]
    assert cooked_flags(kitchen) == {khichdi: True, soup: True}


def test_an_alpha_meal_cooked_with_no_records_reads_cooked_everywhere(
    kitchen: TestClient,
) -> None:
    _dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    with db_of(kitchen) as db:
        m = db.get(Meal, meal)
        assert m is not None
        m.status = "cooked"
        db.commit()
    assert cooked_flags(kitchen) == {khichdi: True, soup: True}


def test_a_note_and_an_ingredient_beside_the_recipes_dont_block_cooked(
    kitchen: TestClient,
) -> None:
    _dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    salt = food(kitchen, "Zorba salt")
    slot = slot_ids(kitchen)["Dinner"]
    day = date.today().isoformat()
    ok(
        kitchen.post(
            f"{API}/plan/items", json={"date": day, "slot_id": slot, "ingredient_id": salt["id"]}
        ),
        201,
    )
    ok(
        kitchen.post(
            f"{API}/plan/items", json={"date": day, "slot_id": slot, "note": "Eating out"}
        ),
        201,
    )
    press(kitchen, meal, soup)
    assert status_of(kitchen, meal) == "planned"
    press(kitchen, meal, khichdi)
    assert status_of(kitchen, meal) == "cooked"


def test_a_meal_with_a_batch_and_a_recipe_needs_both(kitchen: TestClient) -> None:
    _dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    batch = ok(
        kitchen.post(f"{API}/plan/items/{khichdi}/batch", json={"tub_count": 2, "pattern": "pick"}),
        201,
    )["batch_id"]
    assert cooked_flags(kitchen) == {khichdi: False, soup: False}
    # The soup first: the batch is still to cook.
    ok(kitchen.post(f"{API}/plan/meals/{meal}/cook", json={"items": [{"item_id": soup}]}), 201)
    answer = answer_cooked(kitchen, meal)["change"]
    assert status_of(kitchen, meal) == "planned" and "khichdi" not in answer["summary"]
    assert cooked_flags(kitchen) == {khichdi: False, soup: True}
    ok(kitchen.post(f"{API}/plan/batches/{batch}/cook", json={}), 201)
    answer = answer_cooked(kitchen, meal)["change"]
    assert answer["summary"].startswith("Cooked Zorba khichdi (")
    assert status_of(kitchen, meal) == "cooked"
    assert cooked_flags(kitchen) == {khichdi: True, soup: True}


def test_the_batch_first_then_the_recipe(kitchen: TestClient) -> None:
    _dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    batch = ok(
        kitchen.post(f"{API}/plan/items/{khichdi}/batch", json={"tub_count": 2, "pattern": "pick"}),
        201,
    )["batch_id"]
    ok(kitchen.post(f"{API}/plan/batches/{batch}/cook", json={}), 201)
    answer_cooked(kitchen, meal)
    assert status_of(kitchen, meal) == "planned"
    assert cooked_flags(kitchen) == {khichdi: True, soup: False}
    ok(kitchen.post(f"{API}/plan/meals/{meal}/cook", json={"items": [{"item_id": soup}]}), 201)
    answer_cooked(kitchen, meal)
    assert status_of(kitchen, meal) == "cooked"


def test_didnt_cook_it_acts_on_a_part_cooked_meal(kitchen: TestClient) -> None:
    _dal, meal, _khichdi, soup = two_in_a_meal(kitchen)
    press(kitchen, meal, soup)
    ok(kitchen.post(f"{API}/plan/meals/{meal}/mark-not-cooked"))
    assert status_of(kitchen, meal) == "didnt"


def test_another_logins_press_is_not_joined(kitchen: TestClient, wren: TestClient) -> None:  # noqa: F811
    _dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    mine, _ = press(kitchen, meal, soup)
    theirs, answer = press(wren, meal, khichdi)
    assert answer["summary"].startswith("Cooked Zorba khichdi (")
    assert status_of(kitchen, meal) == "cooked"
    # Wren's Undo leaves the first login's cooking.
    assert ok(undo(wren, answer["id"]))["result"] == "done"
    assert not undone(kitchen, mine["id"]) and undone(kitchen, theirs["id"])
    assert records(kitchen) == {soup} and status_of(kitchen, meal) == "planned"


def test_leftovers_of_a_part_cooked_meal_dont_stop_it_being_cooked(kitchen: TestClient) -> None:
    """Tubs made with the first press put a batch on the meal (no record of its own): the
    recipe's own record still counts as cooked."""
    _dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    ok(cook(kitchen, soup), 201)
    ok(
        kitchen.post(
            f"{API}/plan/meals/{meal}/mark-cooked",
            json={"leftovers": {"count": 2, "place_kind": "fridge", "item_id": soup}},
        )
    )
    assert status_of(kitchen, meal) == "planned"
    assert cooked_flags(kitchen) == {khichdi: False, soup: True}
    press(kitchen, meal, khichdi)
    assert status_of(kitchen, meal) == "cooked"


def test_a_deleted_recipe_doesnt_stop_the_meal_being_cooked(kitchen: TestClient) -> None:
    """A recipe deleted after planning can't be cooked, so it doesn't count (F157 review)."""
    _dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    with db_of(kitchen) as db:
        item = db.get(MealItem, khichdi)
        assert item is not None and item.recipe_id is not None
        recipe = db.get(Recipe, item.recipe_id)
        assert recipe is not None
        recipe.removed_at = datetime.now(UTC)
        db.commit()
    press(kitchen, meal, soup)
    assert status_of(kitchen, meal) == "cooked"


def test_the_same_recipe_twice_is_cooked_when_both_are(kitchen: TestClient) -> None:
    """Two copies of one recipe are two items: each needs its own press (F157 review)."""
    _dal, meal, khichdi, _soup = two_in_a_meal(kitchen)
    with db_of(kitchen) as db:
        item = db.get(MealItem, khichdi)
        assert item is not None
        recipe_id = item.recipe_id
    again = ok(
        kitchen.post(
            f"{API}/plan/items",
            json={
                "date": date.today().isoformat(),
                "slot_id": slot_ids(kitchen)["Dinner"],
                "recipe_id": recipe_id,
                "servings": 2,
            },
        ),
        201,
    )["item_id"]
    soup = next(i for i in cooked_flags(kitchen) if i not in (khichdi, again))
    press(kitchen, meal, khichdi)
    press(kitchen, meal, soup)
    assert status_of(kitchen, meal) == "planned"  # the second copy is not cooked
    press(kitchen, meal, again)
    assert status_of(kitchen, meal) == "cooked"


def test_move_it_on_a_part_cooked_meal_names_only_what_moves(kitchen: TestClient) -> None:
    """F162: the change says "Moved Zorba khichdi", not "... and 1 more"."""
    _dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    press(kitchen, meal, soup)
    tomorrow = date.today() + timedelta(days=2)
    body = {"date": tomorrow.isoformat(), "slot_id": slot_ids(kitchen)["Dinner"]}
    moved = ok(kitchen.post(f"{API}/plan/meals/{meal}/mark-moved", json=body))["change"]
    assert moved["summary"].startswith("Moved Zorba khichdi from Dinner on ")
    assert "more" not in moved["summary"] and khichdi


def test_a_recipe_not_cooked_yet_can_be_changed_and_removed_on_its_own(
    kitchen: TestClient,
) -> None:
    """F163: only cooked recipes are locked in a part-cooked meal."""
    _dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    press(kitchen, meal, soup)
    ok(kitchen.patch(f"{API}/plan/items/{khichdi}", json={"servings": 3}))
    locked = kitchen.delete(f"{API}/plan/items/{soup}")
    assert locked.status_code == 409 and locked.json()["code"] == "already_cooked"
    ok(kitchen.delete(f"{API}/plan/items/{khichdi}"))
    assert status_of(kitchen, meal) == "planned"


def test_a_meal_with_every_recipe_cooked_but_still_planned_reads_as_cooked(
    kitchen: TestClient,
) -> None:
    """F158: a lost reply to Confirm left the meal planned; the next read sets it right."""
    _dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    ok(cook(kitchen, soup), 201)
    ok(cook(kitchen, khichdi), 201)  # the pantry was changed; the meal's answer never arrived
    assert status_of(kitchen, meal) == "planned"
    today = date.today().isoformat()
    # Just pressed: the screen's own answer is still on its way, so a read leaves it be.
    plan = ok(kitchen.get(f"{API}/plan", params={"from": today, "to": today}))
    assert [m["status"] for m in plan["meals"] if m["id"] == meal] == ["planned"]
    with db_of(kitchen) as db:
        for record in db.scalars(select(CookedRecord)):
            record.cooked_at = datetime.now(UTC) - timedelta(hours=1)
        db.commit()
    plan = ok(kitchen.get(f"{API}/plan", params={"from": today, "to": today}))
    assert [m["status"] for m in plan["meals"] if m["id"] == meal] == ["cooked"]
    assert status_of(kitchen, meal) == "cooked"
    assert get_today_waiting(kitchen) == []


def get_today_waiting(client: TestClient) -> list[Any]:
    waiting: list[Any] = ok(client.get(f"{API}/today"))["waiting"]
    return waiting


def test_cooking_a_whole_meal_leaves_a_deleted_recipe_out(kitchen: TestClient) -> None:
    """F158: the review of a whole meal doesn't list a recipe taken out of the recipe list."""
    _dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    with db_of(kitchen) as db:
        item = db.get(MealItem, khichdi)
        assert item is not None and item.recipe_id is not None
        recipe = db.get(Recipe, item.recipe_id)
        assert recipe is not None
        recipe.removed_at = datetime.now(UTC)
        db.commit()
    shown = ok(kitchen.post(f"{API}/plan/meals/{meal}/cook/preview", json={"answers": []}))
    assert [i["item_id"] for i in shown["items"]] == [soup]


def test_undo_after_a_healed_meal_leaves_it_planned_with_stock_back_once(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """F158 review H1: lost reply -> the read heals the meal -> Undo of a Cooked it: the meal is
    planned again, Cooked it is offered, the stock is back once; the heal tells other screens."""
    dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    ok(cook(kitchen, soup), 201)
    last = ok(cook(kitchen, khichdi), 201)["change"]  # the answer never arrived
    with db_of(kitchen) as db:
        for record in db.scalars(select(CookedRecord)):
            record.cooked_at = datetime.now(UTC) - timedelta(hours=1)
        db.commit()
    heard: list[Any] = []
    hub = kitchen.app.state.events  # type: ignore[attr-defined]
    real = hub.publish
    monkeypatch.setattr(
        hub, "publish", lambda household, event: (heard.append(event), real(household, event))
    )
    today = date.today().isoformat()
    plan = ok(kitchen.get(f"{API}/plan", params={"from": today, "to": today}))
    assert [m["status"] for m in plan["meals"] if m["id"] == meal] == ["cooked"]
    # The healed meal is a planned meal changing too, so open Plans are told (RF5).
    assert [e.name for e in heard] == ["pantry", "plan"]
    assert ok(undo(kitchen, last["id"]))["result"] == "done"
    assert status_of(kitchen, meal) == "planned"
    assert cooked_flags(kitchen) == {khichdi: False, soup: True}
    assert sum(amounts(kitchen, dal["id"])) == 800_000  # the khichdi's 100 g, back once
    answer = press(kitchen, meal, khichdi)[1]  # Cooked it is offered again
    assert status_of(kitchen, meal) == "cooked" and answer


def test_undo_of_the_only_press_of_a_healed_meal_leaves_it_planned(kitchen: TestClient) -> None:
    """F158 review H1: no record is left after this Undo, and the meal is still planned again."""
    dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    ok(kitchen.delete(f"{API}/plan/items/{soup}"))
    cooked_change = ok(cook(kitchen, khichdi), 201)["change"]
    with db_of(kitchen) as db:
        for record in db.scalars(select(CookedRecord)):
            record.cooked_at = datetime.now(UTC) - timedelta(hours=1)
        db.commit()
    today = date.today().isoformat()
    ok(kitchen.get(f"{API}/plan", params={"from": today, "to": today}))
    assert status_of(kitchen, meal) == "cooked"
    ok(undo(kitchen, cooked_change["id"]))
    assert status_of(kitchen, meal) == "planned"
    assert records(kitchen) == set()
    assert sum(amounts(kitchen, dal["id"])) == 900_000
