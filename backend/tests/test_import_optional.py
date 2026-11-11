# ruff: noqa: F811  (the web fixture comes from test_recipe_import.py and is used by name)
"""Optional ingredients and steps on the importer (0.8 wave 4, R3; F151): "(optional)" in a line
or step marks it Optional and is taken out of the words; a line under "For serving" is the same;
the review's switch is kept when the recipe is saved. The reader's own cases are in
test_ingredient_reader.py."""

from fastapi.testclient import TestClient
from sync_kit import ok
from test_recipe_import import API, Web, review, to_save, web  # noqa: F401
from test_recipe_import import save as save_import

# --- The importer --------------------------------------------------------------------------------

IMPORTED = """Opt imported biryani
Ingredients
500 g mutton
2 tbsps raw papaya paste ((optional))
Optional: 1 tsp kewra water
For serving
1 cup fried onions
Method
1. Rub the mutton with yoghurt.
2. Fry a handful of onions until crisp, for the top. (optional)
3. Optional: Sprinkle with saffron milk.
4. Add salt (optional) and stir.
5. Serve it, optional garnish or not.
"""


def test_the_review_marks_optional_lines_and_steps_and_takes_the_word_out(
    kitchen: TestClient, web: Web
) -> None:
    shown = review(kitchen, IMPORTED)
    lines = {ln["words"]: ln for ln in shown["lines"] if ln["kind"] == "ingredient"}
    assert lines["mutton"]["optional"] is False
    for name in ("raw papaya paste", "kewra water", "fried onions"):
        assert lines[name]["optional"] is True, name
        assert "optional" not in (lines[name]["note"] or ""), name  # not a word in the note
    assert [(s["text"], s["optional"]) for s in shown["steps"]] == [
        ("Rub the mutton with yoghurt.", False),
        ("Fry a handful of onions until crisp, for the top.", True),
        ("Sprinkle with saffron milk.", True),
        ("Add salt (optional) and stir.", False),  # in the middle it is part of the sentence
        ("Serve it, optional garnish or not.", False),  # the word inside a sentence stays
    ]


def test_saving_a_review_keeps_the_optional_switches(kitchen: TestClient, web: Web) -> None:
    shown = review(kitchen, IMPORTED)
    body = to_save(shown)
    body["lines"] = [
        {**ln, "optional": shown["lines"][i]["optional"]} for i, ln in enumerate(body["lines"])
    ]
    saved = ok(save_import(kitchen, body), 201)
    recipe = ok(kitchen.get(f"{API}/recipes/{saved['recipe']['id']}"))
    flags = {ln["words"]: ln["optional"] for ln in recipe["lines"] if ln["kind"] == "ingredient"}
    assert flags == {
        "mutton": False,
        "raw papaya paste": True,
        "kewra water": True,
        "fried onions": True,
    }
    assert [s["optional"] for s in recipe["steps"]] == [False, True, True, False, False]


def test_a_person_can_switch_a_reviewed_line_to_optional_or_back(
    kitchen: TestClient, web: Web
) -> None:
    shown = review(kitchen, IMPORTED)
    body = to_save(shown)
    for ln, read in zip(body["lines"], shown["lines"], strict=True):
        ln["optional"] = (
            not read["optional"] if read["words"] in ("mutton", "kewra water") else read["optional"]
        )
    saved = ok(save_import(kitchen, body), 201)
    recipe = ok(kitchen.get(f"{API}/recipes/{saved['recipe']['id']}"))
    flags = {ln["words"]: ln["optional"] for ln in recipe["lines"] if ln["kind"] == "ingredient"}
    assert flags["mutton"] is True and flags["kewra water"] is False


def test_a_bracket_makes_a_step_optional_only_at_its_end() -> None:
    from mealwright.line_prep import optional_step

    assert optional_step("Fry the onions (optional).") == ("Fry the onions.", True)
    assert optional_step("Fry the onions (optional)") == ("Fry the onions", True)
    assert optional_step("Add salt (optional) and stir.") == (
        "Add salt (optional) and stir.",
        False,
    )
    assert optional_step("Optional: fry the onions") == ("Fry the onions", True)


def test_rf4_i8_a_step_with_a_long_run_of_spaces_is_read_at_once() -> None:
    """RF4 I8: the "(optional)" search took seconds on 20,000 spaces (it slowed with the square of
    the run). The bound is generous: a read now takes a few milliseconds."""
    import time

    from mealwright.line_prep import optional_step

    for text in (
        "Fry the onions" + " " * 20000 + "until golden",
        " " * 20000,
        "Fry" + " (" * 5000 + "x",
        "Fry the onions (optional)" + " " * 20000,
        "a (optional)" + " " * 20000 + "b",
    ):
        started = time.perf_counter()
        optional_step(text)
        assert time.perf_counter() - started < 0.5, text[:20]
    # The reviewer's input: 19 pasted steps, each a bracket, a long run of spaces, then more text
    # (about 1.7 seconds before the fix: the run was tried from every space after the bracket).
    started = time.perf_counter()
    for _ in range(19):
        optional_step("a (optional)" + " " * 4900 + "b")
    assert time.perf_counter() - started < 0.5
    # What it does is unchanged.
    assert optional_step("Fry the onions (optional)") == ("Fry the onions", True)
    assert optional_step("Fry the onions (optional).") == ("Fry the onions.", True)
    assert optional_step("Fry the onions  [ Optional ]  ") == ("Fry the onions", True)
    assert optional_step("Add salt (optional) and stir.") == (
        "Add salt (optional) and stir.",
        False,
    )
