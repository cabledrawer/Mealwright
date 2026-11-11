"""The sign-in slow-down behind a reverse proxy (Caddy).

It counts wrong guesses per account and per real visitor address, taken from the
proxy's X-Forwarded-For header, which is believed only from MEALWRIGHT_TRUSTED_PROXIES.
So one person's wrong guesses slow down that person (and the account they're
guessing at), never everyone else.
"""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mealwright.auth import hash_password
from mealwright.config import Settings
from mealwright.main import create_app
from mealwright.models import Login

PASSWORD = "kitchen-secret-2026"
GUESSER = "203.0.113.5"  # documentation addresses (RFC 5737)
FAMILY = "198.51.100.7"


def make_client(tmp_path: Path, trusted_proxies: str) -> TestClient:
    # TestClient connects from the address "testclient", playing the reverse proxy.
    settings = Settings(data_dir=tmp_path / "data", trusted_proxies=trusted_proxies)
    return TestClient(create_app(settings), base_url="https://testserver")


def set_up_household(client: TestClient) -> None:
    body = {"name": "Tess", "username": "tess", "password": PASSWORD}
    assert client.post("/api/v1/setup", json=body).status_code == 201
    client.delete("/api/v1/session")
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(
            Login(
                household_id=1,
                username="alex",
                name="Alex",
                password_hash=hash_password(PASSWORD),
                role="member",
            )
        )
        db.commit()


def attempt(client: TestClient, username: str, password: str, address: str) -> int:
    response = client.post(
        "/api/v1/session",
        json={"username": username, "password": password},
        headers={"X-Forwarded-For": address},
    )
    client.cookies.clear()
    return response.status_code


@pytest.fixture
def behind_caddy(tmp_path: Path) -> Iterator[TestClient]:
    with make_client(tmp_path, trusted_proxies="testclient") as client:
        set_up_household(client)
        yield client


def test_one_persons_guesses_dont_slow_down_others(behind_caddy: TestClient) -> None:
    for _ in range(5):
        assert attempt(behind_caddy, "tess", "wrong-guess", GUESSER) == 401
    # The guesser now has to wait...
    assert attempt(behind_caddy, "tess", "wrong-guess", GUESSER) == 429
    # ...but someone else, from their own address, signs in to their own account at once.
    assert attempt(behind_caddy, "alex", PASSWORD, FAMILY) == 200


def test_guessing_many_accounts_slows_down_only_the_guesser(behind_caddy: TestClient) -> None:
    for name in ("a", "b", "c", "d", "e"):
        assert attempt(behind_caddy, name, "wrong-guess", GUESSER) == 401
    # A new username doesn't help the guesser: their address is counted too.
    assert attempt(behind_caddy, "alex", "wrong-guess", GUESSER) == 429
    # Everyone else is unaffected.
    assert attempt(behind_caddy, "tess", PASSWORD, FAMILY) == 200
    assert attempt(behind_caddy, "alex", PASSWORD, FAMILY) == 200


def test_the_account_being_guessed_at_is_protected(behind_caddy: TestClient) -> None:
    # By design, the account itself also waits, wherever the next try comes from, so
    # a guesser can't get around the slow-down by changing address.
    for _ in range(5):
        attempt(behind_caddy, "tess", "wrong-guess", GUESSER)
    assert attempt(behind_caddy, "tess", PASSWORD, FAMILY) == 429
    # Other accounts are unaffected.
    assert attempt(behind_caddy, "alex", PASSWORD, FAMILY) == 200


def test_the_log_shows_the_real_address(
    behind_caddy: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="mealwright"):
        attempt(behind_caddy, "tess", "wrong-guess", GUESSER)
    assert f"from {GUESSER}" in caplog.text


def test_forwarded_headers_from_anyone_else_are_ignored(tmp_path: Path) -> None:
    # The proxy is configured as 10.9.9.9, but requests arrive from "testclient".
    # A guesser making up a new X-Forwarded-For each time still counts as one address.
    with make_client(tmp_path, trusted_proxies="10.9.9.9") as client:
        set_up_household(client)
        fake_addresses = [f"192.0.2.{n}" for n in range(1, 7)]
        names = ["a", "b", "c", "d", "e", "f"]
        results = [
            attempt(client, name, "wrong-guess", fake)
            for name, fake in zip(names, fake_addresses, strict=True)
        ]
        assert results == [401, 401, 401, 401, 401, 429]


def test_forwarded_headers_are_ignored_by_default(tmp_path: Path) -> None:
    # MEALWRIGHT_TRUSTED_PROXIES is empty unless the admin sets it.
    with TestClient(
        create_app(Settings(data_dir=tmp_path / "data")), base_url="https://testserver"
    ) as client:
        set_up_household(client)
        results = [
            attempt(client, name, "wrong-guess", f"192.0.2.{n}")
            for n, name in enumerate(["a", "b", "c", "d", "e", "f"], start=1)
        ]
        assert results == [401, 401, 401, 401, 401, 429]


def test_a_made_up_address_in_front_of_the_proxys_is_ignored(behind_caddy: TestClient) -> None:
    # nginx's usual setting adds the visitor's real address after whatever the visitor
    # sent, so the guesser's made-up first entry must be ignored: the last address
    # added by the trusted proxy counts.
    for n in range(5):
        assert attempt(behind_caddy, f"user{n}", "wrong-guess", f"192.0.2.{n}, {GUESSER}") == 401
    assert attempt(behind_caddy, "user9", "wrong-guess", f"192.0.2.99, {GUESSER}") == 429
    assert attempt(behind_caddy, "alex", PASSWORD, FAMILY) == 200
