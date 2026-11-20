"""The roles table (0.9 A1; `mealwright.roles`): every route that needs an Admin refuses a Member
with 403 and changes nothing, and the table itself says which actions those are."""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sync_kit import API, person

from mealwright import roles
from mealwright.roles import Action

# Every admin-only route, with a body that is otherwise fine, and the action it is. A new admin
# route goes here; `test_every_admin_action_has_its_routes_here` keeps the table honest.
ADMIN_ROUTES: list[tuple[str, str, dict[str, Any] | None, Action]] = [
    ("PUT", "/privacy/switches/recipe_import", {"on": True}, Action.PRIVACY),
    ("POST", "/privacy/own-network", {"value": "192.168.1.0/24"}, Action.PRIVACY),
    ("DELETE", "/privacy/own-network/1", None, Action.PRIVACY),
    ("POST", "/updates/check", None, Action.PRIVACY),
    ("PATCH", "/household", {"pints": "us"}, Action.HOUSEHOLD_SETTINGS),
    ("PATCH", "/household", {"batch_cook": False}, Action.HOUSEHOLD_SETTINGS),
    ("PATCH", "/household", {"name": "Ours"}, Action.HOUSEHOLD_SETTINGS),
    ("PATCH", "/household", {"onboarding_done": True}, Action.HOUSEHOLD_SETTINGS),
    ("PATCH", "/household", {"amounts_shown": "metric"}, Action.HOUSEHOLD_SETTINGS),
    ("POST", "/household/fill-from-browser", {"cup_ml": 250}, Action.HOUSEHOLD_SETTINGS),
    ("PATCH", "/meal-slots/{slot}", {"name": "Supper"}, Action.HOUSEHOLD_SETTINGS),
    ("POST", "/meal-slots", {"name": "Elevenses"}, Action.HOUSEHOLD_SETTINGS),
    ("PUT", "/meal-slots/order", {"ids": []}, Action.HOUSEHOLD_SETTINGS),
    ("POST", "/people", {"name": "Joss"}, Action.PEOPLE),
    ("PATCH", "/people/{person}", {"portion_quarters": 2}, Action.PEOPLE),
    ("PATCH", "/people/{person}", {"role": "member"}, Action.PEOPLE),
    ("DELETE", "/people/{person}", None, Action.PEOPLE),
    ("POST", "/people/{person}/login", {"username": "someone"}, Action.PEOPLE),
    ("DELETE", "/people/{person}/login", None, Action.PEOPLE),
    ("PUT", "/people/ask-whos-this", {"on": True}, Action.PEOPLE),
    ("PATCH", "/backups", {"keep": 3}, Action.YOUR_DATA),
    ("POST", "/backups", None, Action.YOUR_DATA),
    ("GET", "/export", None, Action.YOUR_DATA),
    ("POST", "/export", {"password": "a long enough one"}, Action.YOUR_DATA),
    (
        "POST",
        "/delete-everything",
        {"words": "delete everything", "password": "x"},
        Action.YOUR_DATA,
    ),
]

# Actions with no route yet: Settings › Your sign-in comes with 0.9's sign-in work.
NO_ROUTE_YET = {Action.SIGN_IN}


@pytest.fixture
def member(kitchen: TestClient) -> TestClient:
    return person(kitchen)


def _slot(kitchen: TestClient) -> int:
    return int(kitchen.get(f"{API}/meal-slots").json()[0]["id"])


def test_the_table_says_admins_only_for_people_and_household_privacy_and_sign_in() -> None:
    assert set(roles.admin_actions()) == {
        Action.PEOPLE,
        Action.HOUSEHOLD_SETTINGS,
        Action.PRIVACY,
        Action.SIGN_IN,
        Action.YOUR_DATA,
    }
    for action in Action:
        assert roles.allowed(roles.ADMIN, action)
        assert roles.allowed(roles.MEMBER, action) == (action not in roles.admin_actions())
        assert not roles.allowed("someone", action)  # an unknown role may do nothing


def test_every_admin_action_has_its_routes_here() -> None:
    covered = {action for *_, action in ADMIN_ROUTES}
    assert covered | NO_ROUTE_YET == set(roles.admin_actions())


@pytest.mark.parametrize(
    ("method", "path", "body", "action"),
    ADMIN_ROUTES,
    ids=[f"{m} {p} {b}" for m, p, b, _ in ADMIN_ROUTES],
)
def test_a_member_gets_403_on_every_admin_route(
    kitchen: TestClient,
    member: TestClient,
    method: str,
    path: str,
    body: dict[str, Any] | None,
    action: Action,
) -> None:
    admin = kitchen.get(f"{API}/me").json()["member_id"]
    url = API + path.format(slot=_slot(kitchen), person=admin)
    before = kitchen.get(f"{API}/changes").json()
    r = member.request(method, url, json=body)
    assert r.status_code == 403, r.text
    assert r.json()["code"] == "admins_only"
    assert kitchen.get(f"{API}/changes").json() == before
    assert kitchen.get(f"{API}/people").json()["people"][0]["portion_quarters"] == 4


def test_a_member_cannot_undo_an_admins_household_setting(
    kitchen: TestClient, member: TestClient
) -> None:
    made = kitchen.patch(f"{API}/household", json={"pints": "us"})
    assert made.status_code == 200, made.text
    change = kitchen.get(f"{API}/changes").json()["changes"][0]
    assert change["can_undo"] is True
    assert member.get(f"{API}/changes").json()["changes"][0]["can_undo"] is False
    r = member.post(f"{API}/changes/{change['id']}/undo")
    assert r.status_code == 403 and r.json()["code"] == "admins_only"


@pytest.mark.parametrize("kind", ["person_added", "person_changed", "person_removed"])
def test_a_member_cannot_undo_an_admins_change_to_people(
    kitchen: TestClient, member: TestClient, kind: str
) -> None:
    made = kitchen.post(f"{API}/people", json={"name": "Joss"})
    assert made.status_code == 201, made.text
    joss = made.json()["people"][-1]["id"]
    if kind == "person_changed":
        kitchen.patch(f"{API}/people/{joss}", json={"portion_quarters": 2})
    elif kind == "person_removed":
        kitchen.delete(f"{API}/people/{joss}")
    change = kitchen.get(f"{API}/changes").json()["changes"][0]
    assert change["kind"] == kind
    r = member.post(f"{API}/changes/{change['id']}/undo")
    assert r.status_code == 403 and r.json()["code"] == "admins_only"
