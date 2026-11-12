"""Signing a login out of its other devices, or resetting its password, also stops the API tokens
it made (O2 review r1, finding 5; proposed, for cabledrawer): a token is a sign-in too."""

import io
from typing import Any

import pytest
from conftest import ADMIN
from fastapi.testclient import TestClient
from sync_kit import API, ok

from mealwright.reset_admin import reset_admin

NEW = "a much better password"


def a_token_of(client: TestClient) -> TestClient:
    made = ok(
        client.post(f"{API}/api-tokens", json={"name": "Home Assistant", "scope": "full"}), 201
    )
    other = TestClient(client.app, base_url="https://testserver")
    other.headers["Authorization"] = f"Bearer {made['token']}"
    return other


def stopped(app: TestClient) -> None:
    r = app.get(f"{API}/me")
    assert r.status_code == 401, r.text
    assert r.json()["code"] == "bad_token"


@pytest.fixture
def two_devices(kitchen: TestClient) -> TestClient:
    """The admin's sign-in on a second device (the fixture's client is the first)."""
    phone = TestClient(kitchen.app, base_url="https://testserver")
    body = {"username": ADMIN["username"], "password": ADMIN["password"]}
    assert phone.post(f"{API}/session", json=body).status_code == 200
    return phone


def test_sign_out_everywhere_else_stops_the_tokens(
    kitchen: TestClient, two_devices: TestClient
) -> None:
    app = a_token_of(kitchen)
    assert app.get(f"{API}/me").status_code == 200
    assert two_devices.delete(f"{API}/me/sessions/others").status_code == 200
    stopped(app)


def test_a_password_change_that_signs_out_the_others_stops_the_tokens(
    kitchen: TestClient, two_devices: TestClient
) -> None:
    app = a_token_of(kitchen)
    body = {"current_password": ADMIN["password"], "new_password": NEW, "sign_out_others": True}
    assert two_devices.put(f"{API}/me/password", json=body).status_code == 200
    stopped(app)


def test_a_password_change_that_keeps_the_other_devices_keeps_the_tokens(
    kitchen: TestClient, two_devices: TestClient
) -> None:
    app = a_token_of(kitchen)
    body = {"current_password": ADMIN["password"], "new_password": NEW, "sign_out_others": False}
    assert two_devices.put(f"{API}/me/password", json=body).status_code == 200
    assert app.get(f"{API}/me").status_code == 200


def test_signing_out_one_other_device_keeps_the_tokens(
    kitchen: TestClient, two_devices: TestClient
) -> None:
    app = a_token_of(kitchen)
    sessions: list[dict[str, Any]] = two_devices.get(f"{API}/me/sign-in").json()["sessions"]
    other = next(s for s in sessions if not s["this_device"])
    assert two_devices.delete(f"{API}/me/sessions/{other['id']}").status_code == 200
    assert app.get(f"{API}/me").status_code == 200


def test_reset_admin_stops_the_tokens(kitchen: TestClient) -> None:
    app = a_token_of(kitchen)
    out = io.StringIO()
    assert reset_admin(kitchen.app.state.settings, ADMIN["username"], out) == 0  # type: ignore[attr-defined]
    stopped(app)
    assert "API tokens" in out.getvalue()
