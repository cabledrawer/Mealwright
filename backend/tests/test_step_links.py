"""Which ingredient lines each method step uses (0.7 K1; spec section 6 gaps, "Cook mode
ingredients", cabledrawer 17 Oct: "step ↔ ingredient links, each marked guessed or set by hand")."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sync_kit import db, ok
from test_recipes import make, save

from mealwright.models import Household, RecipeStepLine, utcnow
from mealwright.recipes import purge_removed_recipes

API = "/api/v1"

LINES = [
    {"words": "toor dal", "amount": 200, "unit": "g"},
    {"kind": "heading", "words": "For the tempering"},
    {"words": "mustard seeds", "amount": 1, "unit": "tsp"},
    {"words": "curry leaves"},
]


def _sambar(client: TestClient) -> dict[str, Any]:
    return make(
        client,
        lines=LINES,
        steps=[
            {"text": "Boil the dal.", "lines": [0]},
            {"kind": "heading", "text": "Tempering"},
            {"text": "Fry the seeds and leaves.", "lines": [3, 2, 3]},
            {"text": "Serve."},
        ],
    )


def _uses(recipe: dict[str, Any]) -> list[list[tuple[str, str]]]:
    """Each step's lines, by their words, with how each was set."""
    words = [line["words"] for line in recipe["lines"]]
    found = []
    for step in recipe["steps"]:
        for link in step["lines"]:
            assert recipe["lines"][link["line"]]["id"] == link["line_id"]
        found.append([(words[link["line"]], link["kind"]) for link in step["lines"]])
    return found


def _guess(client: TestClient, step_id: int, line_id: int) -> None:
    """A guessed link, as the guessing (0.7 K4) will write it."""
    with db(client) as session:
        session.add(
            RecipeStepLine(household_id=1, step_id=step_id, line_id=line_id, kind="guessed")
        )
        session.commit()


def test_links_set_by_hand_are_read_with_the_recipe(kitchen: TestClient) -> None:
    recipe = _sambar(kitchen)
    assert _uses(recipe) == [
        [("toor dal", "by_hand")],
        [],
        [("mustard seeds", "by_hand"), ("curry leaves", "by_hand")],
        [],
    ]
    assert _uses(ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))) == _uses(recipe)


def test_a_save_that_leaves_the_links_out_keeps_them_and_a_new_line_can_be_linked(
    kitchen: TestClient,
) -> None:
    recipe = _sambar(kitchen)
    _guess(kitchen, recipe["steps"][3]["id"], recipe["lines"][0]["id"])
    saved = ok(save(kitchen, recipe))  # the steps sent back without `lines`
    assert _uses(saved) == [
        [("toor dal", "by_hand")],
        [],
        [("mustard seeds", "by_hand"), ("curry leaves", "by_hand")],
        [("toor dal", "guessed")],
    ]
    # A new line, linked in the same save, by its place in `lines`.
    body = save_body(saved)
    body["lines"].append({"words": "rice"})
    body["steps"][3]["lines"] = [4]
    again = ok(kitchen.put(f"{API}/recipes/{recipe['id']}", json=body))
    assert _uses(again)[3] == [("rice", "by_hand")]
    assert _uses(again)[0] == [("toor dal", "by_hand")]


def save_body(recipe: dict[str, Any]) -> dict[str, Any]:
    """What `save` sends, to change before sending."""
    sent: dict[str, Any] = {}

    class Capture:
        def put(self, _url: str, json: dict[str, Any]) -> None:
            sent.update(json)

    save(Capture(), recipe)  # type: ignore[arg-type]
    return sent


def test_links_that_no_longer_match_go(kitchen: TestClient) -> None:
    recipe = _sambar(kitchen)
    body = save_body(recipe)
    del body["lines"][0]  # toor dal goes: step 1's link with it
    body["steps"][2]["text"] = "Fry the seeds and the leaves."  # new words: a new step
    body["steps"][0]["text"] = "Serve."  # the old "Serve." had no links
    body["steps"][3]["text"] = "Boil the dal."  # moved: its links follow its words
    saved = ok(kitchen.put(f"{API}/recipes/{recipe['id']}", json=body))
    assert _uses(saved) == [[], [], [], []]
    with db(kitchen) as session:
        assert session.scalar(select(RecipeStepLine.id).limit(1)) is None


def test_moved_steps_keep_their_links(kitchen: TestClient) -> None:
    recipe = _sambar(kitchen)
    body = save_body(recipe)
    body["steps"] = list(reversed(body["steps"]))
    saved = ok(kitchen.put(f"{API}/recipes/{recipe['id']}", json=body))
    assert _uses(saved) == [
        [],
        [("mustard seeds", "by_hand"), ("curry leaves", "by_hand")],
        [],
        [("toor dal", "by_hand")],
    ]


def test_set_by_hand_replaces_the_guesses_and_empty_clears(kitchen: TestClient) -> None:
    recipe = _sambar(kitchen)
    _guess(kitchen, recipe["steps"][3]["id"], recipe["lines"][0]["id"])
    body = save_body(recipe)
    body["steps"][3]["lines"] = [2]
    body["steps"][0]["lines"] = []
    saved = ok(kitchen.put(f"{API}/recipes/{recipe['id']}", json=body))
    assert _uses(saved)[0] == []
    assert _uses(saved)[3] == [("mustard seeds", "by_hand")]


def test_a_step_can_only_use_the_recipes_own_ingredient_lines(kitchen: TestClient) -> None:
    for steps in (
        [{"text": "Boil.", "lines": [4]}],  # no fifth line
        [{"text": "Boil.", "lines": [1]}],  # a heading
        [{"kind": "heading", "text": "The dal", "lines": [0]}],  # a heading has none
        [{"text": "Boil.", "lines": [-1]}],
    ):
        answer = kitchen.post(
            f"{API}/recipes", json={"name": "Dal", "lines": LINES, "steps": steps}
        )
        assert answer.status_code == 422, answer.text


def test_links_go_with_the_recipe_when_it_is_deleted_for_good(kitchen: TestClient) -> None:
    recipe = _sambar(kitchen)
    ok(kitchen.delete(f"{API}/recipes/{recipe['id']}"))
    with db(kitchen) as session:
        assert session.scalar(select(RecipeStepLine.id).limit(1)) is not None
        household = session.get(Household, 1)
        assert household is not None
        assert purge_removed_recipes(session, household, utcnow() + timedelta(days=30)) == 1
        assert session.scalar(select(RecipeStepLine.id).limit(1)) is None


def test_the_database_refuses_a_link_between_two_households(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    mine = _sambar(kitchen)
    theirs = make(neighbour, "Rasam", lines=[{"words": "tamarind"}], steps=[{"text": "Boil."}])
    with db(kitchen) as session:
        my_step = mine["steps"][0]["id"]
        their_line = theirs["lines"][0]["id"]
        for household_id in (1, 2):
            session.add(
                RecipeStepLine(
                    household_id=household_id, step_id=my_step, line_id=their_line, kind="by_hand"
                )
            )
            with pytest.raises(IntegrityError):
                session.flush()
            session.rollback()
        # And a link only knows "guessed" and "by hand".
        session.add(
            RecipeStepLine(
                household_id=1, step_id=my_step, line_id=mine["lines"][2]["id"], kind="maybe"
            )
        )
        with pytest.raises(IntegrityError):
            session.flush()
