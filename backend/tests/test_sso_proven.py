"""Password sign-in goes off only over a setup an Admin has proven (0.9 O1 review r2, finding 1).

"Proven": an Admin passed Test sign-in, or signed in with single sign-on, under the setup as it
is now (issuer, client ID, secret, callback address, where the groups come from, the groups and
"Anyone else"). It is kept in memory only (proposed, for cabledrawer), so after a restart turning
passwords off needs a fresh test. Passwords already off stay off."""

# ruff: noqa: F811

from typing import Any, cast

import pytest
from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from test_sso_api import ADMIN_GROUPS, API, PASSWORD, SETUP, _person, admin, browser, idp, sign_in  # noqa: F401

from mealwright.api.v1.sso import PASSWORDS_NEEDED
from mealwright.models import Login


@pytest.fixture
def linked(admin: TestClient, idp: FakeProvider) -> TestClient:
    """An Admin passed the test and was linked, under the setup as saved. Passwords are on."""
    sign_in(admin, idp, path="/sso/test", sub="k", extra=ADMIN_GROUPS)
    assert admin.post(f"{API}/sso/link").is_success
    return admin


def refused(response: Any) -> None:
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "passwords_needed"
    assert response.json()["detail"] == PASSWORDS_NEEDED


# What each r2 case saved over a setup that had been proven; none of them may be turned off.
BROKEN = {
    "a group that isn't the admins' (mistyped)": {
        "group_roles": [{"group": "mealwright-admin", "role": "admin"}]
    },
    "a wrong secret": {"client_secret": "not-the-secret"},
    "another client ID": {"client_id": "mealwright-2"},
    "another place the groups come from": {"group_claim": "roles"},
    "Anyone else let in": {"anyone_else": "member"},
}


@pytest.mark.parametrize("change", BROKEN.values(), ids=BROKEN.keys())
def test_passwords_cant_go_off_after_a_save_that_nobody_has_tested(
    linked: TestClient, change: dict[str, Any]
) -> None:
    body = {**SETUP, "client_secret": "", **change}
    assert linked.put(f"{API}/sso/settings", json=body).is_success  # passwords on: any save
    refused(linked.put(f"{API}/sso/password-sign-in", json={"on": False}))
    # Nor by the setup form's own Save with the switch off.
    refused(linked.put(f"{API}/sso/settings", json={**body, "password_sign_in": False}))
    assert linked.get(f"{API}/sso/settings").json()["password_sign_in"] is True


def test_a_passed_test_of_the_new_setup_lets_passwords_go_off(
    linked: TestClient, idp: FakeProvider
) -> None:
    body = {**SETUP, "client_secret": "", "anyone_else": "member"}
    assert linked.put(f"{API}/sso/settings", json=body).is_success
    refused(linked.put(f"{API}/sso/password-sign-in", json={"on": False}))
    sign_in(linked, idp, path="/sso/test", sub="k", extra=ADMIN_GROUPS)
    assert linked.put(f"{API}/sso/password-sign-in", json={"on": False}).is_success


def test_a_test_that_didnt_make_an_admin_proves_nothing(
    linked: TestClient, idp: FakeProvider
) -> None:
    changed = {**SETUP, "client_secret": "", "anyone_else": "member"}
    assert linked.put(f"{API}/sso/settings", json=changed).is_success
    sign_in(linked, idp, path="/sso/test", sub="k", extra={"groups": ["mealwright-users"]})
    refused(linked.put(f"{API}/sso/password-sign-in", json={"on": False}))


def test_an_admin_signing_in_with_single_sign_on_proves_the_setup(
    linked: TestClient, idp: FakeProvider
) -> None:
    changed = {**SETUP, "client_secret": "", "anyone_else": "member"}
    assert linked.put(f"{API}/sso/settings", json=changed).is_success
    refused(linked.put(f"{API}/sso/password-sign-in", json={"on": False}))
    answer, _ = sign_in(browser(linked), idp, sub="k", extra=ADMIN_GROUPS)
    assert answer.json()["me"]["role"] == "admin"
    assert linked.put(f"{API}/sso/password-sign-in", json={"on": False}).is_success


def test_after_a_restart_turning_passwords_off_needs_a_fresh_test(
    linked: TestClient, idp: FakeProvider
) -> None:
    app = cast(Any, linked.app)
    app.state.sso_proven.clear()  # what a restart does: nothing is remembered
    refused(linked.put(f"{API}/sso/password-sign-in", json={"on": False}))
    sign_in(linked, idp, path="/sso/test", sub="k", extra=ADMIN_GROUPS)
    assert linked.put(f"{API}/sso/password-sign-in", json={"on": False}).is_success
    # Already off stays off after the next restart.
    app.state.sso_proven.clear()
    assert linked.get(f"{API}/sso/settings").json()["password_sign_in"] is False
    assert browser(linked).post(f"{API}/session", json=PASSWORD).status_code == 403


def test_saving_the_same_setup_again_keeps_what_was_proven(linked: TestClient) -> None:
    assert linked.put(f"{API}/sso/settings", json={**SETUP, "client_secret": ""}).is_success
    assert linked.put(f"{API}/sso/password-sign-in", json={"on": False}).is_success


def test_an_admin_linked_at_another_sign_in_server_is_not_counted_as_able_to_sign_in(
    admin: TestClient,
) -> None:
    """O1 review r2, finding 4: with passwords on, an admin who has only a single sign-on
    identity counts only when it is at the saved sign-in server."""
    with cast(Any, admin.app).state.sessionmaker() as db:
        db.add(
            Login(
                household_id=1,
                username="wren",
                name="Wren",
                password_hash=None,
                role="admin",
                sso_issuer="https://old-id.example.org",
                sso_subject="wren-at-the-old-server",
            )
        )
        db.commit()
    mine = _person(admin, "tess")
    refused = admin.patch(f"{API}/people/{mine}", json={"role": "member"})
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "last_admin"


def test_a_waiting_link_belongs_to_the_session_that_tested(
    admin: TestClient, idp: FakeProvider
) -> None:
    """O1 review r2, finding 5: only the signed-in session that ran the test may confirm it,
    not another session of the same admin, nor the same admin after signing out and in."""
    sign_in(admin, idp, path="/sso/test", sub="k", extra=ADMIN_GROUPS)
    other = browser(admin)
    assert other.post(f"{API}/session", json=PASSWORD).status_code == 200
    assert other.get(f"{API}/sso/settings").json()["test"]["link"] == "no"
    assert other.post(f"{API}/sso/link").status_code == 409
    assert admin.delete(f"{API}/session").status_code == 204
    again = browser(admin)
    assert again.post(f"{API}/session", json=PASSWORD).status_code == 200
    assert again.post(f"{API}/sso/link").status_code == 409
    from test_sso_api import subject_of

    assert subject_of(admin, "tess") is None


def test_with_the_switch_off_passwords_work_whatever_the_setting(
    linked: TestClient, idp: FakeProvider
) -> None:
    """Sweep, O1 review r2 finding 1: the Privacy switch can't leave anyone locked out."""
    assert linked.put(f"{API}/sso/password-sign-in", json={"on": False}).is_success
    assert browser(linked).post(f"{API}/session", json=PASSWORD).status_code == 403
    assert linked.put(f"{API}/privacy/switches/single_sign_on", json={"on": False}).is_success
    assert linked.get(f"{API}/sign-in-options").json()["password"] is True
    assert browser(linked).post(f"{API}/session", json=PASSWORD).status_code == 200
