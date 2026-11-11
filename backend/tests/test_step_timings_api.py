"""Batch cook's step timings and the household's kitchen over the API (0.8 wave 6, B1)."""

from typing import Any

from fastapi.testclient import TestClient
from sync_kit import ok, person
from test_recipes import make, save

from mealwright.models import Household, RecipeStep

API = "/api/v1"

SAMBAR = [
    {"text": "Sambar", "kind": "heading"},
    {"text": "Wash the toor dal and pressure cook it with turmeric for 3 whistles."},
    {"text": "Chop the onion, tomato and drumsticks."},
    {"text": "Boil the vegetables in the tamarind water until soft."},
]


def timing(step: dict[str, Any]) -> dict[str, Any]:
    found: dict[str, Any] = step["timing"]
    return found


# --- On a step ----------------------------------------------------------------------------------


def test_every_step_comes_back_with_a_guess_and_a_heading_has_none(kitchen: TestClient) -> None:
    recipe = make(kitchen, "Timed sambar", steps=SAMBAR)
    heading, cooker, chop, boil = recipe["steps"]
    assert heading["timing"] is None
    assert timing(cooker) == {
        "hands": "waiting",
        "minutes": 15,
        "equipment": "pressure",
        "hands_guessed": True,
        "minutes_guessed": True,
        "equipment_guessed": True,
    }
    assert (timing(chop)["hands"], timing(chop)["equipment"]) == ("hands", "none")
    assert (timing(boil)["hands"], timing(boil)["equipment"]) == ("waiting", "hob")


def test_what_is_set_by_hand_is_kept_and_marked_and_the_rest_stays_a_guess(
    kitchen: TestClient,
) -> None:
    recipe = make(
        kitchen,
        "Timed by hand",
        steps=[{"text": "Chop the onion.", "timing": {"hands": "hands", "minutes": 8}}],
    )
    got = timing(recipe["steps"][0])
    assert (got["hands"], got["minutes"], got["equipment"]) == ("hands", 8, "none")
    assert (got["hands_guessed"], got["minutes_guessed"], got["equipment_guessed"]) == (
        False,
        False,
        True,
    )
    again = ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))
    assert timing(again["steps"][0]) == got


def test_a_save_that_says_nothing_about_timing_keeps_it_and_null_clears_it(
    kitchen: TestClient,
) -> None:
    recipe = make(
        kitchen,
        "Timed kept",
        steps=[{"text": "Simmer the sambar.", "timing": {"minutes": 40, "equipment": "oven"}}],
    )
    kept = ok(save(kitchen, recipe))  # `save` sends no `timing`, like a client that knows nothing
    assert timing(kept["steps"][0])["minutes"] == 40
    assert timing(kept["steps"][0])["equipment"] == "oven"
    cleared = ok(
        save(
            kitchen,
            kept,
            steps=[{"kind": "step", "text": "Simmer the sambar.", "timing": None}],
        )
    )
    assert timing(cleared["steps"][0])["minutes_guessed"] is True
    assert timing(cleared["steps"][0])["equipment"] == "hob"


def test_when_the_words_change_a_hand_set_value_stays_and_the_guess_follows_the_words(
    kitchen: TestClient,
) -> None:
    recipe = make(
        kitchen,
        "Timed words",
        steps=[{"text": "Simmer for 10 minutes.", "timing": {"hands": "hands"}}],
    )
    changed = ok(
        save(
            kitchen,
            recipe,
            steps=[
                {
                    "kind": "step",
                    "text": "Pressure cook for 3 whistles.",
                    "timing": {"hands": "hands"},
                }
            ],
        )
    )
    got = timing(changed["steps"][0])
    assert (got["hands"], got["hands_guessed"]) == ("hands", False)
    assert (got["equipment"], got["minutes"]) == ("pressure", 15)


def test_a_bad_timing_is_refused(kitchen: TestClient) -> None:
    for bad in (
        {"hands": "later"},
        {"equipment": "microwave"},
        {"minutes": 0},
        {"minutes": 14_401},
        {"minutes": "ten"},
    ):
        body = {"name": "Timed bad", "steps": [{"text": "Stir.", "timing": bad}]}
        assert kitchen.post(f"{API}/recipes", json=body).status_code == 422
    heading = {"name": "Timed bad", "steps": [{"kind": "heading", "text": "A", "timing": {}}]}
    assert kitchen.post(f"{API}/recipes", json=heading).status_code == 422


def test_a_second_method_and_a_copy_keep_what_was_set_by_hand(kitchen: TestClient) -> None:
    recipe = make(
        kitchen,
        "Timed copy",
        steps=[{"text": "Stir.", "timing": {"minutes": 33, "equipment": "hob"}}],
    )
    copy = ok(kitchen.post(f"{API}/recipes/{recipe['id']}/duplicate", json={}), 201)
    got = timing(copy["steps"][0])
    assert (got["minutes"], got["equipment"], got["minutes_guessed"]) == (33, "hob", False)


def test_a_wait_from_wave_5_counts_as_waiting_and_gives_its_minutes(kitchen: TestClient) -> None:
    recipe = make(
        kitchen,
        "Timed wait",
        steps=[
            {
                "text": "Soak the rice.",
                "wait": {"kind": "soak", "min_minutes": 30, "max_minutes": 90},
            }
        ],
    )
    got = timing(recipe["steps"][0])
    assert (got["hands"], got["minutes"], got["equipment"]) == ("waiting", 90, "none")


def test_another_household_never_sees_or_changes_a_step_timing(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    recipe = make(kitchen, "Timed mine", steps=[{"text": "Stir.", "timing": {"minutes": 7}}])
    assert neighbour.get(f"{API}/recipes/{recipe['id']}").status_code == 404
    body = {
        "name": "Taken",
        "version": recipe["version"],
        "steps": [{"text": "Stir.", "timing": {"minutes": 99}}],
    }
    refused = neighbour.put(f"{API}/recipes/{recipe['id']}", json=body)
    assert refused.status_code == 404  # a valid body: the household check refuses it (r1 L4)
    again = ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))
    assert timing(again["steps"][0])["minutes"] == 7
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        rows = db.query(RecipeStep).filter(RecipeStep.timing_minutes == 7).all()
        assert {row.household_id for row in rows} == {1}


# --- The household's kitchen ---------------------------------------------------------------------


def test_a_new_household_has_the_usual_kitchen_and_has_not_been_asked(kitchen: TestClient) -> None:
    assert ok(kitchen.get(f"{API}/household/kitchen")) == {
        "hob_rings": 4,
        "pressure_cookers": 1,
        "oven": True,
        "asked": False,
    }


def test_saving_the_kitchen_keeps_it_and_counts_as_asked(kitchen: TestClient) -> None:
    saved = ok(
        kitchen.patch(
            f"{API}/household/kitchen", json={"hob_rings": 2, "pressure_cookers": 0, "oven": False}
        )
    )
    assert saved == {"hob_rings": 2, "pressure_cookers": 0, "oven": False, "asked": True}
    assert ok(kitchen.get(f"{API}/household/kitchen")) == saved
    part = ok(kitchen.patch(f"{API}/household/kitchen", json={"hob_rings": 3}))
    assert part == {"hob_rings": 3, "pressure_cookers": 0, "oven": False, "asked": True}


def test_a_bad_kitchen_is_refused_and_nothing_changes(kitchen: TestClient) -> None:
    for bad in (
        {"hob_rings": 0},
        {"hob_rings": 13},
        {"pressure_cookers": -1},
        {"pressure_cookers": 7},
        {"oven": "yes"},
        {"hob_rings": 2.5},
    ):
        assert kitchen.patch(f"{API}/household/kitchen", json=bad).status_code == 422, bad
    assert ok(kitchen.get(f"{API}/household/kitchen"))["hob_rings"] == 4
    assert ok(kitchen.get(f"{API}/household/kitchen"))["asked"] is False


def test_a_member_can_change_the_kitchen(kitchen: TestClient) -> None:
    remy = person(kitchen)
    assert ok(remy.patch(f"{API}/household/kitchen", json={"oven": False}))["oven"] is False
    assert ok(kitchen.get(f"{API}/household/kitchen"))["oven"] is False


def test_signed_out_cannot_read_or_change_the_kitchen(client: TestClient) -> None:
    assert client.get(f"{API}/household/kitchen").status_code == 401
    assert client.patch(f"{API}/household/kitchen", json={"oven": True}).status_code == 401


def test_one_household_changing_its_kitchen_never_changes_anothers(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    ok(kitchen.patch(f"{API}/household/kitchen", json={"hob_rings": 6}))
    assert ok(neighbour.get(f"{API}/household/kitchen")) == {
        "hob_rings": 4,
        "pressure_cookers": 1,
        "oven": True,
        "asked": False,
    }
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        found = [h.kitchen_hob_rings for h in db.query(Household).order_by(Household.id)]
    assert found == [6, 4]
