"""F157 review: leftovers, "Move it" and the waiting card in a part-cooked meal go to a recipe
this press didn't cook only if nothing says otherwise. They follow the press, then the first
recipe not cooked yet, never an already-cooked one."""

from typing import Any

from fastapi.testclient import TestClient
from sync_kit import ok
from test_cooked_parts import cooked_flags, press, two_in_a_meal
from test_cooked_undo import API
from test_cooking import cook
from test_plan import slot_ids
from test_plan_writes import plan_recipe
from test_recipe_list import line
from test_recipes import make
from test_today import ago, get_today, tubs_left


def test_leftovers_with_no_item_are_the_recipe_this_press_cooked(kitchen: TestClient) -> None:
    _dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    press(kitchen, meal, khichdi)  # an earlier press
    ok(cook(kitchen, soup), 201)
    ok(
        kitchen.post(
            f"{API}/plan/meals/{meal}/cooked",
            json={"leftovers": {"count": 2, "place_kind": "fridge"}},
        )
    )
    assert {t["recipe_name"] for t in tubs_left(kitchen)} == {"Zorba soup"}


def test_the_waiting_card_offers_the_recipe_not_cooked_yet(kitchen: TestClient) -> None:
    dal, _m, _k, _s = two_in_a_meal(kitchen)
    dinner = slot_ids(kitchen)["Dinner"]
    first = plan_recipe(
        kitchen,
        make(kitchen, "Zorba rice", serves=2, lines=[line(dal["id"], 100, "g")])["id"],
        ago(kitchen, 1),
        dinner,
    )
    second = plan_recipe(
        kitchen,
        make(kitchen, "Zorba stew", serves=2, lines=[line(dal["id"], 100, "g")])["id"],
        ago(kitchen, 1),
        dinner,
    )
    ok(cook(kitchen, first["item_id"]), 201)
    waiting: list[dict[str, Any]] = get_today(kitchen)["waiting"]
    card = next(w for w in waiting if w["meal_id"] == first["meal_id"])
    assert card["leftover_item_id"] == second["item_id"]


def test_move_it_doesnt_copy_a_recipe_already_cooked(kitchen: TestClient) -> None:
    _dal, meal, khichdi, soup = two_in_a_meal(kitchen)
    press(kitchen, meal, soup)
    to = {"date": str(ago(kitchen, -1)), "slot_id": slot_ids(kitchen)["Lunch"]}
    moved = ok(kitchen.post(f"{API}/plan/meals/{meal}/moved", json=to))
    plan = ok(kitchen.get(f"{API}/plan", params={"from": to["date"], "to": to["date"]}))
    names = [i["recipe"]["name"] for m in plan["meals"] for i in m["items"]]
    assert names == ["Zorba khichdi"], (names, moved)
    assert cooked_flags(kitchen).get(soup) is True and khichdi
