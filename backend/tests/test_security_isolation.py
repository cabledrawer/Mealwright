"""Household 2 can never reach household 1's shopping lists, ticks, notes, questions,
changes or live updates (security audit, 0.4; spec section 6; ASVS 4.2.1).

test_households.py tries household 1's IDs in every plain endpoint. This file does the
same for the sync batch (every action kind and every ID field in it), the changes feed,
the live-update stream and Undo, plus the request-body IDs that file doesn't try. The
ID fields are listed from the OpenAPI document, so a new ID field with no case here fails
`test_every_id_field_in_a_request_body_has_a_case`.

Household 1's rows must be exactly the same afterwards, and nothing household 2 gets
back may name anything of household 1.
"""

import asyncio
import json
from collections.abc import Iterator
from dataclasses import dataclass
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import and_, func, select
from sync_kit import (
    PHONE_A,
    S0,
    action,
    changes,
    db,
    main_id,
    new_id,
    ok,
    one,
    s0,
    send,
    tick,
)
from test_event_streams import Stream
from test_households import NEIGHBOUR, snapshot

from mealwright.auth import COOKIE, hash_password
from mealwright.db import Base
from mealwright.household import add_default_places
from mealwright.models import Household, ListItem, Login, SyncAction

API = "/api/v1"
PHONE_N = "3e9f6c3b-af4d-4cab-8a3e-5cad6f4b8a75"  # next door's phone

# Every name household 1 uses. None may appear in anything household 2 is sent.
SECRETS = (
    "Toor dal",
    "Paneer",
    "Milk",
    "Coriander",
    "Onions",
    "Salt",
    "Eggs",
    "Supermarket",
    "Indian grocer",
    "Tess",
    "Wren",
    "Party",
    "had removed",
    "packet",
)


@dataclass
class Mine:
    """Household 1 after some shopping, and the IDs to attack it with."""

    s: S0
    extra_list: str
    question_id: int
    note_id: int
    tick_id: str  # a standing tick (purchase) of Milk
    action_ids: list[str]
    login_ids: list[int]


@dataclass
class Theirs:
    client: TestClient
    main: str
    food_id: int
    item_id: str  # an item on their own list
    tick_id: str  # their own standing tick of it
    loose_id: str  # another item of theirs, never ticked (so a move gets as far as its IDs)


@pytest.fixture
def mine(kitchen: TestClient) -> Mine:
    s = s0(kitchen)
    # A "both ticked" question: Tess and Wren both bought the Toor dal.
    tick(kitchen, s, "Toor dal")
    tick(s.wren, s, "Toor dal", "2d8e5b2a-9e3c-4b9a-9f2d-4b9c5e3a7f64")
    (question,) = [q for q in changes(kitchen)["questions"] if q["open"]]
    # A quiet note: Wren removed the Paneer while Tess ticked it.
    one(s.wren, "delete", s.c0, "2d8e5b2a-9e3c-4b9a-9f2d-4b9c5e3a7f64", item_id=s.items["Paneer"])
    tick(kitchen, s, "Paneer")
    (note,) = changes(kitchen)["notes"]
    milk = tick(kitchen, s, "Milk")
    extra = new_id()
    send(kitchen, action("create_list", list_id=extra, name="Party"))
    with db(kitchen) as session:
        ids = list(session.scalars(select(SyncAction.id).where(SyncAction.household_id == 1)))
        logins = list(session.scalars(select(Login.id).where(Login.household_id == 1)))
    return Mine(s, extra, int(question["id"]), int(note["id"]), milk["id"], ids, logins)


@pytest.fixture
def theirs(kitchen: TestClient, mine: Mine) -> Iterator[Theirs]:
    """Household 2 (made after household 1's data), signed in, with a ticked item."""
    with db(kitchen) as session:
        session.add(Household(id=2, name="Next door"))
        session.flush()
        add_default_places(session, 2)
        session.add(
            Login(
                household_id=2,
                username=NEIGHBOUR["username"],
                name="Neighbour",
                password_hash=hash_password(NEIGHBOUR["password"]),
                role="admin",
            )
        )
        session.commit()
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        ok(other.post(f"{API}/session", json=NEIGHBOUR))
        ghee = ok(other.post(f"{API}/foods", json={"name": "Ghee"}), 201)["food"]["id"]
        main = main_id(other)
        item = new_id()
        send(other, action("add", list_id=main, item_id=item, food_id=ghee), device=PHONE_N)
        ticked = one(other, "tick", 0, PHONE_N, item_id=item)
        assert ticked["status"] == "applied"
        dal = ok(other.post(f"{API}/foods", json={"name": "Masoor"}), 201)["food"]["id"]
        loose = new_id()
        send(other, action("add", list_id=main, item_id=loose, food_id=dal), device=PHONE_N)
        yield Theirs(other, main, ghee, item, ticked["id"], loose)


def links_across_households(kitchen: TestClient) -> list[str]:
    """Every row that points at a row of another household (by foreign key)."""
    found = []
    with db(kitchen) as session:
        for table in Base.metadata.sorted_tables:
            if "household_id" not in table.c:
                continue
            for constraint in table.foreign_key_constraints:
                parent = constraint.referred_table
                if parent.name == "household" or "household_id" not in parent.c:
                    continue
                child, other = table.alias("child"), parent.alias("parent")
                joined = and_(
                    *(
                        child.c[element.parent.name] == other.c[element.column.name]
                        for element in constraint.elements
                    )
                )
                rows = session.execute(
                    select(func.count())
                    .select_from(child.join(other, joined))
                    .where(child.c.household_id != other.c.household_id)
                ).scalar_one()
                if rows:
                    columns = ", ".join(e.parent.name for e in constraint.elements)
                    found.append(f"{table.name}({columns}) -> {parent.name}: {rows}")
    return found


def leaks(answer: Any) -> list[str]:
    text = json.dumps(answer)
    return [secret for secret in SECRETS if secret in text]


def attacks(mine: Mine, theirs: Theirs) -> list[dict[str, Any]]:
    """Each sync action kind, with household 1's IDs in each ID field it has."""
    s = mine.s
    item, own_item, own_list = s.items["Onions"], theirs.item_id, theirs.main
    loose = theirs.loose_id
    food, size, shop = s.foods["Toor dal"], s.sizes["Toor dal"], s.shops["Supermarket"]
    place = s.places["Fridge"]
    return [
        action("create_list", list_id=s.main, name="Mine now"),
        action("create_list", list_id=mine.extra_list, name="Mine now"),
        action("rename_list", list_id=s.main, name="Mine now"),
        action("remove_list", list_id=mine.extra_list),
        action("add", list_id=s.main, item_id=new_id(), food_id=theirs.food_id),
        action("add", list_id=own_list, item_id=item, food_id=theirs.food_id),
        action("add", list_id=own_list, item_id=new_id(), food_id=food),
        action("add", list_id=own_list, item_id=new_id(), food_id=theirs.food_id, size_id=size),
        action("add", list_id=own_list, item_id=new_id(), food_id=theirs.food_id, shop_id=shop),
        action("set_amount", item_id=item, amount=3),
        action("set_amount", item_id=own_item, amount=500, size_id=size),
        action("delete", item_id=item),
        action("move", item_id=item, list_id=own_list, shop_id=None),
        action("move", item_id=loose, list_id=s.main, shop_id=None),
        action("move", item_id=loose, list_id=mine.extra_list, shop_id=None),
        action("move", item_id=loose, list_id=own_list, shop_id=shop),
        action("tick", item_id=item),
        action("untick", item_id=item, tick_ids=[]),
        action("untick", item_id=own_item, tick_ids=[mine.tick_id]),
        action("put_away", item_id=s.items["Milk"], place_id=place, tick_ids=[mine.tick_id]),
        action("put_away", item_id=own_item, place_id=place, tick_ids=[theirs.tick_id]),
        action("put_away", item_id=own_item, place_id=place, tick_ids=[mine.tick_id]),
        action("different_pack", item_id=s.items["Milk"], tick_id=mine.tick_id, count=1, pack=500),
        action("different_pack", item_id=own_item, tick_id=mine.tick_id, count=1, pack=500),
        action(
            "different_pack",
            item_id=own_item,
            tick_id=theirs.tick_id,
            count=1,
            pack=500,
            size_id=size,
        ),
        action("clear_ticked", list_id=s.main, item_ids=[]),
        action("clear_ticked", list_id=own_list, item_ids=[s.items["Milk"], item]),
        action("answer_double_tick", question_id=mine.question_id, answer="one"),
        action("dismiss_note", note_id=mine.note_id),
        *(action("undo", undoes=key) for key in mine.action_ids),
    ]


def test_the_sync_batch_never_reaches_the_other_household(mine: Mine, theirs: Theirs) -> None:
    kitchen = mine.s.kitchen
    before = snapshot(kitchen)
    tried = attacks(mine, theirs)
    for start in range(0, len(tried), 20):
        answer = send(theirs.client, *tried[start : start + 20], device=PHONE_N)
        assert leaks(answer) == [], answer
        for sent, result in zip(tried[start : start + 20], answer["results"], strict=True):
            # An ID of theirs in an optional field (a size, a shop) is just dropped, and the
            # rest of the change applies to household 2's own item.
            # A move is not given this allowance: a forged list or shop is "gone".
            dropped = sent["kind"] != "move" and ("size_id" in sent or "shop_id" in sent)
            allowed = {"refused", "ignored"} | ({"applied", "merged"} if dropped else set())
            assert result["status"] in allowed, (sent, result)
            assert result["repeat"] is False
    assert snapshot(kitchen) == before
    assert links_across_households(kitchen) == []


def test_a_link_across_households_would_be_found(mine: Mine, theirs: Theirs) -> None:
    """The check above can see a bad link (here made by hand, never by the app)."""
    kitchen = mine.s.kitchen
    assert links_across_households(kitchen) == []
    with db(kitchen) as session:
        row = session.get(ListItem, theirs.item_id)
        row.size_id = mine.s.sizes["Toor dal"]
        session.commit()
    assert links_across_households(kitchen) == ["list_item(size_id) -> food_size: 1"]


def test_the_same_action_ids_in_both_households(mine: Mine, theirs: Theirs) -> None:
    """Household 1's action IDs are new actions next door, never a repeat of household
    1's answer (the sync log is per household)."""
    kitchen = mine.s.kitchen
    before = snapshot(kitchen)
    for n, key in enumerate(mine.action_ids):
        name = f"Our list {n}"
        result = one(
            theirs.client, "rename_list", 0, PHONE_N, id=key, list_id=theirs.main, name=name
        )
        assert result["repeat"] is False and result["status"] == "applied", result
        assert leaks(result) == []
    assert snapshot(kitchen) == before


def test_another_households_login_cannot_send(mine: Mine, theirs: Theirs) -> None:
    kitchen = mine.s.kitchen
    before = snapshot(kitchen)
    for login in mine.login_ids:
        answer = send(
            theirs.client,
            action("tick", item_id=mine.s.items["Onions"]),
            device=PHONE_N,
            login=login,
            status=409,
        )
        assert answer["code"] == "other_login"
        assert leaks(answer) == []
    assert snapshot(kitchen) == before


def test_the_changes_feed_shows_only_their_own(mine: Mine, theirs: Theirs) -> None:
    for device in (PHONE_A, PHONE_N, None):
        feed = changes(theirs.client, 0, device)
        assert leaks(feed) == [], device
        assert [row["id"] for row in feed["lists"]] == [theirs.main]
        assert {row["id"] for row in feed["items"]} == {theirs.item_id, theirs.loose_id}
        assert feed["notes"] == [] and feed["questions"] == []
        assert feed["cursor"] <= changes(theirs.client)["cursor"]
    # Household 1's (higher) cursor tells them nothing either.
    high = changes(mine.s.kitchen)["cursor"] + 100
    assert leaks(changes(theirs.client, high)) == []


def test_the_plain_shopping_endpoints_take_none_of_their_ids(mine: Mine, theirs: Theirs) -> None:
    s = mine.s
    kitchen, other = s.kitchen, theirs.client
    before = snapshot(kitchen)
    size = s.sizes["Toor dal"]
    new_item = {"id": s.items["Onions"], "food_id": theirs.food_id}
    taken = other.post(f"{API}/shopping/lists/{theirs.main}/items", json=new_item)
    assert taken.status_code == 409 and taken.json()["code"] == "id_taken", taken.text
    assert leaks(taken.json()) == []
    for body in (
        {"amount": {"amount": 1, "size_id": size}},
        {"running_low_at": {"amount": 1, "size_id": size}},
    ):
        response = other.patch(f"{API}/shopping/items/{theirs.item_id}", json=body)
        assert response.status_code in {404, 422}, (body, response.text)
        assert leaks(response.json()) == []
    cleared = other.post(
        f"{API}/shopping/lists/{theirs.main}/clear-ticked",
        json={"item_ids": [s.items["Milk"], s.items["Toor dal"]]},
    )
    assert cleared.status_code in {200, 404}, cleared.text
    assert leaks(cleared.json()) == []
    assert snapshot(kitchen) == before


def test_the_live_stream_carries_nothing_of_the_other_household(mine: Mine, theirs: Theirs) -> None:
    kitchen, s = mine.s.kitchen, mine.s

    async def scenario() -> tuple[str, str]:
        ours = Stream(kitchen.app, kitchen.cookies[COOKIE])
        next_door = Stream(kitchen.app, theirs.client.cookies[COOKIE])
        try:
            for stream in (ours, next_door):
                stream.open()
                await stream.hello()
            await asyncio.to_thread(tick, kitchen, s, "Coriander")
            async with asyncio.timeout(3):
                while "event: pantry" not in ours.body:
                    await asyncio.sleep(0.02)
            await asyncio.sleep(0.2)
            return ours.body, next_door.body
        finally:
            await ours.close()
            await next_door.close()

    heard, next_door = asyncio.run(scenario())
    assert "event: shopping" in heard and "event: pantry" in heard
    assert "event: shopping" not in next_door and "event: pantry" not in next_door
    assert leaks(next_door) == []


# --- Every ID field in a request body has a case ---------------------------------------------

# (schema, field) → where it is tried with household 1's ID.
BODY_ID_CASES: dict[tuple[str, str], str] = {
    # Plain endpoints: test_households.py, test_household_ids_in_the_body_are_404.
    ("NewFood", "place_id"): "test_households",
    ("NewFood", "shop_id"): "test_households",
    ("FoodPatch", "place_id"): "test_households",
    ("FoodPatch", "shop_id"): "test_households",
    ("AmountIn", "size_id"): "test_households",
    ("Answer", "food_id"): "test_households",
    ("NewStandIn", "food_id"): "test_households",
    ("NotSame", "food_id"): "test_households",
    ("Merge", "into_id"): "test_households",
    ("Split", "other_name_id"): "test_households",
    ("AddStock", "food_id"): "test_households",
    ("AddStock", "place_id"): "test_households",
    ("Move", "place_id"): "test_households",
    ("FoodAmount", "place_id"): "test_households",
    ("FoodLeft", "place_id"): "test_households",
    ("NewList", "id"): "test_households",
    ("NewItem", "food_id"): "test_households",
    ("NewItem", "shop_id"): "test_households",
    # Recipes: test_recipes_isolation.py, test_household_2_cannot_link_a_line_to_household_1.
    ("RecipeLineIn", "id"): "test_recipes_isolation",
    ("RecipeLineIn", "food_id"): "test_recipes_isolation",
    ("RecipeLineIn", "recipe_id"): "test_recipes_isolation",
    ("RecipeLineIn", "size_id"): "test_recipes_isolation",
    # Photos: test_recipes_isolation.py, test_household_2_cannot_use_household_1s_photos.
    ("RecipeIn", "photo_id"): "test_recipes_isolation",
    ("RecipeUpdate", "photo_id"): "test_recipes_isolation",
    # Recipe import: test_recipe_import.py, test_another_households_ingredients_places_and_photos...
    ("ImportLinkIn", "food_id"): "test_recipe_import",
    ("ImportLinkIn", "place_id"): "test_recipe_import",
    ("ImportLineIn", "size_id"): "test_recipe_import",
    ("ImportSave", "photo_id"): "test_recipe_import",
    # Drafts: test_drafts.py, test_another_household_can_not_..._a_draft and
    # test_ids_inside_a_drafts_review_and_choices_give_nothing_of_another_household.
    ("ImportSave", "draft_id"): "test_drafts",
    ("DraftChoice", "place_id"): "test_drafts",
    ("Ref", "id"): "test_drafts",
    ("SizeRef", "id"): "test_drafts",
    ("PhotoOut", "id"): "test_drafts",
    # Plain shopping endpoints: here.
    ("NewItem", "id"): "test_the_plain_shopping_endpoints_take_none_of_their_ids",
    ("AmountOrNone", "size_id"): "test_the_plain_shopping_endpoints_take_none_of_their_ids",
    ("ClearTicked", "item_ids"): "test_the_plain_shopping_endpoints_take_none_of_their_ids",
    # The sync batch: here.
    ("Envelope", "device_id"): "test_the_changes_feed_shows_only_their_own",
    ("Envelope", "login_id"): "test_another_households_login_cannot_send",
    ("*", "id"): "test_the_same_action_ids_in_both_households",
    ("*", "device_id"): "each action's device is its household's own",
    ("Add", "list_id"): "attacks",
    ("Add", "item_id"): "attacks",
    ("Add", "food_id"): "attacks",
    ("Add", "size_id"): "attacks",
    ("Add", "shop_id"): "attacks",
    ("CreateList", "list_id"): "attacks",
    ("RenameListAction", "list_id"): "attacks",
    ("RemoveList", "list_id"): "attacks",
    ("MoveLine", "item_id"): "attacks",
    ("MoveLine", "list_id"): "attacks",
    ("MoveLine", "shop_id"): "attacks",
    ("SetAmount", "item_id"): "attacks",
    ("SetAmount", "size_id"): "attacks",
    ("Delete", "item_id"): "attacks",
    ("Tick", "item_id"): "attacks",
    ("Untick", "item_id"): "attacks",
    ("Untick", "tick_ids"): "attacks",
    ("PutAway", "item_id"): "attacks",
    ("PutAway", "place_id"): "attacks",
    ("PutAway", "tick_ids"): "attacks",
    ("DifferentPack", "item_id"): "attacks",
    ("DifferentPack", "tick_id"): "attacks",
    ("DifferentPack", "size_id"): "attacks",
    ("ClearTickedAction", "list_id"): "attacks",
    ("ClearTickedAction", "item_ids"): "attacks",
    ("AnswerDoubleTick", "question_id"): "attacks",
    ("DismissNote", "note_id"): "attacks",
    ("UndoAction", "undoes"): "attacks",
}


def _is_id(name: str) -> bool:
    return name in {"id", "undoes"} or name.endswith(("_id", "_ids"))


def body_id_fields(client: TestClient) -> set[tuple[str, str]]:
    """Every ID field reachable from a request body, as (schema, field). The `id` and
    `device_id` every sync action has are listed once, as ("*", field)."""
    spec = client.app.openapi()  # type: ignore[attr-defined]
    schemas = spec["components"]["schemas"]
    found: set[tuple[str, str]] = set()
    seen: set[str] = set()

    def refs(node: Any) -> Iterator[str]:
        if isinstance(node, dict):
            if "$ref" in node:
                yield node["$ref"].rsplit("/", 1)[-1]
            for value in node.values():
                yield from refs(value)
        elif isinstance(node, list):
            for value in node:
                yield from refs(value)

    def visit(name: str) -> None:
        if name in seen:
            return
        seen.add(name)
        properties = schemas[name].get("properties", {})
        is_action = {"kind", "made_at", "seen"} <= set(properties)
        for field in properties:
            if _is_id(field):
                shared = is_action and field in {"id", "device_id"}
                found.add(("*" if shared else name, field))
        for child in refs(schemas[name]):
            visit(child)

    for methods in spec["paths"].values():
        for operation in methods.values():
            for name in refs(operation.get("requestBody", {})):
                visit(name)
    return found


def test_every_id_field_in_a_request_body_has_a_case(kitchen: TestClient) -> None:
    assert body_id_fields(kitchen) == set(BODY_ID_CASES)
