"""K3, the "Cooked it" review: what the screen needs on top of K2's engine (all additions). The
estimate mark, the question in the pantry's unit, about half a packet, the note "2 cloves" (F89),
"Bought some — used them", a new answer replacing an old one (F106), and one ingredient in two
places counted as one total (F101)."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_cooking import FAR, _batch, amounts, cook
from test_cooking_review import list_lines
from test_deduction import plan_item, propose, recipe_of, row_of
from test_plan import db_of
from test_recipe_list import line, place_id, stock
from test_recipes import food

from mealwright.models import CookedRecord, FoodConversion, FoodSize

API = "/api/v1"


def test_a_row_is_marked_an_estimate_only_when_the_units_were_changed(kitchen: TestClient) -> None:
    flour = food(kitchen, "Plain flour")  # the table knows a cup of it
    rice = food(kitchen, "Zorba rice")
    milk = food(kitchen, "Zorba milk", counted_as="volume")
    for each, unit in ((flour, "g"), (rice, "g"), (milk, "ml")):
        stock(kitchen, each["id"], 1000, unit)
    recipe = recipe_of(
        kitchen,
        [line(flour["id"], 1, "cup"), line(rice["id"], 1, "kg"), line(milk["id"], 2, "tbsp")],
    )
    result = propose(kitchen, plan_item(kitchen, recipe, servings=4))
    assert row_of(result, "Plain flour")["estimate"] is True  # a cup in grams
    assert row_of(result, "Zorba rice")["estimate"] is False  # kg to g is fixed maths
    # Each side keeps its own unit: the recipe's words, amount and unit as written.
    assert [(r["amount"], r["unit"]) for r in row_of(result, "Plain flour")["lines"]] == [
        ("1", "cup")
    ]
    assert [(r["amount"], r["unit"]) for r in row_of(result, "Zorba milk")["lines"]] == [
        ("2", "tbsp")
    ]
    assert [row_of(result, n)["unit"] for n in ("Plain flour", "Zorba milk")] == ["g", "ml"]
    assert row_of(result, "Zorba milk")["estimate"] is False  # tbsp to ml too


def test_a_question_says_what_the_recipe_asks_for_on_its_own_side(kitchen: TestClient) -> None:
    toor = food(kitchen, "Zorba toor")  # not in the table: asks
    stock(kitchen, toor["id"], 1000, "g")
    item = plan_item(kitchen, recipe_of(kitchen, [line(toor["id"], 2, "cup")]), servings=2)
    asked = row_of(propose(kitchen, item), "Zorba toor")
    assert asked["status"] == "ask"
    # 2 cups for 4, cooked for 2: 1 cup, 250 ml.
    assert asked["ask_need"] == {"amount": 250, "unit": "ml"}
    assert asked["half"]["amount"] == 500  # about half of the 1 kg packet... of what is there
    answered = row_of(
        propose(
            kitchen, item, answers=[{"kind": "weight_per_ml", "food_id": toor["id"], "grams": 200}]
        ),
        "Zorba toor",
    )
    assert answered["status"] == "take" and answered["estimate"] is True
    assert answered["ask_need"] is None


def test_a_count_pantry_asks_the_item_weight_and_a_row_of_mixed_units_asks_the_old_way(
    kitchen: TestClient,
) -> None:
    lime = food(kitchen, "Zorba lime", counted_as="count")
    stock(kitchen, lime["id"], 4, "count")
    mixed = food(kitchen, "Zorba paste")
    stock(kitchen, mixed["id"], 500, "g")
    recipe = recipe_of(
        kitchen,
        [
            line(lime["id"], 100, "g"),
            line(mixed["id"], 1, "cup"),
            line(mixed["id"], 2, None, words="2 of it"),
        ],
    )
    result = propose(kitchen, plan_item(kitchen, recipe, servings=4))
    assert row_of(result, "Zorba lime")["ask_need"] == {"amount": 100, "unit": "g"}
    assert row_of(result, "Zorba lime")["half"]["amount"] == 2
    assert row_of(result, "Zorba paste")["status"] == "ask"
    assert row_of(result, "Zorba paste")["ask_need"] is None  # a cup and a count in one row


def test_the_note_two_cloves_is_offered_as_a_count(kitchen: TestClient) -> None:
    garlic = food(kitchen, "Zorba garlic")
    stock(kitchen, garlic["id"], 100, "g")
    recipe = recipe_of(
        kitchen, [{"words": "garlic", "food_id": garlic["id"], "note": "2 cloves, minced"}]
    )
    item = plan_item(kitchen, recipe, servings=4)
    row = row_of(propose(kitchen, item), "Zorba garlic")
    assert row["status"] == "no_amount" and row["use"] is False
    assert row["count_note"] == {"count": 2, "word": "clove"}
    # Cooked for 8 of 4: double.
    assert row_of(propose(kitchen, item, portions=8), "Zorba garlic")["count_note"]["count"] == 4
    other = recipe_of(kitchen, [{"words": "garlic", "food_id": garlic["id"], "note": "minced"}])
    assert row_of(propose(kitchen, plan_item(kitchen, other)), "Zorba garlic")["count_note"] is None


def test_a_typed_amount_with_a_size_answer_learns_the_clove_and_a_new_answer_replaces_it(
    kitchen: TestClient,
) -> None:
    garlic = food(kitchen, "Zorba garlic")
    stock(kitchen, garlic["id"], 100, "g")
    recipe = recipe_of(kitchen, [{"words": "garlic", "food_id": garlic["id"], "note": "2 cloves"}])
    key = f"food:{garlic['id']}"

    def clove(grams: float) -> dict[str, Any]:
        return {"kind": "size", "food_id": garlic["id"], "name": "clove", "amount": grams}

    # 10 g for 2 cloves: a clove is 5 g.
    item = plan_item(kitchen, recipe, servings=4, day=FAR)
    ok(
        cook(
            kitchen, item, [{"key": key, "used": {"amount": 10, "unit": "g"}}], answers=[clove(5)]
        ),
        201,
    )
    with db_of(kitchen) as db:
        sizes = list(db.scalars(select(FoodSize).where(FoodSize.food_id == garlic["id"])))
        assert [(s.name, s.amount_milli) for s in sizes] == [("clove", 5000)]
    # Another day, another answer: it replaces the old one.
    again = plan_item(kitchen, recipe, servings=4, day=FAR + timedelta(days=1))
    ok(
        cook(
            kitchen, again, [{"key": key, "used": {"amount": 12, "unit": "g"}}], answers=[clove(6)]
        ),
        201,
    )
    with db_of(kitchen) as db:
        sizes = list(db.scalars(select(FoodSize).where(FoodSize.food_id == garlic["id"])))
        assert [(s.name, s.amount_milli) for s in sizes] == [("clove", 6000)]


def test_a_remembered_answer_in_the_review_replaces_the_old_one_and_off_is_not_kept(
    kitchen: TestClient,
) -> None:
    toor = food(kitchen, "Zorba toor")
    stock(kitchen, toor["id"], 2000, "g")
    recipe = recipe_of(kitchen, [line(toor["id"], 1, "cup")])
    first = plan_item(kitchen, recipe, servings=4, day=FAR)
    answer = {"kind": "weight_per_ml", "food_id": toor["id"], "grams": 200, "remember": True}
    ok(cook(kitchen, first, [], answers=[answer]), 201)

    def learned() -> list[int]:
        with db_of(kitchen) as db:
            return [
                c.value_milli
                for c in db.scalars(
                    select(FoodConversion).where(FoodConversion.food_id == toor["id"])
                )
            ]

    assert learned() == [800]  # 200 g in a 250 ml cup: 800 mg a ml
    second = plan_item(kitchen, recipe, servings=4, day=FAR + timedelta(days=1))
    ok(cook(kitchen, second, [], answers=[{**answer, "grams": 220}]), 201)
    assert learned() == [880]  # the new answer replaced the old
    third = plan_item(kitchen, recipe, servings=4, day=FAR + timedelta(days=2))
    ok(cook(kitchen, third, [], answers=[{**answer, "grams": 100, "remember": False}]), 201)
    assert learned() == [880]  # used for this cook only


def test_bought_some_takes_nothing_and_the_record_keeps_it(kitchen: TestClient) -> None:
    shallot = food(kitchen, "Zorba shallot", counted_as="count")  # none in the pantry
    recipe = recipe_of(kitchen, [line(shallot["id"], 8, None)])
    item = plan_item(kitchen, recipe, servings=4, day=FAR)
    key = f"food:{shallot['id']}"
    row = row_of(propose(kitchen, item), "Zorba shallot")
    assert row["status"] == "none_in_pantry" and row["use"] is False
    done = ok(cook(kitchen, item, [{"key": key, "bought": True}]), 201)
    chosen = next(c for c in done["cooked"]["snapshot"]["choices"] if c["key"] == key)
    assert chosen["bought"] is True and chosen["use"] is False and chosen["used_milli"] == 0
    with db_of(kitchen) as db:
        assert db.scalars(select(CookedRecord)).one().snapshot["choices"][0]["bought"] is True
    assert list_lines(kitchen, shallot["id"]) == []  # bought: nothing is added to the list
    # Without it, the record says it was not bought.
    plain = plan_item(kitchen, recipe, servings=4, day=FAR + timedelta(days=1))
    done = ok(cook(kitchen, plain, []), 201)
    assert done["cooked"]["snapshot"]["choices"][0]["bought"] is False


def test_bought_some_is_refused_with_use_on_an_amount_a_staple_or_no_ingredient(
    kitchen: TestClient,
) -> None:
    shallot = food(kitchen, "Zorba shallot", counted_as="count")
    salt = food(kitchen, "Zorba salt", staple=True)
    recipe = recipe_of(
        kitchen, [line(shallot["id"], 8, None), line(salt["id"], 1, "g"), {"words": "a lime"}]
    )
    item = plan_item(kitchen, recipe, servings=4, day=FAR)
    key = f"food:{shallot['id']}"
    for choice in (
        {"key": key, "bought": True, "use": True},
        {"key": key, "bought": True, "used": {"amount": 1, "unit": "count"}},
    ):
        assert cook(kitchen, item, [choice]).status_code == 422
    assert cook(kitchen, item, [{"key": f"food:{salt['id']}", "bought": True}]).status_code == 422
    line_row = next(r for r in propose(kitchen, item)["rows"] if r["food"] is None)
    assert cook(kitchen, item, [{"key": line_row["key"], "bought": True}]).status_code == 422


def test_one_ingredient_in_two_places_is_one_total_in_the_review(kitchen: TestClient) -> None:
    # F101: Shopping counts stock in every place as one total; so does "Cooked it".
    dal = food(kitchen, "Zorba dal")
    stock(kitchen, dal["id"], 300, "g", place_id=place_id(kitchen, "Fridge"))
    stock(kitchen, dal["id"], 500, "g", place_id=place_id(kitchen, "Cupboard"))
    item = plan_item(kitchen, recipe_of(kitchen, [line(dal["id"], 400, "g")]), servings=4, day=FAR)
    rows = [r for r in propose(kitchen, item)["rows"] if r["food"]]
    assert len(rows) == 1
    take = rows[0]["takes"][0]
    assert (take["before"]["amount"], take["amount"]["amount"], take["after"]["amount"]) == (
        800,
        400,
        400,
    )
    assert sorted(lot["place"]["name"] for lot in take["lots"]) == ["Cupboard", "Fridge"]
    assert rows[0]["short"] is None


def test_a_cooked_batch_cannot_be_taken_off_the_plan_until_cooked_it_is_undone(
    kitchen: TestClient,
) -> None:
    _, _, batch, _ = _batch(kitchen)
    done = ok(kitchen.post(f"{API}/plan/batches/{batch}/cook", json={}), 201)
    refused = kitchen.delete(f"{API}/plan/batches/{batch}")
    assert (refused.status_code, refused.json()["code"]) == (409, "already_cooked")
    assert refused.json()["detail"].startswith("This was cooked on ")
    assert refused.json()["detail"].endswith("Undo “Cooked it” first.")
    ok(kitchen.get(f"{API}/plan/batches/{batch}/cooked"))  # the record is still there
    ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))
    ok(kitchen.delete(f"{API}/plan/batches/{batch}"))  # now it can go


def _sizes(client: TestClient, food_id: int) -> dict[str, int]:
    with db_of(client) as db:
        found = db.scalars(select(FoodSize).where(FoodSize.food_id == food_id))
        return {s.name: s.amount_milli for s in found}


def test_a_size_answer_from_the_pantry_never_changes_an_existing_size(kitchen: TestClient) -> None:
    rice = food(kitchen, "Zorba rice")
    ok(kitchen.post(f"{API}/foods/{rice['id']}/sizes", json={"name": "bag", "amount": 1000}), 201)
    answer = {"kind": "size", "food_id": rice["id"], "name": "bag", "amount": 5}
    body = {"food_id": rice["id"], "amount": {"amount": 1, "unit": "bag", "answers": [answer]}}
    ok(kitchen.post(f"{API}/stock", json=body), 201)
    assert _sizes(kitchen, rice["id"]) == {"bag": 1_000_000}


def test_a_cook_replaces_only_the_size_its_note_asked_about_and_undo_puts_it_back(
    kitchen: TestClient,
) -> None:
    garlic = food(kitchen, "Zorba garlic")
    stock(kitchen, garlic["id"], 100, "g")
    for name, amount in (("clove", 4), ("bag", 1000)):
        ok(
            kitchen.post(
                f"{API}/foods/{garlic['id']}/sizes", json={"name": name, "amount": amount}
            ),
            201,
        )
    recipe = recipe_of(kitchen, [{"words": "garlic", "food_id": garlic["id"], "note": "2 cloves"}])
    item = plan_item(kitchen, recipe, servings=4, day=FAR)

    def size(name: str, amount: float) -> dict[str, Any]:
        return {"kind": "size", "food_id": garlic["id"], "name": name, "amount": amount}

    typed = [{"key": f"food:{garlic['id']}", "used": {"amount": 12, "unit": "g"}}]
    done = ok(cook(kitchen, item, typed, answers=[size("clove", 6), size("bag", 5)]), 201)
    assert _sizes(kitchen, garlic["id"]) == {"clove": 6000, "bag": 1_000_000}
    ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))
    assert _sizes(kitchen, garlic["id"]) == {"clove": 4000, "bag": 1_000_000}


def test_garlic_counted_by_number_asks_in_its_own_word_and_learns_a_fraction_of_one(
    kitchen: TestClient,
) -> None:
    garlic = food(kitchen, "Zorba garlic", counted_as="count")
    ok(kitchen.patch(f"{API}/foods/{garlic['id']}", json={"count_word": "bulb"}))
    stock(kitchen, garlic["id"], 3, "count")
    recipe = recipe_of(kitchen, [{"words": "garlic", "food_id": garlic["id"], "note": "2 cloves"}])
    item = plan_item(kitchen, recipe, servings=4, day=FAR)
    row = row_of(propose(kitchen, item), "Zorba garlic")
    assert (row["unit"], row["unit_word"]) == ("count", "bulbs")
    assert row["half"]["amount"] == 1.5  # half of what is left of the packet with no size
    # Half a bulb for 2 cloves: a clove is a quarter of a bulb.
    typed = [{"key": f"food:{garlic['id']}", "used": {"amount": 0.5, "unit": "count"}}]
    clove = {"kind": "size", "food_id": garlic["id"], "name": "clove", "amount": 0.25}
    ok(cook(kitchen, item, typed, answers=[clove]), 201)
    assert _sizes(kitchen, garlic["id"]) == {"clove": 250}
    assert amounts(kitchen, garlic["id"]) == [2_500]


def test_an_older_cooks_undo_leaves_a_size_a_later_cook_changed_and_says_partly(
    kitchen: TestClient,
) -> None:
    garlic = food(kitchen, "Zorba garlic")
    stock(kitchen, garlic["id"], 100, "g")
    ok(kitchen.post(f"{API}/foods/{garlic['id']}/sizes", json={"name": "clove", "amount": 4}), 201)
    recipe = recipe_of(kitchen, [{"words": "garlic", "food_id": garlic["id"], "note": "2 cloves"}])
    key = f"food:{garlic['id']}"
    typed = [{"key": key, "used": {"amount": 10, "unit": "g"}}]

    def clove(grams: float) -> list[dict[str, Any]]:
        return [{"kind": "size", "food_id": garlic["id"], "name": "clove", "amount": grams}]

    first = ok(
        cook(kitchen, plan_item(kitchen, recipe, servings=4, day=FAR), typed, answers=clove(5)), 201
    )
    later = plan_item(kitchen, recipe, servings=4, day=FAR + timedelta(days=1))
    second = ok(cook(kitchen, later, typed, answers=clove(6)), 201)
    undone = ok(kitchen.post(f"{API}/changes/{first['change']['id']}/undo"))
    assert undone["result"] == "partly"
    assert undone["message"].endswith(
        "A later cook changed the size of a clove, so it was left as it is."
    )
    assert _sizes(kitchen, garlic["id"]) == {"clove": 6000}  # the later cook's size stays
    assert ok(kitchen.post(f"{API}/changes/{second['change']['id']}/undo"))["result"] == "done"
    assert _sizes(kitchen, garlic["id"]) == {"clove": 5000}


def test_a_note_count_that_is_too_long_or_not_plain_digits_is_not_a_count(
    kitchen: TestClient,
) -> None:
    garlic = food(kitchen, "Zorba garlic")
    stock(kitchen, garlic["id"], 100, "g")
    for note in (f"{'9' * 29} cloves", "٣٣٣٣٣٣٣٣٣٣٣٣٣٣٣٣٣٣٣٣٣٣٣٣٣٣٣٣٣ cloves", "12345 cloves"):
        recipe = recipe_of(kitchen, [{"words": "garlic", "food_id": garlic["id"], "note": note}])
        item = plan_item(kitchen, recipe, servings=4, day=FAR)
        row = row_of(propose(kitchen, item), "Zorba garlic")
        assert row["count_note"] is None, note
        assert cook(kitchen, item, []).status_code == 201, note
    recipe = recipe_of(kitchen, [{"words": "garlic", "food_id": garlic["id"], "note": "3 cloves"}])
    item = plan_item(kitchen, recipe, servings=4, day=FAR)
    assert row_of(propose(kitchen, item), "Zorba garlic")["count_note"] == {
        "count": 3,
        "word": "clove",
    }


def test_a_choice_key_that_is_not_plain_digits_is_refused_cleanly(kitchen: TestClient) -> None:
    garlic = food(kitchen, "Zorba garlic")
    recipe = recipe_of(kitchen, [{"words": "garlic", "food_id": garlic["id"]}])
    item = plan_item(kitchen, recipe, servings=4, day=FAR)
    for key in ("food:²", "food:" + "9" * 30, "food:٣", "food:-1", "food:"):
        reply = cook(kitchen, item, [{"key": key, "used": {"amount": 1, "unit": "g"}}])
        assert reply.status_code == 422, key
        assert reply.json()["code"] == "no_ingredient", key
