"""Why an item is on the list (Plan shopping, S3; cabledrawer 6 Nov).

Worked out each time the list is read, from the plan (`shop_from_plan.work_out`), so nothing
is stored: the planned recipes that need the ingredient and their days ("Sambar (Tue) ·
Rasam (Thu)"), "Added by you" for a typed item, "120 g needed" first when the pack bought is
bigger than the need, and, on a plan item, "no pack size" when none is known. The words are
made here so screens show them as they are.
"""

from datetime import date
from typing import cast

from mealwright.api.v1.context import Kitchen
from mealwright.api.v1.schemas import PackLineOut
from mealwright.foods import PackReads, other_names, pack_bought, sizes
from mealwright.models import Food, ListItem
from mealwright.pack_sizes import CountedAs, suggest_sizes
from mealwright.pack_sizes import table as pack_table

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
SEP = " · "


def recipes_text(uses: dict[str, set[date]]) -> str:
    """ "Sambar (Tue, Thu) · Rasam (Fri)": recipes in the order of their first day."""
    first = sorted(uses.items(), key=lambda pair: (min(pair[1]), pair[0].casefold()))
    return SEP.join(
        f"{name} ({', '.join(DAYS[d.weekday()] for d in sorted(days))})" for name, days in first
    )


def _pack_bigger(
    kitchen: Kitchen,
    food: Food,
    item: ListItem,
    pack: PackLineOut | None,
    reads: PackReads | None = None,
) -> bool:
    """Is the pack to buy bigger than what is needed? (A pack line with a size and spare.)"""
    if pack is None or pack.packs is None or item.amount_milli is None:
        return False
    usual = pack_bought(kitchen, food.id, reads)
    return usual is not None and pack.packs * usual.amount_milli > item.amount_milli


def why_text(
    kitchen: Kitchen,
    item: ListItem,
    food: Food,
    pack: PackLineOut | None,
    uses: dict[int, dict[str, set[date]]],
    reads: PackReads | None = None,
) -> str:
    """`reads`: the list's sizes and names, read once (a caller with many lines passes it)."""
    parts: list[str] = []
    if _pack_bigger(kitchen, food, item, pack, reads) and pack is not None:
        parts.append(pack.need)
    if item.source == "plan":
        found = uses.get(food.id)
        parts.append(recipes_text(found) if found else "From the plan")
    else:
        parts.append("Added by you")
    if item.source == "plan" and pack is not None and pack.packs is None:
        parts.append("no pack size")
    return SEP.join(parts)


def tiny_need(
    kitchen: Kitchen, food: Food, need_milli: int | None, reads: PackReads | None = None
) -> bool:
    """Offer "Make it a staple?" (cabledrawer 7 Nov): a best-before ingredient (its pack-size table
    row says "best before"; no row, or "use by", never) whose need is under a twentieth of its
    smallest known pack (the household's sizes and the table's, in the need's unit)."""
    if food.staple or need_milli is None or need_milli <= 0:
        return False
    others = reads.names(food.id) if reads is not None else other_names(kitchen, food.id)
    names = [food.name, *(n.name for n in others)]
    row = pack_table().match(*names)
    if row is None or row.dates != "best before":
        return False
    own = reads.sizes(food.id) if reads is not None else sizes(kitchen, food.id)
    known = [s.amount_milli for s in own if s.amount_milli > 0]
    # The table matched, so these are its own sizes (never the generic ones).
    known += [
        p.amount_milli
        for p in suggest_sizes(names, cast(CountedAs, food.counted_as), food.table_key)
    ]
    return bool(known) and need_milli * 20 < min(known)
