"""Settings → Your data (0.9, D1; spec section 7): backups, export, delete everything.

Everyone in the household can look; only an admin changes anything (cabledrawer's rule for
household settings). Nothing here makes a network connection.

Backups copy the whole database, so they belong to the install, not to one household: the
scheduled job follows the first household's choice (an install has one household; the second
one exists only in tests). cabledrawer 12 Nov.
"""

import logging
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Request, Response, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy import Engine, delete, func, select

from mealwright import backups, export, setup_code, sso_accounts
from mealwright.api.v1.context import Here
from mealwright.api_tokens import not_for_tokens
from mealwright.auth import (
    SameOrigin,
    SlowDown,
    Tries,
    check_password,
    cookie_name,
    counted_check,
)
from mealwright.errors import Problem
from mealwright.household import today
from mealwright.models import Household, Login, Session, utcnow
from mealwright.photos import household_folder, store_of
from mealwright.roles import Action

router = APIRouter(tags=["your data"], dependencies=[SameOrigin])

# Sign-ins and "Delete everything" go to the log file only (mealwright.logs).
sign_in_log = logging.getLogger("mealwright.sign_in")
log = logging.getLogger(__name__)


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
    """How often Mealwright backs up, how many it keeps, and how the last backup went. Not for
    API tokens: it also names the server's backups folder, which the screen doesn't show."""
    if kitchen.by_token:
        raise not_for_tokens()  # O2 review r1, finding 1 (proposed, for cabledrawer)
    return _out(kitchen, _folder(request))


class BackupsChange(BaseModel):
    """Only what is sent changes. Admins only."""

    every: Literal["daily", "twice-daily", "weekly"] | None = None
    keep: int | None = Field(default=None, ge=1, le=backups.KEEP_MOST)


@router.patch("/backups")
def change_backups(body: BackupsChange, kitchen: Here, request: Request) -> BackupsOut:
    """Change how often and how many. Keeping fewer removes the oldest backups now."""
    kitchen.admin_only(Action.YOUR_DATA)
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
    kitchen.admin_only(Action.YOUR_DATA)
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


@router.get(
    "/export",
    response_class=StreamingResponse,
    responses={200: {"content": {"application/zip": {}}, "description": "The export file."}},
)
def export_everything(kitchen: Here) -> StreamingResponse:
    """Export everything (Admins only): one zip file with every recipe, plan, list, pantry
    item, person and setting of the household, and its photos (docs/dev/export-format.md,
    version 1). Sign-ins and passwords are left out. Written as it is sent."""
    kitchen.admin_only(Action.YOUR_DATA)
    household_id = kitchen.household_id
    # Everything is read now, in one snapshot, before the first byte is sent.
    doc = export.document(kitchen.db, household_id)
    kitchen.db.rollback()  # ends the read
    photos = export.photo_files(store_of(kitchen.db), household_id)
    name = export.file_name(today(kitchen.household))
    return StreamingResponse(
        export.zip_stream(doc, photos),
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="{name}"',
            "Cache-Control": "no-store",
        },
    )


# --- Delete everything (start again) --------------------------------------------------------------

WORDS = "delete everything"


class DeleteEverything(BaseModel):
    words: str = Field(max_length=100, description=f'Exactly "{WORDS}".')
    password: str = Field(max_length=1024, description="The admin's own password.")


_ONE_DELETE_AT_A_TIME = threading.Lock()


def _sign_out(request: Request, response: Response) -> None:
    settings = request.app.state.settings
    response.delete_cookie(
        cookie_name(settings),  # this mode's sign-in cookie (0.9 A2)
        httponly=True,
        secure=not settings.allow_plain_http,
        samesite="lax",
        path="/",
    )


def _remove_photos(folder: Path) -> None:
    """Delete the household's photo files. The next household gets the same number, so what
    can't be removed is moved out of `photos/` to `photos-left-over-<UTC time>` beside it,
    where it is never served or exported (review r1; the name is accepted (cabledrawer 12 Nov)). The
    log says how many files, never which."""
    shutil.rmtree(folder, ignore_errors=True)
    if not folder.exists():
        return
    try:
        left = sum(1 for path in folder.rglob("*") if not path.is_dir())
    except OSError:
        left = 0
    stamp = utcnow().strftime("%Y%m%d-%H%M%S")
    aside = folder.parent.parent / f"photos-left-over-{stamp}"
    number = 1
    while aside.exists():
        number += 1
        aside = folder.parent.parent / f"photos-left-over-{stamp}-{number}"
    try:
        folder.rename(aside)
    except OSError as error:
        log.error(
            "Delete everything: couldn't remove photo files (%d) or move them aside (%s). "
            "Remove the household's folder in data/photos by hand.",
            left,
            error.strerror or type(error).__name__,
        )
        return
    log.warning(
        "Delete everything: couldn't remove photo files (%d); moved them out of photos to %s. "
        "Delete that folder by hand.",
        left,
        aside.name,
    )


def _forget_in_memory(
    request: Request, household_id: int, people: list[tuple[int, str]]
) -> None:
    """Everything kept in memory about the deleted household goes too, so the next household
    (which may get the same number) never sees it (whole-0.9 S3, D1). Left alone on purpose:
    counts of wrong guesses by address, look-up and download counters (they only count what is
    running now), the address look-up cache and the built report scrubber (it rebuilds when
    a name table is written to)."""
    state = request.app.state
    state.sso_tests.pop(household_id, None)
    state.sso_links.pop(household_id, None)
    state.sso_proven.pop(household_id, None)
    sso_accounts.forget_kept(household_id)
    state.updates.forget(household_id)
    state.slow_down.forget_people([name for _, name in people], [n for n, _ in people])


@router.post("/delete-everything", status_code=status.HTTP_204_NO_CONTENT)
def delete_everything(
    body: DeleteEverything, kitchen: Here, request: Request, response: Response
) -> None:
    """Delete everything of the household: every recipe, plan, list, pantry item, person, login
    and setting, and its photos. Admins only, with the typed words and the admin's password.
    A safety backup is made first, and nothing is deleted if it can't
    be. The backups folder is kept. Everyone is signed out; Mealwright then starts again at
    first-run setup. There is no Undo."""
    kitchen.admin_only(Action.YOUR_DATA)
    if " ".join(body.words.split()).lower() != WORDS:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "words_wrong",
            f"Type “{WORDS}” to confirm.",
        )
    # The admin's own password, checked as Change password checks it (0.9 A2): through
    # counted_check, on this login's own count ("change:<id>", shared with Change password
    # and apart from sign-in's), so each try is counted before its hash, wrong ones pause
    # the same way, and guessing at the username at sign-in can't hold the admin up.
    slow: SlowDown = request.app.state.slow_down
    login = kitchen.login
    tries = Tries(name=login.username, personal=f"change:{login.id}")
    if not counted_check(slow, tries, lambda: check_password(login, body.password)):
        sign_in_log.warning("Delete everything: wrong password for %s", login.username)
        raise Problem(status.HTTP_403_FORBIDDEN, "password_wrong", "That password isn’t right.")

    engine: Engine = request.app.state.engine
    db = kitchen.db
    household_id = kitchen.household_id
    username = login.username
    # One at a time, the safety backup and the delete together: a second request (a double
    # click, two tabs) waits, then finds nothing left to delete (review r1).
    with _ONE_DELETE_AT_A_TIME:
        db.rollback()  # see what the request before this one did
        if db.scalar(select(Household.id).where(Household.id == household_id)) is None:
            _sign_out(request, response)
            return
        try:
            safety = backups.before_delete_everything(engine, _folder(request))
        except backups.BackupFailed as error:
            raise Problem(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "backup_failed",
                f"{error} Nothing was deleted.",
            ) from error

        sessions = list(db.scalars(select(Session.id).where(Session.household_id == household_id)))
        people = [
            (n, name)
            for n, name in db.execute(
                select(Login.id, Login.username).where(Login.household_id == household_id)
            )
        ]
        photos = household_folder(store_of(db), household_id)
        # Every table points at the household with ON DELETE CASCADE: one row takes all of it.
        db.execute(delete(Household).where(Household.id == household_id))
        db.commit()
        # First-run setup needs a setup code from the log (0.9 A2), and the one made at start-up
        # is long forgotten: make a new one now that nobody is left, and print it as start-up
        # does (joining D1 and A2; cabledrawer 12 Nov).
        if db.scalar(select(func.count()).select_from(Login)) == 0:
            request.app.state.setup_code = setup_code.new_code()
            setup_code.announce(request.app.state.setup_code)
        _remove_photos(photos)
        _forget_in_memory(request, household_id, people)
    for session_id in sessions:  # open live-update streams end now
        request.app.state.events.end_session(session_id)
    _sign_out(request, response)
    sign_in_log.warning(
        "Deleted everything (by %s); safety backup %s; everyone signed out",
        username,
        safety.name,
    )
