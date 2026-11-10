"""Managing tags (cabledrawer 9 Nov): rename, and merge into another tag with Undo."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok

from mealwright.models import RecipeTag, Tag

API = "/api/v1"


def make(client: TestClient, name: str, tags: list[str]) -> dict[str, Any]:
    created: dict[str, Any] = ok(
        client.post(f"{API}/recipes", json={"name": name, "tags": tags}), 201
    )
    return created


def tag_ids(client: TestClient) -> dict[str, int]:
    return {t["name"]: t["id"] for t in ok(client.get(f"{API}/recipes/tags"))["tags"]}


def tags_of(client: TestClient, recipe: dict[str, Any]) -> list[str]:
    found: list[str] = ok(client.get(f"{API}/recipes/{recipe['id']}"))["tags"]
    return found


@pytest.fixture
def setup(kitchen: TestClient) -> dict[str, Any]:
    a = make(kitchen, "Sambar", ["South Indian", "Quick"])
    b = make(kitchen, "Rasam", ["south-indian"])
    c = make(kitchen, "Kootu", ["South Indian", "south-indian"])  # both
    return {"a": a, "b": b, "c": c}


def test_rename_changes_the_tag_on_every_recipe(kitchen: TestClient, setup: dict[str, Any]) -> None:
    ids = tag_ids(kitchen)
    done = ok(kitchen.patch(f"{API}/recipes/tags/{ids['Quick']}", json={"name": "  Fast  "}))
    assert done == {"id": ids["Quick"], "name": "Fast", "recipes": 1}
    assert tags_of(kitchen, setup["a"]) == ["Fast", "South Indian"]
    # Not a change in Recent changes (as a shop's rename isn't).
    kinds = [c["kind"] for c in ok(kitchen.get(f"{API}/changes"))["changes"]]
    assert "tags_merged" not in kinds and "undo" not in kinds


def test_rename_stops_an_editor_that_was_open(kitchen: TestClient, setup: dict[str, Any]) -> None:
    before = setup["a"]["version"]
    ids = tag_ids(kitchen)
    ok(kitchen.patch(f"{API}/recipes/tags/{ids['Quick']}", json={"name": "Fast"}))
    assert ok(kitchen.get(f"{API}/recipes/{setup['a']['id']}"))["version"] == before + 1


def test_rename_to_a_name_that_exists_is_refused_and_names_the_other(
    kitchen: TestClient, setup: dict[str, Any]
) -> None:
    ids = tag_ids(kitchen)
    refused = kitchen.patch(
        f"{API}/recipes/tags/{ids['south-indian']}", json={"name": "south indian"}
    )
    assert refused.status_code == 409
    body = refused.json()
    assert body["code"] == "tag_exists" and body["tag"] == {
        "id": ids["South Indian"],
        "name": "South Indian",
    }
    # Renaming a tag to its own name in another case is fine.
    ok(kitchen.patch(f"{API}/recipes/tags/{ids['Quick']}", json={"name": "QUICK"}))


@pytest.mark.parametrize("name", ["", "   ", "x" * 41, "tab\there", "line\nbreak"])
def test_rename_keeps_the_tag_limits(kitchen: TestClient, setup: dict[str, Any], name: str) -> None:
    ids = tag_ids(kitchen)
    assert (
        kitchen.patch(f"{API}/recipes/tags/{ids['Quick']}", json={"name": name}).status_code == 422
    )


def test_merge_gives_the_recipes_the_other_tag_and_keeps_one_when_both(
    kitchen: TestClient, setup: dict[str, Any]
) -> None:
    ids = tag_ids(kitchen)
    merged = ok(
        kitchen.post(
            f"{API}/recipes/tags/{ids['south-indian']}/merge", json={"into": ids["South Indian"]}
        )
    )
    assert merged["into"] == {"id": ids["South Indian"], "name": "South Indian", "recipes": 3}
    assert merged["change"]["summary"] == "Merged tag south-indian into South Indian"
    assert merged["change"]["can_undo"] is True
    assert tags_of(kitchen, setup["b"]) == ["South Indian"]
    assert tags_of(kitchen, setup["c"]) == ["South Indian"]
    assert set(tag_ids(kitchen)) == {"South Indian", "Quick"}
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert sorted(t.name for t in db.scalars(select(Tag))) == ["Quick", "South Indian"]
    # It is in Recent changes.
    top = ok(kitchen.get(f"{API}/changes", params={"limit": 1}))["changes"][0]
    assert top["id"] == merged["change"]["id"]


def test_undo_brings_the_tag_back_on_exactly_the_recipes_that_had_it(
    kitchen: TestClient, setup: dict[str, Any]
) -> None:
    ids = tag_ids(kitchen)
    merged = ok(
        kitchen.post(
            f"{API}/recipes/tags/{ids['south-indian']}/merge", json={"into": ids["South Indian"]}
        )
    )
    undone = ok(kitchen.post(f"{API}/changes/{merged['change']['id']}/undo"))
    assert undone["result"] == "done"
    assert tags_of(kitchen, setup["a"]) == ["Quick", "South Indian"]  # never had it
    assert tags_of(kitchen, setup["b"]) == ["south-indian"]  # only the other, gained here: gone
    assert tags_of(kitchen, setup["c"]) == ["South Indian", "south-indian"]  # had both: both
    assert tag_ids(kitchen) == {**ids}
    again = kitchen.post(f"{API}/changes/{merged['change']['id']}/undo")
    assert again.status_code == 409 and again.json()["code"] == "already_undone"


def test_undo_is_refused_while_a_tag_with_the_old_name_exists(
    kitchen: TestClient, setup: dict[str, Any]
) -> None:
    ids = tag_ids(kitchen)
    merged = ok(
        kitchen.post(
            f"{API}/recipes/tags/{ids['south-indian']}/merge", json={"into": ids["South Indian"]}
        )
    )
    make(kitchen, "New", ["South-Indian"])
    refused = kitchen.post(f"{API}/changes/{merged['change']['id']}/undo")
    assert refused.status_code == 409 and refused.json()["code"] == "tag_exists"


def test_merge_into_itself_or_an_unknown_tag_is_refused(
    kitchen: TestClient, setup: dict[str, Any]
) -> None:
    ids = tag_ids(kitchen)
    same = kitchen.post(f"{API}/recipes/tags/{ids['Quick']}/merge", json={"into": ids["Quick"]})
    assert same.status_code == 422
    assert (
        kitchen.post(f"{API}/recipes/tags/{ids['Quick']}/merge", json={"into": 99999}).status_code
        == 404
    )
    assert (
        kitchen.post(f"{API}/recipes/tags/99999/merge", json={"into": ids["Quick"]}).status_code
        == 404
    )


def test_a_retried_merge_merges_once(kitchen: TestClient, setup: dict[str, Any]) -> None:
    ids = tag_ids(kitchen)
    url = f"{API}/recipes/tags/{ids['south-indian']}/merge"
    headers = {"Idempotency-Key": "merge-1"}
    first = ok(kitchen.post(url, json={"into": ids["South Indian"]}, headers=headers))
    second = ok(kitchen.post(url, json={"into": ids["South Indian"]}, headers=headers))
    assert second["change"]["id"] == first["change"]["id"]
    assert second["into"]["name"] == "South Indian"


def test_a_deleted_recipe_keeps_its_link_through_a_merge_and_undo(
    kitchen: TestClient, setup: dict[str, Any]
) -> None:
    ids = tag_ids(kitchen)
    ok(kitchen.delete(f"{API}/recipes/{setup['b']['id']}"))
    ids = tag_ids(kitchen)  # south-indian still has Kootu
    merged = ok(
        kitchen.post(
            f"{API}/recipes/tags/{ids['south-indian']}/merge", json={"into": ids["South Indian"]}
        )
    )
    assert merged["into"]["recipes"] == 2  # the deleted recipe isn't counted
    ok(kitchen.post(f"{API}/changes/{merged['change']['id']}/undo"))
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        linked = {(r.recipe_id, r.tag_id) for r in db.scalars(select(RecipeTag))}
    assert (setup["b"]["id"], ids["south-indian"]) in linked
