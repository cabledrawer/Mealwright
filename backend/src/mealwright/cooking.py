""" "Cooked it" takes the ingredients out of the pantry (0.7 K2; spec section 2, "Cooking — how
deduction works", points 5 and 7).

The review is the screen's (K3). Here are the two calls behind it: `preview_*` (the engine's
proposal, nothing changes) and `cook_*` (a confirmed set of choices): one change in Recent
changes (kind `cooked`) with a line for each packet touched, so one Undo puts it all back, and
the cooked record with the recipe as cooked and each row as it was confirmed (`cooked.py`).

- A meal item (one recipe in a meal) and a batch cook each have their own record. A second
  confirm for either is refused, never doubled (the record is unique). The item that a batch
  cook was made from is cooked through the batch (rule 7: ingredients are taken once, on the cook
  day; the tubs were made when the batch was planned, and eating a tub uses the tub).
- Undo reverses the packets (the ordinary Undo of a change) and takes the record away, so the
  item or batch can be cooked again (`forget_record`).
- This does not change the meal's status or make leftover tubs: that is Today's answer, which the
  screen calls too (K3).

Proposed, for cabledrawer (one rule each): a batch cook is worked out for the cook-day eaters plus a
portion for each tub, as Cook once and the shopping list do (F58); a meal that is `cooked` already
(answered on Today before this existed) can still be given its record, one that was skipped or
moved can't.
"""

import uuid
from dataclasses import dataclass
from typing import Any

from fastapi import status
from sqlalchemy import or_, select

from mealwright import cooked, plan
from mealwright.amounts import checked, to_milli
from mealwright.api.v1.context import Kitchen
from mealwright.api.v1.schemas import Answer
from mealwright.batches import batches_cooked_at, cook_batches_of, cook_item_of
from mealwright.deduction import (
    Choice,
    Pool,
    Row,
    Worked,
    offer_as_previewed,
    settle_meal,
    work_out,
)
from mealwright.errors import Problem, not_found
from mealwright.foods import find, find_size, remember_answers
from mealwright.history import Tally, as_utc
from mealwright.household import today
from mealwright.models import (
    BatchCook,
    Change,
    CookedRecord,
    Food,
    FoodSize,
    ListItem,
    Meal,
    MealItem,
    Recipe,
)
from mealwright.names import fold
from mealwright.shop_from_plan import PLAN_KIND, base_amount, round_up
from mealwright.shopping import Batch, ensure_main_list, payload_hash, server_action, tombstone
from mealwright.stock import StockEdit

MOST_PORTIONS = 999


def _already(kitchen: Kitchen, record: CookedRecord) -> Problem:
    day = today(kitchen.household, as_utc(record.cooked_at))
    return Problem(
        status.HTTP_409_CONFLICT,
        "already_cooked",
        f"This was already cooked on {day:%a} {day.day} {day:%b}. Undo “Cooked it” first.",
    )  # proposed, for cabledrawer


def _recipe(kitchen: Kitchen, recipe_id: int | None) -> Recipe:
    recipe = kitchen.db.get(Recipe, recipe_id) if recipe_id is not None else None
    if recipe is None or recipe.household_id != kitchen.household_id or recipe.removed_at:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "not_a_recipe",
            "Only a recipe that is still there can be cooked.",  # proposed, for cabledrawer
        )
    return recipe


def _item_checked(kitchen: Kitchen, item: MealItem) -> tuple[Recipe, Meal]:
    """The recipe of a meal item that can be cooked now."""
    meal = kitchen.db.get(Meal, item.meal_id)
    if meal is None:  # pragma: no cover (the database keeps every item in a meal)
        raise not_found("That meal")
    if meal.status != "cooked":
        plan._planned(meal)  # skipped and moved meals are locked
    recipe = _recipe(kitchen, item.recipe_id) if item.kind == "recipe" else None
    if recipe is None:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "not_a_recipe",
            "Only a recipe that is still there can be cooked.",
        )
    record = cooked.for_meal_item(kitchen.db, kitchen.household_id, item.id)
    if record is not None:
        raise _already(kitchen, record)
    if _batch_of_item(kitchen, item) is not None:
        raise Problem(
            status.HTTP_409_CONFLICT,
            "cook_the_batch",
            "This meal is cooked once for several. Cook the batch instead.",  # proposed
        )
    return recipe, meal


def _batch_of_item(kitchen: Kitchen, item: MealItem) -> BatchCook | None:
    """The batch this item is the cooking of (the first copy of the recipe in its cook meal)."""
    meal = kitchen.db.get(Meal, item.meal_id)
    found = cook_batches_of(kitchen, item, meal) if meal is not None else []
    return found[0] if found else None


def _batch_checked(kitchen: Kitchen, batch: BatchCook) -> Recipe:
    recipe = _recipe(kitchen, batch.recipe_id)
    record = cooked.for_batch(kitchen.db, kitchen.household_id, batch.id)
    if record is not None:
        raise _already(kitchen, record)
    return recipe


def item_portions(item: MealItem, recipe: Recipe) -> int:
    return item.servings or recipe.serves or 1


def batch_portions(kitchen: Kitchen, batch: BatchCook, recipe: Recipe) -> int:
    """The cook-day eaters (the meal's servings, else one) plus a portion for each tub."""
    item = cook_item_of(kitchen, batch)
    eaters = (item.servings if item else None) or 1
    return min(eaters + batch.tub_count, MOST_PORTIONS)


# --- What is to be cooked -----------------------------------------------------------------------


@dataclass
class Entry:
    """One recipe to cook: its portions, the person's choices, and what it is linked to."""

    recipe: Recipe
    portions: int
    choices: dict[str, Choice]
    link: dict[str, int]


def item_entry(
    kitchen: Kitchen, item: MealItem, portions: int | None, choices: dict[str, Choice]
) -> Entry:
    recipe, _ = _item_checked(kitchen, item)
    return Entry(
        recipe,
        portions or item_portions(item, recipe),
        choices,
        {"meal_item_id": item.id, "meal_id": item.meal_id, "item_id": item.id},
    )


def batch_entry(
    kitchen: Kitchen, batch: BatchCook, portions: int | None, choices: dict[str, Choice]
) -> Entry:
    recipe = _batch_checked(kitchen, batch)
    return Entry(
        recipe, portions or batch_portions(kitchen, batch, recipe), choices, {"batch_id": batch.id}
    )


def meal_entries(
    kitchen: Kitchen,
    meal: Meal,
    wanted: dict[int, tuple[int | None, dict[str, Choice]]] | None,
) -> list[Entry]:
    """The recipes of a meal to cook together: every recipe in it, or only the `wanted` items
    (item id -> portions and choices). A tub or a plain ingredient has nothing to take."""
    if meal.status not in ("planned", "cooked"):
        plan._planned(meal)
    items = [i for i in plan.items_of(kitchen, meal) if i.kind == "recipe"]
    if wanted is not None:
        by_id = {i.id: i for i in items}
        for item_id in wanted:
            if item_id not in by_id:
                raise not_found("That item")
        items = [i for i in items if i.id in wanted]
    if not items:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "nothing_to_cook",
            "There’s no recipe in this meal to cook.",  # proposed, for cabledrawer
        )
    return [
        item_entry(kitchen, i, *(wanted[i.id] if wanted is not None else (None, {}))) for i in items
    ]


# --- The proposal, nothing changes --------------------------------------------------------------


def preview(kitchen: Kitchen, entries: list[Entry], answers: list[Answer]) -> list[Worked]:
    """One proposal for each recipe, from one pool of packets: two recipes of a meal never
    both propose the same grams."""
    pool = Pool(kitchen)
    found = [work_out(kitchen, e.recipe, e.portions, answers, None, pool) for e in entries]
    settle_meal(found)
    return found


# --- Confirming -----------------------------------------------------------------------------------


def choices_of(worked: Worked) -> list[cooked.SnapshotChoice]:
    return [_choice_of(row) for row in worked.rows]


def _remember(
    kitchen: Kitchen, worked: list[Worked], answers: list[Answer]
) -> list[dict[str, Any]]:
    """Save the answers. Only here may a size answer replace a size, and only the size the review
    asked about (the word in a row's "2 cloves" note, F89): every other answer keeps the rule
    that an existing size is never changed. What was replaced is returned, for the Undo."""
    asked = {
        (row.food.id, fold(row.count_note[1]))
        for each in worked
        for row in each.rows
        if row.food is not None and row.count_note is not None
    }
    plain: list[Answer] = []
    replaced: list[dict[str, Any]] = []
    for answer in answers:
        if (
            answer.kind == "size"
            and answer.name is not None
            and answer.amount is not None
            and (answer.food_id, fold(answer.name)) in asked
        ):
            found = find_size(kitchen, find(kitchen, answer.food_id), answer.name)
            milli = checked(to_milli(answer.amount))
            if found is not None:
                if found.amount_milli != milli:
                    replaced.append({"id": found.id, "was": found.amount_milli, "now": milli})
                    found.amount_milli = milli
                continue
        plain.append(answer)
    remember_answers(kitchen, plain)
    return replaced


def _choice_of(row: Row) -> cooked.SnapshotChoice:
    return cooked.SnapshotChoice(
        key=row.key,
        status=row.status,
        line_ids=[line.id for line in row.lines],
        food_id=row.food.id if row.food else None,
        food_name=row.food.name if row.food else None,
        recipe_id=row.inner.id if row.inner else None,
        recipe_name=row.inner.name if row.inner else None,
        use=row.use if row.food is not None and row.status != "staple" else False,
        needed_milli=row.needed,
        entered=row.entered,
        entered_milli=row.entered_milli,
        from_freezer=row.from_freezer,
        used_milli=row.taken,
        short_milli=row.short,
        add_to_list=row.add_to_list,
        running_low=row.running_low,
        bought=row.bought,
        takes=[
            cooked.SnapshotTake(
                food_id=take.food.id,
                food_name=take.food.name,
                stand_in=take.stand_in,
                amount_milli=take.amount,
            )
            for take in row.takes
        ],
    )


def _summary(entries: list[Entry]) -> str:
    if len(entries) == 1:
        e = entries[0]
        return (
            f"Cooked {e.recipe.name} ({e.portions} {'portion' if e.portions == 1 else 'portions'})"
        )
    names = [e.recipe.name for e in entries]
    return f"Cooked {', '.join(names[:-1])} and {names[-1]}"


def confirm(kitchen: Kitchen, entries: list[Entry], answers: list[Answer]) -> Change:
    """Take what the choices say from the packets, in one change for every recipe given (all or
    nothing: a refusal comes before anything is written), and write a record for each."""
    pool = Pool(kitchen)
    worked = [work_out(kitchen, e.recipe, e.portions, answers, e.choices, pool) for e in entries]
    # The Use-off rows take the preview's offers first, so settling the meal sees the shortfalls
    # the preview showed for them, not their own unworked ones.
    offer_as_previewed(
        kitchen, [(e.recipe, e.portions, e.choices) for e in entries], worked, answers
    )
    settle_meal(worked)
    replaced = _remember(kitchen, worked, answers)
    edit = StockEdit(kitchen)
    for each in worked:
        for row in each.rows:
            for take in row.takes:
                for lot, amount in take.lots:
                    edit.touch(lot).amount_milli -= amount
    change = edit.record("cooked", _summary(entries), None)
    listed, action_id = _add_to_list(kitchen, [row for each in worked for row in each.rows], change)
    ids: list[int] = []
    for entry, each in zip(entries, worked, strict=True):
        snapshot = cooked.snapshot(kitchen.db, entry.recipe)
        snapshot.choices = choices_of(each)
        record = CookedRecord(
            household_id=kitchen.household_id,
            meal_item_id=entry.link.get("meal_item_id"),
            batch_id=entry.link.get("batch_id"),
            recipe_id=entry.recipe.id,
            portions=entry.portions,
            snapshot=cooked.stored(snapshot),
            change_id=change.id,
            cooked_by_login_id=kitchen.login.id,
            cooked_by_name=kitchen.login.name,
        )
        kitchen.db.add(record)
        kitchen.db.flush()
        ids.append(record.id)
    data: dict[str, Any] = {"cooked_record_id": ids[0], "cooked_record_ids": ids, "listed": listed}
    if replaced:
        data["sizes"] = replaced  # Undo puts the old amounts back
    if action_id:
        data["action"] = action_id  # so the Undo's sync-log row can say what it undoes (5.8)
    if len(entries) == 1:
        data.update(entries[0].link)
    else:
        data["meal_id"] = entries[0].link.get("meal_id")
    change.undo_data = data
    kitchen.db.flush()
    return change


def _open_line(kitchen: Kitchen, list_id: str, food_id: int) -> ListItem | None:
    return kitchen.db.scalar(
        select(ListItem).where(
            ListItem.household_id == kitchen.household_id,
            ListItem.list_id == list_id,
            ListItem.food_id == food_id,
            ListItem.deleted_at.is_(None),
            ListItem.merged_into_id.is_(None),
            ListItem.ticked_at.is_(None),
            ListItem.amount_milli.is_not(None),
        )
    )


def _add_to_list(
    kitchen: Kitchen, rows: list[Row], change: Change
) -> tuple[list[dict[str, Any]], str | None]:
    """What the rows offered to put on the shopping list, where it was ticked (cabledrawer 31 Oct:
    "Confirm adds it to the shopping list"): onto the ingredient's open line when that is too
    small, else a new line, counted up whole. Each ingredient once, whatever recipes need it.
    Returns what Undo needs: the line, whether it is new, how much was added, and the line as it
    was and the version this wrote, and the sync-log action that wrote it."""
    wanted: dict[int, list[Any]] = {}
    for row in rows:
        if row.add_to_list and row.food is not None and row.list_milli > 0:
            found = wanted.setdefault(row.food.id, [row.food, 0])
            found[1] += row.list_milli
    if not wanted:
        return [], None
    main = ensure_main_list(kitchen.db, kitchen.household_id)
    edits: list[tuple[Food, ListItem | None, int]] = []
    for food, milli in wanted.values():
        add = round_up(milli, food.counted_as)
        line = _open_line(kitchen, main.id, food.id)
        if line is None:
            edits.append((food, None, add))
        elif add > (line.amount_milli or 0):  # a line that already covers it is left alone
            edits.append((food, line, add - (line.amount_milli or 0)))
    if not edits:
        return [], None
    batch = Batch(kitchen, action=str(uuid.uuid4()))
    seq = batch.number()
    action = server_action(batch, PLAN_KIND, {}, change, list_id=main.id)
    made: list[dict[str, Any]] = []
    created: list[str] = []
    changed: list[list[Any]] = []
    for food, line, more in edits:
        if line is not None:
            was = {
                "amount": line.amount_milli,
                "size_id": line.size_id,
                "hand_edited": line.hand_edited,
                "version": line.version,
            }
            line.amount_milli = (line.amount_milli or 0) + more
            line.size_id, line.hand_edited, line.version = None, True, seq
            changed.append([line.id, base_amount(was["amount"]), base_amount(line.amount_milli)])
            made.append({"id": line.id, "new": False, "added": more, "was": was, "seq": seq})
            continue
        item = ListItem(
            id=str(uuid.uuid4()),
            household_id=kitchen.household_id,
            list_id=main.id,
            food_id=food.id,
            shop_id=food.shop_id,
            amount_milli=more,
            source="typed",
            hand_edited=True,
            added_by_login_id=kitchen.login.id,
            added_by_name=kitchen.login.name,
            version=seq,
        )
        kitchen.db.add(item)
        created.append(item.id)
        made.append({"id": item.id, "new": True, "added": more, "was": None, "seq": seq})
    # The shape the sync log already has for a list change the server makes (sync protocol 5.8).
    payload: dict[str, Any] = {"created": created, "changed": changed, "removed": []}
    action.payload, action.payload_hash, action.result = payload, payload_hash(payload), payload
    batch.finish()
    kitchen.db.flush()
    return made, action.id


def undo_list(kitchen: Kitchen, change: Change, tally: Tally, batch: Batch) -> None:
    """Undo of "Cooked it" takes back what it put on the list, but only a line nobody has
    changed since (same version, not ticked, merged or removed); any other is left as it is and
    the Undo says "partly". The Undo's own sync-log row is written by the caller (it holds the
    counter number taken here)."""
    listed = (change.undo_data or {}).get("listed") or []
    stand = []
    for each in listed:
        item = kitchen.db.get(ListItem, each["id"])
        if (
            item is None
            or item.household_id != kitchen.household_id
            or item.deleted_at is not None
            or item.merged_into_id is not None
            or item.ticked_at is not None
            or item.version != each["seq"]
        ):
            tally.skipped += 1
        else:
            stand.append((item, each))
    if not stand:
        return
    seq = batch.number()
    for item, each in stand:
        if each["new"]:
            tombstone(kitchen, item, seq, batch.action)
        else:
            was = each["was"]
            item.amount_milli, item.size_id = was["amount"], was["size_id"]
            item.hand_edited, item.version = was["hand_edited"], seq
        tally.done += 1
    kitchen.db.flush()


def undo_sizes(kitchen: Kitchen, change: Change, tally: Tally) -> None:
    """Undo of "Cooked it": a size the cook replaced goes back to its old amount, but only if
    nothing has changed it since: an older cook's Undo leaves a size that a later cook changed,
    and the Undo says "partly" with the reason. (Proposed, for cabledrawer.)"""
    for each in (change.undo_data or {}).get("sizes") or []:
        size = kitchen.db.get(FoodSize, each["id"])
        if size is None or size.household_id != kitchen.household_id:
            continue
        if size.amount_milli == each["now"]:
            size.amount_milli = each["was"]
            tally.done += 1
        else:
            tally.skipped += 1
            tally.sentence = (
                f"A later cook changed the size of a {size.name}, so it was left as it is."
            )
    kitchen.db.flush()


def meal_all_cooked(kitchen: Kitchen, meal: Meal) -> bool:
    """Has every recipe of the meal that can be cooked been cooked (F157)? A recipe is cooked
    by its own record, or, when it is the cooking of a Cook once batch, by the batch's. A recipe
    that was deleted (it can't be cooked), a tub, an ingredient and a note don't count. A meal
    with nothing to cook is cooked."""
    db, hid = kitchen.db, kitchen.household_id
    items = [i for i in plan.items_of(kitchen, meal) if i.kind == "recipe"]
    if not items:
        return True
    done_items = set(
        db.scalars(
            select(CookedRecord.meal_item_id).where(
                CookedRecord.household_id == hid,
                CookedRecord.meal_item_id.in_([i.id for i in items]),
            )
        )
    )
    for item in items:
        if item.id in done_items:
            continue
        recipe = db.get(Recipe, item.recipe_id) if item.recipe_id is not None else None
        if recipe is None or recipe.household_id != hid or recipe.removed_at:
            continue  # can't be cooked
        found = cook_batches_of(kitchen, item, meal)
        if not found or any(cooked.for_batch(db, hid, b.id) is None for b in found):
            return False
    return True


def _has_record(kitchen: Kitchen, meal: Meal) -> bool:
    db, hid = kitchen.db, kitchen.household_id
    ids = [i.id for i in plan.items_of(kitchen, meal)]
    batches = [b.id for b in batches_cooked_at(kitchen, meal)]
    return (
        db.scalar(
            select(CookedRecord.id)
            .where(
                CookedRecord.household_id == hid,
                or_(CookedRecord.meal_item_id.in_(ids), CookedRecord.batch_id.in_(batches)),
            )
            .limit(1)
        )
        is not None
    )


def forget_record(kitchen: Kitchen, change: Change) -> None:
    """Undo of "Cooked it": the records go, so the items or batch can be cooked again (even
    when the Undo was only partly done). A meal that was Cooked is no longer, as a recipe of it
    is not cooked any more (F157)."""
    db, hid = kitchen.db, kitchen.household_id
    meal_ids: set[int] = set()
    for record in db.scalars(
        select(CookedRecord).where(
            CookedRecord.household_id == hid, CookedRecord.change_id == change.id
        )
    ):
        if record.meal_item_id is not None:
            item = db.get(MealItem, record.meal_item_id)
            if item is not None:
                meal_ids.add(item.meal_id)
        elif record.batch_id is not None:
            batch = db.get(BatchCook, record.batch_id)
            if batch is not None and batch.cook_meal_id is not None:
                meal_ids.add(batch.cook_meal_id)
        db.delete(record)
    db.flush()
    for meal_id in meal_ids:
        meal = db.get(Meal, meal_id)
        if meal is None or meal.household_id != hid or meal.status != "cooked":
            continue
        # A meal cooked by its answer alone (no records) stays cooked; one that records say
        # was cooked in parts is not cooked any more.
        if _has_record(kitchen, meal) and not meal_all_cooked(kitchen, meal):
            meal.status = "planned"
    db.flush()
