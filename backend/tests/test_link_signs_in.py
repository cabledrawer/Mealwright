"""F254 (cabledrawer 20 Nov): "sign the person in straight away after choosing the first password."

A sign-in link or a Reset password link that sets the password also signs the person in, on the
device that used it. Only that one redemption of the link makes the session: the link is spent
by it, the session is new (never one the request carried), wrong links are slowed down like
wrong passwords, and every other sign-in of that login ends, as a reset already did.
"""

import hashlib
import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import API, db, ok
from test_people import _add, _fresh, _join, _look, _problem

from mealwright.auth import COOKIE
from mealwright.models import Login, Session

PASSWORD = "joss's first password"


def _sessions(kitchen: TestClient, username: str) -> list[Session]:
    with db(kitchen) as session:
        login = session.scalars(select(Login).where(Login.username == username)).one()
        return list(session.scalars(select(Session).where(Session.login_id == login.id)))


def _joss_link(kitchen: TestClient) -> str:
    return _join(kitchen, _add(kitchen, "Joss"), "joss")


def test_choosing_the_first_password_signs_the_person_in(kitchen: TestClient) -> None:
    token = _joss_link(kitchen)
    device = _fresh(kitchen)
    done = device.post(f"{API}/join", json={"token": token, "password": PASSWORD})
    body: dict[str, Any] = ok(done)
    assert body["username"] == "joss"
    assert body["me"]["username"] == "joss" and body["me"]["role"] == "member"
    assert device.cookies.get(COOKIE)  # the session cookie is on this device
    me = ok(device.get(f"{API}/me"))
    assert me["username"] == "joss"
    [only] = _sessions(kitchen, "joss")
    assert only.remember is False  # until the browser closes or the idle timeout, as at setup


def test_the_link_is_spent_by_the_sign_in(kitchen: TestClient) -> None:
    token = _joss_link(kitchen)
    ok(_fresh(kitchen).post(f"{API}/join", json={"token": token, "password": PASSWORD}))
    second = _fresh(kitchen)
    _problem(
        second.post(f"{API}/join", json={"token": token, "password": "another long password"}),
        404,
        "link_gone",
    )
    _problem(_look(_fresh(kitchen), token), 404, "link_gone")
    assert not second.cookies.get(COOKIE)
    assert len(_sessions(kitchen, "joss")) == 1  # only the first redemption made one


def test_a_wrong_link_makes_no_session(kitchen: TestClient) -> None:
    _joss_link(kitchen)
    device = _fresh(kitchen)
    _problem(
        device.post(f"{API}/join", json={"token": "x" * 43, "password": PASSWORD}), 404, "link_gone"
    )
    assert not device.cookies.get(COOKIE)
    assert _sessions(kitchen, "joss") == []


def test_the_session_is_a_new_one_never_one_the_request_carried(kitchen: TestClient) -> None:
    token = _joss_link(kitchen)
    planted = "an-old-or-planted-session-token"
    device = _fresh(kitchen)
    done = device.post(
        f"{API}/join",
        json={"token": token, "password": PASSWORD},
        headers={"Cookie": f"{COOKIE}={planted}"},
    )
    ok(done)
    given = done.cookies.get(COOKIE)
    assert given and given != planted
    [only] = _sessions(kitchen, "joss")
    assert only.token_hash == hashlib.sha256(given.encode()).hexdigest()


def test_a_reset_signs_in_here_and_ends_every_other_sign_in(kitchen: TestClient) -> None:
    joss = _add(kitchen, "Joss")
    ok(
        _fresh(kitchen).post(
            f"{API}/join", json={"token": _join(kitchen, joss, "joss"), "password": PASSWORD}
        )
    )
    elsewhere = _fresh(kitchen)
    ok(elsewhere.post(f"{API}/session", json={"username": "joss", "password": PASSWORD}))
    made = ok(kitchen.post(f"{API}/people/{joss}/reset-password"), 201)
    token = made["path"].removeprefix("/reset#")
    here = _fresh(kitchen)
    ok(here.post(f"{API}/join", json={"token": token, "password": "joss's new password"}))
    assert ok(here.get(f"{API}/me"))["username"] == "joss"
    assert elsewhere.get(f"{API}/me").status_code == 401
    assert len(_sessions(kitchen, "joss")) == 1


def test_a_first_password_ends_other_sign_ins_of_that_login_too(kitchen: TestClient) -> None:
    """Handled as a reset: a login that already had a session (single sign-on, say) keeps only
    the one this link made (proposed, for cabledrawer)."""
    token = _joss_link(kitchen)
    with db(kitchen) as session:
        login = session.scalars(select(Login).where(Login.username == "joss")).one()
        from datetime import timedelta

        from mealwright.models import utcnow

        session.add(
            Session(
                household_id=1,
                login_id=login.id,
                token_hash="0" * 64,
                remember=False,
                created_at=utcnow(),
                last_seen_at=utcnow(),
                expires_at=utcnow() + timedelta(hours=1),
            )
        )
        session.commit()
    ok(_fresh(kitchen).post(f"{API}/join", json={"token": token, "password": PASSWORD}))
    [only] = _sessions(kitchen, "joss")
    assert only.token_hash != "0" * 64


def test_wrong_links_are_slowed_down_like_wrong_passwords(kitchen: TestClient) -> None:
    token = _joss_link(kitchen)
    guesser = _fresh(kitchen)
    codes = [
        guesser.post(f"{API}/join", json={"token": f"guess-{n}", "password": PASSWORD}).status_code
        for n in range(8)
    ]
    assert 429 in codes and codes[0] == 404
    # The pause is the address's, as for passwords: a right link from there waits too, and
    # the link stays unused.
    _problem(
        guesser.post(f"{API}/join", json={"token": token, "password": PASSWORD}),
        429,
        "too_many_tries",
    )
    assert _look(guesser, token).status_code == 429
    assert _sessions(kitchen, "joss") == []


def test_looking_at_wrong_links_is_slowed_down_too(kitchen: TestClient) -> None:
    codes = [_look(_fresh(kitchen), f"guess-{n}").status_code for n in range(8)]
    assert 429 in codes and codes[0] == 404


def test_password_sign_in_off_saves_the_password_without_signing_in(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mealwright.api.v1 import people as api_people

    token = _joss_link(kitchen)
    monkeypatch.setattr(api_people, "password_sign_in_on", lambda *_: False)
    device = _fresh(kitchen)
    body = ok(device.post(f"{API}/join", json={"token": token, "password": PASSWORD}))
    assert body == {"username": "joss", "me": None}
    assert not device.cookies.get(COOKIE)
    assert _sessions(kitchen, "joss") == []


def test_the_sign_in_is_logged_like_any_other(
    kitchen: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    token = _joss_link(kitchen)
    with caplog.at_level(logging.INFO):
        ok(_fresh(kitchen).post(f"{API}/join", json={"token": token, "password": PASSWORD}))
    assert any(r.getMessage().startswith("Signed in: joss from ") for r in caplog.records)
    assert all(PASSWORD not in r.getMessage() for r in caplog.records)
