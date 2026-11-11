"""Ticks, two phones (docs/dev/sync-protocol.md sections 7, 8 and 14): purchases, the card,
untick, put-away, "Different pack?", and Undo of each, from the queue and from Pantry."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sync_kit import (
    API,
    PHONE_A,
    PHONE_B,
    PHONE_R,
    REMY_PASSWORD,
    S0,
    action,
    changes,
    counter,
    db,
    food,
    item_row,
    new_id,
    ok,
    one,
    s0,
    send,
    tick,
)

from mealwright.models import Change, Food, FoodSize, ListTick, Place, StockLot, SyncAction, utcnow

BOTH = pytest.mark.parametrize("a_first", [True, False], ids=["A-B", "B-A"])


def _in_order(a_first: bool, a: Any, b: Any) -> None:
    for step in (a, b) if a_first else (b, a):
        step()


def _card(client: TestClient) -> list[Any]:
    return [q for q in changes(client)["questions"] if q["open"]]


def _undo(client: TestClient, action_id: str, device: str = PHONE_A, seen: int = 0) -> Any:
    return one(client, "undo", seen, device, undoes=action_id)


# --- Two purchases and the card (L-3, L-4) -------------------------------------------------------


@BOTH
def test_sy01_same_item_ticked_on_both(kitchen: TestClient, a_first: bool) -> None:
    s = s0(kitchen)
    results: list[Any] = []
    _in_order(
        a_first,
        lambda: results.append(tick(kitchen, s, "Toor dal", PHONE_A)),
        lambda: results.append(tick(s.remy, s, "Toor dal", PHONE_R)),
    )
    assert [r["status"] for r in results] == ["applied", "applied"]
    assert s.lots("Toor dal") == [("Cupboard", 500), ("Cupboard", 500)]
    shopped = s.changes_of("Toor dal", "shopped")
    assert sorted(c.login_name for c in shopped) == ["Tess", "Remy"]
    assert shopped[0].summary == "Bought 1\u00a0packet Toor dal → Cupboard"
    row = s.item(kitchen, "Toor dal")
    assert sorted(t["by"]["name"] for t in row["ticks"]) == ["Tess", "Remy"]
    assert all(t["standing"] for t in row["ticks"])
    (mine,) = _card(kitchen)
    (hers,) = _card(s.remy)
    assert mine["id"] == hers["id"] and mine["title"] == "Did you buy 2?"
    assert mine["text"] == (
        "You and Remy both ticked Toor dal while offline, so 2\u00a0packets went into the pantry."
    )
    assert hers["text"].startswith("You and Tess both ticked Toor dal")
    assert (mine["yes"], mine["no"]) == ("Yes, 2", "Just 1")
    assert changes(kitchen)["notes"] == [] and changes(s.remy)["notes"] == []


@BOTH
def test_sy02_ticked_on_two_phones_of_one_login(kitchen: TestClient, a_first: bool) -> None:
    s = s0(kitchen)
    _in_order(
        a_first,
        lambda: tick(kitchen, s, "Toor dal", PHONE_A),
        lambda: tick(kitchen, s, "Toor dal", PHONE_B),
    )
    assert s.total("Toor dal") == 1000
    (card,) = _card(kitchen)
    assert card["text"] == "This was ticked on two phones, so 2\u00a0packets went into the pantry."
    assert _card(s.remy) == []


def test_sy02b_a_count_on_two_phones_never_says_left(kitchen: TestClient) -> None:
    s = s0(kitchen)
    onions = food(kitchen, "Spring onions", counted_as="count")["id"]
    item = new_id()
    send(kitchen, action("add", s.c0, list_id=s.main, item_id=item, food_id=onions, amount=6))
    one(kitchen, "tick", counter(kitchen), PHONE_A, item_id=item)
    one(kitchen, "tick", counter(kitchen), PHONE_B, item_id=item)
    (card,) = _card(kitchen)
    assert card["text"] == "This was ticked on two phones, so 12 went into the pantry."


def test_sy03_ticked_twice_on_one_phone(kitchen: TestClient) -> None:
    s = s0(kitchen)
    assert tick(kitchen, s, "Toor dal")["status"] == "applied"
    second = tick(kitchen, s, "Toor dal")
    assert (second["status"], second["reason"]) == ("ignored", "already_ticked")
    assert s.total("Toor dal") == 500
    assert len(s.ticks("Toor dal")) == 1 and _card(kitchen) == []


def _coriander_ticked(s: S0) -> str:
    """S0 plus Tess's tick t0 on Coriander, seen by both phones (the new C0)."""
    t0 = tick(s.kitchen, s, "Coriander")["id"]
    s.c0 = int(changes(s.kitchen)["cursor"])
    return str(t0)


@BOTH
def test_sy04_a_tick_sticks(kitchen: TestClient, a_first: bool) -> None:
    s = s0(kitchen)
    t0 = _coriander_ticked(s)
    item = s.items["Coriander"]
    results: dict[str, Any] = {}

    def a() -> None:
        results["a_untick"] = one(kitchen, "untick", s.c0, PHONE_A, item_id=item, tick_ids=[t0])
        results["a_tick"] = tick(kitchen, s, "Coriander", PHONE_A)

    def b() -> None:
        results["b"] = one(s.remy, "untick", s.c0, PHONE_R, item_id=item, tick_ids=[t0])

    _in_order(a_first, a, b)
    loser = results["b"] if a_first else results["a_untick"]
    assert (loser["status"], loser["reason"]) == ("ignored", "not_ticked")
    assert results["a_tick"]["status"] == "applied"
    assert s.total("Coriander") == 1
    (standing,) = s.ticks("Coriander")
    assert standing.id == results["a_tick"]["id"] and standing.login_name == "Tess"
    assert changes(kitchen)["notes"] == [] and changes(s.remy)["notes"] == []


@BOTH
def test_sy05_both_untick(kitchen: TestClient, a_first: bool) -> None:
    s = s0(kitchen)
    t0 = _coriander_ticked(s)
    item = s.items["Coriander"]
    results: list[Any] = []
    _in_order(
        a_first,
        lambda: results.append(one(kitchen, "untick", s.c0, PHONE_A, item_id=item, tick_ids=[t0])),
        lambda: results.append(one(s.remy, "untick", s.c0, PHONE_R, item_id=item, tick_ids=[t0])),
    )
    assert [r["status"] for r in results] == ["applied", "ignored"]
    assert results[1]["reason"] == "not_ticked"
    assert s.total("Coriander") == 0
    assert len(s.changes_of("Coriander", "undo")) == 1
    assert not any(t["standing"] for t in s.item(kitchen, "Coriander")["ticks"])


# --- Tick against a delete (L-9) -----------------------------------------------------------------


@BOTH
def test_sy08_sy09_tick_against_a_delete(kitchen: TestClient, a_first: bool) -> None:
    s = s0(kitchen)
    item = s.items["Paneer"]
    results: dict[str, Any] = {}
    _in_order(
        a_first,
        lambda: results.update(tick=tick(kitchen, s, "Paneer")),
        lambda: results.update(delete=one(s.remy, "delete", s.c0, PHONE_R, item_id=item)),
    )
    assert s.lots("Paneer") == [("Fridge", 200), ("Fridge", 200)]
    assert s.item(kitchen, "Paneer", s.c0)["deleted"] is True
    (note,) = changes(kitchen)["notes"]
    assert note["text"] == "Remy had removed this. Your tick still went into the pantry."
    assert note["undo"] == results["tick"]["id"]
    assert changes(s.remy)["notes"] == []
    assert _undo(kitchen, note["undo"])["status"] == "applied"
    assert s.total("Paneer") == 0
    assert changes(kitchen)["notes"] == []


def _removed_with_its_line(s: S0, name: str) -> None:
    """Remy removes the line, then the ingredient (phone A hasn't seen either)."""
    one(s.remy, "delete", s.c0, PHONE_R, item_id=s.items[name])
    ok(s.remy.delete(f"{API}/foods/{s.foods[name]}"))


def _live(s: S0, name: str) -> list[int]:
    with db(s.kitchen) as session:
        rows = session.scalars(select(Food).where(Food.name == name, Food.removed_at.is_(None)))
        return [row.id for row in rows]


def test_a_tick_brings_back_the_removed_ingredient(kitchen: TestClient) -> None:
    """7.1 (cabledrawer 18 Oct): the purchase needs an ingredient to go into the pantry."""
    s = s0(kitchen)
    _removed_with_its_line(s, "Paneer")
    done = tick(kitchen, s, "Paneer")
    assert done["status"] == "applied" and done["message"] == "Paneer is back in Ingredients."
    assert _live(s, "Paneer") == [s.foods["Paneer"]]
    assert s.total("Paneer") == 400
    # Its Undo takes the stock out and removes the ingredient again, as for an add (5.9).
    assert _undo(kitchen, done["id"])["status"] == "applied"
    assert _live(s, "Paneer") == [] and s.total("Paneer") == 0


def test_an_undo_of_a_tick_keeps_the_brought_back_ingredient_while_stock_is_left(
    kitchen: TestClient,
) -> None:
    """Removing it would hide the 250 g added in Pantry since."""
    s = s0(kitchen)
    _removed_with_its_line(s, "Paneer")
    done = tick(kitchen, s, "Paneer")
    more = {"food_id": s.foods["Paneer"], "amount": {"amount": 250, "unit": "g"}}
    ok(kitchen.post(f"{API}/stock", json=more), 201)
    assert _undo(kitchen, done["id"])["status"] == "applied"
    assert _live(s, "Paneer") == [s.foods["Paneer"]] and s.total("Paneer") == 250


def test_an_undo_of_a_tick_keeps_the_brought_back_ingredient_while_it_is_on_a_list(
    kitchen: TestClient,
) -> None:
    """0.2's rule (`cannot_remove`): an ingredient on a list can't be removed. Remy put
    Paneer on the list again after the tick brought it back, so the Undo takes the tick
    back but Paneer stays in Ingredients, and her line stays."""
    s = s0(kitchen)
    _removed_with_its_line(s, "Paneer")
    done = tick(kitchen, s, "Paneer")
    again = one(
        s.remy,
        "add",
        counter(s.remy),
        PHONE_R,
        list_id=s.main,
        item_id=new_id(),
        food_id=s.foods["Paneer"],
        amount=200,
    )
    assert again["status"] == "applied" and again["item_id"] != s.items["Paneer"]
    assert _undo(kitchen, done["id"])["status"] == "applied"
    assert s.ticks("Paneer") == [] and s.total("Paneer") == 0
    assert _live(s, "Paneer") == [s.foods["Paneer"]]
    assert item_row(changes(kitchen), again["item_id"])["deleted"] is False


def test_a_tick_goes_to_the_ingredient_that_has_the_name_now(kitchen: TestClient) -> None:
    """As an `add` would (5.9, SY-66): no second "Paneer"; the stock goes to the live one."""
    s = s0(kitchen)
    _removed_with_its_line(s, "Paneer")
    new = food(kitchen, "Paneer", counted_as="weight")["id"]
    done = tick(kitchen, s, "Paneer")
    assert done["status"] == "applied" and done["message"] is None
    assert done["food_id"] == new  # the ingredient the stock went to (5.4)
    assert _live(s, "Paneer") == [new]
    with db(kitchen) as session:
        lots = session.scalars(select(StockLot).where(StockLot.amount_milli > 0)).all()
        assert [(lot.food_id, lot.amount_milli) for lot in lots] == [(new, 400_000)]
    assert done["change"]["summary"].startswith("Bought 400\u00a0g Paneer")
    assert _undo(kitchen, done["id"])["status"] == "applied"  # and it comes out again
    with db(kitchen) as session:
        assert session.scalar(select(func.sum(StockLot.amount_milli))) == 0


def test_an_undo_of_an_untick_puts_back_into_the_ingredient_that_has_the_name_now(
    kitchen: TestClient,
) -> None:
    s = s0(kitchen)
    _removed_with_its_line(s, "Paneer")
    new = food(kitchen, "Paneer", counted_as="weight")["id"]
    done = tick(kitchen, s, "Paneer")
    off = one(kitchen, "untick", s.c0, item_id=s.items["Paneer"], tick_ids=[done["id"]])
    back = _undo(kitchen, off["id"])
    assert back["change"]["summary"].startswith("Ticked again: 400\u00a0g Paneer")
    with db(kitchen) as session:
        assert session.get(Change, back["change"]["id"]).food_id == new
        lots = session.scalars(select(StockLot).where(StockLot.amount_milli > 0)).all()
        assert [(lot.food_id, lot.amount_milli) for lot in lots] == [(new, 400_000)]


def test_a_tick_into_an_ingredient_counted_differently_puts_nothing_in(
    kitchen: TestClient,
) -> None:
    """7.1 (cabledrawer 18 Oct): 400 g of the old Paneer means nothing for a Paneer counted in
    items. The purchase is recorded with no stock, and the ticker gets a quiet note whose
    Undo takes the tick back."""
    s = s0(kitchen)
    _removed_with_its_line(s, "Paneer")
    new = food(kitchen, "Paneer", counted_as="count")["id"]
    done = tick(kitchen, s, "Paneer")
    assert done["status"] == "applied" and done["change"] is None and done["food_id"] == new
    assert _live(s, "Paneer") == [new]
    (purchase,) = s.ticks("Paneer")
    assert (purchase.bought_milli, purchase.change_id) == (None, None)
    with db(kitchen) as session:
        assert session.scalar(select(func.sum(StockLot.amount_milli))) is None
        assert session.scalars(select(Change).where(Change.kind == "shopped")).all() == []
    (note,) = changes(kitchen)["notes"]
    assert note["text"] == "Paneer is counted differently now, so nothing went into the pantry."
    assert (note["undo"], note["food_id"]) == (done["id"], new)
    assert changes(s.remy)["notes"] == []  # only the ticker's
    assert _undo(kitchen, note["undo"])["status"] == "applied"
    assert s.ticks("Paneer") == [] and changes(kitchen)["notes"] == []


def test_a_tick_with_nothing_to_put_in_brings_nothing_back(kitchen: TestClient) -> None:
    """A staple (or an item with no amount) puts no stock in, so its removed ingredient
    stays removed (7.1)."""
    s = s0(kitchen)
    _removed_with_its_line(s, "Salt")
    done = tick(kitchen, s, "Salt")
    assert done["status"] == "applied" and done["message"] is None
    assert _live(s, "Salt") == []


# --- Put away and Different pack (7.3, 7.4) ------------------------------------------------------


@BOTH
def test_sy13_put_away_on_two_phones(kitchen: TestClient, a_first: bool) -> None:
    s = s0(kitchen)
    t0 = _coriander_ticked(s)
    item = s.items["Coriander"]
    places = s.places
    a = lambda: one(  # noqa: E731
        kitchen, "put_away", s.c0, PHONE_A, item_id=item, place_id=places["Cupboard"], tick_ids=[t0]
    )
    b = lambda: one(  # noqa: E731
        s.remy, "put_away", s.c0, PHONE_R, item_id=item, place_id=places["Freezer"], tick_ids=[t0]
    )
    _in_order(a_first, a, b)
    last = "Freezer" if a_first else "Cupboard"
    assert s.lots("Coriander") == [(last, 1)]
    assert len(s.changes_of("Coriander", "moved")) == 2
    row = s.item(kitchen, "Coriander")
    assert row["put_away_place_id"] == places[last]
    loser, winner = (kitchen, "Remy") if a_first else (s.remy, "Tess")
    (note,) = changes(loser)["notes"]
    assert note["text"] == f"{winner} put Coriander in the {last}"
    first = "Cupboard" if a_first else "Freezer"
    assert _undo(loser, note["undo"])["status"] == "applied"
    assert s.lots("Coriander") == [(first, 1)]


def test_sy14_tick_then_put_away(kitchen: TestClient) -> None:
    s = s0(kitchen)
    t = tick(kitchen, s, "Coriander")
    put = one(
        kitchen,
        "put_away",
        s.c0,
        item_id=s.items["Coriander"],
        place_id=s.places["Freezer"],
        tick_ids=[t["id"]],
    )
    assert put["status"] == "applied" and put["change"]["kind"] == "moved"
    assert s.lots("Coriander") == [("Freezer", 1)]
    summaries = [c.summary for c in s.changes_of("Coriander") if c.kind in ("shopped", "moved")]
    assert summaries == ["Bought 1\u00a0bunch of Coriander → Fridge", "Moved Coriander → Freezer"]
    row = s.item(kitchen, "Coriander")
    assert row["put_away_place_id"] == s.places["Freezer"]
    assert row["ticks"][0]["place_id"] == s.places["Freezer"]


@pytest.mark.parametrize("use_by", ["2026-12-01", "0001-01-01", "9999-12-31"])
@pytest.mark.parametrize("place", ["Fridge", "Freezer"])
def test_put_away_with_a_use_by(kitchen: TestClient, use_by: str, place: str) -> None:
    # Pre-beta sweep: a put_away carrying `use_by` gave a 500 for any date (it reached the
    # database as text) and stalled the phone's queue. It sets the purchase's use-by, even year
    # 1 or 9999, Undo puts the old one back, the screens still read, and the next act applies.
    s = s0(kitchen)
    t = tick(kitchen, s, "Coriander")

    def use_bys() -> list[str]:
        with db(kitchen) as session:
            query = select(StockLot).where(StockLot.food_id == s.foods["Coriander"])
            return [str(row.use_by) for row in session.scalars(query)]

    was = use_bys()
    assert was != [use_by]
    answer = send(
        kitchen,
        action(
            "put_away",
            s.c0,
            item_id=s.items["Coriander"],
            place_id=s.places[place],
            tick_ids=[t["id"]],
            use_by=use_by,
        ),
        action("tick", s.c0, item_id=s.items["Paneer"]),
    )
    put, after = answer["results"]
    assert put["status"] == "applied" and after["status"] == "applied"
    assert s.lots("Coriander") == [(place, 1)]
    assert use_bys() == [use_by]
    for path in ("/pantry", "/today", "/changes", "/shopping/changes?since=0"):
        assert kitchen.get(API + path).status_code == 200, path
    assert _undo(kitchen, put["id"])["status"] == "applied"
    assert s.lots("Coriander") == [("Fridge", 1)]
    assert use_bys() == was  # Undo brings back the old use-by too


@pytest.mark.parametrize("use_by", ["not a date", "2026-02-30", "10000-01-01", 20261201])
def test_put_away_with_an_unreadable_use_by_is_refused(kitchen: TestClient, use_by: Any) -> None:
    s = s0(kitchen)
    t = tick(kitchen, s, "Coriander")
    answer = send(
        kitchen,
        action(
            "put_away",
            s.c0,
            item_id=s.items["Coriander"],
            place_id=s.places["Freezer"],
            tick_ids=[t["id"]],
            use_by=use_by,
        ),
        action("tick", s.c0, item_id=s.items["Paneer"]),
    )
    put, after = answer["results"]
    assert put["status"] == "refused" and after["status"] == "applied"
    assert s.lots("Coriander") == [("Fridge", 1)]


def test_sy15_different_pack(kitchen: TestClient) -> None:
    s = s0(kitchen)
    t = tick(kitchen, s, "Paneer")
    done = one(
        kitchen,
        "different_pack",
        s.c0,
        item_id=s.items["Paneer"],
        tick_id=t["id"],
        count=1,
        pack=400,
    )
    assert done["status"] == "applied" and done["change"]["kind"] == "repacked"
    assert done["change"]["summary"] == (
        "Paneer: bought 400\u00a0g · 1\u00a0pack instead of 400\u00a0g · 2\u00a0packs"
    )
    assert s.lots("Paneer") == [("Fridge", 400)]
    answer = changes(kitchen)
    paneer = next(f for f in answer["foods"] if f["id"] == s.foods["Paneer"])
    new = next(size for size in paneer["sizes"] if size["amount"] == 400)
    assert new["name"] == "pack" and new["added_when_shopping"] is True
    row = item_row(answer, s.items["Paneer"])
    assert row["amount"] == 400 and row["ticks"][0]["bought"]["amount"] == 400


def test_sy15b_a_first_amount_is_worded_as_one(kitchen: TestClient) -> None:
    """An item with no amount, ticked, then "How much?": the change reads as a first
    amount, never "instead of 0 g" (cabledrawer 20 Oct, hand test)."""
    s = s0(kitchen)
    flour = food(kitchen, "Flour", counted_as="weight")["id"]
    item = new_id()
    send(kitchen, action("add", s.c0, list_id=s.main, item_id=item, food_id=flour))
    t = one(kitchen, "tick", counter(kitchen), item_id=item)
    assert t["change"] is None  # nothing went into the pantry
    done = one(
        kitchen,
        "different_pack",
        counter(kitchen),
        item_id=item,
        tick_id=t["id"],
        count=1,
        pack=1000,
    )
    assert done["status"] == "applied" and done["change"]["kind"] == "repacked"
    summary = done["change"]["summary"]
    assert summary == "Flour: bought 1\u00a0kg · 1\u00a0pack (first amount)"
    assert "instead of" not in summary


def test_sy16_different_pack_after_some_was_used(kitchen: TestClient) -> None:
    s = s0(kitchen)
    t = tick(kitchen, s, "Paneer")
    ok(
        s.remy.post(
            f"{API}/foods/{s.foods['Paneer']}/used", json={"amount": {"amount": 100, "unit": "g"}}
        )
    )
    one(
        kitchen,
        "different_pack",
        s.c0,
        item_id=s.items["Paneer"],
        tick_id=t["id"],
        count=1,
        pack=1000,
    )
    assert s.total("Paneer") == 900


def test_sy19_a_lost_tick_answer(kitchen: TestClient) -> None:
    s = s0(kitchen)
    first = tick(kitchen, s, "Toor dal")
    again = one(kitchen, "tick", s.c0, PHONE_A, id=first["id"], item_id=s.items["Toor dal"])
    assert again["repeat"] is True and again["seq"] == first["seq"]
    assert s.total("Toor dal") == 500


# --- Ticks against Clear ticked, deletes and old queues (L-9, L-10) ------------------------------


def _at(days: float = 0, seconds: float = 0) -> str:
    return (utcnow() + timedelta(days=days, seconds=seconds)).isoformat()


def _age(client: TestClient, action_id: str, days: float) -> None:
    """The action was applied `days` ago."""
    with db(client) as session:
        row = session.get(SyncAction, (1, action_id))
        row.applied_at = utcnow() - timedelta(days=days)
        session.commit()


def test_sy21_old_queue_after_clear_ticked(kitchen: TestClient) -> None:
    s = s0(kitchen)
    tick(kitchen, s, "Toor dal")
    one(kitchen, "delete", s.c0, item_id=s.items["Milk"])
    one(kitchen, "clear_ticked", s.c0, list_id=s.main, item_ids=[s.items["Toor dal"]])
    friday = _at(days=-3)
    eggs = new_id()
    answer = send(
        s.remy,
        action("tick", s.c0, item_id=s.items["Toor dal"], made_at=friday),
        action(
            "add",
            s.c0,
            list_id=s.main,
            item_id=eggs,
            food_id=s.foods["Eggs"],
            amount=6,
            made_at=friday,
        ),
        action("set_amount", s.c0, item_id=s.items["Milk"], amount=3000, made_at=friday),
        device=PHONE_R,
    )
    assert [r["status"] for r in answer["results"]] == ["applied", "applied", "ignored"]
    assert s.item(kitchen, "Toor dal", s.c0)["deleted"] is True
    assert item_row(changes(kitchen), eggs)["amount"] == 6
    assert s.item(kitchen, "Milk", s.c0)["deleted"] is True
    assert s.lots("Toor dal") == [("Cupboard", 500), ("Cupboard", 500)]
    assert len(_card(kitchen)) == 1 and len(_card(s.remy)) == 1
    assert changes(kitchen)["notes"] == []
    (note,) = changes(s.remy)["notes"]
    assert note["text"].startswith("Tess had removed Milk")


def test_sy22_queued_undo_counts_and_tick_on_a_delete(kitchen: TestClient) -> None:
    s = s0(kitchen)
    gone = one(kitchen, "delete", s.c0, item_id=s.items["Coriander"])
    _age(kitchen, gone["id"], 14)
    paneer = new_id()
    answer = send(
        s.remy,
        action("tick", s.c0, id=paneer, item_id=s.items["Paneer"], made_at=_at(days=-21)),
        action("undo", s.c0, undoes=paneer, made_at=_at(days=-21, seconds=10)),
        action("tick", s.c0, item_id=s.items["Coriander"], made_at=_at(days=-21, seconds=20)),
        device=PHONE_R,
    )
    assert [r["status"] for r in answer["results"]] == ["applied"] * 3
    assert s.total("Paneer") == 0 and s.ticks("Paneer") == []
    assert s.lots("Coriander") == [("Fridge", 1)]
    (note,) = changes(s.remy)["notes"]
    assert note["text"] == "Tess had removed this. Your tick still went into the pantry."
    assert changes(kitchen)["notes"] == []


def _undo_pressed(
    client: TestClient, target: str, pressed: str, sent: str, device: str = PHONE_R
) -> Any:
    answer = send(
        client, action("undo", 0, undoes=target, made_at=pressed), device=device, sent_at=sent
    )
    return answer["results"][0]


def test_sy22b_queued_undo_pressed_in_time(kitchen: TestClient) -> None:
    s = s0(kitchen)
    first = tick(s.remy, s, "Toor dal", PHONE_R)
    _age(kitchen, first["id"], 10)
    done = _undo_pressed(s.remy, first["id"], _at(days=-8), _at())
    assert done["status"] == "applied"
    assert s.total("Toor dal") == 0 and s.ticks("Toor dal") == []
    again = tick(s.remy, s, "Toor dal", PHONE_R)
    _age(kitchen, again["id"], 10)
    late = _undo_pressed(s.remy, again["id"], _at(days=-1), _at())
    assert (late["status"], late["reason"]) == ("ignored", "too_old")
    assert late["message"]
    assert s.total("Toor dal") == 500


@pytest.mark.parametrize("skew", [-30, 30], ids=["slow", "fast"])
def test_sy63_undo_window_with_a_wrong_clock(kitchen: TestClient, skew: int) -> None:
    s = s0(kitchen)
    first = tick(s.remy, s, "Toor dal", PHONE_R)
    _age(kitchen, first["id"], 3)
    done = _undo_pressed(s.remy, first["id"], _at(days=skew - 1), _at(days=skew))
    assert done["status"] == "applied"
    second = tick(s.remy, s, "Paneer", PHONE_R)
    _age(kitchen, second["id"], 10)
    late = _undo_pressed(s.remy, second["id"], _at(days=skew - 1), _at(days=skew))
    assert (late["status"], late["reason"]) == ("ignored", "too_old")
    assert s.total("Toor dal") == 0 and s.total("Paneer") == 400


# An impossible phone clock (year 1 or 9999) is ignored, as a missing one: never a 500, and the
# queue behind it still goes through (pre-beta security fix).
FIRST, LAST = "0001-01-01T00:00:00Z", "9999-12-31T23:59:59Z"
EAST, WEST = "0001-01-01T00:00:00+05:00", "9999-12-31T23:59:59-05:00"


@pytest.mark.parametrize(
    ("made", "sent"),
    [(FIRST, LAST), (LAST, FIRST), (EAST, WEST), (WEST, EAST), (FIRST, FIRST), (LAST, LAST)],
    ids=["1-9999", "9999-1", "1east-9999west", "9999west-1east", "1-1", "9999-9999"],
)
def test_undo_with_an_impossible_clock(kitchen: TestClient, made: str, sent: str) -> None:
    s = s0(kitchen)
    first = tick(s.remy, s, "Toor dal", PHONE_R)
    _age(kitchen, first["id"], 3)
    second = tick(s.remy, s, "Paneer", PHONE_R)
    _age(kitchen, second["id"], 10)
    answer = send(
        s.remy,
        action("undo", 0, undoes=first["id"], made_at=made),
        action("undo", 0, undoes=second["id"], made_at=made),
        action("tick", 0, item_id=s.items["Coriander"], made_at=made),
        device=PHONE_R,
        sent_at=sent,
    )
    done, late, after = answer["results"]
    assert done["status"] == "applied"  # pressed now: 3 days is inside the window
    assert (late["status"], late["reason"]) == ("ignored", "too_old")  # 10 days is not
    assert after["status"] == "applied"  # the next act in the queue still goes through
    assert s.total("Toor dal") == 0 and s.total("Paneer") == 400
    assert s.lots("Coriander") == [("Fridge", 1)]


# --- The card's answers (L-4) --------------------------------------------------------------------


def _after_sy01(s: S0) -> tuple[Any, Any, int]:
    """SY-01 (A→B), both synced: the two ticks and the card's ID."""
    a = tick(s.kitchen, s, "Toor dal", PHONE_A)
    b = tick(s.remy, s, "Toor dal", PHONE_R)
    s.c0 = int(changes(s.kitchen)["cursor"])
    (card,) = _card(s.kitchen)
    return a, b, int(card["id"])


def _answer(client: TestClient, s: S0, card: int, answer: str, device: str = PHONE_A) -> Any:
    return one(client, "answer_double_tick", s.c0, device, question_id=card, answer=answer)


def test_sy23_just_one_and_its_undo(kitchen: TestClient) -> None:
    s = s0(kitchen)
    a, _, card = _after_sy01(s)
    done = _answer(kitchen, s, card, "one")
    assert done["status"] == "applied"
    assert done["message"] == "Took back 1\u00a0packet Toor dal"
    assert s.lots("Toor dal") == [("Cupboard", 500)]
    (standing,) = s.ticks("Toor dal")
    assert standing.id == a["id"]
    assert _card(kitchen) == [] and _card(s.remy) == []
    assert _undo(kitchen, done["id"])["status"] == "applied"
    assert s.total("Toor dal") == 1000 and len(s.ticks("Toor dal")) == 2
    assert [q["id"] for q in _card(kitchen)] == [card]
    assert [q["id"] for q in _card(s.remy)] == [card]


def test_sy24_sy24u_just_one_after_some_was_used(kitchen: TestClient) -> None:
    s = s0(kitchen)
    _, _, card = _after_sy01(s)
    used = {"amount": {"amount": 800, "unit": "g"}}
    ok(s.remy.post(f"{API}/foods/{s.foods['Toor dal']}/used", json=used))
    assert s.lots("Toor dal") == [("Cupboard", 200)]
    done = _answer(kitchen, s, card, "one")
    assert done["message"] == (
        "Took back 200\u00a0g of the 500\u00a0g: the rest has been used since."
    )
    assert s.total("Toor dal") == 0
    assert [t.login_name for t in s.ticks("Toor dal")] == ["Tess"]
    # SY-24u: Undo puts back exactly what was taken out, into Remy's lot.
    assert _undo(kitchen, done["id"])["status"] == "applied"
    assert s.lots("Toor dal") == [("Cupboard", 200)]
    assert len(s.ticks("Toor dal")) == 2
    assert len(_card(kitchen)) == 1 and len(_card(s.remy)) == 1


@BOTH
def test_sy25_two_answers_offline(kitchen: TestClient, a_first: bool) -> None:
    s = s0(kitchen)
    _, _, card = _after_sy01(s)
    results: dict[str, Any] = {}
    _in_order(
        a_first,
        lambda: results.update(a=_answer(kitchen, s, card, "two")),
        lambda: results.update(b=_answer(s.remy, s, card, "one", PHONE_R)),
    )
    first, second = (results["a"], results["b"]) if a_first else (results["b"], results["a"])
    assert first["status"] == "applied"
    assert (second["status"], second["reason"]) == ("ignored", "answered")
    assert s.total("Toor dal") == (1000 if a_first else 500)
    assert _card(kitchen) == [] and _card(s.remy) == []


# --- Untick, and its Undo (7.2) ------------------------------------------------------------------


def test_sy26_sy26u_untick_after_some_was_used(kitchen: TestClient) -> None:
    s = s0(kitchen)
    t = tick(kitchen, s, "Toor dal")
    used = {"amount": {"amount": 200, "unit": "g"}}
    ok(s.remy.post(f"{API}/foods/{s.foods['Toor dal']}/used", json=used))
    off = one(kitchen, "untick", s.c0, item_id=s.items["Toor dal"], tick_ids=[t["id"]])
    assert off["message"] == (
        "Took back 300\u00a0g of the 500\u00a0g: the rest has been used since."
    )
    assert s.total("Toor dal") == 0
    assert not any(row["standing"] for row in s.item(kitchen, "Toor dal")["ticks"])
    # SY-26u
    before = len(s.changes_of("Toor dal", "shopped"))
    assert _undo(kitchen, off["id"])["status"] == "applied"
    assert s.lots("Toor dal") == [("Cupboard", 300)]
    shopped = s.changes_of("Toor dal", "shopped")
    assert len(shopped) == before + 1
    assert shopped[-1].summary == "Ticked again: 300\u00a0g Toor dal → Cupboard"
    assert [row["standing"] for row in s.item(kitchen, "Toor dal")["ticks"]] == [True]


def test_sy27_untick_naming_both_ticks(kitchen: TestClient) -> None:
    s = s0(kitchen)
    a, b, _ = _after_sy01(s)
    item = s.items["Toor dal"]
    done = one(s.remy, "untick", s.c0, PHONE_R, item_id=item, tick_ids=[a["id"], b["id"]])
    assert done["status"] == "applied"
    assert s.total("Toor dal") == 0 and s.ticks("Toor dal") == []
    assert _card(kitchen) == [] and _card(s.remy) == []


def test_sy27_variant_untick_naming_only_my_tick(kitchen: TestClient) -> None:
    s = s0(kitchen)
    a, b, _ = _after_sy01(s)
    one(kitchen, "untick", s.c0, item_id=s.items["Toor dal"], tick_ids=[a["id"]])
    assert s.total("Toor dal") == 500
    (standing,) = s.ticks("Toor dal")
    assert standing.id == b["id"]
    assert _card(kitchen) == [] and _card(s.remy) == []


@BOTH
def test_sy28_staple_ticked_on_both(kitchen: TestClient, a_first: bool) -> None:
    s = s0(kitchen)
    _in_order(
        a_first,
        lambda: tick(kitchen, s, "Salt", PHONE_A),
        lambda: tick(s.remy, s, "Salt", PHONE_R),
    )
    assert s.total("Salt") == 0 and s.changes_of("Salt", "shopped") == []
    assert len(s.ticks("Salt")) == 2
    assert _card(kitchen) == [] and _card(s.remy) == []


def test_sy29_clear_ticked_and_a_new_tick(kitchen: TestClient) -> None:
    s = s0(kitchen)
    tick(kitchen, s, "Toor dal")
    s.c0 = int(changes(kitchen)["cursor"])
    one(kitchen, "clear_ticked", s.c0, list_id=s.main, item_ids=[s.items["Toor dal"]])
    assert tick(s.remy, s, "Onions", PHONE_R)["status"] == "applied"
    assert s.item(kitchen, "Toor dal", s.c0)["deleted"] is True
    assert s.item(kitchen, "Onions")["ticks"][0]["standing"] is True
    assert s.lots("Toor dal") == [("Cupboard", 500)]
    assert s.lots("Onions") == [("Cupboard", 5)]


def test_sy30_tick_after_clear_ticked(kitchen: TestClient) -> None:
    s = s0(kitchen)
    tick(kitchen, s, "Toor dal")
    one(kitchen, "clear_ticked", s.c0, list_id=s.main, item_ids=[s.items["Toor dal"]])
    assert tick(s.remy, s, "Toor dal", PHONE_R)["status"] == "applied"
    assert s.item(kitchen, "Toor dal", s.c0)["deleted"] is True
    assert s.total("Toor dal") == 1000
    assert len(_card(kitchen)) == 1 and len(_card(s.remy)) == 1
    assert changes(kitchen)["notes"] == [] and changes(s.remy)["notes"] == []


def test_sy31_clear_ticked_and_undo(kitchen: TestClient) -> None:
    s = s0(kitchen)
    tick(kitchen, s, "Toor dal")
    tick(kitchen, s, "Paneer")
    cleared = one(
        kitchen,
        "clear_ticked",
        s.c0,
        list_id=s.main,
        item_ids=[s.items["Toor dal"], s.items["Paneer"]],
    )
    assert (s.total("Toor dal"), s.total("Paneer")) == (500, 400)
    assert _undo(kitchen, cleared["id"])["status"] == "applied"
    for name in ("Toor dal", "Paneer"):
        row = s.item(kitchen, name)
        assert row["deleted"] is False and row["ticks"][0]["standing"] is True
    assert (s.total("Toor dal"), s.total("Paneer")) == (500, 400)


def test_sy32_queue_hits_a_removed_list(kitchen: TestClient) -> None:
    s = s0(kitchen)
    party = new_id()
    crisps = food(kitchen, "Crisps", counted_as="count")["id"]
    lemonade = food(kitchen, "Lemonade", counted_as="count")["id"]
    ok(kitchen.patch(f"{API}/foods/{crisps}", json={"count_word": "bag"}))
    ok(kitchen.patch(f"{API}/foods/{lemonade}", json={"count_word": "bottle"}))
    items = {"crisps": new_id(), "lemonade": new_id(), "candles": new_id()}
    send(
        kitchen,
        action("create_list", list_id=party, name="Party on Saturday"),
        action("add", list_id=party, item_id=items["crisps"], food_id=crisps, amount=2),
        action("add", list_id=party, item_id=items["lemonade"], food_id=lemonade, amount=2),
    )
    seen = int(changes(kitchen)["cursor"])
    removed = one(kitchen, "remove_list", seen, list_id=party)
    answer = send(
        s.remy,
        action("tick", seen, item_id=items["crisps"]),
        action(
            "add",
            seen,
            list_id=party,
            item_id=items["candles"],
            new_food={"name": "Candles", "counted_as": "count", "staple": True},
        ),
        action("set_amount", seen, item_id=items["lemonade"], amount=3),
        device=PHONE_R,
    )
    assert [r["status"] for r in answer["results"]] == ["applied"] * 3
    assert [lot for lot in _lots_of(kitchen, crisps)] == [2]
    (note,) = changes(s.remy)["notes"]
    assert note["text"] == (
        "Tess had removed Party on Saturday. Your changes are kept with it."
        " Your ticks still went into the pantry."
    )
    assert changes(kitchen)["notes"] == []
    assert note["undo"] == removed["id"]
    assert _undo(s.remy, note["undo"], PHONE_R)["status"] == "applied"
    copy = changes(kitchen)
    assert next(row for row in copy["lists"] if row["id"] == party)["removed"] is False
    assert item_row(copy, items["crisps"])["ticks"][0]["standing"] is True
    assert item_row(copy, items["candles"])["deleted"] is False
    assert item_row(copy, items["lemonade"])["amount"] == 3


def _lots_of(client: TestClient, food_id: int) -> list[int]:
    with db(client) as session:
        rows = session.scalars(
            select(StockLot)
            .where(StockLot.food_id == food_id, StockLot.amount_milli > 0)
            .order_by(StockLot.id)
        ).all()
        return [row.amount_milli // 1000 for row in rows]


# --- Undo from the toast and from Pantry (7.2, 5.8) ----------------------------------------------


def _pantry_undo(client: TestClient, change_id: int) -> Any:
    return ok(client.post(f"{API}/changes/{change_id}/undo"))


def test_sy36_pantry_undo_of_a_purchase(kitchen: TestClient) -> None:
    s = s0(kitchen)
    t = tick(kitchen, s, "Toor dal")
    assert t["change"]["summary"] == "Bought 1\u00a0packet Toor dal → Cupboard"
    s.c0 = int(changes(kitchen)["cursor"])
    _pantry_undo(s.remy, t["change"]["id"])
    assert s.total("Toor dal") == 0
    row = s.item(kitchen, "Toor dal", s.c0)
    assert [tick_row["standing"] for tick_row in row["ticks"]] == [False]
    assert _undo(kitchen, t["id"])["reason"] == "already_undone"


def test_sy37_undo_a_tick_from_the_toast(kitchen: TestClient) -> None:
    s = s0(kitchen)
    t = tick(kitchen, s, "Toor dal")
    assert _undo(kitchen, t["id"])["status"] == "applied"
    assert s.total("Toor dal") == 0 and s.ticks("Toor dal") == []


def test_sy38_untick_after_clear_ticked(kitchen: TestClient) -> None:
    s = s0(kitchen)
    t = tick(kitchen, s, "Toor dal")
    s.c0 = int(changes(kitchen)["cursor"])
    one(kitchen, "clear_ticked", s.c0, list_id=s.main, item_ids=[s.items["Toor dal"]])
    off = one(s.remy, "untick", s.c0, PHONE_R, item_id=s.items["Toor dal"], tick_ids=[t["id"]])
    assert off["status"] == "applied"
    assert s.item(kitchen, "Toor dal", s.c0)["deleted"] is True
    assert s.total("Toor dal") == 0
    (note,) = changes(s.remy)["notes"]
    assert note["text"] == (
        "Tess had removed this, so it isn’t back on the list."
        " Your untick took it out of the pantry."
    )
    assert _undo(s.remy, note["undo"], PHONE_R)["status"] == "applied"
    assert s.total("Toor dal") == 500
    assert s.item(kitchen, "Toor dal", s.c0)["deleted"] is True


def test_sy38_no_n5_when_it_had_all_been_used(kitchen: TestClient) -> None:
    """N5 says "Your untick took it out of the pantry": only when it did (8)."""
    s = s0(kitchen)
    t = tick(kitchen, s, "Toor dal")
    s.c0 = int(changes(kitchen)["cursor"])
    one(kitchen, "clear_ticked", s.c0, list_id=s.main, item_ids=[s.items["Toor dal"]])
    used = {"amount": {"amount": 500, "unit": "g"}}
    ok(kitchen.post(f"{API}/foods/{s.foods['Toor dal']}/used", json=used))
    off = one(s.remy, "untick", s.c0, PHONE_R, item_id=s.items["Toor dal"], tick_ids=[t["id"]])
    assert off["status"] == "applied"
    assert s.ticks("Toor dal") == []
    assert changes(s.remy)["notes"] == []


def test_just_1_keeps_the_first_purchase_in_server_order(kitchen: TestClient) -> None:
    """L-3: server order is the counter's, not the server clock's."""
    s = s0(kitchen)
    first = tick(kitchen, s, "Toor dal")
    tick(s.remy, s, "Toor dal", PHONE_R)
    with db(kitchen) as session:  # the clock stepped back between the two
        row = session.get(ListTick, (1, first["id"]))
        row.ticked_at = utcnow() + timedelta(hours=1)
        session.commit()
    (card,) = s.questions(kitchen)
    one(kitchen, "answer_double_tick", question_id=card["id"], answer="one")
    assert [t.login_name for t in s.ticks("Toor dal")] == ["Tess"]


# --- Where a purchase goes (7.1, 7.3) ------------------------------------------------------------


def test_sy46_where_ticks_go(kitchen: TestClient) -> None:
    s = s0(kitchen)
    tick(kitchen, s, "Onions")
    tick(kitchen, s, "Toor dal")
    one(
        kitchen,
        "put_away",
        s.c0,
        item_id=s.items["Coriander"],
        place_id=s.places["Freezer"],
        tick_ids=[],
    )
    tick(kitchen, s, "Coriander")
    assert s.lots("Onions") == [("Cupboard", 5)]
    assert s.lots("Toor dal") == [("Cupboard", 500)]
    assert s.lots("Coriander") == [("Freezer", 1)]
    with db(kitchen) as session:
        assert all(lot.use_by is None for lot in session.scalars(select(StockLot)))


def test_sy47_tick_with_a_merged_item_id(kitchen: TestClient) -> None:
    s = s0(kitchen)
    mine, hers = new_id(), new_id()
    eggs = s.foods["Eggs"]
    one(kitchen, "add", s.c0, list_id=s.main, item_id=mine, food_id=eggs, amount=6)
    merged = one(
        s.remy, "add", s.c0, PHONE_R, list_id=s.main, item_id=hers, food_id=eggs, amount=12
    )
    assert merged["status"] == "merged" and merged["item_id"] == mine
    done = one(s.remy, "tick", s.c0, PHONE_R, item_id=hers)
    assert done["status"] == "applied" and done["item_id"] == mine
    assert item_row(changes(kitchen), mine)["ticks"][0]["standing"] is True
    assert s.total("Eggs") == 12


def test_sy49_pantry_undo_of_a_different_pack(kitchen: TestClient) -> None:
    s = s0(kitchen)
    t = tick(kitchen, s, "Paneer")
    item = s.items["Paneer"]
    repack = one(kitchen, "different_pack", s.c0, item_id=item, tick_id=t["id"], count=1, pack=1000)
    assert s.total("Paneer") == 1000
    _pantry_undo(kitchen, repack["change"]["id"])
    assert s.lots("Paneer") == [("Fridge", 200), ("Fridge", 200)]
    row = s.item(kitchen, "Paneer")
    assert row["ticks"][0]["standing"] is True
    assert row["ticks"][0]["bought"]["amount"] == 400


def _repacked_twice(
    kitchen: TestClient,
) -> tuple[Any, dict[str, Any], dict[str, Any], dict[str, Any]]:
    s = s0(kitchen)
    t = tick(kitchen, s, "Paneer")
    item = s.items["Paneer"]
    first = one(kitchen, "different_pack", s.c0, item_id=item, tick_id=t["id"], count=1, pack=400)
    later = one(kitchen, "different_pack", s.c0, item_id=item, tick_id=t["id"], count=4, pack=200)
    assert s.total("Paneer") == 800
    return s, t, first, later


def _counts_as_undone(kitchen: TestClient, later: dict[str, Any]) -> None:
    """The later different_pack counts as undone: its own Undo has nothing left to do."""
    assert _undo(kitchen, later["id"])["reason"] == "already_undone"
    with db(kitchen) as session:
        assert session.get(SyncAction, (1, later["id"])).undone_by_action_id is not None


def test_undo_of_an_older_different_pack_undoes_the_later_ones_too(kitchen: TestClient) -> None:
    s, _, first, later = _repacked_twice(kitchen)
    done = _undo(kitchen, first["id"])
    assert done["status"] == "applied"
    assert s.lots("Paneer") == [("Fridge", 200), ("Fridge", 200)]
    assert s.item(kitchen, "Paneer")["ticks"][0]["bought"]["amount"] == 400
    _counts_as_undone(kitchen, later)


def test_pantry_undo_of_an_older_different_pack_undoes_the_later_ones_too(
    kitchen: TestClient,
) -> None:
    s, _, first, later = _repacked_twice(kitchen)
    _pantry_undo(kitchen, first["change"]["id"])
    assert s.lots("Paneer") == [("Fridge", 200), ("Fridge", 200)]
    assert s.item(kitchen, "Paneer")["ticks"][0]["bought"]["amount"] == 400
    assert [c.kind for c in s.changes_of("Paneer")].count("repacked") == 2
    _counts_as_undone(kitchen, later)


def _repacked_with_use_between(kitchen: TestClient) -> dict[str, Any]:
    s = s0(kitchen)
    t = tick(kitchen, s, "Paneer")
    item = s.items["Paneer"]
    first = one(kitchen, "different_pack", s.c0, item_id=item, tick_id=t["id"], count=1, pack=400)
    used = {"amount": {"amount": 100, "unit": "g"}}
    ok(kitchen.post(f"{API}/foods/{s.foods['Paneer']}/used", json=used))
    one(kitchen, "different_pack", s.c0, item_id=item, tick_id=t["id"], count=1, pack=1000)
    return first


BACK = (
    "Paneer is back to 400\u00a0g · 2\u00a0packs."
    " Some had been used since, so check how much is left."
)


def test_an_undo_of_a_different_pack_after_a_use_says_so_for_a_pack_change(
    kitchen: TestClient,
) -> None:
    """7.4 item 6 (cabledrawer 18 Oct): nothing was "taken back", so it doesn't say that."""
    first = _repacked_with_use_between(kitchen)
    done = _undo(kitchen, first["id"])
    assert done["status"] == "applied" and done["message"] == BACK


def test_a_pantry_undo_of_a_different_pack_after_a_use_says_so_too(kitchen: TestClient) -> None:
    first = _repacked_with_use_between(kitchen)
    assert _pantry_undo(kitchen, first["change"]["id"])["message"] == BACK


def test_an_undo_with_the_purchase_already_as_it_was_skips_nothing(kitchen: TestClient) -> None:
    s = s0(kitchen)
    t = tick(kitchen, s, "Paneer")
    item = s.items["Paneer"]
    repack = one(kitchen, "different_pack", s.c0, item_id=item, tick_id=t["id"], count=1, pack=400)
    with db(kitchen) as session:  # as a put-back leaves it (7.5)
        row = session.get(ListTick, (1, t["id"]))
        old = (session.get(Change, repack["change"]["id"]).undo_data or {})["shopping"][0]["old"]
        row.bought_milli, row.bought_size_id = old
        session.commit()
    done = _pantry_undo(kitchen, repack["change"]["id"])
    assert done["result"] == "done", done
    assert s.lots("Paneer") == [("Fridge", 200), ("Fridge", 200)]


def test_sy50_pantry_undo_of_the_purchase_after_a_different_pack(kitchen: TestClient) -> None:
    s = s0(kitchen)
    t = tick(kitchen, s, "Paneer")
    one(
        kitchen,
        "different_pack",
        s.c0,
        item_id=s.items["Paneer"],
        tick_id=t["id"],
        count=1,
        pack=1000,
    )
    _pantry_undo(kitchen, t["change"]["id"])
    assert s.total("Paneer") == 0
    assert s.ticks("Paneer") == []


def test_sy51_pantry_undo_of_a_put_away(kitchen: TestClient) -> None:
    s = s0(kitchen)
    t = tick(kitchen, s, "Coriander")
    put = one(
        kitchen,
        "put_away",
        s.c0,
        item_id=s.items["Coriander"],
        place_id=s.places["Freezer"],
        tick_ids=[t["id"]],
    )
    s.c0 = int(changes(kitchen)["cursor"])
    _pantry_undo(kitchen, put["change"]["id"])
    assert s.lots("Coriander") == [("Fridge", 1)]
    row = s.item(s.remy, "Coriander", s.c0)
    assert row["put_away_place_id"] is None
    assert row["ticks"][0]["place_id"] == s.places["Fridge"]
    assert row["ticks"][0]["standing"] is True


def test_sy55_put_away_to_a_removed_place(kitchen: TestClient) -> None:
    s = s0(kitchen)
    with db(kitchen) as session:  # no endpoint removes a place yet (0.8)
        session.delete(session.get(Place, s.places["Spice rack"]))
        session.commit()
    answer = send(
        s.remy,
        action(
            "put_away",
            s.c0,
            item_id=s.items["Coriander"],
            place_id=s.places["Spice rack"],
            tick_ids=[],
        ),
        action("tick", s.c0, item_id=s.items["Coriander"]),
        device=PHONE_R,
    )
    assert answer["results"][1]["status"] == "applied"
    row = s.item(kitchen, "Coriander")
    assert row["put_away_place_id"] is None and row["ticks"][0]["standing"] is True
    assert s.lots("Coriander") == [("Fridge", 1)]


def test_sy62_tick_again_after_signing_back_in(kitchen: TestClient) -> None:
    s = s0(kitchen)
    assert tick(s.remy, s, "Toor dal", PHONE_R)["status"] == "applied"
    assert s.remy.delete(f"{API}/session").status_code == 204
    queued = action("tick", s.c0, item_id=s.items["Toor dal"])
    assert s.remy.post(f"{API}/shopping/actions", json={}).status_code == 401
    ok(s.remy.post(f"{API}/session", json={"username": "remy", "password": REMY_PASSWORD}))
    (again,) = send(s.remy, queued, device=PHONE_R)["results"]
    assert (again["status"], again["reason"]) == ("ignored", "already_ticked")
    assert s.total("Toor dal") == 500 and _card(s.remy) == []


def test_sy15c_a_count_with_no_amount_gets_n_items_and_no_pack_size(kitchen: TestClient) -> None:
    """How much? for whole things (1 · 2 · 6 · 12) is N items, not "a pack of N" (K5, fix 1)."""
    s = s0(kitchen)
    onions = food(kitchen, "Spring onions", counted_as="count")["id"]
    item = new_id()
    send(kitchen, action("add", s.c0, list_id=s.main, item_id=item, food_id=onions))
    t = one(kitchen, "tick", counter(kitchen), item_id=item)
    done = one(
        kitchen,
        "different_pack",
        counter(kitchen),
        item_id=item,
        tick_id=t["id"],
        count=1,
        pack=6,
    )
    assert done["status"] == "applied"
    with db(kitchen) as session:
        lots = [lot.amount_milli for lot in session.query(StockLot).filter_by(food_id=onions)]
        assert [n for n in lots if n] == [6000]
        assert session.query(FoodSize).filter_by(food_id=onions).count() == 0
    answer = changes(kitchen)
    row = next(f for f in answer["foods"] if f["id"] == onions)
    assert row["sizes"] == []
    assert "pack" not in done["change"]["summary"]


def test_sy15d_a_count_is_worded_without_left(kitchen: TestClient) -> None:
    """Whole things read "bought 12 instead of 6", never "6 left" (trial job 3)."""
    s = s0(kitchen)
    onions = food(kitchen, "Spring onions", counted_as="count")["id"]
    item = new_id()
    send(kitchen, action("add", s.c0, list_id=s.main, item_id=item, food_id=onions))
    t = one(kitchen, "tick", counter(kitchen), item_id=item)
    first = one(
        kitchen, "different_pack", counter(kitchen), item_id=item, tick_id=t["id"], count=1, pack=6
    )
    assert first["change"]["summary"] == "Spring onions: bought 6 instead of 1"
    again = one(
        kitchen, "different_pack", counter(kitchen), item_id=item, tick_id=t["id"], count=1, pack=12
    )
    assert again["change"]["summary"] == "Spring onions: bought 12 instead of 6"


def test_sy15e_an_undo_for_a_count_is_worded_without_left(kitchen: TestClient) -> None:
    """The Undo message for whole things never says "1 left" (job 3 review, L2)."""
    s = s0(kitchen)
    onions = food(kitchen, "Spring onions", counted_as="count")["id"]
    item = new_id()
    send(kitchen, action("add", s.c0, list_id=s.main, item_id=item, food_id=onions))
    t = one(kitchen, "tick", counter(kitchen), item_id=item)
    first = one(
        kitchen, "different_pack", counter(kitchen), item_id=item, tick_id=t["id"], count=1, pack=6
    )
    used = {"amount": {"amount": 2, "unit": "count"}}
    ok(kitchen.post(f"{API}/foods/{onions}/used", json=used))
    done = _undo(kitchen, first["id"])
    assert done["status"] == "applied", done
    assert done["message"] == (
        "Spring onions is back to 1. Some had been used since, so check how much is left."
    )
