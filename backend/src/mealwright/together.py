""" "Cooked it" is one press, one Undo (F125, cabledrawer 3 Nov: "Undo of "Cooked it" from Pantry →
Recent changes must also undo the meal's "Cooked" (one change, one Undo, as the toast does).").

One "Cooked it" records more than one change: the review's confirm takes from the pantry (kind
`cooked`, one for the meal's recipes and one for each batch cooked), then the meal's answer
follows (kind `plan_cooked`, with any tubs of "Any left over?"). Recent changes lists only the
pantry's, so the server keeps them together: each one's `undo_data["together"]` names them all,
and the Undo of any one of them takes back every one, newest first, whichever way it comes (Recent
changes, the toast, Ctrl+Z, the sync log). No new column: `undo_data` already holds what an Undo
needs.

They are joined when the meal's answer is recorded: the pantry changes are this login's own, for
this meal (its recipes, or a batch cooked for it), not undone, with nothing else of the login's in
between. An answer given first, or a cook with another change in between, stays on its own.

A tub that "Eat it on…" (F65) then puts on a meal follows the answer: it is the login's very next
change, for a tub the answer made. The Undo of "Cooked it" takes it off that meal first (the tub
can't go while it is in one); the Undo of the placing alone only takes it off.

A meal of a Cook once batch and an ordinary recipe records more than one pantry change in its one
press: Recent changes folds them into one row, the oldest's, so there is one Undo (`press`).
"""

from typing import Any

from sqlalchemy import func, select

from mealwright.api.v1.context import Kitchen
from mealwright.models import BatchCook, Change, CookedRecord, Meal, MealItem, Tub


def _with(change: Change, **extra: Any) -> None:
    # A new dict, so the JSON column is seen as changed.
    change.undo_data = {**(change.undo_data or {}), **extra}


def _cooked_for(kitchen: Kitchen, change: Change, meal: Meal) -> bool:
    """Is this pantry change the cooking of this meal (its recipes, or a batch cooked for it)?"""
    db = kitchen.db
    hid = kitchen.household_id
    for record in db.scalars(
        select(CookedRecord).where(
            CookedRecord.household_id == hid, CookedRecord.change_id == change.id
        )
    ):
        if record.meal_item_id is not None:
            item = db.get(MealItem, record.meal_item_id)
            if item is not None and item.household_id == hid and item.meal_id == meal.id:
                return True
        if record.batch_id is not None:
            batch = db.get(BatchCook, record.batch_id)
            if batch is not None and batch.household_id == hid and batch.cook_meal_id == meal.id:
                return True
    return False


def join_answer(kitchen: Kitchen, meal: Meal, answer: Change) -> None:
    """The meal's "Cooked it" answer, just recorded: join it to the pantry changes of the same
    press, if there are any."""
    db = kitchen.db
    mine = (Change.household_id == kitchen.household_id) & (Change.login_id == kitchen.login.id)
    before = db.scalar(
        select(func.max(Change.id)).where(mine, Change.kind != "cooked", Change.id < answer.id)
    )
    pantry = [
        change
        for change in db.scalars(
            select(Change)
            .where(
                mine,
                Change.kind == "cooked",
                Change.id < answer.id,
                Change.id > (before or 0),
                Change.undone_by_change_id.is_(None),
            )
            .order_by(Change.id)
        )
        if _cooked_for(kitchen, change, meal)
    ]
    if not pantry:
        return
    ids = [change.id for change in pantry] + [answer.id]
    for change in [*pantry, answer]:
        _with(change, together=ids)
    db.flush()


def follow(kitchen: Kitchen, tub: Tub, placed: Change) -> None:
    """A tub just put on a meal: if the login's change before it was the "Cooked it" answer that
    made this tub ("Eat it on…"), the answer's Undo takes this placing back too."""
    db = kitchen.db
    answer = db.scalars(
        select(Change)
        .where(
            Change.household_id == kitchen.household_id,
            Change.login_id == kitchen.login.id,
            Change.id < placed.id,
        )
        .order_by(Change.id.desc())
        .limit(1)
    ).first()
    if answer is None or answer.kind != "plan_cooked" or answer.undone_by_change_id is not None:
        return
    steps = (answer.undo_data or {}).get("plan", [])
    if not any(s.get("op") == "new_tub" and s.get("tub") == tub.id for s in steps):
        return
    _with(answer, followers=[*(answer.undo_data or {}).get("followers", []), placed.id])
    db.flush()


def members(kitchen: Kitchen, change: Change) -> list[Change]:
    """What the Undo of this change takes back with it, not undone yet, newest first (the change
    itself not included)."""
    db = kitchen.db
    ids = set((change.undo_data or {}).get("together", []))
    found = {change.id: change}
    for change_id in ids:
        other = db.get(Change, change_id)
        if other is not None and other.household_id == kitchen.household_id:
            found[other.id] = other
    for each in list(found.values()):
        if each.kind != "plan_cooked":
            continue
        for change_id in (each.undo_data or {}).get("followers", []):
            other = db.get(Change, change_id)
            if other is not None and other.household_id == kitchen.household_id:
                found[other.id] = other
    return sorted(
        (c for c in found.values() if c.id != change.id and c.undone_by_change_id is None),
        key=lambda c: c.id,
        reverse=True,
    )


def press(kitchen: Kitchen, change: Change) -> list[Change]:
    """The pantry changes (`cooked`) of the "Cooked it" press this one is part of, oldest first:
    one for the meal's recipes and one for each batch cooked (review 1, L1). Recent changes
    shows them as one row, the oldest's, with one Undo. Just this change when it is on its own."""
    if change.kind != "cooked":
        return [change]
    found = {change.id: change}
    for change_id in (change.undo_data or {}).get("together", []):
        other = kitchen.db.get(Change, change_id)
        if (
            other is not None
            and other.household_id == kitchen.household_id
            and other.kind == "cooked"
        ):
            found[other.id] = other
    return sorted(found.values(), key=lambda c: c.id)
