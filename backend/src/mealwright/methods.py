"""A recipe's cooking methods (0.8 wave 5, M2; cabledrawer 31 Oct and 9 Nov).

A recipe has one method or two (never more: cabledrawer asked for "two cooking methods", and a
third would need a different switch on the recipe page, in Cook mode and in the plan's question).
Each has its own ingredient lines, steps and time. The first method is the recipe as it always
was. A line or step whose `method_id` is empty belongs to the first method, so code that doesn't
know about methods (and rows made without one) keeps working.

Every place that reads a recipe's lines or steps for one cooking asks this module which method:
the shopping list, Can cook now, Cooked it, the recipe page and Cook mode.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol

from sqlalchemy import Select, select
from sqlalchemy.orm import Session as DbSession

from mealwright.models import RecipeMethod

MAX_METHODS = 2


class InMethod(Protocol):
    method_id: Any


def methods_of(db: DbSession, recipe_id: int) -> list[RecipeMethod]:
    """The recipe's methods, first one first (none for a recipe made without any)."""
    return list(
        db.scalars(
            select(RecipeMethod)
            .where(RecipeMethod.recipe_id == recipe_id)
            .order_by(RecipeMethod.position)
        )
    )


def of_recipes(
    db: DbSession, recipe_ids: Iterable[int] | Select[Any]
) -> dict[int, list[RecipeMethod]]:
    found: dict[int, list[RecipeMethod]] = {}
    ids = recipe_ids if isinstance(recipe_ids, Select) else list(recipe_ids)
    if isinstance(ids, list) and not ids:
        return found
    for method in db.scalars(
        select(RecipeMethod)
        .where(RecipeMethod.recipe_id.in_(ids))
        .order_by(RecipeMethod.recipe_id, RecipeMethod.position)
    ):
        found.setdefault(method.recipe_id, []).append(method)
    return found


def used_last(methods: Sequence[RecipeMethod]) -> RecipeMethod | None:
    """The method planned or cooked most recently (the first when none was)."""
    if not methods:
        return None
    used = [m for m in methods if m.last_used_at is not None]
    if not used:
        return methods[0]
    return max(used, key=lambda m: (m.last_used_at or datetime.min, -m.position))


def named(methods: Sequence[RecipeMethod], method_id: int | None) -> RecipeMethod | None:
    """The method with this id, or the first when `method_id` is empty or isn't one of them."""
    for method in methods:
        if method.id == method_id:
            return method
    return methods[0] if methods else None


def in_method(row: InMethod, methods: Sequence[RecipeMethod], method: RecipeMethod | None) -> bool:
    """Does this line or step belong to `method`? With no methods at all, everything does."""
    if method is None or not methods:
        return True
    if row.method_id is None:
        return method.id == methods[0].id
    return bool(row.method_id == method.id)


def touch(method: RecipeMethod | None, now: datetime) -> None:
    """Remember the method was planned or cooked: it is pre-picked next time."""
    if method is not None:
        method.last_used_at = now


@dataclass
class Picks:
    """Which method counts for each recipe, for a sum over many recipes (the recipe list's Can
    cook now, the shopping list): `chosen` is a method id the caller asked for (a meal's pick);
    otherwise the one used last; otherwise the first. A recipe with no methods has no entry, and
    every line of it counts."""

    methods: dict[int, list[RecipeMethod]]
    chosen: dict[int, int | None] = field(default_factory=dict)

    def method_for(self, recipe_id: int) -> RecipeMethod | None:
        found = self.methods.get(recipe_id, [])
        if not found:
            return None
        wanted = self.chosen.get(recipe_id)
        if wanted is not None:
            for method in found:
                if method.id == wanted:
                    return method
            return found[0]
        if recipe_id in self.chosen:  # asked for, but empty: the first
            return found[0]
        return used_last(found)

    def keeps(self, recipe_id: int, method_id: int | None) -> bool:
        found = self.methods.get(recipe_id, [])
        method = self.method_for(recipe_id)
        if method is None or not found:
            return True
        if method_id is None:
            return method.id == found[0].id
        return method.id == method_id


def picks_for(
    db: DbSession,
    recipe_ids: Iterable[int],
    chosen: dict[int, int | None] | None = None,
    *,
    default: str = "last",
) -> Picks:
    """`default`: "last" (the one used last) or "first". A recipe used inside another always
    uses its first method."""
    found = of_recipes(db, recipe_ids)
    picks = Picks(found, dict(chosen or {}))
    if default == "first":
        for recipe_id in found:
            picks.chosen.setdefault(recipe_id, None)
    return picks
