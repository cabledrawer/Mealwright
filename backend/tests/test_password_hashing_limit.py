"""Only a few Argon2 hashes run at a time (review of v0.6.0, PR A2).

Each hash takes 64 MiB and a moment, so a burst of sign-ins could otherwise use up the
server's memory. Beyond the limit a request waits briefly for a turn, then gets a plain
"busy" answer, never a crash.
"""

import threading
import time
from typing import Any

import pytest
from conftest import ADMIN
from fastapi.testclient import TestClient

from mealwright import auth


class CountingHasher:
    """Wraps the cheap test hasher, counting how many hashes run at once."""

    def __init__(self, inner: Any) -> None:
        self.inner = inner
        self.lock = threading.Lock()
        self.now = 0
        self.most = 0

    def _run(self, call: Any, *args: Any) -> Any:
        with self.lock:
            self.now += 1
            self.most = max(self.most, self.now)
        try:
            time.sleep(0.05)  # long enough for the threads to overlap
            return call(*args)
        finally:
            with self.lock:
                self.now -= 1

    def hash(self, password: str) -> str:
        return str(self._run(self.inner.hash, password))

    def verify(self, stored: str, password: str) -> bool:
        return bool(self._run(self.inner.verify, stored, password))

    def check_needs_rehash(self, stored: str) -> bool:
        return bool(self.inner.check_needs_rehash(stored))


def test_no_more_than_a_few_hashes_at_once(monkeypatch: pytest.MonkeyPatch) -> None:
    counting = CountingHasher(auth._hasher)
    monkeypatch.setattr(auth, "_hasher", counting)
    monkeypatch.setattr(auth, "WAIT_FOR_A_TURN", 30.0)  # all of them get a turn here
    threads = [
        threading.Thread(target=auth.hash_password, args=(f"password number {n}",))
        for n in range(8)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert counting.most == auth.HASHES_AT_ONCE
    assert 1 < auth.HASHES_AT_ONCE <= 4  # "a few"


def test_a_sign_in_that_gets_no_turn_is_told_to_try_again(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Every turn is taken (by other sign-ins), and none comes free in time.
    taken = threading.BoundedSemaphore(auth.HASHES_AT_ONCE)
    for _ in range(auth.HASHES_AT_ONCE):
        taken.acquire()
    monkeypatch.setattr(auth, "_hash_turns", taken)
    monkeypatch.setattr(auth, "WAIT_FOR_A_TURN", 0.05)
    body = {"username": ADMIN["username"], "password": ADMIN["password"]}
    response = kitchen.post("/api/v1/session", json=body)
    assert response.status_code == 503
    assert response.json() == {
        "detail": "Mealwright is busy. Try again in a few seconds.",
        "code": "busy",
    }
    assert response.headers["retry-after"] == "5"
    # A busy answer isn't a wrong guess: it doesn't count towards the slow-down.
    assert kitchen.app.state.slow_down.wait_seconds([f"user:{ADMIN['username']}"]) == 0  # type: ignore[attr-defined]

    # Once a turn is free, signing in works again.
    taken.release()
    assert kitchen.post("/api/v1/session", json=body).status_code == 200


def test_a_turn_is_given_back_when_hashing_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    class Broken:
        def hash(self, password: str) -> str:
            raise RuntimeError("out of memory")

    monkeypatch.setattr(auth, "_hasher", Broken())
    turns = threading.BoundedSemaphore(1)
    monkeypatch.setattr(auth, "_hash_turns", turns)
    with pytest.raises(RuntimeError):
        auth.hash_password("a long enough password")
    assert turns.acquire(blocking=False)  # the turn came back
