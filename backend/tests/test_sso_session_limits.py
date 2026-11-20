"""How long a single sign-on sign-in lasts, and signing out (0.9.5, cabledrawer 13 Nov).

S7: after an explicit Sign out, this browser's next "Sign in with …" asks the sign-in server to
ask for the login again (`prompt=login`), until someone signs in with single sign-on here.
S8: with no refresh token to check it with, a single sign-on sign-in lasts one day, "Remember"
or not, then goes back through the sign-in server."""

# ruff: noqa: F811, F401
from datetime import timedelta
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_sso_api import API, ISSUER, SETUP, admin, begin, browser, idp, person_here, sign_in, waits

from mealwright import sso
from mealwright.auth import REMEMBER_FOR, SSO_UNCHECKED_FOR
from mealwright.models import Session


def _asks_login(url: str) -> bool:
    return parse_qs(urlsplit(url).query).get("prompt") == ["login"]


def _finish(client: TestClient, idp: FakeProvider, url: str, username: str = "lorna") -> Any:
    assert url.startswith(f"{ISSUER}/authorize?")
    code, state = idp.sign_in(url, sub=f"{username}-1", extra={"preferred_username": username})
    answer = client.post(f"{API}/sso/finish", json={"state": state, "code": code})
    assert answer.status_code == 200, answer.text
    assert answer.json()["done"] == "signed_in"
    return answer


def _sso_session(client: TestClient) -> Session:
    with cast(Any, client.app).state.sessionmaker() as db:
        session = db.scalars(select(Session).where(Session.sso.is_(True))).one()
        db.expunge(session)
        return session


def _started_earlier(client: TestClient, by: timedelta) -> None:
    """The single sign-on sign-in started `by` ago (and was idle-checked just now)."""
    with cast(Any, client.app).state.sessionmaker() as db:
        session = db.scalars(select(Session).where(Session.sso.is_(True))).one()
        session.created_at = session.created_at - by
        db.commit()


# S7


def test_after_signing_out_the_next_sign_in_asks_for_the_login_again(
    admin: TestClient, idp: FakeProvider
) -> None:
    person_here(admin, "lorna")
    phone = browser(admin)
    assert not _asks_login(begin(phone))
    _finish(phone, idp, begin(phone))
    assert phone.delete(f"{API}/session").status_code == 204
    again = begin(phone)
    assert _asks_login(again)
    # Asked once is enough: signed in with single sign-on again, the next start doesn't ask.
    _finish(phone, idp, again)
    assert not _asks_login(begin(phone))


def test_signing_out_with_a_password_also_asks_next_time(admin: TestClient) -> None:
    """The admin signed in with a password; whoever uses this browser next is asked who they
    are at the sign-in server, too."""
    assert not _asks_login(begin(admin))
    assert admin.delete(f"{API}/session").status_code == 204
    assert _asks_login(begin(admin))


def test_the_signed_out_mark_is_http_only_and_holds_nothing_else(admin: TestClient) -> None:
    gone = admin.delete(f"{API}/session")
    cookie = next(
        c
        for c in gone.headers.get_list("set-cookie")
        if c.startswith("__Host-mealwright_signed_out=")
    )
    assert cookie.startswith("__Host-mealwright_signed_out=1;")
    assert "HttpOnly" in cookie and "Secure" in cookie and "Path=/" in cookie
    assert "samesite=lax" in cookie.lower()


def test_sign_out_on_almost_there_asks_next_time_too(admin: TestClient, idp: FakeProvider) -> None:
    """A sign-in waiting for an admin has no session here, but its Sign out still means the
    next one on this browser asks who it is at the sign-in server."""
    phone = browser(admin)
    answer, _ = sign_in(
        phone, idp, person=False, sub="noor-1", extra={"preferred_username": "noor"}
    )
    assert waits(answer)
    assert phone.delete(f"{API}/session").status_code == 204
    assert _asks_login(begin(phone))


def test_another_browser_isnt_asked_because_someone_signed_out_elsewhere(
    admin: TestClient,
) -> None:
    assert admin.delete(f"{API}/session").status_code == 204
    assert not _asks_login(begin(browser(admin)))


# S8


def test_with_no_refresh_token_a_remembered_sso_sign_in_lasts_one_day(
    admin: TestClient, idp: FakeProvider
) -> None:
    idp.no_refresh_token = True
    person_here(admin, "lorna")
    phone = browser(admin)
    _finish(phone, idp, begin(phone, "/sso/start?remember=true"))
    session = _sso_session(admin)
    assert session.sso_refresh_sealed is None
    assert session.expires_at - session.created_at == SSO_UNCHECKED_FOR
    assert phone.get(f"{API}/me").status_code == 200
    _started_earlier(admin, SSO_UNCHECKED_FOR - timedelta(minutes=5))
    assert phone.get(f"{API}/me").status_code == 200
    # Busy all day, it still ends a day after it started.
    _started_earlier(admin, timedelta(minutes=6))
    assert phone.get(f"{API}/me").status_code == 401


def test_with_a_refresh_token_a_remembered_sso_sign_in_lasts_as_remember_says(
    admin: TestClient, idp: FakeProvider
) -> None:
    idp.discovery_extra = {"scopes_supported": ["openid", "profile", "email", "offline_access"]}
    sso.cache.forget()
    person_here(admin, "lorna")
    phone = browser(admin)
    _finish(phone, idp, begin(phone, "/sso/start?remember=true"))
    session = _sso_session(admin)
    assert session.sso_refresh_sealed is not None
    assert session.expires_at - session.created_at > REMEMBER_FOR - timedelta(minutes=1)
    _started_earlier(admin, timedelta(days=2))
    assert phone.get(f"{API}/me").status_code == 200


def test_a_password_sign_in_isnt_cut_to_a_day(admin: TestClient) -> None:
    with cast(Any, admin.app).state.sessionmaker() as db:
        session = db.scalars(select(Session)).one()
        session.created_at = session.created_at - timedelta(days=2)
        db.commit()
    assert admin.get(f"{API}/me").status_code == 200


def test_a_refresh_token_dropped_by_a_saved_setup_starts_the_day_from_the_drop(
    admin: TestClient, idp: FakeProvider
) -> None:
    """Saving another client drops every refresh token; the people stay signed in, and the one
    day (S8) runs from then, not from when each sign-in started."""
    idp.discovery_extra = {"scopes_supported": ["openid", "profile", "email", "offline_access"]}
    sso.cache.forget()
    person_here(admin, "lorna")
    phone = browser(admin)
    _finish(phone, idp, begin(phone, "/sso/start?remember=true"))
    _started_earlier(admin, timedelta(days=2))
    assert phone.get(f"{API}/me").status_code == 200
    saved = admin.put(f"{API}/sso/settings", json={**SETUP, "client_id": "another-client"})
    assert saved.status_code == 200, saved.text
    session = _sso_session(admin)
    assert session.sso_refresh_sealed is None
    assert phone.get(f"{API}/me").status_code == 200  # still signed in, two days on
    with cast(Any, admin.app).state.sessionmaker() as db:  # a day less five minutes after the drop
        row = db.scalars(select(Session).where(Session.sso.is_(True))).one()
        row.sso_check_at = row.sso_check_at - (SSO_UNCHECKED_FOR - timedelta(minutes=5))
        db.commit()
    assert phone.get(f"{API}/me").status_code == 200
    with cast(Any, admin.app).state.sessionmaker() as db:
        row = db.scalars(select(Session).where(Session.sso.is_(True))).one()
        row.sso_check_at = row.sso_check_at - timedelta(minutes=6)
        db.commit()
    assert phone.get(f"{API}/me").status_code == 401
