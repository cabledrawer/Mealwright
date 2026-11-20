"""Settings › About › Report a problem (spec section 7, "Bug reports", cabledrawer 17 Oct).

`GET /problem-report` builds the report on the server, with personal details already removed
(see mealwright.problem_report), and hands it to the web app. It makes no connection: the
person reads it, changes or removes any line and sends it themselves.

Everyone signed in may make a report. The recent errors come from the server's log, which
holds every household's errors, so only an admin's report includes them (proposed, for
cabledrawer); a member's has the version and the browser.
"""

from datetime import timedelta

from fastapi import APIRouter, Request
from pydantic import BaseModel

from mealwright import backups
from mealwright.api.v1.context import Here
from mealwright.auth import SameOrigin
from mealwright.config import Settings
from mealwright.models import as_utc
from mealwright.problem_report import (
    NEW_ISSUE_PAGE,
    browser_words,
    error_line,
    recent_errors,
    scrubber_for,
    server_address,
    version_line,
)

router = APIRouter(tags=["about"], dependencies=[SameOrigin])


class ProblemReportOut(BaseModel):
    # "Mealwright 0.9.0".
    version: str
    # "Safari 18 · iPhone": the browser's name and major version and the kind of device.
    browser: str
    # The recent errors from the log, oldest first, with personal details removed. Empty for a
    # member (see `errors_included`).
    errors: list[str]
    # False for a member: the log holds every household's errors, so only admins get them.
    errors_included: bool
    # The project's new-issue page. The web app adds the title and text; the person opens it.
    new_issue_page: str


@router.get("/problem-report")
def problem_report(kitchen: Here, request: Request) -> ProblemReportOut:
    """The report for "Report a problem", with personal details removed. Never connects
    anywhere and never sends anything."""
    settings: Settings = request.app.state.settings
    admin = kitchen.login.role == "admin"
    errors: list[str] = []
    if admin:
        # Nothing from before this household's set-up, nor from before the latest Delete
        # everything of any household: the log holds every household's lines, and a deleted
        # household's names are no longer there to be removed (cabledrawer 12 Nov). The safety
        # backup is stamped just before the delete, so a second is added.
        installed = kitchen.household.created_at
        deleted = backups.last_delete_everything(settings.data_dir / backups.FOLDER)
        if deleted is not None:
            deleted += timedelta(seconds=1)
            installed = max(as_utc(installed), deleted)
        found = recent_errors(settings.data_dir / "logs", installed=installed)
        if found:
            server = server_address(request.url.hostname, request.url.port, settings.port)
            scrub = scrubber_for(kitchen.db, server, settings.data_dir)
            errors = [error_line(error, scrub) for error in found]
    return ProblemReportOut(
        version=version_line(),
        browser=browser_words(request.headers.get("user-agent")),
        errors=errors,
        errors_included=admin,
        new_issue_page=NEW_ISSUE_PAGE,
    )
