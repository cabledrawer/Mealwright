"""D3 "API names": the API is named one way everywhere (consistency review BE13-BE29)."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_plan import db_of
from test_today import ago, ahead, new_recipe

from mealwright.main import create_app
from mealwright.models import BatchCook, MealItem, Tub

API = "/api/v1"


def openapi() -> dict[str, Any]:
    return create_app().openapi()


# --- BE17: list envelopes and paging ---------------------------------------------------------


def test_no_route_answers_a_bare_list() -> None:
    """Every list comes in an object named after what it holds, so a field can be added later
    (paging, a count) without breaking an app."""
    bare = []
    for path, ops in openapi()["paths"].items():
        for method, op in ops.items():
            for code, answer in op.get("responses", {}).items():
                schema = answer.get("content", {}).get("application/json", {}).get("schema", {})
                if code.startswith("2") and schema.get("type") == "array":
                    bare.append(f"{method.upper()} {path}")
    assert bare == []


def test_paged_lists_take_after_and_answer_next() -> None:
    """One cursor name: a paged list takes the `next` of the page before as `after`."""
    old_names = {"before", "more", "cursor", "page", "offset"}
    wrong = [
        f"{method.upper()} {path} ?{param['name']}"
        for path, ops in openapi()["paths"].items()
        for method, op in ops.items()
        for param in op.get("parameters", [])
        if param["in"] == "query" and param["name"] in old_names
    ]
    assert wrong == []


def test_tubs_left_pages_with_after_and_next(kitchen: TestClient) -> None:
    recipe = new_recipe(kitchen, "Paged sambar")
    with db_of(kitchen) as db:
        batch = BatchCook(
            household_id=1,
            recipe_id=recipe,
            recipe_name="Paged sambar",
            cooked_on=ago(kitchen, 1),
            tub_count=3,
            pattern="pick",
        )
        db.add(batch)
        db.flush()
        for days in (1, 2, 3):
            db.add(Tub(household_id=1, batch_id=batch.id, use_by=ahead(kitchen, days)))
        db.commit()
    everything = ok(kitchen.get(f"{API}/plan/tubs-left"))
    assert everything["next"] is None and "more" not in everything
    ids = [t["id"] for t in everything["tubs"]]
    assert len(ids) == 3
    seen: list[int] = []
    after: str | None = None
    for _ in range(3):
        params: dict[str, Any] = {"limit": 2} | ({"after": after} if after else {})
        page = ok(kitchen.get(f"{API}/plan/tubs-left", params=params))
        seen += [t["id"] for t in page["tubs"]]
        after = page["next"]
        if after is None:
            break
    assert seen == ids
    assert kitchen.get(f"{API}/plan/tubs-left", params={"after": "x"}).status_code == 422
    today = ok(kitchen.get(f"{API}/today"))
    assert today["tubs_left_next"] is None and "tubs_left_more" not in today


# --- BE18: the API says "food" ---------------------------------------------------------------


def test_a_planned_ingredient_is_a_food_in_the_api_and_stays_ingredient_in_the_database(
    kitchen: TestClient,
) -> None:
    food = ok(kitchen.post(f"{API}/foods", json={"name": "Banana"}), 201)["food"]
    slot = ok(kitchen.get(f"{API}/meal-slots"))["meal_slots"][0]["id"]
    day = str(ahead(kitchen, 1))
    old = kitchen.post(f"{API}/plan/items", json={"date": day, "slot_id": slot, "ingredient_id": 1})
    assert old.status_code == 422  # the old name is gone, not quietly read
    ok(
        kitchen.post(
            f"{API}/plan/items", json={"date": day, "slot_id": slot, "food_id": food["id"]}
        ),
        201,
    )
    [meal] = ok(kitchen.get(f"{API}/plan", params={"from": day, "to": day}))["meals"]
    [item] = meal["items"]
    assert item["kind"] == "food" and item["food"]["id"] == food["id"]
    assert "ingredient" not in item
    with db_of(kitchen) as db:
        assert [i.kind for i in db.scalars(select(MealItem))] == ["ingredient"]


def test_the_food_names_in_the_routes() -> None:
    paths = openapi()["paths"]
    assert "/api/v1/recipes/drafts/by-food" in paths
    assert "/api/v1/recipes/drafts/by-food/answer" in paths
    assert not [p for p in paths if "ingredient" in p]


# --- BE28: one resource has one home -------------------------------------------------------


def test_your_data_routes_live_under_your_data_and_the_old_ones_are_gone() -> None:
    paths = openapi()["paths"]
    for old in ("/backups", "/export", "/delete-everything", "/shopping/changes"):
        assert f"{API}{old}" not in paths, old
    assert set(paths[f"{API}/your-data/backups"]) == {"get", "patch", "post"}
    assert set(paths[f"{API}/your-data/export"]) == {"get", "post"}
    assert set(paths[f"{API}/your-data/delete-everything"]) == {"get", "post"}
    assert "get" in paths[f"{API}/shopping/sync"]


def test_the_old_your_data_addresses_answer_404(kitchen: TestClient) -> None:
    for old in ("/backups", "/export", "/delete-everything", "/shopping/changes?since=0"):
        assert kitchen.get(f"{API}{old}").status_code == 404, old
    assert ok(kitchen.get(f"{API}/your-data/backups"))["keep"] >= 1
    assert ok(kitchen.get(f"{API}/shopping/sync", params={"since": 0}))["cursor"] == 0
