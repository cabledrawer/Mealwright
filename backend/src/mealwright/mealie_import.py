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
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from fastapi import status
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker

from mealwright import drafts, mealie_file, photos
from mealwright.api.v1.context import Kitchen
from mealwright.api.v1.draft_schemas import DraftIn
from mealwright.api.v1.import_schemas import ImportReview, ReviewLine, ReviewPhoto, ReviewSource
from mealwright.api.v1.recipe_schemas import RecipeIn
from mealwright.conversions import guess_aisle, table
from mealwright.errors import Problem, not_found
from mealwright.foods import shop_choices
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
from mealwright.pack_sizes import usual_shop_id

log = logging.getLogger(__name__)

UNDO_DAYS = 7  # cabledrawer 13 Nov: "one Undo for the whole import (7 days ...)"
READY_HOURS = 24  # a read file nobody brought in is deleted after a day (proposed, for cabledrawer)
NOTE_HOURS = 24  # Today's note shows for a day after it finished (proposed, for cabledrawer)
FOLDER = "mealie"
MAX_FILE_NAME = 200
PREVIEW_TAGS = 3  # the computer's table shows the first few Mealie tags
# The new ingredients' names the preview lists under "See" (the rest are counted).
PREVIEW_NEW_FOODS = 200
# At most this many new ingredients come from one import (proposed, for cabledrawer; round 1):
# the rest aren't added, so the lines that name them aren't read and their recipes wait in
# Drafts, to be checked like any import. The preview says so.
MAX_NEW_FOODS = 5_000
# The import holds the database's write lock in short stretches, so other households' writes
# (and a person's own) get in between: each stretch ends once it has taken about this long,
# after at least one recipe or ingredient (round 1, S-H1).
HOLD_SECONDS = 0.5
# Between two stretches the lock is left free this long, so a write that is waiting for it
# (SQLite's wait checks again every 0.1 s at most) gets its turn.
PAUSE_SECONDS = 0.1
# Recipes read and their photos cleaned at a time, before the lock is taken to add them.
PREPARE = 25
# Undo and "Save all" check and change this many rows a query.
CHUNK = 500

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
    # Only the draft's link is read from its review, not the whole review (round 1, S-L6).
    url = ImportDraft.review[("source", "url")].as_string()
    for name, source in db.execute(
        select(ImportDraft.name, url).where(
            ImportDraft.household_id == household_id, ImportDraft.mealie_import_id.is_not(None)
        )
    ):
        have.add((fold(name), source or None))
    return have


def _food_names(db: Session, household_id: int) -> set[str]:
    """Every visible ingredient's name, folded: read once, not once per Mealie food (S-H1)."""
    return {
        fold(name)
        for name in db.scalars(
            select(Food.name).where(
                Food.household_id == household_id,
                Food.removed_at.is_(None),
                Food.merged_into_id.is_(None),
            )
        )
    }


def _known(names: set[str], food_name: str) -> bool:
    """A Mealie food an ingredient already matches, by its name as Mealie has it or tidied."""
    return fold(food_name) in names or fold(tidy_ingredient_name(food_name)[:100]) in names


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
    names = _food_names(kitchen.db, kitchen.household_id)
    # The new ingredients, once each (folded), with the name they will be shown with.
    new_names: dict[str, str] = {}
    for food in book.foods:
        if _known(names, food.name):
            matching += 1
        else:
            shown = tidy_ingredient_name(food.name)[:100]
            new_names.setdefault(fold(shown), shown)
    new_names.pop("", None)
    return {
        "recipes": rows,
        "new": new,
        "already": already,
        "with_photo": with_photo,
        "photo_bytes": photo_bytes,
        "foods_matching": matching,
        "foods_new": len(new_names),
        "foods_left_out": max(0, len(new_names) - MAX_NEW_FOODS),
        "foods_new_names": sorted(new_names.values(), key=fold)[:PREVIEW_NEW_FOODS],
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
    """Cancel on the preview: the file is deleted, nothing was added. Cancel while it runs
    (proposed, for cabledrawer; no button for it yet): it stops between two short stretches, what
    came in stays and has the import's Undo. Commits."""
    from mealwright.shopping import lock_household

    lock_household(kitchen)
    kitchen.db.refresh(row)
    if row.state == "running":
        row.state = "done"
        row.finished_at = utcnow()
        row.choices = {**row.choices, "stopped": True}
        _drop_file(kitchen.db, row)
        kitchen.db.commit()
        return
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


def _used_foods(book: MealieBook, keys: set[str]) -> set[str]:
    """The Mealie foods the recipes with these keys use."""
    return {food for recipe in book.recipes if recipe.key in keys for food in recipe.foods}


def _foods_to_make(
    kitchen: Kitchen, row: MealieImport, book: MealieBook, used: set[str]
) -> list[dict[str, Any]]:
    """The new ingredients, worked out before any lock is taken: the Mealie foods (of the
    recipes being brought in) no ingredient matches, once each, up to the most one import
    adds (counting any it made before a restart)."""
    room = MAX_NEW_FOODS - (
        kitchen.db.scalar(
            select(func.count()).select_from(Food).where(Food.mealie_import_id == row.id)
        )
        or 0
    )
    names = _food_names(kitchen.db, kitchen.household_id)
    shops = shop_choices(kitchen)
    todo: list[dict[str, Any]] = []
    for food in book.foods:
        if food.key not in used or _known(names, food.name):
            continue
        name = tidy_ingredient_name(food.name)[:100]
        folded = fold(name)
        if not folded:
            continue
        if len(todo) >= room:  # the rest wait: their recipes go to Drafts
            break
        names.add(folded)
        found = table().match(name)
        todo.append(
            {
                "name": name,
                "counted_as": found.counted_as if found else "weight",
                "shop_id": usual_shop_id([name], shops),
                "aisle": guess_aisle(name, found),
                "table_key": found.key if found else None,
            }
        )
    return todo


def _make_foods(kitchen: Kitchen, row: MealieImport, todo: list[dict[str, Any]]) -> bool:
    """Add the new ingredients, marked "from Mealie", a short stretch of the lock at a time.
    A name added meanwhile (by a person, or before a restart) is skipped. False: the import
    stopped meanwhile."""
    from mealwright.shopping import bump_foods

    db = kitchen.db
    at = 0
    while at < len(todo):
        if not _lock(kitchen, row):
            db.rollback()
            return False
        names = _food_names(db, kitchen.household_id)
        began, first = time.monotonic(), at
        made: list[Food] = []
        while at < len(todo) and (at == first or time.monotonic() - began < HOLD_SECONDS):
            plan = todo[at]
            at += 1
            if fold(plan["name"]) in names:
                continue
            names.add(fold(plan["name"]))
            food = Food(
                household_id=kitchen.household_id,
                staple=False,
                mealie_import_id=row.id,
                **plan,
            )
            db.add(food)
            made.append(food)
            if len(made) % 50 == 0:  # written as it goes, so the time counts the writing
                db.flush()
        db.flush()
        bump_foods(kitchen, [food.id for food in made])
        db.commit()
        _pause()
    return True


def _pause() -> None:
    """Leave the lock free for a moment between two stretches."""
    time.sleep(PAUSE_SECONDS)


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


@dataclass
class _Ready:
    """A recipe made ready outside the lock: its review, and its photo cleaned and written
    (the files only; the record is added with the recipe)."""

    recipe: MealieRecipe
    review: ImportReview | None  # None: it couldn't be read
    photo_key: str | None = None
    photo: photos.Cleaned | None = None
    photo_bytes: int = 0
    kept: bool = False  # the photo's record was committed


def _prepare(
    kitchen: Kitchen, chunk: list[MealieRecipe], pictures: MealiePhotos | None
) -> list[_Ready]:
    """Read the recipes and clean their photos, with no lock held (S-M2): the household's
    ingredients are read once for the lot (round 1, review 4)."""
    from mealwright.ingredient_match import kitchen_of
    from mealwright.recipe_import import _food_places

    db = kitchen.db
    known = (kitchen_of(db, kitchen.household_id), _food_places(kitchen))
    db.commit()  # nothing was written: this only ends the read
    store = photos.store_of(db)
    ready: list[_Ready] = []
    for recipe in chunk:
        try:
            item = _Ready(recipe, _review_of(kitchen, recipe, known))
        except Exception as why:
            db.rollback()
            log.warning("A Mealie recipe couldn't be read; it was skipped (%s)", type(why).__name__)
            ready.append(_Ready(recipe, None))
            continue
        ready.append(item)
        if pictures is None or recipe.photo is None:
            continue
        try:
            cleaned = pictures.cleaned(recipe.photo)
            if cleaned is not None:
                key = photos.new_key()
                item.photo_bytes = photos.write(store, kitchen.household_id, key, cleaned)
                item.photo_key, item.photo = key, cleaned
        except Exception as why:  # the photo never stops a recipe
            log.warning("A Mealie photo couldn't be kept (%s)", type(why).__name__)
    return ready


def _photo(kitchen: Kitchen, item: _Ready) -> int | None:
    """The recipe's photo record (its files are written already), not on any recipe yet."""
    if item.photo is None or item.photo_key is None:
        return None
    photo = RecipePhoto(
        household_id=kitchen.household_id,
        recipe_id=None,
        file_key=item.photo_key,
        width=item.photo.large_size[0],
        height=item.photo.large_size[1],
        list_width=item.photo.small_size[0],
        list_height=item.photo.small_size[1],
        bytes=item.photo_bytes,
        added_at=utcnow(),
        added_by_name=kitchen.login.name,
    )
    kitchen.db.add(photo)
    kitchen.db.flush()
    return photo.id


def _let_go(db: Session, household_id: int, ready: list[_Ready]) -> None:
    """Delete the files of photos whose record was never committed."""
    store = photos.store_of(db)
    for item in ready:
        if item.photo_key is not None and not item.kept:
            photos.remove_files(store, household_id, item.photo_key)
            item.photo_key = None


def _review_of(
    kitchen: Kitchen, recipe: MealieRecipe, known: tuple[Any, dict[int, str]]
) -> ImportReview:
    from mealwright.recipe_import import _from_page, _review

    source = _source(recipe.source)
    return _review(
        kitchen,
        _from_page(recipe.page),
        ReviewSource(kind="mealie", url=source, site=_site(source)),
        ReviewPhoto(state="none"),
        known,
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
    kitchen: Kitchen, row: MealieImport, item: _Ready, have: set[tuple[str, str | None]]
) -> dict[str, Any]:
    """One recipe, in its own savepoint: saved, a draft, already here, or skipped."""
    db = kitchen.db
    recipe = item.recipe
    same = (fold(_name(recipe)), _source(recipe.source))
    if same in have:  # added since the preview
        return {"key": recipe.key, "name": _name(recipe), "state": "already"}
    if item.review is None:
        return {"key": recipe.key, "name": _name(recipe), "state": "skipped"}
    review = item.review
    try:
        with db.begin_nested():
            photo_id = _photo(kitchen, item)
            result = _save_or_draft(kitchen, row, review, photo_id)
    except Exception as why:
        # Only the kind of failure: the recipe's own words never go in the log (S-L7).
        log.warning(
            "A Mealie recipe couldn't be brought in; it was skipped (%s)", type(why).__name__
        )
        return {"key": recipe.key, "name": _name(recipe), "state": "skipped"}
    have.add(same)
    return {"key": recipe.key, **result}


def _save_or_draft(
    kitchen: Kitchen, row: MealieImport, review: ImportReview, photo_id: int | None
) -> dict[str, Any]:
    lines = _ingredient_lines(review)
    unread = [line for line in lines if not _read(line)]
    if not unread:
        try:
            with kitchen.db.begin_nested():
                saved = _save(kitchen, review, photo_id, [_read(line) for line in review.lines])
        except (Problem, ValidationError) as why:
            log.info(
                "A Mealie recipe couldn't be saved as it was; kept as a draft (%s)",
                type(why).__name__,
            )
        else:
            return {
                "name": saved.name,
                "state": "saved",
                "recipe_id": saved.id,
                "version": saved.version,
            }
    draft = _draft(kitchen, row, review, photo_id)
    return {
        "name": draft.name,
        "state": "draft",
        "draft_id": draft.id,
        "unread": [cut_text(line.written, 100) for line in unread[:3]],
        "unread_count": len(unread),
    }


def _add(
    kitchen: Kitchen, row: MealieImport, ready: list[_Ready], have: set[tuple[str, str | None]]
) -> bool:
    """Add the prepared recipes, a short stretch of the lock at a time; the import's results
    are written once a stretch (S-L6). False: the import stopped meanwhile."""
    db = kitchen.db
    at = 0
    while at < len(ready):
        if not _lock(kitchen, row):
            db.rollback()
            return False
        began, first = time.monotonic(), at
        results: list[dict[str, Any]] = []
        while at < len(ready) and (at == first or time.monotonic() - began < HOLD_SECONDS):
            results.append(_bring_in(kitchen, row, ready[at], have))
            at += 1
        row.results = [*row.results, *results]
        row.done = len(row.results)
        db.commit()
        for item, result in zip(ready[first:at], results, strict=True):
            item.kept = result["state"] in ("saved", "draft")
        _pause()
    return True


def run(factory: sessionmaker[Session], import_id: int) -> None:
    """Bring the import's recipes in, carrying on from where it stopped. Never raises: a
    failure is kept on the import ("failed")."""
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
        except Exception as why:
            db.rollback()
            log.warning("An import from Mealie stopped part-way (%s)", type(why).__name__)
            with contextlib.suppress(Exception):
                row = db.get(MealieImport, import_id)
                if row is not None and row.state == "running":
                    row.state = "failed"
                    row.finished_at = utcnow()
                    _drop_file(db, row)
                    db.commit()


def _carry_on(kitchen: Kitchen, row: MealieImport, book: MealieBook, path: Path) -> None:
    """The work, in short locked stretches. Each stretch checks the import is still running
    (so stopping it takes effect between them), and a restart skips what was saved."""
    db = kitchen.db
    db.refresh(row)
    if row.state != "running":
        return
    leave_out = set(row.choices.get("leave_out", []))
    already = {entry["key"] for entry in row.preview.get("recipes", []) if entry["already"]}
    wanted = {recipe.key for recipe in book.recipes} - leave_out - already
    if not row.choices.get("foods_made"):
        todo = _foods_to_make(kitchen, row, book, _used_foods(book, wanted))
        db.commit()  # only read: ends the read
        if not _make_foods(kitchen, row, todo) or not _lock(kitchen, row):
            db.rollback()
            return
        row.choices = {**row.choices, "foods_made": True}
        db.commit()
    done = {entry["key"] for entry in row.results}
    todo_recipes = [r for r in book.recipes if r.key in wanted and r.key not in done]
    have = _have(db, kitchen.household_id)  # once; each recipe added joins it
    db.commit()  # only read: ends the read
    with contextlib.ExitStack() as stack:
        pictures = stack.enter_context(MealiePhotos(path)) if row.choices.get("photos") else None
        for first in range(0, len(todo_recipes), PREPARE):
            ready = _prepare(kitchen, todo_recipes[first : first + PREPARE], pictures)
            try:
                if not _add(kitchen, row, ready, have):
                    return
            finally:
                _let_go(db, kitchen.household_id, ready)
    if _lock(kitchen, row):
        row.state = "done"
        row.finished_at = utcnow()
        _drop_file(db, row)
        db.commit()
    else:
        db.rollback()


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


def _ids_where(db: Session, column: Any, ids: list[int], *where: Any) -> set[int]:
    """The values of `column` among `ids` that match `where`, a chunk of ids a query."""
    found: set[int] = set()
    for first in range(0, len(ids), CHUNK):
        chunk = ids[first : first + CHUNK]
        found.update(db.scalars(select(column).where(column.in_(chunk), *where)))
    return found


def _kept_recipes(db: Session, versions: dict[int, int], since: datetime) -> set[int]:
    """Of these recipes (id → version when imported), the ones changed, cooked, planned or
    used in another recipe since the import: they stay. A few queries for all of them."""
    ids = sorted(versions)
    kept = {
        recipe_id
        for first in range(0, len(ids), CHUNK)
        for recipe_id, version in db.execute(
            select(Recipe.id, Recipe.version).where(Recipe.id.in_(ids[first : first + CHUNK]))
        )
        if version != versions[recipe_id]
    }
    kept |= _ids_where(db, CookedRecord.recipe_id, ids, CookedRecord.cooked_at >= since)
    kept |= _ids_where(db, MealItem.recipe_id, ids)
    kept |= _ids_where(
        db,
        RecipeLine.sub_recipe_id,
        ids,
        RecipeLine.recipe_id != RecipeLine.sub_recipe_id,
        RecipeLine.recipe_id.in_(select(Recipe.id).where(Recipe.removed_at.is_(None))),
    )
    return kept


def _used_foods_of(db: Session, household_id: int, ids: list[int]) -> set[int]:
    """Of these ingredients, the ones something uses: the pantry, a list, the plan, a
    homemade recipe, or a recipe that isn't deleted."""
    used: set[int] = set()
    for model in (StockLot, ListItem, MealItem):
        used |= _ids_where(db, model.food_id, ids, model.household_id == household_id)
    used |= _ids_where(db, Recipe.homemade_food_id, ids)
    used |= _ids_where(
        db,
        RecipeLine.food_id,
        ids,
        RecipeLine.recipe_id.in_(select(Recipe.id).where(Recipe.removed_at.is_(None))),
    )
    return used


@dataclass
class Undone:
    recipes: int
    kept: int
    foods: int
    drafts: int


def _undo_ready(row: MealieImport) -> None:
    until = undo_until(row)
    if row.state == "running" or until is None:
        raise Problem(status.HTTP_409_CONFLICT, "mealie_not_done", NOT_DONE)
    if utcnow() > until:
        raise Problem(status.HTTP_410_GONE, "too_old", TOO_LATE)


def undo(kitchen: Kitchen, row: MealieImport) -> Undone:
    """The import's one Undo, in short locked stretches of a few hundred rows each (S-M3):
    what to keep is checked again inside each stretch. A stop part-way leaves the import
    to be undone again, which carries on. Commits."""
    from mealwright.history import as_utc, bump_recipes_by
    from mealwright.shopping import bump_foods, lock_household

    db = kitchen.db
    db.refresh(row)
    _undo_ready(row)
    since = as_utc(row.started_at or row.created_at)
    versions = {
        int(entry["recipe_id"]): int(entry.get("version") or 0)
        for entry in row.results
        if entry.get("recipe_id")
    }
    db.commit()  # only read: ends the read
    removed = kept = foods = gone_drafts = 0
    ids = sorted(versions)
    for first in range(0, max(len(ids), 1), CHUNK):
        chunk = ids[first : first + CHUNK]
        lock_household(kitchen)
        db.refresh(row)
        _undo_ready(row)
        live = set(
            db.scalars(
                select(Recipe.id).where(
                    Recipe.id.in_(chunk),
                    Recipe.household_id == kitchen.household_id,
                    Recipe.removed_at.is_(None),
                )
            )
        )
        stays = _kept_recipes(db, {i: versions[i] for i in live}, since)
        going = sorted(live - stays)
        kept += len(stays)
        now = utcnow()
        for recipe in db.scalars(select(Recipe).where(Recipe.id.in_(going))):
            recipe.removed_at = now
        db.flush()
        users = set(
            db.scalars(select(RecipeLine.recipe_id).where(RecipeLine.sub_recipe_id.in_(going)))
        )
        bump_recipes_by(kitchen, users - set(going))
        removed += len(going)
        db.commit()
        _pause()
    while True:
        lock_household(kitchen)
        db.refresh(row)
        _undo_ready(row)
        chunk = list(
            db.scalars(
                select(ImportDraft.id)
                .where(
                    ImportDraft.household_id == kitchen.household_id,
                    ImportDraft.mealie_import_id == row.id,
                    ImportDraft.removed_at.is_(None),
                )
                .limit(CHUNK)
            )
        )
        drafts.delete_for_good(db, chunk)
        gone_drafts += len(chunk)
        db.commit()
        _pause()
        if len(chunk) < CHUNK:
            break
    food_ids = list(
        db.scalars(
            select(Food.id).where(
                Food.household_id == kitchen.household_id,
                Food.mealie_import_id == row.id,
                Food.removed_at.is_(None),
            )
        )
    )
    db.commit()  # only read: ends the read
    for first in range(0, max(len(food_ids), 1), CHUNK):
        chunk = food_ids[first : first + CHUNK]
        lock_household(kitchen)
        db.refresh(row)
        _undo_ready(row)
        going = sorted(set(chunk) - _used_foods_of(db, kitchen.household_id, chunk))
        now = utcnow()
        for food in db.scalars(select(Food).where(Food.id.in_(going), Food.removed_at.is_(None))):
            food.removed_at = now
        db.flush()
        bump_foods(kitchen, going)
        foods += len(going)
        if first + CHUNK >= len(food_ids):
            row.state = "undone"
            row.undone_at = now
        db.commit()
    return Undone(recipes=removed, kept=kept, foods=foods, drafts=gone_drafts)


# --- 4. Save all as they are ------------------------------------------------------------------


def mealie_drafts(kitchen: Kitchen) -> list[ImportDraft]:
    now = utcnow()
    return list(
        kitchen.db.scalars(
            select(ImportDraft)
            .where(
                *drafts.live(kitchen.household_id, now), ImportDraft.mealie_import_id.is_not(None)
            )
            .order_by(ImportDraft.id)
        )
    )


def _save_draft(kitchen: Kitchen, draft: ImportDraft) -> Recipe | None:
    """One Mealie draft saved as it is, in its own savepoint; None if it can't be."""
    db = kitchen.db
    try:
        review = ImportReview.model_validate(draft.review)
    except ValidationError:
        return None
    review = review.model_copy(update={"name": draft.name or review.name})
    try:
        with db.begin_nested():
            photo = db.scalar(select(RecipePhoto).where(RecipePhoto.draft_id == draft.id))
            if photo is not None:
                photo.draft_id = None
                db.flush()
            recipe = _save(
                kitchen,
                review,
                photo.id if photo is not None else None,
                [_read(line) for line in review.lines],
            )
            db.delete(draft)
            db.flush()
    except Problem, ValidationError:
        return None
    return recipe


def save_all_drafts(kitchen: Kitchen) -> int:
    """Save every Mealie draft as it is: the lines Mealwright read stay tied to their
    ingredient; the others are kept as plain text (not on the shopping list). Each saved
    recipe joins its import's results, so the import's Undo takes it out too. Short locked
    stretches (S-M3); each draft is checked again inside its stretch. Commits."""
    from mealwright.shopping import lock_household

    db = kitchen.db
    ids = [draft.id for draft in mealie_drafts(kitchen)]
    db.commit()  # only read: ends the read
    saved = 0
    at = 0
    while at < len(ids):
        lock_household(kitchen)
        began, first = time.monotonic(), at
        done: dict[int, dict[int, Recipe]] = {}  # import → draft → its recipe
        while at < len(ids) and (at == first or time.monotonic() - began < HOLD_SECONDS):
            draft = db.scalar(
                select(ImportDraft).where(
                    ImportDraft.id == ids[at],
                    *drafts.live(kitchen.household_id, utcnow()),
                    ImportDraft.mealie_import_id.is_not(None),
                )
            )
            at += 1
            if draft is None:
                continue
            import_id, draft_id = draft.mealie_import_id or 0, draft.id
            recipe = _save_draft(kitchen, draft)
            if recipe is None:
                continue
            done.setdefault(import_id, {})[draft_id] = recipe
            saved += 1
        for import_id, recipes in done.items():
            row = db.get(MealieImport, import_id)
            if row is None or row.household_id != kitchen.household_id:
                continue
            row.results = [
                {
                    **entry,
                    "recipe_id": recipes[entry["draft_id"]].id,
                    "version": recipes[entry["draft_id"]].version,
                    "state": "saved_all",
                }
                if entry.get("draft_id") in recipes
                else entry
                for entry in row.results
            ]
        db.commit()
        if at < len(ids):
            _pause()
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
            .where(*drafts.live(household_id, utcnow()), ImportDraft.mealie_import_id.is_not(None))
        )
        or 0
    )
