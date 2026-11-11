"""One Cooked it for a whole Batch cook session (0.8 wave 6, B3; cabledrawer 28 Oct and 11 Nov): every
recipe's stock taken as ONE change with one Undo, the tubs per recipe, and the stock after Cooked
it and after Undo the same as doing each recipe's Cooked it alone and undoing it."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_plan import db_of, slot_ids
from test_plan_writes import D1
from test_recipe_list import stock
from test_recipes import food, make

from mealwright.models import CookedRecord, Food, StockLot

API = "/api/v1"


def session_of(client: TestClient, household_id: int = 1) -> tuple[int, list[int]]:
    """Sambar and Chicken chettinad sharing onions and coconut, with stock for both, as one
    session on D1. Returns the session and its batch ids."""
    onion = food(client, "Onion", counted_as="count")
    dal = food(client, "Toor dal")
    chicken = food(client, "Chicken")
    stock(client, onion["id"], 6, "count")
    stock(client, onion["id"], 3, "count")  # a second packet, so the order matters
    stock(client, dal["id"], 500, "g")
    stock(client, chicken["id"], 700, "g")
    sambar = make(
        client,
        "Sambar",
        serves=4,
        lines=[
            {"words": "200 g toor dal", "food_id": dal["id"], "amount": 200, "unit": "g"},
            {"words": "2 onions", "food_id": onion["id"], "amount": 2},
        ],
        steps=[{"text": "Chop the onions."}, {"text": "Pressure cook the dal."}],
    )
    chettinad = make(
        client,
        "Chicken chettinad",
        serves=4,
        lines=[
            {"words": "500 g chicken", "food_id": chicken["id"], "amount": 500, "unit": "g"},
            {"words": "5 onions", "food_id": onion["id"], "amount": 5},
        ],
        steps=[{"text": "Chop the onions."}, {"text": "Simmer for 20 minutes."}],
    )
    body = {
        "date": D1.isoformat(),
        "slot_id": slot_ids(client, household_id)["Dinner"],
        "recipes": [
            {"recipe_id": sambar["id"], "tub_count": 2},
            {"recipe_id": chettinad["id"], "tub_count": 3},
        ],
    }
    made = ok(client.post(f"{API}/batch-cook/sessions", json=body), 201)
    found = ok(client.get(f"{API}/batch-cook/sessions/{made['session_id']}"))
    return int(made["session_id"]), [r["batch_id"] for r in found["recipes"]]


def pantry(client: TestClient) -> dict[str, list[int]]:
    """Each ingredient's packets, by name, oldest first (thousandths)."""
    with db_of(client) as db:
        names = {f.id: f.name for f in db.scalars(select(Food))}
        out: dict[str, list[int]] = {}
        for lot in db.scalars(select(StockLot).order_by(StockLot.id)):
            out.setdefault(names[lot.food_id], []).append(lot.amount_milli)
        return out


def test_one_cooked_it_takes_the_same_stock_as_each_recipe_alone_and_undo_gives_it_back(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    session, _ = session_of(kitchen)
    _, alone = session_of(neighbour, 2)
    start = pantry(kitchen)
    assert pantry(neighbour) == start

    preview = ok(kitchen.post(f"{API}/batch-cook/sessions/{session}/cook/preview", json={}))
    assert [i["recipe_name"] for i in preview["items"]] == ["Sambar", "Chicken chettinad"]
    assert [i["tub_count"] for i in preview["items"]] == [2, 3]
    assert pantry(kitchen) == start  # the preview changes nothing

    done = ok(kitchen.post(f"{API}/batch-cook/sessions/{session}/cook", json={}), 201)
    assert done["change"]["kind"] == "cooked" and done["change"]["can_undo"] is True
    assert len(done["cooked"]) == 2  # a record for each recipe, one change
    assert {c["snapshot"]["name"] for c in done["cooked"]} == {"Sambar", "Chicken chettinad"}

    changes: list[dict[str, Any]] = []
    for batch in alone:
        changes.append(ok(neighbour.post(f"{API}/plan/batches/{batch}/cook", json={}), 201))
    after = pantry(kitchen)
    assert after != start
    assert after == pantry(neighbour)  # the same as cooking each alone

    ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))
    for each in reversed(changes):
        ok(neighbour.post(f"{API}/changes/{each['change']['id']}/undo"))
    assert pantry(kitchen) == start == pantry(neighbour)
    with db_of(kitchen) as db:
        assert db.scalars(select(CookedRecord)).all() == []  # it can be cooked again


def test_it_is_one_group_in_recent_changes(kitchen: TestClient) -> None:
    session, _ = session_of(kitchen)
    done = ok(kitchen.post(f"{API}/batch-cook/sessions/{session}/cook", json={}), 201)
    listed = ok(kitchen.get(f"{API}/changes", params={"area": "pantry"}))["changes"]
    cooked = [c for c in listed if c["kind"] == "cooked"]
    assert [c["id"] for c in cooked] == [done["change"]["id"]]
    assert "Sambar" in cooked[0]["summary"] and "Chicken chettinad" in cooked[0]["summary"]


def test_a_second_cooked_it_is_refused_and_takes_nothing(kitchen: TestClient) -> None:
    session, _ = session_of(kitchen)
    ok(kitchen.post(f"{API}/batch-cook/sessions/{session}/cook", json={}), 201)
    after = pantry(kitchen)
    again = kitchen.post(f"{API}/batch-cook/sessions/{session}/cook", json={})
    assert again.status_code == 409 and again.json()["code"] == "already_cooked"
    assert pantry(kitchen) == after


def test_one_recipe_refused_means_none_is_taken(kitchen: TestClient) -> None:
    session, batches = session_of(kitchen)
    ok(kitchen.post(f"{API}/plan/batches/{batches[0]}/cook", json={}), 201)  # Sambar, alone
    after = pantry(kitchen)
    refused = kitchen.post(f"{API}/batch-cook/sessions/{session}/cook", json={})
    assert refused.status_code == 409
    assert pantry(kitchen) == after  # Chicken chettinad was not taken either


def test_a_retry_with_the_same_key_takes_nothing_more(kitchen: TestClient) -> None:
    session, _ = session_of(kitchen)
    headers = {"Idempotency-Key": "11111111-1111-4111-8111-111111111111"}
    first = ok(
        kitchen.post(f"{API}/batch-cook/sessions/{session}/cook", json={}, headers=headers), 201
    )
    after = pantry(kitchen)
    second = kitchen.post(f"{API}/batch-cook/sessions/{session}/cook", json={}, headers=headers)
    assert second.status_code == 200 and second.json()["change"]["id"] == first["change"]["id"]
    assert pantry(kitchen) == after


def test_only_some_recipes_and_their_own_portions_can_be_asked_for(kitchen: TestClient) -> None:
    session, batches = session_of(kitchen)
    preview = ok(
        kitchen.post(
            f"{API}/batch-cook/sessions/{session}/cook/preview",
            json={"items": [{"batch_id": batches[1], "portions": 8}]},
        )
    )
    assert [i["recipe_name"] for i in preview["items"]] == ["Chicken chettinad"]
    assert preview["items"][0]["proposal"]["portions"] == 8
    twice = kitchen.post(
        f"{API}/batch-cook/sessions/{session}/cook/preview",
        json={"items": [{"batch_id": batches[0]}, {"batch_id": batches[0]}]},
    )
    assert twice.status_code == 422 and twice.json()["code"] == "twice"
    strange = kitchen.post(
        f"{API}/batch-cook/sessions/{session}/cook/preview", json={"items": [{"batch_id": 9999}]}
    )
    assert strange.status_code == 404


def test_the_tubs_of_each_recipe_are_counted_by_where_they_are(kitchen: TestClient) -> None:
    session, _ = session_of(kitchen)
    preview = ok(kitchen.post(f"{API}/batch-cook/sessions/{session}/cook/preview", json={}))
    for item in preview["items"]:
        assert sum(t["count"] for t in item["tubs"]) == item["tub_count"]


def test_the_other_household_and_the_switch(kitchen: TestClient, neighbour: TestClient) -> None:
    session, _ = session_of(kitchen)
    assert (
        neighbour.post(f"{API}/batch-cook/sessions/{session}/cook/preview", json={}).status_code
        == 404
    )
    assert neighbour.post(f"{API}/batch-cook/sessions/{session}/cook", json={}).status_code == 404
    ok(kitchen.patch(f"{API}/household", json={"batch_cook": False}))
    hidden = kitchen.post(f"{API}/batch-cook/sessions/{session}/cook", json={})
    assert hidden.status_code == 409 and hidden.json()["code"] == "batch_cook_hidden"


def test_another_households_batch_cook_is_not_found_in_my_session(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    session, mine = session_of(kitchen)
    _, theirs = session_of(neighbour, 2)
    before = pantry(kitchen)
    for path in ("cook/preview", "cook"):
        refused = kitchen.post(
            f"{API}/batch-cook/sessions/{session}/{path}",
            json={"items": [{"batch_id": mine[0]}, {"batch_id": theirs[0]}]},
        )
        assert refused.status_code == 404 and refused.json()["code"] == "not_found"
    assert pantry(kitchen) == before
