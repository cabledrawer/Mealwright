"""Settings → Sign-in → API tokens (0.9 O2): make, list and delete the household's tokens.

Admins only, and only from a signed-in device: a token can never make, list or delete tokens
(proposed, for cabledrawer). The token itself is in the answer to making it, once, and never again.
How a token signs a request in is in `mealwright.api_tokens`.
"""

import logging
from datetime import UTC, date, datetime, time, timedelta
from typing import Annotated, Literal

from fastapi import APIRouter, status
from pydantic import AfterValidator, BaseModel, Field
from sqlalchemy import func, select

from mealwright import api_tokens
from mealwright.api.v1.context import Here
from mealwright.auth import CurrentSession, SameOrigin
from mealwright.errors import Problem, StoredInt, not_found
from mealwright.history import as_utc
from mealwright.household import today, zone
from mealwright.models import ApiToken, utcnow
from mealwright.names import one_line
from mealwright.roles import Action
from mealwright.shopping import lock_db

# Mealwright's own log file only (mealwright.logs): these lines name an account.
log = logging.getLogger("mealwright.sign_in")

router = APIRouter(tags=["account"], dependencies=[SameOrigin])

# Proposed, for cabledrawer: a household has at most this many tokens, and one ends at most this
# far ahead.
MOST_TOKENS = 50
LONGEST = timedelta(days=5 * 366)


def _name(value: str) -> str:
    value = one_line(value).strip()
    if not value:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "name_needed", "Give the token a name."
        )
    if len(value) > api_tokens.LONGEST_NAME:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "name_too_long",
            f"Use at most {api_tokens.LONGEST_NAME} characters.",
        )
    return value


class TokenIn(BaseModel):
    name: Annotated[str, Field(max_length=500), AfterValidator(_name)]
    scope: Literal["read", "full"] = Field(
        description='"read": read only. "full": read and change.'
    )
    expires_on: date | None = Field(
        default=None,
        description="The last day it works, in the household's time zone. Empty: never ends.",
    )


class TokenOut(BaseModel):
    id: int
    name: str
    scope: Literal["read", "full"]
    created_at: datetime
    last_used_at: datetime | None = Field(description="To the minute. Empty: never used.")
    expires_on: date | None = Field(description="The last day it works. Empty: never ends.")


class TokensOut(BaseModel):
    tokens: list[TokenOut] = Field(description="Newest first.")
    today: date = Field(description="Today in the household's time zone, for the date chips.")


class MadeToken(BaseModel):
    token: str = Field(description="The token itself: shown this once, never again.")
    made: TokenOut


def _admin(kitchen: Here) -> None:
    kitchen.admin_only(Action.SIGN_IN)


def _last_day(kitchen: Here, row: ApiToken) -> date | None:
    if row.expires_at is None:
        return None
    # It stops at the start of the day after its last day.
    return (as_utc(row.expires_at).astimezone(zone(kitchen.household)) - timedelta(days=1)).date()


def _out(kitchen: Here, row: ApiToken) -> TokenOut:
    return TokenOut(
        id=row.id,
        name=row.name,
        scope="full" if row.scope == api_tokens.FULL else "read",
        created_at=as_utc(row.created_at),
        last_used_at=as_utc(row.last_used_at) if row.last_used_at else None,
        expires_on=_last_day(kitchen, row),
    )


def _live(kitchen: Here) -> list[ApiToken]:
    return list(
        kitchen.db.scalars(
            select(ApiToken)
            .where(ApiToken.household_id == kitchen.household_id, ApiToken.revoked_at.is_(None))
            .order_by(ApiToken.id.desc())
        )
    )


@router.get("/api-tokens")
def list_tokens(kitchen: Here, _signed_in: CurrentSession) -> TokensOut:
    """The household's tokens that haven't been deleted, ended ones too. Admins only."""
    _admin(kitchen)
    return TokensOut(
        tokens=[_out(kitchen, row) for row in _live(kitchen)], today=today(kitchen.household)
    )


@router.post("/api-tokens", status_code=status.HTTP_201_CREATED)
def make_token(body: TokenIn, kitchen: Here, signed_in: CurrentSession) -> MadeToken:
    """Make a token for a script or another app. The answer holds the token itself, this once
    only. It acts as you, and stops if you're removed or made a member. Admins only."""
    _admin(kitchen)
    lock_db(kitchen.db, kitchen.household)
    expires_at = None
    if body.expires_on is not None:
        if body.expires_on < today(kitchen.household):
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "date_passed",
                "That date has passed. Pick today or later.",
            )
        start = datetime.combine(
            body.expires_on + timedelta(days=1), time(), zone(kitchen.household)
        )
        expires_at = start.astimezone(UTC)
        if expires_at - utcnow() > LONGEST:
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "date_too_far",
                "That date is too far ahead. Pick one within 5 years.",
            )
    count = kitchen.db.scalar(
        select(func.count())
        .select_from(ApiToken)
        .where(ApiToken.household_id == kitchen.household_id, ApiToken.revoked_at.is_(None))
    )
    if (count or 0) >= MOST_TOKENS:
        raise Problem(
            status.HTTP_409_CONFLICT,
            "too_many_tokens",
            f"The household has {MOST_TOKENS} tokens. Delete one first.",
        )
    token = api_tokens.new_token(body.scope)
    row = ApiToken(
        household_id=kitchen.household_id,
        login_id=signed_in.login.id,
        name=body.name,
        token_hash=api_tokens.token_hash(token),
        scope=body.scope,
        created_at=utcnow(),
        expires_at=expires_at,
    )
    kitchen.db.add(row)
    kitchen.idempotency_key = None  # a retry makes a new token: the token is never stored
    kitchen.db.commit()
    log.info("API token made by %s", signed_in.login.username)
    return MadeToken(token=token, made=_out(kitchen, row))


@router.delete("/api-tokens/{token_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_token(token_id: StoredInt, kitchen: Here, signed_in: CurrentSession) -> None:
    """Delete a token: it stops working at once, for good. Any admin can delete any of the
    household's tokens. Admins only."""
    _admin(kitchen)
    row = kitchen.db.get(ApiToken, token_id)
    if row is None or row.household_id != kitchen.household_id or row.revoked_at is not None:
        raise not_found("That token")
    row.revoked_at = utcnow()
    kitchen.db.commit()
    log.info("API token deleted by %s", signed_in.login.username)
