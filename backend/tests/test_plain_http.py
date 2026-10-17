"""Signing in needs HTTPS (spec section 7), and says so instead of failing silently.

On a plain http:// address the browser would quietly drop the HTTPS-only session
cookie, and the person would seem to sign in and then be signed straight out.
"""

import logging
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from mealwright.auth import COOKIE, HTTPS_NEEDED
from mealwright.config import Settings
from mealwright.main import create_app

ADMIN = {"name": "Tess", "username": "tess", "password": "kitchen-secret-2026"}
LAN = "http://192.168.1.20:8080"


def browser(app: object, address: str) -> TestClient:
    """A client that behaves like a browser on `address` (it sends its Origin)."""
    client = TestClient(app, base_url=address)  # type: ignore[arg-type]
    client.headers["Origin"] = address
    return client


@pytest.fixture
def app(settings: Settings) -> Iterator[object]:
    application = create_app(settings)
    with TestClient(application):  # run start-up (migrations)
        yield application


def test_plain_http_setup_is_refused_with_a_clear_message(app: object) -> None:
    lan = browser(app, LAN)
    response = lan.post("/api/v1/setup", json=ADMIN)
    assert response.status_code == 400
    assert response.json() == {"detail": HTTPS_NEEDED}
    assert "https://" in HTTPS_NEEDED and "MEALWRIGHT_ALLOW_PLAIN_HTTP" in HTTPS_NEEDED
    assert COOKIE not in response.headers.get("set-cookie", "")
    # Nothing was created, so setup can still happen over HTTPS.
    assert lan.get("/api/v1/setup").json()["needs_setup"] is True


def test_plain_http_sign_in_is_refused_with_a_clear_message(app: object) -> None:
    assert (
        browser(app, "https://mealwright.example").post("/api/v1/setup", json=ADMIN).status_code
        == 201
    )
    response = browser(app, LAN).post(
        "/api/v1/session", json={"username": "tess", "password": ADMIN["password"]}
    )
    assert response.status_code == 400
    assert response.json() == {"detail": HTTPS_NEEDED}


@pytest.mark.parametrize("address", ["http://localhost:8080", "http://127.0.0.1:8080"])
def test_localhost_counts_as_secure(app: object, address: str) -> None:
    # Browsers treat localhost as a secure address, so the cookie works there.
    assert browser(app, address).post("/api/v1/setup", json=ADMIN).status_code == 201


def test_https_works(app: object) -> None:
    client = browser(app, "https://mealwright.example")
    assert client.post("/api/v1/setup", json=ADMIN).status_code == 201
    assert client.get("/api/v1/me").status_code == 200


def test_plain_http_allowed_for_testing(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    settings = Settings(data_dir=tmp_path / "data", allow_plain_http=True)
    with caplog.at_level(logging.WARNING, logger="mealwright"):
        app = create_app(settings)
    assert "MEALWRIGHT_ALLOW_PLAIN_HTTP is on" in caplog.text
    with TestClient(app):
        lan = browser(app, LAN)
        assert lan.get("/api/v1/setup").json()["plain_http_allowed"] is True
        response = lan.post("/api/v1/setup", json=ADMIN)
        assert response.status_code == 201
        assert "secure" not in response.headers["set-cookie"].lower()
        assert lan.get("/api/v1/me").status_code == 200  # stays signed in


def test_plain_http_not_allowed_by_default(app: object) -> None:
    assert browser(app, LAN).get("/api/v1/setup").json()["plain_http_allowed"] is False
