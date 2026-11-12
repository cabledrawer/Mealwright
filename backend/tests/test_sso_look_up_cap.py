"""A name look-up refused because the household's places are all held (recipe import, say) is
not "the sign-in server didn't answer", so it isn't remembered for a minute (0.9 O1 review r2,
finding 3): anyone who can hold the places could otherwise keep everyone off single sign-on."""

from typing import Any, cast

import pytest
from fake_idp import ISSUER, FakeProvider, FakeTLS
from fastapi.testclient import TestClient
from test_sso_api import API, SETUP, browser

from mealwright import outbound, sso


@pytest.fixture(autouse=True)
def fresh_cache() -> None:
    sso.cache.forget()


@pytest.fixture
def named(kitchen: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Set up with a provider that has a host name (so a look-up is made)."""
    idp = FakeProvider()
    idp.install(monkeypatch)
    app = cast(Any, kitchen.app)
    app.state.outbound = outbound.OutboundGate(app.state.sessionmaker, tls=cast(Any, FakeTLS()))
    assert kitchen.put(f"{API}/privacy/switches/single_sign_on", json={"on": True}).is_success
    assert kitchen.put(f"{API}/sso/settings", json=SETUP).is_success
    sso.cache.forget()
    return kitchen


def test_a_full_set_of_look_up_places_is_not_remembered_as_the_server_being_down(
    named: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    anonymous = browser(named)
    monkeypatch.setattr(outbound, "_look_ups_by_household", {1: outbound.MAX_STUCK_PER_HOUSEHOLD})
    monkeypatch.setattr(outbound, "_look_ups_running", outbound.MAX_STUCK_PER_HOUSEHOLD)
    held = anonymous.get(f"{API}/sso/start", follow_redirects=False)
    assert not held.headers["location"].startswith(f"{ISSUER}/authorize")
    assert sso.cache.get("no_discovery", ISSUER) is None
    # The places are free again: the very next start works, with no wait.
    monkeypatch.setattr(outbound, "_look_ups_by_household", {})
    monkeypatch.setattr(outbound, "_look_ups_running", 0)
    again = anonymous.get(f"{API}/sso/start", follow_redirects=False)
    assert again.headers["location"].startswith(f"{ISSUER}/authorize")


def test_a_look_up_that_really_fails_is_still_remembered(
    named: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def down(host: str, port: int) -> list[str]:
        raise OSError("down")

    monkeypatch.setattr(outbound, "_lookup", down)
    browser(named).get(f"{API}/sso/start", follow_redirects=False)
    assert sso.cache.get("no_discovery", ISSUER) == "unreachable"
