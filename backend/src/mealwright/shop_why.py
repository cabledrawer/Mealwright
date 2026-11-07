"""Why an item is on the list (Plan shopping, S3; cabledrawer 6 Nov).

Worked out each time the list is read, from the plan (`shop_from_plan.work_out`), so nothing
is stored: the planned recipes that need the ingredient and their days ("Sambar (Tue) ·
Rasam (Thu)"), "Added by you" for a typed item, "120 g needed" first when the pack bought is
bigger than the need, and, on a plan item, "no pack size" when none is known. The words are made here so
screens show them as they are.
"""

from datetime import date

from mealwright.api.v1.context import Kitchen
from mealwright.api.v1.schemas import PackLineOut
from mealwright.foods import pack_bought
from mealwright.models import Food, ListItem

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
SEP = " · "


def recipes_text(uses: dict[str, set[date]]) -> str:
    """ "Sambar (Tue, Thu) · Rasam (Fri)": recipes in the order of their first day."""
    first = sorted(uses.items(), key=lambda pair: (min(pair[1]), pair[0].casefold()))
    return SEP.join(
        f"{name} ({', '.join(DAYS[d.weekday()] for d in sorted(days))})" for name, days in first
    )


def _pack_bigger(kitchen: Kitchen, food: Food, item: ListItem, pack: PackLineOut | None) -> bool:
    """Is the pack to buy bigger than what is needed? (A pack line with a size and spare.)"""
    if pack is None or pack.packs is None or item.amount_milli is None:
        return False
    usual = pack_bought(kitchen, food.id)
    return usual is not None and pack.packs * usual.amount_milli > item.amount_milli


def why_text(
    kitchen: Kitchen,
    item: ListItem,
    food: Food,
    pack: PackLineOut | None,
    uses: dict[int, dict[str, set[date]]],
) -> str:
    parts: list[str] = []
    if _pack_bigger(kitchen, food, item, pack) and pack is not None:
        parts.append(pack.need)
    if item.source == "plan":
        found = uses.get(food.id)
        parts.append(recipes_text(found) if found else "From the plan")
    else:
        parts.append("Added by you")
    if item.source == "plan" and pack is not None and pack.packs is None:
        parts.append("no pack size")
    return SEP.join(parts)
