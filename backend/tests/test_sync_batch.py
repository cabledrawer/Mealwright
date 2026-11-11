"""The batch endpoint and catching up (docs/dev/sync-protocol.md 4.1, 5.1 to 5.6)."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select, update
from sync_kit import (
    API,
    PHONE_A,
    PHONE_B,
    PHONE_R,
    action,
    changes,
    counter,
    db,
    food,
    item_row,
    login_id,
    main_id,
    new_id,
    ok,
    one,
    person,
    send,
)

from mealwright.models import Change, Food, FoodSize, ListItem, ShoppingList, SyncAction


def _rows(kitchen: TestClient) -> int:
    with db(kitchen) as session:
        return int(session.scalar(select(func.count()).select_from(SyncAction)) or 0)


# --- The envelope (4.1, 5.6) ---------------------------------------------------------------------


def test_needs_sign_in(client: TestClient) -> None:
    body = {
        "protocol": 1,
        "device_id": PHONE_A,
        "login_id": 1,
        "since": 0,
        "sent_at": "2026-10-17T10:00:00Z",
        "actions": [],
    }
    assert client.post(f"{API}/shopping/actions", json=body).status_code == 401
    assert client.get(f"{API}/shopping/changes").status_code == 401


def test_sy35_another_logins_queue_is_refused_whole(kitchen: TestClient) -> None:
    alex = person(kitchen)
    milk = food(kitchen, "Milk")
    start, rows = counter(kitchen), _rows(kitchen)
    main = main_id(kitchen)
    queue = [action("add", list_id=main, item_id=new_id(), food_id=milk["id"]) for _ in range(3)]
    answer = send(kitchen, *queue, login=login_id(alex), status=409)
    assert answer["code"] == "other_login"
    assert answer["detail"] == "These changes were made by another login."
    assert counter(kitchen) == start and _rows(kitchen) == rows


def test_protocol_must_be_1(kitchen: TestClient) -> None:
    body = {
        "protocol": 2,
        "device_id": PHONE_A,
        "login_id": login_id(kitchen),
        "since": 0,
        "sent_at": "2026-10-17T10:00:00Z",
        "actions": [],
    }
    answer = ok(kitchen.post(f"{API}/shopping/actions", json=body), 422)
    assert answer["code"] == "bad_protocol"


def test_at_most_100_actions(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    start = counter(kitchen)
    queue = [action("add", list_id=main, item_id=new_id(), food_id=milk["id"]) for _ in range(101)]
    assert send(kitchen, *queue, status=413)["code"] == "too_many"
    assert counter(kitchen) == start
    assert len(send(kitchen, *queue[:100])["results"]) == 100


def test_a_malformed_envelope_is_a_plain_422(kitchen: TestClient) -> None:
    body = {"protocol": 1, "login_id": login_id(kitchen), "since": 0, "actions": []}
    assert kitchen.post(f"{API}/shopping/actions", json=body).status_code == 422


def test_sy60_a_bad_action_is_refused_and_the_rest_apply(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    start = counter(kitchen)
    item = new_id()
    answer = send(
        kitchen,
        action("teleport", item_id=item),
        action("tick", item_id=item, colour="red"),
        action("add", list_id=main, item_id=item, food_id=milk["id"]),
        {"kind": "add"},
    )
    unknown, tick, added, bare = answer["results"]
    assert unknown["status"] == "refused" and unknown["reason"] == "bad_action"
    assert tick["status"] == "refused" and tick["reason"] == "bad_action"
    assert "colour" in tick["message"]
    assert bare["status"] == "refused" and bare["id"] == ""
    assert added["status"] == "applied" and added["seq"] == start + 1
    assert counter(kitchen) == start + 1


# --- Results, repeats and the counter (5.2 to 5.4) -----------------------------------------------


def test_results_and_changes_come_back_together(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk", counted_as="volume")
    start = counter(kitchen)
    item = new_id()
    answer = send(
        kitchen,
        action("add", list_id=main, item_id=item, food_id=milk["id"], amount=2000),
        action("set_amount", item_id=item, amount=3000),
        since=start,
    )
    added, changed = answer["results"]
    assert added == {
        "id": added["id"],
        "seq": start + 1,
        "status": "applied",
        "reason": None,
        "repeat": False,
        "item_id": item,
        "food_id": milk["id"],
        "change": added["change"],
        "message": None,
    }
    assert added["change"]["kind"] == "item_added"
    assert changed["seq"] == start + 2 and changed["change"]["kind"] == "item_amount"
    got = answer["changes"]
    assert got["cursor"] == start + 2 and got["reset"] is False
    row = item_row(got, item)
    assert row["amount"] == 3000 and row["display"] == "3\u00a0L" and row["hand_edited"] is True
    assert row["version"] == start + 2 and row["ticks"] == []
    assert row["added_by"] == {"login_id": login_id(kitchen), "name": "Tess"}


def test_sy17_a_lost_answer_resent_is_all_repeats(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk", counted_as="volume")
    onions = food(kitchen, "Onions", counted_as="count")
    item, gone = new_id(), new_id()
    send(kitchen, action("add", list_id=main, item_id=gone, food_id=onions["id"], amount=5))
    queue = [
        action("add", list_id=main, item_id=item, food_id=milk["id"], amount=2000),
        action("set_amount", item_id=item, amount=3000),
        action("delete", item_id=gone),
    ]
    first = send(kitchen, *queue)["results"]
    after = counter(kitchen)
    again = send(kitchen, *queue)["results"]
    assert counter(kitchen) == after
    assert [r["seq"] for r in again] == [r["seq"] for r in first]
    assert all(r["repeat"] for r in again) and not any(r["repeat"] for r in first)
    assert [r["status"] for r in again] == [r["status"] for r in first]


def test_sy18_a_longer_batch_after_a_lost_answer(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk", counted_as="volume")
    queue = [
        action("add", list_id=main, item_id=new_id(), food_id=milk["id"], amount=n * 1000)
        for n in range(1, 6)
    ]
    send(kitchen, *queue[:3])
    start = counter(kitchen)
    results = send(kitchen, *queue)["results"]
    assert [r["repeat"] for r in results] == [True, True, True, False, False]
    assert [r["seq"] for r in results[3:]] == [start + 1, start + 2]


def test_the_same_id_twice_in_one_batch_is_a_repeat(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    add = action("add", list_id=main, item_id=new_id(), food_id=milk["id"])
    first, second = send(kitchen, add, add)["results"]
    assert second["repeat"] is True and second["seq"] == first["seq"]


def test_sy20_an_id_reused_for_something_else(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk", counted_as="volume")
    item = new_id()
    x = action("add", list_id=main, item_id=item, food_id=milk["id"], amount=2000)
    send(kitchen, x)
    reused = one(kitchen, "delete", id=x["id"], item_id=item)
    assert reused["status"] == "refused" and reused["reason"] == "key_reused"
    assert reused["message"] == "That change ID was already used for something else."
    # A 0.2 write's Idempotency-Key, then an action with that ID.
    ok(
        kitchen.post(
            f"{API}/stock",
            json={"food_id": milk["id"], "amount": {"amount": 1, "unit": "l"}},
            headers={"Idempotency-Key": "key-y"},
        ),
        201,
    )
    y = one(kitchen, "delete", id="key-y", item_id=item)
    assert y["reason"] == "key_reused"
    # A 0.2 write whose key is an action ID.
    clash = kitchen.post(
        f"{API}/stock",
        json={"food_id": milk["id"], "amount": {"amount": 1, "unit": "l"}},
        headers={"Idempotency-Key": x["id"]},
    )
    assert clash.status_code == 409 and clash.json()["code"] == "key_reused"
    assert item_row(changes(kitchen), item)["amount"] == 2000


def test_refused_actions_take_no_number(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    item = new_id()
    send(kitchen, action("add", list_id=main, item_id=item, food_id=milk["id"]))
    start = counter(kitchen)
    results = send(
        kitchen,
        action("add", list_id=main, item_id=item, food_id=milk["id"]),  # id_taken
        action("remove_list", list_id=main),  # main_list
        action("set_amount", item_id=item, amount=2_000_000_000),  # too_big
    )["results"]
    assert [r["reason"] for r in results] == ["id_taken", "main_list", "too_big"]
    assert all(r["seq"] is None for r in results)
    assert counter(kitchen) == start


# --- Lists (4.2) and new ingredients (4.4) -------------------------------------------------------


def test_sy33_the_main_list_is_renamed_never_removed(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    removed, renamed = send(
        kitchen,
        action("remove_list", list_id=main),
        action("rename_list", list_id=main, name="Our week"),
    )["results"]
    assert removed["status"] == "refused" and removed["reason"] == "main_list"
    assert renamed["status"] == "applied"
    lists = changes(kitchen)["lists"]
    assert [(row["name"], row["main"], row["removed"]) for row in lists] == [
        ("Our week", True, False)
    ]


def test_new_food_makes_the_ingredient(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    item = new_id()
    result = one(
        kitchen,
        "add",
        list_id=main,
        item_id=item,
        new_food={"name": "Tahini", "counted_as": "weight"},
    )
    assert result["status"] == "applied" and result["food_id"] is not None
    got = result["_answer"]["changes"]
    tahini = next(row for row in got["foods"] if row["id"] == result["food_id"])
    assert tahini["name"] == "Tahini" and tahini["counted_as"] == "weight"
    row = item_row(got, item)
    assert row["food_id"] == tahini["id"] and row["amount"] is None  # weight, no size: blank
    # The same name again joins it.
    again = one(
        kitchen,
        "add",
        list_id=main,
        item_id=new_id(),
        new_food={"name": "tahini", "counted_as": "count"},
    )
    assert again["status"] == "merged" and again["food_id"] == tahini["id"]


def test_dismiss_note_of_a_note_that_isnt_there_is_ignored_quietly(kitchen: TestClient) -> None:
    result = one(kitchen, "dismiss_note", note_id=999)
    assert result["status"] == "ignored" and result["reason"] == "gone"
    assert result["message"] is None


# --- Catching up (5.5) ---------------------------------------------------------------------------


def test_changes_since_gives_only_newer_rows_and_a_tombstone(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk, eggs = food(kitchen, "Milk"), food(kitchen, "Eggs")
    keep, gone = new_id(), new_id()
    send(
        kitchen,
        action("add", list_id=main, item_id=keep, food_id=eggs["id"]),
        action("add", list_id=main, item_id=gone, food_id=milk["id"]),
    )
    since = counter(kitchen)
    send(kitchen, action("delete", item_id=gone))
    got = changes(kitchen, since)
    assert got["reset"] is False and got["lists"] == [] and got["foods"] == []
    assert got["items"] == [
        {
            "id": gone,
            "list_id": main,
            "deleted": True,
            "version": since + 1,
            "food_id": milk["id"],
            "shop_id": None,
            "removed_by": "Tess",
        }
    ]
    full = changes(kitchen)
    assert full["reset"] is True
    assert [row["id"] for row in full["items"]] == [keep]  # no tombstones in a full copy
    assert {row["key"] for row in full["aisles"]} >= {"veg_fruit", "other"}
    assert {row["name"] for row in full["places"]} >= {"Fridge", "Freezer", "Cupboard"}
    assert full["people"] == [{"login_id": login_id(kitchen), "name": "Tess"}]


def test_removed_by_names_the_person_or_your_other_phone(kitchen: TestClient) -> None:
    """cabledrawer 18 Oct, decision 10: "Paneer · removed by Alex" needs who removed it."""
    alex = person(kitchen)
    main = main_id(kitchen)
    paneer, milk = food(kitchen, "Paneer"), food(kitchen, "Milk")
    by_alex, by_other_phone = new_id(), new_id()
    send(
        kitchen,
        action("add", list_id=main, item_id=by_alex, food_id=paneer["id"]),
        action("add", list_id=main, item_id=by_other_phone, food_id=milk["id"]),
    )
    since = counter(kitchen)
    send(alex, action("delete", item_id=by_alex), device=PHONE_R)
    send(kitchen, action("delete", item_id=by_other_phone), device=PHONE_B)

    def removed_by(answer: Any) -> dict[str, Any]:
        return {row["id"]: row["removed_by"] for row in answer["items"]}

    assert removed_by(changes(kitchen, since, PHONE_A)) == {
        by_alex: "Alex",
        by_other_phone: "Your other phone",
    }
    # On the phone that removed it, it's just the person's own name.
    assert removed_by(changes(kitchen, since, PHONE_B))[by_other_phone] == "Tess"
    assert removed_by(changes(alex, since))[by_other_phone] == "Tess"
    # The batch answer carries it too.
    answer = send(kitchen, since=since, device=PHONE_A)
    assert removed_by(answer["changes"])[by_other_phone] == "Your other phone"


def test_openapi_lists_the_sync_endpoints_and_every_kind(kitchen: TestClient) -> None:
    spec = ok(kitchen.get(f"{API}/openapi.json"))
    assert "post" in spec["paths"]["/api/v1/shopping/actions"]
    assert "get" in spec["paths"]["/api/v1/shopping/changes"]
    schemas = spec["components"]["schemas"]
    for name in ("Envelope", "BatchOut", "ResultOut", "ChangesOut", "Tombstone", "ItemRow"):
        assert name in schemas, name
    kinds = {
        schema["properties"]["kind"].get("const")
        for schema in schemas.values()
        if "kind" in schema.get("properties", {}) and "const" in schema["properties"]["kind"]
    }
    assert kinds >= {
        "create_list",
        "rename_list",
        "remove_list",
        "add",
        "set_amount",
        "delete",
        "tick",
        "untick",
        "put_away",
        "different_pack",
        "clear_ticked",
        "answer_double_tick",
        "dismiss_note",
        "undo",
        "found_at_home",  # "Already have it" (0.8, sync-protocol 7.6)
    }
    found = schemas["FoundAtHome"]["properties"]
    assert set(found) >= {"item_id", "amount", "size_id", "place_id"}
    assert schemas["TickRow"]["properties"]["found"]["type"] == "boolean"


# The schema names 0.2's endpoints had on main before PR 3 (generated clients use them).
NAMES_0_2 = (
    "AddStock",
    "AisleGroup",
    "AmountIn",
    "AmountOrNone",
    "AmountOut",
    "Answer",
    "AsSoldOut",
    "ChangeItem",
    "ChangeList",
    "ChangeOut",
    "ClearTicked",
    "ClearWrite",
    "Conversion",
    "Converted",
    "FoodAmount",
    "FoodBrief",
    "FoodCounts",
    "FoodLeft",
    "FoodList",
    "FoodListItem",
    "FoodOut",
    "FoodPatch",
    "FoodWrite",
    "Forgotten",
    "FromBrowser",
    "GroupOut",
    "HTTPValidationError",
    "HouseholdOut",
    "ItemAmount",
    "ItemOut",
    "ItemWrite",
    "LastChange",
    "LineOut",
    "ListOut",
    "ListView",
    "ListWrite",
    "ListsOut",
    "LotOut",
    "LotPatch",
    "MaybeSame",
    "Me",
    "Merge",
    "Move",
    "NewFood",
    "NewItem",
    "NewList",
    "NewName",
    "NewShop",
    "NewSize",
    "NewStandIn",
    "NotSame",
    "PantryCounts",
    "PantryOut",
    "PlaceRef",
    "Preferences",
    "Ref",
    "RememberedOut",
    "RenameList",
    "SetLeft",
    "SetupIn",
    "SetupState",
    "ShopGroup",
    "SignIn",
    "SizeBrief",
    "SizeOut",
    "SizePatch",
    "Split",
    "StandIn",
    "StockWrite",
    "ToFreezer",
    "TotalOut",
    "UndoOut",
    "Undone",
    "UnitOut",
    "UseSoonLot",
    "UseSoonOut",
    "UsedSome",
    "ValidationError",
    "VersionOut",
    "Who",
)


def test_openapi_keeps_the_0_2_schema_names(kitchen: TestClient) -> None:
    spec = ok(kitchen.get(f"{API}/openapi.json"))
    schemas = spec["components"]["schemas"]
    assert [name for name in NAMES_0_2 if name not in schemas] == []
    new = [name for name in schemas if "__" in name and "PlaceOut" not in name]  # 0.2's own
    assert new == []


def test_openapi_lists_the_whole_batch_refusals(kitchen: TestClient) -> None:
    spec = ok(kitchen.get(f"{API}/openapi.json"))
    answers = spec["paths"]["/api/v1/shopping/actions"]["post"]["responses"]
    assert {"200", "409", "413", "422"} <= set(answers)
    assert "other_login" in answers["409"]["description"]
    assert "too_many" in answers["413"]["description"]


def test_a_device_id_is_a_uuid(kitchen: TestClient) -> None:
    """3.8: the device ID is a random UUID, in the batch and when catching up."""
    send(kitchen, device="x" * 64, status=422)
    send(kitchen, device=PHONE_A.upper(), status=422)
    ok(kitchen.get(f"{API}/shopping/changes?since=0&device_id={'x' * 36}"), 422)
    send(kitchen, device=PHONE_A)


def test_a_full_copy_has_every_row_even_version_0(kitchen: TestClient) -> None:
    """5.5: `since=0` is a full copy. The main list made at sign-up, and rows from before
    the counter existed (an upgraded install), have version 0 and are still in it."""
    main = main_id(kitchen)
    fresh = changes(kitchen)
    assert fresh["reset"] is True
    assert [row["id"] for row in fresh["lists"]] == [main]
    old = food(kitchen, "Old dal")
    item = new_id()
    send(kitchen, action("add", list_id=main, item_id=item, food_id=old["id"], amount=500))
    with db(kitchen) as session:  # as the 0.3 migration leaves an upgraded install
        session.execute(update(Food).values(version=0))
        session.execute(update(ListItem).values(version=0))
        session.execute(update(ShoppingList).values(version=0))
        session.commit()
    full = changes(kitchen)
    assert [row["id"] for row in full["lists"]] == [main]
    assert [row["id"] for row in full["items"]] == [item]
    assert old["id"] in {row["id"] for row in full["foods"]}
    assert changes(kitchen, counter(kitchen))["items"] == []  # caught up: nothing new


def test_a_phone_ahead_of_the_server_gets_a_full_copy(kitchen: TestClient) -> None:
    """5.5 (cabledrawer 18 Oct): after a restore from a backup the server's counter can be
    behind a phone's cursor; the phone's copy can't be trusted, so it is replaced."""
    main = main_id(kitchen)
    food(kitchen, "Rice")  # takes a number
    now = counter(kitchen)
    assert changes(kitchen, now)["reset"] is False
    ahead = changes(kitchen, now + 50)
    assert ahead["reset"] is True and ahead["cursor"] == now
    assert [row["id"] for row in ahead["lists"]] == [main]
    assert send(kitchen, since=now + 1)["changes"]["reset"] is True


# --- Packet sizes travel with new_food (4.4, cabledrawer 18 Oct decision 8) -------------------------


def test_new_food_carries_its_packet_sizes(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    add_id = new_id()
    result = one(
        kitchen,
        "add",
        id=add_id,
        list_id=main,
        item_id=new_id(),
        new_food={
            "name": "Tahini",
            "counted_as": "weight",
            "sizes": [
                {"name": "jar", "amount": 250},
                {"name": "Jar", "amount": 250},  # the same size twice: made once
                {"name": "tub", "amount": 500},
            ],
        },
    )
    assert result["status"] == "applied"
    got = result["_answer"]["changes"]
    tahini = next(row for row in got["foods"] if row["id"] == result["food_id"])
    assert [(s["name"], s["amount"], s["usual"]) for s in tahini["sizes"]] == [
        ("jar", 250, True),
        ("tub", 500, False),
    ]
    # A blank amount is one of the usual size now.
    assert item_row(got, result["item_id"])["amount"] == 250
    # The sizes are part of the food_created change, so its Undo takes them too.
    with db(kitchen) as session:
        created = session.scalars(
            select(Change).where(Change.kind == "food_created", Change.food_id == tahini["id"])
        ).one()
        assert len(((created.undo_data or {}).get("foods") or {}).get("sizes", {})) == 2
        created_id = created.id
    # Once its list item is undone (on the list it is in use and would stay, cabledrawer 7 Nov),
    # the Undo of that change takes the ingredient and its sizes away again.
    assert one(kitchen, "undo", counter(kitchen), undoes=add_id)["status"] == "applied"
    undone = ok(kitchen.post(f"{API}/changes/{created_id}/undo"))
    assert undone["result"] == "done"
    with db(kitchen) as session:
        assert session.scalar(select(func.count()).select_from(FoodSize)) == 0
        assert session.get(Food, tahini["id"]).removed_at is not None  # type: ignore[union-attr]


def test_a_size_name_needs_letters(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    start = counter(kitchen)
    answer = send(
        kitchen,
        action(
            "add",
            list_id=main,
            item_id=new_id(),
            new_food={
                "name": "Tahini",
                "counted_as": "weight",
                "sizes": [{"name": "1", "amount": 5}],
            },
        ),
    )
    result = answer["results"][0]
    assert result["status"] == "refused" and result["reason"] == "bad_action"
    assert counter(kitchen) == start


def test_sizes_are_ignored_when_the_name_is_taken(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    existing = food(kitchen, "Tahini")
    result = one(
        kitchen,
        "add",
        list_id=main,
        item_id=new_id(),
        new_food={
            "name": "tahini",
            "counted_as": "weight",
            "sizes": [{"name": "jar", "amount": 250}],
        },
    )
    got = result["_answer"]["changes"]
    row = next(r for r in got["foods"] if r["id"] == existing["id"])
    assert row["sizes"] == []
