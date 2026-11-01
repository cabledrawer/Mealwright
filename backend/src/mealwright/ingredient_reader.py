"""Reading one ingredient line: "2 onions, finely chopped" → an amount, a unit, a name and a
note (spec section 6, "Recipe import, decided for 0.5"; docs/dev/ingredient-reader.md).

Pure text in, plain values out: no database, no network. A line it can't read is a result
(`readable=False`), never an error, and `read_line` never raises. The words are always kept
exactly as given in `ReadLine.text`.

What it reads without asking:

- Numbers: ½, 1½, 1 1/2, 1/2, 0.5, 1,5 (and ¼ ¾ ⅓ ⅔ ⅛ and the other fraction signs), and
  1,500 as one thousand five hundred. Several forms of the same number are read by the
  recipe editor's own reader (`recipe_schemas.fraction_of`), so the two always agree.
- Ranges (2-3, 2 to 3, 2 or 3): the higher number is the amount.
- Two units (1 cup (240 ml) rice, 200 g / 7 oz spinach): the metric one is the amount. A cup
  on its own stays a cup; the household's own cup turns it into ml when the line is
  matched (`ingredient_match`).
- Pack multiples: 2 x 400g tins is 800 g.
- No real amount ("to taste", "as needed", "for garnish"): the phrase goes into the note.
  A number the line does have is still its amount.
- Number words at the start ("half a lemon", "two onions", up to twelve) are read as numbers.
  "a dozen" is not: it stays a size word.
- A length ("1 inch ginger", "4 cm ginger") stays in the note with no amount: it can't be
  compared with stock. `LENGTH_UNITS` is the one place to change that.
- A size word before the name ("3 large (ripe bananas, ...)") is a descriptor and goes to the
  note; a name held only in a bracket is taken out of it.
- A label at the start of a line ("optional: 50g pecans", "to serve: limes") is read past; the
  words go first in the note.
"""

import re
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from fractions import Fraction

from mealwright.amounts import DEFAULT_CUP_ML, MAX_AMOUNT, CountedAs, unit_family, unit_size
from mealwright.api.v1.recipe_schemas import GLYPHS, UNIT_ALIASES, fraction_of
from mealwright.line_prep import kitchen_round, strip_footnotes
from mealwright.names import singular, without_hidden
from mealwright.pints import UNIT_ML, kind_of

# The longest line read. Anything longer isn't an ingredient line.
MAX_LINE_CHARS = 1000
MAX_NOTE_CHARS = 200  # the recipe editor's limit for a line's note

# --- The word lists ---------------------------------------------------------------------------

# Prep words (and a few plain descriptors) that are taken out of a name and kept in the
# note. A short, closed list: a word is here only if taking it out never turns one
# ingredient into another. Left out on purpose: dried, ground, powder, frozen, cooked,
# roasted, smoked, red, green, baby, extra... (they are part of what the ingredient is).
PREP_WORDS = frozenset(
    {
        # how it is cut or treated
        "chopped", "diced", "sliced", "minced", "grated", "shredded", "crushed", "peeled",
        "deseeded", "seeded", "pitted", "cubed", "halved", "quartered", "trimmed", "washed",
        "rinsed", "drained", "melted", "softened", "beaten", "sifted", "torn", "crumbled",
        "mashed", "julienned", "cored", "deveined", "shelled", "soaked", "thawed",
        "defrosted", "cooled", "warmed", "unpeeled", "pounded", "squeezed", "zested",
        # how
        "finely", "roughly", "coarsely", "thinly", "thickly", "freshly", "lightly", "well",
        "neatly",
        # plain descriptors
        "fresh", "large", "medium", "small", "big", "ripe", "firm", "organic", "optional",
        "heaped", "heaping", "level", "packed", "divided", "skinless", "boneless",
    }
)  # fmt: skip
# The descriptors among them: the only ones taken out of a packaged product's name
# ("1 x 400g tin chopped tomatoes" keeps "chopped").
DESCRIPTOR_WORDS = frozenset(
    {"fresh", "large", "medium", "small", "big", "ripe", "firm", "organic", "optional"}
)

# Taken out of a name, and kept in the note, wherever it stands (F103).
WHOLE = "whole"

# Words that name a size an ingredient may be bought or measured in. A line with one
# ("1 bunch coriander") counts only if the matched ingredient has a size of that name.
SIZE_WORDS = frozenset(
    {
        "bunch", "sprig", "handful", "clove", "tin", "can", "jar", "packet", "pack", "bag",
        "box", "head", "stick", "slice", "piece", "knob", "stalk", "stem", "bulb", "sachet",
        "carton", "bottle", "tub", "tube", "loaf", "dash", "splash", "drizzle", "glug",
        "dollop", "sheet", "rasher", "fillet", "rib", "pot", "block", "dozen", "tray", "drop",
        "glass", "sprinkle", "swish", "squeeze", "slug",
    }
)  # fmt: skip
# Sizes that are a container: a product's name inside one keeps its prep word.
CONTAINER_WORDS = frozenset(
    {"tin", "can", "jar", "packet", "pack", "bag", "box", "carton", "bottle", "tub", "tube",
     "sachet", "pot", "block"}
)  # fmt: skip
# Size words that mean a fixed number of the thing itself, so an ingredient with no size of that
# name still gets an amount: "a dozen eggs" is 12 eggs. Not "clove": one clove is not one garlic,
# so "2 cloves garlic" stays "2 cloves" like "1 bunch coriander" (F89, cabledrawer 31 Oct).
FIXED_COUNTS = {"dozen": 12}
# A size word that can stand after the name: "2 garlic cloves" is "2 cloves garlic".
TRAILING_SIZE_WORDS = frozenset({"clove", "sprig"})
# Words that say "some", with no number. Kept like a size word; they never count.
QUANTITY_WORDS = frozenset(
    {
        "few",
        "some",
        "little",
        "bit",
        "couple",
        "several",
        "lil",
        "touch",
        "smidge",
        "smidgen",
        "tad",
    }
)
# Size words that say "some" on their own, with no number or "a" before them: "Handful dried
# banana chips", "drop vanilla extract". Closed on purpose: "bunch" or "stick" could start a name.
LOOSE_SIZE_WORDS = frozenset(
    {"handful", "drop", "dash", "splash", "glug", "knob", "sprig", "glass", "sprinkle", "swish",
     "squeeze", "drizzle", "dollop", "slug"}
)  # fmt: skip
# Without "a" in front, only these say "some" ("little gem lettuce" is a name).
BARE_QUANTITY_WORDS = frozenset({"few", "some", "several"})
# A word in a bracket that makes it a note, not another name for the ingredient.
NOTE_HINTS = frozenset(
    {"see", "note", "notes", "substitute", "for", "to", "about", "approx", "plus", "preferably",
     "if", "such", "as", "like", "available", "use", "can", "per", "more", "extra", "or", "and",
     "whole", "total", "each", "only", "the", "a", "an", "of", "in", "with", "from", "your",
     "any", "this", "that", "kind", "type", "sort", "brand", "at", "on", "it", "them", "is"}
)  # fmt: skip

# Colour and size words say little about which ingredient it is: "(green)" after cardamom pods
# is a note, never another name for it, and "green" alone never makes a match (F35).
WEAK_WORDS = frozenset(
    {"green", "red", "white", "black", "yellow", "brown", "orange", "purple", "pink", "golden",
     "dark", "light", "large", "small", "medium", "big", "little", "baby", "fresh", "whole",
     "dried", "ground", "raw", "sweet", "hot", "mild", "plain", "extra", "new", "old", "young"}
)  # fmt: skip
# One word that describes the noun it shares with the other side: "black or white pepper",
# "heavy / thickened cream". The first side takes the other side's last words.
MODIFIER_WORDS = WEAK_WORDS | frozenset(
    {"salted", "unsalted", "heavy", "double", "single", "thickened", "whipping", "thick",
     "thin", "dry", "smoked", "unsmoked", "strong", "frozen", "skimmed", "semi-skimmed", "low-fat",
     "full-fat", "self-raising", "wholemeal", "unsweetened", "sweetened"}
)  # fmt: skip
_VARIETY = re.compile(r"\b(?:variety|varieties|type|kind)\b", re.IGNORECASE)
_VARIETY_WORD = re.compile(r"\b(?:varieties|variety)\b", re.IGNORECASE)

# Pints, read only when the caller says how big a pint is (`read_line(pint_ml=...)`; see pints.py).
PINTS = frozenset({"pint", "pints", "pt"})
# Pints, quarts, gallons and fluid ounces are all read with the household's pint (UK or US):
# the word → which measure it is (`pints.UNIT_ML` has the sizes).
PINT_FAMILY = {
    "pint": "pint", "pints": "pint", "pt": "pint", "quart": "quart", "quarts": "quart",
    "qt": "quart", "gallon": "gallon", "gallons": "gallon", "gal": "gallon", "fl oz": "fl oz",
}  # fmt: skip

# Ounces and pounds on their own convert exactly (cabledrawer 23 Oct, question 18): 1 oz is
# 28.35 g and 1 lb is 453.6 g. Pints, fluid ounces and the rest stay in the note (UK and US
# pints differ).
OUNCES = frozenset({"oz", "ounce", "ounces"})
POUNDS = frozenset({"lb", "lbs", "pound", "pounds"})
GRAMS_PER_OUNCE = Fraction(2835, 100)
GRAMS_PER_POUND = Fraction(4536, 10)

# Units from other systems. They are not the recipe editor's units, so a line that has only
# one of these gets no amount (the measure goes in the note).
OTHER_UNITS = frozenset(
    {"oz", "ounce", "ounces", "lb", "lbs", "pound", "pounds", "pint", "pints", "pt", "quart",
     "quarts", "qt", "gallon", "gallons", "gal", "inch", "inches", "cm", "mm", "fl"}
)  # fmt: skip

# Of those, the lengths: kept in the note with no amount, never counted ("1 inch ginger").
LENGTH_UNITS = frozenset({"inch", "inches", "cm", "mm"})

# Number words at the start of a line. "one" is left to the article rule ("one 14 oz can").
NUMBER_WORDS = {
    "half": "1/2", "two": "2", "three": "3", "four": "4", "five": "5", "six": "6",
    "seven": "7", "eight": "8", "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
}  # fmt: skip
# Words after a number word that make it part of a name or a fraction, not a count: "five spice
# powder", "half fat crème fraîche", "two thirds of a cup", "Ten Acre crisps" (cabledrawer 27
# Oct). The one place to add more.
NOT_A_COUNT = frozenset(
    {"spice", "fat", "acre", "bean", "grain", "seed", "thirds", "third", "quarters", "quarter",
     "fifths", "eighths", "halves"}
)  # fmt: skip
_NUMBER_WORD = re.compile(
    r"(?P<word>" + "|".join(NUMBER_WORDS) + r")(?P<article>\s+(?:a|an))?"
    r"(?=\s+(?!(?:and|" + "|".join(NOT_A_COUNT) + r")\b)\S)",
    re.IGNORECASE,
)
# A length straight after a number word ("Twelve 1 cm cubes"): not a pack multiple.
_LENGTH_AFTER = re.compile(
    r"[\d./ ]+\s*(?:" + "|".join(sorted(LENGTH_UNITS)) + r")\b", re.IGNORECASE
)
# A label that starts a line and says what the rest is for: "optional: 50g pecans".
_LABEL = re.compile(
    r"(?P<label>optional|to\s+serve|for\s+serving|to\s+garnish|for\s+garnish(?:ing)?|garnish"
    r"|for\s+the\s+(?:garnish|topping))\s*:\s*",
    re.IGNORECASE,
)

_UNITS: dict[str, str] = {
    **UNIT_ALIASES,
    "mls": "ml",
    "kgs": "kg",
    "gms": "g",
    "ltr": "l",
    "ltrs": "l",
    "lt": "l",
    "tbs": "tbsp",
    "tbsps": "tbsp",
    "tbl": "tbsp",
    "tbls": "tbsp",
    "tsps": "tsp",
    "c": "cup",
    "dessertspoon": "tbsp",  # not exact (10 ml), so it is left out below
}
del _UNITS["dessertspoon"]
METRIC = ("g", "kg", "ml", "l")

COUNTED_AS: dict[str, CountedAs] = {
    "g": "weight",
    "kg": "weight",
    "ml": "volume",
    "l": "volume",
    "tsp": "volume",
    "tbsp": "volume",
    "cup": "volume",
}

# --- Patterns ---------------------------------------------------------------------------------

_G = "".join(GLYPHS)
_NUMBER = re.compile(
    rf"(?:\d{{1,12}}\s*[{_G}]"  # 1½ and 1 ½
    rf"|\d{{1,12}}(?:\s+|-)\d{{1,12}}\s*/\s*\d{{1,12}}"  # 1 1/2 and 1-1/2
    rf"|\d{{1,12}}\s*/\s*\d{{1,12}}"  # 1/2
    rf"|[{_G}]"  # ½
    rf"|\d{{1,3}}(?:,\d{{3}})+(?:\.\d{{1,12}})?"  # 1,500
    rf"|\d{{1,12}}(?:[.,]\d{{1,12}})?"  # 12, 0.5, 1,5
    rf"|\.\d{{1,12}})(?![\d{_G}])"
)
_QUALIFIER = re.compile(
    r"\s+(heaped|heaping|level|scant|generous|rounded|packed|full)\b", re.IGNORECASE
)
_RANGE = re.compile(r"\s*-\s*|\s+to\s+|\s+or\s+", re.IGNORECASE)
_TIMES = re.compile(rf"\s*[x\u00d7]\s*(?=[\d.{_G}])", re.IGNORECASE)
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
_ARTICLE = re.compile(r"(?:a|an|one)\s+", re.IGNORECASE)
_LEAD = re.compile(
    r"(?:(?:about|approx\.?|approximately|around|roughly|nearly|almost|scant|heaped|heaping|"
    r"level|generous|circa|up\s+to|~)\s*)+",
    re.IGNORECASE,
)
BULLETS = "•*-▢☐□◦▪·✓✔○●■►▪ \t"
_NO_AMOUNT = re.compile(
    r"\b(?:(?:or|and|adjust)\s+)?(?:to\s+taste|as\s+(?:needed|required|desired|per\s+taste)"
    r"|if\s+(?:needed|desired|you\s+like)"
    r"|for\s+(?:the\s+)?(?:garnish|garnishing|serving|frying|deep\s+frying|dusting|decorating"
    r"|decoration|greasing|brushing|topping|drizzling|sprinkling|tempering|pan|tadka)"
    r"|to\s+(?:garnish|serve|season|decorate)|optional"
    r"|made\s+(?:with|from|using)"  # "Beef stock made with 1 stock shot or cube"
    r"|and\s+(?:cut|chop(?:ped)?|slice[ds]?|dice[ds]?|cube[ds]?)\s+(?:into|up|in))\b",
    re.IGNORECASE,
)
_DASHES = str.maketrans(dict.fromkeys("\u2010\u2011\u2012\u2013\u2014\u2015\u2212", "-"))
_SLASHES = str.maketrans({"\u2044": "/", "\u2215": "/"})
_EDGE_PUNCT = " \t.,;:!?*\u2022\"'\u201c\u201d\u2018\u2019-"
_TOP = Decimal("0.001")


# --- The result -------------------------------------------------------------------------------


@dataclass(frozen=True)
class ReadLine:
    """What one ingredient line says.

    - `text`: the line exactly as given, always.
    - `amount`: a number above 0 and at most 1,000,000, or None (no real amount, or one
      from another system such as oz). A range gives its higher number; two units give the
      metric one; "2 x 400g" gives 800.
    - `unit`: g, kg, ml, l, tsp, tbsp, cup or pinch; None for a plain count or a size word.
    - `size_word`: the size word the line uses, lower case, as written ("sprig", "cloves",
      "tin", "few"). Whether it counts is decided by matching.
    - `name`: the ingredient, without amount, unit, size word, brackets, note or prep words.
    - `name_as_written`: the same but with the prep words left in ("chopped tomatoes").
    - `other_names`: names given beside it, from a bracket or a slash ("toor dal" in
      "thuvaram paruppu (toor dal)"; "asafoetida" in "hing / asafoetida").
    - `note`: prep words and anything after a comma or in brackets ("finely chopped"), at
      most 200 characters.
    - `counts`: whether the line counts towards stock by itself: a real amount in a real
      unit, or a plain count. A pinch, a size word, a few and "to taste" never do (a size
      word can count once matching finds the ingredient has that size).
    - `readable`: False for a line with no name left, or over 1,000 characters.
    - `chosen`: the amount was picked from several numbers or units ("2-3", "1 cup (240 ml)",
      "2 x 400g", "8 oz"), so the line is kept as written too.
    """

    text: str
    amount: Decimal | None
    unit: str | None
    size_word: str | None
    name: str
    name_as_written: str
    other_names: tuple[str, ...]
    note: str | None
    counts: bool
    readable: bool
    # The amount or unit was picked from several numbers or units in the text (a range, two
    # units, a pack multiple, ounces or pounds turned into grams): the saved line keeps the
    # text as written beside it.
    chosen: bool = False
    # How many pints the line says, when its amount was worked out from them (the amount is
    # then in ml, for the pint size the caller gave). None for every other line.
    pints: Fraction | None = None
    # Which measure those are: "pint", "quart", "gallon" or "fl oz" (None when `pints` is None).
    pint_unit: str | None = None


def _unreadable(text: str) -> ReadLine:
    return ReadLine(text, None, None, None, "", "", (), None, False, False)


# --- Numbers and units ------------------------------------------------------------------------


def _decimal(value: Fraction) -> Decimal:
    """An exact fraction as a decimal to the thousandth (⅓ is 0.333), the way amounts are
    stored."""
    exact = Decimal(value.numerator) / Decimal(value.denominator)
    rounded = exact.quantize(_TOP, rounding=ROUND_HALF_UP)
    return rounded.quantize(Decimal(1)) if rounded == rounded.to_integral() else rounded.normalize()


def _number(text: str, start: int) -> tuple[Fraction, int] | None:
    found = _NUMBER.match(text, start)
    if found is None:
        return None
    raw = found.group()
    if re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", raw):
        raw = raw.replace(",", "")
    elif "," in raw:
        raw = raw.replace(",", ".")
    if re.fullmatch(r"\d+-\d+\s*/\s*\d+", raw):
        raw = raw.replace("-", " ")
    if raw.startswith("."):
        raw = "0" + raw
    try:
        return fraction_of(raw), found.end()
    except ValueError:
        return None


def _unit(text: str, start: int) -> tuple[str | None, str | None, int]:
    """A unit word at `start`, after any spaces and a hyphen: (the editor's unit or None,
    an other-system unit's word or None, where it ends). Nothing found: (None, None, start)."""
    at = start
    while at < len(text) and text[at] == " ":
        at += 1
    if text[at : at + 1] == "-" and text[at + 1 : at + 2].isalpha():  # 1-inch
        at += 1
    found = _WORD.match(text, at)
    if found is None:
        return None, None, start
    word = found.group()
    end = found.end()
    if text[end : end + 1] == ".":
        end += 1
    after = text[end : end + 2]
    if after[:1].isalnum() or (after[:1] == "-" and after[1:2].isalpha()) or after[:1] == "_":
        return None, None, start
    if word == "T":
        return "tbsp", None, end
    if word == "t":
        return "tsp", None, end
    lower = word.lower()
    if lower == "fl":  # "fl oz"
        inner = _WORD.match(text, end + 1) if text[end : end + 1] == " " else None
        if inner is not None and inner.group().lower() == "oz":
            return None, "fl oz", inner.end()
    if lower in _UNITS:
        return _UNITS[lower], None, end
    if lower in OTHER_UNITS:
        return None, lower, end
    return None, None, start


@dataclass(frozen=True)
class _Measure:
    value: Fraction
    unit: str | None
    other: str | None  # a unit from another system (oz…)
    start: int
    end: int
    chosen: bool = False  # picked from several numbers or units (a range, a pack multiple)
    qualifier: str = ""  # "heaped" in "1 heaped tsp": kept in the note

    @property
    def metric(self) -> bool:
        return self.unit in METRIC


def _base_size(value: Fraction, unit: str | None) -> tuple[str, Fraction] | None:
    """A measure in g or ml, with which of the two it is, for comparing two sides of a
    range. None when it can't be compared (no unit, a pinch, another system's unit). A cup
    counts as the default cup: only the order of the two sides matters here."""
    if unit is None or unit == "pinch":
        return None
    family = unit_family(unit)
    if family is None:
        return None
    return family, value * Fraction(unit_size(unit, DEFAULT_CUP_ML))


MAX_FACTORS = 3  # "2 x 2 x 400g": at most this many numbers multiplied together


def _multiple(text: str, value: Fraction, at: int) -> _Measure | None:
    """A pack multiple after a plain number: "2 x 400g" (800 g), "2 x 2 x 400g" (1,600 g).
    At most `MAX_FACTORS` numbers are multiplied, in a loop, so "1x1x1x..." can't make the
    reader call itself deeper and deeper. None unless the numbers end in a unit ("2 x 3
    onions" is not a pack multiple)."""
    product = value
    for _ in range(MAX_FACTORS - 1):
        times = _TIMES.match(text, at)
        if times is None:
            return None
        inner = _measure(text, times.end(), allow_multiple=False)
        if inner is not None and (inner.unit or inner.other):
            return _Measure(product * inner.value, inner.unit, inner.other, 0, inner.end, True)
        plain = _number(text, times.end())
        if plain is None:
            return None
        product *= plain[0]
        at = plain[1]
    return None


_PACK_START = re.compile(r"\s+(?:(?:a|an)\s+)?(\(\s*)?", re.IGNORECASE)


def _packs(text: str, value: Fraction, at: int) -> _Measure | None:
    """A count straight before a measured container: "1 14-ounce can" is "1 x 14 oz can", "2
    400g tins" is 800 g. Only when a container word (can, tin, jar…) follows the measure."""
    space = _PACK_START.match(text, at)
    if space is None:
        return None
    inner = _measure(text, space.end(), allow_multiple=False)
    if inner is None or not (inner.unit or inner.other) or inner.value == 0:
        return None
    end = inner.end
    if space.group(1):  # "1 (14 ounce) can": the bracket closes before the container word
        close = re.compile(r"\s*\)").match(text, end)
        if close is None:
            return None
        end = close.end()
    word, _after, _passed = _take_size(text, end, frozenset())
    if word is None or not (word in CONTAINER_WORDS or singular(word) in CONTAINER_WORDS):
        return None
    return _Measure(value * inner.value, inner.unit, inner.other, 0, end, True)


def _measure(text: str, start: int, allow_multiple: bool = True) -> _Measure | None:
    """A number with its unit, a range, or a pack multiple, at `start`."""
    first = _number(text, start)
    if first is None:
        return None
    value, at = first
    unit, other, end = _unit(text, at)
    qualifier = ""
    if unit is None and other is None:  # "1 heaped tsp", "1 level tbsp"
        said = _QUALIFIER.match(text, at)
        if said is not None:
            unit, other, end2 = _unit(text, said.end())
            if unit or other:
                qualifier, end = said.group(1).lower(), end2
    if allow_multiple and unit is None and other is None:
        packs = _packs(text, value, at)
        if packs is not None:  # 1 14-ounce can
            return _Measure(packs.value, packs.unit, packs.other, start, packs.end, True)
        multiple = _multiple(text, value, at)
        if multiple is not None:  # 2 x 400g
            return _Measure(
                multiple.value, multiple.unit, multiple.other, start, multiple.end, True
            )
    separator = _RANGE.match(text, end)
    if separator is not None:  # 2-3, 2 to 3, 200g-300g, 200g-1kg
        second = _number(text, separator.end())
        if second is not None:
            top, after = second
            unit2, other2, end2 = _unit(text, after)
            if unit2 or other2:
                if unit is None and other is None:
                    # "3-2 tbsp": only the second side has the unit; the higher number wins.
                    return _Measure(max(value, top), unit2, other2, start, end2, True)
                # Two different units: the bigger side wins, with its own unit.
                low, high = _base_size(value, unit), _base_size(top, unit2)
                if low is not None and high is not None and low[0] == high[0]:
                    if low[1] > high[1]:
                        return _Measure(value, unit, other, start, end2, True)
                    return _Measure(top, unit2, other2, start, end2, True)
                return _Measure(top, unit2, other2, start, end2, True)  # can't compare: second
            return _Measure(max(value, top), unit, other, start, after, True)
    return _Measure(value, unit, other, start, end, qualifier=qualifier)


_SECOND = re.compile(r"\s*\(\s*(?:(?:about|approx\.?|approximately|~)\s*)?")


def _second_measure(text: str, start: int) -> _Measure | None:
    """A second measure straight after the first: (240 ml), (about 7 oz) or / 7 oz."""
    bracket = _SECOND.match(text, start)
    if bracket is not None:
        inner = _measure(text, bracket.end())
        if inner is not None and (inner.unit or inner.other):
            close = re.compile(r"\s*\)").match(text, inner.end)
            if close is not None:
                return _Measure(inner.value, inner.unit, inner.other, start, close.end(), True)
        return None
    slash = re.compile(r"\s*/\s*").match(text, start)
    if slash is not None:
        inner = _measure(text, slash.end())
        if inner is not None and (inner.unit or inner.other):
            return _Measure(inner.value, inner.unit, inner.other, start, inner.end, True)
    return None


_ABOUT = re.compile(r"(?:about|approx\.?|approximately|~)\s*", re.IGNORECASE)


def _bracket_metric(inside: str) -> _Measure | None:
    """The bracket's text if it is nothing but a metric measure ("125g", "about 200 g")."""
    at = _ABOUT.match(inside)
    found = _measure(inside, at.end() if at else 0)
    if found is not None and found.metric and not inside[found.end :].strip():
        return found
    return None


# --- The text around the amount ---------------------------------------------------------------


_CONTROLS = {code: " " for code in (*range(0x20), *range(0x7F, 0xA0))}
_NOT_TEXT = ("Co", "Cn", "Cs")  # private use, unassigned, surrogates


def working_text(text: str) -> str:
    """The text with control characters made into spaces (so "a\x1fb" stays two words) and
    private-use, unassigned and surrogate characters dropped, then hidden characters taken out
    (`names.without_hidden`), dashes and fraction slashes made plain, and the spaces tidied."""
    text = text.translate(_CONTROLS)
    if not text.isascii():
        text = "".join(c for c in text if c.isascii() or unicodedata.category(c) not in _NOT_TEXT)
    plain = strip_footnotes(without_hidden(text.translate(_DASHES).translate(_SLASHES)))
    return " ".join(plain.split()).lstrip(BULLETS)


def _with_digits(work: str) -> str:
    """A number word at the start ("half a lemon", "two onions", "two to three cloves") as
    digits. "half a" loses its article. A number straight after ("two 400g tins") is a pack
    multiple. Anything else is returned as it was."""
    lead = _LEAD.match(work)
    at = lead.end() if lead else 0
    found = _NUMBER_WORD.match(work, at)
    if found is None:
        return work
    digits = NUMBER_WORDS[found.group("word").lower()]
    tail = work[found.end() :].lstrip()
    # "two to three onions", "two or three": the second side too.
    other = re.compile(r"(?P<sep>to|or|-)\s*(?P<word>[a-z]+)(?=\s)", re.IGNORECASE).match(tail)
    if other is not None and other.group("word").lower() in NUMBER_WORDS:
        digits += f" {other.group('sep')} {NUMBER_WORDS[other.group('word').lower()]}"
        tail = tail[other.end() :].lstrip()
    if tail[:1].isdigit() and _LENGTH_AFTER.match(tail):
        return work  # "Twelve 1 cm cubes butter": left as it was
    joiner = " x " if tail[:1].isdigit() else " "
    return f"{work[:at]}{digits}{joiner}{tail}"


_AND_A_PART = re.compile(
    r"(?P<n>one|a|an|" + "|".join(NUMBER_WORDS) + r")\s+and\s+(?:a|an|one)\s+"
    r"(?P<part>half|quarter)\b(?=\s+\S)",
    re.IGNORECASE,
)
_OR_SO = re.compile(r"(?<=\d)\s*-?\s*or[- ]so\b", re.IGNORECASE)
_FILLER = re.compile(r"(?:just|only)\s+(?=\S)", re.IGNORECASE)
_ARTICLE_AFTER = re.compile(r"\s*,\s*((?:a|an|one)\s+[^\W\d_]+)\s*(?=,|$)", re.IGNORECASE)
_AFTER_NAME = re.compile(r"\s*(?:,|:|\s[-\u2013]\s|\s)\s*")


def _amount_after_name(work: str, extra: frozenset[str]) -> str:
    """An amount written after the name moves to the front: "garlic, 2 cloves, minced" is
    "2 cloves garlic, minced"; "olive oil - 2 tbsp" is "2 tbsp olive oil". Only a number with a
    unit or a size word counts, and with a bare space only at the very end ("flour 500g"). A line
    that already starts with an amount is left alone."""
    lead = _LEAD.match(work)
    start = lead.end() if lead else 0
    if _measure(work, start) is not None or _ARTICLE.match(work, start):
        return work
    spoken = _ARTICLE_AFTER.search(work)
    if spoken is not None:  # "golden raisins, a handful"
        word = spoken.group(1).split()[-1].lower()
        name = work[: spoken.start()]
        if (
            (_is_size(word, extra) or word in QUANTITY_WORDS)
            and any(c.isalpha() for c in name)
            and not any(c.isdigit() for c in name)
        ):
            return f"{spoken.group(1)} {name}{work[spoken.end() :]}"
    for found in _AFTER_NAME.finditer(work, 1):
        name = work[: found.start()]
        if not any(c.isalpha() for c in name) or any(c.isdigit() for c in name):
            continue
        measure = _measure(work, found.end())
        if measure is None:
            continue
        end = measure.end
        if not (measure.unit or measure.other):
            word, after, _passed = _take_size(work, end, extra)
            if word is None:
                continue
            end = after
        tail = work[end:].strip()
        bare = found.group().strip() == ""
        if bare and tail:
            continue
        if tail and tail[0] not in ",;(":
            continue
        said = work[found.end() : end].strip()
        return f"{said} {name}{', ' + tail.lstrip(',; ') if tail.lstrip(',; ') else ''}"
    return work


def _spoken(work: str) -> str:
    """ "one and a half cups" → "1 1/2 cups"; "half a dozen" is left to the number-word rule."""
    lead = _LEAD.match(work)
    at = lead.end() if lead else 0
    found = _AND_A_PART.match(work, at)
    if found is None:
        return work
    word = found.group("n").lower()
    whole = NUMBER_WORDS.get(word, "1")
    part = "1/2" if found.group("part").lower() == "half" else "1/4"
    return f"{work[:at]}{whole} {part}{work[found.end() :]}"


def _names_something(bracket: str) -> bool:
    """Whether a bracket's first part can be a name: "ripe bananas, well mashed" can; a measure
    such as "about 1 lb" or "about 2 cups" can't (no digit, and no note word first)."""
    first = re.split(r"[,(]", bracket, maxsplit=1)[0].split()
    return (
        bool(first)
        and not any(c.isdigit() for c in " ".join(first))
        and (_clean_token(first[0]) not in NOTE_HINTS)
    )


def _clean_token(token: str) -> str:
    return token.strip(_EDGE_PUNCT).lower()


def _brackets(text: str) -> tuple[str, list[str]]:
    """The text without its (brackets) and [brackets], and what was inside each."""
    kept: list[str] = []
    inside: list[str] = []
    depth = 0
    current: list[str] = []
    for char in text:
        if char in "([":
            if depth == 0:
                current = []
            else:
                current.append(char)
            depth += 1
        elif char in ")]" and depth:
            depth -= 1
            if depth == 0:
                inside.append("".join(current).strip())
                kept.append(" ")
            else:
                current.append(char)
        elif depth:
            current.append(char)
        else:
            kept.append(char)
    if depth:  # never closed: the rest is a note
        inside.append("".join(current).strip())
    return "".join(kept), [part for part in inside if part]


def _is_prep(word: str, strip: frozenset[str]) -> bool:
    return _clean_token(word) in strip


def _strip_prep(tokens: list[str], strip: frozenset[str]) -> tuple[list[str], list[str]]:
    """The tokens without prep words (and the "and" between them), and the words taken out."""
    prep = [_is_prep(token, strip) for token in tokens]
    kept: list[str] = []
    removed: list[str] = []
    for index, token in enumerate(tokens):
        if prep[index]:
            removed.append(token.strip(_EDGE_PUNCT))
            continue
        if _clean_token(token) in ("and", "&", "or"):
            before = all(prep[:index]) or prep[index - 1] if index else True
            after = all(prep[index + 1 :]) or prep[index + 1] if index + 1 < len(tokens) else True
            if before and after:
                continue
        kept.append(token)
    return kept, removed


def _tidy(text: str) -> str:
    return " ".join(text.strip(_EDGE_PUNCT).split())


def _is_size(word: str, extra: frozenset[str]) -> bool:
    return (
        word in SIZE_WORDS
        or singular(word) in SIZE_WORDS
        or word in extra
        or (singular(word) in extra)
    )


def _take_size(text: str, start: int, extra: frozenset[str]) -> tuple[str | None, int, list[str]]:
    """A size word straight after the amount (past any prep words): (the word, where the
    rest starts, the prep words passed). An "of" after it is skipped."""
    at = start
    passed: list[str] = []
    while True:
        found = re.compile(r"\s*([^\s,;()]+)").match(text, at)
        if found is None:
            return None, start, []
        word = _clean_token(found.group(1))
        if word in PREP_WORDS:
            passed.append(found.group(1).strip(_EDGE_PUNCT))
            at = found.end()
            continue
        if word and _is_size(word, extra):
            end = found.end()
            of = re.compile(r"\s+of\b", re.IGNORECASE).match(text, end)
            return word, of.end() if of else end, passed
        return None, start, []


def _cap(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return (cut or text[:limit]).rstrip(_EDGE_PUNCT)


# Only before pepper (C1 security round 3): "freshly ground almonds" stay ground almonds.
_FRESHLY_GROUND = re.compile(
    r"\bfreshly\s+ground\b(?=\s+(?:black\s+|white\s+)?pepper)", re.IGNORECASE
)
_OR = re.compile(r"\s+or\s+", re.IGNORECASE)


def _with_shared_noun(first: str, last: str) -> str:
    """ "heavy" beside "thickened cream" is "heavy cream"; "black" beside "white pepper" is
    "black pepper". Only when the first side is one describing word and the other side has
    more words; otherwise the first side stands as it is."""
    words = first.split()
    other = last.split()
    if len(words) == 1 and len(other) >= 2 and _clean_token(words[0]) in MODIFIER_WORDS:
        return f"{first} {' '.join(other[1:])}"
    return first


def _alternatives(parts: Iterable[str]) -> list[str]:
    names: list[str] = []
    for part in parts:
        for piece in re.split(r"\s*(?:/|,|;|\bor\b)\s*", part, flags=re.IGNORECASE):
            tokens, _ = _strip_prep(piece.split(), PREP_WORDS)
            name = _tidy(" ".join(tokens))
            if name and any(c.isalpha() for c in name) and name.lower() not in names:
                names.append(name)
    return names


# --- Reading a line ---------------------------------------------------------------------------


def read_line(text: str, size_words: Iterable[str] = (), pint_ml: int | None = None) -> ReadLine:
    """Read one ingredient line. Never raises. `size_words` are extra size words to know
    (the household's own, from `KnownIngredients.size_words`); the built-in list is `SIZE_WORDS`.
    `pint_ml`: the size of a pint to read "2 pints milk" with (568 or 473, see pints.py); without
    it a pint stays in the note, as in 0.5."""
    if len(text) > 4 * MAX_LINE_CHARS:  # not an ingredient line (and not worth a character walk)
        return _unreadable(text)
    work = working_text(text)
    if not work or len(work) > MAX_LINE_CHARS:
        return _unreadable(text)
    label = None
    labelled = _LABEL.match(work)
    if labelled is not None:  # "optional: 50g pecans": read the rest; the words stay in the note
        label = " ".join(labelled.group("label").lower().split())
        work = work[labelled.end() :]
        if not work:
            return _unreadable(text)
    extra = frozenset(_clean_token(word) for word in size_words if word.strip())
    approximately = _OR_SO.search(work) is not None  # "3-or-so cups"
    work = _OR_SO.sub("", work)
    filler = _FILLER.match(work)
    if filler is not None:
        work = work[filler.end() :]
    work = _with_digits(_spoken(work))
    work = _amount_after_name(work, extra)

    # Leading "about", "approx.", "scant"… only when a number follows.
    start = 0
    lead = _LEAD.match(work)
    if lead is not None and _measure(work, lead.end()) is not None:
        start = lead.end()

    amount: Fraction | None = None
    unit: str | None = None
    other: str | None = None
    second_used = False
    size_word: str | None = None
    quantity: str | None = None
    position = start
    passed: list[str] = []
    qualifiers: list[str] = []  # "heaped" in "1 heaped tsp"

    measure = _measure(work, start)
    if measure is None:  # "a 400g tin", "one 14 oz can"
        article = _ARTICLE.match(work, start)
        after = _measure(work, article.end()) if article else None
        if after is not None and (after.unit or after.other):
            measure = after
    if measure is not None:
        amount, unit, other, position = measure.value, measure.unit, measure.other, measure.end
        if measure.qualifier:
            qualifiers.append(measure.qualifier)
        second = _second_measure(work, position)
        if second is not None:
            second_used = True
            if second.metric and not measure.metric:
                amount, unit, other = second.value, second.unit, None
            position = second.end
    else:
        article = _ARTICLE.match(work, start)
        word = _WORD.match(work, article.end() if article else start)
        first = word.group().lower() if word else ""
        if article is not None and first in QUANTITY_WORDS:
            quantity = first
            position = word.end() if word else start
            of = re.compile(r"\s+of\b", re.IGNORECASE).match(work, position)
            position = of.end() if of else position
        elif article is not None:
            amount, position = Fraction(1), article.end()
        elif first == "dozen" and word is not None:  # "dozen eggs"
            amount, position = Fraction(1), word.start()
        elif first in BARE_QUANTITY_WORDS or (
            first in LOOSE_SIZE_WORDS
            and word is not None
            and not re.compile(r"\s+of\b", re.IGNORECASE).match(work, word.end())
        ):
            quantity = first  # "few", "Handful dried banana chips", "drop vanilla extract"
            position = word.end() if word else start
            of = re.compile(r"\s+of\b", re.IGNORECASE).match(work, position)
            position = of.end() if of else position
        elif word is not None and (first in _UNITS or _is_size(first, extra)):
            of = re.compile(r"\s+of\b", re.IGNORECASE).match(work, word.end())
            if of is not None:  # "pinch of salt", "handful of mint"
                amount, position = Fraction(1), word.start()
        if amount is not None and unit is None and other is None:
            unit, other, end = _unit(work, position)
            if unit or other:
                position = end
                of = re.compile(r"\s+of\b", re.IGNORECASE).match(work, position)
                position = of.end() if of else position

    if amount is not None or quantity is not None:
        size_word, position, passed = _take_size(work, position, extra)
        size_word = size_word or quantity

    rest = work[position:] if (amount is not None or quantity is not None) else work[start:]
    notes: list[str] = []

    rest, inside = _brackets(rest)
    if (
        inside
        and not any(c.isalpha() for c in " ".join(_strip_prep(rest.split(), PREP_WORDS)[0]))
        and _names_something(inside[0])
    ):
        # "3 large (ripe bananas, well mashed (about 1 1/2 cups))": the name is all in the
        # bracket. Its first part is read as the rest of the line, after the words before it.
        inner, nested = _brackets(inside.pop(0))
        rest = f"{rest} {inner}"
        inside = [*nested, *inside]
    names: list[str] = []
    variety: list[str] = []
    for part in list(inside):
        # "((kashmiri or byadgi) (less spicy variety))": the variety is part of the name (F32).
        plain, nested = _brackets(part)
        said = " ".join([plain, *nested[1:]])
        if nested and _VARIETY.search(said) and not any(c.isdigit() for c in nested[0]):
            alts = [a.strip() for a in re.split(r"\s*(?:\bor\b|/|,)\s*", nested[0], flags=re.I)]
            alts = [a for a in alts if a]
            if alts and all(len(a.split()) <= 2 for a in alts):
                variety = alts
                inside.remove(part)
                notes.extend(t.strip() for t in [plain, *nested[1:]] if t.strip())
    for part in list(inside):
        # "(kashmiri variety)", "(kashmiri or byadgi variety)": the same as the form above.
        if not _brackets(part)[1] and _VARIETY_WORD.search(part):
            base = _VARIETY_WORD.sub("", part)
            alts = [a.strip() for a in re.split(r"\s*(?:\bor\b|/|,)\s*", base, flags=re.I)]
            alts = [a for a in alts if a]
            if (
                alts
                and not any(c.isdigit() for c in part)
                and all(len(a.split()) <= 2 for a in alts)
                and not any(_clean_token(w) in NOTE_HINTS for a in alts for w in a.split())
            ):
                variety = alts
                inside.remove(part)
                notes.append(part.strip())
    for part in list(inside):
        # "1 cup flour (125g)": a bracket holding only a metric measure is the amount when the
        # line's own unit isn't metric (the metric one wins).
        container = size_word is not None and (
            size_word in CONTAINER_WORDS or singular(size_word) in CONTAINER_WORDS
        )
        if (
            amount is not None
            and unit not in METRIC
            and unit != "pinch"
            and (unit or other or container)
        ):
            metric = _bracket_metric(part)
            if metric is not None:
                # "half a jar (340g)": half of the bracket's amount; "1 cup flour (125g)": it.
                # "2 tins (800 g)": the bracket is the total, 800 g (proposed, for cabledrawer); only
                # one tin or a fraction of one multiplies ("half a jar (340g)" is 170 g).
                whole = unit is None and other is None and amount <= 1
                amount = amount * metric.value if whole else metric.value
                unit, other = metric.unit, None
                second_used = True
                inside.remove(part)
                continue
    for part in inside:
        groups = [piece.split() for piece in re.split(r"[,/;]", part)]
        words = [word for group in groups for word in group]
        if (
            not any(c.isdigit() for c in part)
            and 0 < len(words) <= 6
            and all(0 < len(group) <= 3 for group in groups)
            and not all(_is_prep(w, PREP_WORDS) for w in words)
            and not all(_clean_token(w) in WEAK_WORDS for w in words)
            and not any(_clean_token(w) in NOTE_HINTS for w in words)
            and all(any(c.isalpha() for c in w) for w in words)
        ):
            names.append(part)
        else:
            notes.append(part)

    # After the first comma it's a note.
    head, comma, tail = rest.partition(",")
    # "4 skinless, boneless chicken breast halves": a comma after nothing but prep words
    # doesn't start the note.
    while comma and head.split() and all(_is_prep(word, PREP_WORDS) for word in head.split()):
        more, comma, tail = tail.partition(",")
        head = f"{head} {more}"
    if comma and tail.strip():
        notes.append(tail.strip())
    rest = head

    # "salt to taste", "oil for frying": the phrase and what follows go to the note.
    phrase = _NO_AMOUNT.search(rest)
    if phrase is not None:
        notes.insert(0, rest[phrase.start() :].strip())
        rest = rest[: phrase.start()]

    # "hing / asafoetida": the first is the name, the rest are other names.
    if "/" in rest:
        pieces = [piece.strip() for piece in rest.split("/")]
        if 1 < len(pieces) <= 3 and all(any(c.isalpha() for c in piece) for piece in pieces):
            rest = _with_shared_noun(pieces[0], pieces[-1])
            names.extend(pieces[1:])

    # "ghee or butter", "100ml whole milk or 50ml milk and 50ml cream": the first choice is the
    # line, and the other choice goes in the note.
    choice = _OR.search(rest)
    if choice is not None:
        left, right = rest[: choice.start()], rest[choice.end() :]
        if _strip_prep(left.split(), PREP_WORDS)[0] and any(c.isalpha() for c in right):
            notes.insert(0, f"or {_tidy(right)}")
            rest = _with_shared_noun(left, right)

    grind = _FRESHLY_GROUND.search(rest)  # "freshly ground black pepper" is black pepper
    if grind is not None:
        notes.insert(0, "freshly ground")
        rest = f"{rest[: grind.start()]} {rest[grind.end() :]}"
    tokens = rest.split()
    while tokens and _clean_token(tokens[0]) == "of":
        tokens.pop(0)
    written = _tidy(" ".join(tokens))

    packaged = size_word is not None and (
        size_word in CONTAINER_WORDS or singular(size_word) in CONTAINER_WORDS
    )
    kept, removed = _strip_prep(tokens, DESCRIPTOR_WORDS if packaged else PREP_WORDS)
    # "whole allspice berries" is Allspice berries, "8 whole cloves" is 8 cloves: "whole" comes out
    # of every "whole X" name and stays in the note (F103, cabledrawer 31 Oct). Not when it is all
    # there is ("1 whole"). This is the F87 rule, one step on: F87 keeps a word before "cloves"
    # from being read as the name, and "whole" is now no longer a word to keep.
    others = [token for token in kept if _clean_token(token) != WHOLE]
    if others and len(others) < len(kept):
        removed = [*removed, WHOLE]
        kept = others
    name = _tidy(" ".join(kept))
    parts = name.split()
    if (
        amount is not None
        and size_word is None
        and len(parts) >= 2
        and singular(parts[-1].lower()) in TRAILING_SIZE_WORDS
        # "8 whole cloves" is the spice (name "whole cloves"), not "8 cloves of whole" (F87):
        # what is left must be more than colour, size or "whole/dried/ground" words.
        and not all(_clean_token(word) in WEAK_WORDS for word in parts[:-1])
    ):  # "2 garlic cloves" is "2 cloves garlic"
        size_word = parts[-1].lower()
        name = " ".join(parts[:-1])
        if written.lower().endswith(size_word):
            written = written[: -len(size_word)].rstrip()
    if variety and name:  # "Kashmiri dried red chilies", also called "byadgi"
        name = f"{variety[0]} {name}"
        written = f"{variety[0]} {written}"
        names.extend(variety[1:])
    other_names = _alternatives(names)

    chosen = measure is not None and measure.chosen
    pints = None
    pint_unit = None
    if pint_ml is not None and other in PINT_FAMILY and amount is not None:
        pint_unit = PINT_FAMILY[other]  # 2 pints: 1,136 ml; a UK quart 1,136, a US one 946
        pints = amount
        amount = _rounded(amount * Fraction(UNIT_ML[pint_unit][kind_of(pint_ml)]))
        unit, other, chosen = "ml", None, True
    if other in OUNCES | POUNDS and amount is not None:  # 8 oz on its own: exactly 226.8 g
        amount = _rounded(amount * (GRAMS_PER_OUNCE if other in OUNCES else GRAMS_PER_POUND))
        unit, other, chosen = "g", None, True
    if other is not None and amount is not None:  # 8 pints: not an amount we can use
        said = ""
        if measure is not None and not measure.chosen and not second_used:
            said = _tidy(work[measure.start : measure.end])  # as written ("⅓ inch")
        notes.insert(0, said or f"{_trim(amount)} {other}")
        amount = None
        unit = None
    number: Decimal | None = None
    if amount is not None and amount <= Fraction(MAX_AMOUNT) * 1000:  # far past any amount: none
        try:
            number = _decimal(amount)
        except InvalidOperation:  # more than 28 digits
            number = None
    if number is not None and not (0 < number <= MAX_AMOUNT):  # also 0.0001, which rounds to 0
        number = None
    if number is None:
        unit = None

    note_parts = [
        label or "",
        " ".join([*qualifiers, *passed, *removed]),
        "or so" if approximately else "",
        *notes,
    ]
    note = _cap(", ".join(dict.fromkeys(_tidy(p) for p in note_parts if _tidy(p))), MAX_NOTE_CHARS)

    readable = any(c.isalpha() for c in name)
    if not readable:
        return _unreadable(text)
    counts = number is not None and unit != "pinch" and (unit is not None or size_word is None)
    return ReadLine(
        text=text,
        amount=number,
        unit=unit,
        size_word=size_word,
        name=name,
        name_as_written=written,
        other_names=tuple(other_names),
        note=note or None,
        counts=counts,
        readable=True,
        chosen=chosen or second_used,
        pints=pints if number is not None else None,
        pint_unit=pint_unit if number is not None else None,
    )


def _rounded(value: Fraction) -> Fraction:
    """A converted amount as a cook writes it (340 g, 5.67 g): see `line_prep.kitchen_round`."""
    if value > Fraction(MAX_AMOUNT) * 1000:  # absurdly large: not rounded (and never an error)
        return value
    try:
        exact = Decimal(value.numerator) / Decimal(value.denominator)
        return Fraction(kitchen_round(exact))
    except InvalidOperation, ValueError, OverflowError:
        return value


# --- Two ingredients on one line (F26) --------------------------------------------------------

_PLUS = re.compile(r"\s+\+\s+")
_AND = re.compile(r"\s+and\s+", re.IGNORECASE)
_AND_A = re.compile(
    r"\s+and\s+(?=(?:a|an)\s+(?:pinch|dash|splash|sprinkle|drizzle|handful|knob|glug|swish|squeeze)\b)",
    re.IGNORECASE,
)
_TASTE_END = re.compile(
    r"\b(?:to\s+taste|as\s+(?:needed|required|desired)|for\s+(?:the\s+)?(?:garnish|serving)"
    r"|to\s+(?:serve|garnish))\s*$",
    re.IGNORECASE,
)
MAX_SPLIT_WORDS = 6  # a side longer than this is a sentence, not an ingredient


def split_line(text: str) -> list[str]:
    """One written line that holds two ingredients, as two lines: "a swish of olive oil + a
    sprinkle of salt" (a spaced "+"), and "fish sauce and brown sugar to taste" (an "and" in a
    line that ends "to taste", "as needed" or "for serving", with no amount in it: "salt and
    pepper" is two, "macaroni and cheese" is one). A line that isn't one of these is returned
    as it was, in a list of one."""
    work = working_text(text)
    if not work or len(work) > MAX_LINE_CHARS:
        return [text]
    plus = _PLUS.split(work)
    if 1 < len(plus) <= 3 and all(_short_side(side) for side in plus):
        return [side.strip() for side in plus]
    ending = _TASTE_END.search(work)
    if ending is not None:
        head, suffix = work[: ending.start()], ending.group()
        sides = _AND.split(head)
        if (
            len(sides) == 2
            and not any(c.isdigit() for c in head)
            and all(_short_side(side) for side in sides)
            and not _one_name(sides)
        ):
            return [f"{side.strip()} {suffix}" for side in sides]
    spoken = _AND_A.search(work)  # "olive oil and a sprinkle of salt"
    if spoken is not None and not any(c.isdigit() for c in work):
        left, right = work[: spoken.start()], work[spoken.end() :]
        if _short_side(left) and _short_side(right):
            return [left.strip(), right.strip()]
    return [text]


# A word before "and" that joins the two halves of one name: "sweet and sour sauce", "oil and
# vinegar dressing". "salt and black pepper" is two, because "salt" is not one of these.
JOINED_FIRST_WORDS = MODIFIER_WORDS | frozenset({"oil", "fish", "mac", "macaroni", "bread", "rock"})


def _one_name(sides: list[str]) -> bool:
    """One side is a single word that is on `JOINED_FIRST_WORDS` and the other has more, so the
    "and" joins words of one name."""
    first = _brackets(sides[0])[0].split()
    rest = _brackets(sides[1])[0].split()
    return len(first) == 1 and len(rest) > 1 and _clean_token(first[0]) in JOINED_FIRST_WORDS


def _short_side(side: str) -> bool:
    bare = _brackets(side)[0]
    return any(c.isalpha() for c in bare) and len(bare.split()) <= MAX_SPLIT_WORDS


def read_lines(
    text: str, size_words: Iterable[str] = (), pint_ml: int | None = None
) -> list[ReadLine]:
    """`read_line`, but a line that holds two ingredients gives two (see `split_line`). If
    either half can't be read, the line is read as one. Never raises."""
    extra = tuple(size_words)
    parts = split_line(text)
    if len(parts) > 1:
        reads = [read_line(part, extra, pint_ml) for part in parts]
        if all(read.readable for read in reads):
            return reads
    return [read_line(text, extra, pint_ml)]


def _trim(value: Fraction) -> str:
    return format(_decimal(value), "f")
