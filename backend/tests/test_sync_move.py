"""Moving a line to another shop or list (docs/dev/sync-protocol.md 4.2, rules M-1 to M-7,
tests SY-67 to SY-73): works from a queue, adds up with a line already there, only unticked
lines move, and each clash with another phone has one answer."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sync_kit import (
    API,
    PHONE_A,
    PHONE_R,
    WREN_PASSWORD,
    S0,
    action,
    changes,
    db,
    food,
    main_id,
    new_id,
    ok,
    one,
    s0,
    send,
    tick,
)

from mealwright.auth import hash_password
from mealwright.household import add_default_places
from mealwright.models import Household, ListItem, Login

BOTH = pytest.mark.parametrize("a_first", [True, False], ids=["A-B", "B-A"])


def _in_order(a_first: bool, a: Any, b: Any) -> None:
    for step in (a, b) if a_first else (b, a):
        step()


def _undo(client: TestClient, action_id: str, device: str = PHONE_A) -> Any:
    return one(client, "undo", 0, device, undoes=action_id)


def _move(client: TestClient, s: S0, name: str, shop: int | None, **extra: Any) -> Any:
    device = extra.pop("device", PHONE_A)
    seen = extra.pop("seen", s.c0)
    return one(
        client,
        "move",
        seen,
        device,
        item_id=s.items[name],
        list_id=extra.pop("list_id", s.main),
        shop_id=shop,
    )


def _party(client: TestClient) -> str:
    made = new_id()
    send(client, action("create_list", list_id=made, name="Diwali party"))
    return made


def _where(client: TestClient, item_id: str) -> tuple[str, int | None]:
    row = next(r for r in changes(client)["items"] if r["id"] == item_id)
    return row["list_id"], row["shop_id"]


def _live(client: TestClient, s: S0, name: str) -> list[Any]:
    return [
        r
        for r in changes(client)["items"]
        if r["food_id"] == s.foods[name] and not r["deleted"] and not r.get("merged_into_id")
    ]


def test_sy67_move_to_another_shop(kitchen: TestClient) -> None:
    s = s0(kitchen)
    grocer = s.shops["Indian grocer"]
    result = _move(kitchen, s, "Coriander", grocer)
    assert result["status"] == "applied"
    assert _where(kitchen, s.items["Coriander"]) == (s.main, grocer)
    row = s.item(kitchen, "Coriander")
    assert row["amount"] == 1 and row["ticks"] == []
    change = ok(kitchen.get(f"{API}/changes?limit=1"))["changes"][0]
    assert change["summary"] == "Moved Coriander to Indian grocer"
    assert _undo(kitchen, result["id"])["status"] == "applied"
    assert _where(kitchen, s.items["Coriander"]) == (s.main, s.shops["Supermarket"])


def test_sy67_move_to_any_shop_and_to_another_list(kitchen: TestClient) -> None:
    s = s0(kitchen)
    party = _party(kitchen)
    anywhere = _move(kitchen, s, "Milk", None)
    assert anywhere["status"] == "applied"
    assert _where(kitchen, s.items["Milk"]) == (s.main, None)
    other = _move(kitchen, s, "Onions", s.shops["Supermarket"], list_id=party)
    assert other["status"] == "applied"
    assert _where(kitchen, s.items["Onions"]) == (party, s.shops["Supermarket"])
    summary = ok(kitchen.get(f"{API}/changes?limit=1"))["changes"][0]["summary"]
    assert summary == "Moved Onions to Diwali party"
    # Moving to where it already is changes nothing.
    again = _move(kitchen, s, "Onions", s.shops["Supermarket"], list_id=party)
    assert (again["status"], again["reason"]) == ("ignored", "no_change")


def test_sy68_move_adds_up_with_the_line_already_there(kitchen: TestClient) -> None:
    s = s0(kitchen)
    grocer = s.shops["Indian grocer"]
    extra = new_id()
    send(
        kitchen,
        action(
            "add",
            list_id=s.main,
            item_id=extra,
            food_id=s.foods["Milk"],
            amount=1000,
            shop_id=grocer,
        ),
    )
    moved = _move(kitchen, s, "Milk", grocer, seen=s.c0 + 1)
    assert moved["status"] == "merged" and moved["item_id"] == extra
    (line,) = _live(kitchen, s, "Milk")
    assert line["id"] == extra and line["amount"] == 3000 and line["hand_edited"] is True
    assert s.item(kitchen, "Milk", s.c0)["deleted"] is True
    # Undo splits them again.
    assert _undo(kitchen, moved["id"])["status"] == "applied"
    amounts = sorted(r["amount"] for r in _live(kitchen, s, "Milk"))
    assert amounts == [1000, 2000]
    assert _where(kitchen, s.items["Milk"]) == (s.main, s.shops["Supermarket"])


def test_sy68_undo_of_a_join_leaves_it_alone_once_the_joined_line_is_ticked(
    kitchen: TestClient,
) -> None:
    s = s0(kitchen)
    grocer = s.shops["Indian grocer"]
    extra = new_id()
    send(
        kitchen,
        action(
            "add",
            list_id=s.main,
            item_id=extra,
            food_id=s.foods["Milk"],
            amount=1000,
            shop_id=grocer,
        ),
    )
    moved = _move(kitchen, s, "Milk", grocer, seen=s.c0 + 1)
    assert moved["status"] == "merged"
    assert one(kitchen, "tick", s.c0 + 3, item_id=extra)["status"] == "applied"
    result = _undo(kitchen, moved["id"])
    # Nothing is put back: the 3 L were bought, so no 2 L is asked for again.
    (line,) = _live(kitchen, s, "Milk")
    assert line["id"] == extra and line["amount"] == 3000
    assert s.item(kitchen, "Milk", s.c0)["deleted"] is True
    assert result["status"] == "applied"
    assert result["message"] == "Nothing to put back: it has all changed again since."


def test_sy68_a_blank_line_there_and_the_moved_amount_add_up(kitchen: TestClient) -> None:
    s = s0(kitchen)
    grocer = s.shops["Indian grocer"]
    there = new_id()
    send(
        kitchen,
        action("add", list_id=s.main, item_id=there, food_id=s.foods["Onions"], shop_id=grocer),
    )
    moved = _move(kitchen, s, "Onions", grocer, seen=s.c0 + 1)
    assert moved["status"] == "merged"
    (line,) = _live(kitchen, s, "Onions")
    assert line["amount"] == 6  # the blank add made 1 (items); 1 + 5


def test_sy68_a_ticked_line_there_is_not_joined(kitchen: TestClient) -> None:
    s = s0(kitchen)
    grocer = s.shops["Indian grocer"]
    there = new_id()
    send(
        kitchen,
        action(
            "add", list_id=s.main, item_id=there, food_id=s.foods["Eggs"], amount=6, shop_id=grocer
        ),
    )
    assert one(kitchen, "tick", s.c0 + 1, item_id=there)["status"] == "applied"
    eggs = new_id()
    send(kitchen, action("add", list_id=s.main, item_id=eggs, food_id=s.foods["Eggs"], amount=12))
    moved = one(kitchen, "move", s.c0 + 3, item_id=eggs, list_id=s.main, shop_id=grocer)
    assert moved["status"] == "applied"  # a separate line, as for an add (L-12)
    assert _where(kitchen, eggs) == (s.main, grocer)


def test_sy69_only_unticked_lines_move(kitchen: TestClient) -> None:
    s = s0(kitchen)
    tick(kitchen, s, "Coriander")
    result = _move(kitchen, s, "Coriander", s.shops["Indian grocer"])
    assert (result["status"], result["reason"]) == ("ignored", "ticked")
    assert _where(kitchen, s.items["Coriander"]) == (s.main, s.shops["Supermarket"])
    assert changes(kitchen)["notes"] == []  # same phone: it can see its own tick
    # Unticking makes it movable again.
    ids = [t.id for t in s.ticks("Coriander")]
    one(kitchen, "untick", s.c0, item_id=s.items["Coriander"], tick_ids=ids)
    assert _move(kitchen, s, "Coriander", None)["status"] == "applied"


@BOTH
def test_sy69_move_against_a_tick(kitchen: TestClient, a_first: bool) -> None:
    s = s0(kitchen)
    grocer = s.shops["Indian grocer"]
    results: dict[str, Any] = {}
    _in_order(
        a_first,
        lambda: results.update(move=_move(kitchen, s, "Paneer", grocer)),
        lambda: results.update(tick=tick(s.wren, s, "Paneer", PHONE_R)),
    )
    assert results["tick"]["status"] == "applied"  # a tick always counts
    row = s.item(kitchen, "Paneer")
    assert row["ticks"] and s.total("Paneer") == 400
    if a_first:  # moved, then ticked where it now is
        assert results["move"]["status"] == "applied"
        assert _where(kitchen, s.items["Paneer"]) == (s.main, grocer)
        assert changes(kitchen)["notes"] == []
    else:  # ticked first: the move is not made, and the mover is told
        assert (results["move"]["status"], results["move"]["reason"]) == ("ignored", "ticked")
        assert _where(kitchen, s.items["Paneer"])[1] == s.shops["Supermarket"]
        (note,) = changes(kitchen)["notes"]
        assert note["text"] == "Wren had ticked Paneer, so it wasn’t moved."
        assert note["undo"] is None


@BOTH
def test_sy70_move_against_a_delete(kitchen: TestClient, a_first: bool) -> None:
    s = s0(kitchen)
    results: dict[str, Any] = {}
    _in_order(
        a_first,
        lambda: results.update(move=_move(kitchen, s, "Milk", None)),
        lambda: results.update(
            delete=one(s.wren, "delete", s.c0, PHONE_R, item_id=s.items["Milk"])
        ),
    )
    assert s.item(kitchen, "Milk", s.c0)["deleted"] is True
    if a_first:
        assert results["delete"]["status"] == "applied"
        assert changes(kitchen)["notes"] == []
    else:
        assert (results["move"]["status"], results["move"]["reason"]) == ("ignored", "deleted")
        (note,) = changes(kitchen)["notes"]
        assert note["text"] == "Wren had removed Milk, so your change wasn’t kept."
        assert _undo(kitchen, note["undo"])["status"] == "applied"
        assert s.item(kitchen, "Milk", s.c0)["deleted"] is False


@BOTH
def test_sy71_move_against_an_amount(kitchen: TestClient, a_first: bool) -> None:
    s = s0(kitchen)
    grocer = s.shops["Indian grocer"]
    _in_order(
        a_first,
        lambda: _move(kitchen, s, "Milk", grocer),
        lambda: one(s.wren, "set_amount", s.c0, PHONE_R, item_id=s.items["Milk"], amount=4000),
    )
    row = s.item(kitchen, "Milk")
    assert (row["amount"], row["shop_id"]) == (4000, grocer)  # both stand, either order
    assert changes(kitchen)["notes"] == [] and changes(s.wren)["notes"] == []


@BOTH
def test_sy71_amount_against_a_move_that_joined_a_line(kitchen: TestClient, a_first: bool) -> None:
    s = s0(kitchen)
    grocer = s.shops["Indian grocer"]
    there = new_id()
    send(
        kitchen,
        action(
            "add",
            list_id=s.main,
            item_id=there,
            food_id=s.foods["Milk"],
            amount=1000,
            shop_id=grocer,
        ),
    )
    seen = s.c0 + 1
    results: dict[str, Any] = {}
    _in_order(
        a_first,
        lambda: results.update(move=_move(kitchen, s, "Milk", grocer, seen=seen)),
        lambda: results.update(
            set=one(s.wren, "set_amount", seen, PHONE_R, item_id=s.items["Milk"], amount=4000)
        ),
    )
    (line,) = _live(kitchen, s, "Milk")
    if a_first:  # joined (3 L); Wren's edit of the line that was taken off is not kept
        assert line["amount"] == 3000
        assert (results["set"]["status"], results["set"]["reason"]) == ("ignored", "deleted")
        (note,) = changes(s.wren)["notes"]
        assert note["text"] == "Tess had moved Milk, so your change wasn’t kept."
        # Undo of the note takes the move back: Wren's line is there again, at the old amount.
        assert _undo(s.wren, note["undo"], PHONE_R)["status"] == "applied"
        assert sorted(r["amount"] for r in _live(kitchen, s, "Milk")) == [1000, 2000]
    else:  # Wren's 4 L is what joins the line there (5 L)
        assert line["amount"] == 5000
        assert changes(kitchen)["notes"] == [] and changes(s.wren)["notes"] == []


@BOTH
def test_sy72_two_moves(kitchen: TestClient, a_first: bool) -> None:
    s = s0(kitchen)
    grocer, party = s.shops["Indian grocer"], _party(kitchen)
    results: dict[str, Any] = {}
    _in_order(
        a_first,
        lambda: results.update(a=_move(kitchen, s, "Coriander", grocer, seen=s.c0 + 1)),
        lambda: results.update(
            b=one(
                s.wren,
                "move",
                s.c0 + 1,
                PHONE_R,
                item_id=s.items["Coriander"],
                list_id=party,
                shop_id=None,
            )
        ),
    )
    assert results["a"]["status"] == results["b"]["status"] == "applied"
    last = (party, None) if a_first else (s.main, grocer)
    assert _where(kitchen, s.items["Coriander"]) == last
    loser = kitchen if a_first else s.wren
    (note,) = changes(loser)["notes"]
    expected = (
        "Wren moved Coriander to Diwali party"
        if a_first
        else "Tess moved Coriander to This week"
    )
    assert note["text"] == expected
    # Undo of the note puts the first mover's choice back.
    device = PHONE_A if a_first else PHONE_R
    assert _undo(loser, note["undo"], device)["status"] == "applied"
    assert _where(kitchen, s.items["Coriander"]) == ((s.main, grocer) if a_first else (party, None))


def test_sy72_a_second_move_of_a_line_a_move_joined_is_not_kept(kitchen: TestClient) -> None:
    s = s0(kitchen)
    grocer = s.shops["Indian grocer"]
    there = new_id()
    send(
        kitchen,
        action(
            "add", list_id=s.main, item_id=there, food_id=s.foods["Eggs"], amount=6, shop_id=grocer
        ),
    )
    eggs = new_id()
    send(kitchen, action("add", list_id=s.main, item_id=eggs, food_id=s.foods["Eggs"], amount=6))
    first = one(kitchen, "move", s.c0 + 2, item_id=eggs, list_id=s.main, shop_id=grocer)
    assert first["status"] == "merged"
    stale = one(s.wren, "move", s.c0 + 2, PHONE_R, item_id=eggs, list_id=s.main, shop_id=None)
    assert (stale["status"], stale["reason"]) == ("ignored", "deleted")
    (note,) = changes(s.wren)["notes"]
    assert note["text"] == "Tess had moved Eggs, so your change wasn’t kept."


def test_sy72_a_tick_of_a_line_a_move_joined_still_counts(kitchen: TestClient) -> None:
    s = s0(kitchen)
    grocer = s.shops["Indian grocer"]
    there = new_id()
    send(
        kitchen,
        action(
            "add",
            list_id=s.main,
            item_id=there,
            food_id=s.foods["Milk"],
            amount=1000,
            shop_id=grocer,
        ),
    )
    _move(kitchen, s, "Milk", grocer, seen=s.c0 + 1)
    stale = tick(s.wren, s, "Milk", PHONE_R, seen=s.c0 + 1)
    assert stale["status"] == "applied"
    assert s.total("Milk") == 2000  # the 2 L Wren saw
    (note,) = changes(s.wren)["notes"]
    assert note["text"] == "Tess had moved this. Your tick still went into the pantry."


def test_sy73_a_move_into_nothing(kitchen: TestClient) -> None:
    s = s0(kitchen)
    gone_list = _party(kitchen)
    send(kitchen, action("remove_list", list_id=gone_list))
    result = _move(kitchen, s, "Milk", None, list_id=gone_list)
    assert (result["status"], result["reason"]) == ("ignored", "gone")
    assert result["message"] == "That list was removed, so Milk wasn’t moved."
    no_shop = _move(kitchen, s, "Milk", 99999)
    assert (no_shop["status"], no_shop["reason"]) == ("ignored", "gone")
    assert no_shop["message"] == "That shop was removed, so Milk wasn’t moved."
    unknown = one(kitchen, "move", s.c0, item_id=new_id(), list_id=s.main, shop_id=None)
    assert (unknown["status"], unknown["reason"]) == ("ignored", "gone")


def test_sy73_another_households_list_shop_and_line_are_not_here(kitchen: TestClient) -> None:
    s = s0(kitchen)
    with db(kitchen) as session:
        session.add(Household(id=2, name="Next door"))
        session.flush()
        add_default_places(session, 2)
        session.add(
            Login(
                household_id=2,
                username="neighbour",
                name="Neighbour",
                password_hash=hash_password(WREN_PASSWORD),
                role="admin",
            )
        )
        session.commit()
    neighbour = TestClient(kitchen.app, base_url="https://testserver")
    ok(neighbour.post(f"{API}/session", json={"username": "neighbour", "password": WREN_PASSWORD}))
    their_shop = ok(neighbour.post(f"{API}/shops", json={"name": "Far shop"}), 201)["id"]
    their_list = new_id()
    send(neighbour, action("create_list", list_id=their_list, name="Theirs"))
    bread = food(neighbour, "Bread", counted_as="count")["id"]
    their_line = new_id()
    send(
        neighbour,
        action("add", list_id=main_id(neighbour), item_id=their_line, food_id=bread, amount=1),
    )
    into_list = _move(kitchen, s, "Milk", None, list_id=their_list)
    assert (into_list["status"], into_list["reason"]) == ("ignored", "gone")
    into_shop = _move(kitchen, s, "Milk", their_shop)
    assert (into_shop["status"], into_shop["reason"]) == ("ignored", "gone")
    theirs = one(kitchen, "move", s.c0, item_id=their_line, list_id=s.main, shop_id=None)
    assert (theirs["status"], theirs["reason"]) == ("ignored", "gone")
    assert _where(kitchen, s.items["Milk"]) == (s.main, s.shops["Supermarket"])
    with db(kitchen) as session:
        row = session.get(ListItem, their_line)
        assert row is not None and (row.household_id, row.list_id) == (2, main_id(neighbour))


def test_sy73_sent_twice_is_applied_once(kitchen: TestClient) -> None:
    s = s0(kitchen)
    grocer = s.shops["Indian grocer"]
    move = action("move", s.c0, item_id=s.items["Coriander"], list_id=s.main, shop_id=grocer)
    first = send(kitchen, move)["results"][0]
    again = send(kitchen, move)["results"][0]
    assert first["repeat"] is False and again["repeat"] is True and again["seq"] == first["seq"]
    # Same ID, different words → refused.
    other = {**move, "shop_id": None}
    assert send(kitchen, other)["results"][0]["reason"] == "key_reused"


def test_sy73_the_action_takes_exactly_its_fields(kitchen: TestClient) -> None:
    s = s0(kitchen)
    missing = send(kitchen, action("move", s.c0, item_id=s.items["Milk"], list_id=s.main))
    assert missing["results"][0]["reason"] == "bad_action"
    extra = send(
        kitchen,
        action("move", s.c0, item_id=s.items["Milk"], list_id=s.main, shop_id=None, amount=1),
    )
    assert extra["results"][0]["reason"] == "bad_action"


def test_sy73_undo_leaves_a_line_that_was_ticked_since(kitchen: TestClient) -> None:
    s = s0(kitchen)
    moved = _move(kitchen, s, "Paneer", s.shops["Indian grocer"])
    tick(kitchen, s, "Paneer")
    result = _undo(kitchen, moved["id"])
    assert result["status"] == "applied"
    assert _where(kitchen, s.items["Paneer"])[1] == s.shops["Indian grocer"]
