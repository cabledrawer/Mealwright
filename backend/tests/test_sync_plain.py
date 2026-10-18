"""SY-61: the one-at-a-time list requests kept from PR 2 go through the action handling
(sync protocol 5.1, cabledrawer 18 Oct). For each one: a sync_action row, the counter goes up,
the change shows in changes?since=N, Undo works, and the answer's shape is unchanged."""

from collections.abc import Callable
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import API, action, changes, counter, db, food, main_id, new_id, ok, send

from mealwright.models import ListItem, ListTick, SyncAction, utcnow

LIST_KEYS = {"id", "name", "main", "to_buy", "ticked"}
ITEM_KEYS = {
    "id",
    "list_id",
    "food",
    "amount",
    "shop",
    "aisle",
    "aisle_name",
    "ticked_at",
    "ticked_by",
    "put_away_place",
    "hand_edited",
    "source",
    "added_by",
    "version",
}
CHANGE_KEYS = {"id", "kind", "at", "who", "summary", "can_undo", "undo_until", "undone"}


def _row(answer: Any, part: str, row_id: str) -> Any:
    return next((row for row in answer[part] if row["id"] == row_id), None)


def proves(
    kitchen: TestClient,
    write: Callable[[], Any],
    kind: str,
    part: str,
    row_id: Callable[[Any], str],
    shape: Callable[[Any], None],
) -> Any:
    """Runs `write` (a plain request) and checks everything SY-61 asks of it."""
    start = counter(kitchen)
    answer = write()
    shape(answer)
    assert set(answer["change"]) == CHANGE_KEYS
    assert counter(kitchen) == start + 1
    with db(kitchen) as session:
        row = session.scalar(select(SyncAction).where(SyncAction.seq == start + 1))
        assert row is not None and row.kind == kind and row.status == "applied"
        assert row.change_id == answer["change"]["id"] and row.device_id is None
        original = row.id
    the_id = row_id(answer)
    seen = _row(changes(kitchen, start), part, the_id)
    assert seen is not None and seen["version"] == start + 1
    # Undo, from Recent changes or the toast.
    ok(kitchen.post(f"{API}/changes/{answer['change']['id']}/undo"))
    assert counter(kitchen) == start + 2
    with db(kitchen) as session:
        undo = session.scalar(select(SyncAction).where(SyncAction.seq == start + 2))
        assert undo is not None and undo.kind == "undo" and undo.payload == {"undoes": original}
        assert session.get(SyncAction, (1, original)).undone_by_action_id == undo.id
    after = _row(changes(kitchen, start + 1), part, the_id)
    assert after is not None and after["version"] == start + 2
    return after


def _list_shape(answer: Any) -> None:
    assert set(answer) == {"shopping_list", "change"}
    assert set(answer["shopping_list"]) == LIST_KEYS


def _list_gone_shape(answer: Any) -> None:  # removing a list answers with no list (PR 2)
    assert set(answer) == {"shopping_list", "change"} and answer["shopping_list"] is None


def _item_shape(answer: Any) -> None:
    assert set(answer) == {"item", "merged", "change"}
    assert set(answer["item"]) == ITEM_KEYS


def _item_gone_shape(answer: Any) -> None:  # deleting answers with no item (PR 2)
    assert set(answer) == {"item", "merged", "change"}
    assert answer["item"] is None and answer["merged"] is False


def test_sy61_make_a_list(kitchen: TestClient) -> None:
    after = proves(
        kitchen,
        lambda: ok(kitchen.post(f"{API}/shopping/lists", json={"name": "Party"}), 201),
        "create_list",
        "lists",
        lambda answer: answer["shopping_list"]["id"],
        _list_shape,
    )
    assert after["removed"] is True  # Undo of making it removes it


def test_sy61_rename_a_list(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    after = proves(
        kitchen,
        lambda: ok(kitchen.patch(f"{API}/shopping/lists/{main}", json={"name": "Our week"})),
        "rename_list",
        "lists",
        lambda answer: main,
        _list_shape,
    )
    assert after["name"] == "This week"


def test_sy61_remove_a_list(kitchen: TestClient) -> None:
    party = ok(kitchen.post(f"{API}/shopping/lists", json={"name": "Party"}), 201)
    party_id = party["shopping_list"]["id"]
    after = proves(
        kitchen,
        lambda: ok(kitchen.delete(f"{API}/shopping/lists/{party_id}")),
        "remove_list",
        "lists",
        lambda answer: party_id,
        _list_gone_shape,
    )
    assert after["removed"] is False


def test_sy61_add(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    after = proves(
        kitchen,
        lambda: ok(
            kitchen.post(f"{API}/shopping/lists/{main}/items", json={"food_id": milk["id"]}), 201
        ),
        "add",
        "items",
        lambda answer: answer["item"]["id"],
        _item_shape,
    )
    assert after["deleted"] is True  # Undo of the add takes it off


def test_sy61_change_amount(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk", counted_as="volume")
    item = ok(
        kitchen.post(
            f"{API}/shopping/lists/{main}/items",
            json={"food_id": milk["id"], "amount": {"amount": 2, "unit": "l"}},
        ),
        201,
    )["item"]["id"]
    after = proves(
        kitchen,
        lambda: ok(
            kitchen.patch(
                f"{API}/shopping/items/{item}", json={"amount": {"amount": 4, "unit": "l"}}
            )
        ),
        "set_amount",
        "items",
        lambda answer: item,
        _item_shape,
    )
    assert after["amount"] == 2000


def test_sy61_delete(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk")
    item = ok(
        kitchen.post(f"{API}/shopping/lists/{main}/items", json={"food_id": milk["id"]}), 201
    )["item"]["id"]
    after = proves(
        kitchen,
        lambda: ok(kitchen.delete(f"{API}/shopping/items/{item}")),
        "delete",
        "items",
        lambda answer: item,
        _item_gone_shape,
    )
    assert after["deleted"] is False  # back on the list


def test_sy61_clear_ticked(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    milk = food(kitchen, "Milk", counted_as="volume")
    item = new_id()
    send(kitchen, action("add", list_id=main, item_id=item, food_id=milk["id"], amount=1000))
    with db(kitchen) as session:  # ticked (the tick action comes in the next commit)
        row = session.get(ListItem, item)
        row.ticked_at = utcnow()
        row.ticked_by_name = "Tess"
        session.add(ListTick(household_id=1, id=new_id(), item_id=item, login_name="Tess"))
        session.commit()

    def shape(answer: Any) -> None:
        assert set(answer) == {"cleared", "change"} and answer["cleared"] == [item]

    after = proves(
        kitchen,
        lambda: ok(kitchen.post(f"{API}/shopping/lists/{main}/clear-ticked", json={})),
        "clear_ticked",
        "items",
        lambda answer: item,
        shape,
    )
    assert after["deleted"] is False and after["ticks"][0]["standing"] is True
