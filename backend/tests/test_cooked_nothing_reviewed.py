"""cabledrawer 7 Nov: a "Cooked it" that reviews no recipe, on a meal where one recipe is cooked
and others can still be cooked, is refused naming them. A meal with nothing cooked yet still
cooks whole."""

from datetime import date
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sync_kit import ok
from test_cooked_parts import cooked_flags, press, records, two_in_a_meal
from test_cooked_undo import API, status_of
from test_plan import db_of, slot_ids
from test_recipe_list import line
from test_recipes import make

from mealwright.models import Change


def answer(client: TestClient, meal: int) -> Any:
    return client.post(f"{API}/plan/meals/{meal}/cooked", json={})


def change_count(client: TestClient) -> int:
    with db_of(client) as db:
        return int(db.scalar(select(func.count()).select_from(Change)) or 0)


def test_refused_with_one_name(kitchen: TestClient) -> None:
    _dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    press(kitchen, meal, soup)
    before = change_count(kitchen)
    reply = answer(kitchen, meal)
    assert reply.status_code == 422
    assert reply.json()["detail"] == "Zorba khichdi still needs Cooked it."
    # The meal is as it was: no change row, nothing cooked.
    assert change_count(kitchen) == before
    assert status_of(kitchen, meal) == "planned"
    assert records(kitchen) == {soup}
    assert cooked_flags(kitchen) == {khichdi: False, soup: True}


def test_refused_with_two_names(kitchen: TestClient) -> None:
    dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    third = ok(
        kitchen.post(
            f"{API}/plan/items",
            json={
                "date": date.today().isoformat(),
                "slot_id": slot_ids(kitchen)["Dinner"],
                "recipe_id": make(
                    kitchen, "Zorba rasam", serves=2, lines=[line(dal["id"], 50, "g")]
                )["id"],
                "servings": 2,
            },
        ),
        201,
    )["item_id"]
    press(kitchen, meal, third)
    before = change_count(kitchen)
    reply = answer(kitchen, meal)
    assert reply.status_code == 422
    assert reply.json()["detail"] == "Zorba khichdi and Zorba soup still need Cooked it."
    assert change_count(kitchen) == before
    assert status_of(kitchen, meal) == "planned"
    assert records(kitchen) == {third}
    assert cooked_flags(kitchen) == {khichdi: False, soup: False, third: True}


def test_a_meal_with_nothing_cooked_yet_is_cooked_whole(kitchen: TestClient) -> None:
    _dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    ok(answer(kitchen, meal))
    assert status_of(kitchen, meal) == "cooked"
    assert records(kitchen) == set()  # as before: the meal is cooked, no per-recipe records
    assert cooked_flags(kitchen) == {khichdi: True, soup: True}
