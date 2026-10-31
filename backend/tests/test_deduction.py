"""The deduction engine (0.7 K2; spec section 2, "Cooking — how deduction works"): what "Cooked it"
would take, rule by rule, read through the proposal endpoint. It changes nothing (see
test_cooking.py for the confirm). One thorough test for each rule, then stand-ins, inner recipes
and ask-once."""

from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sync_kit import ok
from test_plan import db_of, slot_ids
from test_recipe_list import line, place_id, stock
from test_recipes import food, make

from mealwright.amounts import NBSP
from mealwright.models import StockLot

API = "/api/v1"
DAY = date.today() + timedelta(days=2)


def plan_item(
    client: TestClient, recipe: dict[str, Any], servings: int | None = None, day: date = DAY
) -> int:
    body: dict[str, Any] = {
        "date": day.isoformat(),
        "slot_id": slot_ids(client)["Dinner"],
        "recipe_id": recipe["id"],
    }
    if servings is not None:
        body["servings"] = servings
    return int(ok(client.post(f"{API}/plan/items", json=body), 201)["item_id"])


def recipe_of(client: TestClient, lines: list[dict[str, Any]], serves: int = 4) -> dict[str, Any]:
    return make(client, "Zorba curry", serves=serves, lines=lines)


def propose(client: TestClient, item_id: int, **body: Any) -> dict[str, Any]:
    result: dict[str, Any] = ok(client.post(f"{API}/plan/items/{item_id}/cook/preview", json=body))
    return result


def row_of(proposal: dict[str, Any], name: str) -> dict[str, Any]:
    return next(r for r in proposal["rows"] if (r["food"] or r["recipe"] or {}).get("name") == name)


# --- Rule 2: scale to what was cooked ----------------------------------------------------------


def test_rule_2_the_amount_is_scaled_to_the_portions_cooked(kitchen: TestClient) -> None:
    dal = food(kitchen, "Zorba dal")
    stock(kitchen, dal["id"], 800, "g")
    item = plan_item(kitchen, recipe_of(kitchen, [line(dal["id"], 200, "g")]), servings=2)
    # The meal's own servings (2 of the recipe's 4) are the default.
    row = row_of(propose(kitchen, item), "Zorba dal")
    assert row["needed"]["amount"] == 100
    assert [t["amount"]["amount"] for t in row["takes"]] == [100]
    assert (row["takes"][0]["before"]["amount"], row["takes"][0]["after"]["amount"]) == (800, 700)
    # Portions can be said: 8 of a recipe for 4 is double.
    assert row_of(propose(kitchen, item, portions=8), "Zorba dal")["needed"]["amount"] == 400
    # The proposal changes nothing.
    assert row_of(propose(kitchen, item), "Zorba dal")["takes"][0]["before"]["amount"] == 800


def test_rule_2_a_recipe_with_no_serves_is_taken_as_written(kitchen: TestClient) -> None:
    dal = food(kitchen, "Zorba dal")
    stock(kitchen, dal["id"], 800, "g")
    batter = make(kitchen, "Zorba batter", serves=None, lines=[line(dal["id"], 300, "g")])
    item = plan_item(kitchen, batter)
    assert row_of(propose(kitchen, item, portions=3), "Zorba dal")["needed"]["amount"] == 300


def test_rule_2_lines_of_one_ingredient_are_added_up_into_one_row(kitchen: TestClient) -> None:
    onion = food(kitchen, "Zorba onion", counted_as="count")
    stock(kitchen, onion["id"], 5, "count")
    recipe = recipe_of(
        kitchen,
        [line(onion["id"], 1, None), line(onion["id"], 2, None, words="sliced onions")],
    )
    result = propose(kitchen, plan_item(kitchen, recipe, servings=4))
    rows = [r for r in result["rows"] if r["food"]]
    assert len(rows) == 1 and len(rows[0]["lines"]) == 2
    assert rows[0]["needed"]["amount"] == 3
    assert (rows[0]["takes"][0]["before"]["amount"], rows[0]["takes"][0]["after"]["amount"]) == (
        5,
        2,
    )


def test_rule_2_a_counted_ingredient_is_rounded_to_the_nearest_half(kitchen: TestClient) -> None:
    onion = food(kitchen, "Zorba onion", counted_as="count")
    egg = food(kitchen, "Zorba egg", counted_as="count")
    stock(kitchen, onion["id"], 5, "count")
    stock(kitchen, egg["id"], 5, "count")
    recipe = recipe_of(kitchen, [line(onion["id"], 1, None), line(egg["id"], 3, None)])
    item = plan_item(kitchen, recipe)
    # 1 onion for 4, cooked for 1: a quarter, but never none: half.
    small = propose(kitchen, item, portions=1)
    assert row_of(small, "Zorba onion")["needed"]["amount"] == 0.5
    assert row_of(small, "Zorba egg")["needed"]["amount"] == 1  # 0.75 -> 1
    # 3 eggs for 4, cooked for 2: 1.5, kept.
    assert row_of(propose(kitchen, item, portions=2), "Zorba egg")["needed"]["amount"] == 1.5


# --- Rule 3: convert only when the units differ -----------------------------------------------


def test_rule_3_the_same_kind_of_unit_converts_by_fixed_maths(kitchen: TestClient) -> None:
    dal = food(kitchen, "Zorba dal")
    milk = food(kitchen, "Zorba milk", counted_as="volume")
    stock(kitchen, dal["id"], 2000, "g")
    stock(kitchen, milk["id"], 2000, "ml")
    recipe = recipe_of(kitchen, [line(dal["id"], 0.5, "kg"), line(milk["id"], 2, "tbsp")])
    result = propose(kitchen, plan_item(kitchen, recipe, servings=4))
    assert row_of(result, "Zorba dal")["needed"]["amount"] == 500  # kg -> g
    assert row_of(result, "Zorba milk")["needed"]["amount"] == 30  # 1 tbsp = 15 ml


def test_rule_3_volume_to_weight_uses_the_household_answer_over_the_table(
    kitchen: TestClient,
) -> None:
    flour = food(kitchen, "Plain flour")  # the bundled table knows it: 528 mg a ml
    stock(kitchen, flour["id"], 1000, "g")
    item = plan_item(kitchen, recipe_of(kitchen, [line(flour["id"], 1, "cup")]), servings=4)
    from_table = row_of(propose(kitchen, item), "Plain flour")
    assert from_table["status"] == "take" and from_table["ask"] is None
    assert from_table["needed"]["amount"] == 132  # 250 ml x 0.528
    # The household's own answer wins.
    ok(kitchen.patch(f"{API}/foods/{flour['id']}", json={"cup_weight": 100}))
    assert row_of(propose(kitchen, item), "Plain flour")["needed"]["amount"] == 100


def test_rule_3_count_to_weight_uses_the_weight_of_one_item(kitchen: TestClient) -> None:
    onion = food(kitchen, "Onion")  # the table: one weighs 110 g
    stock(kitchen, onion["id"], 5, "count")
    item = plan_item(kitchen, recipe_of(kitchen, [line(onion["id"], 220, "g")]), servings=4)
    row = row_of(propose(kitchen, item), "Onion")
    assert row["needed"]["amount"] == 2
    ok(kitchen.patch(f"{API}/foods/{onion['id']}", json={"item_weight": 80}))
    assert row_of(propose(kitchen, item), "Onion")["needed"]["amount"] == 3  # 2.75, to the half


def test_rule_3_a_size_the_line_uses_is_its_own_amount(kitchen: TestClient) -> None:
    ghee = food(kitchen, "Zorba ghee")
    stock(kitchen, ghee["id"], 500, "g")
    size = ok(
        kitchen.post(f"{API}/foods/{ghee['id']}/sizes", json={"name": "tub", "amount": 250}), 201
    )
    tub = next(s for s in size["food"]["sizes"] if s["name"] == "tub")
    recipe = recipe_of(
        kitchen, [{"words": "ghee", "food_id": ghee["id"], "amount": 1, "size_id": tub["id"]}]
    )
    assert (
        row_of(propose(kitchen, plan_item(kitchen, recipe, servings=4)), "Zorba ghee")["needed"][
            "amount"
        ]
        == 250
    )


def test_rule_3_a_line_that_cannot_be_compared_or_has_no_amount_is_not_worked_out(
    kitchen: TestClient,
) -> None:
    salt = food(kitchen, "Zorba salt")
    chilli = food(kitchen, "Zorba chilli")
    stock(kitchen, salt["id"], 500, "g")
    stock(kitchen, chilli["id"], 500, "g")
    recipe = recipe_of(
        kitchen,
        [
            {"words": "salt to taste", "food_id": salt["id"]},
            line(chilli["id"], 1, "pinch"),
            {"words": "a lime I forgot to link"},
        ],
    )
    result = propose(kitchen, plan_item(kitchen, recipe))
    assert row_of(result, "Zorba salt")["status"] == "no_amount"
    assert row_of(result, "Zorba chilli")["status"] == "no_amount"
    assert [r["status"] for r in result["rows"] if r["food"] is None] == ["not_linked"]
    assert all(r["takes"] == [] and r["use"] is False for r in result["rows"])


def test_rule_3_an_unknown_conversion_asks_once_and_the_reply_is_used(kitchen: TestClient) -> None:
    toor = food(kitchen, "Zorba toor")  # not in the table
    stock(kitchen, toor["id"], 1000, "g")
    item = plan_item(kitchen, recipe_of(kitchen, [line(toor["id"], 1, "cup")]), servings=4)
    asked = row_of(propose(kitchen, item), "Zorba toor")
    assert asked["status"] == "ask" and asked["takes"] == [] and asked["needed"] is None
    assert asked["ask"]["kind"] == "weight_per_ml"
    assert asked["ask"]["question"] == f"About how much does 1{NBSP}cup of Zorba toor weigh?"
    assert asked["ask"]["suggested"] == 200
    # The reply is worked in (the proposal itself remembers nothing).
    answer = {"kind": "weight_per_ml", "food_id": toor["id"], "grams": 210}
    answered = row_of(propose(kitchen, item, answers=[answer]), "Zorba toor")
    assert answered["status"] == "take" and answered["needed"]["amount"] == 210
    assert row_of(propose(kitchen, item), "Zorba toor")["status"] == "ask"


# --- Rule 4: the packet that goes off first, the freezer left alone --------------------------


def test_rule_4_the_packet_that_goes_off_first_is_used_first(kitchen: TestClient) -> None:
    rice = food(kitchen, "Zorba rice")
    stock(kitchen, rice["id"], 300, "g", use_by=(DAY + timedelta(days=9)).isoformat())
    stock(kitchen, rice["id"], 300, "g")  # no date: after the dated ones
    stock(kitchen, rice["id"], 300, "g", use_by=(DAY + timedelta(days=2)).isoformat())
    item = plan_item(kitchen, recipe_of(kitchen, [line(rice["id"], 400, "g")]), servings=4)
    take = row_of(propose(kitchen, item), "Zorba rice")["takes"][0]
    assert [(lot["use_by"], lot["amount"]["amount"]) for lot in take["lots"]] == [
        ((DAY + timedelta(days=2)).isoformat(), 300),
        ((DAY + timedelta(days=9)).isoformat(), 100),
    ]
    assert take["before"]["amount"] == 900 and take["after"]["amount"] == 500


def test_rule_4_two_packets_with_the_same_date_go_in_the_order_they_were_added(
    kitchen: TestClient,
) -> None:
    rice = food(kitchen, "Zorba rice")
    day = DAY.isoformat()
    stock(kitchen, rice["id"], 300, "g", use_by=day)
    stock(kitchen, rice["id"], 500, "g", use_by=day)
    item = plan_item(kitchen, recipe_of(kitchen, [line(rice["id"], 100, "g")]), servings=4)
    lots = row_of(propose(kitchen, item), "Zorba rice")["takes"][0]["lots"]
    assert [lot["amount"]["amount"] for lot in lots] == [100]
    with db_of(kitchen) as db:
        first_added = min(lot.id for lot in db.query(StockLot).filter_by(food_id=rice["id"]))
    assert lots[0]["lot_id"] == first_added


def test_rule_4_the_freezer_is_left_alone_unless_the_person_says(kitchen: TestClient) -> None:
    peas = food(kitchen, "Zorba peas")
    stock(kitchen, peas["id"], 100, "g")
    stock(kitchen, peas["id"], 300, "g", place_id=place_id(kitchen, "Freezer"))
    item = plan_item(
        kitchen,
        make(kitchen, "Zorba peas curry", serves=4, lines=[line(peas["id"], 250, "g")]),
        servings=4,
    )
    row = row_of(propose(kitchen, item), "Zorba peas")
    assert row["takes"][0]["amount"]["amount"] == 100  # the fridge/cupboard packet only
    assert row["short"]["amount"] == 150
    assert row["in_freezer"]["amount"] == 300  # waiting, left alone


def test_rule_4_a_frozen_packet_with_the_earliest_date_still_waits(kitchen: TestClient) -> None:
    peas = food(kitchen, "Zorba peas")
    stock(kitchen, peas["id"], 300, "g", use_by=(DAY + timedelta(days=30)).isoformat())
    stock(
        kitchen,
        peas["id"],
        300,
        "g",
        use_by=(DAY + timedelta(days=1)).isoformat(),
        place_id=place_id(kitchen, "Freezer"),
    )
    item = plan_item(
        kitchen,
        make(kitchen, "Zorba peas curry", serves=4, lines=[line(peas["id"], 200, "g")]),
        servings=4,
    )
    lot = row_of(propose(kitchen, item), "Zorba peas")["takes"][0]["lots"][0]
    assert lot["place"]["name"] != "Freezer"


# --- Rule 6: staples never, never below zero --------------------------------------------------


def test_rule_6_a_staple_is_never_taken(kitchen: TestClient) -> None:
    oil = food(kitchen, "Zorba oil", staple=True)
    item = plan_item(kitchen, recipe_of(kitchen, [line(oil["id"], 2, "tbsp")]), servings=4)
    row = row_of(propose(kitchen, item), "Zorba oil")
    assert row["status"] == "staple" and row["takes"] == [] and row["use"] is False
    assert row["short"] is None


def test_rule_6_stock_never_goes_below_zero_and_the_shortfall_is_offered(
    kitchen: TestClient,
) -> None:
    dal = food(kitchen, "Zorba dal")
    stock(kitchen, dal["id"], 150, "g")
    item = plan_item(kitchen, recipe_of(kitchen, [line(dal["id"], 200, "g")]), servings=4)
    row = row_of(propose(kitchen, item), "Zorba dal")
    assert row["takes"][0]["amount"]["amount"] == 150  # everything there is
    assert row["takes"][0]["after"]["amount"] == 0
    assert row["short"]["amount"] == 50  # "add to list"
    assert row["status"] == "take" and row["use"] is True and row["make_first"] is False


def test_rule_6_nothing_in_the_pantry_starts_off_and_all_of_it_is_missing(
    kitchen: TestClient,
) -> None:
    dal = food(kitchen, "Zorba dal")
    item = plan_item(kitchen, recipe_of(kitchen, [line(dal["id"], 200, "g")]), servings=4)
    row = row_of(propose(kitchen, item), "Zorba dal")
    assert row["status"] == "none_in_pantry" and row["takes"] == [] and row["use"] is False
    assert row["short"]["amount"] == 200


def test_rule_6_a_packet_that_is_part_used_is_taken_exactly(kitchen: TestClient) -> None:
    dal = food(kitchen, "Zorba dal")
    size = ok(
        kitchen.post(f"{API}/foods/{dal['id']}/sizes", json={"name": "packet", "amount": 500}), 201
    )
    packet = next(s for s in size["food"]["sizes"] if s["name"] == "packet")
    ok(
        kitchen.post(
            f"{API}/stock",
            json={"food_id": dal["id"], "amount": {"amount": 2, "size_id": packet["id"]}},
        ),
        201,
    )
    item = plan_item(kitchen, recipe_of(kitchen, [line(dal["id"], 130, "g")]), servings=4)
    take = row_of(propose(kitchen, item), "Zorba dal")["takes"][0]
    assert (take["before"]["amount"], take["after"]["amount"]) == (1000, 870)
    assert take["lots"][0]["amount"]["amount"] == 130  # the lot is left at 370 g, not rounded


# --- Stand-ins ("Can use instead") ------------------------------------------------------------


def _stand_in(kitchen: TestClient, food_id: int, stand_in_id: int) -> None:
    ok(kitchen.post(f"{API}/foods/{food_id}/stand-ins", json={"food_id": stand_in_id}), 201)


def test_a_stand_in_is_taken_from_when_the_ingredient_has_none(kitchen: TestClient) -> None:
    onion = food(kitchen, "Zorba onion", counted_as="count")
    red = food(kitchen, "Zorba red onion", counted_as="count")
    _stand_in(kitchen, onion["id"], red["id"])
    stock(kitchen, red["id"], 4, "count")
    item = plan_item(kitchen, recipe_of(kitchen, [line(onion["id"], 2, None)]), servings=4)
    row = row_of(propose(kitchen, item), "Zorba onion")
    assert row["status"] == "take" and row["use"] is True and row["short"] is None
    assert [(t["food"]["name"], t["stand_in"], t["amount"]["amount"]) for t in row["takes"]] == [
        ("Zorba red onion", True, 2)
    ]


def test_a_stand_in_is_never_mixed_in_when_the_ingredient_has_some(kitchen: TestClient) -> None:
    onion = food(kitchen, "Zorba onion", counted_as="count")
    red = food(kitchen, "Zorba red onion", counted_as="count")
    _stand_in(kitchen, onion["id"], red["id"])
    stock(kitchen, onion["id"], 1, "count")
    stock(kitchen, red["id"], 5, "count")
    item = plan_item(kitchen, recipe_of(kitchen, [line(onion["id"], 3, None)]), servings=4)
    row = row_of(propose(kitchen, item), "Zorba onion")
    # cabledrawer 31 Oct: take what there is and offer the rest to buy; the stand-in stays out.
    assert [(t["food"]["name"], t["stand_in"], t["amount"]["amount"]) for t in row["takes"]] == [
        ("Zorba onion", False, 1)
    ]
    assert row["short"]["amount"] == 2 and row["add_to_list"] is True


def test_stock_only_in_the_freezer_is_shown_with_use_off_and_no_stand_in(
    kitchen: TestClient,
) -> None:
    onion = food(kitchen, "Zorba onion", counted_as="count")
    red = food(kitchen, "Zorba red onion", counted_as="count")
    _stand_in(kitchen, onion["id"], red["id"])
    stock(kitchen, onion["id"], 4, "count", place_id=place_id(kitchen, "Freezer"))
    stock(kitchen, red["id"], 5, "count")
    item = plan_item(kitchen, recipe_of(kitchen, [line(onion["id"], 2, None)]), servings=4)
    row = row_of(propose(kitchen, item), "Zorba onion")
    assert row["use"] is False and row["takes"] == [] and row["in_freezer"]["amount"] == 4


def test_two_packets_with_one_use_by_the_opened_one_goes_first(kitchen: TestClient) -> None:
    rice = food(kitchen, "Zorba rice")
    size = ok(
        kitchen.post(f"{API}/foods/{rice['id']}/sizes", json={"name": "bag", "amount": 500}), 201
    )
    bag = next(s for s in size["food"]["sizes"] if s["name"] == "bag")
    day = DAY.isoformat()
    for _ in range(2):
        ok(
            kitchen.post(
                f"{API}/stock",
                json={
                    "food_id": rice["id"],
                    "amount": {"amount": 1, "size_id": bag["id"]},
                    "use_by": day,
                },
            ),
            201,
        )
    with db_of(kitchen) as db:
        lots = list(db.query(StockLot).filter_by(food_id=rice["id"]).order_by(StockLot.id))
        lots[1].amount_milli = 300_000  # the later one was opened
        opened = lots[1].id
        db.commit()
    item = plan_item(kitchen, recipe_of(kitchen, [line(rice["id"], 100, "g")]), servings=4)
    lot = row_of(propose(kitchen, item), "Zorba rice")["takes"][0]["lots"][0]
    assert lot["lot_id"] == opened


def test_a_packet_that_would_be_left_with_under_2_percent_is_used_all(kitchen: TestClient) -> None:
    rice = food(kitchen, "Zorba rice")
    size = ok(
        kitchen.post(f"{API}/foods/{rice['id']}/sizes", json={"name": "bag", "amount": 500}), 201
    )
    bag = next(s for s in size["food"]["sizes"] if s["name"] == "bag")
    ok(
        kitchen.post(
            f"{API}/stock",
            json={"food_id": rice["id"], "amount": {"amount": 1, "size_id": bag["id"]}},
        ),
        201,
    )
    item = plan_item(kitchen, recipe_of(kitchen, [line(rice["id"], 495, "g")]), servings=4)
    take = row_of(propose(kitchen, item), "Zorba rice")["takes"][0]
    assert take["amount"]["amount"] == 500 and take["lots"][0]["used_all"] is True
    # 3 % left is not.
    item2 = plan_item(
        kitchen,
        recipe_of(kitchen, [line(rice["id"], 485, "g")]),
        servings=4,
        day=DAY + timedelta(days=1),
    )
    take = row_of(propose(kitchen, item2), "Zorba rice")["takes"][0]
    assert take["amount"]["amount"] == 485 and take["lots"][0]["used_all"] is False


def test_a_stand_in_counted_another_way_is_not_used(kitchen: TestClient) -> None:
    onion = food(kitchen, "Zorba onion", counted_as="count")
    paste = food(kitchen, "Zorba onion paste")  # by weight
    _stand_in(kitchen, onion["id"], paste["id"])
    stock(kitchen, paste["id"], 500, "g")
    item = plan_item(kitchen, recipe_of(kitchen, [line(onion["id"], 2, None)]), servings=4)
    row = row_of(propose(kitchen, item), "Zorba onion")
    assert row["takes"] == [] and row["short"]["amount"] == 2 and row["status"] == "none_in_pantry"


def test_the_link_goes_one_way(kitchen: TestClient) -> None:
    onion = food(kitchen, "Zorba onion", counted_as="count")
    red = food(kitchen, "Zorba red onion", counted_as="count")
    _stand_in(kitchen, onion["id"], red["id"])  # red onion can stand in for onion
    stock(kitchen, onion["id"], 4, "count")
    item = plan_item(kitchen, recipe_of(kitchen, [line(red["id"], 2, None)]), servings=4)
    row = row_of(propose(kitchen, item), "Zorba red onion")
    assert row["takes"] == [] and row["short"]["amount"] == 2


# --- Recipes inside recipes -------------------------------------------------------------------


def test_an_inner_recipe_with_stock_is_taken_from_the_pantry(kitchen: TestClient) -> None:
    batter = make(kitchen, "Zorba batter", made_ahead=True, makes={"amount": 2, "unit": "l"})
    stock(kitchen, batter["homemade"]["id"], 1500, "ml")
    dosa = recipe_of(
        kitchen, [{"words": "batter", "amount": 500, "unit": "ml", "recipe_id": batter["id"]}]
    )
    row = row_of(propose(kitchen, plan_item(kitchen, dosa, servings=4)), "Zorba batter")
    assert row["food"]["name"] == "Zorba batter" and row["recipe"] == {
        "id": batter["id"],
        "name": "Zorba batter",
    }
    assert row["takes"][0]["amount"]["amount"] == 500 and row["make_first"] is False


def test_an_inner_recipe_with_none_in_the_pantry_offers_make_it_first(kitchen: TestClient) -> None:
    batter = make(kitchen, "Zorba batter", made_ahead=True, makes={"amount": 2, "unit": "l"})
    dosa = recipe_of(
        kitchen, [{"words": "batter", "amount": 500, "unit": "ml", "recipe_id": batter["id"]}]
    )
    row = row_of(propose(kitchen, plan_item(kitchen, dosa, servings=4)), "Zorba batter")
    assert row["status"] == "none_in_pantry" and row["make_first"] is True and row["use"] is False
    assert row["short"]["amount"] == 500


def test_an_inner_recipe_that_is_not_made_ahead_offers_make_it_first(kitchen: TestClient) -> None:
    podi = make(kitchen, "Zorba podi")
    sambar = recipe_of(
        kitchen, [{"words": "podi", "amount": 2, "unit": "tbsp", "recipe_id": podi["id"]}]
    )
    result = propose(kitchen, plan_item(kitchen, sambar))
    [row] = result["rows"]
    assert row["status"] == "make_first" and row["make_first"] is True
    assert row["food"] is None and row["recipe"]["name"] == "Zorba podi" and row["takes"] == []


def test_an_inner_recipe_with_some_stock_takes_it_and_offers_to_make_the_rest(
    kitchen: TestClient,
) -> None:
    batter = make(kitchen, "Zorba batter", made_ahead=True, makes={"amount": 2, "unit": "l"})
    stock(kitchen, batter["homemade"]["id"], 300, "ml")
    dosa = recipe_of(
        kitchen, [{"words": "batter", "amount": 500, "unit": "ml", "recipe_id": batter["id"]}]
    )
    row = row_of(propose(kitchen, plan_item(kitchen, dosa, servings=4)), "Zorba batter")
    assert row["takes"][0]["amount"]["amount"] == 300
    assert row["short"]["amount"] == 200 and row["make_first"] is True


# --- Households ---------------------------------------------------------------------------------


def test_another_households_item_and_foods_are_not_found(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    dal = food(kitchen, "Zorba dal")
    item = plan_item(kitchen, recipe_of(kitchen, [line(dal["id"], 200, "g")]))
    assert neighbour.post(f"{API}/plan/items/{item}/cook/preview", json={}).status_code == 404
    mine = plan_item(kitchen, recipe_of(kitchen, [line(dal["id"], 200, "g")]))
    answer = {
        "kind": "item_weight",
        "food_id": food(neighbour, "Next door's thing")["id"],
        "grams": 5,
    }
    # A food of the other household in `answers` is not found; the same id from its own side is.
    assert (
        kitchen.post(
            f"{API}/plan/items/{mine}/cook/preview", json={"answers": [answer]}
        ).status_code
        == 404
    )
