"""#205 (b) and (d), cabledrawer 12 Nov late: one rule for "another admin can get in" (a password that
works now, or a single sign-on link accepted at the saved sign-in server while single sign-on can
start), and an admin can't make themselves a Member, or a shared login, when no other admin can
get in. A sign-in that is open now, an API token and a link not used yet are no way in."""

# ruff: noqa: F811, F401
from collections.abc import Callable
from datetime import timedelta
from typing import Any, cast

import pytest
from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_sso_api import ADMIN_GROUPS, API, _add_admin, admin, browser, idp, sign_in, sso_only

from mealwright.auth import now
from mealwright.models import Login, Session


def _me(client: TestClient) -> int:
    return int(next(p["id"] for p in client.get(f"{API}/people").json()["people"] if p["is_me"]))


def _live_only(client: TestClient, idp: FakeProvider) -> None:
    """Sam: an admin with no password and no single sign-on link, signed in right now."""
    with cast(Any, client.app).state.sessionmaker() as db:
        login = Login(household_id=1, username="sam", name="Sam", role="admin")
        db.add(login)
        db.flush()
        db.add(
            Session(
                household_id=1,
                login_id=login.id,
                token_hash="a" * 64,
                remember=False,
                expires_at=now() + timedelta(days=1),
            )
        )
        db.commit()


def _password_only(client: TestClient, idp: FakeProvider) -> None:
    _add_admin(client, "sam")


def _linked_only(client: TestClient, idp: FakeProvider) -> None:
    """Sam made an admin by single sign-on, then every sign-in of theirs ends."""
    sign_in(browser(client), idp, sub="sam", extra=ADMIN_GROUPS)
    with cast(Any, client.app).state.sessionmaker() as db:
        for session in db.scalars(select(Session).where(Session.login_id != 1)):
            db.delete(session)
        db.commit()


Make = Callable[[TestClient, FakeProvider], None]
CHANGES = [{"role": "member"}, {"shared": True}]


@pytest.mark.parametrize("change", CHANGES, ids=["member", "shared"])
def test_an_admin_with_only_a_live_sign_in_is_no_way_in(
    admin: TestClient, idp: FakeProvider, change: dict[str, Any]
) -> None:
    _live_only(admin, idp)
    refused = admin.patch(f"{API}/people/{_me(admin)}", json=change)
    assert refused.status_code == 409 and refused.json()["code"] == "last_admin"


@pytest.mark.parametrize("change", CHANGES, ids=["member", "shared"])
def test_an_admin_with_a_working_password_is_a_way_in(
    admin: TestClient, idp: FakeProvider, change: dict[str, Any]
) -> None:
    _password_only(admin, idp)
    assert admin.patch(f"{API}/people/{_me(admin)}", json=change).status_code == 200


@pytest.mark.parametrize("change", CHANGES, ids=["member", "shared"])
def test_an_accepted_single_sign_on_link_is_a_way_in(
    admin: TestClient, idp: FakeProvider, change: dict[str, Any]
) -> None:
    _linked_only(admin, idp)
    assert admin.patch(f"{API}/people/{_me(admin)}", json=change).status_code == 200


@pytest.mark.parametrize("change", CHANGES, ids=["member", "shared"])
def test_a_link_is_no_way_in_while_single_sign_on_is_switched_off(
    admin: TestClient, idp: FakeProvider, change: dict[str, Any]
) -> None:
    _linked_only(admin, idp)
    assert admin.put(f"{API}/privacy/switches/single_sign_on", json={"on": False}).is_success
    refused = admin.patch(f"{API}/people/{_me(admin)}", json=change)
    assert refused.status_code == 409 and refused.json()["code"] == "last_admin"


@pytest.mark.parametrize("change", CHANGES, ids=["member", "shared"])
def test_a_password_is_no_way_in_while_password_sign_in_is_off(
    sso_only: TestClient, idp: FakeProvider, change: dict[str, Any]
) -> None:
    _password_only(sso_only, idp)
    refused = sso_only.patch(f"{API}/people/{_me(sso_only)}", json=change)
    assert refused.status_code == 409 and refused.json()["code"] == "last_admin"


def test_with_passwords_off_a_live_sign_in_is_no_way_in_but_a_link_is(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    _live_only(sso_only, idp)
    refused = sso_only.patch(f"{API}/people/{_me(sso_only)}", json={"role": "member"})
    assert refused.status_code == 409 and refused.json()["code"] == "last_admin"
    _linked_only(sso_only, idp)
    assert (
        sso_only.patch(f"{API}/people/{_me(sso_only)}", json={"role": "member"}).status_code == 200
    )


def test_the_refusal_is_the_same_one_the_other_last_admin_refusals_give(
    admin: TestClient, idp: FakeProvider
) -> None:
    """(b): the words are the existing ones, and nothing changed."""
    _live_only(admin, idp)
    refused = admin.patch(f"{API}/people/{_me(admin)}", json={"role": "member"})
    mine = admin.get(f"{API}/people").json()["people"][0]
    assert refused.json()["detail"] == (
        f"{mine['name']} is the household’s only admin. Make someone else an admin first."
    )
    assert mine["login"]["role"] == "admin"


def test_a_link_the_sign_in_server_refused_is_no_way_in(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """Noor is linked but marked refused (kept signed in after the sign-in server refused her):
    she may be refused again, so she is no way in; once accepted again (the mark ends) she is."""
    sign_in(
        browser(sso_only),
        idp,
        sub="noor",
        extra={**ADMIN_GROUPS, "preferred_username": "noor"},
    )
    with cast(Any, sso_only.app).state.sessionmaker() as db:
        noor = db.scalars(select(Login).where(Login.username == "noor")).one()
        noor.sso_refused_at = now()
        db.commit()
    me = _me(sso_only)
    refused = sso_only.patch(f"{API}/people/{me}", json={"role": "member"})
    assert refused.status_code == 409 and refused.json()["code"] == "last_admin"
    with cast(Any, sso_only.app).state.sessionmaker() as db:
        noor = db.scalars(select(Login).where(Login.username == "noor")).one()
        noor.sso_refused_at = None
        db.commit()
    assert sso_only.patch(f"{API}/people/{me}", json={"role": "member"}).status_code == 200


def test_the_live_only_admin_is_a_way_in_once_given_a_password(
    admin: TestClient, idp: FakeProvider
) -> None:
    """Shows the live-only tests aren't vacuous: Sam is a real admin with a person row, and
    the only thing keeping him from counting is that he has no password."""
    from mealwright.auth import hash_password

    _live_only(admin, idp)
    me = _me(admin)
    assert admin.patch(f"{API}/people/{me}", json={"role": "member"}).status_code == 409
    with cast(Any, admin.app).state.sessionmaker() as db:
        sam = db.scalars(select(Login).where(Login.username == "sam")).one()
        assert sam.member_id is not None and sam.role == "admin"
        sam.password_hash = hash_password("sam's own password")
        db.commit()
    assert admin.patch(f"{API}/people/{me}", json={"role": "member"}).status_code == 200
