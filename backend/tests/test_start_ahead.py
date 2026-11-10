"""The plan works backwards (0.8 wave 5, M3, F124; cabledrawer 31 Oct and 9 Nov): adding a recipe with
a long wait asks when it will be started, suggesting times from the meal's slot time and the wait;
the plan says it the day before; "Done already" and Cook mode record that it was begun; day two
knows how long it has waited. In the app only: nothing here sends anything. Times are the
household's wall clock; they are kept as instants, so a clock change moves nothing."""

from collections.abc import Callable
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sync_kit import ok
from test_plan import db_of, slot_ids
from test_plan_writes import plan_recipe, undo, view
from test_recipes import make

from mealwright import models, start_ahead
from mealwright.models import MealItem

API = "/api/v1"

FERMENT = {"kind": "ferment", "min_minutes": 480, "max_minutes": 720}
NOW = datetime(2026, 11, 12, 12, 0, tzinfo=UTC)  # a Thursday
SAT = date(2026, 11, 14)
FRI = date(2026, 11, 13)
SUN = date(2026, 11, 15)


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> Callable[[datetime], None]:
    """Move the clock the plan reads to a chosen moment (sign-in keeps the real one, so a jump
    of a day doesn't sign the test out)."""
    from mealwright import plan
    from mealwright.api.v1 import plan as plan_api

    def set_to(moment: datetime) -> None:
        shift = moment - datetime.now(UTC)
        for module in (plan, plan_api):
            monkeypatch.setattr(module, "utcnow", lambda: datetime.now(UTC) + shift)

    return set_to


@pytest.fixture(autouse=True)
def _thursday(clock: Callable[[datetime], None]) -> None:
    clock(NOW)


def dosa(kitchen: TestClient, name: str = "Start dosa", **fields: Any) -> dict[str, Any]:
    return make(
        kitchen,
        name,
        time_minutes=30,
        steps=[
            {"text": "Soak the rice and dal, grind to a batter and leave it.", "wait": FERMENT},
            {"text": "Stir the batter and add salt."},
            {"text": "Make the dosas."},
        ],
        **fields,
    )


def plain(kitchen: TestClient) -> dict[str, Any]:
    return make(kitchen, "Start plain", steps=[{"text": "Cook."}])


def london(kitchen: TestClient) -> None:
    kitchen.post(f"{API}/household/from-browser", json={"time_zone": "Europe/London"})


def options(
    kitchen: TestClient, recipe: dict[str, Any], day: date, slot: str = "Breakfast", **extra: Any
) -> dict[str, Any]:
    r = kitchen.get(
        f"{API}/plan/start-options",
        params={
            "recipe_id": recipe["id"],
            "date": day.isoformat(),
            "slot_id": slot_ids(kitchen)[slot],
            **extra,
        },
    )
    assert r.status_code == 200, r.text
    return r.json()  # type: ignore[no-any-return]


def start_of(day: date, at: str) -> dict[str, str]:
    return {"day": day.isoformat(), "time": at}


def item_of(kitchen: TestClient, item_id: int, first: date = FRI, days: int = 10) -> dict[str, Any]:
    for meal in view(kitchen, first, days)["meals"]:
        for item in meal["items"]:
            if item["id"] == item_id:
                return dict(item)
    raise AssertionError("not on the plan")


def plan_dosa(
    kitchen: TestClient,
    recipe: dict[str, Any],
    day: date = SAT,
    slot: str = "Breakfast",
    **extra: Any,
) -> dict[str, Any]:
    return plan_recipe(kitchen, recipe["id"], day, slot_ids(kitchen)[slot], **extra)


def put(kitchen: TestClient, item_id: int, what: str, body: dict[str, Any]) -> Any:
    return kitchen.put(f"{API}/plan/items/{item_id}/{what}", json=body)


# --- The question ----------------------------------------------------------------------------


def test_a_dosa_for_saturday_breakfast_suggests_friday_evening_and_ready_by_the_meal(
    kitchen: TestClient,
) -> None:
    found = options(kitchen, dosa(kitchen), SAT)
    assert found["wait"] == {
        "kind": "ferment",
        "min_minutes": 480,
        "max_minutes": 720,
        "overnight": False,
    }
    assert found["eats_at"] == "08:00"  # the slot's usual time: nothing else says
    first, second = found["options"]
    # The wait in the middle of its range (10 h) and the 30 minutes of work: 21:30, in whole hours.
    assert (first["day"], first["time"], first["ready_by"]) == ("2026-11-13", "21:00", "08:00")
    assert first["ready_by_day"] == "2026-11-14"
    # An earlier one that is ready even if the wait takes the longest (12 h and the work).
    assert (second["day"], second["time"], second["ready_by"]) == ("2026-11-13", "19:00", "07:30")


def test_the_times_follow_the_slot_and_a_wait_that_ends_at_overnight(kitchen: TestClient) -> None:
    soak = make(
        kitchen,
        "Start chickpeas",
        time_minutes=60,
        steps=[
            {
                "text": "Soak the chickpeas.",
                "wait": {"kind": "soak", "min_minutes": 480, "overnight": True},
            }
        ],
    )
    found = options(kitchen, soak, SAT, slot="Dinner")  # eaten at 19:00
    # 8-12 h (overnight counts as 12 h): the middle is 10 h, and an hour of work: 11 h before 19:00.
    assert [(o["day"], o["time"]) for o in found["options"]] == [
        ("2026-11-14", "08:00"),
        ("2026-11-14", "06:00"),
    ]
    assert found["eats_at"] == "19:00"


def test_a_recipe_with_no_long_wait_has_nothing_to_ask(kitchen: TestClient) -> None:
    short = make(
        kitchen,
        "Start rested",
        steps=[{"text": "Rest the dough.", "wait": {"kind": "rest", "min_minutes": 60}}],
    )
    for recipe in (plain(kitchen), short):  # an hour's rest is part of the cooking day
        found = options(kitchen, recipe, SAT)
        assert found["wait"] is None and found["options"] == []


def test_a_time_that_has_gone_by_is_not_suggested_and_with_none_left_it_is_now(
    kitchen: TestClient, clock: Callable[[datetime], None]
) -> None:
    recipe = dosa(kitchen)
    clock(datetime(2026, 11, 13, 20, 0, tzinfo=UTC))  # Friday 20:00: 21:00 is still to come
    assert [o["time"] for o in options(kitchen, recipe, SAT)["options"]] == ["21:00"]
    clock(datetime(2026, 11, 13, 23, 30, tzinfo=UTC))  # both have gone by: start at once
    (now,) = options(kitchen, recipe, SAT)["options"]
    assert now["day"] == "2026-11-13" and now["time"] in ("23:30", "23:35")
    # The earliest it could be ready: the shortest wait (8 h) and the work.
    assert now["ready_by_day"] == "2026-11-14" and now["ready_by"] in ("08:00", "08:05")


def test_the_options_count_real_hours_across_the_clocks_going_back(
    kitchen: TestClient, clock: Callable[[datetime], None]
) -> None:
    """Clocks go back at 02:00 BST on Sunday 25 October 2026: that night is an hour longer, so the
    start is an hour later on the wall clock than on an ordinary night."""
    london(kitchen)
    clock(datetime(2026, 10, 22, 12, 0, tzinfo=UTC))
    recipe = dosa(kitchen)
    ordinary = options(kitchen, recipe, date(2026, 10, 28))["options"][0]
    night = options(kitchen, recipe, date(2026, 10, 25))
    assert ordinary["time"] == "21:00"
    first = night["options"][0]
    # Breakfast at 08:00 GMT; 10 h 30 min back in real time is 22:30 BST: floored, 22:00.
    assert (first["day"], first["time"], first["ready_by"]) == ("2026-10-24", "22:00", "08:00")


def test_the_options_count_real_hours_across_the_clocks_going_forward(
    kitchen: TestClient, clock: Callable[[datetime], None]
) -> None:
    """Clocks go forward at 01:00 GMT on Sunday 29 March 2026: that night is an hour shorter."""
    london(kitchen)
    clock(datetime(2026, 3, 26, 12, 0, tzinfo=UTC))
    first = options(kitchen, dosa(kitchen), date(2026, 3, 29))["options"][0]
    assert (first["day"], first["time"]) == ("2026-03-28", "20:00")  # 08:00 BST is 07:00 UTC


# --- Adding the meal -------------------------------------------------------------------------


def test_adding_a_meal_with_a_start_keeps_it_and_the_plan_says_it(kitchen: TestClient) -> None:
    recipe = dosa(kitchen)
    written = plan_dosa(kitchen, recipe, start=start_of(FRI, "21:00"))
    ahead = item_of(kitchen, written["item_id"])["ahead"]
    assert ahead["start_day"] == "2026-11-13" and ahead["start_time"] == "21:00"
    assert ahead["eats_at"] == "08:00"
    assert ahead["wait"]["min_minutes"] == 480 and ahead["active_minutes"] == 30
    assert ahead["step_text"].startswith("Soak the rice")
    assert (ahead["started_day"], ahead["started_time"], ahead["waited_minutes"]) == (
        None,
        None,
        None,
    )
    # The same on Today, which carries the week.
    today = ok(kitchen.get(f"{API}/today"))["plan"]
    assert any(i["ahead"] for m in today["meals"] for i in m["items"])


def test_a_meal_added_without_a_start_has_the_wait_and_no_time(kitchen: TestClient) -> None:
    """An old client, or "not now": nothing is asked of it, and the meal can be given one later."""
    ahead = item_of(kitchen, plan_dosa(kitchen, dosa(kitchen))["item_id"])["ahead"]
    assert ahead["start_day"] is None and ahead["start_time"] is None


def test_a_recipe_with_no_wait_has_no_ahead_and_refuses_a_start(kitchen: TestClient) -> None:
    written = plan_dosa(kitchen, plain(kitchen))
    assert item_of(kitchen, written["item_id"])["ahead"] is None
    refused = kitchen.post(
        f"{API}/plan/items",
        json={
            "date": SAT.isoformat(),
            "slot_id": slot_ids(kitchen)["Breakfast"],
            "recipe_id": plain(kitchen)["id"],
            "start": start_of(FRI, "21:00"),
        },
    )
    assert (refused.status_code, refused.json()["code"]) == (422, "no_wait")
    note = kitchen.post(
        f"{API}/plan/items",
        json={
            "date": SAT.isoformat(),
            "slot_id": slot_ids(kitchen)["Breakfast"],
            "note": "Eating out",
            "start": start_of(FRI, "21:00"),
        },
    )
    assert (note.status_code, note.json()["code"]) == (422, "not_a_recipe")
    (meal,) = view(kitchen, FRI, 3)["meals"]  # nothing was added by the two refusals
    assert len(meal["items"]) == 1


def test_a_start_after_the_meal_or_far_too_early_is_refused(kitchen: TestClient) -> None:
    recipe = dosa(kitchen)
    for bad in (
        start_of(SAT, "08:00"),
        start_of(SAT, "09:00"),
        start_of(date(2026, 10, 1), "21:00"),
    ):
        r = kitchen.post(
            f"{API}/plan/items",
            json={
                "date": SAT.isoformat(),
                "slot_id": slot_ids(kitchen)["Breakfast"],
                "recipe_id": recipe["id"],
                "start": bad,
            },
        )
        assert (r.status_code, r.json()["code"]) == (422, "bad_start"), bad
    r = kitchen.post(
        f"{API}/plan/items",
        json={
            "date": SAT.isoformat(),
            "slot_id": slot_ids(kitchen)["Breakfast"],
            "recipe_id": recipe["id"],
            "start": {"day": "2026-11-13", "time": "25:99"},
        },
    )
    assert r.status_code == 422


def test_a_start_in_the_past_is_allowed(
    kitchen: TestClient, clock: Callable[[datetime], None]
) -> None:
    """Planned late, for the person who already soaked it: no refusal, the Plan just says so."""
    clock(datetime(2026, 11, 13, 23, 0, tzinfo=UTC))
    written = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))
    assert item_of(kitchen, written["item_id"])["ahead"]["start_time"] == "21:00"


def test_undo_of_adding_the_meal_takes_it_with_its_start(kitchen: TestClient) -> None:
    written = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))
    undo(kitchen, written)
    assert view(kitchen, FRI, 3)["meals"] == []


# --- Changing it from the meal ---------------------------------------------------------------


def test_the_start_can_be_changed_and_taken_away_and_undone(kitchen: TestClient) -> None:
    written = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))
    item = written["item_id"]
    changed = ok(put(kitchen, item, "start", {"start": start_of(FRI, "19:00")}))
    assert changed["change"]["kind"] == "plan_start"
    assert "Start dosa" in changed["change"]["summary"]
    assert item_of(kitchen, item)["ahead"]["start_time"] == "19:00"
    # The same time again changes nothing.
    assert ok(put(kitchen, item, "start", {"start": start_of(FRI, "19:00")}))["change"] is None
    undo(kitchen, changed)
    assert item_of(kitchen, item)["ahead"]["start_time"] == "21:00"
    gone = ok(put(kitchen, item, "start", {"start": None}))
    assert item_of(kitchen, item)["ahead"]["start_time"] is None
    undo(kitchen, gone)
    assert item_of(kitchen, item)["ahead"]["start_time"] == "21:00"


def test_undo_of_a_start_says_nothing_when_it_was_changed_again(kitchen: TestClient) -> None:
    item = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))["item_id"]
    first = ok(put(kitchen, item, "start", {"start": start_of(FRI, "19:00")}))
    ok(put(kitchen, item, "start", {"start": start_of(FRI, "18:00")}))
    r = kitchen.post(f"{API}/changes/{first['change']['id']}/undo")
    assert r.status_code == 200
    assert item_of(kitchen, item)["ahead"]["start_time"] == "18:00"  # the later change stays


def test_a_start_cannot_be_set_on_a_meal_that_cannot_wait(kitchen: TestClient) -> None:
    item = plan_dosa(kitchen, plain(kitchen))["item_id"]
    r = put(kitchen, item, "start", {"start": start_of(FRI, "21:00")})
    assert (r.status_code, r.json()["code"]) == (422, "no_wait")
    gone = kitchen.put(f"{API}/plan/items/99999/start", json={"start": None})
    assert gone.status_code == 404


def test_another_household_cannot_change_a_start(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    item = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))["item_id"]
    assert put(neighbour, item, "start", {"start": None}).status_code == 404
    assert put(neighbour, item, "started", {"started": True}).status_code == 404
    assert item_of(kitchen, item)["ahead"]["start_time"] == "21:00"


def test_another_households_recipe_or_slot_cannot_be_asked_about(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    recipe = dosa(kitchen)
    params = {
        "recipe_id": recipe["id"],
        "date": SAT.isoformat(),
        "slot_id": slot_ids(neighbour, 2)["Breakfast"],
    }
    assert neighbour.get(f"{API}/plan/start-options", params=params).status_code == 404
    mixed = {**params, "slot_id": slot_ids(kitchen)["Breakfast"]}
    assert neighbour.get(f"{API}/plan/start-options", params=mixed).status_code == 404


def test_another_households_recipe_cannot_be_given_a_start_by_a_meal_move(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    item = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))["item_id"]
    theirs = plan_recipe(neighbour, dosa(neighbour)["id"], SAT, slot_ids(neighbour, 2)["Breakfast"])
    with db_of(neighbour) as db:
        meal_id = db.get(MealItem, theirs["item_id"]).meal_id  # type: ignore[union-attr]
    moved = neighbour.post(
        f"{API}/plan/meals/{meal_id}/move",
        json={
            "date": "2026-11-16",
            "slot_id": slot_ids(neighbour, 2)["Breakfast"],
            "starts": [{"item_id": item, **start_of(SUN, "20:00")}],
        },
    )
    assert moved.status_code == 422 and moved.json()["code"] == "start_not_moved"
    assert item_of(kitchen, item)["ahead"]["start_time"] == "21:00"


def test_a_cooked_meal_has_no_ahead_and_cannot_be_started(kitchen: TestClient) -> None:
    item = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))["item_id"]
    with db_of(kitchen) as db:
        row = db.get(MealItem, item)
        assert row is not None
        meal = db.get(models.Meal, row.meal_id)
        assert meal is not None
        meal.status = "cooked"
        db.commit()
    assert item_of(kitchen, item)["ahead"] is None
    assert put(kitchen, item, "start", {"start": None}).status_code == 409


# --- Done already, and Cook mode ---------------------------------------------------------------


def test_done_already_keeps_the_moment_and_day_two_knows_how_long_it_has_waited(
    kitchen: TestClient, clock: Callable[[datetime], None]
) -> None:
    item = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))["item_id"]
    clock(datetime(2026, 11, 13, 21, 40, tzinfo=UTC))
    done = ok(put(kitchen, item, "started", {"started": True}))
    assert done["change"]["kind"] == "plan_started"
    clock(datetime(2026, 11, 14, 8, 0, tzinfo=UTC))
    ahead = item_of(kitchen, item)["ahead"]
    assert (ahead["started_day"], ahead["started_time"]) == ("2026-11-13", "21:40")
    assert 619 <= ahead["waited_minutes"] <= 621  # 10 h 20 min, to the second the test took
    # Pressing it again changes nothing; Undo takes the mark away.
    assert ok(put(kitchen, item, "started", {"started": True}))["change"] is None
    undo(kitchen, done)
    after = item_of(kitchen, item)["ahead"]
    assert after["started_time"] is None and after["waited_minutes"] is None


def test_the_started_moment_is_shown_in_the_household_clock(
    kitchen: TestClient, clock: Callable[[datetime], None]
) -> None:
    london(kitchen)
    item = plan_dosa(
        kitchen, dosa(kitchen), day=date(2026, 7, 4), start=start_of(date(2026, 7, 3), "21:00")
    )["item_id"]
    clock(datetime(2026, 7, 3, 20, 40, tzinfo=UTC))  # 21:40 in London (summer time)
    ok(put(kitchen, item, "started", {"started": True}))
    ahead = item_of(kitchen, item, date(2026, 7, 3))["ahead"]
    assert (ahead["start_time"], ahead["started_day"], ahead["started_time"]) == (
        "21:00",
        "2026-07-03",
        "21:40",
    )


def test_the_waited_time_is_real_time_across_a_clock_change(
    kitchen: TestClient, clock: Callable[[datetime], None]
) -> None:
    """Started at 21:40 BST on Saturday 24 October, looked at 08:00 GMT: the clocks went back in
    between, so it has waited 11 h 20 min, not 10 h 20 min."""
    london(kitchen)
    clock(datetime(2026, 10, 22, 12, 0, tzinfo=UTC))
    item = plan_dosa(kitchen, dosa(kitchen), day=date(2026, 10, 25))["item_id"]
    clock(datetime(2026, 10, 24, 20, 40, tzinfo=UTC))  # 21:40 BST
    ok(put(kitchen, item, "started", {"started": True}))
    clock(datetime(2026, 10, 25, 8, 0, tzinfo=UTC))  # 08:00 GMT
    ahead = item_of(kitchen, item, date(2026, 10, 24))["ahead"]
    assert (ahead["started_day"], ahead["started_time"]) == ("2026-10-24", "21:40")
    assert 679 <= ahead["waited_minutes"] <= 681


# --- Moving, copying, changing the way, removing ------------------------------------------------


def test_moving_the_meal_takes_the_start_away_and_undo_puts_it_back(kitchen: TestClient) -> None:
    item = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))["item_id"]
    with db_of(kitchen) as db:
        meal_id = db.get(MealItem, item).meal_id  # type: ignore[union-attr]
    r = kitchen.post(
        f"{API}/plan/meals/{meal_id}/move",
        json={"date": date(2026, 11, 15).isoformat(), "slot_id": slot_ids(kitchen)["Breakfast"]},
    )
    assert r.status_code == 200, r.text
    assert item_of(kitchen, item, FRI)["ahead"]["start_time"] is None
    undo(kitchen, r.json())
    assert item_of(kitchen, item, FRI)["ahead"]["start_time"] == "21:00"


def test_moving_one_item_to_another_meal_and_copying_it(kitchen: TestClient) -> None:
    item = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))["item_id"]
    copy = kitchen.post(
        f"{API}/plan/items/{item}/move",
        json={
            "date": date(2026, 11, 15).isoformat(),
            "slot_id": slot_ids(kitchen)["Breakfast"],
            "mode": "copy",
        },
    )
    assert copy.status_code == 200, copy.text
    meals = view(kitchen, FRI, 5)["meals"]
    starts = sorted(
        (m["date"], i["ahead"]["start_time"]) for m in meals for i in m["items"] if i["ahead"]
    )
    # The copy asks again (it has no time); the original keeps its own.
    assert starts == [("2026-11-14", "21:00"), ("2026-11-15", None)]
    moved = kitchen.post(
        f"{API}/plan/items/{item}/move",
        json={
            "date": date(2026, 11, 16).isoformat(),
            "slot_id": slot_ids(kitchen)["Breakfast"],
        },
    )
    assert moved.status_code == 200, moved.text
    assert item_of(kitchen, item, FRI, 12)["ahead"]["start_time"] is None
    undo(kitchen, moved.json())
    assert item_of(kitchen, item, FRI, 12)["ahead"]["start_time"] == "21:00"


def test_a_wait_already_begun_stays_begun_when_the_meal_moves(
    kitchen: TestClient, clock: Callable[[datetime], None]
) -> None:
    item = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))["item_id"]
    clock(datetime(2026, 11, 13, 21, 5, tzinfo=UTC))
    ok(put(kitchen, item, "started", {"started": True}))
    moved = kitchen.post(
        f"{API}/plan/items/{item}/move",
        json={"date": date(2026, 11, 15).isoformat(), "slot_id": slot_ids(kitchen)["Breakfast"]},
    )
    assert moved.status_code == 200, moved.text
    ahead = item_of(kitchen, item, FRI)["ahead"]
    assert ahead["started_time"] == "21:05" and ahead["start_time"] is None


def test_removing_the_meal_and_undo_bring_back_its_start_and_started_marks(
    kitchen: TestClient, clock: Callable[[datetime], None]
) -> None:
    item = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))["item_id"]
    clock(datetime(2026, 11, 13, 21, 5, tzinfo=UTC))
    ok(put(kitchen, item, "started", {"started": True}))
    gone = ok(kitchen.delete(f"{API}/plan/items/{item}"))
    assert view(kitchen, FRI, 3)["meals"] == []
    undo(kitchen, gone)
    (meal,) = view(kitchen, FRI, 3)["meals"]
    ahead = meal["items"][0]["ahead"]
    assert (ahead["start_time"], ahead["started_time"]) == ("21:00", "21:05")


def test_the_start_belongs_to_the_way_of_cooking_it_and_a_change_of_way_asks_again(
    kitchen: TestClient,
) -> None:
    recipe = dosa(
        kitchen,
        second_method={
            "name": "Instant",
            "time_minutes": 20,
            "lines": [],
            "steps": [{"text": "Mix and cook."}],
        },
        method_name="Overnight",
    )
    first, other = recipe["methods"][0]["id"], recipe["methods"][1]["id"]
    item = plan_dosa(kitchen, recipe, method_id=first, start=start_of(FRI, "21:00"))["item_id"]
    # Only the way with the long wait has anything to start ahead.
    assert item_of(kitchen, item)["ahead"]["start_time"] == "21:00"
    changed = ok(put(kitchen, item, "method", {"method_id": other}))
    assert item_of(kitchen, item)["ahead"] is None
    undo(kitchen, changed)
    assert item_of(kitchen, item)["ahead"]["start_time"] == "21:00"
    # And the question for the other way has nothing to ask.
    assert options(kitchen, recipe, SAT, method_id=other)["options"] == []
    assert options(kitchen, recipe, SAT, method_id=first)["options"]
    bad = kitchen.get(
        f"{API}/plan/start-options",
        params={
            "recipe_id": recipe["id"],
            "date": SAT.isoformat(),
            "slot_id": slot_ids(kitchen)["Breakfast"],
            "method_id": 99999,
        },
    )
    assert (bad.status_code, bad.json()["code"]) == (422, "not_a_method")


def test_nothing_is_sent_or_scheduled() -> None:
    """No notifications before 1.0 (cabledrawer 18 Oct): the start is only ever read from the plan, so
    the module reaches no job, no outgoing call and no notifier."""
    source = Path(start_ahead.__file__).read_text()
    imports = [line for line in source.splitlines() if line.startswith(("import ", "from "))]
    for word in ("jobs", "outbound", "apprise", "httpx", "smtplib", "socket"):
        assert not [line for line in imports if word in line], word


# --- Round 1 fixes (M3) ----------------------------------------------------------------------


def test_a_meal_whose_time_has_gone_by_has_nothing_to_start_but_the_add_goes_ahead(
    kitchen: TestClient, clock: Callable[[datetime], None]
) -> None:
    recipe = dosa(kitchen)
    clock(datetime(2026, 11, 14, 10, 0, tzinfo=UTC))  # Saturday 10:00; breakfast was at 08:00
    found = options(kitchen, recipe, SAT)
    assert found["wait"] is not None and found["options"] == []
    assert found["eats_at"] == "08:00"
    added = plan_dosa(kitchen, recipe)  # no start, so nothing is refused
    assert item_of(kitchen, added["item_id"], SAT)["ahead"]["start_time"] is None


def test_start_now_is_still_offered_when_it_is_ready_after_the_meal(
    kitchen: TestClient, clock: Callable[[datetime], None]
) -> None:
    recipe = dosa(kitchen)
    clock(datetime(2026, 11, 14, 5, 0, tzinfo=UTC))  # three hours before breakfast; wait is 8 h+
    (now,) = options(kitchen, recipe, SAT)["options"]
    assert now["time"] in ("05:00", "05:05") and now["ready_by"] in ("13:30", "13:35")
    started = plan_dosa(kitchen, recipe, start=start_of(SAT, "05:05"))
    assert item_of(kitchen, started["item_id"], SAT)["ahead"]["start_time"] == "05:05"


def test_copying_a_recipe_with_a_long_wait_can_say_when_to_start_it(kitchen: TestClient) -> None:
    item = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))["item_id"]
    slot = slot_ids(kitchen)["Breakfast"]
    body = {"date": "2026-11-15", "slot_id": slot, "mode": "copy"}
    late = kitchen.post(
        f"{API}/plan/items/{item}/move",
        json={**body, "start": start_of(date(2026, 11, 16), "21:00")},
    )
    assert late.status_code == 422 and late.json()["code"] == "bad_start"
    asked = kitchen.post(
        f"{API}/plan/items/{item}/move", json={**body, "start": start_of(SAT, "21:00")}
    )
    assert asked.status_code == 200, asked.text
    meals = view(kitchen, FRI, 5)["meals"]
    starts = sorted(
        (m["date"], i["ahead"]["start_time"]) for m in meals for i in m["items"] if i["ahead"]
    )
    assert starts == [("2026-11-14", "21:00"), ("2026-11-15", "21:00")]
    leftovers = kitchen.post(
        f"{API}/plan/items/{item}/move",
        json={**body, "date": "2026-11-16", "mode": "leftovers", "start": start_of(SAT, "21:00")},
    )
    assert leftovers.status_code == 422
    assert leftovers.json()["code"] == "start_not_for_leftovers"


# --- A move asks the start time again (cabledrawer 10 Nov) -------------------------------------------


def test_moving_one_recipe_can_say_when_to_start_it_on_its_new_day(kitchen: TestClient) -> None:
    item = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))["item_id"]
    body = {"date": "2026-11-16", "slot_id": slot_ids(kitchen)["Breakfast"]}
    late = kitchen.post(
        f"{API}/plan/items/{item}/move",
        json={**body, "start": start_of(date(2026, 11, 16), "21:00")},
    )
    assert late.status_code == 422 and late.json()["code"] == "bad_start"
    assert item_of(kitchen, item, FRI)["ahead"]["start_time"] == "21:00"  # nothing changed
    moved = kitchen.post(
        f"{API}/plan/items/{item}/move", json={**body, "start": start_of(SUN, "20:00")}
    )
    assert moved.status_code == 200, moved.text
    ahead = item_of(kitchen, item, FRI, 12)["ahead"]
    assert (ahead["start_day"], ahead["start_time"]) == ("2026-11-15", "20:00")
    undo(kitchen, moved.json())
    ahead = item_of(kitchen, item, FRI, 12)["ahead"]
    assert (ahead["start_day"], ahead["start_time"]) == ("2026-11-13", "21:00")


def test_moving_one_recipe_into_a_filled_meal_can_say_when_to_start_it(
    kitchen: TestClient,
) -> None:
    item = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))["item_id"]
    other = plan_dosa(kitchen, dosa(kitchen, "Idli"), day=date(2026, 11, 16))["item_id"]
    assert other
    moved = kitchen.post(
        f"{API}/plan/items/{item}/move",
        json={
            "date": "2026-11-16",
            "slot_id": slot_ids(kitchen)["Breakfast"],
            "start": start_of(SUN, "20:00"),
        },
    )
    assert moved.status_code == 200, moved.text
    assert item_of(kitchen, item, FRI, 12)["ahead"]["start_time"] == "20:00"


def test_moving_a_whole_meal_takes_each_recipes_new_start_time(kitchen: TestClient) -> None:
    item = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))["item_id"]
    with db_of(kitchen) as db:
        meal_id = db.get(MealItem, item).meal_id  # type: ignore[union-attr]
    body = {"date": "2026-11-16", "slot_id": slot_ids(kitchen)["Breakfast"]}
    stray = kitchen.post(
        f"{API}/plan/meals/{meal_id}/move",
        json={**body, "starts": [{"item_id": item + 999, **start_of(SUN, "20:00")}]},
    )
    assert stray.status_code == 422 and stray.json()["code"] == "start_not_moved"
    twice = kitchen.post(
        f"{API}/plan/meals/{meal_id}/move",
        json={
            **body,
            "starts": [
                {"item_id": item, **start_of(SUN, "20:00")},
                {"item_id": item, **start_of(SUN, "21:00")},
            ],
        },
    )
    assert twice.status_code == 422  # one start time for each recipe (FX2 review r1)
    assert item_of(kitchen, item, FRI)["ahead"]["start_time"] == "21:00"  # nothing changed
    moved = kitchen.post(
        f"{API}/plan/meals/{meal_id}/move",
        json={**body, "starts": [{"item_id": item, **start_of(SUN, "20:00")}]},
    )
    assert moved.status_code == 200, moved.text
    ahead = item_of(kitchen, item, FRI, 12)["ahead"]
    assert (ahead["start_day"], ahead["start_time"]) == ("2026-11-15", "20:00")
    undo(kitchen, moved.json())
    ahead = item_of(kitchen, item, FRI, 12)["ahead"]
    assert (ahead["start_day"], ahead["start_time"]) == ("2026-11-13", "21:00")


def test_moving_a_whole_meal_into_a_filled_meal_takes_its_start_time_and_undoes(
    kitchen: TestClient,
) -> None:
    item = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))["item_id"]
    other = plan_dosa(kitchen, dosa(kitchen, "Idli"), day=date(2026, 11, 16))["item_id"]
    with db_of(kitchen) as db:
        meal_id = db.get(MealItem, item).meal_id  # type: ignore[union-attr]
    moved = kitchen.post(
        f"{API}/plan/meals/{meal_id}/move",
        json={
            "date": "2026-11-16",
            "slot_id": slot_ids(kitchen)["Breakfast"],
            "starts": [{"item_id": item, **start_of(SUN, "20:00")}],
        },
    )
    assert moved.status_code == 200, moved.text
    ahead = item_of(kitchen, item, FRI, 12)["ahead"]
    assert (ahead["start_day"], ahead["start_time"]) == ("2026-11-15", "20:00")
    assert item_of(kitchen, other, FRI, 12)["ahead"]["start_time"] is None  # the other is left
    undo(kitchen, moved.json())
    ahead = item_of(kitchen, item, FRI, 12)["ahead"]
    assert (ahead["start_day"], ahead["start_time"]) == ("2026-11-13", "21:00")


def test_a_time_with_another_zone_is_kept_as_utc_text_in_an_undo_step() -> None:
    from datetime import timedelta, timezone

    from mealwright import methods, plan

    plus_two = datetime(2026, 11, 14, 10, 0, tzinfo=timezone(timedelta(hours=2)))
    assert methods.utc_text(plus_two) == "2026-11-14T08:00:00"
    assert plan._moment(plus_two) == "2026-11-14T08:00:00"
    assert plan._moment(datetime(2026, 11, 14, 8, 0)) == "2026-11-14T08:00:00"  # SQLite: UTC
    assert plan._unmoment(plan._moment(plus_two)) == plus_two


@pytest.mark.parametrize("zone", ["Asia/Kolkata", "America/New_York"])
def test_a_start_in_year_one_or_9999_is_refused_not_a_crash(kitchen: TestClient, zone: str) -> None:
    """Release 0.8.0-beta.1 security pass L2: a day at the calendar's ends overflowed when it was
    turned into an instant (500). Every way a start comes in, and the question's own day."""
    kitchen.post(f"{API}/household/from-browser", json={"time_zone": zone})
    with db_of(kitchen) as db:
        db.query(models.Household).update({"time_zone": zone})
        db.commit()
    recipe = dosa(kitchen)
    breakfast = slot_ids(kitchen)["Breakfast"]
    for far in ("0001-01-01", "9999-12-31"):
        start = {"day": far, "time": "00:00" if far.startswith("0") else "23:59"}
        added = kitchen.post(
            f"{API}/plan/items",
            json={
                "date": SAT.isoformat(),
                "slot_id": breakfast,
                "recipe_id": recipe["id"],
                "start": start,
            },
        )
        assert (added.status_code, added.json()["code"]) == (422, "bad_start"), far
        item = plan_dosa(kitchen, recipe)["item_id"]
        changed = put(kitchen, item, "start", {"start": start})
        assert (changed.status_code, changed.json()["code"]) == (422, "bad_start"), far
        asked = kitchen.get(
            f"{API}/plan/start-options",
            params={"recipe_id": recipe["id"], "date": far, "slot_id": breakfast},
        )
        assert asked.status_code == 422, (far, asked.text)


@pytest.mark.parametrize("far", ["0001-01-01", "9999-12-31"])
def test_a_start_in_year_one_or_9999_is_refused_on_every_move_and_copy(
    kitchen: TestClient, far: str
) -> None:
    """The other ways a start comes in (FX5, lead follow-up c): moving one recipe, copying one,
    moving a whole meal. Each is a 422 and changes nothing."""
    item = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))["item_id"]
    with db_of(kitchen) as db:
        meal_id = db.get(MealItem, item).meal_id  # type: ignore[union-attr]
    breakfast = slot_ids(kitchen)["Breakfast"]
    start = {"day": far, "time": "00:00" if far.startswith("0") else "23:59"}
    for mode in ("move", "copy"):
        refused = kitchen.post(
            f"{API}/plan/items/{item}/move",
            json={"date": "2026-11-16", "slot_id": breakfast, "mode": mode, "start": start},
        )
        assert (refused.status_code, refused.json()["code"]) == (422, "bad_start"), (far, mode)
    whole = kitchen.post(
        f"{API}/plan/meals/{meal_id}/move",
        json={
            "date": "2026-11-16",
            "slot_id": breakfast,
            "starts": [{"item_id": item, **start}],
        },
    )
    assert (whole.status_code, whole.json()["code"]) == (422, "bad_start"), far
    assert item_of(kitchen, item, FRI)["ahead"]["start_time"] == "21:00"  # nothing changed


# --- Cook once and a start time (FX5, lead follow-up a) --------------------------------------


def _cook_once(kitchen: TestClient, item_id: int) -> dict[str, Any]:
    r = kitchen.post(
        f"{API}/plan/items/{item_id}/batch",
        json={"tub_count": 2, "pattern": "pick"},
    )
    assert r.status_code == 201, r.text
    return dict(r.json())


def test_cooking_once_keeps_the_recipes_start_time_and_undo_of_it_too(
    kitchen: TestClient,
) -> None:
    item = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))["item_id"]
    made = _cook_once(kitchen, item)
    ahead = item_of(kitchen, item, FRI, 12)["ahead"]
    assert (ahead["start_day"], ahead["start_time"]) == ("2026-11-13", "21:00")
    undo(kitchen, made)
    ahead = item_of(kitchen, item, FRI, 12)["ahead"]
    assert (ahead["start_day"], ahead["start_time"]) == ("2026-11-13", "21:00")


def test_moving_a_cooking_with_a_start_takes_the_new_start_and_undo_puts_the_old_back(
    kitchen: TestClient,
) -> None:
    item = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))["item_id"]
    _cook_once(kitchen, item)
    body = {"date": "2026-11-16", "slot_id": slot_ids(kitchen)["Breakfast"], "mode": "move"}
    moved = kitchen.post(
        f"{API}/plan/items/{item}/move", json={**body, "start": start_of(SUN, "20:00")}
    )
    assert moved.status_code == 200, moved.text
    ahead = item_of(kitchen, item, FRI, 12)["ahead"]
    assert (ahead["start_day"], ahead["start_time"]) == ("2026-11-15", "20:00")
    undo(kitchen, moved.json())
    ahead = item_of(kitchen, item, FRI, 12)["ahead"]
    assert (ahead["start_day"], ahead["start_time"]) == ("2026-11-13", "21:00")


# --- Gaps left by the M3 review (FX5, lead follow-up e) ---------------------------------------


def test_a_start_sent_with_a_note_that_moves_or_is_copied_is_refused(kitchen: TestClient) -> None:
    breakfast = slot_ids(kitchen)["Breakfast"]
    note = kitchen.post(
        f"{API}/plan/items", json={"date": SAT.isoformat(), "slot_id": breakfast, "note": "Out"}
    )
    assert note.status_code == 201, note.text
    item = note.json()["item_id"]
    for mode in ("move", "copy"):
        refused = kitchen.post(
            f"{API}/plan/items/{item}/move",
            json={
                "date": "2026-11-16",
                "slot_id": breakfast,
                "mode": mode,
                "start": start_of(FRI, "21:00"),
            },
        )
        assert (refused.status_code, refused.json()["code"]) == (422, "not_a_recipe"), mode
    (meal,) = view(kitchen, FRI, 5)["meals"]  # nothing moved or copied
    assert [i["id"] for i in meal["items"]] == [item]


def test_a_start_sent_with_leftovers_of_a_meal_or_an_item_is_refused_or_ignored(
    kitchen: TestClient,
) -> None:
    item = plan_dosa(kitchen, dosa(kitchen), start=start_of(FRI, "21:00"))["item_id"]
    breakfast = slot_ids(kitchen)["Breakfast"]
    refused = kitchen.post(
        f"{API}/plan/items/{item}/move",
        json={
            "date": "2026-11-16",
            "slot_id": breakfast,
            "mode": "leftovers",
            "start": start_of(SUN, "20:00"),
        },
    )
    assert (refused.status_code, refused.json()["code"]) == (422, "start_not_for_leftovers")
    assert item_of(kitchen, item, FRI)["ahead"]["start_time"] == "21:00"


def test_a_start_with_a_move_or_copy_of_an_item_that_is_not_there_is_a_404(
    kitchen: TestClient,
) -> None:
    breakfast = slot_ids(kitchen)["Breakfast"]
    for mode in ("move", "copy"):
        gone = kitchen.post(
            f"{API}/plan/items/99999/move",
            json={
                "date": "2026-11-16",
                "slot_id": breakfast,
                "mode": mode,
                "start": start_of(SUN, "20:00"),
            },
        )
        assert gone.status_code == 404, mode
    gone_meal = kitchen.post(
        f"{API}/plan/meals/99999/move",
        json={
            "date": "2026-11-16",
            "slot_id": breakfast,
            "starts": [{"item_id": 1, **start_of(SUN, "20:00")}],
        },
    )
    assert gone_meal.status_code == 404
