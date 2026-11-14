"""Import from Mealie (0.9.5; spec "Decided for 0.9.5", cabledrawer 13 Nov).

The person chooses Mealie's backup file; nothing is added until they have looked it over.

1. **Preview** (`create`): the file is kept in the data folder (`mealie/<household>/<key>.zip`)
   and read in a budgeted child process (`mealie_file.read_file`). The preview says what is in
   it: new recipes, the ones the household already has (same name and source: left out), the
   Mealie foods its recipes use that match an ingredient, the new ingredients, the photos' size,
   and what is never brought in. Nothing is saved but the import's own record.
2. **Bring in** (`start`): one import runs at a time in a household. It runs on the server
   (`MealieRunner`, a thread of this one process; `jobs.py` carries on after a restart), one
   recipe per transaction, so a stop part-way loses nothing and Undo still has all of it.
   New ingredients come first, marked "from Mealie" (`food.mealie_import_id`). A recipe whose
   every ingredient line is read (matched, or a staple) is saved straight away; the others
   become Drafts marked From Mealie, to go through the usual import check.
3. **Undo** (`undo`): one for the whole import, for 7 days. It takes out its recipes and its new
   ingredients and its drafts, except a recipe changed or cooked or planned since, and an
   ingredient something else uses.
4. **Save all as they are** (`save_all_drafts`): the Mealie drafts are saved with the lines
   Mealwright couldn't read kept as plain text (not tied to an ingredient, so never on the
   shopping list).

The file never leaves the server and nothing here connects anywhere. Proposed, for cabledrawer:
the choices marked so in docs/dev/recipe-import.md ("Import from Mealie").
"""

from __future__ import annotations

import contextlib
import logging
import secrets
import shutil
import threading
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import status
from pydantic import ValidationError
from sqlalchemy import exists, func, select
from sqlalchemy.orm import Session, sessionmaker

from mealwright import drafts, mealie_file, photos
from mealwright.api.v1.context import Kitchen
from mealwright.api.v1.draft_schemas import DraftIn
from mealwright.api.v1.import_schemas import ImportReview, ReviewLine, ReviewPhoto, ReviewSource
from mealwright.api.v1.recipe_schemas import RecipeIn
from mealwright.conversions import guess_aisle, table
from mealwright.errors import Problem, not_found
from mealwright.foods import name_owner, suggested_shop
from mealwright.line_prep import clean_recipe_name, tidy_ingredient_name
from mealwright.mealie_file import MealieBook, MealieFileProblem, MealiePhotos, MealieRecipe
from mealwright.models import (
    CookedRecord,
    Food,
    Household,
    ImportDraft,
    ListItem,
    Login,
    MealieImport,
    MealItem,
    Recipe,
    RecipeLine,
    RecipePhoto,
    StockLot,
    utcnow,
)
from mealwright.names import cut_text, fold

log = logging.getLogger(__name__)

UNDO_DAYS = 7  # cabledrawer 13 Nov: "one Undo for the whole import (7 days ...)"
READY_HOURS = 24  # a read file nobody brought in is deleted after a day (proposed, for cabledrawer)
NOTE_HOURS = 24  # Today's note shows for a day after it finished (proposed, for cabledrawer)
FOLDER = "mealie"
MAX_FILE_NAME = 200
PREVIEW_TAGS = 3  # the computer's table shows the first few Mealie tags

# The words are proposed, for cabledrawer (words.md section 81).
BUSY = "An import from Mealie is already running. Wait for it to finish first."
NOT_READY = "That import has already started or was cancelled."
TOO_LATE = "That import can’t be undone any more: it’s more than 7 days ago."
NOT_DONE = "That import hasn’t finished yet."


def folder(db: Session, household_id: int) -> Path:
    """Where this household's Mealie files are kept: beside the photos, in the data folder."""
    return photos.store_of(db).parent / FOLDER / str(household_id)


def file_path(db: Session, row: MealieImport) -> Path | None:
    if row.file_key is None:
        return None
    return folder(db, row.household_id) / f"{row.file_key}.zip"


def _drop_file(db: Session, row: MealieImport) -> None:
    path = file_path(db, row)
    row.file_key = None
    if path is not None:
        path.unlink(missing_ok=True)


# --- Telling the same recipe ------------------------------------------------------------------


def _name(recipe: MealieRecipe) -> str:
    """The name the recipe would be saved with (the same tidying as any import)."""
    return cut_text(clean_recipe_name(recipe.page.name), 200).rstrip()


def _source(url: str | None) -> str | None:
    """Mealie's "original URL", kept like an import's link; anything else is not kept."""
    from mealwright.recipe_import import _source as tidy

    try:
        return tidy(url)
    except Problem:
        return None


def _site(url: str | None) -> str | None:
    from mealwright.recipes import site_of

    return site_of(url)[:253] or None if url else None


def _have(db: Session, household_id: int) -> set[tuple[str, str | None]]:
    """(folded name, source) of every recipe the household has (not deleted), and of every
    Mealie draft still waiting, so a second import of the same file doesn't make the drafts
    twice (proposed, for cabledrawer)."""
    have = {
        (fold(name), source)
        for name, source in db.execute(
            select(Recipe.name, Recipe.source_url).where(
                Recipe.household_id == household_id, Recipe.removed_at.is_(None)
            )
        )
    }
    for name, review in db.execute(
        select(ImportDraft.name, ImportDraft.review).where(
            ImportDraft.household_id == household_id, ImportDraft.source_kind == "mealie"
        )
    ):
        source = (review or {}).get("source") or {}
        have.add((fold(name), source.get("url") if isinstance(source, dict) else None))
    return have


def _same(have: set[tuple[str, str | None]], recipe: MealieRecipe) -> bool:
    """Already here: same name and same source (no source on both counts as the same)."""
    return (fold(_name(recipe)), _source(recipe.source)) in have


# --- 1. The preview ---------------------------------------------------------------------------


def _preview(kitchen: Kitchen, book: MealieBook) -> dict[str, Any]:
    have = _have(kitchen.db, kitchen.household_id)
    rows = []
    new = already = with_photo = photo_bytes = 0
    for recipe in book.recipes:
        here = _same(have, recipe)
        if here:
            already += 1
        else:
            new += 1
            if recipe.photo is not None:
                with_photo += 1
                photo_bytes += recipe.photo_bytes
        rows.append(
            {
                "key": recipe.key,
                "name": _name(recipe) or drafts.NO_NAME,
                "tags": list(recipe.page.tags[:PREVIEW_TAGS]),
                "photo": recipe.photo is not None,
                "already": here,
            }
        )
    matching = 0
    new_names: set[str] = set()
    for food in book.foods:
        if name_owner(kitchen, food.name) is not None:
            matching += 1
        else:
            new_names.add(fold(tidy_ingredient_name(food.name)))
    new_names.discard("")
    return {
        "recipes": rows,
        "new": new,
        "already": already,
        "with_photo": with_photo,
        "photo_bytes": photo_bytes,
        "foods_matching": matching,
        "foods_new": len(new_names),
        "left_out": dict(book.left_out),
    }


def _refused(problem: MealieFileProblem) -> Problem:
    code = (
        status.HTTP_503_SERVICE_UNAVAILABLE
        if problem.reason == "busy"
        else status.HTTP_422_UNPROCESSABLE_CONTENT
    )
    return Problem(code, f"mealie_{problem.reason}", problem.message)


def running(db: Session, household_id: int) -> MealieImport | None:
    return db.scalar(
        select(MealieImport).where(
            MealieImport.household_id == household_id, MealieImport.state == "running"
        )
    )


def create(kitchen: Kitchen, upload: Path, file_name: str) -> MealieImport:
    """Read the uploaded file (`upload`, a temporary file this takes over) and keep it with its
    preview. Any earlier file that was read but not brought in is let go. Commits."""
    from mealwright.shopping import lock_household

    db = kitchen.db
    if running(db, kitchen.household_id) is not None:
        upload.unlink(missing_ok=True)
        raise Problem(status.HTTP_409_CONFLICT, "mealie_busy", BUSY)
    try:
        book = mealie_file.read_file(upload)
    except MealieFileProblem as problem:
        upload.unlink(missing_ok=True)
        raise _refused(problem) from None
    key = secrets.token_hex(16)
    kept = folder(db, kitchen.household_id) / f"{key}.zip"
    try:
        preview = _preview(kitchen, book)
        lock_household(kitchen)
        if running(db, kitchen.household_id) is not None:
            raise Problem(status.HTTP_409_CONFLICT, "mealie_busy", BUSY)
        for earlier in db.scalars(
            select(MealieImport).where(
                MealieImport.household_id == kitchen.household_id, MealieImport.state == "ready"
            )
        ):
            earlier.state = "gone"
            _drop_file(db, earlier)
        kept.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        shutil.move(upload, kept)
        name = " ".join(Path(file_name or "").name.split())[:MAX_FILE_NAME] or "mealie.zip"
        row = MealieImport(
            household_id=kitchen.household_id,
            state="ready",
            file_name=name,
            file_key=key,
            preview=preview,
            choices={},
            total=0,
            done=0,
            results=[],
            started_by_login_id=kitchen.login.id,
            started_by_name=kitchen.login.name,
            created_at=utcnow(),
        )
        db.add(row)
        db.commit()
    except BaseException:
        upload.unlink(missing_ok=True)
        kept.unlink(missing_ok=True)
        raise
    return row


def find(kitchen: Kitchen, import_id: int) -> MealieImport:
    row = kitchen.db.get(MealieImport, import_id)
    if row is None or row.household_id != kitchen.household_id or row.state == "gone":
        raise not_found("That import")
    return row


def latest(kitchen: Kitchen) -> MealieImport | None:
    """The import a screen shows: the one running, else the newest that isn't gone."""
    return running(kitchen.db, kitchen.household_id) or kitchen.db.scalar(
        select(MealieImport)
        .where(MealieImport.household_id == kitchen.household_id, MealieImport.state != "gone")
        .order_by(MealieImport.id.desc())
        .limit(1)
    )


def cancel(kitchen: Kitchen, row: MealieImport) -> None:
    """Cancel on the preview: the file is deleted, nothing was added. Commits."""
    from mealwright.shopping import lock_household

    lock_household(kitchen)
    kitchen.db.refresh(row)
    if row.state != "ready":
        raise Problem(status.HTTP_409_CONFLICT, "mealie_not_ready", NOT_READY)
    row.state = "gone"
    _drop_file(kitchen.db, row)
    kitchen.db.commit()


# --- 2. Bringing it in ------------------------------------------------------------------------


def start(kitchen: Kitchen, row: MealieImport, leave_out: list[str], with_photos: bool) -> None:
    """ "Bring in": refused while another import runs in the household. Commits; the caller
    then hands the import to the runner."""
    from mealwright.shopping import lock_household

    lock_household(kitchen)
    kitchen.db.refresh(row)
    if row.state != "ready":
        raise Problem(status.HTTP_409_CONFLICT, "mealie_not_ready", NOT_READY)
    if running(kitchen.db, kitchen.household_id) is not None:
        raise Problem(status.HTTP_409_CONFLICT, "mealie_busy", BUSY)
    keys = {entry["key"] for entry in row.preview.get("recipes", [])}
    out = sorted(keys & set(leave_out))
    row.choices = {"leave_out": out, "photos": bool(with_photos)}
    row.total = sum(
        1
        for entry in row.preview.get("recipes", [])
        if not entry["already"] and entry["key"] not in out
    )
    row.done = 0
    row.results = []
    row.state = "running"
    row.started_at = utcnow()
    row.started_by_login_id = kitchen.login.id
    row.started_by_name = kitchen.login.name
    kitchen.db.commit()


def _kitchen(db: Session, row: MealieImport) -> Kitchen | None:
    household = db.get(Household, row.household_id)
    if household is None:
        return None
    login = db.get(Login, row.started_by_login_id) if row.started_by_login_id else None
    if login is None or login.household_id != household.id:
        # Whoever started it has gone since: the household's first login carries on, and the
        # recipes say who started it all the same.
        login = db.scalar(
            select(Login).where(Login.household_id == household.id).order_by(Login.id).limit(1)
        )
    if login is None:
        return None
    return Kitchen(
        db=db,
        login=login,
        household=household,
        idempotency_key=None,
        request="Import from Mealie",
    )


def _lock(kitchen: Kitchen, row: MealieImport) -> bool:
    """Take the household's lock and read the import afresh: still running?"""
    from mealwright.shopping import lock_household

    lock_household(kitchen)
    kitchen.db.refresh(row)
    return row.state == "running"


def _new_foods(kitchen: Kitchen, row: MealieImport, book: MealieBook) -> None:
    """The Mealie foods no ingredient matches become ingredients, marked "from Mealie"."""
    from mealwright.shopping import bump_foods

    made: list[int] = []
    for food in book.foods:
        name = tidy_ingredient_name(food.name)
        if not fold(name) or name_owner(kitchen, name) is not None:
            continue
        found = table().match(name)
        new = Food(
            household_id=kitchen.household_id,
            name=name[:100],
            counted_as=found.counted_as if found else "weight",
            staple=False,
            shop_id=suggested_shop(kitchen, name),
            aisle=guess_aisle(name, found),
            table_key=found.key if found else None,
            mealie_import_id=row.id,
        )
        kitchen.db.add(new)
        kitchen.db.flush()
        made.append(new.id)
    bump_foods(kitchen, made)


def _read(line: ReviewLine) -> bool:
    """A line Mealwright read whole: tied to an ingredient (matched, or a staple)."""
    return line.label in ("matched", "staple") and line.food is not None


def _ingredient_lines(review: ImportReview) -> list[ReviewLine]:
    return [
        line
        for line in review.lines
        if line.kind == "ingredient" and (line.written.strip() or line.words.strip())
    ]


def _line_row(line: ReviewLine, linked: bool) -> dict[str, Any]:
    """A review line as the recipe editor's save takes it. Not `linked`: its words only, never
    tied to an ingredient (so never on the shopping list)."""
    if line.kind == "heading":
        return {"kind": "heading", "words": line.words or line.written}
    food_id = line.food.id if linked and line.food is not None else None
    words = (line.words or line.written).strip() if linked else line.written.strip()
    return {
        "kind": "ingredient",
        "words": cut_text(words or line.words, 200),
        "amount": None if not linked or line.amount is None else Decimal(str(line.amount)),
        "unit": line.unit if linked else None,
        "size_id": line.size.id if linked and food_id and line.size else None,
        "food_id": food_id,
        "note": line.note if linked else None,
        "optional": line.optional,
    }


def _recipe_in(review: ImportReview, lines: list[dict[str, Any]], photo_id: int | None) -> RecipeIn:
    steps = [
        {"kind": step.kind, "text": step.text, "optional": step.optional and step.kind == "step"}
        for step in review.steps
    ]
    body: dict[str, Any] = {
        "name": review.name or drafts.NO_NAME,
        "description": review.description,
        # The file's own time: a suggested wait is only a suggestion until someone says yes.
        "time_minutes": review.page_time_minutes or review.time_minutes,
        "serves": review.serves,
        "makes": (
            None
            if review.makes is None
            else {"amount": Decimal(str(review.makes.amount)), "unit": review.makes.unit}
        ),
        "tags": review.tags,
        "nutrition": review.nutrition.model_dump(),
        "lines": lines,
        "steps": steps,
    }
    if review.second_method is not None:
        body["method_name"] = review.method_name
        body["second_method"] = {
            "name": review.second_method.name,
            "time_minutes": body["time_minutes"],
            "lines": lines,
            "steps": [
                {"kind": s.kind, "text": s.text, "optional": s.optional and s.kind == "step"}
                for s in review.second_method.steps
            ],
        }
    if photo_id is not None:
        body["photo_id"] = photo_id
    return RecipeIn.model_validate(body)


def _photo(kitchen: Kitchen, pictures: MealiePhotos | None, recipe: MealieRecipe) -> int | None:
    """The recipe's photo, cleaned like an upload and kept, not on any recipe yet."""
    if pictures is None or recipe.photo is None:
        return None
    cleaned = pictures.cleaned(recipe.photo)
    if cleaned is None:
        return None
    store = photos.store_of(kitchen.db)
    key = photos.new_key()
    size = photos.write(store, kitchen.household_id, key, cleaned)
    photo = RecipePhoto(
        household_id=kitchen.household_id,
        recipe_id=None,
        file_key=key,
        width=cleaned.large_size[0],
        height=cleaned.large_size[1],
        list_width=cleaned.small_size[0],
        list_height=cleaned.small_size[1],
        bytes=size,
        added_at=utcnow(),
        added_by_name=kitchen.login.name,
    )
    kitchen.db.add(photo)
    # The files go if this transaction is rolled back (the record is never made).
    kitchen.db.info.setdefault(_WRITTEN, []).append((kitchen.household_id, key))
    kitchen.db.flush()
    return photo.id


_WRITTEN = "mealwright.mealie_photos_written"


def _forget_written(db: Session, delete: bool) -> None:
    written = db.info.pop(_WRITTEN, [])
    if delete:
        store = photos.store_of(db)
        for household_id, key in written:
            photos.remove_files(store, household_id, key)


def _review_of(kitchen: Kitchen, recipe: MealieRecipe) -> ImportReview:
    from mealwright.recipe_import import _from_page, _review

    source = _source(recipe.source)
    return _review(
        kitchen,
        _from_page(recipe.page),
        ReviewSource(kind="mealie", url=source, site=_site(source)),
        ReviewPhoto(state="none"),
    )


def _save(
    kitchen: Kitchen, review: ImportReview, photo_id: int | None, linked: list[bool]
) -> Recipe:
    from mealwright import recipes

    lines = [_line_row(line, ok) for line, ok in zip(review.lines, linked, strict=True)]
    recipe = recipes.save(kitchen, None, _recipe_in(review, lines, photo_id), remember_key=False)
    recipe.source_url = review.source.url
    recipe.imported_at = utcnow()
    kitchen.db.flush()
    return recipe


def _draft(
    kitchen: Kitchen, row: MealieImport, review: ImportReview, photo_id: int | None
) -> ImportDraft:
    """A Mealie draft: like any draft, but not counted against the 50 (the import made it)."""
    from mealwright.recipes import photo_view

    if photo_id is not None:
        photo = kitchen.db.get(RecipePhoto, photo_id)
        if photo is not None:
            review = review.model_copy(
                update={"photo": ReviewPhoto(state="downloaded", photo=photo_view(photo))}
            )
    now = utcnow()
    draft = ImportDraft(
        household_id=kitchen.household_id,
        source_kind="mealie",
        source_text=row.file_name,
        name="",
        review={},
        choices={},
        started_by_login_id=kitchen.login.id,
        started_by_name=kitchen.login.name,
        created_at=now,
        updated_at=now,
        mealie_import_id=row.id,
    )
    kitchen.db.add(draft)
    kitchen.db.flush()
    drafts.fill(kitchen, draft, DraftIn(text=row.file_name, review=review))
    kitchen.db.flush()
    return draft


def _bring_in(
    kitchen: Kitchen, row: MealieImport, recipe: MealieRecipe, pictures: MealiePhotos | None
) -> dict[str, Any]:
    if _same(_have(kitchen.db, kitchen.household_id), recipe):  # added since the preview
        return {"key": recipe.key, "name": _name(recipe), "state": "already"}
    review = _review_of(kitchen, recipe)
    lines = _ingredient_lines(review)
    unread = [line for line in lines if not _read(line)]
    photo_id = _photo(kitchen, pictures, recipe)
    if not unread:
        try:
            saved = _save(kitchen, review, photo_id, [_read(line) for line in review.lines])
        except (Problem, ValidationError) as why:
            log.info("A Mealie recipe couldn't be saved as it was; kept as a draft (%s)", why)
        else:
            return {
                "key": recipe.key,
                "name": saved.name,
                "state": "saved",
                "recipe_id": saved.id,
                "version": saved.version,
            }
    draft = _draft(kitchen, row, review, photo_id)
    return {
        "key": recipe.key,
        "name": draft.name,
        "state": "draft",
        "draft_id": draft.id,
        "unread": [cut_text(line.written, 100) for line in unread[:3]],
        "unread_count": len(unread),
    }


def run(factory: sessionmaker[Session], import_id: int) -> None:
    """Bring the import's recipes in, one per transaction, carrying on from where it stopped.
    Never raises: a failure is kept on the import ("failed")."""
    with factory() as db:
        row = db.get(MealieImport, import_id)
        if row is None or row.state != "running":
            return
        kitchen = _kitchen(db, row)
        path = file_path(db, row)
        try:
            if kitchen is None or path is None or not path.exists():
                raise MealieFileProblem("unreadable")
            book = mealie_file.read_file(path)
            _carry_on(kitchen, row, book, path)
        except Exception:
            db.rollback()
            _forget_written(db, delete=True)
            log.exception("An import from Mealie stopped part-way")
            with contextlib.suppress(Exception):
                row = db.get(MealieImport, import_id)
                if row is not None and row.state == "running":
                    row.state = "failed"
                    row.finished_at = utcnow()
                    _drop_file(db, row)
                    db.commit()


def _carry_on(kitchen: Kitchen, row: MealieImport, book: MealieBook, path: Path) -> None:
    db = kitchen.db
    if not _lock(kitchen, row):
        return
    if not row.results and row.done == 0 and not row.choices.get("foods_made"):
        _new_foods(kitchen, row, book)
        row.choices = {**row.choices, "foods_made": True}
        db.commit()
    leave_out = set(row.choices.get("leave_out", []))
    already = {entry["key"] for entry in row.preview.get("recipes", []) if entry["already"]}
    with contextlib.ExitStack() as stack:
        pictures = stack.enter_context(MealiePhotos(path)) if row.choices.get("photos") else None
        for recipe in book.recipes:
            if recipe.key in leave_out or recipe.key in already:
                continue
            if not _lock(kitchen, row):
                return
            if any(entry["key"] == recipe.key for entry in row.results):
                continue
            try:
                result = _bring_in(kitchen, row, recipe, pictures)
            except Exception:
                db.rollback()
                _forget_written(db, delete=True)
                log.exception("A Mealie recipe couldn't be brought in; it was skipped")
                if not _lock(kitchen, row):
                    return
                result = {"key": recipe.key, "name": _name(recipe), "state": "skipped"}
            row.results = [*row.results, result]
            row.done = len(row.results)
            db.commit()
            _forget_written(db, delete=False)
    if _lock(kitchen, row):
        row.state = "done"
        row.finished_at = utcnow()
        _drop_file(db, row)
        db.commit()


class MealieRunner:
    """Runs imports on threads of this one server process (Mealwright runs as one worker), at
    most one per import. `jobs.py` hands it any import still running after a restart."""

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory
        self._lock = threading.Lock()
        self._threads: dict[int, threading.Thread] = {}

    def kick(self, import_id: int) -> None:
        with self._lock:
            thread = self._threads.get(import_id)
            if thread is not None and thread.is_alive():
                return
            thread = threading.Thread(
                target=run, args=(self.factory, import_id), name="mealie-import", daemon=True
            )
            self._threads[import_id] = thread
            thread.start()

    def resume(self) -> None:
        """Carry on with every import still marked running (after a restart)."""
        with self.factory() as db:
            ids = list(db.scalars(select(MealieImport.id).where(MealieImport.state == "running")))
        for import_id in ids:
            self.kick(import_id)

    def wait(self, timeout: float = 60) -> None:
        """For tests: until every import this runner started has stopped."""
        with self._lock:
            threads = list(self._threads.values())
        for thread in threads:
            thread.join(timeout)


# --- 3. Undo ----------------------------------------------------------------------------------


def undo_until(row: MealieImport) -> datetime | None:
    from mealwright.history import as_utc

    if row.state not in ("done", "failed") or row.finished_at is None:
        return None
    return as_utc(row.finished_at) + timedelta(days=UNDO_DAYS)


def _kept_recipe(db: Session, recipe: Recipe, version: int, since: datetime) -> bool:
    """Changed, cooked or planned since the import: the recipe stays."""
    if recipe.version != version:
        return True
    cooked = db.scalar(
        select(exists().where(CookedRecord.recipe_id == recipe.id, CookedRecord.cooked_at >= since))
    )
    planned = db.scalar(select(exists().where(MealItem.recipe_id == recipe.id)))
    used = db.scalar(
        select(
            exists().where(
                RecipeLine.sub_recipe_id == recipe.id,
                RecipeLine.recipe_id.in_(
                    select(Recipe.id).where(Recipe.removed_at.is_(None), Recipe.id != recipe.id)
                ),
            )
        )
    )
    return bool(cooked or planned or used)


def _food_used(db: Session, food: Food) -> bool:
    """Something other than the import's own recipes uses the ingredient."""
    for model, column in (
        (StockLot, StockLot.food_id),
        (ListItem, ListItem.food_id),
        (MealItem, MealItem.food_id),
    ):
        if db.scalar(
            select(exists().where(column == food.id, model.household_id == food.household_id))
        ):
            return True
    if db.scalar(select(exists().where(Recipe.homemade_food_id == food.id))):
        return True
    return bool(
        db.scalar(
            select(
                exists().where(
                    RecipeLine.food_id == food.id,
                    RecipeLine.recipe_id.in_(select(Recipe.id).where(Recipe.removed_at.is_(None))),
                )
            )
        )
    )


@dataclass
class Undone:
    recipes: int
    kept: int
    foods: int
    drafts: int


def undo(kitchen: Kitchen, row: MealieImport) -> Undone:
    """The import's one Undo. Commits."""
    from mealwright.history import as_utc, bump_recipes_by
    from mealwright.shopping import bump_foods, lock_household

    db = kitchen.db
    lock_household(kitchen)
    db.refresh(row)
    until = undo_until(row)
    if row.state == "running" or until is None:
        raise Problem(status.HTTP_409_CONFLICT, "mealie_not_done", NOT_DONE)
    if utcnow() > until:
        raise Problem(status.HTTP_410_GONE, "too_old", TOO_LATE)
    since = as_utc(row.started_at or row.created_at)
    now = utcnow()
    removed: list[Recipe] = []
    kept = 0
    for entry in row.results:
        recipe = db.get(Recipe, entry.get("recipe_id") or 0)
        if recipe is None or recipe.household_id != kitchen.household_id or recipe.removed_at:
            continue
        if _kept_recipe(db, recipe, int(entry.get("version") or 0), since):
            kept += 1
            continue
        recipe.removed_at = now
        removed.append(recipe)
    db.flush()
    from mealwright.recipes import _users_of

    users: set[int] = set()
    for recipe in removed:
        users |= _users_of(kitchen, recipe.id)
    bump_recipes_by(kitchen, users - {recipe.id for recipe in removed})
    gone_drafts = list(
        db.scalars(
            select(ImportDraft.id).where(
                ImportDraft.household_id == kitchen.household_id,
                ImportDraft.mealie_import_id == row.id,
                ImportDraft.removed_at.is_(None),
            )
        )
    )
    drafts.delete_for_good(db, gone_drafts)
    db.flush()
    foods: list[int] = []
    for food in db.scalars(
        select(Food).where(
            Food.household_id == kitchen.household_id,
            Food.mealie_import_id == row.id,
            Food.removed_at.is_(None),
        )
    ):
        if not _food_used(db, food):
            food.removed_at = now
            foods.append(food.id)
    db.flush()
    bump_foods(kitchen, foods)
    row.state = "undone"
    row.undone_at = now
    db.commit()
    return Undone(recipes=len(removed), kept=kept, foods=len(foods), drafts=len(gone_drafts))


# --- 4. Save all as they are ------------------------------------------------------------------


def mealie_drafts(kitchen: Kitchen) -> list[ImportDraft]:
    now = utcnow()
    return list(
        kitchen.db.scalars(
            select(ImportDraft)
            .where(*drafts.live(kitchen.household_id, now), ImportDraft.source_kind == "mealie")
            .order_by(ImportDraft.id)
        )
    )


def save_all_drafts(kitchen: Kitchen) -> int:
    """Save every Mealie draft as it is: the lines Mealwright read stay tied to their
    ingredient; the others are kept as plain text (not on the shopping list). Each saved
    recipe joins its import's results, so the import's Undo takes it out too. Commits."""
    from mealwright.shopping import lock_household

    db = kitchen.db
    lock_household(kitchen)
    saved = 0
    for draft in mealie_drafts(kitchen):
        try:
            review = ImportReview.model_validate(draft.review)
        except ValidationError:
            continue
        photo = db.scalar(select(RecipePhoto).where(RecipePhoto.draft_id == draft.id))
        if photo is not None:
            photo.draft_id = None
            db.flush()
        name = draft.name or review.name
        review = review.model_copy(update={"name": name})
        with db.begin_nested():
            try:
                recipe = _save(
                    kitchen,
                    review,
                    photo.id if photo is not None else None,
                    [_read(line) for line in review.lines],
                )
            except Problem, ValidationError:
                if photo is not None:
                    photo.draft_id = draft.id
                continue
        row = db.get(MealieImport, draft.mealie_import_id or 0)
        if row is not None and row.household_id == kitchen.household_id:
            row.results = [
                {**entry, "recipe_id": recipe.id, "version": recipe.version, "state": "saved_all"}
                if entry.get("draft_id") == draft.id
                else entry
                for entry in row.results
            ]
        db.delete(draft)
        db.flush()
        saved += 1
    db.commit()
    return saved


# --- Tidying, for jobs.py ---------------------------------------------------------------------


def tidy(db: Session, now: datetime | None = None) -> int:
    """A file read but not brought in is deleted after a day. Returns how many."""
    from mealwright.history import as_utc

    now = now or utcnow()
    count = 0
    for row in db.scalars(select(MealieImport).where(MealieImport.state == "ready")):
        if as_utc(row.created_at) <= now - timedelta(hours=READY_HOURS):
            row.state = "gone"
            _drop_file(db, row)
            count += 1
    db.commit()
    # Files a stopped upload or a stopped server left behind, a day on.
    home = folder(db, 0).parent
    kept = {
        f"{row.household_id}/{row.file_key}.zip"
        for row in db.scalars(
            select(MealieImport).where(
                MealieImport.state.in_(("ready", "running")), MealieImport.file_key.is_not(None)
            )
        )
    }
    if home.is_dir():
        for path in [*home.glob("incoming/*.part"), *home.glob("*/*.zip")]:
            if f"{path.parent.name}/{path.name}" in kept:
                continue
            with contextlib.suppress(OSError):
                made = datetime.fromtimestamp(path.stat().st_mtime, UTC)
                if made <= now - timedelta(hours=READY_HOURS):
                    path.unlink(missing_ok=True)
    return count


def mealie_draft_count(db: Session, household_id: int) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(ImportDraft)
            .where(*drafts.live(household_id, utcnow()), ImportDraft.source_kind == "mealie")
        )
        or 0
    )
