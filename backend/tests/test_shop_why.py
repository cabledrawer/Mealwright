"""Plan shopping, the server side (S3; cabledrawer 6 Nov): why each item is on the list, recipes
inside recipes on the list, and a new ingredient's aisle (F54)."""

from typing import Any

from fastapi.testclient import TestClient
from sync_kit import changes, main_id, new_id, ok, one
from test_recipe_list import line, stock
from test_recipes import food as new_food
from test_recipes import make
from test_shop_from_plan import API, day, from_plan, plan, plan_lines, recipe
from test_shopping import add

from mealwright.amounts import NBSP
from mealwright.conversions import guess_aisle

WEEK = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")


def shown(kitchen: TestClient) -> dict[str, dict[str, Any]]:
    """The main list as the screen reads it, by ingredient name."""
    view = ok(kitchen.get(f"{API}/shopping/lists/{main_id(kitchen)}"))
    return {
        i["food"]["name"]: i
        for shop in view["shops"]
        for rows in (shop["in_trolley"], *(a["items"] for a in shop["aisles"]))
        for i in rows
    }


def size(kitchen: TestClient, food_id: int, name: str, amount: float, **extra: Any) -> None:
    ok(
        kitchen.post(
            f"{API}/foods/{food_id}/sizes", json={"name": name, "amount": amount, **extra}
        ),
        201,
    )


def weekday(kitchen: TestClient, n: int) -> str:
    return WEEK[day(kitchen, n).weekday()]


# --- Why it is there -----------------------------------------------------------------------------


def test_a_plan_item_says_which_recipes_and_days_need_it(kitchen: TestClient) -> None:
    onion = new_food(kitchen, "Why onion")
    sambar = recipe(kitchen, "Sambar", line(onion["id"], 2, "count"))
    rasam = recipe(kitchen, "Rasam", line(onion["id"], 1, "count"))
    plan(kitchen, sambar, 1)
    plan(kitchen, sambar, 3)
    plan(kitchen, rasam, 2)
    why = shown(kitchen)["Why onion"]["why"]
    one, two, three = (weekday(kitchen, n) for n in (1, 2, 3))
    assert why == f"Sambar ({one}, {three}) · Rasam ({two})"


def test_a_typed_item_says_added_by_you(kitchen: TestClient) -> None:
    milk = new_food(kitchen, "Why milk")
    row = add(kitchen, main_id(kitchen), milk["id"], amount={"amount": 200, "unit": "g"})
    assert row["item"]["why"] == "Added by you"
    assert shown(kitchen)["Why milk"]["why"] == "Added by you"


def test_a_pack_bigger_than_the_need_says_what_is_needed(kitchen: TestClient) -> None:
    ghee = new_food(kitchen, "Why ghee")
    size(kitchen, ghee["id"], "jar", 500, usual=True)
    sambar = recipe(kitchen, "Sambar", line(ghee["id"], 120, "g"))
    plan(kitchen, sambar, 1)
    why = shown(kitchen)["Why ghee"]["why"]
    assert why == f"120{NBSP}g needed · Sambar ({weekday(kitchen, 1)})"


def test_a_pack_that_fits_the_need_says_nothing_extra(kitchen: TestClient) -> None:
    ghee = new_food(kitchen, "Why exact ghee")
    size(kitchen, ghee["id"], "jar", 500, usual=True)
    sambar = recipe(kitchen, "Sambar", line(ghee["id"], 500, "g"))
    plan(kitchen, sambar, 1)
    assert shown(kitchen)["Why exact ghee"]["why"] == f"Sambar ({weekday(kitchen, 1)})"


def test_no_pack_size_is_said_after_the_recipes(kitchen: TestClient) -> None:
    tamarind = new_food(kitchen, "Why tamarind")
    sambar = recipe(kitchen, "Sambar", line(tamarind["id"], 60, "g"))
    plan(kitchen, sambar, 1)
    assert shown(kitchen)["Why tamarind"]["why"] == f"Sambar ({weekday(kitchen, 1)}) · no pack size"


# --- Recipes inside recipes ----------------------------------------------------------------------


def curry_with(kitchen: TestClient, inner: dict[str, Any]) -> int:
    body = {
        "name": "Why curry",
        "lines": [{"kind": "ingredient", "words": "masala", "recipe_id": inner["id"]}],
    }
    return int(ok(kitchen.post(f"{API}/recipes", json=body), 201)["id"])


def test_an_inner_recipe_is_expanded_into_its_ingredients(kitchen: TestClient) -> None:
    cumin = new_food(kitchen, "Why cumin")
    inner = make(kitchen, "Why masala", lines=[line(cumin["id"], 50, "g")])
    plan(kitchen, curry_with(kitchen, inner), 1)
    assert [r["food_id"] for r in plan_lines(kitchen)] == [cumin["id"]]
    assert shown(kitchen)["Why cumin"]["amount"]["amount"] == 50
    assert shown(kitchen)["Why cumin"]["why"].startswith("Why curry")  # the recipe that is planned


def test_inner_recipes_inside_inner_recipes_are_expanded_too(kitchen: TestClient) -> None:
    seed = new_food(kitchen, "Why seed")
    deepest = make(kitchen, "Why deepest", lines=[line(seed["id"], 10, "g")])
    middle = make(
        kitchen,
        "Why middle",
        lines=[{"kind": "ingredient", "words": "d", "recipe_id": deepest["id"]}],
    )
    plan(kitchen, curry_with(kitchen, middle), 1)
    assert [r["food_id"] for r in plan_lines(kitchen)] == [seed["id"]]


def test_a_made_ahead_inner_recipe_in_the_pantry_is_not_expanded(kitchen: TestClient) -> None:
    flour = new_food(kitchen, "Why flour")
    batter = make(
        kitchen,
        "Why batter",
        made_ahead=True,
        makes={"amount": 2, "unit": "l"},
        lines=[line(flour["id"], 300, "g")],
    )
    stock(kitchen, batter["homemade"]["id"], 1500, "ml")
    plan(kitchen, curry_with(kitchen, batter), 1)
    assert plan_lines(kitchen) == []


def test_a_made_ahead_inner_recipe_not_in_the_pantry_is_expanded(kitchen: TestClient) -> None:
    flour = new_food(kitchen, "Why other flour")
    batter = make(
        kitchen,
        "Why other batter",
        made_ahead=True,
        makes={"amount": 2, "unit": "l"},
        lines=[line(flour["id"], 300, "g")],
    )
    plan(kitchen, curry_with(kitchen, batter), 1)
    assert [r["food_id"] for r in plan_lines(kitchen)] == [flour["id"]]
    from_plan(kitchen)


# --- F54: an aisle for a new ingredient ----------------------------------------------------------


def test_the_aisle_is_guessed_from_the_bundled_table(kitchen: TestClient) -> None:
    made = new_food(kitchen, "Basmati rice")
    found = ok(kitchen.get(f"{API}/foods/{made['id']}"))
    assert found["aisle"] == guess_aisle("Basmati rice") != "other"


def test_the_aisle_is_guessed_from_a_name_inside_the_name(kitchen: TestClient) -> None:
    assert guess_aisle("Organic basmati rice") == guess_aisle("basmati rice") != "other"
    made = new_food(kitchen, "Organic basmati rice")
    assert ok(kitchen.get(f"{API}/foods/{made['id']}"))["aisle"] == guess_aisle("basmati rice")


def test_an_unknown_name_falls_back_to_other(kitchen: TestClient) -> None:
    assert guess_aisle("Zzyzx qwerty") == "other"
    made = new_food(kitchen, "Zzyzx qwerty")
    assert ok(kitchen.get(f"{API}/foods/{made['id']}"))["aisle"] == "other"


def test_a_typed_new_ingredient_on_the_list_gets_a_guessed_aisle(kitchen: TestClient) -> None:
    result = one(
        kitchen,
        "add",
        list_id=main_id(kitchen),
        item_id=new_id(),
        new_food={"name": "Organic basmati rice", "counted_as": "weight"},
    )
    assert result["status"] == "applied"
    got = result["_answer"]["changes"]
    row = next(f for f in got["foods"] if f["id"] == result["food_id"])
    assert row["aisle"] == guess_aisle("basmati rice") != "other"
    other = one(
        kitchen,
        "add",
        list_id=main_id(kitchen),
        item_id=new_id(),
        new_food={"name": "Zzyzx qwerty", "counted_as": "weight"},
    )
    found = next(f for f in other["_answer"]["changes"]["foods"] if f["id"] == other["food_id"])
    assert found["aisle"] == "other"


def test_openapi_says_every_item_has_a_why(kitchen: TestClient) -> None:
    schemas = kitchen.get(f"{API}/openapi.json").json()["components"]["schemas"]
    assert schemas["ItemOut"]["properties"]["why"]["type"] == "string"


def test_a_quick_pick_size_reaches_the_next_pull_so_the_screen_follows(
    kitchen: TestClient,
) -> None:
    """The computer's "Usual pack?" quick pick adds a size with POST /foods/{id}/sizes; the
    list's next "changes since" must carry the ingredient (with its size) and the line."""
    tamarind = new_food(kitchen, "Why pick tamarind")
    plan(kitchen, recipe(kitchen, "Sambar", line(tamarind["id"], 60, "g")), 1)
    before = changes(kitchen)
    row = next(r for r in before["items"] if r["food_id"] == tamarind["id"])
    pick = row["pack"]["suggestions"][0]
    ok(
        kitchen.post(
            f"{API}/foods/{tamarind['id']}/sizes",
            json={"name": pick["name"], "amount": pick["amount"], "usual": True},
        ),
        201,
    )
    after = changes(kitchen, since=before["cursor"])
    food = next(f for f in before["foods"] if f["id"] == tamarind["id"])
    newer = [f for f in after["foods"] if f["id"] == tamarind["id"]]
    assert newer and any(s["usual"] for s in newer[0]["sizes"]), (food, after["foods"])


# --- "Make it a staple?" (cabledrawer 7 Nov) ---------------------------------------------------------


def offered(kitchen: TestClient, name: str) -> bool:
    return bool(shown(kitchen)[name]["staple_offer"])


def test_a_tiny_need_of_a_best_before_ingredient_offers_a_staple(kitchen: TestClient) -> None:
    sugar = new_food(kitchen, "Sugar")  # the pack-size table says: best before, 500 g to 2 kg
    plan(kitchen, recipe(kitchen, "Tea", line(sugar["id"], 5, "g")), 1)
    assert offered(kitchen, "Sugar")


def test_a_need_of_a_twentieth_or_more_does_not_offer_it(kitchen: TestClient) -> None:
    sugar = new_food(kitchen, "Sugar")  # smallest pack 500 g: 25 g is exactly a twentieth
    plan(kitchen, recipe(kitchen, "Tea", line(sugar["id"], 25, "g")), 1)
    assert not offered(kitchen, "Sugar")


def test_the_households_smaller_pack_counts(kitchen: TestClient) -> None:
    sugar = new_food(kitchen, "Sugar")
    size(kitchen, sugar["id"], "sachet", 10, usual=True)
    plan(kitchen, recipe(kitchen, "Tea", line(sugar["id"], 5, "g")), 1)
    assert not offered(kitchen, "Sugar")  # 5 g of a 10 g pack


def test_use_by_and_unknown_ingredients_never_offer_it(kitchen: TestClient) -> None:

    from mealwright.pack_sizes import table

    use_by = next(r for r in table().rows.values() if r.dates == "use by" and r.sizes)
    plain = new_food(kitchen, use_by.names[0] if use_by.names else use_by.key.replace("_", " "))
    odd = new_food(kitchen, "Zzyzx qwerty")
    plan(kitchen, recipe(kitchen, "Odd", line(plain["id"], 1, "g"), line(odd["id"], 1, "g")), 1)
    view = shown(kitchen)
    assert not any(row["staple_offer"] for row in view.values())


def test_a_loop_of_recipes_on_the_list_stops_and_still_lists_the_rest(kitchen: TestClient) -> None:
    """Saving refuses a loop, but one that got in another way must not hang the list (S3 r1 L4)."""
    from mealwright.models import RecipeLine

    seed = new_food(kitchen, "Why loop seed")
    inner = make(kitchen, "Why loop inner", lines=[line(seed["id"], 10, "g")])
    outer = curry_with(kitchen, inner)
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(
            RecipeLine(
                household_id=1,
                recipe_id=inner["id"],
                position=1,
                kind="ingredient",
                words="back to the curry",
                sub_recipe_id=outer,
            )
        )
        db.commit()
    plan(kitchen, outer, 1)
    assert [r["food_id"] for r in plan_lines(kitchen)] == [seed["id"]]
    assert shown(kitchen)["Why loop seed"]["amount"]["amount"] == 10
