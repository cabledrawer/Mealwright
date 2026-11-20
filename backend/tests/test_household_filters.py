"""The batched reads keep every query to the household (0.9.5 speed work). Rows of household A
that point at household B's ingredient, pack size, other name and list line are written straight
into the database (nothing in the API can make them); each batched read, asked as A, must show
nothing of B. Each of the six household filters added with the batching is needed for one of
these checks: take any one away and a check below fails (tried by hand, see the commit)."""

import json
import uuid
from typing import Any

from fastapi.testclient import TestClient
from load_kit import API
from sqlalchemy import select
from sync_kit import counter, db, ok, one

from mealwright.models import (
    FoodName,
    FoodSize,
    ListItem,
    ListTick,
    Place,
    StockLot,
    SyncAction,
)

MARK = "Zzz"


def own_food(kitchen: TestClient) -> dict[str, Any]:
    made = ok(
        kitchen.post(f"{API}/foods", json={"name": "Own flour", "counted_as": "weight"}), 201
    )["food"]
    ok(
        kitchen.post(
            f"{API}/foods/{made['id']}/sizes",
            json={"name": "bag", "amount": {"amount": 1, "unit": "kg"}, "usual": True},
        ),
        201,
    )
    return dict(made)


def main_list(kitchen: TestClient) -> str:
    lists = ok(kitchen.get(f"{API}/shopping/lists"))["lists"]
    return str(next(row["id"] for row in lists if row["main"]))


def neighbours_things(neighbour: TestClient) -> tuple[dict[str, Any], int]:
    theirs = ok(neighbour.post(f"{API}/foods", json={"name": f"{MARK} neighbour ingredient"}), 201)[
        "food"
    ]
    size = ok(
        neighbour.post(
            f"{API}/foods/{theirs['id']}/sizes",
            json={"name": f"{MARK}pack", "amount": {"amount": 500, "unit": "g"}},
        ),
        201,
    )
    sizes = ok(neighbour.get(f"{API}/foods/{theirs['id']}"))["sizes"]
    assert size is not None
    return dict(theirs), int(sizes[0]["id"])


def shown(kitchen: TestClient, path: str) -> str:
    return json.dumps(ok(kitchen.get(API + path)))


def test_a_stray_size_name_tick_and_line_of_another_household_never_show(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    mine = own_food(kitchen)
    lst = main_list(kitchen)
    line = ok(
        kitchen.post(
            f"{API}/shopping/lists/{lst}/items",
            json={"food_id": mine["id"], "amount": {"amount": 300, "unit": "g"}},
        ),
        201,
    )["item"]["id"]
    one(kitchen, "tick", counter(kitchen), item_id=line)
    tick_id = next(
        row["id"] for row in ok(kitchen.get(f"{API}/shopping/sync"))["items"][0]["ticks"]
    )
    theirs, their_size = neighbours_things(neighbour)
    with db(kitchen) as s:
        # B's size and other name for MY ingredient (PackReads: sizes, names).
        s.add(
            FoodSize(
                household_id=2,
                food_id=mine["id"],
                name=f"{MARK}size",
                plural=f"{MARK}sizes",
                amount_milli=777_000,
            )
        )
        s.add(FoodName(household_id=2, food_id=mine["id"], name=f"{MARK} alias"))
        # A line of mine that points at B's ingredient and size (visible_foods, the ingredients
        # read in changes_since).
        s.add(
            ListItem(
                id=str(uuid.uuid4()),
                household_id=1,
                list_id=lst,
                food_id=theirs["id"],
                amount_milli=300_000,
                size_id=their_size,
                source="typed",
                added_by_name="x",
            )
        )
        # B's purchase of MY line, and B's "found at home" action with MY purchase's ID
        # (_ticks_by_item).
        s.add(ListTick(household_id=2, id="zz-b-tick", item_id=line, login_name=f"{MARK} stranger"))
        s.add(
            SyncAction(
                household_id=2,
                id=tick_id,
                seq=90_000,
                kind="found_at_home",
                login_name="x",
                payload={},
                payload_hash="0",
                status="applied",
            )
        )
        s.commit()

    changes = ok(kitchen.get(f"{API}/shopping/sync?since=0"))
    text = json.dumps(changes)
    assert MARK not in text and "zzz" not in text.lower()
    row = next(r for r in changes["items"] if r["id"] == line)
    assert [t["id"] for t in row["ticks"]] == [tick_id]  # only my own purchase
    assert row["ticks"][0]["found"] is False  # B's action with the same ID doesn't count
    stray = next(r for r in changes["items"] if r["id"] != line)
    # Nothing of B's ingredient was read for it: no words for the amount, no pack line.
    assert stray["display"] is None and stray["pack"] is None
    assert all(f["id"] != theirs["id"] for f in changes["foods"])
    own = next(f for f in changes["foods"] if f["id"] == mine["id"])
    assert [s["name"] for s in own["sizes"]] == ["bag"] and own["other_names"] == []

    for path in (f"/shopping/lists/{lst}", "/foods?limit=500"):
        assert MARK not in shown(kitchen, path) and "zzz" not in shown(kitchen, path).lower()
    lists = ok(kitchen.get(f"{API}/shopping/lists"))["lists"]
    assert (
        next(r for r in lists if r["main"])["to_buy"]
        + next(r for r in lists if r["main"])["ticked"]
        == 1
    )  # one line of mine; the stray one is not counted


def test_a_packet_of_mine_that_points_at_another_households_ingredient_is_not_shown(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    own_food(kitchen)
    theirs, their_size = neighbours_things(neighbour)
    with db(kitchen) as s:
        place = s.scalars(select(Place).where(Place.household_id == 1)).first()
        assert place is not None
        s.add(
            StockLot(
                household_id=1,
                food_id=theirs["id"],
                place_id=place.id,
                amount_milli=500_000,
                size_id=their_size,
            )
        )
        s.commit()
    for path in ("/pantry", "/pantry/use-soon", "/today"):
        got = kitchen.get(API + path)
        assert MARK not in got.text, path
