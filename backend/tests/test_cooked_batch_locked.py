"""F157 round 2: a recipe cooked through a Cook once batch has no record of its own, but it is
cooked all the same: it stays in its meal, and it is not the leftovers' recipe."""

from datetime import date, timedelta

from fastapi.testclient import TestClient
from sync_kit import ok
from test_cooked_items_locked import refused
from test_cooked_parts import cooked_flags, two_in_a_meal
from test_cooked_undo import API, answer_cooked, status_of
from test_cooking import cook
from test_plan import slot_ids
from test_plan_writes import plan_recipe
from test_recipe_list import line
from test_recipes import make
from test_today import ago, get_today, tubs_left


def batch_cooked(client: TestClient) -> tuple[int, int, int]:
    """Khichdi is a batch's cook item and the batch is cooked; the soup is not. Planned."""
    _dal, meal, khichdi, soup = two_in_a_meal(client)
    batch = ok(
        client.post(f"{API}/plan/items/{khichdi}/batch", json={"tub_count": 2, "pattern": "pick"}),
        201,
    )["batch_id"]
    ok(client.post(f"{API}/plan/batches/{batch}/cook", json={}), 201)
    answer_cooked(client, meal)
    assert status_of(client, meal) == "planned"
    assert cooked_flags(client) == {khichdi: True, soup: False}
    return meal, khichdi, soup


def test_a_recipe_cooked_through_a_batch_cant_be_removed_or_re_served(kitchen: TestClient) -> None:
    meal, khichdi, soup = batch_cooked(kitchen)
    refused(kitchen.delete(f"{API}/plan/items/{khichdi}"))
    refused(kitchen.delete(f"{API}/plan/meals/{meal}"))
    refused(kitchen.patch(f"{API}/plan/items/{khichdi}", json={"servings": 3}))
    to = {
        "date": (date.today() + timedelta(days=1)).isoformat(),
        "slot_id": slot_ids(kitchen)["Dinner"],
    }
    refused(kitchen.post(f"{API}/plan/items/{khichdi}/move", json={**to, "mode": "move"}))
    assert ok(kitchen.delete(f"{API}/plan/items/{soup}"))  # the uncooked one still goes


def test_leftovers_and_move_it_skip_a_recipe_cooked_through_a_batch(kitchen: TestClient) -> None:
    dal, _m, _k, _s = two_in_a_meal(kitchen)
    dinner = slot_ids(kitchen)["Dinner"]
    day = ago(kitchen, 1)
    rice = plan_recipe(
        kitchen,
        make(kitchen, "Zorba rice", serves=2, lines=[line(dal["id"], 100, "g")])["id"],
        day,
        dinner,
    )
    stew = plan_recipe(
        kitchen,
        make(kitchen, "Zorba stew", serves=2, lines=[line(dal["id"], 100, "g")])["id"],
        day,
        dinner,
    )
    batch = ok(
        kitchen.post(
            f"{API}/plan/items/{rice['item_id']}/batch", json={"tub_count": 2, "pattern": "pick"}
        ),
        201,
    )["batch_id"]
    ok(kitchen.post(f"{API}/plan/batches/{batch}/cook", json={}), 201)
    card = next(w for w in get_today(kitchen)["waiting"] if w["meal_id"] == rice["meal_id"])
    assert card["leftover_item_id"] == stew["item_id"]
    before = {t["id"] for t in tubs_left(kitchen)}
    ok(cook(kitchen, stew["item_id"]), 201)
    ok(
        kitchen.post(
            f"{API}/plan/meals/{rice['meal_id']}/cooked",
            json={"leftovers": {"count": 2, "place_kind": "fridge"}},
        )
    )
    new = [
        t for t in tubs_left(kitchen) if t["id"] not in before and t["recipe_name"] != "Zorba rice"
    ]
    assert {t["recipe_name"] for t in new} == {"Zorba stew"}


def test_undo_of_an_older_move_doesnt_carry_a_cooked_recipe_back(kitchen: TestClient) -> None:
    _dal, meal, _khichdi, soup = two_in_a_meal(kitchen)
    to = {
        "date": (date.today() + timedelta(days=1)).isoformat(),
        "slot_id": slot_ids(kitchen)["Dinner"],
    }
    moved = ok(kitchen.post(f"{API}/plan/meals/{meal}/move", json={**to, "mode": "move"}))
    ok(cook(kitchen, soup), 201)
    kitchen.post(f"{API}/changes/{moved['change']['id']}/undo")
    plan = ok(kitchen.get(f"{API}/plan", params={"from": to["date"], "to": to["date"]}))
    assert [m["id"] for m in plan["meals"]] == [meal]  # still where it was moved to


def stock_of(client: TestClient, food_id: int) -> int:
    from sqlalchemy import select as sel
    from test_plan import db_of

    from mealwright.models import StockLot

    with db_of(client) as db:
        return sum(
            lot.amount_milli for lot in db.scalars(sel(StockLot).where(StockLot.food_id == food_id))
        )


def test_undo_of_making_a_batch_doesnt_delete_it_once_cooked(kitchen: TestClient) -> None:
    from sqlalchemy import select as sel
    from test_plan import db_of

    from mealwright.models import BatchCook, CookedRecord

    dal, _meal, khichdi, _soup = two_in_a_meal(kitchen)
    made = ok(
        kitchen.post(f"{API}/plan/items/{khichdi}/batch", json={"tub_count": 2, "pattern": "pick"}),
        201,
    )
    ok(kitchen.post(f"{API}/plan/batches/{made['batch_id']}/cook", json={}), 201)
    taken = stock_of(kitchen, dal["id"])
    kitchen.post(f"{API}/changes/{made['change']['id']}/undo")
    with db_of(kitchen) as db:
        assert db.scalars(sel(BatchCook)).all() and db.scalars(sel(CookedRecord)).all()
    assert stock_of(kitchen, dal["id"]) == taken


def test_leftovers_after_a_batch_press_are_the_batchs_recipes(kitchen: TestClient) -> None:
    _dal, meal, khichdi, _soup = two_in_a_meal(kitchen)
    batch = ok(
        kitchen.post(f"{API}/plan/items/{khichdi}/batch", json={"tub_count": 1, "pattern": "pick"}),
        201,
    )["batch_id"]
    ok(kitchen.post(f"{API}/plan/batches/{batch}/cook", json={}), 201)
    before = {t["id"] for t in tubs_left(kitchen)}
    ok(
        kitchen.post(
            f"{API}/plan/meals/{meal}/cooked",
            json={"leftovers": {"count": 2, "place_kind": "fridge"}},
        )
    )
    new = [t for t in tubs_left(kitchen) if t["id"] not in before]
    assert new and {t["recipe_name"] for t in new} <= {"Zorba khichdi"}


def test_undoing_an_older_removal_keeps_the_cooked_copy_first(kitchen: TestClient) -> None:
    from test_plan import db_of

    from mealwright.models import MealItem

    _dal, meal, k1, soup = two_in_a_meal(kitchen)
    with db_of(kitchen) as db:
        item = db.get(MealItem, k1)
        assert item is not None
        recipe_id = item.recipe_id
    k2 = ok(
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
    batch = ok(
        kitchen.post(f"{API}/plan/items/{k1}/batch", json={"tub_count": 1, "pattern": "pick"}),
        201,
    )["batch_id"]
    removed = ok(kitchen.delete(f"{API}/plan/items/{k1}"))
    ok(kitchen.post(f"{API}/plan/batches/{batch}/cook", json={}), 201)
    kitchen.post(f"{API}/changes/{removed['change']['id']}/undo")
    flags = cooked_flags(kitchen)
    restored = next(i for i in flags if i not in (k2, soup))
    assert flags[k2] is True and flags[restored] is False
    refused(kitchen.delete(f"{API}/plan/items/{k2}"))
    assert meal


def tub_ids(client: TestClient) -> list[int]:
    from sqlalchemy import select as sel
    from test_plan import db_of

    from mealwright.models import Tub

    with db_of(client) as db:
        return [t.id for t in db.scalars(sel(Tub))]


def batch_tub_count(client: TestClient) -> int:
    from sqlalchemy import select as sel
    from test_plan import db_of

    from mealwright.models import BatchCook

    with db_of(client) as db:
        return db.scalars(sel(BatchCook)).one().tub_count


def test_undo_of_leftovers_added_to_a_cooked_batch_takes_them_back(kitchen: TestClient) -> None:
    _dal, meal, khichdi, _soup = two_in_a_meal(kitchen)
    batch = ok(
        kitchen.post(f"{API}/plan/items/{khichdi}/batch", json={"tub_count": 1, "pattern": "pick"}),
        201,
    )["batch_id"]
    ok(kitchen.post(f"{API}/plan/batches/{batch}/cook", json={}), 201)
    assert len(tub_ids(kitchen)) == 1
    answer = ok(
        kitchen.post(
            f"{API}/plan/meals/{meal}/cooked",
            json={"leftovers": {"count": 2, "place_kind": "fridge"}},
        )
    )["change"]
    assert len(tub_ids(kitchen)) == 3 and batch_tub_count(kitchen) == 3
    result = ok(kitchen.post(f"{API}/changes/{answer['id']}/undo"))
    assert result["result"] == "done", result
    assert len(tub_ids(kitchen)) == 1 and batch_tub_count(kitchen) == 1


def test_undo_of_an_answer_not_joined_to_a_press_takes_its_tubs_back(kitchen: TestClient) -> None:
    _dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    batch = ok(
        kitchen.post(f"{API}/plan/items/{khichdi}/batch", json={"tub_count": 1, "pattern": "pick"}),
        201,
    )["batch_id"]
    ok(kitchen.post(f"{API}/plan/batches/{batch}/cook", json={}), 201)
    ok(cook(kitchen, soup), 201)  # another press in between
    for _ in range(2):
        answer = ok(
            kitchen.post(
                f"{API}/plan/meals/{meal}/cooked",
                json={"leftovers": {"count": 2, "place_kind": "fridge", "item_id": khichdi}},
            )
        )["change"]
        assert len(tub_ids(kitchen)) == 3
        kitchen.post(f"{API}/changes/{answer['id']}/undo")
        assert len(tub_ids(kitchen)) == 1 and batch_tub_count(kitchen) == 1


def test_undo_of_an_older_item_move_keeps_the_cooked_copy_first(kitchen: TestClient) -> None:
    from test_plan import db_of

    from mealwright.models import MealItem

    _dal, _meal, k1, _soup = two_in_a_meal(kitchen)
    with db_of(kitchen) as db:
        item = db.get(MealItem, k1)
        assert item is not None
        recipe_id = item.recipe_id
    to = {
        "date": (date.today() + timedelta(days=1)).isoformat(),
        "slot_id": slot_ids(kitchen)["Dinner"],
    }
    moved = ok(kitchen.post(f"{API}/plan/items/{k1}/move", json={**to, "mode": "move"}))
    k2 = ok(
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
    batch = ok(
        kitchen.post(f"{API}/plan/items/{k2}/batch", json={"tub_count": 1, "pattern": "pick"}),
        201,
    )["batch_id"]
    ok(kitchen.post(f"{API}/plan/batches/{batch}/cook", json={}), 201)
    kitchen.post(f"{API}/changes/{moved['change']['id']}/undo")
    flags = cooked_flags(kitchen)
    assert flags[k2] is True and flags[k1] is False
    refused(kitchen.delete(f"{API}/plan/items/{k2}"))
