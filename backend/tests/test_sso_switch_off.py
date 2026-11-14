"""Single sign-on can't be turned off on the last admin who can only get in with it (Tess 14
Nov): "You'd be locked out: set a password or add another admin first." Both ways to end it:
the Privacy switch, and taking off Your own network the entry that lets Mealwright reach the
sign-in server. Another admin counts only by the household's rule: a working password, or an
accepted single sign-on link and signed in right now (#205 (c)+(d))."""

# ruff: noqa: F401
from typing import Any, cast

import pytest
from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_sso_api import ADMIN_GROUPS, API, browser, person_here, sign_in
from test_sso_passwords_off_class import entry_id, fresh_cache, home

from mealwright import sso_accounts
from mealwright.auth import hash_password
from mealwright.models import Login

SENTENCE = "You’d be locked out: set a password or add another admin first."
SWITCH = f"{API}/privacy/switches/single_sign_on"


@pytest.fixture
def link_only(kitchen: TestClient, monkeypatch: pytest.MonkeyPatch) -> FakeProvider:
    """Single sign-on on, the signed-in admin linked, and their password taken away: their one
    way in is the link."""
    idp = home(kitchen, monkeypatch, "192.168.1.50", off=False)
    with cast(Any, kitchen.app).state.sessionmaker() as db:
        for login in db.scalars(select(Login)):
            login.password_hash = None
        db.commit()
    return idp


def _on(client: TestClient) -> bool:
    switches = client.get(f"{API}/privacy/switches").json()["switches"]
    return bool(next(s["on"] for s in switches if s["connection"] == "single_sign_on"))


def _off(client: TestClient) -> Any:
    return client.put(SWITCH, json={"on": False})


def _second_admin(client: TestClient, idp: FakeProvider, *, signed_in: bool) -> TestClient:
    """Lorna, a second admin who signs in with single sign-on only (linked at her first
    sign-in); with `signed_in` her phone stays signed in, else she signs out."""
    person_here(client, "lorna", role="admin")
    phone = browser(client)
    answer, _ = sign_in(
        phone, idp, sub="lorna-1", extra={"preferred_username": "lorna", **ADMIN_GROUPS}
    )
    assert answer.status_code == 200, answer.text
    if not signed_in:
        assert phone.delete(f"{API}/session").status_code in (200, 204)
    return phone


def test_the_last_admin_with_only_a_link_cant_turn_single_sign_on_off(
    kitchen: TestClient, link_only: FakeProvider
) -> None:
    refused = _off(kitchen)
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "locked_out"
    assert refused.json()["detail"] == SENTENCE
    assert _on(kitchen)


def test_removing_the_entry_that_lets_it_reach_the_sign_in_server_is_refused_too(
    kitchen: TestClient, link_only: FakeProvider
) -> None:
    refused = kitchen.delete(f"{API}/privacy/own-network/{entry_id(kitchen)}")
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == SENTENCE
    assert len(kitchen.get(f"{API}/privacy/own-network").json()["entries"]) == 1


def test_an_admin_with_a_password_may_turn_it_off(
    kitchen: TestClient, link_only: FakeProvider
) -> None:
    with cast(Any, kitchen.app).state.sessionmaker() as db:
        for login in db.scalars(select(Login)):
            login.password_hash = hash_password("a long enough password")
        db.commit()
    assert _off(kitchen).status_code == 200
    assert not _on(kitchen)


def test_another_admin_signed_in_with_an_accepted_link_lets_it_be_turned_off(
    kitchen: TestClient, link_only: FakeProvider
) -> None:
    _second_admin(kitchen, link_only, signed_in=True)
    assert _off(kitchen).status_code == 200
    assert not _on(kitchen)


def test_another_admin_linked_but_signed_out_doesnt_count(
    kitchen: TestClient, link_only: FakeProvider
) -> None:
    _second_admin(kitchen, link_only, signed_in=False)
    assert _off(kitchen).status_code == 409
    assert _on(kitchen)


def test_another_admin_with_a_working_password_lets_it_be_turned_off(
    kitchen: TestClient, link_only: FakeProvider
) -> None:
    person_here(kitchen, "noor", role="admin")
    with cast(Any, kitchen.app).state.sessionmaker() as db:
        noor = db.scalars(select(Login).where(Login.username == "noor")).one()
        noor.password_hash = hash_password("noor's own password")
        db.commit()
    assert _off(kitchen).status_code == 200


def test_another_household_cant_make_it_pass(
    kitchen: TestClient, link_only: FakeProvider, neighbour: TestClient
) -> None:
    """The next-door household's admin has a password, and is no way in for this household."""
    assert _off(kitchen).status_code == 409
    assert _on(kitchen)


def test_nothing_is_refused_when_it_is_off_already_or_the_asker_isnt_linked(
    kitchen: TestClient, link_only: FakeProvider
) -> None:
    with cast(Any, kitchen.app).state.sessionmaker() as db:
        for login in db.scalars(select(Login)):
            login.sso_subject = None  # not linked: single sign-on was never their way in
        db.commit()
    assert _off(kitchen).status_code == 200
    assert _off(kitchen).status_code == 200  # again: no change, no refusal
