"""Ticking: the pantry side of a tick (docs/dev/sync-protocol.md sections 7, 8 and 5.8)."""

from collections.abc import Callable
from typing import NamedTuple

from mealwright import shopping
from mealwright.api.v1.context import Kitchen
from mealwright.foods import amount_out
from mealwright.models import Change, DoubleTick, Food, FoodSize, ListItem, ListTick, SyncAction
from mealwright.shopping import Act, Batch

TICK_KINDS = ("tick", "untick", "put_away", "different_pack", "answer_double_tick")

HANDLERS: dict[str, Callable[[Act], None]] = {}


def undo(act: Act, target: SyncAction) -> None:  # pragma: no cover (next commit)
    act.ignore("nothing_to_undo")


def pantry_undo(kitchen: Kitchen, change: Change, batch: Batch) -> Change:
    """Undo from Pantry → Recent changes (api-0.2 6.5), keeping lists in step (5.8)."""
    from mealwright.api.v1.changes import undo_change

    done = undo_change(kitchen, change, batch, batch.action)
    if batch.taken:
        shopping.log_undo(batch, change, done)
    return done


# --- The card (section 8) ------------------------------------------------------------------------

NUMBER_WORDS = {2: "two", 3: "three", 4: "four", 5: "five"}


class CardWords(NamedTuple):
    title: str
    text: str
    yes: str
    no: str


def _names(names: list[str]) -> str:
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def card_words(kitchen: Kitchen, question: DoubleTick, for_login_id: int) -> CardWords:
    """ "Did you buy 2?" for the login it's shown to (section 8, mockup Shop.dc.html)."""
    db = kitchen.db
    hid = kitchen.household_id
    purchases = [
        tick
        for tick_id in question.tick_ids
        if (tick := db.get(ListTick, (hid, tick_id))) is not None
    ]
    standing = [tick for tick in purchases if tick.reversed_at is None]
    shown = standing if len(standing) >= 2 else purchases
    count = len(shown)
    item = db.get(ListItem, question.item_id)
    food = db.get(Food, item.food_id) if item is not None else None
    name = food.name if food is not None else "it"
    people: list[str] = []
    seen: set[object] = set()
    for tick in shown:
        key = tick.login_id if tick.login_id is not None else tick.login_name
        if key in seen:
            continue
        seen.add(key)
        people.append("You" if tick.login_id == for_login_id else tick.login_name)
    people.sort(key=lambda person: person != "You")  # "You" first
    if len(people) <= 1:
        start = f"This was ticked on {NUMBER_WORDS.get(count, str(count))} phones"
    elif len(people) == 2:
        start = f"{_names(people)} both ticked {name}"
    else:
        start = f"{_names(people)} all ticked {name}"
    total = sum(tick.bought_milli or 0 for tick in shown)
    size_id = next((tick.bought_size_id for tick in shown if tick.bought_size_id), None)
    size = db.get(FoodSize, size_id) if size_id else None
    went = amount_out(food, total, size).short if food is not None and total else str(count)
    if len(people) <= 1:
        text = f"{start}, so {went} went into the pantry."
    else:
        text = f"{start} while offline, so {went} went into the pantry."
    return CardWords(title=f"Did you buy {count}?", text=text, yes=f"Yes, {count}", no="Just 1")
