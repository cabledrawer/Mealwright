"""A removed person keeps no sign-in (0.9.0-alpha.1 release security pass, finding 1).

Removing someone deletes their sessions, but a sign-in that checked "not removed" just before
the removal committed could still add one afterwards. So a session only counts while its
person isn't removed, and signing in checks "removed" again under the household's lock.
"""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import API, WREN_PASSWORD, db, ok, person

from mealwright import auth
from mealwright.api.v1 import account
from mealwright.api.v1.events import _still_signed_in
from mealwright.auth import peek_session
from mealwright.models import Login, Member, Session, utcnow

WREN = {"username": "wren", "password": WREN_PASSWORD}


def _wren_member(kitchen: TestClient) -> int:
    with db(kitchen) as s:
        member_id = s.scalar(select(Login.member_id).where(Login.username == "wren"))
        assert member_id is not None
        return int(member_id)


def _mark_removed(kitchen: TestClient) -> None:
    """Mark Wren removed straight in the database, keeping their sessions: what a session
    added by a sign-in that raced the removal looks like."""
    with db(kitchen) as s:
        member = s.get(Member, _wren_member(kitchen))
        assert member is not None
        member.removed_at = utcnow()
        s.commit()


def _sessions(kitchen: TestClient) -> int:
    with db(kitchen) as s:
        login_id = s.scalar(select(Login.id).where(Login.username == "wren"))
        return len(s.scalars(select(Session).where(Session.login_id == login_id)).all())


def test_a_removed_persons_old_session_is_refused_everywhere(kitchen: TestClient) -> None:
    phone = person(kitchen)
    ok(phone.get(f"{API}/me"))
    token = phone.cookies.get(auth.cookie_name(kitchen.app.state.settings))  # type: ignore[attr-defined]
    assert token
    _mark_removed(kitchen)
    assert _sessions(kitchen) == 1  # the row is still there; it must not count
    for path in ("/me", "/people", "/me/sign-in", "/plan/people", "/changes"):
        assert phone.get(f"{API}{path}").status_code == 401, path
    assert phone.put(f"{API}/me/preferences", json={"theme": "dark"}).status_code == 401
    factory = kitchen.app.state.sessionmaker  # type: ignore[attr-defined]
    with factory() as s:
        assert auth.find_session(s, token) is None
        assert peek_session(s, token) is None
    # The live-updates stream asks the same question, before and while it's open.
    assert _still_signed_in(factory, token) is False


def test_a_removal_between_the_password_check_and_the_session_wins(
    kitchen: TestClient, monkeypatch: Any
) -> None:
    person(kitchen)
    real = account.counted_check

    def removed_meanwhile(*args: Any, **kwargs: Any) -> bool:
        right = real(*args, **kwargs)
        assert right  # the check saw a current person ...
        _mark_removed(kitchen)  # ... and the removal commits before the session is added
        return right

    monkeypatch.setattr(account, "counted_check", removed_meanwhile)
    phone = TestClient(kitchen.app, base_url="https://testserver")
    r = phone.post(f"{API}/session", json=WREN)
    assert r.status_code == 401, r.text
    assert r.json()["detail"] == "That username and password don’t match."
    assert phone.get(f"{API}/me").status_code == 401
    # Only the session from `person` (left by the direct mark) is there: none was added.
    assert _sessions(kitchen) == 1


def test_signing_in_rechecks_under_the_households_lock(
    kitchen: TestClient, monkeypatch: Any
) -> None:
    """The second check runs with the household's write lock held, so a removal can't commit
    between it and the new session."""
    person(kitchen)
    taken: list[int] = []
    real = account.lock_db

    def watched(s: Any, household: Any) -> None:
        taken.append(household.id)
        real(s, household)

    monkeypatch.setattr(account, "lock_db", watched)
    ok(TestClient(kitchen.app, base_url="https://testserver").post(f"{API}/session", json=WREN))
    assert taken == [1]
