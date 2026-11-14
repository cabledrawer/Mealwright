"""The automatic link trusts the sign-in server's username only for a login nobody has used
(security pass finding, fix round 1; proposed, for cabledrawer): an exact username match links at
first sign-in only when that login has no password, no link now, never signed in and used no
sign-in link. Any other waits in "Who is this?" for an admin."""

# ruff: noqa: F811, F401
from datetime import UTC, datetime
from typing import Any, cast

from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_sso_api import (
    ADMIN_GROUPS,
    API,
    admin,
    browser,
    fresh_cache,
    idp,
    person_here,
    sign_in,
    subject_of,
    waits,
)
from test_sso_unlink import _admin_linked, _member_id, _unlink

from mealwright.auth import hash_password
from mealwright.models import Login


def _claims(username: str = "lorna") -> dict[str, Any]:
    return {"preferred_username": username}


def _change(client: TestClient, username: str, **fields: Any) -> None:
    with cast(Any, client.app).state.sessionmaker() as db:
        login = db.scalars(select(Login).where(Login.username == username)).one()
        for key, value in fields.items():
            setattr(login, key, value)
        db.commit()


def test_a_login_nobody_has_used_is_linked_automatically(
    admin: TestClient, idp: FakeProvider
) -> None:
    person_here(admin, "lorna")
    answer, _ = sign_in(browser(admin), idp, extra=_claims())
    assert answer.status_code == 200, answer.text
    assert subject_of(admin, "lorna") == "user-1"


def test_a_login_with_a_password_waits_even_on_the_same_username(
    admin: TestClient, idp: FakeProvider
) -> None:
    person_here(admin, "lorna")
    _change(admin, "lorna", password_hash=hash_password("lorna's own password"))
    answer, _ = sign_in(browser(admin), idp, person=False, extra=_claims(" lorna "))
    assert waits(answer)
    assert subject_of(admin, "lorna") is None


def test_a_login_that_signed_in_before_waits(admin: TestClient, idp: FakeProvider) -> None:
    person_here(admin, "lorna")
    _change(admin, "lorna", last_sign_in_at=datetime.now(UTC))
    answer, _ = sign_in(browser(admin), idp, person=False, extra=_claims())
    assert waits(answer)
    assert subject_of(admin, "lorna") is None


def test_a_login_that_used_a_sign_in_link_waits(admin: TestClient, idp: FakeProvider) -> None:
    person_here(admin, "lorna")
    _change(admin, "lorna", link_used_at=datetime.now(UTC))
    answer, _ = sign_in(browser(admin), idp, person=False, extra=_claims())
    assert waits(answer)
    assert subject_of(admin, "lorna") is None


def test_a_login_unlinked_by_an_admin_waits_for_the_next_account_too(
    admin: TestClient, idp: FakeProvider
) -> None:
    person_here(admin, "lorna")
    answer, _ = sign_in(browser(admin), idp, extra=_claims())
    assert answer.status_code == 200, answer.text
    assert _unlink(admin, _member_id(admin, "Lorna")).status_code == 200
    # Another account of the same username: the login has signed in before, so it waits.
    again, _ = sign_in(browser(admin), idp, person=False, sub="stranger-1", extra=_claims())
    assert waits(again)
    assert subject_of(admin, "lorna") is None


def test_the_setup_tests_link_for_the_admin_still_works(
    admin: TestClient, idp: FakeProvider
) -> None:
    """The admin has a password; the setup test and the admin's own confirmation link them."""
    _admin_linked(admin, idp)
    assert subject_of(admin, "tess") == "admin-1"
