"""A change sent again with the same Idempotency-Key must carry the same body (0.9.5,
proposed, for cabledrawer): the same body is the honest retry, a different one is the client's
mistake and is refused, never applied, never silently accepted."""

import hashlib
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok

from mealwright.models import Change, Food

API = "/api/v1"
KEY = {"Idempotency-Key": "key-body-1"}


def foods(kitchen: TestClient) -> list[str]:
    with kitchen.app.state.sessionmaker() as db:
        return sorted(db.scalars(select(Food.name)))


def test_the_same_body_is_the_honest_replay(kitchen: TestClient) -> None:
    first = kitchen.post(f"{API}/foods", json={"name": "Toor dal"}, headers=KEY)
    again = kitchen.post(f"{API}/foods", json={"name": "Toor dal"}, headers=KEY)
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["change"]["id"] == first.json()["change"]["id"]


def test_a_different_body_with_the_same_key_is_refused_and_nothing_changes(
    kitchen: TestClient,
) -> None:
    assert kitchen.post(f"{API}/foods", json={"name": "Toor dal"}, headers=KEY).status_code == 201
    response = kitchen.post(f"{API}/foods", json={"name": "Moong dal"}, headers=KEY)
    assert response.status_code == 409
    assert response.json()["code"] == "key_reused"
    assert response.json()["detail"] == "That change ID was already used for something else."
    assert foods(kitchen) == ["Toor dal"]


def test_the_same_json_with_keys_in_another_order_is_the_same_body(kitchen: TestClient) -> None:
    one = '{"name": "Toor dal", "staple": true}'
    two = '{ "staple" : true,\n "name":"Toor dal" }'
    json_type = {"Content-Type": "application/json", **KEY}
    assert kitchen.post(f"{API}/foods", content=one, headers=json_type).status_code == 201
    again = kitchen.post(f"{API}/foods", content=two, headers=json_type)
    assert again.status_code == 200
    assert foods(kitchen) == ["Toor dal"]


def test_a_request_with_no_body_replays_and_stores_the_hash_of_empty(
    kitchen: TestClient,
) -> None:
    made = ok(kitchen.post(f"{API}/foods", json={"name": "Toor dal"}), 201)
    path = f"{API}/changes/{made['change']['id']}/undo"
    first = kitchen.post(path, headers={"Idempotency-Key": "undo-1"})
    again = kitchen.post(path, headers={"Idempotency-Key": "undo-1"})
    assert first.status_code == 200 and first.json()["result"] == "done"
    assert again.headers["Idempotent-Replayed"] == "true"
    with kitchen.app.state.sessionmaker() as db:
        row = db.scalars(select(Change).where(Change.idempotency_key == "undo-1")).one()
        assert row.body_hash == hashlib.sha256(b"").hexdigest()


def test_an_old_row_with_no_hash_is_checked_by_method_and_path_only(kitchen: TestClient) -> None:
    kitchen.post(f"{API}/foods", json={"name": "Toor dal"}, headers=KEY)
    with kitchen.app.state.sessionmaker() as db:
        change = db.scalars(select(Change).where(Change.idempotency_key == "key-body-1")).one()
        change.body_hash = None
        db.commit()
    again = kitchen.post(f"{API}/foods", json={"name": "Anything else"}, headers=KEY)
    assert again.status_code == 200
    assert again.headers["Idempotent-Replayed"] == "true"
    assert foods(kitchen) == ["Toor dal"]


def test_two_households_using_the_same_key_do_not_meet(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    assert kitchen.post(f"{API}/foods", json={"name": "Toor dal"}, headers=KEY).status_code == 201
    other: Any = neighbour.post(f"{API}/foods", json={"name": "Moong dal"}, headers=KEY)
    assert other.status_code == 201
    assert "Idempotent-Replayed" not in other.headers
