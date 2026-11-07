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
