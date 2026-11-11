"""Browser security rules (spec section 7)."""

import re
from pathlib import Path

import pytest
from conftest import ADMIN
from fastapi.testclient import TestClient
from starlette.types import Receive, Scope, Send

from mealwright.config import Settings
from mealwright.main import create_app
from mealwright.security import SecurityHeadersMiddleware, content_security_policy


def _policy(header: str) -> dict[str, list[str]]:
    directives = {}
    for part in header.split(";"):
        name, *values = part.split()
        directives[name] = values
    return directives


@pytest.mark.parametrize("path", ["/api/v1/version", "/api/v1/openapi.json", "/no-such-page"])
def test_every_response_has_the_headers(client: TestClient, path: str) -> None:
    headers = client.get(path).headers
    assert "content-security-policy" in headers
    assert headers["x-content-type-options"] == "nosniff"
    assert headers["x-frame-options"] == "DENY"
    assert headers["referrer-policy"] == "no-referrer"
    assert headers["cross-origin-opener-policy"] == "same-origin"
    assert headers["cross-origin-resource-policy"] == "same-origin"


def test_policy_only_allows_our_own_server(client: TestClient) -> None:
    policy = _policy(client.get("/api/v1/version").headers["content-security-policy"])
    allowed = {"'self'", "'none'", "data:", "blob:"}
    for name, sources in policy.items():
        for source in sources:
            assert source in allowed, f"{name} allows {source}"
    # No inline or eval'd scripts, no plugins, no framing, no other base URL.
    assert policy["script-src"] == ["'self'"]
    assert policy["default-src"] == ["'self'"]
    assert policy["object-src"] == ["'none'"]
    assert policy["frame-ancestors"] == ["'none'"]
    assert policy["base-uri"] == ["'none'"]


def test_script_hashes_are_the_only_exception() -> None:
    digest = "sha256-" + "A" * 43 + "="
    policy = _policy(content_security_policy([digest]))
    assert policy["script-src"] == ["'self'", f"'{digest}'"]
    assert "'unsafe-inline'" not in str(policy)
    assert "'unsafe-eval'" not in str(policy)


def test_location_is_never_allowed(client: TestClient) -> None:
    permissions = client.get("/api/v1/version").headers["permissions-policy"]
    assert "geolocation=()" in permissions
    assert "camera=()" in permissions
    assert "microphone=()" in permissions
    # Keep screen awake while cooking is the one feature switched on.
    assert re.search(r"screen-wake-lock=\(self\)", permissions)


def test_headers_are_not_duplicated(client: TestClient) -> None:
    response = client.get("/api/v1/version")
    assert len(response.headers.get_list("content-security-policy")) == 1


@pytest.mark.parametrize("path", ["/api/v1/version", "/api/v1/openapi.json", "/api/v1/nope"])
def test_every_api_response_is_no_store(client: TestClient, path: str) -> None:
    assert client.get(path).headers["cache-control"] == "no-store"


def test_no_store_is_only_for_the_api(client: TestClient) -> None:
    assert client.get("/apix").headers.get("cache-control") != "no-store"


# --- HSTS (cabledrawer 19 Oct) ------------------------------------------------------------------


@pytest.mark.parametrize("path", ["/api/v1/version", "/api/v1/nope", "/no-such-page"])
def test_https_mode_tells_browsers_to_use_only_https(client: TestClient, path: str) -> None:
    response = client.get(path)
    # One year; no includeSubDomains (other sub-domains are not affected), never the preload list.
    assert response.headers.get_list("strict-transport-security") == ["max-age=31536000"]


def test_hsts_is_on_a_signed_in_answer_too(client: TestClient) -> None:
    response = client.post("/api/v1/setup", json=ADMIN)
    assert response.status_code == 201
    assert response.headers["strict-transport-security"] == "max-age=31536000"
    assert client.get("/api/v1/me").headers["strict-transport-security"] == "max-age=31536000"


def test_plain_http_mode_never_sends_hsts(tmp_path: Path) -> None:
    settings = Settings(data_dir=tmp_path / "data", run_jobs=False, allow_plain_http=True)
    with TestClient(create_app(settings), base_url="http://192.168.1.20:8080") as lan:
        for path in ("/api/v1/version", "/api/v1/nope", "/no-such-page"):
            response = lan.get(path)
            assert "strict-transport-security" not in response.headers
            assert "content-security-policy" in response.headers  # the rest still sent


def test_plain_http_mode_drops_an_hsts_header_from_further_in() -> None:
    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await send(
            {
                "type": "http.response.start",
                "status": 200,
                "headers": [(b"strict-transport-security", b"max-age=63072000; preload")],
            }
        )
        await send({"type": "http.response.body", "body": b""})

    plain = TestClient(SecurityHeadersMiddleware(app, https=False))
    assert "strict-transport-security" not in plain.get("/").headers
    secure = TestClient(SecurityHeadersMiddleware(app, https=True))
    assert secure.get("/").headers.get_list("strict-transport-security") == ["max-age=31536000"]
