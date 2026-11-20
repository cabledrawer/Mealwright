"""Settings › About: how old this version is, and (admins) Check now (spec section 7, "Updates").

`GET /updates` makes no connection: it says which version is running, the day it was released
and where new versions are listed, so About can say how old it is (level 1, for everyone). For
an admin it adds whether the daily check is on and the last answer (levels 2 and 3).

`POST /updates/check` is Check now (admins only): one request to the public release list
through the outbound gate as a person's press (`pressed=True`), whatever the Privacy switch
says: the switch controls only the daily check (see mealwright.updates; cabledrawer 12 Nov). The
version number for Diun and Renovate stays at `GET /version`, unchanged.
"""

from datetime import date, datetime
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel

from mealwright import __version__
from mealwright.api.v1.context import Here
from mealwright.auth import SameOrigin
from mealwright.outbound import Connection
from mealwright.outbound import switches as stored_switches
from mealwright.roles import Action, allowed
from mealwright.updates import RELEASED, RELEASES_PAGE, CheckResult, UpdateChecks

router = APIRouter(tags=["about"], dependencies=[SameOrigin])


class LastCheckOut(BaseModel):
    # up_to_date: nothing newer; newer: `latest` is out; failed: the list couldn't be had or
    # read.
    outcome: Literal["up_to_date", "newer", "failed"]
    latest: str | None
    checked_at: datetime


class UpdatesOut(BaseModel):
    version: str
    released_on: date
    releases_page: str
    # An admin: sees the two below. can_check: may use Check now (an API token never may).
    can_check: bool
    daily: bool | None
    last: LastCheckOut | None


def _checks(request: Request) -> UpdateChecks:
    checks: UpdateChecks = request.app.state.updates
    return checks


def _out(kitchen: Here, checks: UpdateChecks) -> UpdatesOut:
    admin = kitchen.login.role == "admin"
    last: CheckResult | None = checks.last(kitchen.household_id) if admin else None
    daily = stored_switches(kitchen.db, kitchen.household_id)[Connection.UPDATE_CHECK]
    return UpdatesOut(
        version=__version__,
        released_on=RELEASED,
        releases_page=RELEASES_PAGE,
        can_check=allowed(kitchen.login.role, Action.PRIVACY, kitchen.by_token),
        daily=daily if admin else None,
        last=(
            LastCheckOut(outcome=last.outcome, latest=last.latest, checked_at=last.checked_at)
            if last is not None
            else None
        ),
    )


@router.get("/updates")
def get_updates(kitchen: Here, request: Request) -> UpdatesOut:
    """The running version, the day it was released and where new versions are listed. For an
    admin, also whether the daily check is on and its last answer. Never connects anywhere."""
    return _out(kitchen, _checks(request))


@router.post("/updates/check")
def check_now(kitchen: Here, request: Request) -> UpdatesOut:
    """Admins only. Ask the public release list once, now, and answer with what it said. With
    the Privacy switch off or on: the switch controls only the daily check."""
    # cabledrawer 12 Nov: the switch controls only the daily check.
    kitchen.admin_only(Action.PRIVACY)  # it connects out, as the Privacy switches do
    checks = _checks(request)
    # Read the household before ending the read: after the rollback, `kitchen.household_id`
    # would load it again and keep a database connection through the whole wait (up to 20 s),
    # so a few slow checks could use up the connections everyone else needs.
    household_id = kitchen.household_id
    kitchen.db.rollback()
    checks.check_now(household_id)
    return _out(kitchen, checks)
