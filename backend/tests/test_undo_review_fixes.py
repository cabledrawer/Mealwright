"""Whole-0.8 review, Undo findings D2, D3 and D4: Undo of a removed place brings back its
stocktake progress and says "partly" when a packet has moved on since; Undo of "Planned X" puts
the recipe's "used last" way of cooking back even after another way was picked for that meal."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_plan import slot_ids
from test_plan_writes import D1
from test_recipe_list import stock
from test_recipe_methods import curry
from test_recipes import food

from mealwright.models import RecipeMethod, StockLot, StocktakeEntry, StocktakePlace

API = "/api/v1"


def places(client: TestClient) -> dict[str, int]:
    return {p["name"]: p["id"] for p in ok(client.get(f"{API}/places"))}


def _lot_of(client: TestClient, food_id: int) -> int:
    with client.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        return int(db.scalar(select(StockLot.id).where(StockLot.food_id == food_id)))


def test_undo_of_a_removed_place_brings_back_its_stocktake_progress(kitchen: TestClient) -> None:
    garage = ok(
        kitchen.post(f"{API}/places", json={"name": "Garage freezer", "kind": "freezer"}), 201
    )
    peas = food(kitchen, "Peas", place_id=garage["id"])
    ok(kitchen.post(f"{API}/foods/{peas['id']}/sizes", json={"name": "bag", "amount": 1000}), 201)
    stock(kitchen, peas["id"], 500, "g", place_id=garage["id"])
    answered = kitchen.post(
        f"{API}/stocktake/places/{garage['id']}/foods/{peas['id']}/answer", json={"fraction": 0.5}
    )
    assert answered.status_code == 200, answered.text
    ok(kitchen.post(f"{API}/stocktake/places/{garage['id']}/finish"))

    def progress() -> tuple[list[tuple[int, bool]], int]:
        with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            entries = db.scalars(
                select(StocktakeEntry).where(StocktakeEntry.place_id == garage["id"])
            ).all()
            done = db.scalars(
                select(StocktakePlace).where(StocktakePlace.place_id == garage["id"])
            ).all()
            return sorted((e.food_id, e.answered) for e in entries), len(done)

    held = progress()
    assert held[0] and held[1] == 1
    gone = ok(
        kitchen.delete(
            f"{API}/places/{garage['id']}", params={"move_to": places(kitchen)["Freezer"]}
        )
    )
    assert progress() == ([], 0)
    ok(kitchen.post(f"{API}/changes/{gone['change']['id']}/undo"))
    assert progress() == held


def test_undo_of_a_removed_place_says_partly_when_a_packet_has_moved_on(
    kitchen: TestClient,
) -> None:
    shelf = ok(kitchen.post(f"{API}/places", json={"name": "Spice shelf", "kind": "cupboard"}), 201)
    rice = food(kitchen, "Rice")
    stock(kitchen, rice["id"], 2, "kg", place_id=shelf["id"])
    lot_id = _lot_of(kitchen, rice["id"])
    named = places(kitchen)
    gone = ok(kitchen.delete(f"{API}/places/{shelf['id']}", params={"move_to": named["Cupboard"]}))
    ok(kitchen.post(f"{API}/stock/{lot_id}/move", json={"place_id": named["Fridge"]}))
    undone = ok(kitchen.post(f"{API}/changes/{gone['change']['id']}/undo"))
    assert undone["result"] == "partly"
    assert "changed again" in undone["message"]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.get(StockLot, lot_id).place_id == named["Fridge"]  # it stays where it was moved


def test_undo_of_a_removed_place_says_undone_when_everything_went_back(kitchen: TestClient) -> None:
    shelf = ok(kitchen.post(f"{API}/places", json={"name": "Spice shelf", "kind": "cupboard"}), 201)
    rice = food(kitchen, "Rice")
    stock(kitchen, rice["id"], 2, "kg", place_id=shelf["id"])
    gone = ok(
        kitchen.delete(
            f"{API}/places/{shelf['id']}", params={"move_to": places(kitchen)["Cupboard"]}
        )
    )
    undone = ok(kitchen.post(f"{API}/changes/{gone['change']['id']}/undo"))
    assert undone["result"] == "done"


def test_undo_of_planning_puts_the_used_last_way_back_after_another_way_was_picked(
    kitchen: TestClient,
) -> None:
    a, b, c = (food(kitchen, n) for n in ("Meth chicken", "Meth water", "Meth stock"))
    recipe = curry(kitchen, {"Meth chicken": a, "Meth water": b, "Meth stock": c})
    slot = slot_ids(kitchen)["Dinner"]

    def last_used() -> dict[int, object]:
        with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            return {
                m.id: m.last_used_at
                for m in db.scalars(
                    select(RecipeMethod).where(RecipeMethod.recipe_id == recipe["id"])
                )
            }

    before = last_used()
    planned = ok(
        kitchen.post(
            f"{API}/plan/items",
            json={"date": D1.isoformat(), "slot_id": slot, "recipe_id": recipe["id"]},
        ),
        201,
    )
    other = recipe["methods"][1]["id"]
    ok(kitchen.patch(f"{API}/plan/items/{planned['item_id']}", json={"method_id": other}))
    assert last_used() != before
    ok(kitchen.post(f"{API}/changes/{planned['change']['id']}/undo"))
    assert last_used() == before


def test_undo_of_a_removed_place_leaves_a_new_stocktake_alone(kitchen: TestClient) -> None:
    """RF1 review r1 (proposed, for cabledrawer): remove a place, press "Start a new stocktake",
    then
    Undo the removal: the new stocktake doesn't get the old place's answers or its finished mark."""
    garage = ok(
        kitchen.post(f"{API}/places", json={"name": "Garage freezer", "kind": "freezer"}), 201
    )
    peas = food(kitchen, "Peas", place_id=garage["id"])
    stock(kitchen, peas["id"], 500, "g", place_id=garage["id"])
    freezer = places(kitchen)["Freezer"]
    beans = food(kitchen, "Broad beans", place_id=freezer)
    stock(kitchen, beans["id"], 1000, "g", place_id=freezer)
    for place_id, food_id in ((garage["id"], peas["id"]), (freezer, beans["id"])):
        sized = kitchen.post(f"{API}/foods/{food_id}/sizes", json={"name": "bag", "amount": 1000})
        ok(sized, 201)
        answered = kitchen.post(
            f"{API}/stocktake/places/{place_id}/foods/{food_id}/answer", json={"fraction": 1}
        )
        assert answered.status_code == 200, answered.text
    ok(kitchen.post(f"{API}/stocktake/places/{garage['id']}/finish"))
    gone = ok(kitchen.delete(f"{API}/places/{garage['id']}", params={"move_to": freezer}))
    ok(kitchen.post(f"{API}/stocktake/restart"))
    ok(kitchen.post(f"{API}/changes/{gone['change']['id']}/undo"))
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalars(select(StocktakeEntry)).all() == []
        assert db.scalars(select(StocktakePlace)).all() == []
    assert ok(kitchen.get(f"{API}/stocktake"))["started"] is False
