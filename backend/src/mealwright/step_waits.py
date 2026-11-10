"""Steps that wait (0.8 wave 5, M1; cabledrawer 31 Oct and 9 Nov).

A step can carry a wait: marinate, ferment, soak... as a range in whole minutes, or a range that
ends at "overnight". A recipe's time then shows its active time plus the wait. The wait is kept
in minutes (overnight counts as `OVERNIGHT_MINUTES`) so the plan can later work backwards from it.
"""

from __future__ import annotations

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
