"""Signed-out visitors get nothing (spec section 7; OWASP ASVS 4.0.3 V4.1.3, V3.3.1).

Every /api/v1 endpoint is listed from the app itself: both the real route table and the
OpenAPI document, which must agree, so an endpoint hidden from the API docs is still tried.
Each one is called with no cookie, a made-up cookie, the cookie of a session that ran out
and the cookie of a session that signed out. All must answer 401, except the short list
below, which a visitor needs before they can sign in.
"""

import re
from collections.abc import Iterable, Iterator
from datetime import timedelta
from typing import Any

import pytest
from conftest import ADMIN, SETUP_CODE
from fastapi.testclient import TestClient
from sqlalchemy import update

from mealwright.auth import COOKIE, now
from mealwright.models import Session

API = "/api/v1"

# The only endpoints a signed-out visitor may use, and why.
ALLOWED: dict[tuple[str, str], str] = {
    ("GET", f"{API}/openapi.json"): "the public API description",
    ("GET", f"{API}/version"): "which version is running",
    ("GET", f"{API}/health"): "the image health check: ok only when the database answers",
    ("GET", f"{API}/setup"): "whether this is a fresh install",
    ("POST", f"{API}/setup"): "first-run setup (refused once set up)",
    ("POST", f"{API}/session"): "signing in",
    ("DELETE", f"{API}/session"): "signing out (does nothing without a session)",
    ("GET", f"{API}/sign-in-options"): "what the sign-in page offers (0.9 O1)",
    ("GET", f"{API}/sso/start"): "starting a single sign-on sign-in (0.9 O1)",
    ("POST", f"{API}/sso/finish"): "finishing a single sign-on sign-in (0.9 O1)",
    # 0.9 A1: a person given a login opens their one-time sign-in link before they can sign in.
    # Without a link that works, both answer 404 and change nothing. The link's secret is in
    # the body, never the address (cabledrawer 13 Nov).
    ("POST", f"{API}/join/look"): "whether a sign-in link still works (no names)",
    ("POST", f"{API}/join"): "choosing a password with a sign-in link",
}


def _walk(routes: Iterable[Any]) -> Iterator[tuple[str, str]]:
    for route in routes:
        if hasattr(route, "effective_candidates"):  # an included router (FastAPI 0.14x)
            yield from _walk(route.effective_candidates())
        elif hasattr(route, "routes"):  # a mounted app or a plain router
            yield from _walk(route.routes)
        else:
            for method in getattr(route, "methods", None) or ():
                if method != "HEAD":
                    yield method, route.path


def real_routes(client: TestClient) -> set[tuple[str, str]]:
    return {
        (method, path)
        for method, path in _walk(client.app.routes)  # type: ignore[attr-defined]
        if path == "/api" or path.startswith("/api/")
    }


def documented_routes(client: TestClient) -> set[tuple[str, str]]:
    paths = client.app.openapi()["paths"]  # type: ignore[attr-defined]
    return {(method.upper(), path) for path, methods in paths.items() for method in methods}


def url_for(path: str) -> str:
    # Any id will do: the sign-in check comes before anything is looked up.
    return re.sub(r"\{[^}]+\}", "1", path)


def test_the_route_table_and_the_api_docs_agree(client: TestClient) -> None:
    assert real_routes(client) == documented_routes(client) | {("GET", f"{API}/openapi.json")}


def test_the_allow_list_is_only_real_endpoints(client: TestClient) -> None:
    assert set(ALLOWED) <= real_routes(client)


@pytest.fixture
def stale_cookies(kitchen: TestClient) -> dict[str, str]:
    """Cookies a visitor might still hold: made up, run out, signed out."""
    sessionmaker = kitchen.app.state.sessionmaker  # type: ignore[attr-defined]
    run_out = kitchen.cookies[COOKIE]
    with sessionmaker() as db:
        db.execute(update(Session).values(expires_at=now() - timedelta(seconds=1)))
        db.commit()
    kitchen.cookies.clear()
    assert kitchen.post(f"{API}/session", json=ADMIN).status_code == 200
    signed_out = kitchen.cookies[COOKIE]
    assert kitchen.delete(f"{API}/session").status_code == 204
    kitchen.cookies.clear()
    return {
        "none": "",
        "made up": "x" * 43,
        "run out": run_out,
        "signed out": signed_out,
    }


def test_every_endpoint_needs_a_session(kitchen: TestClient, stale_cookies: dict[str, str]) -> None:
    tried = 0
    for method, path in sorted(real_routes(kitchen) - set(ALLOWED)):
        for why, cookie in stale_cookies.items():
            headers = {"Cookie": f"{COOKIE}={cookie}"} if cookie else {}
            response = kitchen.request(method, url_for(path), json={}, headers=headers)
            assert response.status_code == 401, (method, path, why, response.text)
            assert "please sign in" in response.text.lower(), (method, path, why)
            assert COOKIE not in response.headers.get("set-cookie", ""), (method, path, why)
            tried += 1
    assert tried > 4 * 50  # the walk found the real endpoints


def test_the_allowed_endpoints_say_nothing_private(
    kitchen: TestClient, stale_cookies: dict[str, str]
) -> None:
    assert kitchen.get(f"{API}/me").status_code == 401
    assert set(kitchen.get(f"{API}/version").json()) == {"version"}
    assert kitchen.get(f"{API}/setup").json() == {"needs_setup": False, "plain_http_allowed": False}
    # Setup can't be run a second time to make a new admin.
    again = {"name": "Mallory", "username": "mallory", "password": "a long enough password"}
    again["setup_code"] = SETUP_CODE  # even with the code (all a log reader could know)
    assert kitchen.post(f"{API}/setup", json=again).status_code == 409
    assert kitchen.post(f"{API}/session", json=again).status_code == 401
    assert kitchen.delete(f"{API}/session").status_code == 204
    assert COOKIE not in kitchen.cookies
    docs = kitchen.get(f"{API}/openapi.json").text.lower()
    for private in (ADMIN["username"], ADMIN["password"], ADMIN["name"].lower()):
        assert private not in docs
