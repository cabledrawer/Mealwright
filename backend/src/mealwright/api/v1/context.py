"""What every kitchen endpoint needs: the database, who's signed in, their household, and
the client-made change ID for retries (docs/dev/api-0.2.md section 1.2)."""

import re
from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Header, Request, status
from sqlalchemy.orm import Session as DbSession

from mealwright.auth import CurrentLogin, Db
from mealwright.errors import Problem
from mealwright.models import Household, Login

_KEY = re.compile(r"^[A-Za-z0-9._:-]{1,64}$")


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

    @property
    def household_id(self) -> int:
        return self.household.id

    def admin_only(self) -> None:
        if self.login.role != "admin":
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
    return Kitchen(
        db=db,
        login=signed_in.login,
        household=household,
        idempotency_key=idempotency_key,
        request=f"{request.method} {request.url.path}",
    )


Here = Annotated[Kitchen, Depends(kitchen)]
