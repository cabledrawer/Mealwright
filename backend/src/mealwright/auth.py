"""Signing in: passwords, sessions and the slow-down after wrong guesses (spec section 7).

- Passwords are hashed with Argon2 (argon2-cffi's defaults, RFC 9106).
- A session is a random token in an HttpOnly cookie; only its SHA-256 is stored.
  "Remember this device" keeps it for 30 days; otherwise it ends after 12 hours
  without use, and the browser forgets it when closed. Either way a sign-in lasts at
  most 30 days in total (cabledrawer 19 Oct).
- Repeated wrong guesses for a username, or from one address, slow sign-in down.
- Requests that change something must come from Mealwright's own pages (Origin check);
  together with SameSite=Lax cookies this stops other sites acting as you.
"""

import hashlib
import logging
import math
import secrets
import threading
import time
from collections import defaultdict, deque
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated
from urllib.parse import urlsplit

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response, status
from pydantic import AfterValidator, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mealwright.config import Settings
from mealwright.errors import Problem
from mealwright.models import Login, Session, utcnow

log = logging.getLogger(__name__)

# The sign-in cookie's name (spec section 7, cabledrawer 19 Oct and 11 Nov). In https mode (the
# default) it carries the `__Host-` prefix: browsers then accept it only over https, from this
# exact host, with Path=/ and no Domain, so a site on another sub-domain can't set or replace
# it. That can't work over plain http://, so plain-http mode (MEALWRIGHT_ALLOW_PLAIN_HTTP)
# keeps the old name. In https mode the old name is ignored and cleared: everyone signs in
# again once.
COOKIE = "__Host-mealwright_session"
PLAIN_COOKIE = "mealwright_session"
REMEMBER_FOR = timedelta(days=30)
IDLE_TIMEOUT = timedelta(hours=12)
# The longest any sign-in lasts, however often it's used: the same as "Remember this
# device" (cabledrawer 19 Oct, security audit ASVS 3.3.2).
LONGEST_SIGN_IN = REMEMBER_FOR
SEEN_EVERY = timedelta(minutes=1)  # don't write last_seen_at on every request

# New passwords (setup, change, reset) need at least 12 characters; passwords people already
# have keep working, however short (spec section 7, cabledrawer 19 Oct). Counted in characters
# as Python counts them (code points), as the web app does.
MIN_PASSWORD = 12
MAX_PASSWORD = 1024
TOO_SHORT = f"Use at least {MIN_PASSWORD} characters."

_hasher = PasswordHasher()
# Checked when the username doesn't exist, so a wrong username takes as long as a
# wrong password and doesn't reveal which usernames exist.
_DUMMY_HASH = _hasher.hash(secrets.token_urlsafe(16))


def now() -> datetime:
    return utcnow()


def _as_utc(moment: datetime) -> datetime:
    # SQLite gives back naive datetimes; everything we store is UTC.
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


# --- Passwords -------------------------------------------------------------------------


# Argon2 takes 64 MiB and a noticeable moment for each hash, so only a few run at a time
# (review of v0.6.0). Requests beyond that wait a little for a turn, then get a plain "busy"
# answer instead of piling up memory until the server falls over.
HASHES_AT_ONCE = 2
WAIT_FOR_A_TURN = 5.0  # seconds
BUSY = "Mealwright is busy. Try again in a few seconds."
_hash_turns = threading.BoundedSemaphore(HASHES_AT_ONCE)


@contextmanager
def _hash_turn() -> Iterator[None]:
    turns = _hash_turns  # read once: the tests swap it
    if not turns.acquire(timeout=WAIT_FOR_A_TURN):
        log.warning("Sign-in busy: too many passwords being checked at once")
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, BUSY, headers={"Retry-After": "5"})
    try:
        yield
    finally:
        turns.release()


def hash_password(password: str) -> str:
    with _hash_turn():
        return _hasher.hash(password)


def check_password(login: Login | None, password: str) -> bool:
    """True if the password is right. Upgrades the stored hash if Argon2's settings
    have changed since it was made. Always does one full hash check."""
    stored = login.password_hash if login is not None else None
    with _hash_turn():
        try:
            _hasher.verify(stored or _DUMMY_HASH, password)
        except VerificationError, InvalidHashError:
            return False
        if login is None or stored is None:
            return False
        if _hasher.check_needs_rehash(stored):
            login.password_hash = _hasher.hash(password)
    return True


def _long_enough(value: str) -> str:
    # Raised as a Problem so the answer is one plain sentence, not pydantic's list.
    if len(value) < MIN_PASSWORD:
        raise Problem(status.HTTP_422_UNPROCESSABLE_CONTENT, "password_too_short", TOO_SHORT)
    return value


# Any password someone chooses from now on. Only for new passwords: signing in with one
# never checks the length.
NewPassword = Annotated[str, Field(max_length=MAX_PASSWORD), AfterValidator(_long_enough)]


# --- Slow-down after wrong guesses -------------------------------------------------------


class SlowDown:
    """Counts wrong guesses per username and per address over the last 15 minutes.

    The first FREE wrong guesses cost nothing. After that, each further guess has to
    wait 30 seconds, doubling each time, up to 15 minutes. A right password clears the
    username's count. Kept in memory: a restart clears it, which is fine for one
    process on a home server.
    """

    WINDOW = 15 * 60.0
    FREE = 5
    FIRST_WAIT = 30.0
    MAX_WAIT = 15 * 60.0

    def __init__(self) -> None:
        self._failures: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def _recent(self, key: str, at: float) -> deque[float]:
        # Looking up a key never stores it, and keys with no recent guesses are dropped,
        # so made-up usernames and addresses can't fill the memory.
        times = self._failures.get(key)
        if times is None:
            return deque()
        while times and at - times[0] > self.WINDOW:
            times.popleft()
        if not times:
            del self._failures[key]
        return times

    def wait_seconds(self, keys: list[str], at: float | None = None) -> int:
        """How long until another guess is allowed (0 = now)."""
        at = time.monotonic() if at is None else at
        longest = 0.0
        with self._lock:
            for key in keys:
                times = self._recent(key, at)
                extra = len(times) - self.FREE
                if extra >= 0:
                    wait = min(self.FIRST_WAIT * 2**extra, self.MAX_WAIT)
                    longest = max(longest, times[-1] + wait - at)
        return max(0, math.ceil(longest))

    def failed(self, keys: list[str], at: float | None = None) -> None:
        at = time.monotonic() if at is None else at
        with self._lock:
            # Forget keys whose newest guess is old, so a name typed once (perhaps a
            # password in the wrong box) isn't kept in memory past the window.
            for stale in [k for k, t in self._failures.items() if at - t[-1] > self.WINDOW]:
                del self._failures[stale]
            for key in keys:
                self._recent(key, at)
                self._failures[key].append(at)

    def succeeded(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


# --- Sessions ------------------------------------------------------------------------------


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def cookie_name(settings: Settings) -> str:
    return PLAIN_COOKIE if settings.allow_plain_http else COOKIE


def session_token(request: Request) -> str | None:
    """The sign-in token this request carries, under this mode's cookie name only."""
    return request.cookies.get(cookie_name(request.app.state.settings))


def start_session(
    db: DbSession, response: Response, settings: Settings, login: Login, remember: bool
) -> None:
    token = secrets.token_urlsafe(32)
    started = now()
    expires = started + (REMEMBER_FOR if remember else IDLE_TIMEOUT)
    db.execute(delete(Session).where(Session.expires_at < started))  # tidy up
    db.add(
        Session(
            household_id=login.household_id,
            login_id=login.id,
            token_hash=_token_hash(token),
            remember=remember,
            created_at=started,
            last_seen_at=started,
            expires_at=expires,
        )
    )
    login.last_sign_in_at = started
    response.set_cookie(
        cookie_name(settings),
        token,
        max_age=int(REMEMBER_FOR.total_seconds()) if remember else None,
        httponly=True,
        secure=not settings.allow_plain_http,
        samesite="lax",
        path="/",
    )


def end_session(db: DbSession, request: Request, response: Response, settings: Settings) -> None:
    token = session_token(request)
    if token:
        db.execute(delete(Session).where(Session.token_hash == _token_hash(token)))
    response.delete_cookie(
        cookie_name(settings),
        httponly=True,
        secure=not settings.allow_plain_http,
        samesite="lax",
        path="/",
    )


@dataclass
class SignedIn:
    login: Login
    session: Session


def find_session(db: DbSession, token: str | None) -> SignedIn | None:
    if not token:
        return None
    session = db.scalar(select(Session).where(Session.token_hash == _token_hash(token)))
    if session is None:
        return None
    at = now()
    if _as_utc(session.expires_at) <= at:
        db.delete(session)
        db.commit()
        return None
    if at - _as_utc(session.last_seen_at) >= SEEN_EVERY:
        session.last_seen_at = at
        if not session.remember:
            ends_by = _as_utc(session.created_at) + LONGEST_SIGN_IN
            session.expires_at = min(at + IDLE_TIMEOUT, ends_by)
        db.commit()
    login = db.get(Login, session.login_id)
    if login is None:
        return None
    return SignedIn(login=login, session=session)


def peek_session(db: DbSession, token: str | None) -> SignedIn | None:
    """Like `find_session`, but changes nothing: no `last_seen_at`, no new `expires_at`,
    nothing deleted. The live-updates stream uses it, so an open screen never counts as
    activity and the 12-hour idle sign-out still happens (cabledrawer 18 Oct)."""
    if not token:
        return None
    session = db.scalar(select(Session).where(Session.token_hash == _token_hash(token)))
    if session is None or _as_utc(session.expires_at) <= now():
        return None
    login = db.get(Login, session.login_id)
    return None if login is None else SignedIn(login=login, session=session)


# --- Request helpers (FastAPI dependencies) -------------------------------------------------


def get_db(request: Request) -> Iterator[DbSession]:
    with request.app.state.sessionmaker() as db:
        yield db


Db = Annotated[DbSession, Depends(get_db)]


def same_origin(request: Request) -> None:
    """Refuse requests that change something if a browser says they came from another
    site. Non-browser clients (no Origin header) are let through; they still need a
    session or, later, an API token."""
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    origin = request.headers.get("origin")
    if origin is None:
        return
    if origin == "null" or urlsplit(origin).netloc != request.headers.get("host"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This request came from another site.")


def current(request: Request, db: Db) -> SignedIn:
    found = find_session(db, session_token(request))
    if found is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in.")
    return found


CurrentLogin = Annotated[SignedIn, Depends(current)]
SameOrigin = Depends(same_origin)


HTTPS_NEEDED = (
    "Signing in needs a secure connection. Open Mealwright at its https:// address, "
    "through your reverse proxy. To try it on plain http:// on a network you trust, "
    "the admin can set MEALWRIGHT_ALLOW_PLAIN_HTTP=true."
)
_LOOPBACK = {"localhost", "127.0.0.1", "::1"}


def needs_https(request: Request, settings: Settings) -> None:
    """Refuse to sign in when the browser is on a plain http:// address.

    The session cookie is HTTPS-only, so the browser would quietly drop it and the
    person would seem to sign in and then be signed straight out. The browser's own
    Origin header says which address it's on, whatever proxy sits in between.
    Browsers treat localhost as secure, so it's allowed there.
    """
    if settings.allow_plain_http:
        return
    origin = urlsplit(request.headers.get("origin", ""))
    if origin.scheme == "http" and origin.hostname not in _LOOPBACK:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, HTTPS_NEEDED)


def client_address(request: Request) -> str:
    # ProxyHeadersMiddleware has already applied X-Forwarded-For, from trusted proxies only.
    return request.client.host if request.client else "unknown"


class OldCookieMiddleware:
    """In https mode, clear a sign-in cookie still under the old name (`mealwright_session`).

    It's ignored everywhere (only `__Host-mealwright_session` signs in), so this only tidies the
    browser. Added only in https mode: in plain-http mode the old name is the cookie in use.
    """

    _OLD = PLAIN_COOKIE.encode()
    # The same attributes it was set with, so the browser matches and drops it.
    _CLEAR = f"{PLAIN_COOKIE}=; Max-Age=0; Path=/; Secure; HttpOnly; SameSite=lax".encode()

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._has_old(scope):
            await self.app(scope, receive, send)
            return

        async def send_clearing(message: Message) -> None:
            if message["type"] == "http.response.start":
                message["headers"] = [*message.get("headers", []), (b"set-cookie", self._CLEAR)]
            await send(message)

        await self.app(scope, receive, send_clearing)

    def _has_old(self, scope: Scope) -> bool:
        for name, value in scope.get("headers", []):
            if name == b"cookie":
                for part in value.split(b";"):
                    if part.strip().split(b"=", 1)[0] == self._OLD:
                        return True
        return False
