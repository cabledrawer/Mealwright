"""API tokens and single sign-on (O2 review r1, finding 3; proposed, for cabledrawer): a token acts as
the admin who made it, and only while they are an admin who is signed in. Single sign-on makes
two ways that end: the groups make the admin a Member at their next sign-in, and the sign-in
server ends their sign-in (the job)."""

# ruff: noqa: F811, F401

import re
from typing import Any, cast

import pytest
from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_sso_api import (
    ADMIN_GROUPS,
    API,
    _add_admin,
    admin,
    browser,
    check,
    fresh_cache,
    idp,
    sign_in,
)

from mealwright.auth import now
from mealwright.models import Session


def a_token_of(client: TestClient) -> TestClient:
    made = ok(
        client.post(f"{API}/api-tokens", json={"name": "Home Assistant", "scope": "full"}), 201
    )
    other = TestClient(client.app, base_url="https://testserver")
    other.headers["Authorization"] = f"Bearer {made['token']}"
    return other


@pytest.fixture
def linked(admin: TestClient, idp: FakeProvider) -> TestClient:
    sign_in(admin, idp, path="/sso/test", sub="k", extra=ADMIN_GROUPS)
    assert admin.post(f"{API}/sso/link").is_success
    return admin


def test_a_token_stops_when_the_groups_make_its_admin_a_member(
    linked: TestClient, idp: FakeProvider
) -> None:
    _add_admin(linked, "wren")  # another admin, so the groups may demote this one
    app = a_token_of(linked)
    assert app.get(f"{API}/me").status_code == 200
    answer, _ = sign_in(browser(linked), idp, sub="k", extra={"groups": ["mealwright-users"]})
    assert answer.json()["me"]["role"] == "member"
    refused = app.get(f"{API}/me")
    assert refused.status_code == 401, refused.text
    assert refused.json()["code"] == "bad_token"
    # For good: made an admin again by the groups, the old token doesn't come back.
    again, _ = sign_in(browser(linked), idp, sub="k", extra=ADMIN_GROUPS)
    assert again.json()["me"]["role"] == "admin"
    assert app.get(f"{API}/me").status_code == 401


def test_a_token_stays_when_the_groups_keep_its_admin_an_admin(
    linked: TestClient, idp: FakeProvider
) -> None:
    app = a_token_of(linked)
    sign_in(browser(linked), idp, sub="k", extra=ADMIN_GROUPS)
    assert app.get(f"{API}/me").status_code == 200


def test_a_token_stops_when_the_sign_in_server_ends_its_admins_sign_in(
    linked: TestClient, idp: FakeProvider
) -> None:
    sign_in(browser(linked), idp, sub="k", extra=ADMIN_GROUPS)
    with cast(Any, linked.app).state.sessionmaker() as db:
        for session in db.scalars(select(Session).where(Session.sso.is_(True))):
            session.sso_check_at = now()  # due
        db.commit()
    app = a_token_of(linked)
    assert app.get(f"{API}/me").status_code == 200
    idp.refresh_tokens.clear()  # signed out at the provider
    assert check(linked) == 1
    refused = app.get(f"{API}/me")
    assert refused.status_code == 401, refused.text
    assert refused.json()["code"] == "bad_token"


def test_a_token_stopped_by_the_sign_in_server_is_logged_by_number_only(
    linked: TestClient, idp: FakeProvider, caplog: pytest.LogCaptureFixture
) -> None:
    sign_in(browser(linked), idp, sub="k", extra=ADMIN_GROUPS)
    with cast(Any, linked.app).state.sessionmaker() as db:
        for session in db.scalars(select(Session).where(Session.sso.is_(True))):
            session.sso_check_at = now()
        db.commit()
    a_token_of(linked)
    idp.refresh_tokens.clear()
    with caplog.at_level("INFO", logger="mealwright.sign_in"):
        assert check(linked) == 1
    said = [r.getMessage() for r in caplog.records if "API tokens stopped" in r.getMessage()]
    assert len(said) == 1 and re.fullmatch(r"Single sign-on: login \d+ signed out.*", said[0])
    assert "tess" not in caplog.text.lower()
