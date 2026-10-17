"""Browser security rules (spec section 7)."""

import re

import pytest
from fastapi.testclient import TestClient

from mealwright.security import content_security_policy


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
