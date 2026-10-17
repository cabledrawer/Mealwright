"""Recent changes and Undo (docs/dev/api-0.2.md 6.5; spec section 6, "History and undo")."""

from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import select

from mealwright.api.v1.context import Here, Kitchen
from mealwright.api.v1.foods import FoodOut, food_out
from mealwright.api.v1.schemas import ChangeOut
from mealwright.auth import SameOrigin
from mealwright.errors import Problem, not_found
from mealwright.foods import change_out
from mealwright.history import (
    UNDO_MESSAGES,
    Tally,
    UndoResult,
    already_undone,
    commit,
    record,
    replayed,
    too_old,
    undo_foods,
    undo_merge_record,
    undo_until,
)
from mealwright.models import Change, Food, utcnow

router = APIRouter(tags=["history"], dependencies=[SameOrigin])

# Changes to stock, shown in Pantry → Recent changes (the stock kinds arrive with stock).
STOCK_KINDS = ("added", "used", "binned", "set_left", "moved", "to_freezer", "use_by")


class ChangeLine(BaseModel):
    """One stock lot touched by a change (filled in once stock arrives)."""

    food_id: int
    lot_id: int | None


class ChangeItem(ChangeOut):
    lines: list[ChangeLine]


class ChangeList(BaseModel):
    changes: list[ChangeItem]
    next: str | None


@router.get("/changes")
def list_changes(
    kitchen: Here,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    before: int | None = None,
    food_id: int | None = None,
    area: Literal["pantry"] | None = None,
    mine: bool = False,
) -> ChangeList:
    """Newest first. `area=pantry`: stock changes only. `mine=true&limit=1`: what Ctrl+Z
    undoes (the web app skips it while the cursor is in a text box)."""
    query = select(Change).where(Change.household_id == kitchen.household_id)
    if before is not None:
        query = query.where(Change.id < before)
    if food_id is not None:
        query = query.where(Change.food_id == food_id)
    if area == "pantry":
        query = query.where(Change.kind.in_(STOCK_KINDS))
    if mine:
        query = query.where(Change.login_id == kitchen.login.id, Change.kind != "undo")
    rows = list(kitchen.db.scalars(query.order_by(Change.id.desc()).limit(limit + 1)))
    page = rows[:limit]
    items = [ChangeItem(**change_out(kitchen, c).model_dump(), lines=[]) for c in page]
    return ChangeList(changes=items, next=str(page[-1].id) if len(rows) > limit and page else None)


class UndoOut(BaseModel):
    result: UndoResult
    message: str
    change: ChangeOut  # the Undo itself
    undone: ChangeOut  # the change that was undone
    food: FoodOut | None
    groups: list[Any]  # pantry groups touched (filled in once stock arrives)


def _undo_out(kitchen: Kitchen, undo: Change) -> UndoOut:
    original = kitchen.db.get(Change, undo.undoes_change_id or 0)
    if original is None:  # pragma: no cover (an undo always points at its change)
        raise not_found("That change")
    result: UndoResult = (undo.undo_data or {}).get("result", "done")
    food = None
    if original.food_id is not None:
        found = kitchen.db.get(Food, original.food_id)
        if found is not None and found.removed_at is None and found.merged_into_id is None:
            food = food_out(kitchen, found)
    return UndoOut(
        result=result,
        message=UNDO_MESSAGES[result],
        change=change_out(kitchen, undo),
        undone=change_out(kitchen, original),
        food=food,
        groups=[],
    )


@router.post("/changes/{change_id}/undo")
def undo(change_id: int, kitchen: Here, response: Response) -> UndoOut:
    """Reverse just that change; later changes stay. Anyone in the household can undo
    anyone's change within the undo window (7 days)."""
    earlier = replayed(kitchen)
    if earlier is None:
        change = kitchen.db.get(Change, change_id)
        if change is None or change.household_id != kitchen.household_id:
            raise not_found("That change")
        if change.kind == "undo":
            raise Problem(
                status.HTTP_409_CONFLICT, "cannot_undo", "An Undo can't itself be undone."
            )
        if change.undone_by_change_id is not None:
            raise already_undone()
        if utcnow() >= undo_until(kitchen, change):
            raise too_old()
        tally = Tally()
        data = change.undo_data or {}
        if data.get("foods"):
            undo_foods(kitchen, data["foods"], tally)
        if tally.done:
            undo_merge_record(kitchen, data)
        result = tally.result
        undo_change = record(
            kitchen,
            "undo",
            f"Undid: {change.summary}",
            change.food_id,
            {"result": result},
        )
        undo_change.undoes_change_id = change.id
        change.undone_by_change_id = undo_change.id
        earlier = commit(kitchen)
        if earlier is None:
            return _undo_out(kitchen, undo_change)
    if earlier.kind != "undo":
        raise Problem(
            status.HTTP_409_CONFLICT,
            "key_reused",
            "That change ID was already used for something else.",
        )
    response.headers["Idempotent-Replayed"] = "true"
    return _undo_out(kitchen, earlier)
