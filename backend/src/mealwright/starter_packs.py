"""Starter ingredient packs (cabledrawer 18 Oct; rebuilt on the pack-size table, 7 Nov).

`data/starter-packs.csv` says which ingredients are in which of the seven packs; each row's
key is a row of `data/pack-sizes.csv`, which gives the ingredient's other names, usual pack
sizes and where it is bought. Bundled: nothing is downloaded. Adding a pack makes
ingredients only, never pantry stock or list items.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from functools import cache
from importlib.resources import files

from mealwright.conversions import TableRow
from mealwright.conversions import table as conversion_table
from mealwright.names import fold
from mealwright.pack_sizes import PackRow
from mealwright.pack_sizes import table as pack_table

# The packs in the order they are offered, as (id, name).
PACKS: tuple[tuple[str, str], ...] = (
    ("everyday-basics", "Everyday basics"),
    ("indian", "Indian"),
    ("chinese", "Chinese"),
    ("japanese", "Japanese"),
    ("middle-eastern", "Middle Eastern"),
    ("household", "Household"),
    ("baking", "Baking"),
)
HOUSEHOLD = "household"  # its items are staples ("Don't count it")


@dataclass(frozen=True)
class StarterItem:
    key: str  # the row of pack-sizes.csv
    name: str  # as the ingredient is called when added
    packs: tuple[str, ...]  # pack ids

    @property
    def staple(self) -> bool:
        return HOUSEHOLD in self.packs

    def pack_row(self) -> PackRow:
        return pack_table().rows[self.key]

    def other_names(self) -> list[str]:
        """The table's other names (South Indian and Tamil names included), without the
        ingredient's own name and without repeats."""
        seen = {fold(self.name)}
        out: list[str] = []
        row = self.pack_row()
        for name in (row.key.replace("_", " "), *row.names):
            if fold(name) not in seen:
                seen.add(fold(name))
                out.append(name)
        return out

    def conversion_row(self) -> TableRow | None:
        conversions = conversion_table()
        return conversions.rows.get(self.key) or conversions.match(self.name, *self.other_names())


@cache
def items() -> tuple[StarterItem, ...]:
    ids = {name: pack_id for pack_id, name in PACKS}
    source = files("mealwright") / "data" / "starter-packs.csv"
    with source.open(encoding="utf-8") as handle:
        lines = [line for line in handle if not line.startswith("#")]
    out: list[StarterItem] = []
    for record in csv.DictReader(lines):
        packs = tuple(ids[name] for name in record["packs"].split(";"))
        out.append(StarterItem(record["key"], record["name"], packs))
    return tuple(out)


def pack_items(pack_id: str) -> list[StarterItem]:
    """The items of one pack, in the file's order."""
    return [item for item in items() if pack_id in item.packs]


def pack_name(pack_id: str) -> str | None:
    return next((name for found, name in PACKS if found == pack_id), None)


def counted_as(item: StarterItem) -> str:
    """How the ingredient is counted: the conversion table's word, else the kind its first
    pack size is written in."""
    row = item.conversion_row()
    if row is not None:
        return row.counted_as
    sizes = item.pack_row().sizes
    return sizes[0].counted_as if sizes else "weight"
