"""A recipe that was cooked can't be taken off, moved or re-served while it is part of a
part-cooked meal (F157 review): the meal is still planned, so `_planned` no longer guards it, and
the item's delete would cascade to its cooked record (the pantry would be taken twice)."""

from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sync_kit import ok
from test_cooked_parts import API, cooked_flags, press, records, two_in_a_meal
from test_cooked_undo import status_of
from test_history import wren  # noqa: F401 (a fixture)
from test_plan import slot_ids

WORDS = "Undo “Cooked it” first."


def part_cooked(client: TestClient) -> tuple[int, int, int]:
    _dal, meal, khichdi, soup = two_in_a_meal(client)
    press(client, meal, soup)
    return meal, khichdi, soup


def refused(r: Any) -> None:
    assert r.status_code == 409
    body = r.json()
    assert body["code"] == "already_cooked" and WORDS in body["detail"], body


def tomorrow(client: TestClient) -> dict[str, Any]:
    return {
        "date": (date.today() + timedelta(days=1)).isoformat(),
        "slot_id": slot_ids(client)["Dinner"],
    }


def test_a_cooked_item_cant_be_removed(kitchen: TestClient) -> None:
    _meal, khichdi, soup = part_cooked(kitchen)
    refused(kitchen.delete(f"{API}/plan/items/{soup}"))
    assert records(kitchen) == {soup}
    assert ok(kitchen.delete(f"{API}/plan/items/{khichdi}"))  # the uncooked one still goes
    assert cooked_flags(kitchen) == {soup: True}


def test_a_cooked_item_cant_be_moved_or_re_served(kitchen: TestClient) -> None:
    meal, khichdi, soup = part_cooked(kitchen)
    refused(
        kitchen.post(f"{API}/plan/items/{soup}/move", json={**tomorrow(kitchen), "mode": "move"})
    )
    refused(kitchen.patch(f"{API}/plan/items/{soup}", json={"servings": 3}))
    refused(
        kitchen.post(f"{API}/plan/meals/{meal}/move", json={**tomorrow(kitchen), "mode": "move"})
    )
    # The uncooked recipe is its own; a copy of the cooked one is harmless.
    assert ok(kitchen.patch(f"{API}/plan/items/{khichdi}", json={"servings": 3}))["change"]
    assert ok(
        kitchen.post(f"{API}/plan/items/{soup}/move", json={**tomorrow(kitchen), "mode": "copy"})
    )
    assert records(kitchen) == {soup} and status_of(kitchen, meal) == "planned"


def test_a_meal_holding_a_cooked_item_cant_be_removed(kitchen: TestClient) -> None:
    meal, _khichdi, soup = part_cooked(kitchen)
    refused(kitchen.delete(f"{API}/plan/meals/{meal}"))
    assert records(kitchen) == {soup}


def test_undo_of_planning_a_cooked_item_leaves_it(kitchen: TestClient) -> None:
    _dal, meal, _khichdi, soup = two_in_a_meal(kitchen)
    press(kitchen, meal, soup)
    changes = ok(kitchen.get(f"{API}/changes"))["changes"]
    planned = [c for c in changes if c["kind"] == "plan_added" and "soup" in c["summary"]]
    assert planned
    kitchen.post(f"{API}/changes/{planned[0]['id']}/undo")
    assert records(kitchen) == {soup}
