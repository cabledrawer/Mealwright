"""Many signed-in requests at once must all be answered: none may fail, or stall the rest,
because the database connections ran out (X1 security review r2, older than 0.9).

What went wrong: every step of a request (the sign-in check, the household, the endpoint,
building the answer) runs in a worker thread, one of 40, and the request kept its database
connection from the first step to the last. With more than 40 requests at once, 15 held all
the pool's connections and waited for a free thread, while all 40 threads sat in the sign-in
check waiting for a connection: nothing moved for 30 seconds, then the 40 gave up with 500s.
"""

import threading
import time
from collections import Counter
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

import pytest
from conftest import ADMIN
from fastapi.testclient import TestClient
from sqlalchemy import event

from mealwright import db as database
from mealwright.config import Settings
from mealwright.db import REQUESTS_AT_ONCE, make_engine
from mealwright.main import create_app

# Well past the 40 worker threads and the old 15 connections.
AT_ONCE = 100
# The old stall was the pool's 30 seconds. A hundred small reads take well under a second;
# this leaves room for a busy machine and still ends before a stall could.
SANE_SECONDS = 20


@pytest.fixture
def quiet_client(settings: Settings) -> Iterator[TestClient]:
    """Signed in as the admin; a server error comes back as its 500, as it would for real."""
    app = create_app(settings)
    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as client:
        assert client.post("/api/v1/setup", json=ADMIN).status_code == 201
        yield client


@contextmanager
def connections_out(client: TestClient) -> Iterator[list[int]]:
    """Counts the database connections in use; `[0]` is now, `[1]` the most at any moment."""
    engine = client.app.state.engine  # type: ignore[attr-defined]
    count = [0, 0]
    lock = threading.Lock()

    def out(*_: object) -> None:
        with lock:
            count[0] += 1
            count[1] = max(count)

    def back(*_: object) -> None:
        with lock:
            count[0] -= 1

    event.listen(engine, "checkout", out)
    event.listen(engine, "checkin", back)
    try:
        yield count
    finally:
        event.remove(engine, "checkout", out)
        event.remove(engine, "checkin", back)


def all_at_once(client: TestClient, path: str, how_many: int) -> tuple[Counter[int], float]:
    """`how_many` GETs of `path` started together: the answers' status codes, and how long
    the slowest took."""
    together = threading.Barrier(how_many)

    def one(_: int) -> int:
        together.wait()
        return client.get(path).status_code

    started = time.monotonic()
    with ThreadPoolExecutor(how_many) as threads:
        codes = Counter(threads.map(one, range(how_many)))
    return codes, time.monotonic() - started


def test_a_hundred_signed_in_reads_at_once_are_all_answered(quiet_client: TestClient) -> None:
    with connections_out(quiet_client) as count:
        codes, took = all_at_once(quiet_client, "/api/v1/recipes", AT_ONCE)
    assert codes == {200: AT_ONCE}
    assert took < SANE_SECONDS
    # The requests past the limit waited their turn without a connection, and every
    # connection is back.
    assert count[1] <= REQUESTS_AT_ONCE
    assert count[0] == 0


def test_no_more_requests_use_the_database_at_once_than_the_limit(
    settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the limit at 3 (and so a pool of 3 and a few spare), 30 at once never hold more
    than 3 connections between them, and all are answered."""
    monkeypatch.setattr(database, "REQUESTS_AT_ONCE", 3)
    app = create_app(settings)
    with TestClient(app, base_url="https://testserver", raise_server_exceptions=False) as client:
        assert client.post("/api/v1/setup", json=ADMIN).status_code == 201
        with connections_out(client) as count:
            codes, took = all_at_once(client, "/api/v1/recipes", 30)
    assert codes == {200: 30}
    assert took < SANE_SECONDS
    assert 1 <= count[1] <= 3


def test_the_pool_has_a_connection_for_every_request_let_in_and_some_spare(
    settings: Settings,
) -> None:
    """The rule that keeps the pool from running dry: a connection for each request let in,
    plus spare ones for the short reads made beside them (a Privacy switch, the live
    streams' sign-in check, the hourly jobs)."""
    engine = make_engine(settings.sqlalchemy_url)
    pool = engine.pool
    try:
        assert pool.size() + pool._max_overflow >= REQUESTS_AT_ONCE + 10  # type: ignore[attr-defined]
    finally:
        engine.dispose()


def test_the_connection_is_back_before_the_answer_is_sent(quiet_client: TestClient) -> None:
    """A request gives its connection (and its place) back before its answer starts to go
    out, so a browser that reads slowly, or a photo that takes long to send, holds nothing."""
    app = quiet_client.app
    seen: list[int] = []

    with connections_out(quiet_client) as count:

        async def watching(scope, receive, send):  # type: ignore[no-untyped-def]
            async def watched(message):  # type: ignore[no-untyped-def]
                if message["type"] == "http.response.start":
                    seen.append(count[0])
                await send(message)

            await app(scope, receive, watched)

        cookies = dict(quiet_client.cookies)
        with TestClient(watching, base_url="https://testserver", cookies=cookies) as watcher:
            assert watcher.get("/api/v1/recipes").status_code == 200
    assert seen == [0]
