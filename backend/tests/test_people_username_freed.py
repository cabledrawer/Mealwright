"""A removed person's username is free again once the 7-day Undo has passed (0.9.5 Pe8, cabledrawer
13 Nov), for a new person and for single sign-on. The old login stays removed, with its number,
its data and its link: nobody takes it over."""

# ruff: noqa: F811, F401
from datetime import timedelta
from typing import Any, cast

from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
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

from mealwright import jobs, people
from mealwright.models import Login, Member, utcnow


def _member(client: TestClient, name: str) -> int:
    return next(p["id"] for p in ok(client.get(f"{API}/people"))["people"] if p["name"] == name)


def _removed_ago(client: TestClient, member_id: int, days: float) -> None:
    with cast(Any, client.app).state.sessionmaker() as db:
        member = db.get(Member, member_id)
        assert member is not None
        member.removed_at = utcnow() - timedelta(days=days)
        db.commit()


def _login_row(client: TestClient, member_id: int) -> Login:
    with cast(Any, client.app).state.sessionmaker() as db:
        login = db.scalars(select(Login).where(Login.member_id == member_id)).one()
        db.expunge(login)
        return login


def _new_person_with_login(client: TestClient, name: str, username: str) -> Any:
    ok(client.post(f"{API}/people", json={"name": name}), 201)
    return client.post(
        f"{API}/people/{_member(client, name)}/login", json={"username": username, "role": "member"}
    )


def _lorna_removed(client: TestClient) -> int:
    assert _new_person_with_login(client, "Lorna", "lorna").status_code == 201
    lorna = _member(client, "Lorna")
    ok(client.delete(f"{API}/people/{lorna}"))
    return lorna


def test_the_username_stays_taken_during_the_undo_and_is_free_after_it(admin: TestClient) -> None:
    lorna = _lorna_removed(admin)
    before = _login_row(admin, lorna)
    assert _new_person_with_login(admin, "Noor", "lorna").status_code == 409
    _removed_ago(admin, lorna, 6.9)  # the Undo is still there
    assert _new_person_with_login(admin, "Sam", "lorna").status_code == 409
    _removed_ago(admin, lorna, 7.1)  # the Undo has passed
    assert _new_person_with_login(admin, "Lorna", "lorna").status_code == 201
    old = _login_row(admin, lorna)
    assert old.id == before.id and old.username != "lorna"  # same login number, name let go
    with cast(Any, admin.app).state.sessionmaker() as db:
        assert db.get(Member, lorna).removed_at is not None  # type: ignore[union-attr]
        new = db.scalars(select(Login).where(Login.username == "lorna")).one()
        assert new.id != old.id and new.member_id != lorna  # never reused


def test_the_hourly_job_lets_go_of_the_name_too(admin: TestClient) -> None:
    lorna = _lorna_removed(admin)
    _removed_ago(admin, lorna, 8)
    jobs.purge_removed_ingredients(cast(Any, admin.app).state.sessionmaker)
    assert _login_row(admin, lorna).username != "lorna"
    # The name stays one nobody can type, so it can never be taken by mistake.
    assert "~" in _login_row(admin, lorna).username


def test_a_person_brought_back_by_undo_keeps_their_username(admin: TestClient) -> None:
    assert _new_person_with_login(admin, "Lorna", "lorna").status_code == 201
    lorna = _member(admin, "Lorna")
    removed = ok(admin.delete(f"{API}/people/{lorna}"))
    assert _new_person_with_login(admin, "Noor", "lorna").status_code == 409
    ok(admin.post(f"{API}/changes/{removed['change']['id']}/undo"))
    assert _login_row(admin, lorna).username == "lorna"


def test_undo_is_refused_once_the_username_was_let_go(admin: TestClient) -> None:
    assert _new_person_with_login(admin, "Lorna", "lorna").status_code == 201
    lorna = _member(admin, "Lorna")
    removed = ok(admin.delete(f"{API}/people/{lorna}"))
    with cast(Any, admin.app).state.sessionmaker() as db:  # the hourly job ran, the Undo is still listed
        assert people.free_old_usernames(db, utcnow() + timedelta(days=30)) == 1
        db.commit()
    answer = admin.post(f"{API}/changes/{removed['change']['id']}/undo")
    assert answer.status_code == 409 and answer.json()["code"] == "cannot_undo"
    assert _new_person_with_login(admin, "Noor", "lorna").status_code == 201
    with cast(Any, admin.app).state.sessionmaker() as db:
        assert db.get(Member, lorna).removed_at is not None  # type: ignore[union-attr]


def test_single_sign_on_cannot_take_over_a_removed_login_even_after_the_window(
    admin: TestClient, idp: FakeProvider
) -> None:
    person_here(admin, "lorna")
    answer, _ = sign_in(browser(admin), idp, extra={"preferred_username": "lorna"})
    assert answer.status_code == 200, answer.text
    lorna = _member(admin, "Lorna")
    ok(admin.delete(f"{API}/people/{lorna}"))
    _removed_ago(admin, lorna, 8)
    # Another account of that username: nothing to take over, it waits for an admin.
    other, _ = sign_in(
        browser(admin), idp, person=False, sub="stranger-1", extra={"preferred_username": "lorna"}
    )
    assert waits(other)
    old = _login_row(admin, lorna)
    assert old.sso_subject == "user-1"  # the old link stays on the old login
    # Her own account is still refused: the old login stays removed.
    again, _ = sign_in(browser(admin), idp, person=False, extra={"preferred_username": "lorna"})
    assert again.status_code != 200 or again.json().get("me") is None


def test_a_new_person_from_a_waiting_account_gets_the_freed_username(
    admin: TestClient, idp: FakeProvider
) -> None:
    lorna = _lorna_removed(admin)
    other, _ = sign_in(
        browser(admin), idp, person=False, sub="newcomer-1", extra={"preferred_username": "lorna"}
    )
    assert waits(other)
    waiting = admin.get(f"{API}/people").json()["waiting"]
    made = admin.post(
        f"{API}/people/sso-accounts/{waiting[0]['id']}/link", json={"member_id": None}
    )
    assert made.status_code == 200, made.text
    with cast(Any, admin.app).state.sessionmaker() as db:
        names = set(db.scalars(select(Login.username).where(Login.household_id == 1)))
    assert "lorna-2" in names  # during the Undo: the removed login still holds "lorna"
    _removed_ago(admin, lorna, 8)
    third, _ = sign_in(
        browser(admin), idp, person=False, sub="newcomer-2", extra={"preferred_username": "lorna"}
    )
    assert waits(third)
    waiting = admin.get(f"{API}/people").json()["waiting"]
    made = admin.post(
        f"{API}/people/sso-accounts/{waiting[0]['id']}/link", json={"member_id": None}
    )
    assert made.status_code == 200, made.text
    with cast(Any, admin.app).state.sessionmaker() as db:
        names = set(db.scalars(select(Login.username).where(Login.household_id == 1)))
    with cast(Any, admin.app).state.sessionmaker() as db:
        here = db.scalars(
            select(Login.username)
            .join(Member, Member.id == Login.member_id)
            .where(Login.username == "lorna", Member.removed_at.is_(None))
        ).all()
    assert here == ["lorna"]  # a person who is here now holds "lorna"


def test_the_edge_is_an_hour_after_the_seven_days(admin: TestClient) -> None:
    """Undo stays open a moment past 7 days (the change's own time); the name waits an hour more,
    as the ingredient purge does."""
    lorna = _lorna_removed(admin)
    _removed_ago(admin, lorna, 7.01)  # 7 days and 15 minutes: still inside the margin
    assert _new_person_with_login(admin, "Sam", "lorna").status_code == 409
    _removed_ago(admin, lorna, 7.05)  # 7 days and 72 minutes
    assert _new_person_with_login(admin, "Noor", "lorna").status_code == 201


def test_another_households_expired_name_does_not_block_this_one(
    admin: TestClient, neighbour: TestClient
) -> None:
    """Usernames are unique across households: an expired name there is freed by a call here."""
    with cast(Any, admin.app).state.sessionmaker() as db:
        other = db.scalars(select(Login).where(Login.household_id != 1)).first()
        assert other is not None
        member = db.get(Member, other.member_id)
        assert member is not None
        member.removed_at = utcnow() - timedelta(days=9)
        name = other.username
        db.commit()
    assert _new_person_with_login(admin, "Noor", name).status_code == 201
