"""Single sign-on through the API (0.9 O1): the setup, signing in, accounts and roles, password
sign-in turned off, and the refresh job. The sign-in server is tests/fake_idp.py, on a fake
network: nothing goes online."""

import io
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import ADMIN
from fake_idp import CLIENT_ID, CLIENT_SECRET, ISSUER, FakeProvider, FakeTLS
from fastapi.testclient import TestClient
from sqlalchemy import select

from mealwright import sso, sso_accounts
from mealwright.auth import hash_password, now
from mealwright.history import as_utc
from mealwright.models import Login, Member, Session, SsoSettings
from mealwright.outbound import OutboundGate
from mealwright.reset_admin import reset_admin

API = "/api/v1"
REDIRECT = "https://testserver/auth/callback"
SETUP = {
    "issuer": ISSUER,
    "client_id": CLIENT_ID,
    "client_secret": CLIENT_SECRET,
    "button_name": "Authentik",
    "redirect_uri": REDIRECT,
    "group_claim": "groups",
    "group_roles": [
        {"group": "mealwright-admins", "role": "admin"},
        {"group": "mealwright-users", "role": "member"},
    ],
    "anyone_else": "none",
    "make_accounts": True,
    "password_sign_in": True,
}


@pytest.fixture(autouse=True)
def fresh_cache() -> None:
    sso.cache.forget()


@pytest.fixture
def idp(monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    provider = FakeProvider()
    provider.install(monkeypatch)
    return provider


@pytest.fixture
def admin(kitchen: TestClient, idp: FakeProvider) -> TestClient:
    """Signed in as the admin, with the switch on and the setup saved."""
    app = cast(Any, kitchen.app)
    app.state.outbound = OutboundGate(app.state.sessionmaker, tls=cast(Any, FakeTLS()))
    assert kitchen.put(f"{API}/privacy/switches/single_sign_on", json={"on": True}).is_success
    response = kitchen.put(f"{API}/sso/settings", json=SETUP)
    assert response.status_code == 200, response.text
    return kitchen


def browser(client: TestClient) -> TestClient:
    return TestClient(client.app, base_url="https://testserver", follow_redirects=False)


def sign_in(
    client: TestClient, idp: FakeProvider, path: str = "/sso/start", **claims: Any
) -> tuple[Any, str]:
    """Start, sign in at the provider, and post the callback: (the answer, the state)."""
    started = client.get(f"{API}{path}", follow_redirects=False)
    assert started.status_code == 303, started.text
    assert started.headers["location"].startswith(f"{ISSUER}/authorize?")
    code, state = idp.sign_in(started.headers["location"], **claims)
    answer = client.post(f"{API}/sso/finish", json={"state": state, "code": code})
    return answer, state


def logins(client: TestClient) -> dict[str, str]:
    with cast(Any, client.app).state.sessionmaker() as db:
        return {
            login.username: login.role
            for login in db.scalars(select(Login).where(Login.sso_subject.is_not(None)))
        }


# --- The setup --------------------------------------------------------------------------------


def test_the_sign_in_page_offers_passwords_only_until_set_up(client: TestClient) -> None:
    assert client.get(f"{API}/sign-in-options").json() == {"password": True, "sso_button": None}


def test_the_setup_is_saved_without_ever_sending_the_secret_back(
    admin: TestClient, settings: Any
) -> None:
    body = admin.get(f"{API}/sso/settings").json()
    assert body["secret_set"] is True
    assert CLIENT_SECRET not in str(body)
    assert body["redirect_uri"] == REDIRECT
    assert body["admin_linked"] is False
    assert body["switch_on"] is True
    assert admin.get(f"{API}/sign-in-options").json() == {
        "password": True,
        "sso_button": "Authentik",
    }
    # A blank secret keeps the saved one.
    with cast(Any, admin.app).state.sessionmaker() as db:
        before = db.get(SsoSettings, 1).client_secret_sealed
    assert admin.put(f"{API}/sso/settings", json={**SETUP, "client_secret": ""}).is_success
    with cast(Any, admin.app).state.sessionmaker() as db:
        assert db.get(SsoSettings, 1).client_secret_sealed == before
    # Nowhere in the data folder is the secret readable, apart from the key that seals it.
    for path in Path(settings.data_dir).rglob("*"):
        if path.is_file():
            assert CLIENT_SECRET.encode() not in path.read_bytes(), path.name


def test_the_setup_needs_a_secret_the_first_time(kitchen: TestClient) -> None:
    response = kitchen.put(f"{API}/sso/settings", json={**SETUP, "client_secret": ""})
    assert response.status_code == 422
    assert response.json()["code"] == "no_secret"


@pytest.mark.parametrize(
    "redirect",
    [
        "https://elsewhere.example/auth/callback",  # not this Mealwright's address
        "http://testserver/auth/callback",  # plain http
        "https://testserver/auth/other",
        "https://testserver/auth/callback?next=/",
        "https://someone@testserver/auth/callback",
        "not an address",
    ],
)
def test_a_redirect_address_that_isnt_this_mealwrights_is_refused(
    kitchen: TestClient, redirect: str
) -> None:
    response = kitchen.put(f"{API}/sso/settings", json={**SETUP, "redirect_uri": redirect})
    assert response.status_code == 422
    assert response.json()["code"] == "bad_redirect"


def test_the_redirect_address_is_never_taken_from_a_visitors_forwarded_host(
    kitchen: TestClient,
) -> None:
    # No trusted proxy: X-Forwarded-Host from a visitor changes nothing.
    response = kitchen.put(
        f"{API}/sso/settings",
        json={**SETUP, "redirect_uri": "https://evil.example/auth/callback"},
        headers={"X-Forwarded-Host": "evil.example"},
    )
    assert response.status_code == 422


@pytest.mark.parametrize(
    "change",
    [
        {"issuer": "ftp://id.example.org"},
        {"issuer": "https://id.example.org/?x=1"},
        {"group_roles": [{"group": "a", "role": "admin"}, {"group": "a", "role": "member"}]},
        {"group_roles": [{"group": "a", "role": "owner"}]},
        {"anyone_else": "admin"},
        {"group_roles": [{"group": f"g{n}", "role": "member"} for n in range(51)]},
    ],
)
def test_a_bad_setup_is_refused(kitchen: TestClient, change: dict[str, Any]) -> None:
    assert kitchen.put(f"{API}/sso/settings", json={**SETUP, **change}).status_code == 422


def test_only_an_admin_sees_or_changes_the_setup(admin: TestClient) -> None:
    with cast(Any, admin.app).state.sessionmaker() as db:
        db.add(
            Login(
                household_id=1,
                username="wren",
                name="Wren",
                password_hash=hash_password("wren's own password"),
                role="member",
            )
        )
        db.commit()
    with TestClient(admin.app, base_url="https://testserver") as member:
        assert member.post(
            f"{API}/session", json={"username": "wren", "password": "wren's own password"}
        ).is_success
        for response in (
            member.get(f"{API}/sso/settings"),
            member.put(f"{API}/sso/settings", json=SETUP),
            member.put(f"{API}/sso/password-sign-in", json={"on": False}),
            member.get(f"{API}/sso/test", follow_redirects=False),
        ):
            assert response.status_code == 403
            assert response.json()["code"] == "admins_only"
    signed_out = browser(admin)
    assert signed_out.get(f"{API}/sso/settings").status_code == 401


# --- Signing in -------------------------------------------------------------------------------


def test_a_first_sign_in_makes_an_account_with_its_groups_role(
    admin: TestClient, idp: FakeProvider, caplog: pytest.LogCaptureFixture
) -> None:
    phone = browser(admin)
    with caplog.at_level(logging.INFO, logger="mealwright"):
        answer, _ = sign_in(phone, idp)
    assert answer.status_code == 200, answer.text
    body = answer.json()
    assert body["done"] == "signed_in"
    assert body["me"]["username"] == "ayla"
    assert body["me"]["role"] == "member"
    assert phone.get(f"{API}/me").json()["username"] == "ayla"
    with cast(Any, admin.app).state.sessionmaker() as db:
        login = db.scalars(select(Login).where(Login.username == "ayla")).one()
        assert (login.sso_issuer, login.sso_subject, login.password_hash) == (
            ISSUER,
            "user-1",
            None,
        )
        assert db.get(Member, login.member_id) is not None  # a person too
        session = db.scalars(select(Session).where(Session.login_id == login.id)).one()
        assert session.sso is True
        assert session.sso_refresh_sealed and "rt-1" not in session.sso_refresh_sealed
        assert session.sso_check_at is not None
    assert "rt-1" not in caplog.text and CLIENT_SECRET not in caplog.text
    assert "account asha made on first sign-in" in caplog.text


def test_the_role_follows_the_groups_on_every_sign_in(admin: TestClient, idp: FakeProvider) -> None:
    sign_in(browser(admin), idp, extra={"groups": ["mealwright-admins", "mealwright-users"]})
    assert logins(admin) == {"ayla": "admin"}
    sign_in(browser(admin), idp, extra={"groups": ["mealwright-users"]})
    assert logins(admin) == {"ayla": "member"}


def test_someone_in_no_mapped_group_is_not_let_in_unless_anyone_else_is_a_member(
    admin: TestClient, idp: FakeProvider
) -> None:
    answer, _ = sign_in(browser(admin), idp, extra={"groups": ["friends"]})
    assert answer.status_code == 400
    assert answer.json()["code"] == "not_let_in"
    assert logins(admin) == {}
    admin.put(f"{API}/sso/settings", json={**SETUP, "client_secret": "", "anyone_else": "member"})
    answer, _ = sign_in(browser(admin), idp, extra={"groups": ["friends"]})
    assert answer.status_code == 200
    assert logins(admin) == {"ayla": "member"}


def test_no_account_is_made_when_the_admin_turned_that_off(
    admin: TestClient, idp: FakeProvider
) -> None:
    admin.put(f"{API}/sso/settings", json={**SETUP, "client_secret": "", "make_accounts": False})
    answer, _ = sign_in(browser(admin), idp)
    assert answer.json()["code"] == "no_account"
    assert logins(admin) == {}


def test_a_name_clash_with_a_password_account_is_refused_never_linked(
    admin: TestClient, idp: FakeProvider
) -> None:
    answer, _ = sign_in(browser(admin), idp, extra={"preferred_username": "tess"})
    assert answer.status_code == 400
    assert answer.json()["code"] == "clash"
    with cast(Any, admin.app).state.sessionmaker() as db:
        tess = db.scalars(select(Login).where(Login.username == "tess")).one()
        assert tess.sso_subject is None


def test_the_same_subject_at_the_same_issuer_is_the_same_account(
    admin: TestClient, idp: FakeProvider
) -> None:
    sign_in(browser(admin), idp)
    # The provider now calls them something else: still the same login, found by sub.
    sign_in(browser(admin), idp, extra={"preferred_username": "ayla2"})
    assert logins(admin) == {"ayla": "member"}
    # Another subject with the same user name is someone else, and clashes.
    answer, _ = sign_in(browser(admin), idp, sub="user-2")
    assert answer.json()["code"] == "clash"


def test_a_removed_persons_sign_in_is_refused(admin: TestClient, idp: FakeProvider) -> None:
    sign_in(browser(admin), idp)
    with cast(Any, admin.app).state.sessionmaker() as db:
        login = db.scalars(select(Login).where(Login.username == "ayla")).one()
        db.get(Member, login.member_id).removed_at = now()
        db.commit()
    answer, _ = sign_in(browser(admin), idp)
    assert answer.json()["code"] == "removed"


def test_the_state_works_once_and_only_in_the_browser_that_started(
    admin: TestClient, idp: FakeProvider
) -> None:
    phone = browser(admin)
    started = phone.get(f"{API}/sso/start")
    code, state = idp.sign_in(started.headers["location"])
    other = browser(admin)  # another browser, without the cookie
    stolen = other.post(f"{API}/sso/finish", json={"state": state, "code": code})
    assert stolen.status_code == 400
    assert stolen.json()["code"] == "expired"
    # Taken once: the right browser can't use it now either.
    again = phone.post(f"{API}/sso/finish", json={"state": state, "code": code})
    assert again.json()["code"] == "expired"
    assert logins(admin) == {}


def test_the_binding_cookie_is_http_only_and_short_lived(admin: TestClient) -> None:
    started = browser(admin).get(f"{API}/sso/start")
    cookie = started.headers["set-cookie"]
    assert cookie.startswith("__Host-mealwright_sso=")
    for part in ("HttpOnly", "Secure", "Path=/", "SameSite=lax", f"Max-Age={sso.FLOW_FOR}"):
        assert part in cookie


def test_a_cancelled_sign_in_says_so(admin: TestClient) -> None:
    phone = browser(admin)
    started = phone.get(f"{API}/sso/start")
    state = parse_qs(urlsplit(started.headers["location"]).query)["state"][0]
    answer = phone.post(f"{API}/sso/finish", json={"state": state, "error": "access_denied"})
    assert answer.status_code == 400
    assert answer.json()["code"] == "cancelled"


def test_starting_on_another_address_than_the_saved_one_is_refused(admin: TestClient) -> None:
    other = TestClient(admin.app, base_url="https://other.example", follow_redirects=False)
    started = other.get(f"{API}/sso/start")
    assert started.status_code == 303
    assert started.headers["location"] == "/sign-in?sso=wrong_address"


def test_with_the_switch_off_nothing_leaves_and_the_button_goes(
    admin: TestClient, idp: FakeProvider
) -> None:
    admin.put(f"{API}/privacy/switches/single_sign_on", json={"on": False})
    assert admin.get(f"{API}/sign-in-options").json()["sso_button"] is None
    started = browser(admin).get(f"{API}/sso/start")
    assert started.headers["location"] == "/sign-in?sso=switched_off"
    assert idp.lookups == [] and idp.connections == [] and idp.seen == []


def test_signing_out_drops_the_refresh_token(admin: TestClient, idp: FakeProvider) -> None:
    phone = browser(admin)
    sign_in(phone, idp)
    assert phone.delete(f"{API}/session").status_code == 204
    with cast(Any, admin.app).state.sessionmaker() as db:
        assert db.scalars(select(Session).where(Session.sso.is_(True))).all() == []


def test_a_password_sign_in_after_sso_still_works_while_passwords_are_on(
    admin: TestClient,
) -> None:
    fresh = browser(admin)
    password = {"username": ADMIN["username"], "password": ADMIN["password"]}
    assert fresh.post(f"{API}/session", json=password).status_code == 200


# --- The test, and turning password sign-in off ---------------------------------------------


def test_password_sign_in_stays_on_until_an_admin_has_signed_in_with_sso(
    admin: TestClient, idp: FakeProvider
) -> None:
    for response in (
        admin.put(f"{API}/sso/password-sign-in", json={"on": False}),
        admin.put(f"{API}/sso/settings", json={**SETUP, "password_sign_in": False}),
    ):
        assert response.status_code == 409
        assert response.json()["code"] == "passwords_needed"
    # A member signing in with SSO isn't enough.
    sign_in(browser(admin), idp)
    assert admin.put(f"{API}/sso/password-sign-in", json={"on": False}).status_code == 409


def test_the_setup_test_links_the_admin_and_then_passwords_can_go(
    admin: TestClient, idp: FakeProvider
) -> None:
    answer, _ = sign_in(
        admin,
        idp,
        path="/sso/test",
        sub="tess-at-idp",
        extra={"preferred_username": "tess", "groups": ["mealwright-admins"]},
    )
    assert answer.status_code == 200, answer.text
    test = answer.json()["test"]
    assert test == {
        "passed": True,
        "username": "tess",
        "groups": ["mealwright-admins"],
        "role": "admin",
        "message": None,
        "code": None,
    }
    setup = admin.get(f"{API}/sso/settings").json()
    assert setup["test"]["passed"] is True
    assert setup["admin_linked"] is True
    assert admin.put(f"{API}/sso/password-sign-in", json={"on": False}).status_code == 200

    options = admin.get(f"{API}/sign-in-options").json()
    assert options == {"password": False, "sso_button": "Authentik"}
    password = {"username": ADMIN["username"], "password": ADMIN["password"]}
    refused = browser(admin).post(f"{API}/session", json=password)
    assert refused.status_code == 403
    assert refused.json()["code"] == "password_off"

    # The admin now signs in with SSO as themselves, still an admin.
    phone = browser(admin)
    answer, _ = sign_in(phone, idp, sub="tess-at-idp", extra={"groups": ["mealwright-admins"]})
    assert answer.json()["me"]["username"] == "tess"
    assert answer.json()["me"]["role"] == "admin"

    # With the switch off, passwords work again, so nobody is locked out.
    admin.put(f"{API}/privacy/switches/single_sign_on", json={"on": False})
    assert admin.get(f"{API}/sign-in-options").json()["password"] is True
    assert browser(admin).post(f"{API}/session", json=password).status_code == 200


def test_a_failed_test_is_shown_on_the_setup_screen(admin: TestClient, idp: FakeProvider) -> None:
    answer, _ = sign_in(admin, idp, path="/sso/test", extra={"groups": ["friends"]})
    assert answer.json()["test"]["passed"] is False
    assert answer.json()["test"]["code"] == "not_let_in"
    setup = admin.get(f"{API}/sso/settings").json()
    assert setup["admin_linked"] is False
    assert setup["test"]["passed"] is False


def test_a_test_can_link_only_an_identity_nobody_else_has(
    admin: TestClient, idp: FakeProvider
) -> None:
    sign_in(browser(admin), idp)  # ayla is user-1
    answer, _ = sign_in(admin, idp, path="/sso/test", extra={"groups": ["mealwright-admins"]})
    assert answer.status_code == 400
    assert answer.json()["code"] == "someone_else"
    assert admin.get(f"{API}/sso/settings").json()["test"]["code"] == "someone_else"


def test_reset_admin_turns_password_sign_in_back_on(admin: TestClient, idp: FakeProvider) -> None:
    sign_in(admin, idp, path="/sso/test", sub="k", extra={"groups": ["mealwright-admins"]})
    assert admin.put(f"{API}/sso/password-sign-in", json={"on": False}).is_success
    out = io.StringIO()
    assert reset_admin(cast(Any, admin.app).state.settings, "tess", out) == 0
    assert "Password sign-in was off for single sign-on" in out.getvalue()
    assert browser(admin).get(f"{API}/sign-in-options").json()["password"] is True


# --- Staying signed in --------------------------------------------------------------------


@pytest.fixture
def signed_in(admin: TestClient, idp: FakeProvider) -> Iterator[TestClient]:
    phone = browser(admin)
    sign_in(phone, idp)
    with cast(Any, admin.app).state.sessionmaker() as db:
        for session in db.scalars(select(Session).where(Session.sso.is_(True))):
            session.sso_check_at = now()  # due
        db.commit()
    yield phone


def check(client: TestClient) -> int:
    app = cast(Any, client.app)
    return sso_accounts.check_sessions(
        app.state.outbound, app.state.sessionmaker, app.state.settings.data_dir
    )


def test_the_job_keeps_a_sign_in_the_provider_still_knows(
    signed_in: TestClient, admin: TestClient
) -> None:
    assert check(admin) == 0
    assert signed_in.get(f"{API}/me").status_code == 200
    with cast(Any, admin.app).state.sessionmaker() as db:
        session = db.scalars(select(Session).where(Session.sso.is_(True))).one()
        assert as_utc(session.sso_check_at) > now() + sso.CHECK_EVERY / 2


def test_the_job_signs_out_a_sign_in_the_provider_ended(
    signed_in: TestClient, admin: TestClient, idp: FakeProvider
) -> None:
    idp.refresh_tokens.clear()  # the person was signed out at the provider
    assert check(admin) == 1
    assert signed_in.get(f"{API}/me").status_code == 401
    assert admin.get(f"{API}/me").status_code == 200  # the admin's password sign-in stays


def test_the_job_tries_later_when_the_provider_cant_be_reached(
    signed_in: TestClient, admin: TestClient, idp: FakeProvider
) -> None:
    idp.port = 8443  # it stopped answering: connections are refused
    sso.cache.forget()
    assert check(admin) == 0
    assert signed_in.get(f"{API}/me").status_code == 200
    with cast(Any, admin.app).state.sessionmaker() as db:
        session = db.scalars(select(Session).where(Session.sso.is_(True))).one()
        assert as_utc(session.sso_check_at) <= now() + sso.RETRY_AFTER


def test_the_job_sends_nothing_with_the_switch_off(
    signed_in: TestClient, admin: TestClient, idp: FakeProvider
) -> None:
    admin.put(f"{API}/privacy/switches/single_sign_on", json={"on": False})
    idp.seen.clear()
    idp.lookups.clear()
    assert check(admin) == 0
    assert idp.seen == [] and idp.lookups == []
    assert signed_in.get(f"{API}/me").status_code == 200
