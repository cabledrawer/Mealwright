"""The shopping list, built from the plan (0.6 PR 5).

cabledrawer's rules (BUILD-PLAN 0.6.0, spec "Shopping list" and "Offline shopping-list sync"):
plan minus stock minus staples, with "can use instead" stand-ins counted; plan-made items are
keyed by ingredient + shop, so working the list out again updates them instead of duplicating;
a hand edit beats the app's own sums; a staple is never put on the list but shown on the
"Check you have these" card. The look-ahead is always the household's `plan_ahead_days`
(cabledrawer, 24 Oct, answer 8: "7 days as default"; the list never asks).

What counts. The planned meals (status `planned`, in a slot that is switched on) from today for
`plan_ahead_days` days. A meal that is cooked, "Didn't" or moved, or sits in a switched-off slot,
counts for nothing, so it drops out of the list by itself.

The choices below are the builder's, **proposed, for cabledrawer**, each easy to change later (one
function each):

- Servings: a recipe item is worked out for its servings (its own "serves" when none was
  picked). A batch cook's cook meal is worked out for those servings plus one per tub: the
  people eating at the cook meal eat too, and the tubs are extra (`servings_for`; a Leftovers
  batch has one tub, so a meal for 4 buys for 5). Tubs and plain ingredients ("Fruit") need
  nothing bought: a tub is already made, and a plain ingredient has no amount.
- Inner recipes (a line that uses another recipe) add nothing, made ahead or not, as in the
  recipe stock hints (cabledrawer 20 Oct: "inner recipes are checked in a later version"). A
  made-ahead recipe is made, not bought.
- Stock: everything in the pantry counts, in every place, and stock past its use-by date still
  counts (the Pantry shows it; the person decides). A stand-in ("Can use instead")
  covers what the ingredient's own stock doesn't, if it is counted the same way (weight with
  weight, and so on); stock is shared out in order of ingredient, so one pack of red onions
  never covers two ingredients at once (`share_out`).
- Amounts that can't be compared (no amount, a pinch, "1 cup" of something with no known
  weight) are handled as the stock hints do (cabledrawer 19 Oct, Q22): if there is any stock of the
  ingredient it counts as enough; if there is none, the ingredient goes on the list with no
  amount, so it isn't forgotten (`unknown_need`).
- What is put on the list is rounded up: whole grams or millilitres, and halves for things
  counted by number (`round_up`).
- A typed item for the same ingredient and shop already on the list covers the need: no second
  line is made (a typed item is never touched, and typing one beside a plan line joins them, which
  counts as a hand edit).

Updating the list (`refresh`). Plan-made items (`source = plan`) are matched by (main list,
ingredient, shop = the ingredient's usual shop or Any shop).
- Only items that are not hand-edited and not ticked are changed (rule L-5, sync protocol 6).
- One live item per key. A second one, if ever there is one, is removed.
- An item whose need drops to nothing is removed with a tombstone and a version bump, so phones
  see it. A person's own removal of a plan item stays removed: it is not made again while the
  plan needs no more than it did, and within the last `plan_ahead_days` days (`removed_by_hand`).
  The plan's own removal doesn't block: if the need comes back, a new item is made.
- Every change takes one counter number from the household's list counter, stamps its items
  with it, and is written to the sync log as one `plan_update` action, so phones and live
  updates pick it up. It runs after each plan and batch write and each time Shopping opens, and
  does nothing (no number taken) when nothing would change.
"""

import math
import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from sqlalchemy import and_, or_, select

from mealwright.amounts import MILLI
from mealwright.api.v1.context import Kitchen
from mealwright.history import as_utc
from mealwright.household import today
from mealwright.models import (
    BatchCook,
    Food,
    FoodStandIn,
    ListItem,
    Meal,
    MealItem,
    MealSlot,
    Recipe,
    ShoppingList,
    StapleCheck,
    SyncAction,
    utcnow,
)
from mealwright.names import fold
from mealwright.recipe_list import Line, Stock, _foods, _lines, _scaled
from mealwright.recipes import live_recipes
from mealwright.shopping import Batch, ensure_main_list, payload_hash, server_action

PLAN_KIND = "plan_update"  # the sync-log kind of a plan-driven change
PLAN_NAME = "The plan"  # who made it, for "removed by …"


# --- What the plan needs -------------------------------------------------------------------------


@dataclass
class Need:
    """What the planned meals ask of one ingredient. `milli` adds up the amounts that could be
    compared with stock; `unknown` says some line couldn't be."""

    milli: int = 0
    unknown: bool = False


@dataclass
class ToBuy:
    food: Food
    amount_milli: int | None  # None: no amount


@dataclass
class Worked:
    days: int
    foods: dict[int, Food] = field(default_factory=dict)  # the household's shown ingredients
    to_buy: dict[int, ToBuy] = field(default_factory=dict)  # food id → what to buy
    # staple id → (names of the recipes that use it, ids of the meal items that use it)
    staples: dict[int, tuple[list[str], set[int]]] = field(default_factory=dict)


def base_amount(milli: int | None) -> int | float | None:
    """Thousandths → the base amount (g, ml or items) the sync log carries."""
    if milli is None:
        return None
    return milli // MILLI if milli % MILLI == 0 else milli / MILLI


def servings_for(item: MealItem, recipe: Recipe, batch_tubs: int | None) -> int | None:
    """How many servings a recipe item is worked out for: its own (else the recipe's "serves"),
    plus one per tub when it is a batch cook's cook meal. None when the recipe has no "serves"
    to scale from (amounts as written)."""
    base = item.servings or recipe.serves
    if base is None:
        return None
    return base + (batch_tubs or 0)


def round_up(milli: int, counted_as: str) -> int:
    """Whole grams or millilitres, or halves of an item, always upwards."""
    step = MILLI // 2 if counted_as == "count" else MILLI
    return math.ceil(milli / step) * step


def _stand_ins(kitchen: Kitchen) -> dict[int, list[int]]:
    found: dict[int, list[int]] = defaultdict(list)
    for link in kitchen.db.scalars(
        select(FoodStandIn).where(FoodStandIn.household_id == kitchen.household_id)
    ):
        found[link.food_id].append(link.stand_in_id)
    return {key: sorted(ids) for key, ids in found.items()}


def share_out(
    foods: dict[int, Food],
    needs: dict[int, Need],
    stock: Stock,
    stand_ins: dict[int, list[int]],
) -> dict[int, ToBuy]:
    """What to buy once stock (and stand-ins) are used. Ingredients are taken in order of id;
    each pack of stock is used once, whoever it covers."""
    pool: dict[int, int] = defaultdict(int, stock.total)
    out: dict[int, ToBuy] = {}
    for food_id in sorted(needs):
        food, need = foods[food_id], needs[food_id]
        short = need.milli
        used_any = pool[food_id] > 0
        own = min(pool[food_id], short)
        pool[food_id] -= own
        short -= own
        for other_id in stand_ins.get(food_id, ()):
            other = foods.get(other_id)
            if other is None:
                continue
            if pool[other_id] > 0:
                used_any = True
            if other.counted_as != food.counted_as:  # can't be added up
                continue
            take = min(pool[other_id], short)
            pool[other_id] -= take
            short -= take
        if need.milli > 0 and short > 0:
            out[food_id] = ToBuy(food, round_up(short, food.counted_as))
        elif need.milli == 0 and need.unknown and not used_any:
            out[food_id] = ToBuy(
                food, None
            )  # unknown_need: nothing in stock, say nothing of amount
    return out


def work_out(kitchen: Kitchen) -> Worked:
    """The sums, read-only: what to buy, and the staples the counted meals use."""
    db, hid, household = kitchen.db, kitchen.household_id, kitchen.household
    first = today(household)
    days = household.plan_ahead_days
    last = first + timedelta(days=days - 1)
    worked = Worked(days=days, foods=_foods(kitchen))

    rows = db.execute(
        select(MealItem, Meal.id)
        .join(Meal, and_(Meal.household_id == MealItem.household_id, Meal.id == MealItem.meal_id))
        .join(
            MealSlot, and_(MealSlot.household_id == Meal.household_id, MealSlot.id == Meal.slot_id)
        )
        .where(
            MealItem.household_id == hid,
            MealItem.kind == "recipe",
            MealItem.recipe_id.is_not(None),
            Meal.status == "planned",
            Meal.day >= first,
            Meal.day <= last,
            MealSlot.enabled.is_(True),
        )
        .order_by(MealItem.id)
    ).all()
    if not rows:
        return worked
    tubs: dict[tuple[int, int], int] = {}
    for meal_id, recipe_id, count in db.execute(
        select(BatchCook.cook_meal_id, BatchCook.recipe_id, BatchCook.tub_count).where(
            BatchCook.household_id == hid,
            BatchCook.cook_meal_id.is_not(None),
            BatchCook.recipe_id.is_not(None),
        )
    ):
        if meal_id is not None and recipe_id is not None:
            tubs[(meal_id, recipe_id)] = count
    recipes = live_recipes(kitchen)
    foods = worked.foods
    stock = Stock(kitchen, foods)
    lines: dict[int, list[Line]] = defaultdict(list)
    planned = {item.recipe_id for item, _ in rows if item.recipe_id in recipes}
    for line in _lines(kitchen, set(recipes), only=planned):
        lines[line.recipe_id].append(line)

    needs: dict[int, Need] = defaultdict(Need)
    staple_names: dict[int, set[str]] = defaultdict(set)
    staple_items: dict[int, list[int]] = defaultdict(list)
    for item, meal_id in rows:
        recipe: Recipe | None = recipes.get(item.recipe_id or 0)
        if recipe is None:  # removed, or its Undo window is over
            continue
        servings = servings_for(item, recipe, tubs.get((meal_id, recipe.id)))
        # One recipe's lines for one ingredient, added up, then scaled to the servings.
        per_food: dict[int, Need] = defaultdict(Need)
        for line in lines.get(recipe.id, ()):
            if line.food_id is None:  # an inner recipe, or an unlinked line
                continue
            food = foods.get(line.food_id)
            if food is None:
                continue
            if food.staple:
                staple_names[food.id].add(recipe.name)
                if item.id not in staple_items[food.id]:
                    staple_items[food.id].append(item.id)
                continue
            got = stock.need(line, food)
            if got is None:
                per_food[food.id].unknown = True
            else:
                per_food[food.id].milli += got
        for food_id, part in per_food.items():
            total = needs[food_id]
            total.milli += _scaled(part.milli, recipe, servings)
            total.unknown = total.unknown or part.unknown
    worked.to_buy = share_out(foods, needs, stock, _stand_ins(kitchen))
    for food_id, names in staple_names.items():
        worked.staples[food_id] = (sorted(names), set(staple_items[food_id]))
    return worked


# --- The main list -------------------------------------------------------------------------------


@dataclass
class Edits:
    """What an update would change."""

    create: list[ToBuy] = field(default_factory=list)
    change: list[tuple[ListItem, int | None]] = field(default_factory=list)
    remove: list[ListItem] = field(default_factory=list)

    def __bool__(self) -> bool:
        return bool(self.create or self.change or self.remove)


def _live(item: ListItem) -> bool:
    return item.deleted_at is None and item.merged_into_id is None


def removed_by_hand(kitchen: Kitchen, gone: ListItem, wanted: int | None) -> bool:
    """Did a person remove this plan item recently, for a need no bigger than this one? Then
    it stays removed (rule L-5). The plan's own removals don't count."""
    if gone.deleted_at is None:  # pragma: no cover (callers pass tombstones)
        return False
    days = kitchen.household.plan_ahead_days
    if as_utc(gone.deleted_at) < utcnow() - timedelta(days=days):
        return False
    action = (
        kitchen.db.get(SyncAction, (kitchen.household_id, gone.deleted_action_id))
        if gone.deleted_action_id
        else None
    )
    if action is not None and action.kind == PLAN_KIND:
        return False
    return (wanted or 0) <= (gone.amount_milli or 0)


def plan_edits(kitchen: Kitchen, main: ShoppingList, worked: Worked) -> Edits:
    """Compare what the plan needs with the main list's plan-made items. Read-only."""
    db = kitchen.db
    edits = Edits()
    items = list(
        db.scalars(
            select(ListItem)
            .where(
                ListItem.household_id == kitchen.household_id,
                or_(ListItem.list_id == main.id, ListItem.source == "plan"),
            )
            .order_by(ListItem.added_at, ListItem.id)
        )
    )
    foods = worked.foods
    plan_live: dict[tuple[int, int | None], list[ListItem]] = defaultdict(list)
    plan_gone: dict[tuple[int, int | None], list[ListItem]] = defaultdict(list)
    covered: set[tuple[int, int | None]] = set()  # typed lines, which the plan never doubles
    covered_anywhere: set[int] = set()  # plan lines a person has moved or edited
    for item in items:
        key = (item.food_id, item.shop_id)
        if item.merged_into_id is not None:
            continue
        if item.list_id != main.id:
            # A plan line a person moved to another list: the need is met there (a repeat of
            # it on the main list would be a duplicate).
            if _live(item):
                covered_anywhere.add(item.food_id)
            continue
        if item.source == "plan":
            if _live(item):
                plan_live[key].append(item)
                if item.hand_edited or item.ticked_at is not None:
                    covered_anywhere.add(item.food_id)
            else:
                plan_gone[key].append(item)
        elif _live(item) and item.ticked_at is None:
            covered.add(key)

    # A plan line a person moved onto a line at another shop joined it and was removed by the
    # move: the need is met there.
    covered_anywhere.update(
        db.scalars(
            select(ListItem.food_id)
            .join(
                SyncAction,
                and_(
                    SyncAction.household_id == ListItem.household_id,
                    SyncAction.id == ListItem.deleted_action_id,
                ),
            )
            .where(
                ListItem.household_id == kitchen.household_id,
                ListItem.source == "plan",
                ListItem.deleted_at.is_not(None),
                SyncAction.kind == "move",
            )
        )
    )

    wanted: dict[tuple[int, int | None], ToBuy] = {}
    for buy in worked.to_buy.values():
        wanted[(buy.food.id, buy.food.shop_id)] = buy

    for key, buy in wanted.items():
        mine = plan_live.get(key, [])
        if mine:
            first, *extras = mine
            for extra in extras:
                if not extra.hand_edited and extra.ticked_at is None:
                    edits.remove.append(extra)
            if (
                not first.hand_edited
                and first.ticked_at is None
                and (first.amount_milli != buy.amount_milli or first.size_id is not None)
            ):
                edits.change.append((first, buy.amount_milli))
            continue
        if key in covered:
            continue
        if key[0] in covered_anywhere:  # a person's edited or ticked line, in another shop
            continue
        if any(removed_by_hand(kitchen, gone, buy.amount_milli) for gone in plan_gone.get(key, ())):
            continue
        edits.create.append(buy)

    for key, mine in plan_live.items():
        if key in wanted or key[0] not in foods:
            continue
        for item in mine:
            if not item.hand_edited and item.ticked_at is None:
                edits.remove.append(item)
    return edits


def _apply(kitchen: Kitchen, main: ShoppingList, edits: Edits, batch: Batch) -> None:
    db = kitchen.db
    seq = batch.number()
    action = server_action(batch, PLAN_KIND, {}, None, list_id=main.id)
    action.login_name = PLAN_NAME
    payload: dict[str, Any] = {"created": [], "changed": [], "removed": []}
    for buy in edits.create:
        item = ListItem(
            id=str(uuid.uuid4()),
            household_id=kitchen.household_id,
            list_id=main.id,
            food_id=buy.food.id,
            shop_id=buy.food.shop_id,
            amount_milli=buy.amount_milli,
            source="plan",
            hand_edited=False,
            added_by_login_id=None,
            added_by_name=PLAN_NAME,
            version=seq,
        )
        db.add(item)
        payload["created"].append(item.id)
    for item, amount in edits.change:
        payload["changed"].append([item.id, base_amount(item.amount_milli), base_amount(amount)])
        item.amount_milli = amount
        item.size_id = None
        item.version = seq
    for item in edits.remove:
        item.deleted_at = utcnow()
        item.deleted_by_name = PLAN_NAME
        item.deleted_action_id = action.id
        item.version = seq
        payload["removed"].append(item.id)
    action.payload = payload
    action.payload_hash = payload_hash(payload)
    action.result = dict(payload)
    db.flush()


@dataclass
class Outcome:
    worked: Worked
    changed: bool
    plan_items: int


def refresh(kitchen: Kitchen) -> Outcome:
    """Bring the main list up to date with the plan and the pantry. Safe to call any time;
    changes nothing (and takes no counter number) when the list is already right. The caller
    commits."""
    db = kitchen.db
    main = ensure_main_list(db, kitchen.household_id)
    worked = work_out(kitchen)
    edits = plan_edits(kitchen, main, worked)
    changed = False
    if edits:
        batch = Batch(kitchen, action=str(uuid.uuid4()))  # takes the household's lock
        # Work it out again under the lock: another request may have got there first.
        worked = work_out(kitchen)
        edits = plan_edits(kitchen, main, worked)
        if edits:
            _apply(kitchen, main, edits, batch)
            changed = True
        batch.finish()
    return Outcome(worked, changed, plan_count(kitchen, main, worked.foods))


def plan_count(kitchen: Kitchen, main: ShoppingList, foods: dict[int, Food]) -> int:
    """How many of the main list's lines the plan made (not removed)."""
    items = kitchen.db.scalars(
        select(ListItem).where(
            ListItem.household_id == kitchen.household_id,
            ListItem.list_id == main.id,
            ListItem.source == "plan",
            ListItem.deleted_at.is_(None),
            ListItem.merged_into_id.is_(None),
        )
    )
    return sum(1 for item in items if item.food_id in foods)


# --- The staples card ----------------------------------------------------------------------------


@dataclass
class Staple:
    food: Food
    used_in: list[str]


def staples_card(kitchen: Kitchen, worked: Worked) -> list[Staple]:
    """The staples the counted meals use, except those with "Got it" (while every meal that
    uses one was there when it was said) or already on the list (ticked or not). A, B, C
    order."""
    db = kitchen.db
    if not worked.staples:
        return []
    got = {
        row.food_id: set(row.item_ids)
        for row in db.scalars(
            select(StapleCheck).where(StapleCheck.household_id == kitchen.household_id)
        )
    }
    on_list = set(
        db.scalars(
            select(ListItem.food_id)
            .join(ShoppingList, ShoppingList.id == ListItem.list_id)
            .where(
                ListItem.household_id == kitchen.household_id,
                ShoppingList.main.is_(True),
                ListItem.deleted_at.is_(None),
                ListItem.merged_into_id.is_(None),
            )
        )
    )
    foods = worked.foods
    out = [
        Staple(foods[food_id], names)
        for food_id, (names, items) in worked.staples.items()
        if food_id in foods and not items <= got.get(food_id, set()) and food_id not in on_list
    ]
    return sorted(out, key=lambda s: (fold(s.food.name), s.food.id))


def got_it(kitchen: Kitchen, food: Food) -> None:
    """Remember "Got it" for a staple: the meal items that use it now. It comes back only when
    a meal item that is not among them uses it (a meal added), not as days pass or meals go."""
    worked = work_out(kitchen)
    found = worked.staples.get(food.id)
    ids = sorted(found[1]) if found else []
    row = kitchen.db.get(StapleCheck, food.id)
    if row is None:
        kitchen.db.add(
            StapleCheck(food_id=food.id, household_id=kitchen.household_id, item_ids=ids)
        )
    else:
        row.item_ids = ids
        row.at = utcnow()
    kitchen.db.flush()


def not_got_it(kitchen: Kitchen, food: Food) -> None:
    """Undo of "Got it"."""
    row = kitchen.db.get(StapleCheck, food.id)
    if row is not None and row.household_id == kitchen.household_id:
        kitchen.db.delete(row)
        kitchen.db.flush()
