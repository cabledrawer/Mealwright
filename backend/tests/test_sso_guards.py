"""Five guards in the single sign-on code that no test used to notice missing (0.9 O1 review r2,
finding 6). Each test fails when its guard is taken out (shown in the commit message)."""

# ruff: noqa: F811, F401

import ipaddress
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, ClassVar, cast

import pytest
from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_sso_api import (
    ADMIN_GROUPS,
    API,
    PASSWORD,
    admin,
    begin,
    browser,
    fresh_cache,
    idp,
)

from mealwright import outbound, sso_accounts
from mealwright.api.v1.sso import _fingerprint
from mealwright.auth import hash_password
from mealwright.models import Login, SsoSettings
from mealwright.outbound import USER_AGENT, Connection, OutboundBlocked, OutboundGate
from mealwright.sso import SsoFailed

REAL_OPEN_SOCKET = outbound._open_socket  # before a fixture swaps in the fake provider's


# --- 1. api/v1/sso.py, _finish_test: only the admin who started the test, still an admin ------


def finish_test_as(starter: TestClient, finisher: TestClient, idp: FakeProvider) -> Any:
    url = begin(starter, "/sso/test")
    code, state = idp.sign_in(url, sub="k", extra=ADMIN_GROUPS)
    finisher.cookies.set("__Host-mealwright_sso", starter.cookies.get("__Host-mealwright_sso"))
    return finisher.post(f"{API}/sso/finish", json={"state": state, "code": code})


def test_a_test_is_finished_only_by_a_signed_in_admin_who_started_it(
    admin: TestClient, idp: FakeProvider
) -> None:
    # Nobody signed in at the callback.
    stranger = browser(admin)
    answer = finish_test_as(admin, stranger, idp)
    assert answer.status_code == 400 and answer.json()["code"] == "expired"
    # Another admin's session.
    with cast(Any, admin.app).state.sessionmaker() as db:
        db.add(
            Login(
                household_id=1,
                username="wren",
                name="Wren",
                password_hash=hash_password("w4ren-own-password"),
                role="admin",
            )
        )
        db.commit()
    wren = browser(admin)
    assert wren.post(
        f"{API}/session", json={"username": "wren", "password": "w4ren-own-password"}
    ).is_success
    answer = finish_test_as(admin, wren, idp)
    assert answer.status_code == 400 and answer.json()["code"] == "expired"
    assert (
        admin.get(f"{API}/sso/settings").json()["test"] is None
        or not admin.get(f"{API}/sso/settings").json()["test"]["passed"]
    )


def test_a_test_isnt_finished_by_someone_who_stopped_being_an_admin(
    admin: TestClient, idp: FakeProvider
) -> None:
    url = begin(admin, "/sso/test")
    code, state = idp.sign_in(url, sub="k", extra=ADMIN_GROUPS)
    with cast(Any, admin.app).state.sessionmaker() as db:
        db.scalars(
            select(Login).where(Login.username == PASSWORD["username"])
        ).one().role = "member"
        db.commit()
    answer = admin.post(f"{API}/sso/finish", json={"state": state, "code": code})
    assert answer.status_code == 400 and answer.json()["code"] == "expired"


# --- 2. sso_accounts.link: checked again at the moment of linking -----------------------------


def a_row_and_login(admin: TestClient) -> tuple[SsoSettings, Login]:
    with cast(Any, admin.app).state.sessionmaker() as db:
        row = db.get(SsoSettings, 1)
        login = db.scalars(select(Login).where(Login.username == PASSWORD["username"])).one()
        db.expunge_all()
    return cast(SsoSettings, row), login


def test_linking_is_refused_when_the_sign_in_server_changed(admin: TestClient) -> None:
    row, login = a_row_and_login(admin)
    with pytest.raises(SsoFailed) as refused:
        sso_accounts.link(cast(Any, None), row, login, "https://other.example.org", "sub")
    assert refused.value.code == "link_gone"


def test_linking_is_refused_for_someone_who_is_not_an_admin(admin: TestClient) -> None:
    row, login = a_row_and_login(admin)
    login.role = "member"
    with pytest.raises(SsoFailed) as refused:
        sso_accounts.link(cast(Any, None), row, login, row.issuer, "sub")
    assert refused.value.code == "link_gone"


def test_linking_is_refused_for_a_login_of_another_household(admin: TestClient) -> None:
    row, login = a_row_and_login(admin)
    login.household_id = row.household_id + 1
    with pytest.raises(SsoFailed) as refused:
        sso_accounts.link(cast(Any, None), row, login, row.issuer, "sub")
    assert refused.value.code == "link_gone"


# --- 3. api/v1/sso.py, what a save that changes who gets in is made of ------------------------

CHANGES = {
    "issuer": "https://other.example.org",
    "client_id": "another-client",
    "redirect_uri": "https://testserver/elsewhere",
    "group_claim": "roles",
    "group_roles": [{"group": "x", "role": "admin"}],
    "anyone_else": "member",
    "client_secret_sealed": "another-sealed-secret",
}


@pytest.mark.parametrize("field", CHANGES)
def test_every_part_of_who_gets_in_is_part_of_what_was_proven(
    admin: TestClient, field: str
) -> None:
    row, _ = a_row_and_login(admin)
    before = _fingerprint(row)
    setattr(row, field, CHANGES[field])
    assert _fingerprint(row) != before


# --- 4 and 5. outbound.py, get_pinned: only GET and POST, and always the gate's own user agent -


class _Echo(BaseHTTPRequestHandler):
    seen: ClassVar[list[tuple[str, list[str]]]] = []

    def _answer(self) -> None:
        type(self).seen.append((self.command, self.headers.get_all("User-Agent") or []))
        self.send_response(200)
        self.send_header("Content-Length", "2")
        self.end_headers()
        self.wfile.write(b"ok")

    do_GET = do_POST = do_DELETE = _answer

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def echo() -> Iterator[str]:
    _Echo.seen = []
    httpd = HTTPServer(("127.0.0.1", 0), _Echo)
    thread = threading.Thread(target=httpd.serve_forever, args=(0.02,), daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}/x"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def gate_on(admin: TestClient, monkeypatch: pytest.MonkeyPatch) -> OutboundGate:
    """A real gate, over real sockets, with the Single sign-on switch on (the admin fixture's
    own gate talks to the fake provider)."""
    monkeypatch.setattr(outbound, "_open_socket", REAL_OPEN_SOCKET)
    app = cast(Any, admin.app)
    return OutboundGate(app.state.sessionmaker)


def test_the_gate_sends_only_get_and_post(gate_on: OutboundGate, echo: str) -> None:
    address = ipaddress.ip_address("127.0.0.1")
    with pytest.raises(OutboundBlocked):
        gate_on.get_pinned(1, Connection.SINGLE_SIGN_ON, echo, address, method="DELETE")
    assert _Echo.seen == []
    assert gate_on.get_pinned(1, Connection.SINGLE_SIGN_ON, echo, address).status == 200
    post = gate_on.get_pinned(
        1, Connection.SINGLE_SIGN_ON, echo, address, method="POST", body=b"a=b"
    )
    assert post.status == 200
    assert [method for method, _ in _Echo.seen] == ["GET", "POST"]


def test_the_gate_always_sends_its_own_user_agent(gate_on: OutboundGate, echo: str) -> None:
    address = ipaddress.ip_address("127.0.0.1")
    gate_on.get_pinned(
        1,
        Connection.SINGLE_SIGN_ON,
        echo,
        address,
        headers={"user-agent": "something-else", "User-Agent": "an-app"},
    )
    assert _Echo.seen == [("GET", [USER_AGENT])]  # one only: the gate's own
