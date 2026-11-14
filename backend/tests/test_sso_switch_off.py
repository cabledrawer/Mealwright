"""Single sign-on can't be turned off on the last admin who can only get in with it (Tess 14
Nov): "You'd be locked out: first add another admin who signs in with a password." Ways to end
it: the Privacy switch, taking off Your own network the entry that lets Mealwright reach the
sign-in server, and saving another sign-in server or client ID. Only another admin with a working
password counts: a link ends with single sign-on, signed in or not (cabledrawer 14 Nov)."""

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

SENTENCE = "You’d be locked out: first add another admin who signs in with a password."
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


def test_another_admin_signed_in_with_only_a_link_doesnt_count(
    kitchen: TestClient, link_only: FakeProvider
) -> None:
    """Every link ends with single sign-on, so a link-only admin is no way back in (fix round 1:
    "first add another admin who signs in with a password")."""
    _second_admin(kitchen, link_only, signed_in=True)
    refused = _off(kitchen)
    assert refused.status_code == 409, refused.text
    assert refused.json()["detail"] == SENTENCE
    assert _on(kitchen)


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


def test_another_admins_working_password_counts_with_passwords_off_too(
    kitchen: TestClient, link_only: FakeProvider
) -> None:
    """Ending single sign-on turns password sign-in back on, so their password is a way back."""
    person_here(kitchen, "noor", role="admin")
    with cast(Any, kitchen.app).state.sessionmaker() as db:
        noor = db.scalars(select(Login).where(Login.username == "noor")).one()
        noor.password_hash = hash_password("noor's own password")
        db.commit()
    assert kitchen.put(f"{API}/sso/password-sign-in", json={"on": False}).status_code == 200
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


# Saving the setup (fix round 1): another sign-in server or client orphans every link.


def _save(client: TestClient, **change: Any) -> Any:
    from test_sso_api import SETUP

    return client.put(f"{API}/sso/settings", json={**SETUP, **change})


def test_the_last_link_only_admin_cant_save_another_sign_in_server_or_client(
    kitchen: TestClient, link_only: FakeProvider
) -> None:
    for change in ({"client_id": "another-client"}, {"issuer": "https://other.example.org"}):
        refused = _save(kitchen, **change)
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "locked_out"
        assert refused.json()["detail"] == SENTENCE
    saved = kitchen.get(f"{API}/sso/settings").json()
    assert saved["client_id"] != "another-client" and "other.example" not in saved["issuer"]


def test_a_save_that_keeps_the_server_and_client_is_not_refused(
    kitchen: TestClient, link_only: FakeProvider
) -> None:
    assert _save(kitchen, button_name="Our sign-in").status_code == 200
    assert _save(kitchen, client_secret="a new secret").status_code == 200
    groups = [{"group": "everyone", "role": "member"}]
    assert _save(kitchen, group_roles=groups).status_code == 200


def test_saving_another_client_is_allowed_with_a_password(
    kitchen: TestClient, link_only: FakeProvider
) -> None:
    with cast(Any, kitchen.app).state.sessionmaker() as db:
        for login in db.scalars(select(Login)):
            login.password_hash = hash_password("a long enough password")
        db.commit()
    assert _save(kitchen, client_id="another-client").status_code == 200
