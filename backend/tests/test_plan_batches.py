"""Cook once, eat for… (0.6 PR 4): making a batch cook from a planned recipe, the patterns, the
preview, tubs placed by hand, whose and use-by, the freezer, "leftovers here" making a tub,
Fill from freezer, every write with its Undo, the caps, and ids from another household."""

from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from test_plan import add_food, add_recipe, db_of, slot_ids
from test_plan_writes import D1, D2, plan_recipe, shape, undo, view

from mealwright import batches as batches_module
from mealwright import plan as plan_module
from mealwright.auth import hash_password
from mealwright.models import BatchCook, Household, Login, Meal, MealItem, Tub

API = "/api/v1"
D3 = D1 + timedelta(days=2)


@pytest.fixture
def slots(kitchen: TestClient) -> dict[str, int]:
    return slot_ids(kitchen)


@pytest.fixture
def stuff(kitchen: TestClient) -> dict[str, int]:
    with db_of(kitchen) as db:
        biryani = add_recipe(db, 1, "Veg biryani")
        biryani.kcal_milli, biryani.protein_milli, biryani.fibre_milli = 410_000, 12_000, 6_400
        dosa = add_recipe(db, 1, "Dosa")
        chutney = add_recipe(db, 1, "Coconut chutney")
        banana = add_food(db, 1, "Banana")
        db.commit()
        return {
            "biryani": biryani.id,
            "dosa": dosa.id,
            "chutney": chutney.id,
            "banana": banana.id,
        }


@pytest.fixture
def cook(kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]) -> dict[str, Any]:
    """Veg biryani planned for dinner on D1."""
    return plan_recipe(kitchen, stuff["biryani"], D1, slots["Dinner"])


@pytest.fixture
def wren(kitchen: TestClient) -> int:
    with db_of(kitchen) as db:
        login = Login(
            household_id=1,
            username="wren",
            name="Wren",
            password_hash=hash_password("wren's own password"),
            role="member",
        )
        db.add(login)
        db.commit()
        return login.id


def make(client: TestClient, item_id: int, **body: Any) -> dict[str, Any]:
    r = client.post(
        f"{API}/plan/items/{item_id}/batch",
        json={"tub_count": 4, "pattern": "lunch_dinner", **body},
    )
    assert r.status_code == 201, r.text
    return r.json()  # type: ignore[no-any-return]


def preview(client: TestClient, item_id: int, **body: Any) -> dict[str, Any]:
    r = client.post(
        f"{API}/plan/items/{item_id}/batch/preview",
        json={"tub_count": 4, "pattern": "lunch_dinner", **body},
    )
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def where_tubs_are(client: TestClient, slots: dict[str, int]) -> list[tuple[int, str | None, str]]:
    """(tub number, date, slot name) for every tub of the plan, in tub order; a tub in no meal
    has date None and the place it is in."""
    names = {v: k for k, v in slots.items()}
    plan = view(client, D1 - timedelta(days=1), days=30)
    in_meal = {
        i["tub_id"]: (m["date"], names[m["slot_id"]])
        for m in plan["meals"]
        for i in m["items"]
        if i["tub_id"]
    }
    out = []
    for tub in plan["tubs"]:
        day, slot = in_meal.get(tub["id"], (None, tub["place_kind"] or "nowhere"))
        out.append((tub["number"], day, slot))
    return out


def day(n: int) -> str:
    return (D1 + timedelta(days=n)).isoformat()


# --- The patterns ---------------------------------------------------------------------------------


def test_lunch_and_dinner_fills_the_next_meals_after_the_cook_meal(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    made = make(kitchen, cook["item_id"])
    assert where_tubs_are(kitchen, slots) == [
        (1, day(1), "Lunch"),
        (2, day(1), "Dinner"),
        (3, day(2), "Lunch"),
        (4, day(2), "Dinner"),
    ]
    assert made["batch_id"] and made["change"]["summary"].startswith("Cooked Veg biryani once")
    batch = view(kitchen)["batch_cooks"][0]
    assert batch["cook_meal_id"] == cook["meal_id"] and batch["tub_count"] == 4
    assert batch["cooked_on"] == D1.isoformat() and batch["colour"] == "purple"
    assert batch["pattern"] == "lunch_dinner" and batch["recipe_name"] == "Veg biryani"
    # The cook meal itself is not filled with a tub.
    assert [len(m["items"]) for m in view(kitchen)["meals"] if m["date"] == D1.isoformat()] == [1]


def test_lunches_go_by_their_own_word(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    make(kitchen, cook["item_id"], tub_count=3, pattern="lunches")
    assert {s for _, _, s in where_tubs_are(kitchen, slots)} == {"Lunch"}


def test_dinners_pattern_starts_the_same_evening_only_for_a_later_slot(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    """Cooked at lunch: tonight's dinner is after the cook meal, so it gets a tub."""
    at_lunch = plan_recipe(kitchen, stuff["biryani"], D1, slots["Lunch"])
    made = make(kitchen, at_lunch["item_id"], tub_count=2, pattern="dinners")
    assert made["batch_id"]
    assert where_tubs_are(kitchen, slots) == [(1, day(0), "Dinner"), (2, day(1), "Dinner")]


def test_the_pattern_skips_meals_with_food_and_meals_that_are_off(
    kitchen: TestClient, cook: dict[str, Any], stuff: dict[str, int], slots: dict[str, int]
) -> None:
    plan_recipe(kitchen, stuff["dosa"], D1 + timedelta(days=1), slots["Lunch"])
    r = kitchen.patch(f"{API}/meal-slots/{slots['Dinner']}", json={"enabled": False})
    assert r.status_code == 200
    made = preview(kitchen, cook["item_id"], tub_count=3)
    assert [(t["date"], t["slot_id"]) for t in made["tubs"]] == [
        (day(2), slots["Lunch"]),
        (day(3), slots["Lunch"]),
        (day(4), slots["Lunch"]),
    ]
    assert made["placed"] == 3


def test_i_ll_pick_places_nothing_and_the_tubs_wait_in_the_fridge(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    make(kitchen, cook["item_id"], pattern="pick")
    assert where_tubs_are(kitchen, slots) == [(n, None, "fridge") for n in (1, 2, 3, 4)]
    assert [len(m["items"]) for m in view(kitchen)["meals"]] == [1]


def test_tubs_with_no_meal_to_go_to_are_left_and_extras_go_to_the_freezer(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    kitchen.patch(f"{API}/meal-slots/{slots['Lunch']}", json={"enabled": False})
    kitchen.patch(f"{API}/meal-slots/{slots['Dinner']}", json={"enabled": False})
    made = preview(kitchen, cook["item_id"], extras_to_freezer=True)
    assert made["placed"] == 0 and {t["place_kind"] for t in made["tubs"]} == {"freezer"}
    fridge = preview(kitchen, cook["item_id"])
    assert {t["place_kind"] for t in fridge["tubs"]} == {"fridge"}


def test_only_the_tubs_that_are_not_in_a_meal_are_extras(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    placements: list[Any] = [{"date": day(1), "slot_id": slots["Lunch"]}, None, None]
    made = make(
        kitchen, cook["item_id"], tub_count=3, placements=placements, extras_to_freezer=True
    )
    assert made["batch_id"]
    assert where_tubs_are(kitchen, slots) == [
        (1, day(1), "Lunch"),
        (2, None, "freezer"),
        (3, None, "freezer"),
    ]
    assert [t["place_kind"] for t in view(kitchen)["tubs"]] == ["fridge", "freezer", "freezer"]


def test_use_by_comes_from_the_household_tub_life_counted_from_the_cook_day(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    with db_of(kitchen) as db:
        household = db.get(Household, 1)
        assert household is not None
        household.tub_fridge_days, household.tub_freezer_months = 5, 2
        db.commit()
    kitchen.patch(f"{API}/meal-slots/{slots['Dinner']}", json={"enabled": False})
    placements: list[Any] = [{"date": day(1), "slot_id": slots["Lunch"]}, None, None, None]
    got = preview(kitchen, cook["item_id"], placements=placements, extras_to_freezer=True)
    uses = [(t["place_kind"], t["use_by"]) for t in got["tubs"]]
    two_months = batches_module.add_months(D1, 2).isoformat()
    assert (
        uses == [("fridge", (D1 + timedelta(days=5)).isoformat())] + [("freezer", two_months)] * 3
    )


def test_who_is_eating_decides_whose_each_tub_is(
    kitchen: TestClient, cook: dict[str, Any], wren: int
) -> None:
    people = kitchen.get(f"{API}/plan/people").json()
    assert len(people) == 2 and people[1] == {"login_id": wren, "name": "Wren"}
    ids = [p["login_id"] for p in people]
    both = preview(kitchen, cook["item_id"], member_login_ids=ids)
    assert [t["member_login_id"] for t in both["tubs"]] == [ids[0], wren, ids[0], wren]
    one = preview(kitchen, cook["item_id"], member_login_ids=[wren])
    assert {t["member_login_id"] for t in one["tubs"]} == {wren}
    nobody = preview(kitchen, cook["item_id"])
    assert {t["member_login_id"] for t in nobody["tubs"]} == {None}
    saved = make(kitchen, cook["item_id"], member_login_ids=ids)
    assert saved["batch_id"]
    assert [t["member_login_id"] for t in view(kitchen)["tubs"]] == [ids[0], wren, ids[0], wren]


def test_the_preview_changes_nothing_and_matches_what_is_saved(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    before = shape(kitchen)
    got = preview(kitchen, cook["item_id"], prep_note="Soak the rice")
    assert shape(kitchen) == before and view(kitchen)["batch_cooks"] == []
    assert got["per_tub"] == {"kcal": 410, "protein_g": 12, "fibre_g": 6}
    assert got["recipe_name"] == "Veg biryani" and got["recipe_serves"] == 4
    assert got["cook_date"] == D1.isoformat() and got["cook_meal_id"] == cook["meal_id"]
    make(kitchen, cook["item_id"], prep_note="Soak the rice")
    saved = view(kitchen)
    assert saved["batch_cooks"][0]["prep_note"] == "Soak the rice"
    assert saved["batch_cooks"][0]["colour"] == got["colour"]
    landed = [(d, s) for _, d, s in where_tubs_are(kitchen, slots)]
    assert landed == [
        (t["date"], {v: k for k, v in slots.items()}[t["slot_id"]]) for t in got["tubs"]
    ]


# --- Placing tubs by hand ------------------------------------------------------------------------


def test_the_person_can_choose_every_place_and_may_add_to_a_meal_with_food(
    kitchen: TestClient, cook: dict[str, Any], stuff: dict[str, int], slots: dict[str, int]
) -> None:
    upma = plan_recipe(kitchen, stuff["dosa"], D2, slots["Dinner"])
    assert upma["meal_id"]
    placements: list[Any] = [
        {"date": day(1), "slot_id": slots["Dinner"]},
        None,
        {"date": day(1), "slot_id": slots["Dinner"]},
    ]
    got = preview(kitchen, cook["item_id"], tub_count=3, pattern="pick", placements=placements)
    assert [t["meal_has_food"] for t in got["tubs"]] == [True, False, True]
    make(kitchen, cook["item_id"], tub_count=3, pattern="pick", placements=placements)
    meal = next(m for m in view(kitchen)["meals"] if m["date"] == day(1))
    assert [i["kind"] for i in meal["items"]] == ["recipe", "tub", "tub"]


def test_bad_placements_are_refused(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    url = f"{API}/plan/items/{cook['item_id']}/batch"
    ok = {"date": day(1), "slot_id": slots["Lunch"]}
    short = kitchen.post(url, json={"tub_count": 3, "placements": [ok]})
    assert short.status_code == 422 and short.json()["code"] == "bad_placements"
    off = kitchen.patch(f"{API}/meal-slots/{slots['Snack']}", json={"enabled": False})
    assert off.status_code == 200
    snack = {"date": day(1), "slot_id": slots["Snack"]}
    assert kitchen.post(url, json={"tub_count": 1, "placements": [snack]}).status_code == 422
    far = {"date": "2090-01-01", "slot_id": slots["Lunch"]}
    assert kitchen.post(url, json={"tub_count": 1, "placements": [far]}).json()["code"] == "bad_day"
    assert kitchen.post(url, json={"tub_count": 13}).status_code == 422
    assert kitchen.post(url, json={"tub_count": 0}).status_code == 422
    assert view(kitchen)["batch_cooks"] == []


def test_a_full_meal_takes_no_more_tubs(
    kitchen: TestClient, cook: dict[str, Any], stuff: dict[str, int], slots: dict[str, int]
) -> None:
    for _ in range(plan_module.MOST_ITEMS_IN_MEAL - 1):
        plan_recipe(kitchen, stuff["dosa"], D2, slots["Dinner"])
    spot = {"date": D2.isoformat(), "slot_id": slots["Dinner"]}
    url = f"{API}/plan/items/{cook['item_id']}/batch"
    r = kitchen.post(url, json={"tub_count": 2, "placements": [spot, spot]})
    assert r.status_code == 422 and r.json()["code"] == "meal_full"
    assert kitchen.post(url, json={"tub_count": 1, "placements": [spot]}).status_code == 201


def test_only_a_planned_recipe_that_is_there_can_be_cooked_once(
    kitchen: TestClient, cook: dict[str, Any], stuff: dict[str, int], slots: dict[str, int]
) -> None:
    banana = kitchen.post(
        f"{API}/plan/items",
        json={"date": day(5), "slot_id": slots["Dinner"], "ingredient_id": stuff["banana"]},
    ).json()
    url = f"{API}/plan/items/{banana['item_id']}/batch"
    assert kitchen.post(url, json={"tub_count": 2}).json()["code"] == "not_a_recipe"
    with db_of(kitchen) as db:
        meal = db.get(Meal, cook["meal_id"])
        assert meal is not None
        meal.status = "cooked"
        db.commit()
    done = kitchen.post(f"{API}/plan/items/{cook['item_id']}/batch", json={"tub_count": 2})
    assert done.status_code == 409 and done.json()["code"] == "meal_done"


def test_a_meal_gets_one_batch_of_a_recipe(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    make(kitchen, cook["item_id"])
    again = kitchen.post(f"{API}/plan/items/{cook['item_id']}/batch", json={"tub_count": 2})
    assert again.status_code == 409 and again.json()["code"] == "batch_exists"


def test_the_batch_colour_is_the_next_one_free_nearby(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    colours = []
    for n, name in enumerate(("biryani", "dosa", "chutney")):
        meal = plan_recipe(kitchen, stuff[name], D1 + timedelta(days=n), slots["Dinner"])
        make(kitchen, meal["item_id"], tub_count=1, pattern="pick")
    for b in view(kitchen)["batch_cooks"]:
        colours.append(b["colour"])
    assert colours == ["purple", "amber", "green"]


def test_a_retry_with_the_same_key_makes_one_batch(
    kitchen: TestClient, cook: dict[str, Any]
) -> None:
    url, body = f"{API}/plan/items/{cook['item_id']}/batch", {"tub_count": 2}
    first = kitchen.post(url, json=body, headers={"Idempotency-Key": "cook-1"})
    again = kitchen.post(url, json=body, headers={"Idempotency-Key": "cook-1"})
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["batch_id"] == first.json()["batch_id"]
    assert len(view(kitchen)["batch_cooks"]) == 1


# --- Undo of making a batch -----------------------------------------------------------------------


def test_undo_of_cooking_once_takes_back_the_batch_the_tubs_and_their_meals(
    kitchen: TestClient, cook: dict[str, Any]
) -> None:
    before = shape(kitchen)
    made = make(kitchen, cook["item_id"])
    assert shape(kitchen) != before
    assert undo(kitchen, made)["result"] == "done"
    assert shape(kitchen) == before
    assert view(kitchen)["batch_cooks"] == [] and view(kitchen)["tubs"] == []
    with db_of(kitchen) as db:
        assert db.scalar(select(func.count(Tub.id))) == 0


def test_undo_of_cooking_once_says_partly_when_a_tub_meal_was_cooked_since(
    kitchen: TestClient, cook: dict[str, Any]
) -> None:
    made = make(kitchen, cook["item_id"])
    meal = next(m for m in view(kitchen)["meals"] if m["date"] == day(1))
    with db_of(kitchen) as db:
        row = db.get(Meal, meal["id"])
        assert row is not None
        row.status = "cooked"
        db.commit()
    assert undo(kitchen, made)["result"] == "partly"
    # The cooked meal keeps its tub, so its batch stays too.
    assert len(view(kitchen)["tubs"]) >= 1


# --- Tubs: placing, removing, whose, use-by, freezer ---------------------------------------------


def test_a_tub_left_can_be_placed_moved_and_sent_back_with_undo(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    make(kitchen, cook["item_id"], tub_count=2, pattern="pick")
    left = kitchen.get(f"{API}/plan/tubs-left").json()
    assert [(t["number"], t["tub_count"], t["recipe_name"]) for t in left["tubs"]] == [
        (1, 2, "Veg biryani"),
        (2, 2, "Veg biryani"),
    ]
    tub = left["tubs"][0]["id"]
    put = kitchen.post(
        f"{API}/plan/tubs/{tub}/place", json={"date": day(1), "slot_id": slots["Lunch"]}
    )
    assert put.status_code == 200, put.text
    assert where_tubs_are(kitchen, slots)[0] == (1, day(1), "Lunch")
    assert len(kitchen.get(f"{API}/plan/tubs-left").json()["tubs"]) == 1
    # Placing a tub that is in a meal already moves it.
    moved = kitchen.post(
        f"{API}/plan/tubs/{tub}/place", json={"date": day(2), "slot_id": slots["Dinner"]}
    )
    assert moved.status_code == 200
    assert where_tubs_are(kitchen, slots)[0] == (1, day(2), "Dinner")
    assert [m["date"] for m in view(kitchen)["meals"]] == [D1.isoformat(), day(2)]
    # Undo of the move puts it back where it was.
    assert undo(kitchen, moved.json())["result"] == "done"
    assert where_tubs_are(kitchen, slots)[0] == (1, day(1), "Lunch")
    # Taking it out of the meal sends it back to tubs left, and Undo puts it back.
    item = next(i for m in view(kitchen)["meals"] for i in m["items"] if i["tub_id"] == tub)
    out = kitchen.delete(f"{API}/plan/items/{item['id']}").json()
    assert out["change"]["summary"].startswith("Put Veg biryani tub back in tubs left from")
    assert len(kitchen.get(f"{API}/plan/tubs-left").json()["tubs"]) == 2
    assert undo(kitchen, out)["result"] == "done"
    assert where_tubs_are(kitchen, slots)[0] == (1, day(1), "Lunch")
    # Undo of placing the other tub leaves it in tubs left.
    other = left["tubs"][1]["id"]
    placed = kitchen.post(
        f"{API}/plan/tubs/{other}/place", json={"date": day(3), "slot_id": slots["Lunch"]}
    )
    assert where_tubs_are(kitchen, slots)[1] == (2, day(3), "Lunch")
    assert undo(kitchen, placed.json())["result"] == "done"
    assert where_tubs_are(kitchen, slots)[1] == (2, None, "fridge")
    assert len(kitchen.get(f"{API}/plan/tubs-left").json()["tubs"]) == 1


def test_a_tub_added_to_a_full_meal_or_a_far_day_is_refused(
    kitchen: TestClient, cook: dict[str, Any], stuff: dict[str, int], slots: dict[str, int]
) -> None:
    make(kitchen, cook["item_id"], tub_count=1, pattern="pick")
    tub = kitchen.get(f"{API}/plan/tubs-left").json()["tubs"][0]["id"]
    for _ in range(plan_module.MOST_ITEMS_IN_MEAL):
        plan_recipe(kitchen, stuff["dosa"], D2, slots["Dinner"])
    url = f"{API}/plan/tubs/{tub}/place"
    full = kitchen.post(url, json={"date": D2.isoformat(), "slot_id": slots["Dinner"]})
    assert full.status_code == 422 and full.json()["code"] == "meal_full"
    far = kitchen.post(url, json={"date": "2090-01-01", "slot_id": slots["Dinner"]})
    assert far.json()["code"] == "bad_day"


def test_whose_tub_and_its_use_by_can_be_changed_with_undo(
    kitchen: TestClient, cook: dict[str, Any], wren: int
) -> None:
    make(kitchen, cook["item_id"], tub_count=1, pattern="pick")
    tub = view(kitchen)["tubs"][0]
    url = f"{API}/plan/tubs/{tub['id']}"
    whose = kitchen.patch(url, json={"member_login_id": wren})
    assert whose.status_code == 200 and "Wren" in whose.json()["change"]["summary"]
    assert view(kitchen)["tubs"][0]["member_login_id"] == wren
    again = kitchen.patch(url, json={"member_login_id": wren})
    assert again.json()["change"] is None
    nobody = kitchen.patch(url, json={"member_login_id": None})
    assert view(kitchen)["tubs"][0]["member_login_id"] is None
    assert nobody.json()["change"]["summary"].endswith("nobody’s in particular")
    new_day = (D1 + timedelta(days=9)).isoformat()
    late = kitchen.patch(url, json={"use_by": new_day})
    assert view(kitchen)["tubs"][0]["use_by"] == new_day
    assert undo(kitchen, late.json())["result"] == "done"
    assert view(kitchen)["tubs"][0]["use_by"] == tub["use_by"]
    assert undo(kitchen, whose.json())["result"] == "done"
    assert kitchen.patch(url, json={}).status_code == 422


def test_a_tubs_use_by_cant_be_before_its_cook_day(
    kitchen: TestClient, cook: dict[str, Any]
) -> None:
    """cabledrawer 29 Oct: a tub's use-by can't be set before its cook date."""
    make(kitchen, cook["item_id"], tub_count=1, pattern="pick")
    tub = view(kitchen)["tubs"][0]
    url = f"{API}/plan/tubs/{tub['id']}"
    early = kitchen.patch(url, json={"use_by": (D1 - timedelta(days=1)).isoformat()})
    assert early.status_code == 422
    assert early.json()["code"] == "use_by_before_cook_day"
    assert view(kitchen)["tubs"][0]["use_by"] == tub["use_by"]
    same_day = kitchen.patch(url, json={"use_by": D1.isoformat()})
    assert same_day.status_code == 200
    assert view(kitchen)["tubs"][0]["use_by"] == D1.isoformat()


def test_to_freezer_takes_the_tub_out_of_its_meal_and_sets_the_freezer_use_by(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    make(kitchen, cook["item_id"], tub_count=2)
    tub = view(kitchen)["tubs"][0]
    frozen = kitchen.post(f"{API}/plan/tubs/{tub['id']}/freezer")
    assert frozen.status_code == 200, frozen.text
    now = view(kitchen)["tubs"][0]
    assert now["place_kind"] == "freezer"
    assert now["use_by"] != tub["use_by"] and now["use_by"] > tub["use_by"]
    assert [m["date"] for m in view(kitchen)["meals"]].count(day(1)) == 1
    # Numbered in date order (F50): the tub still in a meal is 1, the one in no meal is last.
    assert where_tubs_are(kitchen, slots)[0] == (2, None, "freezer")
    twice = kitchen.post(f"{API}/plan/tubs/{tub['id']}/freezer")
    assert twice.status_code == 409 and twice.json()["code"] == "already_frozen"
    assert undo(kitchen, frozen.json())["result"] == "done"
    assert where_tubs_are(kitchen, slots)[0] == (1, day(1), "Lunch")
    assert view(kitchen)["tubs"][0]["use_by"] == tub["use_by"]
    assert view(kitchen)["tubs"][0]["place_kind"] == "fridge"


def test_deleting_a_batch_takes_its_tubs_and_places_and_undo_brings_them_back(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    made = make(kitchen, cook["item_id"])
    before_tubs = [t["id"] for t in view(kitchen)["tubs"]]
    before = shape(kitchen)
    gone = kitchen.delete(f"{API}/plan/batches/{made['batch_id']}")
    assert gone.status_code == 200, gone.text
    assert view(kitchen)["tubs"] == [] and view(kitchen)["batch_cooks"] == []
    assert shape(kitchen) == [(D1.isoformat(), slots["Dinner"], ["Veg biryani"])]
    assert undo(kitchen, gone.json())["result"] == "done"
    assert [t["id"] for t in view(kitchen)["tubs"]] == before_tubs
    assert shape(kitchen) == before
    assert view(kitchen)["batch_cooks"][0]["cook_meal_id"] == cook["meal_id"]


def test_deleting_a_batch_with_a_tub_in_a_meal_that_was_cooked_is_refused(
    kitchen: TestClient, cook: dict[str, Any]
) -> None:
    made = make(kitchen, cook["item_id"])
    meal = next(m for m in view(kitchen)["meals"] if m["date"] == day(1))
    with db_of(kitchen) as db:
        row = db.get(Meal, meal["id"])
        assert row is not None
        row.status = "cooked"
        db.commit()
    r = kitchen.delete(f"{API}/plan/batches/{made['batch_id']}")
    assert r.status_code == 409 and r.json()["code"] == "meal_done"
    assert len(view(kitchen)["tubs"]) == 4


def test_a_recipe_deleted_for_good_leaves_the_batch_and_its_tubs_by_name(
    kitchen: TestClient, cook: dict[str, Any], stuff: dict[str, int], slots: dict[str, int]
) -> None:
    make(kitchen, cook["item_id"])
    with db_of(kitchen) as db:
        db.execute(text("DELETE FROM recipe WHERE id = :i"), {"i": stuff["biryani"]})
        db.commit()
    plan = view(kitchen)
    assert plan["batch_cooks"][0]["recipe_name"] == "Veg biryani"
    assert plan["batch_cooks"][0]["recipe_id"] is None and len(plan["tubs"]) == 4
    cook_meal = next(m for m in plan["meals"] if m["date"] == D1.isoformat())
    assert cook_meal["items"][0]["kept_name"] == "Veg biryani"
    # The tubs can still be moved, and the batch taken off, by its kept name.
    tub = plan["tubs"][0]["id"]
    put = kitchen.post(
        f"{API}/plan/tubs/{tub}/place", json={"date": day(4), "slot_id": slots["Lunch"]}
    )
    assert put.status_code == 200


# --- "Leftovers here" makes a tub -----------------------------------------------------------------


def _leftovers(client: TestClient, item_id: int, day_: date, slot: int) -> dict[str, Any]:
    r = client.post(
        f"{API}/plan/items/{item_id}/move",
        # Cook more: the older one-day route says "No portions left" unless told what to do.
        json={
            "date": day_.isoformat(),
            "slot_id": slot,
            "mode": "leftovers",
            "if_none_left": "cook_more",
        },
    )
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def test_leftovers_here_makes_a_tub_of_a_batch_made_on_the_spot(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    before = shape(kitchen)
    made = _leftovers(kitchen, cook["item_id"], D2, slots["Lunch"])
    plan = view(kitchen)
    assert [(b["recipe_name"], b["tub_count"], b["pattern"]) for b in plan["batch_cooks"]] == [
        ("Veg biryani", 1, "pick")
    ]
    assert plan["batch_cooks"][0]["cook_meal_id"] == cook["meal_id"]
    assert plan["batch_cooks"][0]["cooked_on"] == D1.isoformat()
    assert where_tubs_are(kitchen, slots) == [(1, D2.isoformat(), "Lunch")]
    # The cook meal stays as it was; nothing was copied.
    assert [i["kind"] for m in plan["meals"] for i in m["items"]] == ["recipe", "tub"]
    assert plan["tubs"][0]["use_by"] == (D1 + timedelta(days=3)).isoformat()
    assert undo(kitchen, made)["result"] == "done"
    assert shape(kitchen) == before
    assert view(kitchen)["batch_cooks"] == [] and view(kitchen)["tubs"] == []


def test_leftovers_again_reuses_the_batch_and_a_spare_tub_first(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    _leftovers(kitchen, cook["item_id"], D2, slots["Lunch"])
    second = _leftovers(kitchen, cook["item_id"], D2, slots["Dinner"])
    plan = view(kitchen)
    assert len(plan["batch_cooks"]) == 1 and plan["batch_cooks"][0]["tub_count"] == 2
    assert [t["number"] for t in plan["tubs"]] == [1, 2]
    assert undo(kitchen, second)["result"] == "done"
    plan = view(kitchen)
    assert plan["batch_cooks"][0]["tub_count"] == 1 and len(plan["tubs"]) == 1
    # A tub sent back to tubs left is the spare the next leftovers use.
    item = next(i for m in plan["meals"] for i in m["items"] if i["tub_id"])
    kitchen.delete(f"{API}/plan/items/{item['id']}")
    _leftovers(kitchen, cook["item_id"], D3, slots["Lunch"])
    plan = view(kitchen)
    assert len(plan["tubs"]) == 1 and plan["batch_cooks"][0]["tub_count"] == 1


def test_leftovers_of_a_meal_with_several_recipes_makes_a_tub_of_each(
    kitchen: TestClient, stuff: dict[str, int], slots: dict[str, int]
) -> None:
    a = plan_recipe(kitchen, stuff["dosa"], D1, slots["Dinner"])
    plan_recipe(kitchen, stuff["chutney"], D1, slots["Dinner"])
    banana = {"date": D1.isoformat(), "slot_id": slots["Dinner"], "ingredient_id": stuff["banana"]}
    kitchen.post(f"{API}/plan/items", json=banana)
    r = kitchen.post(
        f"{API}/plan/meals/{a['meal_id']}/move",
        json={"date": D2.isoformat(), "slot_id": slots["Lunch"], "mode": "leftovers"},
    )
    assert r.status_code == 200, r.text
    plan = view(kitchen)
    assert sorted(b["recipe_name"] for b in plan["batch_cooks"]) == ["Coconut chutney", "Dosa"]
    lunch = next(m for m in plan["meals"] if m["date"] == D2.isoformat())
    assert sorted(i["kind"] for i in lunch["items"]) == ["ingredient", "tub", "tub"]
    assert undo(kitchen, r.json())["result"] == "done"
    assert view(kitchen)["batch_cooks"] == []
    assert [m["date"] for m in view(kitchen)["meals"]] == [D1.isoformat()]


def test_a_tub_is_never_copied_as_leftovers(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    make(kitchen, cook["item_id"], tub_count=1)
    meal = next(m for m in view(kitchen)["meals"] if m["date"] == day(1))
    tub_item = meal["items"][0]["id"]
    r = kitchen.post(
        f"{API}/plan/items/{tub_item}/move",
        json={"date": day(5), "slot_id": slots["Lunch"], "mode": "leftovers"},
    )
    assert r.status_code == 422 and r.json()["code"] == "tub_once"
    only_tubs = kitchen.post(
        f"{API}/plan/meals/{meal['id']}/move",
        json={"date": day(5), "slot_id": slots["Lunch"], "mode": "leftovers"},
    )
    assert only_tubs.json()["code"] == "nothing_to_copy"


def test_a_batch_holds_at_most_the_most_tubs_and_a_day_the_most_batches(
    kitchen: TestClient, cook: dict[str, Any], stuff: dict[str, int], slots: dict[str, int]
) -> None:
    with db_of(kitchen) as db:
        household = db.get(Household, 1)
        assert household is not None
        household.tub_fridge_days = 30  # so the days below are before the use-by
        db.commit()
    days = [D1 + timedelta(days=n) for n in range(1, 14)]
    for d in days[: batches_module.MOST_TUBS_IN_BATCH]:
        _leftovers(kitchen, cook["item_id"], d, slots["Lunch"])
    full = kitchen.post(
        f"{API}/plan/items/{cook['item_id']}/move",
        json={
            "date": days[-1].isoformat(),
            "slot_id": slots["Lunch"],
            "mode": "leftovers",
            "if_none_left": "cook_more",
        },
    )
    assert full.status_code == 422 and full.json()["code"] == "batch_full"
    # Ten batches cooked on one day is the most.
    other = D1 + timedelta(days=20)
    with db_of(kitchen) as db:
        for n in range(batches_module.MOST_BATCHES_A_DAY):
            db.add(BatchCook(household_id=1, recipe_name=f"R{n}", cooked_on=other, tub_count=1))
        db.commit()
    meal = plan_recipe(kitchen, stuff["dosa"], other, slots["Dinner"])
    r = kitchen.post(f"{API}/plan/items/{meal['item_id']}/batch", json={"tub_count": 1})
    assert r.status_code == 422 and r.json()["code"] == "too_many_batches"


def test_undo_of_a_deleted_batch_keeps_to_the_days_cap(
    kitchen: TestClient, cook: dict[str, Any]
) -> None:
    """Delete a batch, fill the day to the cap, then Undo: the day would have one too many."""
    made = make(kitchen, cook["item_id"])
    gone = kitchen.delete(f"{API}/plan/batches/{made['batch_id']}")
    assert gone.status_code == 200, gone.text
    with db_of(kitchen) as db:
        for n in range(batches_module.MOST_BATCHES_A_DAY):
            db.add(BatchCook(household_id=1, recipe_name=f"R{n}", cooked_on=D1, tub_count=1))
        db.commit()
    r = kitchen.post(f"{API}/changes/{gone.json()['change']['id']}/undo")
    assert r.status_code == 422 and r.json()["code"] == "too_many_batches"
    with db_of(kitchen) as db:
        on_d1 = db.scalar(select(func.count(BatchCook.id)).where(BatchCook.cooked_on == D1))
    assert on_d1 == batches_module.MOST_BATCHES_A_DAY


# --- Fill from freezer first ----------------------------------------------------------------------


def test_fill_from_freezer_puts_the_soonest_tub_on_each_empty_day_with_undo(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    make(kitchen, cook["item_id"], tub_count=3, pattern="pick", extras_to_freezer=True)
    before = shape(kitchen)
    body = {"from": day(0), "to": day(3)}
    filled = kitchen.post(f"{API}/plan/fill-from-freezer", json=body)
    assert filled.status_code == 200, filled.text
    assert where_tubs_are(kitchen, slots) == [
        (1, day(1), "Dinner"),
        (2, day(2), "Dinner"),
        (3, day(3), "Dinner"),
    ]
    again = kitchen.post(f"{API}/plan/fill-from-freezer", json=body)
    assert again.json()["change"] is None
    assert undo(kitchen, filled.json())["result"] == "done"
    assert shape(kitchen) == before
    bad = kitchen.post(f"{API}/plan/fill-from-freezer", json={"from": day(3), "to": day(0)})
    assert bad.json()["code"] == "bad_range"


def test_fill_from_freezer_leaves_out_days_too_far_ahead_to_plan(
    kitchen: TestClient,
    cook: dict[str, Any],
    slots: dict[str, int],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Month's grid runs into next month: days past the last plannable one are skipped, not a
    refusal of the whole fill."""
    make(kitchen, cook["item_id"], tub_count=3, pattern="pick", extras_to_freezer=True)
    # Today moves so that day 2 is the last day that can be planned.
    now = D1 + timedelta(days=2) - timedelta(days=plan_module.DAYS_AHEAD)
    monkeypatch.setattr(plan_module, "today", lambda _household: now)
    monkeypatch.setattr(batches_module, "today", lambda _household: now)
    filled = kitchen.post(f"{API}/plan/fill-from-freezer", json={"from": day(0), "to": day(3)})
    assert filled.status_code == 200, filled.text
    assert where_tubs_are(kitchen, slots) == [
        (1, day(1), "Dinner"),
        (2, day(2), "Dinner"),
        (3, None, "freezer"),
    ]


# --- The plan under SQLite's limit ---------------------------------------------------------------


def test_the_plan_asks_about_batches_and_tubs_with_subqueries_not_lists(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    """With SQLite allowed only a few values per query, a week with many batches still reads,
    and so does a meal holding many tubs, recipes and ingredients (none of their ids go in as a
    list)."""
    make(kitchen, cook["item_id"])
    with db_of(kitchen) as db:
        # Day 5's lunch: past the four tubs the batch above placed.
        meal = Meal(household_id=1, day=D1 + timedelta(days=5), slot_id=slots["Lunch"])
        db.add(meal)
        db.flush()
        position = 0
        for n in range(30):
            batch = BatchCook(
                household_id=1, recipe_name=f"B{n}", cooked_on=D1, tub_count=12, pattern="pick"
            )
            db.add(batch)
            db.flush()
            batch_tubs = [Tub(household_id=1, batch_id=batch.id, use_by=D2) for _ in range(12)]
            db.add_all(batch_tubs)
            db.flush()
            # Straight into the database, past the 20-a-meal cap, to go well over 60 ids.
            if n < 6:
                for tub in batch_tubs:
                    db.add(
                        MealItem(household_id=1, meal_id=meal.id, position=position, tub_id=tub.id)
                    )
                    position += 1
        for n in range(70):
            recipe = add_recipe(db, 1, f"R{n}")
            food = add_food(db, 1, f"F{n}")
            db.add(
                MealItem(household_id=1, meal_id=meal.id, position=position, recipe_id=recipe.id)
            )
            db.add(
                MealItem(household_id=1, meal_id=meal.id, position=position + 1, food_id=food.id)
            )
            position += 2
        db.commit()
    import sqlite3

    from sqlalchemy import event

    engine = kitchen.app.state.sessionmaker.kw["bind"]

    def small(dbapi: Any, _record: Any, *_: Any) -> None:
        dbapi.setlimit(sqlite3.SQLITE_LIMIT_VARIABLE_NUMBER, 60)

    event.listen(engine, "checkout", small)
    try:
        # 31 batches of 12 tubs: well over 60 ids, if they went in as a list.
        plan = view(kitchen)
    finally:
        event.remove(engine, "checkout", small)
    assert len(plan["batch_cooks"]) == 31 and len(plan["tubs"]) == 4 + 360
    lunch = next(m for m in plan["meals"] if m["date"] == day(5) and m["slot_id"] == slots["Lunch"])
    assert len(lunch["items"]) == 72 + 140


# --- Another household's ids ---------------------------------------------------------------------


def test_another_households_ids_get_404_on_every_new_route(
    kitchen: TestClient,
    neighbour: TestClient,
    cook: dict[str, Any],
    stuff: dict[str, int],
    slots: dict[str, int],
) -> None:
    made = make(kitchen, cook["item_id"])
    tub = view(kitchen)["tubs"][0]["id"]
    item = cook["item_id"]
    body = {"tub_count": 2, "pattern": "pick"}
    theirs = slot_ids(kitchen, 2)
    spot = {"date": day(6), "slot_id": slots["Lunch"]}
    their_spot = {"date": day(6), "slot_id": theirs["Lunch"]}
    assert neighbour.post(f"{API}/plan/items/{item}/batch", json=body).status_code == 404
    assert neighbour.post(f"{API}/plan/items/{item}/batch/preview", json=body).status_code == 404
    assert neighbour.delete(f"{API}/plan/batches/{made['batch_id']}").status_code == 404
    assert neighbour.post(f"{API}/plan/tubs/{tub}/place", json=spot).status_code == 404
    assert neighbour.patch(f"{API}/plan/tubs/{tub}", json={"use_by": day(8)}).status_code == 404
    assert neighbour.post(f"{API}/plan/tubs/{tub}/freezer").status_code == 404
    # My tub, their slot; my batch, their login.
    assert kitchen.post(f"{API}/plan/tubs/{tub}/place", json=their_spot).status_code == 404
    other_item = plan_recipe(kitchen, stuff["dosa"], D3 + timedelta(1), slots["Dinner"])
    placements = [{"date": their_spot["date"], "slot_id": their_spot["slot_id"]}]
    r = kitchen.post(
        f"{API}/plan/items/{other_item['item_id']}/batch",
        json={"tub_count": 1, "placements": placements},
    )
    assert r.status_code == 404
    with db_of(kitchen) as db:
        db.add(
            Login(
                household_id=2,
                username="their-cook",
                name="Their cook",
                password_hash=hash_password("x" * 20),
                role="member",
            )
        )
        db.commit()
        their_login = db.scalar(select(Login.id).where(Login.username == "their-cook"))
    r = kitchen.post(
        f"{API}/plan/items/{other_item['item_id']}/batch",
        json={"tub_count": 1, "member_login_ids": [their_login]},
    )
    assert r.status_code == 404
    assert (
        kitchen.patch(f"{API}/plan/tubs/{tub}", json={"member_login_id": their_login}).status_code
        == 404
    )
    # The neighbour sees none of my tubs, people or changes, and cannot undo mine.
    assert neighbour.get(f"{API}/plan/tubs-left").json()["tubs"] == []
    seen = [p["name"] for p in neighbour.get(f"{API}/plan/people").json()]
    assert seen == ["Neighbour", "Their cook"]  # their own household's people, none of mine
    assert neighbour.post(f"{API}/changes/{made['change']['id']}/undo").status_code == 404
    assert (
        neighbour.post(f"{API}/plan/fill-from-freezer", json={"from": day(0), "to": day(3)}).json()[
            "change"
        ]
        is None
    )
    assert len(view(kitchen)["tubs"]) == 4


def test_the_new_routes_need_signing_in(client: TestClient) -> None:
    body = {"tub_count": 1}
    assert client.post(f"{API}/plan/items/1/batch", json=body).status_code == 401
    assert client.post(f"{API}/plan/items/1/batch/preview", json=body).status_code == 401
    assert client.delete(f"{API}/plan/batches/1").status_code == 401
    assert client.get(f"{API}/plan/tubs-left").status_code == 401
    assert client.get(f"{API}/plan/people").status_code == 401
    assert client.post(f"{API}/plan/tubs/1/freezer").status_code == 401


def test_batch_changes_are_in_recent_changes_with_their_undo(
    kitchen: TestClient, cook: dict[str, Any]
) -> None:
    made = make(kitchen, cook["item_id"])
    listed = kitchen.get(f"{API}/changes").json()["changes"]
    mine = next(c for c in listed if c["id"] == made["change"]["id"])
    assert mine["kind"] == "plan_batch" and mine["can_undo"] is True


# --- Never into the past, never before the cooking (F50, cabledrawer 28 Oct) --------------------------


def _after_cook_refused(r: Any) -> None:
    assert r.status_code == 422, r.text
    assert r.json()["code"] == "not_after_cook"


def test_leftovers_are_refused_before_or_at_the_cook_meal_and_in_the_past(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    url = f"{API}/plan/items/{cook['item_id']}/move"
    past = (date.today() - timedelta(days=1)).isoformat()
    for when, slot in (
        (past, "Lunch"),  # in the past
        (D1.isoformat(), "Lunch"),  # the cook day, before the cook meal (dinner)
        (D1 - timedelta(days=1), "Dinner"),  # the day before
    ):
        body = {"date": str(when), "slot_id": slots[slot], "mode": "leftovers"}
        _after_cook_refused(kitchen.post(url, json=body))
    assert view(kitchen)["tubs"] == []


def test_leftovers_of_a_whole_meal_follow_the_same_rule(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    body = {"date": D1.isoformat(), "slot_id": slots["Lunch"], "mode": "leftovers"}
    _after_cook_refused(kitchen.post(f"{API}/plan/meals/{cook['meal_id']}/move", json=body))
    assert view(kitchen)["batch_cooks"] == []


def test_cook_once_placements_are_refused_before_the_cook_meal(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    early = [{"date": D1.isoformat(), "slot_id": slots["Lunch"]}]
    for path in ("batch", "batch/preview"):
        r = kitchen.post(
            f"{API}/plan/items/{cook['item_id']}/{path}",
            json={"tub_count": 1, "pattern": "pick", "placements": early},
        )
        _after_cook_refused(r)
    past = [{"date": (date.today() - timedelta(days=1)).isoformat(), "slot_id": slots["Lunch"]}]
    r = kitchen.post(
        f"{API}/plan/items/{cook['item_id']}/batch",
        json={"tub_count": 1, "pattern": "pick", "placements": past},
    )
    _after_cook_refused(r)
    assert view(kitchen)["batch_cooks"] == []


def test_tubs_are_numbered_in_date_order(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    """Planned later first, then earlier: the earlier one is still tub 1; a tub left is last."""
    _leftovers(kitchen, cook["item_id"], D1 + timedelta(days=3), slots["Lunch"])
    _leftovers(kitchen, cook["item_id"], D1 + timedelta(days=1), slots["Dinner"])
    _leftovers(kitchen, cook["item_id"], D1 + timedelta(days=1), slots["Lunch"])
    assert [(n, d, s) for n, d, s in where_tubs_are(kitchen, slots)] == [
        (3, (D1 + timedelta(days=3)).isoformat(), "Lunch"),
        (2, (D1 + timedelta(days=1)).isoformat(), "Dinner"),
        (1, (D1 + timedelta(days=1)).isoformat(), "Lunch"),
    ]


# --- Dragging a COOK card moves the cooking (0.7 P3) ---------------------------------------------


def _move_meal(client: TestClient, meal_id: int, day_: str, slot: int) -> Any:
    return client.post(
        f"{API}/plan/meals/{meal_id}/move", json={"date": day_, "slot_id": slot, "mode": "move"}
    )


def _batch_row(kitchen: TestClient, batch_id: int) -> tuple[date, list[date]]:
    with db_of(kitchen) as db:
        batch = db.get(BatchCook, batch_id)
        assert batch is not None
        tubs = db.scalars(select(Tub).where(Tub.batch_id == batch_id).order_by(Tub.id))
        return batch.cooked_on, [t.use_by for t in tubs]


def test_moving_the_cook_meal_moves_the_cooking_across_a_week_and_back(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    made = make(kitchen, cook["item_id"])
    cooked_before, use_by_before = _batch_row(kitchen, made["batch_id"])
    assert cooked_before == D1
    moved = _move_meal(kitchen, cook["meal_id"], day(9), slots["Dinner"])  # a week and two days on
    assert moved.status_code == 200, moved.text
    cooked_after, use_by_after = _batch_row(kitchen, made["batch_id"])
    assert cooked_after == D1 + timedelta(days=9)
    # Every tub's use-by keeps its distance from the cook day.
    assert use_by_after == [u + timedelta(days=9) for u in use_by_before]
    # The week it moved to shows the batch (GET /plan finds batches by cook day).
    there = view(kitchen, D1 + timedelta(days=8), days=3)
    assert [b["id"] for b in there["batch_cooks"]] == [made["batch_id"]]
    assert there["batch_cooks"][0]["cooked_on"] == day(9)
    # And back, to before where it was.
    back = _move_meal(kitchen, cook["meal_id"], day(-2), slots["Dinner"])
    assert back.status_code == 200, back.text
    assert _batch_row(kitchen, made["batch_id"])[0] == D1 - timedelta(days=2)


def test_undo_of_moving_the_cook_meal_puts_the_dates_back_exactly(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    made = make(kitchen, cook["item_id"])
    # One tub has its own use-by, so "exactly" means more than the same distance.
    tub = view(kitchen)["tubs"][0]["id"]
    edited = kitchen.patch(f"{API}/plan/tubs/{tub}", json={"use_by": day(20)})
    assert edited.status_code == 200, edited.text
    before = _batch_row(kitchen, made["batch_id"])
    moved = _move_meal(kitchen, cook["meal_id"], day(5), slots["Dinner"])
    assert moved.status_code == 200, moved.text
    assert _batch_row(kitchen, made["batch_id"]) != before
    assert undo(kitchen, moved.json())["result"] == "done"
    assert _batch_row(kitchen, made["batch_id"]) == before


def test_a_batch_that_was_cooked_keeps_its_cook_day(
    kitchen: TestClient, cook: dict[str, Any], slots: dict[str, int]
) -> None:
    from mealwright.models import CookedRecord

    made = make(kitchen, cook["item_id"])
    with db_of(kitchen) as db:
        db.add(
            CookedRecord(
                household_id=1, batch_id=made["batch_id"], portions=4, snapshot={"name": "x"}
            )
        )
        db.commit()
    r = _move_meal(kitchen, cook["meal_id"], day(5), slots["Dinner"])
    assert r.status_code == 409 and r.json()["code"] == "already_cooked"
    assert "Undo “Cooked it” first." in r.json()["detail"]
    assert _batch_row(kitchen, made["batch_id"])[0] == D1


def test_moving_one_households_cook_meal_leaves_the_other_households_batch_alone(
    kitchen: TestClient,
    neighbour: TestClient,
    cook: dict[str, Any],
    slots: dict[str, int],
) -> None:
    made = make(kitchen, cook["item_id"])
    with db_of(kitchen) as db:
        theirs = db.scalars(select(BatchCook).where(BatchCook.household_id == 2)).all()
    assert theirs == []  # the neighbour has no batch yet
    assert neighbour.post(
        f"{API}/plan/meals/{cook['meal_id']}/move",
        json={"date": day(5), "slot_id": slots["Dinner"], "mode": "move"},
    ).status_code in (404, 422)
    assert _batch_row(kitchen, made["batch_id"])[0] == D1
