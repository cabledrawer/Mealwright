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


@pytest.mark.parametrize("blank", ["", "\n"])
def test_a_heading_ending_in_a_colon_stays_a_heading_after_a_numbered_step(blank: str) -> None:
    # cabledrawer 10 Nov: "For the dosa:" straight after a step was joined onto that step.
    recipe = read_pasted(
        "Dosa\nIngredients\nFor the batter\n1 cup urad dal\nFor the dosa\n1 tbsp ghee\n"
        "Method\nFor the batter:\n1. Soak the dal.\n2. Grind and ferment overnight.\n"
        f"{blank}For the dosa:\n1. Spread the batter thin and fry."
    )
    assert recipe.steps == (
        "For the batter:",
        "Soak the dal.",
        "Grind and ferment overnight.",
        "For the dosa:",
        "Spread the batter thin and fry.",
    )


def test_a_wrapped_line_ending_in_a_colon_still_carries_on_its_step() -> None:
    recipe = read_pasted("Ingredients\n1 onion\nMethod\n1. Mix in the\nfollowing:\n2. Fry.")
    assert recipe.steps == ("Mix in the following:", "Fry.")


def test_a_wrapped_line_in_capitals_still_carries_on_its_step() -> None:
    # FX2 review r1: only the colon form is a heading after a numbered step.
    recipe = read_pasted(
        "Ingredients\n1 onion\nMethod\n1. Bake at 180C / 350F\nGAS MARK 4\n2. Cool."
    )
    assert recipe.steps == ("Bake at 180C / 350F GAS MARK 4", "Cool.")


def test_a_bulleted_colon_heading_after_a_numbered_step_stays_a_heading() -> None:
    recipe = read_pasted(
        "Ingredients\n1 onion\nMethod\n1. Soak the dal.\n• For the dosa:\n2. Fry it thin."
    )
    assert recipe.steps == ("Soak the dal.", "For the dosa:", "Fry it thin.")


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


# --- Cutting without breaking anything (round 1) -------------------------------------------------

SCOTLAND = "\U0001f3f4\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f"


def test_a_cut_never_splits_a_flag_emoji() -> None:
    from mealwright.names import has_hidden

    for length in range(190, 205):
        line = "1 g " + "x" * (length - 4) + SCOTLAND
        recipe = read_pasted(f"Dal\nIngredients\n{line}")
        got = recipe.ingredients[0]
        assert len(got) <= 200
        assert not has_hidden(got), length  # no stray tag characters left over
        assert got.endswith(SCOTLAND) or SCOTLAND[0] not in got
    title = read_pasted("x" * 198 + SCOTLAND + "\nIngredients\n1 onion").name
    assert len(title) <= 200 and not has_hidden(title)
    step = read_pasted("Dal\nIngredients\n1 onion\nMethod\n" + "x" * 4998 + SCOTLAND).steps[0]
    assert len(step) <= 5000 and not has_hidden(step)


def test_cut_text_keeps_letters_with_their_marks_and_joined_sequences() -> None:
    from mealwright.names import cut_text

    assert cut_text("abc", 5) == "abc"
    assert cut_text("abcdef", 3) == "abc"
    assert cut_text("abéf", 3) == "ab"  # the accent stays with its letter
    assert cut_text("ab‍cd", 3) == "a"  # b, the joiner and c belong together
    assert cut_text("ab‍cd", 4) == "ab‍c"
    assert cut_text(SCOTLAND + "ab", 3) == ""
    assert cut_text("a" + SCOTLAND + "ab", 3) == "a"
    assert cut_text("a" + SCOTLAND, len(SCOTLAND) + 1) == "a" + SCOTLAND


def test_the_limit_names_are_characters() -> None:
    from mealwright import pasted_recipe

    assert pasted_recipe.MAX_LINE_CHARS == 200
    assert not hasattr(pasted_recipe, "MAX_LINE_WORDS")


# --- A Tips or Notes heading in the middle of the method (round 1) ------------------------------


def test_a_tips_heading_in_the_middle_does_not_drop_the_steps_after_it() -> None:
    recipe = read_pasted(
        "Dal\nIngredients\n1 onion\nMethod\n1. Cook the dal.\nTips\nSoak it first.\n"
        "2. Add the onions and serve.\n3. Eat."
    )
    assert recipe.steps == ("Cook the dal.", "Add the onions and serve.", "Eat.")


def test_a_trailing_notes_part_is_still_dropped() -> None:
    recipe = read_pasted(
        "Dal\nIngredients\n1 onion\nMethod\n1. Cook the dal.\n2. Serve.\nNotes\nKeeps well.\n"
        "1. Soak first."
    )
    # The notes' own list starts again at 1, so it is not the method carrying on.
    assert recipe.steps == ("Cook the dal.", "Serve.")


def test_notes_between_steps_with_a_wrapped_line() -> None:
    recipe = read_pasted(
        "Dal\nIngredients\n1 onion\nMethod\n1. Cook the dal\nuntil soft.\nNotes\nSoak first.\n"
        "2. Serve."
    )
    assert recipe.steps == ("Cook the dal until soft.", "Serve.")


def test_a_step_of_only_combining_marks_is_kept_cut_not_dropped() -> None:
    from mealwright.api.v1.recipe_schemas import MAX_STEP_CHARS

    text = "Ingredients\n1 onion\nMethod\n" + "́" * (MAX_STEP_CHARS + 10)
    steps = read_pasted(text).steps
    assert len(steps) == 1
    assert len(steps[0]) == MAX_STEP_CHARS


def test_notes_and_tips_left_out_are_counted_for_the_review_screen() -> None:
    # cabledrawer 23 Oct, question 17: "4 lines after “Tips” were left out".
    text = (
        "Dal\nIngredients\n1 onion\nMethod\nChop it.\nCook it.\n"
        "Tips\nUse more salt.\nServe hot.\n\nLeftovers keep.\nFreeze it.\n"
    )
    found = read_pasted(text)
    assert [(left.heading, left.lines) for left in found.left_out] == [("Tips", 4)]
    assert found.steps == ("Chop it.", "Cook it.")


def test_nothing_left_out_says_nothing() -> None:
    assert read_pasted("Dal\nIngredients\n1 onion\nMethod\nChop it.\n").left_out == ()
    # A heading with nothing under it left nothing out.
    assert read_pasted("Dal\nIngredients\n1 onion\nMethod\nChop it.\nNotes\n").left_out == ()


def test_each_part_left_out_is_counted_on_its_own() -> None:
    text = "Dal\nIngredients\n1 onion\nNotes\nOne.\nTwo.\nMethod\nChop it.\nStorage\nThree.\n"
    found = read_pasted(text)
    assert [(left.heading, left.lines) for left in found.left_out] == [
        ("Notes", 2),
        ("Storage", 1),
    ]


# --- F171: "Serves 4" and "Takes 30 minutes" ---------------------------------------------------


@pytest.mark.parametrize(
    ("line", "serves", "minutes"),
    [
        ("Serves 4", 4, None),
        ("Serves: 4", 4, None),
        ("Serves 4-6", 6, None),
        ("Servings: 4", 4, None),
        ("Serves 4 people", 4, None),
        ("Takes 30 minutes", None, 30),
        ("Takes 30 mins", None, 30),
        ("Takes 1 hour 15 minutes", None, 75),
        ("Takes 1½ hours", None, 90),
        ("Total time: 45 minutes", None, 45),
        ("Time: 20 min", None, 20),
        ("Ready in 1h 10m", None, 70),
    ],
)
def test_f171_serves_and_time_lines_are_read_and_are_not_ingredients_or_steps(
    line: str, serves: int | None, minutes: int | None
) -> None:
    for text in (
        f"Dal\n{line}\nIngredients\n1 cup toor dal\n2 onions\nMethod\nCook the dal.\n",
        f"Dal\nIngredients\n1 cup toor dal\n{line}\n2 onions\nMethod\nCook the dal.\n",
        f"Dal\n{line}\n1 cup toor dal\n2 onions\nCook the dal.\n",
    ):
        recipe = read_pasted(text)
        assert (recipe.serves, recipe.time_minutes) == (serves, minutes), text
        assert recipe.name == "Dal"
        assert recipe.ingredients == ("1 cup toor dal", "2 onions"), text
        assert recipe.steps == ("Cook the dal.",), text


def test_f171_both_lines_together_and_prep_plus_cook_when_there_is_no_total() -> None:
    both = read_pasted(
        "Dal\nServes 4\nTakes 30 minutes\nIngredients\n1 cup toor dal\nMethod\nCook."
    )
    assert (both.serves, both.time_minutes) == (4, 30)
    parts = read_pasted("Dal\nPrep time: 10 minutes\nCook time: 25 minutes\n1 cup toor dal\nCook.")
    assert parts.time_minutes == 35
    total = read_pasted("Dal\nPrep time: 10 minutes\nTotal time: 40 minutes\n1 cup toor dal\nCook.")
    assert total.time_minutes == 40


def test_f171_sentences_in_the_method_are_not_read_as_facts() -> None:
    recipe = read_pasted(
        "Dal\nIngredients\n1 cup toor dal\nMethod\nServes 4 with rice.\nCook for 30 minutes.\n"
        "This takes 30 minutes to cook.\n"
    )
    assert (recipe.serves, recipe.time_minutes) == (None, None)
    assert len(recipe.steps) == 3


def test_f171_one_line_with_serves_and_a_lone_prep_time() -> None:
    # DAL's "Serves 4. Prep 10 min.": serves is read; a prep time alone is no total time.
    recipe = read_pasted(DAL)
    assert (recipe.serves, recipe.time_minutes) == (4, None)
    assert recipe.name == "Easy Toor Dal" and len(recipe.ingredients) == 5
    assert read_pasted("Dal\n1 cup toor dal\nCook.").serves is None


# --- F171 review fix: a method step is never read as the time -----------------------------------


@pytest.mark.parametrize(
    "step", ["Cook 20 minutes.", "Cook 12 min", "Prep 5 min", "Total 30 min", "Simmer 20 minutes"]
)
@pytest.mark.parametrize("headings", [True, False])
def test_f171_a_short_method_step_with_a_time_stays_a_step(step: str, headings: bool) -> None:
    text = (
        f"Dal\nIngredients\n1 cup toor dal\nMethod\nRinse the lentils.\n{step}\nServe.\n"
        if headings
        else f"Dal\n1 cup toor dal\n2 onions\nRinse the lentils.\n{step}\nServe.\n"
    )
    recipe = read_pasted(text)
    assert recipe.time_minutes is None
    assert recipe.steps == ("Rinse the lentils.", step, "Serve.")


def test_f171_loose_forms_count_only_above_the_headings() -> None:
    recipe = read_pasted(
        "Dal\nPrep 10 min\nCook 25 min\nIngredients\n1 cup toor dal\nMethod\nCook 5 min\nServe."
    )
    assert recipe.time_minutes == 35
    assert recipe.steps == ("Cook 5 min", "Serve.")


def test_a_group_heading_right_under_the_title_is_kept_f222() -> None:
    # Beta 1 hand test: "For the batter" right under the title was dropped as a description, so
    # "Make this its own recipe" was offered on the wrong group.
    text = (
        "Beta1 Poha Test Dosa\nFor the batter\n1 cup urad dal\n2 cups rice\n"
        "For the dosa\n1 tbsp ghee\nMethod\n1. Soak the dal.\n2. Fry it thin."
    )
    recipe = read_pasted(text)
    assert recipe.ingredients == (
        "For the batter",
        "1 cup urad dal",
        "2 cups rice",
        "For the dosa",
        "1 tbsp ghee",
    )


def test_a_group_heading_with_a_colon_under_the_title_is_kept_without_any_headings_f222() -> None:
    recipe = read_pasted("Dosa\n\nFor the batter:\n1 cup urad dal\n2 cups rice\n\nSoak the dal.\n")
    assert recipe.ingredients == ("For the batter:", "1 cup urad dal", "2 cups rice")


def test_a_description_above_the_amounts_is_still_dropped_f222() -> None:
    recipe = read_pasted("Dosa\nA crisp crepe from the south.\n1 cup urad dal\n2 cups rice\nFry.")
    assert "A crisp crepe from the south." not in recipe.ingredients


def test_a_serving_line_under_the_title_is_not_made_a_heading_fx4_review() -> None:
    # FX4 review r1: "For four people" or "For a crowd" says who it serves; it is not a group.
    for line in ("For four people", "For two", "For a crowd", "Serves: for four"):
        recipe = read_pasted(f"Dosa\n{line}\n1 cup urad dal\n2 cups rice\nFry.")
        assert recipe.ingredients == ("1 cup urad dal", "2 cups rice"), line


def test_a_heading_without_the_is_kept_when_another_heading_follows_f222() -> None:
    recipe = read_pasted("Dosa\nTo make the batter\n1 cup urad dal\nFor dipping\n1 tbsp ghee\nFry.")
    assert recipe.ingredients[0] == "To make the batter"
    recipe = read_pasted("Dosa\nFor batter\n1 cup urad dal\nFor dipping\n1 tbsp ghee\nFry.")
    assert recipe.ingredients == ("For batter", "1 cup urad dal", "For dipping", "1 tbsp ghee")


@pytest.mark.parametrize("line", ["Serves 500", "Serves 100", "Serves 0", "Total time: 400 hours"])
def test_rf4_i11_a_serves_or_time_the_boxes_cannot_hold_is_left_empty(line: str) -> None:
    """RF4 I11 (proposed, for cabledrawer): Serves is 1 to 99 and the time up to 14,400 minutes. A
    pasted line that says more is not put in the boxes (they stay empty, so Check never refuses a
    value nobody typed); the line is not read as a fact, so it stays where the text had it."""
    recipe = read_pasted(f"Dal\n{line}\nIngredients\n1 cup toor dal\nMethod\n1. Cook.\n")
    assert (recipe.serves, recipe.time_minutes) == (None, None)
    assert recipe.ingredients == ("1 cup toor dal",)
    assert recipe.steps == ("Cook.",)


def test_rf4_i11_the_edges_are_still_read() -> None:
    assert read_pasted("Dal\nServes 99\n1 cup toor dal\nCook.").serves == 99
    assert read_pasted("Dal\nTotal time: 240 hours\n1 cup toor dal\nCook.").time_minutes == 14_400
    assert (
        read_pasted(
            "Dal\nPrep time: 200 hours\nCook time: 100 hours\n1 cup dal\nCook."
        ).time_minutes
        is None
    )
