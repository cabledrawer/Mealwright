"""Changes saved by 0.9.5-beta.2 still show and still undo after D2-D4's renames (D3 fix).

D3 renamed API fields and routes but no stored change kind and no field inside a change's stored
`undo_data`; old stored values (a planned ingredient's `meal_item.kind = "ingredient"`, the backup
frequency `twice-daily`) are translated at the API's edge. These tests write change rows exactly
as beta.2's code wrote them, straight into the database, then read them back through Recent
changes and undo them through the API.
"""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import delete, select
from sync_kit import ok
from test_api_names import BEFORE_D3
from test_plan import db_of
from test_today import ahead

from mealwright import change_kinds
from mealwright.models import Change, Login, Meal, MealItem, Place, Shop, utcnow

API = "/api/v1"


def _write_as_beta2(
    kitchen: TestClient, kind: str, summary: str, data: dict[str, Any] | None
) -> int:
    """One change row with the columns beta.2's `history.record` filled, nothing else."""
    with db_of(kitchen) as db:
        login = db.scalars(select(Login).where(Login.household_id == 1)).first()
        assert login is not None
        change = Change(
            household_id=1,
            idempotency_key=None,
            request="POST /api/v1/beta2",
            kind=kind,
            login_id=login.id,
            login_name=login.name,
            at=utcnow(),
            summary=summary,
            undo_data=data,
        )
        db.add(change)
        db.commit()
        return change.id


def _drop_newest(kitchen: TestClient, kind: str) -> None:
    """Take away the row today's code just wrote, so only the beta.2 copy is left."""
    with db_of(kitchen) as db:
        newest = db.scalars(
            select(Change.id).where(Change.kind == kind).order_by(Change.id.desc())
        ).first()
        db.execute(delete(Change).where(Change.id == newest))
        db.commit()


def _listed(kitchen: TestClient, **params: Any) -> dict[str, dict[str, Any]]:
    seen: dict[str, dict[str, Any]] = {}
    after: str | None = None
    while True:
        page = ok(
            kitchen.get(
                f"{API}/changes",
                params={"limit": 100, **params, **({"after": after} if after else {})},
            )
        )
        for c in page["changes"]:
            seen[c["summary"]] = c
        after = page["next"]
        if after is None:
            return seen


def test_every_kind_beta2_stored_is_listed_with_its_words(kitchen: TestClient) -> None:
    """Every kind beta.2 could store (the list from before D3) shows in Recent changes, with
    the words it was saved with, and in its own area's list."""
    shown = [k for k in BEFORE_D3 if k not in change_kinds.KEY_ONLY and k != change_kinds.UNDO]
    ids = {k: _write_as_beta2(kitchen, k, f"beta.2 words for {k}", None) for k in shown}
    everything = _listed(kitchen)
    listed = {k for k in shown if f"beta.2 words for {k}" in everything}
    hidden_notes = {"person_login"}  # read on its person's page, never in Recent changes
    assert set(shown) - listed <= hidden_notes
    for kind in listed:
        assert everything[f"beta.2 words for {kind}"]["id"] == ids[kind]
    pantry = _listed(kitchen, area="pantry")
    assert {k for k in change_kinds.STOCK} == {
        k for k in shown if f"beta.2 words for {k}" in pantry
    }
    ingredients = _listed(kitchen, area="ingredients")
    assert {k for k in change_kinds.INGREDIENTS} == {
        k for k in shown if f"beta.2 words for {k}" in ingredients
    }


def test_shops_and_places_beta2_saved_still_undo(kitchen: TestClient) -> None:
    """Shops were recorded by `api/v1/kitchen.py` in beta.2 and by `kitchen_changes` now;
    places' routes moved to `household.py`. The stored payloads beta.2 wrote still undo."""
    shop = ok(kitchen.post(f"{API}/shops", json={"name": "Corner shop"}), 201)
    _drop_newest(kitchen, "shop_added")
    added = _write_as_beta2(
        kitchen,
        "shop_added",
        "Added the shop Corner shop",
        {"shop": {"id": shop["id"], "new": "Corner shop"}},
    )
    other = ok(kitchen.post(f"{API}/shops", json={"name": "Market"}), 201)
    ok(kitchen.patch(f"{API}/shops/{other['id']}", json={"name": "Big market"}))
    _drop_newest(kitchen, "shop_renamed")
    renamed = _write_as_beta2(
        kitchen,
        "shop_renamed",
        "Renamed the shop Market to Big market",
        {"shop": {"id": other["id"], "old": "Market", "new": "Big market"}},
    )
    place = ok(
        kitchen.post(f"{API}/places", json={"name": "Garage shelf", "kind": "cupboard"}), 201
    )
    _drop_newest(kitchen, "place_added")
    with db_of(kitchen) as db:
        kind = db.get(Place, place["id"]).kind  # type: ignore[union-attr]
    place_added = _write_as_beta2(
        kitchen,
        "place_added",
        "Added the place Garage shelf",
        {"place": {"id": place["id"], "new": "Garage shelf", "kind": kind}},
    )
    second = ok(kitchen.post(f"{API}/places", json={"name": "Loft", "kind": "cupboard"}), 201)
    ok(kitchen.patch(f"{API}/places/{second['id']}", json={"name": "Attic"}))
    _drop_newest(kitchen, "place_renamed")
    place_renamed = _write_as_beta2(
        kitchen,
        "place_renamed",
        "Renamed the place Loft to Attic",
        {"place": {"id": second["id"], "old": "Loft", "new": "Attic", "kind": kind}},
    )
    shown = _listed(kitchen)
    for words in (
        "Added the shop Corner shop",
        "Renamed the shop Market to Big market",
        "Added the place Garage shelf",
        "Renamed the place Loft to Attic",
    ):
        assert words in shown
    for change in (place_renamed, place_added, renamed, added):
        ok(kitchen.post(f"{API}/changes/{change}/undo"))
    with db_of(kitchen) as db:
        assert db.get(Shop, shop["id"]) is None
        assert db.get(Shop, other["id"]).name == "Market"  # type: ignore[union-attr]
        assert db.get(Place, place["id"]) is None
        assert db.get(Place, second["id"]).name == "Loft"  # type: ignore[union-attr]


def test_a_planned_ingredient_beta2_saved_still_undoes(kitchen: TestClient) -> None:
    """A planned ingredient is `kind: "food"` in the API since D3 and stays `ingredient` in the
    database; beta.2's plan_added row (its steps name meal and item ids) still undoes."""
    food = ok(kitchen.post(f"{API}/foods", json={"name": "Mango"}), 201)["food"]
    slot = ok(kitchen.get(f"{API}/meal-slots"))["meal_slots"][0]["id"]
    day = str(ahead(kitchen, 2))
    ok(
        kitchen.post(
            f"{API}/plan/items", json={"date": day, "slot_id": slot, "food_id": food["id"]}
        ),
        201,
    )
    _drop_newest(kitchen, "plan_added")
    with db_of(kitchen) as db:
        item = db.scalars(select(MealItem).where(MealItem.food_id == food["id"])).one()
        assert item.kind == "ingredient"
        meal_id, item_id = item.meal_id, item.id
    planned = _write_as_beta2(
        kitchen,
        "plan_added",
        "Planned Mango for beta.2's day",
        {
            "plan": [{"op": "new_meal", "meal": meal_id}, {"op": "add_item", "item": item_id}],
            "thing": "Mango",
            "meal_id": meal_id,
            "item_id": item_id,
        },
    )
    assert "Planned Mango for beta.2's day" in _listed(kitchen)
    ok(kitchen.post(f"{API}/changes/{planned}/undo"))
    with db_of(kitchen) as db:
        assert db.get(MealItem, item_id) is None
        assert db.get(Meal, meal_id) is None
