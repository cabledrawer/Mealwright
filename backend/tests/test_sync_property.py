"""P-1 (docs/dev/sync-protocol.md section 14): three phones (cabledrawer on two, Alex on one)
make random queues offline and send them in random batches, in a random order, sometimes
losing the answer and sending again, while the pantry is used in between. Whatever happens:

- no lot is ever below zero;
- every lot with stock in it belongs to exactly one purchase, so each ingredient's stock is
  the sum of its purchases' lots (S0 starts with an empty pantry);
- a purchase that's been taken back has nothing left in its lots; one still standing has
  at most what it bought, and exactly that if nothing has been used from its lots;
- taking a purchase back (untick, "Just 1", Undo) only ever takes from that purchase's own
  lots, and never more than is left in them;
- putting a purchase back (Undo of an untick or of "Just 1") gives back exactly what
  taking it back took out, lot by lot, no more;
- sending any part of a queue again changes nothing;
- every action has exactly one sync_action row;
- a removed item is back on the list only through an Undo."""

import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import select
from sync_kit import (
    API,
    PHONE_A,
    PHONE_B,
    PHONE_R,
    S0,
    action,
    changes,
    db,
    new_id,
    ok,
    s0,
    send,
)

from mealwright.config import Settings
from mealwright.main import create_app
from mealwright.models import Change, ChangeLine, ListItem, ListTick, StockLot, SyncAction

ADMIN = {"name": "Tess", "username": "tess", "password": "correct horse battery"}
LINES = ("Toor dal", "Paneer", "Milk", "Coriander", "Onions", "Salt")
USED = (("Toor dal", "g"), ("Paneer", "g"), ("Milk", "ml"), ("Coriander", "count"))
KINDS = (  # the kinds that need something to act on come more often
    *("tick", "tick", "tick"),
    *("untick", "untick"),
    *("different_pack", "different_pack"),
    *("put_away", "put_away"),
    *("answer", "answer", "answer"),
    *("undo", "undo"),
    *("dismiss_note", "dismiss_note"),
    "set_amount",
    "delete",
    "add",
    "clear_ticked",
    "create_list",
    "rename_list",
    "remove_list",
)


@dataclass
class Phone:
    client: TestClient
    device: str
    items: dict[str, str]  # the lines this phone knows of → their list
    lists: list[str]  # the lists this phone knows of (the main list first)
    queue: list[dict[str, Any]] = field(default_factory=list)
    sent: int = 0  # how much of the queue the server has answered
    seen: int = 0
    questions: list[int] = field(default_factory=list)
    notes: list[dict[str, Any]] = field(default_factory=list)


# A step: ("make", phone, kind, pick, number), ("sync", phone, batch size, answer lost) or
# ("use", ingredient, amount): someone cooks with it, online, between the syncs.
make = st.tuples(
    st.just("make"),
    st.integers(0, 2),
    st.sampled_from(KINDS),
    st.integers(0, 7),
    st.integers(1, 6),
)
sync = st.tuples(st.just("sync"), st.integers(0, 2), st.integers(1, 5), st.booleans())
use = st.tuples(st.just("use"), st.integers(0, len(USED) - 1), st.integers(1, 700))
steps = st.lists(st.one_of(make, make, make, sync, sync, use), min_size=20, max_size=60)


def _pick(rows: list[Any], pick: int) -> Any:
    return rows[pick % len(rows)] if rows else None


def _my_ticks(phone: Phone, pick: int) -> tuple[str, list[str]]:
    """One of this phone's ticks: its item, and this phone's ticks of that item."""
    ticks = [a for a in phone.queue if a["kind"] == "tick"]
    if not ticks:
        return "", []
    item = str(_pick(ticks, pick)["item_id"])
    return item, [a["id"] for a in ticks if a["item_id"] == item]


def _make(phone: Phone, s: S0, kind: str, pick: int, number: int) -> None:
    item = _pick(list(phone.items), pick)
    mine = phone.queue
    seen = phone.seen
    places = sorted(s.places.values())
    own_lists = phone.lists[1:]
    if kind == "tick":
        made = action("tick", seen, item_id=item)
    elif kind in ("untick", "put_away"):
        item, ticks = _my_ticks(phone, pick)
        if not ticks:
            return
        named = ticks[-number % len(ticks) :]
        if kind == "untick":
            made = action("untick", seen, item_id=item, tick_ids=named)
        else:
            place = places[number % len(places)]
            made = action("put_away", seen, item_id=item, place_id=place, tick_ids=named)
    elif kind == "different_pack":
        item, ticks = _my_ticks(phone, pick)
        if not ticks:
            return
        pack = (100, 200, 250, 500)[pick % 4]
        made = action(
            "different_pack", seen, item_id=item, tick_id=ticks[-1], count=number, pack=pack
        )
    elif kind == "set_amount":
        if item == s.items["Salt"]:
            return
        made = action("set_amount", seen, item_id=item, amount=number * 100)
    elif kind == "delete":
        made = action("delete", seen, item_id=item)
    elif kind == "clear_ticked":
        where = _pick(phone.lists, pick)
        on_it = [i for i, list_id in phone.items.items() if list_id == where]
        if not on_it:
            return
        made = action("clear_ticked", seen, list_id=where, item_ids=on_it[: number + 1])
    elif kind == "undo":
        undoable = [a["id"] for a in mine] + [n["undo"] for n in phone.notes if n["undo"]]
        if not undoable:
            return
        made = action("undo", seen, undoes=_pick(undoable, pick + number))
    elif kind == "add":
        food = s.foods[("Eggs", "Milk", "Onions", "Paneer")[pick % 4]]
        where = _pick(phone.lists, number)
        made = action("add", seen, list_id=where, item_id=new_id(), food_id=food)
        made["amount"] = number * 100
        phone.items[made["item_id"]] = where
    elif kind == "create_list":
        made = action("create_list", seen, list_id=new_id(), name=f"Party {number}")
        phone.lists.append(made["list_id"])
    elif kind == "rename_list":
        if not own_lists:
            return
        made = action("rename_list", seen, list_id=_pick(own_lists, pick), name=f"Picnic {number}")
    elif kind == "remove_list":
        if not own_lists:
            return
        made = action("remove_list", seen, list_id=_pick(own_lists, pick))
    elif kind == "dismiss_note":
        note = _pick(phone.notes, pick)
        if note is None:
            return
        made = action("dismiss_note", seen, note_id=note["id"])
    else:
        card = _pick(phone.questions, pick)
        if card is None:
            return
        answer = "one" if number % 2 else "two"
        made = action("answer_double_tick", seen, question_id=card, answer=answer)
    mine.append(made)


def _sync(phone: Phone, size: int, lost: bool, since: int = 0) -> None:
    batch = phone.queue[phone.sent : phone.sent + size]
    answer = send(phone.client, *batch, device=phone.device, since=since)
    if lost:  # the answer never came back: the phone sends the same batch again
        again = send(phone.client, *batch, device=phone.device, since=since)
        assert all(r["repeat"] for r in again["results"])
        answer = again
    assert [r["id"] for r in answer["results"]] == [a["id"] for a in batch]
    phone.sent += len(batch)
    phone.seen = int(answer["changes"]["cursor"])
    phone.questions = [int(q["id"]) for q in answer["changes"]["questions"] if q["open"]]
    phone.notes = [n for n in answer["changes"]["notes"] if not n["gone"]]


def _use(s: S0, which: int, amount: int) -> None:
    """A use without a place leaves the freezer alone (api-0.2)."""
    name, unit = USED[which]
    if unit == "count":
        amount = amount % 3 + 1
    frozen = [lot for lot in s.lots(name) if lot[0] == "Freezer"]
    had = s.total(name) - sum(left for _, left in frozen)
    answer = s.kitchen.post(
        f"{API}/foods/{s.foods[name]}/used", json={"amount": {"amount": amount, "unit": unit}}
    )
    if answer.status_code == 409:
        assert had == 0, answer.text
        return
    ok(answer)
    assert s.total(name) - sum(left for _, left in frozen) == max(0, had - amount)
    assert [lot for lot in s.lots(name) if lot[0] == "Freezer"] == frozen


def _state(s: S0) -> Any:
    with db(s.kitchen) as session:
        return (
            sorted(
                session.execute(
                    select(StockLot.food_id, StockLot.place_id, StockLot.amount_milli)
                ).all()
            ),
            sorted(
                session.execute(
                    select(ListTick.id, ListTick.bought_milli, ListTick.reversed_at)
                ).all()
            ),
            sorted(
                session.execute(
                    select(
                        ListItem.id, ListItem.amount_milli, ListItem.deleted_at, ListItem.version
                    )
                ).all()
            ),
            sorted(session.execute(select(SyncAction.id, SyncAction.seq)).all()),
            changes(s.kitchen)["cursor"],
        )


def _purchases_hold(s: S0) -> None:
    """The stock checks in the module docstring, per purchase."""
    with db(s.kitchen) as session:
        lots = {lot.id: lot.amount_milli for lot in session.scalars(select(StockLot))}
        assert all(amount >= 0 for amount in lots.values()), lots
        every = {change.id: change for change in session.scalars(select(Change))}
        lines: dict[int, list[ChangeLine]] = defaultdict(list)
        for line in session.scalars(select(ChangeLine)):
            lines[line.change_id].append(line)
        made = [change for change in every.values() if change.tick_id is not None]
        own: dict[str, set[int]] = defaultdict(set)  # purchase → the lots its own changes name
        for change in made:
            if change.kind != "undo":
                own[str(change.tick_id)] |= {
                    line.lot_id for line in lines[change.id] if line.lot_id is not None
                }
        owner: dict[int, str] = {}
        for tick_id, lot_ids in own.items():
            for lot_id in lot_ids:
                assert owner.setdefault(lot_id, tick_id) == tick_id, ("shared lot", lot_id)
        for lot_id, amount in lots.items():
            assert amount == 0 or lot_id in owner, ("stock from no purchase", lot_id)
        for change in made:  # a take-back takes from its own purchase's lots only
            undone = every.get(change.undoes_change_id or 0)
            if change.kind != "undo" or undone is None or undone.kind != "shopped":
                continue
            for line in lines[change.id]:
                assert line.lot_id is None or line.lot_id in own[str(change.tick_id)], line.id
                assert line.amount_before_milli >= line.amount_after_milli >= 0, line.id
        actions = {row.id: row for row in session.scalars(select(SyncAction))}
        for change in made:  # a put-back gives back exactly what its reversal took (7.5)
            data = change.undo_data or {}
            if change.kind != "shopped" or data.get("action") == change.tick_id:
                continue  # the purchase's own `shopped` change, from the tick
            undo = actions[str(data["action"])]
            reversal = (undo.payload or {}).get("undoes")
            took: dict[int | None, int] = defaultdict(int)
            for other in made:
                if (
                    other.kind == "undo"
                    and other.tick_id == change.tick_id
                    and (other.undo_data or {}).get("action") == reversal
                ):
                    for line in lines[other.id]:
                        took[line.lot_id] += line.amount_before_milli - line.amount_after_milli
            back: dict[int | None, int] = defaultdict(int)
            for line in lines[change.id]:
                back[line.lot_id] += line.amount_after_milli - line.amount_before_milli
            took_out = {lot_id: amount for lot_id, amount in took.items() if amount > 0}
            put_back = {lot_id: amount for lot_id, amount in back.items() if amount}
            assert put_back == took_out, ("put back", change.id, put_back, took_out)
        used = {
            line.lot_id
            for change in every.values()
            if change.kind == "used"
            for line in lines[change.id]
            if line.amount_before_milli > line.amount_after_milli
        }
        for tick in session.scalars(select(ListTick)):
            left = sum(lots.get(lot_id, 0) for lot_id in own[tick.id])
            if tick.reversed_at is not None:
                assert left == 0, ("taken back, but stock left", tick.id, left)
            elif own[tick.id] & used:
                assert left <= (tick.bought_milli or 0), (tick.id, left, tick.bought_milli)
            elif own[tick.id]:
                assert left == (tick.bought_milli or 0), (tick.id, left, tick.bought_milli)


def _back_only_through_undo(s: S0, phones: list[Phone]) -> None:
    deletes = [a for p in phones for a in p.queue if a["kind"] == "delete"]
    with db(s.kitchen) as session:
        rows = {
            row.id: row
            for row in session.scalars(select(SyncAction).where(SyncAction.household_id == 1))
        }
        undos = [row for row in rows.values() if row.kind == "undo" and row.status == "applied"]
        for gone in deletes:
            done = rows[gone["id"]]
            item = session.get(ListItem, gone["item_id"])
            while item is not None and item.merged_into_id:  # an add that joined a line
                item = session.get(ListItem, item.merged_into_id)
            if done.status != "applied" or item is None or item.deleted_at is not None:
                continue
            assert any(undo.seq > done.seq for undo in undos), gone


@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(plan=steps)
def test_p1_random_queues_from_three_phones(plan: list[Any]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(Settings(data_dir=Path(tmp) / "data", run_jobs=False))
        with TestClient(app, base_url="https://testserver") as kitchen:
            ok(kitchen.post(f"{API}/setup", json=ADMIN), 201)
            s = s0(kitchen)
            lines = {s.items[name]: s.main for name in LINES}
            phones = [
                Phone(kitchen, PHONE_A, dict(lines), [s.main], seen=s.c0),
                Phone(kitchen, PHONE_B, dict(lines), [s.main], seen=s.c0),  # the same login
                Phone(s.alex, PHONE_R, dict(lines), [s.main], seen=s.c0),
            ]
            before = {row.id for row in _rows(s)}  # S0's own adds

            for step in plan:
                if step[0] == "use":
                    _use(s, step[1], step[2])
                    _purchases_hold(s)
                    continue
                phone = phones[step[1]]
                if step[0] == "make":
                    _make(phone, s, step[2], step[3], step[4])
                elif phone.sent < len(phone.queue):
                    _sync(phone, step[2], step[3])
                    _purchases_hold(s)
            for phone in phones:  # every phone comes back online in the end
                while phone.sent < len(phone.queue):
                    _sync(phone, 5, False)

            _purchases_hold(s)
            _back_only_through_undo(s, phones)
            sent = [a["id"] for p in phones for a in p.queue]
            assert len(sent) == len(set(sent))
            assert {row.id for row in _rows(s)} == before | set(sent)

            settled = _state(s)
            for phone in phones:  # resend a part of each queue: nothing changes
                part = phone.queue[: len(plan) % (len(phone.queue) + 1)]
                if part:
                    answer = send(phone.client, *part, device=phone.device)
                    assert all(r["repeat"] for r in answer["results"])
            assert _state(s) == settled


def _rows(s: S0) -> list[SyncAction]:
    with db(s.kitchen) as session:
        rows = list(session.scalars(select(SyncAction)))
        session.expunge_all()
        return rows
