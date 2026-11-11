# ruff: noqa: F811  (the fixtures come from test_recipe_import.py and are used by name)
"""Import reading (0.8, IM1, cabledrawer 10 Nov): "each" lines (F210) and "or" lines (F217), in the
reader and at the review for both a link and pasted text. Pinch (F218) and a clove in brackets
(F219) are in test_ingredient_reader.py and test_import_consistency.py. The web is faked as in
test_recipe_import.py: no test goes online."""

import json
from decimal import Decimal
from typing import Any

from fastapi.testclient import TestClient
from sync_kit import ok
from test_recipe_import import API, Web, links_on, review, save, to_save, web  # noqa: F401

from mealwright.ingredient_reader import read_line, read_lines

D = Decimal

EACH_LINES = [
    "1 tsp each onion & garlic powder ((Note 1))",
    "1 tbsp each cumin powder, paprika and dried oregano",
    "1 tsp each salt, cumin, ground coriander, paprika (sweet, normal or smokey)",
]


def seen(text: str) -> list[tuple[Decimal | None, str | None, str, str | None]]:
    return [(r.amount, r.unit, r.name, r.note) for r in read_lines(text)]


# --- "each" (F210) ----------------------------------------------------------------------------


def test_f210_each_makes_one_line_per_food_with_the_amount() -> None:
    assert seen(EACH_LINES[0]) == [
        (D(1), "tsp", "onion powder", None),
        (D(1), "tsp", "garlic powder", None),
    ]
    assert seen(EACH_LINES[1]) == [
        (D(1), "tbsp", "cumin powder", None),
        (D(1), "tbsp", "paprika", None),
        (D(1), "tbsp", "dried oregano", None),
    ]
    # The brackets stay with their food (paprika), not the whole line.
    assert seen(EACH_LINES[2]) == [
        (D(1), "tsp", "salt", None),
        (D(1), "tsp", "cumin", None),
        (D(1), "tsp", "ground coriander", None),
        (D(1), "tsp", "paprika", "sweet, normal or smokey"),
    ]


def test_f210_every_line_keeps_the_whole_line_as_written() -> None:
    for text in EACH_LINES:
        assert {r.text for r in read_lines(text)} == {text}


def test_f210_other_ways_of_saying_each() -> None:
    assert [(r.amount, r.name) for r in read_lines("2 tbsp each of salt and pepper")] == [
        (2, "salt"),
        (2, "pepper"),
    ]
    cans = read_lines("1 can each black beans, kidney beans")
    assert [(r.amount, r.size_word, r.name) for r in cans] == [
        (1, "can", "black beans"),
        (1, "can", "kidney beans"),
    ]
    # Not an "each" line: no amount straight before it, or nothing readable after it.
    assert len(read_lines("each of the above")) == 1
    assert len(read_lines("1 tsp salt, 1 tsp each")) == 1
    assert len(read_lines("2 tbsp oil for each pan")) == 1


# --- "or" (F217) ------------------------------------------------------------------------------


def test_f217_the_first_food_is_the_line_and_the_other_choice_is_kept() -> None:
    (line,) = read_lines("1 large shrak or 2 medium size flat bread or tortillas.")
    assert (line.amount, line.name) == (D(1), "shrak")
    assert line.note == "large, or 2 medium size flat bread or tortillas"
    other = line.alternative
    assert other is not None
    assert (other.amount, other.name) == (D(2), "flat bread")
    assert other.note is not None and other.note.startswith("or 1 large shrak")
    assert other.alternative is None


def test_f217_an_alternative_with_no_amount_takes_the_amount_of_the_first() -> None:
    (line,) = read_lines("1 tbsp ghee or butter")
    assert line.alternative is not None
    assert (line.alternative.amount, line.alternative.unit, line.alternative.name) == (
        D(1),
        "tbsp",
        "butter",
    )
    assert line.alternative.note == "or 1 tbsp ghee"


def test_f217_what_was_already_read_is_not_broken() -> None:
    assert read_line("1 tsp black or white pepper").name == "black pepper"
    assert read_line("2 or 3 cloves garlic").amount == D(3)
    assert read_line("2 onions, chopped or sliced").name == "onions"
    assert read_line("1 tsp salt, or to taste").note == "or to taste"
    for text in (
        "2 or 3 cloves garlic",
        "1 cup or 2 cups milk",
        "2 onions, chopped or sliced",
        "chopped or sliced onions",
        "1 tsp salt, or to taste",
        "1 cup milk (whole or 2%)",
        "3-or-so cups broccoli",
    ):
        (line,) = read_lines(text)
        assert line.alternative is None, text


# --- At the review: a link and pasted text, and Save ------------------------------------------


def page(lines: list[str]) -> str:
    return (
        '<html><script type="application/ld+json">'
        + json.dumps(
            {
                "@type": "Recipe",
                "name": "Enchiladas",
                "recipeIngredient": lines,
                "recipeInstructions": ["Cook."],
            }
        )
        + "</script></html>"
    )


def words(shown: dict[str, Any]) -> list[tuple[str, float | None, str | None]]:
    return [(x["words"], x["amount"], x["unit"]) for x in shown["lines"]]


EXPECTED = [
    ("onion powder", 1, "tsp"),
    ("garlic powder", 1, "tsp"),
    ("cumin powder", 1, "tbsp"),
    ("paprika", 1, "tbsp"),
    ("dried oregano", 1, "tbsp"),
    ("oil", 2, "tbsp"),
]


def check_each(shown: dict[str, Any]) -> None:
    assert words(shown) == EXPECTED
    # Each food's row shows the line as written, so the rows say where they came from.
    assert [x["written"] for x in shown["lines"][:2]] == [EACH_LINES[0]] * 2
    assert shown["counts"]["matched"] + shown["counts"]["to_confirm"] + shown["counts"][
        "needs_you"
    ] + shown["counts"]["staple"] == len(EXPECTED)


def test_f210_a_pasted_recipe_has_a_row_for_each_food(kitchen: TestClient, web: Web) -> None:
    text = (
        "Enchiladas\nIngredients\n"
        + "\n".join([*EACH_LINES[:2], "2 tbsp oil"])
        + "\nMethod\n1. Cook.\n"
    )
    check_each(review(kitchen, text))


def test_f210_a_linked_recipe_has_a_row_for_each_food(links_on: TestClient, web: Web) -> None:
    url = "https://bananaleaf.example/enchiladas/"
    web.pages[url] = page([*EACH_LINES[:2], "2 tbsp oil"])
    check_each(review(links_on, url))


def test_f210_check_and_save_agree_on_the_lines(kitchen: TestClient, web: Web) -> None:
    """Check shows N rows and Save sends N lines: the saved recipe has the same lines in the
    same order, so "Line 3" means the same row on both."""
    text = (
        "Enchiladas\nIngredients\n"
        + "\n".join([*EACH_LINES[:2], "2 tbsp oil"])
        + "\nMethod\n1. Cook.\n"
    )
    shown = review(kitchen, text)
    body = to_save(shown)
    assert len(body["lines"]) == len(shown["lines"]) == len(EXPECTED)
    links = {
        i: {"kind": "new", "name": line["words"], "counted_as": "weight"}
        for i, line in enumerate(shown["lines"])
        if line["label"] not in ("matched", "staple")
    }
    saved = ok(save(kitchen, to_save(shown, links)), 201)
    recipe = ok(kitchen.get(f"{API}/recipes/{saved['recipe']['id']}"))
    assert [(x["words"], x["amount"], x["unit"]) for x in recipe["lines"]] == EXPECTED


def test_f217_the_review_carries_the_other_choice_and_save_keeps_it_as_the_note(
    kitchen: TestClient, web: Web
) -> None:
    text = (
        "Mansaf\nIngredients\n1 large shrak or 2 medium size flat bread or tortillas.\n"
        "1 onion\nMethod\n1. Cook.\n"
    )
    shown = review(kitchen, text)
    first, onion = shown["lines"]
    assert (first["words"], first["amount"]) == ("shrak", 1)
    assert first["note"] == "large, or 2 medium size flat bread or tortillas"
    other = first["alternative"]
    assert (other["words"], other["amount"]) == ("flat bread", 2)
    assert other["note"].startswith("or 1 large shrak")
    assert other["alternative"] is None  # the swap is made on the screen, from these two
    assert onion["alternative"] is None
    # Save sends the line as shown: the other choice is only in the note (no new field).
    sent = to_save(shown)["lines"][0]
    assert "alternative" not in sent and sent["note"] == first["note"]


# --- Round 1 fixes (H1, M3, L6) -----------------------------------------------------------------


def test_h1_the_other_choice_keeps_its_own_words_in_both_notes() -> None:
    """Both ways round: the first food's note and the alternative's, in full."""
    cases = {
        "1 large shrak or 2 medium size flat bread or tortillas.": (
            (D(1), "shrak", "large, or 2 medium size flat bread or tortillas"),
            (D(2), "flat bread", "or 1 large shrak, medium size, or tortillas"),
        ),
        "2 tbsp butter or olive oil": (
            (D(2), "butter", "or olive oil"),
            (D(2), "olive oil", "or 2 tbsp butter"),
        ),
        "1 egg or 2 egg whites": (
            (D(1), "egg", "or 2 egg whites"),
            (D(2), "egg whites", "or 1 egg"),
        ),
        "1 shallot or 1/2 red onion": (
            (D(1), "shallot", "or 1/2 red onion"),
            (D("0.5"), "red onion", "or 1 shallot"),
        ),
        "1 tsp black or white pepper": (
            (D(1), "black pepper", "or white pepper"),
            (D(1), "white pepper", "or 1 tsp black pepper"),
        ),
    }
    for text, (first, other) in cases.items():
        (line,) = read_lines(text)
        assert (line.amount, line.name, line.note) == first, text
        assert line.alternative is not None, text
        assert (line.alternative.amount, line.alternative.name, line.alternative.note) == other, (
            text
        )


def test_m3_red_and_green_peppers_are_red_peppers_and_green_peppers() -> None:
    for text, amount, names in (
        ("2 each red and green peppers", 2, ["red peppers", "green peppers"]),
        ("1 each red and green pepper", 1, ["red pepper", "green pepper"]),
    ):
        reads = read_lines(text)
        assert [(r.amount, r.name) for r in reads] == [(amount, n) for n in names], text


def test_l6_each_with_a_comma_a_colon_or_a_describing_word() -> None:
    for text in ("1 tsp each, salt and pepper", "1 tsp each: salt, pepper"):
        assert [(r.amount, r.unit, r.name) for r in read_lines(text)] == [
            (D(1), "tsp", "salt"),
            (D(1), "tsp", "pepper"),
        ], text
    reads = read_lines("2 tbsp each fresh parsley and mint, chopped")
    assert [(r.amount, r.name, r.note) for r in reads] == [
        (D(2), "parsley", "fresh, chopped"),
        (D(2), "mint", "fresh, chopped"),
    ]


def test_fx6_a_matched_ghee_line_is_saved_linked_to_ghee(kitchen: TestClient) -> None:
    """FX6 confirm: the pr180 screenshot showed ghee "not linked" after Check showed it matched."""
    for name in ("Toor dal", "Turmeric", "Ghee"):
        ok(kitchen.post(f"{API}/foods", json={"name": name, "counted_as": "weight"}), 201)
    text = (
        "Saved dal tadka\nServes 4\nIngredients\n200 g toor dal\n1 tsp turmeric\n2 tbsp ghee\n"
        "Method\n1. Cook the dal with the turmeric.\n2. Pour over the hot ghee.\n"
    )
    shown = review(kitchen, text)
    assert [line["label"] for line in shown["lines"] if line["kind"] == "ingredient"] != []
    saved = ok(save(kitchen, to_save(shown)), 201)
    recipe = ok(kitchen.get(f"{API}/recipes/{saved['recipe']['id']}"))
    ghee = next(line for line in recipe["lines"] if "ghee" in line["words"].lower())
    assert ghee["link"] != "none", ghee
