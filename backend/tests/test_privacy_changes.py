"""Settings › Outside connections in Recent changes, with Undo (0.9.5-beta.3, D4, BE5).

cabledrawer 20 Nov: "outside-connection switches and Your own network go into Recent changes
with Undo (as the spec said)". Each switch and each entry added or taken off is a change; an
admin can undo it within the undo window while nothing has changed it since. A member and an
API token can't. An Undo of "switched on" blocks the next outside connection at once. A member
and an API token don't see the own-network changes at all (security review beta.3, finding 1).
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sync_kit import one
from test_api_tokens import _app, _make
from test_privacy import LIST, SWITCHES, values

from mealwright.models import Change
from mealwright.outbound import Connection, OutboundBlocked, OutboundGate, set_switch

API = "/api/v1"


def _undo(client: TestClient, change_id: int, **headers: str) -> Any:
    return client.post(f"{API}/changes/{change_id}/undo", headers=headers)


def _listed(client: TestClient) -> list[dict[str, Any]]:
    return [
        c
        for c in client.get(f"{API}/changes").json()["changes"]
        if c["kind"] in ("connection_changed", "own_network_added", "own_network_removed")
    ]


def _switch(client: TestClient, name: str, on: bool, **headers: str) -> Any:
    return client.put(f"{SWITCHES}/{name}", json={"on": on}, headers=headers)


def _is_on(client: TestClient, name: str) -> bool:
    switches = client.get(SWITCHES).json()["switches"]
    return bool(next(s["on"] for s in switches if s["connection"] == name))


def _gate(client: TestClient) -> OutboundGate:
    return OutboundGate(client.app.state.sessionmaker)  # type: ignore[attr-defined]


# --- The switches -------------------------------------------------------------------------------


def test_a_switch_is_a_change_and_its_undo_blocks_the_gate_at_once(kitchen: TestClient) -> None:
    answer = _switch(kitchen, "recipe_import", True)
    assert answer.status_code == 200, answer.text
    change = answer.json()["change"]
    assert change["kind"] == "connection_changed"
    assert change["summary"] == "Switched recipe import on"
    assert change["can_undo"] is True
    assert change["at"].endswith("Z")
    _gate(kitchen).check_switch(1, Connection.RECIPE_IMPORT)  # allowed: no exception
    assert [c["id"] for c in _listed(kitchen)] == [change["id"]]

    undone = _undo(kitchen, change["id"])
    assert undone.status_code == 200, undone.text
    assert undone.json()["undone"]["kind"] == "connection_changed"
    assert undone.json()["notice"] is None
    assert not _is_on(kitchen, "recipe_import")
    with pytest.raises(OutboundBlocked):
        _gate(kitchen).check_switch(1, Connection.RECIPE_IMPORT)


@pytest.mark.parametrize(
    "name", ["recipe_import", "recipe_photos", "update_check", "single_sign_on"]
)
def test_an_undo_never_switches_an_outside_connection_on(kitchen: TestClient, name: str) -> None:
    # Release security pass beta.3, Low 2: every outside connection is off until someone turns
    # it on on purpose; an Undo (one Ctrl+Z, days later) is not that.
    connection = Connection(name)
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        set_switch(db, 1, connection, True)  # on, however it got there
        db.commit()
    off = _switch(kitchen, name, False)
    assert off.status_code == 200, off.text
    change = off.json()["change"]
    assert change["summary"].endswith(" off")
    assert change["can_undo"] is True  # Ctrl+Z after a reload stops here and says why
    refused = _undo(kitchen, change["id"])
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "cannot_undo"
    assert refused.json()["detail"] == "Switch it on in Settings › Outside connections."
    assert not _is_on(kitchen, name)
    with pytest.raises(OutboundBlocked):
        _gate(kitchen).check_switch(1, connection)
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.query(Change).filter_by(kind="undo").count() == 0
    again = _undo(kitchen, change["id"])  # asked again: the same answer, nothing else undone
    assert again.status_code == 409 and again.json()["detail"] == refused.json()["detail"]


def test_the_offline_queue_cant_undo_a_switch_either(kitchen: TestClient) -> None:
    # A queued `undo` names a list action (sync protocol section 9); a switch change has none,
    # so naming its Idempotency-Key, or its change id, undoes nothing.
    key = "3d4e5f60-7182-493a-9c4d-5e6f708192a3"
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        set_switch(db, 1, Connection.RECIPE_IMPORT, True)
        db.commit()
    off = _switch(kitchen, "recipe_import", False, **{"Idempotency-Key": key}).json()["change"]
    for undoes in (key, str(off["id"])):
        result = one(kitchen, "undo", undoes=undoes)
        assert result["status"] == "ignored", result
        assert result["reason"] == "nothing_to_undo", result
    assert not _is_on(kitchen, "recipe_import")


def test_undoing_a_switch_on_still_switches_it_off(kitchen: TestClient) -> None:
    on = _switch(kitchen, "update_check", True).json()["change"]
    assert on["summary"] == "Switched the update check on"
    assert _undo(kitchen, on["id"]).status_code == 200
    assert not _is_on(kitchen, "update_check")
    with pytest.raises(OutboundBlocked):
        _gate(kitchen).check_switch(1, Connection.UPDATE_CHECK)


def test_asking_for_the_state_it_has_is_not_a_change(kitchen: TestClient) -> None:
    answer = _switch(kitchen, "recipe_photos", False)
    assert answer.status_code == 200
    assert answer.json()["change"] is None
    assert _listed(kitchen) == []


def test_a_switch_changed_again_cant_be_undone(kitchen: TestClient) -> None:
    first = _switch(kitchen, "recipe_photos", True).json()["change"]
    _switch(kitchen, "recipe_photos", False)
    _switch(kitchen, "recipe_photos", True)  # on again, as the first change left it
    refused = _undo(kitchen, first["id"])
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "cannot_undo"
    assert (
        refused.json()["detail"] == "That can’t be undone: recipe photos has been switched again."
    )
    assert _is_on(kitchen, "recipe_photos")


def test_another_switch_changed_since_doesnt_stop_the_undo(kitchen: TestClient) -> None:
    first = _switch(kitchen, "recipe_photos", True).json()["change"]
    _switch(kitchen, "recipe_import", True)
    assert _undo(kitchen, first["id"]).status_code == 200
    assert not _is_on(kitchen, "recipe_photos")
    assert _is_on(kitchen, "recipe_import")


def test_a_switch_sent_again_with_its_key_is_one_change(kitchen: TestClient) -> None:
    key = {"Idempotency-Key": "8f0c1d2e-3a4b-4c5d-8e6f-7a8b9c0d1e2f"}
    first = _switch(kitchen, "recipe_import", True, **key)
    again = _switch(kitchen, "recipe_import", True, **key)
    assert again.status_code == 200
    assert again.headers.get("Idempotent-Replayed") == "true"
    assert again.json()["change"]["id"] == first.json()["change"]["id"]
    assert again.json()["change"]["at"].endswith("Z")
    assert len(_listed(kitchen)) == 1


# --- Your own network -------------------------------------------------------------------------


def test_undoing_an_add_takes_the_entry_off(kitchen: TestClient) -> None:
    added = kitchen.post(LIST, json={"value": "wiki.home.example"})
    assert added.status_code == 201, added.text
    change = added.json()["change"]
    assert change["kind"] == "own_network_added"
    assert change["summary"] == "Added wiki.home.example to Your own network"
    assert _undo(kitchen, change["id"]).status_code == 200
    assert values(kitchen) == []


def test_an_add_whose_entry_is_gone_cant_be_undone(kitchen: TestClient) -> None:
    added = kitchen.post(LIST, json={"value": "wiki.home.example"}).json()
    assert kitchen.delete(f"{LIST}/{added['id']}").status_code == 200
    refused = _undo(kitchen, added["change"]["id"])
    assert refused.status_code == 409
    assert refused.json()["code"] == "cannot_undo"
    assert refused.json()["detail"] == (
        "That can’t be undone: wiki.home.example is no longer on Your own network."
    )


def test_undoing_a_removal_never_puts_the_entry_back(kitchen: TestClient) -> None:
    # Putting it back would let the app reach that place again: like switching a connection
    # on, never by an Undo (release security pass beta.3, Low 2; proposed, for cabledrawer).
    added = kitchen.post(LIST, json={"value": "192.168.1.20"}).json()
    gone = kitchen.delete(f"{LIST}/{added['id']}")
    change = gone.json()["change"]
    assert change["kind"] == "own_network_removed"
    assert change["summary"] == "Removed 192.168.1.20 from Your own network"
    assert change["can_undo"] is True  # Ctrl+Z after a reload stops here and says why
    refused = _undo(kitchen, change["id"])
    assert refused.status_code == 409, refused.text
    assert refused.json()["code"] == "cannot_undo"
    assert refused.json()["detail"] == "Add it again in Settings › Outside connections."
    assert values(kitchen) == []
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.query(Change).filter_by(kind="undo").count() == 0
    # Adding it on purpose still works.
    assert kitchen.post(LIST, json={"value": "192.168.1.20"}).status_code == 201


def test_a_removal_already_put_back_cant_be_undone(kitchen: TestClient) -> None:
    added = kitchen.post(LIST, json={"value": "wiki.home.example"}).json()
    gone = kitchen.delete(f"{LIST}/{added['id']}").json()["change"]
    assert kitchen.post(LIST, json={"value": "wiki.home.example"}).status_code == 201
    refused = _undo(kitchen, gone["id"])
    assert refused.status_code == 409
    assert refused.json()["code"] == "cannot_undo"
    assert refused.json()["detail"] == "That can’t be undone. That’s already on the list."
    assert values(kitchen) == ["wiki.home.example"]


def test_an_add_sent_again_with_its_key_is_one_entry(kitchen: TestClient) -> None:
    key = {"Idempotency-Key": "1b2c3d4e-5f60-4718-9a2b-3c4d5e6f7081"}
    first = kitchen.post(LIST, json={"value": "nas.home.example"}, headers=key)
    again = kitchen.post(LIST, json={"value": "nas.home.example"}, headers=key)
    assert first.status_code == 201 and again.status_code == 200
    assert again.headers.get("Idempotent-Replayed") == "true"
    assert again.json() == first.json()
    assert values(kitchen) == ["nas.home.example"]


def test_a_removal_sent_again_with_its_key_answers_as_the_first(kitchen: TestClient) -> None:
    added = kitchen.post(LIST, json={"value": "nas.home.example"}).json()
    key = {"Idempotency-Key": "2c3d4e5f-6071-4829-8b3c-4d5e6f708192"}
    first = kitchen.delete(f"{LIST}/{added['id']}", headers=key)
    again = kitchen.delete(f"{LIST}/{added['id']}", headers=key)
    assert again.status_code == 200, again.text
    assert again.json() == first.json()


# --- Who may undo ------------------------------------------------------------------------------


def test_a_member_sees_a_switch_change_but_cant_undo_it(
    kitchen: TestClient,
    member: TestClient,
) -> None:
    # A switch's state is readable by a member anyway (GET /privacy/switches), so its change
    # stays in their Recent changes, without Undo. Own-network changes don't: see below.
    change = _switch(kitchen, "recipe_import", True).json()["change"]
    listed = [c for c in _listed(member) if c["id"] == change["id"]]
    assert listed and listed[0]["can_undo"] is False
    refused = _undo(member, change["id"])
    assert refused.status_code == 403
    assert refused.json()["code"] == "admins_only"
    assert _is_on(kitchen, "recipe_import")


def test_an_admins_api_token_cant_undo_them(kitchen: TestClient) -> None:
    switched = _switch(kitchen, "recipe_import", True).json()["change"]
    change = kitchen.post(LIST, json={"value": "wiki.home.example"}).json()["change"]
    app = _app(kitchen, _make(kitchen, "full"))
    refused = _undo(app, switched["id"])
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "not_for_tokens"
    # An own-network change isn't there at all for a token (security review beta.3, finding 1).
    assert _undo(app, change["id"]).status_code == 404
    assert values(kitchen) == ["wiki.home.example"]
    assert _is_on(kitchen, "recipe_import")


# --- Who sees Your own network in Recent changes (security review beta.3, finding 1) ----------
#
# GET /privacy/own-network is for an admin at a screen only (D4, BE12): a member must not be able
# to map the home network, and no API token reads it. Its changes name the entry, so they (and
# the Undos of them) are left out of Recent changes for everyone who can't read the list itself.

SECRETS = ("192.168.1.0/24", "nas.home.example", "wiki.home.example")


def _own_network_history(kitchen: TestClient) -> dict[str, int]:
    """An add, a removal, an Undo of an add, and switch changes in between: the change ids.
    (An Undo of a removal is refused since Low 2; one made before then is an Undo of an
    own-network change like this one.)"""
    ids = {"switch_1": _switch(kitchen, "recipe_import", True).json()["change"]["id"]}
    first = kitchen.post(LIST, json={"value": SECRETS[0]})
    assert first.status_code == 201, first.text
    ids["added"] = first.json()["change"]["id"]
    second = kitchen.post(LIST, json={"value": SECRETS[1]}).json()
    ids["switch_2"] = _switch(kitchen, "recipe_import", False).json()["change"]["id"]
    ids["removed"] = kitchen.delete(f"{LIST}/{second['id']}").json()["change"]["id"]
    third = kitchen.post(LIST, json={"value": SECRETS[2]}).json()["change"]
    ids["undo_added"] = _undo(kitchen, third["id"]).json()["change"]["id"]
    ids["switch_3"] = _switch(kitchen, "recipe_import", True).json()["change"]["id"]
    return ids


def _every_page(
    client: TestClient, limit: int, secrets_shown: bool = False
) -> list[dict[str, Any]]:
    """Recent changes, page by page, following `next` to the end (no page names an entry,
    unless `secrets_shown`)."""
    seen: list[dict[str, Any]] = []
    after: str | None = None
    for _ in range(50):
        params: dict[str, Any] = {"limit": limit}
        if after is not None:
            params["after"] = after
        page = client.get(f"{API}/changes", params=params)
        assert page.status_code == 200, page.text
        body = page.json()
        seen += body["changes"]
        for secret in SECRETS:
            assert secrets_shown or secret not in page.text
        after = body["next"]
        if after is None:
            return seen
    raise AssertionError("Recent changes never ended")


@pytest.mark.parametrize("who", ["member", "read token", "full token"])
def test_own_network_changes_are_left_out_for_whoever_cant_read_the_list(
    kitchen: TestClient, member: TestClient, who: str
) -> None:
    ids = _own_network_history(kitchen)
    caller = member if who == "member" else _app(kitchen, _make(kitchen, who.split()[0]))
    assert caller.get(LIST).status_code == 403  # the rule this follows
    hidden = {ids["added"], ids["removed"], ids["undo_added"]}
    switches = [ids["switch_3"], ids["switch_2"], ids["switch_1"]]
    for limit in (1, 2, 20):
        listed = _every_page(caller, limit)
        assert [c["id"] for c in listed] == switches
        assert not hidden & {c["id"] for c in listed}
    for change_id in hidden:  # not there at all: the same answer as another household's
        refused = _undo(caller, change_id)
        if who == "read token":  # refused before any change is looked at, as for every write
            assert refused.json()["code"] == "read_only_token", refused.text
        else:
            assert refused.status_code == 404, refused.text
        assert all(secret not in refused.text for secret in SECRETS)
    assert values(kitchen) == [SECRETS[0]]


def test_an_admin_still_sees_them_and_can_undo(kitchen: TestClient) -> None:
    ids = _own_network_history(kitchen)
    listed = {c["id"]: c for c in _every_page(kitchen, 1, secrets_shown=True)}
    assert set(ids.values()) <= set(listed)
    assert listed[ids["added"]]["summary"] == f"Added {SECRETS[0]} to Your own network"
    assert listed[ids["added"]]["can_undo"] is True
    assert _undo(kitchen, ids["added"]).status_code == 200
    assert values(kitchen) == []


def test_another_household_cant_see_or_undo_them(
    kitchen: TestClient,
    neighbour: TestClient,
) -> None:
    change = _switch(kitchen, "recipe_import", True).json()["change"]
    assert _undo(neighbour, change["id"]).status_code == 404
    assert _listed(neighbour) == []
    assert _is_on(kitchen, "recipe_import")
