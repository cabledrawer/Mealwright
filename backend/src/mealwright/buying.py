"""What to buy in whole packs, and the line that says so (F120; cabledrawer 31 Oct and 7 Nov).

A shopping line's amount is what the plan needs. With a Usual size known, the line says how
many whole packs buy that: "1 jar (500 g) · 120 g needed". With none, it says the need and
that no pack size is known yet ("60 g needed · no pack size yet"), and the common sizes from
the bundled table are offered as "Usual pack?" quick picks. Display only: the amount stored
on the line stays the need.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import cast

from mealwright import amounts
from mealwright.amounts import NBSP, CountedAs, exact_text
from mealwright.models import Food, FoodSize


@dataclass(frozen=True)
class PackLine:
    packs: int | None  # whole packs to buy; None with no Usual size known
    size_id: int | None
    buy: str | None  # "1 jar (500 g)", "2 tins (400 ml)"
    need: str  # "120 g needed"
    line: str  # "1 jar (500 g) · 120 g needed", "60 g needed · no pack size yet"


def whole_packs(need_milli: int, size_milli: int) -> int:
    """The fewest whole packs that hold the need (at least one for any need)."""
    return max(1, -(-need_milli // size_milli))


def _amount(food: Food, milli: int) -> str:
    if food.counted_as == "count":
        return amounts.count_text(milli, food.count_word, food.count_word_plural).removesuffix(
            f"{NBSP}left"
        )
    return exact_text(milli, cast(CountedAs, food.counted_as))


def pack_line(food: Food, need_milli: int | None, usual: FoodSize | None) -> PackLine | None:
    """The pack wording for one list line, or None when there is nothing to say: no amount,
    or a counted ingredient with no size (five onions need no pack)."""
    if need_milli is None or need_milli <= 0 or food.staple:
        return None
    need = f"{_amount(food, need_milli)} needed"
    if usual is None or usual.amount_milli <= 0:
        if food.counted_as == "count":
            return None
        return PackLine(None, None, None, need, f"{need} · no pack size yet")
    packs = whole_packs(need_milli, usual.amount_milli)
    word = usual.name if packs == 1 else usual.plural
    buy = f"{packs}{NBSP}{word} ({_amount(food, usual.amount_milli)})"
    return PackLine(packs, usual.id, buy, need, f"{buy} · {need}")


# --- Another size (F183 + F204, cabledrawer 8 and 9 Nov) -------------------------------------------

# "When another size would leave much less over it is suggested" (cabledrawer 9 Nov). How much is
# "much less" is the builder's, proposed, for cabledrawer: the other size leaves at most half as much
# over as the usual one and saves at least a tenth of what is needed, and it is no more than
# MOST_PACKS packs (ten small sachets are not a better way to buy).
MUCH_LESS_RATIO = 2  # the other size's leftover times 2 is at most the usual size's
MUCH_LESS_OF_NEED = 10  # and the saving times 10 is at least the need
MOST_PACKS = 6


@dataclass(frozen=True)
class Choice:
    """One way to buy the need: this many of this size."""

    size_id: int | None  # None: a common size from the table, not made yet
    name: str
    plural: str
    size_milli: int
    packs: int
    over_milli: int  # what is left over once the packs are bought


def choice_for(size_id: int | None, name: str, plural: str, size_milli: int, need: int) -> Choice:
    packs = whole_packs(need, size_milli)
    return Choice(size_id, name, plural, size_milli, packs, packs * size_milli - need)


def better_choice(usual: Choice, others: list[Choice]) -> Choice | None:
    """The other size to suggest under the row, or None: the one leaving the least over (then
    the fewest packs), when that is much less than the usual size leaves."""
    if usual.over_milli <= 0:
        return None
    best: Choice | None = None
    for other in others:
        if other.size_milli == usual.size_milli or other.packs > MOST_PACKS:
            continue
        if other.over_milli * MUCH_LESS_RATIO > usual.over_milli:
            continue
        need = usual.packs * usual.size_milli - usual.over_milli
        if (usual.over_milli - other.over_milli) * MUCH_LESS_OF_NEED < need:
            continue
        if best is None or (other.over_milli, other.packs) < (best.over_milli, best.packs):
            best = other
    return best


def size_words(food: Food, choice: Choice) -> str:
    """ "3 tins · 200 ml" (the number and the word with a no-break space, as the list's own)."""
    word = choice.name if choice.packs == 1 else choice.plural
    return f"{choice.packs}{NBSP}{word} · {_amount(food, choice.size_milli)}"


def over_words(food: Food, choice: Choice) -> str:
    """ "nothing left over", "200 ml left over"."""
    if choice.over_milli <= 0:
        return "nothing left over"
    return f"{_amount(food, choice.over_milli)} left over"


def need_words(food: Food, need_milli: int) -> str:
    """ "600 ml needed"."""
    return f"{_amount(food, need_milli)} needed"
