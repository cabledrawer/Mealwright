"""How many live-update streams one sign-in may hold open (security audit, cabledrawer 18 Oct).

Each open stream costs the server a connection and a little memory, so one sign-in must
not be able to open them without end. Past the limit the oldest stream of that sign-in is
closed (a browser reconnects by itself after 5 seconds), so a phone that left dead
connections behind is never locked out. Other sign-ins are not touched.

The streams here are real requests to the app, run as ASGI calls on this test's own event
loop, so many can be open at once (the test client waits for a response to finish).
"""

import asyncio
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager
from typing import Any

import pytest
from conftest import ADMIN
from fastapi.testclient import TestClient

from mealwright.auth import COOKIE
from mealwright.events import MAX_STREAMS_PER_SESSION, Broadcaster

API = "/api/v1"


class Stream:
    """One open GET /api/v1/events, as a browser tab would hold it."""

    def __init__(self, app: Any, token: str) -> None:
        self.app = app
        self.token = token
        self.status: int | None = None
        self.body = ""
        self.ended = asyncio.Event()
        self.started = asyncio.Event()
        self._gone = asyncio.Event()
        self.task: asyncio.Task[None] | None = None

    async def _receive(self) -> dict[str, Any]:
        if not self.started.is_set():
            self.started.set()
            return {"type": "http.request", "body": b"", "more_body": False}
        await self._gone.wait()
        return {"type": "http.disconnect"}

    async def _send(self, message: dict[str, Any]) -> None:
        if message["type"] == "http.response.start":
            self.status = message["status"]
        elif message["type"] == "http.response.body":
            self.body += message.get("body", b"").decode()
            if not message.get("more_body", False):
                self.ended.set()

    def open(self) -> None:
        scope = {
            "type": "http",
            "asgi": {"version": "3.0", "spec_version": "2.4"},
            "http_version": "1.1",
            "method": "GET",
            "scheme": "https",
            "path": f"{API}/events",
            "raw_path": f"{API}/events".encode(),
            "query_string": b"",
            "root_path": "",
            "headers": [
                (b"host", b"testserver"),
                (b"cookie", f"{COOKIE}={self.token}".encode()),
            ],
            "client": ("192.0.2.1", 50000),
            "server": ("testserver", 443),
        }
        self.task = asyncio.create_task(self.app(scope, self._receive, self._send))

    async def hello(self) -> None:
        """Wait until the stream has said hello (it is open and subscribed)."""
        async with asyncio.timeout(5):
            while "event: hello" not in self.body and not self.ended.is_set():
                await asyncio.sleep(0.01)
        assert self.status == 200 and "event: hello" in self.body, (self.status, self.body)

    async def still_open(self, wait: float = 0.2) -> bool:
        try:
            async with asyncio.timeout(wait):
                await self.ended.wait()
        except TimeoutError:
            return True
        return False

    async def close(self) -> None:
        self._gone.set()
        if self.task is not None:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)


@asynccontextmanager
async def streams() -> AsyncIterator[list[Stream]]:
    opened: list[Stream] = []
    try:
        yield opened
    finally:
        for one in opened:
            await one.close()


def hub(client: TestClient) -> Broadcaster:
    found: Broadcaster = client.app.state.events  # type: ignore[attr-defined]
    return found


@pytest.fixture
def second_sign_in(kitchen: TestClient) -> Iterator[str]:
    """The same person, signed in again on another device: a second session."""
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        assert other.post(f"{API}/session", json=ADMIN).status_code == 200
        yield other.cookies[COOKIE]


def test_the_limit_is_a_handful_of_tabs() -> None:
    assert 5 <= MAX_STREAMS_PER_SESSION <= 20


def test_one_sign_in_cannot_open_streams_without_end(
    kitchen: TestClient, second_sign_in: str
) -> None:
    app, mine = kitchen.app, kitchen.cookies[COOKIE]

    async def scenario() -> None:
        async with streams() as opened:
            for _ in range(MAX_STREAMS_PER_SESSION):
                one = Stream(app, mine)
                opened.append(one)
                one.open()
                await one.hello()
            assert hub(kitchen).count() == MAX_STREAMS_PER_SESSION
            # Another device's streams don't count against this one.
            theirs = Stream(app, second_sign_in)
            opened.append(theirs)
            theirs.open()
            await theirs.hello()
            # One more than the limit: the oldest of this sign-in's streams is closed.
            newest = Stream(app, mine)
            opened.append(newest)
            newest.open()
            await newest.hello()
            async with asyncio.timeout(2):
                await opened[0].ended.wait()
            assert opened[0].status == 200
            assert "signed_out" not in opened[0].body  # the browser just reconnects
            for one in (*opened[1:MAX_STREAMS_PER_SESSION], theirs, newest):
                assert await one.still_open(0.05)
            assert hub(kitchen).count() == MAX_STREAMS_PER_SESSION + 1

    asyncio.run(scenario())


def test_many_more_still_leaves_only_the_limit(kitchen: TestClient) -> None:
    app, mine = kitchen.app, kitchen.cookies[COOKIE]

    async def scenario() -> None:
        async with streams() as opened:
            for _ in range(MAX_STREAMS_PER_SESSION * 3):
                one = Stream(app, mine)
                opened.append(one)
                one.open()
                await one.hello()
            await asyncio.sleep(0.1)
            assert hub(kitchen).count() == MAX_STREAMS_PER_SESSION
            still = [one for one in opened if not one.ended.is_set()]
            assert still == opened[-MAX_STREAMS_PER_SESSION:]  # the newest are kept

    asyncio.run(scenario())


def test_the_broadcaster_closes_the_oldest_of_that_session_only() -> None:
    async def scenario() -> None:
        broadcaster = Broadcaster()
        mine = [broadcaster.subscribe(1, session_id=7) for _ in range(MAX_STREAMS_PER_SESSION)]
        other = broadcaster.subscribe(1, session_id=8)
        untracked = broadcaster.subscribe(1)
        newest = broadcaster.subscribe(1, session_id=7)
        await asyncio.sleep(0)
        assert mine[0].queue.qsize() == 1 and mine[0].queue.get_nowait() is None
        for one in (*mine[1:], other, untracked, newest):
            assert one.queue.empty()
        assert broadcaster.count() == MAX_STREAMS_PER_SESSION + 2
        # A closed stream unsubscribing later is harmless.
        broadcaster.unsubscribe(mine[0])
        assert broadcaster.count() == MAX_STREAMS_PER_SESSION + 2

    asyncio.run(scenario())


def test_signing_out_ends_that_sign_ins_streams_at_once(
    kitchen: TestClient, second_sign_in: str
) -> None:
    """Not up to 25 seconds later, at the next check (ASVS 3.3.1)."""
    app, mine = kitchen.app, kitchen.cookies[COOKIE]

    async def scenario() -> None:
        async with streams() as opened:
            for token in (mine, mine, second_sign_in):
                one = Stream(app, token)
                opened.append(one)
                one.open()
                await one.hello()
            signed_out = await asyncio.to_thread(kitchen.delete, f"{API}/session")
            assert signed_out.status_code == 204
            for one in opened[:2]:
                async with asyncio.timeout(2):
                    await one.ended.wait()
                assert one.body.endswith("event: signed_out\ndata: {}\n\n")
            assert await opened[2].still_open()  # the other device stays signed in
            assert hub(kitchen).count() == 1

    asyncio.run(scenario())
