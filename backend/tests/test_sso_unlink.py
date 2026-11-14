"""Unlinking a person from single sign-on on their Person page (0.9.5 Pe3/M2): the account then
waits for an admin ("Who is this?") at its next sign-in, the person's single sign-on sign-ins
end, and the household's last admin who can sign in is never unlinked when single sign-on is
their only way in (#205 b/d)."""

# ruff: noqa: F811, F401
from collections.abc import Iterator
from typing import Any, cast

import pytest
from conftest import ADMIN
from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_sso_api import (
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

from mealwright.auth import hash_password
from mealwright.models import Login, Session, SsoAccount

ADMINS = ["mealwright-admins"]


def _member_id(admin: TestClient, name: str) -> int:
    people = admin.get(f"{API}/people").json()["people"]
    return int(next(p["id"] for p in people if p["name"] == name))


def _lorna_signed_in(admin: TestClient, idp: FakeProvider, **extra: Any) -> TestClient:
    """Lorna, a Member here, signs in with single sign-on and is linked automatically (the same
    username): her phone, signed in."""
    phone = browser(admin)
    claims = {"preferred_username": "lorna", **extra}
    answer, _ = sign_in(phone, idp, sub="lorna-1", extra=claims)
    assert answer.status_code == 200, answer.text
    assert answer.json()["me"]["username"] == "lorna"
    return phone


def _admin_linked(admin: TestClient, idp: FakeProvider) -> None:
    """The admin links their own login with the setup test, as on the setup screen."""
    answer, _ = sign_in(
        admin,
        idp,
        path="/sso/test",
        sub="admin-1",
        extra={"preferred_username": ADMIN["username"], "groups": ADMINS},
    )
    assert answer.status_code == 200, answer.text
    assert admin.post(f"{API}/sso/link").status_code == 200


def _unlink(admin: TestClient, member_id: int) -> Any:
    return admin.delete(f"{API}/people/{member_id}/sso")


@pytest.fixture
def member(admin: TestClient) -> Iterator[TestClient]:
    with cast(Any, admin.app).state.sessionmaker() as db:
        db.add(
            Login(
                household_id=1,
                username="noor",
                name="Noor",
                password_hash=hash_password("noor's own password"),
                role="member",
            )
        )
        db.commit()
    with TestClient(admin.app, base_url="https://testserver") as other:
        body = {"username": "noor", "password": "noor's own password"}
        assert other.post(f"{API}/session", json=body).status_code == 200
        yield other


def test_an_unlinked_person_is_signed_out_and_their_account_waits_from_then_on(
    admin: TestClient, idp: FakeProvider
) -> None:
    phone = _lorna_signed_in(admin, idp)
    lorna = _member_id(admin, "Lorna")
    answer = _unlink(admin, lorna)
    assert answer.status_code == 200, answer.text
    person = next(p for p in answer.json()["people"] if p["id"] == lorna)
    assert person["login"]["sso_linked"] is False
    assert person["login"]["sso_username"] is None
    assert subject_of(admin, "lorna") is None
    assert phone.get(f"{API}/me").status_code == 401
    changes = admin.get(f"{API}/changes").json()["changes"]
    assert changes[0]["summary"] == "Unlinked Lorna from lorna at your sign-in server"
    # The same username no longer links it: it waits for an admin.
    again, _ = sign_in(
        browser(admin), idp, person=False, sub="lorna-1", extra={"preferred_username": "lorna"}
    )
    assert waits(again)
    waiting = admin.get(f"{API}/people").json()["waiting"]
    assert [w["username"] for w in waiting] == ["lorna"]
    # An admin links it again by hand, and she gets in.
    link = f"{API}/people/sso-accounts/{waiting[0]['id']}/link"
    assert admin.post(link, json={"member_id": lorna}).status_code == 200
    back, _ = sign_in(
        browser(admin), idp, person=False, sub="lorna-1", extra={"preferred_username": "lorna"}
    )
    assert back.json()["me"]["username"] == "lorna"


def test_a_password_sign_in_of_the_unlinked_person_is_kept(
    admin: TestClient, idp: FakeProvider
) -> None:
    _lorna_signed_in(admin, idp)
    with cast(Any, admin.app).state.sessionmaker() as db:
        login = db.scalars(select(Login).where(Login.username == "lorna")).one()
        login.password_hash = hash_password("lorna's own password")
        db.commit()
    laptop = browser(admin)
    body = {"username": "lorna", "password": "lorna's own password"}
    assert laptop.post(f"{API}/session", json=body).status_code == 200
    assert _unlink(admin, _member_id(admin, "Lorna")).status_code == 200
    assert laptop.get(f"{API}/me").status_code == 200


def test_an_account_linked_before_it_was_kept_is_kept_when_unlinked(
    admin: TestClient, idp: FakeProvider
) -> None:
    """A login linked with no account kept for it (by the setup test, or before 0.9.5)."""
    _admin_linked(admin, idp)
    with cast(Any, admin.app).state.sessionmaker() as db:
        for account in db.scalars(select(SsoAccount)):
            db.delete(account)
        db.commit()
    person_here(admin, "sam", role="admin")
    with cast(Any, admin.app).state.sessionmaker() as db:
        sam = db.scalars(select(Login).where(Login.username == "sam")).one()
        sam.sso_issuer = (
            db.scalars(select(Login).where(Login.username == "tess")).one().sso_issuer
        )
        sam.sso_subject = "sam-1"
        db.commit()
    assert _unlink(admin, _member_id(admin, "Sam")).status_code == 200
    claims = {"preferred_username": "sam", "groups": ADMINS}
    answer, _ = sign_in(browser(admin), idp, person=False, sub="sam-1", extra=claims)
    assert waits(answer)


def test_the_person_page_knows_single_sign_on_is_set_up_for_an_admin_only(
    admin: TestClient, member: TestClient
) -> None:
    assert member.get(f"{API}/people").json()["single_sign_on"] is False
    assert admin.get(f"{API}/people").json()["single_sign_on"] is True


def test_with_no_single_sign_on_set_up_the_person_page_says_nothing_of_it(
    kitchen: TestClient,
) -> None:
    assert kitchen.get(f"{API}/people").json()["single_sign_on"] is False


def test_someone_not_linked_cant_be_unlinked(admin: TestClient, idp: FakeProvider) -> None:
    person_here(admin, "lorna")
    answer = _unlink(admin, _member_id(admin, "Lorna"))
    assert answer.status_code == 409
    assert answer.json()["code"] == "not_linked"


def test_only_an_admin_of_the_household_unlinks(
    admin: TestClient, idp: FakeProvider, member: TestClient, neighbour: TestClient
) -> None:
    _lorna_signed_in(admin, idp)
    lorna = _member_id(admin, "Lorna")
    assert _unlink(member, lorna).status_code == 403
    assert _unlink(neighbour, lorna).status_code == 404
    assert subject_of(admin, "lorna") == "lorna-1"


def test_the_last_admin_who_signs_in_only_with_sso_is_never_unlinked(
    admin: TestClient, idp: FakeProvider
) -> None:
    _admin_linked(admin, idp)
    me = _member_id(admin, ADMIN["name"])
    assert admin.put(f"{API}/sso/password-sign-in", json={"on": False}).status_code == 200
    refused = _unlink(admin, me)
    assert refused.status_code == 409
    assert refused.json()["code"] == "last_admin"
    assert subject_of(admin, ADMIN["username"]) == "admin-1"
    # With passwords on again, their password is a way in: unlinking is fine.
    assert admin.put(f"{API}/sso/password-sign-in", json={"on": True}).status_code == 200
    assert _unlink(admin, me).status_code == 200


def test_a_live_sign_in_of_another_admin_doesnt_count(admin: TestClient, idp: FakeProvider) -> None:
    """#205 d: Sam is signed in as an admin with single sign-on, then unlinked: he no longer
    counts, so the admin who is left can't be unlinked while passwords are off."""
    _admin_linked(admin, idp)
    phone = browser(admin)
    claims = {"preferred_username": "sam", "groups": ADMINS}
    person_here(admin, "sam", role="admin")
    answer, _ = sign_in(phone, idp, person=False, sub="sam-1", extra=claims)
    assert answer.json()["me"]["role"] == "admin"
    assert admin.put(f"{API}/sso/password-sign-in", json={"on": False}).status_code == 200
    # Another admin who can sign in is left (the admin), so Sam can be unlinked.
    assert _unlink(admin, _member_id(admin, "Sam")).status_code == 200
    assert phone.get(f"{API}/me").status_code == 401
    refused = _unlink(admin, _member_id(admin, ADMIN["name"]))
    assert refused.status_code == 409
    assert refused.json()["code"] == "last_admin"


def test_unlinking_ends_the_open_live_update_streams_of_their_sign_ins(
    admin: TestClient, idp: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Like removing a person: a stream open on a deleted sign-in would go on until it times out
    (fix round 1). Fails without the call to `events.end_session`."""
    _lorna_signed_in(admin, idp)
    with cast(Any, admin.app).state.sessionmaker() as db:
        ids = list(db.scalars(select(Session.id).where(Session.sso.is_(True))))
    assert len(ids) == 1
    ended: list[int] = []
    monkeypatch.setattr(cast(Any, admin.app).state.events, "end_session", ended.append)
    assert _unlink(admin, _member_id(admin, "Lorna")).status_code == 200
    assert ended == ids
