"""Removing a place re-points its purchases, and Undo puts them back: only this household's own
(whole-0.8 review S1). A purchase's id is the phone's own action id, unique only inside a
household, so another household can hold a purchase with the same id."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sync_kit import action, main_id, new_id, ok, send
from test_recipes import food
from test_security_isolation import links_across_households

from mealwright.history import tidy_lists
from mealwright.models import Change, Household, ListItem, ListTick, utcnow

API = "/api/v1"
PHONE_1 = "11111111-1111-4111-8111-111111111111"
PHONE_2 = "22222222-2222-4222-8222-222222222222"


def places(client: TestClient) -> dict[str, int]:
    return {p["name"]: p["id"] for p in ok(client.get(f"{API}/places"))}


def found(client: TestClient, device: str, name: str, tick_id: str, place_id: int) -> None:
    made = food(client, name)
    item = new_id()
    send(client, action("add", list_id=main_id(client), item_id=item, food_id=made["id"]), device)
    answer = send(
        client,
        action("found_at_home", id=tick_id, item_id=item, amount=100, place_id=place_id),
        device,
    )
    assert answer["results"][0]["status"] == "applied", answer


def tick_place(client: TestClient, household: int, tick_id: str) -> int | None:
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        tick = db.get(ListTick, (household, tick_id))
        assert tick is not None
        return tick.place_id


def test_removing_a_place_and_its_undo_leave_another_households_purchase_alone(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    same_id = new_id()  # the same action id in both households (allowed: the log is per household)
    found(neighbour, PHONE_2, "Ghee", same_id, places(neighbour)["Cupboard"])
    theirs = tick_place(neighbour, 2, same_id)
    shelf = ok(kitchen.post(f"{API}/places", json={"name": "Shelf", "kind": "cupboard"}), 201)["id"]
    found(kitchen, PHONE_1, "Toor dal", same_id, shelf)
    removed = ok(
        kitchen.delete(f"{API}/places/{shelf}", params={"move_to": places(kitchen)["Cupboard"]})
    )
    assert tick_place(neighbour, 2, same_id) == theirs
    assert tick_place(kitchen, 1, same_id) == places(kitchen)["Cupboard"]  # this one did move
    ok(kitchen.post(f"{API}/changes/{removed['change']['id']}/undo"))
    assert tick_place(neighbour, 2, same_id) == theirs
    assert tick_place(kitchen, 1, same_id) == shelf  # and came back
    assert links_across_households(kitchen) == []


def test_the_lists_tidy_up_leaves_another_households_purchase_changes_linked(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    """Same sweep (S1): letting go of a purchase's changes before its old shopping line is deleted
    goes by the purchase's id, which another household can hold too."""
    same_id = new_id()
    found(neighbour, PHONE_2, "Ghee", same_id, places(neighbour)["Cupboard"])
    found(kitchen, PHONE_1, "Toor dal", same_id, places(kitchen)["Cupboard"])

    def linked(client: TestClient, household: int) -> int:
        with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            return len(
                db.scalars(
                    select(Change.id).where(
                        Change.household_id == household, Change.tick_id == same_id
                    )
                ).all()
            )

    assert linked(neighbour, 2) >= 1
    mine = linked(kitchen, 1)
    assert mine >= 1
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(update(ListItem).where(ListItem.household_id == 1).values(deleted_at=utcnow()))
        db.commit()
        tidy_lists(db, db.get(Household, 1), utcnow() + timedelta(days=500))
    assert linked(kitchen, 1) == 0  # its own purchase's changes let go
    assert linked(neighbour, 2) >= 1  # theirs did not
