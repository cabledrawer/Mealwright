"""Whole-0.8 review RF2, Sh1 (cabledrawer 11 Nov): a tick carries the amount the phone showed; the
rest of a line that grew meanwhile stays on the list. Sh1's proof was test_q1 in the review."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import PHONE_A, PHONE_B, action, changes, counter, db, new_id, ok, one, send
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
    assert ok(kitchen.get("/api/v1/shopping/sync"))["items"]


def test_a_line_the_plan_removed_is_not_blamed_on_a_person(kitchen: TestClient) -> None:
    # RF2 Sh6 (older than 0.8): a phone's change to a line the plan took off used to say
    # "Your other phone had removed Ghee, so your change wasn't kept." when no phone had.
    ghee = new_food(kitchen, "Ghee")
    size(kitchen, ghee["id"], "jar", 500, usual=True)
    made = plan(kitchen, recipe(kitchen, "Dal", line(ghee["id"], 120, "g")), 1)
    from_plan(kitchen)
    row = row_of(kitchen, ghee["id"])
    seen = counter(kitchen)
    shop = ok(kitchen.post("/api/v1/shops", json={"name": "Corner"}), 201)["id"]
    ok(kitchen.post(f"/api/v1/changes/{made['change']['id']}/undo"))
    from_plan(kitchen)
    one(kitchen, "set_amount", seen, PHONE_B, item_id=row["id"], amount=250)
    one(kitchen, "move", seen, PHONE_B, item_id=row["id"], list_id=row["list_id"], shop_id=shop)
    texts = [n["text"] for n in changes(kitchen)["notes"]]
    assert texts == ["Ghee isn’t needed by the plan any more, so your change wasn’t kept."] * 2
    assert all(n["undo"] is None for n in changes(kitchen)["notes"])


def test_a_line_a_person_removed_still_names_the_person(kitchen: TestClient) -> None:
    ghee = new_food(kitchen, "Ghee")
    size(kitchen, ghee["id"], "jar", 500, usual=True)
    plan(kitchen, recipe(kitchen, "Dal", line(ghee["id"], 120, "g")), 1)
    from_plan(kitchen)
    row = row_of(kitchen, ghee["id"])
    seen = counter(kitchen)
    one(kitchen, "delete", seen, PHONE_A, item_id=row["id"])
    one(kitchen, "set_amount", seen, PHONE_B, item_id=row["id"], amount=250)
    assert [n["text"] for n in changes(kitchen)["notes"]] == [
        "Your other phone had removed Ghee, so your change wasn’t kept."
    ]


# --- RF2 fix round 1 (Opus review r1) -------------------------------------------


def test_a_second_phones_tick_does_not_split_the_line_again(kitchen: TestClient) -> None:
    # Phone A ticked the whole 620 g; phone B, offline, ticks the 120 g it saw. B's amount goes
    # into the pantry (two purchases, the card asks), but A's ticked line is left as it was and
    # no line to buy appears.
    ghee, row, seen = grown_line(kitchen)
    one(kitchen, "tick", counter(kitchen), PHONE_A, item_id=row["id"], amount=620)
    one(kitchen, "tick", seen, PHONE_B, item_id=row["id"], amount=120)
    assert lines(kitchen, ghee["id"]) == [(620, True)]
    assert len([q for q in changes(kitchen)["questions"] if q["open"]]) == 1


def split_tick(kitchen: TestClient) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    ghee, row, seen = grown_line(kitchen)
    done = one(kitchen, "tick", seen, PHONE_B, item_id=row["id"], amount=120)
    assert sorted(lines(kitchen, ghee["id"])) == [(120, False), (120, True)]
    return ghee, row, done


def test_untick_of_a_split_tick_puts_the_line_back_whole(kitchen: TestClient) -> None:
    ghee, row, done = split_tick(kitchen)
    one(kitchen, "untick", counter(kitchen), PHONE_B, item_id=row["id"], tick_ids=[done["id"]])
    assert pantry(kitchen, ghee["id"]) == 0
    assert lines(kitchen, ghee["id"]) == [(620, False)]


def test_undo_of_a_split_tick_puts_the_line_back_whole(kitchen: TestClient) -> None:
    ghee, _row, done = split_tick(kitchen)
    one(kitchen, "undo", counter(kitchen), PHONE_B, undoes=done["id"])
    assert pantry(kitchen, ghee["id"]) == 0
    assert lines(kitchen, ghee["id"]) == [(620, False)]


def test_pantry_undo_of_a_split_purchase_puts_the_line_back_whole(kitchen: TestClient) -> None:
    ghee, _row, done = split_tick(kitchen)
    r = kitchen.post(
        f"/api/v1/changes/{done['change']['id']}/undo", headers={"Idempotency-Key": "k-split"}
    )
    assert r.status_code == 200, r.text
    assert pantry(kitchen, ghee["id"]) == 0
    assert lines(kitchen, ghee["id"]) == [(620, False)]


def test_undo_of_the_untick_splits_it_again(kitchen: TestClient) -> None:
    ghee, row, done = split_tick(kitchen)
    gone = one(
        kitchen, "untick", counter(kitchen), PHONE_B, item_id=row["id"], tick_ids=[done["id"]]
    )
    one(kitchen, "undo", counter(kitchen), PHONE_B, undoes=gone["id"])
    assert pantry(kitchen, ghee["id"]) == 500
    assert sorted(lines(kitchen, ghee["id"])) == [(120, False), (120, True)]


def test_a_hand_edited_line_comes_back_to_its_old_amount(kitchen: TestClient) -> None:
    ghee = new_food(kitchen, "Ghee")
    size(kitchen, ghee["id"], "jar", 500, usual=True)
    plan(kitchen, recipe(kitchen, "Dal", line(ghee["id"], 120, "g")), 1)
    from_plan(kitchen)
    row = row_of(kitchen, ghee["id"])
    seen = counter(kitchen)
    one(kitchen, "set_amount", seen, PHONE_A, item_id=row["id"], amount=1620)
    done = one(kitchen, "tick", seen, PHONE_B, item_id=row["id"], amount=120)
    assert sorted(lines(kitchen, ghee["id"])) == [(120, True), (1120, False)]
    one(kitchen, "undo", counter(kitchen), PHONE_B, undoes=done["id"])
    assert lines(kitchen, ghee["id"]) == [(1620, False)]  # none of the need is lost


def test_a_rest_line_that_was_ticked_since_stays_when_the_first_tick_is_undone(
    kitchen: TestClient,
) -> None:
    # The rest line was bought meanwhile: it is not taken away, and the first line keeps the
    # amount it was ticked at (chosen: nothing that was bought or edited is rewritten).
    ghee, _row, done = split_tick(kitchen)
    rest = next(
        i for i in changes(kitchen)["items"] if i["food_id"] == ghee["id"] and not i["ticks"]
    )
    one(kitchen, "tick", counter(kitchen), PHONE_A, item_id=rest["id"], amount=120)
    one(kitchen, "undo", counter(kitchen), PHONE_B, undoes=done["id"])
    assert sorted(lines(kitchen, ghee["id"])) == [(120, False), (120, True)]


def test_just_1_leaves_a_split_alone(kitchen: TestClient) -> None:
    # A split tick is always the first purchase, and "Just 1" only reverses the later ones.
    ghee, row, _done = split_tick(kitchen)
    second = one(kitchen, "tick", counter(kitchen), PHONE_A, item_id=row["id"])
    assert second["status"] == "applied"
    q = next(q for q in changes(kitchen)["questions"] if q["open"])
    one(kitchen, "answer_double_tick", counter(kitchen), PHONE_A, question_id=q["id"], answer="one")
    assert sorted(lines(kitchen, ghee["id"])) == [(120, False), (120, True)]


def test_a_tick_that_puts_nothing_in_does_not_split(kitchen: TestClient) -> None:
    ghee = new_food(kitchen, "Salt", staple=True)
    plan(kitchen, recipe(kitchen, "Dal", line(ghee["id"], 120, "g")), 1)
    from_plan(kitchen)
    main = ok(kitchen.get("/api/v1/shopping/sync"))["lists"][0]["id"]
    item = new_id()
    send(
        kitchen,
        action("add", list_id=main, item_id=item, food_id=ghee["id"], amount=620),
    )
    one(kitchen, "tick", counter(kitchen), PHONE_A, item_id=item, amount=120)
    assert [x for x in lines(kitchen, ghee["id"]) if not x[1]] == []


def test_a_rest_line_moved_to_another_shop_is_not_bought_twice_when_the_plan_grows(
    kitchen: TestClient,
) -> None:
    ghee, row, seen = grown_line(kitchen)
    one(kitchen, "tick", seen, PHONE_B, item_id=row["id"], amount=120)
    rest = next(
        i for i in changes(kitchen)["items"] if i["food_id"] == ghee["id"] and not i["ticks"]
    )
    shop = ok(kitchen.post("/api/v1/shops", json={"name": "Corner"}), 201)["id"]
    one(
        kitchen,
        "move",
        counter(kitchen),
        PHONE_B,
        item_id=rest["id"],
        list_id=rest["list_id"],
        shop_id=shop,
    )
    plan(kitchen, recipe(kitchen, "Pilau", line(ghee["id"], 100, "g")), 3)
    from_plan(kitchen)
    assert sorted(lines(kitchen, ghee["id"])) == [(120, False), (120, True)]


# --- 0.9.5 L7 (cabledrawer 13 Nov): follow the 11 Nov rule -------------------------------------


def test_untick_of_a_split_tick_whose_rest_was_changed_comes_back_on_its_own(
    kitchen: TestClient,
) -> None:
    # The rest line was edited since: the untick leaves both lines as they are (11 Nov rule), so
    # the unticked line is not joined into the edited one.
    ghee, row, done = split_tick(kitchen)
    rest = next(
        i for i in changes(kitchen)["items"] if i["food_id"] == ghee["id"] and not i["ticks"]
    )
    one(kitchen, "set_amount", counter(kitchen), PHONE_A, item_id=rest["id"], amount=250)
    one(kitchen, "untick", counter(kitchen), PHONE_B, item_id=row["id"], tick_ids=[done["id"]])
    assert pantry(kitchen, ghee["id"]) == 0
    assert sorted(lines(kitchen, ghee["id"])) == [(120, False), (250, False)]


def test_the_same_untick_replayed_offline_leaves_the_edited_rest_alone(
    kitchen: TestClient,
) -> None:
    ghee, row, done = split_tick(kitchen)
    rest = next(
        i for i in changes(kitchen)["items"] if i["food_id"] == ghee["id"] and not i["ticks"]
    )
    one(kitchen, "set_amount", counter(kitchen), PHONE_A, item_id=rest["id"], amount=250)
    again = action("untick", counter(kitchen), item_id=row["id"], tick_ids=[done["id"]])
    send(kitchen, again)
    send(kitchen, again)
    assert sorted(lines(kitchen, ghee["id"])) == [(120, False), (250, False)]


def test_untick_of_both_purchases_leaves_the_lines_apart_whatever_order_they_are_named(
    kitchen: TestClient,
) -> None:
    # Lorna's tick split the line, Sam ticked it again, the rest line was edited since: naming
    # the second purchase first must not decide the answer.
    ghee, row, first = split_tick(kitchen)
    second = one(kitchen, "tick", counter(kitchen), PHONE_A, item_id=row["id"])
    assert second["status"] == "applied"
    rest = next(
        i for i in changes(kitchen)["items"] if i["food_id"] == ghee["id"] and not i["ticks"]
    )
    one(kitchen, "set_amount", counter(kitchen), PHONE_A, item_id=rest["id"], amount=250)
    one(
        kitchen,
        "untick",
        counter(kitchen),
        PHONE_B,
        item_id=row["id"],
        tick_ids=[second["id"], first["id"]],
    )
    assert sorted(lines(kitchen, ghee["id"])) == [(120, False), (250, False)]


def test_untick_of_a_split_tick_whose_ticked_line_was_changed_stays_apart(
    kitchen: TestClient,
) -> None:
    # "Either line was changed since" (11 Nov rule, "neither has been touched"): the ticked
    # line's amount was set by hand, so the unticked line is not joined into the rest.
    ghee, row, done = split_tick(kitchen)
    one(kitchen, "set_amount", counter(kitchen), PHONE_A, item_id=row["id"], amount=150)
    one(kitchen, "untick", counter(kitchen), PHONE_B, item_id=row["id"], tick_ids=[done["id"]])
    assert sorted(lines(kitchen, ghee["id"])) == [(120, False), (150, False)]
