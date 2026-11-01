"""One ingredient in several places counts as one total (F101, cabledrawer 31 Oct): for a recipe's
"in the pantry", for what Shopping buys, and for Running low."""

from typing import Any

from fastapi.testclient import TestClient
from test_pantry import add, group
from test_pantry import food as pantry_food
from test_recipe_list import line, row, stock
from test_recipes import food as new_food
from test_recipes import make
from test_shop_from_plan import amounts, plan, recipe

API = "/api/v1"


def new_place(kitchen: TestClient, name: str, kind: str = "cupboard") -> int:
    made = kitchen.post(f"{API}/places", json={"name": name, "kind": kind})
    assert made.status_code == 201, made.text
    return int(made.json()["id"])


def test_a_recipe_counts_what_is_in_all_the_places(kitchen: TestClient) -> None:
    rice = new_food(kitchen, "Spread rice")
    garage = new_place(kitchen, "Garage")
    stock(kitchen, rice["id"], 150, "g")  # the ingredient's own default place
    stock(kitchen, rice["id"], 150, "g", place_id=garage)  # and a place made just now
    make(kitchen, "Enough together", lines=[line(rice["id"], 300, "g")])
    make(kitchen, "Too much", lines=[line(rice["id"], 301, "g")])
    assert row(kitchen, "Enough together")["stock"]["can_cook_now"] is True
    assert row(kitchen, "Too much")["stock"]["can_cook_now"] is False


def test_shopping_buys_only_what_is_missing_from_the_total(kitchen: TestClient) -> None:
    rice = new_food(kitchen, "Spread rice")
    garage = new_place(kitchen, "Garage")
    stock(kitchen, rice["id"], 150, "g")
    stock(kitchen, rice["id"], 150, "g", place_id=garage)
    plan(kitchen, recipe(kitchen, "Big pot", line(rice["id"], 500, "g")))
    assert amounts(kitchen) == {rice["id"]: 200}  # 500 g needed, 300 g in two places


def test_running_low_looks_at_the_total_in_every_place(kitchen: TestClient) -> None:
    toor: dict[str, Any] = pantry_food(kitchen, "Spread dal", counted_as="weight")
    kitchen.patch(
        f"{API}/foods/{toor['id']}", json={"running_low_at": {"amount": 300, "unit": "g"}}
    )
    garage = new_place(kitchen, "Garage")
    add(kitchen, toor["id"], 200, "g")
    add(kitchen, toor["id"], 200, "g", place_id=garage)
    # 200 g in each is under 300 g in either place, but 400 g together is not low.
    assert [g["running_low"] for g in _groups(kitchen, "Spread dal")] == [False, False]
    lot = _groups(kitchen, "Spread dal")[0]["lots"][0]
    kitchen.post(f"{API}/stock/{lot['id']}/left", json={"amount": {"amount": 50, "unit": "g"}})
    assert [g["running_low"] for g in _groups(kitchen, "Spread dal")] == [True, True]
    assert group(kitchen, "Spread dal")["running_low"] is True


def _groups(kitchen: TestClient, name: str) -> list[dict[str, Any]]:
    found = []
    for place in kitchen.get(f"{API}/pantry").json()["places"]:
        found += [g for g in place["groups"] if g["food"]["name"] == name]
    return found
