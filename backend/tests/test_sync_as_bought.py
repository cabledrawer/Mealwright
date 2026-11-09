"""An add "as bought" (cabledrawer 9 Nov, FR2 review 1, finding 3): its own line, never joined into
a line that is still to buy (sync protocol 4.2, `as_bought`). Without the flag an add still joins
(rule L-12)."""

from typing import Any

from fastapi.testclient import TestClient
from sync_kit import action, changes, food, main_id, new_id, one, send


def _live(client: TestClient, food_id: int) -> list[Any]:
    return [
        r
        for r in changes(client)["items"]
        if r["food_id"] == food_id and not r["deleted"] and not r.get("merged_into_id")
    ]


def _line_to_buy(client: TestClient, main: str, name: str) -> tuple[int, str]:
    loquat = food(client, name, counted_as="count")["id"]
    first = new_id()
    send(client, action("add", list_id=main, item_id=first, food_id=loquat, amount=3000))
    return loquat, first


def test_an_add_without_the_flag_still_joins(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    loquat, first = _line_to_buy(kitchen, main, "Loquat")
    second = one(kitchen, "add", list_id=main, item_id=new_id(), food_id=loquat, amount=2000)
    assert second["status"] == "merged" and second["item_id"] == first
    (line,) = _live(kitchen, loquat)
    assert line["amount"] == 5000


def test_an_add_as_bought_is_its_own_line_and_the_tick_leaves_the_other_alone(
    kitchen: TestClient,
) -> None:
    main = main_id(kitchen)
    loquat, first = _line_to_buy(kitchen, main, "Loquat")
    mine = new_id()
    added = one(
        kitchen,
        "add",
        list_id=main,
        item_id=mine,
        food_id=loquat,
        amount=2000,
        as_bought=True,
    )
    assert added["status"] == "applied" and added["item_id"] == mine
    assert one(kitchen, "tick", item_id=mine)["status"] == "applied"
    lines = {r["id"]: r for r in _live(kitchen, loquat)}
    assert set(lines) == {first, mine}
    assert lines[first]["amount"] == 3000 and not lines[first]["ticks"]
    assert lines[mine]["amount"] == 2000 and len(lines[mine]["ticks"]) == 1


def test_an_add_as_bought_sent_twice_makes_one_line(kitchen: TestClient) -> None:
    main = main_id(kitchen)
    loquat, _ = _line_to_buy(kitchen, main, "Loquat")
    again = action(
        "add", list_id=main, item_id=new_id(), food_id=loquat, amount=2000, as_bought=True
    )
    assert send(kitchen, again)["results"][0]["repeat"] is False
    assert send(kitchen, again)["results"][0]["repeat"] is True
    assert len(_live(kitchen, loquat)) == 2  # the line to buy, and the one as bought
