"""A removed person and the meals (0.9.5 Pe6, cabledrawer 13 Nov): "a removed person is taken off
future meals (past meals show "<name> (removed)")". Future is decided by the household's own day:
a meal on the day of the removal or after it no longer counts them; Undo of the removal within
7 days puts them back; a meal before that day keeps them, named with "(removed)"."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_plan import slot_ids
from test_plan_writes import plan_recipe, view
from test_recipe_list import line
from test_recipes import food as new_food
from test_recipes import make as new_recipe
from test_today import ago, ahead

from mealwright.models import Login, MealEater

API = "/api/v1"


@pytest.fixture
def slots(kitchen: TestClient) -> dict[str, int]:
    return slot_ids(kitchen)


@pytest.fixture
def sambar(kitchen: TestClient) -> int:
    rice = new_food(kitchen, "Rice")
    made = new_recipe(kitchen, "Sambar", lines=[line(rice["id"], 200, "g")], serves=4)
    return int(made["id"])


@pytest.fixture
def lorna(kitchen: TestClient) -> int:
    with kitchen.app.state.sessionmaker() as db:
        login = Login(
            household_id=1, username="lorna", name="Lorna", password_hash="x", role="member"
        )
        db.add(login)
        db.commit()
        return int(login.member_id or 0)


def _eaters(kitchen: TestClient, meal_id: int, day: Any) -> list[int]:
    shown = view(kitchen, day - timedelta(days=1), 3)
    return next(m for m in shown["meals"] if m["id"] == meal_id)["eater_member_ids"]


def _remove(kitchen: TestClient, member_id: int) -> dict[str, Any]:
    return ok(kitchen.delete(f"{API}/people/{member_id}"))


def _tick(kitchen: TestClient, meal_id: int, ids: list[int]) -> None:
    ok(kitchen.patch(f"{API}/plan/meals/{meal_id}", json={"member_ids": ids}))


def test_a_removed_person_is_off_future_meals_and_undo_puts_them_back(
    kitchen: TestClient, sambar: int, lorna: int, slots: dict[str, int]
) -> None:
    day = ahead(kitchen, 2)
    meal = plan_recipe(kitchen, sambar, day, slots["Dinner"])["meal_id"]
    _tick(kitchen, meal, [1, lorna])
    removed = _remove(kitchen, lorna)
    assert _eaters(kitchen, meal, day) == [1]
    # Undo of the removal: back on the meal.
    ok(kitchen.post(f"{API}/changes/{removed['change']['id']}/undo"))
    assert _eaters(kitchen, meal, day) == [1, lorna]


def test_a_meal_only_ticked_for_a_removed_person_is_for_everyone_again(
    kitchen: TestClient, sambar: int, lorna: int, slots: dict[str, int]
) -> None:
    day = ahead(kitchen, 2)
    meal = plan_recipe(kitchen, sambar, day, slots["Dinner"])["meal_id"]
    _tick(kitchen, meal, [lorna])
    _remove(kitchen, lorna)
    assert _eaters(kitchen, meal, day) == []


def test_today_counts_as_future_and_yesterday_does_not(
    kitchen: TestClient, sambar: int, lorna: int, slots: dict[str, int]
) -> None:
    today_meal = plan_recipe(kitchen, sambar, ahead(kitchen, 0), slots["Dinner"])["meal_id"]
    past_meal = plan_recipe(kitchen, sambar, ago(kitchen, 1), slots["Dinner"])["meal_id"]
    _tick(kitchen, today_meal, [1, lorna])
    _tick(kitchen, past_meal, [1, lorna])
    ok(kitchen.post(f"{API}/plan/meals/{past_meal}/mark-not-cooked"))
    _remove(kitchen, lorna)
    assert _eaters(kitchen, today_meal, ahead(kitchen, 0)) == [1]
    assert _eaters(kitchen, past_meal, ago(kitchen, 1)) == [1, lorna]
    # The plan names the removed person, so a past meal can say "Lorna (removed)".
    shown = view(kitchen, ago(kitchen, 2), 4)
    assert shown["removed_people"] == [{"member_id": lorna, "name": "Lorna"}]


def test_a_meal_that_was_ahead_at_the_removal_is_still_off_it_when_looked_at_later(
    kitchen: TestClient, sambar: int, lorna: int, slots: dict[str, int]
) -> None:
    """The day of the removal decides, not the day it is looked at."""
    day = ahead(kitchen, 1)
    meal = plan_recipe(kitchen, sambar, day, slots["Dinner"])["meal_id"]
    _tick(kitchen, meal, [1, lorna])
    _remove(kitchen, lorna)
    with kitchen.app.state.sessionmaker() as db:
        from mealwright.models import Member

        member = db.get(Member, lorna)
        assert member is not None and member.removed_at is not None
        member.removed_at = member.removed_at - timedelta(days=3)  # removed 3 days ago
        db.commit()
    assert _eaters(kitchen, meal, day) == [1]  # the removal day (3 days ago) is before it
    with kitchen.app.state.sessionmaker() as db:
        assert db.scalar(select(MealEater).where(MealEater.member_id == lorna)) is not None


def test_a_removed_person_cannot_be_ticked(
    kitchen: TestClient, sambar: int, lorna: int, slots: dict[str, int]
) -> None:
    day = ahead(kitchen, 2)
    meal = plan_recipe(kitchen, sambar, day, slots["Dinner"])["meal_id"]
    _tick(kitchen, meal, [1, lorna])
    _remove(kitchen, lorna)
    r = kitchen.patch(f"{API}/plan/meals/{meal}", json={"member_ids": [1, lorna]})
    assert r.status_code == 404


def test_ticking_others_after_a_removal_keeps_the_hidden_tick_for_undo(
    kitchen: TestClient, sambar: int, lorna: int, slots: dict[str, int]
) -> None:
    day = ahead(kitchen, 2)
    meal = plan_recipe(kitchen, sambar, day, slots["Dinner"])["meal_id"]
    noor = _person(kitchen, "Noor")
    _tick(kitchen, meal, [noor, lorna])
    removed = _remove(kitchen, lorna)
    _tick(kitchen, meal, [1])  # the others change who eats
    assert _eaters(kitchen, meal, day) == [1]
    ok(kitchen.post(f"{API}/changes/{removed['change']['id']}/undo"))
    assert _eaters(kitchen, meal, day) == [1, lorna]


def test_everyone_after_a_removal_is_not_undone_into_her_alone(
    kitchen: TestClient, sambar: int, lorna: int, slots: dict[str, int]
) -> None:
    """Fix round 1: the others choose Everyone ([]); Undo of the removal must not make the meal
    Lorna's alone. (The earlier expectation, `[lorna]`, was wrong.)"""
    day = ahead(kitchen, 2)
    meal = plan_recipe(kitchen, sambar, day, slots["Dinner"])["meal_id"]
    _tick(kitchen, meal, [1, lorna])
    removed = _remove(kitchen, lorna)
    _tick(kitchen, meal, [])
    assert _eaters(kitchen, meal, day) == []
    ok(kitchen.post(f"{API}/changes/{removed['change']['id']}/undo"))
    assert _eaters(kitchen, meal, day) == []


def _person(kitchen: TestClient, name: str) -> int:
    with kitchen.app.state.sessionmaker() as db:
        login = Login(
            household_id=1, username=name.lower(), name=name, password_hash="x", role="member"
        )
        db.add(login)
        db.commit()
        return int(login.member_id or 0)


def test_a_removal_and_its_undo_tell_the_open_plans(
    kitchen: TestClient, sambar: int, lorna: int, slots: dict[str, int]
) -> None:
    from mealwright import events

    seen: list[int] = []
    real = events.note_plan
    events.note_plan = lambda session, household_id: (
        seen.append(household_id),
        real(session, household_id),
    )[1]  # type: ignore[assignment]
    try:
        removed = _remove(kitchen, lorna)
        assert seen, "removing a person should note a plan change"
        seen.clear()
        ok(kitchen.post(f"{API}/changes/{removed['change']['id']}/undo"))
        assert seen, "its Undo should note a plan change"
    finally:
        events.note_plan = real
