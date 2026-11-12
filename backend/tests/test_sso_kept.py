"""With passwords off, the hourly check never ends the only admin's last sign-in (Tess
12 Nov; proposed, for cabledrawer): its tokens stop, the sign-in stays, Settings warns the admin."""

# ruff: noqa: F811, F401

from typing import Any, cast

import pytest
from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_sso_api import ADMIN_GROUPS, API, PASSWORD, admin, browser, check, idp, sign_in, sso_only
from test_sso_refused import a_token

from mealwright import sso_accounts
from mealwright.auth import now
from mealwright.models import Login, Session


@pytest.fixture(autouse=True)
def no_old_warning() -> None:
    sso_accounts._kept.clear()


def _due(client: TestClient, subject: str) -> None:
    with cast(Any, client.app).state.sessionmaker() as db:
        for session in db.scalars(
            select(Session)
            .join(Login, Login.id == Session.login_id)
            .where(Session.sso.is_(True), Login.sso_subject == subject)
        ):
            session.sso_check_at = now()
        db.commit()


def _warning(client: TestClient) -> str | None:
    return cast("str | None", client.get(f"{API}/sso/settings").json()["kept_warning"])


def test_the_only_admins_last_sign_in_is_kept_with_a_warning_while_passwords_are_off(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """Fails when the check ends that sign-in: nobody could get in but reset-admin."""
    phone = browser(sso_only)
    sign_in(phone, idp, sub="k", extra=ADMIN_GROUPS)
    token = a_token(phone)
    assert token.get(f"{API}/me").status_code == 200
    taken = set(idp.refresh_tokens)
    idp.refresh_tokens.clear()  # the sign-in server no longer accepts them
    _due(sso_only, "k")
    assert check(sso_only) == 0  # none ended
    assert phone.get(f"{API}/me").status_code == 200  # the sign-in stays
    assert token.get(f"{API}/me").status_code == 401  # the tokens stop
    warning = _warning(sso_only)
    assert warning is not None and warning.startswith("The sign-in server no longer accepts ")
    assert "only admin who can get in" in warning
    # A refresh that works again takes the warning away.
    idp.refresh_tokens.update(taken)
    _due(sso_only, "k")
    assert check(sso_only) == 0
    assert _warning(sso_only) is None


def test_the_warning_goes_when_passwords_are_back_on(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    phone = browser(sso_only)
    sign_in(phone, idp, sub="k", extra=ADMIN_GROUPS)
    idp.refresh_tokens.clear()
    _due(sso_only, "k")
    check(sso_only)
    assert _warning(sso_only) is not None
    assert sso_only.put(f"{API}/sso/password-sign-in", json={"on": True}).is_success
    assert _warning(sso_only) is None


def test_with_another_admin_who_can_get_in_the_sign_in_ends_as_before(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    wren = browser(sso_only)
    sign_in(wren, idp, sub="wren", extra=ADMIN_GROUPS)  # a live sign-in: a way in
    phone = browser(sso_only)
    sign_in(phone, idp, sub="k", extra=ADMIN_GROUPS)
    idp.refresh_tokens.clear()
    _due(sso_only, "k")
    assert check(sso_only) == 1
    assert phone.get(f"{API}/me").status_code == 401
    assert _warning(sso_only) is None


def test_a_member_is_never_shown_the_warning(sso_only: TestClient, idp: FakeProvider) -> None:
    """The setup screen's answer is admins only (a Member is refused), so the warning isn't
    theirs to see."""
    member = browser(sso_only)
    sign_in(member, idp, sub="mem", extra={"groups": ["mealwright-users"]})
    assert member.get(f"{API}/sso/settings").status_code == 403
