"""With passwords off, the hourly check never ends the only admin's last sign-in (cabledrawer
12 Nov; proposed, for cabledrawer): its tokens stop, the sign-in stays, Settings warns the admin."""

# ruff: noqa: F811, F401

import io
from typing import Any, cast

import pytest
from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from sqlalchemy import select
from test_sso_api import (
    ADMIN_GROUPS,
    API,
    PASSWORD,
    SETUP,
    admin,
    browser,
    check,
    idp,
    sign_in,
    sso_only,
)
from test_sso_refused import a_token

from mealwright import sso_accounts
from mealwright.auth import now
from mealwright.models import Login, Session


@pytest.fixture(autouse=True)
def no_old_warning() -> None:
    sso_accounts._kept.clear()


def _due(client: TestClient, subject: str) -> None:
    with cast(Any, client.app).state.sessionmaker() as db:
        for session in db.scalars(
            select(Session)
            .join(Login, Login.id == Session.login_id)
            .where(Session.sso.is_(True), Login.sso_subject == subject)
        ):
            session.sso_check_at = now()
        db.commit()


def _unlink_first_admin(client: TestClient) -> None:
    """The set-up admin's single sign-on link goes (passwords are off), so they are no way in."""
    with cast(Any, client.app).state.sessionmaker() as db:
        login = db.get(Login, 1)
        assert login is not None
        login.sso_issuer = login.sso_subject = None
        db.commit()


def _live_only_admin(client: TestClient) -> None:
    """Sam: an admin with no password and no link, signed in right now."""
    from datetime import timedelta

    with cast(Any, client.app).state.sessionmaker() as db:
        login = Login(household_id=1, username="sam", name="Sam", role="admin")
        db.add(login)
        db.flush()
        db.add(
            Session(
                household_id=1,
                login_id=login.id,
                token_hash="b" * 64,
                remember=False,
                expires_at=now() + timedelta(days=1),
            )
        )
        db.commit()


def _warning(client: TestClient) -> str | None:
    return cast("str | None", client.get(f"{API}/sso/settings").json()["kept_warning"])


def test_the_only_admins_last_sign_in_is_kept_with_a_warning_while_passwords_are_off(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """Fails when the check ends that sign-in: nobody could get in but reset-admin."""
    phone = browser(sso_only)
    sign_in(phone, idp, sub="k", extra=ADMIN_GROUPS)
    token = a_token(phone)
    assert token.get(f"{API}/me").status_code == 200
    taken = set(idp.refresh_tokens)
    idp.refresh_tokens.clear()  # the sign-in server no longer accepts them
    _due(sso_only, "k")
    assert check(sso_only) == 0  # none ended
    assert phone.get(f"{API}/me").status_code == 200  # the sign-in stays
    assert token.get(f"{API}/me").status_code == 401  # the tokens stop
    warning = _warning(sso_only)
    assert warning is not None and warning.startswith("The sign-in server no longer accepts ")
    assert "only admin who can get in" in warning
    # A refresh that works again does not end the mark (the groups aren't asked on a refresh),
    # so the warning stays; a fresh sign-in the groups accept as an admin takes it away.
    idp.refresh_tokens.update(taken)
    _due(sso_only, "k")
    assert check(sso_only) == 0
    assert _warning(sso_only) is not None
    again, _ = sign_in(browser(sso_only), idp, sub="k", extra=ADMIN_GROUPS)
    assert again.status_code == 200
    assert _warning(sso_only) is None


def test_the_warning_goes_when_passwords_are_back_on(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    phone = browser(sso_only)
    sign_in(phone, idp, sub="k", extra=ADMIN_GROUPS)
    idp.refresh_tokens.clear()
    _due(sso_only, "k")
    check(sso_only)
    assert _warning(sso_only) is not None
    assert sso_only.put(f"{API}/sso/password-sign-in", json={"on": True}).is_success
    assert _warning(sso_only) is None


def test_with_another_admin_who_can_get_in_the_sign_in_ends_as_before(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """Lorna is linked and not refused: she is a way in that lasts, so Sam's refused sign-in
    ends (it was a live sign-in that counted before 0.9.5; now the accepted link does)."""
    lorna = browser(sso_only)
    sign_in(lorna, idp, sub="lorna", extra=ADMIN_GROUPS)
    sam = browser(sso_only)
    sign_in(sam, idp, sub="k", extra=ADMIN_GROUPS)
    idp.refresh_tokens.clear()
    _due(sso_only, "k")
    assert check(sso_only) == 1
    assert sam.get(f"{API}/me").status_code == 401
    assert _warning(sso_only) is None
    # And Lorna can still get in: she is not marked.
    assert lorna.get(f"{API}/me").status_code == 200


def test_another_admins_live_sign_in_is_no_way_in_so_the_sign_in_is_kept(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """#205 (d), cabledrawer 12 Nov late: Sam is signed in but has no password and no link, so a
    sign-in that will end is no way in: the set-up admin's refused sign-in is kept."""
    _live_only_admin(sso_only)
    phone = browser(sso_only)
    sign_in(phone, idp, sub="k", extra=ADMIN_GROUPS)
    idp.refresh_tokens.clear()
    _due(sso_only, "k")
    assert check(sso_only) == 0
    assert phone.get(f"{API}/me").status_code == 200
    assert _warning(sso_only) is not None


SAM = {**ADMIN_GROUPS, "preferred_username": "sam"}


@pytest.mark.parametrize("first", ["lorna", "sam"])
def test_two_admins_taken_out_together_leave_one_who_can_get_in(
    sso_only: TestClient, idp: FakeProvider, first: str
) -> None:
    """Both linked admins are signed in and both are taken out at the sign-in server. Each counts
    the other (a link and a sign-in open now), so the first one's check ends, and that ends its
    sign-in: the other has nobody left and is kept. Exactly one stays, in either order, and
    nothing flips over later runs."""
    devices: dict[str, TestClient] = {}
    for who in (first, "sam" if first == "lorna" else "lorna"):
        devices[who] = browser(sso_only)
        sign_in(devices[who], idp, sub=who, extra=SAM if who == "sam" else ADMIN_GROUPS)
    _unlink_first_admin(sso_only)
    idp.refresh_tokens.clear()
    for _ in range(3):
        _due(sso_only, "lorna")
        _due(sso_only, "sam")
        check(sso_only)
        alive = sorted(c.get(f"{API}/me").status_code for c in devices.values())
        assert alive == [200, 401]


def test_a_signed_out_admin_with_a_link_is_no_way_in_that_lasts(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """#205 (c), as built before 0.9.5: Lorna is linked but signed out, so Sam, taken out at the
    sign-in server, is kept; and a demotion by the groups waits."""
    lorna, sam = browser(sso_only), browser(sso_only)
    sign_in(lorna, idp, sub="lorna", extra=ADMIN_GROUPS)
    sign_in(sam, idp, sub="sam", extra=SAM)
    assert lorna.delete(f"{API}/session").status_code == 204
    _unlink_first_admin(sso_only)
    idp.refresh_tokens.clear()
    _due(sso_only, "sam")
    assert check(sso_only) == 0
    assert sam.get(f"{API}/me").status_code == 200
    again, _ = sign_in(browser(sso_only), idp, sub="sam", extra={"groups": ["mealwright-users"]})
    assert again.json()["me"]["role"] == "admin"


def test_an_idle_sign_in_running_out_doesnt_mark_a_good_admin(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """One of Lorna's two devices has its token run out by itself: she isn't marked, so she is
    still a way in. Sam, then taken out at the sign-in server, has his sign-in ended, and Lorna
    can make him a Member or remove him."""
    lorna_phone, lorna_tablet, sam = browser(sso_only), browser(sso_only), browser(sso_only)
    seen = set(idp.refresh_tokens)
    sign_in(lorna_phone, idp, sub="lorna", extra=ADMIN_GROUPS)
    phone_token = (set(idp.refresh_tokens) - seen).pop()
    sign_in(lorna_tablet, idp, sub="lorna", extra=ADMIN_GROUPS)
    seen = set(idp.refresh_tokens)
    sign_in(sam, idp, sub="sam", extra=SAM)
    sam_token = (set(idp.refresh_tokens) - seen).pop()
    _unlink_first_admin(sso_only)
    idp.refresh_tokens.discard(phone_token)  # one device's sign-in runs out by itself
    _due(sso_only, "lorna")
    check(sso_only)
    assert _login_row(sso_only, "lorna").sso_refused_at is None
    assert lorna_tablet.get(f"{API}/me").status_code == 200
    idp.refresh_tokens.discard(sam_token)  # Sam is disabled at the sign-in server
    _due(sso_only, "sam")
    assert check(sso_only) == 1
    assert sam.get(f"{API}/me").status_code == 401
    assert _login_row(sso_only, "lorna").sso_refused_at is None
    people = lorna_tablet.get(f"{API}/people").json()["people"]
    sam_id = next(p["id"] for p in people if p["login"] and p["login"]["username"] == "sam")
    assert lorna_tablet.patch(f"{API}/people/{sam_id}", json={"role": "member"}).status_code == 200
    assert lorna_tablet.delete(f"{API}/people/{sam_id}").status_code == 200


def test_a_password_admin_whose_sso_sign_in_runs_out_isnt_marked(
    admin: TestClient, idp: FakeProvider
) -> None:
    """Passwords on. The set-up admin has a password; one of her single sign-on sign-ins runs
    out: not marked, she still makes API tokens, and she can step down once Sam has a password."""
    from test_sso_api import _add_admin

    sign_in(admin, idp, path="/sso/test", sub="k", extra=ADMIN_GROUPS)
    assert admin.post(f"{API}/sso/link").is_success
    phone = browser(admin)
    sign_in(phone, idp, sub="k", extra=ADMIN_GROUPS)
    idp.refresh_tokens.clear()
    _due(admin, "k")
    assert check(admin) == 1
    assert _login_row(admin, "k").sso_refused_at is None
    assert admin.post(f"{API}/api-tokens", json={"name": "HA", "scope": "full"}).status_code == 201
    _add_admin(admin, "sam")
    me = next(p["id"] for p in admin.get(f"{API}/people").json()["people"] if p["is_me"])
    assert admin.patch(f"{API}/people/{me}", json={"role": "member"}).status_code == 200


def test_with_another_admin_who_has_a_password_the_sign_in_ends_as_before(
    admin: TestClient, idp: FakeProvider
) -> None:
    """Passwords work and Sam has one: he is a way in, so the other admin's refused sign-in ends."""
    from test_sso_api import _add_admin

    _add_admin(admin, "sam")
    phone = browser(admin)
    sign_in(phone, idp, sub="k", extra=ADMIN_GROUPS)
    idp.refresh_tokens.clear()
    _due(admin, "k")
    assert check(admin) == 1
    assert phone.get(f"{API}/me").status_code == 401


def test_a_member_is_never_shown_the_warning(sso_only: TestClient, idp: FakeProvider) -> None:
    """The setup screen's answer is admins only (a Member is refused), so the warning isn't
    theirs to see."""
    member = browser(sso_only)
    sign_in(member, idp, sub="mem", extra={"groups": ["mealwright-users"]})
    assert member.get(f"{API}/sso/settings").status_code == 403


def test_the_warning_goes_when_the_kept_admin_has_no_sign_in_left(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """O2 pass, L: a kept admin who signs out is no longer someone the warning is about."""
    phone = browser(sso_only)
    sign_in(phone, idp, sub="k", extra=ADMIN_GROUPS)
    idp.refresh_tokens.clear()
    _due(sso_only, "k")
    check(sso_only)
    assert _warning(sso_only) is not None
    with cast(Any, sso_only.app).state.sessionmaker() as db:  # every sign-in of theirs is gone
        for session in db.scalars(select(Session)):
            db.delete(session)
        db.commit()
    with cast(Any, sso_only.app).state.sessionmaker() as db:
        data_dir = cast(Any, sso_only.app).state.settings.data_dir
        assert sso_accounts.kept_warning(db, data_dir, 1) is None


def test_the_only_admin_made_by_single_sign_on_keeps_their_sign_in_with_passwords_on(
    admin: TestClient, idp: FakeProvider
) -> None:
    """O2 pass, L: Wren (no password) is the only admin; the hourly check used to end her
    sign-in, as only reset-admin gets her back. Passwords are on, so the warning doesn't tell
    her to turn them on (proposed, for cabledrawer)."""
    from test_sso_refused import _people

    wren = browser(admin)
    sign_in(wren, idp, sub="wren", extra=ADMIN_GROUPS)
    kid = _people(wren)["Tess"]
    assert wren.patch(f"{API}/people/{kid}", json={"role": "member"}).is_success
    token = a_token(wren)
    idp.refresh_tokens.clear()
    _due(admin, "wren")
    assert check(admin) == 0
    assert wren.get(f"{API}/me").status_code == 200  # the sign-in stays
    assert token.get(f"{API}/me").status_code == 401  # the tokens stop
    warning = wren.get(f"{API}/sso/settings").json()["kept_warning"]
    assert warning is not None and warning.endswith("Fix it at the sign-in server.")


def _login_row(client: TestClient, subject: str) -> Any:
    with cast(Any, client.app).state.sessionmaker() as db:
        row = db.scalar(select(Login).where(Login.sso_subject == subject))
        db.expunge(row)
        return row


def test_a_kept_refused_admin_cant_make_a_token_that_outlives_the_keep(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """O2 fix13, M (cabledrawer 12 Nov, option A). X, refused but kept, used to make a token, sign
    out, and keep the token for good. Now the mark stops it: no new token, and one made after
    the mark doesn't work. The mark is on the login, so sign-out and a restart keep it."""
    from mealwright.models import ApiToken

    x = browser(sso_only)
    sign_in(x, idp, sub="x", extra=ADMIN_GROUPS)
    assert sso_only.delete(f"{API}/session").status_code == 204  # K is signed out
    _unlink_first_admin(sso_only)  # and not linked any more: X is the only way in
    idp.refresh_tokens.clear()
    _due(sso_only, "x")
    assert check(sso_only) == 0  # kept
    made = x.post(f"{API}/api-tokens", json={"name": "HA", "scope": "full"})
    assert made.status_code == 403 and made.json()["code"] == "sign_in_refused"
    # A token row made after the mark (by the old rule, or a race) doesn't work either.
    from mealwright.api_tokens import new_token, token_hash

    secret = new_token("full")
    with cast(Any, sso_only.app).state.sessionmaker() as db:
        login = db.scalar(select(Login).where(Login.sso_subject == "x"))
        assert login is not None and login.sso_refused_at is not None
        db.add(
            ApiToken(
                household_id=1,
                login_id=login.id,
                name="late",
                token_hash=token_hash(secret),
                scope="full",
            )
        )
        db.commit()
    late = TestClient(sso_only.app, base_url="https://testserver")
    late.headers["Authorization"] = f"Bearer {secret}"
    assert late.get(f"{API}/me").status_code == 401
    # Sign-out and a restart (nothing in memory) change nothing: the mark is in the database.
    sso_accounts._kept.clear()
    assert _login_row(sso_only, "x").sso_refused_at is not None
    assert late.get(f"{API}/me").status_code == 401


def test_the_mark_ends_when_the_sign_in_server_accepts_them_again_and_old_tokens_stay_dead(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    from mealwright.api_tokens import new_token, token_hash
    from mealwright.models import ApiToken

    x = browser(sso_only)
    sign_in(x, idp, sub="x", extra=ADMIN_GROUPS)
    assert sso_only.delete(f"{API}/session").status_code == 204  # nobody else is signed in
    _unlink_first_admin(sso_only)  # nor linked: X is the only way in
    taken = set(idp.refresh_tokens)
    idp.refresh_tokens.clear()
    _due(sso_only, "x")
    check(sso_only)
    assert _login_row(sso_only, "x").sso_refused_at is not None
    secret = new_token("full")
    with cast(Any, sso_only.app).state.sessionmaker() as db:
        login = db.scalar(select(Login).where(Login.sso_subject == "x"))
        assert login is not None
        db.add(
            ApiToken(
                household_id=1,
                login_id=login.id,
                name="late",
                token_hash=token_hash(secret),
                scope="full",
            )
        )
        db.commit()
    idp.refresh_tokens.update(taken)  # a refresh works again: the mark stands (fix13 review)
    _due(sso_only, "x")
    check(sso_only)
    assert _login_row(sso_only, "x").sso_refused_at is not None
    refused = x.post(f"{API}/api-tokens", json={"name": "HA", "scope": "full"})
    assert refused.status_code == 403
    accepted, _ = sign_in(browser(sso_only), idp, sub="x", extra=ADMIN_GROUPS)  # admin again
    assert accepted.status_code == 200
    assert _login_row(sso_only, "x").sso_refused_at is None
    again = x.post(f"{API}/api-tokens", json={"name": "HA", "scope": "full"})
    assert again.status_code == 201
    late = TestClient(sso_only.app, base_url="https://testserver")
    late.headers["Authorization"] = f"Bearer {secret}"
    assert late.get(f"{API}/me").status_code == 401  # made during the mark: stays dead


def test_a_working_refresh_does_not_end_the_mark_and_the_warning_stays(
    sso_only: TestClient, idp: FakeProvider
) -> None:
    """Fix13 review, M. X is dropped from the admin group, refused and kept; their older
    sign-in still refreshes (the groups aren't asked on a refresh). That must not clear the mark
    or they could make a token and sign out with it. Fails when a refresh clears the mark."""
    x = browser(sso_only)
    sign_in(x, idp, sub="x", extra=ADMIN_GROUPS)
    assert sso_only.delete(f"{API}/session").status_code == 204  # nobody else is signed in
    _unlink_first_admin(sso_only)  # nor linked: X is the only way in
    refused, _ = sign_in(browser(sso_only), idp, sub="x", extra={"groups": []})
    assert refused.status_code != 200
    assert _login_row(sso_only, "x").sso_refused_at is not None
    _due(sso_only, "x")
    assert check(sso_only) == 0  # the refresh token still works at the provider
    assert _login_row(sso_only, "x").sso_refused_at is not None
    assert x.post(f"{API}/api-tokens", json={"name": "HA", "scope": "full"}).status_code == 403


def test_signing_in_as_a_member_by_the_setup_does_not_end_the_mark(
    admin: TestClient, idp: FakeProvider
) -> None:
    """Fix13 review, L. The only admin (no password), refused and kept, sets "anyone else" to
    Member and signs in as a Member by the groups: the role isn't Admin, so the mark stays."""
    from test_sso_api import SETUP
    from test_sso_refused import _people

    wren = browser(admin)
    sign_in(wren, idp, sub="wren", extra=ADMIN_GROUPS)
    kid = _people(wren)["Tess"]
    assert wren.patch(f"{API}/people/{kid}", json={"role": "member"}).is_success
    sign_in(browser(admin), idp, sub="wren", extra={"groups": []})  # refused, kept: marked
    assert _login_row(admin, "wren").sso_refused_at is not None
    put = wren.put(
        f"{API}/sso/settings", json={**SETUP, "client_secret": "", "anyone_else": "member"}
    )
    assert put.is_success
    sign_in(browser(admin), idp, sub="wren", extra={"groups": []})  # now a Member by the setup
    assert _login_row(admin, "wren").sso_refused_at is not None  # still the kept admin: marked
    assert wren.post(f"{API}/api-tokens", json={"name": "HA", "scope": "full"}).status_code == 403


def test_the_warning_is_left_only_once_the_job_has_saved(
    sso_only: TestClient, idp: FakeProvider, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Fails when the warning goes into memory before the job's save: if Delete everything
    removes the household while the sign-in server is being asked, the save fails, and the
    old admin's name stayed in memory under a household number the next setup reuses
    (v0.9.0 release security pass, L2)."""
    phone = browser(sso_only)
    sign_in(phone, idp, sub="k", extra=ADMIN_GROUPS)
    idp.refresh_tokens.clear()  # the sign-in server no longer accepts it
    _due(sso_only, "k")
    real = sso_accounts._hourly_keeps

    def keeps_then_save_fails(db: Any, *args: Any, **kwargs: Any) -> Any:
        def gone() -> None:
            raise RuntimeError("the household was deleted meanwhile")

        monkeypatch.setattr(db, "commit", gone)
        return real(db, *args, **kwargs)

    monkeypatch.setattr(sso_accounts, "_hourly_keeps", keeps_then_save_fails)
    with pytest.raises(RuntimeError):
        check(sso_only)
    assert sso_accounts._kept == {}


def _mark(client: TestClient, username: str) -> None:
    with cast(Any, client.app).state.sessionmaker() as db:
        login = db.scalars(select(Login).where(Login.username == username)).one()
        login.sso_refused_at = now()
        db.commit()


def _marked(client: TestClient, username: str) -> bool:
    with cast(Any, client.app).state.sessionmaker() as db:
        return (
            db.scalars(select(Login).where(Login.username == username)).one().sso_refused_at
            is not None
        )


def test_the_refused_mark_ends_when_the_person_is_unlinked(
    admin: TestClient, idp: FakeProvider
) -> None:
    """B7 low (and #255 review L3)."""
    from test_sso_unlink import _lorna_signed_in, _member_id, _unlink

    _lorna_signed_in(admin, idp)
    _mark(admin, "lorna")
    assert _unlink(admin, _member_id(admin, "Lorna")).status_code == 200
    assert not _marked(admin, "lorna")


def test_the_refused_mark_ends_when_the_sign_in_server_changes(admin: TestClient) -> None:
    _mark(admin, "tess")
    same = admin.put(f"{API}/sso/settings", json={**SETUP, "button_name": "Other"})
    assert same.status_code == 200, same.text
    assert _marked(admin, "tess")  # the same server and client: the mark stays
    moved = admin.put(f"{API}/sso/settings", json={**SETUP, "client_id": "new-client"})
    assert moved.status_code == 200, moved.text
    assert not _marked(admin, "tess")


def test_the_refused_mark_ends_with_reset_admin(admin: TestClient) -> None:
    from mealwright.reset_admin import reset_admin

    _mark(admin, "tess")
    assert reset_admin(cast(Any, admin.app).state.settings, "tess", out=io.StringIO()) == 0
    assert not _marked(admin, "tess")
