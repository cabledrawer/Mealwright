""" "Who is this?" (0.9.5 Pe3/M2, cabledrawer 13 Nov): a single sign-on sign-in that matches nobody
waits, with no session, until an admin of its household links it to a person, makes a new
person for it, or refuses it."""

# ruff: noqa: F811, F401
from collections.abc import Iterator
from typing import Any, cast

import pytest
from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_sso_api import API, admin, browser, idp, logins, person_here, sign_in, subject_of, waits

from mealwright.auth import hash_password
from mealwright.models import Login, Member, SsoAccount, utcnow
from mealwright.sso_accounts import MOST_WAITING


def _wait(admin: TestClient, idp: FakeProvider, sub: str = "lorna-1", **extra: Any) -> int:
    """Lorna signs in with single sign-on, matches nobody and waits: her waiting sign-in's id."""
    claims = {"preferred_username": "lorna.s", "name": "Lorna S", **extra}
    answer, _ = sign_in(browser(admin), idp, person=False, sub=sub, extra=claims)
    assert waits(answer)
    assert answer.json()["username"] == claims["preferred_username"]
    waiting = admin.get(f"{API}/people").json()["waiting"]
    return int(next(w["id"] for w in waiting if w["username"] == claims["preferred_username"]))


def _member_id(admin: TestClient, name: str) -> int:
    people = admin.get(f"{API}/people").json()["people"]
    return int(next(p["id"] for p in people if p["name"] == name))


def _profile(admin: TestClient, name: str) -> int:
    """A person with no login ("Profile only")."""
    with cast(Any, admin.app).state.sessionmaker() as db:
        member = Member(household_id=1, name=name)
        db.add(member)
        db.commit()
        return int(member.id)


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


def test_a_waiting_sign_in_is_listed_for_an_admin_only(
    admin: TestClient, idp: FakeProvider, member: TestClient
) -> None:
    account = _wait(admin, idp)
    waiting = admin.get(f"{API}/people").json()["waiting"]
    assert [(w["id"], w["username"], w["role"]) for w in waiting] == [
        (account, "lorna.s", "member")
    ]
    assert member.get(f"{API}/people").json()["waiting"] == []
    noor = _member_id(admin, "Noor")
    link = f"{API}/people/sso-accounts/{account}/link"
    assert member.post(link, json={"member_id": noor}).status_code == 403
    assert member.post(f"{API}/people/sso-accounts/{account}/refuse").status_code == 403
    assert len(admin.get(f"{API}/people").json()["waiting"]) == 1


def test_signing_in_again_while_waiting_waits_again_and_is_listed_once(
    admin: TestClient, idp: FakeProvider
) -> None:
    first = _wait(admin, idp)
    again = _wait(admin, idp)
    assert first == again
    assert len(admin.get(f"{API}/people").json()["waiting"]) == 1


def test_another_households_admin_never_sees_or_links_it(
    admin: TestClient, idp: FakeProvider, neighbour: TestClient
) -> None:
    account = _wait(admin, idp)
    assert neighbour.get(f"{API}/people").json()["waiting"] == []
    theirs = neighbour.get(f"{API}/people").json()["people"][0]["id"]
    link = f"{API}/people/sso-accounts/{account}/link"
    assert neighbour.post(link, json={"member_id": theirs}).status_code == 404
    assert neighbour.post(link, json={"member_id": None}).status_code == 404
    assert neighbour.post(f"{API}/people/sso-accounts/{account}/refuse").status_code == 404
    assert len(admin.get(f"{API}/people").json()["waiting"]) == 1


def test_it_cant_be_linked_to_another_households_person(
    admin: TestClient, idp: FakeProvider, neighbour: TestClient
) -> None:
    """The body's member_id (test_security_isolation's case for SsoLinkIn): a person of another
    household is "not found", and nothing changes."""
    account = _wait(admin, idp)
    theirs = neighbour.get(f"{API}/people").json()["people"][0]["id"]
    link = f"{API}/people/sso-accounts/{account}/link"
    answer = admin.post(link, json={"member_id": theirs})
    assert answer.status_code == 404, answer.text
    assert answer.json()["code"] == "not_found"
    assert len(admin.get(f"{API}/people").json()["waiting"]) == 1
    person = neighbour.get(f"{API}/people").json()["people"][0]
    assert person["id"] == theirs and not (person["login"] or {}).get("sso_linked")


def test_linked_to_a_person_with_a_login_they_get_in_on_the_next_sign_in(
    admin: TestClient, idp: FakeProvider
) -> None:
    person_here(admin, "lorna")
    account = _wait(admin, idp)
    lorna = _member_id(admin, "Lorna")
    answer = admin.post(f"{API}/people/sso-accounts/{account}/link", json={"member_id": lorna})
    assert answer.status_code == 200, answer.text
    assert answer.json()["waiting"] == []
    person = next(p for p in answer.json()["people"] if p["id"] == lorna)
    assert person["login"]["sso_linked"] is True
    assert person["login"]["sso_username"] == "lorna.s"
    assert subject_of(admin, "lorna") == "lorna-1"
    again, _ = sign_in(
        browser(admin), idp, person=False, sub="lorna-1", extra={"preferred_username": "lorna.s"}
    )
    assert again.status_code == 200, again.text
    assert again.json()["me"]["username"] == "lorna"
    # Recent changes says so, with no Undo of its own.
    changes = admin.get(f"{API}/changes").json()["changes"]
    assert changes[0]["summary"] == "Linked Lorna to lorna.s at your sign-in server"


def test_linked_to_a_person_with_no_login_makes_them_one_with_the_groups_role(
    admin: TestClient, idp: FakeProvider
) -> None:
    lorna = _profile(admin, "Lorna")
    account = _wait(admin, idp, groups=["mealwright-admins"])
    answer = admin.post(f"{API}/people/sso-accounts/{account}/link", json={"member_id": lorna})
    assert answer.status_code == 200, answer.text
    person = next(p for p in answer.json()["people"] if p["id"] == lorna)
    assert person["login"]["username"] == "lorna.s"
    assert person["login"]["role"] == "admin"
    assert person["login"]["has_password"] is False
    assert logins(admin) == {"lorna.s": "admin"}


def test_a_new_person_is_named_as_the_sign_in_server_names_them(
    admin: TestClient, idp: FakeProvider
) -> None:
    person_here(admin, "lorna.s")  # the username is taken: the new login's gets a number
    with cast(Any, admin.app).state.sessionmaker() as db:
        db.scalars(select(Login).where(Login.username == "lorna.s")).one().shared = True
        db.commit()
    account = _wait(admin, idp)
    answer = admin.post(f"{API}/people/sso-accounts/{account}/link", json={"member_id": None})
    assert answer.status_code == 200, answer.text
    added = next(p for p in answer.json()["people"] if p["name"] == "Lorna S")
    assert added["login"]["username"] == "lorna.s-2"
    assert added["login"]["role"] == "member"
    assert added["login"]["sso_linked"] is True
    changes = admin.get(f"{API}/changes").json()["changes"]
    assert changes[0]["summary"] == "Added Lorna S, linked to lorna.s at your sign-in server"


def test_a_username_mealwright_doesnt_allow_gets_one_made_for_it(
    admin: TestClient, idp: FakeProvider
) -> None:
    account = _wait(admin, idp, preferred_username="Lorna Stone")
    answer = admin.post(f"{API}/people/sso-accounts/{account}/link", json={"member_id": None})
    assert answer.status_code == 200, answer.text
    with cast(Any, admin.app).state.sessionmaker() as db:
        made = db.scalars(select(Login).where(Login.sso_subject == "lorna-1")).one()
        assert made.username.startswith("sso-")
        assert made.password_hash is None


def test_a_refused_sign_in_is_refused_until_an_admin_links_it_after_all(
    admin: TestClient, idp: FakeProvider
) -> None:
    account = _wait(admin, idp)
    refused = admin.post(f"{API}/people/sso-accounts/{account}/refuse")
    assert refused.status_code == 200, refused.text
    assert refused.json()["waiting"] == []
    assert admin.get(f"{API}/changes").json()["changes"][0]["summary"] == (
        "Refused lorna.s at your sign-in server"
    )
    claims = {"preferred_username": "lorna.s"}
    answer, _ = sign_in(browser(admin), idp, person=False, sub="lorna-1", extra=claims)
    assert answer.status_code == 400
    assert answer.json()["code"] == "not_known"
    assert "mealwright_session" not in answer.headers.get("set-cookie", "")
    # Not listed again, even with the person of that username added now: refused is final
    # until an admin changes it.
    person_here(admin, "lorna.s")
    answer, _ = sign_in(browser(admin), idp, person=False, sub="lorna-1", extra=claims)
    assert answer.json()["code"] == "not_known"
    assert admin.get(f"{API}/people").json()["waiting"] == []
    assert subject_of(admin, "lorna.s") is None
    # The admin links it after all.
    lorna = _member_id(admin, "Lorna.s")
    linked = admin.post(f"{API}/people/sso-accounts/{account}/link", json={"member_id": lorna})
    assert linked.status_code == 200, linked.text
    answer, _ = sign_in(browser(admin), idp, person=False, sub="lorna-1", extra=claims)
    assert answer.status_code == 200, answer.text
    assert answer.json()["me"]["username"] == "lorna.s"


def test_a_shared_login_or_one_linked_already_cant_be_linked(
    admin: TestClient, idp: FakeProvider
) -> None:
    person_here(admin, "tablet")
    person_here(admin, "noor")
    with cast(Any, admin.app).state.sessionmaker() as db:
        db.scalars(select(Login).where(Login.username == "tablet")).one().shared = True
        db.commit()
    noor_answer, _ = sign_in(
        browser(admin), idp, person=False, sub="noor-1", extra={"preferred_username": "noor"}
    )
    assert noor_answer.status_code == 200, noor_answer.text
    account = _wait(admin, idp)
    link = f"{API}/people/sso-accounts/{account}/link"
    shared = admin.post(link, json={"member_id": _member_id(admin, "Tablet")})
    assert shared.status_code == 409
    assert shared.json()["code"] == "shared_login"
    taken = admin.post(link, json={"member_id": _member_id(admin, "Noor")})
    assert taken.status_code == 409
    assert taken.json()["code"] == "linked_already"
    assert subject_of(admin, "noor") == "noor-1"
    assert len(admin.get(f"{API}/people").json()["waiting"]) == 1


def test_an_admin_is_linked_only_to_an_account_the_groups_make_an_admin(
    admin: TestClient, idp: FakeProvider
) -> None:
    account = _wait(admin, idp)  # the groups make it a Member
    me = next(p for p in admin.get(f"{API}/people").json()["people"] if p["is_me"])
    answer = admin.post(f"{API}/people/sso-accounts/{account}/link", json={"member_id": me["id"]})
    assert answer.status_code == 409
    assert answer.json()["code"] == "needs_admin"
    assert subject_of(admin, me["login"]["username"]) is None


def test_a_linked_account_cant_be_linked_or_refused_again(
    admin: TestClient, idp: FakeProvider
) -> None:
    account = _wait(admin, idp)
    link = f"{API}/people/sso-accounts/{account}/link"
    assert admin.post(link, json={"member_id": None}).status_code == 200
    assert admin.post(link, json={"member_id": None}).status_code == 404
    assert admin.post(f"{API}/people/sso-accounts/{account}/refuse").status_code == 404


def test_only_the_newest_sign_ins_wait(admin: TestClient, idp: FakeProvider) -> None:
    for n in range(MOST_WAITING + 2):
        answer, _ = sign_in(
            browser(admin), idp, person=False, sub=f"s{n}", extra={"preferred_username": f"p{n}"}
        )
        assert waits(answer)
    waiting = admin.get(f"{API}/people").json()["waiting"]
    assert len(waiting) == MOST_WAITING
    assert waiting[0]["username"] == f"p{MOST_WAITING + 1}"
    assert "p0" not in {w["username"] for w in waiting}


def test_an_earlier_sign_in_servers_sign_ins_are_never_listed(
    admin: TestClient, idp: FakeProvider
) -> None:
    account = _wait(admin, idp)
    with cast(Any, admin.app).state.sessionmaker() as db:
        db.get(SsoAccount, account).issuer = "https://earlier.example"
        db.commit()
    assert admin.get(f"{API}/people").json()["waiting"] == []
    link = f"{API}/people/sso-accounts/{account}/link"
    assert admin.post(link, json={"member_id": None}).status_code == 404


def test_linking_by_hand_leaves_the_refusal_mark_alone(
    admin: TestClient, idp: FakeProvider
) -> None:
    """The mark ends only when the sign-in server accepts them as an Admin again, or an admin
    makes them a Member or removes them (spec section 7), not by being linked by hand."""
    person_here(admin, "lorna")
    with cast(Any, admin.app).state.sessionmaker() as db:
        login = db.scalars(select(Login).where(Login.username == "lorna")).one()
        login.sso_refused_at = utcnow()
        db.commit()
    account = _wait(admin, idp)
    linked = admin.post(
        f"{API}/people/sso-accounts/{account}/link", json={"member_id": _member_id(admin, "Lorna")}
    )
    assert linked.status_code == 200, linked.text
    with cast(Any, admin.app).state.sessionmaker() as db:
        login = db.scalars(select(Login).where(Login.username == "lorna")).one()
        assert login.sso_subject == "lorna-1" and login.sso_refused_at is not None
