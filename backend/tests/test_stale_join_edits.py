"""L3 (whole-0.9 review): a phone that has not heard that an untick joined the bought row into the
line to buy takes off or re-counts only that row's own amount; the rest stays to buy (Sh7)."""

from fastapi.testclient import TestClient
from sync_kit import PHONE_B, counter, one
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
