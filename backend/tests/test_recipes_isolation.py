"""One household can never see or change another's recipes, tags, lines or photos
(cabledrawer 19 Oct).

Two real households, each with its own admin and session. Household 1 has recipes (one
inside another), tags, lines, an ingredient with a size, and a deleted recipe that can be
undone. From household 2, every recipe endpoint is tried with household 1's ids, reading and
writing, and each answer is a plain "not found". Household 1's rows must be exactly the same
afterwards. (PR 0a has a general isolation test; when it merges this one can share its helpers.)
"""

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import photo_kit as kit
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
    assert ok(neighbour.get(f"{API}/recipes")) == {
        "total": 0,
        "all_recipes": 0,
        "recipes": [],
        "next": None,
    }
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


def test_household_2_cannot_merge_or_split_with_household_1_ingredients(
    kitchen: TestClient, neighbour: TestClient, mine: dict[str, Any]
) -> None:
    ghee = ok(neighbour.post(f"{API}/foods", json={"name": "Ghee"}), 201)["food"]
    ok(neighbour.post(f"{API}/foods/{ghee['id']}/other-names", json={"name": "nei"}), 201)
    their_name = ok(neighbour.get(f"{API}/foods/{ghee['id']}"))["other_names"][0]["id"]
    # Give household 1 an other name and a merge so there is something to split.
    arhar = ok(kitchen.post(f"{API}/foods", json={"name": "Arhar dal"}), 201)["food"]
    ok(kitchen.post(f"{API}/foods/{arhar['id']}/merge", json={"into_id": mine["food_id"]}))
    name_id = ok(kitchen.get(f"{API}/foods/{mine['food_id']}"))["other_names"][0]["id"]
    before = rows_of_household_1(kitchen)
    attempts = [
        ("POST", f"{API}/foods/{ghee['id']}/merge", {"into_id": mine["food_id"]}),
        ("POST", f"{API}/foods/{mine['food_id']}/merge", {"into_id": ghee["id"]}),
        ("POST", f"{API}/foods/{mine['food_id']}/split", {"other_name_id": name_id}),
        ("POST", f"{API}/foods/{ghee['id']}/split", {"other_name_id": name_id}),
        ("POST", f"{API}/foods/{mine['food_id']}/split", {"other_name_id": their_name}),
        ("DELETE", f"{API}/foods/{mine['food_id']}", None),
        ("GET", f"{API}/foods/{mine['food_id']}", None),
    ]
    for method, url, body in attempts:
        response = neighbour.request(method, url, json=body)
        not_found(response)
    assert rows_of_household_1(kitchen) == before
    # Household 1's recipe line is still on its ingredient.
    sambar = ok(kitchen.get(f"{API}/recipes/{mine['recipe_id']}"))
    assert sambar["lines"][0]["food"]["id"] == mine["food_id"]


def test_used_in_counts_and_the_unused_filter_do_not_leak(
    kitchen: TestClient, neighbour: TestClient, mine: dict[str, Any]
) -> None:
    # Household 1 uses its Toor dal in a recipe, and has the recipe-less Arhar dal too.
    ok(kitchen.post(f"{API}/foods", json={"name": "Arhar dal"}), 201)
    toor2 = ok(neighbour.post(f"{API}/foods", json={"name": "Toor dal"}), 201)["food"]
    ok(neighbour.post(f"{API}/foods", json={"name": "Rice"}), 201)
    listed = ok(neighbour.get(f"{API}/foods"))
    assert {f["name"]: f["used_in_recipes"] for f in listed["foods"]} == {
        "Toor dal": 0,
        "Rice": 0,
    }
    assert listed["counts"]["unused"] == 2 and listed["counts"]["all"] == 2
    unused = ok(neighbour.get(f"{API}/foods", params={"filter": "unused"}))
    assert sorted(f["name"] for f in unused["foods"]) == ["Rice", "Toor dal"]
    assert ok(neighbour.get(f"{API}/foods/{toor2['id']}"))["used_in"] == []
    # And household 1's numbers are its own.
    mine_listed = ok(kitchen.get(f"{API}/foods"))
    counts = {f["name"]: f["used_in_recipes"] for f in mine_listed["foods"]}
    assert counts["Toor dal"] == 1 and counts["Arhar dal"] == 0
    assert mine_listed["counts"]["unused"] == 2  # Arhar dal and the made-ahead Sambar powder
    # A recipe in household 2 using its own Toor dal doesn't count towards household 1's.
    make(neighbour, "Dal", lines=[{"words": "dal", "food_id": toor2["id"]}])
    assert ok(kitchen.get(f"{API}/foods/{mine['food_id']}"))["used_in_recipes"] == 1
    assert ok(neighbour.get(f"{API}/foods/{toor2['id']}"))["used_in_recipes"] == 1


# --- Photos (cabledrawer 19 and 20 Oct) -----------------------------------------------------------


@pytest.fixture
def photos_of_1(kitchen: TestClient, mine: dict[str, Any]) -> dict[str, Any]:
    """Household 1's photos: one on Sambar, one uploaded and not saved yet."""
    on_recipe = kit.uploaded(kitchen)
    ok(save(kitchen, mine["sambar"], photo_id=on_recipe["id"]))
    waiting = kit.uploaded(kitchen, kit.png())
    return {"on_recipe": on_recipe, "waiting": waiting}


def files_of_household(kitchen: TestClient, household_id: int) -> list[tuple[str, bytes]]:
    folder = (
        Path(kitchen.app.state.settings.data_dir)  # type: ignore[attr-defined]
        / "photos"
        / str(household_id)
    )
    if not folder.exists():
        return []
    return sorted((p.name, p.read_bytes()) for p in folder.iterdir())


def test_household_2_cannot_fetch_or_delete_household_1s_photos(
    kitchen: TestClient, neighbour: TestClient, photos_of_1: dict[str, Any]
) -> None:
    before = rows_of_household_1(kitchen), files_of_household(kitchen, 1)
    unknown = 999_999
    for photo in photos_of_1.values():
        for url in (photo["url"], photo["list_url"]):
            not_found(neighbour.get(url))
            # Exactly as for an id that doesn't exist.
            assert (
                neighbour.get(url).json()
                == neighbour.get(url.replace(f"/{photo['id']}/", f"/{unknown}/")).json()
            )
        not_found(neighbour.delete(f"{API}/recipes/photos/{photo['id']}"))
        assert (
            neighbour.delete(f"{API}/recipes/photos/{photo['id']}").json()
            == neighbour.delete(f"{API}/recipes/photos/{unknown}").json()
        )
    assert (rows_of_household_1(kitchen), files_of_household(kitchen, 1)) == before
    # Household 1 still sees both.
    for photo in photos_of_1.values():
        assert kitchen.get(photo["url"]).status_code == 200


def test_household_2_cannot_use_household_1s_photos(
    kitchen: TestClient, neighbour: TestClient, mine: dict[str, Any], photos_of_1: dict[str, Any]
) -> None:
    before = rows_of_household_1(kitchen), files_of_household(kitchen, 1)
    own = make(neighbour, "Rasam")
    unknown = {"name": "Rasam", "photo_id": 999_999}
    for photo in photos_of_1.values():
        # Attach to a new recipe, or put on (replace) its own recipe's photo.
        body = {"name": "Rasam", "photo_id": photo["id"]}
        response = neighbour.post(f"{API}/recipes", json=body)
        not_found(response)
        assert response.json() == neighbour.post(f"{API}/recipes", json=unknown).json()
        not_found(save(neighbour, own, photo_id=photo["id"]))
        # Clear or replace household 1's own recipe photo.
        not_found(save(neighbour, mine["sambar"], photo_id=None))
    assert ok(neighbour.get(f"{API}/recipes"))["total"] == 1
    assert (rows_of_household_1(kitchen), files_of_household(kitchen, 1)) == before
    assert files_of_household(kitchen, 2) == []
    sambar = ok(kitchen.get(f"{API}/recipes/{mine['recipe_id']}"))
    assert sambar["photo"] == photos_of_1["on_recipe"]


def test_each_households_photos_are_in_its_own_folder(
    kitchen: TestClient, neighbour: TestClient, photos_of_1: dict[str, Any]
) -> None:
    theirs = kit.uploaded(neighbour)
    root = Path(kitchen.app.state.settings.data_dir) / "photos"  # type: ignore[attr-defined]
    assert {p.name for p in root.iterdir()} == {"1", "2"}
    assert len(files_of_household(kitchen, 1)) == 4
    assert len(files_of_household(kitchen, 2)) == 2
    assert kitchen.get(theirs["url"]).status_code == 404
    assert neighbour.get(theirs["url"]).status_code == 200


def test_the_10_waiting_uploads_are_counted_per_household(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    small = kit.jpeg(40, 30)
    for _ in range(10):
        kit.uploaded(kitchen, small)
    assert kit.upload(kitchen, small).status_code == 409
    # Household 1's ten don't use up household 2's places.
    theirs = [kit.uploaded(neighbour, small) for _ in range(10)]
    assert kit.upload(neighbour, small).status_code == 409
    # And household 2 attaching one frees a place for household 2 only.
    make(neighbour, "Rasam", photo_id=theirs[0]["id"])
    assert kit.upload(kitchen, small).status_code == 409
    kit.uploaded(neighbour, small)


def test_uploads_under_way_are_counted_per_household(
    kitchen: TestClient, neighbour: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Household 1's uploads still being worked on don't take household 2's places."""
    import threading

    from mealwright import photos

    mine, theirs = kit.jpeg(40, 30), kit.jpeg(42, 30)
    gate, started = threading.Event(), threading.Semaphore(0)
    real = photos.clean

    def slow(data: bytes) -> photos.Cleaned:
        if data == mine:  # household 1's are held while they're worked on
            started.release()
            gate.wait(30)
        return real(data)

    monkeypatch.setattr(photos, "clean", slow)
    answers: list[int] = []

    def one() -> None:
        other = TestClient(kitchen.app, base_url="https://testserver")
        other.cookies.update(kitchen.cookies)
        answers.append(kit.upload(other, mine).status_code)

    threads = [threading.Thread(target=one) for _ in range(10)]
    for thread in threads:
        thread.start()
    try:
        for _ in range(10):
            assert started.acquire(timeout=30)
        assert kit.upload(kitchen, mine).status_code == 409  # household 1's 10 are under way
        for _ in range(10):
            kit.uploaded(neighbour, theirs)
        assert kit.upload(neighbour, theirs).status_code == 409
    finally:
        gate.set()
        for thread in threads:
            thread.join(60)
    assert answers == [201] * 10


def test_the_clean_up_only_deletes_each_households_own_old_uploads(
    kitchen: TestClient, neighbour: TestClient, photos_of_1: dict[str, Any]
) -> None:
    from datetime import timedelta

    from sqlalchemy import update

    from mealwright import jobs
    from mealwright.models import RecipePhoto, utcnow

    theirs = kit.uploaded(neighbour)
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(
            update(RecipePhoto)
            .where(RecipePhoto.id == theirs["id"])
            .values(added_at=utcnow() - timedelta(hours=25))
        )
        db.commit()
    before = rows_of_household_1(kitchen), files_of_household(kitchen, 1)
    jobs.purge_removed_ingredients(kitchen.app.state.sessionmaker)  # type: ignore[attr-defined]
    assert (rows_of_household_1(kitchen), files_of_household(kitchen, 1)) == before
    assert files_of_household(kitchen, 2) == []


def test_search_tags_filters_and_stock_hints_never_see_the_other_household(
    kitchen: TestClient, neighbour: TestClient, mine: dict[str, Any]
) -> None:
    # Household 1: Toor dal with another name, stock that goes off today, a tagged recipe.
    ok(kitchen.post(f"{API}/foods/{mine['food_id']}/other-names", json={"name": "thuvaram"}), 201)
    ok(
        kitchen.post(
            f"{API}/stock",
            json={
                "food_id": mine["food_id"],
                "amount": {"amount": 2, "unit": "packet"},
                "use_by": ok(kitchen.get(f"{API}/household"))["today"],
            },
        ),
        201,
    )
    mine_listed = {r["name"]: r for r in ok(kitchen.get(f"{API}/recipes"))["recipes"]}
    assert mine_listed["Sambar"]["use_soon"]["foods"][0]["name"] == "Toor dal"
    before = rows_of_household_1(kitchen)

    # Household 2 searches for everything household 1 has: names, tags, ingredients, other names.
    for q in ["Sambar", "powder", "Quick", "Batch", "Podi", "toor", "dal", "thuvaram", "Old rasam"]:
        found = ok(neighbour.get(f"{API}/recipes", params={"q": q}))
        assert found == {"total": 0, "all_recipes": 0, "recipes": [], "next": None}, q
    for params in [{"tag": "Quick"}, {"tag": "podi"}, {"can_cook_now": "true"}]:
        found = ok(neighbour.get(f"{API}/recipes", params=params))
        assert found["recipes"] == [] and found["total"] == 0, params

    # Household 2 has its own Toor dal and recipe: it finds only its own, with its own stock.
    toor2 = ok(neighbour.post(f"{API}/foods", json={"name": "Toor dal"}), 201)["food"]
    make(
        neighbour,
        "Dal tadka",
        lines=[{"words": "dal", "food_id": toor2["id"], "amount": 100, "unit": "g"}],
    )
    for q in ["toor", "dal", "thuvaram"]:
        found = ok(neighbour.get(f"{API}/recipes", params={"q": q}))
        assert [r["name"] for r in found["recipes"]] == (
            ["Dal tadka"] if q != "thuvaram" else []
        ), q
    theirs = ok(neighbour.get(f"{API}/recipes"))["recipes"][0]
    assert theirs["stock"] == {
        "counted": 1,
        "missing": 1,
        "can_cook_now": False,
    }  # no stock of its own
    assert theirs["use_soon"] is None
    assert ok(neighbour.get(f"{API}/recipes", params={"can_cook_now": "true"}))["total"] == 0

    # And household 1's answers are unchanged by any of it.
    assert rows_of_household_1(kitchen) == before
    assert ok(kitchen.get(f"{API}/recipes", params={"q": "thuvaram"}))["total"] == 1
    assert [
        r["name"] for r in ok(kitchen.get(f"{API}/recipes", params={"q": "dal tadka"}))["recipes"]
    ] == []
    assert ok(kitchen.get(f"{API}/recipes"))["all_recipes"] == 2
