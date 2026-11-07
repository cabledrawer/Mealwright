"""Recent changes and Undo (docs/dev/api-0.2.md 6.5; spec section 6, "History and undo")."""

from collections.abc import Callable
from datetime import date
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import aliased

from mealwright import cooking, drafts, plan, recipes, removals, shopping, together
from mealwright.amounts import NBSP, count_text, exact_text
from mealwright.api.v1.context import Here, Kitchen
from mealwright.api.v1.foods import FoodOut, food_out
from mealwright.api.v1.pantry import GroupOut, Pantry
from mealwright.api.v1.schemas import AmountOut, ChangeOut, Ref
from mealwright.auth import SameOrigin
from mealwright.errors import Problem, StoredInt, not_found
from mealwright.foods import amount_out, change_out
from mealwright.history import (
    JOINED_BOUGHT_MESSAGES,
    KEY_ONLY_KINDS,
    NOTE_KINDS,
    UNDO_MESSAGES,
    Shortfall,
    Tally,
    UndoResult,
    already_undone,
    as_utc,
    back_undone,
    commit,
    foods_in,
    record,
    record_back,
    removal_stands,
    replayed,
    too_old,
    undo_foods,
    undo_lines,
    undo_lot_amounts,
    undo_merge_record,
    undo_message,
    undo_until,
)
from mealwright.models import (
    Change,
    ChangeLine,
    Food,
    MealItem,
    Recipe,
    RecipeLine,
    StapleCheck,
    StockLot,
    utcnow,
)
from mealwright.stock import lots_of, place_totals

router = APIRouter(tags=["history"], dependencies=[SameOrigin])

# Changes to stock, shown in Pantry → Recent changes.
STOCK_KINDS = (
    "added",
    "used",
    "binned",
    "set_left",
    "moved",
    "to_freezer",
    "use_by",
    "shopped",
    "found",
    "repacked",
    "cooked",
    "stocktake",
)

# Changes to ingredients, shown in Ingredients → Recent changes.
INGREDIENT_KINDS = (
    "food_created",
    "food_edited",
    "food_removed",
    "food_back",
    "merged",
    "split",
    "recipe_imported",
)


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
    """One ingredient in one place: its whole amount there before and after the change,
    other packets included, worded as sold ("Paneer: 200 g · 1 pack → 400 g · 2 packs").
    Changes recorded before 0.2.1 only add up the packets they touched."""

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


def _lines_of(kitchen: Kitchen, changes: list[Change]) -> list[ChangeLine]:
    """The packet lines of these changes (one row of Recent changes), oldest change first."""
    return list(
        kitchen.db.scalars(
            select(ChangeLine)
            .where(ChangeLine.change_id.in_([c.id for c in changes]))
            .order_by(ChangeLine.change_id, ChangeLine.id)
        )
    )


def _totals(kitchen: Kitchen, view: Pantry, changes: list[Change]) -> list[TotalOut]:
    # Per ingredient and place pair: the packets touched added up (the old way, and still
    # how a move reads), and the whole-place amounts the change saved (0.2.1 onwards). A row
    # of more than one change (one "Cooked it", together.press) runs from the first change's
    # before to the last one's after.
    sums: dict[tuple[int, int | None, int | None], list[int]] = {}
    whole: dict[tuple[int, int | None, int | None], list[int] | None] = {}
    first_of: dict[tuple[int, int | None, int | None], int] = {}
    for line in _lines_of(kitchen, changes):
        key = (line.food_id, line.place_before_id, line.place_after_id)
        entry = sums.setdefault(key, [0, 0])
        entry[0] += line.amount_before_milli
        entry[1] += line.amount_after_milli
        saved = line.total_before_milli is not None and line.total_after_milli is not None
        stays = line.place_before_id is None or line.place_before_id == line.place_after_id
        if key not in whole:
            first_of[key] = line.change_id
            whole[key] = (
                [line.total_before_milli or 0, line.total_after_milli or 0]
                if saved and stays
                else None
            )
        elif line.change_id != first_of[key]:
            shown = whole[key]
            if shown is not None and saved and stays:
                shown[1] = line.total_after_milli or 0

    def place(place_id: int | None) -> Ref | None:
        found = view.places.get(place_id) if place_id is not None else None
        return Ref(id=found.id, name=found.name) if found is not None else None

    result = []
    for key, (before, after) in sums.items():
        food_id, before_id, after_id = key
        food = view.food(food_id)
        usual = view.usual(food_id)
        shown = whole[key]
        if shown is not None:
            before, after = shown
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


def _lines(kitchen: Kitchen, view: Pantry, changes: list[Change]) -> list[LineOut]:
    result = []
    rows = _lines_of(kitchen, changes)
    lot_ids = {line.lot_id for line in rows if line.lot_id is not None}
    # One query for all the packets, not one per line.
    lots = (
        {
            lot.id: lot
            for lot in kitchen.db.scalars(select(StockLot).where(StockLot.id.in_(lot_ids)))
        }
        if lot_ids
        else {}
    )
    for line in rows:
        food = view.food(line.food_id)
        lot = lots.get(line.lot_id) if line.lot_id is not None else None
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
    before: StoredInt | None = None,
    food_id: StoredInt | None = None,
    area: Literal["pantry", "ingredients"] | None = None,
    mine: bool = False,
) -> ChangeList:
    """Newest first. `area=pantry`: stock changes only. `area=ingredients`: changes to
    ingredients only (new, edited, removed, back, merged, split), with their Undos.
    `mine=true&limit=1`: what Ctrl+Z undoes (the web app skips it while the cursor is in a
    text box)."""
    query = select(Change).where(
        Change.household_id == kitchen.household_id, Change.kind.not_in(KEY_ONLY_KINDS)
    )
    if food_id is not None:
        query = query.where(Change.food_id == food_id)
    if area is not None:
        kinds = STOCK_KINDS if area == "pantry" else INGREDIENT_KINDS
        undone = aliased(Change)
        # The household test is repeated for the changes an Undo points at.
        of_area = select(undone.id).where(
            undone.household_id == kitchen.household_id, undone.kind.in_(kinds)
        )
        # An Undo that undid a line of the area along the way ("Lemon is back in
        # Ingredients", undone with the add that brought it back) is listed there too.
        undid_area = select(undone.undone_by_change_id).where(
            undone.household_id == kitchen.household_id,
            undone.kind.in_(kinds),
            undone.undone_by_change_id.is_not(None),
        )
        query = query.where(
            Change.kind.in_(kinds)
            | (
                (Change.kind == "undo")
                & (Change.undoes_change_id.in_(of_area) | Change.id.in_(undid_area))
            )
        )
    if mine:
        query = query.where(
            Change.login_id == kitchen.login.id,
            Change.kind != "undo",
            Change.kind.not_in(NOTE_KINDS),
        )
    whole = query  # every change this list could show, from any page: a press folds into its first
    if before is not None:
        query = query.where(Change.id < before)
    rows: list[Change] = []
    cursor: int | None = None
    while len(rows) <= limit:
        older = query if cursor is None else query.where(Change.id < cursor)
        chunk = list(kitchen.db.scalars(older.order_by(Change.id.desc()).limit(limit + 1)))
        folded = set() if mine else _folded(kitchen, whole, chunk)
        rows += [c for c in chunk if c.id not in folded]
        if len(chunk) <= limit:
            break
        cursor = chunk[-1].id
    page = rows[:limit]
    view = Pantry(kitchen)
    items = []
    for c in page:
        shown = _row_of(kitchen, c) if not mine else [c]
        items.append(
            ChangeItem(
                **change_out(kitchen, c).model_dump(),
                totals=_totals(kitchen, view, shown),
                lines=_lines(kitchen, view, shown),
            )
        )
    return ChangeList(changes=items, next=str(page[-1].id) if len(rows) > limit and page else None)


def _row_of(kitchen: Kitchen, change: Change) -> list[Change]:
    """The changes one row of Recent changes adds up: a "Cooked it" press's pantry changes, or,
    for the Undo of its first, the Undos of all of them (review 2, M), oldest first."""
    if change.kind != "undo" or change.undoes_change_id is None:
        return together.press(kitchen, change)
    undone = kitchen.db.get(Change, change.undoes_change_id)
    if undone is None or undone.household_id != kitchen.household_id:
        return [change]
    members = together.press(kitchen, undone)
    if members[0].id != undone.id:
        return [change]
    found = {change.id: change}
    for member in members:
        if member.undone_by_change_id is None:
            continue
        undo = kitchen.db.get(Change, member.undone_by_change_id)
        if undo is not None and undo.household_id == kitchen.household_id:
            found[undo.id] = undo
    return sorted(found.values(), key=lambda c: c.id)


def _folded(kitchen: Kitchen, query: Any, chunk: list[Change]) -> set[int]:
    """Which of these changes are not rows of their own. One "Cooked it" is one row with one Undo
    (F125, review 1, L1): a later pantry change of the same press, or the Undo of one, is shown in
    the row of the press's first, when this list has that one too. The whole chunk is worked out
    in a few queries, not a few per change (0.7 security review, L1: a press of 21 parts)."""
    db = kitchen.db
    undone_ids = {
        c.undoes_change_id for c in chunk if c.kind == "undo" and c.undoes_change_id is not None
    }
    undone = (
        {c.id: c for c in db.scalars(select(Change).where(Change.id.in_(undone_ids)))}
        if undone_ids
        else {}
    )
    targets: dict[int, Change] = {}  # a change's id → the change whose press decides its row
    for change in chunk:
        if change.kind != "undo" or change.undoes_change_id is None:
            targets[change.id] = change
            continue
        target = undone.get(change.undoes_change_id)
        if target is not None and target.household_id == kitchen.household_id:
            targets[change.id] = target
    wanted = {
        i
        for t in targets.values()
        if t.kind in ("cooked", "plan_cooked")
        for i in (t.undo_data or {}).get("together", [])
    }
    parts = (
        {
            c.id
            for c in db.scalars(
                select(Change).where(
                    Change.id.in_(wanted),
                    Change.household_id == kitchen.household_id,
                    Change.kind == "cooked",
                )
            )
        }
        if wanted
        else set()
    )
    first_of: dict[int, int] = {}  # a change's id → the first of its press
    for key, target in targets.items():
        together_ids = (
            (target.undo_data or {}).get("together", [])
            if target.kind in ("cooked", "plan_cooked")
            else []
        )
        first = min([target.id, *(i for i in together_ids if i in parts)])
        if first != target.id:
            first_of[key] = first
    if not first_of:
        return set()
    listed = set(
        db.scalars(query.with_only_columns(Change.id).where(Change.id.in_(set(first_of.values()))))
    )
    return {key for key, first in first_of.items() if first in listed}


class UndoOut(BaseModel):
    result: UndoResult
    message: str
    change: ChangeOut  # the Undo itself
    undone: ChangeOut  # the change that was undone
    food: FoodOut | None
    groups: list[GroupOut]  # the pantry groups touched, as they are now
    brought_back: list[Ref]  # removed ingredients this Undo returned to Ingredients
    recipe: Ref | None = None  # the recipe this Undo brought back (0.4)


def _plain(food: Food, milli: int) -> str:
    if food.counted_as == "count":
        return count_text(milli, None, None).removesuffix(f"{NBSP}left")
    return exact_text(milli, food.counted_as)  # type: ignore[arg-type]


def _message(
    kitchen: Kitchen,
    result: UndoResult,
    short: list[Shortfall],
    joined_bought: bool = False,
    thing: str | None = None,
) -> str:
    if joined_bought and result in JOINED_BOUGHT_MESSAGES:
        return JOINED_BOUGHT_MESSAGES[result]
    if result != "done" and len(short) == 1:
        food = kitchen.db.get(Food, short[0].food_id)
        if food is not None:
            applied, wanted = _plain(food, short[0].applied), _plain(food, short[0].wanted)
            if short[0].applied:
                return f"Took back {applied} of the {wanted}: the rest has been used since."
            return f"Nothing to take back: the {wanted} has all been used since."
    return undo_message(result, thing)


def _bring_back(
    kitchen: Kitchen, lots: list[StockLot], data: dict[str, object]
) -> tuple[str, list[int]]:
    """An Undo that puts stock back into an ingredient that has since been removed brings
    the ingredient back (otherwise the stock would be hidden, then deleted with it).
    Returns what to tell the person, and which ingredients came back."""
    moved = data.get("lot_amounts")
    if isinstance(moved, dict):
        lots = lots + [
            lot for key in moved if (lot := kitchen.db.get(StockLot, int(key))) is not None
        ]
    view = Pantry(kitchen)
    revived: list[Food] = []
    for lot in lots:
        if lot.amount_milli <= 0:
            continue
        food = kitchen.db.get(Food, lot.food_id)
        if food is not None and food.removed_at is not None and food not in revived:
            food.removed_at = None
            revived.append(food)
    kitchen.db.flush()
    for food in revived:
        record_back(kitchen, food)
    sentences = []
    for food in revived:
        stock = lots_of(kitchen, [food.id])
        total = sum(lot.amount_milli for lot in stock)
        places = sorted(
            {view.places[lot.place_id].name for lot in stock if lot.place_id in view.places}
        )
        where = places[0] if len(places) == 1 else "the pantry"
        amount = amount_out(food, total, view.usual(food.id)).short
        the = "the " if len(places) == 1 else ""
        sentences.append(f"{food.name} is back in Ingredients, with {amount} in {the}{where}.")
    return " ".join(sentences), [food.id for food in revived]


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
    recipe = None
    if data.get("recipe_id") is not None:
        back_recipe = kitchen.db.get(Recipe, data["recipe_id"])
        if back_recipe is not None and back_recipe.household_id == kitchen.household_id:
            recipe = Ref(id=back_recipe.id, name=back_recipe.name)
    revived = []
    for food_id in data.get("brought_back", []):
        back = kitchen.db.get(Food, food_id)
        if back is not None:
            revived.append(Ref(id=back.id, name=back.name))
    return UndoOut(
        brought_back=revived,
        recipe=recipe,
        result=result,
        message=data.get("message", UNDO_MESSAGES[result]),
        change=change_out(kitchen, undo),
        undone=change_out(kitchen, original),
        food=food,
        groups=Pantry(kitchen).groups_for(pairs),
    )


def in_use(kitchen: Kitchen, food_id: int) -> bool:
    """Is this ingredient used anywhere: a recipe line (or made ahead by a recipe), the plan,
    the shopping list, the pantry, or a staple someone has dealt with (cabledrawer 7 Nov)? A
    staple counts once it has been checked ("Got it") or restocked, not by being a staple."""
    db, home = kitchen.db, kitchen.household_id
    food = db.get(Food, food_id)
    if food is None or food.household_id != home:
        return False
    if food.restocked_at is not None or food.restock_typed_at is not None:
        return True
    if db.get(StapleCheck, food_id) is not None:
        return True
    if recipes.made_ahead_of(kitchen, food_id) is not None:
        return True
    if db.scalar(
        select(RecipeLine.id)
        .where(RecipeLine.household_id == home, RecipeLine.food_id == food_id)
        .limit(1)
    ):
        return True
    if db.scalar(
        select(MealItem.id)
        .where(MealItem.household_id == home, MealItem.food_id == food_id)
        .limit(1)
    ):
        return True
    return shopping.still_needed(kitchen, food_id)


def _keep_in_use(
    kitchen: Kitchen, change: Change, foods: dict[str, Any], tally: Tally
) -> frozenset[int]:
    """The Undo of a change that made ingredients (Add ingredient, a starter pack, or the
    ingredient made with a new shopping-list item) takes out only the ones not used anywhere;
    the rest stay, and the message says how many (cabledrawer 7 Nov: one rule for every Undo that
    would take out an ingredient)."""
    if change.kind != "food_created":
        return frozenset()
    kept = frozenset(
        int(key.split(":")[0])
        for key, (old, _new) in foods.get("fields", {}).items()
        if key.endswith(":exists") and old is None and in_use(kitchen, int(key.split(":")[0]))
    )
    if kept:
        tally.skipped += len(kept)
        count = len(kept)
        taken = (
            sum(
                1
                for key, (old, _new) in foods.get("fields", {}).items()
                if key.endswith(":exists") and old is None
            )
            - count
        )
        if taken:
            tally.message = (
                f"Took out what could be: {count} ingredient{'s are' if count > 1 else ' is'}"
                f" already in use, so {'they stay' if count > 1 else 'it stays'}."
            )
        else:
            tally.message = "Nothing to take out: these ingredients are already in use."
    return kept


def _still_needed(kitchen: Kitchen, change: Change, foods: dict[str, Any]) -> bool:
    """An `add` that brought its ingredient back (5.9): its Undo removes it again, but not
    while it has stock or is on a list (0.2's rule): then it stays."""
    return change.kind == "item_added" and any(
        shopping.still_needed(kitchen, food_id) for food_id in foods_in(foods)
    )


def undo_change(
    kitchen: Kitchen,
    change: Change,
    batch: shopping.Batch,
    action: str,
    *,
    summary: str | None = None,
    tick_id: str | None = None,
    extra: dict[str, object] | None = None,
) -> Change:
    """Reverse just that change (the checks are the caller's). Records and returns the
    `undo` change. `action` is the Undo's action ID; the household's lock is `batch`'s."""
    tally = Tally()
    data = change.undo_data or {}
    if change.kind == "recipe_imported":
        recipes.check_import_undo(kitchen, data)  # at 50 drafts: refused before anything is done
    if change.kind in removals.KINDS:
        removals.restore(kitchen, change, batch)  # the shop or place first: the rest points at it
    if data.get("shopping"):
        shopping.undo_shopping(kitchen, change, tally, batch, action)
    # Each lot as it was before the Undo, so the Undo gets its own lines.
    touched: dict[int, tuple[StockLot, int, int, date | None]] = {}
    start: dict[int, dict[int, int]] = {}
    for line in kitchen.db.scalars(select(ChangeLine).where(ChangeLine.change_id == change.id)):
        lot = kitchen.db.get(StockLot, line.lot_id) if line.lot_id is not None else None
        if lot is not None and lot.id not in touched:
            touched[lot.id] = (lot, lot.amount_milli, lot.place_id, lot.use_by)
            if lot.food_id not in start:
                start[lot.food_id] = place_totals(kitchen, lot.food_id)
    short = undo_lines(kitchen, change, tally)
    if data.get("listed"):
        cooking.undo_list(kitchen, change, tally, batch)
    if data.get("sizes"):
        cooking.undo_sizes(kitchen, change, tally)
    if data.get("foods") and not _still_needed(kitchen, change, data["foods"]):
        done_before = tally.done
        kept = _keep_in_use(kitchen, change, data["foods"], tally)
        touched_foods = undo_foods(kitchen, data["foods"], tally, kept)
        if tally.done > done_before:
            shopping.bump_foods(kitchen, touched_foods, batch)
    if data.get("lot_amounts"):
        undo_lot_amounts(kitchen, data["lot_amounts"])
    draft_back = None
    if change.kind == "recipe_imported":
        draft_back = recipes.undo_import(kitchen, data, tally)
        if "draft" in data:
            # The draft is back (or can't be): the Save's copy of it is no use now, so the
            # change keeps only the rest (it is undone, so nothing reads the copy again).
            change.undo_data = {key: value for key, value in data.items() if key != "draft"}
    if tally.done:
        undo_merge_record(kitchen, data)
    result = tally.result
    back, revived = _bring_back(kitchen, [lot for lot, *_ in touched.values()], data)
    named = kitchen.db.get(Food, change.food_id) if change.food_id is not None else None
    message = _message(kitchen, result, short, tally.joined_bought, named.name if named else None)
    if tally.message:
        message = tally.message
    if tally.sentence and result != "done":
        message = f"{message} {tally.sentence}"
    if back:
        message = back if result == "done" else f"{back} {message}"
    if draft_back:
        message = f"{message} {draft_back}"
    undo = record(
        kitchen,
        "undo",
        summary or f"Undid: {change.summary}",
        change.food_id,
        {
            "result": result,
            "message": message,
            # Ingredients this Undo brought back from Ingredients' removed list.
            "brought_back": revived,
            # Thinning totals the Undo with the change it undid: same kind, same month.
            "undoes_kind": change.kind,
            "undoes_at": as_utc(change.at).isoformat(),
            **(extra or {}),
        },
    )
    undo.undoes_change_id = change.id
    if tick_id is not None:
        undo.tick_id = tick_id
    # What the Undo actually did to each lot (a partial undo: only what it put back),
    # for Recent changes and so the monthly totals net out.
    end = {food: place_totals(kitchen, food) for food in start}
    for lot, amount, place_id, use_by in touched.values():
        if (lot.amount_milli, lot.place_id, lot.use_by) != (amount, place_id, use_by):
            kitchen.db.add(
                ChangeLine(
                    household_id=kitchen.household_id,
                    change_id=undo.id,
                    food_id=lot.food_id,
                    lot_id=lot.id,
                    amount_before_milli=amount,
                    amount_after_milli=lot.amount_milli,
                    place_before_id=place_id,
                    place_after_id=lot.place_id,
                    use_by_before=use_by,
                    use_by_after=lot.use_by,
                    total_before_milli=start[lot.food_id].get(place_id, 0),
                    total_after_milli=end[lot.food_id].get(lot.place_id, 0),
                )
            )
    kitchen.db.flush()
    change.undone_by_change_id = undo.id
    if data.get("foods"):
        back_undone(kitchen, data["foods"], undo.id)
    return undo


def undo_kind_refusal(change: Change) -> str | None:
    """The first checks of an Undo, whichever way it comes: `cannot_undo` for an Undo or a
    change that only keeps a request key, `already_undone`; None when nothing stands in the way."""
    if change.kind == "undo" or change.kind in KEY_ONLY_KINDS:
        return "cannot_undo"
    if change.undone_by_change_id is not None:
        return "already_undone"
    return None


def undo_standing_refusal(kitchen: Kitchen, change: Change) -> str | None:
    """`cannot_undo` for "Lemon is back in Ingredients", or a removal of Lemon that no longer
    stands. The HTTP Undo asks it after the window, the sync log in `undo_refusal`."""
    if change.kind in NOTE_KINDS or (
        change.kind == "food_removed" and not removal_stands(kitchen, change)
    ):
        return "cannot_undo"
    return None


def undo_refusal(kitchen: Kitchen, change: Change) -> str | None:
    """Why this change cannot be undone, the window apart (the sync log corrects the window for
    the phone's clock, so it asks for it itself)."""
    return undo_kind_refusal(change) or undo_standing_refusal(kitchen, change)


def undo_run(
    kitchen: Kitchen, change: Change, batch: shopping.Batch, stock: Callable[[], Change]
) -> Change:
    """Do the Undo, by the kind of change: one place for both ways in, so they cannot drift.
    `stock` is the caller's way of undoing a stock or list change. A change of one "Cooked it"
    takes the others back with it, newest first (F125, `together.py`); the answer is this
    change's own Undo, with the others' words when one of them was only partly done."""
    others = together.members(kitchen, change)
    if not others:
        return _undo_one(kitchen, change, stock)
    from mealwright.ticks import pantry_undo

    def other(member: Change) -> Change:
        # No key (it is the asked-for Undo's only), and its own stretch of list writing, so
        # its sync-log row says what it undoes.
        kept, kitchen.idempotency_key = kitchen.idempotency_key, None
        own_batch = shopping.Batch(kitchen)
        done = _undo_one(kitchen, member, lambda: pantry_undo(kitchen, member, own_batch))
        own_batch.finish()
        kitchen.idempotency_key = kept
        return done

    said = [other(member) for member in others if member.id > change.id]
    own = _undo_one(kitchen, change, stock)
    said += [other(member) for member in others if member.id < change.id]
    _say_for_all(own, said)
    return own


def _say_for_all(own: Change, others: list[Change]) -> None:
    """The one Undo's answer: its own words, unless it was all done and another of the same
    press was not (or brought an ingredient back): then those (the pantry's first)."""
    data = own.undo_data or {}
    if data.get("result", "done") != "done":
        return
    ranked = sorted(others, key=lambda u: (u.undo_data or {}).get("undoes_kind") != "cooked")
    for undo in ranked:
        theirs = undo.undo_data or {}
        if theirs.get("result", "done") != "done" or theirs.get("brought_back"):
            own.undo_data = {
                **data,
                "result": theirs.get("result", "done"),
                "message": theirs.get("message", data.get("message")),
                "brought_back": [*data.get("brought_back", []), *theirs.get("brought_back", [])],
            }
            return


def _undo_one(kitchen: Kitchen, change: Change, stock: Callable[[], Change]) -> Change:
    if change.kind == "recipe_removed":
        return recipes.undo_removal(kitchen, change)
    if change.kind == "draft_removed":
        return drafts.undo_removal(kitchen, change)
    if change.kind.startswith("plan_"):
        return plan.undo(kitchen, change)
    undone = stock()
    if change.kind == "cooked":
        cooking.forget_record(kitchen, change)  # so it can be cooked again
    return undone


@router.post("/changes/{change_id}/undo")
def undo(change_id: StoredInt, kitchen: Here, response: Response) -> UndoOut:
    """Reverse just that change; later changes stay. Anyone in the household can undo
    anyone's change within the undo window (7 days)."""
    earlier = replayed(kitchen)
    if earlier is None:
        # The household's lock first (sync protocol 5.2): an Undo can change lists too.
        batch = shopping.Batch(kitchen)
        change = kitchen.db.get(Change, change_id)
        if change is None or change.household_id != kitchen.household_id:
            raise not_found("That change")
        refused = undo_kind_refusal(change)
        if refused == "already_undone":
            raise already_undone()
        if refused is not None:
            message = (
                "An Undo can’t itself be undone."
                if change.kind == "undo"
                else "That can’t be undone."
            )
            raise Problem(status.HTTP_409_CONFLICT, refused, message)
        if utcnow() >= undo_until(kitchen, change):
            raise too_old()
        if undo_standing_refusal(kitchen, change) is not None:
            raise Problem(status.HTTP_409_CONFLICT, "cannot_undo", "That can’t be undone.")
        from mealwright.ticks import pantry_undo

        undone = undo_run(kitchen, change, batch, lambda: pantry_undo(kitchen, change, batch))
        batch.finish()
        earlier = commit(kitchen)
        if earlier is None:
            return _undo_out(kitchen, undone)
    if earlier.kind != "undo":
        raise Problem(
            status.HTTP_409_CONFLICT,
            "key_reused",
            "That change ID was already used for something else.",
        )
    response.headers["Idempotent-Replayed"] = "true"
    return _undo_out(kitchen, earlier)
