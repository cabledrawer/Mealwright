"""Duplicate a recipe (0.7 paper cuts; spec, "Paper cuts"): "Sambar (copy)" with everything in
the recipe, none of its cooked history or plan, and a photo file of its own."""

from pathlib import Path
from typing import Any

import photo_kit as kit
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sync_kit import ok
from test_plan import slot_ids
from test_plan_writes import D1, plan_recipe
from test_recipes import make, save

from mealwright.models import MealItem, Recipe, RecipePhoto, RecipeStepLine

API = "/api/v1"


def duplicate(client: TestClient, recipe_id: int, **headers: str) -> Any:
    return client.post(f"{API}/recipes/{recipe_id}/duplicate", headers=headers)


def full_recipe(client: TestClient) -> dict[str, Any]:
    toor = ok(client.post(f"{API}/foods", json={"name": "Toor dal"}), 201)
    food_id = toor["food"]["id"]
    body = {
        "name": "Sambar",
        "description": "Lentil stew",
        "time_minutes": 50,
        "serves": 6,
        "makes": {"amount": 2, "unit": "l"},
        "tags": ["Batch-friendly", "Quick"],
        "nutrition": {"kcal": 320, "protein": 14.5},
        "source_note": "Amma",
        "lines": [
            {"kind": "heading", "words": "For the dal"},
            {
                "words": "toor dal",
                "amount": "200",
                "unit": "g",
                "food_id": food_id,
                "note": "rinsed",
            },
            {"words": "salt"},
        ],
        "steps": [
            {"kind": "step", "text": "Boil the dal.", "lines": [1]},
            {"kind": "step", "text": "Salt it."},
        ],
    }
    return ok(client.post(f"{API}/recipes", json=body), 201)  # type: ignore[no-any-return]


def test_the_copy_has_everything_in_the_recipe_under_a_new_name(kitchen: TestClient) -> None:
    mine = full_recipe(kitchen)
    copy = ok(duplicate(kitchen, mine["id"]), 201)
    assert copy["id"] != mine["id"]
    assert copy["name"] == "Sambar (copy)"
    assert copy["version"] == 1
    for field in ("description", "time_minutes", "serves", "makes", "source_note", "nutrition"):
        assert copy[field] == mine[field], field
    assert sorted(copy["tags"]) == sorted(mine["tags"]) == ["Batch-friendly", "Quick"]

    def shape(r: dict[str, Any]) -> list[tuple[Any, ...]]:
        return [
            (x["kind"], x["words"], x["amount"], x["unit"], x["note"], x["food"])
            for x in r["lines"]
        ]

    assert shape(copy) == shape(mine)
    assert [s["text"] for s in copy["steps"]] == [s["text"] for s in mine["steps"]]
    assert {line["id"] for line in copy["lines"]}.isdisjoint({line["id"] for line in mine["lines"]})
    # The original is untouched, and the copy is listed.
    assert ok(kitchen.get(f"{API}/recipes/{mine['id']}")) == mine
    listed = ok(kitchen.get(f"{API}/recipes", params={"q": "Sambar"}))["recipes"]
    assert {r["name"] for r in listed} == {"Sambar", "Sambar (copy)"}


def test_a_step_keeps_its_ingredient_links_on_the_copies_own_lines(kitchen: TestClient) -> None:
    mine = full_recipe(kitchen)
    copy = ok(duplicate(kitchen, mine["id"]), 201)
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        links = list(db.scalars(select(RecipeStepLine)))
    copy_line_ids = {line["id"] for line in copy["lines"]}
    mine_line_ids = {line["id"] for line in mine["lines"]}
    on_copy = [link for link in links if link.line_id in copy_line_ids]
    on_mine = [link for link in links if link.line_id in mine_line_ids]
    assert len(on_copy) == len(on_mine) >= 1
    assert all(link.kind == "by_hand" for link in on_copy)


def test_a_long_name_still_fits(kitchen: TestClient) -> None:
    mine = make(kitchen, "N" * 200)
    copy = ok(duplicate(kitchen, mine["id"]), 201)
    assert len(copy["name"]) <= 200 and copy["name"].endswith(" (copy)")


def test_the_plan_is_not_copied(kitchen: TestClient) -> None:
    mine = full_recipe(kitchen)
    plan_recipe(kitchen, mine["id"], D1, slot_ids(kitchen)["Dinner"])
    copy = ok(duplicate(kitchen, mine["id"]), 201)
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        planned = db.scalar(
            select(func.count()).select_from(MealItem).where(MealItem.recipe_id == mine["id"])
        )
        on_copy = db.scalar(
            select(func.count()).select_from(MealItem).where(MealItem.recipe_id == copy["id"])
        )
    assert (planned, on_copy) == (1, 0)


def test_a_retry_with_the_same_key_makes_one_copy(kitchen: TestClient) -> None:
    mine = make(kitchen)
    first = ok(duplicate(kitchen, mine["id"], **{"Idempotency-Key": "dup-1"}), 201)
    again = duplicate(kitchen, mine["id"], **{"Idempotency-Key": "dup-1"})
    assert again.status_code == 200 and again.json()["id"] == first["id"]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalar(select(func.count()).select_from(Recipe)) == 2


def test_the_photo_is_a_file_of_the_copys_own(kitchen: TestClient) -> None:
    mine = make(kitchen)
    photo = kit.uploaded(kitchen)
    mine = ok(save(kitchen, mine, photo_id=photo["id"]))
    copy = ok(duplicate(kitchen, mine["id"]), 201)
    assert copy["photo"] and copy["photo"]["id"] != photo["id"]
    big = kitchen.get(copy["photo"]["url"])
    assert big.status_code == 200 and big.content == kitchen.get(photo["url"]).content
    folder = Path(kitchen.app.state.settings.data_dir) / "photos" / "1"  # type: ignore[attr-defined]
    assert len(list(folder.iterdir())) == 4
    # Taking the photo off the copy leaves the original's.
    ok(save(kitchen, copy, photo_id=None))
    assert kitchen.get(photo["url"]).status_code == 200
    assert len(list(folder.iterdir())) == 2
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalar(select(func.count()).select_from(RecipePhoto)) == 1


def test_no_photo_means_none_on_the_copy(kitchen: TestClient) -> None:
    copy = ok(duplicate(kitchen, make(kitchen)["id"]), 201)
    assert copy["photo"] is None


def test_a_made_ahead_recipe_gets_its_own_ingredient_and_every_copy_a_new_name(
    kitchen: TestClient,
) -> None:
    mine = make(kitchen, "Sambar powder", made_ahead=True, makes={"amount": 200, "unit": "g"})
    copies = [ok(duplicate(kitchen, mine["id"]), 201) for _ in range(3)]
    names = ["Sambar powder (copy)", "Sambar powder (copy 2)", "Sambar powder (copy 3)"]
    assert [c["name"] for c in copies] == names
    assert [c["homemade"]["name"] for c in copies] == names
    assert len({c["homemade"]["id"] for c in copies} | {mine["homemade"]["id"]}) == 4


def test_a_plain_recipe_numbers_its_copies_the_same_way(kitchen: TestClient) -> None:
    mine = make(kitchen)
    names = [ok(duplicate(kitchen, mine["id"]), 201)["name"] for _ in range(3)]
    assert names == ["Sambar (copy)", "Sambar (copy 2)", "Sambar (copy 3)"]
    long = make(kitchen, "N" * 200)
    first, second = (ok(duplicate(kitchen, long["id"]), 201)["name"] for _ in range(2))
    assert len(first) <= 200 and len(second) <= 200 and second.endswith(" (copy 2)")


def test_a_missing_or_removed_recipe_is_a_404(kitchen: TestClient) -> None:
    assert duplicate(kitchen, 999).status_code == 404
    mine = make(kitchen)
    assert kitchen.delete(f"{API}/recipes/{mine['id']}").status_code == 200
    assert duplicate(kitchen, mine["id"]).status_code == 404


def test_another_household_cannot_copy_it(kitchen: TestClient, neighbour: TestClient) -> None:
    mine = make(kitchen)
    r = duplicate(neighbour, mine["id"])
    assert r.status_code == 404
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalar(select(func.count()).select_from(Recipe)) == 1
