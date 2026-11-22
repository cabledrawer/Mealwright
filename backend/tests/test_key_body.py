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


def test_try_again_without_the_answers_after_an_ask_once_save_is_the_same_change(
    kitchen: TestClient,
) -> None:
    """The app's "Try again" after a lost answer sends the change ID without the answers the
    saved attempt carried: same change, so a replay (200), applied once (fix round 1)."""
    food = ok(kitchen.post(f"{API}/foods", json={"name": "Toor dal"}), 201)["food"]
    kitchen.post(f"{API}/foods/{food['id']}/sizes", json={"name": "packet", "amount": 500})
    url = f"{API}/foods/{food['id']}"
    key = {"Idempotency-Key": "ask-once-1"}
    asked = kitchen.patch(url, json={"counted_as": "volume"}, headers=key)
    assert asked.status_code == 409 and asked.json()["code"] == "ask_once"
    answer = {"kind": "weight_per_ml", "food_id": food["id"], "grams": 200, "remember": True}
    saved = kitchen.patch(url, json={"counted_as": "volume", "answers": [answer]}, headers=key)
    assert saved.status_code == 200
    again = kitchen.patch(url, json={"counted_as": "volume"}, headers=key)
    assert again.status_code == 200, again.text
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["change"]["id"] == saved.json()["change"]["id"]
    with kitchen.app.state.sessionmaker() as db:
        assert (
            len(list(db.scalars(select(Change).where(Change.idempotency_key == "ask-once-1")))) == 1
        )


def test_answers_are_left_out_of_the_hash_at_any_depth() -> None:
    from mealwright.limits import body_hash

    plain = b'{"running_low_at": {"amount": 1, "unit": "cup"}}'
    nested = (
        b'{"running_low_at": {"amount": 1, "unit": "cup", "answers": [{"grams": 3}]},'
        b' "answers": []}'
    )
    assert body_hash(plain) == body_hash(nested)
    assert body_hash(plain) != body_hash(b'{"running_low_at": {"amount": 2, "unit": "cup"}}')


def test_a_body_nested_too_deep_to_read_is_hashed_as_bytes() -> None:
    """T4 (22 Nov): a body nested deeper than Python reads is hashed as its bytes, as one
    that isn't JSON is, instead of failing the request."""
    from mealwright.limits import body_hash

    for depth in (2_000, 100_000):
        deep = b"[" * depth + b"]" * depth
        assert body_hash(deep) == hashlib.sha256(deep).hexdigest()
