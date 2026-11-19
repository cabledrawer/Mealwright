"""Q2 (cabledrawer 18 Nov): what a single sign-on confirm is for (Keep and its number, Back up
now, Delete everything) is sealed in the sign-in trip itself, in the cookie of the browser that
began it, not kept per login on the server. The confirmation that comes back is for exactly
that action."""

# ruff: noqa: F811, F401
import json
from typing import Any, cast

import pytest
from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from test_backups import _folder
from test_backup_keep_confirm import _count, _make
from test_sso_api import API, admin, browser, fresh_cache, idp
from test_sso_confirm_delete import ADMINS, ORIGIN, WORDS, _how, sso_only

from mealwright import secret_box, sso
from mealwright.api.v1 import sso as sso_api

COOKIE = "__Host-mealwright_sso"


def _begin(client: TestClient, body: dict[str, Any]) -> str:
    started = client.post(f"{API}/sso/confirm", headers=ORIGIN, json=body)
    assert started.status_code == 200, started.text
    return str(started.json()["url"])


def _data_dir(client: TestClient) -> Any:
    return cast(Any, client.app).state.settings.data_dir


def _trip(client: TestClient) -> dict[str, Any]:
    return cast(
        dict[str, Any],
        json.loads(secret_box.open_sealed(_data_dir(client), str(client.cookies.get(COOKIE)))),
    )


def test_a_trip_for_keep_cannot_confirm_delete_everything(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """The attack: a second request for the same login asks for Delete everything between the
    start of a Keep trip and its finish. Before, the per-login store was overwritten and the
    Keep trip's confirmation became a Delete everything one."""
    _make(sso_only, 7)
    keep_url = _begin(sso_only, {"action": "keep", "keep": 2})
    keep_cookie = str(sso_only.cookies.get(COOKIE))
    _begin(sso_only, {"action": "delete_everything"})  # in between; its cookie is not used
    sso_only.cookies.set(COOKIE, keep_cookie)
    code, state = idp.sign_in(keep_url, sub="admin-1", extra=ADMINS)
    done = sso_only.post(f"{API}/sso/finish", json={"state": state, "code": code})
    assert done.status_code == 200, done.text
    refused = sso_only.post(f"{API}/delete-everything", json=WORDS)
    assert refused.status_code == 403
    assert _how(sso_only)["confirmed"] is False  # for Keep 2 only, not for this
    assert sso_only.patch(f"{API}/backups", json={"keep": 3}).status_code == 403
    assert sso_only.patch(f"{API}/backups", json={"keep": 2}).status_code == 200
    assert _count(sso_only) == 2


def test_a_swapped_or_tampered_sealed_trip_is_refused(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    keep_url = _begin(sso_only, {"action": "keep", "keep": 2})
    keep_cookie = str(sso_only.cookies.get(COOKIE))
    _begin(sso_only, {"action": "delete_everything"})
    other_cookie = str(sso_only.cookies.get(COOKIE))
    code, state = idp.sign_in(keep_url, sub="admin-1", extra=ADMINS)
    # Another trip's sealed value (for another action) doesn't answer this state.
    sso_only.cookies.set(COOKIE, other_cookie)
    swapped = sso_only.post(f"{API}/sso/finish", json={"state": state, "code": code})
    assert swapped.status_code == 400 and swapped.json()["code"] == "expired"
    # A changed byte is no sealed value at all.
    broken = keep_cookie[:-3] + ("AAA" if not keep_cookie.endswith("AAA") else "BBB")
    sso_only.cookies.set(COOKIE, broken)
    tampered = sso_only.post(f"{API}/sso/finish", json={"state": state, "code": code})
    assert tampered.status_code == 400 and tampered.json()["code"] == "expired"
    assert _how(sso_only)["confirmed"] is False


@pytest.mark.parametrize(
    ("body", "doing"),
    [
        ({"action": "keep", "keep": 2}, "keep"),
        ({"action": "backup_now"}, "backup_now"),
        ({"action": "delete_everything"}, "delete_everything"),
        (None, "delete_everything"),  # left out: Delete everything, as before
    ],
)
def test_each_action_confirms_end_to_end_and_only_itself(
    sso_only: TestClient, idp: FakeProvider, body: dict[str, Any] | None, doing: str
) -> None:
    _make(sso_only, 7)
    url = _begin(sso_only, body or {})
    assert _trip(sso_only)["action"] == doing
    code, state = idp.sign_in(url, sub="admin-1", extra=ADMINS)
    assert sso_only.post(f"{API}/sso/finish", json={"state": state, "code": code}).is_success
    if doing == "keep":
        assert sso_only.post(f"{API}/backups").status_code == 403
        assert sso_only.patch(f"{API}/backups", json={"keep": 2}).status_code == 200
        assert _count(sso_only) == 2
    elif doing == "backup_now":
        assert sso_only.post(f"{API}/delete-everything", json=WORDS).status_code == 403
        assert sso_only.post(f"{API}/backups").status_code == 200
        assert _count(sso_only) == 7
    else:
        assert sso_only.post(f"{API}/backups").status_code == 403
        assert sso_only.post(f"{API}/delete-everything", json=WORDS).status_code == 204


def test_a_trip_sealed_before_the_action_was_part_of_it_is_refused(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """An upgrade in the middle of a confirm: the old cookie names no action. It must not be
    read as Delete everything: the person is told to start again, and nothing is confirmed."""
    url = _begin(sso_only, {"action": "keep", "keep": 2})
    old = _trip(sso_only)
    del old["action"], old["keep"]
    sso_only.cookies.set(
        COOKIE, secret_box.seal(_data_dir(sso_only), json.dumps(old, separators=(",", ":")))
    )
    code, state = idp.sign_in(url, sub="admin-1", extra=ADMINS)
    answer = sso_only.post(f"{API}/sso/finish", json={"state": state, "code": code})
    assert answer.status_code == 400
    assert answer.json()["code"] == "expired"
    assert _how(sso_only)["confirmed"] is False


@pytest.mark.parametrize(
    "changes",
    [
        {"action": "wipe_it"},
        {"action": "keep", "keep": None},
        {"action": "keep", "keep": 31},
        {"action": "keep", "keep": True},
        {"action": "backup_now", "keep": 3},
        {"action": None},
    ],
)
def test_a_confirm_trip_with_an_unfitting_action_does_not_unpack(changes: dict[str, Any]) -> None:
    flow = sso.Flow(
        household_id=1,
        mode="confirm",
        state="s",
        nonce="n",
        verifier="v",
        issuer="https://i",
        client_id="c",
        redirect_uri="https://r",
        login_id=1,
        action="delete_everything",
    )
    packed = json.loads(flow.pack()) | changes
    with pytest.raises(sso.SsoFailed):
        sso.Flow.unpack(json.dumps(packed))
    assert sso.Flow.unpack(flow.pack()) == flow


def test_the_other_modes_carry_no_action() -> None:
    flow = sso.Flow(
        household_id=1, mode="sign_in", state="s", nonce="n", verifier="v",
        issuer="https://i", client_id="c", redirect_uri="https://r",
    )  # fmt: skip
    packed = json.loads(flow.pack()) | {"action": "delete_everything"}
    with pytest.raises(sso.SsoFailed):
        sso.Flow.unpack(json.dumps(packed))
