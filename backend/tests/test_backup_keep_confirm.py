"""R6 (cabledrawer 17 Nov): keeping fewer backups than there are now deletes the oldest at
once, so it asks for the admin's own password first (or, for an admin who signs in only with
single sign-on, the fresh confirmation Delete everything asks for), counted like Delete
everything's. Keeping as many or more, and a change that deletes nothing, ask for nothing."""

# ruff: noqa: F811, F401
import contextlib
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast

import pytest
from conftest import ADMIN
from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from test_backups import API, _folder, _household, member
from test_sso_api import admin, browser, fresh_cache, idp
from test_sso_confirm_delete import ADMINS, ORIGIN, _confirm, _how, _link_admin, sso_only

from mealwright import backups
from mealwright.api.v1 import sso as sso_api

PASSWORD = ADMIN["password"]
V1 = "/api/v1"


def _make(client: TestClient, count: int) -> None:
    start = datetime(2026, 11, 1, 3, 0, tzinfo=UTC)
    for day in range(count):
        backups.back_up(
            cast(Any, client.app).state.engine, _folder(client), 30, start + timedelta(days=day)
        )


def _confirm_for(
    client: TestClient, idp: FakeProvider, action: str, keep: int | None = None
) -> Any:
    """A fresh sign-in at the sign-in server, begun for one action (B8b round 2)."""
    body: dict[str, Any] = {"action": action}
    if keep is not None:
        body["keep"] = keep
    started = client.post(f"{V1}/sso/confirm", headers=ORIGIN, json=body)
    assert started.status_code == 200, started.text
    code, state = idp.sign_in(started.json()["url"], sub="admin-1", extra=ADMINS)
    return client.post(f"{V1}/sso/finish", json={"state": state, "code": code})


def _count(client: TestClient) -> int:
    return len(backups.backups(_folder(client)))


def test_lowering_keep_so_backups_go_needs_the_password(kitchen: TestClient) -> None:
    _make(kitchen, 4)
    refused = kitchen.patch(API, json={"keep": 2})
    assert refused.status_code == 403
    assert refused.json()["code"] == "wrong_password"
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
    assert _confirm_for(sso_only, idp, "keep", 2).status_code == 200
    done = sso_only.patch(API, json={"keep": 2})
    assert done.status_code == 200, done.text
    assert _count(sso_only) == 2
    # Used once: a second lowering asks again.
    assert sso_only.patch(API, json={"keep": 1}).status_code == 403


def test_an_sso_only_admin_needs_nothing_when_nothing_is_deleted(sso_only: TestClient) -> None:
    _make(sso_only, 2)
    assert sso_only.patch(API, json={"keep": 5}).status_code == 200


def test_one_confirmation_passes_only_one_of_two_requests_sent_at_once() -> None:
    """Security review, finding 2: take_confirmed checked, then removed, so two at once could
    both pass. (The routes now also run one at a time, so this asks take_confirmed itself.)"""
    from types import SimpleNamespace

    state = SimpleNamespace(sso_confirmed={1: object()})
    request = SimpleNamespace(app=SimpleNamespace(state=state))
    kitchen = SimpleNamespace(household_id=1)
    real = sso_api.has_confirmed
    both = threading.Barrier(2, timeout=1)

    def slow(request: Any, kitchen: Any, *rest: Any) -> bool:
        answer = kitchen.household_id in request.app.state.sso_confirmed
        with contextlib.suppress(threading.BrokenBarrierError):
            both.wait()  # the old code reached here twice before either removed the proof
        return answer

    results: list[bool] = []
    sso_api.has_confirmed = slow  # type: ignore[assignment]
    try:
        threads = [
            threading.Thread(
                target=lambda: results.append(sso_api.take_confirmed(request, kitchen))  # type: ignore[arg-type]
            )
            for _ in range(2)
        ]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
    finally:
        sso_api.has_confirmed = real  # type: ignore[assignment]
    assert sorted(results) == [False, True]


# --- Back up now: a new backup at a full folder pushes the oldest out (security review, finding 1)


def test_back_up_now_at_a_full_folder_needs_the_password_and_makes_nothing(
    kitchen: TestClient,
) -> None:
    kitchen.patch(API, json={"keep": 3})
    _make(kitchen, 3)
    before = {b.path for b in backups.backups(_folder(kitchen))}
    refused = kitchen.post(API)
    assert refused.status_code == 403
    assert refused.json()["code"] == "wrong_password"
    wrong = kitchen.post(API, json={"password": "nope"})
    assert wrong.status_code == 403
    assert {b.path for b in backups.backups(_folder(kitchen))} == before  # none made or lost


def test_seven_presses_without_a_password_leave_every_old_backup(kitchen: TestClient) -> None:
    _make(kitchen, 7)
    before = {b.path for b in backups.backups(_folder(kitchen))}
    for _ in range(7):  # the wrong tries are counted, so the later ones are paused (429)
        assert kitchen.post(API).status_code in (403, 429)
    assert {b.path for b in backups.backups(_folder(kitchen))} == before


def test_back_up_now_with_the_password_makes_one_and_trims(kitchen: TestClient) -> None:
    kitchen.patch(API, json={"keep": 3})
    _make(kitchen, 3)
    oldest = backups.backups(_folder(kitchen))[-1].path
    done = kitchen.post(API, json={"password": PASSWORD})
    assert done.status_code == 200, done.text
    assert done.json()["count"] == 3
    assert not oldest.exists()


def test_back_up_now_below_keep_needs_no_password(kitchen: TestClient) -> None:
    _make(kitchen, 2)  # keep is 7
    assert kitchen.post(API).status_code == 200
    assert _count(kitchen) == 3


def test_a_wrong_password_on_back_up_now_is_counted(kitchen: TestClient) -> None:
    kitchen.patch(API, json={"keep": 2})
    _make(kitchen, 2)
    for _ in range(5):
        assert kitchen.post(API, json={"password": "nope"}).status_code == 403
    assert kitchen.post(API, json={"password": PASSWORD}).status_code == 429


def test_an_sso_only_admin_backs_up_over_the_oldest_only_after_confirming(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    _make(sso_only, 7)
    refused = sso_only.post(API)
    assert refused.status_code == 403
    assert refused.json()["code"] == "confirm_first"
    assert _confirm_for(sso_only, idp, "backup_now").status_code == 200
    assert sso_only.post(API).status_code == 200
    assert _count(sso_only) == 7


def test_the_scheduled_job_still_trims_without_a_password(kitchen: TestClient) -> None:
    _make(kitchen, 5)
    engine = cast(Any, kitchen.app).state.engine
    start = datetime(2026, 12, 1, 3, 0, tzinfo=UTC)
    backups.back_up(engine, _folder(kitchen), 3, start)
    assert _count(kitchen) == 3


def test_a_confirmation_for_one_action_passes_no_other(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """B8b round 2, finding 2: a confirm for Keep 6 doesn't pass Keep 1, Back up now or Delete
    everything, and a refusal doesn't use it up."""
    _make(sso_only, 7)
    assert _confirm_for(sso_only, idp, "keep", 6).status_code == 200
    assert sso_only.patch(API, json={"keep": 1}).status_code == 403
    assert sso_only.post(API).status_code == 403
    assert (
        sso_only.post(f"{V1}/delete-everything", json={"words": "delete everything"}).status_code
        == 403
    )
    assert _count(sso_only) == 7
    assert _how(sso_only) == {"confirm_with": "single_sign_on", "confirmed": False}
    assert sso_only.get(f"{V1}/delete-everything", params={"action": "keep", "keep": 6}).json()[
        "confirmed"
    ]
    assert sso_only.patch(API, json={"keep": 6}).status_code == 200
    assert _count(sso_only) == 6


def test_a_back_up_now_confirmation_passes_no_keep_and_no_delete_everything(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    _make(sso_only, 7)
    assert _confirm_for(sso_only, idp, "backup_now").status_code == 200
    assert sso_only.patch(API, json={"keep": 2}).status_code == 403
    assert (
        sso_only.post(f"{V1}/delete-everything", json={"words": "delete everything"}).status_code
        == 403
    )
    assert _count(sso_only) == 7


def test_deleting_everything_keeps_its_own_confirmation(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """The start with nothing said is still Delete everything's, and a Keep or Back up now
    can't use it."""
    _make(sso_only, 7)
    assert _confirm(sso_only, idp).status_code == 200
    assert sso_only.patch(API, json={"keep": 2}).status_code == 403
    assert sso_only.post(API).status_code == 403
    assert _how(sso_only)["confirmed"] is True


# --- Counting and then deleting is one step (B8b round 2, finding 1)


def _slow_back_up(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make every backup take a moment, as one with photos does, so a request counting the
    folder outside the lock would see the same count as the others."""
    import time

    real = backups.back_up

    def slow(*args: Any, **kwargs: Any) -> Any:
        time.sleep(0.3)
        return real(*args, **kwargs)

    monkeypatch.setattr(backups, "back_up", slow)


def _in_other_client(client: TestClient, send: Any) -> int:
    with TestClient(cast(Any, client.app), base_url="https://testserver") as other:
        other.cookies.update(client.cookies)
        return int(send(other).status_code)


def test_five_back_ups_at_once_one_below_keep_make_one_and_delete_nothing(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    import itertools

    import mealwright.api.v1.your_data as your_data

    _make(kitchen, 6)  # Keep is 7: room for exactly one
    old = {path.name for path in backups.backups(_folder(kitchen)) for path in [path.path]}
    seconds = itertools.count(1)
    start = datetime(2026, 12, 1, 3, 0, tzinfo=UTC)
    monkeypatch.setattr(
        your_data, "utcnow", lambda: start + timedelta(seconds=next(seconds)), raising=True
    )
    _slow_back_up(monkeypatch)
    results: list[int] = []
    threads = [
        threading.Thread(
            target=lambda: results.append(_in_other_client(kitchen, lambda c: c.post(API)))
        )
        for _ in range(5)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert sorted(results) == [200, 403, 403, 403, 403]
    now = {found.path.name for found in backups.backups(_folder(kitchen))}
    assert old <= now  # no old backup was deleted
    assert len(now) == 7


def test_keeping_exactly_what_there_is_cannot_slip_past_a_back_up_now(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Keep = the count asks for nothing; a Back up now finishing before that change's trim
    used to delete one with no password."""
    _make(kitchen, 6)
    old = {found.path.name for found in backups.backups(_folder(kitchen))}
    _slow_back_up(monkeypatch)
    real_trim = backups.trim

    def slow_trim(folder: Any, keep: int) -> Any:
        if keep == 6:  # this change's own trim, run after the other request's backup is made
            import time

            time.sleep(0.6)
        return real_trim(folder, keep)

    monkeypatch.setattr(backups, "trim", slow_trim)
    results: dict[str, int] = {}

    def press() -> None:
        results["post"] = _in_other_client(kitchen, lambda c: c.post(API))

    def lower() -> None:
        import time

        time.sleep(0.1)
        results["patch"] = _in_other_client(kitchen, lambda c: c.patch(API, json={"keep": 6}))

    threads = [threading.Thread(target=press), threading.Thread(target=lower)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    now = {found.path.name for found in backups.backups(_folder(kitchen))}
    assert old <= now, results  # none of the six was deleted without a password
