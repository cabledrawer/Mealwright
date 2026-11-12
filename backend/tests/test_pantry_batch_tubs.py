"""F230 (cabledrawer 12 Nov): the Pantry's Fridge lists the tubs of a Batch cook session only after
that session's Cooked it. A Cook once tub (no session) is listed as before."""

from typing import Any

from fastapi.testclient import TestClient
from sync_kit import ok
from test_batch_cooked import session_of
from test_cook_ahead import plan_ahead

API = "/api/v1"


def pantry_tubs(client: TestClient) -> int:
    shown: dict[str, Any] = ok(client.get(f"{API}/pantry"))
    return int(shown["counts"]["tubs"])


def listed(client: TestClient) -> list[str]:
    shown: dict[str, Any] = ok(client.get(f"{API}/pantry"))
    return [t["recipe_name"] for p in shown["places"] for t in p["tubs"]]


def soon(client: TestClient) -> list[str]:
    shown: dict[str, Any] = ok(client.get(f"{API}/pantry/use-soon"))
    return [t["recipe_name"] for t in shown["tubs"]]


def test_a_session_not_cooked_yet_has_no_tubs_in_the_pantry(kitchen: TestClient) -> None:
    session_of(kitchen)
    # The tubs exist (the plan's "tubs left" has them) but the food is not cooked yet.
    assert ok(kitchen.get(f"{API}/plan/tubs-left"))["tubs"]
    assert pantry_tubs(kitchen) == 0
    assert listed(kitchen) == []
    assert soon(kitchen) == []


def test_they_are_listed_after_the_sessions_cooked_it(kitchen: TestClient) -> None:
    session, _ = session_of(kitchen)
    ok(kitchen.post(f"{API}/batch-cook/sessions/{session}/cook", json={}), 201)
    left = ok(kitchen.get(f"{API}/plan/tubs-left"))["tubs"]
    assert pantry_tubs(kitchen) == len(left) > 0
    assert set(listed(kitchen)) == {"Sambar", "Chicken chettinad"}


def test_one_recipe_of_the_session_cooked_on_its_own_lists_only_its_tubs(
    kitchen: TestClient,
) -> None:
    _, batches = session_of(kitchen)
    ok(kitchen.post(f"{API}/plan/batches/{batches[0]}/cook", json={}), 201)  # Sambar, alone
    assert set(listed(kitchen)) == {"Sambar"}


def test_a_cook_once_batch_outside_a_session_is_listed_before_it_is_cooked(
    kitchen: TestClient,
) -> None:
    _dal, _meal, item, _day = plan_ahead(kitchen)
    ok(
        kitchen.post(f"{API}/plan/items/{item}/batch", json={"tub_count": 2, "pattern": "pick"}),
        201,
    )
    assert listed(kitchen) == ["Zorba khichdi"]
    assert pantry_tubs(kitchen) == 2
