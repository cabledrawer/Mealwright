"""K2 round 3: an Undo sent through /sync does what the Undo in Recent changes does. Both go
through `undo_checked`/`undo_run`, so "Cooked it" can be cooked again after either, and a
removal that no longer stands cannot be undone by either."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sync_kit import PHONE_A, new_id, ok, one, s0
from test_cooking import amounts, cook, far_curry
from test_plan import db_of

from mealwright.models import Change, CookedRecord, SyncAction, utcnow

API = "/api/v1"


def test_a_sync_undo_of_cooked_it_lets_it_be_cooked_again(kitchen: TestClient) -> None:
    dal, item = far_curry(kitchen, 60)
    done = ok(cook(kitchen, item), 201)
    with db_of(kitchen) as db:
        row = db.scalars(
            select(SyncAction).where(SyncAction.change_id == done["change"]["id"])
        ).one()
        action_id = row.id
    assert one(kitchen, "undo", 0, PHONE_A, undoes=action_id)["status"] == "applied"
    with db_of(kitchen) as db:
        assert db.scalars(select(CookedRecord)).all() == []  # the record went with the Undo
    assert amounts(kitchen, dal["id"]) == [60_000]
    again = cook(kitchen, item)
    assert again.status_code == 201, again.text  # not 409 already_cooked
    assert amounts(kitchen, dal["id"]) == [0]


def test_a_sync_undo_of_a_removal_that_no_longer_stands_is_refused(kitchen: TestClient) -> None:
    """The same rule as `can_undo` for Recent changes: Paneer is back, so its removal stays."""
    s = s0(kitchen)
    one(s.wren, "delete", s.c0, "0b6c3f0e-7c1a-4f7e-9d0b-2f7a3c1e5d43", item_id=s.items["Paneer"])
    ok(s.wren.delete(f"{API}/foods/{s.foods['Paneer']}"))
    one(
        s.wren,
        "add",
        s.c0,
        "0b6c3f0e-7c1a-4f7e-9d0b-2f7a3c1e5d43",
        list_id=s.main,
        item_id=new_id(),
        new_food={"name": "paneer", "counted_as": "weight"},
    )  # Paneer is back in Ingredients
    with db_of(kitchen) as db:
        removed = db.scalars(select(Change).where(Change.kind == "food_removed")).one()
        row = db.scalars(select(SyncAction).where(SyncAction.change_id == removed.id)).one()
        action_id = row.id
    result = one(kitchen, "undo", 0, PHONE_A, undoes=action_id)
    assert result["status"] == "ignored" and result["reason"] == "cannot_undo"
    http = kitchen.post(f"{API}/changes/{removed.id}/undo")
    assert http.status_code == 409 and http.json()["code"] == "cannot_undo"


def test_a_too_old_removal_that_no_longer_stands_says_too_old_over_http(
    kitchen: TestClient,
) -> None:
    """Undo in Recent changes asks the window before whether the removal stands, as it always
    did."""
    s = s0(kitchen)
    phone = "0b6c3f0e-7c1a-4f7e-9d0b-2f7a3c1e5d43"
    one(s.wren, "delete", s.c0, phone, item_id=s.items["Paneer"])
    ok(s.wren.delete(f"{API}/foods/{s.foods['Paneer']}"))
    one(
        s.wren,
        "add",
        s.c0,
        phone,
        list_id=s.main,
        item_id=new_id(),
        new_food={"name": "paneer", "counted_as": "weight"},
    )
    with db_of(kitchen) as db:
        removed = db.scalars(select(Change).where(Change.kind == "food_removed")).one()
        db.execute(
            update(Change).where(Change.id == removed.id).values(at=utcnow() - timedelta(days=8))
        )
        db.commit()
    response = kitchen.post(f"{API}/changes/{removed.id}/undo")
    assert response.status_code == 410 and response.json()["code"] == "too_old"
