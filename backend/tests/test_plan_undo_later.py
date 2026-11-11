# ruff: noqa: F811  (the fixtures come from other test files and are used by name)
"""F165 (cabledrawer 7 Nov): Undo of an older plan change never overwrites a later one. What has
changed again since stays, and the message says so (F140's words)."""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sync_kit import ok
from test_plan import slot_ids
from test_plan_batches import cook, make, stuff  # noqa: F401
from test_plan_serves import alex, item_of, sambar  # noqa: F401
from test_plan_writes import D1, D2, plan_recipe, undo, view

API = "/api/v1"


@pytest.fixture
def slots(kitchen: TestClient) -> dict[str, int]:
    return slot_ids(kitchen)


def test_serves_2_3_4_undo_of_the_first_leaves_4(
    kitchen: TestClient,
    sambar: int,
    slots: dict[str, int],
) -> None:
    plan = plan_recipe(kitchen, sambar, D1, slots["Dinner"], servings=2)
    url = f"{API}/plan/items/{plan['item_id']}"
    first = ok(kitchen.patch(url, json={"servings": 3}))
    second = ok(kitchen.patch(url, json={"servings": 4}))
    result = undo(kitchen, first)
    assert result["result"] == "nothing"
    assert result["message"].startswith("Nothing to put back for Sambar (")
    assert item_of(kitchen, plan["item_id"])["servings"] == 4
    # The latest change still undoes, back to what it found.
    assert undo(kitchen, second)["result"] == "done"
    assert item_of(kitchen, plan["item_id"])["servings"] == 3


def test_a_meal_moved_thu_fri_sat_undo_of_the_first_leaves_it_on_sat(
    kitchen: TestClient,
    sambar: int,
    slots: dict[str, int],
) -> None:
    plan = plan_recipe(kitchen, sambar, D1, slots["Dinner"])
    url = f"{API}/plan/meals/{plan['meal_id']}/move"
    d3 = D2 + timedelta(days=1)
    first = ok(kitchen.post(url, json={"date": D2.isoformat(), "slot_id": slots["Dinner"]}))
    second = ok(kitchen.post(url, json={"date": d3.isoformat(), "slot_id": slots["Dinner"]}))
    result = undo(kitchen, first)
    assert result["result"] == "nothing"
    assert [m["date"] for m in view(kitchen)["meals"]] == [d3.isoformat()]
    assert undo(kitchen, second)["result"] == "done"
    assert [m["date"] for m in view(kitchen)["meals"]] == [D2.isoformat()]


def test_an_item_moved_twice_undo_of_the_first_leaves_it_where_it_is(
    kitchen: TestClient,
    sambar: int,
    slots: dict[str, int],
) -> None:
    a = plan_recipe(kitchen, sambar, D1, slots["Dinner"])
    plan_recipe(kitchen, sambar, D1, slots["Dinner"])  # so the meal on D1 stays after the move
    first = ok(
        kitchen.post(
            f"{API}/plan/items/{a['item_id']}/move",
            json={"date": D2.isoformat(), "slot_id": slots["Dinner"]},
        )
    )
    ok(
        kitchen.post(
            f"{API}/plan/items/{a['item_id']}/move",
            json={"date": D2.isoformat(), "slot_id": slots["Lunch"]},
        )
    )
    result = undo(kitchen, first)
    assert result["result"] == "nothing"
    lunch = next(m for m in view(kitchen)["meals"] if m["slot_id"] == slots["Lunch"])
    assert [i["id"] for i in lunch["items"]] == [a["item_id"]]


def test_who_is_eating_changed_twice_undo_of_the_first_leaves_the_second(
    kitchen: TestClient,
    sambar: int,
    alex: int,
    slots: dict[str, int],
) -> None:
    plan = plan_recipe(kitchen, sambar, D1, slots["Dinner"])
    url = f"{API}/plan/meals/{plan['meal_id']}/eaters"
    first = ok(kitchen.put(url, json={"login_ids": [alex]}))
    second = ok(kitchen.put(url, json={"login_ids": [1, alex]}))
    assert undo(kitchen, first)["result"] == "nothing"
    assert view(kitchen)["meals"][0]["eater_login_ids"] == [1, alex]
    assert undo(kitchen, second)["result"] == "done"
    assert view(kitchen)["meals"][0]["eater_login_ids"] == [alex]


def test_a_meal_slot_hidden_then_shown_undo_of_the_hide_leaves_it_shown(
    kitchen: TestClient, slots: dict[str, int]
) -> None:
    url = f"{API}/meal-slots/{slots['Dinner']}"
    hide = ok(kitchen.patch(url, json={"enabled": False}))
    ok(kitchen.patch(url, json={"enabled": True}))
    assert undo(kitchen, hide)["result"] == "nothing"
    dinner = next(s for s in kitchen.get(f"{API}/meal-slots").json() if s["id"] == slots["Dinner"])
    assert dinner["enabled"] is True


def test_a_tub_given_to_someone_else_since_is_not_taken_back(
    kitchen: TestClient,
    cook: dict,
    alex: int,
) -> None:
    make(kitchen, cook["item_id"], tub_count=1, pattern="pick")
    tub = view(kitchen)["tubs"][0]
    url = f"{API}/plan/tubs/{tub['id']}"
    first = ok(kitchen.patch(url, json={"member_login_id": alex}))
    ok(kitchen.patch(url, json={"member_login_id": 1}))
    result = undo(kitchen, first)
    assert result["result"] == "nothing"
    assert view(kitchen)["tubs"][0]["member_login_id"] == 1


def test_a_tub_given_another_use_by_since_the_cooking_moved_keeps_it(
    kitchen: TestClient, cook: dict, slots: dict[str, int]
) -> None:
    from test_plan_batches import _batch_row, _move_meal

    made = make(kitchen, cook["item_id"])
    tub = view(kitchen)["tubs"][0]["id"]
    moved = _move_meal(
        kitchen, cook["meal_id"], (D1 + timedelta(days=5)).isoformat(), slots["Dinner"]
    )
    assert moved.status_code == 200, moved.text
    later = (D1 + timedelta(days=20)).isoformat()
    ok(kitchen.patch(f"{API}/plan/tubs/{tub}", json={"use_by": later}))
    assert undo(kitchen, moved.json())["result"] == "partly"
    cooked_on, use_bys = _batch_row(kitchen, made["batch_id"])
    assert cooked_on == D1
    assert later in {u.isoformat() for u in use_bys}


def test_undo_of_to_the_freezer_keeps_a_use_by_set_since(
    kitchen: TestClient, cook: dict, alex: int
) -> None:
    """Review r1 M1: "To the freezer" records what it left, so its Undo puts the tub back in
    the fridge but keeps a use-by (and whose) set since."""
    make(kitchen, cook["item_id"], tub_count=1, pattern="pick")
    tub = view(kitchen)["tubs"][0]
    frozen = ok(kitchen.post(f"{API}/plan/tubs/{tub['id']}/freezer"))
    later = (D1 + timedelta(days=40)).isoformat()
    url = f"{API}/plan/tubs/{tub['id']}"
    ok(kitchen.patch(url, json={"use_by": later, "member_login_id": alex}))
    assert undo(kitchen, frozen)["result"] == "partly"
    now = view(kitchen)["tubs"][0]
    assert (now["use_by"], now["member_login_id"]) == (later, alex)
    assert now["place_id"] == tub["place_id"]


def test_a_tub_edit_of_two_fields_puts_back_the_one_not_changed_since(
    kitchen: TestClient, cook: dict, alex: int
) -> None:
    """Review r1 L2: a tub edit of whose and use-by, then whose again: Undo puts the use-by
    back and says "partly", not "nothing"."""
    make(kitchen, cook["item_id"], tub_count=1, pattern="pick")
    tub = view(kitchen)["tubs"][0]
    url = f"{API}/plan/tubs/{tub['id']}"
    later = (D1 + timedelta(days=9)).isoformat()
    first = ok(kitchen.patch(url, json={"use_by": later, "member_login_id": alex}))
    ok(kitchen.patch(url, json={"member_login_id": 1}))
    result = undo(kitchen, first)
    assert result["result"] == "partly"
    now = view(kitchen)["tubs"][0]
    assert (now["use_by"], now["member_login_id"]) == (tub["use_by"], 1)
