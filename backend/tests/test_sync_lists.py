"""List edits from two phones (docs/dev/sync-protocol.md sections 5, 6 and 14): deletes
against edits, two adds, two amounts, and things changed elsewhere while a phone was
offline."""

import threading
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sync_kit import (
    API,
    PHONE_A,
    PHONE_R,
    WREN_PASSWORD,
    S0,
    action,
    changes,
    counter,
    db,
    food,
    item_row,
    main_id,
    new_id,
    ok,
    one,
    s0,
    send,
    tick,
)

from mealwright.auth import hash_password
from mealwright.history import purge_removed
from mealwright.household import add_default_places
from mealwright.models import Food, Household, ListItem, Login, Shop, StockLot, SyncAction, utcnow

BOTH = pytest.mark.parametrize("a_first", [True, False], ids=["A-B", "B-A"])


def _in_order(a_first: bool, a: Any, b: Any) -> None:
    for step in (a, b) if a_first else (b, a):
        step()


def _undo(client: TestClient, action_id: str, device: str = PHONE_A) -> Any:
    return one(client, "undo", 0, device, undoes=action_id)


def _lines(client: TestClient, s: S0, name: str, list_id: str | None = None) -> list[Any]:
    return [
        row
        for row in changes(client)["items"]
        if row["food_id"] == s.foods[name]
        and row["list_id"] == (list_id or s.main)
        and not row.get("merged_into_id")  # an add's own ID, leading to the line it joined
    ]


# --- A delete against an edit (L-9) --------------------------------------------------------------


@pytest.mark.parametrize(("a_first", "back_at"), [(True, 2000), (False, 4000)], ids=["06", "07"])
def test_sy06_sy07_delete_against_an_edit(kitchen: TestClient, a_first: bool, back_at: int) -> None:
    s = s0(kitchen)
    milk = s.items["Milk"]
    results: dict[str, Any] = {}
    _in_order(
        a_first,
        lambda: results.update(delete=one(kitchen, "delete", s.c0, item_id=milk)),
        lambda: results.update(
            set=one(s.wren, "set_amount", s.c0, PHONE_R, item_id=milk, amount=4000)
        ),
    )
    assert s.item(kitchen, "Milk", s.c0)["deleted"] is True
    assert s.total("Milk") == 0
    (note,) = changes(s.wren)["notes"]
    assert note["text"] == "Tess had removed Milk, so your change wasn't kept."
    assert note["undo"] == results["delete"]["id"]
    assert changes(kitchen)["notes"] == []
    assert _undo(s.wren, note["undo"], PHONE_R)["status"] == "applied"
    row = s.item(kitchen, "Milk")
    assert row["deleted"] is False and row["amount"] == back_at


@BOTH
def test_sy45_deleted_on_both(kitchen: TestClient, a_first: bool) -> None:
    s = s0(kitchen)
    milk = s.items["Milk"]
    results: list[Any] = []
    _in_order(
        a_first,
        lambda: results.append(one(kitchen, "delete", s.c0, item_id=milk)),
        lambda: results.append(one(s.wren, "delete", s.c0, PHONE_R, item_id=milk)),
    )
    first, second = results
    assert first["status"] == "applied"
    assert (second["status"], second["reason"]) == ("ignored", "deleted")
    assert _undo(kitchen, second["id"])["reason"] == "nothing_to_undo"
    assert _undo(kitchen, first["id"])["status"] == "applied"
    assert s.item(kitchen, "Milk")["deleted"] is False


# --- Two adds of one ingredient (L-6, decision 8) ------------------------------------------------


@BOTH
def test_sy10_both_add_eggs(kitchen: TestClient, a_first: bool) -> None:
    s = s0(kitchen)
    eggs = s.foods["Eggs"]
    mine, hers = new_id(), new_id()
    results: dict[str, Any] = {}
    _in_order(
        a_first,
        lambda: results.update(
            a=one(kitchen, "add", s.c0, list_id=s.main, item_id=mine, food_id=eggs, amount=6)
        ),
        lambda: results.update(
            b=one(
                s.wren, "add", s.c0, PHONE_R, list_id=s.main, item_id=hers, food_id=eggs, amount=12
            )
        ),
    )
    later = results["b"] if a_first else results["a"]
    assert later["status"] == "merged"
    (line,) = _lines(kitchen, s, "Eggs")
    assert line["amount"] == 12
    (mine_note,) = changes(kitchen)["notes"]
    (her_note,) = changes(s.wren)["notes"]
    assert mine_note["text"] == "Wren added Eggs too"
    assert her_note["text"] == "Tess added Eggs too"
    assert mine_note["undo"] == later["id"] == her_note["undo"]
    assert _undo(kitchen, mine_note["undo"])["status"] == "applied"
    (line,) = _lines(kitchen, s, "Eggs")
    assert line["amount"] == (6 if a_first else 12)


@BOTH
def test_sy11_adds_to_other_lists_and_shops_stay_apart(kitchen: TestClient, a_first: bool) -> None:
    s = s0(kitchen)
    party = new_id()
    send(kitchen, action("create_list", list_id=party, name="Party"))
    seen = counter(kitchen)
    eggs = s.foods["Eggs"]

    def a() -> None:
        one(kitchen, "add", seen, list_id=s.main, item_id=new_id(), food_id=eggs, amount=6)

    def b() -> None:
        send(
            s.wren,
            action("add", seen, list_id=party, item_id=new_id(), food_id=eggs, amount=6),
            action(
                "add", seen, list_id=s.main, item_id=new_id(), food_id=eggs, amount=6, shop_id=None
            ),
            device=PHONE_R,
        )

    _in_order(a_first, a, b)
    assert sorted(row["shop_id"] or 0 for row in _lines(kitchen, s, "Eggs")) == sorted(
        [0, s.shops["Supermarket"]]
    )
    assert len(_lines(kitchen, s, "Eggs", party)) == 1
    assert changes(kitchen)["notes"] == [] and changes(s.wren)["notes"] == []


@BOTH
def test_sy39_two_new_ingredients_with_one_name(kitchen: TestClient, a_first: bool) -> None:
    s = s0(kitchen)
    results: dict[str, Any] = {}

    def a() -> None:
        results["a"] = one(
            kitchen,
            "add",
            s.c0,
            list_id=s.main,
            item_id=new_id(),
            new_food={"name": "Tahini", "counted_as": "weight"},
        )

    def b() -> None:
        results["b"] = one(
            s.wren,
            "add",
            s.c0,
            PHONE_R,
            list_id=s.main,
            item_id=new_id(),
            new_food={"name": "tahini", "counted_as": "count"},
        )

    _in_order(a_first, a, b)
    assert results["a"]["food_id"] == results["b"]["food_id"]
    with db(kitchen) as session:
        (made,) = session.scalars(select(Food).where(Food.name.ilike("tahini"))).all()
        assert (made.name, made.counted_as) == (
            ("Tahini", "weight") if a_first else ("tahini", "count")
        )
    lines = [
        row
        for row in changes(kitchen)["items"]
        if row["food_id"] == made.id and not row["merged_into_id"]
    ]
    assert len(lines) == 1
    assert len(changes(kitchen)["notes"]) == 1 and len(changes(s.wren)["notes"]) == 1


@BOTH
def test_sy39_variant_one_name_counted_two_ways(kitchen: TestClient, a_first: bool) -> None:
    """4.4 (pending cabledrawer): the second adder's amount was for another way of counting, so
    it isn't kept. Its add counts as a blank one, and the adder gets note N9."""
    s = s0(kitchen)
    results: dict[str, Any] = {}

    def a() -> None:
        results["a"] = one(
            kitchen,
            "add",
            s.c0,
            list_id=s.main,
            item_id=new_id(),
            new_food={"name": "Tahini", "counted_as": "weight"},
            amount=500,
        )

    def b() -> None:
        results["b"] = one(
            s.wren,
            "add",
            s.c0,
            PHONE_R,
            list_id=s.main,
            item_id=new_id(),
            new_food={"name": "tahini", "counted_as": "count"},
            amount=2,
        )

    _in_order(a_first, a, b)
    with db(kitchen) as session:
        (made,) = session.scalars(select(Food).where(Food.name.ilike("tahini"))).all()
        name = made.name
    (line,) = [
        row
        for row in changes(kitchen)["items"]
        if row["food_id"] == made.id and not row["merged_into_id"]
    ]
    # The first adder's amount stands: 500 g by weight, or 2 in items.
    assert line["amount"] == (500 if a_first else 2)
    late, first = (s.wren, kitchen) if a_first else (kitchen, s.wren)
    texts = [note["text"] for note in changes(late)["notes"]]
    n9 = f"{name} was already in Ingredients, counted another way, so check the amount."
    assert n9 in texts
    assert all("counted another way" not in note["text"] for note in changes(first)["notes"])
    (note,) = [note for note in changes(late)["notes"] if note["text"] == n9]
    assert note["undo"] == results["b" if a_first else "a"]["id"]
    assert note["item_id"] == line["id"]


def test_a_new_ingredient_counted_another_way_gets_a_blank_amount(kitchen: TestClient) -> None:
    """4.4 (pending cabledrawer): 500 g means nothing for a Tahini counted in items: 1."""
    s = s0(kitchen)
    there = food(kitchen, "Tahini", counted_as="count")["id"]
    item = new_id()
    added = one(
        s.wren,
        "add",
        s.c0,
        PHONE_R,
        list_id=s.main,
        item_id=item,
        new_food={"name": "tahini", "counted_as": "weight"},
        amount=500,
    )
    assert added["status"] == "applied" and added["food_id"] == there
    row = item_row(changes(kitchen), item)
    assert (row["amount"], row["size_id"]) == (1, None)
    (note,) = changes(s.wren)["notes"]
    assert (
        note["text"]
        == "Tahini was already in Ingredients, counted another way, so check the amount."
    )
    before = counter(kitchen)
    assert _undo(s.wren, note["undo"], PHONE_R)["status"] == "applied"
    assert item_row(changes(kitchen, before), item)["deleted"] is True
    assert changes(s.wren)["notes"] == []


def test_sy64_an_add_to_a_line_you_could_see(kitchen: TestClient) -> None:
    s = s0(kitchen)
    added = one(
        kitchen, "add", s.c0, list_id=s.main, item_id=new_id(), food_id=s.foods["Milk"], amount=1000
    )
    assert added["status"] == "merged"
    (line,) = _lines(kitchen, s, "Milk")
    assert line["amount"] == 3000
    assert changes(kitchen)["notes"] == []


def test_sy65_two_adds_from_one_phone(kitchen: TestClient) -> None:
    s = s0(kitchen)
    box = s.sizes["Eggs"]
    answer = send(
        kitchen,
        action(
            "add",
            s.c0,
            list_id=s.main,
            item_id=new_id(),
            food_id=s.foods["Eggs"],
            amount=6,
            size_id=box,
        ),
        action(
            "add",
            s.c0,
            list_id=s.main,
            item_id=new_id(),
            food_id=s.foods["Eggs"],
            amount=6,
            size_id=box,
        ),
    )
    assert [r["status"] for r in answer["results"]] == ["applied", "merged"]
    (line,) = _lines(kitchen, s, "Eggs")
    assert (line["amount"], line["size_id"]) == (12, box)
    assert line["display"] == "2\u00a0boxes"
    assert changes(kitchen)["notes"] == []


def test_sy65_variant_part_of_a_packet(kitchen: TestClient) -> None:
    s = s0(kitchen)
    one(
        kitchen,
        "add",
        s.c0,
        list_id=s.main,
        item_id=new_id(),
        food_id=s.foods["Toor dal"],
        amount=250,
    )
    line = s.item(kitchen, "Toor dal")
    assert line["amount"] == 750 and line["display"] == "1½\u00a0packets"


# --- Two amounts (L-7) ---------------------------------------------------------------------------


@BOTH
def test_sy12_two_amounts(kitchen: TestClient, a_first: bool) -> None:
    s = s0(kitchen)
    milk = s.items["Milk"]
    results: dict[str, Any] = {}
    _in_order(
        a_first,
        lambda: results.update(a=one(kitchen, "set_amount", s.c0, item_id=milk, amount=3000)),
        lambda: results.update(
            b=one(s.wren, "set_amount", s.c0, PHONE_R, item_id=milk, amount=4000)
        ),
    )
    row = s.item(kitchen, "Milk")
    assert row["amount"] == (4000 if a_first else 3000) and row["hand_edited"] is True
    loser, text, mine = (
        (kitchen, "Wren changed Milk to 4\u00a0L", 3000)
        if a_first
        else (s.wren, "Tess changed Milk to 3\u00a0L", 4000)
    )
    (note,) = changes(loser)["notes"]
    assert note["text"] == text
    device = PHONE_A if a_first else PHONE_R
    assert _undo(loser, note["undo"], device)["status"] == "applied"
    assert s.item(kitchen, "Milk")["amount"] == mine


def test_sy44_typed_then_hand_edited(kitchen: TestClient) -> None:
    s = s0(kitchen)
    item = new_id()
    one(kitchen, "add", s.c0, list_id=s.main, item_id=item, food_id=s.foods["Eggs"], amount=6)
    row = item_row(changes(kitchen), item)
    assert (row["source"], row["hand_edited"]) == ("typed", False)
    one(kitchen, "set_amount", s.c0, item_id=item, amount=12)
    assert item_row(changes(kitchen), item)["hand_edited"] is True


# --- Blank amounts (decision 1) ------------------------------------------------------------------


def test_sy40_blank_adds(kitchen: TestClient) -> None:
    s = s0(kitchen)
    extra = new_id()
    send(kitchen, action("create_list", list_id=extra, name="Weekend"))
    tahini = food(kitchen, "Tahini", counted_as="weight")["id"]
    ids = {name: new_id() for name in ("Toor dal", "Onions", "Tahini")}
    foods = {**s.foods, "Tahini": tahini}
    send(
        kitchen,
        *(action("add", list_id=extra, item_id=ids[name], food_id=foods[name]) for name in ids),
    )
    copy = changes(kitchen)
    toor = item_row(copy, ids["Toor dal"])
    assert (toor["amount"], toor["size_id"]) == (500, s.sizes["Toor dal"])
    assert item_row(copy, ids["Onions"])["amount"] == 1
    assert item_row(copy, ids["Tahini"])["amount"] is None
    assert one(kitchen, "tick", item_id=ids["Tahini"])["status"] == "applied"
    with db(kitchen) as session:
        assert session.scalars(select(StockLot).where(StockLot.food_id == tahini)).all() == []


# --- Changed elsewhere while the phone was offline (5.9) -----------------------------------------


def test_sy52_add_of_an_ingredient_merged_meanwhile(kitchen: TestClient) -> None:
    s = s0(kitchen)
    arhar = food(kitchen, "Arhar dal", counted_as="weight")["id"]
    ok(kitchen.post(f"{API}/foods/{arhar}/merge", json={"into_id": s.foods["Toor dal"]}))
    added = one(
        s.wren, "add", s.c0, PHONE_R, list_id=s.main, item_id=new_id(), food_id=arhar, amount=1000
    )
    assert added["status"] == "merged" and added["item_id"] == s.items["Toor dal"]
    (line,) = _lines(kitchen, s, "Toor dal")
    assert line["amount"] == 1500 and line["shop_id"] == s.shops["Supermarket"]
    assert changes(s.wren)["notes"] == []


def test_sy53_add_brings_back_a_removed_ingredient(kitchen: TestClient) -> None:
    s = s0(kitchen)
    ok(kitchen.delete(f"{API}/foods/{s.foods['Eggs']}"))
    item = new_id()
    added = one(
        s.wren,
        "add",
        s.c0,
        PHONE_R,
        list_id=s.main,
        item_id=item,
        food_id=s.foods["Eggs"],
        amount=6,
    )
    assert added["status"] == "applied"
    assert added["message"] == "Eggs is back in Ingredients."
    assert item_row(changes(kitchen), item)["amount"] == 6
    with db(kitchen) as session:
        assert session.get(Food, s.foods["Eggs"]).removed_at is None


def test_sy54_add_of_an_ingredient_deleted_for_good(kitchen: TestClient) -> None:
    s = s0(kitchen)
    ok(kitchen.delete(f"{API}/foods/{s.foods['Eggs']}"))
    with db(kitchen) as session:
        session.execute(
            update(Food)
            .where(Food.id == s.foods["Eggs"])
            .values(removed_at=utcnow() - timedelta(days=8))
        )
        session.commit()
        purge_removed(session, session.get(Household, 1))
    added = one(
        s.wren,
        "add",
        s.c0,
        PHONE_R,
        list_id=s.main,
        item_id=new_id(),
        food_id=s.foods["Eggs"],
        amount=6,
    )
    assert (added["status"], added["reason"]) == ("ignored", "gone")
    assert added["message"] == "Eggs was removed from Ingredients, so it wasn't added."


def test_sy56_amount_in_a_size_removed_meanwhile(kitchen: TestClient) -> None:
    s = s0(kitchen)
    pack = s.sizes["Paneer"]
    ok(kitchen.delete(f"{API}/foods/{s.foods['Paneer']}/sizes/{pack}"))
    done = one(
        s.wren, "set_amount", s.c0, PHONE_R, item_id=s.items["Paneer"], amount=600, size_id=pack
    )
    assert done["status"] == "applied"
    row = s.item(kitchen, "Paneer")
    assert (row["amount"], row["size_id"]) == (600, None)
    assert row["display"] == "600\u00a0g"


def test_sy57_add_with_a_shop_removed_meanwhile(kitchen: TestClient) -> None:
    s = s0(kitchen)
    grocer = s.shops["Indian grocer"]
    with db(kitchen) as session:  # no endpoint removes a shop yet
        session.delete(session.get(Shop, grocer))
        session.commit()
    item = new_id()
    one(
        s.wren,
        "add",
        s.c0,
        PHONE_R,
        list_id=s.main,
        item_id=item,
        food_id=s.foods["Eggs"],
        amount=6,
        shop_id=grocer,
    )
    row = item_row(changes(kitchen), item)
    assert row["shop_id"] == s.shops["Supermarket"] and row["amount"] == 6


def test_sy66_add_via_a_removed_ingredient_when_a_new_one_has_its_name(kitchen: TestClient) -> None:
    s = s0(kitchen)
    old = food(kitchen, "Ghee", counted_as="weight")["id"]
    ok(kitchen.delete(f"{API}/foods/{old}"))
    new = food(kitchen, "Ghee", counted_as="weight")["id"]
    item = new_id()
    added = one(s.wren, "add", s.c0, PHONE_R, list_id=s.main, item_id=item, food_id=old, amount=500)
    assert added["status"] == "applied" and added["food_id"] == new
    assert item_row(changes(kitchen), item)["food_id"] == new
    with db(kitchen) as session:
        assert session.get(Food, old).removed_at is not None


def test_sy66_variant_add_via_a_removed_ingredient(kitchen: TestClient) -> None:
    s = s0(kitchen)
    old = food(kitchen, "Ghee", counted_as="weight")["id"]
    ok(kitchen.delete(f"{API}/foods/{old}"))
    added = one(
        s.wren, "add", s.c0, PHONE_R, list_id=s.main, item_id=new_id(), food_id=old, amount=500
    )
    assert added["status"] == "applied" and added["food_id"] == old
    with db(kitchen) as session:
        assert session.get(Food, old).removed_at is None
    assert _undo(s.wren, added["id"], PHONE_R)["status"] == "applied"
    with db(kitchen) as session:
        assert session.get(Food, old).removed_at is not None


def test_an_undo_of_an_add_keeps_the_brought_back_ingredient_while_it_is_on_a_list(
    kitchen: TestClient,
) -> None:
    """5.9 with 0.2's rule (`cannot_remove`): an ingredient on a list can't be removed.
    Tess put the brought-back Ghee on the list for the Indian grocer too, so the Undo of
    Wren's add takes her line off but leaves Ghee in Ingredients."""
    s = s0(kitchen)
    old = food(kitchen, "Ghee", counted_as="weight")["id"]
    ok(kitchen.delete(f"{API}/foods/{old}"))
    added = one(
        s.wren, "add", s.c0, PHONE_R, list_id=s.main, item_id=new_id(), food_id=old, amount=500
    )
    other = one(
        kitchen,
        "add",
        counter(kitchen),
        PHONE_A,
        list_id=s.main,
        item_id=new_id(),
        food_id=old,
        amount=200,
        shop_id=s.shops["Indian grocer"],
    )
    assert other["status"] == "applied" and other["item_id"] != added["item_id"]
    before = counter(kitchen)
    assert _undo(s.wren, added["id"], PHONE_R)["status"] == "applied"
    assert item_row(changes(kitchen, before), added["item_id"])["deleted"] is True
    assert item_row(changes(kitchen), other["item_id"])["deleted"] is False
    with db(kitchen) as session:
        assert session.get(Food, old).removed_at is None


def test_an_add_via_a_removed_ingredient_never_carries_its_amount_to_one_counted_differently(
    kitchen: TestClient,
) -> None:
    """7.1 (pending cabledrawer): 500 g of the old Ghee means nothing for a Ghee counted in
    items, so the line gets a blank add's amount: 1 (it has no usual size), and the adder
    gets note N9."""
    s = s0(kitchen)
    old = food(kitchen, "Ghee", counted_as="weight")["id"]
    ok(kitchen.delete(f"{API}/foods/{old}"))
    new = food(kitchen, "Ghee", counted_as="count")["id"]
    item = new_id()
    added = one(s.wren, "add", s.c0, PHONE_R, list_id=s.main, item_id=item, food_id=old, amount=500)
    assert added["status"] == "applied" and added["food_id"] == new
    row = item_row(changes(kitchen), item)
    assert (row["food_id"], row["amount"], row["size_id"]) == (new, 1, None)
    # The adder is told, as for a typed new ingredient (N9).
    (note,) = changes(s.wren)["notes"]
    assert note["text"] == (
        "Ghee was already in Ingredients, counted another way, so check the amount."
    )
    assert (note["undo"], note["item_id"]) == (added["id"], item)
    assert changes(kitchen)["notes"] == []


# --- Sign-in runs out while offline (11.5) -------------------------------------------------------


def test_sy34_queue_sent_after_signing_in_again(kitchen: TestClient) -> None:
    s = s0(kitchen)
    queued = [
        action("tick", s.c0, item_id=s.items["Toor dal"]),
        action("set_amount", s.c0, item_id=s.items["Milk"], amount=3000),
        action("delete", s.c0, item_id=s.items["Onions"]),
    ]
    wren = s.wren
    me = int(ok(wren.get(f"{API}/me"))["id"])
    assert wren.delete(f"{API}/session").status_code == 204
    body = {
        "protocol": 1,
        "device_id": PHONE_R,
        "login_id": me,
        "since": s.c0,
        "sent_at": utcnow().isoformat(),
        "actions": queued,
    }
    assert wren.post(f"{API}/shopping/actions", json=body).status_code == 401
    assert counter(kitchen) == s.c0
    ok(wren.post(f"{API}/session", json={"username": "wren", "password": WREN_PASSWORD}))
    answer = send(wren, *queued, device=PHONE_R)
    assert [r["status"] for r in answer["results"]] == ["applied"] * 3


# --- The counter and catching up (5.2, 5.5) ------------------------------------------------------


def test_sy42_changes_since(kitchen: TestClient) -> None:
    s = s0(kitchen)
    for amount in range(1, 11):
        one(kitchen, "set_amount", s.c0, item_id=s.items["Milk"], amount=amount * 100)
    middle = counter(kitchen)
    for amount in range(1, 9):
        one(kitchen, "set_amount", s.c0, item_id=s.items["Onions"], amount=amount)
    one(kitchen, "delete", s.c0, item_id=s.items["Coriander"])
    tick(kitchen, s, "Paneer")
    answer = changes(kitchen, middle)
    assert answer["reset"] is False
    rows = answer["items"] + answer["lists"]
    assert all(row["version"] > middle for row in rows)
    assert {row["id"] for row in answer["items"]} == {
        s.items["Onions"],
        s.items["Coriander"],
        s.items["Paneer"],
    }
    assert item_row(answer, s.items["Coriander"])["deleted"] is True
    with db(kitchen) as session:
        newer = set(
            session.scalars(
                select(ListItem.id).where(
                    ListItem.version > middle, ListItem.merged_into_id.is_(None)
                )
            )
        )
    assert newer == {row["id"] for row in answer["items"]}
    full = changes(kitchen)
    assert full["reset"] is True
    assert all(row.get("deleted") is False for row in full["items"])
    with db(kitchen) as session:
        session.get(Household, 1).list_purged_seq = middle + 1
        session.commit()
    assert changes(kitchen, middle)["reset"] is True
    assert changes(kitchen, middle + 1)["reset"] is False


def _client_like(client: TestClient) -> TestClient:
    other = TestClient(client.app, base_url="https://testserver")
    other.cookies.update(client.cookies)
    return other


def test_sy43_two_batches_at_once(kitchen: TestClient) -> None:
    s = s0(kitchen)
    first = [
        action("set_amount", s.c0, item_id=s.items["Milk"], amount=amount * 100)
        for amount in range(1, 16)
    ]
    second = [
        first[0],  # a repeat
        action("set_amount", s.c0, item_id=s.items["Onions"], amount=1, id=first[1]["id"]),
        *(action("set_amount", s.c0, item_id=s.items["Onions"], amount=n) for n in range(2, 16)),
    ]
    cursors: list[int] = []
    stop = threading.Event()

    def reader() -> None:
        poller = _client_like(kitchen)
        since = s.c0
        while not stop.is_set():
            answer = changes(poller, since)
            cursors.append(answer["cursor"])
            since = answer["cursor"]

    answers: dict[str, Any] = {}
    threads = [
        threading.Thread(target=reader),
        threading.Thread(target=lambda: answers.update(a=send(_client_like(kitchen), *first))),
        threading.Thread(
            target=lambda: answers.update(b=send(_client_like(s.wren), *second, device=PHONE_R))
        ),
    ]
    for thread in threads:
        thread.start()
    for thread in threads[1:]:
        thread.join()
    stop.set()
    threads[0].join()
    with db(kitchen) as session:
        seqs = sorted(session.scalars(select(SyncAction.seq).where(SyncAction.seq > s.c0)).all())
    assert seqs == list(range(s.c0 + 1, s.c0 + 1 + len(seqs)))
    assert counter(kitchen) == seqs[-1]
    taken = [
        r["seq"]
        for answer in answers.values()
        for r in answer["results"]
        if not r["repeat"] and r["status"] != "refused"
    ]
    assert sorted(taken) == seqs
    assert cursors == sorted(cursors)
    reasons = [(r["status"], r["reason"]) for r in answers["b"]["results"][:2]]
    assert reasons[1] == ("refused", "key_reused") or answers["a"]["results"][1]["reason"] == (
        "key_reused"
    )


def test_sy48_a_resend_while_the_first_is_still_running(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from mealwright import ticks

    s = s0(kitchen)
    batch = [
        action("tick", s.c0, item_id=s.items["Toor dal"]),
        action("tick", s.c0, item_id=s.items["Paneer"]),
        action("add", s.c0, list_id=s.main, item_id=new_id(), food_id=s.foods["Eggs"], amount=6),
    ]
    started, release = threading.Event(), threading.Event()
    real = ticks.HANDLERS["tick"]

    def held(act: Any) -> None:  # the test hook: holds the first batch's work open
        if not started.is_set():
            started.set()
            release.wait(30)
        real(act)

    monkeypatch.setitem(ticks.HANDLERS, "tick", held)
    answers: dict[str, Any] = {}
    one_thread = threading.Thread(
        target=lambda: answers.update(a=send(_client_like(kitchen), *batch))
    )
    one_thread.start()
    assert started.wait(30)
    two_thread = threading.Thread(
        target=lambda: answers.update(b=send(_client_like(kitchen), *batch))
    )
    two_thread.start()
    two_thread.join(1)  # the resend waits for the household's lock
    assert two_thread.is_alive()
    release.set()
    one_thread.join()
    two_thread.join()
    assert [r["repeat"] for r in answers["b"]["results"]] == [True] * 3
    assert [r["seq"] for r in answers["b"]["results"]] == [
        r["seq"] for r in answers["a"]["results"]
    ]
    assert counter(kitchen) == s.c0 + 3
    assert s.total("Toor dal") == 500 and s.total("Paneer") == 400


# --- Another household (5.9) ---------------------------------------------------------------------


def test_sy41_another_households_ids(kitchen: TestClient) -> None:
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
    theirs = food(neighbour, "Bread", counted_as="count")["id"]
    their_main = main_id(neighbour)
    my_main = s.main
    mine = new_id()
    send(neighbour, action("add", list_id=their_main, item_id=mine, food_id=theirs, amount=1))
    before = changes(kitchen)
    item = s.items["Paneer"]
    toor = s.foods["Toor dal"]
    tries = [
        action("rename_list", list_id=my_main, name="Hacked"),
        action("set_amount", item_id=item, amount=5),
        action("delete", item_id=item),
        action("tick", item_id=item),
        action("untick", item_id=item, tick_ids=[]),
        action("put_away", item_id=item, place_id=s.places["Fridge"], tick_ids=[]),
        action("clear_ticked", list_id=my_main, item_ids=[item]),
        action("dismiss_note", note_id=1),
        action("answer_double_tick", question_id=1, answer="one"),
        action("add", list_id=my_main, item_id=new_id(), food_id=toor),
    ]
    results = send(neighbour, *tries, device=PHONE_R)["results"]
    assert all(r["status"] == "ignored" and r["reason"] == "gone" for r in results), results
    taken = send(
        neighbour,
        action("add", list_id=their_main, item_id=s.items["Milk"], food_id=theirs),
        device=PHONE_R,
    )["results"][0]
    assert (taken["status"], taken["reason"]) == ("refused", "id_taken")
    shop_and_size = send(
        neighbour,
        action(
            "add",
            list_id=their_main,
            item_id=new_id(),
            food_id=theirs,
            amount=2,
            shop_id=s.shops["Supermarket"],
            size_id=s.sizes["Toor dal"],
        ),
        action("put_away", item_id=mine, place_id=s.places["Freezer"], tick_ids=[]),
        device=PHONE_R,
    )["results"]
    assert shop_and_size[0]["status"] in ("applied", "merged")
    after = changes(kitchen)
    assert after["items"] == before["items"] and after["lists"] == before["lists"]
    assert s.total("Paneer") == 0
    for row in changes(neighbour)["items"]:
        assert row.get("shop_id") != s.shops["Supermarket"]
        assert row.get("size_id") != s.sizes["Toor dal"]
        assert row.get("put_away_place_id") != s.places["Freezer"]


def test_a_note_never_offers_to_undo_an_undo(kitchen: TestClient) -> None:
    """N4 after the item went by an Undo of its `add`: Undo of an Undo is `cannot_undo`
    (9), so the note has no Undo, only its close button."""
    s = s0(kitchen)
    item = new_id()
    added = one(kitchen, "add", list_id=s.main, item_id=item, food_id=s.foods["Eggs"], amount=6)
    seen = counter(kitchen)
    one(kitchen, "undo", seen, undoes=added["id"])
    late = one(s.wren, "set_amount", seen, PHONE_R, item_id=item, amount=12)
    assert (late["status"], late["reason"]) == ("ignored", "deleted")
    (note,) = changes(s.wren)["notes"]
    assert note["text"] == "Tess had removed Eggs, so your change wasn't kept."
    assert note["undo"] is None


# --- Undo of server-made rows from a list (9) ----------------------------------------------------


def _last_row(kitchen: TestClient, kind: str) -> str:
    with db(kitchen) as session:
        return str(
            session.scalars(
                select(SyncAction.id).where(SyncAction.kind == kind).order_by(SyncAction.seq.desc())
            ).first()
        )


def test_an_ingredient_edit_can_be_undone_from_a_list(kitchen: TestClient) -> None:
    s = s0(kitchen)
    with db(kitchen) as session:
        before = session.get(Food, s.foods["Onions"]).aisle
    assert before != "dry_goods"
    ok(kitchen.patch(f"{API}/foods/{s.foods['Onions']}", json={"aisle": "dry_goods"}))
    done = one(s.wren, "undo", 0, PHONE_R, undoes=_last_row(kitchen, "food_edit"))
    assert done["status"] == "applied", done
    with db(kitchen) as session:
        assert session.get(Food, s.foods["Onions"]).aisle == before


def test_a_followed_shop_can_be_undone_from_a_list(kitchen: TestClient) -> None:
    s = s0(kitchen)
    grocer = s.shops["Indian grocer"]
    ok(kitchen.patch(f"{API}/foods/{s.foods['Toor dal']}", json={"shop_id": grocer}))
    assert _lines(kitchen, s, "Toor dal")[0]["shop_id"] == grocer
    done = one(s.wren, "undo", 0, PHONE_R, undoes=_last_row(kitchen, "follow_shop"))
    assert done["status"] == "applied", done
    assert _lines(kitchen, s, "Toor dal")[0]["shop_id"] == s.shops["Supermarket"]


def test_a_merge_can_be_undone_from_a_list(kitchen: TestClient) -> None:
    s = s0(kitchen)
    arhar = food(kitchen, "Arhar dal", counted_as="weight")["id"]
    ok(kitchen.post(f"{API}/foods/{arhar}/merge", json={"into_id": s.foods["Toor dal"]}))
    done = one(s.wren, "undo", 0, PHONE_R, undoes=_last_row(kitchen, "merge_foods"))
    assert done["status"] == "applied", done
    with db(kitchen) as session:
        assert session.get(Food, arhar).merged_into_id is None


@pytest.mark.parametrize("kind", ["untick_by_undo", "place_by_undo"])
def test_a_server_made_undo_cant_be_undone(kitchen: TestClient, kind: str) -> None:
    s = s0(kitchen)
    t = tick(kitchen, s, "Coriander")
    undone = t["change"]["id"]
    if kind == "place_by_undo":
        item, freezer = s.items["Coriander"], s.places["Freezer"]
        put = one(kitchen, "put_away", s.c0, item_id=item, place_id=freezer, tick_ids=[t["id"]])
        undone = put["change"]["id"]
    ok(kitchen.post(f"{API}/changes/{undone}/undo"))
    done = one(s.wren, "undo", 0, PHONE_R, undoes=_last_row(kitchen, kind))
    assert done["status"] == "ignored" and done["reason"] == "cannot_undo"
