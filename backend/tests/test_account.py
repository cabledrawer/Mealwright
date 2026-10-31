"""First-run setup, signing in and out, sessions and the slow-down (spec section 7)."""

import hashlib
import logging
from datetime import UTC, datetime, timedelta

import pytest
from conftest import CHEAP_HASHER
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from mealwright import auth
from mealwright.api.v1.account import how_long
from mealwright.auth import COOKIE, IDLE_TIMEOUT, LONGEST_SIGN_IN, SlowDown, now
from mealwright.models import Login, Session

ADMIN = {"name": "Tess", "username": "tess", "password": "kitchen-secret-2026"}


def set_up(client: TestClient) -> None:
    assert client.post("/api/v1/setup", json=ADMIN).status_code == 201


def sign_in(client: TestClient, password: str = ADMIN["password"], **extra: object) -> int:
    body = {"username": "tess", "password": password, **extra}
    return client.post("/api/v1/session", json=body).status_code


def cookie_header(client: TestClient, path: str = "/api/v1/session") -> str:
    response = client.post(path, json={"username": "tess", "password": ADMIN["password"]})
    return response.headers["set-cookie"]


def db(client: TestClient):  # type: ignore[no-untyped-def]
    return client.app.state.sessionmaker()  # type: ignore[attr-defined]


# --- First run ----------------------------------------------------------------------------


def test_fresh_install_needs_setup(client: TestClient) -> None:
    assert client.get("/api/v1/setup").json()["needs_setup"] is True
    assert client.get("/api/v1/me").status_code == 401


def test_setup_creates_the_admin_and_signs_in(client: TestClient) -> None:
    response = client.post("/api/v1/setup", json=ADMIN)
    assert response.status_code == 201
    assert response.json() == {
        "id": 1,
        "name": "Tess",
        "username": "tess",
        "role": "admin",
        "theme": "auto",
    }
    assert client.get("/api/v1/setup").json()["needs_setup"] is False
    assert client.get("/api/v1/me").json()["username"] == "tess"


def test_setup_only_works_once(client: TestClient) -> None:
    set_up(client)
    other = {"name": "Someone", "username": "someone", "password": "another-password"}
    assert client.post("/api/v1/setup", json=other).status_code == 409


def test_setup_race_is_refused(client: TestClient) -> None:
    # Another request created the household a moment earlier.
    from mealwright.models import Household

    with db(client) as session:
        session.add(Household(id=1, name="Home"))
        session.commit()
    assert client.post("/api/v1/setup", json=ADMIN).status_code == 409


@pytest.mark.parametrize(
    "change",
    [
        {"password": "short"},  # under 10 characters
        {"username": "Has Space"},
        {"username": ""},
        {"name": "   "},
    ],
)
def test_setup_checks_its_input(client: TestClient, change: dict[str, str]) -> None:
    assert client.post("/api/v1/setup", json=ADMIN | change).status_code == 422
    assert client.get("/api/v1/setup").json()["needs_setup"] is True


# argon2-cffi's defaults (RFC 9106): 64 MiB, 3 passes, 4 lanes. The tests hash cheaply
# (conftest.py, cabledrawer 31 Oct) except where marked `real_hashing`.
APP_HASH = "$argon2id$v=19$m=65536,t=3,p=4$"


@pytest.mark.real_hashing
def test_password_is_stored_scrambled(client: TestClient) -> None:
    set_up(client)
    with db(client) as session:
        stored = session.scalar(select(Login.password_hash))
    assert stored is not None
    assert stored.startswith(APP_HASH)
    assert ADMIN["password"] not in stored


@pytest.mark.real_hashing
def test_a_weaker_stored_hash_is_made_stronger_at_sign_in(client: TestClient) -> None:
    set_up(client)
    with db(client) as session:
        session.execute(update(Login).values(password_hash=CHEAP_HASHER.hash(ADMIN["password"])))
        session.commit()
    assert sign_in(client) == 200
    with db(client) as session:
        stored = session.scalar(select(Login.password_hash))
    assert stored is not None
    assert stored.startswith(APP_HASH)


def test_the_other_tests_hash_cheaply(client: TestClient) -> None:
    set_up(client)
    with db(client) as session:
        stored = session.scalar(select(Login.password_hash))
    assert stored is not None
    assert stored.startswith("$argon2id$v=19$m=8,t=1,p=1$")


# --- Signing in and out ----------------------------------------------------------------------


def test_sign_in_and_out(client: TestClient) -> None:
    set_up(client)
    client.delete("/api/v1/session")
    assert client.get("/api/v1/me").status_code == 401
    assert sign_in(client) == 200
    assert client.get("/api/v1/me").status_code == 200
    assert client.delete("/api/v1/session").status_code == 204
    assert client.get("/api/v1/me").status_code == 401


def test_username_ignores_case_and_spaces(client: TestClient) -> None:
    set_up(client)
    body = {"username": "  Tess ", "password": ADMIN["password"]}
    assert client.post("/api/v1/session", json=body).status_code == 200


def test_wrong_password_and_unknown_user_look_the_same(client: TestClient) -> None:
    set_up(client)
    wrong = client.post("/api/v1/session", json={"username": "tess", "password": "nope"})
    unknown = client.post("/api/v1/session", json={"username": "nobody", "password": "nope"})
    assert wrong.status_code == unknown.status_code == 401
    assert wrong.json() == unknown.json() == {"detail": "That username and password don’t match."}


def test_session_cookie_is_locked_down(client: TestClient) -> None:
    set_up(client)
    header = cookie_header(client).lower()
    assert header.startswith(f"{COOKIE}=")
    for part in ("httponly", "secure", "samesite=lax", "path=/"):
        assert part in header
    assert "max-age" not in header  # forgotten when the browser closes


def test_remember_this_device_keeps_the_cookie_30_days(client: TestClient) -> None:
    set_up(client)
    response = client.post(
        "/api/v1/session",
        json={"username": "tess", "password": ADMIN["password"], "remember": True},
    )
    assert f"max-age={30 * 24 * 3600}" in response.headers["set-cookie"].lower()


def test_only_a_hash_of_the_token_is_stored(client: TestClient) -> None:
    set_up(client)
    token = client.cookies[COOKIE]
    with db(client) as session:
        hashes = session.scalars(select(Session.token_hash)).all()
    assert token not in hashes
    assert hashlib.sha256(token.encode()).hexdigest() in hashes


def test_idle_session_ends(client: TestClient) -> None:
    set_up(client)
    with db(client) as session:
        session.execute(update(Session).values(expires_at=now() - timedelta(seconds=1)))
        session.commit()
    assert client.get("/api/v1/me").status_code == 401


def test_using_a_session_keeps_it_alive(client: TestClient) -> None:
    set_up(client)
    # Last used an hour ago, and about to run out.
    with db(client) as session:
        session.execute(
            update(Session).values(
                last_seen_at=now() - timedelta(hours=1), expires_at=now() + timedelta(minutes=1)
            )
        )
        session.commit()
    assert client.get("/api/v1/me").status_code == 200
    with db(client) as session:
        expires = session.scalar(select(Session.expires_at))
    assert expires is not None
    # Using it pushed the end back to 12 hours from now.
    assert expires.replace(tzinfo=UTC) > now() + IDLE_TIMEOUT - timedelta(minutes=1)


class Clock:
    """Time travel for sign-ins: `auth.now()` answers whatever `at` is set to."""

    def __init__(self) -> None:
        self.at = now()

    def __call__(self) -> datetime:
        return self.at


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Clock:
    clock = Clock()
    monkeypatch.setattr(auth, "now", clock)
    return clock


def test_unused_for_12_hours_ends_the_sign_in(client: TestClient, clock: Clock) -> None:
    set_up(client)  # without "Remember this device"
    clock.at += IDLE_TIMEOUT - timedelta(minutes=1)
    assert client.get("/api/v1/me").status_code == 200
    clock.at += IDLE_TIMEOUT
    assert client.get("/api/v1/me").status_code == 401


def test_a_sign_in_used_every_day_still_ends_at_30_days(client: TestClient, clock: Clock) -> None:
    # cabledrawer 19 Oct: 30 days at most in total, as with "Remember this device".
    assert LONGEST_SIGN_IN.days == 30
    set_up(client)  # without "Remember this device"
    started = clock.at
    # Used every 10 hours, so the 12 hours without use never run out.
    while clock.at + timedelta(hours=10) < started + LONGEST_SIGN_IN:
        clock.at += timedelta(hours=10)
        assert client.get("/api/v1/me").status_code == 200, clock.at - started
        with db(client) as session:
            expires = session.scalar(select(Session.expires_at))
        assert expires is not None
        assert expires.replace(tzinfo=UTC) <= started + LONGEST_SIGN_IN
    clock.at = started + LONGEST_SIGN_IN - timedelta(minutes=1)
    assert client.get("/api/v1/me").status_code == 200
    clock.at = started + LONGEST_SIGN_IN
    assert client.get("/api/v1/me").status_code == 401
    assert client.get("/api/v1/events").status_code == 401  # nor the live updates
    with db(client) as session:
        assert session.scalars(select(Session)).all() == []


def test_remember_this_device_also_ends_at_30_days(client: TestClient, clock: Clock) -> None:
    set_up(client)
    client.delete("/api/v1/session")
    started = clock.at
    assert sign_in(client, remember=True) == 200
    clock.at = started + timedelta(days=29)
    assert client.get("/api/v1/me").status_code == 200
    clock.at = started + LONGEST_SIGN_IN
    assert client.get("/api/v1/me").status_code == 401


def test_signing_out_deletes_the_session(client: TestClient) -> None:
    set_up(client)
    client.delete("/api/v1/session")
    with db(client) as session:
        assert session.scalars(select(Session)).all() == []


# --- Slow-down after wrong guesses ------------------------------------------------------------


def test_slow_down_after_five_wrong_guesses(client: TestClient) -> None:
    set_up(client)
    for _ in range(5):
        assert sign_in(client, "wrong-password") == 401
    blocked = client.post(
        "/api/v1/session", json={"username": "tess", "password": ADMIN["password"]}
    )
    # Even the right password has to wait.
    assert blocked.status_code == 429
    assert int(blocked.headers["retry-after"]) > 0
    assert blocked.json()["detail"] == "Too many tries. Wait 30 seconds."


@pytest.mark.parametrize(
    ("seconds", "words"),
    [
        (1, "1 second"),
        (30, "30 seconds"),
        (59, "59 seconds"),
        (60, "1 minute"),
        (61, "2 minutes"),  # never shorter than the real wait
        (120, "2 minutes"),
        (15 * 60, "15 minutes"),
    ],
)
def test_wait_in_plain_words(seconds: int, words: str) -> None:
    assert how_long(seconds) == words


def test_slow_down_timing() -> None:
    slow = SlowDown()
    keys = ["user:tess", "addr:1.2.3.4"]
    for i in range(5):
        assert slow.wait_seconds(keys, at=float(i)) == 0
        slow.failed(keys, at=float(i))
    assert slow.wait_seconds(keys, at=4.0) == 30  # after the 5th wrong guess
    assert slow.wait_seconds(keys, at=4.9995) == 30  # 29.0005 s left still says 30
    assert slow.wait_seconds(keys, at=34.0) == 0
    slow.failed(keys, at=34.0)
    assert slow.wait_seconds(keys, at=34.0) == 60  # doubles
    for t in range(35, 45):
        slow.failed(keys, at=float(t))
    assert slow.wait_seconds(keys, at=44.0) == 15 * 60  # capped at 15 minutes
    # Old guesses drop out after 15 minutes.
    assert slow.wait_seconds(keys, at=44.0 + 15 * 60 + 1) == 0


def test_right_password_clears_the_username_count() -> None:
    slow = SlowDown()
    for i in range(4):
        slow.failed(["user:tess"], at=float(i))
    slow.succeeded("user:tess")
    slow.failed(["user:tess"], at=5.0)
    assert slow.wait_seconds(["user:tess"], at=5.0) == 0


# --- Other sites can't act for you ---------------------------------------------------------------


def test_requests_from_other_sites_are_refused(client: TestClient) -> None:
    set_up(client)
    body = {"username": "tess", "password": ADMIN["password"]}
    evil = client.post("/api/v1/session", json=body, headers={"Origin": "https://evil.example"})
    assert evil.status_code == 403
    null = client.post("/api/v1/session", json=body, headers={"Origin": "null"})
    assert null.status_code == 403
    ours = client.post("/api/v1/session", json=body, headers={"Origin": "https://testserver"})
    assert ours.status_code == 200


# --- Preferences --------------------------------------------------------------------------------


def test_theme_preference(client: TestClient) -> None:
    set_up(client)
    response = client.put("/api/v1/me/preferences", json={"theme": "dark"})
    assert response.status_code == 200
    assert client.get("/api/v1/me").json()["theme"] == "dark"
    assert client.put("/api/v1/me/preferences", json={"theme": "purple"}).status_code == 422


def test_preferences_need_sign_in(client: TestClient) -> None:
    assert client.put("/api/v1/me/preferences", json={"theme": "dark"}).status_code == 401


def test_the_message_matches_the_real_lock(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    clock = [1000.0]
    monkeypatch.setattr("mealwright.auth.time.monotonic", lambda: clock[0])
    set_up(client)
    for _ in range(5):
        assert sign_in(client, "wrong-password") == 401
    blocked = client.post("/api/v1/session", json={"username": "tess", "password": "x"})
    assert blocked.json()["detail"] == "Too many tries. Wait 30 seconds."
    assert blocked.headers["retry-after"] == "30"
    clock[0] += 29.5
    assert sign_in(client, "wrong-password") == 429  # still locked half a second before
    clock[0] += 0.5
    assert sign_in(client, "wrong-password") == 401  # checked normally at 30 s
    # The 6th wrong guess doubles the wait, and the message says so.
    blocked = client.post("/api/v1/session", json={"username": "tess", "password": "x"})
    assert blocked.json()["detail"] == "Too many tries. Wait 1 minute."
    clock[0] += 59.5
    assert sign_in(client) == 429
    clock[0] += 0.5
    assert sign_in(client) == 200


def test_slow_down_is_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    set_up(client)
    with caplog.at_level(logging.WARNING, logger="mealwright"):
        for _ in range(5):
            sign_in(client, "wrong-password")
        # Refused tries cost the guesser nothing, so they must not each write a line:
        # that would let anyone fill the disk.
        for _ in range(200):
            assert sign_in(client) == 429
    assert caplog.text.count("Sign-in failed for tess from testclient") == 5
    assert caplog.text.count("Sign-in slowed down") == 1
    assert "Sign-in slowed down for tess from testclient (wait 30 s)" in caplog.text
    assert len(caplog.records) == 6


def test_unknown_usernames_are_not_logged(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    set_up(client)
    typed = "my-secret-password-in-the-wrong-box"
    with caplog.at_level(logging.INFO, logger="mealwright"):
        for _ in range(6):  # 5 wrong guesses start the slow-down; the 6th is refused
            client.post("/api/v1/session", json={"username": typed, "password": "x"})
    assert typed not in caplog.text
    assert "Sign-in failed for unknown user from testclient" in caplog.text
    assert "Sign-in failed for tess" not in caplog.text
    assert "Sign-in slowed down for unknown user from testclient" in caplog.text


def test_every_sign_in_is_logged(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="mealwright"):
        set_up(client)  # setup signs the admin in too
        client.delete("/api/v1/session")
        for remember in (False, True, False):
            assert sign_in(client, remember=remember) == 200
            client.delete("/api/v1/session")
    signed_in = [r for r in caplog.records if r.getMessage().startswith("Signed in: tess")]
    assert len(signed_in) == 4


def test_looking_up_made_up_names_keeps_no_memory() -> None:
    slow = SlowDown()
    for i in range(1000):
        assert slow.wait_seconds([f"user:made-up-{i}", f"addr:10.0.{i // 256}.{i % 256}"]) == 0
    assert slow._failures == {}
    slow.failed(["user:tess"], at=0.0)
    assert slow.wait_seconds(["user:tess"], at=15 * 60 + 1) == 0
    assert slow._failures == {}  # dropped once its guesses are old


def test_a_name_typed_once_is_forgotten() -> None:
    slow = SlowDown()
    slow.failed(["user:my-password-in-the-wrong-box", "addr:1.2.3.4"], at=0.0)
    slow.failed(["user:tess", "addr:5.6.7.8"], at=15 * 60 + 1)
    assert set(slow._failures) == {"user:tess", "addr:5.6.7.8"}
