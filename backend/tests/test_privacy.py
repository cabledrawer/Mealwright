"""Settings → Privacy: the switches and "Your own network" (0.5 PR 4).

Everyone in the household reads them, only an admin changes them, one household never sees
or changes another's, and a change reaches the outbound gate at once.
"""

import logging
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from mealwright import own_network
from mealwright.auth import hash_password
from mealwright.household import add_default_places
from mealwright.models import Household, Login, OwnNetworkEntry
from mealwright.outbound import Connection, OutboundBlocked, OutboundGate

API = "/api/v1"
SWITCHES = f"{API}/privacy/switches"
LIST = f"{API}/privacy/own-network"
NEIGHBOUR = {"username": "neighbour", "password": "next door's own password"}
ADMINS_ONLY = "Only the household’s admin can change this."


@pytest.fixture
def member(kitchen: TestClient) -> Iterator[TestClient]:
    """A second login in the same household, with the Member role."""
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(
            Login(
                household_id=1,
                username="remy",
                name="Remy",
                password_hash=hash_password("remy's own password"),
                role="member",
            )
        )
        db.commit()
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        response = other.post(
            f"{API}/session", json={"username": "remy", "password": "remy's own password"}
        )
        assert response.status_code == 200
        yield other


@pytest.fixture
def neighbour(kitchen: TestClient) -> Iterator[TestClient]:
    """Household 2, with its own admin, signed in on its own client."""
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(Household(id=2, name="Next door"))
        db.flush()
        add_default_places(db, 2)
        db.add(
            Login(
                household_id=2,
                username=NEIGHBOUR["username"],
                name="Neighbour",
                password_hash=hash_password(NEIGHBOUR["password"]),
                role="admin",
            )
        )
        db.commit()
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        assert other.post(f"{API}/session", json=NEIGHBOUR).status_code == 200
        yield other


def on(client: TestClient) -> dict[str, bool]:
    body = client.get(SWITCHES).json()
    return {s["connection"]: s["on"] for s in body["switches"]}


def values(client: TestClient) -> list[str]:
    return [e["value"] for e in client.get(LIST).json()["entries"]]


# --- The switches ------------------------------------------------------------------------


def test_both_switches_start_off(kitchen: TestClient) -> None:
    body = kitchen.get(SWITCHES).json()
    assert body == {
        "switches": [
            {"connection": "recipe_import", "on": False},
            {"connection": "recipe_photos", "on": False},
        ],
        "can_change": True,
    }


def test_an_admin_turns_a_switch_on_and_off(kitchen: TestClient) -> None:
    response = kitchen.put(f"{SWITCHES}/recipe_import", json={"on": True})
    assert response.status_code == 200
    assert response.json()["switches"][0] == {"connection": "recipe_import", "on": True}
    assert on(kitchen) == {"recipe_import": True, "recipe_photos": False}
    kitchen.put(f"{SWITCHES}/recipe_photos", json={"on": True})
    kitchen.put(f"{SWITCHES}/recipe_import", json={"on": False})
    assert on(kitchen) == {"recipe_import": False, "recipe_photos": True}


def test_asking_for_the_state_it_has_changes_nothing(
    kitchen: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="mealwright.api.v1.privacy"):
        kitchen.put(f"{SWITCHES}/recipe_import", json={"on": False})
        kitchen.put(f"{SWITCHES}/recipe_import", json={"on": True})
        kitchen.put(f"{SWITCHES}/recipe_import", json={"on": True})
    assert on(kitchen)["recipe_import"] is True
    assert [r.getMessage() for r in caplog.records] == ["Privacy: recipe import switched on"]


def test_a_member_sees_the_switches_but_cannot_change_them(
    kitchen: TestClient, member: TestClient
) -> None:
    kitchen.put(f"{SWITCHES}/recipe_import", json={"on": True})
    body = member.get(SWITCHES).json()
    assert body["can_change"] is False
    assert on(member) == {"recipe_import": True, "recipe_photos": False}
    for want in (True, False):
        response = member.put(f"{SWITCHES}/recipe_photos", json={"on": want})
        assert response.status_code == 403
        assert response.json()["code"] == "admins_only"
        assert response.json()["detail"] == ADMINS_ONLY
    assert on(kitchen) == {"recipe_import": True, "recipe_photos": False}


def test_a_switch_that_does_nothing_yet_is_not_there(kitchen: TestClient) -> None:
    # The update check, notifications and single sign-on arrive with 0.8.
    for name in ("update_check", "notifications", "single_sign_on", "nonsense"):
        assert kitchen.put(f"{SWITCHES}/{name}", json={"on": True}).status_code == 422
    assert kitchen.put(f"{SWITCHES}/recipe_import", json={"on": "maybe"}).status_code == 422
    assert kitchen.put(f"{SWITCHES}/recipe_import", json={}).status_code == 422
    assert on(kitchen) == {"recipe_import": False, "recipe_photos": False}


def test_a_switch_belongs_to_its_household(kitchen: TestClient, neighbour: TestClient) -> None:
    kitchen.put(f"{SWITCHES}/recipe_import", json={"on": True})
    assert on(neighbour) == {"recipe_import": False, "recipe_photos": False}
    neighbour.put(f"{SWITCHES}/recipe_photos", json={"on": True})
    assert on(kitchen) == {"recipe_import": True, "recipe_photos": False}
    neighbour.put(f"{SWITCHES}/recipe_import", json={"on": False})
    assert on(kitchen)["recipe_import"] is True


def test_a_change_reaches_the_gate_at_once(kitchen: TestClient) -> None:
    gate: OutboundGate = kitchen.app.state.outbound  # type: ignore[attr-defined]
    with pytest.raises(OutboundBlocked):
        gate.check_switch(1, Connection.RECIPE_IMPORT)
    kitchen.put(f"{SWITCHES}/recipe_import", json={"on": True})
    gate.check_switch(1, Connection.RECIPE_IMPORT)  # the very next connection is let through
    assert gate.is_allowed(1, Connection.RECIPE_IMPORT)
    assert not gate.is_allowed(1, Connection.RECIPE_PHOTOS)  # each has its own switch
    kitchen.put(f"{SWITCHES}/recipe_import", json={"on": False})
    with pytest.raises(OutboundBlocked):
        gate.check_switch(1, Connection.RECIPE_IMPORT)
    kitchen.put(f"{SWITCHES}/recipe_photos", json={"on": True})
    assert gate.is_allowed(1, Connection.RECIPE_PHOTOS)


def test_signed_out_gets_nothing(client: TestClient) -> None:
    assert client.get(SWITCHES).status_code == 401
    assert client.put(f"{SWITCHES}/recipe_import", json={"on": True}).status_code == 401
    assert client.get(LIST).status_code == 401
    assert client.post(LIST, json={"value": "wiki.home.example"}).status_code == 401
    assert client.delete(f"{LIST}/1").status_code == 401


def test_a_change_from_another_site_is_refused(kitchen: TestClient) -> None:
    response = kitchen.put(
        f"{SWITCHES}/recipe_import", json={"on": True}, headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403
    response = kitchen.post(
        LIST, json={"value": "wiki.home.example"}, headers={"Origin": "https://evil.example"}
    )
    assert response.status_code == 403
    assert on(kitchen)["recipe_import"] is False
    assert values(kitchen) == []


# --- Your own network: reading --------------------------------------------------------------


def test_the_list_starts_empty(kitchen: TestClient) -> None:
    assert kitchen.get(LIST).json() == {"entries": [], "limit": 100, "can_change": True}


def test_an_admin_adds_a_name_an_address_and_a_range(kitchen: TestClient) -> None:
    name = kitchen.post(LIST, json={"value": "  Wiki.Home.Example. "})
    assert name.status_code == 201
    first = name.json()
    assert first["kind"] == "name"
    assert first["value"] == "wiki.home.example"
    assert first["addresses"] is None
    assert first["added_by"] == "Tess"
    assert len(first["added_on"]) == 10  # a date, like 2026-10-22
    address = kitchen.post(LIST, json={"value": "192.168.1.20"}).json()
    assert (address["kind"], address["value"], address["addresses"]) == (
        "address",
        "192.168.1.20",
        None,
    )
    ranged = kitchen.post(LIST, json={"value": "192.168.1.77/24"}).json()  # tidied
    assert (ranged["kind"], ranged["value"], ranged["addresses"]) == (
        "range",
        "192.168.1.0/24",
        256,
    )
    v6 = kitchen.post(LIST, json={"value": "fd12:3456:789a::/48"}).json()
    assert (v6["kind"], v6["addresses"]) == ("range", None)
    body = kitchen.get(LIST).json()
    assert [e["id"] for e in body["entries"]] == [
        first["id"],
        address["id"],
        ranged["id"],
        v6["id"],
    ]
    assert values(kitchen) == [
        "wiki.home.example",
        "192.168.1.20",
        "192.168.1.0/24",
        "fd12:3456:789a::/48",
    ]


def test_a_member_sees_the_list_but_cannot_change_it(
    kitchen: TestClient, member: TestClient
) -> None:
    entry = kitchen.post(LIST, json={"value": "wiki.home.example"}).json()
    body = member.get(LIST).json()
    assert body["can_change"] is False
    assert [e["value"] for e in body["entries"]] == ["wiki.home.example"]
    added = member.post(LIST, json={"value": "192.168.1.20"})
    assert added.status_code == 403
    assert added.json()["code"] == "admins_only"
    removed = member.delete(f"{LIST}/{entry['id']}")
    assert removed.status_code == 403
    assert removed.json()["detail"] == ADMINS_ONLY
    assert values(kitchen) == ["wiki.home.example"]


# --- Your own network: the refusals --------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "status", "code", "sentence"),
    [
        ("", 422, "bad_entry", own_network.BAD_ENTRY),
        ("   ", 422, "bad_entry", own_network.BAD_ENTRY),
        ("not a name", 422, "bad_entry", own_network.BAD_ENTRY),
        ("http://wiki.home.example/page", 422, "bad_entry", own_network.BAD_ENTRY),
        ("192.168.1.0/99", 422, "bad_entry", own_network.BAD_ENTRY),
        ("x" * 300, 422, "bad_entry", own_network.BAD_ENTRY),
        ("localhost", 422, "always_blocked", own_network.NEVER),
        ("app.localhost", 422, "always_blocked", own_network.NEVER),
        # Written so the international-name mapping makes them "localhost" (review of PR 57).
        (
            "\uff4c\uff4f\uff43\uff41\uff4c\uff48\uff4f\uff53\uff54",
            422,
            "always_blocked",
            own_network.NEVER,
        ),
        (
            "app.\uff4c\uff4f\uff43\uff41\uff4c\uff48\uff4f\uff53\uff54",
            422,
            "always_blocked",
            own_network.NEVER,
        ),
        ("localhost\u200b", 422, "always_blocked", own_network.NEVER),
        ("local\u00adhost", 422, "always_blocked", own_network.NEVER),
        ("127.0.0.1", 422, "always_blocked", own_network.NEVER),
        ("::1", 422, "always_blocked", own_network.NEVER),
        ("169.254.169.254", 422, "always_blocked", own_network.NEVER),
        ("100.100.100.200", 422, "always_blocked", own_network.NEVER),
        ("fd00:ec2::254", 422, "always_blocked", own_network.NEVER),
        ("169.254.0.0/16", 422, "always_blocked", own_network.NEVER),
        ("0.0.0.0/0", 422, "always_blocked", own_network.NEVER),
        ("10.0.0.0/7", 422, "too_wide", own_network.TOO_WIDE),
        ("2001:db8::/16", 422, "too_wide", own_network.TOO_WIDE),
    ],
)
def test_every_refusal_has_its_own_sentence_and_adds_nothing(
    kitchen: TestClient, text: str, status: int, code: str, sentence: str
) -> None:
    response = kitchen.post(LIST, json={"value": text})
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.json()["detail"] == sentence
    assert values(kitchen) == []


def test_the_same_entry_twice(kitchen: TestClient) -> None:
    assert kitchen.post(LIST, json={"value": "wiki.home.example"}).status_code == 201
    for text in ("wiki.home.example", "WIKI.home.example.", " wiki.home.example "):
        response = kitchen.post(LIST, json={"value": text})
        assert response.status_code == 409
        assert response.json()["code"] == "already_listed"
        assert response.json()["detail"] == own_network.ALREADY
    assert kitchen.post(LIST, json={"value": "192.168.1.5/32"}).status_code == 201
    assert kitchen.post(LIST, json={"value": "192.168.1.5"}).status_code == 409
    assert len(values(kitchen)) == 2


def test_a_value_is_needed(kitchen: TestClient) -> None:
    assert kitchen.post(LIST, json={}).status_code == 422
    assert kitchen.post(LIST, json={"value": 5}).status_code == 422
    assert kitchen.post(LIST, json={"value": "a" * 1001}).status_code == 422
    assert values(kitchen) == []


def test_the_list_holds_a_hundred_and_then_says_so(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    for i in range(100):
        assert kitchen.post(LIST, json={"value": f"host{i}.home.example"}).status_code == 201
    response = kitchen.post(LIST, json={"value": "one-more.home.example"})
    assert response.status_code == 409
    assert response.json()["code"] == "list_full"
    assert response.json()["detail"] == own_network.FULL
    assert len(values(kitchen)) == 100
    # A repeat is "already on the list", not "full": the sentence names the real reason.
    assert kitchen.post(LIST, json={"value": "host5.home.example"}).json()["code"] == (
        "already_listed"
    )
    # Another household has its own list of 100.
    assert neighbour.post(LIST, json={"value": "one-more.home.example"}).status_code == 201
    # Taking one off makes room.
    first = kitchen.get(LIST).json()["entries"][0]["id"]
    assert kitchen.delete(f"{LIST}/{first}").status_code == 204
    assert kitchen.post(LIST, json={"value": "one-more.home.example"}).status_code == 201


# --- Your own network: removing -------------------------------------------------------------


def test_an_admin_removes_an_entry(kitchen: TestClient) -> None:
    a = kitchen.post(LIST, json={"value": "wiki.home.example"}).json()
    kitchen.post(LIST, json={"value": "192.168.1.20"})
    response = kitchen.delete(f"{LIST}/{a['id']}")
    assert response.status_code == 204
    assert response.content == b""
    assert values(kitchen) == ["192.168.1.20"]
    again = kitchen.delete(f"{LIST}/{a['id']}")
    assert again.status_code == 404
    assert again.json()["code"] == "not_found"
    assert kitchen.delete(f"{LIST}/99999").status_code == 404
    assert kitchen.delete(f"{LIST}/{2**70}").status_code == 422
    assert kitchen.delete(f"{LIST}/abc").status_code == 422
    # The same text can be added again afterwards.
    assert kitchen.post(LIST, json={"value": "wiki.home.example"}).status_code == 201


def test_an_entry_is_used_by_the_fetcher_straight_away(kitchen: TestClient) -> None:
    entry = kitchen.post(LIST, json={"value": "wiki.home.example"}).json()
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert own_network.load(db, 1).lists_name("wiki.home.example")
    kitchen.delete(f"{LIST}/{entry['id']}")
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert not own_network.load(db, 1).lists_name("wiki.home.example")


# --- Two households ---------------------------------------------------------------------------


def test_one_household_never_sees_or_changes_anothers_list(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    mine = kitchen.post(LIST, json={"value": "wiki.home.example"}).json()
    theirs = neighbour.post(LIST, json={"value": "nas.next-door.example"}).json()
    assert values(kitchen) == ["wiki.home.example"]
    assert values(neighbour) == ["nas.next-door.example"]
    # The same text can be on both lists.
    assert neighbour.post(LIST, json={"value": "wiki.home.example"}).status_code == 201
    # Removing the other household's entry is "not here", and changes nothing.
    response = neighbour.delete(f"{LIST}/{mine['id']}")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"
    assert kitchen.delete(f"{LIST}/{theirs['id']}").status_code == 404
    assert values(kitchen) == ["wiki.home.example"]
    assert values(neighbour) == ["nas.next-door.example", "wiki.home.example"]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert own_network.load(db, 1).lists_name("wiki.home.example")
        assert not own_network.load(db, 1).lists_name("nas.next-door.example")


# --- Logs ------------------------------------------------------------------------------------


def test_the_log_never_holds_an_address(
    kitchen: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        entry = kitchen.post(LIST, json={"value": "secret-wiki.home.example"}).json()
        kitchen.post(LIST, json={"value": "secret-wiki.home.example"})  # refused
        kitchen.post(LIST, json={"value": "10.9.8.7"})
        kitchen.delete(f"{LIST}/{entry['id']}")
        kitchen.put(f"{SWITCHES}/recipe_import", json={"on": True})
    text = "\n".join(r.getMessage() for r in caplog.records)
    assert "secret-wiki" not in text
    assert "10.9.8.7" not in text
    messages = [r.getMessage() for r in caplog.records if r.name.endswith("privacy")]
    assert messages == [
        "Your own network: added",
        "Your own network: added",
        "Your own network: removed",
        "Privacy: recipe import switched on",
    ]


def test_the_day_added_is_the_households_own_day(kitchen: TestClient) -> None:
    entry = kitchen.post(LIST, json={"value": "wiki.home.example"}).json()
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.get(Household, 1).time_zone = "Pacific/Auckland"  # type: ignore[union-attr]
        db.get(OwnNetworkEntry, entry["id"]).added_at = datetime(  # type: ignore[union-attr]
            2026, 10, 22, 23, 30, tzinfo=UTC
        )
        db.commit()
    assert kitchen.get(LIST).json()["entries"][0]["added_on"] == "2026-10-23"
