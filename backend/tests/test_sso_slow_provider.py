"""A slow or dead sign-in server must not tie up the app (O2 release pass, M availability).

A signed-out stranger can send /sso/start as often as they like. While the sign-in server is
slow and nothing is remembered about it, each start used to hold a database place (and a
thread) for up to 20 s and make its own discovery fetch: 60 at once used every place and
another household's admin waited behind them. Now one fetch is made at a time and shared,
at most four requests of a household wait on the sign-in server, and none of them holds a place
while it waits. No fixed waits: the slow provider is held by an event the test releases."""

import threading
from collections.abc import Callable, Iterator
from typing import Any, cast

import pytest
from fake_idp import FakeProvider, FakeTLS
from fastapi.testclient import TestClient
from test_sso_api import ADMIN_GROUPS, API, SETUP, begin

from mealwright import db as database
from mealwright import outbound, sso

PLACES = 3  # the database places, few, so holding them is visible
STARTS = 12  # more than the places and more than the four a household may have waiting


@pytest.fixture(autouse=True)
def fresh_cache() -> None:
    sso.cache.forget()


@pytest.fixture
def few_places(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(database, "REQUESTS_AT_ONCE", PLACES)


@pytest.fixture
def slow(
    few_places: None, kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> Iterator[tuple[TestClient, FakeProvider, threading.Event, threading.Event]]:
    """The admin's kitchen set up for single sign-on with a provider whose connections are held
    until `release` is set. `reached` is set when the first connection is being made."""
    idp = FakeProvider()
    idp.install(monkeypatch)
    app = cast(Any, kitchen.app)
    app.state.outbound = outbound.OutboundGate(app.state.sessionmaker, tls=cast(Any, FakeTLS()))
    assert kitchen.put(f"{API}/privacy/switches/single_sign_on", json={"on": True}).is_success
    assert kitchen.put(f"{API}/sso/settings", json=SETUP).is_success
    sso.cache.forget()
    reached, release = threading.Event(), threading.Event()
    real = idp.open_socket

    def held(address: str, port: int, timeout: float | None) -> Any:
        reached.set()
        release.wait(30)  # an upper bound only: the test always sets it
        return real(address, port, timeout)

    monkeypatch.setattr(outbound, "_open_socket", held)
    yield kitchen, idp, reached, release
    release.set()


def _in_threads(count: int, work: Callable[[], Any]) -> list[threading.Thread]:
    threads = [threading.Thread(target=work, daemon=True) for _ in range(count)]
    for thread in threads:
        thread.start()
    return threads


def test_a_flood_of_starts_makes_one_fetch_and_leaves_the_places_free(
    slow: tuple[TestClient, FakeProvider, threading.Event, threading.Event],
) -> None:
    """Fails with a connection for every start, and with every place held by a waiting start
    so the admin's own request can't be answered."""
    client, idp, reached, release = slow
    answered: list[int] = []
    lock = threading.Lock()

    def start() -> None:
        r = client.get(f"{API}/sso/start", follow_redirects=False)
        with lock:
            answered.append(r.status_code)

    starts = _in_threads(STARTS, start)
    assert reached.wait(10)
    # The starts past the four allowed to wait are answered at once ("try again").
    for thread in starts:
        thread.join(timeout=0.01)  # a poll, not a wait: collected below
    mine: list[int] = []
    me = _in_threads(1, lambda: mine.append(client.get(f"{API}/me").status_code))[0]
    me.join(timeout=10)  # an upper bound: it is answered at once when no place is held
    assert mine == [200], "the admin's own request waited behind the starts"
    release.set()
    for thread in starts:
        thread.join(timeout=20)
    assert len(answered) == STARTS and set(answered) == {303}
    assert len(idp.connections) == 1  # one discovery fetch, shared


def test_finish_holds_no_database_place_during_the_token_exchange(
    slow: tuple[TestClient, FakeProvider, threading.Event, threading.Event],
) -> None:
    """Fails when `finish` keeps its place while the sign-in server answers the code."""
    client, idp, _, release = slow
    release.set()  # discovery is quick; only the token exchange is held below
    url = begin(client)
    code, state = idp.sign_in(url, sub="k", extra=ADMIN_GROUPS)
    inside, let_go = threading.Event(), threading.Event()

    def token(form: dict[str, str]) -> tuple[int, dict[str, Any]]:
        inside.set()
        let_go.wait(30)  # an upper bound only
        return 400, {"error": "invalid_grant"}

    idp.token_override = token
    answered: list[int] = []
    done = _in_threads(
        1,
        lambda: answered.append(
            client.post(f"{API}/sso/finish", json={"state": state, "code": code}).status_code
        ),
    )[0]
    assert inside.wait(10)
    app = cast(Any, client.app)
    free = [turn._value for turn in app.state.database_turns.values()]  # type: ignore[attr-defined]
    let_go.set()
    done.join(timeout=20)
    assert free == [PLACES], free  # every place free while the exchange waited
    assert answered == [400]


THREADS = 4  # the worker threads, as few as the places, so a thread waiting for a place shows


@pytest.fixture
def healthy(
    few_places: None, kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> tuple[TestClient, FakeProvider]:
    """Set up with a quick provider, discovery remembered, and as few worker threads as places."""
    import anyio
    import anyio.to_thread

    idp = FakeProvider()
    idp.install(monkeypatch)
    app = cast(Any, kitchen.app)
    app.state.outbound = outbound.OutboundGate(app.state.sessionmaker, tls=cast(Any, FakeTLS()))
    assert kitchen.put(f"{API}/privacy/switches/single_sign_on", json={"on": True}).is_success
    assert kitchen.put(f"{API}/sso/settings", json=SETUP).is_success
    sso.cache.forget()

    async def fewer() -> None:
        anyio.to_thread.current_default_thread_limiter().total_tokens = THREADS

    cast(Any, kitchen).portal.call(fewer)
    assert kitchen.get(f"{API}/sso/start", follow_redirects=False).status_code == 303  # remembered
    return kitchen, idp


def test_a_flood_of_starts_with_the_answer_remembered_never_hangs_the_app(
    healthy: tuple[TestClient, FakeProvider],
) -> None:
    """O2 fix11, H1. 80 starts at once with 4 places and 4 threads: a start that gave its place
    back and then waited for one again left every thread waiting for a place and every place
    waiting for a thread. Fails (nothing answered) when the place is given up for an answer
    that was already remembered."""
    client, _ = healthy
    codes: list[int] = []
    lock = threading.Lock()

    def start() -> None:
        code = client.get(f"{API}/sso/start", follow_redirects=False).status_code
        with lock:
            codes.append(code)

    starts = _in_threads(80, start)
    for thread in starts:
        thread.join(timeout=30)  # an upper bound: all are answered at once when nothing hangs
    assert len(codes) == 80 and set(codes) == {303}, "starts were left hanging"
    mine: list[int] = []
    _in_threads(1, lambda: mine.append(client.get(f"{API}/me").status_code))[0].join(timeout=10)
    assert mine == [200]


def test_waiters_are_told_to_try_again_when_the_fetch_fails_unexpectedly(
    slow: tuple[TestClient, FakeProvider, threading.Event, threading.Event],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """O2 fix11, Low: a leader that fails with something other than SsoFailed left the others
    with no answer (a 500). They get "try again", and it is not remembered."""
    client, *_ = slow
    reached, go = threading.Event(), threading.Event()

    def crash(*args: Any, **kwargs: Any) -> Any:
        reached.set()
        go.wait(30)  # an upper bound only
        raise RuntimeError("something unforeseen")

    monkeypatch.setattr(sso, "_discover", crash)
    results: list[Any] = []
    lock = threading.Lock()

    def start() -> None:
        try:
            r = client.get(f"{API}/sso/start", follow_redirects=False)
            outcome: Any = (r.status_code, r.headers.get("location", ""))
        except Exception as error:  # the leader's own unforeseen error
            outcome = error
        with lock:
            results.append(outcome)

    leader = _in_threads(1, start)[0]
    assert reached.wait(10)
    waiters = _in_threads(2, start)
    while sum(sso._in_flight.values()) < 3:  # both are waiting on the leader's fetch
        threading.Event().wait(0.01)
    go.set()
    for thread in [leader, *waiters]:
        thread.join(timeout=20)
    tried_again = [r for r in results if isinstance(r, tuple)]
    assert len(results) == 3 and len(tried_again) == 2, results
    assert all(code == 303 and "sso=unreachable" in where for code, where in tried_again)
    assert sso.cache.get("no_discovery", SETUP["issuer"]) is None
