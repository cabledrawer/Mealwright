"""Your own sign-in: change your password, see where you're signed in, sign out a device or
everywhere else (Settings › Your sign-in; PR A2).

Every answer is about the signed-in login only: nobody sees or ends anyone else's sessions here.
"""

import logging
from datetime import datetime

from fastapi import APIRouter, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from mealwright import api_tokens, people
from mealwright.auth import (
    MAX_PASSWORD,
    CurrentSession,
    Db,
    NewPassword,
    SameOrigin,
    SignedIn,
    SlowDown,
    Tries,
    _as_utc,
    check_password,
    client_address,
    counted_check,
    hash_password,
    now,
    remember_device,
)
from mealwright.errors import Problem, StoredInt, not_found, wrong_password
from mealwright.models import JoinLink, Session

# These lines name an account or an address: Mealwright's own log file only (mealwright.logs).
log = logging.getLogger("mealwright.sign_in")

router = APIRouter(tags=["account"], dependencies=[SameOrigin])

NOTHING_TO_CHANGE = "This login has no password to change: it signs in with single sign-on."
THIS_ONE = "That’s this device. Use Sign out at the bottom of Settings."


class SignInPlace(BaseModel):
    """One device where you're signed in."""

    id: int
    device: str | None = Field(description='"iPhone · Safari"; empty if not recognised.')
    last_used_at: datetime
    remember: bool = Field(description="Remembered for 30 days (else signed out after 12 h idle).")
    this_device: bool = Field(description="The device this request came from.")


class MySignIn(BaseModel):
    has_password: bool
    password_changed_at: datetime | None
    sessions: list[SignInPlace] = Field(description="This device first, then most recently used.")


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=MAX_PASSWORD)
    new_password: NewPassword
    sign_out_others: bool = True


def _my_sign_in(db: DbSession, signed_in: SignedIn) -> MySignIn:
    login = signed_in.login
    at = now()
    found = db.scalars(select(Session).where(Session.login_id == login.id)).all()
    places = [
        SignInPlace(
            id=s.id,
            device=s.device,
            last_used_at=_as_utc(s.last_seen_at),
            remember=s.remember,
            this_device=s.id == signed_in.session.id,
        )
        for s in found
        if _as_utc(s.expires_at) > at
    ]
    places.sort(key=lambda p: (not p.this_device, -p.last_used_at.timestamp()))
    changed = login.password_changed_at
    return MySignIn(
        has_password=login.password_hash is not None,
        password_changed_at=_as_utc(changed) if changed else None,
        sessions=places,
    )


def _end_others(request: Request, db: DbSession, signed_in: SignedIn) -> list[int]:
    """End every other session of this login, and the API tokens it made; their live-update
    streams end at once."""
    ended = list(
        db.scalars(
            select(Session.id).where(
                Session.login_id == signed_in.login.id, Session.id != signed_in.session.id
            )
        )
    )
    if ended:
        db.execute(delete(Session).where(Session.id.in_(ended)))
    # A token is a sign-in too: signing everything else out stops the tokens this login made
    # (O2 review r1, finding 5; proposed, for cabledrawer).
    api_tokens.stop_for(db, signed_in.login.id)
    # And no unused link of this login is left (16b security pass S-M1; proposed, for cabledrawer).
    people.drop_links(db, signed_in.login)
    return ended


def _tell_streams(request: Request, ended: list[int]) -> None:
    for session_id in ended:
        request.app.state.events.end_session(session_id)


@router.get("/me/sign-in")
def my_sign_in(signed_in: CurrentSession, db: Db) -> MySignIn:
    """Your password's date and every device where you're signed in."""
    return _my_sign_in(db, signed_in)


@router.put("/me/password")
def change_password(
    body: PasswordChange, request: Request, response: Response, signed_in: CurrentSession, db: Db
) -> MySignIn:
    """Change your password. Needs the current one; wrong ones have their own pause for this
    login, apart from signing in, so guessing at the username can't stop you changing it.
    Signs out your other devices unless `sign_out_others` is false. Every known device is
    forgotten (the new password makes their cookies useless) except this one, which is
    remembered again under the new password."""
    login = signed_in.login
    if login.password_hash is None:
        raise Problem(status.HTTP_409_CONFLICT, "no_password", NOTHING_TO_CHANGE)
    slow: SlowDown = request.app.state.slow_down
    address = client_address(request)
    tries = Tries(name=login.username, personal=f"change:{login.id}")
    if not counted_check(slow, tries, lambda: check_password(login, body.current_password)):
        log.warning(
            "Password change refused for %s from %s (wrong password)", login.username, address
        )
        raise wrong_password()
    login.password_hash = hash_password(body.new_password)
    login.password_changed_at = now()
    people.drop_links(db, login)  # no link made before outlives the change (S-M1)
    ended = _end_others(request, db, signed_in) if body.sign_out_others else []
    db.commit()
    remember_device(request, response, request.app.state.settings, login)
    _tell_streams(request, ended)
    log.info(
        "Password changed: %s from %s (%d other device(s) signed out)",
        login.username,
        address,
        len(ended),
    )
    return _my_sign_in(db, signed_in)


@router.delete("/me/sessions/others")
def sign_out_everywhere_else(request: Request, signed_in: CurrentSession, db: Db) -> MySignIn:
    """Sign out every device but this one."""
    ended = _end_others(request, db, signed_in)
    db.commit()
    _tell_streams(request, ended)
    log.info("Signed out everywhere else: %s (%d device(s))", signed_in.login.username, len(ended))
    return _my_sign_in(db, signed_in)


@router.delete("/me/reset-link", status_code=status.HTTP_204_NO_CONTENT)
def cancel_my_reset_link(signed_in: CurrentSession, db: Db) -> None:
    """Cancel a Reset password link an admin made for you: it stops working, and your
    password stays as it is. Only your own login's; nothing to cancel is fine too. Admin or
    not. Needs a sign-in, not an API token."""
    # 16b security pass S-M1 e; proposed (the docstring above is in the OpenAPI document).
    db.execute(
        delete(JoinLink).where(
            JoinLink.login_id == signed_in.login.id, JoinLink.kind == people.RESET
        )
    )
    db.commit()
    log.info("Reset link cancelled by %s", signed_in.login.username)


@router.delete("/me/sessions/{session_id}")
def sign_out_one(
    session_id: StoredInt, request: Request, signed_in: CurrentSession, db: Db
) -> MySignIn:
    """Sign out one of your other devices. Someone else's session is "not found"."""
    found = db.get(Session, session_id)
    if found is None or found.login_id != signed_in.login.id:
        raise not_found("That sign-in")
    if found.id == signed_in.session.id:
        raise Problem(status.HTTP_409_CONFLICT, "this_device", THIS_ONE)
    db.delete(found)
    db.commit()
    _tell_streams(request, [session_id])
    log.info("Signed out one device: %s", signed_in.login.username)
    return _my_sign_in(db, signed_in)
