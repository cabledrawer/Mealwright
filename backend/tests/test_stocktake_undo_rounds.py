"""L1c: Undo of a removed place puts its stocktake answers back only into the stocktake they
came from, whatever order things happened in (RF1 review r2, Low)."""

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_recipe_list import stock
from test_recipes import food
from test_undo_review_fixes import API, places

from mealwright.models import StocktakeEntry


def setup(kitchen: TestClient) -> dict[str, tuple[int, int]]:
    a = ok(kitchen.post(f"{API}/places", json={"name": "Garage freezer", "kind": "freezer"}), 201)
    b = ok(kitchen.post(f"{API}/places", json={"name": "Shed", "kind": "cupboard"}), 201)
    out: dict[str, tuple[int, int]] = {}
    for tag, place in (("a", a), ("b", b)):
        f = food(kitchen, f"Peas {tag}", place_id=place["id"])
        ok(kitchen.post(f"{API}/foods/{f['id']}/sizes", json={"name": "bag", "amount": 1000}), 201)
        stock(kitchen, f["id"], 500, "g", place_id=place["id"])
        out[tag] = (place["id"], f["id"])
    return out


def answer(kitchen: TestClient, place_id: int, food_id: int, fraction: float = 0.5) -> None:
    r = kitchen.post(
        f"{API}/stocktake/places/{place_id}/foods/{food_id}/answer", json={"fraction": fraction}
    )
    assert r.status_code == 200, r.text


def rows(kitchen: TestClient, place_id: int) -> int:
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        return len(
            db.scalars(select(StocktakeEntry).where(StocktakeEntry.place_id == place_id)).all()
        )


def test_c1_other_place_answered_after_removal(kitchen: TestClient) -> None:
    s = setup(kitchen)
    answer(kitchen, *s["a"])
    gone = ok(
        kitchen.delete(f"{API}/places/{s['a'][0]}", params={"move_to": places(kitchen)["Freezer"]})
    )
    answer(kitchen, *s["b"])
    ok(kitchen.post(f"{API}/changes/{gone['change']['id']}/undo"))
    assert rows(kitchen, s["a"][0]) == 1


def test_c2_restart_after_removal_and_nothing_answered(kitchen: TestClient) -> None:
    s = setup(kitchen)
    answer(kitchen, *s["a"])
    gone = ok(
        kitchen.delete(f"{API}/places/{s['a'][0]}", params={"move_to": places(kitchen)["Freezer"]})
    )
    ok(kitchen.post(f"{API}/stocktake/restart"))
    ok(kitchen.post(f"{API}/changes/{gone['change']['id']}/undo"))
    assert rows(kitchen, s["a"][0]) == 0


def test_c3_other_answer_tapped_again(kitchen: TestClient) -> None:
    s = setup(kitchen)
    answer(kitchen, *s["a"])
    answer(kitchen, *s["b"])
    gone = ok(
        kitchen.delete(f"{API}/places/{s['a'][0]}", params={"move_to": places(kitchen)["Freezer"]})
    )
    answer(kitchen, *s["b"], 1)
    ok(kitchen.post(f"{API}/changes/{gone['change']['id']}/undo"))
    assert rows(kitchen, s["a"][0]) == 1


def test_c4_both_removed_undo_first_removal_first(kitchen: TestClient) -> None:
    s = setup(kitchen)
    answer(kitchen, *s["a"])
    answer(kitchen, *s["b"])
    fr = places(kitchen)["Freezer"]
    gone_a = ok(kitchen.delete(f"{API}/places/{s['a'][0]}", params={"move_to": fr}))
    ok(kitchen.delete(f"{API}/places/{s['b'][0]}", params={"move_to": fr}))
    ok(kitchen.post(f"{API}/changes/{gone_a['change']['id']}/undo"))
    assert rows(kitchen, s["a"][0]) == 1
