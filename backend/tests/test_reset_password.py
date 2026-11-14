"""Reset password (0.9.5 Pe1, cabledrawer 13 Nov): an admin makes a one-time link, for 24 hours,
where a person who has forgotten their password chooses a new one; their data stays as it is.
The link's secret follows a `#` like a sign-in link's, and the Person page says when it was
used."""

import io
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from conftest import ADMIN
from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sync_kit import API, db, ok
from test_people import _add, _fresh, _join, _look, _newest, _people, _problem

from mealwright.api.v1 import people as api_people
from mealwright.history import as_utc
from mealwright.models import ApiToken, JoinLink, Login, Session
from mealwright.reset_admin import reset_admin

FIRST = "lorna's first password"
NEW = "lorna's brand new password"


def _lorna(kitchen: TestClient) -> int:
    """Lorna, a member who has used her sign-in link and signs in with her own password."""
    lorna = _add(kitchen, "Lorna", portion_quarters=3)
    token = _join(kitchen, lorna, "lorna")
    ok(_fresh(kitchen).post(f"{API}/join", json={"token": token, "password": FIRST}))
    return lorna


def _reset(client: TestClient, member_id: int) -> Any:
    return client.post(f"{API}/people/{member_id}/reset-password")


def _token(made: Any) -> str:
    link = ok(made, 201)
    assert link["path"].startswith("/reset#")
    return str(link["path"].removeprefix("/reset#"))


def _login(kitchen: TestClient, member_id: int) -> dict[str, Any]:
    return next(p for p in _people(kitchen)["people"] if p["id"] == member_id)["login"]


def _signs_in(kitchen: TestClient, password: str) -> bool:
    r = _fresh(kitchen).post(f"{API}/session", json={"username": "lorna", "password": password})
    return r.status_code == 200


def test_an_admin_resets_a_password_and_the_person_chooses_a_new_one(kitchen: TestClient) -> None:
    lorna = _lorna(kitchen)
    signed_in = _fresh(kitchen)
    ok(signed_in.post(f"{API}/session", json={"username": "lorna", "password": FIRST}))
    before = next(p for p in _people(kitchen)["people"] if p["id"] == lorna)
    token = _token(_reset(kitchen, lorna))
    assert _login(kitchen, lorna)["reset_pending"] is True
    assert _login(kitchen, lorna)["link_pending"] is False
    note = _newest(kitchen)
    assert note["summary"] == "Made a reset link for Lorna" and note["can_undo"] is False
    # Only the secret's SHA-256 is stored, and the link lasts 24 hours.
    with db(kitchen) as session:
        link = session.scalars(select(JoinLink)).one()
        assert link.kind == "reset" and token not in link.token_hash
        assert link.expires_at - link.created_at == timedelta(hours=24)
    # Until the link is used, the old password still works.
    assert _signs_in(kitchen, FIRST)
    page = ok(_look(_fresh(kitchen), token))
    assert page["kind"] == "reset" and set(page) == {"kind", "expires_at", "min_password"}
    done = _fresh(kitchen).post(f"{API}/join", json={"token": token, "password": NEW})
    assert done.status_code == 200 and done.json() == {"username": "lorna"}, done.text
    with db(kitchen) as session:  # no sign-in of hers is left anywhere
        login = session.scalars(select(Login).where(Login.username == "lorna")).one()
        assert session.scalars(select(Session).where(Session.login_id == login.id)).all() == []
    assert _signs_in(kitchen, NEW) and not _signs_in(kitchen, FIRST)
    # The link works once.
    _problem(_look(_fresh(kitchen), token), 404, "link_gone")
    again = _fresh(kitchen).post(f"{API}/join", json={"token": token, "password": "someone else's"})
    _problem(again, 404, "link_gone")
    # Her data stays as it is.
    after = next(p for p in _people(kitchen)["people"] if p["id"] == lorna)
    assert {k: v for k, v in after.items() if k != "login"} == {
        k: v for k, v in before.items() if k != "login"
    }
    assert after["login"]["username"] == "lorna" and after["login"]["role"] == "member"
    # Whoever was signed in as her is signed out everywhere, like reset-admin (proposed, for
    # cabledrawer): someone who used a link meant for her loses the login when she resets again.
    assert signed_in.get(f"{API}/me").status_code == 401
    # The Person page says when the link was used, and the password's date is the new one.
    used = datetime.fromisoformat(after["login"]["link_used_at"])
    assert timedelta(0) <= datetime.now(UTC) - used < timedelta(minutes=1)
    assert after["login"]["reset_pending"] is False
    with db(kitchen) as session:
        login = session.scalars(select(Login).where(Login.username == "lorna")).one()
        assert login.password_changed_at is not None
        assert as_utc(login.password_changed_at) == used


def test_a_new_reset_link_cancels_the_old_one(kitchen: TestClient) -> None:
    lorna = _lorna(kitchen)
    first = _token(_reset(kitchen, lorna))
    second = _token(_reset(kitchen, lorna))
    _problem(_look(_fresh(kitchen), first), 404, "link_gone")
    ok(_look(_fresh(kitchen), second))
    with db(kitchen) as session:
        assert len(session.scalars(select(JoinLink)).all()) == 1  # the used sign-in link went too


def test_a_reset_link_runs_out_after_24_hours(kitchen: TestClient) -> None:
    token = _token(_reset(kitchen, _lorna(kitchen)))
    with db(kitchen) as session:
        link = session.scalars(select(JoinLink)).one()
        link.expires_at = link.created_at - timedelta(seconds=1)
        session.commit()
    _problem(_look(_fresh(kitchen), token), 404, "link_gone")
    r = _fresh(kitchen).post(f"{API}/join", json={"token": token, "password": NEW})
    _problem(r, 404, "link_gone")
    assert _signs_in(kitchen, FIRST)


def test_only_an_admin_resets_and_never_their_own_password(kitchen: TestClient) -> None:
    lorna = _lorna(kitchen)
    sam = _add(kitchen, "Sam")  # a member, signed in
    joined = {"token": _join(kitchen, sam, "sam"), "password": FIRST}
    ok(_fresh(kitchen).post(f"{API}/join", json=joined))
    sams = _fresh(kitchen)
    ok(sams.post(f"{API}/session", json={"username": "sam", "password": FIRST}))
    assert _reset(sams, lorna).status_code == 403
    assert _reset(sams, sam).status_code == 403
    me = next(p["id"] for p in _people(kitchen)["people"] if p["is_me"])
    detail = _problem(_reset(kitchen, me), 409, "own_password")
    assert detail == "To change your own password, use Settings → Sign-in."
    with db(kitchen) as session:
        assert session.scalars(select(JoinLink).where(JoinLink.kind == "reset")).all() == []


def test_a_reset_needs_a_password_to_reset(kitchen: TestClient) -> None:
    noor = _add(kitchen, "Noor")
    _problem(_reset(kitchen, noor), 409, "no_login")  # profile only
    _join(kitchen, noor, "noor")
    detail = _problem(_reset(kitchen, noor), 409, "no_password")  # hasn't chosen one yet
    assert detail == "Noor hasn’t chosen a password yet. Make a new link instead."
    assert _login(kitchen, noor)["link_pending"] is True  # the sign-in link still works
    sam = _add(kitchen, "Sam")
    _join(kitchen, sam, "sam")
    with db(kitchen) as session:  # Sam signs in only with single sign-on
        login = session.scalars(select(Login).where(Login.username == "sam")).one()
        login.sso_issuer, login.sso_subject = "https://sign-in.example", "sam-1"
        session.commit()
    detail = _problem(_reset(kitchen, sam), 409, "no_password")
    assert detail == "Sam has no password here to reset."
    lorna = _lorna(kitchen)
    ok(kitchen.delete(f"{API}/people/{lorna}"))
    assert _reset(kitchen, lorna).status_code == 404  # removed


def test_a_reset_link_stops_when_its_login_has_no_password_any_more(kitchen: TestClient) -> None:
    token = _token(_reset(kitchen, _lorna(kitchen)))
    with db(kitchen) as session:
        login = session.scalars(select(Login).where(Login.username == "lorna")).one()
        login.password_hash = None
        session.commit()
    _problem(_look(_fresh(kitchen), token), 404, "link_gone")


def test_a_reset_link_opened_where_someone_is_signed_in_is_refused(kitchen: TestClient) -> None:
    """Pe2 (cabledrawer 13 Nov), for Reset password links too: the link stays unused."""
    token = _token(_reset(kitchen, _lorna(kitchen)))
    _problem(_look(kitchen, token), 409, "signed_in_here")
    r = kitchen.post(f"{API}/join", json={"token": token, "password": NEW})
    _problem(r, 409, "signed_in_here")
    assert _signs_in(kitchen, FIRST)
    ok(_look(_fresh(kitchen), token))


def test_a_reset_stops_the_logins_api_tokens(kitchen: TestClient) -> None:
    """An API token is a sign-in too: an admin's tokens stop when their password is reset."""
    noor = _add(kitchen, "Noor")
    token = _join(kitchen, noor, "noor", role="admin")
    ok(_fresh(kitchen).post(f"{API}/join", json={"token": token, "password": FIRST}))
    theirs = _fresh(kitchen)
    ok(theirs.post(f"{API}/session", json={"username": "noor", "password": FIRST}))
    ok(theirs.post(f"{API}/api-tokens", json={"name": "Kitchen display", "scope": "read"}), 201)
    reset = _token(_reset(kitchen, noor))
    ok(_fresh(kitchen).post(f"{API}/join", json={"token": reset, "password": NEW}))
    with db(kitchen) as session:
        tokens = session.scalars(select(ApiToken)).all()
        assert len(tokens) == 1 and tokens[0].revoked_at is not None
    # Someone else's sign-ins stay: the admin who made the link is still signed in.
    assert kitchen.get(f"{API}/me").status_code == 200


def _lorna_signed_in(kitchen: TestClient) -> tuple[int, TestClient]:
    lorna = _lorna(kitchen)
    hers = _fresh(kitchen)
    ok(hers.post(f"{API}/session", json={"username": "lorna", "password": FIRST}))
    return lorna, hers


def test_changing_your_own_password_ends_a_reset_link_made_before(kitchen: TestClient) -> None:
    """16b security pass S-M1 (proposed, for cabledrawer): no link outlives the way back in, even
    when the person keeps their other devices signed in."""
    lorna, hers = _lorna_signed_in(kitchen)
    token = _token(_reset(kitchen, lorna))
    body = {"current_password": FIRST, "new_password": NEW, "sign_out_others": False}
    ok(hers.put(f"{API}/me/password", json=body))
    _problem(_look(_fresh(kitchen), token), 404, "link_gone")
    assert _login(kitchen, lorna)["reset_pending"] is False
    with db(kitchen) as session:
        assert session.scalars(select(JoinLink)).all() == []


def test_signing_out_everywhere_else_ends_a_reset_link(kitchen: TestClient) -> None:
    lorna, hers = _lorna_signed_in(kitchen)
    token = _token(_reset(kitchen, lorna))
    ok(hers.delete(f"{API}/me/sessions/others"))
    _problem(_look(_fresh(kitchen), token), 404, "link_gone")
    assert _signs_in(kitchen, FIRST)


def test_reset_admin_ends_a_reset_link(kitchen: TestClient) -> None:
    noor = _add(kitchen, "Noor")
    joined = _join(kitchen, noor, "noor", role="admin")
    ok(_fresh(kitchen).post(f"{API}/join", json={"token": joined, "password": FIRST}))
    token = _token(_reset(kitchen, noor))
    out = io.StringIO()
    assert reset_admin(kitchen.app.state.settings, "noor", out) == 0  # type: ignore[attr-defined]
    _problem(_look(_fresh(kitchen), token), 404, "link_gone")


def _noor_admin(kitchen: TestClient) -> tuple[int, TestClient]:
    """Noor, a second admin who has chosen her password and is signed in."""
    noor = _add(kitchen, "Noor")
    joined = _join(kitchen, noor, "noor", role="admin")
    ok(_fresh(kitchen).post(f"{API}/join", json={"token": joined, "password": FIRST}))
    hers = _fresh(kitchen)
    ok(hers.post(f"{API}/session", json={"username": "noor", "password": FIRST}))
    return noor, hers


def test_an_admin_made_a_member_leaves_no_reset_link_behind(kitchen: TestClient) -> None:
    """16b security pass S-M1 d (proposed, for cabledrawer): every unused reset link in the
    household goes when an admin stops being one; sign-in links for new people stay."""
    lorna = _lorna(kitchen)
    noor, hers = _noor_admin(kitchen)
    token = _token(_reset(hers, lorna))
    sam = _add(kitchen, "Sam")
    sams = _join(hers, sam, "sam")
    ok(kitchen.patch(f"{API}/people/{noor}", json={"role": "member"}))
    _problem(_look(_fresh(kitchen), token), 404, "link_gone")
    ok(_look(_fresh(kitchen), sams))


def test_an_admin_removed_leaves_no_reset_link_behind(kitchen: TestClient) -> None:
    lorna = _lorna(kitchen)
    noor, hers = _noor_admin(kitchen)
    token = _token(_reset(hers, lorna))
    ok(kitchen.delete(f"{API}/people/{noor}"))
    _problem(_look(_fresh(kitchen), token), 404, "link_gone")
    assert _signs_in(kitchen, FIRST)


def test_a_member_removed_leaves_other_reset_links(kitchen: TestClient) -> None:
    lorna = _lorna(kitchen)
    token = _token(_reset(kitchen, lorna))
    sam = _add(kitchen, "Sam")
    _join(kitchen, sam, "sam")
    ok(kitchen.delete(f"{API}/people/{sam}"))
    ok(_look(_fresh(kitchen), token))


def test_you_can_cancel_a_reset_link_made_for_you(kitchen: TestClient) -> None:
    """16b security pass S-M1 e (proposed, for cabledrawer): your own pending reset link shows on
    your Person page, admin or not, and you can cancel it. Only your own."""
    lorna, hers = _lorna_signed_in(kitchen)
    token = _token(_reset(kitchen, lorna))
    noor = _add(kitchen, "Noor")
    ok(
        _fresh(kitchen).post(
            f"{API}/join", json={"token": _join(kitchen, noor, "noor"), "password": FIRST}
        )
    )
    nours = _token(_reset(kitchen, noor))
    mine = next(p for p in _people(hers)["people"] if p["is_me"])
    assert mine["login"]["reset_pending"] is True
    assert hers.delete(f"{API}/me/reset-link").status_code == 204
    _problem(_look(_fresh(kitchen), token), 404, "link_gone")
    assert _login(kitchen, lorna)["reset_pending"] is False
    assert _signs_in(kitchen, FIRST)  # her password stays as it is
    ok(_look(_fresh(kitchen), nours))  # someone else's link stays
    assert hers.delete(f"{API}/me/reset-link").status_code == 204  # nothing left: fine
    assert _fresh(kitchen).delete(f"{API}/me/reset-link").status_code == 401
    paths = kitchen.get(f"{API}/openapi.json").json()["paths"]
    assert "delete" in paths[f"{API}/me/reset-link"]


@pytest.mark.parametrize("kind", ["reset", "join"])
def test_a_link_cancelled_while_the_password_is_hashed_sets_nothing(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
    """16b security pass S-L2: the link is checked again, in the same write as the password, so
    a link cancelled while the slow hash runs sets no password."""
    if kind == "reset":
        lorna = _lorna(kitchen)
        token = _token(_reset(kitchen, lorna))
    else:
        lorna = _add(kitchen, "Lorna")
        token = _join(kitchen, lorna, "lorna")
    with db(kitchen) as session:
        before = session.scalars(select(Login).where(Login.username == "lorna")).one()
        used_before = before.link_used_at
    real = api_people.hash_password

    def slow_hash(password: str) -> str:
        hashed = real(password)
        with db(kitchen) as session:  # meanwhile, the link is cancelled
            session.execute(delete(JoinLink))
            session.commit()
        return hashed

    monkeypatch.setattr(api_people, "hash_password", slow_hash)
    r = _fresh(kitchen).post(f"{API}/join", json={"token": token, "password": NEW})
    _problem(r, 404, "link_gone")
    assert not _signs_in(kitchen, NEW)
    with db(kitchen) as session:
        login = session.scalars(select(Login).where(Login.username == "lorna")).one()
        assert login.link_used_at == used_before
    if kind == "reset":
        assert _signs_in(kitchen, FIRST)


def test_a_reset_ends_the_logins_live_updates(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """16b security pass S-L3: like removing a person, the signed-out devices' open
    live-update streams end at once."""
    lorna, _hers = _lorna_signed_in(kitchen)
    with db(kitchen) as session:
        login = session.scalars(select(Login).where(Login.username == "lorna")).one()
        theirs = sorted(session.scalars(select(Session.id).where(Session.login_id == login.id)))
    assert theirs
    ended: list[int] = []
    monkeypatch.setattr(kitchen.app.state.events, "end_session", ended.append)  # type: ignore[attr-defined]
    token = _token(_reset(kitchen, lorna))
    ok(_fresh(kitchen).post(f"{API}/join", json={"token": token, "password": NEW}))
    assert sorted(ended) == theirs


def _owner_changes_password(kitchen: TestClient, noor: int) -> None:
    body = {"current_password": ADMIN["password"], "new_password": NEW, "sign_out_others": False}
    ok(kitchen.put(f"{API}/me/password", json=body))


def _owner_runs_reset_admin(kitchen: TestClient, noor: int) -> None:
    settings = kitchen.app.state.settings  # type: ignore[attr-defined]
    assert reset_admin(settings, ADMIN["username"], io.StringIO()) == 0


RECOVERIES = {
    "noor removed": lambda kitchen, noor: ok(kitchen.delete(f"{API}/people/{noor}")),
    "noor made a member": lambda kitchen, noor: ok(
        kitchen.patch(f"{API}/people/{noor}", json={"role": "member"})
    ),
    "password changed": _owner_changes_password,
    "signed out everywhere else": lambda kitchen, noor: ok(
        kitchen.delete(f"{API}/me/sessions/others")
    ),
    "reset-admin": _owner_runs_reset_admin,
}


@pytest.mark.parametrize("recovery", RECOVERIES)
def test_no_admins_sign_in_link_outlives_the_owner_taking_the_household_back(
    kitchen: TestClient, recovery: str
) -> None:
    """16b security re-check S2-M1 (proposed, for cabledrawer): Noor, a hostile admin, adds Sam as
    an admin and keeps his 24-hour sign-in link. Each way the owner takes the household back
    ends it; a Member's sign-in link stays."""
    noor, hers = _noor_admin(kitchen)
    sam = _add(hers, "Sam")
    sams = _join(hers, sam, "sam", role="admin")
    lorna = _add(hers, "Lorna")
    lornas = _join(hers, lorna, "lorna")
    RECOVERIES[recovery](kitchen, noor)
    _problem(_look(_fresh(kitchen), sams), 404, "link_gone")
    ok(_look(_fresh(kitchen), lornas))


@pytest.mark.parametrize("recovery", ["noor removed", "password changed"])
def test_an_admins_sign_in_link_being_hashed_ends_when_the_owner_takes_the_household_back(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch, recovery: str
) -> None:
    """16b security re-check S3-L1 (proposed, for cabledrawer): Noor uses the sign-in link she made
    for Sam, an admin, and the owner takes the household back while the password is still
    being hashed. The claimed link goes too, so the link page is told it's gone (404) and
    nobody signs in as Sam."""
    noor, hers = _noor_admin(kitchen)
    sam = _add(hers, "Sam")
    sams = _join(hers, sam, "sam", role="admin")
    real = api_people.hash_password

    def slow_hash(password: str) -> str:
        hashed = real(password)
        RECOVERIES[recovery](kitchen, noor)  # meanwhile
        return hashed

    monkeypatch.setattr(api_people, "hash_password", slow_hash)
    r = _fresh(kitchen).post(f"{API}/join", json={"token": sams, "password": "Sam's new pass"})
    _problem(r, 404, "link_gone")
    monkeypatch.setattr(api_people, "hash_password", real)
    tried = {"username": "sam", "password": "Sam's new pass"}
    assert _fresh(kitchen).post(f"{API}/session", json=tried).status_code != 200


def test_profile_only_while_the_password_is_hashed_says_the_link_is_gone(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """16b security re-check (a note): an admin chooses "Profile only" for Lorna while her
    sign-in link's password is still being hashed. Her login is gone, so the link page is told
    the link is gone (404), not that something went wrong (500)."""
    lorna = _add(kitchen, "Lorna")
    token = _join(kitchen, lorna, "lorna")
    real = api_people.hash_password

    def slow_hash(password: str) -> str:
        hashed = real(password)
        assert kitchen.delete(f"{API}/people/{lorna}/login").status_code == 204  # meanwhile
        return hashed

    monkeypatch.setattr(api_people, "hash_password", slow_hash)
    fresh = TestClient(kitchen.app, base_url="https://testserver", raise_server_exceptions=False)
    r = fresh.post(f"{API}/join", json={"token": token, "password": NEW})
    _problem(r, 404, "link_gone")
    with db(kitchen) as session:
        assert session.scalars(select(Login).where(Login.username == "lorna")).all() == []
