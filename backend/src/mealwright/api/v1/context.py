"""What every kitchen endpoint needs: the database, who's signed in, their household, and
the client-made change ID for retries (docs/dev/api-0.2.md section 1.2)."""

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Header, Request, status
from sqlalchemy.orm import Session as DbSession

from mealwright.api_tokens import not_for_tokens
from mealwright.auth import SEEN_EVERY, CurrentLogin, Db
from mealwright.errors import Problem
from mealwright.models import Household, Login, Member, Session, utcnow
from mealwright.roles import Action, allowed

_KEY = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")
# A "Who's this?" pick counts for 30 minutes after it was made or after the last change made as
# that person, like the browser's 30 minutes without use (cabledrawer 12 Nov). "Just looking"
# (an hour without asking) stays in the browser: it records nobody, so the server needn't know.
PICK_FOR = timedelta(minutes=30)
SAFE = {"GET", "HEAD", "OPTIONS"}


@dataclass
class Kitchen:
    db: DbSession
    login: Login
    household: Household
    idempotency_key: str | None
    request: str  # "POST /api/v1/foods/7/sizes", to spot a key reused for something else
    # Set while a shopping action is applied: only its first change carries the key (the
    # action ID), any further changes it makes carry none (sync protocol 4.4).
    key_once: bool = False
    # Who is doing it (0.9 A1): the login's own person, or on a shared login the one picked in
    # "Who's this?" (None: nobody picked). Recent changes names them.
    member_id: int | None = None
    # Through an API token, not a signed-in device (PR O2): `roles.TOKENS_NEVER` is refused.
    by_token: bool = False
    # Where the install's files are, for the one question that reads a sealed secret
    # ("do passwords count as off?", `sso_accounts.passwords_off`); None where unknown.
    data_dir: Path | None = None

    @property
    def household_id(self) -> int:
        return self.household.id

    def admin_only(self, action: Action) -> None:
        """Refuse (403) unless this login's role may do `action` (`mealwright.roles`)."""
        if not allowed(self.login.role, action, self.by_token):
            if self.by_token and allowed(self.login.role, action):
                raise not_for_tokens()
            raise Problem(
                status.HTTP_403_FORBIDDEN,
                "admins_only",
                "Only the household’s admin can change this.",
            )


def kitchen(
    request: Request,
    db: Db,
    signed_in: CurrentLogin,
    idempotency_key: Annotated[
        str | None,
        Header(
            description="A client-made ID (e.g. a UUID) for this change, so a retry "
            "isn’t applied twice."
        ),
    ] = None,
) -> Kitchen:
    if idempotency_key is not None and not _KEY.match(idempotency_key):
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "bad_key",
            "Idempotency-Key must be 1 to 64 letters, digits, dots, dashes, colons or underscores.",
        )
    household = db.get(Household, signed_in.login.household_id)
    if household is None:  # pragma: no cover (a login always has a household)
        raise Problem(status.HTTP_401_UNAUTHORIZED, "signed_out", "Please sign in.")
    member_id = acting_member(db, signed_in.login, household, signed_in.session)
    if signed_in.session is not None and signed_in.login.shared and member_id is not None:
        # Any request from the device keeps the pick going, as `last_seen_at` does for the
        # sign-in: reading a recipe or the plan for half an hour is still using the tablet
        # (whole-0.9 Pe5). A change made as the picked person saves it with the change; a
        # request that only looks writes it at most once a minute.
        picked_at = signed_in.session.picked_at
        if request.method not in SAFE:
            signed_in.session.picked_at = utcnow()
        elif (
            picked_at is None
            or utcnow() - (picked_at if picked_at.tzinfo else picked_at.replace(tzinfo=UTC))
            >= SEEN_EVERY
        ):
            signed_in.session.picked_at = utcnow()
            db.commit()
    return Kitchen(
        db=db,
        login=signed_in.login,
        household=household,
        idempotency_key=idempotency_key,
        request=f"{request.method} {request.url.path}",
        member_id=member_id,
        by_token=signed_in.by_token,
        data_dir=request.app.state.settings.data_dir,
    )


def acting_member(
    db: DbSession, login: Login, household: Household, session: Session | None
) -> int | None:
    """Who a change is recorded for: on a shared login, the person picked on this device (if
    the household still asks "Who's this?", the pick is under 30 minutes old and they're still
    in the household; an API token has no device, so nobody); otherwise the login's own
    person."""
    if not login.shared:
        wanted = login.member_id
    elif session is None or not household.ask_whos_this or not _fresh_pick(session):
        return None
    else:
        wanted = session.member_id
    if wanted is None:
        return None
    member = db.get(Member, wanted)
    if member is None or member.household_id != login.household_id:
        return None
    if login.shared and member.removed_at is not None:
        return None
    return member.id


def _utc(moment: datetime) -> datetime:
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _fresh_pick(session: Session) -> bool:
    picked_at = session.picked_at
    if session.member_id is None or picked_at is None:
        return False
    return utcnow() - _utc(picked_at) < PICK_FOR


Here = Annotated[Kitchen, Depends(kitchen)]
