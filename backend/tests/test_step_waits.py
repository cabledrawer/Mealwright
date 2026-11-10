"""Steps that wait (0.8 wave 5, M1; cabledrawer 31 Oct and 9 Nov): a step can carry a wait (a kind and
a range, or one that ends at "overnight"); a recipe's time stays its active time and the waits
come back added up; recipes made before keep their single time."""

# ruff: noqa: F811  (the web fixture comes from test_recipe_import.py and is used by name)
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sync_kit import ok
from test_plan import slot_ids
from test_plan_writes import D1, plan_recipe, view
from test_recipe_import import API as IMPORT_API
from test_recipe_import import LINK, Web, review, switch, to_save, web  # noqa: F401
from test_recipe_import import save as save_import
from test_recipe_list import listing, row
from test_recipes import make, save

from mealwright.outbound import Connection
from mealwright.step_waits import Wait, active_time, read_wait

API = "/api/v1"

MARINATE = {"kind": "marinate", "min_minutes": 240, "overnight": True}


def tandoori(kitchen: TestClient, **fields: Any) -> dict[str, Any]:
    return make(
        kitchen,
        "Wait tandoori",
        time_minutes=45,
        steps=[
            {"text": "Rub the chicken. Leave to marinate.", "wait": MARINATE},
            {"text": "Fry the onions."},
        ],
        **fields,
    )


def test_a_step_keeps_its_wait_and_overnight_ends_at_twelve_hours(kitchen: TestClient) -> None:
    recipe = tandoori(kitchen)
    assert recipe["steps"][0]["wait"] == {
        "kind": "marinate",
        "min_minutes": 240,
        "max_minutes": 720,
        "overnight": True,
    }
    assert recipe["steps"][1]["wait"] is None
    again = ok(kitchen.get(f"{API}/recipes/{recipe['id']}"))
    assert again["steps"][0]["wait"] == recipe["steps"][0]["wait"]
    saved = ok(save(kitchen, again))  # sent back whole, as the editor does
    assert saved["steps"][0]["wait"] == recipe["steps"][0]["wait"]


def test_the_time_is_the_active_time_and_the_waits_come_back_added_up(
    kitchen: TestClient,
) -> None:
    recipe = make(
        kitchen,
        "Wait two",
        time_minutes=45,
        steps=[
            {"text": "Soak the rice.", "wait": {"kind": "soak", "min_minutes": 30}},
            {
                "text": "Marinate.",
                "wait": {"kind": "marinate", "min_minutes": 60, "max_minutes": 120},
            },
        ],
    )
    assert recipe["time_minutes"] == 45
    assert recipe["wait"] == {
        "kind": "wait",
        "min_minutes": 90,
        "max_minutes": 150,
        "overnight": False,
    }
    one = make(
        kitchen, "Wait one", steps=[{"text": "Soak.", "wait": {"kind": "soak", "min_minutes": 90}}]
    )
    assert one["wait"] == {"kind": "soak", "min_minutes": 90, "max_minutes": 90, "overnight": False}


def test_a_recipe_made_before_keeps_its_single_time_and_has_no_wait(kitchen: TestClient) -> None:
    old = make(kitchen, "Wait old", time_minutes=745, steps=[{"text": "Marinate for 12 hours."}])
    assert old["time_minutes"] == 745
    assert old["wait"] is None
    assert old["steps"][0]["wait"] is None


def test_the_list_and_the_plan_carry_the_added_up_wait(kitchen: TestClient) -> None:
    recipe = tandoori(kitchen)
    make(kitchen, "Wait plain", time_minutes=20)
    assert row(kitchen, "Wait tandoori")["wait"]["max_minutes"] == 720
    assert row(kitchen, "Wait plain")["wait"] is None
    assert listing(kitchen)["total"] >= 2
    plan_recipe(kitchen, recipe["id"], D1, slot_ids(kitchen)["Dinner"])
    meal = view(kitchen, D1)["meals"][0]
    found = meal["items"][0]["recipe"]
    assert found["time_minutes"] == 45
    assert found["wait"]["min_minutes"] == 240


def test_a_copy_keeps_the_waits(kitchen: TestClient) -> None:
    recipe = tandoori(kitchen)
    copy = ok(kitchen.post(f"{API}/recipes/{recipe['id']}/duplicate"), 201)
    assert copy["steps"][0]["wait"] == recipe["steps"][0]["wait"]
    assert copy["wait"] == recipe["wait"]


def test_a_save_that_leaves_the_wait_out_keeps_it_and_null_takes_it_off(
    kitchen: TestClient,
) -> None:
    """A client that knows nothing of waits sends steps without `wait`: they stay (M1 fix 8a).
    Only an explicit null takes one off; a step whose words changed has nothing to keep."""
    recipe = tandoori(kitchen)
    words = recipe["steps"][0]["text"]
    kept = ok(save(kitchen, recipe, steps=[{"text": words}]))
    assert kept["steps"][0]["wait"] == recipe["steps"][0]["wait"]
    assert kept["wait"] == recipe["wait"]
    off = ok(save(kitchen, kept, steps=[{"text": words, "wait": None}]))
    assert off["steps"][0]["wait"] is None and off["wait"] is None
    again = ok(save(kitchen, off, steps=[{"text": words}]))  # nothing there to keep
    assert again["steps"][0]["wait"] is None
    back = ok(save(kitchen, again, steps=[{"text": words, "wait": MARINATE}]))
    reworded = ok(save(kitchen, back, steps=[{"text": words + " Then rest it."}]))
    assert reworded["steps"][0]["wait"] is None


def test_a_wait_is_checked(kitchen: TestClient) -> None:
    def refused(**wait: Any) -> int:
        return kitchen.post(
            f"{API}/recipes", json={"name": "Wait bad", "steps": [{"text": "Wait.", "wait": wait}]}
        ).status_code

    assert refused(kind="fry", min_minutes=10) == 422  # not a kind
    assert refused(kind="soak", min_minutes=0) == 422
    assert refused(kind="soak", min_minutes=20_000) == 422
    assert refused(kind="soak", min_minutes=120, max_minutes=60) == 422  # longest below shortest
    heading = kitchen.post(
        f"{API}/recipes",
        json={
            "name": "Wait bad",
            "steps": [
                {"kind": "heading", "text": "Later", "wait": {"kind": "soak", "min_minutes": 5}}
            ],
        },
    )
    assert heading.status_code == 422


# --- The importer ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "kind", "low", "high", "overnight"),
    [
        ("Rub it. Leave to marinate for 4 hours, or overnight.", "marinate", 240, 720, True),
        ("Marinate for 4 hours or overnight.", "marinate", 240, 720, True),
        ("Let the batter ferment 8\u201312 hours.", "ferment", 480, 720, False),
        ("Ferment 8-12 hrs at room temperature.", "ferment", 480, 720, False),
        ("Soak the dal overnight.", "soak", 720, 720, True),
        ("Soak the chickpeas for 8 hours.", "soak", 480, 480, False),
        ("Chill for 2 to 3 hours.", "chill", 120, 180, False),
        ("Cover and refrigerate overnight.", "chill", 720, 720, True),
        ("Prove for 1 day.", "prove", 1440, 1440, False),
        ("Cook it for 20 minutes, then rest for 1 hour.", "rest", 60, 60, False),
        ("Marinate from 1 hour to overnight.", "marinate", 60, 720, True),
        # M1 fix 2: overnight anywhere in the clause is the long end; 1 hour 30 minutes is 90.
        ("Marinate overnight, or for at least 4 hours.", "marinate", 240, 720, True),
        ("Soak the lentils for 1 hour 30 minutes.", "soak", 90, 90, False),
        ("Soak for 1 h and 30 min.", "soak", 90, 90, False),
    ],
)
def test_the_reader_suggests_a_wait_from_the_words(
    text: str, kind: str, low: int, high: int, overnight: bool
) -> None:
    assert read_wait(text) == Wait(kind, low, high, overnight)


@pytest.mark.parametrize(
    "text",
    [
        "Fry the onions until golden, about 12 minutes.",
        "Add the soaked chickpeas and simmer for 45 minutes.",  # soaked, not "soak"
        "Marinate for 20 minutes.",  # short: part of the step
        "Rest the steak 5 minutes.",
        "Fry 2 onions and soak the rice.",  # no length
        "Bring 2 litres of water to the boil, then soak the noodles for 10 minutes.",
        "Serve overnight oats cold.",  # overnight with no wait word before it
        # M1 fix 2: the length must be in the wait word's own clause.
        "Add the rest of the stock and simmer for 2 hours.",
        "Soak the beans, then drain and cook for 2 hours.",
        "Chill the dough, then bake at 180C for 45 minutes.",
        "Soak the beans and simmer for 2 hours.",
        "Chill the dough, bake for 1 hour.",
    ],
)
def test_the_reader_leaves_other_steps_alone(text: str) -> None:
    assert read_wait(text) is None


def test_the_active_time_leaves_out_the_waits_a_page_counts() -> None:
    marinate = Wait("marinate", 240, 720, True)
    assert active_time(745, [marinate]) == 25  # "745 min": 25 active and a night of marinating
    assert active_time(285, [marinate]) == 45  # the page counted the 4 hours
    assert active_time(100, [marinate]) == 100  # too short to have held it: not guessed
    assert active_time(None, [marinate]) is None
    assert active_time(30, []) == 30


PAGE = """<html><head><script type="application/ld+json">
{"@context":"https://schema.org","@type":"Recipe","name":"Wait tandoori chicken",
 "totalTime":"PT12H25M","recipeYield":"4",
 "recipeIngredient":["500 g chicken","1 cup yoghurt"],
 "recipeInstructions":[
  {"@type":"HowToStep","text":"Rub the chicken. Leave to marinate for 4 hours, or overnight."},
  {"@type":"HowToStep","text":"Fry the onions until golden, about 12 minutes."}]}
</script></head><body></body></html>"""


def test_the_review_suggests_the_wait_and_the_pages_time_loses_it(
    kitchen: TestClient, web: Web
) -> None:
    switch(kitchen, Connection.RECIPE_IMPORT)
    web.pages[LINK] = PAGE
    shown = review(kitchen, LINK)
    assert shown["time_minutes"] == 25  # not 745
    assert shown["page_time_minutes"] == 745  # the page's own total stays, for "No wait"
    assert shown["steps"][0]["wait"] == {
        "kind": "marinate",
        "min_minutes": 240,
        "max_minutes": 720,
        "overnight": True,
    }
    assert shown["steps"][1]["wait"] is None
    saved = ok(save_import(kitchen, to_save(shown)), 201)
    recipe = ok(kitchen.get(f"{IMPORT_API}/recipes/{saved['recipe']['id']}"))
    assert recipe["time_minutes"] == 25
    assert recipe["steps"][0]["wait"]["max_minutes"] == 720
    assert recipe["wait"]["overnight"] is True


def test_a_wait_the_person_took_off_or_changed_is_saved_as_they_left_it(
    kitchen: TestClient, web: Web
) -> None:
    switch(kitchen, Connection.RECIPE_IMPORT)
    web.pages[LINK] = PAGE
    shown = review(kitchen, LINK)
    body = to_save(shown)
    body["steps"][0]["wait"] = {"kind": "soak", "min_minutes": 90}
    body["steps"][1]["wait"] = None
    saved = ok(save_import(kitchen, body), 201)
    recipe = ok(kitchen.get(f"{IMPORT_API}/recipes/{saved['recipe']['id']}"))
    assert recipe["steps"][0]["wait"] == {
        "kind": "soak",
        "min_minutes": 90,
        "max_minutes": 90,
        "overnight": False,
    }
    body = to_save(shown)
    body["steps"][0]["wait"] = None  # "No wait"
    again = ok(save_import(kitchen, body), 201)
    assert ok(kitchen.get(f"{IMPORT_API}/recipes/{again['recipe']['id']}"))["wait"] is None


def test_a_pasted_recipe_gets_suggested_waits_too(kitchen: TestClient, web: Web) -> None:
    shown = review(
        kitchen,
        "Wait pasted dosa\nIngredients\n2 cups rice\nMethod\n1. Soak the rice overnight.\n"
        "2. Grind and ferment 8-12 hours.\n3. Cook on a hot pan.\n",
    )
    assert [s["wait"] and s["wait"]["kind"] for s in shown["steps"]] == ["soak", "ferment", None]
