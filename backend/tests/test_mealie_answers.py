"""Fixing Mealie drafts by ingredient (cabledrawer 15 Nov, 0.9.5-beta.2): the groups, each kind of
answer, a recipe moving only when all its lines are answered, Undo, who may, and speed.
Every file is made up here (made-up recipes); nothing goes online."""

import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sync_kit import person
from test_mealie_import import API, bring_in, database, line, recipe, zipped

from mealwright.models import (
    Change,
    Food,
    ImportDraft,
    MealieImport,
    Place,
    Recipe,
    RecipeLine,
)

A, B, C = (f"a{i:031d}" for i in range(3))
NAMES = {A: "Dish a", B: "Dish b", C: "Dish c"}
SOY = "2 tbsp soya sauce"
KASURI = "kasuri methi, a pinch"
GALANGAL = "2 cm galangal"


def file(recipes: dict[str, list[str]]) -> dict[str, Any]:
    """Recipes (key → their free-text lines): every line is one nobody can read, so each
    recipe waits in Drafts."""
    data = database()
    keys = list(recipes)
    data["recipes"] = [recipe(key, NAMES.get(key) or f"Dish {int(key[1:])}") for key in keys]
    data["recipes_ingredients"] = [
        line(key, at, text) for key, texts in recipes.items() for at, text in enumerate(texts)
    ]
    data["recipe_instructions"] = []
    data["recipes_to_tags"] = []
    data["ingredient_foods"] = []
    return data


@pytest.fixture
def waiting(kitchen: TestClient, tmp_path: Path) -> TestClient:
    """A: soya sauce, kasuri methi. B: soya sauce. C: soya sauce, galangal."""
    raw = zipped(
        tmp_path / "f.zip",
        file({A: [SOY, KASURI], B: ["1 tsp soya sauce"], C: [SOY, GALANGAL]}),
        photo=False,
    )
    job = bring_in(kitchen, raw)
    assert job["counts"]["drafts"] == 3, job
    return kitchen


def groups(client: TestClient, **query: Any) -> dict[str, Any]:
    answer = client.get(f"{API}/recipes/drafts/by-ingredient", params=query)
    assert answer.status_code == 200, answer.text
    return answer.json()  # type: ignore[no-any-return]


def answer(client: TestClient, key: str, kind: str, **fields: Any) -> Any:
    return client.post(
        f"{API}/recipes/drafts/by-ingredient/answer", json={"key": key, "kind": kind, **fields}
    )


def make_food(client: TestClient, name: str) -> int:
    made = client.post(f"{API}/foods", json={"name": name})
    assert made.status_code == 201, made.text
    return made.json()["food"]["id"]  # type: ignore[no-any-return]


def db(client: TestClient) -> Any:
    return client.app.state.sessionmaker()  # type: ignore[attr-defined]


def place_id(client: TestClient, name: str) -> int:
    with db(client) as session:
        found = session.scalar(select(Place.id).where(Place.name == name))
    assert found is not None
    return found  # type: ignore[no-any-return]


def draft_names(client: TestClient) -> list[str]:
    with db(client) as session:
        return sorted(d.name for d in session.scalars(select(ImportDraft)))


def recipe_lines(client: TestClient, name: str) -> dict[str, int | None]:
    with db(client) as session:
        found = session.scalar(
            select(Recipe).where(Recipe.name == name, Recipe.removed_at.is_(None))
        )
        assert found is not None, name
        return {
            row.words: row.food_id
            for row in session.scalars(select(RecipeLine).where(RecipeLine.recipe_id == found.id))
        }


# --- The groups -----------------------------------------------------------------------------


def test_the_unanswered_lines_are_grouped_by_ingredient_most_used_first(
    waiting: TestClient,
) -> None:
    found = groups(waiting)
    assert next(g["key"] for g in found["groups"]) == "soya sauce"
    soy = found["groups"][0]
    assert soy["drafts"] == 3 and soy["lines"] == 3
    assert len(soy["examples"]) == 2 and SOY in soy["examples"]
    assert found["total"] == 3 and found["drafts"] == 3
    assert {g["key"]: g["drafts"] for g in found["groups"]} == {
        "soya sauce": 3,
        "kasuri methi": 1,
        "galangal": 1,
    }
    assert [p["name"] for p in found["places"]][:1] == ["Fridge"]
    # Looking changes nothing.
    assert draft_names(waiting) == ["Dish a", "Dish b", "Dish c"]


def test_a_group_suggests_an_ingredient_the_household_has(waiting: TestClient) -> None:
    soy = make_food(waiting, "Soya sauce")
    first = groups(waiting)["groups"][0]
    assert first["suggestion"] is not None and first["suggestion"]["id"] == soy
    assert first["new_name"]


def test_limit_shows_the_first_groups_and_total_says_how_many(waiting: TestClient) -> None:
    found = groups(waiting, limit=1)
    assert len(found["groups"]) == 1 and found["total"] == 3


# --- Answers ------------------------------------------------------------------------------------


def test_an_ingredient_i_have_goes_into_every_draft_that_uses_it(waiting: TestClient) -> None:
    soy = make_food(waiting, "Soy sauce")
    done = answer(waiting, "soya sauce", "ingredient", food_id=soy)
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["drafts"] == 3 and body["moved"] == 1  # only Dish b had nothing else
    assert body["ingredient"]["id"] == soy
    assert (
        body["change"]["summary"]
        == "Answered “soya sauce” in 3 drafts · 1 recipes moved to Recipes"
    )
    assert draft_names(waiting) == ["Dish a", "Dish c"]
    assert list(recipe_lines(waiting, "Dish b").values()) == [soy]
    left = groups(waiting)
    assert {g["key"] for g in left["groups"]} == {"kasuri methi", "galangal"}
    # The two that stay show their progress.
    listed = waiting.get(f"{API}/recipes/drafts").json()["drafts"]
    assert {d["name"]: d["lines_checked"] for d in listed} == {"Dish a": 1, "Dish c": 1}


def test_a_recipe_moves_only_when_every_line_is_answered(waiting: TestClient) -> None:
    soy = make_food(waiting, "Soy sauce")
    answer(waiting, "soya sauce", "ingredient", food_id=soy)
    assert "Dish a" in draft_names(waiting)
    done = answer(waiting, "kasuri methi", "text")
    assert done.json()["moved"] == 1 and done.json()["ingredient"] is None
    assert draft_names(waiting) == ["Dish c"]
    lines = recipe_lines(waiting, "Dish a")
    assert KASURI in lines and lines[KASURI] is None  # plain text: never tied to an ingredient
    assert soy in lines.values()


def test_a_new_ingredient_is_made_once_with_its_place(waiting: TestClient) -> None:
    fridge = place_id(waiting, "Fridge")
    done = answer(waiting, "soya sauce", "new", name="  soya   sauce ", place_id=fridge)
    assert done.status_code == 200, done.text
    with db(waiting) as session:
        made = session.scalars(select(Food).where(Food.name == "soya sauce")).all()
        assert len(made) == 1 and made[0].place_id == fridge and made[0].staple is False
        assert made[0].mealie_import_id is not None
    assert done.json()["ingredient"]["id"] == made[0].id
    # Typed again later: it is the same ingredient, nothing is made twice.
    again = answer(waiting, "kasuri methi", "new", name="Soya sauce", place_id=fridge)
    assert again.json()["ingredient"]["id"] == made[0].id
    with db(waiting) as session:
        assert len(session.scalars(select(Food).where(Food.name.ilike("soya sauce"))).all()) == 1


def test_an_answer_can_be_refused(waiting: TestClient) -> None:
    assert answer(waiting, "nothing like it", "text").status_code == 404
    assert answer(waiting, "soya sauce", "ingredient", food_id=99999).status_code == 404
    assert answer(waiting, "soya sauce", "new", name="Soy", place_id=99999).status_code == 404
    assert answer(waiting, "soya sauce", "ingredient").status_code == 422
    assert answer(waiting, "soya sauce", "new", name="  ").status_code == 422
    assert draft_names(waiting) == ["Dish a", "Dish b", "Dish c"]  # nothing changed


def test_a_draft_the_person_changed_on_check_is_not_saved_for_them(waiting: TestClient) -> None:
    with db(waiting) as session:
        draft = session.scalar(select(ImportDraft).where(ImportDraft.name == "Dish b"))
        assert draft is not None
        draft.choices = {"name": "My own name", "lines": {}}
        session.commit()
    soy = make_food(waiting, "Soy sauce")
    done = answer(waiting, "soya sauce", "ingredient", food_id=soy).json()
    assert done["drafts"] == 3 and done["moved"] == 0
    assert draft_names(waiting) == ["Dish a", "Dish b", "Dish c"]


def test_a_retry_with_the_same_key_answers_once(waiting: TestClient) -> None:
    soy = make_food(waiting, "Soy sauce")
    body = {"key": "soya sauce", "kind": "ingredient", "food_id": soy}
    path = f"{API}/recipes/drafts/by-ingredient/answer"
    first = waiting.post(path, json=body, headers={"Idempotency-Key": "k-1"})
    second = waiting.post(path, json=body, headers={"Idempotency-Key": "k-1"})
    assert first.status_code == second.status_code == 200
    assert second.headers.get("Idempotent-Replayed") == "true"
    assert second.json()["change"]["id"] == first.json()["change"]["id"]
    with db(waiting) as session:
        assert (
            len(
                session.scalars(select(Change).where(Change.kind == "mealie_drafts_answered")).all()
            )
            == 1
        )


def test_the_imports_own_undo_still_takes_an_answered_recipe_out(waiting: TestClient) -> None:
    soy = make_food(waiting, "Soy sauce")
    answer(waiting, "soya sauce", "ingredient", food_id=soy)
    with db(waiting) as session:
        row = session.scalars(select(MealieImport)).one()
        states = {e["name"]: e["state"] for e in row.results}
        assert states["Dish b"] == "answered"
        import_id = row.id
    undone = waiting.post(f"{API}/mealie-imports/{import_id}/undo").json()
    assert undone["recipes"] == 1


# --- Undo -------------------------------------------------------------------------------------


def test_undo_puts_the_answers_back_and_the_recipes_back_in_drafts(waiting: TestClient) -> None:
    fridge = place_id(waiting, "Fridge")
    done = answer(waiting, "soya sauce", "new", name="Soya sauce", place_id=fridge).json()
    assert draft_names(waiting) == ["Dish a", "Dish c"]
    first = done["change"]["id"]
    undone = waiting.post(f"{API}/changes/{first}/undo")
    assert undone.status_code == 200, undone.text
    # B comes back to Drafts; A and C are unanswered again for soya sauce (C's recipe stays:
    # it was saved by the galangal answer, which was not undone... it is back only if untouched).
    names = draft_names(waiting)
    assert names == ["Dish a", "Dish b", "Dish c"]
    left = {g["key"] for g in groups(waiting)["groups"]}
    assert "soya sauce" in left
    with db(waiting) as session:
        made = session.scalar(select(Food).where(Food.name == "Soya sauce"))
        assert made is not None and made.removed_at is not None  # nothing else uses it
        row = session.scalars(select(MealieImport)).one()
        assert {e["name"]: e["state"] for e in row.results}["Dish b"] == "draft"
    again = waiting.post(f"{API}/changes/{first}/undo")
    assert again.status_code == 409


def test_undo_keeps_an_ingredient_a_saved_recipe_still_uses(waiting: TestClient) -> None:
    fridge = place_id(waiting, "Fridge")
    done = answer(waiting, "soya sauce", "new", name="Soya sauce", place_id=fridge).json()
    food_id = done["ingredient"]["id"]
    answer(waiting, "galangal", "text")  # Dish c is now complete and moves to Recipes
    assert draft_names(waiting) == ["Dish a"]
    waiting.post(f"{API}/changes/{done['change']['id']}/undo")
    with db(waiting) as session:
        assert session.get(Food, food_id).removed_at is None  # type: ignore[union-attr]
    assert "Dish c" not in draft_names(waiting)  # that recipe was saved by the other answer


def test_undo_leaves_a_recipe_changed_since_in_recipes(waiting: TestClient) -> None:
    soy = make_food(waiting, "Soy sauce")
    done = answer(waiting, "soya sauce", "ingredient", food_id=soy).json()
    with db(waiting) as session:
        recipe_row = session.scalar(select(Recipe).where(Recipe.name == "Dish b"))
        assert recipe_row is not None
        recipe_row.version += 1
        session.commit()
    undone = waiting.post(f"{API}/changes/{done['change']['id']}/undo").json()
    assert "stay in Recipes" in str(undone), undone
    assert "Dish b" not in draft_names(waiting)


def test_undo_of_a_partly_answered_draft_leaves_a_line_the_person_changed(
    waiting: TestClient,
) -> None:
    soy = make_food(waiting, "Soy sauce")
    done = answer(waiting, "soya sauce", "ingredient", food_id=soy).json()
    other = make_food(waiting, "Galangal")
    with db(waiting) as session:
        draft = session.scalar(select(ImportDraft).where(ImportDraft.name == "Dish c"))
        assert draft is not None
        lines = dict(draft.choices["lines"])
        first = next(iter(lines))
        lines[first] = {"kind": "ingredient", "food": {"id": other, "name": "Galangal"}}
        draft.choices = {**draft.choices, "lines": lines}
        session.commit()
    waiting.post(f"{API}/changes/{done['change']['id']}/undo")
    with db(waiting) as session:
        draft = session.scalar(select(ImportDraft).where(ImportDraft.name == "Dish c"))
        assert draft is not None
        assert next(iter(draft.choices["lines"].values()))["food"]["id"] == other


# --- Who may --------------------------------------------------------------------------------------


def test_signed_out_refused_and_other_households_see_nothing(
    waiting: TestClient, neighbour: TestClient, client: TestClient
) -> None:
    assert groups(neighbour)["groups"] == []
    assert answer(neighbour, "soya sauce", "text").status_code == 404
    assert draft_names(waiting) == ["Dish a", "Dish b", "Dish c"]
    out = TestClient(waiting.app, base_url="https://testserver")
    assert out.get(f"{API}/recipes/drafts/by-ingredient").status_code == 401
    assert (
        out.post(
            f"{API}/recipes/drafts/by-ingredient/answer", json={"key": "x", "kind": "text"}
        ).status_code
        == 401
    )


def test_a_member_and_a_token_may_answer_as_with_the_other_draft_routes(
    waiting: TestClient,
) -> None:
    noor = person(waiting, name="Noor", username="noor")
    assert noor.get(f"{API}/recipes/drafts").status_code == 200
    assert groups(noor)["total"] == 3
    assert answer(noor, "galangal", "text").status_code == 200
    made = waiting.post(f"{API}/api-tokens", json={"name": "script", "scope": "full"})
    app = TestClient(waiting.app, base_url="https://testserver")
    app.headers["Authorization"] = f"Bearer {made.json()['token']}"
    assert app.get(f"{API}/recipes/drafts").status_code == 200
    assert groups(app)["total"] == 2
    read_only = waiting.post(f"{API}/api-tokens", json={"name": "look", "scope": "read"})
    if read_only.status_code == 201:
        look = TestClient(waiting.app, base_url="https://testserver")
        look.headers["Authorization"] = f"Bearer {read_only.json()['token']}"
        assert answer(look, "kasuri methi", "text").status_code == 403


# --- F249 and speed ------------------------------------------------------------------------------


def test_a_mealie_food_brought_in_as_new_gets_a_pantry_place(
    kitchen: TestClient, tmp_path: Path
) -> None:
    """F249: a Mealie food keeps only an id and a name; its place is the first guess."""
    data = database()
    data["ingredient_foods"] = [
        {"id": "9a0e7c1a000040008000000000000002", "name": "Whole milk"},
        {"id": "9a0e7c1a000040008000000000000003", "name": "Vegetable stock"},
    ]
    job = bring_in(kitchen, zipped(tmp_path / "p.zip", data, photo=False))
    with db(kitchen) as session:
        places = {p.id: p.name for p in session.scalars(select(Place))}
        found = {
            f.name: places.get(f.place_id or 0)  # type: ignore[arg-type]
            for f in session.scalars(select(Food).where(Food.mealie_import_id == job["id"]))
        }
    assert found == {"Whole milk": "Fridge", "Vegetable stock": "Cupboard"}


def test_700_drafts_are_grouped_in_a_few_queries_and_a_short_time(
    kitchen: TestClient, tmp_path: Path
) -> None:
    recipes = {
        f"r{i:031d}": [f"{1 + i % 3} tbsp thing {i % 40}", f"a pinch of rarity {i}"]
        for i in range(700)
    }
    raw = zipped(tmp_path / "big.zip", file(recipes), photo=False)
    job = bring_in(kitchen, raw)
    assert job["counts"]["drafts"] == 700
    asked: list[str] = []
    engine = kitchen.app.state.engine  # type: ignore[attr-defined]

    def count(conn: Any, cursor: Any, statement: str, *_: Any) -> None:
        asked.append(statement)

    event.listen(engine, "after_cursor_execute", count)
    try:
        began = time.monotonic()
        found = groups(kitchen, limit=50)
        took = time.monotonic() - began
    finally:
        event.remove(engine, "after_cursor_execute", count)
    assert found["drafts"] == 700 and found["total"] == 40 + 700
    assert found["groups"][0]["drafts"] == 18  # most-used first (700 / 40, rounded up)
    assert len(asked) < 40, len(asked)  # not a query per draft
    assert took < 5, took
