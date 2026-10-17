"""Recent changes and Undo (docs/dev/api-0.2.md 6.5; spec section 6, "History and undo")."""

from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import aliased

from mealwright.amounts import count_text, exact_text
from mealwright.api.v1.context import Here, Kitchen
from mealwright.api.v1.foods import FoodOut, food_out
from mealwright.api.v1.pantry import GroupOut, Pantry
from mealwright.api.v1.schemas import AmountOut, ChangeOut, Ref
from mealwright.auth import SameOrigin
from mealwright.errors import Problem, not_found
from mealwright.foods import amount_out, change_out
from mealwright.history import (
    UNDO_MESSAGES,
    Shortfall,
    Tally,
    UndoResult,
    already_undone,
    as_utc,
    commit,
    record,
    replayed,
    too_old,
    undo_foods,
    undo_lines,
    undo_lot_amounts,
    undo_merge_record,
    undo_until,
)
from mealwright.models import Change, ChangeLine, Food, StockLot, utcnow

router = APIRouter(tags=["history"], dependencies=[SameOrigin])

# Changes to stock, shown in Pantry → Recent changes.
STOCK_KINDS = ("added", "used", "binned", "set_left", "moved", "to_freezer", "use_by")


class LineOut(BaseModel):
    """One stock lot touched by a change: before → after."""

    food: Ref
    lot_id: int | None
    before: AmountOut
    after: AmountOut
    place_before: Ref | None
    place_after: Ref | None
    use_by_before: date | None
    use_by_after: date | None


class TotalOut(BaseModel):
    """One ingredient in one place: the packets this change touched, added up and worded
    as sold ("Paneer: 0 g → 2 packs · 400 g")."""

    food_id: int
    name: str
    place_before: Ref | None  # null for packets the change added
    place_after: Ref | None
    before: AmountOut
    after: AmountOut


class ChangeItem(ChangeOut):
    totals: list[TotalOut]  # for Recent changes: one entry per ingredient and place
    lines: list[LineOut]  # each packet, for detail


class ChangeList(BaseModel):
    changes: list[ChangeItem]
    next: str | None


def _totals(kitchen: Kitchen, view: Pantry, change: Change) -> list[TotalOut]:
    sums: dict[tuple[int, int | None, int | None], list[int]] = {}
    for line in kitchen.db.scalars(
        select(ChangeLine).where(ChangeLine.change_id == change.id).order_by(ChangeLine.id)
    ):
        key = (line.food_id, line.place_before_id, line.place_after_id)
        entry = sums.setdefault(key, [0, 0])
        entry[0] += line.amount_before_milli
        entry[1] += line.amount_after_milli

    def place(place_id: int | None) -> Ref | None:
        found = view.places.get(place_id) if place_id is not None else None
        return Ref(id=found.id, name=found.name) if found is not None else None

    result = []
    for (food_id, before_id, after_id), (before, after) in sums.items():
        food = view.food(food_id)
        usual = view.usual(food_id)
        result.append(
            TotalOut(
                food_id=food.id,
                name=food.name,
                place_before=place(before_id),
                place_after=place(after_id),
                before=amount_out(food, before, usual),
                after=amount_out(food, after, usual),
            )
        )
    return result


def _lines(kitchen: Kitchen, view: Pantry, change: Change) -> list[LineOut]:
    result = []
    for line in kitchen.db.scalars(
        select(ChangeLine).where(ChangeLine.change_id == change.id).order_by(ChangeLine.id)
    ):
        food = view.food(line.food_id)
        lot = kitchen.db.get(StockLot, line.lot_id) if line.lot_id is not None else None
        size = view.lot_size(lot) if lot is not None else view.usual(food.id)

        def place(place_id: int | None) -> Ref | None:
            found = view.places.get(place_id) if place_id is not None else None
            return Ref(id=found.id, name=found.name) if found is not None else None

        result.append(
            LineOut(
                food=Ref(id=food.id, name=food.name),
                lot_id=line.lot_id,
                before=amount_out(food, line.amount_before_milli, size),
                after=amount_out(food, line.amount_after_milli, size),
                place_before=place(line.place_before_id),
                place_after=place(line.place_after_id),
                use_by_before=line.use_by_before,
                use_by_after=line.use_by_after,
            )
        )
    return result


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
        undone = aliased(Change)
        stock_undos = select(undone.id).where(undone.kind.in_(STOCK_KINDS))
        query = query.where(
            Change.kind.in_(STOCK_KINDS)
            | ((Change.kind == "undo") & Change.undoes_change_id.in_(stock_undos))
        )
    if mine:
        query = query.where(Change.login_id == kitchen.login.id, Change.kind != "undo")
    rows = list(kitchen.db.scalars(query.order_by(Change.id.desc()).limit(limit + 1)))
    page = rows[:limit]
    view = Pantry(kitchen)
    items = [
        ChangeItem(
            **change_out(kitchen, c).model_dump(),
            totals=_totals(kitchen, view, c),
            lines=_lines(kitchen, view, c),
        )
        for c in page
    ]
    return ChangeList(changes=items, next=str(page[-1].id) if len(rows) > limit and page else None)


class UndoOut(BaseModel):
    result: UndoResult
    message: str
    change: ChangeOut  # the Undo itself
    undone: ChangeOut  # the change that was undone
    food: FoodOut | None
    groups: list[GroupOut]  # the pantry groups touched, as they are now


def _plain(food: Food, milli: int) -> str:
    if food.counted_as == "count":
        return count_text(milli, None, None).removesuffix(" left")
    return exact_text(milli, food.counted_as)  # type: ignore[arg-type]


def _message(kitchen: Kitchen, result: UndoResult, short: list[Shortfall]) -> str:
    if result != "done" and len(short) == 1:
        food = kitchen.db.get(Food, short[0].food_id)
        if food is not None:
            applied, wanted = _plain(food, short[0].applied), _plain(food, short[0].wanted)
            if short[0].applied:
                return f"Took back {applied} of the {wanted}: the rest has been used since."
            return f"Nothing to take back: the {wanted} has all been used since."
    return UNDO_MESSAGES[result]


def _undo_out(kitchen: Kitchen, undo: Change) -> UndoOut:
    original = kitchen.db.get(Change, undo.undoes_change_id or 0)
    if original is None:  # pragma: no cover (an undo always points at its change)
        raise not_found("That change")
    data = undo.undo_data or {}
    result: UndoResult = data.get("result", "done")
    food = None
    if original.food_id is not None:
        found = kitchen.db.get(Food, original.food_id)
        if found is not None and found.removed_at is None and found.merged_into_id is None:
            food = food_out(kitchen, found)
    pairs: set[tuple[int, int]] = set()
    for line in kitchen.db.scalars(select(ChangeLine).where(ChangeLine.change_id == original.id)):
        for place_id in (line.place_before_id, line.place_after_id):
            if place_id is not None:
                pairs.add((line.food_id, place_id))
    return UndoOut(
        result=result,
        message=data.get("message", UNDO_MESSAGES[result]),
        change=change_out(kitchen, undo),
        undone=change_out(kitchen, original),
        food=food,
        groups=Pantry(kitchen).groups_for(pairs),
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
        # Each lot as it was before the Undo, so the Undo gets its own lines.
        touched: dict[int, tuple[StockLot, int, int, date | None]] = {}
        for line in kitchen.db.scalars(select(ChangeLine).where(ChangeLine.change_id == change.id)):
            lot = kitchen.db.get(StockLot, line.lot_id) if line.lot_id is not None else None
            if lot is not None and lot.id not in touched:
                touched[lot.id] = (lot, lot.amount_milli, lot.place_id, lot.use_by)
        short = undo_lines(kitchen, change, tally)
        if data.get("foods"):
            undo_foods(kitchen, data["foods"], tally)
        if data.get("lot_amounts"):
            undo_lot_amounts(kitchen, data["lot_amounts"])
        if tally.done:
            undo_merge_record(kitchen, data)
        result = tally.result
        undo_change = record(
            kitchen,
            "undo",
            f"Undid: {change.summary}",
            change.food_id,
            {
                "result": result,
                "message": _message(kitchen, result, short),
                # Thinning totals the Undo with the change it undid: same kind, same month.
                "undoes_kind": change.kind,
                "undoes_at": as_utc(change.at).isoformat(),
            },
        )
        undo_change.undoes_change_id = change.id
        # What the Undo actually did to each lot (a partial undo: only what it put back),
        # for Recent changes and so the monthly totals net out.
        for lot, amount, place_id, use_by in touched.values():
            if (lot.amount_milli, lot.place_id, lot.use_by) != (amount, place_id, use_by):
                kitchen.db.add(
                    ChangeLine(
                        household_id=kitchen.household_id,
                        change_id=undo_change.id,
                        food_id=lot.food_id,
                        lot_id=lot.id,
                        amount_before_milli=amount,
                        amount_after_milli=lot.amount_milli,
                        place_before_id=place_id,
                        place_after_id=lot.place_id,
                        use_by_before=use_by,
                        use_by_after=lot.use_by,
                    )
                )
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
