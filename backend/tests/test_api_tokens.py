"""API tokens (0.9 O2; spec section 7, cabledrawer 17 Oct): read only or full, with an optional end
date, for scripts and other apps. Only admins make them; a token never does more than the admin
who made it, and never what `SESSION_ONLY` and `roles.TOKENS_NEVER` list."""

import logging
import re
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sync_kit import API, PHONE_A, action, db, login_id, new_id, ok, person, send

from mealwright import api_tokens, roles
from mealwright.auth import COOKIE, current_session
from mealwright.models import ApiToken, Login, Member, utcnow

# Every endpoint a token can never use, whatever it may do otherwise (proposed, for cabledrawer):
# making, listing and deleting tokens, your own password, where you’re signed in and a reset
# link made for you (16b S-M1 e), and "Who's this?" on a shared device.
SESSION_ONLY = {
    ("GET", f"{API}/api-tokens"),
    ("POST", f"{API}/api-tokens"),
    ("DELETE", f"{API}/api-tokens/{{token_id}}"),
    ("GET", f"{API}/me/sign-in"),
    ("PUT", f"{API}/me/password"),
    ("DELETE", f"{API}/me/sessions/others"),
    ("DELETE", f"{API}/me/reset-link"),
    ("DELETE", f"{API}/me/sessions/{{session_id}}"),
    ("GET", f"{API}/whos-this"),
    ("PUT", f"{API}/whos-this"),
}


def _make(client: TestClient, scope: str = "read", **extra: Any) -> str:
    made = ok(
        client.post(f"{API}/api-tokens", json={"name": "Home Assistant", "scope": scope, **extra}),
        201,
    )
    return str(made["token"])


def _app(kitchen: TestClient, token: str) -> TestClient:
    """Another app: no cookie, only the token."""
    other = TestClient(kitchen.app, base_url="https://testserver")
    other.headers["Authorization"] = f"Bearer {token}"
    return other


def _people_ids(client: TestClient) -> dict[str, int]:
    return {p["name"]: p["id"] for p in ok(client.get(f"{API}/people"))["people"]}


def _refused(r: Any, status: int, code: str) -> None:
    assert r.status_code == status, r.text
    assert r.json()["code"] == code


# --- Making and listing ---------------------------------------------------------------------


def test_a_token_is_shown_once_and_only_its_hash_is_kept(kitchen: TestClient) -> None:
    read = _make(kitchen, "read")
    full = _make(kitchen, "full")
    assert read.startswith("mw_ro_") and len(read) == 6 + 43
    assert full.startswith("mw_rw_")
    listed = ok(kitchen.get(f"{API}/api-tokens"))
    assert [t["scope"] for t in listed["tokens"]] == ["full", "read"]  # newest first
    first = listed["tokens"][1]
    assert first["name"] == "Home Assistant" and first["last_used_at"] is None
    assert first["expires_on"] is None
    assert abs(date.fromisoformat(listed["today"]) - date.today()) <= timedelta(days=1)
    text = kitchen.get(f"{API}/api-tokens").text
    assert read not in text and full not in text
    with db(kitchen) as session:
        hashes = set(session.scalars(select(ApiToken.token_hash)))
    assert hashes == {api_tokens.token_hash(read), api_tokens.token_hash(full)}
    assert read not in hashes


def test_names_and_dates_are_checked(kitchen: TestClient) -> None:
    body = {"name": "  ", "scope": "read"}
    _refused(kitchen.post(f"{API}/api-tokens", json=body), 422, "name_needed")
    body = {"name": "x" * 61, "scope": "read"}
    _refused(kitchen.post(f"{API}/api-tokens", json=body), 422, "name_too_long")
    assert (
        kitchen.post(f"{API}/api-tokens", json={"name": "S", "scope": "admin"}).status_code == 422
    )
    yesterday = (date.today() - timedelta(days=2)).isoformat()
    _refused(
        kitchen.post(
            f"{API}/api-tokens", json={"name": "S", "scope": "read", "expires_on": yesterday}
        ),
        422,
        "date_passed",
    )
    far = (date.today() + timedelta(days=6 * 366)).isoformat()
    _refused(
        kitchen.post(f"{API}/api-tokens", json={"name": "S", "scope": "read", "expires_on": far}),
        422,
        "date_too_far",
    )
    on = (date.today() + timedelta(days=30)).isoformat()
    _make(kitchen, expires_on=on)
    assert ok(kitchen.get(f"{API}/api-tokens"))["tokens"][0]["expires_on"] == on


def test_only_an_admin_makes_lists_or_deletes_tokens(kitchen: TestClient) -> None:
    token = _make(kitchen)
    wren = person(kitchen)
    _refused(wren.get(f"{API}/api-tokens"), 403, "admins_only")
    _refused(
        wren.post(f"{API}/api-tokens", json={"name": "S", "scope": "read"}), 403, "admins_only"
    )
    token_id = ok(kitchen.get(f"{API}/api-tokens"))["tokens"][0]["id"]
    _refused(wren.delete(f"{API}/api-tokens/{token_id}"), 403, "admins_only")
    assert _app(kitchen, token).get(f"{API}/me").status_code == 200


def test_a_household_sees_and_deletes_only_its_own_tokens(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    _make(kitchen)
    token_id = ok(kitchen.get(f"{API}/api-tokens"))["tokens"][0]["id"]
    assert ok(neighbour.get(f"{API}/api-tokens"))["tokens"] == []
    _refused(neighbour.delete(f"{API}/api-tokens/{token_id}"), 404, "not_found")
    assert len(ok(kitchen.get(f"{API}/api-tokens"))["tokens"]) == 1


# --- Using a token -----------------------------------------------------------------------------


def test_a_read_only_token_reads_and_never_changes(kitchen: TestClient) -> None:
    app = _app(kitchen, _make(kitchen, "read"))
    assert ok(app.get(f"{API}/me"))["username"] == "tess"
    ok(app.get(f"{API}/foods"))
    writes = [
        app.post(f"{API}/foods", json={"name": "Rice"}),
        app.patch(f"{API}/household", json={"cook_per_step": True}),
        app.put(f"{API}/places/order", json={"ids": []}),
        app.delete(f"{API}/places/1"),
        app.post(f"{API}/recipes/import", json={"text": "https://example.org/pie"}),
        app.post(f"{API}/recipes/import/save", json={}),
    ]
    for r in writes:
        _refused(r, 403, "read_only_token")
    ok(kitchen.get(f"{API}/foods"))


def test_a_full_token_reads_and_changes_the_kitchen(kitchen: TestClient) -> None:
    app = _app(kitchen, _make(kitchen, "full"))
    ok(app.post(f"{API}/foods", json={"name": "Toor dal"}), 201)
    assert "Toor dal" in kitchen.get(f"{API}/foods").text
    ok(app.patch(f"{API}/household", json={"cook_per_step": True}))  # household settings: yes


@pytest.mark.parametrize("method,path", sorted(SESSION_ONLY))
def test_a_token_never_uses_the_session_only_endpoints(
    kitchen: TestClient, method: str, path: str
) -> None:
    app = _app(kitchen, _make(kitchen, "full"))
    r = app.request(method, path.replace("{token_id}", "1").replace("{session_id}", "1"), json={})
    _refused(r, 403, "not_for_tokens")


def test_the_session_only_list_is_every_endpoint_that_refuses_tokens(kitchen: TestClient) -> None:
    """Read from the app: every route whose dependencies include `current_session`."""

    def needs_session(dependant: Any) -> bool:
        return any(d.call is current_session or needs_session(d) for d in dependant.dependencies)

    def routes(found: Any) -> Any:
        for route in found:
            if hasattr(route, "effective_candidates"):
                yield from routes(route.effective_candidates())
            elif hasattr(route, "dependant"):
                yield route
            elif hasattr(route, "routes"):
                yield from routes(route.routes)

    found = {
        (method, route.path)
        for route in routes(kitchen.app.routes)  # type: ignore[attr-defined]
        if needs_session(route.dependant)
        for method in route.methods
        if method != "HEAD"
    }
    assert found == SESSION_ONLY


def test_a_token_never_changes_people_roles_privacy_or_sign_in(kitchen: TestClient) -> None:
    person(kitchen)
    app = _app(kitchen, _make(kitchen, "full"))
    wren = _people_ids(kitchen)["Wren"]
    ok(kitchen.post(f"{API}/people", json={"name": "Sam"}), 201)
    sam = _people_ids(kitchen)["Sam"]
    refused = [
        app.post(f"{API}/people", json={"name": "Joss"}),
        app.patch(f"{API}/people/{wren}", json={"role": "admin"}),
        app.delete(f"{API}/people/{wren}"),
        app.post(f"{API}/people/{wren}/login", json={"username": "wren2"}),
        app.delete(f"{API}/people/{wren}/login"),
        app.post(f"{API}/people/{sam}/reset-password"),
        app.put(f"{API}/people/ask-whos-this", json={"on": True}),
        app.put(f"{API}/privacy/switches/recipe_import", json={"on": True}),
        app.post(f"{API}/privacy/own-network", json={"value": "wiki.home"}),
        app.delete(f"{API}/privacy/own-network/1"),
    ]
    for r in refused:
        _refused(r, 403, "not_for_tokens")
    listed = ok(app.get(f"{API}/people"))  # reading is fine, but it can't change them
    assert listed["can_change"] is False
    assert ok(app.get(f"{API}/privacy/switches"))["can_change"] is False


def test_a_token_cant_undo_a_change_to_the_people(kitchen: TestClient) -> None:
    ok(kitchen.post(f"{API}/people", json={"name": "Joss"}), 201)
    change = ok(kitchen.get(f"{API}/changes"))["changes"][0]
    app = _app(kitchen, _make(kitchen, "full"))
    seen = ok(app.get(f"{API}/changes"))["changes"][0]
    assert seen["id"] == change["id"] and seen["can_undo"] is False
    _refused(app.post(f"{API}/changes/{change['id']}/undo"), 403, "not_for_tokens")


def test_every_token_that_doesnt_work_gets_the_same_answer(kitchen: TestClient) -> None:
    good = _make(kitchen, "full")
    deleted = _make(kitchen, "full")
    ended = _make(kitchen, "full")
    with db(kitchen) as session:
        row = session.scalar(
            select(ApiToken).where(ApiToken.token_hash == api_tokens.token_hash(ended))
        )
        assert row is not None
        row.expires_at = utcnow() - timedelta(seconds=1)
        session.commit()
    with db(kitchen) as session:
        gone = session.scalar(
            select(ApiToken.id).where(ApiToken.token_hash == api_tokens.token_hash(deleted))
        )
    assert kitchen.delete(f"{API}/api-tokens/{gone}").status_code == 204
    answers = []
    for token in (
        deleted,
        ended,
        "mw_rw_" + "A" * 43,  # made up
        good[:-1],  # cut short
        good + "x",
        "mw_" + good[6:],
    ):
        r = _app(kitchen, token).get(f"{API}/me")
        assert r.status_code == 401, token
        assert r.headers["www-authenticate"] == 'Bearer realm="mealwright"'
        answers.append(r.json())
    assert all(a == {"detail": api_tokens.DOESNT_WORK, "code": "bad_token"} for a in answers)
    assert _app(kitchen, good).get(f"{API}/me").status_code == 200
    assert ok(kitchen.get(f"{API}/api-tokens"))["tokens"] != []  # the ended one is still listed


def test_a_token_and_a_cookie_together_are_refused(kitchen: TestClient) -> None:
    token = _make(kitchen, "full")
    r = kitchen.get(f"{API}/me", headers={"Authorization": f"Bearer {token}"})
    _refused(r, 400, "token_and_cookie")
    assert COOKIE in kitchen.cookies


def test_a_proxys_own_authorization_header_leaves_the_cookie_working(kitchen: TestClient) -> None:
    for header in ("Basic a3Jpc2huYTpzZWNyZXQ=", "Bearer eyJhbGciOi.proxy.token"):
        assert kitchen.get(f"{API}/me", headers={"Authorization": header}).status_code == 200
    other = TestClient(kitchen.app, base_url="https://testserver")
    r = other.get(f"{API}/me", headers={"Authorization": "Basic a3Jpc2huYTpzZWNyZXQ="})
    assert r.status_code == 401 and r.json()["detail"] == "Please sign in."


def test_last_used_is_written_at_most_once_a_minute(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _make(kitchen)
    app = _app(kitchen, token)
    ok(app.get(f"{API}/me"))
    first = ok(kitchen.get(f"{API}/api-tokens"))["tokens"][0]["last_used_at"]
    assert first is not None
    ok(app.get(f"{API}/me"))
    assert ok(kitchen.get(f"{API}/api-tokens"))["tokens"][0]["last_used_at"] == first
    later = utcnow() + timedelta(minutes=2)
    monkeypatch.setattr(api_tokens, "utcnow", lambda: later)
    ok(app.get(f"{API}/me"))
    assert ok(kitchen.get(f"{API}/api-tokens"))["tokens"][0]["last_used_at"] != first


# --- Tokens follow the admin who made them ---------------------------------------------------


def _second_admin(kitchen: TestClient) -> TestClient:
    wren = person(kitchen)
    ok(kitchen.patch(f"{API}/people/{_people_ids(kitchen)['Wren']}", json={"role": "admin"}))
    return wren


def test_made_a_member_their_tokens_stop_for_good(kitchen: TestClient) -> None:
    app = _app(kitchen, _make(kitchen, "full"))
    wren = _second_admin(kitchen)
    ok(wren.patch(f"{API}/people/{_people_ids(wren)['Tess']}", json={"role": "member"}))
    assert app.get(f"{API}/me").status_code == 401
    change = ok(wren.get(f"{API}/changes"))["changes"][0]
    ok(wren.post(f"{API}/changes/{change['id']}/undo"))  # an admin again…
    assert ok(kitchen.get(f"{API}/me"))["role"] == "admin"
    assert app.get(f"{API}/me").status_code == 401  # …but the token stays deleted
    assert ok(kitchen.get(f"{API}/api-tokens"))["tokens"] == []


def test_a_removed_admins_tokens_stop_for_good(kitchen: TestClient) -> None:
    wren = _second_admin(kitchen)
    app = _app(kitchen, _make(wren, "full"))
    assert app.get(f"{API}/me").status_code == 200
    ok(kitchen.delete(f"{API}/people/{_people_ids(kitchen)['Wren']}"))
    assert app.get(f"{API}/me").status_code == 401
    change = ok(kitchen.get(f"{API}/changes"))["changes"][0]
    ok(kitchen.post(f"{API}/changes/{change['id']}/undo"))
    assert app.get(f"{API}/me").status_code == 401


def test_a_token_stops_at_once_whatever_way_its_admin_stops_being_one(kitchen: TestClient) -> None:
    """Belt and braces: even changed straight in the database, the role is checked each time."""
    wren = _second_admin(kitchen)
    app = _app(kitchen, _make(wren, "full"))
    with db(kitchen) as session:
        session.execute(update(Login).where(Login.username == "wren").values(role="member"))
        session.commit()
    assert app.get(f"{API}/me").status_code == 401
    with db(kitchen) as session:
        session.execute(update(Login).where(Login.username == "wren").values(role="admin"))
        member_id = session.scalar(select(Login.member_id).where(Login.username == "wren"))
        session.execute(update(Member).where(Member.id == member_id).values(removed_at=utcnow()))
        session.commit()
    assert app.get(f"{API}/me").status_code == 401


# --- Never logged, documented ------------------------------------------------------------------


def test_a_token_is_never_logged(kitchen: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    caplog.set_level(logging.DEBUG)
    token = _make(kitchen, "read")
    app = _app(kitchen, token)
    ok(app.get(f"{API}/me"))
    app.post(f"{API}/foods", json={"name": "Rice"})
    _app(kitchen, token[:-1] + "Z").get(f"{API}/me")
    kitchen.get(f"{API}/me", headers={"Authorization": f"Bearer {token}"})
    text = caplog.text
    assert token not in text and token[6:] not in text and token[6:20] not in text
    assert api_tokens.token_hash(token) not in text
    assert "API token made by tess" in text


def test_the_api_docs_describe_the_bearer_token(kitchen: TestClient) -> None:
    spec = kitchen.get(f"{API}/openapi.json").json()
    scheme = spec["components"]["securitySchemes"]["ApiToken"]
    assert scheme["type"] == "http" and scheme["scheme"] == "bearer"
    assert {"ApiToken": []} in spec["paths"][f"{API}/foods"]["get"]["security"]


# --- Settings › Backups & your data is never for a token (O2 review r1, finding 1; proposed,
# for cabledrawer)
# --

YOUR_DATA_ROUTES = [
    ("GET", "/your-data/backups", None),
    ("PATCH", "/your-data/backups", {"keep": 3}),
    ("POST", "/your-data/backups", None),
    ("GET", "/your-data/export", None),
    ("GET", "/your-data/delete-everything", None),
    ("POST", "/your-data/export", {"password": "a long enough one"}),
    ("POST", "/your-data/delete-everything", {"words": "delete everything", "password": "x"}),
    # D3: confirming Delete everything with single sign-on is a Your data action too
    ("POST", "/sso/confirm", None),
]


@pytest.mark.parametrize("scope", ["read", "full"])
@pytest.mark.parametrize("method,path,body", YOUR_DATA_ROUTES)
def test_a_token_never_reaches_your_data(
    kitchen: TestClient, scope: str, method: str, path: str, body: Any
) -> None:
    """A read-only token used to read the whole export (every table), and a full one could
    make backups or Delete everything. Now every Your data route says no to either."""
    app = _app(kitchen, _make(kitchen, scope))
    r = app.request(method, f"{API}{path}", json=body)
    assert r.status_code == 403, r.text
    if scope == "full" or method == "GET":
        _refused(r, 403, "not_for_tokens")
    else:
        assert r.json()["code"] in {"read_only_token", "not_for_tokens"}


def test_a_token_cant_start_a_wrong_password_pause_on_the_admin(kitchen: TestClient) -> None:
    app = _app(kitchen, _make(kitchen, "full"))
    for _ in range(6):
        _refused(
            app.post(
                f"{API}/your-data/delete-everything",
                json={"words": "delete everything", "password": "not the password"},
            ),
            403,
            "not_for_tokens",
        )
    # The admin's own first wrong try is an ordinary wrong password, not a pause.
    again = kitchen.post(
        f"{API}/your-data/delete-everything",
        json={"words": "delete everything", "password": "still not the password"},
    )
    _refused(again, 403, "wrong_password")


def test_the_export_isnt_readable_with_a_read_only_token(kitchen: TestClient) -> None:
    assert kitchen.get(f"{API}/your-data/export").status_code == 200  # the admin can
    _refused(
        _app(kitchen, _make(kitchen, "read")).get(f"{API}/your-data/export"), 403, "not_for_tokens"
    )


# --- Every route of a token-never action, so taking an action out of TOKENS_NEVER fails here
# (O2 review r1, finding 4). A full token on each, as an admin's own would be. ----------------

NEVER_ROUTES = [
    # People
    ("POST", "/people", {"name": "Joss"}),
    ("PATCH", "/people/{wren}", {"role": "admin"}),
    ("DELETE", "/people/{wren}", None),
    ("POST", "/people/{wren}/login", {"username": "wren2"}),
    ("DELETE", "/people/{wren}/login", None),
    ("POST", "/people/{someone}/reset-password", None),
    ("PUT", "/people/ask-whos-this", {"on": True}),
    # "Who is this?" and the Person page's single sign-on row (0.9.5 Pe3/M2)
    ("POST", "/people/sso-accounts/{someone}/link", {"member_id": None}),
    ("POST", "/people/sso-accounts/{someone}/refuse", None),
    ("DELETE", "/people/{person}/sso", None),
    # Privacy (and the update check, which connects out)
    ("PUT", "/privacy/switches/{switch}", {"on": True}),
    ("GET", "/privacy/own-network", None),  # a Household page, admins only (D4, BE12)
    ("POST", "/privacy/own-network", {"value": "wiki.home"}),
    ("DELETE", "/privacy/own-network/{entry}", None),
    ("POST", "/updates/check", None),
    # Sign-in: single sign-on, in every part (reading the setup too)
    ("GET", "/sso/settings", None),
    (
        "PUT",
        "/sso/settings",
        {
            "issuer": "https://id.example.org",
            "client_id": "mealwright",
            "client_secret": "a-secret",
            "button_name": "Authentik",
            "redirect_uri": "https://testserver/auth/callback",
        },
    ),
    ("PUT", "/sso/password-sign-in", {"on": False}),
    ("POST", "/sso/test", None),
    ("POST", "/sso/link", None),
    ("DELETE", "/sso/link", None),
    # Your data
    ("GET", "/your-data/backups", None),
    ("PATCH", "/your-data/backups", {"keep": 3}),
    ("POST", "/your-data/backups", None),
    ("GET", "/your-data/export", None),
    ("GET", "/your-data/delete-everything", None),
    ("POST", "/your-data/export", {"password": "a long enough one"}),
    ("POST", "/your-data/delete-everything", {"words": "delete everything", "password": "x"}),
    # D3: confirming Delete everything with single sign-on is a Your data action too
    ("POST", "/sso/confirm", None),
]


def _never(app: TestClient, wren: int) -> list[tuple[str, str, Any]]:
    out = []
    for method, path, body in NEVER_ROUTES:
        filled = path.replace("{wren}", str(wren))
        filled = filled.replace("{switch}", "recipe_import").replace("{entry}", "1")
        filled = filled.replace("{person}", str(wren))
        filled = filled.replace("{someone}", "1")  # any id: a token is refused before a person
        r = app.request(method, f"{API}{filled}", json=body)
        out.append((method, path, r))
    return out


def test_a_full_token_is_refused_on_every_route_of_a_token_never_action(
    kitchen: TestClient,
) -> None:
    person(kitchen)
    app = _app(kitchen, _make(kitchen, "full"))
    for method, path, r in _never(app, _people_ids(kitchen)["Wren"]):
        assert r.status_code == 403 and r.json()["code"] == "not_for_tokens", (method, path, r.text)


@pytest.mark.parametrize("action", sorted(roles.TOKENS_NEVER))
def test_taking_an_action_out_of_tokens_never_is_noticed(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch, action: roles.Action
) -> None:
    """Whichever action is let through, some route above stops being refused."""
    person(kitchen)
    app = _app(kitchen, _make(kitchen, "full"))
    wren = _people_ids(kitchen)["Wren"]
    monkeypatch.setattr(roles, "TOKENS_NEVER", roles.TOKENS_NEVER - {action})
    let_through = [
        (method, path)
        for method, path, r in _never(app, wren)
        if not (r.status_code == 403 and r.json().get("code") == "not_for_tokens")
    ]
    assert let_through, f"nothing in NEVER_ROUTES notices {action} leaving TOKENS_NEVER"


# --- Every route of the app is listed, so a new one can't slip through (O2 review r1 finding 2,
# r2 finding 2, r3 finding 4: how GET /backups was missed, and why the walk now covers every
# route and method, matched exactly). A route is token-never (NEVER_ROUTES), session-only
# (SESSION_ONLY), one a token may read (below, with its reason), one that needs no sign-in, or
# a kitchen route a token may use (the explicit prefix list below). A route in none of them,
# or one with no dependants to look at (a plain Starlette route), fails the test. ----------

# Read-only routes a token may use, each with why that is fine.
A_TOKEN_MAY_READ = {
    ("GET", "/people"): "names and roles, no sign-in details: the household's own page shows them",
    ("GET", "/privacy/switches"): "which switches are on; changing one is token-never",
    ("GET", "/updates"): "the version and the last answer; checking now is token-never",
}

# Routes that need no sign-in at all (a token or cookie doesn't change what they do).
NO_SIGN_IN = {
    ("GET", "/setup"): "is Mealwright set up yet",
    ("POST", "/setup"): "the first admin, by the setup code",
    ("GET", "/sso/start"): "starts a sign-in at the provider",
    ("POST", "/sso/finish"): "the callback page posts what the provider sent",
    ("GET", "/sign-in-options"): "which ways of signing in the sign-in page offers",
    ("GET", "/version"): "the running version, as the sign-in page shows it",
    ("GET", "/health"): "the image health check: ok only when the database answers",
    ("GET", "/problem-report"): "the text a person copies when something goes wrong",
    ("POST", "/session"): "signing in",
    ("DELETE", "/session"): "signing out",
    ("POST", "/join/look"): "a join link, proved by the link itself",
    ("POST", "/join"): "a join link, proved by the link itself",
    ("GET", "/openapi.json"): "the API's own description",
    ("GET", "/{path:path}"): "the web app's files, for any address that isn't the API",
}

# The kitchen: every route under these a token may use, as the admin who made it could (a
# read-only token only reads; household settings are an admin action a token may do).
TOKEN_KITCHEN_PREFIXES = (
    "/recipes",
    "/plan",
    "/pantry",
    "/foods",
    "/shopping",
    "/stock",
    "/stocktake",
    "/batch-cook",
    "/conversions",
    "/meal-slots",
    "/places",
    "/shops",
    "/starter-packs",
    "/units",
    "/today",
    "/changes",
    "/events",
    "/household",
    "/me",
)
# Routes under /me that aren't kitchen routes: they are in SESSION_ONLY (checked first).

NO_DEPENDANTS_OK = {"/openapi.json", "/docs", "/redoc"}


def _all_routes(found: Any) -> Any:
    for route in found:
        if hasattr(route, "effective_candidates"):
            yield from _all_routes(route.effective_candidates())
        elif hasattr(route, "path") and hasattr(route, "methods"):
            yield route
        elif hasattr(route, "routes"):
            yield from _all_routes(route.routes)
        else:
            yield route


def _same(path: str) -> str:
    """A route's path with every {name} as {}: so a listing matches a route exactly, not by
    pattern."""
    return re.sub(r"\{[^}]*\}", "{}", path)


def unlisted_routes(app: Any) -> list[str]:
    """Every route-and-method of the app that is in no list, and every route with no
    dependants to check (other than the API's own description)."""
    never = {(m, _same(p)) for m, p, _ in NEVER_ROUTES}
    session_only = {(m, _same(p.removeprefix(API))) for m, p in SESSION_ONLY}
    may_read = {(m, _same(p)) for m, p in A_TOKEN_MAY_READ}
    no_sign_in = {(m, _same(p)) for m, p in NO_SIGN_IN}
    out = []
    for route in _all_routes(app.routes):
        path = getattr(route, "path", None)
        methods = getattr(route, "methods", None)
        if path is None or methods is None:
            out.append(f"{type(route).__name__} (no path or methods)")
            continue
        short = _same(path.removeprefix(API))
        if not hasattr(route, "dependant") and short not in NO_DEPENDANTS_OK:
            out.append(f"{sorted(methods)} {path} (no dependants)")
            continue
        for method in sorted(methods - {"HEAD"}):
            key = (method, short)
            listed = (
                key in session_only
                or key in may_read
                or key in no_sign_in
                or key in never
                or short.startswith(TOKEN_KITCHEN_PREFIXES)
            )
            if not listed:
                out.append(f"{method} {short}")
    return out


def test_every_route_of_the_app_is_listed(kitchen: TestClient) -> None:
    assert unlisted_routes(kitchen.app) == []


def test_the_token_may_read_routes_are_only_reads_a_token_can_make(kitchen: TestClient) -> None:
    app = _app(kitchen, _make(kitchen, "read"))
    for (method, path), why in A_TOKEN_MAY_READ.items():
        assert method == "GET" and why
        assert app.get(f"{API}{path}").status_code == 200, path


def test_a_new_route_fails_the_walk_until_it_is_listed(kitchen: TestClient) -> None:
    """O2 review r3, finding 4: the reviewer's scratch routes. A route with a new path, a new
    method on a listed path (PUT /people/{person_id}), a path variable in an area the walk
    named only by prefix before (GET /sso/{peek}) and a plain Starlette route are all found."""
    from fastapi import APIRouter
    from starlette.routing import Route

    app = kitchen.app
    extra = APIRouter()
    extra.add_api_route("/sso/secret-peek", lambda: {}, methods=["GET"])
    extra.add_api_route("/sso/{peek}", lambda peek: {}, methods=["GET"])
    extra.add_api_route("/people/{person_id}", lambda person_id: {}, methods=["PUT"])
    app.include_router(extra, prefix=API)  # type: ignore[attr-defined]
    app.router.routes.append(Route("/api/v1/sso/plain", lambda request: None))  # type: ignore[attr-defined]
    found = unlisted_routes(app)
    assert "GET /sso/secret-peek" in found
    assert "GET /sso/{}" in found
    assert "PUT /people/{}" in found
    assert any("/api/v1/sso/plain" in line and "no dependants" in line for line in found), found


def test_a_token_cant_undo_a_people_change_through_the_shopping_actions(
    kitchen: TestClient,
) -> None:
    """O2 review r2, finding 4 (`sync.undo`'s own `by_token` check): a hand-made log row of an
    action that made an admin-only change, undone by `undo {undoes}` through a token, is
    ignored (`cannot_undo`) and nothing is undone."""
    from mealwright.models import Change, SyncAction

    ok(kitchen.post(f"{API}/people", json={"name": "Joss"}), 201)
    with db(kitchen) as session:
        change = session.scalar(select(Change).where(Change.kind == "person_added"))
        assert change is not None
        session.add(
            SyncAction(
                household_id=1,
                id=new_id(),
                seq=10_000,
                kind="add",
                login_name="Tess",
                payload={},
                payload_hash="x",
                status="applied",
                change_id=change.id,
            )
        )
        session.commit()
        target = session.scalar(select(SyncAction.id).where(SyncAction.seq == 10_000))
    app = _app(kitchen, _make(kitchen, "full"))
    answer = send(app, action("undo", undoes=target), login=login_id(kitchen), device=PHONE_A)
    result = answer["results"][0]
    assert (result["status"], result.get("reason")) == ("ignored", "cannot_undo"), result
    names = {p["name"] for p in ok(kitchen.get(f"{API}/people"))["people"]}
    assert "Joss" in names


def test_a_token_is_told_it_cant_check_for_updates(kitchen: TestClient) -> None:
    """O2 review r3, finding 6: `can_check` followed the role, so a token (refused by
    `POST /updates/check`) was told it could."""
    assert ok(kitchen.get(f"{API}/updates"))["can_check"] is True
    for scope in ("read", "full"):
        body = ok(_app(kitchen, _make(kitchen, scope)).get(f"{API}/updates"))
        assert body["can_check"] is False
