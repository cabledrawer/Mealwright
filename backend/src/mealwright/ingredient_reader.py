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
from decimal import ROUND_HALF_UP, Decimal
from fractions import Fraction

from mealwright.amounts import DEFAULT_CUP_ML, MAX_AMOUNT, CountedAs, unit_family, unit_size
from mealwright.api.v1.recipe_schemas import GLYPHS, UNIT_ALIASES, fraction_of
from mealwright.names import singular, without_hidden

# The longest line read. Anything longer isn't an ingredient line.
MAX_LINE_CHARS = 1000
MAX_NOTE_CHARS = 200  # the recipe editor's limit for a line's note

# --- The word lists ---------------------------------------------------------------------------

# Prep words (and a few plain descriptors) that are taken out of a name and kept in the
# note. A short, closed list: a word is here only if taking it out never turns one
# ingredient into another. Left out on purpose: dried, ground, powder, whole, frozen, cooked,
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
        "heaped", "heaping", "level", "packed", "divided",
    }
)  # fmt: skip
# The descriptors among them: the only ones taken out of a packaged product's name
# ("1 x 400g tin chopped tomatoes" keeps "chopped").
DESCRIPTOR_WORDS = frozenset(
    {"fresh", "large", "medium", "small", "big", "ripe", "firm", "organic", "optional"}
)

# Words that name a size an ingredient may be bought or measured in. A line with one
# ("1 bunch coriander") counts only if the matched ingredient has a size of that name.
SIZE_WORDS = frozenset(
    {
        "bunch", "sprig", "handful", "clove", "tin", "can", "jar", "packet", "pack", "bag",
        "box", "head", "stick", "slice", "piece", "knob", "stalk", "stem", "bulb", "sachet",
        "carton", "bottle", "tub", "tube", "loaf", "dash", "splash", "drizzle", "glug",
        "dollop", "sheet", "rasher", "fillet", "rib", "pot", "block", "dozen", "tray",
    }
)  # fmt: skip
# Sizes that are a container: a product's name inside one keeps its prep word.
CONTAINER_WORDS = frozenset(
    {"tin", "can", "jar", "packet", "pack", "bag", "box", "carton", "bottle", "tub", "tube",
     "sachet", "pot", "block"}
)  # fmt: skip
# Words that say "some", with no number. Kept like a size word; they never count.
QUANTITY_WORDS = frozenset({"few", "some", "little", "bit", "couple", "several"})
# Without "a" in front, only these say "some" ("little gem lettuce" is a name).
BARE_QUANTITY_WORDS = frozenset({"few", "some", "several"})
# A word in a bracket that makes it a note, not another name for the ingredient.
NOTE_HINTS = frozenset(
    {"see", "note", "notes", "substitute", "for", "to", "about", "approx", "plus", "preferably",
     "if", "such", "as", "like", "available", "use", "can", "per", "more", "extra", "or", "and",
     "whole", "total", "each", "only", "the", "a", "an", "of", "in", "with", "from", "your",
     "any", "this", "that", "kind", "type", "sort", "brand", "at", "on", "it", "them", "is"}
)  # fmt: skip

# Pints, read only when the caller says how big a pint is (`read_line(pint_ml=...)`; see pints.py).
PINTS = frozenset({"pint", "pints", "pt"})

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
# powder", "half fat crème fraîche", "two thirds of a cup", "Ten Acre crisps" (proposed, for
# cabledrawer). The one place to add more.
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
    r"|to\s+(?:garnish|serve|season|decorate)|optional)\b",
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


def _measure(text: str, start: int, allow_multiple: bool = True) -> _Measure | None:
    """A number with its unit, a range, or a pack multiple, at `start`."""
    first = _number(text, start)
    if first is None:
        return None
    value, at = first
    unit, other, end = _unit(text, at)
    if allow_multiple and unit is None and other is None:
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
    return _Measure(value, unit, other, start, end)


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
    plain = without_hidden(text.translate(_DASHES).translate(_SLASHES))
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


def _names_something(bracket: str) -> bool:
    """Whether a bracket's first part can be a name: "ripe bananas, well mashed" can; a measure
    such as "about 1 lb" or "about 2 cups" can't (no digit, and no note word first)."""
    first = re.split(r"[,(]", bracket, maxsplit=1)[0].split()
    return bool(first) and not any(c.isdigit() for c in " ".join(first)) and (
        _clean_token(first[0]) not in NOTE_HINTS
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
    work = _with_digits(work)
    extra = frozenset(_clean_token(word) for word in size_words if word.strip())

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

    measure = _measure(work, start)
    if measure is None:  # "a 400g tin", "one 14 oz can"
        article = _ARTICLE.match(work, start)
        after = _measure(work, article.end()) if article else None
        if after is not None and (after.unit or after.other):
            measure = after
    if measure is not None:
        amount, unit, other, position = measure.value, measure.unit, measure.other, measure.end
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
        elif first in BARE_QUANTITY_WORDS:
            quantity = first
            position = word.end() if word else start
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
    for part in list(inside):
        # "1 cup flour (125g)": a bracket holding only a metric measure is the amount when the
        # line's own unit isn't metric (the metric one wins).
        if amount is not None and unit not in METRIC and unit != "pinch" and (unit or other):
            metric = _bracket_metric(part)
            if metric is not None:
                amount, unit, other = metric.value, metric.unit, None
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
            and not any(_clean_token(w) in NOTE_HINTS for w in words)
            and all(any(c.isalpha() for c in w) for w in words)
        ):
            names.append(part)
        else:
            notes.append(part)

    # After the first comma it's a note.
    head, comma, tail = rest.partition(",")
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
            rest = pieces[0]
            names.extend(pieces[1:])

    tokens = rest.split()
    while tokens and _clean_token(tokens[0]) == "of":
        tokens.pop(0)
    written = _tidy(" ".join(tokens))

    packaged = size_word is not None and (
        size_word in CONTAINER_WORDS or singular(size_word) in CONTAINER_WORDS
    )
    kept, removed = _strip_prep(tokens, DESCRIPTOR_WORDS if packaged else PREP_WORDS)
    name = _tidy(" ".join(kept))
    other_names = _alternatives(names)

    chosen = measure is not None and measure.chosen
    pints = None
    if pint_ml is not None and other in PINTS and amount is not None:  # 2 pints: 1,136 ml
        pints = amount
        amount *= pint_ml
        unit, other, chosen = "ml", None, True
    if other in OUNCES | POUNDS and amount is not None:  # 8 oz on its own: exactly 226.8 g
        amount *= GRAMS_PER_OUNCE if other in OUNCES else GRAMS_PER_POUND
        unit, other, chosen = "g", None, True
    if other is not None and amount is not None:  # 8 pints: not an amount we can use
        said = ""
        if measure is not None and not measure.chosen and not second_used:
            said = _tidy(work[measure.start : measure.end])  # as written ("⅓ inch")
        notes.insert(0, said or f"{_trim(amount)} {other}")
        amount = None
        unit = None
    number = _decimal(amount) if amount is not None else None
    if number is not None and not (0 < number <= MAX_AMOUNT):  # also 0.0001, which rounds to 0
        number = None
    if number is None:
        unit = None

    note_parts = [label or "", " ".join([*passed, *removed]), *notes]
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
    )


def _trim(value: Fraction) -> str:
    return format(_decimal(value), "f")
