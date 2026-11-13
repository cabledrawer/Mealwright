"""F230 (cabledrawer 12 Nov): a tub is never put in a meal at or before its batch's cook meal."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sync_kit import ok
from test_batch_cooked import session_of
from test_plan import slot_ids
from test_plan_writes import D1, TODAY

API = "/api/v1"


def one_tub(kitchen: TestClient) -> int:
    session_of(kitchen)  # cooked on D1 at Dinner
    tubs: list[dict[str, Any]] = ok(kitchen.get(f"{API}/plan/tubs-left"))["tubs"]
    return int(tubs[0]["id"])


def place(kitchen: TestClient, tub: int, day: Any, slot: str):  # type: ignore[no-untyped-def]
    return kitchen.post(
        f"{API}/plan/tubs/{tub}/place",
        json={"date": day.isoformat(), "slot_id": slot_ids(kitchen)[slot]},
    )


def test_a_tub_is_refused_two_days_before_its_cook_day(kitchen: TestClient) -> None:
    tub = one_tub(kitchen)
    refused = place(kitchen, tub, D1 - timedelta(days=2), "Lunch")
    assert refused.status_code == 422 and refused.json()["code"] == "not_after_cook"


def test_a_tub_is_refused_at_the_cook_meal_and_before_it_that_day(kitchen: TestClient) -> None:
    tub = one_tub(kitchen)
    assert place(kitchen, tub, D1, "Dinner").status_code == 422
    assert place(kitchen, tub, D1, "Lunch").status_code == 422


def test_a_tub_is_fine_the_next_day(kitchen: TestClient) -> None:
    tub = one_tub(kitchen)
    ok(place(kitchen, tub, D1 + timedelta(days=1), "Lunch"))


def test_moving_a_placed_tub_to_before_the_cook_is_refused(kitchen: TestClient) -> None:
    tub = one_tub(kitchen)
    ok(place(kitchen, tub, D1 + timedelta(days=1), "Lunch"))
    plan = ok(
        kitchen.get(
            f"{API}/plan",
            params={"from": D1.isoformat(), "to": (D1 + timedelta(days=3)).isoformat()},
        )
    )
    item = next(i for m in plan["meals"] for i in m["items"] if i["tub_id"] == tub)
    moved = kitchen.post(
        f"{API}/plan/items/{item['id']}/move",
        json={
            "date": (D1 - timedelta(days=1)).isoformat(),
            "slot_id": slot_ids(kitchen)["Lunch"],
            "mode": "move",
        },
    )
    assert moved.status_code == 422 and moved.json()["code"] == "not_after_cook"
    # And placing it again that way is refused too (the "already in a meal" branch).
    again = place(kitchen, tub, D1, "Dinner")
    assert again.status_code == 422


def test_a_session_cooked_early_offers_its_tubs_from_the_day_it_was_cooked(
    kitchen: TestClient,
) -> None:
    """L1 (whole-0.9 review): cooked three days ahead of its planned day, its tubs count from
    the day they were really cooked, and the list says so."""
    sid, _ = session_of(kitchen)  # planned for D1 (today + 3) at Dinner
    ok(kitchen.post(f"{API}/batch-cook/sessions/{sid}/cook", json={}), 201)  # cooked today
    tubs: list[dict[str, Any]] = ok(kitchen.get(f"{API}/plan/tubs-left"))["tubs"]
    assert tubs[0]["cooked_on"] == TODAY.isoformat()
    tub = int(tubs[0]["id"])
    ok(place(kitchen, tub, TODAY + timedelta(days=1), "Lunch"))
    ok(place(kitchen, tub, D1, "Lunch"))  # the planned day itself is fine now


def test_a_batch_cooked_on_its_own_early_offers_its_tubs_the_next_day(kitchen: TestClient) -> None:
    _, batches = session_of(kitchen)
    ok(kitchen.post(f"{API}/plan/batches/{batches[0]}/cook", json={}), 201)
    tubs: list[dict[str, Any]] = ok(kitchen.get(f"{API}/plan/tubs-left"))["tubs"]
    mine = next(t for t in tubs if t["batch_id"] == batches[0])
    ok(place(kitchen, int(mine["id"]), TODAY + timedelta(days=1), "Lunch"))


def test_a_tub_cooked_early_is_still_refused_before_the_day_it_was_cooked(
    kitchen: TestClient,
) -> None:
    sid, _ = session_of(kitchen)
    ok(kitchen.post(f"{API}/batch-cook/sessions/{sid}/cook", json={}), 201)
    tubs: list[dict[str, Any]] = ok(kitchen.get(f"{API}/plan/tubs-left"))["tubs"]
    refused = place(kitchen, int(tubs[0]["id"]), TODAY - timedelta(days=1), "Lunch")
    assert refused.status_code == 422 and refused.json()["code"] == "not_after_cook"
