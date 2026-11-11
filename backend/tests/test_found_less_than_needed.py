"""Whole-0.8 review RF2, Sh3: "Already have it" with less than the plan needs keeps the rest on
the list (it used to take the whole line off for good). Proof: test_r1 in the review."""

from fastapi.testclient import TestClient
from sync_kit import PHONE_A, changes, counter, one
from test_recipes import food as new_food
from test_shop_from_plan import from_plan, line, plan, recipe
from test_tick_shown_amount import lines, pantry
from test_whole_packs import row_of, size


def halwa(kitchen: TestClient) -> tuple[dict[str, object], dict[str, object]]:
    ghee = new_food(kitchen, "Ghee")
    size(kitchen, ghee["id"], "jar", 500, usual=True)
    plan(kitchen, recipe(kitchen, "Halwa", line(ghee["id"], 620, "g")), 1)
    from_plan(kitchen)
    return ghee, row_of(kitchen, ghee["id"])


def test_found_less_than_the_need_leaves_the_rest_to_buy(kitchen: TestClient) -> None:
    ghee, row = halwa(kitchen)
    done = one(kitchen, "found_at_home", counter(kitchen), PHONE_A, item_id=row["id"], amount=125)
    assert done["status"] == "applied"
    assert pantry(kitchen, ghee["id"]) == 125
    from_plan(kitchen)
    # The found line is in the trolley; the 495 g the pantry still lacks is on the list.
    assert sorted(lines(kitchen, ghee["id"])) == [(495, False), (620, True)]


def test_the_rest_comes_back_after_clear_ticked_too(kitchen: TestClient) -> None:
    ghee, row = halwa(kitchen)
    one(kitchen, "found_at_home", counter(kitchen), PHONE_A, item_id=row["id"], amount=125)
    one(
        kitchen,
        "clear_ticked",
        counter(kitchen),
        PHONE_A,
        list_id=row["list_id"],
        item_ids=[row["id"]],
    )
    from_plan(kitchen)
    assert lines(kitchen, ghee["id"]) == [(495, False)]


def test_finding_all_of_it_leaves_nothing_to_buy(kitchen: TestClient) -> None:
    ghee, row = halwa(kitchen)
    one(kitchen, "found_at_home", counter(kitchen), PHONE_A, item_id=row["id"], amount=620)
    from_plan(kitchen)
    assert lines(kitchen, ghee["id"]) == [(620, True)]
    assert changes(kitchen)["items"]
