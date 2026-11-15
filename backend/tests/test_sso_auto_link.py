"""The automatic link trusts the sign-in server's username only for a login nobody has used
(security pass finding; cabledrawer 14 Nov): an exact username match links at
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


import pytest  # noqa: E402


@pytest.mark.parametrize(
    "hidden",
    ["lor​na", "lor­na", "﻿lorna", "lor\x00na", "lorna‮", "lor‎na"],
    ids=["zero-width space", "soft hyphen", "BOM", "NUL", "right-to-left", "left-to-right mark"],
)
def test_a_username_with_a_hidden_character_is_not_the_exact_username(
    admin: TestClient, idp: FakeProvider, hidden: str
) -> None:
    """Tidying for display must not widen "exact" (round 2 security pass F2)."""
    person_here(admin, "lorna")
    answer, _ = sign_in(browser(admin), idp, person=False, extra=_claims(hidden))
    assert waits(answer)
    assert subject_of(admin, "lorna") is None


def test_a_login_with_a_live_sign_in_link_waits_and_the_link_still_works(
    admin: TestClient, idp: FakeProvider
) -> None:
    """Someone holds the link: a same-named account must not take the login and kill it (round 2
    security pass F3)."""
    assert admin.post(f"{API}/people", json={"name": "Lorna"}).status_code == 201
    made = admin.post(
        f"{API}/people/{_member_id(admin, 'Lorna')}/login",
        json={"username": "lorna", "role": "member"},
    )
    token = made.json()["path"].removeprefix("/join#")
    answer, _ = sign_in(browser(admin), idp, person=False, extra=_claims())
    assert waits(answer)
    assert subject_of(admin, "lorna") is None
    other = TestClient(admin.app, base_url="https://testserver")
    assert other.post(f"{API}/join/look", json={"token": token}).status_code == 200


def test_a_live_reset_link_counts_too(admin: TestClient, idp: FakeProvider) -> None:
    from datetime import timedelta

    from mealwright.models import JoinLink, utcnow

    person_here(admin, "lorna")
    _change(admin, "lorna", password_hash=hash_password("x" * 12), last_sign_in_at=None)
    with cast(Any, admin.app).state.sessionmaker() as db:
        login = db.scalars(select(Login).where(Login.username == "lorna")).one()
        db.add(
            JoinLink(
                household_id=1,
                login_id=login.id,
                token_hash="r" * 64,
                created_at=utcnow(),
                expires_at=utcnow() + timedelta(hours=5),
                kind="reset",
            )
        )
        login.password_hash = None  # only the live link makes it "in use"
        db.commit()
    answer, _ = sign_in(browser(admin), idp, person=False, extra=_claims())
    assert waits(answer)


def test_an_automatic_link_writes_a_recent_changes_line(
    admin: TestClient, idp: FakeProvider
) -> None:
    person_here(admin, "lorna")
    answer, _ = sign_in(browser(admin), idp, extra=_claims())
    assert answer.status_code == 200, answer.text
    changes = admin.get(f"{API}/changes").json()["changes"]
    assert changes[0]["summary"] == "Linked Lorna to lorna at your sign-in server, automatically"
    assert changes[0]["can_undo"] is False
