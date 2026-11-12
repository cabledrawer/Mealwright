"""Guards around API tokens that nothing noticed missing (O2 review r1, finding 6). Each test
fails when its guard is taken out (shown in the commit message)."""

# ruff: noqa: F811, F401

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from sync_kit import API, db, ok, person
from test_api_tokens import _app, _make
from test_recipe_import import LINK, start, web

from mealwright.api.v1.tokens import MOST_TOKENS
from mealwright.models import ApiToken, Login, Member


def test_a_token_works_only_in_the_household_of_the_login_that_made_it(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    """api_tokens.py: `ApiToken.household_id == Login.household_id`. A token whose household
    isn't its login's (a row made wrong) is never accepted."""
    app = _app(kitchen, _make(kitchen, "read"))
    assert app.get(f"{API}/me").status_code == 200
    with db(kitchen) as session:
        session.execute(update(ApiToken).values(household_id=2))
        session.commit()
    answer = app.get(f"{API}/me")
    assert answer.status_code == 401 and answer.json()["code"] == "bad_token"


def test_a_household_has_at_most_fifty_tokens(kitchen: TestClient) -> None:
    """tokens.py: the cap. A deleted token doesn't count."""
    for number in range(MOST_TOKENS):
        ok(kitchen.post(f"{API}/api-tokens", json={"name": f"App {number}", "scope": "read"}), 201)
    refused = kitchen.post(f"{API}/api-tokens", json={"name": "One too many", "scope": "read"})
    assert refused.status_code == 409 and refused.json()["code"] == "too_many_tokens"
    first = ok(kitchen.get(f"{API}/api-tokens"))["tokens"][0]["id"]
    assert kitchen.delete(f"{API}/api-tokens/{first}").status_code == 204
    ok(kitchen.post(f"{API}/api-tokens", json={"name": "Room again", "scope": "read"}), 201)


def test_tokens_are_made_and_deleted_only_from_this_site(kitchen: TestClient) -> None:
    """tokens.py: the router's SameOrigin. Another site can't make or delete one."""
    elsewhere = {"Origin": "https://evil.example"}
    made = kitchen.post(
        f"{API}/api-tokens", json={"name": "Sneaky", "scope": "full"}, headers=elsewhere
    )
    assert made.status_code == 403, made.text
    assert ok(kitchen.get(f"{API}/api-tokens"))["tokens"] == []
    own = ok(kitchen.post(f"{API}/api-tokens", json={"name": "Mine", "scope": "read"}), 201)
    deleted = kitchen.delete(f"{API}/api-tokens/{own['made']['id']}", headers=elsewhere)
    assert deleted.status_code == 403, deleted.text
    assert len(ok(kitchen.get(f"{API}/api-tokens"))["tokens"]) == 1


def test_the_list_a_phone_shares_with_names_only_people_who_can_sign_in(
    kitchen: TestClient,
) -> None:
    """sync.py: `can_sign_in()` in "Synced with". Someone whose sign-in link isn't used yet (a
    login with no password and no single sign-on) isn't someone who can see the list."""
    person(kitchen)  # Wren signs in
    with db(kitchen) as session:
        member = Member(household_id=1, name="Joss")
        session.add(member)
        session.flush()
        session.add(
            Login(
                household_id=1,
                username="joss",
                name="Joss",
                password_hash=None,
                role="member",
                member_id=member.id,
            )
        )
        session.commit()
    names = [p["name"] for p in ok(kitchen.get(f"{API}/shopping/changes?since=0"))["people"]]
    assert names == ["Tess", "Wren"]


def test_a_tokens_import_error_doesnt_tell_it_to_use_privacy(kitchen: TestClient, web: Any) -> None:
    """recipe_import.py: `roles.allowed(..., kitchen.by_token)`. A token can't turn the import
    switch on, so its refusal isn't the admin's ("Turn it on in Privacy")."""
    mine = start(kitchen, LINK)
    assert mine.status_code == 403 and mine.json()["admin"] is True
    app = _app(kitchen, _make(kitchen, "full"))
    theirs = start(app, LINK)
    assert theirs.status_code == 403
    assert theirs.json()["admin"] is False
