"""P-1 (docs/dev/sync-protocol.md section 14): two phones make random queues offline and
send them in random batches, in a random order, sometimes losing the answer and sending
again. Whatever happens:

- each ingredient's stock is what its standing purchases brought in, and never below zero
  (and after a use, that minus the use, never below zero);
- sending any part of a queue again changes nothing;
- every action has exactly one sync_action row;
- a removed item is back on the list only through an Undo.

Uses come after the queues: a use and a later untick of the same purchase share the
purchase out (SY-26u), so the sum only holds with the uses last."""

import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from sqlalchemy import func, select
from sync_kit import API, PHONE_A, PHONE_R, S0, action, changes, db, new_id, ok, s0, send

from mealwright.config import Settings
from mealwright.main import create_app
from mealwright.models import Food, ListItem, ListTick, StockLot, SyncAction

ADMIN = {"name": "Tess", "username": "tess", "password": "correct horse battery"}
LINES = ("Toor dal", "Paneer", "Milk", "Coriander", "Onions", "Salt")
KINDS = (
    "tick",
    "tick",
    "untick",
    "untick",
    "set_amount",
    "delete",
    "undo",
    "add",
    "answer",
    "answer",
)


@dataclass
class Phone:
    client: TestClient
    device: str
    items: list[str]  # the lines this phone knows of
    queue: list[dict[str, Any]] = field(default_factory=list)
    sent: int = 0  # how much of the queue the server has answered
    seen: int = 0
    questions: list[int] = field(default_factory=list)


# A step: ("make", phone, kind, pick, number) or ("sync", phone, batch size, answer lost).
make = st.tuples(
    st.just("make"),
    st.integers(0, 1),
    st.sampled_from(KINDS),
    st.integers(0, 3),
    st.integers(1, 6),
)
sync = st.tuples(st.just("sync"), st.integers(0, 1), st.integers(1, 5), st.booleans())
steps = st.lists(st.one_of(make, make, sync), min_size=10, max_size=40)


def _make(phone: Phone, s: S0, kind: str, pick: int, number: int) -> None:
    item = phone.items[pick % len(phone.items)]
    mine = phone.queue
    if kind == "tick":
        made = action("tick", phone.seen, item_id=item)
    elif kind == "untick":
        ticks = [a["id"] for a in mine if a["kind"] == "tick" and a["item_id"] == item]
        if not ticks:
            return
        made = action("untick", phone.seen, item_id=item, tick_ids=ticks[-number % len(ticks) :])
    elif kind == "set_amount":
        if item == s.items["Salt"]:
            return
        made = action("set_amount", phone.seen, item_id=item, amount=number * 100)
    elif kind == "delete":
        made = action("delete", phone.seen, item_id=item)
    elif kind == "undo":
        if not mine:
            return
        made = action("undo", phone.seen, undoes=mine[pick % len(mine)]["id"])
    elif kind == "add":
        food = s.foods[("Eggs", "Milk", "Onions")[pick % 3]]
        made = action("add", phone.seen, list_id=s.main, item_id=new_id(), food_id=food)
        made["amount"] = number
        phone.items.append(made["item_id"])
    else:
        if not phone.questions:
            return
        card = phone.questions[pick % len(phone.questions)]
        made = action(
            "answer_double_tick",
            phone.seen,
            question_id=card,
            answer="one" if number % 2 else "two",
        )
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


def _stock_matches_purchases(s: S0) -> dict[int, int]:
    with db(s.kitchen) as session:
        lots = dict(
            session.execute(
                select(StockLot.food_id, func.sum(StockLot.amount_milli)).group_by(StockLot.food_id)
            ).all()
        )
        bought = dict(
            session.execute(
                select(ListItem.food_id, func.sum(ListTick.bought_milli))
                .join(ListItem, ListItem.id == ListTick.item_id)
                .join(Food, Food.id == ListItem.food_id)
                .where(
                    ListTick.reversed_at.is_(None),
                    ListTick.change_id.is_not(None),
                    Food.staple.is_(False),
                )
                .group_by(ListItem.food_id)
            ).all()
        )
        lowest = session.scalar(select(func.min(StockLot.amount_milli)))
        assert lowest is None or lowest >= 0
    for food_id in set(lots) | set(bought):
        assert int(lots.get(food_id) or 0) == int(bought.get(food_id) or 0), food_id
    return {food_id: int(total or 0) for food_id, total in lots.items()}


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
            if done.status != "applied" or item is None or item.deleted_at is not None:
                continue
            assert any(undo.seq > done.seq for undo in undos), gone


@settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)
@given(plan=steps, uses=st.lists(st.integers(1, 3000), min_size=3, max_size=3))
def test_p1_random_queues_from_two_phones(plan: list[Any], uses: list[int]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        app = create_app(Settings(data_dir=Path(tmp) / "data", run_jobs=False))
        with TestClient(app, base_url="https://testserver") as kitchen:
            ok(kitchen.post(f"{API}/setup", json=ADMIN), 201)
            s = s0(kitchen)
            lines = [s.items[name] for name in LINES]
            phones = [
                Phone(kitchen, PHONE_A, list(lines), seen=s.c0),
                Phone(s.wren, PHONE_R, list(lines), seen=s.c0),
            ]
            before = {row.id for row in _rows(s)}  # S0's own adds

            for step in plan:
                phone = phones[step[1]]
                if step[0] == "make":
                    _make(phone, s, step[2], step[3], step[4])
                elif phone.sent < len(phone.queue):
                    _sync(phone, step[2], step[3])
            for phone in phones:  # both phones come back online in the end
                while phone.sent < len(phone.queue):
                    _sync(phone, 5, False)

            _stock_matches_purchases(s)
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

            totals = _stock_matches_purchases(s)
            for name, used in zip(("Toor dal", "Paneer", "Milk"), uses, strict=True):
                food_id = s.foods[name]
                unit = "ml" if name == "Milk" else "g"
                answer = kitchen.post(
                    f"{API}/foods/{food_id}/used",
                    json={"amount": {"amount": used, "unit": unit}},
                )
                had = totals.get(food_id, 0)
                if had == 0:
                    assert answer.status_code == 409
                    continue
                ok(answer)
                assert s.total(name) * 1000 == max(0, had - used * 1000)


def _rows(s: S0) -> list[SyncAction]:
    with db(s.kitchen) as session:
        rows = list(session.scalars(select(SyncAction)))
        session.expunge_all()
        return rows
