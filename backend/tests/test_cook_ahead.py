"""F159 (cabledrawer 6 Nov): Cooked it works on a later day's meal (cooking ahead). The meal stays
on its day, stock is taken once, Didn't is still refused before the day, and tubs count their
use-by from the day they were really cooked."""

from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_cooked_undo import API, answer_cooked, status_of, undo
from test_cooking import amounts, cook
from test_plan import db_of, slot_ids
from test_recipe_list import line, stock
from test_recipes import food, make

from mealwright.models import CookedRecord, Meal, Tub


def plan_ahead(client: TestClient, days: int = 1) -> tuple[dict[str, Any], int, int, date]:
    dal = food(client, "Zorba dal")
    stock(client, dal["id"], 900, "g")
    day = date.today() + timedelta(days=days)
    recipe = make(client, "Zorba khichdi", serves=2, lines=[line(dal["id"], 100, "g")])
    planned = ok(
        client.post(
            f"{API}/plan/items",
            json={
                "date": day.isoformat(),
                "slot_id": slot_ids(client)["Dinner"],
                "recipe_id": recipe["id"],
                "servings": 2,
            },
        ),
        201,
    )
    return dal, int(planned["meal_id"]), int(planned["item_id"]), day


def test_cooked_it_on_a_later_days_meal_works(kitchen: TestClient) -> None:
    dal, meal, item, day = plan_ahead(kitchen)
    ok(cook(kitchen, item), 201)
    answer_cooked(kitchen, meal)
    assert status_of(kitchen, meal) == "cooked"
    with db_of(kitchen) as db:
        assert db.get(Meal, meal).day == day  # type: ignore[union-attr]
    assert sum(amounts(kitchen, dal["id"])) == 800_000  # taken once


def test_didnt_on_a_later_days_meal_is_still_refused(kitchen: TestClient) -> None:
    _dal, meal, _item, _day = plan_ahead(kitchen)
    r = kitchen.post(f"{API}/plan/meals/{meal}/didnt")
    assert r.status_code == 422 and r.json()["code"] == "not_yet"
    assert status_of(kitchen, meal) == "planned"


def test_undo_of_an_early_cooked_it_puts_everything_back(kitchen: TestClient) -> None:
    dal, meal, item, _day = plan_ahead(kitchen)
    pantry = ok(cook(kitchen, item), 201)["change"]
    answer_cooked(kitchen, meal)
    assert ok(undo(kitchen, pantry["id"]))["result"] == "done"
    assert status_of(kitchen, meal) == "planned"
    assert sum(amounts(kitchen, dal["id"])) == 900_000


def test_a_batch_cooked_a_day_early_has_tubs_that_count_from_the_cooking_day(
    kitchen: TestClient,
) -> None:
    _dal, meal, item, day = plan_ahead(kitchen)
    batch = ok(
        kitchen.post(f"{API}/plan/items/{item}/batch", json={"tub_count": 2, "pattern": "pick"}),
        201,
    )["batch_id"]
    fridge = timedelta(days=3)
    with db_of(kitchen) as db:
        assert {t.use_by for t in db.scalars(select(Tub))} == {day + fridge}
    cooked = ok(kitchen.post(f"{API}/plan/batches/{batch}/cook", json={}), 201)["change"]
    answer_cooked(kitchen, meal)
    with db_of(kitchen) as db:
        assert {t.use_by for t in db.scalars(select(Tub))} == {date.today() + fridge}
    ok(undo(kitchen, cooked["id"]))
    with db_of(kitchen) as db:
        assert {t.use_by for t in db.scalars(select(Tub))} == {day + fridge}


def test_leftover_tubs_of_an_early_cook_count_from_the_cooking_day(kitchen: TestClient) -> None:
    _dal, meal, item, _day = plan_ahead(kitchen)
    ok(cook(kitchen, item), 201)
    answer_cooked(kitchen, meal, tubs=2)
    with db_of(kitchen) as db:
        assert {t.use_by for t in db.scalars(select(Tub))} == {date.today() + timedelta(days=3)}


def test_a_batch_cooked_early_counts_later_tubs_from_the_day_it_was_cooked(
    kitchen: TestClient,
) -> None:
    """F159 review L4: the use-by a new tub gets (and the after-use-by check) follows the day
    the batch was really cooked, not its planned cook day."""
    from mealwright.api.v1.context import Kitchen
    from mealwright.batches import portions_of, really_cooked_on
    from mealwright.models import BatchCook, Household, Login

    _dal, meal, item, day = plan_ahead(kitchen)
    batch_id = ok(
        kitchen.post(f"{API}/plan/items/{item}/batch", json={"tub_count": 2, "pattern": "pick"}),
        201,
    )["batch_id"]
    ok(kitchen.post(f"{API}/plan/batches/{batch_id}/cook", json={}), 201)
    answer_cooked(kitchen, meal)
    with db_of(kitchen) as db:
        for tub in db.scalars(select(Tub)):
            tub.amount_quarters = 0  # none spare: a new tub's use-by is worked out afresh
        db.commit()
        here = Kitchen(
            db=db,
            login=db.scalars(select(Login)).first(),  # type: ignore[arg-type]
            household=db.scalars(select(Household)).first(),  # type: ignore[arg-type]
            idempotency_key=None,
            request="",
        )
        batch = db.get(BatchCook, batch_id)
        assert batch is not None and batch.cooked_on == day
        assert really_cooked_on(here, batch) == date.today()
        assert portions_of(here, batch).use_by == date.today() + timedelta(days=3)


def test_an_undone_answer_then_a_healed_cook_then_its_undo_leaves_the_meal_planned(
    kitchen: TestClient,
) -> None:
    """F158 review: an answer that was undone no longer counts as the meal's answer."""
    from datetime import UTC, datetime

    dal, meal, item, _day = plan_ahead(kitchen, days=0)
    first = ok(cook(kitchen, item), 201)["change"]
    answer_cooked(kitchen, meal)
    ok(undo(kitchen, first["id"]))
    assert status_of(kitchen, meal) == "planned"
    again = ok(cook(kitchen, item), 201)["change"]  # this time the answer's reply is lost
    with db_of(kitchen) as db:
        for record in db.scalars(select(CookedRecord)):
            record.cooked_at = datetime.now(UTC) - timedelta(hours=1)
        db.commit()
    today = date.today().isoformat()
    ok(kitchen.get(f"{API}/plan", params={"from": today, "to": today}))
    assert status_of(kitchen, meal) == "cooked"
    ok(undo(kitchen, again["id"]))
    assert status_of(kitchen, meal) == "planned"
    assert sum(amounts(kitchen, dal["id"])) == 900_000
