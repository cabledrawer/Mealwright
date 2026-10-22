# ruff: noqa: RUF001  (a test of line separators and other look-alike characters)
"""Pasted recipe text → title, ingredients and method (docs/dev/ingredient-reader.md)."""

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mealwright.ingredient_reader import read_line
from mealwright.pasted_recipe import (
    MAX_PASTED_CHARS,
    PASTED_TOO_LONG,
    PastedRecipe,
    PastedTooLong,
    read_pasted,
)

DAL = """Easy Toor Dal

Serves 4. Prep 10 min.

Ingredients
1 cup thuvaram paruppu (toor dal)
1 sprig curry leaves
¼ tsp hing / asafoetida
2 onions, finely chopped
Salt to taste

Method
1. Wash the dal and cook it in a pressure cooker.
   Whistle three times.
2. Heat oil and add the tempering.
3. Mix and serve.

Notes
Keeps 3 days in the fridge.
"""


def test_a_recipe_with_headings() -> None:
    recipe = read_pasted(DAL)
    assert recipe.name == "Easy Toor Dal"
    assert recipe.ingredients == (
        "1 cup thuvaram paruppu (toor dal)",
        "1 sprig curry leaves",
        "¼ tsp hing / asafoetida",
        "2 onions, finely chopped",
        "Salt to taste",
    )
    assert recipe.steps == (
        "Wash the dal and cook it in a pressure cooker. Whistle three times.",
        "Heat oil and add the tempering.",
        "Mix and serve.",
    )
    assert (recipe.lines_cut, recipe.steps_cut) == (0, 0)


def test_the_lines_go_straight_to_the_line_reader() -> None:
    recipe = read_pasted(DAL)
    assert read_line(recipe.ingredients[2]).other_names == ("asafoetida",)


@pytest.mark.parametrize(
    "heading",
    [
        "Ingredients",
        "INGREDIENTS",
        "ingredients:",
        "Ingredients:",
        "## Ingredients",
        "**Ingredients**",
        "**Ingredients:**",
        "Ingredients (serves 4)",
        "_Ingredients_",
        "--- Ingredients ---",
        "You will need",
        "You'll need:",
        "Ingredient list",
    ],
)
def test_ingredient_headings(heading: str) -> None:
    recipe = read_pasted(f"Pancakes\n{heading}\n200 g flour\n300 ml milk\nMethod\nMix. Fry.")
    assert recipe.name == "Pancakes"
    assert recipe.ingredients == ("200 g flour", "300 ml milk")
    assert recipe.steps == ("Mix. Fry.",)


@pytest.mark.parametrize(
    "heading",
    [
        "Method",
        "METHOD",
        "Method:",
        "Instructions",
        "Instruction",
        "Directions",
        "## Instructions",
        "**Directions:**",
        "Preparation",
        "Steps",
        "Procedure",
        "How to make it",
        "Cooking instructions",
    ],
)
def test_method_headings(heading: str) -> None:
    recipe = read_pasted(f"Pancakes\nIngredients\n200 g flour\n{heading}\nMix.\nFry.")
    assert recipe.ingredients == ("200 g flour",)
    assert recipe.steps == ("Mix.", "Fry.")


def test_markdown_bullets_and_step_words() -> None:
    recipe = read_pasted(
        "## Pancakes\n**Ingredients:**\n- 200 g flour\n* 300 ml milk\n▢ 1 egg\n"
        "**Instructions:**\nStep 1: Mix everything.\nStep 2: Fry in a pan.\n"
    )
    assert recipe.name == "Pancakes"
    assert recipe.ingredients == ("200 g flour", "300 ml milk", "1 egg")
    assert recipe.steps == ("Mix everything.", "Fry in a pan.")


@pytest.mark.parametrize(
    ("line", "step"),
    [
        ("1. Heat the oil.", "Heat the oil."),
        ("1) Heat the oil.", "Heat the oil."),
        ("1: Heat the oil.", "Heat the oil."),
        ("12. Heat the oil.", "Heat the oil."),
        ("Step 3. Heat the oil.", "Heat the oil."),
        ("1 - Heat the oil.", "Heat the oil."),
        ("• Heat the oil.", "Heat the oil."),
        ("Heat the oil.", "Heat the oil."),
    ],
)
def test_step_numbers_are_taken_off(line: str, step: str) -> None:
    assert read_pasted(f"Ingredients\n1 onion\nMethod\n{line}\n").steps == (step,)


def test_unnumbered_method_lines_are_each_a_step() -> None:
    recipe = read_pasted("Ingredients\n1 onion\nMethod\nChop it.\nFry it.\n\nServe it.")
    assert recipe.steps == ("Chop it.", "Fry it.", "Serve it.")


def test_a_wrapped_numbered_step_carries_on_but_a_blank_line_ends_it() -> None:
    recipe = read_pasted(
        "Ingredients\n1 onion\nMethod\n1. Chop the onion\nvery finely.\n\nLeave it.\n2. Fry."
    )
    assert recipe.steps == ("Chop the onion very finely.", "Leave it.", "Fry.")


def test_notes_and_other_sections_after_the_method_are_left_out() -> None:
    recipe = read_pasted(
        "Dal\nIngredients\n1 cup dal\nMethod\nCook it.\nNotes\nKeeps well.\nTips\nSoak first."
    )
    assert recipe.steps == ("Cook it.",)


def test_heading_words_inside_sentences_are_not_headings() -> None:
    recipe = read_pasted(
        "Dal\nIngredients\n1 cup dal\nMethod\nFollow the method on the packet.\n"
        "Ingredients for the tempering are below.\nPreparation time is 10 minutes."
    )
    assert recipe.steps == (
        "Follow the method on the packet.",
        "Ingredients for the tempering are below.",
        "Preparation time is 10 minutes.",
    )


def test_a_method_heading_twice_is_just_text() -> None:
    recipe = read_pasted("Dal\nIngredients\n1 cup dal\nMethod\nCook it.\nMethod\nServe it.")
    assert recipe.steps == ("Cook it.", "Method", "Serve it.")


def test_only_an_ingredients_heading() -> None:
    recipe = read_pasted(
        "Soup\nIngredients\n1 onion\n2 carrots\nChop the veg.\nSimmer for 20 minutes."
    )
    assert recipe.ingredients == ("1 onion", "2 carrots")
    assert recipe.steps == ("Chop the veg.", "Simmer for 20 minutes.")


def test_only_a_method_heading() -> None:
    recipe = read_pasted("Soup\n1 onion\n2 carrots\nMethod\nChop the veg.")
    assert recipe.name == "Soup"
    assert recipe.ingredients == ("1 onion", "2 carrots")
    assert recipe.steps == ("Chop the veg.",)


# --- No headings: the best guess ---------------------------------------------------------------


def test_no_headings_best_guess() -> None:
    recipe = read_pasted(
        "Quick Omelette\n2 eggs\n1 tbsp butter\nSalt\n"
        "Beat the eggs with salt. Melt the butter in a pan and cook the eggs for 2 minutes.\n"
        "Serve hot."
    )
    assert recipe.name == "Quick Omelette"
    assert recipe.ingredients == ("2 eggs", "1 tbsp butter", "Salt")
    assert recipe.steps == (
        "Beat the eggs with salt. Melt the butter in a pan and cook the eggs for 2 minutes.",
        "Serve hot.",
    )


def test_no_headings_numbered_steps_are_not_ingredients() -> None:
    recipe = read_pasted(
        "Tea\n1 cup water\n1 tsp tea leaves\n1 tbsp sugar\n"
        "1. Boil the water.\n2. Add the tea leaves.\n3. Cook for 3 minutes.\n"
    )
    assert recipe.ingredients == ("1 cup water", "1 tsp tea leaves", "1 tbsp sugar")
    assert recipe.steps == ("Boil the water.", "Add the tea leaves.", "Cook for 3 minutes.")


def test_times_and_temperatures_are_not_amounts() -> None:
    recipe = read_pasted(
        "Bread\n500 g flour\n1 tsp salt\n300 ml water\nBake at 180°C for 30 minutes.\n"
        "180°C for 30 minutes\n20 minutes more.\n"
    )
    assert recipe.ingredients == ("500 g flour", "1 tsp salt", "300 ml water")
    assert recipe.steps == (
        "Bake at 180°C for 30 minutes.",
        "180°C for 30 minutes",
        "20 minutes more.",
    )


def test_a_decimal_amount_is_not_a_numbered_step() -> None:
    recipe = read_pasted("Tea\n1.5 cups water\n2.5 tsp sugar\nBoil it.")
    assert recipe.ingredients == ("1.5 cups water", "2.5 tsp sugar")
    assert recipe.steps == ("Boil it.",)


def test_no_amounts_at_all_is_a_title_and_a_method() -> None:
    recipe = read_pasted("Mystery\nDo this.\nThen that.")
    assert recipe.name == "Mystery"
    assert recipe.ingredients == ()
    assert recipe.steps == ("Do this.", "Then that.")


def test_text_that_starts_with_an_amount_has_no_title() -> None:
    recipe = read_pasted("2 onions\n1 tsp salt\nFry the onions.")
    assert recipe.name == ""
    assert recipe.ingredients == ("2 onions", "1 tsp salt")


def test_tamil_and_hindi_text() -> None:
    recipe = read_pasted(
        "பருப்பு குழம்பு\nIngredients\n1 cup துவரம் பருப்பு (toor dal)\n"
        "1 tsp जीरा (cumin)\nMethod\nபருப்பை வேகவைக்கவும்.\n"
    )
    assert recipe.name == "பருப்பு குழம்பு"
    assert recipe.ingredients == ("1 cup துவரம் பருப்பு (toor dal)", "1 tsp जीरा (cumin)")
    assert recipe.steps == ("பருப்பை வேகவைக்கவும்.",)


# --- Empty and odd text ------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["", "   ", "\n\n\n", "\t​\n"])
def test_empty_text_is_an_empty_result(text: str) -> None:
    assert read_pasted(text) == PastedRecipe("", (), (), 0, 0)


def test_a_title_is_cut_at_200_characters() -> None:
    assert len(read_pasted("Dal " * 100 + "\nIngredients\n1 onion").name) <= 200


def test_an_ingredient_line_and_a_step_are_cut_to_the_editors_limits() -> None:
    recipe = read_pasted("Dal\nIngredients\n" + "1 onion " * 100 + "\nMethod\n" + "Stir. " * 2000)
    assert len(recipe.ingredients[0]) <= 200
    assert len(recipe.steps[0]) <= 5000


# --- Hidden characters -------------------------------------------------------------------------


def test_hidden_characters_are_stripped_not_refused() -> None:
    recipe = read_pasted("Dal‮​\nIngredients\n2​ onions\x00⁦\n1\ttsp salt\nMethod\nCook­ it.\x07\n")
    assert recipe.name == "Dal"
    assert recipe.ingredients == ("2 onions", "1 tsp salt")
    assert recipe.steps == ("Cook it.",)


def test_joiners_in_indian_scripts_stay() -> None:
    text = "க்ஷ‍ா"
    recipe = read_pasted(f"Dal\nIngredients\n1 cup {text}")
    assert recipe.ingredients == (f"1 cup {text}",)


def test_every_kind_of_line_break_works() -> None:
    for linebreak in ("\n", "\r\n", "\r", " ", " "):
        text = linebreak.join(["Dal", "Ingredients", "1 onion", "Method", "Cook."])
        recipe = read_pasted(text)
        assert (recipe.name, recipe.ingredients, recipe.steps) == ("Dal", ("1 onion",), ("Cook.",))


# --- Size limits -------------------------------------------------------------------------------


def test_over_200_ingredient_lines_keeps_the_first_200() -> None:
    lines = [f"{n} g thing{n}" for n in range(1, 251)]
    recipe = read_pasted("Big\nIngredients\n" + "\n".join(lines) + "\nMethod\nCook.")
    assert len(recipe.ingredients) == 200
    assert recipe.ingredients[0] == "1 g thing1"
    assert recipe.ingredients[-1] == "200 g thing200"
    assert recipe.lines_cut == 50
    assert recipe.steps_cut == 0


def test_over_100_steps_keeps_the_first_100() -> None:
    steps = [f"{n}. Do thing {n}." for n in range(1, 131)]
    recipe = read_pasted("Big\nIngredients\n1 onion\nMethod\n" + "\n".join(steps))
    assert len(recipe.steps) == 100
    assert recipe.steps[0] == "Do thing 1."
    assert recipe.steps[-1] == "Do thing 100."
    assert recipe.steps_cut == 30
    assert recipe.lines_cut == 0


def test_exactly_the_limits_cut_nothing() -> None:
    recipe = read_pasted(
        "Big\nIngredients\n"
        + "\n".join(f"{n} g thing" for n in range(1, 201))
        + "\nMethod\n"
        + "\n".join(f"Step {n}." for n in range(1, 101))
    )
    assert (len(recipe.ingredients), len(recipe.steps)) == (200, 100)
    assert (recipe.lines_cut, recipe.steps_cut) == (0, 0)


def test_100000_characters_is_fine_and_one_more_is_refused() -> None:
    body = "Dal\nIngredients\n1 onion\nMethod\n"
    text = body + "x" * (MAX_PASTED_CHARS - len(body))
    assert len(text) == MAX_PASTED_CHARS
    assert read_pasted(text).name == "Dal"
    with pytest.raises(PastedTooLong) as error:
        read_pasted(text + "x")
    assert str(error.value) == PASTED_TOO_LONG
    assert "100,000" in PASTED_TOO_LONG


def test_the_length_is_counted_before_anything_is_stripped() -> None:
    with pytest.raises(PastedTooLong):
        read_pasted("​" * (MAX_PASTED_CHARS + 1))


# --- Properties --------------------------------------------------------------------------------


@settings(max_examples=300, deadline=None)
@given(st.text(max_size=600))
def test_never_raises_and_stays_within_limits(text: str) -> None:
    recipe = read_pasted(text)
    assert len(recipe.name) <= 200
    assert len(recipe.ingredients) <= 200 and len(recipe.steps) <= 100
    assert all(len(line) <= 200 and line == line.strip() and line for line in recipe.ingredients)
    assert all(len(step) <= 5000 and step for step in recipe.steps)
    assert "\n" not in recipe.name
    assert recipe.lines_cut >= 0 and recipe.steps_cut >= 0


LINES = st.sampled_from(
    [
        "Ingredients", "Method:", "## Instructions", "Notes", "1 cup rice", "2 onions, chopped",
        "Salt", "1. Boil it.", "Step 2: Stir.", "Cook for 20 minutes.", "", "Dal", "- 1 tsp salt",
        "• mix", "180°C", "1.5 kg flour",
    ]
)  # fmt: skip


@settings(max_examples=300, deadline=None)
@given(st.lists(LINES, max_size=40))
def test_never_raises_on_recipe_like_lines(lines: list[str]) -> None:
    recipe = read_pasted("\n".join(lines))
    assert len(recipe.ingredients) <= 200 and len(recipe.steps) <= 100
    for line in recipe.ingredients:
        read_line(line)  # every ingredient line can be read, whatever it says


def test_without_hidden_keeps_flags_and_joiners_and_drops_the_rest() -> None:
    from mealwright.names import has_hidden, without_hidden

    scotland = "\U0001f3f4\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f"
    text = f"a‍b{scotland}‮c\x00d\te\r\nf g\U000e0041"
    clean = without_hidden(text)
    assert clean == f"a‍b{scotland}cd e\nf\ng"
    assert not has_hidden(clean, newlines=True)
    assert without_hidden("plain") == "plain"
