"""Where each ingredient of one recipe is, for the recipe page (GET /recipes/{id}/stock,
docs/dev/api-0.4-recipes.md section 5): the list's stock rules line by line, in a fixed number
of queries. The other household is in test_recipes_isolation.py."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import event
from sync_kit import ok
from test_recipe_list import line, place_id, row, stock
from test_recipes import food, make

API = "/api/v1"


def stock_of(
    kitchen: TestClient, recipe: dict[str, Any], servings: int | None = None
) -> dict[str, Any]:
    params = {} if servings is None else {"servings": servings}
    answer: dict[str, Any] = ok(kitchen.get(f"{API}/recipes/{recipe['id']}/stock", params=params))
    return answer


def states(
    kitchen: TestClient, recipe: dict[str, Any], servings: int | None = None
) -> dict[int, tuple[str, str | None]]:
    """line id → (state, place)."""
    return {
        found["line_id"]: (found["state"], found["place"])
        for found in stock_of(kitchen, recipe, servings)["lines"]
    }


def test_each_line_says_in_stock_staple_short_or_missing_and_where(kitchen: TestClient) -> None:
    rice = food(kitchen, "Zorba rice")
    peas = food(kitchen, "Zorba peas")
    dal = food(kitchen, "Zorba dal")
    oil = food(kitchen, "Zorba oil", staple=True)
    ghee = food(kitchen, "Zorba ghee")
    stock(kitchen, rice["id"], 500, "g")
    stock(kitchen, peas["id"], 300, "g", place_id=place_id(kitchen, "Freezer"))
    stock(kitchen, dal["id"], 50, "g")
    recipe = make(
        kitchen,
        "Mixed",
        lines=[
            line(rice["id"], 200, "g"),
            line(peas["id"], 200, "g"),
            line(dal["id"], 200, "g"),
            line(oil["id"], 1, "tbsp"),
            line(ghee["id"], 1, "tbsp"),
        ],
    )
    ids = [found["id"] for found in recipe["lines"]]
    answer = stock_of(kitchen, recipe)
    assert states(kitchen, recipe) == {
        ids[0]: ("in_stock", "Cupboard"),
        ids[1]: ("in_stock", "Freezer"),
        ids[2]: ("short", None),
        ids[3]: ("staple", None),
        ids[4]: ("missing", None),
    }
    assert [found["food"]["name"] for found in answer["lines"]] == [
        "Zorba rice",
        "Zorba peas",
        "Zorba dal",
        "Zorba oil",
        "Zorba ghee",
    ]
    assert (answer["counted"], answer["missing"], answer["stock_unchecked"]) == (5, 2, False)


def test_headings_lines_without_an_amount_and_unlinked_lines_have_no_state(
    kitchen: TestClient,
) -> None:
    rice = food(kitchen, "Zorba rice")
    nothing = food(kitchen, "Zorba nothing")
    stock(kitchen, rice["id"], 500, "g")
    recipe = make(
        kitchen,
        "Plain",
        lines=[
            {"kind": "heading", "words": "For the rice"},
            line(rice["id"], 100, "g"),
            {"words": "salt to taste", "food_id": nothing["id"]},
            {"words": "a handful of coriander"},
        ],
    )
    assert list(states(kitchen, recipe).values()) == [("in_stock", "Cupboard")]
    nothing_counts = make(kitchen, "Only words", lines=[{"words": "salt to taste"}])
    assert stock_of(kitchen, nothing_counts) == {
        "lines": [],
        "counted": 0,
        "missing": 0,
        "stock_unchecked": False,
    }


def test_a_line_without_an_amount_gets_a_mark_but_never_counts(kitchen: TestClient) -> None:
    """0.5.1 (cabledrawer's hand test): "salt to taste" linked to the Salt staple showed no
    "Staple".
    A line with no amount still never counts towards stock (cabledrawer 19 Oct, question 13)."""
    salt = food(kitchen, "Zorba salt", staple=True)
    lemon = food(kitchen, "Zorba lemon")
    dal = food(kitchen, "Zorba dal")
    gone = food(kitchen, "Zorba gone")
    stock(kitchen, lemon["id"], 100, "g", place_id=place_id(kitchen, "Fridge"))
    stock(kitchen, dal["id"], 50, "g")
    recipe = make(
        kitchen,
        "Marks",
        lines=[
            {"words": "salt to taste", "food_id": salt["id"]},
            {"words": "a squeeze of lemon", "food_id": lemon["id"]},
            {"words": "gone to taste", "food_id": gone["id"]},
            line(dal["id"], 200, "g"),
            {"words": "more dal", "food_id": dal["id"]},
        ],
    )
    ids = [found["id"] for found in recipe["lines"]]
    answer = stock_of(kitchen, recipe)
    assert states(kitchen, recipe) == {
        ids[0]: ("staple", None),
        ids[1]: ("in_stock", "Fridge"),
        ids[3]: ("short", None),
        ids[4]: ("short", None),  # shares the counted line's state
    }
    # Only the dal line counts, exactly as in the list's hint.
    assert (answer["counted"], answer["missing"]) == (1, 1)
    assert row(kitchen, "Marks")["stock"] == {"counted": 1, "missing": 1, "can_cook_now": False}


def test_two_lines_for_one_ingredient_are_added_up_and_share_its_state(
    kitchen: TestClient,
) -> None:
    rice = food(kitchen, "Zorba rice")
    stock(kitchen, rice["id"], 200, "g")
    recipe = make(kitchen, "Twice", lines=[line(rice["id"], 100, "g"), line(rice["id"], 150, "g")])
    assert {state for state, _ in states(kitchen, recipe).values()} == {"short"}
    stock(kitchen, rice["id"], 100, "g")
    assert {state for state, _ in states(kitchen, recipe).values()} == {"in_stock"}


def test_the_place_is_the_one_holding_most_of_it(kitchen: TestClient) -> None:
    peas = food(kitchen, "Zorba peas")
    stock(kitchen, peas["id"], 100, "g", place_id=place_id(kitchen, "Fridge"))
    stock(kitchen, peas["id"], 400, "g", place_id=place_id(kitchen, "Freezer"))
    recipe = make(kitchen, "Peas", lines=[line(peas["id"], 200, "g")])
    assert list(states(kitchen, recipe).values()) == [("in_stock", "Freezer")]


def test_a_made_ahead_recipe_line_is_checked_through_its_own_ingredient(
    kitchen: TestClient,
) -> None:
    batter = make(kitchen, "Dosa batter", made_ahead=True, makes={"amount": 2, "unit": "litres"})
    dosa = make(
        kitchen,
        "Dosa",
        lines=[{"words": "batter", "amount": 2, "unit": "cup", "recipe_id": batter["id"]}],
    )
    answer = stock_of(kitchen, dosa)
    assert [(s["state"], s["food"]["id"]) for s in answer["lines"]] == [
        ("missing", batter["homemade"]["id"])
    ]
    stock(kitchen, batter["homemade"]["id"], 1500, "ml")
    assert list(states(kitchen, dosa).values()) == [("in_stock", "Cupboard")]
    assert stock_of(kitchen, dosa)["stock_unchecked"] is False


def test_a_line_using_an_unchecked_recipe_has_no_state_and_the_recipe_says_so(
    kitchen: TestClient,
) -> None:
    rice = food(kitchen, "Zorba rice")
    stock(kitchen, rice["id"], 500, "g")
    base = make(kitchen, "Plain base")
    recipe = make(
        kitchen,
        "Uses a base",
        lines=[
            line(rice["id"], 100, "g"),
            {"words": "base", "amount": 1, "unit": "cup", "recipe_id": base["id"]},
        ],
    )
    answer = stock_of(kitchen, recipe)
    assert [s["state"] for s in answer["lines"]] == ["in_stock"]
    assert answer["stock_unchecked"] is True
    # A line with no amount is ignored, whatever it uses: nothing is left unchecked.
    fine = make(
        kitchen,
        "No amount",
        lines=[line(rice["id"], 100, "g"), {"words": "base", "recipe_id": base["id"]}],
    )
    assert stock_of(kitchen, fine)["stock_unchecked"] is False


def test_the_page_agrees_with_the_list_for_every_recipe(kitchen: TestClient) -> None:
    rice = food(kitchen, "Zorba rice")
    dal = food(kitchen, "Zorba dal")
    oil = food(kitchen, "Zorba oil", staple=True)
    ghee = food(kitchen, "Zorba ghee")
    stock(kitchen, rice["id"], 500, "g")
    stock(kitchen, dal["id"], 100, "g")
    base = make(kitchen, "Plain base")
    recipes = [
        make(kitchen, "A", lines=[line(rice["id"], 100, "g"), line(oil["id"], 1, "tsp")]),
        make(kitchen, "B", lines=[line(rice["id"], 900, "g"), line(dal["id"], 50, "g")]),
        make(kitchen, "C", lines=[line(ghee["id"], 1, "tbsp"), line(dal["id"], 500, "g")]),
        make(
            kitchen,
            "D",
            lines=[
                line(rice["id"], 1, "g"),
                {"words": "base", "amount": 1, "unit": "cup", "recipe_id": base["id"]},
            ],
        ),
        make(kitchen, "E", lines=[{"words": "salt"}]),
    ]
    for recipe in recipes:
        answer = stock_of(kitchen, recipe)
        hint = row(kitchen, recipe["name"])
        if hint["stock"] is None:
            assert (answer["counted"], answer["missing"]) == (0, 0)
        else:
            assert (answer["counted"], answer["missing"]) == (
                hint["stock"]["counted"],
                hint["stock"]["missing"],
            )
        assert answer["stock_unchecked"] == hint["stock_unchecked"]
        foods = {s["food"]["id"]: s["state"] for s in answer["lines"]}
        assert sum(state in ("short", "missing") for state in foods.values()) == answer["missing"]


def test_the_chosen_servings_scale_what_is_needed(kitchen: TestClient) -> None:
    """cabledrawer, 19 Oct, Q22: enough for the recipe at the chosen servings."""
    rice = food(kitchen, "Zorba rice")
    stock(kitchen, rice["id"], 300, "g")
    short_at_own = make(kitchen, "Four", serves=4, lines=[line(rice["id"], 400, "g")])
    assert {s for s, _ in states(kitchen, short_at_own).values()} == {"short"}
    assert {s for s, _ in states(kitchen, short_at_own, 4).values()} == {"short"}
    # Half the servings, half the rice: 200 g of 300 g.
    assert {s for s, _ in states(kitchen, short_at_own, 2).values()} == {"in_stock"}
    again = stock_of(kitchen, short_at_own, 2)
    assert (again["counted"], again["missing"]) == (1, 0)
    # The other way round: enough at its own servings, not at 8.
    stock(kitchen, rice["id"], 200, "g")  # 500 g now
    enough = make(kitchen, "Also four", serves=4, lines=[line(rice["id"], 400, "g")])
    assert {s for s, _ in states(kitchen, enough).values()} == {"in_stock"}
    assert {s for s, _ in states(kitchen, enough, 8).values()} == {"short"}
    doubled = stock_of(kitchen, enough, 8)
    assert (doubled["counted"], doubled["missing"]) == (1, 1)
    # Nothing in the pantry stays "missing" at any servings.
    ghee = food(kitchen, "Zorba ghee")
    none = make(kitchen, "No ghee", serves=4, lines=[line(ghee["id"], 1, "tbsp")])
    assert {s for s, _ in states(kitchen, none, 1).values()} == {"missing"}


def test_servings_round_up_so_a_short_pantry_is_never_enough(kitchen: TestClient) -> None:
    rice = food(kitchen, "Zorba rice")
    stock(kitchen, rice["id"], 33, "g")
    recipe = make(kitchen, "Thirds", serves=3, lines=[line(rice["id"], 100, "g")])
    assert {s for s, _ in states(kitchen, recipe, 1).values()} == {"short"}  # 33.33 g
    stock(kitchen, rice["id"], 1, "g")
    assert {s for s, _ in states(kitchen, recipe, 1).values()} == {"in_stock"}


def test_an_amount_that_cannot_be_compared_is_in_stock_at_any_servings(
    kitchen: TestClient,
) -> None:
    grain = food(kitchen, "Zorba grain")  # no known weight for a cup
    stock(kitchen, grain["id"], 1, "g")
    recipe = make(kitchen, "Cups", serves=2, lines=[line(grain["id"], 3, "cup")])
    for servings in (None, 1, 2, 99):
        assert {s for s, _ in states(kitchen, recipe, servings).values()} == {"in_stock"}


def test_servings_are_ignored_when_the_recipe_has_no_serves(kitchen: TestClient) -> None:
    rice = food(kitchen, "Zorba rice")
    stock(kitchen, rice["id"], 300, "g")
    recipe = make(kitchen, "No serves", serves=None, lines=[line(rice["id"], 400, "g")])
    for servings in (None, 1, 2, 99):
        assert {s for s, _ in states(kitchen, recipe, servings).values()} == {"short"}


def test_servings_must_be_a_whole_number_from_1_to_99(kitchen: TestClient) -> None:
    recipe = make(kitchen, "Any", serves=4)
    for bad in ("0", "100", "-1", "2.5", "many", ""):
        answer = kitchen.get(f"{API}/recipes/{recipe['id']}/stock", params={"servings": bad})
        assert answer.status_code == 422, bad
    for good in (1, 99):
        assert stock_of(kitchen, recipe, good)["lines"] == []


def test_a_deleted_or_unknown_recipe_is_not_found(kitchen: TestClient) -> None:
    gone = make(kitchen, "Old")
    ok(kitchen.delete(f"{API}/recipes/{gone['id']}"))
    for recipe_id in (gone["id"], 99999):
        answer = kitchen.get(f"{API}/recipes/{recipe_id}/stock")
        assert answer.status_code == 404 and answer.json()["code"] == "not_found"


def count_queries(kitchen: TestClient, recipe: dict[str, Any], servings: int | None = None) -> int:
    engine = kitchen.app.state.engine  # type: ignore[attr-defined]
    counted: list[str] = []

    def note(*args: Any) -> None:
        counted.append(str(args[2]))

    event.listen(engine, "before_cursor_execute", note)
    try:
        stock_of(kitchen, recipe, servings)
    finally:
        event.remove(engine, "before_cursor_execute", note)
    return len(counted)


def test_a_fixed_number_of_queries_however_many_lines_and_recipes(kitchen: TestClient) -> None:
    foods = [food(kitchen, f"Zorba food {i:03d}") for i in range(60)]
    for found in foods[:30]:
        stock(kitchen, found["id"], 1000, "g")
    few = make(kitchen, "Few", lines=[line(f["id"], 10, "g") for f in foods[:3]])
    before = count_queries(kitchen, few)
    assert count_queries(kitchen, few, 2) == before
    for i in range(40):
        make(kitchen, f"Other {i:02d}", lines=[line(f["id"], 10, "g") for f in foods[:5]])
    many = make(kitchen, "Many", lines=[line(f["id"], 10, "g") for f in foods])
    assert len(stock_of(kitchen, many)["lines"]) == 60
    assert count_queries(kitchen, many) == before
    assert count_queries(kitchen, many, 7) == before
    assert before <= 20
