# ruff: noqa: RUF001  (these tests use look-alike dashes, signs and spaces on purpose)
"""Reading one ingredient line (docs/dev/ingredient-reader.md)."""

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mealwright.ingredient_reader import MAX_LINE_CHARS, ReadLine, read_line, working_text

D = Decimal


def core_of(text: str) -> tuple[Decimal | None, str | None, str]:
    line = read_line(text)
    return line.amount, line.unit, line.name


def amount_of(text: str) -> tuple[Decimal | None, str | None]:
    line = read_line(text)
    return line.amount, line.unit


# --- Every number form ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "amount"),
    [
        ("2 onions", D(2)),
        ("½ tsp salt", D("0.5")),
        ("1½ cups rice", D("1.5")),
        ("1 ½ cups rice", D("1.5")),
        ("1 1/2 cups rice", D("1.5")),
        ("1/2 tsp salt", D("0.5")),
        ("0.5 tsp salt", D("0.5")),
        (".5 tsp salt", D("0.5")),
        ("1,5 tsp salt", D("1.5")),
        ("1.25 kg flour", D("1.25")),
        ("1,500 g flour", D(1500)),
        ("¼ tsp salt", D("0.25")),
        ("¾ cup milk", D("0.75")),
        ("⅓ cup milk", D("0.333")),
        ("⅔ cup milk", D("0.667")),
        ("⅛ tsp salt", D("0.125")),
        ("2⅓ cups milk", D("2.333")),
        ("1⁄ 2 tsp salt", D("0.5")),  # a fraction slash
        ("1-1/2 cups rice", D("1.5")),
        ("  3   eggs ", D(3)),
    ],
)
def test_every_number_form(text: str, amount: Decimal) -> None:
    assert read_line(text).amount == amount


def test_amounts_have_no_trailing_zeros() -> None:
    assert str(read_line("2 onions").amount) == "2"
    assert str(read_line("1.50 kg flour").amount) == "1.5"


def test_a_number_in_hindi_digits() -> None:
    assert read_line("२ onions").amount == D(2)


@pytest.mark.parametrize("text", ["0 g salt", "0.0001 g salt", "2000000 g flour", "1/0 tsp salt"])
def test_amounts_that_cannot_be_stored_are_no_amount(text: str) -> None:
    line = read_line(text)
    assert line.amount is None
    assert not line.counts
    assert line.readable


def test_a_very_long_number_is_not_a_number() -> None:
    line = read_line("1" * 40 + " g flour")
    assert line.amount is None


# --- Ranges ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "2-3 green chillies",
        "2–3 green chillies",  # en dash
        "2—3 green chillies",  # em dash
        "2 - 3 green chillies",
        "2 to 3 green chillies",
        "2 TO 3 green chillies",
        "2 or 3 green chillies",
        "3-2 green chillies",
    ],
)
def test_a_range_gives_the_higher_number(text: str) -> None:
    line = read_line(text)
    assert line.amount == D(3)
    assert line.name == "green chillies"
    assert line.text == text  # the words are kept as written


def test_ranges_with_units_and_fractions() -> None:
    assert amount_of("1-2 tbsp oil") == (D(2), "tbsp")
    assert amount_of("½-1 tsp salt") == (D(1), "tsp")
    assert amount_of("200g-300g flour") == (D(300), "g")
    assert amount_of("1 to 1½ cups rice") == (D("1.5"), "cup")
    assert amount_of("1 1/2 - 2 cups rice") == (D(2), "cup")


def test_a_range_across_two_units_keeps_the_bigger_side_with_its_unit() -> None:
    assert amount_of("200g-1kg flour") == (D(1), "kg")
    assert amount_of("750 ml-1 l stock") == (D(1), "l")
    assert amount_of("500g - 1kg chicken") == (D(1), "kg")
    assert amount_of("1 kg - 500 g potatoes") == (D(1), "kg")  # the first side is the bigger
    assert amount_of("1 l to 500 ml stock") == (D(1), "l")
    assert amount_of("2 tbsp - 1 cup milk") == (D(1), "cup")
    assert amount_of("1 cup - 500 ml milk") == (D(500), "ml")
    assert amount_of("100 g - 2 kg flour") == (D(2), "kg")
    # Units that can't be compared (weight and volume): the second side, as written.
    assert amount_of("100 g - 2 ml flour") == (D(2), "ml")


def test_pack_multiples_are_read_once_so_a_long_chain_cannot_go_deep() -> None:
    line = read_line("1x" * 499 + "1 flour")
    assert line.readable is not None  # no RecursionError
    assert read_line("2 x 3 x 400g tins flour").amount is not None


# --- Units -----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("word", "unit"),
    [
        ("g", "g"),
        ("gm", "g"),
        ("gms", "g"),
        ("grams", "g"),
        ("gram", "g"),
        ("kg", "kg"),
        ("kgs", "kg"),
        ("kilo", "kg"),
        ("kilograms", "kg"),
        ("ml", "ml"),
        ("mls", "ml"),
        ("millilitres", "ml"),
        ("milliliter", "ml"),
        ("l", "l"),
        ("L", "l"),
        ("ltr", "l"),
        ("litre", "l"),
        ("litres", "l"),
        ("liter", "l"),
        ("tsp", "tsp"),
        ("tsp.", "tsp"),
        ("Tsp", "tsp"),
        ("tsps", "tsp"),
        ("t", "tsp"),
        ("teaspoon", "tsp"),
        ("teaspoons", "tsp"),
        ("tbsp", "tbsp"),
        ("Tbsp", "tbsp"),
        ("tbs", "tbsp"),
        ("tbsp.", "tbsp"),
        ("T", "tbsp"),
        ("tablespoon", "tbsp"),
        ("Tablespoons", "tbsp"),
        ("cup", "cup"),
        ("cups", "cup"),
        ("c", "cup"),
        ("pinch", "pinch"),
        ("pinches", "pinch"),
    ],
)
def test_units_and_their_spellings(word: str, unit: str) -> None:
    for text in (f"2 {word} sugar", f"2{word} sugar"):
        line = read_line(text)
        assert (line.amount, line.unit, line.name) == (D(2), unit, "sugar"), text


def test_a_unit_has_to_be_a_whole_word() -> None:
    line = read_line("2 garlic cloves")  # 0.7.0: "cloves" after the name is still the size word
    assert (line.amount, line.unit, line.size_word, line.name) == (D(2), None, "cloves", "garlic")
    line = read_line("1 gram-flour mix")
    assert line.unit is None
    assert line.name == "gram-flour mix"
    assert read_line("3 T-bone steaks").unit is None


def test_a_plain_count_has_no_unit() -> None:
    line = read_line("3 eggs")
    assert (line.amount, line.unit, line.size_word, line.counts) == (D(3), None, None, True)


def test_pints_and_the_like_are_no_amount() -> None:
    for text in ("2 pints milk", "1 fl oz brandy", "3 quarts stock"):
        line = read_line(text)
        assert line.amount is None
        assert not line.counts
        assert line.note is not None
        assert line.readable
    assert read_line("2 pints milk").name == "milk"
    assert read_line("2 pints milk").note == "2 pints"
    assert read_line("1 fl oz brandy").name == "brandy"


@pytest.mark.parametrize(
    ("text", "grams"),
    [
        ("1 oz butter", D(28)),
        ("8 oz spinach", D(227)),
        ("2 ounces cheese", D(57)),
        ("½ oz yeast", D(14)),
        ("1 lb potatoes", D(454)),
        ("2 lbs potatoes", D(907)),
        ("1½ pounds flour", D(680)),
        ("1 pound flour", D(454)),
    ],
)
def test_ounces_and_pounds_on_their_own_convert_and_are_rounded_as_a_cook_writes(
    text: str, grams: D
) -> None:
    # cabledrawer 23 Oct, question 18: 1 oz = 28.35 g, 1 lb = 453.6 g, so they count; 0.7.0 rounds
    # the result to a whole gram (two decimals only below 10 g): 340 g, not 340.2 g.
    line = read_line(text)
    assert (line.amount, line.unit) == (grams, "g")
    assert line.counts
    assert line.chosen  # the line is kept as written too
    assert line.note is None


def test_a_metric_amount_beside_ounces_still_wins() -> None:
    assert amount_of("8 oz spinach (225g)") == (D(225), "g")
    assert amount_of("200 g (7 oz) spinach") == (D(200), "g")


@pytest.mark.parametrize(
    ("text", "amount", "unit"),
    [
        ("3-2 tbsp oil", D(3), "tbsp"),
        ("3 - 2 tbsp oil", D(3), "tbsp"),
        ("3 to 2 cups rice", D(3), "cup"),
        ("2-3 tbsp oil", D(3), "tbsp"),
        ("5-1 g salt", D(5), "g"),
    ],
)
def test_a_range_written_high_to_low_takes_the_higher_number(
    text: str, amount: D, unit: str
) -> None:
    # cabledrawer 23 Oct, question 18: "3-2 tbsp" (written with an en dash) is 3 tbsp, not 2.
    assert amount_of(text) == (amount, unit)


def test_a_chain_of_pack_multiples_is_multiplied() -> None:
    line = read_line("2 x 2 x 400g tins chopped tomatoes")
    assert (line.amount, line.unit, line.size_word) == (D(1600), "g", "tins")
    assert line.name == "chopped tomatoes"
    assert read_line("2 × 3 × 15ml spoons oil").amount == D(90)
    # At most three numbers are multiplied; the rest isn't a pack multiple.
    assert read_line("2 x 2 x 2 x 400g tins").amount != D(3200)
    assert read_line("2 x 3 x 400g tins flour").amount == D(2400)
    assert read_line("2 x 3 onions").amount == D(2)  # still no unit: not a pack multiple


def test_text_picked_from_several_numbers_is_marked_chosen() -> None:
    for text in (
        "2-3 green chillies",
        "1 cup (240 ml) rice",
        "2 x 400g tins tomatoes",
        "8 oz spinach",
    ):
        assert read_line(text).chosen, text
    for text in ("2 green chillies", "200 g rice", "1 cup flour", "salt to taste"):
        assert not read_line(text).chosen, text


def test_control_characters_are_spaces_and_private_use_characters_are_dropped() -> None:
    # #55 round 2, L3: a control character between words used to join them ("2 cups" +
    # U+001F + "rice" became "2 cupsrice"), and private-use or unassigned characters stayed.
    for control in ("\x1c", "\x1d", "\x1e", "\x1f", "\x00", "\x07", "\x85"):
        line = read_line(f"2 cups{control}basmati rice")
        assert (line.amount, line.unit, line.name) == (D(2), "cup", "basmati rice"), control
    assert read_line("200 g\ue000 dal").name == "dal"  # private use
    assert read_line("200 g dal\U000f0000").name == "dal"  # private use, plane 15
    assert read_line("200 g da\u0378l").name == "dal"  # unassigned
    assert working_text("a\x1fb") == "a b"
    assert working_text("a\ue000b") == "ab"


# --- Two units -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "amount", "unit", "name"),
    [
        ("1 cup (240 ml) rice", D(240), "ml", "rice"),
        ("1 cup (about 240 ml) rice", D(240), "ml", "rice"),
        ("200 g (7 oz) spinach", D(200), "g", "spinach"),
        ("200g / 7oz spinach", D(200), "g", "spinach"),
        ("7 oz (200 g) spinach", D(200), "g", "spinach"),
        ("8 oz / 225 g spinach", D(225), "g", "spinach"),
        ("1 cup (125 g) flour", D(125), "g", "flour"),
        ("1 kg (1000 g) flour", D(1), "kg", "flour"),
        ("2 tbsp (30 ml) oil", D(30), "ml", "oil"),
        ("1 cup (8 oz) rice", D(1), "cup", "rice"),  # no metric one: the cup stays a cup
        ("1 cup rice", D(1), "cup", "rice"),
    ],
)
def test_two_units_the_metric_one_is_the_amount(
    text: str, amount: Decimal, unit: str, name: str
) -> None:
    line = read_line(text)
    assert (line.amount, line.unit, line.name) == (amount, unit, name)
    assert line.text == text
    assert line.note is None


def test_a_cup_alone_stays_a_cup() -> None:
    # The household's own cup turns it into ml when the line is matched (ingredient_match).
    assert amount_of("1 cup rice") == (D(1), "cup")
    assert amount_of("½ cup rice") == (D("0.5"), "cup")


def test_pack_multiples() -> None:
    line = read_line("1 x 400g tin chopped tomatoes")
    assert (line.amount, line.unit, line.size_word) == (D(400), "g", "tin")
    assert line.name == "chopped tomatoes"  # a tin keeps "chopped": it is the product
    assert line.counts
    line = read_line("2 x 400 g tins chopped tomatoes")
    assert (line.amount, line.unit, line.size_word) == (D(800), "g", "tins")
    line = read_line("3 × 15ml spoons oil")
    assert (line.amount, line.unit) == (D(45), "ml")
    assert read_line("2 x 3 onions").amount == D(2)  # no unit: not a pack multiple


@pytest.mark.parametrize(
    ("text", "amount", "unit", "name", "note"),
    [
        ("1 cup flour (125g)", D(125), "g", "flour", None),
        ("1 cup rice (about 200 g)", D(200), "g", "rice", None),
        ("2 tbsp oil (30 ml), plus extra", D(30), "ml", "oil", "plus extra"),
        ("1 cup flour (sifted) (125g)", D(125), "g", "flour", "sifted"),
        ("8 oz spinach (225g)", D(225), "g", "spinach", None),
        ("200 g flour (1 cup)", D(200), "g", "flour", "1 cup"),  # already metric: kept
        ("2 onions (300 g)", D(2), None, "onions", "300 g"),  # a count is not a second unit
        ("1 cup flour (125g of it)", D(1), "cup", "flour", "125g of it"),
    ],
)
def test_a_bracket_after_the_name_with_only_a_metric_amount_is_the_amount(
    text: str, amount: Decimal, unit: str | None, name: str, note: str | None
) -> None:
    line = read_line(text)
    assert (line.amount, line.unit, line.name, line.note) == (amount, unit, name, note)


def test_a_count_with_its_weight_in_brackets() -> None:
    line = read_line("1 (400 g) can chickpeas, drained")
    assert (line.amount, line.unit, line.size_word) == (D(400), "g", "can")
    assert line.name == "chickpeas"
    assert line.note == "drained"
    # 0.7.0: the same as "one 14-ounce can chickpeas" (397 g).
    line = read_line("1 (14 oz) can chickpeas")
    assert (line.amount, line.unit, line.size_word) == (D(397), "g", "can")
    assert line.counts


# --- Size words ------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "amount", "word", "name"),
    [
        ("1 bunch coriander", D(1), "bunch", "coriander"),
        ("2 bunches coriander", D(2), "bunches", "coriander"),
        ("1 sprig curry leaves", D(1), "sprig", "curry leaves"),
        ("a sprig of thyme", D(1), "sprig", "thyme"),
        ("a handful of mint", D(1), "handful", "mint"),
        ("handful of mint", D(1), "handful", "mint"),
        ("2 cloves garlic", D(2), "cloves", "garlic"),
        ("2 large cloves of garlic", D(2), "cloves", "garlic"),
        ("1 can chickpeas", D(1), "can", "chickpeas"),
        ("1 dozen eggs", D(1), "dozen", "eggs"),
        ("2 packets noodles", D(2), "packets", "noodles"),
    ],
)
def test_a_size_word_is_kept_and_does_not_count_by_itself(
    text: str, amount: Decimal, word: str, name: str
) -> None:
    line = read_line(text)
    assert (line.amount, line.unit, line.size_word, line.name) == (amount, None, word, name)
    assert not line.counts
    assert line.readable


@pytest.mark.parametrize(
    ("text", "amount", "unit", "word", "name"),
    [
        ("a 400g tin chopped tomatoes", D(400), "g", "tin", "chopped tomatoes"),
        ("an 800 g tin chopped tomatoes", D(800), "g", "tin", "chopped tomatoes"),
        ("one 400g tin chickpeas", D(400), "g", "tin", "chickpeas"),
        ("a 14 oz (400 g) can beans", D(400), "g", "can", "beans"),
        ("a cup of rice", D(1), "cup", None, "rice"),
        ("a 2 cm piece ginger", None, None, "piece", "ginger"),
        ("a large onion", D(1), None, None, "onion"),
    ],
)
def test_a_measure_after_a_or_one_is_read_before_falling_back_to_one(
    text: str, amount: Decimal | None, unit: str | None, word: str | None, name: str
) -> None:
    line = read_line(text)
    assert (line.amount, line.unit, line.size_word, line.name) == (amount, unit, word, name)


def test_a_few_is_kept_and_has_no_amount() -> None:
    for text in ("a few curry leaves", "few curry leaves", "some curry leaves"):
        line = read_line(text)
        assert line.amount is None
        assert line.size_word in ("few", "some")
        assert line.name == "curry leaves"
        assert not line.counts
    assert read_line("a little oil").size_word == "little"
    assert read_line("a bit of salt").name == "salt"
    assert read_line("little gem lettuce").name == "little gem lettuce"


def test_the_households_own_size_words() -> None:
    assert read_line("1 dabba curd").size_word is None
    line = read_line("1 dabba curd", size_words=["dabba", "Dabbas"])
    assert (line.size_word, line.name) == ("dabba", "curd")


# --- No real amount --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "name", "note"),
    [
        ("salt to taste", "salt", "to taste"),
        ("Salt, to taste", "Salt", "to taste"),
        ("salt or to taste", "salt", "or to taste"),
        ("salt as needed", "salt", "as needed"),
        ("oil as required", "oil", "as required"),
        ("coriander leaves for garnish", "coriander leaves", "for garnish"),
        ("oil for frying", "oil", "for frying"),
        ("lemon wedges, to serve", "lemon wedges", "to serve"),
        ("chilli flakes (optional)", "chilli flakes", "optional"),
    ],
)
def test_no_real_amount(text: str, name: str, note: str) -> None:
    line = read_line(text)
    assert (line.amount, line.unit, line.name, line.note) == (None, None, name, note)
    assert not line.counts
    assert line.readable  # not a problem


def test_a_number_the_line_does_have_is_still_its_amount() -> None:
    line = read_line("1 tsp salt, or to taste")
    assert (line.amount, line.unit, line.counts) == (D(1), "tsp", True)
    assert line.note == "or to taste"


def test_a_pinch_is_kept_and_never_counts() -> None:
    for text in ("a pinch of salt", "pinch of salt", "1 pinch salt", "2 pinches salt"):
        line = read_line(text)
        assert line.unit == "pinch"
        assert line.amount is not None
        assert not line.counts
        assert line.name == "salt"


# --- The name and the note -------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "name", "note"),
    [
        ("2 onions, finely chopped", "onions", "finely chopped"),
        ("finely chopped red onions", "red onions", "finely chopped"),
        ("2 large onions, finely chopped", "onions", "large, finely chopped"),
        ("3 cloves garlic, crushed", "garlic", "crushed"),
        ("onions, chopped", "onions", "chopped"),
        ("2 onions chopped", "onions", "chopped"),
        ("2 peeled and chopped tomatoes", "tomatoes", "peeled chopped"),
        ("1 tbsp freshly grated ginger", "ginger", "freshly grated"),
        ("1 tsp salt, plus extra to taste", "salt", "plus extra to taste"),
        ("200 g paneer (cottage cheese), cubed", "paneer", "cubed"),
        ("2 onions (about 300 g), sliced", "onions", "about 300 g, sliced"),
        ("1 cup dried chickpeas, soaked overnight", "dried chickpeas", "soaked overnight"),
        ("1 tsp ground cumin", "ground cumin", None),  # "ground" is part of what it is
        ("1 cup cooked rice", "cooked rice", None),
    ],
)
def test_the_name_and_the_note(text: str, name: str, note: str | None) -> None:
    line = read_line(text)
    assert (line.name, line.note) == (name, note)
    assert line.text == text


def test_the_name_with_prep_words_kept() -> None:
    line = read_line("2 large onions, finely chopped")
    assert line.name_as_written == "large onions"
    assert read_line("finely chopped red onions").name_as_written == "finely chopped red onions"


def test_other_names_from_brackets_and_slashes() -> None:
    line = read_line("1 cup thuvaram paruppu (toor dal)")
    assert (line.name, line.other_names, line.note) == ("thuvaram paruppu", ("toor dal",), None)
    line = read_line("¼ tsp hing / asafoetida")
    assert (line.amount, line.unit, line.name, line.other_names) == (
        D("0.25"),
        "tsp",
        "hing",
        ("asafoetida",),
    )
    line = read_line("1 cup toor dal (arhar dal / tuvar dal)")
    assert line.other_names == ("arhar dal", "tuvar dal")
    line = read_line("2 tbsp ghee (clarified butter), melted")
    assert (line.name, line.other_names, line.note) == ("ghee", ("clarified butter",), "melted")


def test_brackets_that_are_notes_are_not_names() -> None:
    for text, note in (
        ("1 onion (optional)", "optional"),
        ("1 onion (see note)", "see note"),
        ("1 onion (finely chopped)", "finely chopped"),
        ("1 onion (about 2 cups)", "about 2 cups"),
    ):
        line = read_line(text)
        assert line.other_names == (), text
        assert line.note == note, text
        assert line.name == "onion"


def test_a_bracket_that_never_closes() -> None:
    line = read_line("2 onions (the red kind")
    assert line.name == "onions"
    assert line.note == "the red kind"


def test_a_note_is_cut_at_200_characters() -> None:
    line = read_line("1 onion, " + "very finely chopped and then fried " * 20)
    assert line.note is not None
    assert len(line.note) <= 200


# --- Real-looking lines ----------------------------------------------------------------------


def test_uk_packets() -> None:
    line = read_line("1 x 400g tin chopped tomatoes")
    assert line.name == "chopped tomatoes"
    line = read_line("2 x 400g tins coconut milk")
    assert (line.amount, line.name) == (D(800), "coconut milk")
    line = read_line("1 x 15g pack fresh coriander")
    assert (line.amount, line.unit, line.name) == (D(15), "g", "coriander")
    line = read_line("500g pack mince")
    assert (line.amount, line.unit, line.size_word, line.name) == (D(500), "g", "pack", "mince")


def test_indian_recipes() -> None:
    line = read_line("1 cup thuvaram paruppu (toor dal)")
    assert (line.amount, line.unit, line.name) == (D(1), "cup", "thuvaram paruppu")
    line = read_line("1 sprig curry leaves")
    assert (line.size_word, line.name, line.counts) == ("sprig", "curry leaves", False)
    line = read_line("¼ tsp hing / asafoetida")
    assert (line.name, line.other_names) == ("hing", ("asafoetida",))
    line = read_line("2 tbsp நல்லெண்ணெய் (sesame oil)")
    assert (line.amount, line.unit, line.name, line.other_names) == (
        D(2),
        "tbsp",
        "நல்லெண்ணெய்",
        ("sesame oil",),
    )
    line = read_line("1 tsp जीरा (cumin seeds)")
    assert (line.name, line.other_names) == ("जीरा", ("cumin seeds",))
    line = read_line("2-3 green chillies, slit")
    assert (line.amount, line.name, line.note) == (D(3), "green chillies", "slit")
    line = read_line("1 inch piece ginger, grated")
    assert (line.amount, line.size_word, line.name) == (None, "piece", "ginger")


def test_bullets_and_checkboxes_are_ignored() -> None:
    for text in ("▢ 3 eggs", "• 3 eggs", "- 3 eggs", "* 3 eggs", "☐ 3 eggs", "• 3 eggs"):
        assert read_line(text).amount == D(3), text
        assert read_line(text).text == text


def test_leading_about() -> None:
    assert amount_of("About 2 cups milk") == (D(2), "cup")
    assert amount_of("approx. 200 g flour") == (D(200), "g")
    assert amount_of("~200g flour") == (D(200), "g")
    assert read_line("scant 1 tsp salt").amount == D(1)


def test_a_line_with_a_number_in_its_name() -> None:
    assert read_line("5 spice powder").amount == D(5)


def test_hidden_characters_are_ignored_but_the_words_are_kept() -> None:
    text = "2​ onions‮, chopped\x00"
    line = read_line(text)
    assert (line.amount, line.name, line.note, line.text) == (D(2), "onions", "chopped", text)


# --- Lines it cannot read --------------------------------------------------------------------


@pytest.mark.parametrize(
    "text", ["", "   ", "2", "2 cups", "1/2 tsp", "-", "...", "(optional)", "chopped"]
)
def test_a_line_it_cannot_read_is_a_result_not_an_error(text: str) -> None:
    line = read_line(text)
    assert isinstance(line, ReadLine)
    assert line.readable is False
    assert (line.amount, line.unit, line.counts, line.name) == (None, None, False, "")
    assert line.text == text


def test_a_very_long_line_is_unreadable() -> None:
    text = "2 onions " + "x" * MAX_LINE_CHARS
    assert read_line(text).readable is False
    assert read_line(text).text == text


# --- Properties ------------------------------------------------------------------------------

LINE_ALPHABET = st.sampled_from(list("0123456789 .,/-–()½¼¾⅓x×abcdgklmnopstuvwyz ▢•\t\n:;&'"))


@settings(max_examples=400, deadline=None)
@given(st.text())
def test_never_raises_on_any_text(text: str) -> None:
    line = read_line(text)
    assert line.text == text
    assert isinstance(line.readable, bool)


@settings(max_examples=400, deadline=None)
@given(st.text(alphabet=LINE_ALPHABET, max_size=80))
def test_never_raises_on_line_like_text(text: str) -> None:
    line = read_line(text)
    assert line.text == text
    if line.amount is not None:
        assert 0 < line.amount <= 1_000_000
    if not line.readable:
        assert line.amount is None
        assert not line.counts
    if line.counts:
        assert line.amount is not None
    if line.note is not None:
        assert len(line.note) <= 200


@settings(max_examples=300, deadline=None)
@given(
    st.lists(st.text(alphabet=LINE_ALPHABET), min_size=1, max_size=4),
    st.sampled_from(["", " ", "\n"]),
)
def test_the_words_are_kept_exactly(parts: list[str], joiner: str) -> None:
    given_text = joiner.join(parts)
    line = read_line("".join(given_text))  # a copy, so this compares text, not the same object
    assert line.text == given_text
    # And what it found comes from those words: nothing is made up.
    if line.readable:
        seen = set(working_text(given_text)) | set(" ,.")
        assert set(line.name) <= seen
        assert all(set(other) <= seen for other in line.other_names)
        assert set(line.name_as_written) <= seen


NUMBERS = st.one_of(
    st.integers(1, 999).map(str),
    st.sampled_from(["½", "¼", "¾", "⅓", "1½", "2 1/2", "1/2", "0.5", "1,5", "12.25"]),
)
SIDE_UNITS = st.sampled_from(["", "g", " g", "kg", " kg", "ml", " ml", "l", " l", " tsp", " cup"])
SEPARATORS = ["-", " - ", " to ", "\u2013", " or "]


def _base(number: str, unit: str) -> Decimal:
    """The size of a range side in g or ml (a cup is 250), for checking the answer."""
    amount = read_line(f"{number}{unit} x").amount
    assert amount is not None
    sizes = {"g": 1, "kg": 1000, "ml": 1, "l": 1000, "tsp": 5, "cup": 250, "": 1}
    return amount * sizes[unit.strip()]


@settings(max_examples=500, deadline=None)
@given(NUMBERS, SIDE_UNITS, NUMBERS, SIDE_UNITS, st.sampled_from(SEPARATORS))
def test_the_higher_side_of_a_range_wins_whatever_its_units(
    low: str, low_unit: str, high: str, high_unit: str, joiner: str
) -> None:
    line = read_line(f"{low}{low_unit}{joiner}{high}{high_unit} flour")
    assert line.text.endswith("flour")
    if line.amount is None:
        return
    assert line.amount > 0
    sides = []
    for number, unit in ((low, low_unit), (high, high_unit)):
        single = read_line(f"{number}{unit} flour")
        if single.amount is not None:
            sides.append((single.amount, single.unit))
    if not sides:
        return
    families = {"g": "w", "kg": "w", "ml": "v", "l": "v", "tsp": "v", "tbsp": "v", "cup": "v"}
    sizes = {"g": 1, "kg": 1000, "ml": 1, "l": 1000, "tsp": 5, "tbsp": 15, "cup": 250}
    if len(sides) == 2 and all(unit in sizes for _, unit in sides):
        if families[sides[0][1] or "g"] == families[sides[1][1] or "g"]:
            # Both sides have a unit of the same kind: the answer is the bigger side.
            bases = [amount * sizes[unit or "g"] for amount, unit in sides]
            answer = line.amount * sizes[line.unit or "g"]
            assert abs(answer - max(bases)) <= max(bases) / 500 + 1
    elif len(sides) == 2:
        assert line.amount >= min(amount for amount, _ in sides)


@settings(max_examples=300, deadline=None)
@given(
    st.integers(-(10**6), 10**6), st.sampled_from(["", "g", " ml", " tsp", " cup", " kg", " pinch"])
)
def test_the_amount_is_never_negative(number: int, unit: str) -> None:
    line = read_line(f"{number}{unit} flour")
    assert line.amount is None or line.amount > 0
    line = read_line(f"\u2212{abs(number)}{unit} flour")  # a minus sign
    assert line.amount is None or line.amount > 0


@settings(max_examples=500, deadline=None)
@given(st.text(max_size=300))
def test_the_amount_is_always_in_range_for_any_text(text: str) -> None:
    line = read_line(text)
    if line.amount is not None:
        assert 0 < line.amount <= 1_000_000
        assert line.readable


# --- 0.6 fixes, from the real lines in the 0.5 report -----------------------------------------


@pytest.mark.parametrize(
    ("text", "amount", "unit", "name"),
    [
        ("half a lemon", D("0.5"), None, "lemon"),
        ("Half an onion", D("0.5"), None, "onion"),
        ("half a cup milk", D("0.5"), "cup", "milk"),
        ("half cup rice", D("0.5"), "cup", "rice"),
        ("about half a cup rice", D("0.5"), "cup", "rice"),
        ("two onions", D(2), None, "onions"),
        ("Three cloves garlic", D(3), None, "garlic"),
        ("twelve eggs", D(12), None, "eggs"),
        ("two 400g tins tomatoes", D(800), "g", "tomatoes"),
        ("two to three green chillies", D(3), None, "green chillies"),
        ("two or three limes", D(3), None, "limes"),
    ],
)
def test_number_words_at_the_start(text: str, amount: Decimal, unit: str | None, name: str) -> None:
    line = read_line(text)
    assert (line.amount, line.unit, line.name) == (amount, unit, name)
    assert line.text == text


@pytest.mark.parametrize(
    "text",
    [
        "half and half",
        "half-and-half cream",
        "twofold sauce",
        "Threefold ale",
        "two",
        "five spice powder",
        "half fat crème fraîche",
        "Two thirds of a cup milk",
        "Ten Acre crisps",
    ],
)
def test_a_number_word_that_is_part_of_a_name_is_left_alone(text: str) -> None:
    line = read_line(text)
    assert line.amount is None
    assert line.name == text.strip()


def test_a_dozen_stays_a_size_word() -> None:
    line = read_line("a dozen eggs")
    assert (line.amount, line.size_word, line.name) == (D(1), "dozen", "eggs")


@pytest.mark.parametrize(
    ("text", "name", "note"),
    [
        ("1 inch ginger", "ginger", "1 inch"),
        ("4 cm ginger", "ginger", "4 cm"),
        ("⅓ inch ginger, grated", "ginger", "⅓ inch, grated"),
        ("½ inch piece ginger", "ginger", "½ inch"),
        ("1-inch piece fresh ginger", "ginger", "fresh, 1-inch"),
        ("2 cm piece turmeric", "turmeric", "2 cm"),
    ],
)
def test_a_length_stays_in_the_note_and_is_no_amount(text: str, name: str, note: str) -> None:
    line = read_line(text)
    assert (line.amount, line.unit, line.counts) == (None, None, False)
    assert line.size_word in (None, "piece")  # "piece" is kept as before, with no amount
    assert (line.name, line.note) == (name, note)


def test_a_size_word_before_a_name_held_in_a_bracket() -> None:
    line = read_line("3 large (ripe bananas, well mashed (about 1 1/2 cups))")
    assert (line.amount, line.unit, line.name, line.counts) == (D(3), None, "bananas", True)
    assert line.note is not None
    for kept in ("large", "ripe", "well mashed", "about 1 1/2 cups"):
        assert kept in line.note


def test_a_name_that_starts_with_a_number_word_keeps_it() -> None:
    # The amount after the name is read like one before it (0.7.0, F18).
    line = read_line("five spice powder, 1 tsp")
    assert (line.amount, line.unit, line.name) == (D(1), "tsp", "five spice powder")
    assert core_of("1 tsp five spice powder") == core_of("five spice powder, 1 tsp")


@pytest.mark.parametrize("text", ["3 medium (about 1 lb)", "1 small (about 2 cups)"])
def test_a_measure_in_a_bracket_is_never_the_name(text: str) -> None:
    line = read_line(text)
    assert (line.amount, line.name) == (read_line(text.split(" (")[0]).amount, "")


def test_a_number_word_before_a_length_makes_no_note_of_it() -> None:
    line = read_line("Twelve 1 cm cubes butter")
    assert (line.amount, line.note, line.name) == (None, None, "Twelve 1 cm cubes butter")


def test_a_bracket_after_a_name_is_still_a_note() -> None:
    line = read_line("2 large (ripe) avocados")
    assert (line.amount, line.name, line.note) == (D(2), "avocados", "large, ripe")


@pytest.mark.parametrize(
    ("text", "amount", "unit", "name", "note"),
    [
        ("optional: 50g pecans", D(50), "g", "pecans", "optional"),
        (
            "Optional: 1 handful of Jerusalem artichokes",
            D(1),
            None,
            "Jerusalem artichokes",
            "optional",
        ),
        ("To serve: limes", None, None, "limes", "to serve"),
        (
            "For serving: limes, unsweetened coconut yogurt",
            None,
            None,
            "limes",
            "for serving, unsweetened coconut yogurt",
        ),
        ("To garnish: 2 tbsp chopped coriander", D(2), "tbsp", "coriander", "to garnish, chopped"),
    ],
)
def test_a_label_at_the_start_is_read_past_and_kept_in_the_note(
    text: str, amount: Decimal | None, unit: str | None, name: str, note: str
) -> None:
    line = read_line(text)
    assert (line.amount, line.unit, line.name, line.note) == (amount, unit, name, note)
    assert line.readable
    assert line.text == text


def test_the_real_to_serve_line_is_read() -> None:
    line = read_line(
        "to serve: lots of pan-fried tofu cubes, toasted almonds, scallions,"
        " chive flowers (optional)"
    )
    assert line.readable
    assert line.name == "lots of pan-fried tofu cubes"
    assert line.note is not None and line.note.startswith("to serve")


def test_a_label_with_nothing_after_it_is_not_a_line() -> None:
    assert not read_line("optional:").readable
    assert not read_line("To serve: ").readable


# --- W2b (0.8): a number in brackets, and a doubled "((optional))" ---------------------------


@pytest.mark.parametrize(
    "text",
    [
        "1 teaspoon (4) garlic",
        "1 teaspoon garlic (4)",
        "1 tsp (4) garlic",
        "1 tsp garlic (4)",
        "1 tsp garlic, (4)",
    ],
)
def test_f139_a_number_in_brackets_stays_a_bracketed_note(text: str) -> None:
    """F139: "1 teaspoon (4) garlic" is 1 tsp garlic with "(4)" as the note, never "1 tsp 4"."""
    line = read_line(text)
    assert (line.amount, line.unit, line.name) == (D(1), "tsp", "garlic")
    assert line.note == "(4)"


@pytest.mark.parametrize("inside", ["4-5", "4.5", "½", "1/2"])
def test_f139_a_range_or_fraction_in_brackets_is_kept_in_its_brackets_too(inside: str) -> None:
    """Both ways of writing: before the name and after it give the same bracketed note."""
    for text in (f"1 tsp ({inside}) garlic", f"1 tsp garlic ({inside})"):
        line = read_line(text)
        assert (line.amount, line.unit, line.name) == (D(1), "tsp", "garlic"), text
        assert line.note == f"({inside})", text


@pytest.mark.parametrize(
    "text",
    [
        "2 tbsps raw papaya paste (optional)",
        "2 tbsps raw papaya paste ((optional))",
        "2 tbsps raw papaya paste ((optional)",
        "2 tbsps raw papaya paste [(optional)]",
        "2 tbsps raw papaya paste, optional",
    ],
)
def test_a_note_that_already_has_brackets_gets_no_more(text: str) -> None:
    """The importer's doubled "((optional))" reads exactly as "(optional)": one note, no other
    name, no extra brackets (the same thing written two ways gives the same result)."""
    line = read_line(text)
    assert (line.amount, line.unit, line.name) == (D(2), "tbsp", "raw papaya paste")
    assert line.note == "optional"
    assert line.other_names == ()


def test_deeply_nested_brackets_read_fast() -> None:
    """A line of hundreds of nested brackets (from an imported page) reads in one pass: only one
    extra pair is taken off, so the time doesn't grow with the square of the line's length."""
    import time

    depth = (MAX_LINE_CHARS - 10) // 2
    text = "1 tsp x " + "(" * depth + "y" + ")" * depth
    started = time.perf_counter()
    for _ in range(20):
        read_line(text)
    assert time.perf_counter() - started < 0.5


# --- Hostile lines read in linear time (security pass L2, L3; 7 Nov) ------------------------------

HOSTILE_LINES = [
    ",".join(["a"] * 500),  # a separator at every second character (L2)
    "1 big," + ",".join(["big"] * 190),  # a prep word at every comma (L3)
    "1 big," + "big," * 240,
]


def test_two_hundred_hostile_lines_are_read_well_under_half_a_second() -> None:
    import time

    lines = [HOSTILE_LINES[n % len(HOSTILE_LINES)][:MAX_LINE_CHARS] for n in range(200)]
    started = time.perf_counter()
    for text in lines:
        read_line(text)
    spent = time.perf_counter() - started
    assert spent < 0.5, f"{spent:.2f} s for 200 hostile lines"


def test_a_line_of_commas_and_prep_words_reads_as_it_did() -> None:
    """The same answers as before the speed-up, for the shapes it touches."""
    chicken = read_line("4 skinless, boneless chicken breast halves")
    assert (chicken.amount, chicken.name) == (Decimal(4), "chicken breast halves")
    garlic = read_line("garlic, 2 cloves, minced")
    assert (garlic.amount, garlic.size_word, garlic.name) == (Decimal(2), "cloves", "garlic")
