"""Pasted recipe text → a title, ingredient lines and method steps (spec section 6, "Recipe
import, decided for 0.5"; docs/dev/ingredient-reader.md).

Pure text in, plain values out: nothing is read from the network or the database. The
ingredient lines go to `ingredient_reader.read_line` one by one.

It finds the parts from common headings ("Ingredients", "Method", "Instructions",
"Directions", numbered steps). With no headings it makes its best guess: lines that look
like an amount are ingredients, the first line is the title, the rest is the method. Hidden
characters are stripped, not refused (it is pasted, not typed).
"""

import re
from dataclasses import dataclass

from mealwright.api.v1.recipe_schemas import GLYPHS, MAX_LINES, MAX_STEP_CHARS, MAX_STEPS
from mealwright.ingredient_reader import BULLETS, read_line
from mealwright.line_prep import is_ingredient_heading, is_step_heading
from mealwright.names import cut_text, without_hidden

MAX_PASTED_CHARS = 100_000
MAX_TITLE_CHARS = 200  # a recipe's name
MAX_LINE_CHARS = 200  # the most characters in an ingredient line's words

PASTED_TOO_LONG = (
    "That text is longer than 100,000 characters. Paste just the recipe: its title, "
    "ingredients and method."
)


class PastedTooLong(ValueError):
    """The pasted text is over 100,000 characters. `str(error)` is a sentence to show."""

    def __init__(self) -> None:
        super().__init__(PASTED_TOO_LONG)


@dataclass(frozen=True)
class LeftOut:
    """A part of the pasted text that was left out for being a note or a tip: its heading as
    written ("Tips") and how many lines were under it (cabledrawer 23 Oct, question 17). The review
    screen says so, so the lines can be added by hand."""

    heading: str
    lines: int


@dataclass(frozen=True)
class PastedRecipe:
    """What was found in pasted text.

    - `name`: the title, or "" if the text has none.
    - `ingredients`: the ingredient lines, as written (bullets taken off), up to 200.
    - `steps`: the method steps, numbers taken off, up to 100.
    - `lines_cut`, `steps_cut`: how many ingredient lines / steps were left out for being
      over the limits (the review screen says so).
    - `left_out`: the Notes, Tips and similar parts left out, each with its line count.
    """

    name: str
    ingredients: tuple[str, ...]
    steps: tuple[str, ...]
    lines_cut: int
    steps_cut: int
    left_out: tuple[LeftOut, ...] = ()
    serves: int | None = None
    time_minutes: int | None = None


# --- Serves and time (F171) --------------------------------------------------------------------

_NUM = r"(?:\d+\s*[½¼¾]|\d+(?:\.\d+)?|[½¼¾])"
_SERVES_FACT = re.compile(
    r"(?:serves|servings?|serving size)\s*:?\s*(?P<a>\d{1,3})"
    r"(?:\s*(?:-|\u2013|to)\s*(?P<b>\d{1,3}))?"
    r"(?:\s*(?:people|persons?|portions?|servings?))?",
    re.IGNORECASE,
)
_TIME_FACT = re.compile(
    r"(?P<kind>takes|total time|total|time|ready in|prep(?:aration)?(?P<prep_time> time)?|"
    r"cook(?:ing)?(?P<cook_time> time)?)(?P<colon>\s*:)?\s*(?:about\s+|around\s+|approx\.?\s+)?"
    rf"(?:(?P<h>{_NUM})\s*(?:h|hr|hrs|hours?))?\s*(?:(?P<m>\d+)\s*(?:m|min|mins|minutes?))?",
    re.IGNORECASE,
)
_FACT_SEPARATORS = re.compile(r"\s*(?:[.·|;•,]|\s-\s)\s*")


def _hours(text: str) -> float:
    total = 0.0
    for part in re.findall(r"\d+(?:\.\d+)?|[½¼¾]", text):
        total += {"½": 0.5, "¼": 0.25, "¾": 0.75}.get(part) or float(part)
    return total


def _fact_line(line: str, strict: bool = True) -> tuple[int | None, dict[str, int]] | None:
    """A line made only of "Serves 4" / "Takes 30 minutes" facts (several may share a line,
    "Serves 4. Prep 10 min."): (serves, minutes by kind), else None. A sentence that merely
    mentions them ("Serves 4 with rice.", "Cook for 30 minutes.") is not a fact line.

    `strict`: below the Ingredients or Method heading, and with no headings at all, a line
    that could be a method step ("Cook 20 minutes.", "Prep 5 min") is a step: only the clear
    forms count ("Takes …", "Total time …", "Prep time: …", "Cook time: …", "Ready in …",
    "Serves …"). Above the headings every form does."""
    text = line.strip().lstrip(BULLETS).strip(_DECORATION)
    if not text or len(text) > 80:
        return None
    serves: int | None = None
    minutes: dict[str, int] = {}
    for part in (p.strip() for p in _FACT_SEPARATORS.split(text)):
        if not part:
            continue
        found = _SERVES_FACT.fullmatch(part)
        if found:
            serves = int(found["b"] or found["a"])
            continue
        found = _TIME_FACT.fullmatch(part)
        if not found or not (found["h"] or found["m"]):
            return None
        word = found["kind"].lower()
        if strict and not (
            word in {"takes", "total time", "time", "ready in"}
            or found["colon"]
            or found["prep_time"]
            or found["cook_time"]
        ):
            return None  # "Cook 20 minutes.", "Total 30 min": maybe a step
        kind = "prep" if word.startswith("prep") else "cook" if word.startswith("cook") else "total"
        minutes[kind] = round(_hours(found["h"] or "") * 60) + int(found["m"] or 0)
    if serves is None and not minutes:
        return None
    return serves, minutes


def _total_minutes(minutes: dict[str, int]) -> int | None:
    """A total beats the parts; prep and cook together add up; a lone cook time stands in for
    the total; a lone prep time is not one."""
    if "total" in minutes:
        return minutes["total"] or None
    if "prep" in minutes and "cook" in minutes:
        return minutes["prep"] + minutes["cook"]
    return minutes.get("cook") or None


# --- Headings ---------------------------------------------------------------------------------

_DECORATION = " \t#*_>=~|-–—:.•"  # noqa: RUF001
_INGREDIENTS = re.compile(
    r"(?:ingredients?|ingredient list|you(?: will|'ll|’ll) need|what you(?: will|'ll|’ll)"
    r" need)(?:\s*\([^)]*\))?",
    re.IGNORECASE,
)
_METHOD = re.compile(
    r"(?:method|instructions?|directions?|preparation|steps?|procedure|how to make it|"
    r"cooking (?:method|instructions?)|preparation method)(?:\s*\([^)]*\))?",
    re.IGNORECASE,
)
_OTHER = re.compile(
    r"(?:notes?|tips?|chef(?:'s|’s)? notes?|nutrition(?: facts| information)?|equipment|"
    r"storage|variations?|serving suggestions?|video|reviews?|comments?)(?:\s*\([^)]*\))?",
    re.IGNORECASE,
)


def _heading(line: str) -> str | None:
    """ "ingredients", "method" or "other" if the line is a heading of that kind."""
    text = line.strip(_DECORATION)
    if not text or len(text) > 40:
        return None
    if _INGREDIENTS.fullmatch(text):
        return "ingredients"
    if _METHOD.fullmatch(text):
        return "method"
    if _OTHER.fullmatch(text):
        return "other"
    return None


# --- Lines that look like what ---------------------------------------------------------------

_NUMBERED = re.compile(r"\s*(?:step\s*)?\d{1,3}\s*(?:[.):]|[-\u2013]\s)\s*\S", re.IGNORECASE)
_STEP_NUMBER = re.compile(r"(?:step\s*)?\d{1,3}\s*(?:[.):]|[-\u2013]\s)\s*", re.IGNORECASE)
_DECIMAL_START = re.compile(r"\d+\s*[.):]\s*\d")  # 1.5 cups, 1) 2 onions: not a step number
_QUANTITY_START = re.compile(rf"[\d{''.join(GLYPHS)}]|\.\d")
_TIME = re.compile(
    r"\d\s*[°º]|\b(?:degrees?|minutes?|mins?|hours?|hrs?|seconds?|secs?|gas mark)\b",
    re.IGNORECASE,
)
_ARTICLE_START = re.compile(r"(?:a|an)\s+(?:pinch|handful|few|little|bit|sprig|bunch)\b", re.I)


def _looks_like_amount(line: str) -> bool:
    """Does the line read like an ingredient with an amount ("2 onions, chopped")? Not a
    numbered step ("1. Heat oil"), not a time or temperature ("20 minutes", "180°C")."""
    text = line.lstrip(BULLETS)
    if not text or len(text) > 150 or _TIME.search(text):
        return False
    if _is_numbered_step(text):
        return False
    if not (_QUANTITY_START.match(text) or _ARTICLE_START.match(text)):
        return False
    read = read_line(text)
    if not read.readable or (read.amount is None and read.size_word is None):
        return False
    if read.unit is not None or read.size_word is not None:
        return True
    return len(text.split()) <= 7 and not text.endswith(".")


def _step_number(line: str) -> int | None:
    found = re.match(r"(?:step\s*)?(\d{1,3})", line.lstrip(BULLETS), re.IGNORECASE)
    return int(found[1]) if found else None


def _is_numbered_step(line: str) -> bool:
    text = line.lstrip(BULLETS)
    return bool(_NUMBERED.match(text)) and not _DECIMAL_START.match(text)


def _short_text(line: str) -> bool:
    """Short enough to be a bare ingredient ("Salt", "Curry leaves") among other ingredients."""
    text = line.lstrip(BULLETS)
    return 0 < len(text) <= 50 and len(text.split()) <= 6 and not text.endswith((".", "!", "?"))


# --- Steps ------------------------------------------------------------------------------------


def _colon_heading(text: str) -> bool:
    """A short title ending in a colon that starts with a capital ("For the dosa:", "• For the
    dosa:"): `is_step_heading`'s colon form only."""
    words = text.lstrip(BULLETS).strip()
    return words[:1].isupper() and words.endswith(":") and is_step_heading(words)


def _step_texts(lines: list[str]) -> list[str]:
    """Method lines → steps. If any line is numbered, an unnumbered line straight after a
    numbered one carries on that step (a wrapped line), unless it is a heading ("For the dosa:",
    `is_step_heading`, starting with a capital); a blank line ends a step. If none are numbered,
    every line is a step."""
    numbered = any(_is_numbered_step(line) for line in lines)
    steps: list[str] = []
    carrying = False
    for line in lines:
        text = line.strip()
        if not text:
            carrying = False
            continue
        if _is_numbered_step(text):
            steps.append(_STEP_NUMBER.sub("", text.lstrip(BULLETS), count=1).strip())
            carrying = True
        elif _colon_heading(text):
            # A heading ("For the dosa:") straight after a step is never part of it (cabledrawer
            # 10 Nov). A wrapped line starts small ("following:"), so it still carries on, and
            # so does a wrapped line in capitals ("GAS MARK 4"): only the colon makes a heading.
            steps.append(text.lstrip(BULLETS).strip())
            carrying = False
        elif numbered and carrying and steps:
            if len(steps[-1]) < MAX_STEP_CHARS:  # (and no quadratic copying of a huge step)
                steps[-1] = f"{steps[-1]} {text}"
        else:
            steps.append(text.lstrip(BULLETS))
            carrying = False
    return [cut_text(step, MAX_STEP_CHARS).rstrip() for step in steps if step]


def _ingredient_texts(lines: list[str]) -> list[str]:
    found = []
    for line in lines:
        text = line.strip().lstrip(BULLETS).strip()
        if text:
            found.append(cut_text(text, MAX_LINE_CHARS).rstrip())
    return found


# --- Splitting without headings ---------------------------------------------------------------


_SAYS_THE = re.compile(r"(?:for|to)\s+the\s", re.IGNORECASE)


def _bare(line: str) -> str:
    """The line without its bullet and outer spaces."""
    return line.strip().lstrip(BULLETS).strip()


def _split_by_look(lines: list[str]) -> tuple[list[str], list[str]]:
    """No headings to go by: (ingredient lines, method lines). The lines from the first to
    the last amount-like one are the ingredients, with short lines between them; lines
    before them are dropped (a description), lines after them are the method."""
    amounts = [i for i, line in enumerate(lines) if _looks_like_amount(line)]
    if not amounts:
        return [], [line for line in lines if line.strip()]
    first, last = amounts[0], amounts[-1]
    # A group heading right above the first amount ("For the batter") is kept, not dropped as
    # a description (F222). Only when it says "the" or another heading follows among the
    # ingredients: "For four people" or "For a crowd" under the title says who it serves
    # (FX4 review r1).
    above = first - 1
    while above >= 0 and not lines[above].strip():
        above -= 1
    if above >= 0:
        heading = _bare(lines[above])
        if is_ingredient_heading(heading) and (
            _SAYS_THE.match(heading)
            or any(is_ingredient_heading(_bare(line)) for line in lines[first : last + 1])
        ):
            first = above
    # A bare line straight after the last amount ("Salt") is still an ingredient.
    while (
        last + 1 < len(lines)
        and _short_text(lines[last + 1])
        and len(lines[last + 1].split()) <= 4
        and not _heading(lines[last + 1])
        and not _TIME.search(lines[last + 1])
    ):
        last += 1
    ingredients = [
        line
        for line in lines[first : last + 1]
        if line.strip() and (_looks_like_amount(line) or _short_text(line))
    ]
    steps = [line for line in lines[last + 1 :] if line.strip()]
    # Lines in the middle that are neither (a sentence) belong to the method.
    middle = [
        line
        for line in lines[first : last + 1]
        if line.strip() and not (_looks_like_amount(line) or _short_text(line))
    ]
    return ingredients, middle + steps


# --- The reader -------------------------------------------------------------------------------


def _title(lines: list[str]) -> str:
    for line in lines:
        text = line.strip().strip(_DECORATION).strip()
        if text:
            if _looks_like_amount(text) or _is_numbered_step(text):
                return ""
            return cut_text(" ".join(text.split()), MAX_TITLE_CHARS).rstrip()
    return ""


def read_pasted(text: str) -> PastedRecipe:
    """Find the title, ingredients and method in pasted recipe text. Text over 100,000
    characters raises `PastedTooLong`; anything else gives a result, even if it is empty."""
    if len(text) > MAX_PASTED_CHARS:
        raise PastedTooLong
    lines = [line.strip() for line in without_hidden(text).split("\n")]
    # "Serves 4" and "Takes 30 minutes" lines are read, then left out of the lines (F171).
    serves: int | None = None
    minutes: dict[str, int] = {}
    kept: list[str] = []
    first_heading = next(
        (i for i, line in enumerate(lines) if _heading(line) in {"ingredients", "method"}),
        0,
    )
    for at, line in enumerate(lines):
        fact = _fact_line(line, strict=at >= first_heading)
        if fact is None:
            kept.append(line)
            continue
        serves = fact[0] if serves is None else serves
        for which, amount in fact[1].items():
            minutes.setdefault(which, amount)
    lines = kept

    sections: dict[str, list[str]] = {"start": [], "ingredients": [], "method": []}
    left_headings: list[str] = []  # each part left out, and how many lines it had
    left_lines: list[int] = []
    current = "start"
    seen: set[str] = set()
    last_step: int | None = None
    for line in lines:
        kind = _heading(line)
        if kind is not None and (kind == "other" or kind not in seen):
            seen.add(kind)
            current = (
                "ingredients"
                if kind == "ingredients"
                else "method"
                if kind == "method"
                else "other"
            )
            if current == "other":
                sections.setdefault("other", [])
                left_headings.append(line.strip(_DECORATION).strip())
                left_lines.append(0)
            continue
        number = _step_number(line) if _is_numbered_step(line) else None
        # A left-out part ("Tips") in the middle of the method ends where the numbered steps
        # carry on (the next number); only a trailing part is dropped.
        if current == "other" and last_step is not None and number == last_step + 1:
            current = "method"
        if current == "method" and number is not None:
            last_step = number
        sections.setdefault(current, []).append(line)
        if current == "other" and line and left_lines:
            left_lines[-1] += 1

    if "ingredients" in seen or "method" in seen:
        name = _title(sections["start"])
        title_taken = bool(name)
        ingredients = sections["ingredients"]
        steps = sections["method"]
        if "ingredients" not in seen:  # only a method heading: the amounts above it
            rest = sections["start"][1:] if title_taken else sections["start"]
            ingredients, middle = _split_by_look(rest)
            steps = middle + steps
        elif "method" not in seen:  # only an ingredients heading: the method follows it
            ingredients, steps = _split_ingredients_then_method(ingredients)
    else:
        name = _title(lines)
        first = next((i for i, line in enumerate(lines) if line.strip()), 0)
        body = lines[first + 1 :] if name else lines
        ingredients, steps = _split_by_look(body)

    ingredient_lines = _ingredient_texts(ingredients)
    step_lines = _step_texts(steps)
    return PastedRecipe(
        name=name,
        ingredients=tuple(ingredient_lines[:MAX_LINES]),
        steps=tuple(step_lines[:MAX_STEPS]),
        lines_cut=max(0, len(ingredient_lines) - MAX_LINES),
        steps_cut=max(0, len(step_lines) - MAX_STEPS),
        serves=serves,
        time_minutes=_total_minutes(minutes),
        left_out=tuple(
            LeftOut(heading, count)
            for heading, count in zip(left_headings, left_lines, strict=True)
            if count
        ),
    )


def _split_ingredients_then_method(lines: list[str]) -> tuple[list[str], list[str]]:
    """Only an "Ingredients" heading: the ingredients end at the first numbered step, or
    after the last amount-like line; what follows is the method."""
    end = next((i for i, line in enumerate(lines) if _is_numbered_step(line)), len(lines))
    amounts = [i for i, line in enumerate(lines[:end]) if _looks_like_amount(line)]
    if amounts:
        end = min(end, amounts[-1] + 1)
    return lines[:end], lines[end:]
