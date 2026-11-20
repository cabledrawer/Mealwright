"""Settings › Outside connections in Recent changes, with Undo (0.9.5-beta.3, D4, BE5).

cabledrawer 20 Nov: "outside-connection switches and Your own network go into Recent changes
with Undo (as the spec said)". Each switch and each entry added or taken off is a change; an
admin can undo it within the undo window while nothing has changed it since. A member and an
API token can't. An Undo of "switched on" blocks the next outside connection at once.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from test_api_tokens import _app, _make
from test_privacy import LIST, SWITCHES, member, neighbour, values  # noqa: F401

from mealwright.models import Change
from mealwright.outbound import Connection, OutboundBlocked, OutboundGate

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


def test_undoing_a_switch_off_turns_it_back_on(kitchen: TestClient) -> None:
    _switch(kitchen, "update_check", True)
    off = _switch(kitchen, "update_check", False).json()["change"]
    assert off["summary"] == "Switched the update check off"
    assert _undo(kitchen, off["id"]).status_code == 200
    assert _is_on(kitchen, "update_check")
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


def test_undoing_a_removal_adds_the_entry_back_as_a_new_one(kitchen: TestClient) -> None:
    added = kitchen.post(LIST, json={"value": "192.168.1.20"}).json()
    gone = kitchen.delete(f"{LIST}/{added['id']}")
    change = gone.json()["change"]
    assert change["kind"] == "own_network_removed"
    assert change["summary"] == "Removed 192.168.1.20 from Your own network"
    assert _undo(kitchen, change["id"]).status_code == 200
    entries = kitchen.get(LIST).json()["entries"]
    assert [e["value"] for e in entries] == ["192.168.1.20"]
    assert entries[0]["id"] != added["id"]  # a new entry (spec)
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.query(Change).filter_by(kind="undo").count() == 1


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


def test_a_member_sees_them_but_cant_undo(
    kitchen: TestClient,
    member: TestClient,  # noqa: F811
) -> None:
    change = _switch(kitchen, "recipe_import", True).json()["change"]
    listed = [c for c in _listed(member) if c["id"] == change["id"]]
    assert listed and listed[0]["can_undo"] is False
    refused = _undo(member, change["id"])
    assert refused.status_code == 403
    assert refused.json()["code"] == "admins_only"
    assert _is_on(kitchen, "recipe_import")


def test_an_admins_api_token_cant_undo_them(kitchen: TestClient) -> None:
    change = kitchen.post(LIST, json={"value": "wiki.home.example"}).json()["change"]
    app = _app(kitchen, _make(kitchen, "full"))
    refused = _undo(app, change["id"])
    assert refused.status_code == 403, refused.text
    assert values(kitchen) == ["wiki.home.example"]


def test_another_household_cant_see_or_undo_them(
    kitchen: TestClient,
    neighbour: TestClient,  # noqa: F811
) -> None:
    change = _switch(kitchen, "recipe_import", True).json()["change"]
    assert _undo(neighbour, change["id"]).status_code == 404
    assert _listed(neighbour) == []
    assert _is_on(kitchen, "recipe_import")
