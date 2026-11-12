"""Sign-in under attack (PR A2, security review r1).

- Someone guessing at a known username from a few addresses mustn't keep its owner out: a
  device that has signed in as that login before skips the username's pause (it keeps its
  own small one, and the address limit still applies). reset-admin lifts the pause too, and
  changing your password has its own count.
- A flood of sign-ins mustn't stall everyone: only a few wait for a hash turn, the rest are
  told "busy" at once.
- Every try is counted before the password is checked, so a burst from one address gets
  its five free guesses and no more.
"""

import io
import threading
import time
from collections.abc import Iterator
from http.cookies import SimpleCookie
from typing import Any

import pytest
from conftest import ADMIN
from fastapi import HTTPException
from fastapi.testclient import TestClient

from mealwright import auth
from mealwright.config import Settings
from mealwright.main import create_app
from mealwright.reset_admin import reset_admin

PASSWORD = ADMIN["password"]
RIGHT = {"username": ADMIN["username"], "password": PASSWORD}
WRONG = {"username": ADMIN["username"], "password": "a wrong guess"}
OWNER = "198.51.100.7"  # documentation addresses (RFC 5737, RFC 3849)
GUESSERS = [f"203.0.113.{n}" for n in range(10)]


class Clock:
    def __init__(self) -> None:
        self.at = 1000.0

    def __call__(self) -> float:
        return self.at


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    ticking = Clock()
    monkeypatch.setattr("mealwright.auth.time.monotonic", ticking)
    return ticking


@pytest.fixture
def proxied(settings: Settings) -> Iterator[TestClient]:
    """Behind a trusted reverse proxy (TestClient plays it), so X-Forwarded-For counts."""
    settings = settings.model_copy(update={"trusted_proxies": "testclient"})
    with TestClient(create_app(settings), base_url="https://testserver") as client:
        assert client.post("/api/v1/setup", json=ADMIN).status_code == 201
        client.delete("/api/v1/session")
        client.cookies.clear()
        yield client


def fresh(client: TestClient) -> TestClient:
    """Another browser on the same server: no cookies."""
    return TestClient(client.app, base_url="https://testserver")


def from_(address: str) -> dict[str, str]:
    return {"X-Forwarded-For": address}


def guess(client: TestClient, address: str, body: dict[str, str] = WRONG) -> int:
    with fresh(client) as other:
        return other.post("/api/v1/session", json=body, headers=from_(address)).status_code


# --- A known device gets past a username's pause ---------------------------------------------


def test_guessing_from_a_few_addresses_doesnt_keep_the_owner_out(
    proxied: TestClient, clock: Clock
) -> None:
    # The owner's phone signed in before, then signed out.
    phone = fresh(proxied)
    assert phone.post("/api/v1/session", json=RIGHT, headers=from_(OWNER)).status_code == 200
    assert phone.delete("/api/v1/session").status_code == 204

    # The review's attack: a wrong guess each time the username's pause runs out (about one
    # a minute), spread over a few addresses so none of them reaches its own limit, keeps the
    # username paused for good.
    held = 0
    for tick in range(120):  # 20 minutes, 10 seconds a tick
        guess(proxied, GUESSERS[tick % len(GUESSERS)])
        if tick >= 10:
            # A browser that never signed in as tess is held up by the username's pause...
            held += guess(proxied, OWNER, RIGHT) == 429
        clock.at += 10
    assert held == 110
    guess(proxied, GUESSERS[0])
    assert guess(proxied, OWNER, RIGHT) == 429
    # ...but the phone that has, gets in.
    answer = phone.post("/api/v1/session", json=RIGHT, headers=from_(OWNER))
    assert answer.status_code == 200


def test_the_known_device_cookie_is_locked_down(client: TestClient) -> None:
    assert client.post("/api/v1/setup", json=ADMIN).status_code == 201
    client.delete("/api/v1/session")
    answer = client.post("/api/v1/session", json=RIGHT)
    headers = [h for h in answer.headers.get_list("set-cookie") if h.startswith(auth.DEVICE_COOKIE)]
    assert len(headers) == 1
    header = headers[0].lower()
    assert "httponly" in header and "secure" in header and "path=/" in header
    assert "samesite=lax" in header and "domain" not in header
    assert f"max-age={int(auth.KNOWN_FOR.total_seconds())}" in header
    # Nothing in it that names the person or the password.
    value = SimpleCookie(headers[0])[auth.DEVICE_COOKIE].value
    assert "tess" not in value and PASSWORD not in value


def test_plain_http_mode_names_the_device_cookie_without_the_prefix(settings: Settings) -> None:
    settings = settings.model_copy(update={"allow_plain_http": True})
    with TestClient(create_app(settings), base_url="http://testserver") as client:
        assert client.post("/api/v1/setup", json=ADMIN).status_code == 201
        assert client.cookies.get(auth.PLAIN_DEVICE_COOKIE)
        assert client.cookies.get(auth.DEVICE_COOKIE) is None


def pause_the_username(client: TestClient) -> None:
    for n in range(6):
        guess(client, f"192.0.2.{n}")
    assert guess(client, OWNER, RIGHT) == 429


def test_a_made_up_device_cookie_doesnt_get_past_the_pause(proxied: TestClient) -> None:
    phone = fresh(proxied)
    assert phone.post("/api/v1/session", json=RIGHT, headers=from_(OWNER)).status_code == 200
    real = phone.cookies[auth.DEVICE_COOKIE]
    login_id, nonce, mac = real.split(".")
    pause_the_username(proxied)
    for made_up in (f"{login_id}.{nonce}.{mac[:-2]}AA", f"{login_id}.other.{mac}", "1.x.y", "~~~"):
        with fresh(proxied) as other:
            other.cookies.set(auth.DEVICE_COOKIE, made_up)
            answer = other.post("/api/v1/session", json=RIGHT, headers=from_(OWNER))
            assert answer.status_code == 429


def test_a_new_password_forgets_the_known_devices(kitchen: TestClient) -> None:
    phone = fresh(kitchen)
    assert phone.post("/api/v1/session", json=RIGHT).status_code == 200
    phone.delete("/api/v1/session")
    new = "a brand new password"
    body = {"current_password": PASSWORD, "new_password": new}
    assert kitchen.put("/api/v1/me/password", json=body).status_code == 200
    for _ in range(6):
        guess(kitchen, "testclient", {"username": "tess", "password": "wrong"})
    answer = phone.post("/api/v1/session", json={"username": "tess", "password": new})
    assert answer.status_code == 429


def test_a_known_devices_wrong_guesses_have_their_own_pause(proxied: TestClient) -> None:
    phone = fresh(proxied)
    assert phone.post("/api/v1/session", json=RIGHT, headers=from_(OWNER)).status_code == 200
    phone.delete("/api/v1/session")
    for n in range(5):
        # From different addresses, so only the device's own count can pause it.
        answer = phone.post("/api/v1/session", json=WRONG, headers=from_(f"192.0.2.{n}"))
        assert answer.status_code == 401
    paused = phone.post("/api/v1/session", json=RIGHT, headers=from_("192.0.2.9"))
    assert paused.status_code == 429
    assert paused.json() == {
        "detail": "Too many wrong passwords for tess. Try again in 30 seconds.",
        "code": "username_paused",
    }
    # The phone's guesses don't pause the username for everyone else.
    assert guess(proxied, OWNER, RIGHT) == 200


# --- reset-admin and change password ------------------------------------------------------------


def test_reset_admin_lifts_the_usernames_pause(client: TestClient) -> None:
    assert client.post("/api/v1/setup", json=ADMIN).status_code == 201
    for _ in range(6):
        guess(client, "testclient")
    assert guess(client, "testclient", RIGHT) == 429
    # The address pause is the guesser's own; only the username's is lifted.
    client.app.state.slow_down.succeeded("addr:testclient")  # type: ignore[attr-defined]
    out = io.StringIO()
    assert reset_admin(client.app.state.settings, "tess", out) == 0  # type: ignore[attr-defined]
    password = out.getvalue().split("New password for tess: ")[1].split()[0]
    assert guess(client, "testclient", {"username": "tess", "password": password}) == 200


def test_sign_in_guessing_doesnt_block_changing_your_password(kitchen: TestClient) -> None:
    for _ in range(6):
        guess(kitchen, "testclient")
    kitchen.app.state.slow_down.succeeded("addr:testclient")  # type: ignore[attr-defined]
    assert guess(kitchen, "testclient", RIGHT) == 429  # tess is paused at sign-in
    body = {"current_password": PASSWORD, "new_password": "a brand new password"}
    assert kitchen.put("/api/v1/me/password", json=body).status_code == 200


def test_change_password_guessing_doesnt_pause_signing_in(kitchen: TestClient) -> None:
    body = {"current_password": "not it", "new_password": "a brand new password"}
    for _ in range(5):
        assert kitchen.put("/api/v1/me/password", json=body).status_code == 422
    assert kitchen.put("/api/v1/me/password", json=body).status_code == 429
    assert guess(kitchen, "testclient", RIGHT) == 200


# --- A flood waits in a small room ----------------------------------------------------------------


def test_only_a_few_wait_for_a_hash_turn(monkeypatch: pytest.MonkeyPatch) -> None:
    taken = threading.BoundedSemaphore(auth.HASHES_AT_ONCE)
    for _ in range(auth.HASHES_AT_ONCE):
        taken.acquire()
    monkeypatch.setattr(auth, "_hash_turns", taken)
    monkeypatch.setattr(auth, "WAIT_FOR_A_TURN", 3.0)
    busy: list[float] = []
    done: list[float] = []
    started = time.monotonic()

    def one() -> None:
        try:
            auth.check_password(None, "a guess")
            done.append(time.monotonic() - started)
        except HTTPException as refused:
            assert refused.status_code == 503
            busy.append(time.monotonic() - started)

    threads = [threading.Thread(target=one) for _ in range(20)]
    for thread in threads:
        thread.start()
    time.sleep(0.5)
    # The ones beyond the waiting room are told at once; the rest are still waiting.
    assert len(busy) == 20 - auth.WAITING_ROOM
    assert all(seconds < 0.5 for seconds in busy)
    assert 1 <= auth.WAITING_ROOM <= 4
    for _ in range(auth.HASHES_AT_ONCE):
        taken.release()
    for thread in threads:
        thread.join()
    assert len(done) == auth.WAITING_ROOM  # those who waited got their turn


def test_ipv6_addresses_count_by_their_64(proxied: TestClient) -> None:
    for n in range(5):
        body = {"username": f"guess-{n}", "password": "x"}
        assert guess(proxied, f"2001:db8:1:2::{n + 1}", body) == 401
    # The next address in the same /64 is the same guesser...
    assert guess(proxied, "2001:db8:1:2:ffff::9", RIGHT) == 429
    # ...a neighbouring /64 isn't.
    assert guess(proxied, "2001:db8:1:3::1", RIGHT) == 200


# --- Every try is counted before the hash ---------------------------------------------------


class SlowHasher:
    """The cheap test hasher, slowed down and counting how many passwords it judged."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.judged = 0
        self.lock = threading.Lock()

    def hash(self, password: str) -> str:
        return str(self.inner.hash(password))

    def verify(self, stored: str, password: str) -> bool:
        with self.lock:
            self.judged += 1
        time.sleep(0.05)
        return bool(self.inner.verify(stored, password))

    def check_needs_rehash(self, stored: str) -> bool:
        return bool(self.inner.check_needs_rehash(stored))


def burst(count: int, send: Any) -> list[int]:
    answers: list[int] = []
    lock = threading.Lock()
    gate = threading.Barrier(count)

    def one() -> None:
        gate.wait()
        status = send()
        with lock:
            answers.append(status)

    threads = [threading.Thread(target=one) for _ in range(count)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return answers


def test_a_burst_of_guesses_gets_five_and_no_more(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    slow = SlowHasher(auth._hasher)
    monkeypatch.setattr(auth, "_hasher", slow)
    monkeypatch.setattr(auth, "WAIT_FOR_A_TURN", 30.0)
    monkeypatch.setattr(auth, "WAITING_ROOM", 100, raising=False)  # all may wait here
    answers = burst(40, lambda: kitchen.post("/api/v1/session", json=WRONG).status_code)
    assert slow.judged == auth.SlowDown.FREE
    assert answers.count(401) == auth.SlowDown.FREE
    assert answers.count(429) == 40 - auth.SlowDown.FREE


def test_a_burst_of_change_password_guesses_gets_five_and_no_more(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    slow = SlowHasher(auth._hasher)
    monkeypatch.setattr(auth, "_hasher", slow)
    monkeypatch.setattr(auth, "WAIT_FOR_A_TURN", 30.0)
    monkeypatch.setattr(auth, "WAITING_ROOM", 100, raising=False)
    body = {"current_password": "not it", "new_password": "a brand new password"}
    answers = burst(40, lambda: kitchen.put("/api/v1/me/password", json=body).status_code)
    assert slow.judged == auth.SlowDown.FREE
    assert answers.count(422) == auth.SlowDown.FREE


def test_a_right_password_gives_its_try_back(kitchen: TestClient) -> None:
    slow: auth.SlowDown = kitchen.app.state.slow_down  # type: ignore[attr-defined]
    for _ in range(4):
        assert guess(kitchen, "testclient") == 401
    for _ in range(3):  # right passwords never use up the address's free guesses
        assert guess(kitchen, "testclient", RIGHT) == 200
    assert slow.wait_seconds(["addr:testclient"]) == 0
    assert guess(kitchen, "testclient") == 401  # the 5th wrong one


def test_a_busy_answer_gives_its_try_back(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    taken = threading.BoundedSemaphore(auth.HASHES_AT_ONCE)
    for _ in range(auth.HASHES_AT_ONCE):
        taken.acquire()
    monkeypatch.setattr(auth, "_hash_turns", taken)
    monkeypatch.setattr(auth, "WAIT_FOR_A_TURN", 0.01)
    for _ in range(10):
        assert guess(kitchen, "testclient", RIGHT) == 503
    slow: auth.SlowDown = kitchen.app.state.slow_down  # type: ignore[attr-defined]
    assert slow.wait_seconds(["addr:testclient", "user:tess"]) == 0
    assert slow._failures == {}


def test_the_setup_code_burst_gets_five_and_no_more(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mealwright import setup_code

    judged = []
    real = setup_code.matches

    def slow_match(expected: str | None, typed: str) -> bool:
        judged.append(typed)
        time.sleep(0.05)
        return real(expected, typed)

    monkeypatch.setattr(setup_code, "matches", slow_match)
    wrong = ADMIN | {"setup_code": "ABCD-EFGH-JKMN"}
    answers = burst(30, lambda: client.post("/api/v1/setup", json=wrong).status_code)
    assert len(judged) == auth.SlowDown.FREE
    assert answers.count(403) == auth.SlowDown.FREE
