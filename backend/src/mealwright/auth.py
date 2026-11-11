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

from mealwright.config import Settings
from mealwright.errors import Problem
from mealwright.models import Login, Session, utcnow

log = logging.getLogger(__name__)

COOKIE = "mealwright_session"
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


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def check_password(login: Login | None, password: str) -> bool:
    """True if the password is right. Upgrades the stored hash if Argon2's settings
    have changed since it was made. Always does one full hash check."""
    stored = login.password_hash if login is not None else None
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
        COOKIE,
        token,
        max_age=int(REMEMBER_FOR.total_seconds()) if remember else None,
        httponly=True,
        secure=not settings.allow_plain_http,
        samesite="lax",
        path="/",
    )


def end_session(db: DbSession, request: Request, response: Response, settings: Settings) -> None:
    token = request.cookies.get(COOKIE)
    if token:
        db.execute(delete(Session).where(Session.token_hash == _token_hash(token)))
    response.delete_cookie(
        COOKIE, httponly=True, secure=not settings.allow_plain_http, samesite="lax", path="/"
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
    found = find_session(db, request.cookies.get(COOKIE))
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
