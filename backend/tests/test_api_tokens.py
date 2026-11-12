"""API tokens (0.9 O2; spec section 7, cabledrawer 17 Oct): read only or full, with an optional end
date, for scripts and other apps. Only admins make them; a token never does more than the admin
who made it, and never what `SESSION_ONLY` and `roles.TOKENS_NEVER` list."""

import logging
from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sync_kit import API, db, ok, person

from mealwright import api_tokens, roles
from mealwright.auth import COOKIE, current_session
from mealwright.models import ApiToken, Login, Member, utcnow

# Every endpoint a token can never use, whatever it may do otherwise (proposed, for cabledrawer):
# making, listing and deleting tokens, your own password and where you're signed in, and
# "Who's this?" on a shared device.
SESSION_ONLY = {
    ("GET", f"{API}/api-tokens"),
    ("POST", f"{API}/api-tokens"),
    ("DELETE", f"{API}/api-tokens/{{token_id}}"),
    ("GET", f"{API}/me/sign-in"),
    ("PUT", f"{API}/me/password"),
    ("DELETE", f"{API}/me/sessions/others"),
    ("DELETE", f"{API}/me/sessions/{{sign_in_id}}"),
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
    r = app.request(method, path.replace("{token_id}", "1").replace("{sign_in_id}", "1"), json={})
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
    refused = [
        app.post(f"{API}/people", json={"name": "Joss"}),
        app.patch(f"{API}/people/{wren}", json={"role": "admin"}),
        app.delete(f"{API}/people/{wren}"),
        app.post(f"{API}/people/{wren}/login", json={"username": "wren2"}),
        app.delete(f"{API}/people/{wren}/login"),
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


# --- Settings → Your data is never for a token (O2 review r1, finding 1; proposed, for cabledrawer) --

YOUR_DATA_ROUTES = [
    ("GET", "/backups", None),
    ("PATCH", "/backups", {"keep": 3}),
    ("POST", "/backups", None),
    ("GET", "/export", None),
    ("POST", "/delete-everything", {"words": "delete everything", "password": "x"}),
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
                f"{API}/delete-everything",
                json={"words": "delete everything", "password": "not the password"},
            ),
            403,
            "not_for_tokens",
        )
    # The admin's own first wrong try is an ordinary wrong password, not a pause.
    again = kitchen.post(
        f"{API}/delete-everything",
        json={"words": "delete everything", "password": "still not the password"},
    )
    _refused(again, 403, "password_wrong")


def test_the_export_isnt_readable_with_a_read_only_token(kitchen: TestClient) -> None:
    assert kitchen.get(f"{API}/export").status_code == 200  # the admin can
    _refused(_app(kitchen, _make(kitchen, "read")).get(f"{API}/export"), 403, "not_for_tokens")


# --- Every route of a token-never action, so taking an action out of TOKENS_NEVER fails here
# (O2 review r1, finding 4). A full token on each, as an admin's own would be. ----------------

NEVER_ROUTES = [
    # People
    ("POST", "/people", {"name": "Joss"}),
    ("PATCH", "/people/{wren}", {"role": "admin"}),
    ("DELETE", "/people/{wren}", None),
    ("POST", "/people/{wren}/login", {"username": "wren2"}),
    ("DELETE", "/people/{wren}/login", None),
    ("PUT", "/people/ask-whos-this", {"on": True}),
    # Privacy (and the update check, which connects out)
    ("PUT", "/privacy/switches/recipe_import", {"on": True}),
    ("POST", "/privacy/own-network", {"value": "wiki.home"}),
    ("DELETE", "/privacy/own-network/1", None),
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
    ("GET", "/backups", None),
    ("PATCH", "/backups", {"keep": 3}),
    ("POST", "/backups", None),
    ("GET", "/export", None),
    ("POST", "/delete-everything", {"words": "delete everything", "password": "x"}),
]


def _never(app: TestClient, wren: int) -> list[tuple[str, str, Any]]:
    out = []
    for method, path, body in NEVER_ROUTES:
        r = app.request(method, f"{API}{path.replace('{wren}', str(wren))}", json=body)
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
