"""Every admin check goes through `roles.allowed()` (0.9.5-beta.3, D4, BE11).

A route asks `Kitchen.may(action)` or `Kitchen.admin_only(action)` (one refusal, `refuse_unless`),
never `login.role == "admin"` by hand, so an admin's API token sees on the read-only pages what
`TOKENS_NEVER` hides everywhere else.
"""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from test_api_tokens import _app, _make

API = "/api/v1"
ROUTES = Path(__file__).resolve().parents[1] / "src" / "mealwright" / "api" / "v1"


def test_no_route_compares_a_role_by_hand() -> None:
    by_hand = re.compile(
        r"(kitchen|caller|signed_in)\.login\.role\s*[!=]=|role\s*[!=]=\s*\"admin\""
    )
    found = [
        f"{path.name}:{number}"
        for path in sorted(ROUTES.glob("*.py"))
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        # Not a check: an answer saying which role the signed-in person has.
        if by_hand.search(line) and 'else "member"' not in line
    ]
    assert found == []


def test_an_admins_token_gets_no_backups_page(kitchen: TestClient) -> None:
    app = _app(kitchen, _make(kitchen, "full"))
    assert kitchen.get(f"{API}/your-data/backups").json()["database_size"] is not None
    refused = app.get(f"{API}/your-data/backups")
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "not_for_tokens"


def test_an_admins_token_sees_the_updates_page_as_a_member_does(kitchen: TestClient) -> None:
    app = _app(kitchen, _make(kitchen, "full"))
    answer = app.get(f"{API}/updates").json()
    assert answer["can_check"] is False
    assert answer["daily"] is None and answer["last"] is None
    assert kitchen.get(f"{API}/updates").json()["daily"] is False


def test_an_admins_token_gets_no_server_errors_in_the_report(kitchen: TestClient) -> None:
    app = _app(kitchen, _make(kitchen, "read"))
    answer = app.get(f"{API}/problem-report")
    assert answer.status_code == 200, answer.text
    assert answer.json()["errors"] == [] and answer.json()["errors_included"] is False
    assert kitchen.get(f"{API}/problem-report").json()["errors_included"] is True


# --- One rule for a member (D4, BE12; proposed, for cabledrawer) -------------------------------
# cabledrawer 15 Nov: a member doesn't see the Household group at all. A member is answered what
# a screen a member can open reads, with the may-change flag false and nothing an admin alone is
# told; a Household page's own data answers 403 `admins_only`.

_HOUSEHOLD_PAGES_ONLY = [
    "/api-tokens",
    "/sso/settings",
    "/privacy/own-network",
    "/your-data/backups",
    "/your-data/delete-everything",
]


@pytest.mark.parametrize("path", _HOUSEHOLD_PAGES_ONLY)
def test_a_member_is_refused_a_household_page(member: TestClient, path: str) -> None:
    refused = member.get(f"{API}{path}")
    assert refused.status_code == 403, refused.text
    assert refused.json()["code"] == "admins_only"


def test_what_a_members_screens_read_says_they_cant_change_it(
    kitchen: TestClient,
    member: TestClient,
) -> None:
    people = member.get(f"{API}/people").json()  # the plan's eaters
    assert people["can_change"] is False
    switches = member.get(f"{API}/privacy/switches").json()  # the import screen
    assert switches["can_change"] is False
    updates = member.get(f"{API}/updates").json()  # About, in the Mealwright group
    assert updates["can_check"] is False and updates["daily"] is None
