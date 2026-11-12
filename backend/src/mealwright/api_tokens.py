"""API tokens for scripts and other apps (0.9 O2; spec section 7, cabledrawer 17 Oct: "each token is
read-only or full access, with an optional expiry date").

- A token is `mw_ro_…` (read only) or `mw_rw_…` (read and change) followed by 32 random bytes,
  so one pasted somewhere it shouldn't be is easy to spot. It's shown once, when it's made; only
  its SHA-256 is stored, like a session's, so a copy of the database can't be used.
- It's sent as `Authorization: Bearer mw_…`, to `/api/v1` only. It's looked up by its hash
  (the secret itself is never compared), and an unknown, deleted, ended or malformed token all
  get the same answer.
- It acts as the admin who made it, and only while they're still an admin of the household:
  removed or made a member, their tokens stop at once and for good (proposed, for cabledrawer).
- A read-only token can't change anything. No token can do what `SESSION_ONLY` lists, nor the
  admin actions in `roles.TOKENS_NEVER` (proposed, for cabledrawer).
- A request with both a token and a sign-in cookie is refused (proposed, for cabledrawer).
- The token is never logged, and using one writes nothing to the log: the spec's log keeps
  errors and sign-ins only (cabledrawer 17 Oct), and a token's use is neither.
"""

import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Request, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session as DbSession

from mealwright.errors import Problem
from mealwright.models import ApiToken, Login, Member, utcnow
from mealwright.roles import ADMIN

READ = "read"
FULL = "full"
_PREFIX = {READ: "mw_ro_", FULL: "mw_rw_"}
# What Mealwright writes: the prefix, then token_urlsafe(32), 43 characters.
_SHAPE = re.compile(r"mw_(ro|rw)_[A-Za-z0-9_-]{43}")
USED_EVERY = timedelta(minutes=1)  # last_used_at is written at most this often
LONGEST_NAME = 60

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})

# The answer for every token that doesn't work, whatever the reason (proposed, for cabledrawer).
DOESNT_WORK = "That API token doesn’t work. Make a new one in Settings, Sign-in."
READ_ONLY = "This API token can only read. Make one that can read and change."
NOT_FOR_TOKENS = "API tokens can’t do this. Sign in to Mealwright to do it."
BOTH = "Send an API token or a sign-in cookie, not both."


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def new_token(scope: str) -> str:
    return _PREFIX[scope] + secrets.token_urlsafe(32)


def doesnt_work() -> Problem:
    problem = Problem(status.HTTP_401_UNAUTHORIZED, "bad_token", DOESNT_WORK)
    problem.headers = {"WWW-Authenticate": 'Bearer realm="mealwright"'}
    return problem


def not_for_tokens() -> Problem:
    return Problem(status.HTTP_403_FORBIDDEN, "not_for_tokens", NOT_FOR_TOKENS)


def bearer(request: Request) -> str | None:
    """The Mealwright token in `Authorization: Bearer mw_…`, else None.

    Any other Authorization header (a reverse proxy's own Basic or Bearer sign-in, passed on)
    is left alone, so the sign-in cookie still works behind such a proxy. A `mw_` token that
    isn't the shape Mealwright makes gets the same 401 as one that doesn't work."""
    header = request.headers.get("authorization")
    if header is None:
        return None
    scheme, _, value = header.strip().partition(" ")
    value = value.strip()
    if scheme.lower() != "bearer" or not value.startswith("mw_"):
        return None
    if not _SHAPE.fullmatch(value):
        raise doesnt_work()
    return value


@dataclass
class TokenSignIn:
    login: Login
    token: ApiToken


def find(db: DbSession, token: str) -> TokenSignIn | None:
    """The working token with this text and its login, else None: not deleted, not ended, and
    its login still an admin of the token's household whose person hasn't been removed."""
    at = utcnow()
    found = db.execute(
        select(ApiToken, Login)
        .join(Login, Login.id == ApiToken.login_id)
        .outerjoin(Member, Member.id == Login.member_id)
        .where(
            ApiToken.token_hash == token_hash(token),
            ApiToken.revoked_at.is_(None),
            ApiToken.household_id == Login.household_id,
            Login.role == ADMIN,
            Member.removed_at.is_(None),
        )
    ).first()
    if found is None:
        return None
    row, login = found[0], found[1]
    if row.expires_at is not None and _as_utc(row.expires_at) <= at:
        return None
    if row.last_used_at is None or at - _as_utc(row.last_used_at) >= USED_EVERY:
        row.last_used_at = at
        db.commit()
    return TokenSignIn(login=login, token=row)


def check_method(row: ApiToken, method: str) -> None:
    """A read-only token may only read."""
    if row.scope != FULL and method.upper() not in SAFE_METHODS:
        raise Problem(status.HTTP_403_FORBIDDEN, "read_only_token", READ_ONLY)


def stop_for(db: DbSession, login_id: int) -> None:
    """Delete every token this login made, for good: they were removed, or aren't an admin
    any more."""
    db.execute(
        update(ApiToken)
        .where(ApiToken.login_id == login_id, ApiToken.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )


def _as_utc(moment: datetime) -> datetime:
    # SQLite gives back naive datetimes; everything stored is UTC.
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)
