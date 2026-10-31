# ruff: noqa: RUF001  (these tests use look-alike dashes and signs on purpose)
"""Importer consistency (0.7.0, cabledrawer 28 and 30 Oct: "the same thing written two ways must
give the same result"). Each test writes one thing two ways and checks the reader gives the
same amount, unit and name."""

from decimal import Decimal

import pytest

from mealwright.ingredient_reader import ReadLine, read_line

D = Decimal
PINT_UK = 568
PINT_US = 473


def core(text: str, pint_ml: int | None = PINT_UK) -> tuple[Decimal | None, str | None, str]:
    line = read_line(text, pint_ml=pint_ml)
    return line.amount, line.unit, line.name.lower()


def same(*ways: str, pint_ml: int | None = PINT_UK) -> ReadLine:
    """Every way of writing it reads as the same amount, unit and name. Returns the first."""
    first = core(ways[0], pint_ml)
    for way in ways[1:]:
        assert core(way, pint_ml) == first, (way, core(way, pint_ml), first)
    return read_line(ways[0], pint_ml=pint_ml)


# --- Amounts (F28, F18, F8, follow-ups 5 and 6) -------------------------------------------------


def test_f28_three_or_so_cups_is_three_cups() -> None:
    line = same(
        "3-or-so cups broccoli florets", "3 cups broccoli florets", "3 or so cups broccoli florets"
    )
    assert (line.amount, line.unit, line.name) == (D(3), "cup", "broccoli florets")
    assert line.note == "or so"


def test_f28_a_handful_has_no_amount_and_keeps_the_word() -> None:
    for text in (
        "a handful of golden raisins",
        "handful golden raisins",
        "Handful of golden raisins",
    ):
        line = read_line(text)
        assert (line.name, line.size_word) == ("golden raisins", "handful"), text


def test_f55_a_bare_size_word_is_not_part_of_the_name() -> None:
    assert read_line("Handful dried banana chips").name == "dried banana chips"
    assert read_line("drop vanilla extract").name == "vanilla extract"  # F8
    assert read_line("Glass red wine").name == "red wine"


def test_f18_amount_after_the_name_is_the_same_as_before_it() -> None:
    line = same(
        "2 cloves garlic, minced",
        "garlic, 2 cloves, minced",
        "garlic: 2 cloves, minced",
        "garlic - 2 cloves, minced",
    )
    assert (line.amount, line.size_word, line.name, line.note) == (
        D(2),
        "cloves",
        "garlic",
        "minced",
    )
    same("1 tsp salt", "salt, 1 tsp", "salt 1 tsp")
    same("500 g flour", "Flour 500g", "flour, 500 g")
    same("2 tbsp olive oil", "olive oil - 2 tbsp", "olive oil, 2 tbsp")


def test_an_amount_after_the_name_needs_a_unit_or_a_size_word() -> None:
    line = read_line("Vitamin B12")
    assert (line.amount, line.name) == (None, "Vitamin B12")
    assert read_line("eggs, 3").amount is None


def test_f8_one_14_ounce_can_and_half_a_jar() -> None:
    can = same(
        "one 14-ounce can coconut milk", "1 14-ounce can coconut milk", "one 14 oz can coconut milk"
    )
    assert (can.unit, can.size_word, can.name) == ("g", "can", "coconut milk")
    assert can.amount == D(397)
    jar = same(
        "half a 340g jar strawberry jam",
        "1/2 x 340g jar strawberry jam".replace("x ", ""),
        "0.5 340g jar strawberry jam",
    )
    assert (jar.amount, jar.unit) == (D(170), "g")


def test_f87_a_word_before_cloves_is_part_of_the_name_not_the_name() -> None:
    """F87 (cabledrawer 31 Oct): "8 whole cloves" is the spice, never a new ingredient "Whole"."""
    for text, name in (
        ("8 whole cloves", "whole cloves"),
        ("8 dried cloves", "dried cloves"),
        ("4 ground cloves", "ground cloves"),
        ("2 whole sprigs thyme", "whole sprigs thyme"),
    ):
        line = read_line(text)
        assert (line.amount, line.size_word, line.name) == (D(text[0]), None, name), text
        assert line.counts, text
    # A name before the clove still makes it the size word.
    for text in ("2 garlic cloves", "2 whole garlic cloves"):
        assert read_line(text).size_word == "cloves", text


def test_follow_up_5_one_and_a_half_cups_flour() -> None:
    line = same("one and a half cups flour", "1 1/2 cups flour", "1½ cups flour", "1.5 cups flour")
    assert (line.amount, line.unit, line.name) == (D("1.5"), "cup", "flour")
    same("two and a half cups flour", "2½ cups flour")
    same("one and a quarter cups flour", "1¼ cups flour")


def test_follow_up_6_a_dozen_is_twelve_of_them() -> None:
    # The reader keeps "dozen" as a size word (an ingredient sold by the dozen); the review turns
    # it into 12 when the ingredient has no such size (tests/test_recipe_import.py).
    for text in ("a dozen eggs", "1 dozen eggs", "one dozen eggs", "dozen eggs"):
        line = read_line(text)
        assert (line.size_word, line.name) == ("dozen", "eggs"), text
    assert read_line("half a dozen eggs").amount == D("0.5")
    assert read_line("2 dozen eggs").amount == D(2)


def test_follow_up_6_quarts_and_fluid_ounces_follow_the_household_pint() -> None:
    assert core("1 quart milk") == (D(1136), "ml", "milk")
    assert core("2 pints milk") == core("1 quart milk")
    assert core("1 quart milk", PINT_US) == (D(946), "ml", "milk")
    assert core("1 gallon milk") == (D(4546), "ml", "milk")
    assert core("1 gallon milk", PINT_US) == (D(3785), "ml", "milk")
    assert core("20 fl oz milk") == core("1 pint milk")
    assert core("16 fl oz milk", PINT_US) == core("1 pint milk", PINT_US)
    assert core("10 fl oz milk") == (D(284), "ml", "milk")
    assert core("10 fl oz milk", PINT_US) == (D(296), "ml", "milk")
    assert core("2 fl. oz milk") == core("2 fl oz milk")
    # With no pint size given (the old behaviour), they stay in the note.
    line = read_line("1 quart milk", pint_ml=None)
    assert line.amount is None and line.note == "1 quart"


def test_quarts_report_their_pints_so_the_switch_still_works() -> None:
    line = read_line("1 quart milk", pint_ml=PINT_UK)
    assert (line.pints, line.pint_unit) == (1, "quart")
    line = read_line("2 fl oz milk", pint_ml=PINT_UK)
    assert (line.pints, line.pint_unit) == (2, "fl oz")


def test_f12_a_heaped_unit_is_still_a_unit() -> None:
    line = same("1 heaped tsp plain flour", "1 tsp plain flour", "1 level tsp plain flour")
    assert (line.amount, line.unit, line.name) == (D(1), "tsp", "plain flour")
    assert line.note == "heaped"


def test_just_a_little_is_no_amount_not_part_of_the_name() -> None:
    line = read_line("just a lil fish sauce")
    assert line.name == "fish sauce"
    assert line.amount is None or line.size_word == "lil"


@pytest.mark.parametrize(
    ("a", "b"),
    [("2–3 cups spinach", "2-3 cups spinach"), ("2 to 3 cups spinach", "2 or 3 cups spinach")],
)
def test_ranges_give_the_higher_number(a: str, b: str) -> None:
    assert core(a) == core(b) == (D(3), "cup", "spinach")


# --- Names (F12, F20, F31, F32, F35, F9, F17, F7) ------------------------------------------------


def test_f20_two_names_with_one_noun_are_cream_not_heavy() -> None:
    line = same(
        "1 cup heavy / thickened cream", "1 cup heavy cream", "1 cup heavy/thickened cream (Note 5)"
    )
    assert line.name == "heavy cream"
    assert line.other_names == ("thickened cream",)


def test_a_slash_between_two_whole_names_is_still_other_names() -> None:
    line = read_line("1 tsp hing / asafoetida")
    assert (line.name, line.other_names) == ("hing", ("asafoetida",))


def test_f31_a_comma_after_prep_words_does_not_start_the_note() -> None:
    line = same(
        "4 skinless, boneless chicken breast halves", "4 skinless boneless chicken breast halves"
    )
    assert line.name == "chicken breast halves"
    assert line.note == "skinless boneless"
    assert read_line("1 onion, finely chopped").name == "onion"


def test_f32_a_variety_in_brackets_is_part_of_the_name() -> None:
    line = read_line("4 to 5 dried red chilies ((kashmiri or byadgi) (less spicy variety))")
    assert line.amount == D(5)
    assert line.name == "kashmiri dried red chilies"
    assert line.other_names == ("byadgi",)
    assert line.note == "less spicy variety"


def test_f35_a_colour_in_brackets_is_a_note_not_another_name() -> None:
    line = read_line("6 whole cardamom pods (green)")
    assert line.other_names == ()
    assert line.note == "green"


def test_f17_footnote_marks_are_dropped() -> None:
    a = read_line("1 cup heavy cream ((Note 5))")
    b = read_line("1 cup heavy cream")
    assert (a.amount, a.unit, a.name, a.note) == (b.amount, b.unit, b.name, b.note)
    assert core("1 cup milk (, full fat)") == core("1 cup milk (full fat)")
    assert (
        read_line("1 cup milk (, full fat)").other_names
        == read_line("1 cup milk (full fat)").other_names
    )
    assert (
        read_line("1 tbsp oil ( OR 1 tbsp vegetable oil (Note 3))").note
        == "OR 1 tbsp vegetable oil"
    )
    assert read_line("2 eggs [3]").name == "eggs"


def test_f7_a_prep_word_shows_once() -> None:
    for text in (
        "200 g softened butter, softened",
        "200 g butter, softened",
        "200 g softened butter",
    ):
        line = read_line(text)
        assert (line.name, line.note) == ("butter", "softened"), text
    assert read_line("4 eggs beaten, beaten").note == "beaten"
    assert read_line("small knob of butter, small").note is not None


def test_made_with_is_a_note() -> None:
    line = read_line("Beef stock made with 1 stock shot or cube")
    assert (line.name, line.note) == ("Beef stock", "made with 1 stock shot or cube")


def test_and_cut_into_chunks_is_a_note() -> None:
    line = read_line("King Edward potatoes and cut into chunks")
    assert (line.name, line.note) == ("King Edward potatoes", "and cut into chunks")


# --- Lines (F11, F26) --------------------------------------------------------------------------


def test_f11_or_gives_the_first_choice_and_a_note() -> None:
    line = read_line("100ml whole milk or 50ml milk and 50ml cream")
    assert (line.amount, line.unit, line.name) == (D(100), "ml", "whole milk")
    assert line.note == "or 50ml milk and 50ml cream"
    same("1 tbsp ghee or butter", "1 tbsp ghee")
    assert read_line("1 tbsp ghee or butter").note == "or butter"
    assert read_line("1 tsp black or white pepper").name == "black pepper"
    # prep words either side of "or" are still prep words
    assert read_line("2 onions, chopped or sliced").name == "onions"
    assert read_line("chopped or sliced onions").name == "onions"


def test_f26_plus_and_and_make_two_lines() -> None:
    from mealwright.ingredient_reader import read_lines

    for text in ("a swish of olive oil + a sprinkle of salt",):
        names = [r.name for r in read_lines(text)]
        assert names == ["olive oil", "salt"], text
    both = read_lines("just a lil fish sauce (trust me!) and brown sugar to taste")
    assert [r.name for r in both] == ["fish sauce", "brown sugar"]
    assert all("to taste" in (r.note or "") for r in both)
    assert [r.name for r in read_lines("salt and pepper to taste")] == ["salt", "pepper"]
    # An "and" that is part of one name, or has amounts, is not split.
    assert len(read_lines("macaroni and cheese")) == 1
    assert len(read_lines("2 tbsp salt and pepper")) == 1
    assert len(read_lines("half and half")) == 1


# --- Line clutter (F33, F34, F19, F23) ----------------------------------------------------------


def test_f33_page_buttons_are_junk_but_real_lines_are_not() -> None:
    from mealwright.line_prep import is_page_junk

    for text in ("Cook Mode", "Prevent your screen from going dark", "½x1×2×", "1x 2x 3x", "Print"):
        assert is_page_junk(text), text
    for text in ("2 cups flour", "Print edition butter", "Salt", "Method acting"):
        assert not is_page_junk(text), text


def test_f34_for_the_x_is_a_heading_with_or_without_a_colon() -> None:
    from mealwright.line_prep import is_ingredient_heading, is_step_heading

    for text in ("For the Lamb", "For the Garnish:", "To assemble", "For serving", "To serve:"):
        assert is_ingredient_heading(text), text
    for text in ("salt, to taste", "To taste", "2 cups flour", "For the sauce, 2 tbsp"):
        assert not is_ingredient_heading(text), text
    assert is_step_heading("FULL RECIPE") and is_step_heading("For the sauce:")
    assert not is_step_heading("Heat the oil.") and not is_step_heading("MIX WELL until smooth.")


def test_f19_serving_headings() -> None:
    from mealwright.line_prep import serving_heading

    for text in ("For serving", "To serve:", "Garnish", "For the garnish", "Optional"):
        assert serving_heading(text), text
    assert not serving_heading("For the Lamb")


# --- Names and tags (F9, section 9) -------------------------------------------------------------


# F91, round 3: a table of real-looking titles, written before the rule was changed again. A
# dash is a separator only with spaces round it; "Recipe" goes only as a label; whose recipe it
# is (my, our, Mum's, Kids') stays.
RECIPE_TITLES = [
    # hyphenated words anywhere
    ("Gluten-Free Banana Bread Recipe", "Gluten-Free Banana Bread"),
    ("Easy One-Pot Pasta Recipe", "Easy One-Pot Pasta"),
    ("Slow-Cooker Beef Stew Recipe", "Slow-Cooker Beef Stew"),
    ("No-Knead Bread Recipe", "No-Knead Bread"),
    ("Stir-Fried Noodles Recipe", "Stir-Fried Noodles"),
    ("Pan-Fried Salmon recipe", "Pan-Fried Salmon"),
    ("One-Pot Chicken and Rice", "One-Pot Chicken and Rice"),
    ("Gluten-Free Recipes for Kids", "Gluten-Free Recipes for Kids"),
    ("Dal - Gluten-Free Recipe", "Dal"),
    ("Dal Makhani Recipe | Gluten-Free Kitchen", "Dal Makhani"),
    # Recipe first, middle, last
    ("Recipe", "Recipe"),
    ("Recipe Box Brownies", "Recipe Box Brownies"),
    ("The Recipe Tin lasagne", "The Recipe Tin lasagne"),
    ("Quick Recipe Idea", "Quick Recipe Idea"),
    ("Grandma's Recipe Cookies", "Grandma's Recipe Cookies"),
    ("Chef John's Recipe for Fish Tacos", "Chef John's Recipe for Fish Tacos"),
    ("Recipe for Banana Bread", "Banana Bread"),
    ("Recipe for a Perfect Roast", "Perfect Roast"),
    ("Recipe for the", "Recipe for the"),
    ("Recipe of the Day: Dal", "Recipe of the Day: Dal"),
    ("Recipe: Dal", "Dal"),
    ("Recipe - Dal", "Dal"),
    ("Recipe-tested Chili", "Recipe-tested Chili"),
    ("Recipe-Box Brownies", "Recipe-Box Brownies"),
    ("Recipe (Easy) Dal", "Recipe (Easy) Dal"),
    ("Moist Banana Bread: Recipe", "Moist Banana Bread"),
    ("Banana Bread Recipe: Moist and Easy", "Banana Bread Recipe: Moist and Easy"),
    ("Pie Recipe \u2014 Apple Pie", "Pie Recipe \u2014 Apple Pie"),
    ("Tarka Dal Recipe  ", "Tarka Dal"),
    ("Mac & Cheese Recipe!", "Mac & Cheese"),
    # possessives and pronouns
    ("Mum's Recipe", "Mum's Recipe"),
    ("Mum\u2019s Recipe", "Mum\u2019s Recipe"),
    ("Grandma\u2019s Recipe", "Grandma\u2019s Recipe"),
    ("Kids' Recipe", "Kids' Recipe"),
    ("Kids\u2019 Recipe", "Kids\u2019 Recipe"),
    ("My Recipe", "My Recipe"),
    ("Your Recipe", "Your Recipe"),
    ("Our Family Recipe", "Our Family Recipe"),
    ("Their Secret Recipe", "Their Secret Recipe"),
    ("His and Hers Recipe", "His and Hers Recipe"),
    ("My Mum's Famous Dal Recipe", "My Mum's Famous Dal Recipe"),
    ("My Recipe: Dal", "My Recipe: Dal"),
    ("Family Recipe: Dal", "Family Recipe: Dal"),
    ("Secret Recipe - Chili", "Secret Recipe - Chili"),
    ("5-Minute Recipe - Hummus", "5-Minute Recipe - Hummus"),
    ("Nan's recipe's best scones", "Nan's recipe's best scones"),
    ("Mum's Recipe, Revisited", "Mum's Recipe, Revisited"),
    ("Mum's Recipe (Revisited)", "Mum's Recipe (Revisited)"),
    # site tails, brackets, colons
    ("Butter Chicken Recipe - BBC Good Food", "Butter Chicken"),
    ("Pancakes - Allrecipes", "Pancakes"),
    ("Easy Pancake Recipe | BBC Good Food", "Easy Pancake"),
    ("Quick Naan Recipe | The Spruce Eats", "Quick Naan"),
    ("Pad Thai \u2013 Authentic Recipe", "Pad Thai"),
    ("Chicken Tikka Masala (Restaurant Style) Recipe", "Chicken Tikka Masala (Restaurant Style)"),
    ("Chicken Tikka Masala Recipe (Restaurant Style)", "Chicken Tikka Masala (Restaurant Style)"),
    ("Lentil Soup (Vegan Recipe)", "Lentil Soup"),
    ("Easy Chilli [Recipe]", "Easy Chilli"),
    ("Dal Recipe (Easy)", "Dal"),
    ("Lemon Rice Recipe (Chitranna)", "Lemon Rice (Chitranna)"),
    ("Sambar Recipe, How to Make Sambar", "Sambar"),
    ("How to Make Butter Chicken (Authentic Indian Recipe)", "Butter Chicken"),
    ("How to Make Masala Chai", "Masala Chai"),
    ("Classic Victoria Sponge Recipe", "Classic Victoria Sponge"),
    ("Classic Victoria sandwich", "Classic Victoria sandwich"),
    # capitals and other languages
    ("BEST EVER CHILLI RECIPE", "BEST EVER CHILLI"),
    ("RECIPE: DAL", "DAL"),
    ("RECIPE FOR LEMON CAKE", "LEMON CAKE"),
    ("Jalape\u00f1o Poppers Recipe", "Jalape\u00f1o Poppers"),
    ("G\u00e2teau au chocolat", "G\u00e2teau au chocolat"),
    ("Recette de ratatouille", "Recette de ratatouille"),
    ("Rezept f\u00fcr Apfelkuchen", "Rezept f\u00fcr Apfelkuchen"),
    ("Wei\u00dfwurst Rezept", "Wei\u00dfwurst Rezept"),
    ("Poulet r\u00f4ti \u00e0 l\u2019ancienne", "Poulet r\u00f4ti \u00e0 l\u2019ancienne"),
]


@pytest.mark.parametrize(("written", "cleaned"), RECIPE_TITLES)
def test_recipe_title_table(written: str, cleaned: str) -> None:
    from mealwright.line_prep import clean_recipe_name

    assert clean_recipe_name(written) == cleaned


@pytest.mark.parametrize(
    ("written", "cleaned"),
    [
        ("Classic Victoria sandwich recipe", "Classic Victoria sandwich"),
        ("Classic Victoria sandwich Recipe", "Classic Victoria sandwich"),
        ("How to Make Butter Chicken (Authentic Indian Recipe)", "Butter Chicken"),
        ("Butter chicken - the best curry recipe", "Butter chicken"),
        ("Butter Chicken (Authentic)", "Butter Chicken"),
        ("Recipe", "Recipe"),
        ("Recipe book cake", "Recipe book cake"),
        # F91 (proposed, for cabledrawer): "Recipe" goes only where it is a label.
        ("Recipe for Banana Bread", "Banana Bread"),
        ("Recipe for the best dal", "Best dal"),
        ("Recipe: Banana Bread", "Banana Bread"),
        ("RECIPE: Dal", "Dal"),
        ("Recipe - Dal", "Dal"),
        ("Recipe", "Recipe"),
        ("The Best Recipe", "The Best"),
        ("Dal Recipe (Easy)", "Dal"),
        ("Recipe Box Brownies", "Recipe Box Brownies"),
        ("Recipe of the Day: Dal", "Recipe of the Day: Dal"),
        ("Recipe for the Recipe", "Recipe for the Recipe"),
        ("Recipe for the", "Recipe for the"),
        ("Recipe for a", "Recipe for a"),
        ("Grandma's Recipe", "Grandma's Recipe"),
        ("Mum's Recipe", "Mum's Recipe"),
        ("Mum\u2019s Recipe", "Mum\u2019s Recipe"),
        ("Mum's Recipe, Revisited", "Mum's Recipe, Revisited"),
        ("Mum's Recipe (Revisited)", "Mum's Recipe (Revisited)"),
        ("Nan's recipe's best scones", "Nan's recipe's best scones"),
        ("The Recipe Tin lasagne", "The Recipe Tin lasagne"),
        ("Recipe-tested Chili", "Recipe-tested Chili"),
        ("Recipe-Box Brownies", "Recipe-Box Brownies"),
        ("My Recipe: Dal", "My Recipe: Dal"),
        ("Family Recipe: Dal", "Family Recipe: Dal"),
        ("Secret Recipe - Chili", "Secret Recipe - Chili"),
        ("5-Minute Recipe - Hummus", "5-Minute Recipe - Hummus"),
        ("Lasagne Recipe - Easy Dinner", "Lasagne Recipe - Easy Dinner"),
        ("Gâteau au chocolat", "Gâteau au chocolat"),
        ("Rezept für Apfelkuchen", "Rezept für Apfelkuchen"),
        ("Recette de ratatouille", "Recette de ratatouille"),
        ("Sambar Recipe, How to Make Sambar", "Sambar"),
        ("Lemon Rice Recipe (Chitranna)", "Lemon Rice (Chitranna)"),
        ("Classic Victoria sandwich", "Classic Victoria sandwich"),
        ("Classic Lemon Rice Recipe: How to Make It", "Classic Lemon Rice"),
        ("Dal recipe - how to cook dal", "Dal"),
        ("Recipes for two", "Recipes for two"),
        ("Unrecipe cake", "Unrecipe cake"),
        ("Banana bread", "Banana bread"),
    ],
)
def test_recipe_name_patterns(written: str, cleaned: str) -> None:
    from mealwright.line_prep import clean_recipe_name

    assert clean_recipe_name(written) == cleaned


def test_tags_get_capitals_and_synonyms_are_joined() -> None:
    from mealwright.line_prep import tidy_tags

    assert tidy_tags(["dinner", "MAINS", "Main course", "vegetarian", "veggie", "gluten-free"]) == [
        "Dinner",
        "Main",
        "Vegetarian",
        "Gluten free",
    ]
    assert tidy_tags(["BBC", "easy", " ", "easy"]) == ["BBC", "Easy"]


def test_ingredient_name_capitals() -> None:
    from mealwright.line_prep import tidy_ingredient_name

    assert tidy_ingredient_name("Kashmiri Chillies") == "Kashmiri chillies"
    assert tidy_ingredient_name("KASHMIRI CHILLIES") == "Kashmiri chillies"
    assert tidy_ingredient_name("kashmiri chillies") == "Kashmiri chillies"
    assert tidy_ingredient_name("Worcestershire sauce") == "Worcestershire sauce"
    assert tidy_ingredient_name("King Edward potatoes") == "King Edward potatoes"
    assert tidy_ingredient_name("Milk") == "Milk"


def test_converted_amounts_are_rounded_as_a_cook_writes_them() -> None:
    assert core("12 oz flour") == (D(340), "g", "flour")
    assert core("14 oz tomatoes") == (D(397), "g", "tomatoes")
    assert core("1 lb mince") == (D(454), "g", "mince")
    assert core("1/4 oz yeast")[0] == D("7.09") or core("1/4 oz yeast")[0] == D("7.1")
    assert core("2 pints milk") == (D(1136), "ml", "milk")


# --- Review round 1 ------------------------------------------------------------------------------


def test_scale_button_check_is_fast_on_long_lines() -> None:
    """Security: the scale-button pattern used to backtrack exponentially."""
    import time

    from mealwright.line_prep import is_page_junk

    for line in ("x " * 5000, "x " * 24 + "y", "1x " * 5000 + "y", "½x" * 5000 + "!"):
        started = time.perf_counter()
        assert not is_page_junk(line)
        assert time.perf_counter() - started < 0.1, line[:20]
    assert is_page_junk("½x1×2×") and is_page_junk("1x 2x 3x")


def test_every_new_pattern_is_fast_on_100_kb_of_its_own_pieces() -> None:
    """Security sweep: each pattern added in this PR against 100 kB of repeats of its pieces."""
    import time

    from mealwright import ingredient_reader as reader
    from mealwright import line_prep as prep

    pieces = [
        "x ", "1x ", "(Note ", "( ", "(, ", "[3] ", " and ", " + ", " or ", " / ", "For the ",
        "recipe ", "| ", "- ", "(", ")", "heaped ", "a handful ", "1 ", "½ ", "cloves, ",
        "(variety) ", " to taste ", "made with ", "and cut ", "1 14-ounce ", "Recipe (",
    ]  # fmt: skip
    for piece in pieces:
        big = piece * (100_000 // len(piece))
        for name, call in (
            ("strip_footnotes", prep.strip_footnotes),
            ("is_page_junk", prep.is_page_junk),
            ("is_ingredient_heading", prep.is_ingredient_heading),
            ("is_step_heading", prep.is_step_heading),
            ("serving_heading", prep.serving_heading),
            ("clean_recipe_name", prep.clean_recipe_name),
            ("tidy_ingredient_name", prep.tidy_ingredient_name),
            ("tidy_tags", lambda t: prep.tidy_tags([t])),
            ("split_line", reader.split_line),
            ("read_lines", reader.read_lines),
        ):
            started = time.perf_counter()
            call(big)
            assert time.perf_counter() - started < 1.0, (name, piece)
        # The reader's limit is a line of 1,000 characters: at that size it is fast, too.
        started = time.perf_counter()
        reader.read_line(big[:1000])
        assert time.perf_counter() - started < 0.3, ("read_line", piece)


@pytest.mark.parametrize(
    "text",
    [
        "999999999999 999999999999oz can beans",
        "999999999999 x 999999999999 lb tins beans",
        "999999999999 999999999999 gallon cans beans",
        "999999999999999999 oz flour",
        "999999999999999999999999 pints milk",
    ],
)
def test_a_huge_converted_amount_never_raises(text: str) -> None:
    line = read_line(text, pint_ml=PINT_UK)
    assert line.text == text  # read_line answered, whatever it made of it
    assert line.amount is None or line.amount > 0


def test_variety_in_brackets_is_never_another_name() -> None:
    a = read_line("4 dried red chilies (kashmiri variety)")
    b = read_line("4 dried red chilies (kashmiri or byadgi variety)")
    c = read_line("4 dried red chilies ((kashmiri or byadgi) (less spicy variety))")
    assert a.name == b.name == c.name == "kashmiri dried red chilies"
    assert a.other_names == ()
    assert b.other_names == c.other_names == ("byadgi",)
    assert "variety" in (a.note or "") and "variety" in (b.note or "")


def test_a_jar_and_its_weight_three_ways() -> None:
    line = same(
        "1/2 a 340g jar strawberry jam",
        "half a jar (340g) strawberry jam",
        "half a 340g jar strawberry jam",
        "0.5 jar (340 g) strawberry jam",
    )
    assert (line.amount, line.unit, line.name) == (D(170), "g", "strawberry jam")


def test_a_bracketed_tin_size_is_the_same_as_the_hyphenated_one() -> None:
    line = same("1 (14 ounce) can tomatoes", "one 14-ounce can tomatoes", "1 14 oz can tomatoes")
    assert (line.amount, line.unit, line.name) == (D(397), "g", "tomatoes")


def test_olive_oil_and_a_sprinkle_of_salt_is_two_lines() -> None:
    from mealwright.ingredient_reader import read_lines

    for text in ("olive oil and a sprinkle of salt", "olive oil + a sprinkle of salt"):
        assert [r.name for r in read_lines(text)] == ["olive oil", "salt"], text
    assert len(read_lines("macaroni and a sprinkle of cheese, 2")) <= 2


def test_garlic_cloves_after_the_name_is_the_same_as_before() -> None:
    a, b = read_line("2 garlic cloves"), read_line("2 cloves garlic")
    assert (
        (a.amount, a.size_word, a.name)
        == (b.amount, b.size_word, b.name)
        == (D(2), "cloves", "garlic")
    )
    assert read_line("1 cinnamon stick").name == "cinnamon stick"  # stick is not one of them


def test_a_handful_after_the_name_is_the_same_as_before() -> None:
    a = read_line("golden raisins, a handful")
    b = read_line("a handful of golden raisins")
    assert (a.amount, a.size_word, a.name) == (b.amount, b.size_word, b.name)
    assert read_line("salt, a pinch").name == "salt"


def test_and_joining_one_name_does_not_split() -> None:
    from mealwright.ingredient_reader import read_lines

    for text in ("sweet and sour sauce, to taste", "oil and vinegar dressing to serve"):
        assert len(read_lines(text)) == 1, text
    assert len(read_lines("salt and pepper to taste")) == 2


def test_tags_acronyms_and_sweet() -> None:
    from mealwright.line_prep import tidy_tags

    assert tidy_tags(["bbq", "Sweet"]) == ["BBQ", "Sweet"]


def test_a_site_name_after_the_title_is_dropped() -> None:
    from mealwright.line_prep import clean_recipe_name

    assert clean_recipe_name("Easy Pancake Recipe | BBC Good Food") == "Easy Pancake"
    assert clean_recipe_name("Pancakes - Allrecipes") == "Pancakes"
    assert clean_recipe_name("Chicken - Rice Bowl") == "Chicken - Rice Bowl"


# --- Review round 2 ------------------------------------------------------------------------------


def test_normalise_is_fast_on_a_run_of_open_brackets() -> None:
    import time

    from mealwright.names import normalise

    for hostile in ("(" * 200_000, "[" * 200_000, "(note 1" * 30_000):
        started = time.perf_counter()
        normalise(hostile)
        assert time.perf_counter() - started < 0.5, hostile[:8]
    assert normalise("Flour (plain) [sifted]") == normalise("Flour")


def test_the_empty_bracket_pattern_is_fast_on_non_breaking_spaces() -> None:
    import time

    from mealwright.line_prep import strip_footnotes

    started = time.perf_counter()
    strip_footnotes("(" + " " * 100_000)
    assert time.perf_counter() - started < 0.2


def test_and_between_two_seasonings_is_still_two_lines() -> None:
    from mealwright.ingredient_reader import read_lines

    for text, names in (
        ("salt and black pepper to taste", ["salt", "black pepper"]),
        ("salt and freshly ground black pepper, to taste", ["salt", "black pepper"]),
        ("sweet and sour sauce, to taste", ["sweet and sour sauce"]),
        ("oil and vinegar dressing to serve", ["oil and vinegar dressing"]),
    ):
        assert [r.name for r in read_lines(text)] == names, text


def test_freshly_ground_goes_to_the_note_only_for_pepper() -> None:
    # C1 security round 3, L3: the rule is for "salt and freshly ground black pepper", not
    # every ground spice or nut.
    assert read_line("2 tsp freshly ground black pepper").name == "black pepper"
    assert read_line("1 tsp freshly ground white pepper").name == "white pepper"
    assert read_line("100 g freshly ground almonds").name == "ground almonds"
    assert read_line("1 tsp freshly ground cumin").name == "ground cumin"


def test_nested_brackets_keep_their_inner_words_in_the_matching_key() -> None:
    # C1 security round 3, L2: the bracket pattern is linear, so only the inner bracket goes.
    # The key is never stored; only foods named with nested brackets match differently.
    from mealwright.names import normalise

    assert normalise("Chilli (Kashmiri (dried))") == "chilli kashmiri"
    assert normalise("Chilli (dried)") == "chilli"


def test_only_cloves_and_sprigs_move_from_after_the_name() -> None:
    for text in ("4 chicken fillets", "6 bacon rasher", "3 celery stalks"):
        assert read_line(text).size_word is None, text
        assert read_line(text).name.split()[-1] in text
    assert read_line("2 thyme sprigs").name == "thyme"


def test_a_bracketed_weight_is_the_total_for_several_tins() -> None:
    two = read_line("2 tins (800 g) tomatoes")
    assert (two.amount, two.unit, two.name) == (D(800), "g", "tomatoes")
    one = read_line("1 tin (400 g) tomatoes")
    assert (one.amount, one.unit) == (D(400), "g")
    assert core("half a jar (340g) strawberry jam") == (D(170), "g", "strawberry jam")


def test_variety_regex_is_whole_words_and_site_tail_keeps_taste() -> None:
    from mealwright.line_prep import clean_recipe_name

    assert read_line("4 dried red chilies (varietyx)").other_names != ()
    assert read_line("4 dried red chilies (kashmiri variety)").name == "kashmiri dried red chilies"
    assert clean_recipe_name("Pancakes - Taste the difference") == "Pancakes - Taste the difference"
    assert clean_recipe_name("Pancakes - Kitchen sink") == "Pancakes - Kitchen sink"
