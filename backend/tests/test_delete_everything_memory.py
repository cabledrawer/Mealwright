"""Delete everything also empties what Mealwright keeps in memory about the old household."""

# ruff: noqa: F811, F401
from typing import Any, cast

from conftest import ADMIN, SETUP_CODE
from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_sso_api import ADMIN_GROUPS, API, admin, begin, browser, fresh_cache, idp, sign_in

from mealwright import sso_accounts
from mealwright.auth import now
from mealwright.models import Household, Login
from mealwright.updates import CheckResult


def _delete(admin: TestClient) -> None:
    gone = admin.post(
        f"{API}/your-data/delete-everything",
        json={"words": "delete everything", "password": ADMIN["password"]},
    )
    assert gone.status_code == 204, gone.text


def test_delete_everything_forgets_the_last_single_sign_on_test_and_link_and_proof(
    admin: TestClient, idp: FakeProvider
) -> None:
    answer, _ = sign_in(
        admin,
        idp,
        path="/sso/test",
        sub="tess-at-idp",
        extra={
            "preferred_username": "tess.old",
            "name": "Tess Oldhousehold",
            "email": "tess@oldhousehold.example",
            "groups": ["mealwright-admins", "family-oldhousehold"],
        },
    )
    assert answer.status_code == 200, answer.text
    state = cast(Any, admin.app).state
    state.sso_links[1] = object()
    state.sso_proven[1] = "a fingerprint"
    _delete(admin)
    assert state.sso_tests == {}
    assert state.sso_links == {}
    assert state.sso_proven == {}
    fresh = TestClient(admin.app, base_url="https://testserver")
    new_admin = {
        "name": "Someone New",
        "username": "newperson",
        "password": "a new long password",
        "setup_code": SETUP_CODE,
    }
    assert fresh.post(f"{API}/setup", json=new_admin).status_code == 201
    setup = fresh.get(f"{API}/sso/settings")
    assert setup.status_code == 200, setup.text
    assert setup.json()["test"] is None


def test_delete_everything_forgets_the_kept_warning_the_update_answer_and_wrong_passwords(
    admin: TestClient,
) -> None:
    app = cast(Any, admin.app)
    with app.state.sessionmaker() as db:
        household_id = db.scalar(select(Household.id))
        mine = db.scalar(select(Login.id).where(Login.household_id == household_id))
        name = db.scalar(select(Login.username).where(Login.household_id == household_id))
    sso_accounts._kept[household_id] = (1, "Tess", True)
    app.state.updates._results[household_id] = CheckResult("failed", None, now())
    wrong = [f"user:{name}", f"change:{mine}", f"dev:{mine}:abc"]
    for _ in range(6):
        app.state.slow_down.failed(wrong[::2])  # paused
    app.state.slow_down.failed([wrong[1]])  # change:<id> below its pause, or the delete is refused
    _delete(admin)
    assert sso_accounts._kept == {}
    assert app.state.updates.last(household_id) is None
    assert app.state.slow_down.wait_seconds(wrong) == 0, "paused still"
    assert not set(wrong) & set(app.state.slow_down._failures)


def test_a_single_sign_on_test_finished_after_delete_everything_leaves_nothing(
    admin: TestClient, idp: FakeProvider
) -> None:
    """Fails when a test sign-in that comes back after Delete everything leaves its result
    in memory under the old household number, which the next setup reuses and shows on its
    Single sign-on screen (v0.9.0 release security pass, review of the L2 fix)."""
    url = begin(admin, "/sso/test")
    code, state = idp.sign_in(url, sub="k-at-idp", extra=ADMIN_GROUPS)
    gone = admin.post(
        f"{API}/your-data/delete-everything",
        json={"words": "delete everything", "password": ADMIN["password"]},
    )
    assert gone.status_code == 204, gone.text
    state_ = cast(Any, admin.app).state
    late = admin.post(f"{API}/sso/finish", json={"state": state, "code": code})
    assert late.status_code >= 400
    assert state_.sso_tests == {}
    assert state_.sso_links == {}
    fresh = TestClient(admin.app, base_url="https://testserver")
    new = {
        "name": "Someone New",
        "username": "newperson",
        "password": "a new long password",
        "setup_code": SETUP_CODE,
    }
    assert fresh.post(f"{API}/setup", json=new).status_code == 201
    assert fresh.get(f"{API}/sso/settings").json()["test"] is None
