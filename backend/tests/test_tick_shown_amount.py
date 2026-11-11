"""Whole-0.8 review RF2, Sh1 (cabledrawer 11 Nov): a tick carries the amount the phone showed; the
rest of a line that grew meanwhile stays on the list. Sh1's proof was test_q1 in the review."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import PHONE_A, PHONE_B, action, changes, counter, db, ok, one, send
from test_recipes import food as new_food
from test_shop_from_plan import from_plan, line, plan, recipe
from test_whole_packs import row_of, size

from mealwright.models import StockLot


def pantry(kitchen: TestClient, food_id: int) -> float:
    with db(kitchen) as s:
        return (
            sum(
                lot.amount_milli
                for lot in s.scalars(select(StockLot).where(StockLot.food_id == food_id))
            )
            / 1000
        )


def lines(kitchen: TestClient, food_id: int) -> list[tuple[float, bool]]:
    """(amount, ticked) of the ingredient's live lines."""
    return [
        (i["amount"], any(t["standing"] for t in i["ticks"]))
        for i in changes(kitchen)["items"]
        if i["food_id"] == food_id and not i["deleted"]
    ]


def grown_line(kitchen: TestClient) -> tuple[dict[str, Any], dict[str, Any], int]:
    """Ghee, a 500 g jar, a line of 120 g that a phone sees; then the plan makes it 620 g."""
    ghee = new_food(kitchen, "Ghee")
    size(kitchen, ghee["id"], "jar", 500, usual=True)
    plan(kitchen, recipe(kitchen, "Dal", line(ghee["id"], 120, "g")), 1)
    from_plan(kitchen)
    row = row_of(kitchen, ghee["id"])
    seen = counter(kitchen)
    plan(kitchen, recipe(kitchen, "Halwa", line(ghee["id"], 500, "g")), 2)
    from_plan(kitchen)
    assert row_of(kitchen, ghee["id"])["amount"] == 620
    return ghee, row, seen


def test_a_tick_puts_in_what_the_phone_showed_and_the_rest_stays_to_buy(
    kitchen: TestClient,
) -> None:
    # One jar bought for the 120 g the phone showed; the plan grew the line to 620 g meanwhile.
    ghee, row, seen = grown_line(kitchen)
    done = one(kitchen, "tick", seen, PHONE_B, item_id=row["id"], amount=120)
    assert done["status"] == "applied"
    assert pantry(kitchen, ghee["id"]) == 500
    # The ticked line is the 120 g the phone showed. The jar in the pantry covers 500 g of the
    # 620 g now needed, so the 120 g still lacking is one line to buy (the second jar).
    assert sorted(lines(kitchen, ghee["id"])) == [(120, False), (120, True)]
    # The next plan update leaves that line alone, and makes no second one.
    from_plan(kitchen)
    assert len([x for x in lines(kitchen, ghee["id"]) if not x[1]]) == 1


def test_a_tick_with_no_amount_keeps_todays_rule_for_a_queue_made_before_the_update(
    kitchen: TestClient,
) -> None:
    ghee, row, seen = grown_line(kitchen)
    done = one(kitchen, "tick", seen, PHONE_B, item_id=row["id"])
    assert done["status"] == "applied"
    assert pantry(kitchen, ghee["id"]) == 1000  # the line's 620 g at arrival: two jars
    assert lines(kitchen, ghee["id"]) == [(620, True)]


def test_a_tick_with_the_amount_the_line_still_has_changes_nothing(kitchen: TestClient) -> None:
    ghee = new_food(kitchen, "Ghee")
    size(kitchen, ghee["id"], "jar", 500, usual=True)
    plan(kitchen, recipe(kitchen, "Dal", line(ghee["id"], 120, "g")), 1)
    from_plan(kitchen)
    row = row_of(kitchen, ghee["id"])
    one(kitchen, "tick", counter(kitchen), PHONE_A, item_id=row["id"], amount=120)
    assert pantry(kitchen, ghee["id"]) == 500
    assert lines(kitchen, ghee["id"]) == [(120, True)]


def test_a_tick_with_an_amount_that_is_not_valid_is_refused(kitchen: TestClient) -> None:
    _ghee, row, seen = grown_line(kitchen)
    bad = send(kitchen, action("tick", seen, item_id=row["id"], amount=0), device=PHONE_B)
    assert bad["results"][0]["status"] == "refused"
    assert ok(kitchen.get("/api/v1/shopping/changes"))["items"]
