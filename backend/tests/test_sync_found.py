"""Already have it (`found_at_home`, docs/dev/sync-protocol.md 4.2 and 7.6): the amount at home
goes into the pantry as found, not bought; repeats, Undo, untick and two phones."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sync_kit import (
    API,
    PHONE_A,
    PHONE_B,
    PHONE_R,
    S0,
    action,
    changes,
    db,
    food,
    ok,
    one,
    s0,
    send,
    tick,
)

from mealwright.models import Food, StockLot


def _found(
    client: TestClient, s: S0, name: str, amount: int, place: str | None = None, **extra: object
) -> object:
    fields: dict[str, object] = {"item_id": s.items[name], "amount": amount, **extra}
    if place is not None:
        fields["place_id"] = s.places[place]
    device = extra.pop("device", PHONE_A) if "device" in extra else PHONE_A
    fields.pop("device", None)
    return one(client, "found_at_home", s.c0, str(device), **fields)


def test_found_goes_into_the_pantry_as_found_not_bought(kitchen: TestClient) -> None:
    s = s0(kitchen)
    done = _found(kitchen, s, "Toor dal", 500, "Cupboard", size_id=s.sizes["Toor dal"])
    assert done["status"] == "applied"  # type: ignore[index]
    assert s.lots("Toor dal") == [("Cupboard", 500)]
    assert s.changes_of("Toor dal", "shopped") == []
    (change,) = s.changes_of("Toor dal", "found")
    assert change.summary == "Found Toor dal at home: 1\u00a0packet → Cupboard"
    row = s.item(kitchen, "Toor dal")
    (t,) = row["ticks"]
    assert t["found"] is True and t["standing"] and t["bought"]["amount"] == 500
    assert t["place_id"] == s.places["Cupboard"]


def _how_added(client: TestClient) -> dict[str, list[str]]:
    """Each ingredient's lots in the Pantry, with how each one got there."""
    out: dict[str, list[str]] = {}
    for place in client.get(f"{API}/pantry").json()["places"]:
        for group in place["groups"]:
            out.setdefault(group["food"]["name"], []).extend(
                lot["how_added"] for lot in group["lots"]
            )
    return out


def test_a_lot_found_at_home_says_found_and_a_bought_one_says_bought(kitchen: TestClient) -> None:
    """F201: the Pantry tells a lot found at home from a bought one, by the change that made it."""
    s = s0(kitchen)
    _found(kitchen, s, "Toor dal", 500, "Cupboard", size_id=s.sizes["Toor dal"])
    tick(kitchen, s, "Milk")
    typed = kitchen.post(
        f"{API}/stock",
        json={
            "food_id": s.foods["Paneer"],
            "place_id": s.places["Fridge"],
            "amount": {"amount": 200, "unit": "g"},
        },
    )
    assert typed.status_code == 201, typed.text
    seen = _how_added(kitchen)
    assert seen["Toor dal"] == ["found"]
    assert seen["Milk"] == ["bought"]
    assert seen["Paneer"] == ["found"]  # typed in: nobody bought it here


def test_found_takes_only_what_is_at_home_not_the_list_amount(kitchen: TestClient) -> None:
    s = s0(kitchen)
    _found(kitchen, s, "Paneer", 100, "Fridge")
    assert s.lots("Paneer") == [("Fridge", 100)]
    (change,) = s.changes_of("Paneer", "found")
    assert change.summary == "Found Paneer at home: about ½\u00a0pack → Fridge"


def test_found_without_a_place_uses_the_usual_one(kitchen: TestClient) -> None:
    s = s0(kitchen)
    _found(kitchen, s, "Milk", 1000)
    assert s.lots("Milk") == [("Fridge", 1000)]


def test_a_tick_is_not_found(kitchen: TestClient) -> None:
    s = s0(kitchen)
    tick(kitchen, s, "Toor dal")
    assert s.item(kitchen, "Toor dal")["ticks"][0]["found"] is False


def test_found_sent_twice_is_applied_once(kitchen: TestClient) -> None:
    s = s0(kitchen)
    body = action(
        "found_at_home", s.c0, item_id=s.items["Milk"], amount=1000, place_id=s.places["Fridge"]
    )
    first = send(kitchen, body)["results"][0]
    again = send(kitchen, body)["results"][0]
    assert first["status"] == "applied" and again["repeat"] is True
    assert again["status"] == "applied"
    assert s.total("Milk") == 1000
    assert len(s.changes_of("Milk", "found")) == 1


def test_found_after_the_same_phone_ticked_is_ignored(kitchen: TestClient) -> None:
    s = s0(kitchen)
    tick(kitchen, s, "Milk")
    second = _found(kitchen, s, "Milk", 1000)
    assert (second["status"], second["reason"]) == ("ignored", "already_ticked")  # type: ignore[index]
    assert s.total("Milk") == 2000


def test_found_on_a_line_someone_removed_still_counts_like_a_tick(kitchen: TestClient) -> None:
    s = s0(kitchen)
    one(kitchen, "delete", s.c0, item_id=s.items["Milk"])
    done = _found(kitchen, s, "Milk", 1000)
    assert done["status"] == "applied"  # type: ignore[index]
    assert s.total("Milk") == 1000


def test_found_on_a_line_that_never_existed_is_ignored(kitchen: TestClient) -> None:
    s = s0(kitchen)
    done = one(kitchen, "found_at_home", s.c0, item_id="nope", amount=5)
    assert (done["status"], done["reason"]) == ("ignored", "gone")
    assert s.total("Milk") == 0


def test_found_for_a_staple_puts_nothing_in(kitchen: TestClient) -> None:
    s = s0(kitchen)
    done = _found(kitchen, s, "Salt", 500)
    assert done["status"] == "applied"  # type: ignore[index]
    assert s.total("Salt") == 0
    assert s.changes_of("Salt", "found") == []


@pytest.mark.parametrize("amount", [0, -5])
def test_found_needs_an_amount_above_nothing(kitchen: TestClient, amount: int) -> None:
    s = s0(kitchen)
    done = _found(kitchen, s, "Milk", amount)
    assert (done["status"], done["reason"]) == ("refused", "bad_action")  # type: ignore[index]


def test_undo_of_found_takes_it_out_and_unticks(kitchen: TestClient) -> None:
    s = s0(kitchen)
    done = _found(kitchen, s, "Toor dal", 500, "Cupboard")
    undone = one(kitchen, "undo", s.c0, PHONE_A, undoes=done["id"])  # type: ignore[index]
    assert undone["status"] == "applied"
    assert s.total("Toor dal") == 0
    assert s.item(kitchen, "Toor dal")["ticks"][0]["standing"] is False


def test_untick_of_found_then_undo_puts_it_back_as_found(kitchen: TestClient) -> None:
    s = s0(kitchen)
    done = _found(kitchen, s, "Toor dal", 500, "Cupboard")
    gone = one(
        kitchen,
        "untick",
        s.c0,
        item_id=s.items["Toor dal"],
        tick_ids=[done["id"]],  # type: ignore[index]
    )
    assert s.total("Toor dal") == 0
    one(kitchen, "undo", s.c0, PHONE_A, undoes=gone["id"])
    assert s.total("Toor dal") == 500
    assert s.changes_of("Toor dal", "shopped") == []
    assert len(s.changes_of("Toor dal", "found")) == 2


def test_different_pack_does_not_apply_to_found(kitchen: TestClient) -> None:
    s = s0(kitchen)
    done = _found(kitchen, s, "Paneer", 100)
    r = one(
        kitchen,
        "different_pack",
        s.c0,
        item_id=s.items["Paneer"],
        tick_id=done["id"],  # type: ignore[index]
        count=1,
        pack=400,
    )
    assert (r["status"], r["reason"]) == ("ignored", "no_change")
    assert s.total("Paneer") == 100


def test_found_on_two_phones_counts_once_and_the_second_phone_is_told(
    kitchen: TestClient,
) -> None:
    # RF2 Sh2 (cabledrawer 11 Nov, spec "Found at home twice"): this used to be two finds and 1500
    # in the pantry for one carton at home (review of the whole of 0.8, Sh2).
    s = s0(kitchen)
    first = _found(kitchen, s, "Milk", 1000, device=PHONE_A)
    second = _found(s.wren, s, "Milk", 500, device=PHONE_R)
    assert first["status"] == "applied"  # type: ignore[index]
    assert (second["status"], second["reason"]) == ("ignored", "already_found")  # type: ignore[index]
    assert second["message"] == "Already found at home by the other phone."  # type: ignore[index]
    assert second.get("change") is None  # type: ignore[union-attr]  # nothing to undo
    assert s.total("Milk") == 1000
    assert [q for q in changes(kitchen)["questions"] if q["open"]] == []
    assert len(s.item(kitchen, "Milk")["ticks"]) == 1
    assert len(s.changes_of("Milk", "found")) == 1


def test_found_twice_still_lets_the_first_be_undone_and_then_found_again(
    kitchen: TestClient,
) -> None:
    s = s0(kitchen)
    first = _found(kitchen, s, "Milk", 1000, device=PHONE_A)
    _found(s.wren, s, "Milk", 500, device=PHONE_R)
    one(kitchen, "undo", s.c0, PHONE_A, undoes=first["id"])  # type: ignore[index]
    assert s.total("Milk") == 0
    again = _found(s.wren, s, "Milk", 500, device=PHONE_R)
    assert again["status"] == "applied"  # type: ignore[index]
    assert s.total("Milk") == 500


def test_found_then_a_bought_tick_on_another_phone_asks_nothing(kitchen: TestClient) -> None:
    s = s0(kitchen)
    _found(kitchen, s, "Milk", 1000, device=PHONE_A)
    tick(kitchen, s, "Milk", PHONE_B)
    assert [q for q in changes(kitchen)["questions"] if q["open"]] == []
    assert s.total("Milk") == 3000


def test_found_from_the_pantry_recent_changes_can_be_undone(kitchen: TestClient) -> None:
    s = s0(kitchen)
    _found(kitchen, s, "Toor dal", 500, "Cupboard")
    (change,) = s.changes_of("Toor dal", "found")
    r = kitchen.post(f"/api/v1/changes/{change.id}/undo", headers={"Idempotency-Key": "k-found-1"})
    assert r.status_code == 200, r.text
    assert s.total("Toor dal") == 0
    assert s.item(kitchen, "Toor dal")["ticks"][0]["standing"] is False


def test_found_brings_back_a_removed_ingredient_and_undo_removes_it_again(
    kitchen: TestClient,
) -> None:
    """Phone B removed the line and Paneer; phone A's offline "Already have it" still lands:
    the ingredient comes back (as for a tick, 7.1) so the stock isn't hidden."""
    s = s0(kitchen)
    one(s.wren, "delete", s.c0, PHONE_R, item_id=s.items["Paneer"])
    ok(s.wren.delete(f"{API}/foods/{s.foods['Paneer']}"))
    done = _found(kitchen, s, "Paneer", 200, "Fridge")
    assert done["status"] == "applied"  # type: ignore[index]
    assert done["message"] == "Paneer is back in Ingredients."  # type: ignore[index]
    with db(kitchen) as session:
        assert session.get(Food, s.foods["Paneer"]).removed_at is None  # type: ignore[union-attr]
    assert s.total("Paneer") == 200
    undone = one(kitchen, "undo", 0, PHONE_A, undoes=done["id"])  # type: ignore[index]
    assert undone["status"] == "applied"
    assert s.total("Paneer") == 0
    with db(kitchen) as session:
        assert session.get(Food, s.foods["Paneer"]).removed_at is not None  # type: ignore[union-attr]


def test_found_against_a_delete_tells_the_finder_like_a_tick(kitchen: TestClient) -> None:
    """L-9 / N1: the deleter hadn't seen the find."""
    s = s0(kitchen)
    _found(s.wren, s, "Milk", 1000, device=PHONE_R)
    one(kitchen, "delete", s.c0, PHONE_A, item_id=s.items["Milk"])
    (note,) = changes(s.wren)["notes"]
    assert note["text"] == "Tess had removed this. Your tick still went into the pantry."


@pytest.mark.parametrize("a_first", [True, False], ids=["A-B", "B-A"])
def test_found_against_a_delete(kitchen: TestClient, a_first: bool) -> None:
    """Both orders: the find still goes in; the finder gets N1 whichever lands first."""
    s = s0(kitchen)
    item = s.items["Paneer"]
    steps = [
        lambda: _found(kitchen, s, "Paneer", 200, "Fridge"),
        lambda: one(s.wren, "delete", s.c0, PHONE_R, item_id=item),
    ]
    for step in steps if a_first else steps[::-1]:
        step()
    assert s.lots("Paneer") == [("Fridge", 200)]
    (note,) = changes(kitchen)["notes"]
    assert note["text"] == "Wren had removed this. Your tick still went into the pantry."
    assert changes(s.wren)["notes"] == []


def test_found_into_an_ingredient_counted_differently_puts_nothing_in(
    kitchen: TestClient,
) -> None:
    s = s0(kitchen)
    one(s.wren, "delete", s.c0, PHONE_R, item_id=s.items["Paneer"])
    ok(s.wren.delete(f"{API}/foods/{s.foods['Paneer']}"))
    new = food(kitchen, "Paneer", counted_as="count")["id"]
    done: Any = _found(kitchen, s, "Paneer", 200, "Fridge")
    assert done["status"] == "applied" and done["change"] is None
    with db(kitchen) as session:
        assert session.query(StockLot).filter(StockLot.amount_milli > 0).count() == 0
    (note,) = changes(kitchen)["notes"]
    assert note["text"] == "Paneer is counted differently now, so nothing went into the pantry."
    assert (note["undo"], note["food_id"]) == (done["id"], new)
