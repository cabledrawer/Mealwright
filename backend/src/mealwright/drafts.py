"""Import drafts: an import left unfinished, kept for 15 days (spec section 6, "Drafts
(cabledrawer 21 Oct)" and "Drafts: how long they last (cabledrawer 22 Oct, question 8)";
docs/dev/recipe-import.md, "Drafts").

A draft belongs to the household, like a recipe, and anyone in it can carry on. It keeps what
was typed in the box, the review the server sent, the choices made on it and, through
`recipe_photo.draft_id`, the downloaded photo. **Nothing here touches Ingredients**: no
ingredient, staple or other name is made or changed by keeping, changing or deleting a draft;
the new ingredients and learned names it holds are only made when the recipe is saved
(`recipe_import.save`).

- **The 15 days** count from the last change (`updated_at`). The hourly tidy-up
  (`purge`) deletes an older draft quietly, with its photo; until then it is already hidden.
- **Deleting** hides a draft at once and records `draft_removed` in the change log (a Toast
  Undo, or Ctrl+Z). It is deleted for good, with its photo, once the undo window (7 days) has
  passed. Undo brings it back as if it had just been changed.
- **Saving a recipe from a draft** deletes the draft, but its Save keeps a copy in its own change
  record (`snapshot`), so that Undo of the Save brings the draft back (`bring_back`): the same
  id, its choices and photo, its 15 days started again (spec section 6, question 36). The
  copy is dropped as soon as that Undo is used, or by the hourly tidy-up once the Save's undo
  window has passed (`drop_save_copies`); the rest of the change stays.
- **50 drafts** at most per household. At 50 nothing is deleted to make room (cabledrawer 22 Oct,
  question 9): the answer is a plain sentence.
- **Two people at once:** the last save wins. A draft is only a place to carry on from, and
  Save checks everything again.

Nothing here makes a network connection, and nothing logs a draft's link or text.
"""

from datetime import datetime, timedelta
from typing import Any

from fastapi import status
from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession

from mealwright.api.v1.context import Kitchen
from mealwright.api.v1.draft_schemas import (
    DraftBrief,
    DraftChoice,
    DraftChoices,
    DraftIn,
    DraftOut,
    DraftSource,
)
from mealwright.api.v1.import_schemas import ImportReview, ReviewCounts, ReviewLine, ReviewPhoto
from mealwright.api.v1.schemas import Ref
from mealwright.errors import Problem, not_found
from mealwright.history import as_utc, record
from mealwright.household import undo_window
from mealwright.models import (
    Change,
    Food,
    Household,
    ImportDraft,
    Login,
    Recipe,
    RecipePhoto,
    utcnow,
)
from mealwright.names import fold
from mealwright.photos import delete_after_commit

DRAFT_DAYS = 15
MAX_DRAFTS = 50

# Spec section 6, question 9.
TOO_MANY = "You have 50 drafts. Finish or delete one first."
# The photo was a waiting upload that has since been deleted (it waits 24 hours), or isn't this
# household's: the draft is kept without it. Proposed, for cabledrawer.
PHOTO_GONE = "The photo wasn’t kept."
NO_NAME = "Untitled recipe"  # proposed, for cabledrawer: a draft whose Name box is empty


# --- Finding ----------------------------------------------------------------------------------


def expires_at(draft: ImportDraft) -> datetime:
    return as_utc(draft.updated_at) + timedelta(days=DRAFT_DAYS)


def days_left(draft: ImportDraft, now: datetime | None = None) -> int:
    """Whole days, counted up: 15 for a draft changed just now, 1 for its last day."""
    left = expires_at(draft) - (now or utcnow())
    return max(0, -(-int(left.total_seconds()) // 86_400))


def _live(household_id: int, now: datetime) -> list[Any]:
    """Drafts that are there to see: the household's, not deleted, not past their 15 days."""
    return [
        ImportDraft.household_id == household_id,
        ImportDraft.removed_at.is_(None),
        ImportDraft.updated_at > now - timedelta(days=DRAFT_DAYS),
    ]


def is_live(kitchen: Kitchen, draft_id: int) -> bool:
    """Whether the draft is there to see (the same test as `find`, without raising)."""
    return (
        kitchen.db.scalar(
            select(ImportDraft.id).where(
                ImportDraft.id == draft_id, *_live(kitchen.household_id, utcnow())
            )
        )
        is not None
    )


def find(kitchen: Kitchen, draft_id: int) -> ImportDraft:
    """A draft in this household that is there to see (else 404, whoever it belongs to)."""
    draft = kitchen.db.scalar(
        select(ImportDraft).where(
            ImportDraft.id == draft_id, *_live(kitchen.household_id, utcnow())
        )
    )
    if draft is None:
        raise not_found("That draft")
    return draft


def count(db: DbSession, household_id: int, now: datetime | None = None) -> int:
    return (
        db.scalar(
            select(func.count())
            .select_from(ImportDraft)
            .where(*_live(household_id, now or utcnow()))
        )
        or 0
    )


def _too_many() -> Problem:
    return Problem(status.HTTP_409_CONFLICT, "too_many_drafts", TOO_MANY)


# --- Describing -------------------------------------------------------------------------------


def brief(draft: ImportDraft, now: datetime | None = None) -> DraftBrief:
    return DraftBrief(
        id=draft.id,
        name=draft.name,
        source=DraftSource(kind=draft.source_kind, site=draft.site),  # type: ignore[arg-type]
        started_by=draft.started_by_name,
        started_at=as_utc(draft.created_at),
        updated_at=as_utc(draft.updated_at),
        expires_at=expires_at(draft),
        days_left=days_left(draft, now),
        lines_total=draft.lines_total,
        lines_checked=draft.lines_checked,
    )


def listing(kitchen: Kitchen) -> list[DraftBrief]:
    """The household's drafts, the one changed last first. A draft with ingredients still
    waiting is counted as opening it would find it (RF4 I7): one that another draft has made
    the ingredient for since shows it checked, so the list's count and its Save recipe button
    agree with the draft."""
    now = utcnow()
    rows = list(
        kitchen.db.scalars(
            select(ImportDraft)
            .where(*_live(kitchen.household_id, now))
            .order_by(ImportDraft.updated_at.desc(), ImportDraft.id.desc())
        )
    )
    given: list[tuple[int, str, Ref]] | None = None
    briefs = []
    for draft in rows:
        out = brief(draft, now)
        if draft.lines_checked < draft.lines_total:
            if given is None:
                given = _answers_given(kitchen, now)
            try:
                review = ImportReview.model_validate(draft.review)
                choices = DraftChoices.model_validate(draft.choices)
            except ValueError:
                briefs.append(out)
                continue
            review, choices = rematch(kitchen, review, choices, draft.id, given)
            review, choices = freshen(kitchen, review, choices)
            total, checked = _progress(review, choices)
            out = out.model_copy(update={"lines_total": total, "lines_checked": checked})
        briefs.append(out)
    return briefs


def detail(kitchen: Kitchen, draft: ImportDraft) -> DraftOut:
    """A draft to carry on with, with the ingredients that have gone since it was kept
    taken out (see `freshen`)."""
    review = ImportReview.model_validate(draft.review)
    choices = DraftChoices.model_validate(draft.choices)
    review, choices = rematch(kitchen, review, choices, draft.id)
    review, choices = freshen(kitchen, review, choices)
    return DraftOut(
        **brief(draft).model_dump(), text=draft.source_text, review=review, choices=choices
    )


# --- Drafts from one batch learn from each other (F213, F215) -------------------------------


def _answers_given(kitchen: Kitchen, now: datetime | None = None) -> list[tuple[int, str, Ref]]:
    """What the household's waiting drafts were told "Same as": (the draft, the line's words
    folded, the ingredient), the newest draft first."""
    rows = kitchen.db.scalars(
        select(ImportDraft)
        .where(*_live(kitchen.household_id, now or utcnow()))
        .order_by(ImportDraft.updated_at.desc(), ImportDraft.id.desc())
    )
    given: list[tuple[int, str, Ref]] = []
    for other in rows:
        try:
            review = ImportReview.model_validate(other.review)
            choices = DraftChoices.model_validate(other.choices)
        except ValueError:
            continue
        for index, choice in choices.lines.items():
            if choice.kind != "ingredient" or not choice.learn or choice.food is None:
                continue
            if not 0 <= index < len(review.lines):
                continue
            line = review.lines[index]
            name = line.learn_name or line.words
            if line.kind == "ingredient" and name:
                given.append((other.id, fold(name), choice.food))
    return given


def _answers_of_others(
    kitchen: Kitchen, draft_id: int, now: datetime | None = None
) -> dict[str, Ref]:
    """What the household's other waiting drafts were told "Same as": the line's words → the
    ingredient. The first answer found for a name wins (the newest draft first)."""
    return _others(_answers_given(kitchen, now), draft_id)


def _others(given: list[tuple[int, str, Ref]], draft_id: int) -> dict[str, Ref]:
    answers: dict[str, Ref] = {}
    for owner, name, food in given:
        if owner != draft_id:
            answers.setdefault(name, food)
    return answers


def rematch(
    kitchen: Kitchen,
    review: ImportReview,
    choices: DraftChoices,
    draft_id: int,
    given: list[tuple[int, str, Ref]] | None = None,
) -> tuple[ImportReview, DraftChoices]:
    """Bring a draft's matches up to date with the ingredients as they are now, without changing
    anything stored (F213, F215; cabledrawer 10 Nov).

    A draft is read once, when it is made, so an ingredient another draft from the same batch
    made (and saved) since is not known to its lines, and its "Same as" answers were asked again.
    On opening: a line still waiting ("needs you" or "to confirm") with no choice is read against
    the ingredients as they are today; a line the person set to a *new* ingredient whose name now
    exists is set to that ingredient instead; and a line that another waiting draft was told
    "Same as X" takes the same answer. `given`: those answers, when the caller has them already
    (the Drafts list asks for every draft at once)."""
    from mealwright import recipe_import
    from mealwright.ingredient_match import kitchen_of
    from mealwright.pints import PINT_ML

    waiting = [
        index
        for index, line in enumerate(review.lines)
        if line.kind == "ingredient" and line.readable and line.label in ("needs_you", "to_confirm")
    ]
    new_choices = [
        index
        for index, choice in choices.lines.items()
        if choice.kind in ("new", "staple") and choice.name
    ]
    if not waiting and not new_choices:
        return review, choices
    ingredients = kitchen_of(kitchen.db, kitchen.household_id)
    lines = list(review.lines)
    kept = dict(choices.lines)
    for index in new_choices:
        owner = next(
            (f for f in ingredients.foods if fold(f.name) == fold(kept[index].name or "")), None
        )
        if owner is not None:
            kept[index] = DraftChoice(kind="ingredient", food=Ref(id=owner.id, name=owner.name))
    places = recipe_import._food_places(kitchen)
    pint_ml = PINT_ML[review.pints.reading]
    answers: dict[str, Ref] | None = None
    for index in waiting:
        if index in kept:
            continue
        line = lines[index]
        found = recipe_import._lines(ingredients, places, line.written, False, pint_ml)
        fresh = _same_reading(line, [read for read, _pints in found])
        if fresh is not None:
            moved = fresh.label in ("matched", "staple") or (
                fresh.label == "to_confirm" and line.label == "needs_you"
            )
            if moved and fresh.food is not None:
                # Only the match is new: what the person may have fixed by hand while the
                # line waited (the words, amount, unit and note) stays (RF4 I1).
                lines[index] = line = fresh.model_copy(
                    update={
                        "written": line.written,
                        "words": line.words,
                        "amount": line.amount,
                        "amount_text": line.amount_text,
                        "unit": line.unit,
                        "note": line.note,
                        "pint_ml": line.pint_ml,
                        "optional": line.optional,
                        "own": line.own,
                    }
                )
        if line.label in ("matched", "staple"):
            continue
        name = line.learn_name or line.words
        if answers is None:
            answers = (
                _others(given, draft_id)
                if given is not None
                else _answers_of_others(kitchen, draft_id)
            )
        answered = answers.get(fold(name)) if name else None
        if answered is not None:
            kept[index] = DraftChoice(kind="ingredient", food=answered, learn=True)
    if lines == list(review.lines) and kept == choices.lines:
        return review, choices
    counts = {"matched": 0, "to_confirm": 0, "needs_you": 0, "staple": 0}
    for line in lines:
        if line.label is not None:
            counts[line.label] += 1
    return (
        review.model_copy(update={"lines": lines, "counts": ReviewCounts(**counts)}),
        choices.model_copy(update={"lines": kept}),
    )


def _same_reading(line: ReviewLine, reads: list[ReviewLine]) -> ReviewLine | None:
    """The fresh read of a written line that says what the stored line says: the one whose words
    are the same. A line written "each salt, cumin" is several lines (M4), and a line that says
    "or" can have been swapped to its other choice (H2, F217): then the fresh read's alternative
    is the match, with the fresh first choice as its own alternative so it can still be swapped
    back. None when no fresh read has the stored words (the person changed them): the line stays."""
    words = fold(line.words)
    for read in reads:
        if fold(read.words) == words:
            return read
        other = read.alternative
        if other is not None and fold(other.words) == words:
            return other.model_copy(
                update={"alternative": read.model_copy(update={"alternative": None})}
            )
    return None


# --- Ingredients that have gone ---------------------------------------------------------------


def _current(foods: dict[int, Food | None], food_id: int) -> Food | None:
    """The ingredient this id is today: followed through merges, None if it was removed."""
    food, seen = foods.get(food_id), set()
    while food is not None and food.merged_into_id is not None and food.id not in seen:
        seen.add(food.id)
        food = foods.get(food.merged_into_id)
    if food is None or food.removed_at is not None:
        return None
    return food


def freshen(
    kitchen: Kitchen, review: ImportReview, choices: DraftChoices
) -> tuple[ImportReview, DraftChoices]:
    """Bring a draft's ingredients up to date, without changing anything stored.

    A draft can wait up to 15 days, and ingredients change meanwhile. An ingredient that was
    renamed shows its new name; one that was merged into another shows that one; one that was
    removed is no longer offered: a line that was matched to it goes back to "needs you", and a
    choice that pointed at it is dropped, so the person picks again. (Save would refuse
    them anyway, line by line.) Only the household's own ingredients are looked at."""
    ids = {line.food.id for line in review.lines if line.food}
    ids |= {c.food.id for c in choices.lines.values() if c.food}
    recipe_ids = {c.recipe.id for c in choices.lines.values() if c.recipe}
    if not ids and not recipe_ids:
        return review, choices
    # A recipe a line was set to use (F188): its new name, or no choice when it is gone.
    recipes = {
        recipe.id: recipe
        for recipe in kitchen.db.scalars(
            select(Recipe).where(
                Recipe.household_id == kitchen.household_id, Recipe.id.in_(recipe_ids)
            )
        )
    }
    foods: dict[int, Food | None] = {}
    wanted = set(ids)
    while wanted:  # the ids asked for, and the ones they were merged into
        rows = kitchen.db.scalars(
            select(Food).where(Food.household_id == kitchen.household_id, Food.id.in_(wanted))
        )
        found = {food.id: food for food in rows}
        for food_id in wanted:
            foods[food_id] = found.get(food_id)
        wanted = {
            food.merged_into_id
            for food in found.values()
            if food.merged_into_id is not None and food.merged_into_id not in foods
        }
    lines = []
    for line in review.lines:
        if line.food is not None:
            now_food = _current(foods, line.food.id)
            if now_food is None:
                line = line.model_copy(
                    update={
                        "food": None,
                        "label": "needs_you" if line.kind == "ingredient" else line.label,
                        "place": None,
                        "matched_by": None,
                        "learn_name": None,
                    }
                )
            else:
                line = line.model_copy(update={"food": Ref(id=now_food.id, name=now_food.name)})
        lines.append(line)
    counts = {"matched": 0, "to_confirm": 0, "needs_you": 0, "staple": 0}
    for line in lines:
        if line.label is not None:
            counts[line.label] += 1
    kept: dict[int, DraftChoice] = {}
    for index, choice in choices.lines.items():
        if choice.food is not None:
            now_food = _current(foods, choice.food.id)
            if now_food is None:
                continue
            choice = choice.model_copy(update={"food": Ref(id=now_food.id, name=now_food.name)})
        if choice.recipe is not None:
            now_recipe = recipes.get(choice.recipe.id)
            if now_recipe is None or now_recipe.removed_at is not None:
                continue
            choice = choice.model_copy(
                update={"recipe": Ref(id=now_recipe.id, name=now_recipe.name)}
            )
        kept[index] = choice
    return (
        review.model_copy(update={"lines": lines, "counts": ReviewCounts(**counts)}),
        choices.model_copy(update={"lines": kept}),
    )


# --- Keeping and changing ---------------------------------------------------------------------


def _progress(review: ImportReview, choices: DraftChoices) -> tuple[int, int]:
    """(ingredient lines, how many are tied to an ingredient): a matched or staple line is,
    and so is any line with a choice. The same count the review screen makes."""
    total = checked = 0
    for index, line in enumerate(review.lines):
        # A line added on Check and never named is not saved, so it doesn't count (F187).
        if line.kind != "ingredient" or (not line.written and not line.words.strip()):
            continue
        total += 1
        if index in choices.lines or (line.label in ("matched", "staple") and line.food):
            checked += 1
    return total, checked


def _name_of(review: ImportReview, choices: DraftChoices) -> str:
    return ((choices.name or "").strip() or review.name.strip() or NO_NAME)[:200]


def _hold_photo(kitchen: Kitchen, draft: ImportDraft, review: ImportReview) -> ImportReview:
    """Make the review's downloaded photo the draft's own, and let go of any other photo the
    draft held. Only a waiting photo of this household (or one this draft already has) can be
    taken; anything else, such as a photo that was deleted after 24 hours or one that is
    another household's, is left alone and the draft is kept without a photo."""
    from mealwright.recipes import delete_photo, photo_view

    db = kitchen.db
    photo = None
    if review.photo.state == "downloaded" and review.photo.photo is not None:
        photo = db.get(RecipePhoto, review.photo.photo.id)
        if (
            photo is None
            or photo.household_id != kitchen.household_id
            or photo.recipe_id is not None
            or photo.draft_id not in (None, draft.id)
        ):
            photo = None
            review = review.model_copy(
                update={"photo": ReviewPhoto(state="failed", message=PHOTO_GONE)}
            )
    elif review.photo.state == "downloaded":
        review = review.model_copy(update={"photo": ReviewPhoto(state="none")})
    if photo is not None:
        photo.draft_id = draft.id
        review = review.model_copy(
            update={"photo": ReviewPhoto(state="downloaded", photo=photo_view(photo))}
        )
    for other in db.scalars(
        select(RecipePhoto).where(
            RecipePhoto.household_id == kitchen.household_id,
            RecipePhoto.draft_id == draft.id,
            RecipePhoto.id != (photo.id if photo else 0),
        )
    ):
        delete_photo(db, other)
    return review


def _fill(kitchen: Kitchen, draft: ImportDraft, body: DraftIn) -> None:
    review = _hold_photo(kitchen, draft, body.review)
    total, checked = _progress(review, body.choices)
    draft.source_kind = review.source.kind
    draft.source_text = body.text
    draft.site = review.source.site[:253] if review.source.site else None
    draft.name = _name_of(review, body.choices)
    draft.review = review.model_dump(mode="json")
    draft.choices = body.choices.model_dump(mode="json")
    draft.lines_total, draft.lines_checked = total, checked
    draft.updated_at = utcnow()


def create(kitchen: Kitchen, body: DraftIn) -> ImportDraft:
    """Keep a review as a draft. The caller holds the household's lock and commits. At 50
    drafts it refuses (never deleting an old one to make room)."""
    now = utcnow()
    if count(kitchen.db, kitchen.household_id, now) >= MAX_DRAFTS:
        raise _too_many()
    draft = ImportDraft(
        household_id=kitchen.household_id,
        source_kind=body.review.source.kind,
        source_text=body.text,
        name="",
        review={},
        choices={},
        started_by_login_id=kitchen.login.id,
        started_by_name=kitchen.login.name,
        created_at=now,
        updated_at=now,
    )
    kitchen.db.add(draft)
    kitchen.db.flush()
    _fill(kitchen, draft, body)
    kitchen.db.flush()
    return draft


def update(kitchen: Kitchen, draft: ImportDraft, body: DraftIn) -> None:
    """Replace what a draft keeps (the last save wins). It counts as a change: the 15 days
    start again."""
    _fill(kitchen, draft, body)
    kitchen.db.flush()


# --- Deleting and Undo ------------------------------------------------------------------------


def remove(kitchen: Kitchen, draft: ImportDraft) -> Change:
    """Delete a draft: hidden at once, gone for good (with its photo) after the undo window."""
    draft.removed_at = utcnow()
    return record(
        kitchen,
        "draft_removed",
        f"Deleted the {draft.name} draft",
        None,
        {"draft_id": draft.id},
    )


def undo_removal(kitchen: Kitchen, change: Change) -> Change:
    """Undo a delete: the draft comes back, counted as just changed (its 15 days start again,
    so it can't be back for a moment and then vanish). Refused at 50 drafts."""
    data = change.undo_data or {}
    draft = kitchen.db.get(ImportDraft, data.get("draft_id", 0))
    if draft is None or draft.household_id != kitchen.household_id:
        raise Problem(status.HTTP_410_GONE, "too_old", "That’s too long ago to undo.")
    if count(kitchen.db, kitchen.household_id) >= MAX_DRAFTS:
        raise _too_many()
    draft.removed_at = None
    draft.updated_at = utcnow()
    undo = record(
        kitchen,
        "undo",
        f"Undid: {change.summary}",
        None,
        {
            "result": "done",
            "message": f"The {draft.name} draft is back in Drafts.",
            "undoes_kind": change.kind,
            "undoes_at": as_utc(change.at).isoformat(),
        },
    )
    undo.undoes_change_id = change.id
    change.undone_by_change_id = undo.id
    kitchen.db.flush()
    return undo


def snapshot(draft: ImportDraft, photo_id: int | None) -> dict[str, Any]:
    """Everything of a draft that Save is about to delete, kept in the Save's own change record
    so that Undo can bring the draft back as it was (spec section 6, question 36). The photo is
    only its id: the file moves to the recipe on Save and back to the draft on Undo."""
    return {
        "id": draft.id,
        "source_kind": draft.source_kind,
        "source_text": draft.source_text,
        "site": draft.site,
        "name": draft.name,
        "review": draft.review,
        "choices": draft.choices,
        "lines_total": draft.lines_total,
        "lines_checked": draft.lines_checked,
        "started_by_login_id": draft.started_by_login_id,
        "started_by_name": draft.started_by_name,
        "created_at": as_utc(draft.created_at).isoformat(),
        "photo_id": photo_id,
    }


def make_room(kitchen: Kitchen) -> None:
    """Bringing a draft back never makes a 51st: refused with the same sentence as keeping one."""
    if count(kitchen.db, kitchen.household_id) >= MAX_DRAFTS:
        raise _too_many()


def bring_back(kitchen: Kitchen, recipe_id: int, saved: dict[str, Any]) -> str:
    """Undo of a Save from a draft: the draft is made again from its snapshot, counted as just
    changed (its 15 days start again), and its photo moves back from the recipe. Only this
    household's own photo, the one that is still the recipe's, is taken back: if the recipe's
    photo was changed or removed since, the draft comes back without it and says so. The caller
    has checked the recipe is this household's and `make_room`. Returns the Undo's sentence."""
    db = kitchen.db
    login_id = saved.get("started_by_login_id")
    if login_id is not None:
        login = db.get(Login, login_id)
        if login is None or login.household_id != kitchen.household_id:
            login_id = None
    review = ImportReview.model_validate(saved["review"])
    photo = db.get(RecipePhoto, saved["photo_id"]) if saved.get("photo_id") else None
    if photo is not None and (
        photo.household_id != kitchen.household_id or photo.recipe_id != recipe_id
    ):
        photo = None
    if photo is None and review.photo.state == "downloaded":
        review = review.model_copy(
            update={"photo": ReviewPhoto(state="failed", message=PHOTO_GONE)}
        )
    draft_id = saved.get("id")
    draft = ImportDraft(
        id=draft_id if db.get(ImportDraft, draft_id or 0) is None else None,
        household_id=kitchen.household_id,
        source_kind=saved["source_kind"],
        source_text=saved["source_text"],
        site=saved.get("site"),
        name=saved["name"],
        review=review.model_dump(mode="json"),
        choices=saved["choices"],
        lines_total=saved.get("lines_total", 0),
        lines_checked=saved.get("lines_checked", 0),
        started_by_login_id=login_id,
        started_by_name=saved.get("started_by_name", ""),
        created_at=datetime.fromisoformat(saved["created_at"]),
        updated_at=utcnow(),
    )
    db.add(draft)
    db.flush()
    if photo is not None:
        photo.recipe_id = None
        photo.draft_id = draft.id
        db.flush()
    return f"The {draft.name} draft is back in Drafts."


def delete_for_good(db: DbSession, ids: list[int]) -> None:
    """Delete these drafts and their photos (the files once this is committed)."""
    if not ids:
        return
    keys = list(
        db.execute(
            select(RecipePhoto.household_id, RecipePhoto.file_key).where(
                RecipePhoto.draft_id.in_(ids)
            )
        )
    )
    for household_id, key in keys:
        delete_after_commit(db, household_id, [key])
    db.execute(delete(RecipePhoto).where(RecipePhoto.draft_id.in_(ids)))
    db.execute(delete(ImportDraft).where(ImportDraft.id.in_(ids)))


def purge(db: DbSession, household: Household, now: datetime | None = None) -> int:
    """The hourly tidy-up: drafts 15 days past their last change are deleted quietly, and
    deleted drafts once their undo window has passed (a little past it, so a delete can't
    vanish while its Undo is still offered). Their photos go with them. Returns how many."""
    from mealwright.shopping import lock_db

    now = now or utcnow()
    lock_db(db, household)
    ids = list(
        db.scalars(
            select(ImportDraft.id).where(
                ImportDraft.household_id == household.id,
                (
                    ImportDraft.removed_at.is_(None)
                    & (ImportDraft.updated_at <= now - timedelta(days=DRAFT_DAYS))
                )
                | (
                    ImportDraft.removed_at.is_not(None)
                    & (ImportDraft.removed_at < now - undo_window(household) - timedelta(hours=1))
                ),
            )
        )
    )
    delete_for_good(db, ids)
    drop_save_copies(db, household, now)
    db.commit()
    return len(ids)


def drop_save_copies(db: DbSession, household: Household, now: datetime) -> int:
    """Drop the draft copy that a Save from a draft keeps in its change, once the Save's undo
    window has passed (its Undo is then refused, so the copy has no use). Only the copy goes:
    the rest of the change stays. The caller holds the lock and commits. Returns how many."""
    dropped = 0
    for change in db.scalars(
        select(Change).where(
            Change.household_id == household.id,
            Change.kind == "recipe_imported",
            Change.at < now - undo_window(household),
            Change.undo_data.is_not(None),
        )
    ):
        data = change.undo_data or {}
        if "draft" in data:
            change.undo_data = {key: value for key, value in data.items() if key != "draft"}
            dropped += 1
    return dropped
