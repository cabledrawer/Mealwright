"""Batch cook mode's schedule and progress (0.8 wave 6, B3; cabledrawer 28 Oct and 11 Nov): made when
the mode is started and kept on the session, Now and Next, timers, done and Undo, a reload or
another phone carrying on, Plan again, live updates, the switch and the other household."""

from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sync_kit import ok, person
from test_events import broadcaster, heard, quiet, run
from test_plan import slot_ids
from test_plan_writes import D1
from test_recipes import food, make

from mealwright import batch_mode
from mealwright.api.v1.context import Kitchen
from mealwright.models import BatchSession, BatchTaskProgress, Household, Login, utcnow

API = "/api/v1"


def recipe(
    kitchen: TestClient, name: str, onions: int, steps: list[dict[str, Any]], onion: dict[str, Any]
) -> dict[str, Any]:
    return make(
        kitchen,
        name,
        lines=[{"words": f"{onions} onions", "food_id": onion["id"], "amount": onions}],
        steps=steps,
    )


@pytest.fixture
def session(kitchen: TestClient) -> int:
    """A batch cook of Sambar and Chicken chettinad, both chopping onions, on D1."""
    onion = food(kitchen, "Onion")
    sambar = recipe(
        kitchen,
        "Sambar",
        1,
        [
            {"text": "Chop the onion.", "lines": [0]},
            {"text": "Pressure cook the dal for 3 whistles."},
            {"text": "Temper the mustard seeds in ghee for 5 minutes."},
        ],
        onion,
    )
    chettinad = recipe(
        kitchen,
        "Chicken chettinad",
        2,
        [
            {"text": "Chop the onions finely.", "lines": [0]},
            {"text": "Fry the onions and chicken for 8 minutes."},
            {"text": "Simmer for 25 minutes."},
        ],
        onion,
    )
    slots = slot_ids(kitchen)
    body = {
        "date": D1.isoformat(),
        "slot_id": slots["Dinner"],
        "recipes": [
            {"recipe_id": sambar["id"], "tub_count": 3},
            {"recipe_id": chettinad["id"], "tub_count": 4},
        ],
    }
    made = ok(kitchen.post(f"{API}/batch-cook/sessions", json=body), 201)
    return int(made["session_id"])


def url(session_id: int, rest: str = "") -> str:
    return f"{API}/batch-cook/sessions/{session_id}/schedule{rest}"


def start(kitchen: TestClient, session_id: int, **body: Any) -> dict[str, Any]:
    found: dict[str, Any] = ok(kitchen.post(url(session_id), json=body or None), 201)
    return found


def task(found: dict[str, Any], tid: str) -> dict[str, Any]:
    return next(t for t in found["tasks"] if t["id"] == tid)


def now_task(found: dict[str, Any]) -> dict[str, Any]:
    return task(found, found["now_id"])


# --- Starting -----------------------------------------------------------------------------------


def test_the_schedule_is_not_there_before_the_mode_is_started(
    kitchen: TestClient, session: int
) -> None:
    refused = kitchen.get(url(session))
    assert refused.status_code == 404 and refused.json()["code"] == "schedule_not_started"


def test_starting_makes_the_schedule_with_shared_prep_first_and_keeps_it(
    kitchen: TestClient, session: int
) -> None:
    made = start(kitchen, session)
    assert made["stale"] is False and made["done_count"] == 0
    assert made["cook_day"] == D1.isoformat()
    assert made["kitchen"] == {"hob_rings": 4, "pressure_cookers": 1, "oven": True}
    assert [r["recipe_name"] for r in made["recipes"]] == ["Sambar", "Chicken chettinad"]
    prep = made["tasks"][0]
    assert prep["kind"] == "prep" and prep["start"] == 0
    assert prep["title"] == "Chop 3 onions: 1 for Sambar, 2 for Chicken chettinad"
    assert len(prep["recipe_ids"]) == 2 and len(prep["step_ids"]) == 2
    assert made["now_id"] == prep["id"] and made["next_id"] is not None
    # Every step once: 2 shared into 1, so 6 steps are 5 tasks.
    assert len(made["tasks"]) == 5
    again = ok(kitchen.post(url(session)))  # started already: the same one, not a new one
    assert again["made_at"] == made["made_at"] and again["tasks"] == made["tasks"]
    assert ok(kitchen.get(url(session)))["tasks"] == made["tasks"]


def test_a_recipe_still_cooks_in_its_steps_order(kitchen: TestClient, session: int) -> None:
    made = start(kitchen, session)
    chettinad = [t for t in made["tasks"] if made["recipes"][1]["recipe_id"] in t["recipe_ids"]]
    for a, b in pairwise(chettinad):
        assert a["end"] <= b["start"]


# --- Progress -----------------------------------------------------------------------------------


def test_done_moves_now_on_and_undo_takes_it_back(kitchen: TestClient, session: int) -> None:
    made = start(kitchen, session)
    first = made["now_id"]
    after = ok(kitchen.put(url(session, f"/tasks/{first}/done")))
    assert task(after, first)["state"] == "done" and task(after, first)["done_at"]
    assert after["done_count"] == 1 and after["now_id"] != first
    assert ok(kitchen.put(url(session, f"/tasks/{first}/done")))["done_count"] == 1  # once
    back = ok(kitchen.delete(url(session, f"/tasks/{first}/done")))
    assert back["now_id"] == first and back["done_count"] == 0
    assert task(back, first)["done_at"] is None


def test_a_waiting_task_starts_its_timer_and_ends_by_itself(
    kitchen: TestClient, session: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    made = start(kitchen, session)
    ok(kitchen.put(url(session, f"/tasks/{made['now_id']}/done")))
    waiting = next(
        t
        for t in ok(kitchen.get(url(session)))["tasks"]
        if t["hands"] == "waiting" and t["state"] == "ready"
    )
    running = ok(kitchen.put(url(session, f"/tasks/{waiting['id']}/timer")))
    t = task(running, waiting["id"])
    assert t["state"] == "running" and t["started_at"] and t["ends_at"]
    assert running["in_use"]["pressure"] + running["in_use"]["hob"] >= 1
    first = t["started_at"]
    assert (
        task(ok(kitchen.put(url(session, f"/tasks/{waiting['id']}/timer"))), waiting["id"])[
            "started_at"
        ]
        == first
    )  # the first start stays
    # The wait runs out: the task is done and what follows it is ready.
    later = utcnow() + timedelta(minutes=waiting["minutes"] + 1)
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        view = batch_mode.view_of(_kitchen(db), db.get(BatchSession, session), later)
    assert next(x for x in view.tasks if x.id == waiting["id"]).state == "done"


def _kitchen(db: Any) -> Kitchen:
    return Kitchen(
        db=db,
        login=db.query(Login).first(),
        household=db.get(Household, 1),
        idempotency_key=None,
        request="",
    )


def test_a_hands_on_task_has_no_timer(kitchen: TestClient, session: int) -> None:
    made = start(kitchen, session)
    refused = kitchen.put(url(session, f"/tasks/{made['now_id']}/timer"))
    assert refused.status_code == 422 and refused.json()["code"] == "not_a_wait"


def test_a_task_that_is_not_there_is_a_404(kitchen: TestClient, session: int) -> None:
    start(kitchen, session)
    assert kitchen.put(url(session, "/tasks/t99/done")).status_code == 404
    assert kitchen.put(url(session, "/tasks/nope/done")).status_code == 422


def test_another_phone_carries_on_where_the_first_was(kitchen: TestClient, session: int) -> None:
    made = start(kitchen, session)
    ok(kitchen.put(url(session, f"/tasks/{made['now_id']}/done")))
    alex = person(kitchen)
    seen = ok(alex.get(url(session)))
    assert seen["done_count"] == 1 and seen["now_id"] != made["now_id"]
    ok(alex.put(url(session, f"/tasks/{seen['now_id']}/done")))
    assert ok(kitchen.get(url(session)))["done_count"] == 2


# --- Plan again ---------------------------------------------------------------------------------


def test_a_changed_kitchen_or_recipe_says_plan_again_and_plan_again_clears_the_progress(
    kitchen: TestClient, session: int
) -> None:
    made = start(kitchen, session)
    ok(kitchen.put(url(session, f"/tasks/{made['now_id']}/done")))
    assert ok(kitchen.get(url(session)))["stale"] is False
    ok(kitchen.patch(f"{API}/household/kitchen", json={"hob_rings": 2}))
    stale = ok(kitchen.get(url(session)))
    assert stale["stale"] is True and stale["kitchen"]["hob_rings"] == 4  # the running one stays
    again = ok(kitchen.post(url(session), json={"plan_again": True}), 201)
    assert again["stale"] is False and again["kitchen"]["hob_rings"] == 2
    assert again["done_count"] == 0
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.query(BatchTaskProgress).count() == 0


def test_editing_a_recipes_step_makes_it_stale(kitchen: TestClient, session: int) -> None:
    start(kitchen, session)
    sambar = ok(kitchen.get(f"{API}/batch-cook/sessions/{session}"))["recipes"][0]["recipe_id"]
    full = ok(kitchen.get(f"{API}/recipes/{sambar}"))
    body = {
        k: full[k]
        for k in (
            "name",
            "description",
            "time_minutes",
            "serves",
            "makes",
            "made_ahead",
            "tags",
            "nutrition",
        )
    }
    body["lines"] = [
        {
            "id": ln["id"],
            "kind": ln["kind"],
            "words": ln["words"],
            "amount": ln["amount"],
            "food_id": ln["food"]["id"] if ln.get("food") else None,
        }
        for ln in full["lines"]
    ]
    body["steps"] = [
        {"text": s["text"]} | ({"timing": {"minutes": 40}} if i == 1 else {})
        for i, s in enumerate(full["steps"])
    ]
    ok(kitchen.put(f"{API}/recipes/{sambar}", json={**body, "version": full["version"]}))
    assert ok(kitchen.get(url(session)))["stale"] is True


# --- The switch and the other household ---------------------------------------------------------


def test_hidden_batch_cook_refuses_the_schedule(kitchen: TestClient, session: int) -> None:
    ok(kitchen.patch(f"{API}/household", json={"batch_cook": False}))
    assert kitchen.post(url(session)).status_code == 409
    assert kitchen.get(url(session)).json()["code"] == "batch_cook_hidden"


def test_the_other_household_gets_404_on_every_route(
    kitchen: TestClient, neighbour: TestClient, session: int
) -> None:
    made = start(kitchen, session)
    tid = made["now_id"]
    assert neighbour.post(url(session)).status_code == 404
    assert neighbour.get(url(session)).status_code == 404
    assert neighbour.put(url(session, f"/tasks/{tid}/done")).status_code == 404
    assert neighbour.delete(url(session, f"/tasks/{tid}/done")).status_code == 404
    assert neighbour.put(url(session, f"/tasks/{tid}/timer")).status_code == 404
    assert ok(kitchen.get(url(session)))["done_count"] == 0


# --- Live updates -------------------------------------------------------------------------------


def test_every_open_screen_hears_a_change_of_progress(kitchen: TestClient, session: int) -> None:
    made = start(kitchen, session)
    tid = made["now_id"]

    async def scenario() -> None:
        import asyncio

        mine, theirs = broadcaster(kitchen).subscribe(1), broadcaster(kitchen).subscribe(2)
        await asyncio.to_thread(kitchen.put, url(session, f"/tasks/{tid}/done"))
        item = await heard(mine)
        assert item is not None and item.name == "batch_cook"
        assert item.data == {"session_id": session}
        assert await quiet(theirs)

    run(scenario())


# --- Review B3 round 1 ------------------------------------------------------------------------


def two_dals(kitchen: TestClient) -> int:
    """Two recipes that each start by pressure cooking, in a kitchen with one pressure cooker."""
    ok(kitchen.patch(f"{API}/household/kitchen", json={"pressure_cookers": 1}))
    recipes = [
        make(
            kitchen,
            f"Dal {n}",
            steps=[{"text": "Pressure cook the dal for 3 whistles."}, {"text": "Fry the onions."}],
        )
        for n in (1, 2)
    ]
    body = {
        "date": D1.isoformat(),
        "slot_id": slot_ids(kitchen)["Dinner"],
        "recipes": [{"recipe_id": r["id"], "tub_count": 2} for r in recipes],
    }
    return int(ok(kitchen.post(f"{API}/batch-cook/sessions", json=body), 201)["session_id"])


def test_a_second_timer_for_the_one_pressure_cooker_is_refused_until_the_first_is_done(
    kitchen: TestClient,
) -> None:
    session = two_dals(kitchen)
    made = start(kitchen, session)
    cooks = [t for t in made["tasks"] if t["equipment"] == "pressure"]
    assert len(cooks) == 2 and {t["state"] for t in cooks} == {"ready", "later"}
    first = next(t for t in cooks if t["state"] == "ready")["id"]
    second = next(t for t in cooks if t["state"] == "later")["id"]
    refused = kitchen.put(url(session, f"/tasks/{second}/timer"))
    assert refused.status_code == 409 and refused.json()["code"] == "not_ready"
    assert ok(kitchen.put(url(session, f"/tasks/{first}/timer")))["in_use"]["pressure"] == 1
    assert kitchen.put(url(session, f"/tasks/{second}/timer")).status_code == 409
    ok(kitchen.put(url(session, f"/tasks/{first}/done")))  # taken off: the cooker is free
    assert (
        task(ok(kitchen.put(url(session, f"/tasks/{second}/timer"))), second)["state"] == "running"
    )


def test_a_timer_pressed_offline_counts_from_when_it_was_pressed_and_never_from_outside_the_session(
    kitchen: TestClient,
) -> None:
    session = two_dals(kitchen)
    made = start(kitchen, session)
    first = next(t for t in made["tasks"] if t["equipment"] == "pressure" and t["state"] == "ready")
    made_at = datetime.fromisoformat(made["made_at"]).replace(tzinfo=UTC)
    pressed = made_at + (datetime.now(UTC) - made_at) / 2  # between the two
    body = {"at": pressed.isoformat()}
    got = task(ok(kitchen.put(url(session, f"/tasks/{first['id']}/timer"), json=body)), first["id"])
    assert datetime.fromisoformat(got["started_at"]).replace(tzinfo=UTC) == pressed
    # Done too: a time before the schedule was made, or in the future, is the server's own clock.
    for at in (made_at - timedelta(days=1), datetime.now(UTC) + timedelta(days=1)):
        ok(kitchen.delete(url(session, f"/tasks/{first['id']}/done")))
        sent = task(
            ok(
                kitchen.put(url(session, f"/tasks/{first['id']}/done"), json={"at": at.isoformat()})
            ),
            first["id"],
        )
        stamp = datetime.fromisoformat(sent["done_at"]).replace(tzinfo=UTC)
        assert made_at <= stamp <= datetime.now(UTC) + timedelta(seconds=5)


def test_removing_the_session_and_undo_bring_back_its_schedule_and_progress(
    kitchen: TestClient, session: int
) -> None:
    """Review B3 round 1, fix 3: Undo of taking the session off the plan puts the schedule, what
    was done and a running timer back, as they were."""
    made = start(kitchen, session)
    first = made["now_id"]
    ok(kitchen.put(url(session, f"/tasks/{first}/done")))
    after = ok(kitchen.get(url(session)))
    waiting = next(t for t in after["tasks"] if t["hands"] == "waiting" and t["state"] == "ready")
    ok(kitchen.put(url(session, f"/tasks/{waiting['id']}/timer")))
    before = ok(kitchen.get(url(session)))
    removed = ok(kitchen.delete(f"{API}/batch-cook/sessions/{session}"))
    assert kitchen.get(url(session)).status_code == 404
    ok(kitchen.post(f"{API}/changes/{removed['change']['id']}/undo"))
    again = ok(kitchen.get(url(session)))
    for key in ("made_at", "tasks", "stale", "done_count", "now_id", "next_id", "total_minutes"):
        assert again[key] == before[key], key
    assert task(again, first)["done_at"] == task(before, first)["done_at"]
    assert task(again, waiting["id"])["started_at"] == task(before, waiting["id"])["started_at"]


# --- Whole-0.8 review fixes (RF3): C8 ------------------------------------------------------------


def test_a_mark_for_an_older_schedule_is_refused_after_plan_again(
    kitchen: TestClient, session: int
) -> None:
    """C8: a phone still holding the old schedule sends a done for t1, after another phone has
    pressed Plan again (same task ids, different steps): refused, nothing marked."""
    old = start(kitchen, session)
    again = ok(kitchen.post(url(session), json={"plan_again": True}), 201)
    assert again["made_at"] != old["made_at"]
    tid = old["now_id"]
    sent = {"made_at": old["made_at"]}
    for refused in (
        kitchen.put(url(session, f"/tasks/{tid}/done"), json=sent),
        kitchen.put(url(session, f"/tasks/{tid}/timer"), json=sent),
        kitchen.delete(url(session, f"/tasks/{tid}/done"), params=sent),
    ):
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "schedule_replaced"
    assert ok(kitchen.get(url(session)))["done_count"] == 0
    # The current schedule's own made_at is accepted, and a mark without one still works.
    assert (
        kitchen.put(
            url(session, f"/tasks/{tid}/done"), json={"made_at": again["made_at"]}
        ).status_code
        == 200
    )
    assert kitchen.put(url(session, f"/tasks/{again['next_id']}/done")).status_code == 200


def test_a_marinade_in_the_middle_of_a_recipe_is_left_for_the_night_before(
    kitchen: TestClient,
) -> None:
    """C4: Today says Start tonight, so the session has no twelve-hour timer."""
    tandoori = make(
        kitchen,
        "Tandoori",
        steps=[
            {"text": "Mix the yoghurt and spices and coat the chicken."},
            {
                "text": "Leave to marinate.",
                "wait": {"kind": "marinate", "min_minutes": 240, "overnight": True},
            },
            {"text": "Grill for 20 minutes."},
        ],
    )
    rice = make(kitchen, "Plain rice", steps=[{"text": "Simmer the rice for 15 minutes."}])
    slots = slot_ids(kitchen)
    body = {
        "date": D1.isoformat(),
        "slot_id": slots["Dinner"],
        "recipes": [
            {"recipe_id": tandoori["id"], "tub_count": 2},
            {"recipe_id": rice["id"], "tub_count": 2},
        ],
    }
    sid = int(ok(kitchen.post(f"{API}/batch-cook/sessions", json=body), 201)["session_id"])
    made = start(kitchen, sid)
    assert made["total_minutes"] < 120
    assert len(made["before"]) == 2
    assert [t["title"] for t in made["tasks"] if "marinate" in t["title"]] == []


# --- Whole-0.8 review fixes (RF3): S5 ------------------------------------------------------------


def test_a_mark_can_be_answered_with_the_progress_only_so_no_step_words_are_sent_again(
    kitchen: TestClient, session: int
) -> None:
    """S5: with `brief=true` the answer to a done, an undo or a timer has each task's state and
    times but not the steps' words; without it the answer is the whole schedule as before."""
    made = start(kitchen, session)
    tid = made["now_id"]
    whole = ok(kitchen.put(url(session, f"/tasks/{tid}/done")))
    assert "title" in whole["tasks"][0] and "before" in whole
    brief = ok(kitchen.put(url(session, f"/tasks/{tid}/done"), params={"brief": "true"}))
    assert set(brief["tasks"][0]) == {"id", "state", "started_at", "done_at", "ends_at"}
    assert "before" not in brief and "recipes" not in brief
    assert brief["made_at"] == made["made_at"] and brief["done_count"] == whole["done_count"]
    assert [t["state"] for t in brief["tasks"]] == [t["state"] for t in whole["tasks"]]
    undone = ok(kitchen.delete(url(session, f"/tasks/{tid}/done"), params={"brief": "true"}))
    assert undone["done_count"] == 0 and "title" not in undone["tasks"][0]
    waiting = next(t["id"] for t in made["tasks"] if t["hands"] == "waiting")
    # A timer can only start when the wait is ready: do what is before it first.
    for t in made["tasks"]:
        if t["id"] == waiting:
            break
        kitchen.put(url(session, f"/tasks/{t['id']}/done"))
    timed = ok(kitchen.put(url(session, f"/tasks/{waiting}/timer"), params={"brief": "true"}))
    assert next(t for t in timed["tasks"] if t["id"] == waiting)["state"] == "running"


def test_a_steps_optional_mark_is_not_part_of_the_schedules_fingerprint() -> None:
    """RF3 fix 2: a schedule made before `optional` existed must not show as stale for it."""
    from dataclasses import replace

    from mealwright.batch_mode import basis_of
    from mealwright.batch_schedule import KitchenIn, RecipeIn, StepIn

    kit = KitchenIn(hob_rings=4, pressure_cookers=1, oven=True)
    step = StepIn(id=1, text="Chop.", hands="on", minutes=5, equipment="none")  # type: ignore[arg-type]
    plain = RecipeIn(id=1, name="Sambar", steps=(step,))
    marked = RecipeIn(id=1, name="Sambar", steps=(replace(step, optional=True),))
    assert basis_of([plain], kit) == basis_of([marked], kit)
