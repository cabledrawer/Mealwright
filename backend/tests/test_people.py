"""Settings → Household (0.9 A1): the people of the household, their logins and roles, the
one-time sign-in link, removing with Undo, and "Who's this?" on a shared login."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import API, db, ok, person

from mealwright.models import JoinLink, Login, Member, Session


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
    assert link["path"].startswith("/join/")
    return str(link["path"].removeprefix("/join/"))


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
        "link_pending": False,
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
        "link_pending": True,
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
    page = ok(joss_client.get(f"{API}/join/{token}"))
    assert page["name"] == "Joss" and page["username"] == "joss" and page["min_password"] == 12
    short = joss_client.post(f"{API}/join/{token}", json={"password": "eleven char"})
    assert short.status_code == 422
    me = ok(joss_client.post(f"{API}/join/{token}", json={"password": "joss's own password"}))
    assert me["member_id"] == joss and me["role"] == "member"
    assert ok(joss_client.get(f"{API}/me"))["username"] == "joss"
    # The link works once.
    _problem(_fresh(kitchen).get(f"{API}/join/{token}"), 404, "link_gone")
    again = _fresh(kitchen).post(f"{API}/join/{token}", json={"password": "someone else's pw"})
    _problem(again, 404, "link_gone")
    # She signs in with her own password from now on; a second link is refused.
    signed = _fresh(kitchen).post(
        f"{API}/session", json={"username": "joss", "password": "joss's own password"}
    )
    assert signed.status_code == 200
    r = kitchen.post(f"{API}/people/{joss}/login", json={"username": "joss"})
    _problem(r, 409, "signs_in_already")
    after = next(p for p in _people(kitchen)["people"] if p["id"] == joss)["login"]
    assert after["has_password"] is True and after["link_pending"] is False


def test_a_link_runs_out_after_24_hours(kitchen: TestClient) -> None:
    joss = _add(kitchen)
    token = _join(kitchen, joss, "joss")
    with db(kitchen) as session:
        link = session.scalars(select(JoinLink)).one()
        assert link.expires_at - link.created_at == timedelta(hours=24)
        link.expires_at = link.created_at - timedelta(seconds=1)
        session.commit()
    detail = _problem(_fresh(kitchen).get(f"{API}/join/{token}"), 404, "link_gone")
    assert detail.startswith("This sign-in link has been used or has run out.")


def test_a_new_link_replaces_the_old_one_and_profile_only_takes_it_back(
    kitchen: TestClient,
) -> None:
    joss = _add(kitchen)
    first = _join(kitchen, joss, "joss")
    second = _join(kitchen, joss, "joss2", role="admin")
    _problem(_fresh(kitchen).get(f"{API}/join/{first}"), 404, "link_gone")
    assert ok(_fresh(kitchen).get(f"{API}/join/{second}"))["username"] == "joss2"
    ok_status = kitchen.delete(f"{API}/people/{joss}/login")
    assert ok_status.status_code == 204
    _problem(_fresh(kitchen).get(f"{API}/join/{second}"), 404, "link_gone")
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
    _problem(_fresh(kitchen).get(f"{API}/join/{token}"), 404, "link_gone")


def test_joining_needs_https_like_signing_in(kitchen: TestClient) -> None:
    joss = _add(kitchen)
    token = _join(kitchen, joss, "joss")
    r = _fresh(kitchen).post(
        f"{API}/join/{token}",
        json={"password": "joss's own password"},
        headers={"Origin": "http://192.0.2.5"},
    )
    assert r.status_code in (400, 403), r.text
    assert ok(_fresh(kitchen).get(f"{API}/join/{token}"))["name"] == "Joss"  # still unused


def test_a_wrong_token_is_link_gone(kitchen: TestClient) -> None:
    _problem(_fresh(kitchen).get(f"{API}/join/nonsense"), 404, "link_gone")
    _problem(_fresh(kitchen).get(f"{API}/join/{'x' * 300}"), 404, "link_gone")


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


def test_a_member_can_pick_but_not_switch(kitchen: TestClient) -> None:
    tablet = _tablet(kitchen)
    r = tablet.put(f"{API}/people/ask-whos-this", json={"on": True})
    _problem(r, 403, "admins_only")
