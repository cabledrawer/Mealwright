"""Whole packs on the list, and another size when it leaves much less over (F183 + F204;
cabledrawer 8 and 9 Nov)."""

from typing import Any

from fastapi.testclient import TestClient
from sync_kit import changes, ok
from test_recipe_list import line
from test_recipes import food as new_food
from test_shop_from_plan import from_plan, plan, recipe

from mealwright.amounts import NBSP

API = "/api/v1"


def size(
    kitchen: TestClient, food_id: int, name: str, amount: float, usual: bool = False
) -> dict[str, Any]:
    body: dict[str, Any] = {"name": name, "amount": amount}
    if usual:
        body["usual"] = True
    created: dict[str, Any] = ok(kitchen.post(f"{API}/foods/{food_id}/sizes", json=body), 201)
    return created


def row_of(kitchen: TestClient, food_id: int) -> dict[str, Any]:
    return next(
        r for r in changes(kitchen)["items"] if r["food_id"] == food_id and not r.get("deleted")
    )


def need(kitchen: TestClient, food: dict[str, Any], amount: float, unit: str) -> dict[str, Any]:
    plan(kitchen, recipe(kitchen, f"Dish {food['name']}", line(food["id"], amount, unit)))
    from_plan(kitchen)
    return row_of(kitchen, food["id"])


def test_two_teaspoons_of_salt_is_one_whole_pack_never_2_ml(kitchen: TestClient) -> None:
    # F204 (cabledrawer's own example). Salt made from "2 tsp salt" is counted by weight (W4c's
    # first_guess, tested in test_ingredient_match), so the need is in grams and the 750 g pack
    # applies. Whole packs of a usual size were already worked out before W4c; an ingredient made
    # before W4c and counted by volume keeps doing so (W4c review L3).
    salt = new_food(kitchen, "Salt", counted_as="weight")
    size(kitchen, salt["id"], "pack", 750, usual=True)
    pack = need(kitchen, salt, 2, "tsp")["pack"]
    assert pack["packs"] == 1
    assert pack["buy"] == f"1{NBSP}pack (750{NBSP}g)"
    assert "ml" not in pack["line"]


def test_nine_hundred_grams_with_500_g_packs_is_two_packs(kitchen: TestClient) -> None:
    flour = new_food(kitchen, "Plain flour", counted_as="weight")
    size(kitchen, flour["id"], "bag", 500, usual=True)
    pack = need(kitchen, flour, 900, "g")["pack"]
    assert pack["packs"] == 2
    assert pack["line"] == f"2{NBSP}bags (500{NBSP}g) · 900{NBSP}g needed"


def test_with_no_usual_size_the_amount_stays_and_says_so(kitchen: TestClient) -> None:
    # Nothing is invented: the need stays as the amount, marked "no pack size yet", with the
    # table's sizes to pick from.
    salt = new_food(kitchen, "Salt", counted_as="weight")
    pack = need(kitchen, salt, 2, "tsp")["pack"]
    assert pack["packs"] is None
    assert pack["line"].endswith("needed · no pack size yet")
    assert [s["amount_text"] for s in pack["suggestions"]] == [
        f"750{NBSP}g",
        f"1{NBSP}kg",
        f"500{NBSP}g",
    ]
    assert pack["alternative"] is None


def coconut(kitchen: TestClient) -> dict[str, Any]:
    milk = new_food(kitchen, "Coconut milk", counted_as="volume")
    size(kitchen, milk["id"], "tin", 400, usual=True)
    size(kitchen, milk["id"], "small tin", 200)
    return milk


def test_another_size_is_suggested_when_it_leaves_much_less(kitchen: TestClient) -> None:
    milk = coconut(kitchen)
    pack = need(kitchen, milk, 600, "ml")["pack"]
    assert pack["line"] == f"2{NBSP}tins (400{NBSP}ml) · 600{NBSP}ml needed"
    other = pack["alternative"]
    assert other["buy"] == f"3{NBSP}small tins · 200{NBSP}ml"
    assert other["text"] == f"Or 3{NBSP}small tins · 200{NBSP}ml: nothing left over"
    assert other["size_id"] is not None and other["usual"] is False


def test_no_other_size_when_it_is_not_much_better(kitchen: TestClient) -> None:
    milk = coconut(kitchen)
    # 700 ml: two 400 ml tins leave 100 ml, four 200 ml tins leave 100 ml too.
    assert need(kitchen, milk, 700, "ml")["pack"]["alternative"] is None


def test_no_other_size_when_the_usual_size_leaves_nothing(kitchen: TestClient) -> None:
    milk = coconut(kitchen)
    assert need(kitchen, milk, 800, "ml")["pack"]["alternative"] is None


def test_a_line_bought_in_its_own_size_shows_that_size_and_no_suggestion(
    kitchen: TestClient,
) -> None:
    milk = coconut(kitchen)
    row = need(kitchen, milk, 600, "ml")
    small = row["pack"]["alternative"]["size_id"]
    # "Use this": the usual change of amount, in the other size.
    ok(
        kitchen.patch(
            f"{API}/shopping/items/{row['id']}", json={"amount": {"amount": 3, "size_id": small}}
        )
    )
    pack = row_of(kitchen, milk["id"])["pack"]
    assert pack["buy"] == f"3{NBSP}small tins (200{NBSP}ml)"
    assert pack["alternative"] is None
    # Working the plan out again leaves the hand-made choice alone.
    from_plan(kitchen)
    assert row_of(kitchen, milk["id"])["pack"]["buy"] == pack["buy"]


def test_the_sheet_lists_every_size_with_what_it_leaves(kitchen: TestClient) -> None:
    milk = coconut(kitchen)
    row = need(kitchen, milk, 600, "ml")
    sheet = ok(kitchen.get(f"{API}/shopping/items/{row['id']}/pack-sizes"))
    assert sheet["need"] == f"600{NBSP}ml needed"
    by_buy = {c["buy"]: c for c in sheet["choices"]}
    tins = by_buy[f"2{NBSP}tins · 400{NBSP}ml"]
    assert tins["usual"] and tins["chosen"] and tins["over"] == f"200{NBSP}ml left over"
    small = by_buy[f"3{NBSP}small tins · 200{NBSP}ml"]
    assert small["least"] and small["over"] == "nothing left over" and not small["usual"]
    assert sum(1 for c in sheet["choices"] if c["least"]) == 1
    # The table's own common sizes it has not got come last, to be made when picked.
    assert any(c["size_id"] is None for c in sheet["choices"])
    assert all(c["size_id"] is not None for c in sheet["choices"] if c["name"] != "tin")


def test_the_sheet_for_a_removed_line_or_a_staple_or_another_household(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    milk = coconut(kitchen)
    row = need(kitchen, milk, 600, "ml")
    assert neighbour.get(f"{API}/shopping/items/{row['id']}/pack-sizes").status_code == 404
    assert kitchen.get(f"{API}/shopping/items/{row['id']}/pack-sizes").status_code == 200


def test_use_this_is_undone_like_any_change_of_amount(kitchen: TestClient) -> None:
    milk = coconut(kitchen)
    row = need(kitchen, milk, 600, "ml")
    small = row["pack"]["alternative"]["size_id"]
    done = ok(
        kitchen.patch(
            f"{API}/shopping/items/{row['id']}", json={"amount": {"amount": 3, "size_id": small}}
        )
    )
    ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))
    back = row_of(kitchen, milk["id"])
    assert back["pack"]["buy"] == f"2{NBSP}tins (400{NBSP}ml)"
