"""First-run setup, signing in and out, and the signed-in person's own details."""

import logging
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from mealwright import setup_code
from mealwright.auth import (
    MAX_PASSWORD,
    CurrentLogin,
    Db,
    NewPassword,
    SameOrigin,
    SlowDown,
    Tries,
    address_key,
    check_password,
    client_address,
    counted_check,
    end_session,
    hash_password,
    known_device,
    needs_https,
    new_password,
    peek_session,
    remember_device,
    session_token,
    start_session,
)
from mealwright.devices import device_label
from mealwright.errors import Problem
from mealwright.household import add_default_places, add_default_slots
from mealwright.models import Household, Login
from mealwright.names import one_line
from mealwright.people import removed
from mealwright.shopping import ensure_main_list

# Every line here names an account or an address, so it goes to Mealwright's own 14-day
# log file only, never to the container output (mealwright.logs, cabledrawer 17 Oct).
log = logging.getLogger("mealwright.sign_in")

router = APIRouter(tags=["account"], dependencies=[SameOrigin])

USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,49}$")
WRONG = "That username and password don’t match."
Theme = Literal["auto", "light", "dark"]


class Me(BaseModel):
    id: int
    name: str
    username: str
    role: Literal["admin", "member"]
    theme: Theme
    # This login's own person (0.9 A1): who it is in who's eating, whose tub and Recent changes.
    member_id: int | None = None
    # Used by several people ("Kitchen tablet"): it may ask "Who's this?".
    shared: bool = False


def _me(login: Login) -> Me:
    return Me(
        id=login.id,
        name=login.name,
        username=login.username,
        role="admin" if login.role == "admin" else "member",
        theme=login.theme if login.theme in ("auto", "light", "dark") else "auto",  # type: ignore[arg-type]
        member_id=login.member_id,
        shared=login.shared,
    )


def _device(request: Request) -> str | None:
    """ "iPhone · Safari": only this short name is kept, never the whole User-Agent."""
    return device_label(request.headers.get("user-agent"))


def _normalise_username(value: str) -> str:
    return value.strip().lower()


# --- First run -----------------------------------------------------------------------------


class SetupState(BaseModel):
    needs_setup: bool
    # True when the admin allowed sign-in over plain http:// for testing; the web app
    # then shows a warning on plain http:// addresses.
    plain_http_allowed: bool


class SetupIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    username: str
    password: NewPassword
    # Printed in the log at start-up (PR A2): only someone who can read the server's log can
    # create the admin account. Typed in any case, with or without the dashes.
    setup_code: str = Field(max_length=64)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = one_line(value).strip()
        if not value:
            raise ValueError("Enter your name.")
        return value

    @field_validator("username")
    @classmethod
    def _username(cls, value: str) -> str:
        value = _normalise_username(value)
        if not USERNAME.match(value):
            raise ValueError(
                "Use up to 50 lowercase letters, numbers, dots, dashes or underscores."
            )
        return value


@router.get("/setup")
def setup_state(request: Request, db: Db) -> SetupState:
    """Whether Mealwright still needs its first (admin) account."""
    return SetupState(
        needs_setup=db.scalar(select(func.count()).select_from(Login)) == 0,
        plain_http_allowed=request.app.state.settings.allow_plain_http,
    )


@router.post("/setup", status_code=status.HTTP_201_CREATED)
def setup(body: SetupIn, request: Request, response: Response, db: Db) -> Me:
    """Create the household and its admin, then sign in. Works only once: there is no
    default admin, so the first person to set up becomes the admin (spec section 7)."""
    needs_https(request, request.app.state.settings)
    if db.scalar(select(func.count()).select_from(Login)):
        raise HTTPException(status.HTTP_409_CONFLICT, "Mealwright is already set up.")
    # Wrong setup codes are slowed down like wrong passwords, per address (PR A2).
    slow: SlowDown = request.app.state.slow_down
    address = client_address(request)
    tries = Tries(address=address_key(address))
    expected = request.app.state.setup_code
    if not counted_check(slow, tries, lambda: setup_code.matches(expected, body.setup_code)):
        log.warning("Set up refused: wrong setup code from %s", address)  # never the code
        raise Problem(
            status.HTTP_403_FORBIDDEN,
            "wrong_setup_code",
            "That isn’t the setup code. Mealwright prints it in its log each time it starts.",
        )
    household = Household(id=1, name="Home")  # one household per install (spec section 3)
    login = Login(
        household_id=1,
        username=body.username,
        name=body.name,
        password_hash=hash_password(body.password),
        role="admin",
    )
    try:
        db.add(household)
        db.flush()
        add_default_places(db, household.id)
        add_default_slots(db, household.id)
        ensure_main_list(db, household.id, body.name)
        db.add(login)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Mealwright is already set up.") from None
    settings = request.app.state.settings
    start_session(db, response, settings, login, remember=False, device=_device(request))
    db.commit()
    remember_device(request, response, settings, login)
    request.app.state.setup_code = None  # used up
    log.info("Set up: admin account %s created", login.username)
    # Setup signs the admin in, so it gets its own "Signed in" line like every sign-in.
    log.info("Signed in: %s from %s", login.username, client_address(request))
    return _me(login)


# --- Signing in and out ----------------------------------------------------------------------


class SignIn(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=MAX_PASSWORD)
    remember: bool = False


@router.post("/session")
def sign_in(body: SignIn, request: Request, response: Response, db: Db) -> Me:
    needs_https(request, request.app.state.settings)
    slow: SlowDown = request.app.state.slow_down
    username = _normalise_username(body.username)
    address = client_address(request)
    login = db.scalar(select(Login).where(Login.username == username))
    user_key = f"user:{username}"
    device = None
    if login is not None:
        # A device that has signed in as this login before skips the username's pause and
        # has its own instead (PR A2).
        device = known_device(request, login)
    tries = Tries(
        name=username,
        personal=device or user_key,
        address=address_key(address),
        # Just after a new password (Settings, or reset-admin) the username's pause doesn't
        # stop a try (security review r2).
        new_password=login is not None and device is None and new_password(login),
    )
    # Only a real account's name is logged: a password typed into the username box
    # must never end up in the log. Refused tries (429) aren't logged: they cost nothing,
    # so logging each one would let anyone fill the disk. The slow-down is logged once,
    # when it starts or doubles (below).
    who = login.username if login else "unknown user"

    def failed() -> None:
        log.warning("Sign-in failed for %s from %s", who, address)
        if wait := slow.wait_seconds(tries.keys):
            log.warning("Sign-in slowed down for %s from %s (wait %d s)", who, address, wait)

    # A removed person's login can't sign in (0.9 A1): it's told only what anyone is, and the
    # try is counted like a wrong password.
    def password_right() -> bool:
        return check_password(login, body.password) and login is not None and not removed(db, login)

    right = counted_check(slow, tries, password_right, failed)
    if not right or not login:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, WRONG)
    slow.succeeded(user_key)
    if device:
        slow.succeeded(device)
    remember_device(request, response, request.app.state.settings, login)
    start_session(
        db,
        response,
        request.app.state.settings,
        login,
        remember=body.remember,
        device=_device(request),
    )
    db.commit()
    log.info("Signed in: %s from %s", login.username, address)
    return _me(login)


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def sign_out(request: Request, response: Response, db: Db) -> None:
    signed_in = peek_session(db, session_token(request))
    end_session(db, request, response, request.app.state.settings)
    db.commit()
    if signed_in is not None:  # its open live-update streams end now
        request.app.state.events.end_session(signed_in.session.id)


# --- The signed-in person ------------------------------------------------------------------------


@router.get("/me")
def me(signed_in: CurrentLogin) -> Me:
    return _me(signed_in.login)


class Preferences(BaseModel):
    theme: Theme


@router.put("/me/preferences")
def set_preferences(body: Preferences, signed_in: CurrentLogin, db: Db) -> Me:
    """Personal settings that follow you between devices. Theme: Auto · Light · Dark."""
    login = signed_in.login
    login.theme = body.theme
    db.commit()
    return _me(login)
