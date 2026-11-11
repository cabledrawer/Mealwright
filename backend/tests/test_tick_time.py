"""An offline Shopping tick keeps the phone's time, unless that time is in the future or clearly
wrong, then the server's time (cabledrawer 2 Nov; sync-protocol.md, ticks)."""

from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import API, PHONE_A, PHONE_B, PHONE_R, action, db, ok, s0, send

from mealwright.history import as_utc
from mealwright.models import ListItem, ListTick, StockLot, utcnow

FIRST, LAST = "0001-01-01T00:00:00Z", "9999-12-31T23:59:59Z"


def _iso(days: float = 0, seconds: float = 0) -> str:
    return (utcnow() + timedelta(days=days, seconds=seconds)).isoformat()


def _tick_at(
    client: TestClient, s: Any, name: str, made: str | None, sent: str | None = None
) -> Any:
    fields: dict[str, Any] = {"item_id": s.items[name]}
    if made is not None:
        fields["made_at"] = made
    row = action("tick", s.c0, **fields)
    if made is None:
        del row["made_at"]
    return send(client, row, device=PHONE_R, sent_at=sent)["results"][0]


def _times(s: Any, name: str) -> tuple[datetime, datetime, datetime]:
    """The tick's moment, the item's copy of it, and when its lot was added."""
    with db(s.kitchen) as session:
        tick = session.scalars(select(ListTick).where(ListTick.item_id == s.items[name])).one()
        item = session.get(ListItem, s.items[name])
        lot = session.scalars(select(StockLot).where(StockLot.food_id == s.foods[name])).first()
        assert item is not None and item.ticked_at is not None and lot is not None
        return as_utc(tick.ticked_at), as_utc(item.ticked_at), as_utc(lot.added_at)


def _near(found: datetime, wanted: datetime) -> bool:
    return abs(found - wanted) < timedelta(seconds=5)


def test_an_offline_tick_keeps_the_phones_time(kitchen: TestClient) -> None:
    s = s0(kitchen)
    monday = utcnow() - timedelta(days=2)
    done = _tick_at(s.remy, s, "Toor dal", monday.isoformat(), sent_at_now())
    assert done["status"] == "applied"
    ticked, copy, added = _times(s, "Toor dal")
    assert _near(ticked, monday) and ticked == copy == added


def sent_at_now() -> str:
    return utcnow().isoformat()


def test_a_phone_clock_two_hours_fast_is_corrected(kitchen: TestClient) -> None:
    s = s0(kitchen)
    # The phone thinks it is 2 hours later than the server; the tick was pressed 1 day ago by
    # the server's clock.
    skew = timedelta(hours=2)
    sent = utcnow() + skew
    made = sent - timedelta(days=1)
    _tick_at(s.remy, s, "Toor dal", made.isoformat(), sent.isoformat())
    ticked, copy, added = _times(s, "Toor dal")
    assert _near(ticked, utcnow() - timedelta(days=1)) and ticked == copy == added


@pytest.mark.parametrize(
    "made",
    [_iso(days=1), _iso(days=-30), FIRST, LAST],
    ids=["future", "30-days-back", "year-1", "year-9999"],
)
def test_a_wrong_phone_time_uses_the_servers(kitchen: TestClient, made: str | None) -> None:
    s = s0(kitchen)
    done = _tick_at(s.remy, s, "Toor dal", made, sent_at_now())
    assert done["status"] == "applied"
    ticked, copy, added = _times(s, "Toor dal")
    assert _near(ticked, datetime.now(UTC)) and ticked == copy == added


@pytest.mark.parametrize("sent", [FIRST, LAST], ids=["sent-year-1", "sent-year-9999"])
def test_an_impossible_sent_time_is_never_a_500(kitchen: TestClient, sent: str) -> None:
    s = s0(kitchen)
    done = _tick_at(s.remy, s, "Toor dal", _iso(days=-1), sent)
    assert done["status"] == "applied"
    ticked, _, _ = _times(s, "Toor dal")
    assert _near(ticked, datetime.now(UTC))


def _type(client: TestClient, food: int, when: datetime) -> None:
    ok(client.patch(f"{API}/foods/{food}", json={"restocked_at": when.isoformat()}))


def _restocked(client: TestClient, food: int) -> datetime | None:
    found = ok(client.get(f"{API}/foods/{food}"))["restocked_at"]
    return datetime.fromisoformat(found).astimezone(UTC) if found else None


def test_a_tick_made_before_the_typed_date_no_longer_counts(kitchen: TestClient) -> None:
    """Ticked offline on Monday, synced after Saturday's date was typed: the typed date wins."""
    s = s0(kitchen)
    salt = s.foods["Salt"]
    saturday = utcnow() - timedelta(days=3)
    _type(kitchen, salt, saturday)
    monday = utcnow() - timedelta(days=5)
    _tick_at(s.remy, s, "Salt", monday.isoformat(), sent_at_now())
    found = _restocked(kitchen, salt)
    assert found is not None and _near(found, saturday)


def test_a_tick_made_after_the_typed_date_still_wins(kitchen: TestClient) -> None:
    """The typed date counts from the moment it was typed: a tick pressed after that wins."""
    s = s0(kitchen)
    salt = s.foods["Salt"]
    _type(kitchen, salt, utcnow() - timedelta(days=3))
    pressed = utcnow()
    _tick_at(s.remy, s, "Salt", pressed.isoformat(), sent_at_now())
    found = _restocked(kitchen, salt)
    assert found is not None and _near(found, pressed)


def test_a_missing_phone_time_is_the_servers() -> None:
    from types import SimpleNamespace

    from mealwright.sync import happened_at

    for made, sent in ((None, utcnow()), (utcnow(), None), (None, None)):
        act: Any = SimpleNamespace(made_at=made, sent_at=sent)
        assert _near(happened_at(act), datetime.now(UTC))


def _zone(moment: datetime, hours: int) -> str:
    """The same moment written with a UTC offset, as a phone in another zone sends it."""
    return moment.astimezone(timezone(timedelta(hours=hours))).isoformat()


@pytest.mark.parametrize("hours", [14, -12], ids=["plus-14", "minus-12"])
def test_a_phone_time_with_an_offset_lands_at_the_real_moment(
    kitchen: TestClient, hours: int
) -> None:
    """A made_at and sent_at written with +14:00 or -12:00 are the same moment as in UTC: the
    tick is not stored as wall-clock time, up to 14 hours late (security pass, 2 Nov)."""
    s = s0(kitchen)
    pressed = utcnow() - timedelta(hours=3)
    _tick_at(s.remy, s, "Toor dal", _zone(pressed, hours), _zone(utcnow(), hours))
    ticked, copy, added = _times(s, "Toor dal")
    assert _near(ticked, pressed) and ticked == copy == added
    assert ticked <= datetime.now(UTC)


@pytest.mark.parametrize("hours", [14, -12], ids=["plus-14", "minus-12"])
def test_undo_pressed_at_is_right_with_an_offset(hours: int) -> None:
    from types import SimpleNamespace

    from mealwright.sync import pressed_at

    applied = utcnow() - timedelta(hours=5)
    pressed = utcnow() - timedelta(hours=1)
    act: Any = SimpleNamespace(
        made_at=datetime.fromisoformat(_zone(pressed, hours)),
        sent_at=datetime.fromisoformat(_zone(utcnow(), hours)),
    )
    found = pressed_at(act, applied)
    assert _near(found, pressed) and found.utcoffset() == timedelta(0)


def _lot_dates(s: Any, name: str) -> list[datetime]:
    with db(s.kitchen) as session:
        lots = session.scalars(
            select(StockLot).where(StockLot.food_id == s.foods[name], StockLot.amount_milli > 0)
        ).all()
        return [as_utc(lot.added_at) for lot in lots]


def test_a_different_pack_keeps_the_ticks_date(kitchen: TestClient) -> None:
    """Ticked offline 2 days back, then "Different pack?": the new lots keep that date."""
    s = s0(kitchen)
    monday = utcnow() - timedelta(days=2)
    done = _tick_at(s.remy, s, "Paneer", monday.isoformat(), sent_at_now())
    assert done["status"] == "applied"
    row = action("different_pack", s.c0, item_id=s.items["Paneer"], tick_id=done["id"])
    row.update(count=3, pack=150)
    changed = send(s.remy, row, device=PHONE_R)["results"][0]
    assert changed["status"] == "applied"
    dates = _lot_dates(s, "Paneer")
    assert len(dates) == 3 and all(_near(found, monday) for found in dates)


def test_a_tick_put_back_keeps_its_date(kitchen: TestClient) -> None:
    """Ticked a day back, unticked, then the untick undone ("Ticked again"): the new lot has
    the tick's date, not the time of the Undo."""
    s = s0(kitchen)
    monday = utcnow() - timedelta(days=1)
    done = _tick_at(s.remy, s, "Paneer", monday.isoformat(), sent_at_now())
    off = send(
        s.remy,
        action("untick", s.c0, item_id=s.items["Paneer"], tick_ids=[done["id"]]),
        device=PHONE_R,
    )["results"][0]
    assert _lot_dates(s, "Paneer") == []
    with db(s.kitchen) as session:  # the lot is gone: put-back makes a new one
        for lot in session.scalars(select(StockLot).where(StockLot.food_id == s.foods["Paneer"])):
            session.delete(lot)
        session.commit()
    back = send(s.remy, action("undo", s.c0, undoes=off["id"]), device=PHONE_R)["results"][0]
    assert back["status"] == "applied"
    dates = _lot_dates(s, "Paneer")
    assert dates and all(_near(found, monday) for found in dates)


def test_the_move_note_names_the_first_tick_in_server_order(kitchen: TestClient) -> None:
    """An online tick from one phone, then a back-dated offline tick from another synced
    later: N10 is decided against the first tick the server took, not the oldest by time."""
    s = s0(kitchen)
    first = send(kitchen, action("tick", s.c0, item_id=s.items["Paneer"]), device=PHONE_A)
    assert first["results"][0]["status"] == "applied"
    old = (utcnow() - timedelta(days=3)).isoformat()
    later = _tick_at(s.remy, s, "Paneer", old, sent_at_now())
    assert later["status"] == "applied"
    move = send(
        kitchen,
        action(
            "move",
            s.c0,
            item_id=s.items["Paneer"],
            list_id=s.main,
            shop_id=s.shops["Indian grocer"],
        ),
        device=PHONE_B,
    )["results"][0]
    assert (move["status"], move["reason"]) == ("ignored", "ticked")
    (note,) = ok(kitchen.get(f"{API}/shopping/changes?since=0"))["notes"]
    assert note["text"] == "Your other phone had ticked Paneer, so it wasn’t moved."
