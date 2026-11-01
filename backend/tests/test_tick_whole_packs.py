"""F122 (cabledrawer 31 Oct): ticking a list line puts the pack bought into the pantry, not the
exact need. 38 g ghee with a 500 g jar is 1 jar (500 g). Decided in ticks.tick (the size is
foods.pack_bought); every way a tick reaches the server (online, or queued and sent later)
goes through that one function, and Undo takes out exactly what went in."""

import time
from typing import Any

from fastapi.testclient import TestClient
from sync_kit import (
    API,
    PHONE_A,
    PHONE_R,
    S0,
    action,
    changes,
    counter,
    db,
    food,
    item_row,
    new_id,
    ok,
    one,
    s0,
    send,
)

from mealwright.models import FoodSize, ListTick


def _line(
    s: S0, name: str, amount: int | None, size: str | None = None, **extra: Any
) -> tuple[str, int]:
    """A food (weight, or as asked) with an optional pack size, and one list line for it."""
    made = food(
        s.kitchen,
        name,
        counted_as=extra.pop("counted_as", "weight"),
        staple=extra.pop("staple", False),
        place_id=s.places["Cupboard"],
    )
    if size is not None:
        pack, grams = size.split("=")
        sized = ok(
            s.kitchen.post(
                f"{API}/foods/{made['id']}/sizes", json={"name": pack, "amount": float(grams) if "." in grams else int(grams)}
            ),
            201,
        )
        s.sizes[name] = sized["food"]["sizes"][0]["id"]
    item = new_id()
    line: dict[str, Any] = {"list_id": s.main, "item_id": item, "food_id": made["id"], **extra}
    if amount is not None:
        line["amount"] = amount
    send(s.kitchen, action("add", counter(s.kitchen), **line))
    s.foods[name] = made["id"]
    s.items[name] = item
    return item, made["id"]


def _tick(s: S0, name: str, **extra: Any) -> Any:
    return one(s.kitchen, "tick", counter(s.kitchen), PHONE_A, item_id=s.items[name], **extra)


def _bought(s: S0, name: str) -> tuple[int | None, int | None]:
    with db(s.kitchen) as session:
        row = session.query(ListTick).filter(ListTick.item_id == s.items[name]).one()
        return (None if row.bought_milli is None else row.bought_milli // 1000, row.bought_size_id)


def test_a_line_smaller_than_the_jar_puts_a_whole_jar_in(kitchen: TestClient) -> None:
    s = s0(kitchen)
    _line(s, "Ghee", 38, "jar=500")
    done = _tick(s, "Ghee")
    assert done["status"] == "applied"
    assert s.lots("Ghee") == [("Cupboard", 500)]
    assert _bought(s, "Ghee")[0] == 500
    assert done["change"]["summary"] == "Bought 1\u00a0jar Ghee → Cupboard"
    bought = item_row(changes(kitchen), s.items["Ghee"])["ticks"][0]["bought"]
    assert bought["amount"] == 500 and "1\u00a0jar" in bought["display"]


def test_more_than_one_jar_rounds_up_to_whole_jars(kitchen: TestClient) -> None:
    s = s0(kitchen)
    _line(s, "Ghee", 620, "jar=500")
    _tick(s, "Ghee")
    assert s.lots("Ghee") == [("Cupboard", 500), ("Cupboard", 500)]


def test_an_exact_number_of_jars_is_unchanged(kitchen: TestClient) -> None:
    s = s0(kitchen)
    _line(s, "Ghee", 500, "jar=500")
    _tick(s, "Ghee")
    assert s.total("Ghee") == 500


def test_the_usual_size_is_the_one_bought_when_there_are_several(kitchen: TestClient) -> None:
    s = s0(kitchen)
    _, ghee = _line(s, "Ghee", 38, "jar=500")
    ok(kitchen.post(f"{API}/foods/{ghee}/sizes", json={"name": "tin", "amount": 100}), 201)
    _tick(s, "Ghee")
    assert s.total("Ghee") == 500  # the first size made is the Usual one


def test_several_sizes_and_none_usual_puts_the_exact_amount_in(kitchen: TestClient) -> None:
    s = s0(kitchen)
    _, ghee = _line(s, "Ghee", 38, "jar=500")
    made = ok(kitchen.post(f"{API}/foods/{ghee}/sizes", json={"name": "tin", "amount": 100}), 201)
    # Nothing Usual (a size can only be made Usual, never un-made): drop the flag directly.
    with db(kitchen) as session:
        for size in session.query(FoodSize).filter(FoodSize.food_id == ghee):
            size.usual = False
        session.commit()
    assert len(made["food"]["sizes"]) == 2
    _tick(s, "Ghee")
    assert s.total("Ghee") == 38


def test_an_ingredient_with_no_size_goes_in_as_listed(kitchen: TestClient) -> None:
    s = s0(kitchen)
    _line(s, "Ghee", 38)
    _tick(s, "Ghee")
    assert s.total("Ghee") == 38


def test_a_line_already_in_packs_goes_in_as_it_is(kitchen: TestClient) -> None:
    s = s0(kitchen)
    ghee = food(kitchen, "Ghee", counted_as="weight", place_id=s.places["Cupboard"])["id"]
    made = ok(kitchen.post(f"{API}/foods/{ghee}/sizes", json={"name": "jar", "amount": 500}), 201)
    item = new_id()
    send(
        kitchen,
        action(
            "add",
            counter(kitchen),
            list_id=s.main,
            item_id=item,
            food_id=ghee,
            amount=750,
            size_id=made["food"]["sizes"][0]["id"],
        ),
    )
    s.foods["Ghee"], s.items["Ghee"] = ghee, item
    _tick(s, "Ghee")
    assert s.total("Ghee") == 750  # a jar and a half, as before: the line was already in packs


def test_a_counted_ingredient_rounds_up_to_whole_boxes(kitchen: TestClient) -> None:
    s = s0(kitchen)
    _line(s, "Eggs for baking", 4, "box=6", counted_as="count")
    done = _tick(s, "Eggs for baking")
    assert s.total("Eggs for baking") == 6
    assert done["change"]["summary"] == "Bought 1\u00a0box Eggs for baking → Cupboard"


def test_a_staple_still_puts_nothing_in(kitchen: TestClient) -> None:
    s = s0(kitchen)
    _line(s, "Ghee", 38, "jar=500", staple=True)
    _tick(s, "Ghee")
    assert s.total("Ghee") == 0


def test_undo_of_the_tick_takes_out_the_whole_jar(kitchen: TestClient) -> None:
    s = s0(kitchen)
    _line(s, "Ghee", 38, "jar=500")
    done = _tick(s, "Ghee")
    assert s.total("Ghee") == 500
    undone = one(kitchen, "undo", counter(kitchen), PHONE_A, undoes=done["id"])
    assert undone["status"] == "applied"
    assert s.total("Ghee") == 0


def test_a_queued_tick_sent_later_puts_the_jar_in_too(kitchen: TestClient) -> None:
    """A phone offline sends its tick with the rest of its queue; the server decides there."""
    s = s0(kitchen)
    _line(s, "Ghee", 38, "jar=500")
    tick_id = new_id()
    send(
        kitchen,
        action("tick", s.c0, id=tick_id, item_id=s.items["Ghee"]),
        action(
            "put_away",
            s.c0,
            item_id=s.items["Ghee"],
            place_id=s.places["Cupboard"],
            tick_ids=[tick_id],
        ),
        device=PHONE_R,
    )
    assert s.total("Ghee") == 500


# --- A cap on packets (review round 1): a tiny size can't make a million packets ----------


def _lot_count(s: S0, name: str) -> int:
    return len(s.lots(name))


def test_a_tiny_size_and_a_huge_line_goes_in_as_listed_not_as_a_million_packets(
    kitchen: TestClient,
) -> None:
    s = s0(kitchen)
    _line(s, "Ghee", 1_000_000, "grain=0.001")
    started = time.monotonic()
    done = _tick(s, "Ghee")
    assert time.monotonic() - started < 5
    assert done["status"] == "applied"
    assert s.lots("Ghee") == [("Cupboard", 1_000_000)]


def test_twenty_thousand_grams_with_a_one_gram_size_is_quick_and_one_lot(
    kitchen: TestClient,
) -> None:
    s = s0(kitchen)
    _line(s, "Rock salt", 20_000, "pinch=1")
    started = time.monotonic()
    _tick(s, "Rock salt")
    assert time.monotonic() - started < 5
    assert s.lots("Rock salt") == [("Cupboard", 20_000)]


def test_fifty_packs_still_round_up_and_fifty_one_does_not(kitchen: TestClient) -> None:
    s = s0(kitchen)
    _line(s, "Ghee", 24_900, "jar=500")  # 49.8 jars -> 50 whole jars
    _line(s, "Oil", 25_100, "jar=500")  # 50.2 jars -> over the cap, as listed
    _tick(s, "Ghee")
    _tick(s, "Oil")
    assert _lot_count(s, "Ghee") == 50 and s.total("Ghee") == 25_000
    assert s.lots("Oil") == [("Cupboard", 25_100)]


def test_a_line_already_in_packs_is_capped_too(kitchen: TestClient) -> None:
    s = s0(kitchen)
    ghee = food(kitchen, "Ghee", counted_as="weight", place_id=s.places["Cupboard"])["id"]
    made = ok(kitchen.post(f"{API}/foods/{ghee}/sizes", json={"name": "grain", "amount": 1}), 201)
    item = new_id()
    send(
        kitchen,
        action(
            "add",
            counter(kitchen),
            list_id=s.main,
            item_id=item,
            food_id=ghee,
            amount=20_000,
            size_id=made["food"]["sizes"][0]["id"],
        ),
    )
    s.foods["Ghee"], s.items["Ghee"] = ghee, item
    _tick(s, "Ghee")
    assert s.lots("Ghee") == [("Cupboard", 20_000)]


def test_a_queued_tick_of_a_huge_line_is_capped_too(kitchen: TestClient) -> None:
    s = s0(kitchen)
    _line(s, "Rock salt", 20_000, "pinch=1")
    tick_id = new_id()
    started = time.monotonic()
    send(
        kitchen,
        action("tick", s.c0, id=tick_id, item_id=s.items["Rock salt"]),
        action(
            "put_away",
            s.c0,
            item_id=s.items["Rock salt"],
            place_id=s.places["Cupboard"],
            tick_ids=[tick_id],
        ),
        device=PHONE_R,
    )
    assert time.monotonic() - started < 5
    assert s.lots("Rock salt") == [("Cupboard", 20_000)]
