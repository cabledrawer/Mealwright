"""Settings → Your data (0.9, D1; spec section 7): backups, export, delete everything.

Everyone in the household can look; only an admin changes anything (cabledrawer's rule for
household settings). Nothing here makes a network connection.

Backups copy the whole database, so they belong to the install, not to one household: the
scheduled job follows the first household's choice (an install has one household; the second
one exists only in tests). Proposed, for cabledrawer.
"""

from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field
from sqlalchemy import Engine

from mealwright import backups
from mealwright.api.v1.context import Here
from mealwright.auth import SameOrigin
from mealwright.models import utcnow

router = APIRouter(tags=["your data"], dependencies=[SameOrigin])


def _folder(request: Request) -> Path:
    return Path(request.app.state.settings.data_dir) / backups.FOLDER


class BackupOut(BaseModel):
    at: datetime
    size: int = Field(description="In bytes.")


class BackupsOut(BaseModel):
    """How Mealwright backs itself up, and how the last backup went."""

    every: Literal["daily", "twice-daily", "weekly"] = Field(
        description="How often: daily at 03:00, twice a day (03:00 and 15:00), or weekly "
        "(Mondays 03:00), in the household's time."
    )
    keep: int = Field(description="How many of its own backups are kept, 1 to 30.")
    last: BackupOut | None = Field(description="The newest backup, or null when there's none.")
    problem: str | None = Field(
        description="Why the last try failed, in plain words, or null when backups work."
    )
    problem_at: datetime | None
    count: int = Field(description="How many of its own backups are in the folder.")
    folder: str = Field(description="Where the backups are, on the server.")


def _out(kitchen: Here, folder: Path) -> BackupsOut:
    household = kitchen.household
    found = backups.backups(folder)
    every = household.backup_every if household.backup_every in backups.EVERY else "daily"
    return BackupsOut(
        every=every,  # type: ignore[arg-type]
        keep=household.backup_keep,
        last=BackupOut(at=found[0].made_at, size=found[0].size) if found else None,
        problem=household.backup_problem,
        problem_at=household.backup_problem_at,
        count=len(found),
        folder=str(folder),
    )


@router.get("/backups")
def get_backups(kitchen: Here, request: Request) -> BackupsOut:
    """How often Mealwright backs up, how many it keeps, and how the last backup went."""
    return _out(kitchen, _folder(request))


class BackupsChange(BaseModel):
    """Only what is sent changes. Admins only."""

    every: Literal["daily", "twice-daily", "weekly"] | None = None
    keep: int | None = Field(default=None, ge=1, le=backups.KEEP_MOST)


@router.patch("/backups")
def change_backups(body: BackupsChange, kitchen: Here, request: Request) -> BackupsOut:
    """Change how often and how many. Keeping fewer removes the oldest backups now."""
    kitchen.admin_only()
    household = kitchen.household
    folder = _folder(request)
    if body.every is not None:
        household.backup_every = body.every
    if body.keep is not None:
        household.backup_keep = body.keep
    kitchen.db.commit()
    if body.keep is not None:
        backups.trim(folder, body.keep)
    return _out(kitchen, folder)


@router.post("/backups")
def back_up_now(kitchen: Here, request: Request) -> BackupsOut:
    """Back up now ("Back up now"). Admins only. A failure is answered as the settings with
    `problem` set, as the screen shows it, not as an error."""
    kitchen.admin_only()
    engine: Engine = request.app.state.engine
    folder = _folder(request)
    now = utcnow()
    try:
        backups.back_up(engine, folder, kitchen.household.backup_keep, now)
    except backups.BackupFailed as error:
        backups.note_problem(kitchen.db, kitchen.household, str(error), now)
    else:
        backups.note_problem(kitchen.db, kitchen.household, None, now)
    return _out(kitchen, folder)

