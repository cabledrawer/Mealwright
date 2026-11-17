"""R6 (cabledrawer 17 Nov): keeping fewer backups than there are now deletes the oldest at
once, so it asks for the admin's own password first (or, for an admin who signs in only with
single sign-on, the fresh confirmation Delete everything asks for), counted like Delete
everything's. Keeping as many or more, and a change that deletes nothing, ask for nothing."""

# ruff: noqa: F811, F401
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from conftest import ADMIN
from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from test_backups import API, _folder, _household, member
from test_sso_api import admin, browser, fresh_cache, idp
from test_sso_confirm_delete import ADMINS, _confirm, _link_admin, sso_only

from mealwright import backups

PASSWORD = ADMIN["password"]


def _make(client: TestClient, count: int) -> None:
    start = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)
    for day in range(count):
        backups.back_up(
            cast(Any, client.app).state.engine, _folder(client), 30, start + timedelta(days=day)
        )


def _count(client: TestClient) -> int:
    return len(backups.backups(_folder(client)))


def test_lowering_keep_so_backups_go_needs_the_password(kitchen: TestClient) -> None:
    _make(kitchen, 4)
    refused = kitchen.patch(API, json={"keep": 2})
    assert refused.status_code == 403
    assert refused.json()["code"] == "password_wrong"
    assert _count(kitchen) == 4
    assert _household(kitchen).backup_keep == 7  # nothing changed, not even the setting


def test_a_wrong_password_changes_nothing_and_is_counted_like_delete_everything(
    kitchen: TestClient,
) -> None:
    _make(kitchen, 4)
    for _ in range(5):
        wrong = kitchen.patch(API, json={"keep": 2, "password": "nope"})
        assert wrong.status_code == 403
    assert kitchen.patch(API, json={"keep": 2, "password": "nope"}).status_code == 429
    # The count is shared with Delete everything's: the right one waits too.
    assert kitchen.patch(API, json={"keep": 2, "password": PASSWORD}).status_code == 429
    assert _count(kitchen) == 4
    assert _household(kitchen).backup_keep == 7


def test_the_right_password_lowers_keep_and_trims(kitchen: TestClient) -> None:
    _make(kitchen, 4)
    done = kitchen.patch(API, json={"keep": 2, "password": PASSWORD})
    assert done.status_code == 200, done.text
    assert (done.json()["keep"], done.json()["count"]) == (2, 2)
    assert _count(kitchen) == 2


def test_nothing_to_delete_needs_no_password(kitchen: TestClient) -> None:
    _make(kitchen, 3)
    assert kitchen.patch(API, json={"keep": 3}).status_code == 200  # exactly as many
    assert kitchen.patch(API, json={"keep": 10}).status_code == 200  # raising
    assert kitchen.patch(API, json={"keep": 4}).status_code == 200  # lowering, nothing goes
    assert kitchen.patch(API, json={"every": "weekly", "photos": False}).status_code == 200
    assert _count(kitchen) == 3


def test_other_changes_sent_with_a_refused_keep_are_not_made(kitchen: TestClient) -> None:
    _make(kitchen, 3)
    refused = kitchen.patch(API, json={"keep": 1, "every": "weekly"})
    assert refused.status_code == 403
    assert _household(kitchen).backup_every == "daily"


def test_a_member_is_refused_as_before(member: TestClient) -> None:
    assert member.patch(API, json={"keep": 1, "password": "wren's own password"}).status_code == 403


def test_a_token_is_refused_as_before(kitchen: TestClient) -> None:
    made = kitchen.post("/api/v1/api-tokens", json={"name": "t", "scope": "full"})
    assert made.status_code in (200, 201), made.text
    token = made.json()["token"]
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        answer = other.patch(
            API,
            json={"keep": 1, "password": PASSWORD},
            headers={"Authorization": f"Bearer {token}"},
        )
    assert answer.status_code == 403


def test_an_sso_only_admin_needs_a_fresh_confirmation(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    _make(sso_only, 4)
    refused = sso_only.patch(API, json={"keep": 2})
    assert refused.status_code == 403
    assert refused.json()["code"] == "confirm_first"
    assert _count(sso_only) == 4
    # No password is ever read for them.
    assert sso_only.patch(API, json={"keep": 2, "password": PASSWORD}).status_code == 403
    assert _confirm(sso_only, idp).status_code == 200
    done = sso_only.patch(API, json={"keep": 2})
    assert done.status_code == 200, done.text
    assert _count(sso_only) == 2
    # Used once: a second lowering asks again.
    assert sso_only.patch(API, json={"keep": 1}).status_code == 403


def test_an_sso_only_admin_needs_nothing_when_nothing_is_deleted(sso_only: TestClient) -> None:
    _make(sso_only, 2)
    assert sso_only.patch(API, json={"keep": 5}).status_code == 200
