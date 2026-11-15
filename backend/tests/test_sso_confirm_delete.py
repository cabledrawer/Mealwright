"""D3 (cabledrawer 13 Nov): an admin who signs in only with single sign-on confirms Delete
everything
with a fresh single sign-on sign-in instead of a password.

"Fresh" is proven so: `POST /sso/confirm` asks the sign-in server for the login again
(`prompt=login`) and to say when it was given (`max_age=0`, so the ID token carries
`auth_time`, OIDC Core 3.1.2.1). The finish counts it only when `auth_time` is after the
confirmation started (a minute's leeway for the clocks), the account is the one linked to this
admin, and the groups still make them an Admin. The proof is kept in memory for this signed-in
session only, for 10 minutes, and used once."""

# ruff: noqa: F811, F401
import dataclasses
import time
from typing import Any, cast
from urllib.parse import parse_qs, urlsplit

import pytest
from conftest import ADMIN
from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from test_sso_api import API, ISSUER, admin, browser, fresh_cache, idp, sign_in

from mealwright.models import Login

ADMINS = {"preferred_username": ADMIN["username"], "groups": ["mealwright-admins"]}
WORDS = {"words": "delete everything"}
ORIGIN = {"Origin": "https://testserver"}


def _link_admin(admin: TestClient, idp: FakeProvider) -> None:
    answer, _ = sign_in(admin, idp, path="/sso/test", sub="admin-1", extra=ADMINS)
    assert answer.status_code == 200, answer.text
    assert admin.post(f"{API}/sso/link").status_code == 200


@pytest.fixture
def sso_only(admin: TestClient, idp: FakeProvider) -> TestClient:
    """The admin is linked, and password sign-in is off: single sign-on is their only way in."""
    _link_admin(admin, idp)
    assert admin.put(f"{API}/sso/password-sign-in", json={"on": False}).status_code == 200
    return admin


def _start(client: TestClient) -> str:
    started = client.post(f"{API}/sso/confirm", headers=ORIGIN)
    assert started.status_code == 200, started.text
    return str(started.json()["url"])


def _confirm(client: TestClient, idp: FakeProvider, sub: str = "admin-1", **extra: Any) -> Any:
    code, state = idp.sign_in(_start(client), sub=sub, extra={**ADMINS, **extra})
    return client.post(f"{API}/sso/finish", json={"state": state, "code": code})


def _how(client: TestClient) -> dict[str, Any]:
    answer = client.get(f"{API}/delete-everything")
    assert answer.status_code == 200, answer.text
    return cast(dict[str, Any], answer.json())


def _logins(client: TestClient) -> int:
    with cast(Any, client.app).state.sessionmaker() as db:
        return int(db.scalar(select(func.count()).select_from(Login)) or 0)


def test_an_admin_with_a_password_confirms_with_it(admin: TestClient, idp: FakeProvider) -> None:
    _link_admin(admin, idp)
    assert _how(admin) == {"confirm_with": "password", "confirmed": False}
    refused = admin.post(f"{API}/sso/confirm", headers=ORIGIN)
    assert refused.status_code == 409
    assert refused.json()["code"] == "use_password"


def test_an_sso_only_admin_confirms_with_a_fresh_sign_in_then_deletes(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    assert _how(sso_only) == {"confirm_with": "single_sign_on", "confirmed": False}
    refused = sso_only.post(f"{API}/delete-everything", json=WORDS)
    assert refused.status_code == 403
    assert refused.json()["code"] == "confirm_first"
    url = _start(sso_only)
    query = parse_qs(urlsplit(url).query)
    assert url.startswith(f"{ISSUER}/authorize?")
    assert query["prompt"] == ["login"] and query["max_age"] == ["0"]
    code, state = idp.sign_in(url, sub="admin-1", extra=ADMINS)
    answer = sso_only.post(f"{API}/sso/finish", json={"state": state, "code": code})
    assert answer.status_code == 200, answer.text
    assert answer.json()["done"] == "confirmed"
    assert _how(sso_only)["confirmed"] is True
    deleted = sso_only.post(f"{API}/delete-everything", json=WORDS)
    assert deleted.status_code == 204, deleted.text
    assert _logins(sso_only) == 0


def test_a_login_with_no_password_confirms_with_sso_even_while_passwords_are_on(
    admin: TestClient, idp: FakeProvider
) -> None:
    _link_admin(admin, idp)
    with cast(Any, admin.app).state.sessionmaker() as db:
        db.scalars(
            select(Login).where(Login.username == ADMIN["username"])
        ).one().password_hash = None
        db.commit()
    assert _how(admin)["confirm_with"] == "single_sign_on"


def test_another_account_at_the_sign_in_server_confirms_nothing(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    answer = _confirm(sso_only, idp, sub="someone-else")
    assert answer.status_code == 400
    assert answer.json()["code"] == "not_you"
    assert _how(sso_only)["confirmed"] is False


@pytest.mark.parametrize("when", ["missing", "an hour ago"])
def test_a_sign_in_the_server_doesnt_say_is_fresh_confirms_nothing(
    sso_only: TestClient, idp: FakeProvider, when: str
) -> None:
    if when == "missing":
        idp.no_auth_time = True
        answer = _confirm(sso_only, idp)
    else:
        answer = _confirm(sso_only, idp, auth_time=int(time.time()) - 3600)
    assert answer.status_code == 400
    assert answer.json()["code"] == "not_fresh"
    assert _how(sso_only)["confirmed"] is False
    assert sso_only.post(f"{API}/delete-everything", json=WORDS).status_code == 403


def test_groups_that_no_longer_make_them_an_admin_confirm_nothing(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    answer = _confirm(sso_only, idp, groups=["mealwright-users"])
    assert answer.status_code == 400
    assert answer.json()["code"] == "not_let_in"
    assert _how(sso_only)["confirmed"] is False


def test_the_proof_is_this_sessions_only_and_wrong_words_dont_use_it_up(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    assert _confirm(sso_only, idp).json()["done"] == "confirmed"
    # The same admin on another device, signed in with single sign-on: not confirmed there.
    phone = browser(sso_only)
    answer, _ = sign_in(phone, idp, person=False, sub="admin-1", extra=ADMINS)
    assert answer.json()["me"]["role"] == "admin"
    assert _how(phone)["confirmed"] is False
    assert phone.post(f"{API}/delete-everything", json=WORDS).status_code == 403
    wrong = sso_only.post(f"{API}/delete-everything", json={"words": "delete"})
    assert wrong.status_code == 422
    assert sso_only.post(f"{API}/delete-everything", json=WORDS).status_code == 204


def test_the_proof_runs_out(sso_only: TestClient, idp: FakeProvider) -> None:
    assert _confirm(sso_only, idp).json()["done"] == "confirmed"
    state = cast(Any, sso_only.app).state
    state.sso_confirmed[1] = dataclasses.replace(state.sso_confirmed[1], expires=time.monotonic())
    assert _how(sso_only)["confirmed"] is False
    assert sso_only.post(f"{API}/delete-everything", json=WORDS).status_code == 403
    assert _logins(sso_only) > 0


def test_a_confirmation_starts_only_by_a_post_from_this_site(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    seen = len(idp.seen)
    followed = sso_only.get(f"{API}/sso/confirm", follow_redirects=False)
    assert followed.status_code in (404, 405)  # there is no such link
    assert "set-cookie" not in followed.headers
    other = sso_only.post(f"{API}/sso/confirm", headers={"Origin": "https://elsewhere.example"})
    assert other.status_code == 403
    assert "set-cookie" not in other.headers
    assert len(idp.seen) == seen  # the sign-in server wasn't asked


def test_a_member_cant_start_one(sso_only: TestClient, idp: FakeProvider) -> None:
    phone = browser(sso_only)
    answer, _ = sign_in(phone, idp, sub="lorna-1", extra={"preferred_username": "lorna"})
    assert answer.json()["me"]["role"] == "member"
    assert phone.post(f"{API}/sso/confirm", headers=ORIGIN).status_code == 403
    assert phone.get(f"{API}/delete-everything").status_code == 403
