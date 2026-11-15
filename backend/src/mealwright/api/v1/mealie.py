"""Import from Mealie (0.9.5): upload the backup file, look it over, bring it in, Undo, and Save
all as they are (`mealwright.mealie_import`; docs/dev/recipe-import.md, "Import from Mealie").

Who may (cabledrawer 14 Nov): the household's admin, like the other Your data
actions. Sending the file, Bring in, Cancel, Undo and Save all check the role (sending the file
before a byte of it is read), and refuse API tokens, as Your data does. Anyone in the household
may look (the import screen's state, Today's note, Drafts).
"""

import logging
import secrets
import threading
from collections.abc import AsyncIterator
from datetime import datetime, timedelta
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Query, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from starlette.requests import ClientDisconnect

from mealwright import mealie_import
from mealwright.api.v1.context import Here, Kitchen
from mealwright.api_tokens import not_for_tokens
from mealwright.auth import SameOrigin, current
from mealwright.errors import Problem, StoredInt
from mealwright.history import as_utc
from mealwright.limits import MAX_MEALIE_BYTES, MEALIE_TOO_BIG
from mealwright.mealie_file import MAX_RECIPES
from mealwright.models import Food, MealieImport, utcnow
from mealwright.roles import Action, allowed

router = APIRouter(tags=["recipes"], dependencies=[SameOrigin])

CHUNK = 1024 * 1024
# The words are proposed, for cabledrawer (words.md section 81).
UPLOAD_BUSY = "Another Mealie file is being sent. Try again in a moment."
log = logging.getLogger(__name__)

NO_FILE = "Choose the Mealie file (.zip)."
ADMINS_ONLY = "Only the household’s admin can change this."  # as Kitchen.admin_only says

# One upload at a time (cabledrawer 14 Nov) in this one server process: a 1 GB file is plenty to be
# writing.
# The households sending a file now: one file at a time for each household, so a slow or
# stalled upload holds up only its own household, never the others (round 1, review 12, S-L8).
_UPLOADING: set[int] = set()
_UPLOADING_LOCK = threading.Lock()


class PreviewRecipe(BaseModel):
    key: str  # Mealie's id for it (send it in `leave_out` to leave it out)
    name: str
    tags: list[str]  # its first few Mealie tags
    photo: bool
    already: bool  # the household has it already (same name and source): left out


class MealiePreview(BaseModel):
    new: int
    already: int
    with_photo: int  # new recipes with a photo
    photo_bytes: int  # those photos' size in the file
    foods_matching: int  # Mealie foods the recipes use that match an ingredient
    foods_new: int  # the ones that will be new ingredients, marked "from Mealie"
    # Of those, the ones past the most one import adds (5,000): not added, so the recipes
    # that use them wait in Drafts (0 in a preview read before round 1).
    foods_left_out: int = 0
    # Their names, A to Z, the first 200 (empty in a preview read before 0.9.5's "See").
    foods_new_names: list[str] = []
    # Never brought in: "meal_plans", "shopping_lists", "users", "cookbooks" → how many.
    left_out: dict[str, int]
    recipes: list[PreviewRecipe]  # every recipe in the file, in its order (not once started)


class MealieResult(BaseModel):
    key: str
    name: str
    # saved: in Recipes; draft: in Drafts, lines to check; saved_all: a draft saved by Save all;
    # already: the household had it by then (left out); skipped: couldn't be brought in.
    state: Literal["saved", "draft", "saved_all", "already", "skipped"]
    recipe_id: int | None = None
    draft_id: int | None = None
    unread: list[str] = Field(default_factory=list)  # the first lines it couldn't read
    unread_count: int = 0


class MealieCounts(BaseModel):
    saved: int  # ready to cook, in Recipes
    drafts: int  # with lines to check, in Drafts
    already: int  # left out: the household had them
    skipped: int
    new_foods: int  # new ingredients, marked "from Mealie"


class MealieImportOut(BaseModel):
    id: int
    state: Literal["ready", "running", "done", "failed", "undone"]
    file_name: str
    file_bytes: int | None  # the file's size while it's kept (until it ends)
    started_by: str
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    undo_until: datetime | None  # while Undo works (7 days after it finished)
    photos: bool  # "Bring in photos" (once started)
    leave_out: list[str]
    total: int  # recipes to bring in
    done: int
    counts: MealieCounts
    preview: MealiePreview
    recent: list[MealieResult]  # the last few brought in, newest last (the running screen)
    to_check: list[MealieResult]  # recipes waiting in Drafts (the first 50)


class MealieCurrent(BaseModel):
    """The import to show: the one running, or the newest one; null for none."""

    current: MealieImportOut | None


class MealieStart(BaseModel):
    # Mealie keys of recipes to leave out (the computer's tick boxes).
    leave_out: list[Annotated[str, Field(max_length=64)]] = Field(
        default_factory=list, max_length=MAX_RECIPES
    )
    photos: bool = True


class MealieUndone(BaseModel):
    recipes: int  # taken out
    kept: int  # changed, cooked or planned since: kept
    foods: int  # new ingredients taken out
    drafts: int


class MealieSavedAll(BaseModel):
    saved: int


def out(kitchen: Kitchen, row: MealieImport) -> MealieImportOut:
    results = [MealieResult.model_validate(entry) for entry in row.results]
    tally = {state: 0 for state in ("saved", "draft", "saved_all", "already", "skipped")}
    for result in results:
        tally[result.state] += 1
    new_foods = (
        kitchen.db.scalar(
            select(func.count()).select_from(Food).where(Food.mealie_import_id == row.id)
        )
        or 0
    )
    preview = MealiePreview.model_validate(
        {**row.preview, "recipes": row.preview.get("recipes", []) if row.state == "ready" else []}
    )
    until = mealie_import.undo_until(row)
    path = mealie_import.file_path(kitchen.db, row)
    try:
        size = path.stat().st_size if path is not None else None
    except OSError:
        size = None
    return MealieImportOut(
        id=row.id,
        state=row.state,  # type: ignore[arg-type]
        file_name=row.file_name,
        file_bytes=size,
        started_by=row.started_by_name,
        created_at=as_utc(row.created_at),
        started_at=as_utc(row.started_at) if row.started_at else None,
        finished_at=as_utc(row.finished_at) if row.finished_at else None,
        undo_until=until if until is not None and row.state != "undone" else None,
        photos=bool(row.choices.get("photos", True)),
        leave_out=list(row.choices.get("leave_out", [])),
        total=row.total,
        done=row.done,
        counts=MealieCounts(
            saved=tally["saved"] + tally["saved_all"],
            drafts=tally["draft"],
            already=row.preview.get("already", 0) + tally["already"],
            skipped=tally["skipped"],
            new_foods=new_foods,
        ),
        preview=preview,
        recent=results[-8:],
        to_check=[result for result in results if result.state == "draft"][:50],
    )


def _signed_in(request: Request) -> int:
    """Refuse (401) unless signed in, and (403) unless the household's admin on a device, before
    a byte of the file is read (a short session of its own, as for a photo upload). The
    household's id."""
    with request.app.state.sessionmaker() as db:
        caller = current(request, db)
        if not allowed(caller.login.role, Action.YOUR_DATA, caller.by_token):
            if caller.by_token and allowed(caller.login.role, Action.YOUR_DATA):
                raise not_for_tokens()
            raise Problem(status.HTTP_403_FORBIDDEN, "admins_only", ADMINS_ONLY)
        return caller.login.household_id


async def _mealie_file(
    request: Request, household_id: Annotated[int, Depends(_signed_in)]
) -> AsyncIterator[Path]:
    """The uploaded file, streamed to a temporary file in the data folder (never held in
    memory). The body limit (1 GB on this route only) is checked as it arrives. The household's
    upload guard is held until the route has read the file and made its preview (round 2, S1),
    so a second upload from the household is refused meanwhile."""
    with _UPLOADING_LOCK:
        if household_id in _UPLOADING:
            raise Problem(status.HTTP_503_SERVICE_UNAVAILABLE, "mealie_upload_busy", UPLOAD_BUSY)
        _UPLOADING.add(household_id)
    path: Path | None = None
    try:
        incoming: Path = request.app.state.settings.data_dir / mealie_import.FOLDER / "incoming"
        incoming.mkdir(mode=0o700, parents=True, exist_ok=True)
        path = incoming / f"{secrets.token_hex(16)}.part"
        size = 0
        try:
            with path.open("xb") as file:
                async for chunk in request.stream():
                    size += len(chunk)
                    if size > MAX_MEALIE_BYTES:  # the middleware stops it first; to be sure
                        raise Problem(
                            status.HTTP_413_CONTENT_TOO_LARGE,
                            "mealie_too_big",
                            MEALIE_TOO_BIG,
                        )
                    file.write(chunk)
        except ClientDisconnect:
            # The sender went away mid-file: nothing to answer, so no traceback (round 2).
            path.unlink(missing_ok=True)
            log.info("A Mealie upload was dropped part-way (ClientDisconnect)")
            raise Problem(status.HTTP_400_BAD_REQUEST, "mealie_dropped", NO_FILE) from None
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        if size == 0:
            path.unlink(missing_ok=True)
            raise Problem(status.HTTP_422_UNPROCESSABLE_CONTENT, "mealie_no_file", NO_FILE)
        yield path
    finally:
        # The route has finished or failed. `create()` moves the file away when it keeps it
        # (and deletes it when it refuses), so only a failure after the body arrived (a refused
        # sign-in, say) leaves a file here: it goes now, not a day on (security check of L1).
        if path is not None:
            path.unlink(missing_ok=True)
        with _UPLOADING_LOCK:
            _UPLOADING.discard(household_id)


MealieFile = Annotated[Path, Depends(_mealie_file)]

_FILE_BODY = {
    "requestBody": {
        "required": True,
        "description": "Mealie's backup file itself (the .zip from Settings > Admin Settings >"
        f" Backups), as the request body (not a form). At most {MAX_MEALIE_BYTES // 1024**3} GB.",
        "content": {"application/zip": {"schema": {"type": "string", "format": "binary"}}},
    }
}


@router.post(
    "/mealie-imports",
    status_code=status.HTTP_201_CREATED,
    openapi_extra=_FILE_BODY,
    responses={
        409: {"description": "`mealie_busy`: an import is running in the household."},
        413: {"description": "`mealie_too_big` (over 1 GB) or `body_too_big`."},
        422: {
            "description": "`mealie_not_zip`, `mealie_not_mealie`, `mealie_too_big`,"
            " `mealie_too_many`, `mealie_unreadable`, `mealie_no_file`."
        },
        503: {"description": "`mealie_busy` or `mealie_upload_busy`: try again in a moment."},
    },
)
def upload(
    upload: MealieFile,
    kitchen: Here,
    file_name: Annotated[str, Query(max_length=500)] = "",
) -> MealieImportOut:
    """Send Mealie's backup file and get what is in it. Nothing is added: the file is kept on
    the server until "Bring in" (`POST /mealie-imports/{id}/start`) or Cancel, or for a day.
    Only one file waits at a time: sending another lets the earlier one go."""
    row = mealie_import.create(kitchen, upload, file_name)
    return out(kitchen, row)


@router.get("/mealie-imports/current")
def get_current(kitchen: Here) -> MealieCurrent:
    """The import running now, or else the newest one (for the import screen to carry on)."""
    row = mealie_import.latest(kitchen)
    return MealieCurrent(current=out(kitchen, row) if row is not None else None)


@router.get("/mealie-imports/{import_id}")
def get_one(import_id: StoredInt, kitchen: Here) -> MealieImportOut:
    """One import, with its progress while it runs (the screens ask every few seconds)."""
    return out(kitchen, mealie_import.find(kitchen, import_id))


@router.post(
    "/mealie-imports/{import_id}/start",
    status_code=status.HTTP_202_ACCEPTED,
    responses={409: {"description": "`mealie_busy` or `mealie_not_ready`."}},
)
def start(
    import_id: StoredInt, body: MealieStart, kitchen: Here, request: Request
) -> MealieImportOut:
    """ "Bring in": the server brings the recipes in on its own; the screen can be left.
    Recipes whose every ingredient line was read are saved; the others wait in Drafts."""
    kitchen.admin_only(Action.YOUR_DATA)
    row = mealie_import.find(kitchen, import_id)
    mealie_import.start(kitchen, row, body.leave_out, body.photos)
    request.app.state.mealie.kick(row.id)
    return out(kitchen, row)


@router.delete(
    "/mealie-imports/{import_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={409: {"description": "`mealie_not_ready`: it has finished already."}},
)
def cancel(import_id: StoredInt, kitchen: Here) -> Response:
    """Cancel on the preview: the file is deleted and nothing was added. Cancel while it runs:
    it stops between two short stretches of work; what came in stays, with the import's Undo."""
    # Cancel while it runs is proposed, for cabledrawer (round 1). Not in the docstring: that is
    # the public API page, which names nobody.
    kitchen.admin_only(Action.YOUR_DATA)
    mealie_import.cancel(kitchen, mealie_import.find(kitchen, import_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/mealie-imports/{import_id}/undo",
    responses={
        409: {"description": "`mealie_not_done`: it hasn't finished."},
        410: {"description": "`too_old`: more than 7 days ago."},
    },
)
def undo(import_id: StoredInt, kitchen: Here) -> MealieUndone:
    """The import's one Undo, for 7 days: its recipes, new ingredients and drafts are taken out,
    except recipes changed, cooked or planned since and ingredients something else uses."""
    kitchen.admin_only(Action.YOUR_DATA)
    done = mealie_import.undo(kitchen, mealie_import.find(kitchen, import_id))
    return MealieUndone(recipes=done.recipes, kept=done.kept, foods=done.foods, drafts=done.drafts)


@router.post("/mealie-imports/drafts/save-all")
def save_all(kitchen: Here) -> MealieSavedAll:
    """Save all the Mealie drafts as they are: lines Mealwright couldn't read are kept as plain
    text and never go on the shopping list."""
    kitchen.admin_only(Action.YOUR_DATA)
    return MealieSavedAll(saved=mealie_import.save_all_drafts(kitchen))


class MealieNote(BaseModel):
    """Today's note for an import that finished in the last day."""

    id: int
    state: Literal["done", "failed"]
    recipes: int
    to_check: int


def today_note(kitchen: Kitchen, now: datetime | None = None) -> MealieNote | None:
    now = now or utcnow()
    row = kitchen.db.scalar(
        select(MealieImport)
        .where(
            MealieImport.household_id == kitchen.household_id,
            MealieImport.state.in_(("done", "failed")),
            MealieImport.finished_at.is_not(None),
        )
        .order_by(MealieImport.id.desc())
        .limit(1)
    )
    if row is None or row.finished_at is None:
        return None
    if as_utc(row.finished_at) <= now - timedelta(hours=mealie_import.NOTE_HOURS):
        return None
    saved = drafts = 0
    for entry in row.results:
        state: Any = entry.get("state")
        saved += state in ("saved", "saved_all")
        drafts += state == "draft"
    return MealieNote(id=row.id, state=row.state, recipes=saved + drafts, to_check=drafts)  # type: ignore[arg-type]
