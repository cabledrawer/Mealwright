"""Passwords count as off only while single sign-on can start (O1 review r3, findings 1 and 2).

Every case here was "passwords off while single sign-on can't start": a lock-out. They are
closed together, by one question (`sso_accounts.sso_can_start`, which applies the rule the
outbound gate applies, with no look-up) that every place enforcing "passwords off" asks.
"""

import re
from pathlib import Path
from typing import Any, cast

import pytest
from fake_idp import ISSUER, FakeProvider, FakeTLS
from fastapi.testclient import TestClient
from test_sso_api import ADMIN_GROUPS, API, PASSWORD, SETUP, _add_admin, browser

from mealwright import outbound, sso, sso_accounts
from mealwright.models import utcnow
from mealwright.people import admins_left


@pytest.fixture(autouse=True)
def fresh_cache() -> None:
    sso.cache.forget()


def home(
    kitchen: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    listed: str,
    *,
    issuer: str = ISSUER,
    address: str = "192.168.1.50",
    port: int = 443,
    off: bool = True,
) -> FakeProvider:
    """A sign-in server at a private address listed on Your own network, an admin linked by
    a tested sign-in, and (by default) passwords off."""
    idp = FakeProvider(issuer=issuer, address=address, port=port)
    idp.install(monkeypatch)
    app = cast(Any, kitchen.app)
    app.state.outbound = outbound.OutboundGate(app.state.sessionmaker, tls=cast(Any, FakeTLS()))
    assert kitchen.put(f"{API}/privacy/switches/single_sign_on", json={"on": True}).is_success
    assert kitchen.post(f"{API}/privacy/own-network", json={"value": listed}).is_success
    assert kitchen.put(f"{API}/sso/settings", json={**SETUP, "issuer": issuer}).is_success
    started = kitchen.post(f"{API}/sso/test", headers={"Origin": "https://testserver"})
    code, state = idp.sign_in(str(started.json()["url"]), sub="k", extra=ADMIN_GROUPS)
    assert kitchen.post(f"{API}/sso/finish", json={"state": state, "code": code}).is_success
    assert kitchen.post(f"{API}/sso/link").is_success
    if off:
        assert kitchen.put(f"{API}/sso/password-sign-in", json={"on": False}).is_success
        assert browser(kitchen).post(f"{API}/session", json=PASSWORD).status_code == 403
    return idp


def entry_id(client: TestClient) -> int:
    return int(client.get(f"{API}/privacy/own-network").json()["entries"][0]["id"])


def passwords_work(kitchen: TestClient) -> bool:
    return browser(kitchen).post(f"{API}/session", json=PASSWORD).status_code == 200


def look_up_down(host: str, port: int) -> list[str]:
    raise OSError("the look-up is down")


def test_an_entry_removed_with_passwords_on_still_stops_passwords_going_off(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 1: the proof ignored Your own network."""
    home(kitchen, monkeypatch, "id.example.org", off=False)
    removed = kitchen.delete(f"{API}/privacy/own-network/{entry_id(kitchen)}")
    assert removed.status_code == 200, removed.text
    assert removed.json() == {"passwords_back_on": False, "notice": None}
    off = kitchen.put(f"{API}/sso/password-sign-in", json={"on": False})
    assert off.status_code == 409 and off.json()["code"] == "passwords_needed"
    assert passwords_work(kitchen)


def test_a_removal_while_the_look_up_is_down_leaves_passwords_working(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 2a."""
    home(kitchen, monkeypatch, "id.example.org")
    monkeypatch.setattr(outbound, "_lookup", look_up_down)
    gone = kitchen.delete(f"{API}/privacy/own-network/{entry_id(kitchen)}")
    assert gone.status_code == 200 and gone.json()["passwords_back_on"] is True
    assert passwords_work(kitchen)


def test_a_removal_while_the_look_up_places_are_held_leaves_passwords_working(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 2b: a Member can hold the look-up places."""
    home(kitchen, monkeypatch, "id.example.org")
    full = outbound.MAX_STUCK_PER_HOUSEHOLD
    monkeypatch.setattr(outbound, "_look_ups_by_household", {1: full})
    monkeypatch.setattr(outbound, "_look_ups_running", full)
    gone = kitchen.delete(f"{API}/privacy/own-network/{entry_id(kitchen)}")
    assert gone.status_code == 200 and gone.json()["passwords_back_on"] is True
    assert passwords_work(kitchen)


def test_a_public_server_on_an_odd_port_listed_by_name_is_off_the_list_when_removed(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 2c: the port rule of the gate, not only the private-address rule."""
    issuer = "https://id.example.org:8443"
    home(kitchen, monkeypatch, "id.example.org", issuer=issuer, address="93.184.216.40", port=8443)
    gone = kitchen.delete(f"{API}/privacy/own-network/{entry_id(kitchen)}")
    assert gone.status_code == 200 and gone.json()["passwords_back_on"] is True
    assert passwords_work(kitchen)


def test_a_removal_while_the_switch_is_off_leaves_passwords_working_when_it_is_on_again(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Finding 2d."""
    home(kitchen, monkeypatch, "id.example.org")
    assert kitchen.put(f"{API}/privacy/switches/single_sign_on", json={"on": False}).is_success
    removed = kitchen.delete(f"{API}/privacy/own-network/{entry_id(kitchen)}")
    assert removed.status_code == 200, removed.text
    assert removed.json() == {"passwords_back_on": False, "notice": None}
    assert kitchen.put(f"{API}/privacy/switches/single_sign_on", json={"on": True}).is_success
    assert passwords_work(kitchen)


def test_a_range_removed_while_the_look_up_is_down_leaves_passwords_working(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    home(kitchen, monkeypatch, "192.168.1.0/24")
    monkeypatch.setattr(outbound, "_lookup", look_up_down)
    assert kitchen.delete(f"{API}/privacy/own-network/{entry_id(kitchen)}").status_code == 200
    assert passwords_work(kitchen)


def test_adding_the_entry_back_turns_passwords_off_again(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Nothing was changed in the setting, only what counts: so it follows what can start."""
    home(kitchen, monkeypatch, "id.example.org")
    kitchen.delete(f"{API}/privacy/own-network/{entry_id(kitchen)}")
    assert passwords_work(kitchen)
    assert kitchen.post(f"{API}/privacy/own-network", json={"value": "id.example.org"}).is_success
    assert browser(kitchen).post(f"{API}/session", json=PASSWORD).status_code == 403


def test_a_server_not_remembered_yet_counts_as_one_that_cant_start(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Anything it can't tell is "can't start": passwords work."""
    home(kitchen, monkeypatch, "id.example.org")
    sso.forget_remembered()
    assert passwords_work(kitchen)


def test_every_place_enforcing_passwords_off_asks_the_one_question(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Sign-in, the sign-in page's options, the Settings screen's switch, and counting the
    admins who can get in all follow `sso_can_start`: made False, passwords are back everywhere."""
    home(kitchen, monkeypatch, "id.example.org")
    _add_admin(kitchen, "wren")  # a password-only admin: doesn't count while passwords are off
    assert not passwords_work(kitchen)
    assert browser(kitchen).get(f"{API}/sign-in-options").json()["password"] is False
    assert kitchen.get(f"{API}/sso/settings").json()["password_sign_in"] is False
    with cast(Any, kitchen.app).state.sessionmaker() as db:
        from mealwright.api.v1.context import Kitchen
        from mealwright.models import Household, Login

        household = db.get(Household, 1)
        login = db.query(Login).filter(Login.username == "tess").one()
        here = Kitchen(db=db, login=login, household=household, idempotency_key=None, request="T")  # type: ignore[arg-type]
        here.data_dir = cast(Any, kitchen.app).state.settings.data_dir
        only_sso_admins = admins_left(here)
        monkeypatch.setattr(sso_accounts, "sso_can_start", lambda *a, **k: False)
        assert admins_left(here) > only_sso_admins
    assert passwords_work(kitchen)
    assert browser(kitchen).get(f"{API}/sign-in-options").json()["password"] is True
    assert kitchen.get(f"{API}/sso/settings").json()["password_sign_in"] is True


SOURCE = Path(__file__).resolve().parents[1] / "src" / "mealwright"
# Files that may read the stored setting `password_sign_in` itself: the one question's home,
# the places that write it, and the reset command.
MAY_READ = {"sso_accounts.py", "models.py", "reset_admin.py", "sso.py"}


def test_nothing_reads_the_stored_password_setting_except_the_one_question() -> None:
    """A new route that refuses passwords must go through `passwords_off`, not the setting."""
    offenders: list[str] = []
    for path in SOURCE.rglob("*.py"):
        if "migrations" in path.parts or path.name in MAY_READ:
            continue
        for number, line in enumerate(path.read_text().splitlines(), 1):
            if re.search(r"\.password_sign_in\b", line) and not re.search(
                r"\.password_sign_in\s*=[^=]|body\.password_sign_in|kitchen\.", line
            ):
                offenders.append(f"{path.relative_to(SOURCE)}:{number}: {line.strip()}")
    assert not offenders, offenders


def test_another_admins_test_of_someone_elses_identity_proves_nothing(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O1 review r3, L3: two admins. The first is linked and proven; the second saves a setup
    and tests another identity (not linking it): that's no proof for the first."""
    idp = home(kitchen, monkeypatch, "id.example.org", off=False)
    _add_admin(kitchen, "wren")
    wren = browser(kitchen)
    mine = {"username": "wren", "password": "wren's own password"}
    assert wren.post(f"{API}/session", json=mine).status_code == 200
    new = {
        **SETUP,
        "client_secret": "",
        "group_roles": [{"group": "kitchen-admins", "role": "admin"}],
    }
    assert wren.put(f"{API}/sso/settings", json=new).is_success
    started = wren.post(f"{API}/sso/test", headers={"Origin": "https://testserver"})
    code, state = idp.sign_in(
        str(started.json()["url"]), sub="r", extra={"groups": ["kitchen-admins"]}
    )
    assert wren.post(f"{API}/sso/finish", json={"state": state, "code": code}).is_success
    assert wren.delete(f"{API}/sso/link").is_success  # Not now: nothing linked
    off = wren.put(f"{API}/sso/password-sign-in", json={"on": False})
    assert off.status_code == 409 and off.json()["code"] == "passwords_needed"
    assert passwords_work(kitchen)


def test_a_waiting_link_does_not_survive_signing_out_and_in_even_if_the_session_id_is_reused(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O1 review r3, L4: the link waits for the session's token, not its row id (SQLite may
    hand a new session the id of a deleted one)."""
    from sqlalchemy import update

    from mealwright.models import Session

    idp = home(kitchen, monkeypatch, "id.example.org", off=False)
    # A second test by the same admin leaves a link waiting ("can" needs an unlinked admin).
    assert kitchen.delete(f"{API}/sso/link").is_success
    with cast(Any, kitchen.app).state.sessionmaker() as db:
        from mealwright.models import Login

        db.execute(
            update(Login).where(Login.username == "tess").values(sso_subject=None, sso_issuer=None)
        )
        db.commit()
    started = kitchen.post(f"{API}/sso/test", headers={"Origin": "https://testserver"})
    code, state = idp.sign_in(str(started.json()["url"]), sub="mallory", extra=ADMIN_GROUPS)
    assert kitchen.post(f"{API}/sso/finish", json={"state": state, "code": code}).is_success
    with cast(Any, kitchen.app).state.sessionmaker() as db:
        old_id = db.query(Session).one().id
    assert kitchen.delete(f"{API}/session").status_code == 204
    again = browser(kitchen)
    assert again.post(f"{API}/session", json=PASSWORD).status_code == 200
    with cast(Any, kitchen.app).state.sessionmaker() as db:  # the new session has the old id
        db.execute(update(Session).values(id=old_id))
        db.commit()
    r = again.post(f"{API}/sso/link")
    assert r.status_code == 409 and r.json()["code"] == "link_gone"


def _make_token_and_sso_session(
    kitchen: TestClient, idp: FakeProvider
) -> tuple[TestClient, TestClient]:
    from sync_kit import ok
    from test_sso_api import sign_in

    there = browser(kitchen)
    signed, _ = sign_in(there, idp, sub="k", extra=ADMIN_GROUPS)
    assert signed.status_code == 200
    made = ok(kitchen.post(f"{API}/api-tokens", json={"name": "HA", "scope": "full"}), 201)
    app = TestClient(kitchen.app, base_url="https://testserver")
    app.headers["Authorization"] = f"Bearer {made['token']}"
    assert app.get(f"{API}/me").status_code == 200
    return there, app


def _due_now(kitchen: TestClient) -> None:
    from sqlalchemy import select

    from mealwright.auth import now
    from mealwright.models import Session

    with cast(Any, kitchen.app).state.sessionmaker() as db:
        for session in db.scalars(select(Session).where(Session.sso.is_(True))):
            session.sso_check_at = now()
        db.commit()


def test_moving_to_another_sign_in_server_keeps_the_admins_api_tokens(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O1 review r3, L5: the old refresh tokens aren't sent to the new server (which would
    answer invalid_grant, end the session and stop the tokens for good)."""
    from test_sso_api import check

    idp = home(kitchen, monkeypatch, "id.example.org", off=False)
    there, app = _make_token_and_sso_session(kitchen, idp)
    other = "https://id.example.org/realms/new"
    idp.issuer = other
    idp.refresh_tokens.clear()  # the new server never gave that token
    saved = kitchen.put(f"{API}/sso/settings", json={**SETUP, "client_secret": "", "issuer": other})
    assert saved.is_success, saved.text
    _due_now(kitchen)
    assert check(kitchen) == 0
    assert app.get(f"{API}/me").status_code == 200
    assert there.get(f"{API}/me").status_code == 200
    assert not [s for s in idp.seen if s.method == "POST" and b"refresh_token" in s.body]


def test_the_hourly_job_skips_a_sign_in_from_another_issuer(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even if a token from the old server is still there (say, a restored backup), a login
    linked at another issuer is not asked about."""
    from sqlalchemy import update
    from test_sso_api import check

    from mealwright.models import Login

    idp = home(kitchen, monkeypatch, "id.example.org", off=False)
    _there, app = _make_token_and_sso_session(kitchen, idp)
    idp.refresh_tokens.clear()  # a token the server would refuse
    with cast(Any, kitchen.app).state.sessionmaker() as db:
        db.execute(
            update(Login)
            .where(Login.username == "tess")
            .values(sso_issuer="https://old.example.org")
        )
        db.commit()
    _due_now(kitchen)
    assert check(kitchen) == 0
    assert app.get(f"{API}/me").status_code == 200
    assert not [s for s in idp.seen if s.method == "POST" and b"refresh_token" in s.body]


def test_a_members_single_sign_on_sign_in_does_not_prove_the_setup(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O1 review r3, L6: only an Admin's sign-in is proof that an admin can still get in."""
    idp = home(kitchen, monkeypatch, "id.example.org", off=False)
    changed = {**SETUP, "client_secret": "", "anyone_else": "member"}  # who gets in changed
    assert kitchen.put(f"{API}/sso/settings", json=changed).is_success
    from test_sso_api import person_here

    person_here(kitchen, "ayla")  # their person, with the same username (Pe3/M2)
    member = browser(kitchen)
    url = str(member.get(f"{API}/sso/start", follow_redirects=False).headers["location"])
    code, state = idp.sign_in(url, sub="someone", extra={"groups": []})
    done = member.post(f"{API}/sso/finish", json={"state": state, "code": code})
    assert done.status_code == 200 and done.json()["me"]["role"] == "member"
    off = kitchen.put(f"{API}/sso/password-sign-in", json={"on": False})
    assert off.status_code == 409 and off.json()["code"] == "passwords_needed"


def _sso_only_admin_with_a_token(
    kitchen: TestClient, idp: FakeProvider
) -> tuple[TestClient, TestClient]:
    """Wren: an admin made by their first single sign-on sign-in (no password), with an API
    token that works."""
    from sync_kit import ok
    from test_sso_api import sign_in

    wren = browser(kitchen)
    done, _ = sign_in(wren, idp, sub="wren", extra=ADMIN_GROUPS)
    assert done.status_code == 200 and done.json()["me"]["role"] == "admin"
    made = ok(wren.post(f"{API}/api-tokens", json={"name": "HA", "scope": "full"}), 201)
    app = TestClient(kitchen.app, base_url="https://testserver")
    app.headers["Authorization"] = f"Bearer {made['token']}"
    assert app.get(f"{API}/me").status_code == 200
    return wren, app


def test_an_admin_the_groups_no_longer_let_in_loses_their_api_tokens(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O2 review r2, finding 1, branch `not_let_in`: refused at sign-in, the tokens stop too
    (committed before the refusal, which rolls back)."""
    from test_sso_api import sign_in

    idp = home(kitchen, monkeypatch, "id.example.org", off=False)
    _, app = _sso_only_admin_with_a_token(kitchen, idp)
    nobody = {**SETUP, "client_secret": "", "group_roles": [], "anyone_else": "none"}
    assert kitchen.put(f"{API}/sso/settings", json=nobody).is_success
    refused, _ = sign_in(browser(kitchen), idp, sub="wren", extra={"groups": []})
    assert refused.status_code == 400 and refused.json()["code"] == "not_let_in"
    assert app.get(f"{API}/me").status_code == 401


def test_an_admin_taken_out_of_the_household_loses_their_api_tokens_at_their_next_sign_in(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Branch `removed`."""
    from sqlalchemy import update
    from test_sso_api import sign_in

    from mealwright.models import Login, Member

    idp = home(kitchen, monkeypatch, "id.example.org", off=False)
    _, app = _sso_only_admin_with_a_token(kitchen, idp)
    with cast(Any, kitchen.app).state.sessionmaker() as db:
        member = db.query(Login).filter(Login.sso_subject == "wren").one().member_id
        db.execute(update(Member).where(Member.id == member).values(removed_at=utcnow()))
        db.commit()
    refused, _ = sign_in(browser(kitchen), idp, sub="wren", extra=ADMIN_GROUPS)
    assert refused.status_code == 400 and refused.json()["code"] == "removed"
    assert app.get(f"{API}/me").status_code == 401
