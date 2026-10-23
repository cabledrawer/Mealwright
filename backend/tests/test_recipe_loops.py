"""Recipes inside recipes: any depth, but never a loop (cabledrawer 19 Oct, questions 19 and 20).
The server names the chain in the error, tells the editor which recipes it can't pick, and
checks again on every save."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sync_kit import ok
from test_recipes import make, save

API = "/api/v1"
CANT = "can\u2019t"


def uses(client: TestClient, recipe: dict[str, Any], *others: dict[str, Any]) -> Any:
    """Save `recipe` so that its ingredients are exactly these other recipes."""
    lines = [{"recipe_id": other["id"], "amount": 1, "unit": "tbsp"} for other in others]
    return save(client, recipe, lines=lines)


def current(client: TestClient, recipe: dict[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] = ok(client.get(f"{API}/recipes/{recipe['id']}"))
    return found


def test_a_recipe_can_use_another_recipe_and_it_is_marked_as_one(kitchen: TestClient) -> None:
    powder = make(kitchen, "Sambar powder")
    sambar = make(kitchen, "Sambar")
    saved = ok(uses(kitchen, sambar, powder))
    line = saved["lines"][0]
    assert line["link"] == "recipe" and line["recipe"] == {
        "id": powder["id"],
        "name": "Sambar powder",
    }
    assert line["food"] is None and (line["amount"], line["unit"]) == (1, "tbsp")
    assert current(kitchen, powder)["used_by"] == [{"id": sambar["id"], "name": "Sambar"}]


def test_any_depth_is_fine(kitchen: TestClient) -> None:
    masala = make(kitchen, "Masala")
    powder = make(kitchen, "Sambar powder")
    sambar = make(kitchen, "Sambar")
    lunch = make(kitchen, "Lunch")
    ok(uses(kitchen, powder, masala))
    ok(uses(kitchen, sambar, powder))
    ok(uses(kitchen, lunch, sambar))
    assert [r["name"] for r in current(kitchen, masala)["used_by"]] == ["Sambar powder"]


def test_a_recipe_cannot_use_itself(kitchen: TestClient) -> None:
    sambar = make(kitchen, "Sambar")
    response = uses(kitchen, sambar, sambar)
    assert response.status_code == 422
    problem = response.json()
    assert problem["code"] == "recipe_self" and problem["line"] == 0
    assert problem["detail"] == f"A recipe {CANT} use itself."
    assert current(kitchen, sambar)["version"] == 1  # nothing was saved


def test_a_two_step_loop_names_the_chain(kitchen: TestClient) -> None:
    powder = make(kitchen, "Sambar powder")
    sambar = make(kitchen, "Sambar")
    ok(uses(kitchen, sambar, powder))
    response = uses(kitchen, powder, sambar)
    assert response.status_code == 409
    problem = response.json()
    assert problem["code"] == "recipe_loop"
    assert problem["detail"] == (
        f"Sambar powder {CANT} use Sambar, because Sambar uses Sambar powder."
    )
    assert problem["chain"] == ["Sambar", "Sambar powder"]
    assert problem["line"] == 0 and problem["recipe_id"] == sambar["id"]
    assert current(kitchen, powder)["lines"] == []


def test_a_three_step_loop_says_which_uses(kitchen: TestClient) -> None:
    powder = make(kitchen, "Sambar powder")
    rasam = make(kitchen, "Rasam powder")
    sambar = make(kitchen, "Sambar")
    ok(uses(kitchen, sambar, rasam))  # Sambar uses Rasam powder
    ok(uses(kitchen, rasam, powder))  # Rasam powder uses Sambar powder
    response = uses(kitchen, powder, sambar)  # Sambar powder uses Sambar: a loop
    assert response.status_code == 409
    assert response.json()["detail"] == (
        f"Sambar powder {CANT} use Sambar, "
        "because Sambar uses Rasam powder, which uses Sambar powder."
    )
    assert response.json()["chain"] == ["Sambar", "Rasam powder", "Sambar powder"]


def test_a_longer_loop_keeps_adding_which_uses(kitchen: TestClient) -> None:
    a, b, c, d = (make(kitchen, name) for name in ["Aa", "Bb", "Cc", "Dd"])
    ok(uses(kitchen, a, b))
    ok(uses(kitchen, b, c))
    ok(uses(kitchen, c, d))
    response = uses(kitchen, d, a)
    assert response.json()["detail"] == (
        f"Dd {CANT} use Aa, because Aa uses Bb, which uses Cc, which uses Dd."
    )


def test_the_picker_greys_out_what_it_cannot_use_before_save(kitchen: TestClient) -> None:
    powder = make(kitchen, "Sambar powder")
    rasam = make(kitchen, "Rasam powder")
    sambar = make(kitchen, "Sambar")
    other = make(kitchen, "Plain rice")
    ok(uses(kitchen, sambar, rasam))
    ok(uses(kitchen, rasam, powder))
    blocked = ok(kitchen.get(f"{API}/recipes/{powder['id']}/cannot-use"))["recipes"]
    assert [(b["name"], b["reason"]) for b in blocked] == [
        ("Sambar powder", f"A recipe {CANT} use itself."),
        (
            "Rasam powder",
            f"Sambar powder {CANT} use Rasam powder, because Rasam powder uses Sambar powder.",
        ),
        (
            "Sambar",
            f"Sambar powder {CANT} use Sambar, "
            "because Sambar uses Rasam powder, which uses Sambar powder.",
        ),
    ]
    assert other["id"] not in {b["id"] for b in blocked}
    assert blocked[2]["chain"] == ["Sambar", "Rasam powder", "Sambar powder"]
    # Every recipe it lists is refused by the save, and the ones it doesn't list aren't.
    for entry in blocked:
        assert uses(kitchen, powder, {"id": entry["id"]}).status_code in (409, 422)
    assert uses(kitchen, powder, other).status_code == 200


def test_a_recipe_nobody_uses_blocks_only_itself(kitchen: TestClient) -> None:
    make(kitchen, "Other")
    lonely = make(kitchen, "Lonely")
    blocked = ok(kitchen.get(f"{API}/recipes/{lonely['id']}/cannot-use"))["recipes"]
    assert [b["name"] for b in blocked] == ["Lonely"]


def test_a_loop_made_by_editing_the_inner_recipe_is_caught(kitchen: TestClient) -> None:
    """Dosa uses Batter. Someone edits Batter (in another window, where Dosa wasn't picked
    yet) to use Dosa: the server checks again on that save."""
    batter = make(kitchen, "Dosa batter")
    dosa = make(kitchen, "Dosa")
    stale_batter_editor = batter  # opened before Dosa used it
    ok(uses(kitchen, dosa, batter))
    # The editor opened on Batter before the change doesn't know Dosa uses it.
    now = current(kitchen, batter)
    assert stale_batter_editor["version"] == now["version"]  # Batter itself didn't change
    response = uses(kitchen, now, dosa)
    assert response.status_code == 409 and response.json()["code"] == "recipe_loop"
    assert response.json()["detail"] == (
        f"Dosa batter {CANT} use Dosa, because Dosa uses Dosa batter."
    )


def test_a_loop_made_by_editing_the_outer_recipe_into_a_deep_chain(kitchen: TestClient) -> None:
    a, b, c = (make(kitchen, name) for name in ["Aa", "Bb", "Cc"])
    ok(uses(kitchen, b, c))
    ok(uses(kitchen, c, a))
    # Aa wants Bb: Aa -> Bb -> Cc -> Aa.
    response = uses(kitchen, a, b)
    assert response.status_code == 409
    assert response.json()["chain"] == ["Bb", "Cc", "Aa"]


def test_two_lines_may_use_the_same_recipe_and_other_lines_are_checked_by_number(
    kitchen: TestClient,
) -> None:
    powder = make(kitchen, "Sambar powder")
    sambar = make(kitchen, "Sambar")
    ok(uses(kitchen, sambar, powder))
    response = save(
        kitchen,
        powder,
        lines=[{"words": "salt"}, {"words": "x", "recipe_id": sambar["id"]}],
    )
    assert response.status_code == 409 and response.json()["line"] == 1


def test_a_deleted_recipe_is_not_in_the_way(kitchen: TestClient) -> None:
    powder = make(kitchen, "Sambar powder")
    sambar = make(kitchen, "Sambar")
    ok(uses(kitchen, sambar, powder))
    ok(kitchen.delete(f"{API}/recipes/{sambar['id']}"))
    # Sambar is deleted, so Sambar powder can't pick it (it isn't there) …
    assert uses(kitchen, powder, sambar).status_code == 404
    assert ok(kitchen.get(f"{API}/recipes/{powder['id']}/cannot-use"))["recipes"][0]["name"] == (
        "Sambar powder"
    )
    assert len(ok(kitchen.get(f"{API}/recipes/{powder['id']}/cannot-use"))["recipes"]) == 1


def test_deleting_a_recipe_that_another_uses_keeps_the_line_and_undo_relinks_it(
    kitchen: TestClient,
) -> None:
    powder = make(kitchen, "Sambar powder")
    sambar = make(kitchen, "Sambar")
    ok(uses(kitchen, sambar, powder))
    change = ok(kitchen.delete(f"{API}/recipes/{powder['id']}"))["change"]
    line = current(kitchen, sambar)["lines"][0]
    assert line["words"] == "Sambar powder" and line["link"] == "recipe_removed"
    assert line["food"] is None and (line["amount"], line["unit"]) == (1, "tbsp")
    assert line["recipe"]["id"] == powder["id"]  # sent back as it is, the link is kept
    # The recipe that was left with a "recipe removed" line can still be saved as it is.
    saved = ok(save(kitchen, current(kitchen, sambar), name="Sambar 2"))
    assert saved["lines"][0]["link"] == "recipe_removed"
    # But a removed recipe can't be picked fresh.
    fresh = save(
        kitchen,
        saved,
        lines=[
            *[
                {
                    "id": saved["lines"][0]["id"],
                    "words": "Sambar powder",
                    "recipe_id": powder["id"],
                },
                {"words": "again", "recipe_id": powder["id"]},
            ]
        ],
    )
    assert fresh.status_code == 404 and fresh.json()["line"] == 1
    ok(kitchen.post(f"{API}/changes/{change['id']}/undo"))
    back = current(kitchen, sambar)["lines"][0]
    assert back["link"] == "recipe" and back["recipe"]["name"] == "Sambar powder"
    assert current(kitchen, powder)["used_by"] == [{"id": sambar["id"], "name": "Sambar 2"}]


def test_a_recipe_deleted_for_good_leaves_the_words_and_no_link(kitchen: TestClient) -> None:
    from datetime import timedelta

    from mealwright.models import Household, Recipe, utcnow
    from mealwright.recipes import purge_removed_recipes

    powder = make(kitchen, "Sambar powder")
    sambar = make(kitchen, "Sambar")
    ok(uses(kitchen, sambar, powder))
    ok(kitchen.delete(f"{API}/recipes/{powder['id']}"))
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.get(Recipe, powder["id"]).removed_at = utcnow() - timedelta(days=8)  # type: ignore[union-attr]
        db.commit()
        assert purge_removed_recipes(db, db.get(Household, 1)) == 1  # type: ignore[arg-type]
    line = current(kitchen, sambar)["lines"][0]
    assert line["words"] == "Sambar powder" and line["link"] == "none"


def test_undo_of_a_delete_cannot_make_a_loop(kitchen: TestClient) -> None:
    """A uses B, B uses C. B is deleted. C is then saved using A. Bringing B back would make
    B -> C -> A -> B, so the Undo is refused, with the same words as a save."""
    a, b, c = (make(kitchen, name) for name in ["Aa", "Bb", "Cc"])
    ok(uses(kitchen, a, b))
    ok(uses(kitchen, b, c))
    removed = ok(kitchen.delete(f"{API}/recipes/{b['id']}"))["change"]
    ok(uses(kitchen, c, a))  # nothing is in the way: Bb is deleted
    response = kitchen.post(f"{API}/changes/{removed['id']}/undo")
    assert response.status_code == 409, response.text
    problem = response.json()
    assert problem["code"] == "recipe_loop"
    assert problem["detail"] == f"Bb {CANT} use Cc, because Cc uses Aa, which uses Bb."
    assert problem["chain"] == ["Cc", "Aa", "Bb"] and problem["line"] == 0
    # Nothing came back, and the change can still be undone once the loop is gone.
    assert kitchen.get(f"{API}/recipes/{b['id']}").status_code == 404
    ok(save(kitchen, current(kitchen, c), lines=[]))
    ok(kitchen.post(f"{API}/changes/{removed['id']}/undo"))
    assert kitchen.get(f"{API}/recipes/{b['id']}").status_code == 200


def test_the_loop_check_is_fast_in_a_big_household(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """2,000 recipes, each using twenty earlier ones. The picker's list and a save both look
    at the whole web of recipes while the household's write lock is held, so they must be
    quick: one search, not one per recipe. The work is counted rather than timed (a busy
    machine makes times vary): the database statements each call runs, the searches, the
    recipes each search visits, and its passes over (and lookups in) the web of recipes. A
    version with a query, a search or a pass over the web per recipe would run thousands."""
    import random
    from collections import deque

    from sqlalchemy import event

    from mealwright import recipes as recipe_code
    from mealwright.models import Recipe, RecipeLine, utcnow

    rng = random.Random(7)  # noqa: S311 (a test graph, not a secret)
    count = 2000
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        now = utcnow()
        for i in range(1, count + 2):
            db.add(
                Recipe(
                    id=i,
                    household_id=1,
                    name=f"Recipe {i:04d}",
                    version=1,
                    created_at=now,
                    updated_at=now,
                    updated_by_name="Tess",
                )
            )
        db.flush()
        for i in range(2, count + 1):
            for sub in rng.sample(range(1, i), min(20, i - 1)):
                db.add(
                    RecipeLine(
                        household_id=1,
                        recipe_id=i,
                        position=0,
                        kind="ingredient",
                        words="x",
                        sub_recipe_id=sub,
                    )
                )
        db.commit()

    work = {"statements": 0, "searches": 0, "visited": 0, "graph passes": 0, "graph lookups": 0}

    def statement(*args: Any) -> None:
        work["statements"] += 1

    class Graph(dict[int, set[int]]):
        """The web of recipes as the search gets it: each pass over it, and each lookup in
        it, is counted. A search that rebuilt its index at every visit would make thousands
        of passes, with no more queries, searches or visits."""

        def _pass(self) -> None:
            work["graph passes"] += 1

        def items(self) -> Any:
            self._pass()
            return super().items()

        def keys(self) -> Any:
            self._pass()
            return super().keys()

        def values(self) -> Any:
            self._pass()
            return super().values()

        def __iter__(self) -> Any:
            self._pass()
            return super().__iter__()

        def __getitem__(self, key: int) -> set[int]:
            work["graph lookups"] += 1
            return super().__getitem__(key)

        def get(self, key: int, default: Any = None) -> Any:
            work["graph lookups"] += 1
            return super().get(key, default)

        def __contains__(self, key: object) -> bool:
            work["graph lookups"] += 1
            return super().__contains__(key)

    real_graph = recipe_code.uses_graph

    def graph(*args: Any, **kwargs: Any) -> dict[int, set[int]]:
        return Graph(real_graph(*args, **kwargs))

    real_reaching = recipe_code.reaching

    def search(graph: dict[int, set[int]], target: int) -> dict[int, int]:
        work["searches"] += 1
        return real_reaching(graph, target)

    class Queue(deque[int]):  # the search's queue: each recipe taken from it is a visit
        def popleft(self) -> int:
            work["visited"] += 1
            return super().popleft()

    monkeypatch.setattr(recipe_code, "reaching", search)
    monkeypatch.setattr(recipe_code, "deque", Queue)
    monkeypatch.setattr(recipe_code, "uses_graph", graph)
    engine = kitchen.app.state.engine  # type: ignore[attr-defined]
    event.listen(engine, "before_cursor_execute", statement)

    def counted(call: Any) -> Any:
        work.update(dict.fromkeys(work, 0))
        result = call()
        # One pass over the web of recipes per search, and at most one lookup per recipe.
        assert work["graph passes"] <= work["searches"], work
        assert work["graph lookups"] <= count + 1, work
        return result

    try:
        lonely = count + 1  # nobody uses it: only itself is blocked
        blocked = ok(counted(lambda: kitchen.get(f"{API}/recipes/{lonely}/cannot-use")))
        assert [b["name"] for b in blocked["recipes"]] == [f"Recipe {lonely:04d}"]
        assert work["searches"] == 1 and work["visited"] == 1
        assert work["statements"] <= 10, work  # 7 today; one per recipe would be 2,000
        # A recipe nearly everything reaches: lots of reasons, each from the same search.
        blocked = ok(counted(lambda: kitchen.get(f"{API}/recipes/3/cannot-use")))["recipes"]
        assert work["searches"] == 1
        assert work["visited"] <= count + 1  # each recipe visited once at most
        assert work["statements"] <= 10, work  # 7 today; one per recipe would be 2,000
        assert len(blocked) > 1000
        by_id = {b["id"]: b for b in blocked}
        middle = by_id[count]
        assert middle["reason"].startswith(f"Recipe 0003 {CANT} use Recipe {count:04d}, because ")
        assert middle["chain"][0] == f"Recipe {count:04d}" and middle["chain"][-1] == "Recipe 0003"
        # A save that picks a recipe is checked against the same web, also quickly.
        mine = ok(kitchen.get(f"{API}/recipes/{lonely}"))
        lines = [{"words": "x", "recipe_id": i} for i in (10, 20, 30)]
        saved = counted(lambda: save(kitchen, mine, lines=lines))
        assert saved.status_code == 200, saved.text
        assert work["searches"] == 1 and work["visited"] == 1
        assert work["statements"] <= 40, work  # 31 today, most of them the save itself
    finally:
        event.remove(engine, "before_cursor_execute", statement)
