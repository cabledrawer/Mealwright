"""Steps that wait (0.8 wave 5, M1; cabledrawer 31 Oct and 9 Nov): a step can carry a wait (a kind and
a range, or one that ends at "overnight"); a recipe's time stays its active time and the waits
come back added up; recipes made before keep their single time."""

from typing import Any

from fastapi.testclient import TestClient
from sync_kit import ok
from test_plan import slot_ids
from test_plan_writes import D1, plan_recipe, view
from test_recipe_list import listing, row
from test_recipes import make, save

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


def test_a_save_that_leaves_the_wait_out_takes_it_off(kitchen: TestClient) -> None:
    recipe = tandoori(kitchen)
    saved = ok(save(kitchen, recipe, steps=[{"text": "Rub the chicken."}]))
    assert saved["steps"][0]["wait"] is None
    assert saved["wait"] is None


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
