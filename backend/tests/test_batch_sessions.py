"""Batch cook sessions over the API (0.8 wave 6, B2; cabledrawer 28 Oct and 11 Nov): "Plan this
batch" sends each recipe through Cook once on the cook day, marked as one session; one change with
one Undo for the whole session; the Plan shows it; change and remove; every route against another
household's ids."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sync_kit import ok, person
from test_batch_suggest import recipe
from test_plan import db_of, slot_ids
from test_plan_writes import D1, plan_recipe, shape, undo, view
from test_recipes import food

from mealwright.models import BatchCook, BatchSession, Meal, MealItem, Tub

API = "/api/v1"


@pytest.fixture
def three(kitchen: TestClient) -> list[int]:
    onion = food(kitchen, "Onion")
    return [
        recipe(kitchen, "Chicken", [onion], ["Chop the onion.", "Marinate for 30 minutes."])["id"],
        recipe(kitchen, "Sambar", [onion], ["Chop the onion.", "Pressure cook for 3 whistles."])[
            "id"
        ],
        recipe(kitchen, "Keerai", [food(kitchen, "Spinach")], ["Fry the spinach."])["id"],
    ]


def body(kitchen: TestClient, ids: list[int], tubs: int = 2, **each: Any) -> dict[str, Any]:
    slots = slot_ids(kitchen)
    return {
        "date": D1.isoformat(),
        "slot_id": slots["Dinner"],
        "recipes": [{"recipe_id": i, "tub_count": tubs, "pattern": "dinners", **each} for i in ids],
    }


def make(kitchen: TestClient, ids: list[int], tubs: int = 2, **each: Any) -> dict[str, Any]:
    written: dict[str, Any] = ok(
        kitchen.post(f"{API}/batch-cook/sessions", json=body(kitchen, ids, tubs, **each)), 201
    )
    return written


def plan_changes(kitchen: TestClient) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = ok(kitchen.get(f"{API}/changes"))["changes"]
    return [c for c in changes if c["kind"].startswith("plan_")]


def counts(kitchen: TestClient) -> tuple[int, int, int, int, int]:
    with db_of(kitchen) as db:
        return tuple(  # type: ignore[return-value]
            db.scalar(select(func.count()).select_from(t)) or 0
            for t in (BatchSession, BatchCook, Tub, Meal, MealItem)
        )


def test_planning_a_batch_makes_one_session_with_each_recipe_cooked_once(
    kitchen: TestClient, three: list[int]
) -> None:
    written = make(kitchen, three)
    assert written["session_id"] and written["meal_id"]
    assert written["change"]["kind"] == "plan_batch_session"
    assert written["change"]["summary"] == (
        f"Planned a batch cook of 3 recipes for {D1:%a} {D1.day} {D1:%b}"
    )
    plan = view(kitchen)
    [session] = plan["batch_sessions"]
    assert session["id"] == written["session_id"] and session["cook_day"] == D1.isoformat()
    assert session["one_by_one_minutes"] and session["together_minutes"]
    assert session["together_minutes"] <= session["one_by_one_minutes"]
    assert session["start_day"] is None and session["start_time"] is None
    assert [b["recipe_name"] for b in plan["batch_cooks"]] == ["Chicken", "Sambar", "Keerai"]
    assert {b["session_id"] for b in plan["batch_cooks"]} == {session["id"]}
    assert len({b["colour"] for b in plan["batch_cooks"]}) == 3  # each in its own batch colour
    assert {b["tub_count"] for b in plan["batch_cooks"]} == {2}
    cook_meal = next(m for m in plan["meals"] if m["id"] == written["meal_id"])
    assert [i["recipe"]["name"] for i in cook_meal["items"]] == ["Chicken", "Sambar", "Keerai"]
    assert len(plan["tubs"]) == 6


def test_one_undo_takes_the_whole_session_away_and_a_second_makes_nothing_twice(
    kitchen: TestClient, three: list[int]
) -> None:
    before_counts, before = counts(kitchen), shape(kitchen)
    written = make(kitchen, three)
    assert counts(kitchen) != before_counts
    only_one = plan_changes(kitchen)
    assert len(only_one) == 1 and only_one[0]["can_undo"]
    undone = undo(kitchen, written)
    assert undone["change"]["kind"] == "undo"
    assert counts(kitchen) == before_counts and shape(kitchen) == before
    assert view(kitchen)["batch_sessions"] == []


def test_a_retry_with_the_same_key_makes_nothing_more(
    kitchen: TestClient, three: list[int]
) -> None:
    sent = {"Idempotency-Key": "batch-1"}
    first = kitchen.post(f"{API}/batch-cook/sessions", json=body(kitchen, three), headers=sent)
    after_first = counts(kitchen)
    again = kitchen.post(f"{API}/batch-cook/sessions", json=body(kitchen, three), headers=sent)
    assert first.status_code == 201 and again.status_code == 200
    assert again.json()["session_id"] == first.json()["session_id"]
    assert counts(kitchen) == after_first


def test_the_session_is_read_with_its_recipes_in_order(
    kitchen: TestClient, three: list[int]
) -> None:
    written = make(kitchen, three, tubs=3, extras_to_freezer=True)
    session = ok(kitchen.get(f"{API}/batch-cook/sessions/{written['session_id']}"))
    assert session["cook_day"] == D1.isoformat()
    assert [r["recipe_name"] for r in session["recipes"]] == ["Chicken", "Sambar", "Keerai"]
    assert [r["recipe_id"] for r in session["recipes"]] == three
    assert {r["tub_count"] for r in session["recipes"]} == {3}


def test_removing_the_session_is_one_undo(kitchen: TestClient, three: list[int]) -> None:
    before = counts(kitchen)
    written = make(kitchen, three)
    made = counts(kitchen), shape(kitchen)
    removed = ok(kitchen.delete(f"{API}/batch-cook/sessions/{written['session_id']}"))
    assert removed["change"]["kind"] == "plan_batch_session_removed"
    assert counts(kitchen) == before
    assert view(kitchen)["batch_sessions"] == []
    undo(kitchen, removed)
    assert (counts(kitchen), shape(kitchen)) == made
    assert [b["session_id"] for b in view(kitchen)["batch_cooks"]] == [written["session_id"]] * 3
    assert kitchen.get(f"{API}/batch-cook/sessions/{written['session_id']}").status_code == 200
    # And the session can be removed again, and then the first one undone with it gone.
    ok(kitchen.delete(f"{API}/batch-cook/sessions/{written['session_id']}"))
    assert counts(kitchen) == before


def test_changing_the_session_replaces_it_in_one_change_and_one_undo(
    kitchen: TestClient, three: list[int]
) -> None:
    fourth = recipe(kitchen, "Rasam", [food(kitchen, "Tomato")])["id"]
    written = make(kitchen, three)
    first = counts(kitchen), shape(kitchen)
    new = body(kitchen, [three[0], fourth], tubs=1)
    changed = ok(kitchen.put(f"{API}/batch-cook/sessions/{written['session_id']}", json=new))
    assert changed["change"]["kind"] == "plan_batch_session_changed"
    assert changed["session_id"] != written["session_id"]
    plan = view(kitchen)
    assert [b["recipe_name"] for b in plan["batch_cooks"]] == ["Chicken", "Rasam"]
    assert [s["id"] for s in plan["batch_sessions"]] == [changed["session_id"]]
    assert kitchen.get(f"{API}/batch-cook/sessions/{written['session_id']}").status_code == 404
    undo(kitchen, changed)
    assert (counts(kitchen), shape(kitchen)) == first
    assert [s["id"] for s in view(kitchen)["batch_sessions"]] == [written["session_id"]]
    assert [b["recipe_name"] for b in view(kitchen)["batch_cooks"]] == [
        "Chicken",
        "Sambar",
        "Keerai",
    ]


def test_taking_the_last_recipe_off_one_by_one_takes_the_session_with_it(
    kitchen: TestClient, three: list[int]
) -> None:
    written = make(kitchen, three[:2])
    batch_ids = [b["id"] for b in view(kitchen)["batch_cooks"]]
    ok(kitchen.delete(f"{API}/plan/batches/{batch_ids[0]}"))
    assert [s["id"] for s in view(kitchen)["batch_sessions"]] == [written["session_id"]]
    last = ok(kitchen.delete(f"{API}/plan/batches/{batch_ids[1]}"))
    assert view(kitchen)["batch_sessions"] == []
    undo(kitchen, last)  # the session comes back with its last recipe
    assert [s["id"] for s in view(kitchen)["batch_sessions"]] == [written["session_id"]]


def test_a_cooked_recipe_keeps_the_session(kitchen: TestClient, three: list[int]) -> None:
    from mealwright.models import CookedRecord

    written = make(kitchen, three)
    with db_of(kitchen) as db:
        batch = db.scalars(select(BatchCook).order_by(BatchCook.id)).first()
        assert batch is not None
        db.add(
            CookedRecord(
                household_id=1,
                batch_id=batch.id,
                recipe_id=batch.recipe_id,
                portions=3,
                snapshot={},
            )
        )
        db.commit()
    gone = kitchen.delete(f"{API}/batch-cook/sessions/{written['session_id']}")
    assert gone.status_code == 409 and gone.json()["code"] == "already_cooked"
    swapped = kitchen.put(
        f"{API}/batch-cook/sessions/{written['session_id']}", json=body(kitchen, three[:2])
    )
    assert swapped.status_code == 409
    assert len(view(kitchen)["batch_sessions"]) == 1


# --- What is refused ----------------------------------------------------------------------------


def test_two_to_four_different_recipes(kitchen: TestClient, three: list[int]) -> None:
    fourth = recipe(kitchen, "D", [food(kitchen, "D")])["id"]
    fifth = recipe(kitchen, "E", [food(kitchen, "E")])["id"]
    one = kitchen.post(f"{API}/batch-cook/sessions", json=body(kitchen, three[:1]))
    assert one.status_code == 422
    five = kitchen.post(f"{API}/batch-cook/sessions", json=body(kitchen, [*three, fourth, fifth]))
    assert five.status_code == 422
    twice = kitchen.post(f"{API}/batch-cook/sessions", json=body(kitchen, [three[0], three[0]]))
    assert twice.status_code == 422 and twice.json()["code"] == "same_recipe_twice"
    assert counts(kitchen)[0] == 0
    assert (
        kitchen.post(f"{API}/batch-cook/sessions", json=body(kitchen, [*three, fourth])).status_code
        == 201
    )


def test_nothing_is_half_made_when_the_second_recipe_is_refused(
    kitchen: TestClient, three: list[int]
) -> None:
    before = counts(kitchen), shape(kitchen)
    bad = body(kitchen, three[:2])
    bad["recipes"][1]["tub_count"] = 99  # more than a batch holds
    assert kitchen.post(f"{API}/batch-cook/sessions", json=bad).status_code == 422
    other = body(kitchen, three[:2])
    other["recipes"][1]["placements"] = [{"date": "2020-01-01", "slot_id": other["slot_id"]}] * 2
    assert kitchen.post(f"{API}/batch-cook/sessions", json=other).status_code in (400, 409, 422)
    assert (counts(kitchen), shape(kitchen)) == before
    assert plan_changes(kitchen) == []


def test_a_removed_recipe_and_a_bad_day_are_refused(kitchen: TestClient, three: list[int]) -> None:
    ok(kitchen.delete(f"{API}/recipes/{three[2]}"))
    assert kitchen.post(f"{API}/batch-cook/sessions", json=body(kitchen, three)).status_code == 404
    late = body(kitchen, three[:2])
    late["date"] = (D1 + timedelta(days=5000)).isoformat()
    assert kitchen.post(f"{API}/batch-cook/sessions", json=late).status_code == 422


def test_hidden_batch_cook_refuses_the_session_routes(
    kitchen: TestClient, three: list[int]
) -> None:
    written = make(kitchen, three)
    ok(kitchen.patch(f"{API}/household", json={"batch_cook": False}))
    for response in (
        kitchen.post(f"{API}/batch-cook/sessions", json=body(kitchen, three)),
        kitchen.post(f"{API}/batch-cook/sessions/preview", json={**body(kitchen, three[:1])}),
        kitchen.get(f"{API}/batch-cook/sessions/{written['session_id']}"),
        kitchen.put(
            f"{API}/batch-cook/sessions/{written['session_id']}", json=body(kitchen, three)
        ),
        kitchen.delete(f"{API}/batch-cook/sessions/{written['session_id']}"),
    ):
        assert response.status_code == 409 and response.json()["code"] == "batch_cook_hidden"
    # What was already planned stays on the Plan; taking it off waits until Batch cook is on again.
    assert len(view(kitchen)["batch_sessions"]) == 1
    ok(kitchen.patch(f"{API}/household", json={"batch_cook": True}))
    ok(kitchen.delete(f"{API}/batch-cook/sessions/{written['session_id']}"))


# --- The preview of each Cook once sheet -------------------------------------------------------


def test_the_preview_sees_the_meals_the_earlier_recipes_filled_and_saves_nothing(
    kitchen: TestClient, three: list[int]
) -> None:
    before = counts(kitchen), shape(kitchen)
    first = body(kitchen, three[:1], tubs=2)
    one = ok(kitchen.post(f"{API}/batch-cook/sessions/preview", json=first))
    assert one["recipe_name"] == "Chicken" and len(one["tubs"]) == 2
    two = body(kitchen, three[:2], tubs=2)
    second = ok(kitchen.post(f"{API}/batch-cook/sessions/preview", json=two))
    assert second["recipe_name"] == "Sambar" and second["cook_date"] == D1.isoformat()
    # The dinners the first recipe's tubs fill are taken, so the second's go to the next ones.
    assert {t["date"] for t in one["tubs"]} & {t["date"] for t in second["tubs"]} == set()
    assert (counts(kitchen), shape(kitchen)) == before
    assert plan_changes(kitchen) == []
    # And the saved session puts the tubs where the sheets showed them.
    written = make(kitchen, three[:2], tubs=2)
    by_batch = {
        b["recipe_name"]: sorted(t["id"] for t in view(kitchen)["tubs"] if t["batch_id"] == b["id"])
        for b in view(kitchen)["batch_cooks"]
    }
    assert written["session_id"] and all(len(v) == 2 for v in by_batch.values())
    placed = [
        (i["tub_id"], m["date"])
        for m in view(kitchen)["meals"]
        for i in m["items"]
        if i["kind"] == "tub"
    ]
    shown = [t["date"] for t in one["tubs"] + second["tubs"] if t["date"] is not None]
    assert sorted(d for _t, d in placed) == sorted(shown)


# --- Other households and members --------------------------------------------------------------


def test_another_households_ids_are_not_found_on_any_route(
    kitchen: TestClient, neighbour: TestClient, three: list[int]
) -> None:
    written = make(kitchen, three)
    sid = written["session_id"]
    theirs = recipe(neighbour, "Theirs", [food(neighbour, "Rice")])["id"]
    theirs_too = recipe(neighbour, "Theirs too", [food(neighbour, "Peas")])["id"]
    assert neighbour.get(f"{API}/batch-cook/sessions/{sid}").status_code == 404
    assert neighbour.delete(f"{API}/batch-cook/sessions/{sid}").status_code == 404
    mine = body(neighbour, [theirs, theirs_too])
    assert neighbour.put(f"{API}/batch-cook/sessions/{sid}", json=mine).status_code == 404
    # Their recipes in my session, my recipes in theirs, my slot in theirs: all not found.
    assert (
        kitchen.post(
            f"{API}/batch-cook/sessions", json=body(kitchen, [theirs, theirs_too])
        ).status_code
        == 404
    )
    assert (
        neighbour.post(f"{API}/batch-cook/sessions", json=body(neighbour, three[:2])).status_code
        == 404
    )
    mixed = body(neighbour, [theirs, theirs_too])
    mixed["slot_id"] = slot_ids(kitchen)["Dinner"]
    assert neighbour.post(f"{API}/batch-cook/sessions", json=mixed).status_code == 404
    preview = neighbour.post(f"{API}/batch-cook/sessions/preview", json=body(neighbour, three[:1]))
    assert preview.status_code == 404
    leak = body(kitchen, three[:2])
    leak["date"] = (D1 + timedelta(days=10)).isoformat()
    leak["recipes"][0]["member_login_ids"] = [2]
    assert kitchen.post(f"{API}/batch-cook/sessions", json=leak).status_code == 404
    assert len(view(kitchen)["batch_sessions"]) == 1
    assert view(neighbour)["batch_sessions"] == []
    assert (
        neighbour.get(f"{API}/plan", params={"from": D1.isoformat(), "to": D1.isoformat()}).json()[
            "batch_cooks"
        ]
        == []
    )


def test_any_signed_in_person_can_plan_a_batch(kitchen: TestClient, three: list[int]) -> None:
    wren = person(kitchen)
    made = wren.post(f"{API}/batch-cook/sessions", json=body(kitchen, three[:2]))
    assert made.status_code == 201
    assert wren.delete(f"{API}/batch-cook/sessions/{made.json()['session_id']}").status_code == 200


def test_signed_out_is_refused(client: TestClient) -> None:
    for call in (
        client.post(f"{API}/batch-cook/sessions", json={}),
        client.get(f"{API}/batch-cook/sessions/1"),
        client.put(f"{API}/batch-cook/sessions/1", json={}),
        client.delete(f"{API}/batch-cook/sessions/1"),
        client.post(f"{API}/batch-cook/sessions/preview", json={}),
    ):
        assert call.status_code in (401, 403)


def test_the_start_of_the_session_is_the_earliest_start_ahead_of_its_recipes(
    kitchen: TestClient,
) -> None:
    from mealwright.models import utcnow

    soak = recipe(
        kitchen,
        "Idli",
        [food(kitchen, "Rice")],
        ["Soak the rice for 8 hours.", "Steam for 15 minutes."],
    )["id"]
    other = recipe(kitchen, "Chutney", [food(kitchen, "Coconut")], ["Grind."])["id"]
    written = make(kitchen, [soak, other])
    with db_of(kitchen) as db:
        item = db.scalars(select(MealItem).where(MealItem.recipe_id == soak)).one()
        item.start_at = utcnow().replace(hour=4, minute=30, second=0, microsecond=0)
        db.commit()
    [session] = view(kitchen)["batch_sessions"]
    assert session["id"] == written["session_id"]
    assert session["start_day"] is not None and session["start_time"] is not None
    assert len(session["start_time"]) == 5


# --- Review round 1 (B2): the meal, the preview of a change, the savepoint ----------------------


def _meal_of(kitchen: TestClient, session_id: int) -> int:
    """The meal slot a session's recipes are planned in."""
    return int(ok(kitchen.get(f"{API}/batch-cook/sessions/{session_id}"))["slot_id"])


def _no_slot(kitchen: TestClient, ids: list[int], **extra: Any) -> dict[str, Any]:
    sent = body(kitchen, ids, **extra)
    del sent["slot_id"]
    return sent


def test_a_session_with_no_meal_named_goes_in_the_last_meal_with_no_recipe_that_day(
    kitchen: TestClient, three: list[int]
) -> None:
    slots = slot_ids(kitchen)
    # Nothing planned: the last meal that is on.
    first = ok(kitchen.post(f"{API}/batch-cook/sessions", json=_no_slot(kitchen, three[:2])), 201)
    assert _meal_of(kitchen, first["session_id"]) == slots["Dinner"]
    # Dinner now has recipes: the session goes in the next one up.
    undo(kitchen, first)
    plan_recipe(kitchen, three[2], D1, slots["Dinner"])
    second = ok(kitchen.post(f"{API}/batch-cook/sessions", json=_no_slot(kitchen, three[:2])), 201)
    assert _meal_of(kitchen, second["session_id"]) == slots["Lunch"]


def test_tubs_do_not_fill_a_meal_and_the_week_the_screen_loaded_does_not_matter(
    kitchen: TestClient, three: list[int]
) -> None:
    slots = slot_ids(kitchen)
    day = D1 + timedelta(days=30)  # a month away from anything the Plan has loaded
    # A batch cooked the day before, its tubs in lunch and dinner on the cook day.
    cooking = plan_recipe(kitchen, three[2], day - timedelta(days=1), slots["Dinner"])
    spread = {"tub_count": 2, "pattern": "lunch_dinner"}
    ok(kitchen.post(f"{API}/plan/items/{cooking['item_id']}/batch", json=spread), 201)
    meals = {m["slot_id"] for m in view(kitchen, day, 0)["meals"] if m["date"] == day.isoformat()}
    assert {slots["Lunch"], slots["Dinner"]} <= meals  # both hold tubs
    sent = _no_slot(kitchen, three[:2])
    sent["date"] = day.isoformat()
    made = ok(kitchen.post(f"{API}/batch-cook/sessions", json=sent), 201)
    assert _meal_of(kitchen, made["session_id"]) == slots["Dinner"]  # not Breakfast


def test_changing_a_session_keeps_its_meal_and_a_named_meal_wins(
    kitchen: TestClient, three: list[int]
) -> None:
    slots = slot_ids(kitchen)
    made = ok(kitchen.post(f"{API}/batch-cook/sessions", json=body(kitchen, three[:2])), 201)
    assert _meal_of(kitchen, made["session_id"]) == slots["Dinner"]
    # Something else is planned in Dinner now, so the rule alone would move the session.
    plan_recipe(kitchen, three[2], D1, slots["Dinner"])
    same = ok(
        kitchen.put(
            f"{API}/batch-cook/sessions/{made['session_id']}", json=_no_slot(kitchen, three[:2])
        )
    )
    assert _meal_of(kitchen, same["session_id"]) == slots["Dinner"]
    named = body(kitchen, three[:2])
    named["slot_id"] = slots["Lunch"]
    moved = ok(kitchen.put(f"{API}/batch-cook/sessions/{same['session_id']}", json=named))
    assert _meal_of(kitchen, moved["session_id"]) == slots["Lunch"]


def test_the_preview_of_a_change_is_what_the_change_saves(
    kitchen: TestClient, three: list[int]
) -> None:
    made = ok(kitchen.post(f"{API}/batch-cook/sessions", json=body(kitchen, three[:2])), 201)
    new = body(kitchen, three[:2], tubs=2)
    del new["slot_id"]
    # Without the session named, its own tubs fill the dinners the preview offers.
    blind = ok(kitchen.post(f"{API}/batch-cook/sessions/preview", json=new))
    seen = ok(
        kitchen.post(
            f"{API}/batch-cook/sessions/preview", json={**new, "session_id": made["session_id"]}
        )
    )
    assert [t["date"] for t in seen["tubs"]] != [t["date"] for t in blind["tubs"]]
    assert seen["cook_slot_id"] == _meal_of(kitchen, made["session_id"])
    changed = ok(kitchen.put(f"{API}/batch-cook/sessions/{made['session_id']}", json=new))
    plan = view(kitchen)
    last = max(
        (b for b in plan["batch_cooks"] if b["session_id"] == changed["session_id"]),
        key=lambda b: b["id"],
    )
    saved = sorted(t["id"] for t in plan["tubs"] if t["batch_id"] == last["id"])
    placed = sorted(m["date"] for m in plan["meals"] for i in m["items"] if i["tub_id"] in saved)
    assert placed == sorted(t["date"] for t in seen["tubs"] if t["date"])


def test_a_preview_of_a_change_names_only_the_households_own_session(
    kitchen: TestClient, neighbour: TestClient, three: list[int]
) -> None:
    made = ok(kitchen.post(f"{API}/batch-cook/sessions", json=body(kitchen, three[:2])), 201)
    theirs = recipe(neighbour, "Theirs", [food(neighbour, "Rice")])["id"]
    sent = body(neighbour, [theirs])
    sent["session_id"] = made["session_id"]
    assert neighbour.post(f"{API}/batch-cook/sessions/preview", json=sent).status_code == 404


def test_a_preview_saves_nothing_even_when_the_session_is_committed_after_it(
    kitchen: TestClient, three: list[int]
) -> None:
    """The savepoint is what keeps the preview from saving: commit after it and count."""
    from mealwright import batch_sessions
    from mealwright.api.v1.context import Kitchen
    from mealwright.models import Change

    def totals() -> tuple[int, ...]:
        with db_of(kitchen) as db:
            return (
                *counts(kitchen),
                db.scalar(select(func.count()).select_from(Change)) or 0,
            )

    before = totals()
    with db_of(kitchen) as db:
        from mealwright.models import Household, Login

        login = db.scalars(select(Login)).first()
        household = db.get(Household, 1)
        assert login is not None and household is not None
        door = Kitchen(db, login, household, None, "POST /preview")
        choices = [
            batch_sessions.RecipeChoice(recipe_id=i, tub_count=2, pattern="dinners")
            for i in three[:2]
        ]
        slot = slot_ids(kitchen)["Dinner"]
        batch_sessions.preview(door, D1, slot, choices, lambda worked: len(worked.tubs))
        db.commit()  # what a stray flush would be kept by
    assert totals() == before


# --- Whole-0.8 review fixes (RF3): C5 ------------------------------------------------------------


def test_moving_the_cook_day_meal_moves_the_session_with_it_and_undo_puts_it_back(
    kitchen: TestClient, three: list[int]
) -> None:
    """C5: the Batch cook card, "Cooked it · Sun 15 Nov" and the session's own day follow the
    meal (they stayed on the old day, where nothing is cooked any more)."""
    written = make(kitchen, three)
    sid = written["session_id"]
    meal = next(m for m in view(kitchen)["meals"] if m["date"] == D1.isoformat())
    later = D1 + timedelta(days=9)  # another week
    moved = kitchen.post(
        f"{API}/plan/meals/{meal['id']}/move",
        json={"date": later.isoformat(), "slot_id": slot_ids(kitchen)["Lunch"], "mode": "move"},
    )
    assert moved.status_code == 200, moved.text
    assert ok(kitchen.get(f"{API}/batch-cook/sessions/{sid}"))["cook_day"] == later.isoformat()
    there = view(kitchen, later - timedelta(days=1), days=3)
    assert [s["cook_day"] for s in there["batch_sessions"]] == [later.isoformat()]
    assert {b["cooked_on"] for b in there["batch_cooks"]} == {later.isoformat()}
    undo(kitchen, moved.json())
    assert ok(kitchen.get(f"{API}/batch-cook/sessions/{sid}"))["cook_day"] == D1.isoformat()
    assert [s["cook_day"] for s in view(kitchen)["batch_sessions"]] == [D1.isoformat()]


def test_another_households_method_or_optional_line_is_refused_in_a_session(
    kitchen: TestClient, neighbour: TestClient, three: list[int]
) -> None:
    """RF3, C6: the new `method_id` and `optional_use` of a session's recipe are the recipe's own
    ways and lines only: another household's ids are refused, and nothing is planned."""
    theirs = recipe(neighbour, "Theirs", [food(neighbour, "Rice")])
    their_way = ok(neighbour.get(f"{API}/recipes/{theirs['id']}"))["methods"][0]["id"]
    their_line = ok(neighbour.get(f"{API}/recipes/{theirs['id']}"))["lines"][0]["id"]
    for field, value in (("method_id", their_way), ("optional_use", [their_line])):
        mine = body(kitchen, three[:2])
        mine["recipes"][0][field] = value
        refused = kitchen.post(f"{API}/batch-cook/sessions", json=mine)
        assert refused.status_code == 422, (field, refused.text)
    assert view(kitchen)["batch_sessions"] == []
