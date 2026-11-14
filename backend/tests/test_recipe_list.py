"""The All recipes list (docs/dev/api-0.4-recipes.md, section 4): A to Z, search (names, tags,
ingredient names and other names, never the method), tags, "Can cook now", the stock hints,
nutrition that stays unknown, and a fixed number of queries however many recipes there are.
The other household is in test_recipes_isolation.py."""

from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import event
from sync_kit import ok
from test_recipes import food, make, save

API = "/api/v1"


def today(kitchen: TestClient) -> date:
    return date.fromisoformat(ok(kitchen.get(f"{API}/household"))["today"])


def stock(kitchen: TestClient, food_id: int, amount: float, unit: str, **extra: Any) -> None:
    body = {"food_id": food_id, "amount": {"amount": amount, "unit": unit}, **extra}
    ok(kitchen.post(f"{API}/stock", json=body), 201)


def fresh(kitchen: TestClient, name: str, **fields: Any) -> dict[str, Any]:
    """An ingredient whose date is a Use by one (0.8): Use soon nudges only for those, and a
    table row such as spinach says Best before."""
    made = food(kitchen, name, **fields)
    if not made["date_kind_locked"]:
        ok(kitchen.patch(f"{API}/foods/{made['id']}", json={"date_kind": "use_by"}))
    return made


def place_id(kitchen: TestClient, name: str) -> int:
    return next(p["id"] for p in kitchen.get(f"{API}/places").json() if p["name"] == name)


def listing(kitchen: TestClient, **params: Any) -> dict[str, Any]:
    result: dict[str, Any] = ok(kitchen.get(f"{API}/recipes", params=params))
    return result


def names(kitchen: TestClient, **params: Any) -> list[str]:
    return [r["name"] for r in listing(kitchen, **params)["recipes"]]


def row(kitchen: TestClient, name: str) -> dict[str, Any]:
    return next(r for r in listing(kitchen, limit=500)["recipes"] if r["name"] == name)


def line(food_id: int, amount: Any, unit: str | None = None, **extra: Any) -> dict[str, Any]:
    return {"words": "x", "food_id": food_id, "amount": amount, "unit": unit, **extra}


# --- The row -----------------------------------------------------------------------------------


def test_the_list_is_a_to_z_ignoring_case_and_accents(kitchen: TestClient) -> None:
    for name in ["rasam", "Éclair", "Dosa", "chana masala", "Biryani"]:
        make(kitchen, name)
    assert names(kitchen) == ["Biryani", "chana masala", "Dosa", "Éclair", "rasam"]


def test_time_and_kcal_are_there_only_when_known(kitchen: TestClient) -> None:
    make(kitchen, "Sambar", time_minutes=50, nutrition={"kcal": 320})
    make(kitchen, "Rajma", time_minutes=60)
    make(kitchen, "Zero", nutrition={"kcal": 0})
    sambar, rajma, zero = (row(kitchen, n) for n in ["Sambar", "Rajma", "Zero"])
    assert (sambar["time_minutes"], sambar["kcal"]) == (50, 320)
    assert (rajma["time_minutes"], rajma["kcal"]) == (60, None)  # unknown, never 0
    assert zero["kcal"] == 0 and zero["time_minutes"] is None  # a real zero stays a zero


def test_the_title_count_is_every_recipe_whatever_is_filtered(kitchen: TestClient) -> None:
    make(kitchen, "Sambar", tags=["Quick"])
    make(kitchen, "Rasam")
    answer = listing(kitchen, tag="Quick")
    assert (answer["total"], answer["all_recipes"]) == (1, 2)
    gone = make(kitchen, "Old")
    ok(kitchen.delete(f"{API}/recipes/{gone['id']}"))
    assert listing(kitchen)["all_recipes"] == 2


# --- Stock hints -------------------------------------------------------------------------------


def test_enough_for_the_recipe_when_the_amounts_can_be_compared(kitchen: TestClient) -> None:
    rice = fresh(kitchen, "Zorba rice")
    stock(kitchen, rice["id"], 500, "g")
    make(kitchen, "Small", lines=[line(rice["id"], 200, "g")])
    make(kitchen, "Exact", lines=[line(rice["id"], 0.5, "kg")])
    make(kitchen, "Big", lines=[line(rice["id"], 600, "g")])
    assert row(kitchen, "Small")["stock"] == {"counted": 1, "missing": 0, "can_cook_now": True}
    assert row(kitchen, "Exact")["stock"]["can_cook_now"] is True
    assert row(kitchen, "Big")["stock"] == {"counted": 1, "missing": 1, "can_cook_now": False}


def test_two_lines_for_the_same_ingredient_are_added_up(kitchen: TestClient) -> None:
    rice = fresh(kitchen, "Zorba rice")
    stock(kitchen, rice["id"], 200, "g")
    make(kitchen, "Twice", lines=[line(rice["id"], 100, "g"), line(rice["id"], 150, "g")])
    assert row(kitchen, "Twice")["stock"] == {"counted": 1, "missing": 1, "can_cook_now": False}


def test_any_stock_counts_when_the_amounts_cannot_be_compared(kitchen: TestClient) -> None:
    grain = food(kitchen, "Zorba grain")  # no known weight for a cup
    other = food(kitchen, "Zorba seeds")
    stock(kitchen, grain["id"], 5, "g")
    make(kitchen, "Cups", lines=[line(grain["id"], 3, "cup")])
    make(kitchen, "Pinch", lines=[line(grain["id"], 1, "pinch")])
    make(kitchen, "Nothing", lines=[line(other["id"], 3, "cup")])
    assert row(kitchen, "Cups")["stock"]["can_cook_now"] is True
    assert row(kitchen, "Pinch")["stock"]["can_cook_now"] is True
    assert row(kitchen, "Nothing")["stock"] == {"counted": 1, "missing": 1, "can_cook_now": False}


def test_a_cup_is_compared_once_its_weight_is_known(kitchen: TestClient) -> None:
    grain = food(kitchen, "Zorba grain")
    ok(kitchen.patch(f"{API}/foods/{grain['id']}", json={"cup_weight": 200}))
    stock(kitchen, grain["id"], 500, "g")
    make(kitchen, "Two cups", lines=[line(grain["id"], 2, "cup")])
    make(kitchen, "Three cups", lines=[line(grain["id"], 3, "cup")])
    assert row(kitchen, "Two cups")["stock"]["can_cook_now"] is True  # 400 g of 500 g
    assert row(kitchen, "Three cups")["stock"]["can_cook_now"] is False  # 600 g of 500 g


def test_sizes_and_counted_ingredients(kitchen: TestClient) -> None:
    dal = food(kitchen, "Zorba dal")
    packet = ok(
        kitchen.post(f"{API}/foods/{dal['id']}/sizes", json={"name": "packet", "amount": 500}), 201
    )["food"]["sizes"][0]
    stock(kitchen, dal["id"], 1, "packet")
    eggs = food(kitchen, "Zorba eggs", counted_as="count")
    stock(kitchen, eggs["id"], 2, "count")
    make(kitchen, "One packet", lines=[line(dal["id"], 1, size_id=packet["id"])])
    make(kitchen, "Two packets", lines=[line(dal["id"], 2, size_id=packet["id"])])
    make(kitchen, "Two eggs", lines=[line(eggs["id"], 2)])
    make(kitchen, "Three eggs", lines=[line(eggs["id"], 3)])
    assert row(kitchen, "One packet")["stock"]["can_cook_now"] is True
    assert row(kitchen, "Two packets")["stock"]["can_cook_now"] is False
    assert row(kitchen, "Two eggs")["stock"]["can_cook_now"] is True
    assert row(kitchen, "Three eggs")["stock"]["can_cook_now"] is False


def test_a_staple_is_always_in_stock_and_the_freezer_counts(kitchen: TestClient) -> None:
    salt = food(kitchen, "Zorba salt", staple=True)
    peas = food(kitchen, "Zorba peas")
    stock(kitchen, peas["id"], 300, "g", place_id=place_id(kitchen, "Freezer"))
    make(kitchen, "Peas", lines=[line(salt["id"], 1, "tsp"), line(peas["id"], 200, "g")])
    assert row(kitchen, "Peas")["stock"] == {"counted": 2, "missing": 0, "can_cook_now": True}


def test_lines_without_an_amount_and_headings_never_count(kitchen: TestClient) -> None:
    rice = fresh(kitchen, "Zorba rice")
    nothing = food(kitchen, "Zorba nothing")
    stock(kitchen, rice["id"], 500, "g")
    make(
        kitchen,
        "Plain",
        lines=[
            {"kind": "heading", "words": "For the rice"},
            line(rice["id"], 100, "g"),
            {"words": "salt to taste", "food_id": nothing["id"]},  # no amount, nothing in stock
            {"words": "a handful of coriander"},  # not linked at all
        ],
    )
    make(kitchen, "Only words", lines=[{"words": "salt to taste", "food_id": nothing["id"]}])
    make(kitchen, "Empty")
    assert row(kitchen, "Plain")["stock"] == {"counted": 1, "missing": 0, "can_cook_now": True}
    # Nothing counts: no hint, and not "Can cook now" (there is nothing to say it can be cooked).
    assert row(kitchen, "Only words")["stock"] is None
    assert row(kitchen, "Empty")["stock"] is None
    assert names(kitchen, can_cook_now=True) == ["Plain"]


def test_a_made_ahead_recipe_is_checked_through_its_own_ingredient(kitchen: TestClient) -> None:
    batter = make(kitchen, "Dosa batter", made_ahead=True, makes={"amount": 2, "unit": "litres"})
    make(
        kitchen,
        "Dosa",
        lines=[{"words": "batter", "amount": 2, "unit": "cup", "recipe_id": batter["id"]}],
    )
    # The made-ahead batter has no stock yet.
    dosa = row(kitchen, "Dosa")
    assert dosa["stock"] == {"counted": 1, "missing": 1, "can_cook_now": False}
    assert dosa["stock_unchecked"] is False
    stock(kitchen, batter["homemade"]["id"], 1500, "ml")
    dosa = row(kitchen, "Dosa")
    assert dosa["stock"] == {"counted": 1, "missing": 0, "can_cook_now": True}
    assert dosa["stock_unchecked"] is False
    assert names(kitchen, can_cook_now="true") == ["Dosa"]


def test_a_recipe_using_an_unchecked_recipe_is_never_all_in_stock_or_can_cook_now(
    kitchen: TestClient,
) -> None:
    """cabledrawer 20 Oct: a recipe that uses another recipe that isn't made ahead is left out of
    Can cook now and never says "all in stock"; inner recipes are checked in a later version."""
    rice = fresh(kitchen, "Zorba rice")
    dal = food(kitchen, "Zorba dal")
    stock(kitchen, rice["id"], 500, "g")
    base = make(kitchen, "Plain base")
    make(
        kitchen,
        "Everything else here",
        lines=[
            line(rice["id"], 100, "g"),
            {"words": "base", "amount": 1, "unit": "cup", "recipe_id": base["id"]},
        ],
    )
    make(
        kitchen,
        "One missing",
        lines=[
            line(rice["id"], 100, "g"),
            line(dal["id"], 100, "g"),
            {"words": "base", "amount": 1, "unit": "cup", "recipe_id": base["id"]},
        ],
    )
    # A line with no amount is ignored, whatever it points at (cabledrawer 20 Oct, question 13).
    make(kitchen, "Only the base", lines=[{"words": "base", "recipe_id": base["id"]}])
    make(
        kitchen,
        "Rice and some base",
        lines=[line(rice["id"], 100, "g"), {"words": "base", "recipe_id": base["id"]}],
    )
    everything = row(kitchen, "Everything else here")
    assert everything["stock"] == {"counted": 1, "missing": 0, "can_cook_now": False}
    assert everything["stock_unchecked"] is True
    one_missing = row(kitchen, "One missing")
    assert one_missing["stock"] == {"counted": 2, "missing": 1, "can_cook_now": False}
    assert one_missing["stock_unchecked"] is True
    only = row(kitchen, "Only the base")
    assert only["stock"] is None and only["stock_unchecked"] is False
    some = row(kitchen, "Rice and some base")
    assert some["stock"] == {"counted": 1, "missing": 0, "can_cook_now": True}
    assert some["stock_unchecked"] is False
    # The inner recipe itself is a plain recipe with no lines: nothing unchecked.
    assert row(kitchen, "Plain base")["stock_unchecked"] is False
    stock(kitchen, dal["id"], 500, "g")
    assert names(kitchen, can_cook_now="true") == ["Rice and some base"]
    assert row(kitchen, "Everything else here")["stock"]["can_cook_now"] is False


def test_made_ahead_without_a_pantry_ingredient_or_removed_is_unchecked(
    kitchen: TestClient,
) -> None:
    """cabledrawer 20 Oct: both count as "can't be checked", like a recipe that isn't made ahead."""
    batter = make(kitchen, "Dosa batter", made_ahead=True)
    save(kitchen, batter, made_ahead=False)
    gone = make(kitchen, "Gone base")
    make(
        kitchen,
        "Uses batter",
        lines=[{"words": "b", "amount": 1, "unit": "cup", "recipe_id": batter["id"]}],
    )
    make(
        kitchen,
        "Uses gone",
        lines=[{"words": "g", "amount": 1, "unit": "cup", "recipe_id": gone["id"]}],
    )
    ok(kitchen.delete(f"{API}/recipes/{gone['id']}"))
    assert row(kitchen, "Uses batter")["stock_unchecked"] is True
    assert row(kitchen, "Uses gone")["stock_unchecked"] is True


def test_two_levels_deep_the_outer_recipe_is_unchecked_and_the_middle_one_is_checked(
    kitchen: TestClient,
) -> None:
    batter = make(kitchen, "Dosa batter", made_ahead=True, makes={"amount": 2, "unit": "litres"})
    stock(kitchen, batter["homemade"]["id"], 1500, "ml")
    middle = make(
        kitchen,
        "Middle",
        lines=[{"words": "batter", "amount": 1, "unit": "cup", "recipe_id": batter["id"]}],
    )
    make(
        kitchen,
        "Outer",
        lines=[{"words": "middle", "amount": 1, "unit": "cup", "recipe_id": middle["id"]}],
    )
    assert row(kitchen, "Middle")["stock"] == {"counted": 1, "missing": 0, "can_cook_now": True}
    assert row(kitchen, "Middle")["stock_unchecked"] is False
    assert row(kitchen, "Outer")["stock"] is None
    assert row(kitchen, "Outer")["stock_unchecked"] is True
    assert names(kitchen, can_cook_now="true") == ["Middle"]


def test_a_made_ahead_recipe_that_uses_an_unchecked_one_is_still_checked_by_its_stock(
    kitchen: TestClient,
) -> None:
    tempering = make(kitchen, "Tempering")
    batter = make(
        kitchen,
        "Dosa batter",
        made_ahead=True,
        makes={"amount": 2, "unit": "litres"},
        lines=[{"words": "t", "amount": 1, "unit": "cup", "recipe_id": tempering["id"]}],
    )
    stock(kitchen, batter["homemade"]["id"], 1500, "ml")
    make(
        kitchen,
        "Dosa",
        lines=[{"words": "batter", "amount": 1, "unit": "cup", "recipe_id": batter["id"]}],
    )
    assert row(kitchen, "Dosa batter")["stock_unchecked"] is True
    assert row(kitchen, "Dosa")["stock"] == {"counted": 1, "missing": 0, "can_cook_now": True}
    assert row(kitchen, "Dosa")["stock_unchecked"] is False
    assert names(kitchen, can_cook_now="true") == ["Dosa"]


def test_removed_and_merged_ingredients_do_not_count(kitchen: TestClient) -> None:
    rice = fresh(kitchen, "Zorba rice")
    ok(kitchen.delete(f"{API}/foods/{rice['id']}"))
    make(kitchen, "Gone", lines=[{"words": "rice", "amount": 1, "unit": "cup"}])
    assert row(kitchen, "Gone")["stock"] is None


# --- Use soon ----------------------------------------------------------------------------------


def test_what_a_recipe_uses_that_is_about_to_go_off(kitchen: TestClient) -> None:
    now = today(kitchen)
    spinach = fresh(kitchen, "Spinach")
    paneer = fresh(kitchen, "Paneer")
    milk = fresh(kitchen, "Milk", counted_as="volume")
    old = fresh(kitchen, "Old kale")
    far = fresh(kitchen, "Far cabbage")
    stock(kitchen, spinach["id"], 200, "g", use_by=now.isoformat())
    stock(kitchen, paneer["id"], 200, "g", use_by=now.isoformat())
    stock(kitchen, milk["id"], 1000, "ml", use_by=(now + timedelta(days=2)).isoformat())
    stock(kitchen, old["id"], 200, "g", use_by=(now - timedelta(days=1)).isoformat())
    stock(kitchen, far["id"], 200, "g", use_by=(now + timedelta(days=3)).isoformat())
    make(
        kitchen, "Palak paneer", lines=[line(paneer["id"], 100, "g"), line(spinach["id"], 100, "g")]
    )
    make(kitchen, "Latte", lines=[line(milk["id"], 200, "ml"), line(far["id"], 10, "g")])
    make(kitchen, "Old", lines=[line(old["id"], 10, "g")])
    make(kitchen, "Far", lines=[line(far["id"], 10, "g")])
    soon = row(kitchen, "Palak paneer")["use_soon"]
    assert [f["name"] for f in soon["foods"]] == ["Paneer", "Spinach"]
    assert (soon["use_by"], soon["days_left"]) == (now.isoformat(), 0)
    latte = row(kitchen, "Latte")["use_soon"]
    assert latte["days_left"] == 2 and [f["name"] for f in latte["foods"]] == ["Milk"]
    assert row(kitchen, "Old")["use_soon"] is None  # its date has passed: not a nudge
    assert row(kitchen, "Far")["use_soon"] is None  # not soon yet


def test_only_the_soonest_date_is_named(kitchen: TestClient) -> None:
    now = today(kitchen)
    spinach = fresh(kitchen, "Spinach")
    paneer = fresh(kitchen, "Paneer")
    stock(kitchen, spinach["id"], 200, "g", use_by=(now + timedelta(days=1)).isoformat())
    stock(kitchen, paneer["id"], 200, "g", use_by=(now + timedelta(days=2)).isoformat())
    make(kitchen, "Both", lines=[line(paneer["id"], 1, "g"), line(spinach["id"], 1, "g")])
    soon = row(kitchen, "Both")["use_soon"]
    assert [f["name"] for f in soon["foods"]] == ["Spinach"] and soon["days_left"] == 1


def test_use_soon_keeps_exactly_the_recipes_that_have_a_use_soon_hint(kitchen: TestClient) -> None:
    now = today(kitchen)
    spinach = fresh(kitchen, "Spinach")
    old = fresh(kitchen, "Old kale")
    far = fresh(kitchen, "Far cabbage")
    rice = fresh(kitchen, "Zorba rice")
    stock(kitchen, spinach["id"], 200, "g", use_by=now.isoformat())
    stock(kitchen, old["id"], 200, "g", use_by=(now - timedelta(days=1)).isoformat())
    stock(kitchen, far["id"], 200, "g", use_by=(now + timedelta(days=3)).isoformat())
    stock(kitchen, rice["id"], 500, "g")  # no date: never a nudge
    make(kitchen, "Palak", lines=[line(spinach["id"], 100, "g")])
    make(kitchen, "Old", lines=[line(old["id"], 10, "g")])
    make(kitchen, "Far", lines=[line(far["id"], 10, "g")])
    make(kitchen, "Rice", lines=[line(rice["id"], 10, "g")])
    make(kitchen, "Nothing")
    assert names(kitchen, use_soon="true") == ["Palak"]
    # The same rule as the rows' hint: nobody else can disagree with it.
    hinted = [r["name"] for r in listing(kitchen, limit=500)["recipes"] if r["use_soon"]]
    assert names(kitchen, use_soon="true") == hinted
    assert names(kitchen, use_soon="false") == names(kitchen)
    assert names(kitchen) == ["Far", "Nothing", "Old", "Palak", "Rice"]


def test_use_soon_works_with_search_tags_and_can_cook_now(kitchen: TestClient) -> None:
    now = today(kitchen).isoformat()
    spinach = fresh(kitchen, "Spinach")
    paneer = fresh(kitchen, "Paneer")
    ghee = food(kitchen, "Ghee")
    stock(kitchen, spinach["id"], 200, "g", use_by=now)
    stock(kitchen, paneer["id"], 200, "g", use_by=now)
    make(kitchen, "Palak", tags=["Quick"], lines=[line(spinach["id"], 100, "g")])
    make(
        kitchen,
        "Palak paneer",
        lines=[
            line(spinach["id"], 100, "g"),
            line(paneer["id"], 100, "g"),
            line(ghee["id"], 1, "g"),
        ],
    )
    make(kitchen, "Paneer tikka", tags=["Quick"], lines=[line(paneer["id"], 100, "g")])
    make(kitchen, "Plain", tags=["Quick"])
    assert names(kitchen, use_soon="true") == ["Palak", "Palak paneer", "Paneer tikka"]
    assert names(kitchen, use_soon="true", q="paneer") == ["Palak paneer", "Paneer tikka"]
    assert names(kitchen, use_soon="true", tag="quick") == ["Palak", "Paneer tikka"]
    # Ghee is missing from Palak paneer, so only the others can be cooked now.
    assert names(kitchen, use_soon="true", can_cook_now="true") == ["Palak", "Paneer tikka"]
    assert names(kitchen, use_soon="true", can_cook_now="true", q="paneer", tag="quick") == [
        "Paneer tikka"
    ]
    assert names(kitchen, use_soon="true", q="nothing like this") == []


def test_use_soon_keeps_the_totals_and_the_paging_right(kitchen: TestClient) -> None:
    now = today(kitchen).isoformat()
    spinach = fresh(kitchen, "Spinach")
    stock(kitchen, spinach["id"], 5000, "g", use_by=now)
    for i in range(7):
        make(kitchen, f"Soon {i}", lines=[line(spinach["id"], 10, "g")])
        make(kitchen, f"Later {i}")
    first = listing(kitchen, use_soon="true", limit=3)
    assert (first["total"], first["all_recipes"]) == (7, 14)  # the title count is every recipe
    assert [r["name"] for r in first["recipes"]] == ["Soon 0", "Soon 1", "Soon 2"]
    assert first["next"] == "3"
    second = listing(kitchen, use_soon="true", limit=3, after=first["next"])
    assert [r["name"] for r in second["recipes"]] == ["Soon 3", "Soon 4", "Soon 5"]
    last = listing(kitchen, use_soon="true", limit=3, after=second["next"])
    assert [r["name"] for r in last["recipes"]] == ["Soon 6"] and last["next"] is None


def test_use_soon_takes_only_true_or_false(kitchen: TestClient) -> None:
    assert kitchen.get(f"{API}/recipes", params={"use_soon": "maybe"}).status_code == 422
    assert kitchen.get(f"{API}/recipes", params={"use_soon": "2"}).status_code == 422
    for value in ["true", "false", "1", "0"]:
        assert kitchen.get(f"{API}/recipes", params={"use_soon": value}).status_code == 200


# --- Can cook now, tags, search ----------------------------------------------------------------


def test_can_cook_now_keeps_recipes_with_nothing_missing(kitchen: TestClient) -> None:
    rice = fresh(kitchen, "Zorba rice")
    dal = food(kitchen, "Zorba dal")
    stock(kitchen, rice["id"], 500, "g")
    make(kitchen, "Plain rice", lines=[line(rice["id"], 100, "g")])
    make(kitchen, "Rice and dal", lines=[line(rice["id"], 100, "g"), line(dal["id"], 100, "g")])
    answer = listing(kitchen, can_cook_now="true")
    assert [r["name"] for r in answer["recipes"]] == ["Plain rice"]
    assert (answer["total"], answer["all_recipes"]) == (1, 2)
    stock(kitchen, dal["id"], 100, "g")
    assert names(kitchen, can_cook_now="true") == ["Plain rice", "Rice and dal"]


def test_filter_by_a_tag_ignoring_case(kitchen: TestClient) -> None:
    make(kitchen, "Sambar", tags=["Batch-friendly", "Quick"])
    make(kitchen, "Rasam", tags=["quick"])
    make(kitchen, "Kheer", tags=["Sweet"])
    assert names(kitchen, tag="QUICK") == ["Rasam", "Sambar"]
    assert names(kitchen, tag="Nothing") == []


def test_search_finds_names_tags_and_ingredient_names_including_other_names(
    kitchen: TestClient,
) -> None:
    toor = food(kitchen, "Toor dal")
    ok(
        kitchen.post(f"{API}/foods/{toor['id']}/other-names", json={"name": "thuvaram paruppu"}),
        201,
    )
    make(kitchen, "Sambar", tags=["Batch-friendly"], lines=[line(toor["id"], 100, "g")])
    make(kitchen, "Jeera rice", tags=["Quick"], lines=[{"words": "basmati rice", "amount": 1}])
    make(kitchen, "Kheer", steps=[{"text": "Stir the toor dal until it thickens."}])
    assert names(kitchen, q="thuvaram") == ["Sambar"]  # another name of an ingredient
    assert names(kitchen, q="TOOR dal") == ["Sambar"]  # not the method of Kheer
    assert names(kitchen, q="batch") == ["Sambar"]  # a tag
    assert names(kitchen, q="jeera") == ["Jeera rice"]  # the recipe's name
    assert names(kitchen, q="basmati") == ["Jeera rice"]  # words typed on a line
    assert names(kitchen, q="stir") == []  # never the method
    assert names(kitchen, q="  ") == ["Jeera rice", "Kheer", "Sambar"]


def test_search_looks_for_every_word_and_ignores_accents(kitchen: TestClient) -> None:
    make(kitchen, "Crème brûlée", tags=["Sweet"])
    make(kitchen, "Crème fraîche dip", tags=["Quick"])
    assert names(kitchen, q="creme brulee") == ["Crème brûlée"]
    assert names(kitchen, q="creme quick") == ["Crème fraîche dip"]
    assert names(kitchen, q="creme zzz") == []


def test_a_recipe_is_found_by_the_recipe_it_uses(kitchen: TestClient) -> None:
    powder = make(kitchen, "Sambar powder")
    make(
        kitchen,
        "Sambar",
        lines=[{"words": "masala", "amount": 2, "unit": "tbsp", "recipe_id": powder["id"]}],
    )
    assert names(kitchen, q="powder") == ["Sambar", "Sambar powder"]


def test_search_tag_and_can_cook_now_work_together(kitchen: TestClient) -> None:
    rice = fresh(kitchen, "Zorba rice")
    dal = food(kitchen, "Zorba dal")
    stock(kitchen, rice["id"], 500, "g")
    make(kitchen, "Rice bowl", tags=["Quick"], lines=[line(rice["id"], 100, "g")])
    make(kitchen, "Rice pudding", lines=[line(rice["id"], 100, "g")])
    make(
        kitchen,
        "Rice and dal",
        tags=["Quick"],
        lines=[line(rice["id"], 1, "g"), line(dal["id"], 1, "g")],
    )
    assert names(kitchen, q="rice") == ["Rice and dal", "Rice bowl", "Rice pudding"]
    assert names(kitchen, q="rice", can_cook_now="true") == ["Rice bowl", "Rice pudding"]
    assert names(kitchen, q="rice", tag="quick") == ["Rice and dal", "Rice bowl"]
    assert names(kitchen, q="rice", tag="quick", can_cook_now="true") == ["Rice bowl"]


def test_pages_follow_the_filters(kitchen: TestClient) -> None:
    for i in range(5):
        make(kitchen, f"Quick {i}", tags=["Quick"])
    make(kitchen, "Slow")
    first = listing(kitchen, tag="Quick", limit=2)
    assert [r["name"] for r in first["recipes"]] == ["Quick 0", "Quick 1"]
    assert (first["total"], first["next"]) == (5, "2")
    last = listing(kitchen, tag="Quick", limit=2, after="4")
    assert [r["name"] for r in last["recipes"]] == ["Quick 4"] and last["next"] is None


# --- One query per page, not one per recipe -----------------------------------------------------


def count_queries(kitchen: TestClient, **params: Any) -> int:
    engine = kitchen.app.state.engine  # type: ignore[attr-defined]
    counted: list[str] = []

    def note(*args: Any) -> None:
        counted.append(str(args[2]))

    event.listen(engine, "before_cursor_execute", note)
    try:
        listing(kitchen, **params)
    finally:
        event.remove(engine, "before_cursor_execute", note)
    return len(counted)


def test_the_list_reads_a_fixed_number_of_queries_however_many_recipes(
    kitchen: TestClient,
) -> None:
    rice = fresh(kitchen, "Zorba rice")
    dal = food(kitchen, "Zorba dal")
    stock(kitchen, rice["id"], 5000, "g", use_by=today(kitchen).isoformat())

    def add(count: int, start: int) -> None:
        for i in range(start, start + count):
            make(
                kitchen,
                f"Recipe {i:03d}",
                tags=["Quick", f"Tag {i % 7}"],
                nutrition={"kcal": 300 + i},
                lines=[line(rice["id"], 50, "g"), line(dal["id"], 50, "g"), {"words": "salt"}],
            )

    add(10, 0)
    few = {
        "plain": count_queries(kitchen, limit=50),
        "search": count_queries(kitchen, limit=50, q="rice quick"),
        "cook": count_queries(kitchen, limit=50, can_cook_now="true", tag="quick"),
        "soon": count_queries(kitchen, limit=50, use_soon="true", q="rice", can_cook_now="true"),
    }
    add(290, 10)  # 300 recipes
    assert listing(kitchen, limit=500)["total"] == 300
    many = {
        "plain": count_queries(kitchen, limit=50),
        "search": count_queries(kitchen, limit=50, q="rice quick"),
        "cook": count_queries(kitchen, limit=50, can_cook_now="true", tag="quick"),
        "soon": count_queries(kitchen, limit=50, use_soon="true", q="rice", can_cook_now="true"),
    }
    assert many == few
    assert listing(kitchen, use_soon="true", limit=500)["total"] == 300
    assert max(many.values()) <= 25
    # And a page of 500 rows still answers every row with its hints.
    everything = listing(kitchen, limit=500)["recipes"]
    assert len(everything) == 300 and all(r["stock"]["missing"] == 1 for r in everything)
    assert all(r["use_soon"]["foods"][0]["name"] == "Zorba rice" for r in everything)


def test_a_best_before_packet_is_no_nudge_to_cook(kitchen: TestClient) -> None:
    """0.8: Use soon counts a Best before date only once it has passed, and a passed date is
    no nudge either, so a recipe's Use soon hint comes only from Use by ingredients."""
    now = today(kitchen)
    dal = food(kitchen, "Toor dal")  # the pack-size table says best before
    stock(kitchen, dal["id"], 200, "g", use_by=now.isoformat())
    make(kitchen, "Dal soup", lines=[line(dal["id"], 100, "g")])
    assert row(kitchen, "Dal soup")["use_soon"] is None
    assert names(kitchen, use_soon="true") == []


# --- Hints only for the page shown (0.9.5) ----------------------------------------------------


def test_hints_are_worked_out_only_for_the_recipes_on_the_page(
    kitchen: TestClient, monkeypatch: Any
) -> None:
    from mealwright import recipe_list

    rice = food(kitchen, "Hint rice")
    stock(kitchen, rice["id"], 5000, "g")
    for i in range(12):
        make(kitchen, f"Hint {i:02d}", lines=[line(rice["id"], 50, "g")])
    worked: list[int] = []
    real = recipe_list.hints

    def spy(*args: Any, **kwargs: Any) -> Any:
        found = real(*args, **kwargs)
        worked.extend(found)
        return found

    monkeypatch.setattr(recipe_list, "hints", spy)
    page = listing(kitchen, limit=5)
    assert len(page["recipes"]) == 5 and page["total"] == 12
    assert len(worked) == 5  # not twelve
    assert all(r["stock"]["can_cook_now"] for r in page["recipes"])
    # A filter that needs every recipe's hint still gets the right total.
    worked.clear()
    kept = listing(kitchen, limit=5, can_cook_now="true")
    assert kept["total"] == 12 and len(kept["recipes"]) == 5
    # A search narrows first, so only the matches are worked out.
    worked.clear()
    one = listing(kitchen, limit=5, q="Hint 03", can_cook_now="true")
    assert one["total"] == 1 and len(worked) == 1
