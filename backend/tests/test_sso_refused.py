"""A refused known login (O2 review r3, findings 1, 2 and 5): its tokens and sign-ins stop,
except for the household's last admin who can still sign in by password."""

# ruff: noqa: F811

from typing import Any, cast

import pytest
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
    refusals = [r for r in caplog.records if "refused (" in r.getMessage()]
    assert refusals  # a refusal is a warning, on the one logger (D4, BE25)
    assert {(r.levelno, r.name) for r in refusals} == {(logging.WARNING, "mealwright.sign_in")}


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


def _people(client: TestClient) -> dict[str, int]:
    return {p["name"]: p["id"] for p in ok(client.get(f"{API}/people"))["people"]}


def test_a_refused_admin_is_signed_out_only_while_another_admin_can_get_in(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """O2 review r5, findings 1 and 3, and #205 (d). Two linked admins, passwords off, the groups
    drop both. At sign-in the sign-in server is the one refusing, so being linked is no way in
    (nor is a live sign-in): the first refusal leaves that admin's sign-ins, and so does the
    second's."""
    lorna = browser(sso_only)
    sign_in(lorna, idp, sub="lorna", extra=ADMIN_GROUPS)
    first, _ = sign_in(browser(sso_only), idp, sub="k", extra={"groups": []})
    assert first.status_code != 200
    assert sso_only.get(f"{API}/sso/settings").status_code == 200  # the first: kept
    second, _ = sign_in(browser(sso_only), idp, sub="lorna", extra={"groups": []})
    assert second.status_code != 200
    assert lorna.get(f"{API}/sso/settings").status_code == 200  # the second: kept too


def test_a_refused_admin_is_signed_out_when_another_admin_has_a_working_password(
    admin: TestClient, idp: FakeProvider
) -> None:
    """#205 (d): the other way in that does count. Sam has a password and passwords work."""
    from test_sso_api import _add_admin

    _add_admin(admin, "sam")
    sign_in(admin, idp, path="/sso/test", sub="k", extra=ADMIN_GROUPS)
    assert admin.post(f"{API}/sso/link").is_success
    first, _ = sign_in(browser(admin), idp, sub="k", extra={"groups": []})
    assert first.status_code != 200
    assert admin.get(f"{API}/me").status_code == 401


def test_a_linked_admin_with_no_live_sign_in_is_no_way_in(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """The same, the other order: Wren is linked but has no sign-in left, so Tess's refusal
    leaves his sign-ins (the household can't be locked out)."""
    wren = browser(sso_only)
    sign_in(wren, idp, sub="wren", extra=ADMIN_GROUPS)
    with cast(Any, sso_only.app).state.sessionmaker() as db:
        for session in db.scalars(select(Session).where(Session.login_id != 1)):
            db.delete(session)
        db.commit()
    first, _ = sign_in(browser(sso_only), idp, sub="k", extra={"groups": []})
    assert first.status_code != 200
    assert sso_only.get(f"{API}/sso/settings").status_code == 200


def test_a_sole_admin_with_no_password_keeps_their_sign_ins_with_passwords_on(
    admin: TestClient, idp: FakeProvider
) -> None:
    """O2 review r5, finding 2: Wren (made by single sign-on, no password) is the only admin
    left; refused, they keep their sign-ins and lose their token."""
    wren = browser(admin)
    sign_in(wren, idp, sub="wren", extra=ADMIN_GROUPS)
    kid = _people(wren)["Tess"]
    assert wren.patch(f"{API}/people/{kid}", json={"role": "member"}).is_success
    token = a_token(wren)
    refused, _ = sign_in(browser(admin), idp, sub="wren", extra={"groups": []})
    assert refused.status_code != 200
    assert wren.get(f"{API}/sso/settings").status_code == 200
    assert token.get(f"{API}/me").status_code == 401


def _admins(db_app: Any) -> list[str]:
    with db_app.state.sessionmaker() as db:
        return sorted(db.scalars(select(Login.username).where(Login.role == "admin")))


def test_demoting_by_groups_never_leaves_no_admin_tess_first(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """O2 review r8, finding 1. Passwords off, two linked admins signed in. The admin group goes
    and the first admin is in users: he is demoted (the other admin's accepted link is a way in that
    lasts); then the other, in no group, is refused and stays the admin."""
    wren = browser(sso_only)
    sign_in(wren, idp, sub="wren", extra=ADMIN_GROUPS)
    sam = browser(sso_only)
    demoted, _ = sign_in(sam, idp, sub="k", extra={"groups": ["mealwright-users"]})
    assert demoted.json()["me"]["role"] == "member"
    # A Member makes no API token.
    assert sam.post(f"{API}/api-tokens", json={"name": "HA", "scope": "full"}).status_code == 403
    refused, _ = sign_in(browser(sso_only), idp, sub="wren", extra={"groups": []})
    assert refused.status_code != 200
    assert len(_admins(sso_only.app)) == 1
    assert wren.get(f"{API}/sso/settings").status_code == 200


def test_a_demotion_by_groups_waits_when_the_other_admin_has_only_a_live_sign_in(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """#205 (d): Sam is signed in but has no password and no link: no way in that lasts."""
    from datetime import timedelta

    from mealwright.auth import now

    with cast(Any, sso_only.app).state.sessionmaker() as db:
        sam = Login(household_id=1, username="sam", name="Sam", role="admin")
        db.add(sam)
        db.flush()
        db.add(
            Session(
                household_id=1,
                login_id=sam.id,
                token_hash="c" * 64,
                remember=False,
                expires_at=now() + timedelta(days=1),
            )
        )
        db.commit()
    kept, _ = sign_in(browser(sso_only), idp, sub="k", extra={"groups": ["mealwright-users"]})
    assert kept.json()["me"]["role"] == "admin"


def test_demoting_by_groups_never_leaves_no_admin_wren_first(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """The other order: Wren is refused first (Tess is signed in, so she loses hers); then
    Tess, in users only, would be demoted but nobody else can get in, so he stays admin."""
    wren = browser(sso_only)
    sign_in(wren, idp, sub="wren", extra=ADMIN_GROUPS)
    refused, _ = sign_in(browser(sso_only), idp, sub="wren", extra={"groups": []})
    assert refused.status_code != 200
    kept, _ = sign_in(browser(sso_only), idp, sub="k", extra={"groups": ["mealwright-users"]})
    assert kept.json()["me"]["role"] == "admin"
    assert "tess" in _admins(sso_only.app)


def test_another_admins_expired_sign_in_is_no_way_in(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """O2 review r8, finding 3. Wren's only sign-in has run out: Tess's refusal leaves his.
    Fails if `Session.expires_at > now()` is dropped from `another_admin_gets_in`."""
    from datetime import timedelta

    from mealwright.auth import now

    sign_in(browser(sso_only), idp, sub="wren", extra=ADMIN_GROUPS)
    with cast(Any, sso_only.app).state.sessionmaker() as db:
        for session in db.scalars(select(Session).where(Session.login_id != 1)):
            session.expires_at = now() - timedelta(days=1)
        db.commit()
    refused, _ = sign_in(browser(sso_only), idp, sub="k", extra={"groups": []})
    assert refused.status_code != 200
    assert sso_only.get(f"{API}/sso/settings").status_code == 200


def test_a_group_demotion_needs_the_other_admin_to_be_able_to_sign_in_again(
    admin: TestClient, idp: FakeProvider
) -> None:
    """O2 review r9, finding 1. Joss is an admin with a password, signed in from before
    passwords went off; Tess links himself and turns passwords off. The provider sends him
    only the users group: Joss's sign-in will run out and she has no way back in, so he stays
    admin. Fails when a still-signed-in admin counts for a demotion."""
    from test_sso_api import _add_admin

    _add_admin(admin, "joss")
    joss = browser(admin)
    assert joss.post(
        f"{API}/session", json={"username": "joss", "password": "joss's own password"}
    ).is_success
    sign_in(admin, idp, path="/sso/test", sub="k", extra=ADMIN_GROUPS)
    assert admin.post(f"{API}/sso/link").is_success
    assert admin.put(f"{API}/sso/password-sign-in", json={"on": False}).is_success
    result, _ = sign_in(browser(admin), idp, sub="k", extra={"groups": ["mealwright-users"]})
    assert result.json()["me"]["role"] == "admin"


def test_an_admin_demoted_by_the_groups_leaves_no_reset_link_behind(
    admin: TestClient, idp: FakeProvider
) -> None:
    """16b security pass S-M1 d (proposed, for cabledrawer): as when an admin makes them a
    member, every unused Reset password link in the household goes."""
    noor = browser(admin)
    done, _ = sign_in(noor, idp, sub="noor", extra=ADMIN_GROUPS)
    assert done.json()["me"]["role"] == "admin"
    lorna = ok(admin.post(f"{API}/people", json={"name": "Lorna"}), 201)
    lorna_id = next(p["id"] for p in lorna["people"] if p["name"] == "Lorna")
    joined = ok(admin.post(f"{API}/people/{lorna_id}/login", json={"username": "lorna"}), 201)
    fresh = TestClient(admin.app, base_url="https://testserver")
    secret = joined["path"].removeprefix("/join#")
    ok(fresh.post(f"{API}/join", json={"token": secret, "password": "lorna's long password"}))
    made = ok(noor.post(f"{API}/people/{lorna_id}/reset-password"), 201)
    token = made["path"].removeprefix("/reset#")
    demoted, _ = sign_in(browser(admin), idp, sub="noor", extra={"groups": ["mealwright-users"]})
    assert demoted.json()["me"]["role"] == "member"
    look = TestClient(admin.app, base_url="https://testserver")
    assert look.post(f"{API}/join/look", json={"token": token}).status_code == 404


def test_an_admin_refused_by_the_groups_leaves_no_reset_link_behind(
    admin: TestClient, idp: FakeProvider
) -> None:
    """16b security pass S-M1 d (lead, 14 Nov; proposed, for cabledrawer): an admin the groups no
    longer let in is treated as one made a member: every unused Reset password link in the
    household goes, and join links stay."""
    noor = browser(admin)
    done, _ = sign_in(noor, idp, sub="noor", extra=ADMIN_GROUPS)
    assert done.json()["me"]["role"] == "admin"
    lorna = ok(admin.post(f"{API}/people", json={"name": "Lorna"}), 201)
    lorna_id = next(p["id"] for p in lorna["people"] if p["name"] == "Lorna")
    joined = ok(admin.post(f"{API}/people/{lorna_id}/login", json={"username": "lorna"}), 201)
    fresh = TestClient(admin.app, base_url="https://testserver")
    secret = joined["path"].removeprefix("/join#")
    ok(fresh.post(f"{API}/join", json={"token": secret, "password": "lorna's long password"}))
    made = ok(noor.post(f"{API}/people/{lorna_id}/reset-password"), 201)
    token = made["path"].removeprefix("/reset#")
    sam = ok(admin.post(f"{API}/people", json={"name": "Sam"}), 201)
    sam_id = next(p["id"] for p in sam["people"] if p["name"] == "Sam")
    sams = ok(admin.post(f"{API}/people/{sam_id}/login", json={"username": "sam"}), 201)
    refused, _ = sign_in(browser(admin), idp, sub="noor", extra={"groups": []})
    assert refused.status_code != 200
    look = TestClient(admin.app, base_url="https://testserver")
    assert look.post(f"{API}/join/look", json={"token": token}).status_code == 404
    sam_secret = sams["path"].removeprefix("/join#")
    assert look.post(f"{API}/join/look", json={"token": sam_secret}).status_code == 200


def _lorna_with_a_login(admin: TestClient) -> int:
    lorna = ok(admin.post(f"{API}/people", json={"name": "Lorna"}), 201)
    lorna_id = next(p["id"] for p in lorna["people"] if p["name"] == "Lorna")
    joined = ok(admin.post(f"{API}/people/{lorna_id}/login", json={"username": "lorna"}), 201)
    fresh = TestClient(admin.app, base_url="https://testserver")
    secret = joined["path"].removeprefix("/join#")
    ok(fresh.post(f"{API}/join", json={"token": secret, "password": "lorna's long password"}))
    return lorna_id


def _new_reset_token(admin: TestClient, lorna_id: int) -> bool:
    made = ok(admin.post(f"{API}/people/{lorna_id}/reset-password"), 201)
    return str(made["path"].removeprefix("/reset#"))


def test_a_refusal_that_ends_nothing_leaves_the_households_reset_links(
    admin: TestClient, idp: FakeProvider
) -> None:
    """B7 low: the same refusal again (or a removed login's) must not wipe the household's reset
    links each time; the first refusal that ended something did already."""
    noor = browser(admin)
    sign_in(noor, idp, sub="noor", extra=ADMIN_GROUPS)
    lorna_id = _lorna_with_a_login(admin)
    refused, _ = sign_in(browser(admin), idp, sub="noor", extra={"groups": []})
    assert refused.status_code != 200  # ended Noor's sign-in and the links of that time
    token = _new_reset_token(admin, lorna_id)  # a new link, made after
    again, _ = sign_in(browser(admin), idp, sub="noor", extra={"groups": []})
    assert again.status_code != 200  # nothing left to end
    look = TestClient(admin.app, base_url="https://testserver")
    assert look.post(f"{API}/join/look", json={"token": token}).status_code == 200


def test_a_removed_admins_refused_sign_in_leaves_the_households_reset_links(
    admin: TestClient, idp: FakeProvider
) -> None:
    noor = browser(admin)
    sign_in(noor, idp, sub="noor", extra=ADMIN_GROUPS)
    lorna_id = _lorna_with_a_login(admin)
    noor_id = next(
        p["id"]
        for p in admin.get(f"{API}/people").json()["people"]
        if p["login"] and p["login"]["sso_linked"] and not p["is_me"]
    )
    ok(admin.delete(f"{API}/people/{noor_id}"))
    token = _new_reset_token(admin, lorna_id)
    gone, _ = sign_in(browser(admin), idp, sub="noor", extra=ADMIN_GROUPS)
    assert gone.status_code != 200
    look = TestClient(admin.app, base_url="https://testserver")
    assert look.post(f"{API}/join/look", json={"token": token}).status_code == 200


@pytest.mark.parametrize("groups", [["mealwright-users"], []], ids=["made a member", "refused"])
def test_no_admins_sign_in_link_outlives_the_groups_ending_the_admin_who_made_it(
    admin: TestClient, idp: FakeProvider, groups: list[str]
) -> None:
    """16b security re-check S2-M1 (proposed, for cabledrawer): Noor adds Sam as an admin and keeps
    his sign-in link; when the groups make her a member or no longer let her in, it ends. A
    Member's sign-in link stays."""
    noor = browser(admin)
    done, _ = sign_in(noor, idp, sub="noor", extra=ADMIN_GROUPS)
    assert done.json()["me"]["role"] == "admin"
    links = {}
    for name, role in (("Sam", "admin"), ("Lorna", "member")):
        added = ok(noor.post(f"{API}/people", json={"name": name}), 201)
        person = next(p["id"] for p in added["people"] if p["name"] == name)
        body = {"username": name.lower(), "role": role}
        made = ok(noor.post(f"{API}/people/{person}/login", json=body), 201)
        links[name] = made["path"].removeprefix("/join#")
    sign_in(browser(admin), idp, sub="noor", extra={"groups": groups})
    look = TestClient(admin.app, base_url="https://testserver")
    assert look.post(f"{API}/join/look", json={"token": links["Sam"]}).status_code == 404
    assert look.post(f"{API}/join/look", json={"token": links["Lorna"]}).status_code == 200
