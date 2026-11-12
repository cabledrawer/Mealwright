"""Taking the sign-in server off "Your own network" while password sign-in is off (0.9 O1 review
r2, finding 2): passwords come back on, and the answer says so (words proposed, for cabledrawer)."""

from typing import Any, cast

import pytest
from fake_idp import FakeProvider, FakeTLS
from fastapi.testclient import TestClient
from test_sso_api import (
    ADMIN_GROUPS,
    API,
    PASSWORD,
    SETUP,
    browser,
    sign_in,
)

from mealwright import outbound, sso
from mealwright.api.v1.privacy import PASSWORDS_BACK_ON_OWN_NETWORK


@pytest.fixture(autouse=True)
def fresh_cache() -> None:
    sso.cache.forget()


@pytest.fixture
def at_home(kitchen: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """The sign-in server is on the household's own network (a private address), is listed
    there by name, and the admin is linked with passwords off."""
    idp = FakeProvider(address="192.168.1.50")
    idp.install(monkeypatch)
    app = cast(Any, kitchen.app)
    app.state.outbound = outbound.OutboundGate(app.state.sessionmaker, tls=cast(Any, FakeTLS()))
    assert kitchen.put(f"{API}/privacy/switches/single_sign_on", json={"on": True}).is_success
    assert kitchen.post(f"{API}/privacy/own-network", json={"value": "id.example.org"}).is_success
    assert kitchen.put(f"{API}/sso/settings", json=SETUP).is_success
    sign_in(kitchen, idp, path="/sso/test", sub="k", extra=ADMIN_GROUPS)
    assert kitchen.post(f"{API}/sso/link").is_success
    assert kitchen.put(f"{API}/sso/password-sign-in", json={"on": False}).is_success
    assert browser(kitchen).post(f"{API}/session", json=PASSWORD).status_code == 403
    return kitchen


def entry_id(client: TestClient, index: int = 0) -> int:
    return int(client.get(f"{API}/privacy/own-network").json()["entries"][index]["id"])


def test_removing_the_sign_in_server_turns_passwords_back_on_and_says_so(
    at_home: TestClient,
) -> None:
    gone = at_home.delete(f"{API}/privacy/own-network/{entry_id(at_home)}")
    assert gone.status_code == 200, gone.text
    assert gone.json() == {"passwords_back_on": True, "notice": PASSWORDS_BACK_ON_OWN_NETWORK}
    assert at_home.get(f"{API}/sso/settings").json()["password_sign_in"] is True
    assert browser(at_home).post(f"{API}/session", json=PASSWORD).status_code == 200


def test_removing_another_entry_changes_nothing(at_home: TestClient) -> None:
    other = at_home.post(f"{API}/privacy/own-network", json={"value": "wiki.home.lan"})
    assert other.is_success
    gone = at_home.delete(f"{API}/privacy/own-network/{other.json()['id']}")
    assert gone.status_code == 204, gone.text
    assert at_home.get(f"{API}/sso/settings").json()["password_sign_in"] is False


def test_removing_it_with_passwords_on_changes_nothing(at_home: TestClient) -> None:
    assert at_home.put(f"{API}/sso/password-sign-in", json={"on": True}).is_success
    gone = at_home.delete(f"{API}/privacy/own-network/{entry_id(at_home)}")
    assert gone.status_code == 204, gone.text
