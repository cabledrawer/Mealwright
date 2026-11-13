"""L3 (whole-0.9 review): a phone that has not heard that an untick joined the bought row into the
line to buy takes off or re-counts only that row's own amount; the rest stays to buy (Sh7)."""

from fastapi.testclient import TestClient
from sync_kit import PHONE_A, PHONE_B, counter, food, main_id, new_id, one
from test_untick_join import bought_line, lines, untick


def test_a_stale_delete_of_the_bought_row_takes_only_its_own_amount_off(
    kitchen: TestClient,
) -> None:
    ghee, _to_buy, bought, done = bought_line(kitchen)  # 800 g to buy, 300 g bought
    seen = counter(kitchen)  # phone B last heard from the server here
    untick(kitchen, bought, done)  # phone A: one line, 1100 g
    assert lines(kitchen, ghee["id"]) == [(1100, False)]
    result = one(kitchen, "delete", seen, PHONE_B, item_id=bought)
    assert result["status"] == "applied"
    assert lines(kitchen, ghee["id"]) == [(800, False)]


def test_a_stale_delete_after_the_phone_heard_of_the_join_takes_the_whole_line(
    kitchen: TestClient,
) -> None:
    ghee, _to_buy, bought, done = bought_line(kitchen)
    untick(kitchen, bought, done)
    one(kitchen, "delete", counter(kitchen), PHONE_B, item_id=bought)  # it did hear of the join
    assert lines(kitchen, ghee["id"]) == []


def test_a_stale_set_amount_of_the_bought_row_changes_only_its_own_part(
    kitchen: TestClient,
) -> None:
    ghee, _to_buy, bought, done = bought_line(kitchen)
    seen = counter(kitchen)
    untick(kitchen, bought, done)
    one(kitchen, "set_amount", seen, PHONE_B, item_id=bought, amount=200)  # 300 g -> 200 g
    assert lines(kitchen, ghee["id"]) == [(1000, False)]


def test_undo_of_a_stale_delete_puts_the_amount_back(kitchen: TestClient) -> None:
    ghee, _to_buy, bought, done = bought_line(kitchen)
    seen = counter(kitchen)
    untick(kitchen, bought, done)
    gone = one(kitchen, "delete", seen, PHONE_B, item_id=bought)
    one(kitchen, "undo", counter(kitchen), PHONE_B, undoes=gone["id"])
    assert lines(kitchen, ghee["id"]) == [(1100, False)]


PHONE_C = "4f0a6c3b-0f4d-4c0b-8a3e-5c0d6f4b8a75"


def test_two_stale_amount_changes_from_one_phone_take_the_row_off_once(
    kitchen: TestClient,
) -> None:
    ghee, _to_buy, bought, done = bought_line(kitchen)  # 800 g to buy, 300 g bought
    seen = counter(kitchen)
    untick(kitchen, bought, done)
    one(kitchen, "set_amount", seen, PHONE_B, item_id=bought, amount=200)
    one(kitchen, "set_amount", seen, PHONE_B, item_id=bought, amount=250)
    assert lines(kitchen, ghee["id"]) == [(1050, False)]  # 800 + the phone's last 250


def test_a_stale_amount_change_then_a_stale_delete_leave_only_the_line_to_buy(
    kitchen: TestClient,
) -> None:
    ghee, _to_buy, bought, done = bought_line(kitchen)
    seen = counter(kitchen)
    untick(kitchen, bought, done)
    one(kitchen, "set_amount", seen, PHONE_B, item_id=bought, amount=200)
    one(kitchen, "delete", seen, PHONE_B, item_id=bought)
    assert lines(kitchen, ghee["id"]) == [(800, False)]


def test_two_stale_phones_deleting_the_bought_row_take_it_off_once(kitchen: TestClient) -> None:
    ghee, _to_buy, bought, done = bought_line(kitchen)
    seen = counter(kitchen)
    untick(kitchen, bought, done)
    one(kitchen, "delete", seen, PHONE_B, item_id=bought)
    one(kitchen, "delete", seen, PHONE_C, item_id=bought)
    assert lines(kitchen, ghee["id"]) == [(800, False)]


def test_undo_of_a_stale_amount_change_gives_the_row_its_old_part_back(
    kitchen: TestClient,
) -> None:
    ghee, _to_buy, bought, done = bought_line(kitchen)
    seen = counter(kitchen)
    untick(kitchen, bought, done)
    changed = one(kitchen, "set_amount", seen, PHONE_B, item_id=bought, amount=200)
    one(kitchen, "undo", counter(kitchen), PHONE_B, undoes=changed["id"])
    assert lines(kitchen, ghee["id"]) == [(1100, False)]
    one(kitchen, "delete", seen, PHONE_C, item_id=bought)  # the part is the 300 g again
    assert lines(kitchen, ghee["id"]) == [(800, False)]


def test_a_stale_delete_when_the_line_to_buy_had_no_amount_puts_it_back_to_none(
    kitchen: TestClient,
) -> None:
    ghee = food(kitchen, "Ghee")
    one(
        kitchen,
        "add",
        counter(kitchen),
        PHONE_A,
        list_id=main_id(kitchen),
        item_id=new_id(),
        food_id=ghee["id"],
    )  # "buy ghee", no amount
    bought = new_id()
    one(
        kitchen,
        "add",
        counter(kitchen),
        PHONE_A,
        list_id=main_id(kitchen),
        item_id=bought,
        food_id=ghee["id"],
        amount=300,
        as_bought=True,
    )
    done = one(kitchen, "tick", counter(kitchen), PHONE_A, item_id=bought, amount=300)
    seen = counter(kitchen)
    untick(kitchen, bought, done)
    assert lines(kitchen, ghee["id"]) == [(300, False)]
    one(kitchen, "delete", seen, PHONE_B, item_id=bought)
    assert lines(kitchen, ghee["id"]) == [(None, False)]
