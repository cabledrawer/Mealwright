"""Live updates (docs/dev/sync-protocol.md section 10): who hears what, and when."""

import asyncio
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import S0, db, s0, tick

from mealwright import auth
from mealwright.api.v1.events import stream
from mealwright.events import Broadcaster, Event, Subscription
from mealwright.models import Change, Household, Session, StockLot, utcnow


def run(work: Awaitable[Any]) -> Any:
    async def go() -> Any:
        return await work

    return asyncio.run(go())


async def heard(sub: Subscription, wait: float = 2) -> Event | None:
    return await asyncio.wait_for(sub.queue.get(), timeout=wait)


async def quiet(sub: Subscription, wait: float = 0.2) -> bool:
    try:
        await asyncio.wait_for(sub.queue.get(), timeout=wait)
    except TimeoutError:
        return True
    return False


def broadcaster(client: TestClient) -> Broadcaster:
    found: Broadcaster = client.app.state.events  # type: ignore[attr-defined]
    return found


# --- The endpoint ------------------------------------------------------------------------------


def test_needs_sign_in(client: TestClient) -> None:
    assert client.get("/api/v1/events").status_code == 401


def test_headers_and_first_lines(kitchen: TestClient) -> None:
    broadcaster(kitchen).close()  # the stream ends after its first lines
    with kitchen.stream("GET", "/api/v1/events") as response:
        body = "".join(response.iter_text())
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["x-accel-buffering"] == "no"
    assert "content-security-policy" in response.headers
    assert body.startswith("retry: 5000\n\n")
    assert 'event: hello\ndata: {"cursor": 0}\n\n' in body


def test_documented_in_openapi(client: TestClient) -> None:
    spec = client.get("/api/v1/openapi.json").json()
    ok = spec["paths"]["/api/v1/events"]["get"]["responses"]["200"]
    assert "text/event-stream" in ok["content"]


# --- Who hears what ---------------------------------------------------------------------------


def test_only_the_same_household_hears() -> None:
    async def scenario() -> None:
        hub = Broadcaster()
        mine, other = hub.subscribe(1), hub.subscribe(2)
        hub.publish(1, Event("shopping", {"cursor": 5}))
        assert await heard(mine) == Event("shopping", {"cursor": 5})
        assert await quiet(other)
        hub.unsubscribe(mine)
        assert hub.count() == 1

    run(scenario())


def test_a_second_household_is_not_told(kitchen: TestClient) -> None:
    async def scenario() -> None:
        with db(kitchen) as session:
            session.add(Household(name="Next door"))
            session.commit()
            other_id = session.scalars(select(Household.id).where(Household.id != 1)).one()
        mine, theirs = broadcaster(kitchen).subscribe(1), broadcaster(kitchen).subscribe(other_id)
        with db(kitchen) as session:
            session.get(Household, 1).list_seq += 1  # type: ignore[union-attr]
            session.commit()
        assert await heard(mine) == Event("shopping", {"cursor": 1})
        assert await quiet(theirs)

    run(scenario())


def test_a_tick_announces_the_counter_and_the_stock_change(kitchen: TestClient) -> None:
    s: S0 = s0(kitchen)

    async def scenario() -> None:
        sub = broadcaster(kitchen).subscribe(1)
        await asyncio.to_thread(tick, kitchen, s, "Toor dal")
        names: dict[str, dict[str, int]] = {}
        item = await heard(sub)
        while item is not None:
            names[item.name] = item.data  # the last word on each is the one that counts
            try:
                item = await heard(sub, 0.3)
            except TimeoutError:
                item = None
        assert set(names) == {"shopping", "pantry"}
        with db(kitchen) as session:
            cursor = session.get(Household, 1).list_seq  # type: ignore[union-attr]
            newest = session.scalar(select(Change.id).order_by(Change.id.desc()).limit(1))
            assert session.scalars(select(StockLot)).first() is not None
        assert names["shopping"] == {"cursor": cursor}
        assert names["pantry"] == {"change_id": newest}
        assert cursor > s.c0

    run(scenario())


def test_nothing_is_sent_before_the_commit_or_after_a_rollback(kitchen: TestClient) -> None:
    async def scenario() -> None:
        sub = broadcaster(kitchen).subscribe(1)
        with db(kitchen) as session:
            session.get(Household, 1).list_seq += 5  # type: ignore[union-attr]
            session.flush()
            assert await quiet(sub)  # flushed, not committed
            session.rollback()
        assert await quiet(sub)
        with db(kitchen) as session:
            session.get(Household, 1).list_seq += 1  # type: ignore[union-attr]
            session.commit()
        # Only the committed number, not the rolled-back one.
        assert await heard(sub) == Event("shopping", {"cursor": 1})
        assert await quiet(sub)

    run(scenario())


def test_a_change_that_touches_nothing_is_silent(kitchen: TestClient) -> None:
    async def scenario() -> None:
        sub = broadcaster(kitchen).subscribe(1)
        with db(kitchen) as session:
            session.get(Household, 1).name = "Renamed"  # type: ignore[union-attr]
            session.commit()
        assert await quiet(sub)

    run(scenario())


# --- Signing in, keep-alives -------------------------------------------------------------------


def token(client: TestClient) -> str:
    found = client.cookies.get(auth.COOKIE)
    assert found
    return found


# The stream is read until it has sent what the test is about, never for a stretch of the clock:
# under load the same stretch holds fewer keep-alives. GUARD only ends a stream that never sends
# it (the test then fails); it is never what a test waits for.
GUARD = 30
KEEP_ALIVE = ": keep-alive\n\n"


async def lines(
    client: TestClient,
    until: Callable[[list[str]], bool] | None = None,
    each: Callable[[list[str]], None] | None = None,
    keepalive: float = 0.05,
) -> list[str]:
    """What the stream sends until `until(parts so far)` says enough or the stream ends.
    `each` is called after every part."""
    hub = broadcaster(client)
    sub = hub.subscribe(1)
    out: list[str] = []
    generator = stream(
        client.app.state.sessionmaker,  # type: ignore[attr-defined]
        sub,
        hub.unsubscribe,
        token(client),
        0,
        keepalive,
    )
    try:
        async with asyncio.timeout(GUARD):
            async for part in generator:
                out.append(part)
                if each is not None:
                    each(out)
                if until is not None and until(out):
                    break
    finally:
        await generator.aclose()
    assert hub.count() == 0  # unsubscribed cleanly
    return out


def keep_alives(count: int) -> Callable[[list[str]], bool]:
    return lambda out: out.count(KEEP_ALIVE) >= count


def test_keep_alive_comments_while_signed_in(kitchen: TestClient) -> None:
    out = run(lines(kitchen, until=keep_alives(2)))
    assert out[0] == "retry: 5000\n\n"
    assert out.count(KEEP_ALIVE) == 2


def test_keep_alives_come_however_slow_the_sign_in_check_is(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The count is of what the stream sent, not of what fitted in a stretch of the clock: a
    slow machine (here, a slow check) only takes longer."""
    from mealwright.api.v1 import events

    real = events._still_signed_in

    def slow(*args: Any) -> bool:
        time.sleep(0.3)
        return real(*args)

    monkeypatch.setattr(events, "_still_signed_in", slow)
    out = run(lines(kitchen, until=keep_alives(2)))
    assert out.count(KEEP_ALIVE) == 2


def test_signed_out_when_the_session_runs_out(kitchen: TestClient) -> None:
    with db(kitchen) as session:
        row = session.scalars(select(Session)).one()
        row.expires_at = utcnow() - timedelta(seconds=1)
        session.commit()
    out = run(lines(kitchen))
    assert out[-1] == "event: signed_out\ndata: {}\n\n"
    assert KEEP_ALIVE not in out


def test_signed_out_after_signing_out_elsewhere(kitchen: TestClient) -> None:
    def sign_out_after_the_first_keep_alive(out: list[str]) -> None:
        if out.count(KEEP_ALIVE) == 1 and out[-1] == KEEP_ALIVE:
            with db(kitchen) as session:
                session.delete(session.scalars(select(Session)).one())
                session.commit()

    out = run(lines(kitchen, each=sign_out_after_the_first_keep_alive))
    assert out.count(KEEP_ALIVE) == 1
    assert out[-1] == "event: signed_out\ndata: {}\n\n"


def test_the_check_does_not_extend_the_session(kitchen: TestClient) -> None:
    """cabledrawer 18 Oct: an open screen is not activity; the 12-hour idle sign-out stays."""
    old = utcnow() - timedelta(minutes=30)
    soon = utcnow() + timedelta(hours=1)
    with db(kitchen) as session:
        row = session.scalars(select(Session)).one()
        row.last_seen_at, row.expires_at, row.remember = old, soon, False
        session.commit()
        before = (old.replace(tzinfo=None), soon.replace(tzinfo=None))
    run(lines(kitchen, until=keep_alives(2)))
    with db(kitchen) as session:
        row = session.scalars(select(Session)).one()
        assert (row.last_seen_at, row.expires_at) == before
        assert auth.peek_session(session, token(kitchen)) is not None
        assert (row.last_seen_at, row.expires_at) == before


# --- The plan (RF5 fix round 1, H3: an open Plan hears another person's change) -----------------


def _plan_kit(kitchen: TestClient) -> tuple[int, int, str]:
    """A recipe-less plan write needs an ingredient, a meal slot and a day."""
    food = kitchen.post("/api/v1/foods", json={"name": "Rice"}).json()["food"]["id"]
    slot = kitchen.get("/api/v1/meal-slots").json()["meal_slots"][-1]["id"]
    return food, slot, kitchen.get("/api/v1/household").json()["today"]


async def _plan_heard(sub: Subscription) -> list[Event]:
    got: list[Event] = []
    try:
        while True:
            got.append(await heard(sub, 0.5))
    except TimeoutError:
        return got


def _names(events: list[Event]) -> set[str]:
    return {e.name for e in events}


def test_every_plan_write_announces_a_plan_event(kitchen: TestClient) -> None:
    food, slot, today = _plan_kit(kitchen)
    api = "/api/v1"

    async def after(call: Callable[[], Any]) -> set[str]:
        sub = broadcaster(kitchen).subscribe(1)
        response = await asyncio.to_thread(call)
        assert response.status_code < 300, response.text
        names = _names(await _plan_heard(sub))
        broadcaster(kitchen).unsubscribe(sub)
        return names

    async def scenario() -> None:
        added = await asyncio.to_thread(
            lambda: kitchen.post(
                f"{api}/plan/items", json={"date": today, "slot_id": slot, "ingredient_id": food}
            )
        )
        assert added.status_code == 201, added.text
        item_id, meal_id = added.json()["item_id"], added.json()["meal_id"]
        sub = broadcaster(kitchen).subscribe(1)
        await asyncio.to_thread(
            lambda: kitchen.post(
                f"{api}/plan/items",
                json={"date": today, "slot_id": slot, "ingredient_id": food},
            )
        )
        assert "plan" in _names(await _plan_heard(sub))  # adding a meal or item
        calls: dict[str, Callable[[], Any]] = {
            "eaters": lambda: kitchen.patch(
                f"{api}/plan/meals/{meal_id}",
                json={
                    "member_ids": [
                        kitchen.get(f"{api}/plan/people").json()["people"][0]["member_id"]
                    ]
                },
            ),
            "remove item": lambda: kitchen.delete(f"{api}/plan/items/{item_id}"),
            "remove meal": lambda: kitchen.delete(f"{api}/plan/meals/{meal_id}"),
            "rename a meal slot": lambda: kitchen.patch(
                f"{api}/meal-slots/{slot}", json={"name": "Supper!"}
            ),
        }
        for name, call in calls.items():
            assert "plan" in await after(call), name

    run(scenario())


def test_a_read_or_a_change_outside_the_plan_sends_no_plan_event(kitchen: TestClient) -> None:
    async def scenario() -> None:
        sub = broadcaster(kitchen).subscribe(1)
        await asyncio.to_thread(lambda: kitchen.get("/api/v1/plan?from=2026-11-01&to=2026-11-07"))
        await asyncio.to_thread(lambda: kitchen.post("/api/v1/shops", json={"name": "Aldi"}))
        assert "plan" not in _names(await _plan_heard(sub))

    run(scenario())


def test_clearing_the_eaters_announces_a_plan_event(
    kitchen: TestClient,
) -> None:
    # Clearing writes with a bulk DELETE, which the session can't see (RF5 fix round 1).
    _, slot, today = _plan_kit(kitchen)
    api = "/api/v1"
    me = kitchen.get(f"{api}/me").json()["id"]
    recipe = kitchen.post(f"{api}/recipes", json={"name": "Dal", "steps": [{"text": "Cook."}]})
    recipe_id = recipe.json()["id"]
    planned = kitchen.post(
        f"{api}/plan/items", json={"date": today, "slot_id": slot, "recipe_id": recipe_id}
    ).json()
    kitchen.patch(f"{api}/plan/meals/{planned['meal_id']}", json={"member_ids": [me]})

    async def scenario() -> None:
        for name, call in {
            "clear the eaters": lambda: kitchen.patch(
                f"{api}/plan/meals/{planned['meal_id']}", json={"member_ids": []}
            ),
        }.items():
            sub = broadcaster(kitchen).subscribe(1)
            response = await asyncio.to_thread(call)
            assert response.status_code < 300, (name, response.text)
            assert "plan" in _names(await _plan_heard(sub)), name
            broadcaster(kitchen).unsubscribe(sub)

    run(scenario())
