"""A refused known login (O2 review r3, findings 1, 2 and 5): its tokens and sign-ins stop,
except for the household's last admin who can still sign in by password."""

# ruff: noqa: F811

from typing import Any, cast

from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_sso_api import (  # noqa: F401
    ADMIN_GROUPS,
    API,
    PASSWORD,
    admin,
    browser,
    idp,
    sign_in,
    sso_only,
)

from mealwright.models import Login, Session


def a_token(client: TestClient) -> TestClient:
    made = ok(client.post(f"{API}/api-tokens", json={"name": "HA", "scope": "full"}), 201)
    other = TestClient(client.app, base_url="https://testserver")
    other.headers["Authorization"] = f"Bearer {made['token']}"
    return other


def test_the_last_admin_with_a_password_keeps_their_token_while_passwords_work(
    admin: TestClient, idp: FakeProvider
) -> None:
    sign_in(admin, idp, path="/sso/test", sub="k", extra=ADMIN_GROUPS)
    assert admin.post(f"{API}/sso/link").is_success
    token = a_token(admin)
    refused, _ = sign_in(browser(admin), idp, sub="k", extra={"groups": []})
    assert refused.status_code != 200
    assert token.get(f"{API}/me").status_code == 200  # they stay an admin and can still get in
    assert admin.get(f"{API}/me").status_code == 200  # and so does their session


def test_with_passwords_off_the_refused_last_admin_loses_their_token(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """Review r3, finding 1. Fails when the exception ignores the password setting: nobody
    could sign in to delete that token."""
    token = a_token(sso_only)
    refused, _ = sign_in(browser(sso_only), idp, sub="k", extra={"groups": []})
    assert refused.status_code != 200
    assert token.get(f"{API}/me").status_code == 401


def test_a_refused_admin_is_signed_out_everywhere_and_cannot_make_a_new_token(
    admin: TestClient, idp: FakeProvider
) -> None:
    """Review r3, finding 2. Fails without ending the login's sessions in the refusal."""
    wren = browser(admin)
    done, _ = sign_in(wren, idp, sub="wren", extra=ADMIN_GROUPS)
    assert done.json()["me"]["role"] == "admin"
    token = a_token(wren)
    refused, _ = sign_in(browser(admin), idp, sub="wren", extra={"groups": []})
    assert refused.status_code != 200
    assert token.get(f"{API}/me").status_code == 401
    assert wren.get(f"{API}/me").status_code == 401
    assert wren.post(f"{API}/api-tokens", json={"name": "HA2", "scope": "full"}).status_code == 401
    with cast(Any, admin.app).state.sessionmaker() as db:
        assert db.scalars(select(Session).where(Session.sso.is_(True))).all() == []


def test_the_refusal_is_logged_with_the_login_number_never_a_name(
    admin: TestClient, idp: FakeProvider, caplog: Any
) -> None:
    """Review r3, finding 6: the log line gives the login's number, as the hourly job's does."""
    import logging

    wren = browser(admin)
    sign_in(wren, idp, sub="wren", extra=ADMIN_GROUPS)
    with cast(Any, admin.app).state.sessionmaker() as db:
        number = db.scalar(select(Login.id).where(Login.sso_subject == "wren"))
    with caplog.at_level(logging.INFO, logger="mealwright"):
        sign_in(browser(admin), idp, sub="wren", extra={"groups": []})
    lines = [
        r.getMessage()
        for r in caplog.records
        if "login" in r.getMessage() and "refused" in r.getMessage()
    ]
    assert lines == [
        f"Single sign-on: login {number} refused (not_let_in); "
        "their sign-ins and API tokens stopped"
    ]


def test_the_only_admin_with_passwords_off_keeps_their_sign_ins_but_loses_their_tokens(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """O2 review r4, finding 1 (proposed, for cabledrawer). A refused sign-in on a phone must not
    lock the household out: the laptop stays signed in to turn passwords back on; the token
    stops. Fails when the refusal ends every session of the last admin."""
    token = a_token(sso_only)
    refused, _ = sign_in(browser(sso_only), idp, sub="k", extra={"groups": []})
    assert refused.status_code != 200
    assert sso_only.get(f"{API}/me").status_code == 200  # the laptop
    assert sso_only.get(f"{API}/sso/settings").status_code == 200
    assert token.get(f"{API}/me").status_code == 401
    assert browser(sso_only).post(f"{API}/session", json=PASSWORD).status_code == 403
    # And from the laptop they can turn passwords back on.
    assert sso_only.put(f"{API}/sso/password-sign-in", json={"on": True}).is_success
    assert browser(sso_only).post(f"{API}/session", json=PASSWORD).status_code == 200


def test_a_refused_last_admin_is_logged_as_keeping_their_sign_ins(
    sso_only: TestClient, idp: FakeProvider, caplog: Any
) -> None:
    import logging

    with caplog.at_level(logging.INFO, logger="mealwright"):
        sign_in(browser(sso_only), idp, sub="k", extra={"groups": []})
    lines = [
        r.getMessage()
        for r in caplog.records
        if "login" in r.getMessage() and "refused" in r.getMessage()
    ]
    assert len(lines) == 1 and "sign-ins kept, as the last admin" in lines[0]


async def _next_or_end(gen: Any) -> Any:
    import asyncio

    try:
        return await asyncio.wait_for(gen.__anext__(), 2.0)
    except StopAsyncIteration:
        return None


def test_a_refused_logins_open_event_stream_ends_at_once(
    admin: TestClient, idp: FakeProvider
) -> None:
    """O2 review r4, finding 4. The stream's keep-alive is 30 s here: it must not be what ends
    it. Fails without `events.end_session` for the refused login's sessions."""
    import asyncio

    from mealwright.api.v1.events import stream
    from mealwright.auth import COOKIE

    wren = browser(admin)
    sign_in(wren, idp, sub="wren", extra=ADMIN_GROUPS)
    app = cast(Any, admin.app)
    token = wren.cookies[COOKIE]
    with app.state.sessionmaker() as db:
        sid = db.scalars(select(Session.id).where(Session.sso.is_(True))).one()

    async def go() -> list[str]:
        sub = app.state.events.subscribe(1, sid)
        gen = stream(app.state.sessionmaker, sub, app.state.events.unsubscribe, token, 0, 30.0)
        await _next_or_end(gen)  # the first frame
        await asyncio.to_thread(
            lambda: sign_in(browser(admin), idp, sub="wren", extra={"groups": []})
        )
        seen = []
        while (frame := await _next_or_end(gen)) is not None:
            seen.append(frame)
        return seen

    frames = asyncio.run(go())
    assert any("signed_out" in f for f in frames), frames
