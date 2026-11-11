"""The history job's tidy-up of the shopping lists (docs/dev/sync-protocol.md section 3.9),
and what an old queue meets afterwards (SY-58, SY-59)."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sync_kit import (
    API,
    PHONE_R,
    S0,
    action,
    changes,
    counter,
    db,
    new_id,
    ok,
    one,
    s0,
    send,
    tick,
)

from mealwright.history import purge_removed, tidy_lists
from mealwright.models import (
    Change,
    DoubleTick,
    Food,
    Household,
    ListItem,
    ListNote,
    ListTick,
    ShoppingList,
    SyncAction,
    utcnow,
)


def _tidy(client: TestClient) -> int:
    with db(client) as session:
        return tidy_lists(session, session.get(Household, 1))


def _purge(client: TestClient) -> int:
    with db(client) as session:
        return purge_removed(session, session.get(Household, 1))


def _ago(days: float) -> Any:
    return utcnow() - timedelta(days=days)


def _after_sy01(s: S0) -> int:
    """SY-01 (A→B), both synced: the card's ID."""
    tick(s.kitchen, s, "Toor dal")
    tick(s.remy, s, "Toor dal", PHONE_R)
    s.c0 = int(changes(s.kitchen)["cursor"])
    (card,) = [q for q in changes(s.kitchen)["questions"] if q["open"]]
    return int(card["id"])


def test_old_notes_and_closed_questions_go(kitchen: TestClient) -> None:
    s = s0(kitchen)
    card = _after_sy01(s)
    one(kitchen, "delete", s.c0, item_id=s.items["Paneer"])
    tick(s.remy, s, "Paneer", PHONE_R)  # N1 for Remy
    (note,) = changes(s.remy)["notes"]
    assert _tidy(kitchen) == 0  # both still new
    one(kitchen, "answer_double_tick", s.c0, question_id=card, answer="two")
    with db(kitchen) as session:
        session.execute(update(ListNote).values(created_at=_ago(8)))
        session.execute(update(DoubleTick).values(answered_at=_ago(8)))
        session.commit()
    assert _tidy(kitchen) == 2
    with db(kitchen) as session:
        assert session.get(ListNote, note["id"]) is None
        assert session.get(DoubleTick, card) is None
    assert changes(s.remy)["notes"] == [] and changes(s.remy)["questions"] == []


def test_open_questions_and_new_notes_stay(kitchen: TestClient) -> None:
    s = s0(kitchen)
    card = _after_sy01(s)
    with db(kitchen) as session:
        session.execute(update(DoubleTick).values(created_at=_ago(30)))
        session.commit()
    _tidy(kitchen)
    with db(kitchen) as session:
        assert session.get(DoubleTick, card) is not None


def test_old_tombstones_go_with_their_ticks(kitchen: TestClient) -> None:
    s = s0(kitchen)
    bought = tick(kitchen, s, "Paneer")
    one(kitchen, "clear_ticked", s.c0, list_id=s.main, item_ids=[s.items["Paneer"]])
    behind = counter(kitchen)
    one(kitchen, "delete", s.c0, item_id=s.items["Milk"])
    with db(kitchen) as session:
        version = session.get(ListItem, s.items["Milk"]).version
        session.execute(
            update(ListItem)
            .where(ListItem.id.in_([s.items["Paneer"], s.items["Milk"]]))
            .values(deleted_at=_ago(400))
        )
        session.commit()
    assert _tidy(kitchen) == 2
    with db(kitchen) as session:
        assert session.get(ListItem, s.items["Paneer"]) is None
        assert session.get(ListTick, (1, bought["id"])) is None
        shopped = session.get(Change, bought["change"]["id"])
        assert shopped is not None and shopped.tick_id is None  # the history stays
        assert session.get(Household, 1).list_purged_seq == version
        assert session.get(ListItem, s.items["Onions"]) is not None
    assert s.total("Paneer") == 400  # the pantry is untouched
    answer = changes(kitchen, behind)
    assert answer["reset"] is True
    assert s.items["Milk"] not in {row["id"] for row in answer["items"]}
    assert changes(kitchen, version)["reset"] is False


def test_old_removed_lists_go_with_their_items(kitchen: TestClient) -> None:
    s = s0(kitchen)
    party, crisps = new_id(), new_id()
    send(
        kitchen,
        action("create_list", list_id=party, name="Party"),
        action("add", list_id=party, item_id=crisps, food_id=s.foods["Eggs"], amount=6),
    )
    one(kitchen, "remove_list", list_id=party)
    with db(kitchen) as session:
        session.execute(update(ShoppingList).values(removed_at=_ago(400)))  # main: never
        session.commit()
    _tidy(kitchen)
    with db(kitchen) as session:
        assert session.get(ShoppingList, party) is None
        assert session.get(ListItem, crisps) is None
        assert session.get(ShoppingList, s.main) is not None


def test_old_sync_log_rows_are_kept_but_emptied(kitchen: TestClient) -> None:
    s = s0(kitchen)
    first = action("tick", s.c0, item_id=s.items["Toor dal"])
    (done,) = send(kitchen, first)["results"]
    with db(kitchen) as session:
        session.execute(update(SyncAction).values(applied_at=_ago(400)))
        session.commit()
    _tidy(kitchen)
    with db(kitchen) as session:
        row = session.get(SyncAction, (1, first["id"]))
        assert row is not None and row.payload == {} and row.result == {}
        assert row.seq == done["seq"] and row.kind == "tick" and row.status == "applied"
    (again,) = send(kitchen, first)["results"]
    assert again["repeat"] is True and again["seq"] == done["seq"]
    assert s.total("Toor dal") == 500


def test_a_purge_takes_a_number_and_resets_phones(kitchen: TestClient) -> None:
    s = s0(kitchen)
    ok(kitchen.delete(f"{API}/foods/{s.foods['Eggs']}"))
    with db(kitchen) as session:
        session.execute(update(Food).where(Food.id == s.foods["Eggs"]).values(removed_at=_ago(9)))
        session.commit()
    before = counter(kitchen)
    assert _purge(kitchen) == 1
    assert counter(kitchen) == before + 1
    with db(kitchen) as session:
        assert session.get(Household, 1).list_purged_seq == before + 1
        purge = session.scalar(select(SyncAction).where(SyncAction.kind == "purge"))
        assert purge is not None and purge.seq == before + 1
        assert purge.payload == {"foods": {str(s.foods["Eggs"]): "Eggs"}}
    assert changes(kitchen, before)["reset"] is True
    assert changes(kitchen, before + 1)["reset"] is False


def test_sy58_an_old_queue_after_the_tidy_up(kitchen: TestClient) -> None:
    s = s0(kitchen)
    card = _after_sy01(s)
    one(kitchen, "delete", s.c0, item_id=s.items["Paneer"])
    paneer = tick(s.remy, s, "Paneer", PHONE_R)
    (note,) = changes(s.remy)["notes"]
    seen = counter(kitchen)
    one(kitchen, "answer_double_tick", seen, question_id=card, answer="two")
    with db(kitchen) as session:  # 8 days on; the Paneer tombstone's tidy-up is due
        session.execute(update(ListNote).values(created_at=_ago(8)))
        session.execute(update(DoubleTick).values(answered_at=_ago(8)))
        session.execute(
            update(ListItem).where(ListItem.id == s.items["Paneer"]).values(deleted_at=_ago(400))
        )
        session.commit()
    _tidy(kitchen)
    answer = send(
        s.remy,
        action("dismiss_note", seen, note_id=note["id"]),
        action("answer_double_tick", seen, question_id=card, answer="one"),
        action("untick", seen, item_id=s.items["Paneer"], tick_ids=[paneer["id"]]),
        device=PHONE_R,
    )
    results = answer["results"]
    assert [(r["status"], r["reason"]) for r in results] == [("ignored", "gone")] * 3
    assert results[0]["message"] is None  # no toast for the note
    assert s.total("Toor dal") == 1000 and s.total("Paneer") == 400


def test_sy59_answer_after_the_card_and_an_ingredient_went(kitchen: TestClient) -> None:
    s = s0(kitchen)
    card = _after_sy01(s)
    one(kitchen, "answer_double_tick", s.c0, question_id=card, answer="one")
    ok(kitchen.delete(f"{API}/foods/{s.foods['Eggs']}"))
    with db(kitchen) as session:  # day 10: Eggs went for good on day 8
        session.execute(update(Food).where(Food.id == s.foods["Eggs"]).values(removed_at=_ago(10)))
        session.execute(update(DoubleTick).values(answered_at=_ago(10)))
        session.commit()
    _purge(kitchen)
    _tidy(kitchen)
    answer = send(
        s.remy,
        action("answer_double_tick", s.c0, question_id=card, answer="two"),
        device=PHONE_R,
        since=s.c0,
    )
    ((status, reason),) = [(r["status"], r["reason"]) for r in answer["results"]]
    assert (status, reason) == ("ignored", "gone")
    copy = answer["changes"]
    assert copy["reset"] is True and copy["questions"] == []
    assert s.foods["Eggs"] not in {row["id"] for row in copy["foods"]}
    assert s.total("Toor dal") == 500
    assert [t.login_name for t in s.ticks("Toor dal")] == ["Tess"]


def test_an_add_that_joined_a_tidied_line_is_gone(kitchen: TestClient) -> None:
    s = s0(kitchen)
    hers = new_id()
    added = one(s.remy, "add", s.c0, PHONE_R, list_id=s.main, item_id=hers, food_id=s.foods["Milk"])
    assert added["status"] == "merged" and added["item_id"] == s.items["Milk"]
    one(kitchen, "delete", s.c0, item_id=s.items["Milk"])
    with db(kitchen) as session:
        session.execute(
            update(ListItem).where(ListItem.id == s.items["Milk"]).values(deleted_at=_ago(400))
        )
        session.commit()
    _tidy(kitchen)
    with db(kitchen) as session:  # no foreign key: it points at nothing now
        assert session.get(ListItem, hers).merged_into_id == s.items["Milk"]
        assert session.get(ListItem, s.items["Milk"]) is None
    seen = counter(kitchen)
    answer = send(
        s.remy,
        action("set_amount", seen, item_id=hers, amount=3000),
        action("delete", seen, item_id=hers),
        action("undo", seen, undoes=added["id"]),
        device=PHONE_R,
    )
    results = [(r["status"], r["reason"]) for r in answer["results"]]
    # Its Undo too: the line it joined is gone for good (5.9).
    assert results == [("ignored", "gone"), ("ignored", "gone"), ("ignored", "gone")]
    assert changes(s.remy)["reset"] is True
