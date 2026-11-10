"""Steps that wait (0.8 wave 5, M1; cabledrawer 31 Oct and 9 Nov).

A step can carry a wait: marinate, ferment, soak... as a range in whole minutes, or a range that
ends at "overnight". A recipe's time then shows its active time plus the wait. The wait is kept
in minutes (overnight counts as `OVERNIGHT_MINUTES`) so the plan can later work backwards from it.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass

from mealwright.models import RecipeStep

# The kinds, in the order the Waits field offers them (words in docs/dev/words.md).
KINDS = ("marinate", "soak", "ferment", "rest", "chill", "prove")
OVERNIGHT_MINUTES = 12 * 60  # "overnight" for the plan's sums
MAX_WAIT_MINUTES = 14_400  # ten days, as a recipe's own time


@dataclass(frozen=True)
class Wait:
    kind: str
    min_minutes: int
    max_minutes: int
    overnight: bool


def of_step(step: RecipeStep) -> Wait | None:
    """The step's wait, or None."""
    if step.kind != "step" or step.wait_kind is None or step.wait_min_minutes is None:
        return None
    longest = step.wait_max_minutes or step.wait_min_minutes
    return Wait(
        kind=step.wait_kind,
        min_minutes=step.wait_min_minutes,
        max_minutes=max(longest, step.wait_min_minutes),
        overnight=bool(step.wait_overnight),
    )


def total(steps: Iterable[RecipeStep]) -> Wait | None:
    """All of a recipe's waits as one: the shortest and longest added up, "overnight" if any end
    that way, and the kind if they are all one kind ("waiting" otherwise: kind `"wait"`).
    None when no step waits."""
    waits = [w for w in (of_step(s) for s in steps) if w is not None]
    if not waits:
        return None
    kinds = {w.kind for w in waits}
    return Wait(
        kind=waits[0].kind if len(kinds) == 1 else "wait",
        min_minutes=sum(w.min_minutes for w in waits),
        max_minutes=sum(w.max_minutes for w in waits),
        overnight=any(w.overnight for w in waits),
    )


# --- Reading a wait from a step's words ----------------------------------------------------------
# The importer only suggests; the person confirms it on Check. Only the base verb counts
# ("marinate", "soak", "ferment", "rest", "chill", "refrigerate", "prove"), never "soaked
# chickpeas", so "add the soaked chickpeas and simmer 45 minutes" is not a wait.

_KIND_WORDS = (
    ("marinate", r"marinat(?:e|ing)"),
    ("soak", r"soak(?:ing)?"),
    ("ferment", r"ferment(?:ing)?"),
    ("rest", r"rest(?:ing)?"),
    ("chill", r"chill(?:ing)?|refrigerat(?:e|ing)|refrigeration"),
    ("prove", r"prov(?:e|ing)|proof(?:ing)?"),
)
_KIND = re.compile(
    "|".join(f"(?P<{kind}>\\b(?:{words})\\b)" for kind, words in _KIND_WORDS), re.IGNORECASE
)
_NUMBER = r"\d{1,4}(?:\.\d{1,2})?"
_UNIT = r"(?:h(?:ou)?rs?|hours?|h|mins?|minutes?|days?)\b"
_DURATION = re.compile(
    rf"(?P<a>{_NUMBER})\s*(?P<au>{_UNIT})?"
    rf"(?:\s*,?\s*(?:-|–|—|to|or)\s*(?:(?P<b>{_NUMBER})\s*(?P<bu>{_UNIT})|(?P<on>overnight)))?",  # noqa: RUF001
    re.IGNORECASE,
)
_OVERNIGHT = re.compile(r"\bovernight\b", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.;!?])\s+|\n+")
SUGGEST_FROM_MINUTES = 30  # a shorter rest or soak is part of the step, not a wait


def _minutes(number: str, unit: str) -> int:
    unit = unit.lower()
    per = 1 if unit.startswith("m") else 1440 if unit.startswith("d") else 60
    return round(float(number) * per)


def read_wait(text: str) -> Wait | None:
    """A wait suggested from a step's words, or None: "marinate for 4 hours or overnight",
    "ferment 8-12 hours", "soak overnight". The first sentence with a wait word and a length
    after it of 30 minutes or more (or "overnight") gives it; one step gets one wait."""
    for sentence in _SENTENCE.split(text):
        for found in _KIND.finditer(sentence):
            kind = found.lastgroup or "rest"
            wait = _length(kind, sentence[found.end() :])
            if wait is not None:
                return wait
    return None


def _length(kind: str, after: str) -> Wait | None:
    for found in _DURATION.finditer(after):
        first_unit = found.group("au") or found.group("bu")
        if first_unit is None:
            continue  # "2 onions": a number with no time
        low = _minutes(found.group("a"), first_unit)
        if found.group("on"):
            return _make(kind, low, OVERNIGHT_MINUTES, True)
        high = _minutes(found.group("b"), found.group("bu")) if found.group("b") else low
        # "1 hour or 2": the second number has no unit of its own and is not matched; fine.
        if max(low, high) < SUGGEST_FROM_MINUTES:
            return None  # the first length after the word is short: not a wait
        return _make(kind, low, high, False)
    if _OVERNIGHT.search(after):
        return _make(kind, OVERNIGHT_MINUTES, OVERNIGHT_MINUTES, True)
    return None


def _make(kind: str, low: int, high: int, overnight: bool) -> Wait | None:
    low, high = min(low, high), max(low, high)
    if low < 1 or high > MAX_WAIT_MINUTES:
        return None
    return Wait(kind=kind, min_minutes=low, max_minutes=high, overnight=overnight)


def active_time(total: int | None, waits: Iterable[Wait]) -> int | None:
    """A page's total time without the waits it counts (M1, F124: "745 min" is 25 min and a night
    of marinating). The longest waits come off if the total is big enough to have held them,
    otherwise the shortest; if it held neither the total is left alone (nothing is guessed), and
    so is a total that would be left with nothing."""
    if total is None:
        return None
    waits = list(waits)
    for take in (sum(w.max_minutes for w in waits), sum(w.min_minutes for w in waits)):
        if take and total - take >= 1:
            return total - take
    return total
