"""Settings → Household (0.9 A1): the people of the household, their logins and roles, the
one-time sign-in link, removing with Undo, and "Who's this?" on a shared login."""

import threading
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import API, db, ok, person

from mealwright import people
from mealwright.api.v1.context import Kitchen
from mealwright.history import as_utc
from mealwright.models import Household, JoinLink, Login, Member, Session, utcnow


def _people(client: TestClient) -> dict[str, Any]:
    return ok(client.get(f"{API}/people"))


def _id(client: TestClient, name: str) -> int:
    return next(p["id"] for p in _people(client)["people"] if p["name"] == name)


def _newest(client: TestClient) -> dict[str, Any]:
    return ok(client.get(f"{API}/changes"))["changes"][0]


def _undo(client: TestClient, change: dict[str, Any], status: int = 200) -> Any:
    r = client.post(f"{API}/changes/{change['id']}/undo")
    assert r.status_code == status, r.text
    return r.json()


def _add(client: TestClient, name: str = "Joss", **extra: Any) -> int:
    ok(client.post(f"{API}/people", json={"name": name, **extra}), 201)
    return _id(client, name)


def _join(client: TestClient, member_id: int, username: str, role: str = "member") -> str:
    link = ok(
        client.post(f"{API}/people/{member_id}/login", json={"username": username, "role": role}),
        201,
    )
    assert link["path"].startswith("/join#")
    return str(link["path"].removeprefix("/join#"))


def _look(client: TestClient, token: str) -> Any:
    """What the link page asks before the password is chosen (the secret in the body)."""
    return client.post(f"{API}/join/look", json={"token": token})


def _fresh(kitchen: TestClient) -> TestClient:
    return TestClient(kitchen.app, base_url="https://testserver")


def _problem(r: Any, status: int, code: str) -> str:
    assert r.status_code == status, r.text
    assert r.json()["code"] == code
    return str(r.json()["detail"])


# --- Listing ---------------------------------------------------------------------------------


def test_everyone_sees_the_people_and_only_an_admin_can_change_them(kitchen: TestClient) -> None:
    wren = person(kitchen)
    mine = _people(kitchen)
    assert mine["can_change"] is True and mine["ask_whos_this"] is False
    me, other = mine["people"]
    assert me["name"] == "Tess" and me["is_me"] is True
    assert me["login"] == {
        "username": "tess",
        "role": "admin",
        "shared": False,
        "has_password": True,
        "signs_in": True,
        "link_pending": False,
        "link_used_at": None,
        "reset_pending": False,
    }
    assert me["portion_quarters"] == 4
    assert other["name"] == "Wren" and other["is_me"] is False
    theirs = _people(wren)
    assert theirs["can_change"] is False
    assert [p["id"] for p in theirs["people"]] == [me["id"], other["id"]]
    assert ok(wren.get(f"{API}/me"))["member_id"] == other["id"]


def test_a_neighbours_people_are_never_listed_or_changed(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    joss = _add(kitchen)
    assert [p["name"] for p in _people(neighbour)["people"]] == ["Neighbour"]
    for r in (
        neighbour.patch(f"{API}/people/{joss}", json={"portion_quarters": 2}),
        neighbour.delete(f"{API}/people/{joss}"),
        neighbour.post(f"{API}/people/{joss}/login", json={"username": "joss"}),
    ):
        _problem(r, 404, "not_found")
    assert _people(kitchen)["people"][1]["portion_quarters"] == 4


# --- Adding and changing -------------------------------------------------------------------------


def test_adding_a_person_without_a_login_and_undo(kitchen: TestClient) -> None:
    joss = _add(kitchen, colour="amber", portion_quarters=2)
    added = next(p for p in _people(kitchen)["people"] if p["id"] == joss)
    assert added["login"] is None and added["colour"] == "amber"
    assert added["portion_quarters"] == 2 and added["created_by_name"] == "Tess"
    change = _newest(kitchen)
    assert change["summary"] == "Added Joss to the household" and change["can_undo"]
    # Joss now eats: she's offered in who's eating.
    assert "Joss" in [p["name"] for p in ok(kitchen.get(f"{API}/plan/people"))]
    _undo(kitchen, change)
    assert [p["name"] for p in _people(kitchen)["people"]] == ["Tess"]


def test_each_change_answers_with_its_change_and_a_retry_changes_nothing_more(
    kitchen: TestClient,
) -> None:
    key = {"Idempotency-Key": "4b1c1f0e-0a51-4d1e-9a8e-6f7e3a0d5c21"}
    first = kitchen.post(f"{API}/people", json={"name": "Joss"}, headers=key)
    assert first.status_code == 201, first.text
    change = first.json()["change"]
    assert change["summary"] == "Added Joss to the household" and change["can_undo"]
    again = kitchen.post(f"{API}/people", json={"name": "Joss"}, headers=key)
    assert again.status_code == 201 and again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["change"]["id"] == change["id"]
    assert [p["name"] for p in again.json()["people"]] == ["Tess", "Joss"]
    joss = _id(kitchen, "Joss")
    changed = ok(kitchen.patch(f"{API}/people/{joss}", json={"portion_quarters": 2}))
    assert changed["change"]["kind"] == "person_changed"
    same = ok(kitchen.patch(f"{API}/people/{joss}", json={"portion_quarters": 2}))
    assert same["change"] is None  # nothing changed
    assert ok(kitchen.delete(f"{API}/people/{joss}"))["change"]["kind"] == "person_removed"
    switched = ok(kitchen.put(f"{API}/people/ask-whos-this", json={"on": True}))
    assert switched["change"]["kind"] == "whos_this_switch" and switched["ask_whos_this"]
    assert ok(kitchen.get(f"{API}/people"))["change"] is None


def test_names_must_differ_and_portions_are_quarter_to_two(kitchen: TestClient) -> None:
    _add(kitchen)
    _problem(kitchen.post(f"{API}/people", json={"name": " joss "}), 409, "name_taken")
    assert (
        kitchen.post(f"{API}/people", json={"name": "Ben", "portion_quarters": 0}).status_code
        == 422
    )
    assert (
        kitchen.post(f"{API}/people", json={"name": "Ben", "portion_quarters": 9}).status_code
        == 422
    )
    assert kitchen.post(f"{API}/people", json={"name": "   "}).status_code == 422
    assert kitchen.post(f"{API}/people", json={"name": "Ben", "colour": "pink"}).status_code == 422


def test_changing_a_person_and_undo(kitchen: TestClient) -> None:
    joss = _add(kitchen, colour="amber")
    ok(kitchen.patch(f"{API}/people/{joss}", json={"portion_quarters": 2, "name": "Joss B"}))
    change = _newest(kitchen)
    assert change["summary"] == "Changed Joss B: renamed from Joss, ½ portion (was 1 portion)"
    ok(kitchen.patch(f"{API}/people/{joss}", json={"colour": None}))
    shown = next(p for p in _people(kitchen)["people"] if p["id"] == joss)
    assert shown["colour"] is None and shown["name"] == "Joss B"
    # The colour has changed since, but not what this change changed: it can be undone.
    _undo(kitchen, change)
    shown = next(p for p in _people(kitchen)["people"] if p["id"] == joss)
    assert (shown["name"], shown["portion_quarters"], shown["colour"]) == ("Joss", 4, None)


def test_undo_is_refused_when_the_person_was_changed_again(kitchen: TestClient) -> None:
    joss = _add(kitchen)
    ok(kitchen.patch(f"{API}/people/{joss}", json={"portion_quarters": 2}))
    first = _newest(kitchen)
    ok(kitchen.patch(f"{API}/people/{joss}", json={"portion_quarters": 6}))
    r = kitchen.post(f"{API}/changes/{first['id']}/undo")
    assert "changed again" in _problem(r, 409, "cannot_undo")


def test_a_change_that_changes_nothing_records_nothing(kitchen: TestClient) -> None:
    joss = _add(kitchen)
    before = _newest(kitchen)["id"]
    ok(kitchen.patch(f"{API}/people/{joss}", json={"portion_quarters": 4, "name": "Joss"}))
    assert _newest(kitchen)["id"] == before


def test_renaming_a_person_renames_their_login(kitchen: TestClient) -> None:
    person(kitchen)
    wren = _id(kitchen, "Wren")
    ok(kitchen.patch(f"{API}/people/{wren}", json={"name": "Ram"}))
    with db(kitchen) as session:
        assert session.scalar(select(Login.name).where(Login.username == "wren")) == "Ram"


def test_role_and_shared_need_a_login(kitchen: TestClient) -> None:
    joss = _add(kitchen)
    _problem(kitchen.patch(f"{API}/people/{joss}", json={"role": "admin"}), 409, "no_login")
    _problem(kitchen.patch(f"{API}/people/{joss}", json={"shared": True}), 409, "no_login")


# --- Roles and the last admin --------------------------------------------------------------------


def test_the_only_admin_cant_be_made_a_member_until_there_is_another(kitchen: TestClient) -> None:
    wren_client = person(kitchen)
    me, wren = _people(kitchen)["people"][0]["id"], _id(kitchen, "Wren")
    detail = _problem(
        kitchen.patch(f"{API}/people/{me}", json={"role": "member"}), 409, "last_admin"
    )
    assert detail == "Tess is the household’s only admin. Make someone else an admin first."
    ok(kitchen.patch(f"{API}/people/{wren}", json={"role": "admin"}))
    promoted = _newest(kitchen)
    assert promoted["summary"] == "Changed Wren: an admin now"
    assert _people(wren_client)["can_change"] is True
    ok(kitchen.patch(f"{API}/people/{me}", json={"role": "member"}))
    assert _people(kitchen)["can_change"] is False
    # Undoing Wren's promotion would leave no admin: refused, nothing changed.
    r = wren_client.post(f"{API}/changes/{promoted['id']}/undo")
    assert "only admin" in _problem(r, 409, "cannot_undo")


def _pending_admin(kitchen: TestClient, name: str = "Joss") -> int:
    """A person made an admin whose sign-in link isn't used yet: they can't sign in."""
    member_id = _add(kitchen, name)
    _join(kitchen, member_id, name.lower(), role="admin")
    return member_id


def test_only_admins_who_can_sign_in_count(kitchen: TestClient) -> None:
    """Review r1: an admin with no password yet, or removed, is no admin anyone can use."""
    _pending_admin(kitchen)
    person(kitchen)
    wren = _id(kitchen, "Wren")
    ok(kitchen.patch(f"{API}/people/{wren}", json={"role": "admin"}))
    ok(kitchen.delete(f"{API}/people/{wren}"))
    with db(kitchen) as session:
        me = session.scalars(select(Login).where(Login.username == "tess")).one()
        household = session.get(Household, me.household_id)
        assert household is not None
        here = Kitchen(db=session, login=me, household=household, idempotency_key=None, request="")
        assert people.admins_left(here) == 1
        assert people.admins_left(here, me.member_id) == 0


def test_an_admin_cant_step_down_when_the_other_admin_cant_sign_in_yet(
    kitchen: TestClient,
) -> None:
    _pending_admin(kitchen)
    me = _id(kitchen, "Tess")
    _problem(kitchen.patch(f"{API}/people/{me}", json={"role": "member"}), 409, "last_admin")
    assert _people(kitchen)["can_change"] is True


def test_undo_of_a_promotion_is_refused_when_the_other_admin_cant_sign_in_yet(
    kitchen: TestClient,
) -> None:
    wren_client = person(kitchen)
    me, wren = _id(kitchen, "Tess"), _id(kitchen, "Wren")
    ok(kitchen.patch(f"{API}/people/{wren}", json={"role": "admin"}))
    promoted = _newest(kitchen)
    _pending_admin(kitchen)
    ok(wren_client.patch(f"{API}/people/{me}", json={"role": "member"}))
    r = wren_client.post(f"{API}/changes/{promoted['id']}/undo")
    assert "only admin" in _problem(r, 409, "cannot_undo")
    assert _people(wren_client)["can_change"] is True


def test_removing_an_admin_counts_only_admins_who_can_sign_in(kitchen: TestClient) -> None:
    """Whoever removes is an admin who signs in, so removing another admin always leaves one;
    a pending admin is never needed for that."""
    person(kitchen)
    wren = _id(kitchen, "Wren")
    ok(kitchen.patch(f"{API}/people/{wren}", json={"role": "admin"}))
    joss = _pending_admin(kitchen)
    ok(kitchen.delete(f"{API}/people/{wren}"))
    ok(kitchen.delete(f"{API}/people/{joss}"))
    assert [p["name"] for p in _people(kitchen)["people"]] == ["Tess"]


def test_a_pending_admins_new_link_can_make_them_a_member(kitchen: TestClient) -> None:
    joss = _pending_admin(kitchen)
    _join(kitchen, joss, "joss", role="member")
    with db(kitchen) as session:
        assert session.scalars(select(Login.role).where(Login.username == "joss")).one() == (
            "member"
        )


def test_an_admin_cant_remove_themselves(kitchen: TestClient) -> None:
    me = _people(kitchen)["people"][0]["id"]
    detail = _problem(kitchen.delete(f"{API}/people/{me}"), 409, "remove_yourself")
    assert detail == "You can’t remove yourself. Ask another admin."


# --- Removing ------------------------------------------------------------------------------------


def test_removing_a_person_keeps_their_history_and_ends_their_sign_in(kitchen: TestClient) -> None:
    wren_client = person(kitchen)
    wren = _id(kitchen, "Wren")
    ok(wren_client.patch(f"{API}/household", json={"cook_per_step": True}))
    theirs = _newest(kitchen)
    assert theirs["who"]["name"] == "Wren" and theirs["who"]["member_id"] == wren
    ok(kitchen.delete(f"{API}/people/{wren}"))
    removed = _newest(kitchen)
    assert removed["summary"] == "Removed Wren from the household" and removed["can_undo"]
    assert [p["name"] for p in _people(kitchen)["people"]] == ["Tess"]
    assert "Wren" not in [p["name"] for p in ok(kitchen.get(f"{API}/plan/people"))]
    # Their change stays, under "Wren (removed)".
    shown = next(c for c in ok(kitchen.get(f"{API}/changes"))["changes"] if c["id"] == theirs["id"])
    assert shown["who"]["name"] == "Wren (removed)"
    # Signed out everywhere, and can't sign in again: told only what anyone is told.
    assert wren_client.get(f"{API}/me").status_code == 401
    again = _fresh(kitchen).post(
        f"{API}/session", json={"username": "wren", "password": "wren's long password"}
    )
    assert again.status_code == 401 and again.json()["detail"] == (
        "That username and password don’t match."
    )
    # Undo brings them back, and they can sign in again.
    _undo(kitchen, removed)
    assert "Wren" in [p["name"] for p in _people(kitchen)["people"]]
    back = _fresh(kitchen).post(
        f"{API}/session", json={"username": "wren", "password": "wren's long password"}
    )
    assert back.status_code == 200, back.text
    shown = next(c for c in ok(kitchen.get(f"{API}/changes"))["changes"] if c["id"] == theirs["id"])
    assert shown["who"]["name"] == "Wren"


def test_a_removed_persons_right_password_counts_like_a_wrong_one(kitchen: TestClient) -> None:
    """Signing in as a removed person is counted towards the username's pause, so their old
    password can't be tried for free (0.9 A1 with A2's counted checks)."""
    person(kitchen)
    ok(kitchen.delete(f"{API}/people/{_id(kitchen, 'Wren')}"))
    stranger = _fresh(kitchen)
    wren = {"username": "wren", "password": "wren's long password"}
    for _ in range(5):
        assert stranger.post(f"{API}/session", json=wren).status_code == 401
    _problem(stranger.post(f"{API}/session", json=wren), 429, "username_paused")


def test_removing_an_admin_while_another_stays(kitchen: TestClient) -> None:
    person(kitchen)
    wren = _id(kitchen, "Wren")
    ok(kitchen.patch(f"{API}/people/{wren}", json={"role": "admin"}))
    ok(kitchen.delete(f"{API}/people/{wren}"))
    _problem(kitchen.delete(f"{API}/people/{wren}"), 404, "not_found")
    _problem(kitchen.patch(f"{API}/people/{wren}", json={"name": "R"}), 404, "not_found")


def test_undo_of_a_removal_is_refused_when_someone_else_has_the_name(kitchen: TestClient) -> None:
    joss = _add(kitchen)
    ok(kitchen.delete(f"{API}/people/{joss}"))
    removed = _newest(kitchen)
    _add(kitchen)  # a new Joss
    r = kitchen.post(f"{API}/changes/{removed['id']}/undo")
    assert "someone else called Joss" in _problem(r, 409, "cannot_undo")


def test_a_removed_persons_meals_and_tubs_keep_them(kitchen: TestClient) -> None:
    joss = _add(kitchen)
    with db(kitchen) as session:
        member = session.get(Member, joss)
        assert member is not None and member.removed_at is None
    ok(kitchen.delete(f"{API}/people/{joss}"))
    with db(kitchen) as session:
        member = session.get(Member, joss)
        assert member is not None and member.removed_at is not None  # kept, only marked


def test_an_admin_renames_the_household_and_can_undo_it(kitchen: TestClient) -> None:
    before = ok(kitchen.get(f"{API}/household"))["name"]
    renamed = ok(kitchen.patch(f"{API}/household", json={"name": "  Our   kitchen "}))
    assert renamed["name"] == "Our kitchen"
    change = _newest(kitchen)
    assert change["summary"] == f"Renamed the household to Our kitchen (was {before})"
    assert change["kind"] == "household_renamed"
    blank = kitchen.patch(f"{API}/household", json={"name": "   "})
    assert blank.status_code == 422
    _undo(kitchen, change)
    assert ok(kitchen.get(f"{API}/household"))["name"] == before
    # Renamed again since: that Undo is refused.
    ok(kitchen.patch(f"{API}/household", json={"name": "One"}))
    first = _newest(kitchen)
    ok(kitchen.patch(f"{API}/household", json={"name": "Two"}))
    _problem(kitchen.post(f"{API}/changes/{first['id']}/undo"), 409, "cannot_undo")


# --- The sign-in link ---------------------------------------------------------------------------


def test_give_a_login_join_with_the_link_and_sign_in(kitchen: TestClient) -> None:
    joss = _add(kitchen)
    token = _join(kitchen, joss, " Joss ")
    shown = next(p for p in _people(kitchen)["people"] if p["id"] == joss)
    assert shown["login"] == {
        "username": "joss",
        "role": "member",
        "shared": False,
        "has_password": False,
        "signs_in": False,
        "link_pending": True,
        "link_used_at": None,
        "reset_pending": False,
    }
    note = _newest(kitchen)
    assert note["summary"] == "Made a sign-in link for Joss" and note["can_undo"] is False
    # Only the token's SHA-256 is stored.
    with db(kitchen) as session:
        stored = session.scalars(select(JoinLink.token_hash)).all()
        assert token not in stored and len(stored) == 1 and len(stored[0]) == 64
    # Nobody can sign in as Joss before she picks a password.
    blank = _fresh(kitchen).post(f"{API}/session", json={"username": "joss", "password": ""})
    assert blank.status_code == 401
    joss_client = _fresh(kitchen)
    page = ok(_look(joss_client, token))
    # Nobody is named before the password is set (cabledrawer 13 Nov).
    assert set(page) == {"kind", "expires_at", "min_password"} and page["min_password"] == 12
    assert page["kind"] == "join"
    short = joss_client.post(f"{API}/join", json={"token": token, "password": "eleven char"})
    assert short.status_code == 422
    joined = joss_client.post(
        f"{API}/join", json={"token": token, "password": "joss's own password"}
    )
    # Only now is the username given, to sign in with.
    assert joined.status_code == 200 and joined.json() == {"username": "joss"}, joined.text
    # Joining sets the password only: she signs in on the sign-in page like anyone else.
    assert joss_client.get(f"{API}/me").status_code == 401
    # The link works once.
    _problem(_look(_fresh(kitchen), token), 404, "link_gone")
    again = _fresh(kitchen).post(
        f"{API}/join", json={"token": token, "password": "someone else's pw"}
    )
    _problem(again, 404, "link_gone")
    # She signs in with her own password from now on; a second link is refused.
    signed = _fresh(kitchen).post(
        f"{API}/session", json={"username": "joss", "password": "joss's own password"}
    )
    assert signed.status_code == 200
    assert signed.json()["member_id"] == joss and signed.json()["role"] == "member"
    r = kitchen.post(f"{API}/people/{joss}/login", json={"username": "joss"})
    _problem(r, 409, "signs_in_already")
    after = next(p for p in _people(kitchen)["people"] if p["id"] == joss)["login"]
    assert after["has_password"] is True and after["link_pending"] is False
    # The Person page says when the link was used (cabledrawer 13 Nov), so an admin can spot a link
    # someone else used.
    used = datetime.fromisoformat(after["link_used_at"])
    assert timedelta(0) <= datetime.now(UTC) - used < timedelta(minutes=1)


def test_a_link_works_once_even_for_requests_at_the_same_time(kitchen: TestClient) -> None:
    """Review r1: four joins at once: exactly one sets its password, the rest are told the link
    is gone, and the one that was told yes is the password that works."""
    token = _join(kitchen, _add(kitchen), "joss")
    results: dict[int, int] = {}
    start = threading.Barrier(4)

    def join(i: int) -> None:
        client = _fresh(kitchen)
        start.wait()
        r = client.post(f"{API}/join", json={"token": token, "password": f"password number {i}!!"})
        results[i] = r.status_code

    threads = [threading.Thread(target=join, args=(i,)) for i in range(4)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results.values()) == [200, 404, 404, 404]
    winner = next(i for i, code in results.items() if code == 200)
    for i in range(4):
        r = _fresh(kitchen).post(
            f"{API}/session", json={"username": "joss", "password": f"password number {i}!!"}
        )
        assert r.status_code == (200 if i == winner else 401), (i, winner)


def test_a_link_works_again_when_the_password_couldnt_be_set(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    token = _join(kitchen, _add(kitchen), "joss")

    def broken(password: str) -> str:
        raise RuntimeError("hash failed")

    monkeypatch.setattr("mealwright.api.v1.people.hash_password", broken)
    with pytest.raises(RuntimeError):
        _fresh(kitchen).post(f"{API}/join", json={"token": token, "password": "a long password!!"})
    monkeypatch.undo()
    assert all(
        p["login"] is None or p["login"]["link_used_at"] is None for p in _people(kitchen)["people"]
    )
    assert ok(_look(_fresh(kitchen), token))["min_password"] == 12
    r = _fresh(kitchen).post(f"{API}/join", json={"token": token, "password": "a long password!!"})
    assert r.status_code == 200, r.text


def test_a_link_runs_out_after_24_hours(kitchen: TestClient) -> None:
    joss = _add(kitchen)
    token = _join(kitchen, joss, "joss")
    with db(kitchen) as session:
        link = session.scalars(select(JoinLink)).one()
        assert link.expires_at - link.created_at == timedelta(hours=24)
        link.expires_at = link.created_at - timedelta(seconds=1)
        session.commit()
    detail = _problem(_look(_fresh(kitchen), token), 404, "link_gone")
    assert detail.startswith("This sign-in link has been used or has run out.")


def test_a_new_link_replaces_the_old_one_and_profile_only_takes_it_back(
    kitchen: TestClient,
) -> None:
    joss = _add(kitchen)
    first = _join(kitchen, joss, "joss")
    second = _join(kitchen, joss, "joss2", role="admin")
    _problem(_look(_fresh(kitchen), first), 404, "link_gone")
    ok(_look(_fresh(kitchen), second))
    ok_status = kitchen.delete(f"{API}/people/{joss}/login")
    assert ok_status.status_code == 204
    _problem(_look(_fresh(kitchen), second), 404, "link_gone")
    assert next(p for p in _people(kitchen)["people"] if p["id"] == joss)["login"] is None


def test_profile_only_is_refused_for_someone_who_signs_in(kitchen: TestClient) -> None:
    person(kitchen)
    r = kitchen.delete(f"{API}/people/{_id(kitchen, 'Wren')}/login")
    _problem(r, 409, "signs_in_already")


def test_usernames_are_unique_and_checked(kitchen: TestClient) -> None:
    joss = _add(kitchen)
    r = kitchen.post(f"{API}/people/{joss}/login", json={"username": "tess"})
    _problem(r, 409, "username_taken")
    r = kitchen.post(f"{API}/people/{joss}/login", json={"username": "Joss Smith"})
    assert r.status_code == 422


def test_a_removed_persons_link_stops_working(kitchen: TestClient) -> None:
    joss = _add(kitchen)
    token = _join(kitchen, joss, "joss")
    ok(kitchen.delete(f"{API}/people/{joss}"))
    _problem(_look(_fresh(kitchen), token), 404, "link_gone")


def test_joining_needs_https_like_signing_in(kitchen: TestClient) -> None:
    joss = _add(kitchen)
    token = _join(kitchen, joss, "joss")
    r = _fresh(kitchen).post(
        f"{API}/join",
        json={"token": token, "password": "joss's own password"},
        headers={"Origin": "http://192.0.2.5"},
    )
    assert r.status_code in (400, 403), r.text
    ok(_look(_fresh(kitchen), token))  # still unused


def test_a_wrong_token_is_link_gone(kitchen: TestClient) -> None:
    _problem(_look(_fresh(kitchen), "nonsense"), 404, "link_gone")
    _problem(_look(_fresh(kitchen), "x" * 300), 404, "link_gone")
    use = {"token": "x" * 300, "password": "a long password!!"}
    _problem(_fresh(kitchen).post(f"{API}/join", json=use), 404, "link_gone")


def test_the_link_secret_is_never_in_an_address(kitchen: TestClient) -> None:
    """Link hardening (cabledrawer 13 Nov): the secret follows a `#`, which a browser never sends;
    the old addresses with the secret in the path are gone."""
    token = _join(kitchen, _add(kitchen, "Sam"), "sam")
    assert "/" not in token and "#" not in token
    assert _fresh(kitchen).get(f"{API}/join/{token}").status_code in (404, 405)
    old = _fresh(kitchen).post(f"{API}/join/{token}", json={"password": "a long password!!"})
    assert old.status_code in (404, 405)
    ok(_look(_fresh(kitchen), token))  # still unused
    paths = kitchen.get(f"{API}/openapi.json").json()["paths"]
    assert not [path for path in paths if "{token}" in path]


# --- "Who's this?" -------------------------------------------------------------------------------


def _tablet(kitchen: TestClient) -> TestClient:
    tablet = person(kitchen, name="Kitchen tablet", username="tablet")
    ok(kitchen.patch(f"{API}/people/{_id(kitchen, 'Kitchen tablet')}", json={"shared": True}))
    return tablet


def test_a_shared_login_doesnt_eat_and_asks_only_when_switched_on(kitchen: TestClient) -> None:
    tablet = _tablet(kitchen)
    _add(kitchen)
    asked = ok(tablet.get(f"{API}/whos-this"))
    assert asked["ask"] is False and asked["picked"] is None
    assert [p["name"] for p in asked["people"]] == ["Tess", "Joss"]
    assert "Kitchen tablet" not in [p["name"] for p in ok(kitchen.get(f"{API}/plan/people"))]
    ok(kitchen.put(f"{API}/people/ask-whos-this", json={"on": True}))
    switched = _newest(kitchen)
    assert switched["summary"] == "Switched Ask “Who’s this?” on"
    assert ok(tablet.get(f"{API}/whos-this"))["ask"] is True
    assert ok(kitchen.get(f"{API}/whos-this"))["ask"] is False  # not a shared login
    assert ok(tablet.get(f"{API}/me"))["shared"] is True
    _undo(kitchen, switched)
    assert ok(tablet.get(f"{API}/whos-this"))["ask"] is False


def test_the_picked_person_is_named_in_recent_changes(kitchen: TestClient) -> None:
    tablet = _tablet(kitchen)
    ok(kitchen.put(f"{API}/people/ask-whos-this", json={"on": True}))
    joss = _add(kitchen)
    # Nobody picked yet: the change is the tablet's.
    ok(tablet.patch(f"{API}/household", json={"cook_per_step": True}))
    assert _newest(kitchen)["who"]["name"] == "Kitchen tablet"
    picked = ok(tablet.put(f"{API}/whos-this", json={"member_id": joss}))
    assert picked["picked"] == joss
    ok(tablet.patch(f"{API}/household", json={"cook_per_step": False}))
    who = _newest(kitchen)["who"]
    assert who["name"] == "Joss" and who["member_id"] == joss
    # Only this device's sign-in is Joss: the pick is kept with the session.
    with db(kitchen) as session:
        assert session.scalars(
            select(Session.member_id).where(Session.member_id == joss)
        ).all() == [joss]
    # "Just looking": nobody picked again.
    assert ok(tablet.put(f"{API}/whos-this", json={"member_id": None}))["picked"] is None
    ok(tablet.patch(f"{API}/household", json={"cook_per_step": True}))
    assert _newest(kitchen)["who"]["name"] == "Kitchen tablet"


def test_a_pick_counts_only_while_the_household_asks_whos_this(kitchen: TestClient) -> None:
    """Review r1: with the switch off, a pick made earlier credits nobody."""
    tablet = _tablet(kitchen)
    ok(kitchen.put(f"{API}/people/ask-whos-this", json={"on": True}))
    joss = _add(kitchen)
    ok(tablet.put(f"{API}/whos-this", json={"member_id": joss}))
    ok(kitchen.put(f"{API}/people/ask-whos-this", json={"on": False}))
    ok(tablet.patch(f"{API}/household", json={"cook_per_step": True}))
    who = _newest(kitchen)["who"]
    assert who["name"] == "Kitchen tablet" and who["member_id"] is None
    assert ok(tablet.get(f"{API}/whos-this"))["picked"] is None


def _pick_made(kitchen: TestClient, minutes_ago: int) -> None:
    with db(kitchen) as session:
        for row in session.scalars(select(Session).where(Session.member_id.is_not(None))):
            row.picked_at = utcnow() - timedelta(minutes=minutes_ago)
        session.commit()


def test_a_pick_older_than_30_minutes_without_a_change_credits_nobody(
    kitchen: TestClient,
) -> None:
    """Review r1: the server forgets a pick like the browser does (cabledrawer 12 Nov); a
    change made as the person keeps it going."""
    tablet = _tablet(kitchen)
    ok(kitchen.put(f"{API}/people/ask-whos-this", json={"on": True}))
    joss = _add(kitchen)
    ok(tablet.put(f"{API}/whos-this", json={"member_id": joss}))
    _pick_made(kitchen, 25)
    ok(tablet.patch(f"{API}/household", json={"cook_per_step": True}))
    assert _newest(kitchen)["who"]["member_id"] == joss
    _pick_made(kitchen, 20)
    # Reading changes nothing: 20 minutes on from the last change, still Joss.
    assert ok(tablet.get(f"{API}/whos-this"))["picked"] == joss
    _pick_made(kitchen, 31)
    assert ok(tablet.get(f"{API}/whos-this"))["picked"] is None
    ok(tablet.patch(f"{API}/household", json={"cook_per_step": False}))
    who = _newest(kitchen)["who"]
    assert who["name"] == "Kitchen tablet" and who["member_id"] is None


def test_a_change_made_as_the_picked_person_keeps_the_pick_going(kitchen: TestClient) -> None:
    tablet = _tablet(kitchen)
    ok(kitchen.put(f"{API}/people/ask-whos-this", json={"on": True}))
    joss = _add(kitchen)
    ok(tablet.put(f"{API}/whos-this", json={"member_id": joss}))
    _pick_made(kitchen, 25)
    ok(tablet.patch(f"{API}/household", json={"cook_per_step": True}))
    with db(kitchen) as session:
        picked_at = session.scalars(
            select(Session.picked_at).where(Session.member_id == joss)
        ).one()
    assert picked_at is not None
    assert utcnow() - as_utc(picked_at) < timedelta(minutes=1)


def test_the_shopping_list_is_synced_only_with_people_who_sign_in(kitchen: TestClient) -> None:
    """Review r1: "Synced with ..." leaves out a removed person, a person whose sign-in link
    isn't used yet and a shared login (a device, not a person)."""
    person(kitchen)
    _tablet(kitchen)
    person(kitchen, name="Sam", username="sam")
    ok(kitchen.delete(f"{API}/people/{_id(kitchen, 'Sam')}"))
    _join(kitchen, _add(kitchen), "joss")
    ok(kitchen.patch(f"{API}/people/{_id(kitchen, 'Wren')}", json={"name": "Ram"}))
    names = [p["name"] for p in ok(kitchen.get(f"{API}/shopping/changes"))["people"]]
    assert names == ["Tess", "Ram"]


def test_picking_is_for_shared_logins_and_people_of_the_household(kitchen: TestClient) -> None:
    tablet = _tablet(kitchen)
    joss = _add(kitchen)
    r = kitchen.put(f"{API}/whos-this", json={"member_id": joss})
    _problem(r, 409, "not_shared")
    tablet_id = _id(kitchen, "Kitchen tablet")
    _problem(tablet.put(f"{API}/whos-this", json={"member_id": tablet_id}), 404, "not_found")
    _problem(tablet.put(f"{API}/whos-this", json={"member_id": 999}), 404, "not_found")
    ok(tablet.put(f"{API}/whos-this", json={"member_id": joss}))
    ok(kitchen.delete(f"{API}/people/{joss}"))
    # Removing Joss ends her pick on every device.
    assert ok(tablet.get(f"{API}/whos-this"))["picked"] is None
    _problem(tablet.put(f"{API}/whos-this", json={"member_id": joss}), 404, "not_found")


def test_a_shared_login_cant_pick_a_neighbours_person(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    tablet = _tablet(kitchen)
    ok(kitchen.put(f"{API}/people/ask-whos-this", json={"on": True}))
    theirs = _people(neighbour)["people"][0]["id"]
    _problem(tablet.put(f"{API}/whos-this", json={"member_id": theirs}), 404, "not_found")
    assert ok(tablet.get(f"{API}/whos-this"))["picked"] is None


def test_a_member_can_pick_but_not_switch(kitchen: TestClient) -> None:
    tablet = _tablet(kitchen)
    r = tablet.put(f"{API}/people/ask-whos-this", json={"on": True})
    _problem(r, 403, "admins_only")


def test_a_link_claimed_while_a_new_one_is_made_stays_gone_when_the_hash_fails(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    joss = _add(kitchen)
    old = _join(kitchen, joss, "joss")
    entered, release = threading.Event(), threading.Event()

    def slow_broken(password: str) -> str:
        entered.set()
        release.wait(10)
        raise RuntimeError("hash failed")

    monkeypatch.setattr("mealwright.api.v1.people.hash_password", slow_broken)

    def go() -> None:
        with pytest.raises(RuntimeError):
            _fresh(kitchen).post(
                f"{API}/join", json={"token": old, "password": "a long password!!"}
            )

    thread = threading.Thread(target=go)
    thread.start()
    assert entered.wait(10)
    new = _join(kitchen, joss, "joss")  # while the first join is still hashing
    release.set()
    thread.join()
    monkeypatch.undo()
    _problem(_look(_fresh(kitchen), old), 404, "link_gone")
    ok(_look(_fresh(kitchen), new))
    with db(kitchen) as session:
        assert len(session.scalars(select(JoinLink)).all()) == 1


def test_giving_a_link_back_needs_the_link_to_exist_and_no_newer_one(kitchen: TestClient) -> None:
    joss = _add(kitchen)
    old = _join(kitchen, joss, "joss")
    with db(kitchen) as session:
        first = session.scalars(select(JoinLink)).one()
        first.used_at = utcnow()
        session.commit()
        session.add(
            JoinLink(
                household_id=first.household_id,
                login_id=first.login_id,
                token_hash="x" * 64,
                created_at=utcnow(),
                expires_at=utcnow() + timedelta(hours=24),
            )
        )
        session.commit()
        people.give_back_link(session, first)
        assert session.scalars(select(JoinLink).where(JoinLink.id == first.id)).one().used_at
    _problem(_look(_fresh(kitchen), old), 404, "link_gone")


def test_a_shared_login_is_not_the_last_admin(kitchen: TestClient) -> None:
    tablet = person(kitchen, name="Kitchen tablet", username="tablet")
    me, tid = _id(kitchen, "Tess"), _id(kitchen, "Kitchen tablet")
    ok(kitchen.patch(f"{API}/people/{tid}", json={"shared": True, "role": "admin"}))
    detail = _problem(
        kitchen.patch(f"{API}/people/{me}", json={"role": "member"}), 409, "last_admin"
    )
    assert detail == "Tess is the household’s only admin. Make someone else an admin first."
    assert _people(tablet)["can_change"] is True  # it can still be an admin, just never the last
    _problem(kitchen.delete(f"{API}/people/{me}"), 409, "remove_yourself")


def test_the_only_admin_cant_be_made_a_shared_login(kitchen: TestClient) -> None:
    me = _id(kitchen, "Tess")
    _problem(kitchen.patch(f"{API}/people/{me}", json={"shared": True}), 409, "last_admin")
    wren = person(kitchen)
    ok(kitchen.patch(f"{API}/people/{_id(kitchen, 'Wren')}", json={"role": "admin"}))
    ok(kitchen.patch(f"{API}/people/{me}", json={"shared": True}))
    assert _people(wren)["can_change"] is True


def test_removing_a_person_ends_their_open_event_streams(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O2 review r4, finding 4: their sessions go with them, so do their live-update streams.
    Fails without the call to `events.end_session`."""
    joss = _add(kitchen)
    token = _join(kitchen, joss, "joss")
    joss_client = _fresh(kitchen)
    assert joss_client.post(
        f"{API}/join", json={"token": token, "password": "joss's own password"}
    ).is_success
    signed = joss_client.post(
        f"{API}/session", json={"username": "joss", "password": "joss's own password"}
    )
    assert signed.status_code == 200, signed.text
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        ids = list(
            db.scalars(
                select(Session.id)
                .join(Login, Login.id == Session.login_id)
                .where(Login.username == "joss")
            )
        )
    assert len(ids) == 1
    ended: list[int] = []
    monkeypatch.setattr(kitchen.app.state.events, "end_session", ended.append)  # type: ignore[attr-defined]
    ok(kitchen.delete(f"{API}/people/{joss}"))
    assert ended == ids
