"""A staple's restock date (0.7 K1; spec section 6, "Shopping rows", cabledrawer 20 Oct)."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sync_kit import API, PHONE_R, changes, db, new_id, ok, one, s0, tick

from mealwright.history import tidy_lists
from mealwright.models import Food, Household, ListItem, ListTick, utcnow


def _restocked(client: TestClient, food_id: int) -> datetime | None:
    found = ok(client.get(f"{API}/foods/{food_id}"))["restocked_at"]
    return datetime.fromisoformat(found).astimezone(UTC) if found else None


def _listed(client: TestClient, food_id: int) -> Any:
    rows = ok(client.get(f"{API}/foods?limit=100"))["foods"]
    return next(row for row in rows if row["id"] == food_id)["restocked_at"]


def _close(a: datetime | None, b: datetime) -> bool:
    return a is not None and abs(a - b) < timedelta(seconds=5)


def test_ticking_a_staple_restocks_it_and_other_ingredients_have_no_date(
    kitchen: TestClient,
) -> None:
    s = s0(kitchen)
    salt, dal = s.foods["Salt"], s.foods["Toor dal"]
    assert _restocked(kitchen, salt) is None and _listed(kitchen, salt) is None
    tick(kitchen, s, "Salt")
    tick(kitchen, s, "Toor dal")
    assert _close(_restocked(kitchen, salt), datetime.now(UTC))
    assert _listed(kitchen, salt) is not None
    assert _restocked(kitchen, dal) is None and _listed(kitchen, dal) is None
    with db(kitchen) as session:
        marked = {t.item_id: t.restock for t in session.query(ListTick)}
    assert marked == {s.items["Salt"]: True, s.items["Toor dal"]: False}


def test_untick_puts_the_date_back_to_the_restock_before(kitchen: TestClient) -> None:
    s = s0(kitchen)
    salt = s.foods["Salt"]
    first, second = new_id(), new_id()
    tick(kitchen, s, "Salt", id=first)
    earlier = utcnow() - timedelta(days=3)
    with db(kitchen) as session:
        session.execute(update(ListTick).where(ListTick.id == first).values(ticked_at=earlier))
        session.commit()
    tick(s.wren, s, "Salt", PHONE_R, id=second)
    assert _close(_restocked(kitchen, salt), datetime.now(UTC))
    seen = int(changes(kitchen)["cursor"])
    one(kitchen, "untick", seen, item_id=s.items["Salt"], tick_ids=[second])
    assert _close(_restocked(kitchen, salt), earlier)
    seen = int(changes(kitchen)["cursor"])
    one(kitchen, "untick", seen, item_id=s.items["Salt"], tick_ids=[first])
    assert _restocked(kitchen, salt) is None


def test_the_date_outlives_the_tidy_up(kitchen: TestClient) -> None:
    s = s0(kitchen)
    salt = s.foods["Salt"]
    tick(kitchen, s, "Salt")
    when = _restocked(kitchen, salt)
    assert when is not None
    with db(kitchen) as session:
        session.execute(
            update(ListItem)
            .where(ListItem.id == s.items["Salt"])
            .values(deleted_at=utcnow() - timedelta(days=400))
        )
        session.commit()
        tidy_lists(session, session.get(Household, 1))
        assert session.query(ListTick).filter(ListTick.item_id == s.items["Salt"]).count() == 0
        kept = session.get(Food, salt).restocked_at  # type: ignore[union-attr]
    assert kept is not None
    assert _close(_restocked(kitchen, salt), when)


def test_a_staple_no_longer_a_staple_shows_no_date(kitchen: TestClient) -> None:
    s = s0(kitchen)
    salt = s.foods["Salt"]
    tick(kitchen, s, "Salt")
    ok(kitchen.patch(f"{API}/foods/{salt}", json={"staple": False}))
    assert _restocked(kitchen, salt) is None


def test_a_merge_keeps_the_newer_date_and_undo_puts_it_back(kitchen: TestClient) -> None:
    def staple(name: str) -> int:
        made = ok(kitchen.post(f"{API}/foods", json={"name": name, "staple": True}), 201)
        return int(made["food"]["id"])

    kept, gone = staple("Rock salt"), staple("Sea salt")
    older, newer = utcnow() - timedelta(days=40), utcnow() - timedelta(days=2)
    with db(kitchen) as session:
        for food_id, when in ((kept, older), (gone, newer)):
            session.execute(update(Food).where(Food.id == food_id).values(restocked_at=when))
        session.commit()
    merged = ok(kitchen.post(f"{API}/foods/{gone}/merge", json={"into_id": kept}))
    assert _close(_restocked(kitchen, kept), newer)
    ok(kitchen.post(f"{API}/changes/{merged['change']['id']}/undo"))
    assert _close(_restocked(kitchen, kept), older)
    assert _close(_restocked(kitchen, gone), newer)


def test_a_merge_copies_no_live_tick_so_untick_still_puts_the_date_back(
    kitchen: TestClient,
) -> None:
    s = s0(kitchen)
    salt = s.foods["Salt"]
    tick_id = new_id()
    tick(kitchen, s, "Salt", id=tick_id)
    rock = ok(kitchen.post(f"{API}/foods", json={"name": "Rock salt", "staple": True}), 201)
    kept = int(rock["food"]["id"])
    ok(kitchen.post(f"{API}/foods/{salt}/merge", json={"into_id": kept}))
    assert _close(_restocked(kitchen, kept), datetime.now(UTC))  # the tick moved with its line
    seen = int(changes(kitchen)["cursor"])
    one(kitchen, "untick", seen, item_id=s.items["Salt"], tick_ids=[tick_id])
    assert _restocked(kitchen, kept) is None


def test_undo_of_a_merge_is_whole_when_the_date_was_raised_since(kitchen: TestClient) -> None:
    def staple(name: str) -> int:
        made = ok(kitchen.post(f"{API}/foods", json={"name": name, "staple": True}), 201)
        return int(made["food"]["id"])

    kept, gone = staple("Rock salt"), staple("Sea salt")
    older, newer = utcnow() - timedelta(days=40), utcnow() - timedelta(days=2)
    with db(kitchen) as session:
        for food_id, when in ((kept, older), (gone, newer)):
            session.execute(update(Food).where(Food.id == food_id).values(restocked_at=when))
        session.commit()
    merged = ok(kitchen.post(f"{API}/foods/{gone}/merge", json={"into_id": kept}))
    with db(kitchen) as session:  # a restock kept by the tidy-up since
        session.execute(update(Food).where(Food.id == kept).values(restocked_at=utcnow()))
        session.commit()
    undone = ok(kitchen.post(f"{API}/changes/{merged['change']['id']}/undo"))
    assert undone["result"] == "done"
    assert _close(_restocked(kitchen, kept), older)


# --- Changing the date by hand (0.7 K5) -------------------------------------------------------


def _restock_now(client: TestClient, food: int) -> Any:
    """What the Restocked button sends: the household's today as the day."""
    today = ok(client.get(f"{API}/household"))["today"]
    return ok(client.patch(f"{API}/foods/{food}", json={"restocked_on": today}))


def _staple(client: TestClient, name: str = "Rock salt") -> int:
    made = ok(client.post(f"{API}/foods", json={"name": name, "staple": True}), 201)
    return int(made["food"]["id"])


def test_the_date_can_be_set_and_undone(kitchen: TestClient) -> None:
    food = _staple(kitchen)
    when = datetime.now(UTC) - timedelta(days=20)
    done = ok(kitchen.patch(f"{API}/foods/{food}", json={"restocked_at": when.isoformat()}))
    assert _close(_restocked(kitchen, food), when)
    assert _close(datetime.fromisoformat(done["food"]["restocked_at"]), when)
    assert _listed(kitchen, food) is not None
    ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))
    assert _restocked(kitchen, food) is None


def test_the_date_can_go_back_to_an_earlier_day(kitchen: TestClient) -> None:
    food = _staple(kitchen)
    _restock_now(kitchen, food)
    earlier = datetime.now(UTC) - timedelta(days=9)
    ok(kitchen.patch(f"{API}/foods/{food}", json={"restocked_at": earlier.isoformat()}))
    assert _close(_restocked(kitchen, food), earlier)


def test_a_date_in_the_future_is_refused(kitchen: TestClient) -> None:
    food = _staple(kitchen)
    later = datetime.now(UTC) + timedelta(days=1)
    sent = kitchen.patch(f"{API}/foods/{food}", json={"restocked_at": later.isoformat()})
    assert sent.status_code == 422 and sent.json()["code"] == "restock_in_future"
    assert _restocked(kitchen, food) is None


def test_a_clock_a_little_fast_is_taken_as_now(kitchen: TestClient) -> None:
    food = _staple(kitchen)
    a_bit = datetime.now(UTC) + timedelta(minutes=2)
    ok(kitchen.patch(f"{API}/foods/{food}", json={"restocked_at": a_bit.isoformat()}))
    kept = _restocked(kitchen, food)
    assert kept is not None and kept <= datetime.now(UTC) + timedelta(seconds=1)


# --- The date typed wins (cabledrawer 2 Nov) ------------------------------------------------------


def _backdate_ticks(client: TestClient, item_id: str, when: datetime) -> None:
    with db(client) as session:
        session.execute(update(ListTick).where(ListTick.item_id == item_id).values(ticked_at=when))
        session.commit()


def _type(client: TestClient, food: int, when: datetime) -> Any:
    return ok(client.patch(f"{API}/foods/{food}", json={"restocked_at": when.isoformat()}))


def _on_pantry(client: TestClient, food: int) -> datetime | None:
    staples = ok(client.get(f"{API}/pantry"))["staples"]
    found = next(row for row in staples if row["id"] == food)["restocked_at"]
    return datetime.fromisoformat(found).astimezone(UTC) if found else None


def test_a_typed_date_under_a_newer_tick_is_shown_everywhere(kitchen: TestClient) -> None:
    """Tick Monday, type the Saturday before: Saturday is shown on Pantry and Ingredients."""
    s = s0(kitchen)
    salt = s.foods["Salt"]
    tick(kitchen, s, "Salt")
    monday = utcnow() - timedelta(days=2)
    _backdate_ticks(kitchen, s.items["Salt"], monday)
    saturday = utcnow() - timedelta(days=4)
    done = _type(kitchen, salt, saturday)
    assert done["change"]["summary"] == "Salt restocked"
    assert _close(_restocked(kitchen, salt), saturday)
    assert _close(datetime.fromisoformat(_listed(kitchen, salt)).astimezone(UTC), saturday)
    assert _close(_on_pantry(kitchen, salt), saturday)


def test_a_tick_after_the_typing_wins_and_its_untick_brings_the_typed_date_back(
    kitchen: TestClient,
) -> None:
    s = s0(kitchen)
    salt = s.foods["Salt"]
    saturday = utcnow() - timedelta(days=4)
    _type(kitchen, salt, saturday)
    tick_id = new_id()
    tick(kitchen, s, "Salt", id=tick_id)
    assert _close(_restocked(kitchen, salt), datetime.now(UTC))
    assert _close(_on_pantry(kitchen, salt), datetime.now(UTC))
    seen = int(changes(kitchen)["cursor"])
    one(kitchen, "untick", seen, item_id=s.items["Salt"], tick_ids=[tick_id])
    assert _close(_restocked(kitchen, salt), saturday)
    assert _close(_on_pantry(kitchen, salt), saturday)


def test_undo_of_the_typed_date_shows_the_tick_again(kitchen: TestClient) -> None:
    s = s0(kitchen)
    salt = s.foods["Salt"]
    tick(kitchen, s, "Salt")
    monday = utcnow() - timedelta(days=2)
    _backdate_ticks(kitchen, s.items["Salt"], monday)
    done = _type(kitchen, salt, utcnow() - timedelta(days=4))
    ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))
    assert _close(_restocked(kitchen, salt), monday)
    with db(kitchen) as session:
        food = session.get(Food, salt)
        assert food is not None and food.restock_typed_at is None and food.restocked_at is None


def test_the_same_typed_date_again_is_no_change(kitchen: TestClient) -> None:
    food = _staple(kitchen)
    when = utcnow() - timedelta(days=4)
    _type(kitchen, food, when)
    again = ok(kitchen.patch(f"{API}/foods/{food}", json={"restocked_at": when.isoformat()}))
    assert again["change"] is None


def _tidy(client: TestClient, item_id: str) -> None:
    with db(client) as session:
        session.execute(
            update(ListItem)
            .where(ListItem.id == item_id)
            .values(deleted_at=utcnow() - timedelta(days=400))
        )
        session.commit()
        tidy_lists(session, session.get(Household, 1))
        assert session.query(ListTick).filter(ListTick.item_id == item_id).count() == 0


def test_the_tidy_up_keeps_a_typed_date_under_an_older_tick(kitchen: TestClient) -> None:
    """A tick made before the typing didn't count; deleting it changes nothing shown."""
    s = s0(kitchen)
    salt = s.foods["Salt"]
    tick(kitchen, s, "Salt")
    _backdate_ticks(kitchen, s.items["Salt"], utcnow() - timedelta(days=2))
    saturday = utcnow() - timedelta(days=4)
    _type(kitchen, salt, saturday)
    _tidy(kitchen, s.items["Salt"])
    assert _close(_restocked(kitchen, salt), saturday)
    assert _close(_on_pantry(kitchen, salt), saturday)


def test_the_tidy_up_keeps_a_tick_made_after_the_typing(kitchen: TestClient) -> None:
    s = s0(kitchen)
    salt = s.foods["Salt"]
    _type(kitchen, salt, utcnow() - timedelta(days=4))
    tick(kitchen, s, "Salt")
    shown = _restocked(kitchen, salt)
    assert _close(shown, datetime.now(UTC))
    _tidy(kitchen, s.items["Salt"])
    assert shown is not None and _close(_restocked(kitchen, salt), shown)
    with db(kitchen) as session:
        food = session.get(Food, salt)
        assert food is not None and food.restock_typed_at is None  # no longer a typed date


def test_a_merge_keeps_what_was_shown_when_a_tick_hid_under_a_typed_date(
    kitchen: TestClient,
) -> None:
    """Salt: ticked 2 days ago, typed 10 days ago (shown: 10). Rock salt: 6 days ago. Merged,
    Rock salt shows 6 days ago: Salt's hidden tick doesn't come back; Undo puts both back."""
    s = s0(kitchen)
    salt = s.foods["Salt"]
    tick(kitchen, s, "Salt")
    _backdate_ticks(kitchen, s.items["Salt"], utcnow() - timedelta(days=2))
    ten = utcnow() - timedelta(days=10)
    _type(kitchen, salt, ten)
    rock = _staple(kitchen)
    six = utcnow() - timedelta(days=6)
    with db(kitchen) as session:
        session.execute(update(Food).where(Food.id == rock).values(restocked_at=six))
        session.commit()
    merged = ok(kitchen.post(f"{API}/foods/{salt}/merge", json={"into_id": rock}))
    assert _close(_restocked(kitchen, rock), six)
    assert _close(_on_pantry(kitchen, rock), six)
    ok(kitchen.post(f"{API}/changes/{merged['change']['id']}/undo"))
    assert _close(_restocked(kitchen, rock), six)
    assert _close(_restocked(kitchen, salt), ten)


def test_a_merge_keeps_a_newer_tick_over_a_typed_date(kitchen: TestClient) -> None:
    """Rock salt: typed 10 days ago. Salt: ticked 3 days ago (shown: 3). Merged into Rock salt,
    3 days ago is shown; Undo puts both back."""
    s = s0(kitchen)
    salt = s.foods["Salt"]
    rock = _staple(kitchen)
    ten = utcnow() - timedelta(days=10)
    _type(kitchen, rock, ten)
    tick(kitchen, s, "Salt")
    three = utcnow() - timedelta(days=3)
    _backdate_ticks(kitchen, s.items["Salt"], three)
    assert _close(_restocked(kitchen, salt), three)
    merged = ok(kitchen.post(f"{API}/foods/{salt}/merge", json={"into_id": rock}))
    assert _close(_restocked(kitchen, rock), three)
    ok(kitchen.post(f"{API}/changes/{merged['change']['id']}/undo"))
    assert _close(_restocked(kitchen, rock), ten)
    assert _close(_restocked(kitchen, salt), three)


def test_another_household_cant_see_or_set_a_typed_date(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    food = _staple(kitchen)
    when = utcnow() - timedelta(days=4)
    _type(kitchen, food, when)
    assert neighbour.get(f"{API}/foods/{food}").status_code == 404
    staples = ok(neighbour.get(f"{API}/pantry"))["staples"]
    assert all(row["id"] != food for row in staples)
    later = (utcnow() - timedelta(days=1)).isoformat()
    sent = neighbour.patch(f"{API}/foods/{food}", json={"restocked_at": later})
    assert sent.status_code == 404
    assert _close(_restocked(kitchen, food), when)


def test_only_a_staple_has_a_date_and_a_date_is_needed(kitchen: TestClient) -> None:
    s = s0(kitchen)
    dal = s.foods["Toor dal"]
    now = datetime.now(UTC).isoformat()
    sent = kitchen.patch(f"{API}/foods/{dal}", json={"restocked_at": now})
    assert sent.status_code == 422 and sent.json()["code"] == "not_a_staple"
    today = ok(kitchen.get(f"{API}/household"))["today"]
    assert kitchen.patch(f"{API}/foods/{dal}", json={"restocked_on": today}).status_code == 422
    food = _staple(kitchen)
    none = kitchen.patch(f"{API}/foods/{food}", json={"restocked_at": None})
    assert none.status_code == 422 and none.json()["code"] == "restock_date_needed"


def test_the_restocked_tap_sets_now_and_undo_puts_it_back(kitchen: TestClient) -> None:
    food = _staple(kitchen)
    old = datetime.now(UTC) - timedelta(days=30)
    ok(kitchen.patch(f"{API}/foods/{food}", json={"restocked_at": old.isoformat()}))
    done = _restock_now(kitchen, food)
    assert _close(_restocked(kitchen, food), datetime.now(UTC))
    assert done["change"]["summary"] == "Rock salt restocked"
    ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))
    assert _close(_restocked(kitchen, food), old)


def test_another_household_gets_not_found(kitchen: TestClient, neighbour: TestClient) -> None:
    food = _staple(kitchen)
    now = datetime.now(UTC).isoformat()
    assert neighbour.patch(f"{API}/foods/{food}", json={"restocked_at": now}).status_code == 404
    assert (
        neighbour.patch(f"{API}/foods/{food}", json={"restocked_on": "2026-10-01"}).status_code
        == 404
    )
    assert _restocked(kitchen, food) is None


def test_the_pantry_gives_each_staple_its_date(kitchen: TestClient) -> None:
    food = _staple(kitchen)
    other = _staple(kitchen, "Black pepper")
    _restock_now(kitchen, food)
    staples = ok(kitchen.get(f"{API}/pantry"))["staples"]
    dates = {row["id"]: row["restocked_at"] for row in staples}
    assert dates[other] is None
    assert _close(datetime.fromisoformat(dates[food]).astimezone(UTC), datetime.now(UTC))


def test_a_day_picked_in_the_editor_is_the_households_own_day(kitchen: TestClient) -> None:
    food = _staple(kitchen)
    ok(kitchen.post(f"{API}/household/from-browser", json={"time_zone": "Pacific/Auckland"}))
    today = ok(kitchen.get(f"{API}/household"))["today"]
    day = (datetime.fromisoformat(today) - timedelta(days=22)).date().isoformat()
    done = ok(kitchen.patch(f"{API}/foods/{food}", json={"restocked_on": day}))
    assert done["food"]["restocked_on"] == day
    assert done["food"]["restocked_days_ago"] == 22
    listed = next(
        row for row in ok(kitchen.get(f"{API}/foods?limit=100"))["foods"] if row["id"] == food
    )
    assert (listed["restocked_on"], listed["restocked_days_ago"]) == (day, 22)
    pantry = ok(kitchen.get(f"{API}/pantry"))["staples"]
    assert next(row for row in pantry if row["id"] == food)["restocked_on"] == day


def test_today_is_a_day_and_tomorrow_is_not(kitchen: TestClient) -> None:
    food = _staple(kitchen)
    today = ok(kitchen.get(f"{API}/household"))["today"]
    done = ok(kitchen.patch(f"{API}/foods/{food}", json={"restocked_on": today}))
    assert done["food"]["restocked_on"] == today and done["food"]["restocked_days_ago"] == 0
    tomorrow = (datetime.fromisoformat(today) + timedelta(days=1)).date().isoformat()
    sent = kitchen.patch(f"{API}/foods/{food}", json={"restocked_on": tomorrow})
    assert sent.status_code == 422 and sent.json()["code"] == "restock_in_future"


# --- Extreme dates (fix round 1) --------------------------------------------------------------


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"restocked_at": "0001-01-01T00:00:00+14:00"}, "restock_too_old"),
        ({"restocked_at": "0001-01-01T00:00:00Z"}, "restock_too_old"),
        ({"restocked_at": "1999-12-31T23:59:59Z"}, "restock_too_old"),
        ({"restocked_at": "9999-12-31T23:59:59-14:00"}, "restock_in_future"),
        ({"restocked_at": "9999-12-31T23:59:59Z"}, "restock_in_future"),
        ({"restocked_on": "0001-01-01"}, "restock_too_old"),
        ({"restocked_on": "1999-12-31"}, "restock_too_old"),
        ({"restocked_on": "9999-12-31"}, "restock_in_future"),
    ],
)
def test_an_extreme_date_is_a_422_not_a_500(kitchen: TestClient, body: Any, code: str) -> None:
    food = _staple(kitchen)
    sent = kitchen.patch(f"{API}/foods/{food}", json=body)
    assert sent.status_code == 422 and sent.json()["code"] == code
    assert _restocked(kitchen, food) is None


def test_a_year_one_value_stored_directly_breaks_no_page_in_a_western_zone(
    kitchen: TestClient,
) -> None:
    food = _staple(kitchen)
    ok(kitchen.post(f"{API}/household/from-browser", json={"time_zone": "America/Los_Angeles"}))
    with db(kitchen) as session:
        session.execute(
            update(Food).where(Food.id == food).values(restocked_at=datetime(1, 1, 1, tzinfo=UTC))
        )
        session.commit()
    one = ok(kitchen.get(f"{API}/foods/{food}"))
    assert one["restocked_on"] is None and one["restocked_days_ago"] is None
    assert ok(kitchen.get(f"{API}/foods?limit=100"))["foods"]
    assert any(row["id"] == food for row in ok(kitchen.get(f"{API}/pantry"))["staples"])


def test_restocked_today_follows_the_servers_own_clock(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The browser tests move the server's clock: "today" as the day must not be 'future'."""
    from mealwright import models

    monkeypatch.setattr(models, "TEST_CLOCK_SHIFT", timedelta(days=-10))
    food = _staple(kitchen)
    done = _restock_now(kitchen, food)
    assert done["food"]["restocked_days_ago"] == 0
