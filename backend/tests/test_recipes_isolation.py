"""One household can never see or change another's recipes, tags or lines (cabledrawer 19 Oct).

Two real households, each with its own admin and session. Household 1 has recipes (one
inside another), tags, lines, an ingredient with a size, and a deleted recipe that can be
undone. From household 2, every recipe endpoint is tried with household 1's ids, reading and
writing, and each answer is a plain "not found". Household 1's rows must be exactly the same
afterwards. (PR 0a has a general isolation test; when it merges this one can share its helpers.)
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sync_kit import ok
from test_recipes import make, save

from mealwright.auth import hash_password
from mealwright.db import Base
from mealwright.household import add_default_places
from mealwright.models import Household, Login, Recipe, RecipeLine, RecipeTag, Tag

API = "/api/v1"
NEIGHBOUR = {"username": "neighbour", "password": "next door's own password"}


@pytest.fixture
def neighbour(kitchen: TestClient) -> Iterator[TestClient]:
    """Household 2, with its own admin, signed in on its own client."""
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(Household(id=2, name="Next door"))
        db.flush()
        add_default_places(db, 2)
        db.add(
            Login(
                household_id=2,
                username=NEIGHBOUR["username"],
                name="Neighbour",
                password_hash=hash_password(NEIGHBOUR["password"]),
                role="admin",
            )
        )
        db.commit()
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        assert other.post(f"{API}/session", json=NEIGHBOUR).status_code == 200
        yield other


def rows_of_household_1(kitchen: TestClient) -> dict[str, list[tuple[Any, ...]]]:
    """Every row of household 1, in every table, exactly as stored."""
    found: dict[str, list[tuple[Any, ...]]] = {}
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        for table in Base.metadata.sorted_tables:
            column = "id" if table.name == "household" else "household_id"
            query = f'SELECT * FROM "{table.name}" WHERE {column} = 1 ORDER BY 1, 2'  # noqa: S608
            found[table.name] = [tuple(row) for row in db.execute(text(query)).all()]
    return found


@pytest.fixture
def mine(kitchen: TestClient) -> dict[str, Any]:
    """Household 1's recipes, and the ids to attack them with."""
    toor = ok(kitchen.post(f"{API}/foods", json={"name": "Toor dal"}), 201)["food"]
    size = ok(
        kitchen.post(f"{API}/foods/{toor['id']}/sizes", json={"name": "packet", "amount": 500}),
        201,
    )["food"]["sizes"][0]
    powder = make(kitchen, "Sambar powder", tags=["Podi"], made_ahead=True)
    sambar = make(
        kitchen,
        "Sambar",
        tags=["Quick", "Batch-friendly"],
        steps=[{"text": "Boil."}],
        lines=[
            {"words": "dal", "amount": 1, "size_id": size["id"], "food_id": toor["id"]},
            {"words": "powder", "amount": 2, "unit": "tbsp", "recipe_id": powder["id"]},
        ],
    )
    gone = make(kitchen, "Old rasam", tags=["Old"])
    removed = ok(kitchen.delete(f"{API}/recipes/{gone['id']}"))["change"]
    return {
        "food_id": toor["id"],
        "size_id": size["id"],
        "powder": powder,
        "sambar": sambar,
        "recipe_id": sambar["id"],
        "powder_id": powder["id"],
        "gone_id": gone["id"],
        "line_id": sambar["lines"][0]["id"],
        "homemade_id": powder["homemade"]["id"],
        "remove_change_id": removed["id"],
    }


def not_found(response: Any) -> None:
    assert response.status_code == 404, response.text
    assert response.json()["code"] == "not_found", response.text


def test_the_other_household_sees_no_recipes_and_no_tags(
    kitchen: TestClient, neighbour: TestClient, mine: dict[str, Any]
) -> None:
    before = rows_of_household_1(kitchen)
    assert ok(neighbour.get(f"{API}/recipes")) == {"total": 0, "recipes": [], "next": None}
    assert ok(neighbour.get(f"{API}/recipes/tags")) == {"tags": []}
    assert ok(neighbour.get(f"{API}/recipes/tags", params={"q": "quick"})) == {"tags": []}
    assert ok(neighbour.get(f"{API}/foods"))["foods"] == []
    assert rows_of_household_1(kitchen) == before
    # And household 1 still sees its own.
    assert [r["name"] for r in ok(kitchen.get(f"{API}/recipes"))["recipes"]] == [
        "Sambar",
        "Sambar powder",
    ]
    assert [t["name"] for t in ok(kitchen.get(f"{API}/recipes/tags"))["tags"]] == [
        "Batch-friendly",
        "Podi",
        "Quick",
    ]


def test_household_1_recipe_ids_are_404_for_household_2(
    kitchen: TestClient, neighbour: TestClient, mine: dict[str, Any]
) -> None:
    before = rows_of_household_1(kitchen)
    recipe_id, gone_id = mine["recipe_id"], mine["gone_id"]
    not_found(neighbour.get(f"{API}/recipes/{recipe_id}"))
    not_found(neighbour.get(f"{API}/recipes/{recipe_id}/cannot-use"))
    not_found(neighbour.delete(f"{API}/recipes/{recipe_id}"))
    not_found(neighbour.put(f"{API}/recipes/{recipe_id}", json={"name": "Mine now", "version": 1}))
    # A deleted recipe is no more reachable, and household 2 can't undo household 1's delete.
    not_found(neighbour.get(f"{API}/recipes/{gone_id}"))
    not_found(neighbour.post(f"{API}/changes/{mine['remove_change_id']}/undo"))
    assert rows_of_household_1(kitchen) == before


def test_household_2_cannot_link_a_line_to_household_1(
    kitchen: TestClient, neighbour: TestClient, mine: dict[str, Any]
) -> None:
    before = rows_of_household_1(kitchen)
    ghee = ok(neighbour.post(f"{API}/foods", json={"name": "Ghee"}), 201)["food"]
    own = make(neighbour, "Own recipe", lines=[{"words": "ghee", "food_id": ghee["id"]}])
    attempts: list[tuple[str, dict[str, Any]]] = [
        ("an ingredient", {"words": "dal", "food_id": mine["food_id"]}),
        ("a recipe", {"words": "powder", "recipe_id": mine["powder_id"]}),
        ("a deleted recipe", {"words": "rasam", "recipe_id": mine["gone_id"]}),
        (
            "a size",
            {"words": "ghee", "size_id": mine["size_id"], "food_id": ghee["id"]},
        ),
        ("a line", {"id": mine["line_id"], "words": "stolen"}),
    ]
    for what, line in attempts:
        created = neighbour.post(f"{API}/recipes", json={"name": "Try", "lines": [line]})
        assert created.status_code == 404, (what, created.text)
        assert created.json()["code"] == "not_found" and created.json()["line"] == 0, what
        saved = save(neighbour, own, lines=[line])
        assert saved.status_code == 404, (what, saved.text)
    assert ok(neighbour.get(f"{API}/recipes"))["total"] == 1  # only "Own recipe"
    assert rows_of_household_1(kitchen) == before


def test_household_2_cannot_loop_or_loop_check_against_household_1(
    kitchen: TestClient, neighbour: TestClient, mine: dict[str, Any]
) -> None:
    # Household 2's "Sambar powder" is not household 1's: Sambar uses Sambar powder in
    # household 1 only, so household 2's own recipes are free to use each other.
    powder2 = make(neighbour, "Sambar powder")
    sambar2 = make(neighbour, "Sambar")
    blocked = ok(neighbour.get(f"{API}/recipes/{powder2['id']}/cannot-use"))["recipes"]
    assert [b["name"] for b in blocked] == ["Sambar powder"]  # just itself
    ok(save(neighbour, powder2, lines=[{"words": "x", "recipe_id": sambar2["id"]}]))
    # And household 1's cannot-use list is unchanged by what household 2 did.
    blocked_1 = ok(kitchen.get(f"{API}/recipes/{mine['powder_id']}/cannot-use"))["recipes"]
    assert [b["name"] for b in blocked_1] == ["Sambar powder", "Sambar"]


def test_tags_are_each_households_own(
    kitchen: TestClient, neighbour: TestClient, mine: dict[str, Any]
) -> None:
    before = rows_of_household_1(kitchen)
    make(neighbour, "Theirs", tags=["Quick", "Kids"])
    assert [t["name"] for t in ok(neighbour.get(f"{API}/recipes/tags"))["tags"]] == [
        "Kids",
        "Quick",
    ]
    assert ok(neighbour.get(f"{API}/recipes/tags"))["tags"][1]["recipes"] == 1  # not 2
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        owners = {
            tag.name: {t.household_id for t in db.scalars(select(Tag).where(Tag.name == tag.name))}
            for tag in db.scalars(select(Tag))
        }
        assert owners["Quick"] == {1, 2}
    # Changing or dropping a tag in household 2 doesn't touch household 1's.
    theirs = ok(neighbour.get(f"{API}/recipes"))["recipes"][0]["id"]
    ok(save(neighbour, ok(neighbour.get(f"{API}/recipes/{theirs}")), tags=[]))
    assert ok(neighbour.get(f"{API}/recipes/tags"))["tags"] == []
    assert rows_of_household_1(kitchen) == before


def test_ingredient_counts_and_merges_stay_inside_the_household(
    kitchen: TestClient, neighbour: TestClient, mine: dict[str, Any]
) -> None:
    toor2 = ok(neighbour.post(f"{API}/foods", json={"name": "Toor dal"}), 201)["food"]
    arhar2 = ok(neighbour.post(f"{API}/foods", json={"name": "Arhar dal"}), 201)["food"]
    make(neighbour, "Dal", lines=[{"words": "arhar", "food_id": arhar2["id"]}])
    assert ok(neighbour.get(f"{API}/foods/{toor2['id']}"))["used_in_recipes"] == 0
    assert ok(kitchen.get(f"{API}/foods/{mine['food_id']}"))["used_in_recipes"] == 1
    before = rows_of_household_1(kitchen)
    ok(neighbour.post(f"{API}/foods/{arhar2['id']}/merge", json={"into_id": toor2["id"]}))
    assert ok(neighbour.get(f"{API}/foods/{toor2['id']}"))["used_in_recipes"] == 1
    assert rows_of_household_1(kitchen) == before
    # Removing household 1's ingredient unlinks household 1's lines only.
    ok(kitchen.delete(f"{API}/foods/{mine['food_id']}"))
    assert ok(neighbour.get(f"{API}/recipes"))["recipes"][0]["ingredient_count"] == 1
    lines = ok(
        neighbour.get(f"{API}/recipes/{ok(neighbour.get(f'{API}/recipes'))['recipes'][0]['id']}")
    )["lines"]
    assert lines[0]["food"]["name"] == "Toor dal"


def test_made_ahead_names_are_checked_inside_the_household(
    kitchen: TestClient, neighbour: TestClient, mine: dict[str, Any]
) -> None:
    # Household 1 already has an ingredient called "Sambar powder" (its made-ahead recipe's).
    theirs = make(neighbour, "Sambar powder", made_ahead=True)
    assert theirs["homemade"]["name"] == "Sambar powder"
    assert theirs["homemade"]["id"] != mine["homemade_id"]
    not_found(neighbour.get(f"{API}/foods/{mine['homemade_id']}"))


def test_the_same_change_id_in_both_households_deletes_in_each(
    kitchen: TestClient, neighbour: TestClient, mine: dict[str, Any]
) -> None:
    theirs = make(neighbour, "Sambar")
    headers = {"Idempotency-Key": "same-key-in-two-households"}
    first = ok(kitchen.delete(f"{API}/recipes/{mine['recipe_id']}", headers=headers))
    second = ok(neighbour.delete(f"{API}/recipes/{theirs['id']}", headers=headers))
    assert first["change"]["id"] != second["change"]["id"]
    assert ok(neighbour.get(f"{API}/recipes"))["total"] == 0
    # The other household's Undo is its own.
    ok(neighbour.post(f"{API}/changes/{second['change']['id']}/undo"))
    assert ok(neighbour.get(f"{API}/recipes"))["total"] == 1
    assert kitchen.get(f"{API}/recipes/{mine['recipe_id']}").status_code == 404


def test_every_recipe_row_belongs_to_the_household_that_made_it(
    kitchen: TestClient, neighbour: TestClient, mine: dict[str, Any]
) -> None:
    make(neighbour, "Theirs", tags=["Quick"], lines=[{"words": "salt"}], steps=[{"text": "Mix."}])
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        recipe_owner = {r.id: r.household_id for r in db.scalars(select(Recipe))}
        assert {1, 2} <= set(recipe_owner.values())
        for line in db.scalars(select(RecipeLine)):
            assert line.household_id == recipe_owner[line.recipe_id]
            if line.sub_recipe_id is not None:
                assert recipe_owner[line.sub_recipe_id] == line.household_id
        tag_owner = {t.id: t.household_id for t in db.scalars(select(Tag))}
        for link in db.scalars(select(RecipeTag)):
            assert link.household_id == recipe_owner[link.recipe_id] == tag_owner[link.tag_id]


def test_the_same_create_key_in_both_households_makes_a_recipe_in_each(
    kitchen: TestClient, neighbour: TestClient, mine: dict[str, Any]
) -> None:
    headers = {"Idempotency-Key": "same-create-key"}
    first = ok(kitchen.post(f"{API}/recipes", json={"name": "Rasam"}, headers=headers), 201)
    second = ok(neighbour.post(f"{API}/recipes", json={"name": "Rasam"}, headers=headers), 201)
    assert first["id"] != second["id"]
    # A retry in each household gets its own recipe back.
    again = neighbour.post(f"{API}/recipes", json={"name": "Rasam"}, headers=headers)
    assert again.status_code == 200 and again.json()["id"] == second["id"]
    again = kitchen.post(f"{API}/recipes", json={"name": "Rasam"}, headers=headers)
    assert again.status_code == 200 and again.json()["id"] == first["id"]
