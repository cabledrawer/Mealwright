"""A request that is cancelled part-way (the server stopping, a caller giving up) still
closes its database session, there and then, before it gives its place back: nothing is left
checked out for the garbage collector to find (pool-fix review r1).

Before: a cancelled request gave its place back but left its session open. A few cancelled
bursts took all 50 connections with all 40 places free, and the next request waited 30
seconds for a connection and failed.
"""

import asyncio
import time
from typing import Any

import anyio
from conftest import ADMIN
from fastapi.testclient import TestClient
from sqlalchemy import event
from test_many_at_once import connections_out
from test_slow_uploads import cookie_of

from mealwright.config import Settings
from mealwright.db import REQUESTS_AT_ONCE, SPARE_CONNECTIONS
from mealwright.main import create_app

BURST = 60  # more than there are places, so some are cancelled while waiting their turn too
HOLDING = 20  # cancel once this many of a burst have a connection
# Enough bursts that, if each left its connections out, the pool would be empty.
BURSTS = (REQUESTS_AT_ONCE + SPARE_CONNECTIONS) // HOLDING + 1
SANE_SECONDS = 20


def read_scope(cookie: str) -> dict[str, Any]:
    return {
        "type": "http",
        "asgi": {"version": "3.0"},
        "http_version": "1.1",
        "method": "GET",
        "scheme": "https",
        "path": "/api/v1/recipes",
        "raw_path": b"/api/v1/recipes",
        "query_string": b"",
        "root_path": "",
        "headers": [(b"host", b"testserver"), (b"cookie", cookie.encode())],
        "client": ("testclient", 50000),
        "server": ("testserver", 443),
    }


def test_cancelled_requests_leave_no_connection_out(settings: Settings) -> None:
    app = create_app(settings)
    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as client:
        assert client.post("/api/v1/setup", json=ADMIN).status_code == 201
        cookie = cookie_of(client)
        portal = client.portal
        assert portal is not None
        engine = app.state.engine

        async def cancelled_burst() -> int:
            """Starts BURST reads and cancels them all the moment HOLDING of them have taken
            a connection; how many reads were cut short."""
            loop = asyncio.get_running_loop()
            enough = asyncio.Event()
            taken = 0
            finished = 0

            def took_one(*_: object) -> None:  # in a worker thread
                nonlocal taken
                taken += 1
                if taken >= HOLDING:
                    loop.call_soon_threadsafe(enough.set)

            async def receive() -> dict[str, Any]:
                return {"type": "http.request", "body": b"", "more_body": False}

            async def send(_message: dict[str, Any]) -> None:
                pass

            async def one() -> None:
                nonlocal finished
                await app(read_scope(cookie), receive, send)
                finished += 1

            event.listen(engine, "checkout", took_one)
            try:
                async with anyio.create_task_group() as requests:
                    for _ in range(BURST):
                        requests.start_soon(one)
                    await enough.wait()
                    requests.cancel_scope.cancel()
            finally:
                event.remove(engine, "checkout", took_one)
            return BURST - finished

        with connections_out(client) as count:
            for _ in range(BURSTS):
                cut_short = portal.call(cancelled_burst)
                assert cut_short > 0  # the burst really was cancelled part-way
                # Straight away, with no help from the garbage collector.
                assert count[0] == 0
            turns = [turn._value for turn in app.state.database_turns.values()]
            assert turns == [REQUESTS_AT_ONCE]  # every place is free again
            started = time.monotonic()
            assert client.get("/api/v1/recipes").status_code == 200
            assert time.monotonic() - started < SANE_SECONDS
            assert count[0] == 0
