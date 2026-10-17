"""First-run setup, signing in and out, and the signed-in person's own details."""

import logging
import re
from typing import Literal

from fastapi import APIRouter, HTTPException, Request, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError

from mealwright.auth import (
    MAX_PASSWORD,
    MIN_PASSWORD,
    CurrentLogin,
    Db,
    SameOrigin,
    SlowDown,
    check_password,
    client_address,
    end_session,
    hash_password,
    needs_https,
    start_session,
)
from mealwright.models import Household, Login

log = logging.getLogger(__name__)

router = APIRouter(tags=["account"], dependencies=[SameOrigin])

USERNAME = re.compile(r"^[a-z0-9][a-z0-9._-]{0,49}$")
WRONG = "That username and password don't match."
Theme = Literal["auto", "light", "dark"]


class Me(BaseModel):
    id: int
    name: str
    username: str
    role: Literal["admin", "member"]
    theme: Theme


def _me(login: Login) -> Me:
    return Me(
        id=login.id,
        name=login.name,
        username=login.username,
        role="admin" if login.role == "admin" else "member",
        theme=login.theme if login.theme in ("auto", "light", "dark") else "auto",  # type: ignore[arg-type]
    )


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
    password: str = Field(min_length=MIN_PASSWORD, max_length=MAX_PASSWORD)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Please enter your name.")
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
        db.add(login)
        db.flush()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status.HTTP_409_CONFLICT, "Mealwright is already set up.") from None
    start_session(db, response, request.app.state.settings, login, remember=False)
    db.commit()
    log.info("Set up: admin account %s created", login.username)
    # Setup signs the admin in, so it gets its own "Signed in" line like every sign-in.
    log.info("Signed in: %s from %s", login.username, client_address(request))
    return _me(login)


# --- Signing in and out ----------------------------------------------------------------------


class SignIn(BaseModel):
    username: str = Field(max_length=100)
    password: str = Field(max_length=MAX_PASSWORD)
    remember: bool = False


def how_long(seconds: int) -> str:
    """The wait in plain words, never shorter than the real one.

    Under a minute it's shown in seconds; from a minute on, in whole minutes, rounded up.
    """
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes = -(-seconds // 60)
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


@router.post("/session")
def sign_in(body: SignIn, request: Request, response: Response, db: Db) -> Me:
    needs_https(request, request.app.state.settings)
    slow: SlowDown = request.app.state.slow_down
    username = _normalise_username(body.username)
    address = client_address(request)
    keys = [f"user:{username}", f"addr:{address}"]
    wait = slow.wait_seconds(keys)
    login = db.scalar(select(Login).where(Login.username == username))
    # Only a real account's name is logged: a password typed into the username box
    # must never end up in the log.
    who = login.username if login else "unknown user"
    if wait:
        log.warning("Sign-in slowed down for %s from %s (wait %d s)", who, address, wait)
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            f"Too many tries. Please wait {how_long(wait)}.",
            headers={"Retry-After": str(wait)},
        )
    if not check_password(login, body.password) or login is None:
        slow.failed(keys)
        log.warning("Sign-in failed for %s from %s", who, address)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, WRONG)
    slow.succeeded(keys[0])
    start_session(db, response, request.app.state.settings, login, remember=body.remember)
    db.commit()
    log.info("Signed in: %s from %s", login.username, address)
    return _me(login)


@router.delete("/session", status_code=status.HTTP_204_NO_CONTENT)
def sign_out(request: Request, response: Response, db: Db) -> None:
    end_session(db, request, response, request.app.state.settings)
    db.commit()


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
