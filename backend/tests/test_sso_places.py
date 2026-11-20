"""Signed-out callers can't hold every single sign-on place or start as often as they like
(review R7): the last place of a household, and of the total, is for the background checks
only; and each start or finish is counted per address."""

from typing import Any, cast

import pytest
from fake_idp import ISSUER, FakeProvider, FakeTLS
from fastapi.testclient import TestClient
from test_sso_api import API, SETUP

from mealwright import outbound, sso
from mealwright.auth import SlowDown


def test_signed_out_callers_can_never_take_the_places_the_background_checks_need(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = {1: sso.IN_FLIGHT_MOST - 1}
    monkeypatch.setattr(sso, "_in_flight", held)
    # a start or finish, signed out:
    with pytest.raises(sso.SsoFailed) as refused, sso.waiting_for(1):
        pass  # pragma: no cover
    assert refused.value.code == "unreachable"
    assert refused.value.say_nothing_of_it
    with sso._slot(1):  # the background check still has its place
        assert held[1] == sso.IN_FLIGHT_MOST
    assert held == {1: sso.IN_FLIGHT_MOST - 1}


def test_the_last_place_in_all_is_the_background_checks_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    held = {2: sso.IN_FLIGHT_MOST - 1, 3: sso.IN_FLIGHT_MOST - 1, 1: 1}
    assert sum(held.values()) == sso.IN_FLIGHT_TOTAL - 1
    monkeypatch.setattr(sso, "_in_flight", held)
    with pytest.raises(sso.SsoFailed), sso.waiting_for(1):
        pass  # pragma: no cover
    with sso._slot(1):
        assert sum(held.values()) == sso.IN_FLIGHT_TOTAL
    # Past the cap, even the background check is told to try again (as before).
    monkeypatch.setattr(sso, "_in_flight", {1: 1, 2: 3, 3: 3, 4: 1})
    with pytest.raises(sso.SsoFailed), sso._slot(1):
        pass  # pragma: no cover


@pytest.fixture
def named(kitchen: TestClient, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    idp = FakeProvider()
    idp.install(monkeypatch)
    app = cast(Any, kitchen.app)
    app.state.outbound = outbound.OutboundGate(app.state.sessionmaker, tls=cast(Any, FakeTLS()))
    assert kitchen.put(f"{API}/privacy/switches/single_sign_on", json={"on": True}).is_success
    assert kitchen.put(f"{API}/sso/settings", json=SETUP).is_success
    sso.cache.forget()
    return kitchen


def _from(app: TestClient, address: str) -> TestClient:
    return TestClient(app.app, base_url="https://testserver", client=(address, 50000))


def test_many_starts_from_one_address_are_slowed_down_and_another_address_still_works(
    named: TestClient,
) -> None:
    flood = _from(named, "203.0.113.9")
    for _ in range(SlowDown.SSO_FREE):
        got = flood.get(f"{API}/sso/start", follow_redirects=False)
        assert got.headers["location"].startswith(f"{ISSUER}/authorize")
    refused = flood.get(f"{API}/sso/start", follow_redirects=False)
    assert not refused.headers["location"].startswith(f"{ISSUER}/authorize")
    assert "sso=unreachable" in refused.headers["location"]
    # A finish from the same address is slowed down by the same count.
    done = flood.post(f"{API}/sso/finish", json={"state": "x", "code": "y"})
    assert done.status_code == 400
    assert done.json()["code"] == "unreachable"
    # Another address is not.
    other = _from(named, "203.0.113.10")
    fine = other.get(f"{API}/sso/start", follow_redirects=False)
    assert fine.headers["location"].startswith(f"{ISSUER}/authorize")


def test_a_few_starts_from_one_address_are_never_slowed(named: TestClient) -> None:
    home = _from(named, "198.51.100.7")
    for _ in range(10):
        got = home.get(f"{API}/sso/start", follow_redirects=False)
        assert got.headers["location"].startswith(f"{ISSUER}/authorize")
