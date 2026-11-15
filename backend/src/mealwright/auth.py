"""Signing in: passwords, sessions and the slow-down after wrong guesses (spec section 7).

- Passwords are hashed with Argon2 (argon2-cffi's defaults, RFC 9106).
- A session is a random token in an HttpOnly cookie; only its SHA-256 is stored.
  "Remember this device" keeps it for 30 days; otherwise it ends after 12 hours
  without use, and the browser forgets it when closed. Either way a sign-in lasts at
  most 30 days in total (cabledrawer 19 Oct).
- Repeated wrong guesses for a username, or from one address, slow sign-in down. Each try
  is counted before its password is checked. A device that has signed in as someone before
  (the "known device" cookie) skips that username's pause, so guessing at a username can't
  keep its owner out (PR A2). For ten minutes after a password is set, the username's pause
  doesn't stop its owner's right password either (`NEW_PASSWORD_WINDOW`).
- Requests that change something must come from Mealwright's own pages (Origin check);
  together with SameSite=Lax cookies this stops other sites acting as you.
"""

import asyncio
import base64
import contextlib
import hashlib
import hmac
import ipaddress
import logging
import math
import re
import secrets
import threading
import time
from collections import defaultdict, deque
from collections.abc import AsyncIterator, Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any
from urllib.parse import urlsplit

import anyio
import anyio.from_thread
import anyio.to_thread
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from fastapi import Depends, HTTPException, Request, Response, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import AfterValidator, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from mealwright import api_tokens
from mealwright import db as database
from mealwright.config import Settings
from mealwright.errors import Problem
from mealwright.models import ApiToken, Login, Member, Session, utcnow

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
# A single sign-on sign-in with no refresh token can't be checked with the sign-in server, so it
# lasts at most a day, then goes back through the sign-in server (S8, cabledrawer 13 Nov).
SSO_UNCHECKED_FOR = timedelta(days=1)
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
# (review of v0.6.0). A few more requests may wait a little for a turn (the waiting room);
# anyone beyond that, or who waits too long, gets a plain "busy" answer at once, instead of
# piling up memory or holding every worker thread while a flood of sign-ins queues (PR A2).
HASHES_AT_ONCE = 2
WAITING_ROOM = 4
WAIT_FOR_A_TURN = 5.0  # seconds
BUSY = "Mealwright is busy. Try again in a few seconds."
_hash_turns = threading.BoundedSemaphore(HASHES_AT_ONCE)
_waiting = 0
_waiting_lock = threading.Lock()


def _busy() -> HTTPException:
    log.warning("Sign-in busy: too many passwords being checked at once")
    return HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, BUSY, headers={"Retry-After": "5"})


@contextmanager
def _hash_turn() -> Iterator[None]:
    global _waiting
    turns = _hash_turns  # read once: the tests swap it
    if not turns.acquire(blocking=False):
        with _waiting_lock:
            if _waiting >= WAITING_ROOM:
                raise _busy()
            _waiting += 1
        try:
            got_one = turns.acquire(timeout=WAIT_FOR_A_TURN)
        finally:
            with _waiting_lock:
                _waiting -= 1
        if not got_one:
            raise _busy()
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
    """Counts wrong guesses per key over the last 15 minutes: per username (`user:`), per
    address (`addr:`), per known device (`dev:`) and per login changing its password
    (`change:`).

    The first FREE wrong guesses cost nothing. After that, each further guess has to
    wait 30 seconds, doubling each time: up to 15 minutes for an address, but never more
    than a minute for a username, a known device or a password change (PR A2), so guesses
    from many addresses can't lock someone out of their own account. A right password
    clears the username's count.

    A try is counted when it starts (`begin`), under the lock, before its password is
    checked, so a burst of tries at once can't all slip in before the first is counted; a
    right password, or a busy answer, takes it back (`take_back`).

    Kept in memory, not in the database: a restart clears it, which is fine for one
    process on a home server, and nothing about wrong guesses is ever written to disk
    beyond the sign-in log.
    """

    WINDOW = 15 * 60.0
    FREE = 5
    FIRST_WAIT = 30.0
    MAX_WAIT = 15 * 60.0
    MAX_USERNAME_WAIT = 60.0
    # Each key keeps only its newest guesses: the wait needs no more than the count up to its
    # cap and the newest time, and a flood of guesses can't grow the memory (A2 review r3).
    KEEP = FREE + 64
    # Past this many doubles every wait is at its cap anyway; a bigger power would overflow.
    MAX_DOUBLINGS = 30

    def _longest(self, key: str) -> float:
        personal = key.startswith(("user:", "dev:", "change:"))
        return self.MAX_USERNAME_WAIT if personal else self.MAX_WAIT

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

    def _wait(self, key: str, at: float) -> int:
        times = self._recent(key, at)
        extra = len(times) - self.FREE
        if extra < 0:
            return 0
        doublings = min(extra, self.MAX_DOUBLINGS)
        wait: float = min(self.FIRST_WAIT * 2**doublings, self._longest(key))
        return max(0, math.ceil(times[-1] + wait - at))

    def wait_seconds(self, keys: list[str], at: float | None = None) -> int:
        """How long until another guess is allowed (0 = now)."""
        at = time.monotonic() if at is None else at
        with self._lock:
            return max((self._wait(key, at) for key in keys), default=0)

    def _count(self, keys: list[str], at: float) -> None:
        # Forget keys whose newest guess is old, so a name typed once (perhaps a
        # password in the wrong box) isn't kept in memory past the window.
        for stale in [k for k, t in self._failures.items() if at - t[-1] > self.WINDOW]:
            del self._failures[stale]
        for key in keys:
            self._recent(key, at)
            times = self._failures[key]
            times.append(at)
            while len(times) > self.KEEP:
                times.popleft()

    def forget_people(self, usernames: Iterable[str], login_ids: Iterable[int]) -> None:
        """Drop the counts kept for these people: a username, a device of a login or a password
        change by it (Delete everything: they belong to the people who are gone, and only
        theirs; another household's stay). Counts by address stay: they say who is guessing,
        not who lived here."""
        users = {f"user:{name}" for name in usernames}
        changes = {f"change:{n}" for n in login_ids}
        devices = tuple(f"dev:{n}:" for n in login_ids)
        with self._lock:
            for key in [
                k
                for k in self._failures
                if k in users or k in changes or (devices and k.startswith(devices))
            ]:
                del self._failures[key]

    def failed(self, keys: list[str], at: float | None = None) -> None:
        at = time.monotonic() if at is None else at
        with self._lock:
            self._count(keys, at)

    def begin(
        self, keys: list[str], at: float | None = None, unstopped: frozenset[str] = frozenset()
    ) -> tuple[float | None, dict[str, int]]:
        """Start a try: if none of the keys is paused, count it now as a wrong guess and give
        back its moment (for `take_back`); otherwise count nothing and give back each key's
        wait. Both in one step under the lock.

        A key in `unstopped` doesn't stop the try while paused: the try is counted all the
        same, and its wait comes back with the moment (`counted_check` tells a wrong guess
        it's paused)."""
        at = time.monotonic() if at is None else at
        with self._lock:
            waits = {key: self._wait(key, at) for key in keys}
            if any(wait for key, wait in waits.items() if key not in unstopped):
                return None, waits
            self._count(keys, at)
            return at, {key: waits[key] for key in keys if key in unstopped and waits[key]}

    def take_back(self, keys: list[str], at: float) -> None:
        """Un-count a try `begin` counted: the password was right, or it was never checked."""
        with self._lock:
            for key in keys:
                times = self._failures.get(key)
                if times is not None and at in times:
                    times.remove(at)
                    if not times:
                        del self._failures[key]

    def succeeded(self, key: str) -> None:
        with self._lock:
            self._failures.pop(key, None)


# For this long after a login's password is set (Settings, or reset-admin), the username's pause
# doesn't stop a try for that login: a guesser polling the username can't keep its owner out of
# the new password. Each try is still counted and still meets the address limit and the hash
# turns; a wrong one is told the username is paused, as before (PR A2, security review r2;
# cabledrawer 12 Nov).
NEW_PASSWORD_WINDOW = timedelta(minutes=10)


def new_password(login: Login) -> bool:
    """True if `login`'s password was set less than NEW_PASSWORD_WINDOW ago."""
    changed = login.password_changed_at
    return changed is not None and now() - _as_utc(changed) < NEW_PASSWORD_WINDOW


# --- Counting a password check ------------------------------------------------------------


def address_key(address: str) -> str:
    """The address as the slow-down counts it: an IPv6 address by its /64, the block one home
    or phone usually gets, so stepping through it doesn't give a guesser new free guesses."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return f"addr:{address}"
    if isinstance(ip, ipaddress.IPv6Address):
        if ip.ipv4_mapped is not None:
            return f"addr:{ip.ipv4_mapped}"
        return f"addr:{ipaddress.ip_network(f'{ip}/64', strict=False)}"
    return f"addr:{ip}"


def how_long(seconds: int) -> str:
    """The wait in plain words, never shorter than the real one.

    Under a minute it's shown in seconds; from a minute on, in whole minutes, rounded up.
    """
    if seconds < 60:
        return f"{seconds} second{'s' if seconds != 1 else ''}"
    minutes = -(-seconds // 60)
    return f"{minutes} minute{'s' if minutes != 1 else ''}"


@dataclass(frozen=True)
class Tries:
    """What a password check's wrong guesses count towards.

    `personal` is the login's own count (`user:<name>`, `dev:<…>` or `change:<id>`, never
    paused for more than a minute); its pause is told as "Too many wrong passwords for
    <name>" and reads the same for a made-up username as for a real one. `address` is the
    address's count (`address_key`), told as "Too many tries".
    """

    name: str = ""
    personal: str | None = None
    address: str | None = None
    # The login's password was set in the last NEW_PASSWORD_WINDOW: `personal`'s pause doesn't
    # stop the try (a wrong one is still told it's paused).
    new_password: bool = False

    @property
    def keys(self) -> list[str]:
        return [key for key in (self.personal, self.address) if key]


def _paused(tries: Tries, waits: dict[str, int]) -> Problem:
    for_personal = waits.get(tries.personal, 0) if tries.personal else 0
    for_address = waits.get(tries.address, 0) if tries.address else 0
    wait = max(for_personal, for_address)
    if tries.personal and for_personal >= for_address:
        problem = Problem(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "username_paused",
            f"Too many wrong passwords for {tries.name}. Try again in {how_long(wait)}.",
        )
    else:
        problem = Problem(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "too_many_tries",
            f"Too many tries. Wait {how_long(wait)}.",
        )
    problem.headers = {"Retry-After": str(wait)}
    return problem


def counted_check(
    slow: SlowDown,
    tries: Tries,
    check: Callable[[], bool],
    on_wrong: Callable[[], None] | None = None,
) -> bool:
    """Run one password (or setup code) check under the slow-down; every such check goes
    through here.

    Refused at once (429) while any of the keys is paused. Otherwise the try is counted
    first, then `check` runs (Argon2 checks take a hash turn, with its waiting room); a right
    answer, or a busy one (503), takes the try back. Gives back whether it was right; a wrong
    one stays counted (and `on_wrong` runs). Refused tries aren't logged: they cost nothing,
    and a line each would let anyone fill the disk.

    Just after a password change (`tries.new_password`) the personal pause doesn't refuse the
    try, so a guesser can't keep the owner out of their new password; a wrong one is then
    told it's paused (429), in the same words as a refused try.
    """
    keys = tries.keys
    unstopped = frozenset([tries.personal] if tries.new_password and tries.personal else [])
    at, waits = slow.begin(keys, unstopped=unstopped)
    if at is None:
        raise _paused(tries, waits)
    try:
        right = check()
    except BaseException:
        slow.take_back(keys, at)
        raise
    if right:
        slow.take_back(keys, at)
        return True
    if on_wrong is not None:
        on_wrong()
    if waits:
        raise _paused(tries, {key: slow.wait_seconds([key]) for key in keys})
    return False


# --- Sessions ------------------------------------------------------------------------------


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def cookie_name(settings: Settings) -> str:
    return PLAIN_COOKIE if settings.allow_plain_http else COOKIE


# Signed out here on purpose (S7, cabledrawer 13 Nov): the next "Sign in with …" in this browser
# asks
# the sign-in server to ask for the login again (`prompt=login`), so whoever uses the device next
# isn't let in as the person who just signed out. Holds nothing but "1"; gone once someone signs
# in with single sign-on here.
SIGNED_OUT_COOKIE = "__Host-mealwright_signed_out"
PLAIN_SIGNED_OUT_COOKIE = "mealwright_signed_out"


def _signed_out_name(settings: Settings) -> str:
    return PLAIN_SIGNED_OUT_COOKIE if settings.allow_plain_http else SIGNED_OUT_COOKIE


def mark_signed_out(response: Response, settings: Settings) -> None:
    response.set_cookie(
        _signed_out_name(settings),
        "1",
        max_age=int(REMEMBER_FOR.total_seconds()),
        httponly=True,
        secure=not settings.allow_plain_http,
        samesite="lax",
        path="/",
    )


def signed_out_here(request: Request) -> bool:
    return request.cookies.get(_signed_out_name(request.app.state.settings)) == "1"


def forget_signed_out(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        _signed_out_name(settings),
        httponly=True,
        secure=not settings.allow_plain_http,
        samesite="lax",
        path="/",
    )


def session_token(request: Request) -> str | None:
    """The sign-in token this request carries, under this mode's cookie name only."""
    return request.cookies.get(cookie_name(request.app.state.settings))


# --- Known devices (PR A2, security review r1) ---------------------------------------------------
#
# A device that has signed in as someone before gets a long-lived "known device" cookie, and
# skips that username's pause next time: guessing at a username from a few addresses then
# can't keep its owner out. Its own wrong guesses have their own small pause, and the address
# limit and the hash turns still apply.
#
# Nothing is stored for it. Each entry is "<login id>.<random>.<HMAC>", keyed by the login's
# own password hash, which only the server knows; so it can't be made up, and every known
# device is forgotten when the password changes (Settings, or reset-admin), except the one that
# changed it in Settings, which is remembered again. Sign out everywhere else doesn't forget
# them. Up to five logins per browser (a shared kitchen tablet). Same rules as the sign-in
# cookie: HttpOnly, SameSite, and Secure with the `__Host-` prefix in https mode.
DEVICE_COOKIE = "__Host-mealwright_device"
PLAIN_DEVICE_COOKIE = "mealwright_device"
KNOWN_FOR = timedelta(days=365)
KNOWN_LOGINS = 5
_LONGEST_DEVICE_COOKIE = 1000  # characters; five entries are about 330


def device_cookie_name(settings: Settings) -> str:
    return PLAIN_DEVICE_COOKIE if settings.allow_plain_http else DEVICE_COOKIE


def _device_mac(login: Login, nonce: str) -> str | None:
    if not login.password_hash:
        return None
    message = f"mealwright known device {login.id} {nonce}".encode()
    digest = hmac.new(login.password_hash.encode(), message, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


# Each part of an entry: what Mealwright writes (a login id, URL-safe base64 without padding).
_DEVICE_PART = re.compile(r"[A-Za-z0-9_-]{1,64}")


def _device_entries(request: Request) -> list[tuple[str, str, str]]:
    """The cookie's entries, read strictly: an entry with any part Mealwright wouldn't write
    (a control character, a space, too long…) is dropped without a word, so it is never
    checked, never sent back and never reaches a header or the log (security review r2)."""
    value = request.cookies.get(device_cookie_name(request.app.state.settings), "")
    if len(value) > _LONGEST_DEVICE_COOKIE:
        return []
    entries = []
    for entry in value.split("~"):
        parts = entry.split(".")
        if len(parts) == 3 and all(_DEVICE_PART.fullmatch(part) for part in parts):
            entries.append((parts[0], parts[1], parts[2]))
    return entries[:KNOWN_LOGINS]


def known_device(request: Request, login: Login) -> str | None:
    """This device's own slow-down key if it has signed in as `login` since the password was
    last set, else None."""
    for login_id, nonce, mac in _device_entries(request):
        if login_id != str(login.id):
            continue
        want = _device_mac(login, nonce)
        if want is not None and hmac.compare_digest(want.encode(), mac.encode()):
            return f"dev:{login.id}:{nonce}"
    return None


def remember_device(request: Request, response: Response, settings: Settings, login: Login) -> None:
    """After a right password: this device is known for `login` (a new entry each time)."""
    nonce = secrets.token_urlsafe(16)
    mac = _device_mac(login, nonce)
    if mac is None:
        return
    others = [e for e in _device_entries(request) if e[0] != str(login.id)]
    entries = [(str(login.id), nonce, mac), *others][:KNOWN_LOGINS]
    response.set_cookie(
        device_cookie_name(settings),
        "~".join(".".join(entry) for entry in entries),
        max_age=int(KNOWN_FOR.total_seconds()),
        httponly=True,
        secure=not settings.allow_plain_http,
        samesite="lax",
        path="/",
    )


def start_session(
    db: DbSession,
    response: Response,
    settings: Settings,
    login: Login,
    remember: bool,
    device: str | None = None,
) -> Session:
    token = secrets.token_urlsafe(32)
    started = now()
    expires = started + (REMEMBER_FOR if remember else IDLE_TIMEOUT)
    db.execute(delete(Session).where(Session.expires_at < started))  # tidy up
    session = Session(
        household_id=login.household_id,
        login_id=login.id,
        token_hash=_token_hash(token),
        remember=remember,
        created_at=started,
        last_seen_at=started,
        expires_at=expires,
        device=device,
    )
    db.add(session)
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
    return session


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


def _session_and_login(db: DbSession, token: str) -> tuple[Session, Login] | None:
    """The session with this token and its login, in one query, only while the login's person
    hasn't been removed: a session that outlived a removal (one added by a sign-in that raced
    it) is never used (0.9.0-alpha.1 security pass)."""
    found = db.execute(
        select(Session, Login)
        .join(Login, Login.id == Session.login_id)
        .outerjoin(Member, Member.id == Login.member_id)
        .where(Session.token_hash == _token_hash(token), Member.removed_at.is_(None))
    ).first()
    return None if found is None else (found[0], found[1])


def last_moment(session: Session) -> datetime:
    """When a sign-in ends however busy: LONGEST_SIGN_IN after it started; for a single sign-on
    one with no refresh token (S8) a day after it started, or, when a refresh token was dropped
    since (a saved sign-in server or client), a day after that (`sso_check_at` holds the moment
    it was dropped, which nothing else reads while there is no token)."""
    started = _as_utc(session.created_at)
    if session.sso and session.sso_refresh_sealed is None:
        if session.sso_check_at is not None:
            started = max(started, _as_utc(session.sso_check_at))
        return started + SSO_UNCHECKED_FOR
    return started + LONGEST_SIGN_IN


def _ended(session: Session, at: datetime) -> bool:
    """Run out: idle too long, or past its last moment (a refresh token dropped since it started
    starts the day from the drop, S8)."""
    return _as_utc(session.expires_at) <= at or last_moment(session) <= at


def find_session(db: DbSession, token: str | None) -> SignedIn | None:
    if not token:
        return None
    found = _session_and_login(db, token)
    if found is None:
        return None
    session, login = found
    at = now()
    if _ended(session, at):
        db.delete(session)
        db.commit()
        return None
    if at - _as_utc(session.last_seen_at) >= SEEN_EVERY:
        session.last_seen_at = at
        if not session.remember:
            ends_by = last_moment(session)
            session.expires_at = min(at + IDLE_TIMEOUT, ends_by)
        db.commit()
    return SignedIn(login=login, session=session)


def peek_session(db: DbSession, token: str | None) -> SignedIn | None:
    """Like `find_session`, but changes nothing: no `last_seen_at`, no new `expires_at`,
    nothing deleted. The live-updates stream uses it, so an open screen never counts as
    activity and the 12-hour idle sign-out still happens (cabledrawer 18 Oct)."""
    if not token:
        return None
    found = _session_and_login(db, token)
    if found is None or _ended(found[0], now()):
        return None
    return SignedIn(login=found[1], session=found[0])


# --- Request helpers (FastAPI dependencies) -------------------------------------------------


def _turns(app: Any) -> asyncio.Semaphore:
    """The app's `REQUESTS_AT_ONCE` places, made when first asked for. One set for each event
    loop: the server has one loop; the tests sometimes run two clients on one app."""
    loop = asyncio.get_running_loop()
    turns: asyncio.Semaphore | None = app.state.database_turns.get(loop)
    if turns is None:
        turns = app.state.database_turns[loop] = asyncio.Semaphore(database.REQUESTS_AT_ONCE)
    return turns


async def get_db(request: Request) -> AsyncIterator[DbSession]:
    """The request's database session.

    Only `REQUESTS_AT_ONCE` requests hold one at a time, and the pool has a connection for
    each of them, so a request that has its session never waits for a connection while it
    waits for a thread (see `mealwright.db.REQUESTS_AT_ONCE`). A request past the limit
    waits here, in the order it came, holding no thread and no connection.

    Asked for with `scope="function"` (in `Db`): the session is closed, and the place given
    up, as soon as the answer is built and before it is sent, so a slow reader or a photo
    being sent holds neither.
    """
    async with _turns(request.app):
        db: DbSession = request.app.state.sessionmaker()  # opens nothing yet
        try:
            yield db
        finally:
            # Closing gives the connection back. Even when the request is cancelled (the
            # shield), and before the place is given up, so no place is ever free while its
            # connection is still out. In a thread, since on Postgres closing talks to the
            # server, and one of its own, never one of the 40, which may all be busy.
            with anyio.CancelScope(shield=True):
                await anyio.to_thread.run_sync(db.close, limiter=anyio.CapacityLimiter(1))


@contextlib.contextmanager
def without_place(request: Request, db: DbSession) -> Iterator[None]:
    """For a handler that is about to wait a long time on someone else (the sign-in server): give
    the request's database connection and its place back, and take a place again after. So a
    flood of slow waits never holds the places everyone else needs (O2 release pass, M). Only
    for a handler that runs in a worker thread, and that reads what it needs first: after the
    rollback, what was loaded is read again from the database when next used."""
    db.rollback()  # the connection goes back to the pool
    turns = anyio.from_thread.run_sync(_turns, request.app)
    anyio.from_thread.run_sync(turns.release)
    try:
        yield
    finally:
        anyio.from_thread.run(turns.acquire)


Db = Annotated[DbSession, Depends(get_db, scope="function")]


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


@dataclass
class Caller:
    """Who a request to /api/v1 comes from: a signed-in device (`session`) or an API token
    (`token`, PR O2), never both."""

    login: Login
    session: Session | None = None
    token: ApiToken | None = None

    @property
    def by_token(self) -> bool:
        return self.token is not None


def _has_cookie(request: Request) -> bool:
    return bool(request.cookies.get(COOKIE) or request.cookies.get(PLAIN_COOKIE))


# Documents the token in OpenAPI (`ApiToken`); `current` reads the header itself.
_BEARER = HTTPBearer(
    auto_error=False,
    scheme_name="ApiToken",
    description="An API token from Settings, Sign-in, API tokens: `Authorization: Bearer mw_…`. "
    "Read-only tokens (`mw_ro_`) can only read. Without one, the sign-in cookie is used.",
)


def current(
    request: Request,
    db: Db,
    _documented: Annotated[HTTPAuthorizationCredentials | None, Security(_BEARER)] = None,
) -> Caller:
    """The signed-in device's login, or an API token's (`Authorization: Bearer mw_…`). A request
    carrying both is refused (proposed, for cabledrawer); a read-only token may only read."""
    token = api_tokens.bearer(request)
    if token is not None:
        if _has_cookie(request):
            raise Problem(status.HTTP_400_BAD_REQUEST, "token_and_cookie", api_tokens.BOTH)
        by_token = api_tokens.find(db, token)
        if by_token is None:
            raise api_tokens.doesnt_work()
        api_tokens.check_method(by_token.token, request.method)
        return Caller(login=by_token.login, token=by_token.token)
    found = find_session(db, session_token(request))
    if found is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in.")
    return Caller(login=found.login, session=found.session)


def current_session(signed_in: Annotated[Caller, Depends(current)]) -> SignedIn:
    """Only a signed-in device, never an API token: for what tokens never do (making or
    listing tokens, your password, where you're signed in, "Who's this?"; proposed, for
    cabledrawer)."""
    if signed_in.session is None:
        raise api_tokens.not_for_tokens()
    return SignedIn(login=signed_in.login, session=signed_in.session)


CurrentLogin = Annotated[Caller, Depends(current)]
CurrentSession = Annotated[SignedIn, Depends(current_session)]
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
