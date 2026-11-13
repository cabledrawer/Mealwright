"""The hourly single sign-on check holds no database lock while it asks the sign-in server."""

# ruff: noqa: F811, F401
import contextlib
import threading
import time
from datetime import timedelta
from typing import Any, cast

from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_sso_api import API, admin, browser, fresh_cache, idp, sign_in

from mealwright import sso_accounts
from mealwright.auth import now
from mealwright.models import Session


def _check(client: TestClient) -> int:
    app = cast(Any, client.app)
    return sso_accounts.check_sessions(
        app.state.outbound, app.state.sessionmaker, app.state.settings.data_dir, app.state.events
    )


def _all_due(client: TestClient) -> int:
    with cast(Any, client.app).state.sessionmaker() as db:
        due = list(db.scalars(select(Session).where(Session.sso.is_(True))))
        for session in due:
            session.sso_check_at = now()
        db.commit()
        return len(due)


def _three_people(admin: TestClient, idp: FakeProvider) -> list[TestClient]:
    phones = []
    for n in (1, 2, 3):
        phone = browser(admin)
        answer, _ = sign_in(
            phone, idp, sub=f"user-{n}", extra={"preferred_username": f"person{n}", "name": f"P{n}"}
        )
        assert answer.status_code == 200, answer.text
        phones.append(phone)
    return phones


def test_a_slow_sign_in_server_does_not_make_saves_wait_during_the_check(
    admin: TestClient, idp: FakeProvider
) -> None:
    """Three people signed in with single sign-on; the sign-in server takes 3 s to answer each
    refresh. While the job runs, an ordinary save by the admin (the theme) is timed."""
    _three_people(admin, idp)
    assert _all_due(admin) == 3
    slow = 3.0

    def token(form: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        assert form.get("grant_type") == "refresh_token"
        time.sleep(slow)
        return 200, {"access_token": "at", "token_type": "Bearer", "expires_in": 300}

    idp.token_override = token
    # A save with nothing else going on, to compare.
    assert admin.put(f"{API}/me/preferences", json={"theme": "dark"}).status_code == 200

    # The admin's own device was last used two minutes ago (so its next request notes the time).
    with cast(Any, admin.app).state.sessionmaker() as db:
        for session in db.scalars(select(Session).where(Session.sso.is_(False))):
            session.last_seen_at = now() - timedelta(minutes=2)
        db.commit()
    job = threading.Thread(target=_check, args=(admin,))
    job.start()
    time.sleep(slow + 0.7)  # the job is now waiting on the second person's refresh
    started = time.monotonic()
    admin.get(f"{API}/me")  # only looking: no save at all
    looking = time.monotonic() - started
    started = time.monotonic()
    admin.put(f"{API}/me/preferences", json={"theme": "light"})
    waited = time.monotonic() - started
    job.join()
    waited = max(waited, looking)
    assert waited < 1.0, f"a request waited {waited:.1f} s for the single sign-on check"


def test_a_check_that_stops_half_way_keeps_the_earlier_new_refresh_tokens(
    admin: TestClient, idp: FakeProvider, monkeypatch: Any
) -> None:
    """The sign-in server gives a new refresh token each time and ends the old one (rotation, as
    Authentik and Keycloak can). The check is stopped while on its second person (the stand-in
    here is an error raised there; a container stop or a failed final save does the same):
    nothing it learnt is saved, so at the next check the first person, whom the server had
    accepted, is signed out, and an admin's API tokens are deleted for good."""
    answer, _ = sign_in(
        admin,
        idp,
        path="/sso/test",
        sub="k-at-idp",
        extra={"preferred_username": "tess", "groups": ["mealwright-admins"]},
    )
    assert answer.status_code == 200, answer.text
    assert admin.post(f"{API}/sso/link").status_code == 200
    laptop = browser(admin)  # the admin signs in with single sign-on on a second device
    answer, _ = sign_in(laptop, idp, sub="k-at-idp", extra={"groups": ["mealwright-admins"]})
    assert answer.json()["me"]["username"] == "tess"
    made = admin.post(f"{API}/api-tokens", json={"name": "Home Assistant", "scope": "read"})
    assert made.status_code == 201, made.text
    token = {"Authorization": f"Bearer {made.json()['token']}"}
    script = TestClient(admin.app, base_url="https://testserver")
    assert script.get(f"{API}/me", headers=token).status_code == 200
    other = browser(admin)
    assert sign_in(other, idp, sub="user-2", extra={"preferred_username": "p2"})[0].is_success
    assert _all_due(admin) == 2

    valid = set(idp.refresh_tokens)
    made_count = [100]

    def rotating(form: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        if form.get("grant_type") != "refresh_token":
            raise AssertionError("only refreshes here")
        old = form.get("refresh_token")
        if old not in valid:
            return 400, {"error": "invalid_grant"}
        valid.discard(old)  # used once: the old one is ended
        made_count[0] += 1
        new = f"rt-{made_count[0]}"
        valid.add(new)
        return 200, {"access_token": "at", "refresh_token": new, "token_type": "Bearer"}

    idp.token_override = rotating
    real = sso_accounts.sso.refresh
    calls = [0]

    def stops_on_the_second(*args: Any, **kwargs: Any) -> Any:
        calls[0] += 1
        if calls[0] == 2:
            raise RuntimeError("the server was stopped here")
        return real(*args, **kwargs)

    monkeypatch.setattr(sso_accounts.sso, "refresh", stops_on_the_second)
    with contextlib.suppress(RuntimeError):
        _check(admin)
    monkeypatch.setattr(sso_accounts.sso, "refresh", real)
    assert laptop.get(f"{API}/me").status_code == 200  # still signed in after the stopped run

    assert _all_due(admin) == 2
    _check(admin)  # the next run, an hour later
    assert laptop.get(f"{API}/me").status_code == 200
    assert script.get(f"{API}/me", headers=token).status_code == 200
