"""Settings → About: how old this version is, and (admins) Check now (spec section 7, "Updates").

`GET /updates` makes no connection: it says which version is running, the day it was released
and where new versions are listed, so About can say how old it is (level 1, for everyone). For
an admin it adds whether the daily check is on and the last answer (levels 2 and 3).

`POST /updates/check` is Check now (admins only): one request to the public release list
through the outbound gate, only if the Privacy switch is on (see mealwright.updates). The
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
from mealwright.roles import Action
from mealwright.updates import RELEASED, RELEASES_PAGE, CheckResult, UpdateChecks

router = APIRouter(tags=["about"], dependencies=[SameOrigin])


class LastCheckOut(BaseModel):
    # up_to_date: nothing newer; newer: `latest` is out; failed: the list couldn't be had or
    # read; off: the Privacy switch is off, so nothing was asked.
    outcome: Literal["up_to_date", "newer", "failed", "off"]
    latest: str | None
    checked_at: datetime


class UpdatesOut(BaseModel):
    version: str
    released: date
    releases_page: str
    # An admin: may use Check now, and sees the two below. A member sees neither.
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
        released=RELEASED,
        releases_page=RELEASES_PAGE,
        can_check=admin,
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
    the Privacy switch off nothing is asked, and `last.outcome` is "off"."""
    kitchen.admin_only(Action.PRIVACY)  # it connects out, as the Privacy switches do
    checks = _checks(request)
    kitchen.db.rollback()  # end the read before waiting on the network (up to 20 s)
    checks.check_now(kitchen.household_id)
    return _out(kitchen, checks)
