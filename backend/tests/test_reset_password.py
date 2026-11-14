"""Reset password (0.9.5 Pe1, cabledrawer 13 Nov): an admin makes a one-time link, for 24 hours,
where a person who has forgotten their password chooses a new one; their data stays as it is.
The link's secret follows a `#` like a sign-in link's, and the Person page says when it was
used."""

import io
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import API, db, ok, person
from test_people import _add, _fresh, _id, _join, _look, _newest, _people, _problem

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
    wren = person(kitchen)  # a member
    assert _reset(wren, lorna).status_code == 403
    assert _reset(wren, _id(kitchen, "Wren")).status_code == 403
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
