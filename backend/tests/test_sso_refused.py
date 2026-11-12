"""A refused known login (O2 review r3, findings 1, 2 and 5): its tokens and sign-ins stop,
except for the household's last admin who can still sign in by password."""

# ruff: noqa: F811

from typing import Any, cast

from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_sso_api import ADMIN_GROUPS, API, admin, browser, idp, sign_in, sso_only  # noqa: F401, F811

from mealwright.models import Session


def a_token(client: TestClient) -> TestClient:
    made = ok(client.post(f"{API}/api-tokens", json={"name": "HA", "scope": "full"}), 201)
    other = TestClient(client.app, base_url="https://testserver")
    other.headers["Authorization"] = f"Bearer {made['token']}"
    return other


def test_the_last_admin_with_a_password_keeps_their_token_while_passwords_work(
    admin: TestClient, idp: FakeProvider
) -> None:
    sign_in(admin, idp, path="/sso/test", sub="k", extra=ADMIN_GROUPS)
    assert admin.post(f"{API}/sso/link").is_success
    token = a_token(admin)
    refused, _ = sign_in(browser(admin), idp, sub="k", extra={"groups": []})
    assert refused.status_code != 200
    assert token.get(f"{API}/me").status_code == 200  # they stay an admin and can still get in
    assert admin.get(f"{API}/me").status_code == 200  # and so does their session


def test_with_passwords_off_the_refused_last_admin_loses_their_token(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """Review r3, finding 1. Fails when the exception ignores the password setting: nobody
    could sign in to delete that token."""
    token = a_token(sso_only)
    refused, _ = sign_in(browser(sso_only), idp, sub="k", extra={"groups": []})
    assert refused.status_code != 200
    assert token.get(f"{API}/me").status_code == 401


def test_a_refused_admin_is_signed_out_everywhere_and_cannot_make_a_new_token(
    admin: TestClient, idp: FakeProvider
) -> None:
    """Review r3, finding 2. Fails without ending the login's sessions in the refusal."""
    wren = browser(admin)
    done, _ = sign_in(wren, idp, sub="wren", extra=ADMIN_GROUPS)
    assert done.json()["me"]["role"] == "admin"
    token = a_token(wren)
    refused, _ = sign_in(browser(admin), idp, sub="wren", extra={"groups": []})
    assert refused.status_code != 200
    assert token.get(f"{API}/me").status_code == 401
    assert wren.get(f"{API}/me").status_code == 401
    assert wren.post(f"{API}/api-tokens", json={"name": "HA2", "scope": "full"}).status_code == 401
    with cast(Any, admin.app).state.sessionmaker() as db:
        assert db.scalars(select(Session).where(Session.sso.is_(True))).all() == []
