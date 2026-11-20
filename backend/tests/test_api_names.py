"""D3 "API names": the API is named one way everywhere (consistency review BE13-BE29)."""

from typing import Any

from fastapi.testclient import TestClient
from sync_kit import ok
from test_plan import db_of
from test_today import ago, ahead, new_recipe

from mealwright.main import create_app
from mealwright.models import BatchCook, Tub

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
