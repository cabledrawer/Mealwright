"""Ingredients that recipes use (cabledrawer 19 Oct, question 30): merging moves the recipe lines
to the kept ingredient, and "made its own ingredient again" puts them back; removing keeps
each line's words but unlinks it ("not linked"), and Undo relinks it; "used in N recipes"."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok, person
from test_recipes import food, make, save

from mealwright.models import Food, Household, RecipeLine, utcnow

API = "/api/v1"


def current(client: TestClient, recipe: dict[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] = ok(client.get(f"{API}/recipes/{recipe['id']}"))
    return found


def links(client: TestClient, recipe: dict[str, Any]) -> list[tuple[str, str | None, str]]:
    """(words, linked ingredient's name or None, link) for each ingredient line."""
    return [
        (line["words"], line["food"]["name"] if line["food"] else None, line["link"])
        for line in current(client, recipe)["lines"]
        if line["kind"] == "ingredient"
    ]


def two_dals(kitchen: TestClient) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    toor = food(kitchen, "Toor dal")
    arhar = food(kitchen, "Arhar dal")
    sambar = make(
        kitchen,
        "Sambar",
        lines=[
            {"words": "thuvaram paruppu", "amount": 200, "unit": "g", "food_id": toor["id"]},
            {"words": "arhar", "amount": 1, "unit": "cup", "food_id": arhar["id"]},
            {"words": "salt"},
        ],
    )
    return toor, arhar, sambar


# --- Used in N recipes -------------------------------------------------------------------------


def test_an_ingredient_says_how_many_recipes_use_it(kitchen: TestClient) -> None:
    toor = food(kitchen, "Toor dal")
    food(kitchen, "Rice")
    assert ok(kitchen.get(f"{API}/foods/{toor['id']}"))["used_in_recipes"] == 0
    a = make(kitchen, "Sambar", lines=[{"words": "dal", "food_id": toor["id"]}] * 1)
    b = make(
        kitchen,
        "Dal fry",
        lines=[
            {"words": "dal", "food_id": toor["id"]},
            {"words": "more dal", "food_id": toor["id"]},
        ],
    )
    editor = ok(kitchen.get(f"{API}/foods/{toor['id']}"))
    assert editor["used_in_recipes"] == 2  # two recipes, even though Dal fry has two lines
    assert editor["used_in"] == [
        {"id": b["id"], "name": "Dal fry"},
        {"id": a["id"], "name": "Sambar"},
    ]
    listed = ok(kitchen.get(f"{API}/foods"))
    assert {f["name"]: f["used_in_recipes"] for f in listed["foods"]} == {"Rice": 0, "Toor dal": 2}
    # A deleted recipe no longer counts, and counts again after Undo.
    change = ok(kitchen.delete(f"{API}/recipes/{b['id']}"))["change"]
    assert ok(kitchen.get(f"{API}/foods/{toor['id']}"))["used_in_recipes"] == 1
    ok(kitchen.post(f"{API}/changes/{change['id']}/undo"))
    assert ok(kitchen.get(f"{API}/foods/{toor['id']}"))["used_in_recipes"] == 2


def test_not_in_any_recipe_filter(kitchen: TestClient) -> None:
    toor = food(kitchen, "Toor dal")
    food(kitchen, "Rice")
    make(kitchen, "Sambar", lines=[{"words": "dal", "food_id": toor["id"]}])
    unused = ok(kitchen.get(f"{API}/foods", params={"filter": "unused"}))
    assert [f["name"] for f in unused["foods"]] == ["Rice"]
    assert unused["counts"]["unused"] == 1 and unused["counts"]["all"] == 2


# --- Merging -----------------------------------------------------------------------------------


def test_merging_moves_the_recipe_lines_to_the_kept_ingredient(kitchen: TestClient) -> None:
    toor, arhar, sambar = two_dals(kitchen)
    before = current(kitchen, sambar)
    ok(kitchen.post(f"{API}/foods/{arhar['id']}/merge", json={"into_id": toor["id"]}))
    assert links(kitchen, sambar) == [
        ("thuvaram paruppu", "Toor dal", "ingredient"),
        ("arhar", "Toor dal", "ingredient"),  # the words stay as typed
        ("salt", None, "none"),
    ]
    after = current(kitchen, sambar)
    assert [line["id"] for line in after["lines"]] == [line["id"] for line in before["lines"]]
    assert after["version"] == before["version"] + 1  # see "Links changed behind the editor"
    assert ok(kitchen.get(f"{API}/foods/{toor['id']}"))["used_in_recipes"] == 1


def test_merging_undone_puts_the_lines_back(kitchen: TestClient) -> None:
    toor, arhar, sambar = two_dals(kitchen)
    merged = ok(kitchen.post(f"{API}/foods/{arhar['id']}/merge", json={"into_id": toor["id"]}))
    undone = ok(kitchen.post(f"{API}/changes/{merged['change']['id']}/undo"))
    assert undone["result"] == "done"
    assert links(kitchen, sambar)[:2] == [
        ("thuvaram paruppu", "Toor dal", "ingredient"),
        ("arhar", "Arhar dal", "ingredient"),
    ]


def test_made_its_own_ingredient_again_puts_the_lines_back(kitchen: TestClient) -> None:
    toor, arhar, sambar = two_dals(kitchen)
    ok(kitchen.post(f"{API}/foods/{arhar['id']}/merge", json={"into_id": toor["id"]}))
    name_id = next(n["id"] for n in ok(kitchen.get(f"{API}/foods/{toor['id']}"))["other_names"])
    split = ok(
        kitchen.post(f"{API}/foods/{toor['id']}/split", json={"other_name_id": name_id}), 201
    )
    assert split["food"]["name"] == "Arhar dal"
    assert links(kitchen, sambar)[:2] == [
        ("thuvaram paruppu", "Toor dal", "ingredient"),
        ("arhar", "Arhar dal", "ingredient"),
    ]
    # And that can be undone: the line goes back to the kept ingredient.
    ok(kitchen.post(f"{API}/changes/{split['change']['id']}/undo"))
    assert links(kitchen, sambar)[1] == ("arhar", "Toor dal", "ingredient")


def test_a_line_that_was_not_on_the_merged_ingredient_stays_put_on_split(
    kitchen: TestClient,
) -> None:
    toor, arhar, _sambar = two_dals(kitchen)
    ok(kitchen.post(f"{API}/foods/{arhar['id']}/merge", json={"into_id": toor["id"]}))
    other = make(kitchen, "Dal fry", lines=[{"words": "dal", "food_id": toor["id"]}])
    name_id = ok(kitchen.get(f"{API}/foods/{toor['id']}"))["other_names"][0]["id"]
    ok(kitchen.post(f"{API}/foods/{toor['id']}/split", json={"other_name_id": name_id}), 201)
    assert links(kitchen, other) == [("dal", "Toor dal", "ingredient")]


def test_merging_keeps_a_lines_size_even_when_the_same_size_exists_twice(
    kitchen: TestClient,
) -> None:
    toor = food(kitchen, "Toor dal")
    arhar = food(kitchen, "Arhar dal")
    sizes = {}
    for name, item in (("toor", toor), ("arhar", arhar)):
        made = ok(
            kitchen.post(f"{API}/foods/{item['id']}/sizes", json={"name": "packet", "amount": 500}),
            201,
        )
        sizes[name] = made["food"]["sizes"][0]["id"]
    sambar = make(
        kitchen,
        "Sambar",
        lines=[
            {
                "words": "packet of arhar",
                "amount": 2,
                "size_id": sizes["arhar"],
                "food_id": arhar["id"],
            }
        ],
    )
    merged = ok(kitchen.post(f"{API}/foods/{arhar['id']}/merge", json={"into_id": toor["id"]}))
    line = current(kitchen, sambar)["lines"][0]
    assert line["food"]["name"] == "Toor dal"
    assert line["size"]["id"] == sizes["toor"]  # the twin size it joined; "2 packets" stays
    ok(kitchen.post(f"{API}/changes/{merged['change']['id']}/undo"))
    line = current(kitchen, sambar)["lines"][0]
    assert line["food"]["name"] == "Arhar dal" and line["size"]["id"] == sizes["arhar"]


def test_merging_the_ingredient_of_a_recipe_that_is_made_ahead_follows_it(
    kitchen: TestClient,
) -> None:
    batter = make(kitchen, "Dosa batter", made_ahead=True)
    kept = food(kitchen, "Batter")
    merged = ok(
        kitchen.post(f"{API}/foods/{batter['homemade']['id']}/merge", json={"into_id": kept["id"]})
    )
    assert current(kitchen, batter)["homemade"] == {"id": kept["id"], "name": "Batter"}
    ok(kitchen.post(f"{API}/changes/{merged['change']['id']}/undo"))
    assert current(kitchen, batter)["homemade"]["name"] == "Dosa batter"


# --- Removing ----------------------------------------------------------------------------------


def test_removing_keeps_the_words_and_unlinks_the_lines(kitchen: TestClient) -> None:
    toor, _arhar, sambar = two_dals(kitchen)
    version = current(kitchen, sambar)["version"]
    removed = ok(kitchen.delete(f"{API}/foods/{toor['id']}"))
    assert removed["change"]["summary"] == "Removed Toor dal from Ingredients"
    assert links(kitchen, sambar) == [
        ("thuvaram paruppu", None, "none"),
        ("arhar", "Arhar dal", "ingredient"),
        ("salt", None, "none"),
    ]
    line = current(kitchen, sambar)["lines"][0]
    assert (line["amount"], line["unit"]) == (200, "g")  # the amount stays
    assert current(kitchen, sambar)["version"] == version + 1


def test_removing_can_be_undone_and_the_lines_are_linked_again(kitchen: TestClient) -> None:
    toor, _arhar, sambar = two_dals(kitchen)
    removed = ok(kitchen.delete(f"{API}/foods/{toor['id']}"))
    undone = ok(kitchen.post(f"{API}/changes/{removed['change']['id']}/undo"))
    assert undone["result"] == "done"
    assert links(kitchen, sambar)[0] == ("thuvaram paruppu", "Toor dal", "ingredient")


def test_undo_of_a_removal_leaves_a_line_that_was_linked_to_something_else(
    kitchen: TestClient,
) -> None:
    toor, arhar, sambar = two_dals(kitchen)
    removed = ok(kitchen.delete(f"{API}/foods/{toor['id']}"))
    recipe = current(kitchen, sambar)
    first = recipe["lines"][0]
    ok(
        save(
            kitchen,
            recipe,
            lines=[
                {"id": first["id"], "words": first["words"], "food_id": arhar["id"]},
                *[{"id": line["id"], "words": line["words"]} for line in recipe["lines"][1:]],
            ],
        )
    )
    undone = ok(kitchen.post(f"{API}/changes/{removed['change']['id']}/undo"))
    assert undone["result"] == "partly"
    assert links(kitchen, sambar)[0] == ("thuvaram paruppu", "Arhar dal", "ingredient")


def test_undo_of_a_removal_skips_a_line_taken_out_of_the_recipe(kitchen: TestClient) -> None:
    toor, _arhar, sambar = two_dals(kitchen)
    removed = ok(kitchen.delete(f"{API}/foods/{toor['id']}"))
    recipe = current(kitchen, sambar)
    ok(save(kitchen, recipe, lines=[{"id": recipe["lines"][2]["id"], "words": "salt"}]))
    undone = ok(kitchen.post(f"{API}/changes/{removed['change']['id']}/undo"))
    assert undone["result"] == "partly"  # the ingredient is back; the line it had is gone
    assert ok(kitchen.get(f"{API}/foods/{toor['id']}"))["name"] == "Toor dal"
    assert links(kitchen, sambar) == [("salt", None, "none")]


def test_a_removed_ingredient_deleted_for_good_leaves_lines_with_their_words(
    kitchen: TestClient,
) -> None:
    from mealwright.history import purge_removed

    toor, _arhar, sambar = two_dals(kitchen)
    ok(kitchen.delete(f"{API}/foods/{toor['id']}"))
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.get(Food, toor["id"]).removed_at = utcnow() - timedelta(days=8)  # type: ignore[union-attr]
        db.commit()
        assert purge_removed(db, db.get(Household, 1)) == 1  # type: ignore[arg-type]
        assert db.scalars(select(Food).where(Food.id == toor["id"])).all() == []
        assert db.scalars(select(RecipeLine).where(RecipeLine.food_id == toor["id"])).all() == []
    assert links(kitchen, sambar)[0] == ("thuvaram paruppu", None, "none")


def test_an_ingredient_a_recipe_makes_itself_cannot_be_removed(kitchen: TestClient) -> None:
    batter = make(kitchen, "Dosa batter", made_ahead=True)
    response = kitchen.delete(f"{API}/foods/{batter['homemade']['id']}")
    assert response.status_code == 409 and response.json()["code"] == "in_use"
    assert response.json()["detail"] == (
        "Dosa batter is the made-ahead ingredient of Dosa batter. "
        "Turn off Made ahead on that recipe first."
    )
    # Once Made ahead is off, it can go.
    ok(save(kitchen, batter, made_ahead=False))
    ok(kitchen.delete(f"{API}/foods/{batter['homemade']['id']}"))


def test_a_removed_ingredient_cannot_be_picked_for_a_line(kitchen: TestClient) -> None:
    toor, _arhar, sambar = two_dals(kitchen)
    ok(kitchen.delete(f"{API}/foods/{toor['id']}"))
    recipe = current(kitchen, sambar)
    response = save(
        kitchen,
        recipe,
        lines=[{"id": recipe["lines"][0]["id"], "words": "x", "food_id": toor["id"]}],
    )
    assert response.status_code == 404 and response.json()["line"] == 0


def test_a_merged_away_id_still_links_to_the_ingredient_it_went_into(kitchen: TestClient) -> None:
    toor, arhar, sambar = two_dals(kitchen)
    ok(kitchen.post(f"{API}/foods/{arhar['id']}/merge", json={"into_id": toor["id"]}))
    recipe = current(kitchen, sambar)
    saved = ok(
        save(
            kitchen,
            recipe,
            lines=[{"words": "old tab", "amount": 1, "unit": "cup", "food_id": arhar["id"]}],
        )
    )
    assert saved["lines"][0]["food"]["name"] == "Toor dal"


# --- Links changed behind the editor ------------------------------------------------------------


def test_a_merge_stops_an_editor_that_was_open_on_the_recipe(kitchen: TestClient) -> None:
    """Tess opens Sambar. Wren merges two dals. Tess's save would write the old
    links back, so it is stopped and says it was Wren."""
    wren = person(kitchen)
    toor, arhar, sambar = two_dals(kitchen)
    opened = current(kitchen, sambar)  # Tess's editor holds this version
    ok(wren.post(f"{API}/foods/{arhar['id']}/merge", json={"into_id": toor["id"]}))
    stopped = save(kitchen, opened, name="Sambar 2")
    assert stopped.status_code == 409, stopped.text
    problem = stopped.json()
    assert problem["code"] == "recipe_changed"
    assert problem["detail"] == "Wren changed this recipe after you opened it."
    assert problem["version"] == opened["version"] + 1
    assert links(kitchen, sambar)[1] == ("arhar", "Toor dal", "ingredient")  # the merge stands


def test_removing_splitting_undoing_and_deleting_also_move_the_version(kitchen: TestClient) -> None:
    toor, arhar, sambar = two_dals(kitchen)
    powder = make(kitchen, "Sambar powder")
    ok(
        save(
            kitchen,
            current(kitchen, sambar),
            lines=[
                {"id": line["id"], "words": line["words"], "food_id": line["food"]["id"]}
                for line in current(kitchen, sambar)["lines"]
                if line["food"]
            ]
            + [{"words": "powder", "recipe_id": powder["id"]}],
        )
    )
    version = current(kitchen, sambar)["version"]

    def bumped() -> bool:
        nonlocal version
        now = current(kitchen, sambar)["version"]
        moved, version = now > version, now
        return moved

    merged = ok(kitchen.post(f"{API}/foods/{arhar['id']}/merge", json={"into_id": toor["id"]}))
    assert bumped()
    ok(kitchen.post(f"{API}/changes/{merged['change']['id']}/undo"))
    assert bumped()  # undoing the merge moves the lines again
    removed = ok(kitchen.delete(f"{API}/foods/{arhar['id']}"))
    assert bumped()
    ok(kitchen.post(f"{API}/changes/{removed['change']['id']}/undo"))
    assert bumped()
    gone = ok(kitchen.delete(f"{API}/recipes/{powder['id']}"))["change"]
    assert bumped()  # its line now says "recipe removed"
    ok(kitchen.post(f"{API}/changes/{gone['id']}/undo"))
    assert bumped()
    # Splitting: merge, then make it its own ingredient again.
    ok(kitchen.post(f"{API}/foods/{arhar['id']}/merge", json={"into_id": toor["id"]}))
    assert bumped()
    name_id = ok(kitchen.get(f"{API}/foods/{toor['id']}"))["other_names"][0]["id"]
    ok(kitchen.post(f"{API}/foods/{toor['id']}/split", json={"other_name_id": name_id}), 201)
    assert bumped()
    # A recipe that doesn't use any of them is left alone.
    other = make(kitchen, "Plain rice")
    ok(kitchen.delete(f"{API}/foods/{toor['id']}"))
    assert current(kitchen, other)["version"] == 1


def test_a_recipe_deleted_for_good_moves_the_version_of_the_recipes_that_used_it(
    kitchen: TestClient,
) -> None:
    from mealwright.recipes import purge_removed_recipes

    powder = make(kitchen, "Sambar powder")
    sambar = make(kitchen, "Sambar", lines=[{"words": "powder", "recipe_id": powder["id"]}])
    ok(kitchen.delete(f"{API}/recipes/{powder['id']}"))
    version = current(kitchen, sambar)["version"]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        from mealwright.models import Recipe

        db.get(Recipe, powder["id"]).removed_at = utcnow() - timedelta(days=8)  # type: ignore[union-attr]
        db.commit()
        assert purge_removed_recipes(db, db.get(Household, 1)) == 1  # type: ignore[arg-type]
    now = current(kitchen, sambar)
    assert now["version"] == version + 1 and now["lines"][0]["link"] == "none"
    assert save(kitchen, {**now, "version": version}).status_code == 409
