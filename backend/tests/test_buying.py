"""What to buy in whole packs on a Shopping line (F120; cabledrawer 31 Oct and 7 Nov)."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sync_kit import changes, main_id, ok
from test_recipe_list import line
from test_recipes import food as new_food
from test_shop_from_plan import from_plan, plan, recipe

from mealwright.amounts import NBSP
from mealwright.buying import whole_packs

API = "/api/v1"


def size(kitchen: TestClient, food_id: int, name: str, amount: float) -> None:
    ok(kitchen.post(f"{API}/foods/{food_id}/sizes", json={"name": name, "amount": amount}), 201)


@pytest.mark.parametrize("size_g", [1, 7, 200, 400, 500, 1000])
def test_whole_packs_hold_the_need_without_a_spare_pack(size_g: int) -> None:
    for need_g in range(1, 3001, 7):
        packs = whole_packs(need_g * 1000, size_g * 1000)
        assert packs * size_g >= need_g
        assert (packs - 1) * size_g < need_g


def test_a_week_with_known_sizes_is_bought_in_whole_packs(kitchen: TestClient) -> None:
    ghee = new_food(kitchen, "Ghee")
    dal = new_food(kitchen, "Toor dal")
    coconut = new_food(kitchen, "Coconut milk", counted_as="volume")
    salt = new_food(kitchen, "Sea salt")
    for food, name, amount in [
        (ghee, "jar", 500),
        (dal, "bag", 1000),
        (coconut, "tin", 400),
        (salt, "tub", 750),
    ]:
        size(kitchen, food["id"], name, amount)
    needs = [(ghee, 120, "g"), (dal, 1.2, "kg"), (coconut, 600, "ml"), (salt, 750, "g")]
    sambar = recipe(kitchen, "Sambar", *(line(f["id"], n, u) for f, n, u in needs))
    plan(kitchen, sambar)
    from_plan(kitchen)
    rows = {r["food_id"]: r for r in changes(kitchen)["items"] if not r.get("deleted")}

    sizes = {ghee["id"]: 500, dal["id"]: 1000, coconut["id"]: 400, salt["id"]: 750}
    for food_id, row in rows.items():
        pack = row["pack"]
        need = row["amount"]
        assert pack["packs"] * sizes[food_id] >= need
        assert (pack["packs"] - 1) * sizes[food_id] < need
    assert rows[ghee["id"]]["pack"]["line"] == f"1{NBSP}jar (500{NBSP}g) · 120{NBSP}g needed"
    assert rows[dal["id"]]["pack"]["buy"] == f"2{NBSP}bags (1{NBSP}kg)"
    assert rows[coconut["id"]]["pack"]["line"] == (
        f"2{NBSP}tins (400{NBSP}ml) · 600{NBSP}ml needed"
    )
    # An exact fit is one pack, not two.
    assert rows[salt["id"]]["pack"]["packs"] == 1
    assert rows[ghee["id"]]["pack"]["suggestions"] == []

    # The plain API says the same.
    view = ok(kitchen.get(f"{API}/shopping/lists/{main_id(kitchen)}"))
    shown = [i for s in view["shops"] for a in s["aisles"] for i in a["items"]]
    assert {i["food"]["id"]: i["pack"]["line"] for i in shown} == {
        food_id: row["pack"]["line"] for food_id, row in rows.items()
    }


def test_no_size_says_the_need_and_offers_the_common_sizes(kitchen: TestClient) -> None:
    tamarind = new_food(kitchen, "Tamarind")
    sambar = recipe(kitchen, "Sambar", line(tamarind["id"], 60, "g"))
    plan(kitchen, sambar)
    from_plan(kitchen)
    row = next(r for r in changes(kitchen)["items"] if r["food_id"] == tamarind["id"])
    pack = row["pack"]
    assert pack["packs"] is None and pack["buy"] is None
    assert pack["line"] == f"60{NBSP}g needed · no pack size yet"
    assert pack["suggestions"]
    assert all(s["amount_text"] for s in pack["suggestions"])
    first = pack["suggestions"][0]
    # A tap makes it the Usual size, and the line follows.
    ok(
        kitchen.post(
            f"{API}/foods/{tamarind['id']}/sizes",
            json={"name": first["name"], "amount": first["amount"], "usual": True},
        ),
        201,
    )
    row = next(r for r in changes(kitchen)["items"] if r["food_id"] == tamarind["id"])
    assert row["pack"]["packs"] == 1  # 60 g fits in the first suggested size
    assert row["pack"]["suggestions"] == []
    assert "no pack size" not in row["pack"]["line"]


def test_a_counted_ingredient_with_no_size_has_no_pack_line(kitchen: TestClient) -> None:
    onion = new_food(kitchen, "Onion", counted_as="count")
    sambar = recipe(kitchen, "Sambar", line(onion["id"], 5))
    plan(kitchen, sambar)
    from_plan(kitchen)
    row = next(r for r in changes(kitchen)["items"] if r["food_id"] == onion["id"])
    assert row["pack"] is None


def test_a_counted_ingredient_with_a_size_rounds_up_to_whole_packs(kitchen: TestClient) -> None:
    eggs: dict[str, Any] = new_food(kitchen, "Eggs")
    size(kitchen, eggs["id"], "box", 6)
    sambar = recipe(kitchen, "Sambar", line(eggs["id"], 8))
    plan(kitchen, sambar)
    from_plan(kitchen)
    row = next(r for r in changes(kitchen)["items"] if r["food_id"] == eggs["id"])
    assert row["pack"]["line"] == f"2{NBSP}boxes (6) · 8 needed"
