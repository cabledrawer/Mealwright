"""L1c Sh7 (cabledrawer 12 Nov: "join back on untick"): unticking a trolley line joins it back into
the line still to buy for the same ingredient, list and shop, and Undo of the untick puts both
lines back exactly as they were."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import PHONE_A, PHONE_B, action, changes, counter, food, main_id, new_id, one, send
from test_whole_packs import size

from mealwright.models import StockLot


def pantry(kitchen: TestClient, food_id: int) -> float:
    with kitchen.app.state.sessionmaker() as s:  # type: ignore[attr-defined]
        found = s.scalars(select(StockLot).where(StockLot.food_id == food_id))
        return float(sum(lot.amount_milli for lot in found)) / 1000


def lines(kitchen: TestClient, food_id: int) -> list[tuple[float | None, bool]]:
    """(amount, ticked) of the ingredient's lines a phone shows (not taken off, not joined)."""
    found = [
        (i["amount"], any(t["standing"] for t in i["ticks"]))
        for i in changes(kitchen)["items"]
        if i["food_id"] == food_id and not i["deleted"] and not i["merged_into_id"]
    ]
    return sorted(found, key=lambda line: (line[0] is not None, line[0] or 0, line[1]))


def add(kitchen: TestClient, food_id: int, amount: float, **extra: Any) -> str:
    item = new_id()
    one(
        kitchen,
        "add",
        counter(kitchen),
        PHONE_A,
        list_id=main_id(kitchen),
        item_id=item,
        food_id=food_id,
        amount=amount,
        **extra,
    )
    return item


def bought_line(kitchen: TestClient) -> tuple[dict[str, Any], str, str, dict[str, Any]]:
    """Ghee: 800 g still to buy, and 300 g added as bought (its own line, ticked)."""
    ghee = food(kitchen, "Ghee")
    to_buy = add(kitchen, ghee["id"], 800)
    bought = add(kitchen, ghee["id"], 300, as_bought=True)
    done = one(kitchen, "tick", counter(kitchen), PHONE_A, item_id=bought, amount=300)
    assert lines(kitchen, ghee["id"]) == [(300, True), (800, False)]
    assert pantry(kitchen, ghee["id"]) == 300
    return ghee, to_buy, bought, done


def untick(kitchen: TestClient, bought: str, done: dict[str, Any], device: str = PHONE_A) -> Any:
    return one(kitchen, "untick", counter(kitchen), device, item_id=bought, tick_ids=[done["id"]])


def test_unticking_an_as_bought_line_joins_it_into_the_line_to_buy(kitchen: TestClient) -> None:
    ghee, _to_buy, bought, done = bought_line(kitchen)
    untick(kitchen, bought, done)
    assert lines(kitchen, ghee["id"]) == [(1100, False)]
    assert pantry(kitchen, ghee["id"]) == 0


def test_undo_of_that_untick_puts_both_lines_back_exactly(kitchen: TestClient) -> None:
    ghee, to_buy, bought, done = bought_line(kitchen)
    gone = untick(kitchen, bought, done)
    one(kitchen, "undo", counter(kitchen), PHONE_A, undoes=gone["id"])
    assert lines(kitchen, ghee["id"]) == [(300, True), (800, False)]
    assert pantry(kitchen, ghee["id"]) == 300
    # The same two lines, with their own IDs.
    ids = {
        i["id"] for i in changes(kitchen)["items"] if not i["deleted"] and not i["merged_into_id"]
    }
    assert {to_buy, bought} <= ids
    # And unticking again joins again.
    untick(kitchen, bought, done)
    assert lines(kitchen, ghee["id"]) == [(1100, False)]


def test_the_same_untick_sent_twice_joins_once(kitchen: TestClient) -> None:
    ghee, _to_buy, bought, done = bought_line(kitchen)
    twice = action("untick", counter(kitchen), item_id=bought, tick_ids=[done["id"]])
    send(kitchen, twice)
    again = send(kitchen, twice)
    assert again["results"][0]["repeat"] is True
    assert lines(kitchen, ghee["id"]) == [(1100, False)]


def test_the_undo_sent_twice_splits_once(kitchen: TestClient) -> None:
    ghee, _to_buy, bought, done = bought_line(kitchen)
    gone = untick(kitchen, bought, done)
    undo = action("undo", counter(kitchen), undoes=gone["id"])
    send(kitchen, undo)
    send(kitchen, undo)
    assert lines(kitchen, ghee["id"]) == [(300, True), (800, False)]
    assert pantry(kitchen, ghee["id"]) == 300


def test_a_stale_phones_tick_of_the_joined_line_does_not_double_the_amount(
    kitchen: TestClient,
) -> None:
    # Phone B still shows the 300 g line ticked-then-unticked as its own line to buy and ticks
    # it after the join: the tick lands on the joined line, for the 300 g it saw, and the
    # other 800 g stay to buy.
    ghee, _to_buy, bought, done = bought_line(kitchen)
    seen = counter(kitchen)
    untick(kitchen, bought, done)
    one(kitchen, "tick", seen, PHONE_B, item_id=bought, amount=300)
    assert lines(kitchen, ghee["id"]) == [(300, True), (800, False)]
    assert pantry(kitchen, ghee["id"]) == 300


def test_a_stale_phones_tick_of_the_line_it_saw_leaves_what_was_joined_to_buy(
    kitchen: TestClient,
) -> None:
    ghee, to_buy, bought, done = bought_line(kitchen)
    seen = counter(kitchen)
    untick(kitchen, bought, done)
    one(kitchen, "tick", seen, PHONE_B, item_id=to_buy, amount=800)
    assert lines(kitchen, ghee["id"]) == [(300, False), (800, True)]
    assert pantry(kitchen, ghee["id"]) == 800


def test_undo_when_the_joined_line_was_changed_since_keeps_it_and_brings_the_bought_one_back(
    kitchen: TestClient,
) -> None:
    # Nothing a person did is rewritten: the line keeps its 2000 g, the 300 g come back ticked.
    ghee, to_buy, bought, done = bought_line(kitchen)
    gone = untick(kitchen, bought, done)
    one(kitchen, "set_amount", counter(kitchen), PHONE_A, item_id=to_buy, amount=2000)
    one(kitchen, "undo", counter(kitchen), PHONE_A, undoes=gone["id"])
    assert lines(kitchen, ghee["id"]) == [(300, True), (2000, False)]
    assert pantry(kitchen, ghee["id"]) == 300


def test_undo_when_the_joined_line_was_bought_since_brings_the_bought_one_back(
    kitchen: TestClient,
) -> None:
    ghee, to_buy, bought, done = bought_line(kitchen)
    gone = untick(kitchen, bought, done)
    one(kitchen, "tick", counter(kitchen), PHONE_A, item_id=to_buy, amount=1100)
    one(kitchen, "undo", counter(kitchen), PHONE_A, undoes=gone["id"])
    assert lines(kitchen, ghee["id"]) == [(300, True), (1100, True)]
    assert pantry(kitchen, ghee["id"]) == 1400  # the 1100 g bought since and the 300 g put back


def test_a_line_at_another_shop_is_not_joined(kitchen: TestClient) -> None:
    ghee = food(kitchen, "Ghee")
    shop = send_shop(kitchen)
    add(kitchen, ghee["id"], 800, shop_id=shop)
    bought = add(kitchen, ghee["id"], 300, as_bought=True)
    done = one(kitchen, "tick", counter(kitchen), PHONE_A, item_id=bought, amount=300)
    untick(kitchen, bought, done)
    assert lines(kitchen, ghee["id"]) == [(300, False), (800, False)]


def test_a_line_counted_in_another_size_is_not_joined(kitchen: TestClient) -> None:
    ghee = food(kitchen, "Ghee")
    size(kitchen, ghee["id"], "jar", 500)
    jar = next(
        s["id"] for f in changes(kitchen)["foods"] if f["id"] == ghee["id"] for s in f["sizes"]
    )
    add(kitchen, ghee["id"], 1000, size_id=jar)
    bought = add(kitchen, ghee["id"], 300, as_bought=True)
    done = one(kitchen, "tick", counter(kitchen), PHONE_A, item_id=bought, amount=300)
    untick(kitchen, bought, done)
    assert lines(kitchen, ghee["id"]) == [(300, False), (1000, False)]


def test_nothing_joins_when_there_is_no_line_to_buy(kitchen: TestClient) -> None:
    ghee = food(kitchen, "Ghee")
    only = add(kitchen, ghee["id"], 300)
    done = one(kitchen, "tick", counter(kitchen), PHONE_A, item_id=only, amount=300)
    untick(kitchen, only, done)
    assert lines(kitchen, ghee["id"]) == [(300, False)]


def test_an_untick_that_leaves_another_tick_standing_does_not_join(kitchen: TestClient) -> None:
    # Two phones ticked the same line; one purchase is taken back, the line is still bought.
    ghee = food(kitchen, "Ghee")
    add(kitchen, ghee["id"], 800)
    bought = add(kitchen, ghee["id"], 300, as_bought=True)
    seen = counter(kitchen)
    first = one(kitchen, "tick", seen, PHONE_A, item_id=bought, amount=300)
    one(kitchen, "tick", seen, PHONE_B, item_id=bought, amount=300)
    untick(kitchen, bought, first)
    assert lines(kitchen, ghee["id"]) == [(300, True), (800, False)]


def send_shop(kitchen: TestClient) -> int:
    made = kitchen.post("/api/v1/shops", json={"name": "Corner"})
    assert made.status_code == 201, made.text
    return int(made.json()["id"])


def test_a_tick_keeps_the_rest_of_a_line_for_an_ingredient_with_no_pack_size(
    kitchen: TestClient,
) -> None:
    # Found while building Sh7: the amount the phone showed was lost for an ingredient with no
    # size to buy in, so a tick of 300 g on a line that had grown to 1100 g bought it all.
    ghee = food(kitchen, "Ghee")
    line = add(kitchen, ghee["id"], 1100)
    one(kitchen, "tick", counter(kitchen), PHONE_A, item_id=line, amount=300)
    assert lines(kitchen, ghee["id"]) == [(300, True), (800, False)]


def test_an_as_bought_line_with_no_amount_joins_and_comes_back_on_undo(
    kitchen: TestClient,
) -> None:
    # "Add as bought" with no amount typed: the line has none, so the line to buy keeps its
    # 800 g, and Undo of the untick brings the bought line back on its own.
    ghee = food(kitchen, "Ghee")
    add(kitchen, ghee["id"], 800)
    bought = new_id()
    one(
        kitchen,
        "add",
        counter(kitchen),
        PHONE_A,
        list_id=main_id(kitchen),
        item_id=bought,
        food_id=ghee["id"],
        as_bought=True,
    )
    done = one(kitchen, "tick", counter(kitchen), PHONE_A, item_id=bought)
    assert lines(kitchen, ghee["id"]) == [(None, True), (800, False)]
    gone = untick(kitchen, bought, done)
    assert lines(kitchen, ghee["id"]) == [(800, False)]
    one(kitchen, "undo", counter(kitchen), PHONE_A, undoes=gone["id"])
    assert lines(kitchen, ghee["id"]) == [(None, True), (800, False)]


def test_a_staples_bought_line_is_not_joined_because_nothing_went_into_the_pantry(
    kitchen: TestClient,
) -> None:
    salt = food(kitchen, "Salt", staple=True)
    add(kitchen, salt["id"], 800)
    bought = add(kitchen, salt["id"], 300, as_bought=True)
    done = one(kitchen, "tick", counter(kitchen), PHONE_A, item_id=bought, amount=300)
    untick(kitchen, bought, done)
    assert lines(kitchen, salt["id"]) == [(300, False), (800, False)]
