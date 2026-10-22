# ruff: noqa: RUF001  (these tests use look-alike dashes, signs and spaces on purpose)
"""Reading one ingredient line (docs/dev/ingredient-reader.md)."""

from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from mealwright.ingredient_reader import MAX_LINE_CHARS, ReadLine, read_line

D = Decimal


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
    line = read_line("2 garlic cloves")
    assert (line.amount, line.unit, line.name) == (D(2), None, "garlic cloves")
    line = read_line("1 gram-flour mix")
    assert line.unit is None
    assert line.name == "gram-flour mix"
    assert read_line("3 T-bone steaks").unit is None


def test_a_plain_count_has_no_unit() -> None:
    line = read_line("3 eggs")
    assert (line.amount, line.unit, line.size_word, line.counts) == (D(3), None, None, True)


def test_other_systems_units_are_no_amount() -> None:
    for text in ("8 oz spinach", "1 lb potatoes", "2 pints milk", "1 fl oz brandy"):
        line = read_line(text)
        assert line.amount is None
        assert not line.counts
        assert line.note is not None
        assert line.readable
    assert read_line("8 oz spinach").name == "spinach"
    assert read_line("8 oz spinach").note == "8 oz"
    assert read_line("1 fl oz brandy").name == "brandy"


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


def test_a_count_with_its_weight_in_brackets() -> None:
    line = read_line("1 (400 g) can chickpeas, drained")
    assert (line.amount, line.unit, line.size_word) == (D(400), "g", "can")
    assert line.name == "chickpeas"
    assert line.note == "drained"
    line = read_line("1 (14 oz) can chickpeas")
    assert (line.amount, line.unit, line.size_word) == (D(1), None, "can")
    assert not line.counts


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
    text = joiner.join(parts)
    assert read_line(text).text == text


@settings(max_examples=300, deadline=None)
@given(st.integers(0, 999), st.integers(0, 999), st.sampled_from(["-", " - ", " to ", "–", " or "]))
def test_the_higher_number_of_a_range_is_never_the_lower(low: int, high: int, joiner: str) -> None:
    line = read_line(f"{low}{joiner}{high} green chillies")
    if max(low, high) == 0:
        assert line.amount is None
    else:
        assert line.amount == D(max(low, high))
    if line.amount is not None:
        assert line.amount >= D(min(low, high))
        assert line.amount >= D(low)
        assert line.amount >= D(high)


@settings(max_examples=300, deadline=None)
@given(
    st.integers(-(10**6), 10**6), st.sampled_from(["", "g", " ml", " tsp", " cup", " kg", " pinch"])
)
def test_the_amount_is_never_negative(number: int, unit: str) -> None:
    line = read_line(f"{number}{unit} flour")
    assert line.amount is None or line.amount > 0
