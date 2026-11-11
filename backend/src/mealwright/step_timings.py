"""What a method step needs for Batch cook (Experimental; 0.8 wave 6, B1; cabledrawer 28 Oct and
11 Nov): whether the cook's hands are busy or the step waits, roughly how many minutes, and what
equipment it uses (a hob ring, a pressure cooker, the oven, or nothing).

Each of the three is **guessed from the step's words** unless a person set it by hand, and the
screens say which ("guessed" or "set by you"). Guesses are made when a step is read, never
stored: a step's words changing, or this module getting better, changes the guess, while a value
set by hand is kept as it is (the three columns `recipe_step.timing_*`; empty means guessed).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from mealwright import step_waits
from mealwright.models import RecipeStep

Hands = Literal["hands", "waiting"]
Equipment = Literal["hob", "pressure", "oven", "none"]
HANDS = ("hands", "waiting")
EQUIPMENT = ("hob", "pressure", "oven", "none")
MAX_MINUTES = step_waits.MAX_WAIT_MINUTES  # ten days, as a wait
PER_WHISTLE = 5  # a pressure cooker's whistle is about five minutes of cooking

# What a step does, by its words. Whole words only, any case.
_PRESSURE = re.compile(
    r"\bpressure[- ]cook|\bwhistles?\b|\binstant pot\b|\bpressure cooker\b", re.I
)
_OVEN = re.compile(r"\bbak(?:e|ing)\b|\boven\b|\bpreheat\b|\broast(?:ing)?\b", re.I)
# "dry roast the cumin in a pan" is a hob job, not the oven.
_PAN_ROAST = re.compile(
    r"\b(?:dry[- ])?roast\b[^.]{0,60}\b(?:pan|kadai|skillet|wok|tawa)\b|\bdry[- ]roast", re.I
)
_HOB_HANDS = re.compile(
    r"\bfr(?:y|ying)\b|\bsaut[eé](?:ing)?\b|\btemper(?:ing)?\b|\bsplutter|\bsizzle|\bstir[- ]fry"
    r"|\btoast\b|\bsear\b|\bbrown\b",
    re.I,
)
_HOB_WAIT = re.compile(r"\bsimmer(?:ing)?\b|\bboil(?:ing)?\b|\bstew\b|\bsteam(?:ing)?\b", re.I)
# Heat, a kadai or the stove is the hob even with "add" beside it ("Heat oil and add the onions");
# "cook" on its own words, too ("Add the tomatoes and cook until soft"; B1 review r1 M2). Not
# "pan": a loaf pan that chills or a cake cooling in its pan uses no hob ring (r2 M1).
_HOB_ALWAYS = re.compile(
    r"\bheat\b|\bstove\b|\bhob\b|\bkadai\b|\bkadhai\b|\btawa\b|\bskillet\b|\bwok\b"
    r"|\bcook\b",
    re.I,
)
# "cooking" is often a noun ("the cooking liquid"): the hob only when nothing hands-on is said.
_HOB_OTHER = re.compile(r"\bcooking\b", re.I)
_HANDS_ON = re.compile(
    r"\bchop(?:ping)?\b|\bgrind(?:ing)?\b|\bblend\b|\bmix(?:ing)?\b|\bknead(?:ing)?\b"
    r"|\bslice\b|\bdice\b|\bmince\b|\bgrate\b|\bpeel\b|\bwash\b|\bwhisk\b|\bshape\b|\broll\b"
    r"|\bgarnish\b|\bserve\b|\bstir\b|\badd\b|\bcombine\b",
    re.I,
)
_WAIT_WORDS = re.compile(
    r"\bsoak(?:ing)?\b|\bmarinat(?:e|ing)\b|\brest(?:ing)?\b|\bferment|\bchill(?:s|ed|ing)?\b|\brefrigerat"
    r"|\bprov(?:e|ing)\b|\bproof\b|\bsteep|\bcool(?:ing)?\b|\blet (?:it|them) (?:stand|sit|rest)"
    r"|\bset aside for\b",
    re.I,
)
_NOT_REST = re.compile(r"\bthe\s+rest\b|\brest\s+of\b", re.I)
_WHISTLES = re.compile(r"\b(\d{1,2})\s*(?:to\s*\d{1,2}\s*)?whistles?\b", re.I)
_HOURS_MINUTES = re.compile(
    r"(\d{1,3})\s*(?:h(?:ou)?rs?|h)\s*(?:and\s*)?(\d{1,2})\s*(?:mins?|minutes?)\b", re.I
)
_NUMBER = r"\d{1,4}(?:\.\d{1,2})?"
_UNIT = r"(?:h(?:ou)?rs?|hours?|h|mins?|minutes?)\b"
_TIME = re.compile(
    rf"(?P<a>{_NUMBER})\s*(?P<au>{_UNIT})?(?:\s*(?:-|–|—|to)\s*(?P<b>{_NUMBER})\s*(?P<bu>{_UNIT}))?",  # noqa: RUF001
    re.I,
)
_SPACES = re.compile(r"\s+")
_LONGEST_TEXT = 1_500  # how much of a step's words are read (a step's limit is 5000)

# A rough default per kind when the step names no time.
_DEFAULT_MINUTES = {"pressure": 20, "oven": 30, "hob_wait": 15, "hob_hands": 5, "hands": 5}


@dataclass(frozen=True)
class Guess:
    hands: Hands
    minutes: int
    equipment: Equipment


@dataclass(frozen=True)
class Timing:
    """A step's timing as shown: each value, and whether it is still a guess."""

    hands: Hands
    minutes: int
    equipment: Equipment
    hands_guessed: bool
    minutes_guessed: bool
    equipment_guessed: bool


def _unit_minutes(number: str, unit: str | None) -> float:
    if unit is None:
        return 0.0
    per = 1 if unit.lower().startswith("m") else 60
    return float(number) * per


def times_in(text: str) -> int | None:
    """The minutes a step's own words give, added together ("fry 2 minutes, then simmer 10
    minutes" is 12; "10-15 minutes" is 15, the longer end so nothing is planned too early), or
    None when it names no time."""
    text = _HOURS_MINUTES.sub(lambda m: f"{int(m[1]) * 60 + int(m[2])} minutes", text)
    total = 0.0
    for found in _TIME.finditer(text):
        unit = found.group("bu") or found.group("au")
        if unit is None:
            continue  # "2 onions"
        total += _unit_minutes(found.group("b") or found.group("a"), unit)
    minutes = round(total)
    return minutes if minutes > 0 else None


def guess(text: str, wait: step_waits.Wait | None = None) -> Guess:
    """The guess for one step's words (and its M1 wait, which counts as waiting)."""
    text = _SPACES.sub(" ", text[:_LONGEST_TEXT]).strip()
    pan_roast = _PAN_ROAST.search(text) is not None
    if _PRESSURE.search(text):
        equipment: Equipment = "pressure"
    elif _OVEN.search(text) and not pan_roast:
        equipment = "oven"
    elif (
        _HOB_HANDS.search(text)
        or _HOB_WAIT.search(text)
        or pan_roast
        or _HOB_ALWAYS.search(text)
        or (_HOB_OTHER.search(text) and not _HANDS_ON.search(text))
    ):
        equipment = "hob"
    else:
        equipment = "none"

    rest_word = _WAIT_WORDS.search(text)
    if rest_word and rest_word.group(0).lower().startswith("rest") and _NOT_REST.search(text):
        rest_word = None
    if wait is not None or equipment in ("pressure", "oven"):
        hands: Hands = "waiting"
        kind = "pressure" if equipment == "pressure" else "oven" if equipment == "oven" else "wait"
    elif _HOB_HANDS.search(text) and not _HOB_WAIT.search(text):
        hands, kind = "hands", "hob_hands"
    elif _HOB_WAIT.search(text) or rest_word:
        hands, kind = "waiting", "hob_wait"
    else:
        hands, kind = "hands", "hands"

    named = times_in(text)
    whistles = _WHISTLES.search(text)
    if wait is not None:
        minutes = (
            step_waits.OVERNIGHT_MINUTES if wait.overnight else wait.max_minutes
        )  # the wait is already in minutes
    elif named is not None:
        minutes = named
    elif whistles:
        minutes = int(whistles.group(1)) * PER_WHISTLE
    else:
        minutes = _DEFAULT_MINUTES.get(kind, _DEFAULT_MINUTES["hob_wait"])
    return Guess(hands=hands, minutes=min(max(1, minutes), MAX_MINUTES), equipment=equipment)


def of_step(step: RecipeStep) -> Timing | None:
    """The step's timing: the guess, with anything set by hand put over it. None for a heading."""
    if step.kind != "step":
        return None
    guessed = guess(step.text, step_waits.of_step(step))
    hands = step.timing_hands if step.timing_hands in HANDS else None
    equipment = step.timing_equipment if step.timing_equipment in EQUIPMENT else None
    minutes = step.timing_minutes
    return Timing(
        hands=hands or guessed.hands,  # type: ignore[arg-type]
        minutes=minutes if minutes is not None else guessed.minutes,
        equipment=equipment or guessed.equipment,  # type: ignore[arg-type]
        hands_guessed=hands is None,
        minutes_guessed=minutes is None,
        equipment_guessed=equipment is None,
    )
