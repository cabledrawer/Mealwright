"""A sign-in (join) link of a person ends when their login is linked to single sign-on, so it
doesn't work again when an admin unlinks them (0.9.5 Pe3/M2, open point A): "a new link cancels
the old" holds for a link made by hand, an automatic link and a link an admin makes."""

# ruff: noqa: F811, F401
from datetime import timedelta
from typing import Any

from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_sso_api import API, admin, browser, fresh_cache, idp, sign_in
from test_sso_unlink import _member_id, _unlink

from mealwright.models import JoinLink, utcnow


def _lorna_with_a_sign_in_link(admin: TestClient) -> str:
    """Lorna, given a login "lorna" and a sign-in link, which nobody has used."""
    assert admin.post(f"{API}/people", json={"name": "Lorna"}).status_code == 201
    made = admin.post(
        f"{API}/people/{_member_id(admin, 'Lorna')}/login",
        json={"username": "lorna", "role": "member"},
    )
    assert made.status_code == 201, made.text
    return str(made.json()["path"].removeprefix("/join#"))


def _link_works(admin: TestClient, token: str) -> bool:
    other = TestClient(admin.app, base_url="https://testserver")
    answer = other.post(f"{API}/join/look", json={"token": token})
    assert answer.status_code in (200, 404), answer.text
    return answer.status_code == 200


def test_an_automatic_link_ends_the_persons_run_out_sign_in_link(
    admin: TestClient, idp: FakeProvider
) -> None:
    """A live link now keeps the automatic link away (test_sso_auto_link.py); a link that ran
    out doesn't, and the link goes, so Unlink can't bring anything back."""
    token = _lorna_with_a_sign_in_link(admin)
    with admin.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        for link in db.scalars(select(JoinLink)):
            link.expires_at = utcnow() - timedelta(hours=1)
        db.commit()
    assert not _link_works(admin, token)
    answer, _ = sign_in(browser(admin), idp, sub="lorna-1", extra={"preferred_username": "lorna"})
    assert answer.status_code == 200, answer.text
    with admin.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalars(select(JoinLink)).all() == []
    assert _unlink(admin, _member_id(admin, "Lorna")).status_code == 200
    assert not _link_works(admin, token)
    joined = TestClient(admin.app, base_url="https://testserver").post(
        f"{API}/join", json={"token": token, "password": "lorna's own password"}
    )
    assert joined.status_code == 404, joined.text


def test_an_admin_linking_by_hand_ends_the_persons_unused_sign_in_link(
    admin: TestClient, idp: FakeProvider
) -> None:
    token = _lorna_with_a_sign_in_link(admin)
    sign_in(
        browser(admin), idp, person=False, sub="lorna-1", extra={"preferred_username": "lorna.s"}
    )
    account = admin.get(f"{API}/people").json()["waiting"][0]["id"]
    linked = admin.post(
        f"{API}/people/sso-accounts/{account}/link",
        json={"member_id": _member_id(admin, "Lorna")},
    )
    assert linked.status_code == 200, linked.text
    assert not _link_works(admin, token)
    assert _unlink(admin, _member_id(admin, "Lorna")).status_code == 200
    assert not _link_works(admin, token)
