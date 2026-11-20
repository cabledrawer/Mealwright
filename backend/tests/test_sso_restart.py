"""O1 review r4: a restart must not reopen password sign-in; the memory of the sign-in
server's address (kept in memory only) is refilled at start, and behaves at its edges."""

from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_sso_api import API, PASSWORD, SETUP, browser, check
from test_sso_passwords_off_class import (
    _due_now,
    _make_token_and_sso_session,
    home,
    look_up_down,
    passwords_work,
)

from mealwright import jobs, outbound, sso
from mealwright.models import Session


def restart(kitchen: TestClient) -> None:
    """What a restart loses: everything in memory (then the start job runs, if asked)."""
    app = cast(Any, kitchen.app)
    sso.forget_remembered()
    sso.cache.forget()
    app.state.sso_proven.clear()
    app.state.sso_tests.clear()
    app.state.sso_links.clear()


def start_job(kitchen: TestClient) -> None:
    app = cast(Any, kitchen.app)
    jobs.check_single_sign_on(
        app.state.outbound,
        app.state.sessionmaker,
        app.state.settings.data_dir,
        app.state.events,
    )


def test_a_restart_then_the_start_job_keeps_passwords_off(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fails without `fill_memory`: the empty memory read as "can't start"."""
    home(kitchen, monkeypatch, "id.example.org")
    restart(kitchen)
    assert passwords_work(kitchen)  # the moment before the job runs: can't tell
    start_job(kitchen)
    anon = browser(kitchen)
    assert anon.get(f"{API}/sign-in-options").json()["password"] is False
    assert anon.post(f"{API}/session", json=PASSWORD).status_code == 403


def test_a_restart_with_the_look_up_failing_leaves_passwords_working(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    home(kitchen, monkeypatch, "id.example.org")
    restart(kitchen)
    monkeypatch.setattr(outbound, "_lookup", look_up_down)
    start_job(kitchen)
    assert browser(kitchen).get(f"{API}/sign-in-options").json()["password"] is True
    assert passwords_work(kitchen)


def test_the_start_job_makes_no_look_up_when_nothing_needs_one(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Passwords on, or the name already remembered, or the switch off: no look-up."""
    home(kitchen, monkeypatch, "id.example.org")
    calls: list[str] = []

    def count(host: str, port: int) -> list[str]:
        calls.append(host)
        raise OSError("no")

    monkeypatch.setattr(outbound, "_lookup", count)
    start_job(kitchen)  # remembered already
    assert kitchen.put(f"{API}/sso/password-sign-in", json={"on": True}).is_success
    sso.forget_remembered()
    start_job(kitchen)  # passwords on
    assert kitchen.put(f"{API}/privacy/switches/single_sign_on", json={"on": False}).is_success
    from sqlalchemy import update

    from mealwright.models import SsoSettings

    with cast(Any, kitchen.app).state.sessionmaker() as db:  # passwords off again, stored
        db.execute(update(SsoSettings).values(password_sign_in=False))
        db.commit()
    sso.forget_remembered()
    start_job(kitchen)  # switch off
    assert calls == []


def test_a_stale_remembered_address_counts_as_cannot_start(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O1 review r4, L2. Fails with the address remembered only after it passed the check."""
    idp = home(kitchen, monkeypatch, "unrelated.example.net", address="93.184.216.40")
    idp.address = "192.168.1.50"  # the name moved to a private address nobody listed
    sso.cache.forget()
    started = browser(kitchen).get(f"{API}/sso/start")
    assert "own_network" in started.headers["location"]
    assert passwords_work(kitchen)


def test_the_memory_drops_its_oldest_name_not_everything(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O1 review r4, 5c. Fails with the memory emptied at 51 names."""
    home(kitchen, monkeypatch, "id.example.org")
    first = sso.remembered("id.example.org")
    assert first
    for n in range(49):
        sso.remember(f"h{n}.example.org", first)
    sso.remember("id.example.org", first)  # used again: now the newest
    for n in range(49, 54):
        sso.remember(f"h{n}.example.org", first)
    assert len(sso._seen) <= 50
    assert sso.remembered("h53.example.org") == first
    assert sso.remembered("h10.example.org") == first  # not emptied
    assert sso.remembered("h0.example.org") is None  # the oldest went
    assert sso.remembered("h4.example.org") is None
    assert sso.remembered("h5.example.org") == first
    assert sso.remembered("id.example.org") == first  # used lately, so it stayed


def test_a_client_id_only_change_drops_the_refresh_tokens(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O1 review r4, 5a. Fails without the save's refresh-token drop: the server (which
    refuses the old token for the new client) would end the session and stop the API token."""
    idp = home(kitchen, monkeypatch, "id.example.org", off=False)
    there, app = _make_token_and_sso_session(kitchen, idp)
    idp.refresh_tokens.clear()  # what the server says to a token for another client
    saved = kitchen.put(
        f"{API}/sso/settings", json={**SETUP, "client_secret": "", "client_id": "another-client"}
    )
    assert saved.is_success, saved.text
    with cast(Any, kitchen.app).state.sessionmaker() as db:
        kept = [bool(s.sso_refresh_sealed) for s in db.scalars(select(Session).where(Session.sso))]
    assert kept and not any(kept)
    _due_now(kitchen)
    assert check(kitchen) == 0
    assert app.get(f"{API}/me").status_code == 200
    assert there.get(f"{API}/me").status_code == 200


def test_a_save_in_the_fall_back_keeps_the_stored_choice(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O1 review r4, finding 3. The settings give the stored choice beside the effective
    value; sending it back in a save keeps passwords off once single sign-on starts again."""
    home(kitchen, monkeypatch, "id.example.org")
    restart(kitchen)  # memory empty: passwords work for now
    shown = kitchen.get(f"{API}/sso/settings").json()
    assert shown["password_sign_in"] is True  # what counts
    assert shown["password_sign_in_stored"] is False  # what the admin chose
    body = {**SETUP, "client_secret": "", "button_name": "Sign in"}
    saved = kitchen.put(
        f"{API}/sso/settings", json={**body, "password_sign_in": shown["password_sign_in_stored"]}
    )
    assert saved.is_success and saved.json()["password_sign_in_stored"] is False
    start_job(kitchen)  # the memory is filled again
    assert browser(kitchen).post(f"{API}/session", json=PASSWORD).status_code == 403


def test_turning_passwords_off_while_single_sign_on_cannot_start_is_refused(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    home(kitchen, monkeypatch, "id.example.org")
    restart(kitchen)
    refused = kitchen.put(f"{API}/sso/password-sign-in", json={"on": False})
    assert refused.status_code == 409 and refused.json()["code"] == "passwords_needed"
    start_job(kitchen)
    assert kitchen.put(f"{API}/sso/password-sign-in", json={"on": False}).is_success


def test_one_wrong_answer_for_the_name_is_looked_at_again_by_the_job(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """O1 review r5, finding 1. Fails when the job skips any remembered name: the wrong answer
    (an address not on Your own network) stayed remembered, so passwords stayed open."""
    idp = home(kitchen, monkeypatch, "192.168.1.50")  # listed by address
    right = idp.address
    restart(kitchen)
    idp.address = "10.66.66.66"  # one wrong answer
    start_job(kitchen)
    assert passwords_work(kitchen)  # can't start: passwords work
    idp.address = right  # the name answers right again
    start_job(kitchen)
    assert browser(kitchen).get(f"{API}/sign-in-options").json()["password"] is False
    assert not passwords_work(kitchen)
