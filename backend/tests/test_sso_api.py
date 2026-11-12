"""Single sign-on through the API (0.9 O1): the setup, signing in, accounts and roles, password
sign-in turned off, and the refresh job. The sign-in server is tests/fake_idp.py, on a fake
network: nothing goes online."""

import io
import logging
import time
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


def begin(client: TestClient, path: str = "/sso/start") -> str:
    """Start a sign-in (a link) or a test (a POST from the setup screen): the sign-in
    server's address for the browser."""
    if path == "/sso/test":
        started = client.post(f"{API}{path}", headers={"Origin": "https://testserver"})
        assert started.status_code == 200, started.text
        return str(started.json()["url"])
    started = client.get(f"{API}{path}", follow_redirects=False)
    assert started.status_code == 303, started.text
    return str(started.headers["location"])


def sign_in(
    client: TestClient, idp: FakeProvider, path: str = "/sso/start", **claims: Any
) -> tuple[Any, str]:
    """Start, sign in at the provider, and post the callback: (the answer, the state)."""
    url = begin(client, path)
    assert url.startswith(f"{ISSUER}/authorize?")
    code, state = idp.sign_in(url, **claims)
    answer = client.post(f"{API}/sso/finish", json={"state": state, "code": code})
    return answer, state


def subject_of(client: TestClient, username: str) -> str | None:
    with cast(Any, client.app).state.sessionmaker() as db:
        login = db.scalars(select(Login).where(Login.username == username)).one()
        return cast("str | None", login.sso_subject)


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
            member.post(f"{API}/sso/test"),
            member.post(f"{API}/sso/link"),
            member.delete(f"{API}/sso/link"),
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
    cookie = phone.cookies.get("__Host-mealwright_sso")
    code, state = idp.sign_in(started.headers["location"])
    other = browser(admin)  # another browser, without the cookie
    stolen = other.post(f"{API}/sso/finish", json={"state": state, "code": code})
    assert stolen.status_code == 400
    assert stolen.json()["code"] == "expired"
    assert logins(admin) == {}
    # A cookie this server didn't seal is no better than none.
    other.cookies.set("__Host-mealwright_sso", "made-up")
    forged = other.post(f"{API}/sso/finish", json={"state": state, "code": code})
    assert forged.json()["code"] == "expired"
    # The right browser signs in, once: its cookie put back by hand doesn't work again.
    assert phone.post(f"{API}/sso/finish", json={"state": state, "code": code}).is_success
    assert phone.cookies.get("__Host-mealwright_sso") is None
    phone.cookies.set("__Host-mealwright_sso", str(cookie))
    again = phone.post(f"{API}/sso/finish", json={"state": state, "code": code})
    assert again.json()["code"] == "expired"


# O1 review r1 M2: someone signed out can't stop other people's sign-ins.


def test_strangers_starting_sign_ins_cant_push_out_someone_elses(
    admin: TestClient, idp: FakeProvider
) -> None:
    victim = browser(admin)
    url = begin(victim)
    for n in range(250):  # more than the 200 that used to wait at once
        stranger = TestClient(
            admin.app,
            base_url="https://testserver",
            follow_redirects=False,
            client=(f"203.0.113.{n + 1}", 40000),
        )
        begin(stranger)
    code, state = idp.sign_in(url)
    answer = victim.post(f"{API}/sso/finish", json={"state": state, "code": code})
    assert answer.status_code == 200, answer.text
    assert answer.json()["me"]["username"] == "ayla"


def test_a_sign_in_server_that_doesnt_answer_isnt_asked_again_by_every_start(
    admin: TestClient, idp: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    idp.port = 8443  # it stopped answering: connections are refused
    sso.cache.forget()
    started = browser(admin).get(f"{API}/sso/start")
    assert started.headers["location"] == "/sign-in?sso=unreachable"
    tried = len(idp.connections)
    assert tried >= 1
    for _ in range(20):
        started = browser(admin).get(f"{API}/sso/start")
        assert started.headers["location"] == "/sign-in?sso=unreachable"
    assert len(idp.connections) == tried  # nobody waited on it again
    # The admin's own test asks at once: they may just have mended it.
    idp.port = 443
    assert admin.post(f"{API}/sso/test").status_code == 200
    # Everyone else's sign-in asks again after a minute.
    idp.port = 8443
    sso.cache.forget()
    assert browser(admin).get(f"{API}/sso/start").headers["location"].startswith("/sign-in?")
    tried = len(idp.connections)
    real = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: real + 61)
    idp.port = 443
    started = browser(admin).get(f"{API}/sso/start")
    assert started.headers["location"].startswith(f"{ISSUER}/authorize?")
    assert len(idp.connections) > tried


def test_a_state_works_only_with_the_cookie_of_the_sign_in_it_started(
    admin: TestClient, idp: FakeProvider
) -> None:
    one, two = browser(admin), browser(admin)
    url = begin(one)
    begin(two)  # another browser, with a sign-in of its own under way
    code, state = idp.sign_in(url)
    stolen = two.post(f"{API}/sso/finish", json={"state": state, "code": code})
    assert stolen.status_code == 400
    assert stolen.json()["code"] == "expired"
    # The cookie holds nothing readable: the state, nonce and verifier are sealed in it.
    cookie = one.cookies.get("__Host-mealwright_sso")
    assert cookie and state not in cookie
    assert one.post(f"{API}/sso/finish", json={"state": state, "code": code}).status_code == 200


def test_a_sign_in_that_took_too_long_is_refused(
    admin: TestClient, idp: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    phone = browser(admin)
    code, state = idp.sign_in(begin(phone))
    real = time.time()
    monkeypatch.setattr(sso.time, "time", lambda: real + sso.FLOW_FOR + 1)
    answer = phone.post(f"{API}/sso/finish", json={"state": state, "code": code})
    assert answer.status_code == 400
    assert answer.json()["code"] == "expired"


def test_the_sign_ins_cookie_is_http_only_and_short_lived(admin: TestClient) -> None:
    started = browser(admin).get(f"{API}/sso/start")
    cookie = started.headers["set-cookie"]
    assert cookie.startswith("__Host-mealwright_sso=")
    for part in ("HttpOnly", "Secure", "Path=/", "SameSite=lax", f"Max-Age={sso.FLOW_FOR}"):
        assert part in cookie
    assert len(cookie) < 2000  # well inside what a browser keeps (4096)


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


def test_the_setup_test_then_linking_lets_passwords_go(
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
        "name": "Ayla",
        "email": "ayla@example.org",
        "groups": ["mealwright-admins"],
        "role": "admin",
        "link": "can",
        "message": None,
        "code": None,
    }
    assert admin.post(f"{API}/sso/link").status_code == 200  # the admin confirms
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


# O1 review r1 H1: a test never hands the admin's account to whoever is signed in at the provider.

MALLORY = {"preferred_username": "mallory", "name": "Mallory M", "email": "mallory@example.org"}


def test_a_member_at_the_provider_in_the_admins_browser_is_never_linked(
    admin: TestClient, idp: FakeProvider
) -> None:
    answer, _ = sign_in(
        admin,
        idp,
        path="/sso/test",
        sub="mallory-1",
        extra={**MALLORY, "groups": ["mealwright-users"]},
    )
    assert answer.status_code == 200, answer.text
    assert subject_of(admin, "tess") is None
    test = answer.json()["test"]
    assert (test["passed"], test["role"], test["link"]) == (True, "member", "no")
    assert admin.get(f"{API}/sso/settings").json()["admin_linked"] is False
    # Asking to link anyway is refused: there is nothing to confirm.
    refused = admin.post(f"{API}/sso/link")
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "link_gone"
    assert subject_of(admin, "tess") is None
    # Mallory then signs in as herself, a member: never as the admin.
    answer, _ = sign_in(
        browser(admin), idp, sub="mallory-1", extra={**MALLORY, "groups": ["mealwright-users"]}
    )
    assert answer.json()["me"]["username"] == "mallory"
    assert answer.json()["me"]["role"] == "member"


def test_a_test_sign_in_starts_only_by_a_post_from_this_site(
    admin: TestClient, idp: FakeProvider
) -> None:
    # A link another site gets the admin's browser to follow starts nothing.
    followed = admin.get(f"{API}/sso/test", follow_redirects=False)
    assert followed.status_code in (404, 405)  # there is no such link
    assert "set-cookie" not in followed.headers
    # Nor does a form on another site.
    posted = admin.post(f"{API}/sso/test", headers={"Origin": "https://evil.example"})
    assert posted.status_code == 403
    assert "set-cookie" not in posted.headers
    assert idp.seen == []  # the sign-in server wasn't even asked
    # The setup screen's own POST does.
    started = admin.post(f"{API}/sso/test", headers={"Origin": "https://testserver"})
    assert started.status_code == 200, started.text
    assert started.json()["url"].startswith(f"{ISSUER}/authorize?")


def test_a_test_asks_the_provider_to_ask_who_you_are(admin: TestClient) -> None:
    query = parse_qs(urlsplit(begin(admin, "/sso/test")).query)
    assert query["prompt"] == ["login"]
    # An everyday sign-in doesn't: someone signed in at the provider goes straight through.
    assert "prompt" not in parse_qs(urlsplit(begin(browser(admin))).query)


def test_nothing_is_linked_until_the_admin_confirms(admin: TestClient, idp: FakeProvider) -> None:
    answer, _ = sign_in(
        admin,
        idp,
        path="/sso/test",
        sub="tess-at-idp",
        extra={
            "preferred_username": "tess.r",
            "name": "Tess R",
            "email": "tess@example.org",
            "groups": ["mealwright-admins"],
        },
    )
    test = answer.json()["test"]
    assert (test["passed"], test["role"], test["link"]) == (True, "admin", "can")
    # Who the provider says it was, for the question on the setup screen.
    assert (test["username"], test["name"], test["email"]) == (
        "tess.r",
        "Tess R",
        "tess@example.org",
    )
    setup = admin.get(f"{API}/sso/settings").json()
    assert setup["admin_linked"] is False and setup["test"]["link"] == "can"
    assert subject_of(admin, "tess") is None
    assert admin.put(f"{API}/sso/password-sign-in", json={"on": False}).status_code == 409
    # A confirmation from another site is refused.
    cross = admin.post(f"{API}/sso/link", headers={"Origin": "https://evil.example"})
    assert cross.status_code == 403
    assert subject_of(admin, "tess") is None
    # Confirmed: linked.
    linked = admin.post(f"{API}/sso/link", headers={"Origin": "https://testserver"})
    assert linked.status_code == 200, linked.text
    assert linked.json()["admin_linked"] is True and linked.json()["test"]["link"] == "linked"
    assert subject_of(admin, "tess") == "tess-at-idp"
    # Once: there's nothing left to confirm.
    assert admin.post(f"{API}/sso/link").status_code == 409


def test_not_now_drops_the_link_that_was_waiting(admin: TestClient, idp: FakeProvider) -> None:
    sign_in(admin, idp, path="/sso/test", sub="k", extra={"groups": ["mealwright-admins"]})
    dropped = admin.delete(f"{API}/sso/link")
    assert dropped.status_code == 200, dropped.text
    assert dropped.json()["test"]["link"] == "no"
    assert admin.post(f"{API}/sso/link").status_code == 409
    assert subject_of(admin, "tess") is None


def test_only_the_admin_who_tested_can_confirm_and_not_after_a_save_or_too_late(
    admin: TestClient, idp: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    with cast(Any, admin.app).state.sessionmaker() as db:
        db.add(
            Login(
                household_id=1,
                username="wren",
                name="Wren",
                password_hash=hash_password("wren's own password"),
                role="admin",
            )
        )
        db.commit()
    sign_in(admin, idp, path="/sso/test", sub="k", extra={"groups": ["mealwright-admins"]})
    with TestClient(admin.app, base_url="https://testserver") as wren:
        assert wren.post(
            f"{API}/session", json={"username": "wren", "password": "wren's own password"}
        ).is_success
        assert wren.get(f"{API}/sso/settings").json()["test"]["link"] == "no"
        assert wren.post(f"{API}/sso/link").status_code == 409
        assert subject_of(admin, "wren") is None
    # Saving the setup drops the test: it was of the setup before.
    assert admin.put(f"{API}/sso/settings", json={**SETUP, "client_secret": ""}).is_success
    assert admin.post(f"{API}/sso/link").status_code == 409
    # And a test's link waits only so long.
    sign_in(admin, idp, path="/sso/test", sub="k", extra={"groups": ["mealwright-admins"]})
    real = time.monotonic()
    monkeypatch.setattr(time, "monotonic", lambda: real + sso.FLOW_FOR + 1)
    assert admin.get(f"{API}/sso/settings").json()["test"]["link"] == "no"
    assert admin.post(f"{API}/sso/link").status_code == 409
    assert subject_of(admin, "tess") is None


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
    assert admin.post(f"{API}/sso/link").is_success
    assert admin.put(f"{API}/sso/password-sign-in", json={"on": False}).is_success
    out = io.StringIO()
    assert reset_admin(cast(Any, admin.app).state.settings, "tess", out) == 0
    assert "Password sign-in was off for single sign-on" in out.getvalue()
    assert browser(admin).get(f"{API}/sign-in-options").json()["password"] is True


# O1 review r1 M3: with passwords off, a change that could break single sign-on never leaves
# every admin locked out.

PASSWORD = {"username": ADMIN["username"], "password": ADMIN["password"]}
ADMIN_GROUPS = {"groups": ["mealwright-admins"]}


@pytest.fixture
def sso_only(admin: TestClient, idp: FakeProvider) -> TestClient:
    """The admin is linked, and password sign-in is off."""
    sign_in(admin, idp, path="/sso/test", sub="k", extra=ADMIN_GROUPS)
    assert admin.post(f"{API}/sso/link").is_success
    assert admin.put(f"{API}/sso/password-sign-in", json={"on": False}).is_success
    assert browser(admin).post(f"{API}/session", json=PASSWORD).status_code == 403
    return admin


def a_way_in(client: TestClient) -> None:
    assert client.get(f"{API}/sign-in-options").json()["password"] is True
    assert browser(client).post(f"{API}/session", json=PASSWORD).status_code == 200


@pytest.mark.parametrize(
    "change",
    [
        # The reviewer's cases: a mistyped group, a wrong secret, a new issuer.
        {"group_roles": [{"group": "mealwright-admin", "role": "admin"}]},
        {"client_secret": "not-the-secret"},
        {"issuer": "https://id2.example.org"},
        # And the others that decide who gets in.
        {"client_id": "mealwright-2"},
        {"anyone_else": "member"},
        {"group_claim": "roles"},
    ],
    ids=["mistyped-group", "wrong-secret", "new-issuer", "client-id", "anyone-else", "claim"],
)
def test_a_change_that_could_break_sso_turns_passwords_back_on_and_says_so(
    sso_only: TestClient, change: dict[str, Any]
) -> None:
    # The setup screen sends the whole form, with password sign-in still off.
    body = {**SETUP, "client_secret": "", "password_sign_in": False, **change}
    saved = sso_only.put(f"{API}/sso/settings", json=body)
    assert saved.status_code == 200, saved.text
    assert saved.json()["password_sign_in"] is True
    assert saved.json()["passwords_back_on"] is True
    a_way_in(sso_only)


def test_a_lost_key_file_lets_passwords_work_again(sso_only: TestClient, settings: Any) -> None:
    (Path(settings.data_dir) / "secret.key").unlink()
    a_way_in(sso_only)
    # The admin types the secret again: a change, so passwords are on again for good.
    saved = sso_only.put(f"{API}/sso/settings", json={**SETUP, "password_sign_in": False})
    assert saved.json()["passwords_back_on"] is True
    a_way_in(sso_only)


def test_a_key_file_that_isnt_mealwrights_lets_passwords_work_again(
    sso_only: TestClient, settings: Any
) -> None:
    (Path(settings.data_dir) / "secret.key").write_bytes(b"")
    a_way_in(sso_only)


def test_a_save_that_changes_nothing_about_who_gets_in_keeps_passwords_off(
    sso_only: TestClient,
) -> None:
    body = {**SETUP, "password_sign_in": False, "button_name": "Our sign-in"}
    for secret in ("", CLIENT_SECRET):  # blank keeps it; the same one typed again is no change
        saved = sso_only.put(f"{API}/sso/settings", json={**body, "client_secret": secret})
        assert saved.status_code == 200, saved.text
        assert saved.json()["password_sign_in"] is False
        assert saved.json()["passwords_back_on"] is False
    assert sso_only.get(f"{API}/sign-in-options").json()["password"] is False


def test_passwords_cant_go_off_in_the_same_save_as_such_a_change(
    admin: TestClient, idp: FakeProvider
) -> None:
    sign_in(admin, idp, path="/sso/test", sub="k", extra=ADMIN_GROUPS)
    assert admin.post(f"{API}/sso/link").is_success
    body = {
        **SETUP,
        "client_secret": "",
        "password_sign_in": False,
        "group_roles": [{"group": "mealwright-admin", "role": "admin"}],
    }
    refused = admin.put(f"{API}/sso/settings", json=body)
    assert refused.status_code == 409
    assert refused.json()["code"] == "passwords_needed"
    a_way_in(admin)
    # Nothing of that save was kept.
    assert admin.get(f"{API}/sso/settings").json()["group_roles"] == SETUP["group_roles"]


def _add_admin(client: TestClient, username: str) -> int:
    """Another admin, with a password only. Gives their person's id."""
    with cast(Any, client.app).state.sessionmaker() as db:
        login = Login(
            household_id=1,
            username=username,
            name=username.title(),
            password_hash=hash_password(f"{username}'s own password"),
            role="admin",
        )
        db.add(login)
        db.commit()
        return int(login.member_id)


def _person(client: TestClient, username: str) -> int:
    with cast(Any, client.app).state.sessionmaker() as db:
        login = db.scalars(select(Login).where(Login.username == username)).one()
        return int(login.member_id)


def test_with_passwords_off_only_admins_linked_by_sso_count_as_able_to_sign_in(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    _add_admin(sso_only, "wren")  # an admin, but with a password only: she can't sign in now
    me = _person(sso_only, "tess")
    for change in ({"role": "member"}, {"shared": True}):
        refused = sso_only.patch(f"{API}/people/{me}", json=change)
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "last_admin"
    # Nor do the groups make the only admin who can sign in a Member.
    answer, _ = sign_in(browser(sso_only), idp, sub="k", extra={"groups": ["mealwright-users"]})
    assert answer.json()["me"]["role"] == "admin"
    # With passwords on again, Wren counts.
    assert sso_only.put(f"{API}/sso/password-sign-in", json={"on": True}).is_success
    assert sso_only.patch(f"{API}/people/{me}", json={"role": "member"}).status_code == 200


def test_passwords_cant_go_off_while_the_saved_secret_cant_be_read(
    admin: TestClient, idp: FakeProvider, settings: Any
) -> None:
    sign_in(admin, idp, path="/sso/test", sub="k", extra=ADMIN_GROUPS)
    assert admin.post(f"{API}/sso/link").is_success
    (Path(settings.data_dir) / "secret.key").unlink()
    refused = admin.put(f"{API}/sso/password-sign-in", json={"on": False})
    assert refused.status_code == 409
    assert refused.json()["code"] == "passwords_needed"


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
