"""Importing a recipe: the one box (a link or pasted text), the review, and Save (spec section 6,
"Recipe import, decided for 0.5"; docs/dev/recipe-import.md, "The import's API").

`start` reads what was given and answers with the review. **Nothing is saved**, except a main
photo that was downloaded, which waits like an uploaded one until Save (the hourly tidy-up
drops an unclaimed one). `save` is one transaction: the recipe, its new ingredients, its new
staples and the other names it learned, with **one** entry in Recent changes whose Undo takes
the whole save back.

A link goes through the outbound gate only (`page_fetch`) and its page is read only with
`page_budget.read_within_budget`. Pasted text never goes online. The whole import has 30
seconds (cabledrawer 22 Oct, question 12): the fetch, a wait for a place to read, and the photo
share them. Log lines name only the connection and the kind of problem, never an address.
"""

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from decimal import Decimal

from fastapi import status
from pydantic import ValidationError
from sqlalchemy import select

from mealwright import drafts, page_budget, page_fetch, photos
from mealwright.aisles import DEFAULT_AISLE
from mealwright.api.v1.context import Kitchen
from mealwright.api.v1.import_schemas import (
    AlreadyImported,
    ImportReview,
    ImportSave,
    LeftOutOut,
    NewIngredientOut,
    ReviewCounts,
    ReviewLine,
    ReviewMakes,
    ReviewPhoto,
    ReviewSource,
    ReviewStep,
)
from mealwright.api.v1.recipe_schemas import (
    MAX_LINES,
    MAX_STEP_CHARS,
    MAX_STEPS,
    MakesIn,
    NutritionIn,
    RecipeIn,
    SizeRef,
    amount_text,
)
from mealwright.api.v1.schemas import Ref
from mealwright.conversions import table
from mealwright.errors import Problem, not_found
from mealwright.foods import find as find_food
from mealwright.foods import name_owner, name_taken, refresh_table_key
from mealwright.history import FoodEdit
from mealwright.ingredient_match import KnownIngredients, Match, kitchen_of, match_line
from mealwright.ingredient_reader import ReadLine, read_line, working_text
from mealwright.models import (
    Change,
    Food,
    FoodName,
    Place,
    Recipe,
    RecipePhoto,
    utcnow,
)
from mealwright.names import cut_text, fold
from mealwright.outbound import LABELS, Connection, OutboundGate
from mealwright.page_budget import PageBusy, PageUnreadable, read_within_budget
from mealwright.page_fetch import FetchRefused
from mealwright.page_fetch import Problem as FetchProblem
from mealwright.page_reader import PageRecipe
from mealwright.pasted_recipe import PastedTooLong, read_pasted
from mealwright.photos import MAX_WAITING, Cleaned

log = logging.getLogger(__name__)

type Left = Callable[[], float]  # seconds the import has left

MAX_IMPORT_SECONDS = 30  # the whole import, cabledrawer 22 Oct, question 12
MAX_WORDS = 200  # a line's words
MAX_NOTE = 200
MAX_WRITTEN = 1000  # how much of a line as written the review keeps

# Sentences the screens show (docs/dev/words.md section 18; the ones marked there as proposed
# are for cabledrawer).
NOTHING_GIVEN = "Paste a link or the recipe’s text."
NO_RECIPE_ON_PAGE = (
    "That page doesn’t have a recipe Mealwright can read. Paste the recipe’s text instead."
)
NO_RECIPE_IN_TEXT = (
    "Mealwright couldn’t find a recipe in that text. Paste its title, ingredients and method."
)
MEMBER_SWITCHED_OFF = "Importing from links is switched off. An admin can switch it on."
ALREADY = "You already have this recipe"


# --- The one box ------------------------------------------------------------------------------


def looks_like_link(text: str) -> bool:
    """A link is one word with no spaces that starts like a web address (or names another
    kind of address, such as ftp://). Anything with spaces or line breaks is recipe text."""
    if not text or any(c.isspace() for c in text):
        return False
    low = text.lower()
    return low.startswith(("http://", "https://", "www.")) or "://" in low


def _problem(why: FetchProblem, kitchen: Kitchen) -> Problem:
    """A refused fetch as the API's answer: the sentence, and a code the screen reacts to."""
    message = page_fetch.MESSAGES[why]
    if why in (FetchProblem.SWITCHED_OFF, FetchProblem.PHOTO_SWITCHED_OFF):
        admin = kitchen.login.role == "admin"
        if why == FetchProblem.SWITCHED_OFF and not admin:
            message = MEMBER_SWITCHED_OFF
        return Problem(status.HTTP_403_FORBIDDEN, why.value, message, admin=admin)
    return Problem(status.HTTP_422_UNPROCESSABLE_CONTENT, why.value, message)


@dataclass
class _Found:
    """What a page or the pasted text gave, in one shape."""

    name: str = ""
    description: str | None = None
    author: str | None = None
    time_minutes: int | None = None
    serves: int | None = None
    makes: tuple[Decimal, str] | None = None
    nutrition: dict[str, Decimal | None] = field(default_factory=dict)
    tags: tuple[str, ...] = ()
    photo_url: str | None = None
    lines: list[tuple[str, bool]] = field(default_factory=list)  # (text, is a heading)
    steps: list[tuple[str, bool]] = field(default_factory=list)
    lines_cut: bool = False
    steps_cut: bool = False
    left_out: list[LeftOutOut] = field(default_factory=list)


def _from_page(page: PageRecipe) -> _Found:
    return _Found(
        name=page.name,
        description=page.description,
        author=page.author,
        time_minutes=page.total_minutes,
        serves=page.serves,
        makes=page.makes,
        nutrition=dict(page.nutrition),
        tags=page.tags,
        photo_url=page.photo_url,
        lines=[(line.text, line.heading) for line in page.ingredients],
        steps=[(line.text, line.heading) for line in page.steps],
        lines_cut=page.lines_cut,
        steps_cut=page.steps_cut,
    )


def _now() -> float:
    """The clock the import's 30 seconds run on (a test can stand in for it)."""
    return time.monotonic()


def start(kitchen: Kitchen, gate: OutboundGate, text: str, again: bool = False) -> ImportReview:
    """Read a link or pasted text and answer with the review. Raises Problem."""
    text = text.strip()
    if not text:
        raise Problem(status.HTTP_422_UNPROCESSABLE_CONTENT, "nothing_given", NOTHING_GIVEN)
    # Nothing is held open while a page is fetched or read.
    kitchen.db.commit()
    began = _now()

    def left() -> float:
        return MAX_IMPORT_SECONDS - (_now() - began)

    if looks_like_link(text):
        link = text if "://" in text else f"https://{text}"
        return _from_link(kitchen, gate, link, again, left)
    return _from_text(kitchen, text)


# --- A link -----------------------------------------------------------------------------------


def _from_link(
    kitchen: Kitchen,
    gate: OutboundGate,
    link: str,
    again: bool,
    left: Left,
) -> ImportReview:
    try:
        tidy = page_fetch.tidy_link(link)
    except FetchRefused as refused:
        raise _problem(refused.problem, kitchen) from None
    # The switch comes before everything else, so a switched-off import tells nothing about
    # what the household already has.
    try:
        gate.check_switch(kitchen.household_id, Connection.RECIPE_IMPORT)
    except Exception:
        raise _problem(FetchProblem.SWITCHED_OFF, kitchen) from None
    if not again:
        _check_duplicate(kitchen, tidy)
    # The "already have it" check opened a read transaction: end it before the fetch, which can
    # take 30 seconds (a connection kept idle in a transaction, on a database that has them).
    kitchen.db.commit()
    try:
        fetched = page_fetch.fetch_page(gate, kitchen.household_id, tidy, seconds=left())
    except FetchRefused as refused:
        raise _problem(refused.problem, kitchen) from None
    except Exception as error:  # anything the fetch didn't expect
        # The connection's label and the kind of error only: the message and the traceback
        # could hold the address.
        log.warning("Couldn't fetch a page: %s, %s", LABELS[Connection.RECIPE_IMPORT], _kind(error))
        raise _problem(FetchProblem.CANT_REACH, kitchen) from None
    if not again and fetched.url != tidy:
        _check_duplicate(kitchen, fetched.url)
        kitchen.db.commit()  # and not held open while the page is read
    if left() < page_budget.MIN_READ_SECONDS:  # the fetch used the time the read needs
        raise _problem(FetchProblem.TIMEOUT, kitchen)
    page = _read(kitchen, fetched.html, fetched.url, left)
    if page is None:
        raise Problem(status.HTTP_422_UNPROCESSABLE_CONTENT, "no_recipe", NO_RECIPE_ON_PAGE)
    found = _from_page(page)
    held = _hold_photo(kitchen, gate, found.photo_url, left)
    return _review(
        kitchen, found, ReviewSource(kind="link", url=fetched.url, site=_site(fetched.url)), held
    )


def _read(kitchen: Kitchen, html: str, url: str, left: Left) -> PageRecipe | None:
    """Read a page within the work budget. Anything that goes wrong is the plain sentence,
    never a stack trace; the log has the connection's label and the kind of error only."""
    label = LABELS[Connection.RECIPE_IMPORT]
    try:
        # The wait for a place and the read both fit in what is left of the import's 30 seconds.
        return read_within_budget(html, url, within_seconds=max(0.0, left()))
    except PageBusy:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT, FetchProblem.BUSY.value, page_budget.BUSY
        ) from None
    except PageUnreadable:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            FetchProblem.CANT_READ.value,
            page_budget.CANT_READ,
        ) from None
    except Exception as error:  # anything the reader didn't expect
        log.warning("Couldn't read a page: %s, %s", label, _kind(error))
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            FetchProblem.CANT_READ.value,
            page_budget.CANT_READ,
        ) from None


def _kind(error: Exception) -> str:
    """The kind of an error for a log line: its type's name, never its message."""
    return type(error).__name__


def _site(url: str) -> str:
    from mealwright.recipes import site_of

    return site_of(url)


def _check_duplicate(kitchen: Kitchen, url: str) -> None:
    """409 if the household already has a recipe (not deleted) from this address."""
    found = kitchen.db.scalar(
        select(Recipe)
        .where(
            Recipe.household_id == kitchen.household_id,
            Recipe.removed_at.is_(None),
            Recipe.source_url == url,
        )
        .order_by(Recipe.id)
        .limit(1)
    )
    if found is None:
        return
    from mealwright.history import as_utc
    from mealwright.recipes import photo_out, site_of

    already = AlreadyImported(
        recipe=Ref(id=found.id, name=found.name),
        imported_at=as_utc(found.imported_at or found.created_at).isoformat(),
        site=site_of(url),
        photo=photo_out(kitchen.db, found.id),
    )
    raise Problem(
        status.HTTP_409_CONFLICT, "already_imported", ALREADY, **already.model_dump(mode="json")
    )


# --- The photo --------------------------------------------------------------------------------


def _hold_photo(kitchen: Kitchen, gate: OutboundGate, url: str | None, left: Left) -> ReviewPhoto:
    """Download the main photo (switch on) and hold it as a waiting photo until Save. A photo
    that can't be had never stops the import: the review says why."""
    from mealwright.recipes import photo_view

    if not gate.is_allowed(kitchen.household_id, Connection.RECIPE_PHOTOS):
        return ReviewPhoto(
            state="off", message=page_fetch.MESSAGES[FetchProblem.PHOTO_SWITCHED_OFF]
        )
    if url is None:
        return ReviewPhoto(state="none")
    if left() <= 0:  # the page used all of the import's 30 seconds
        return ReviewPhoto(state="failed", message=page_fetch.MESSAGES[FetchProblem.TIMEOUT])
    try:
        cleaned = page_fetch.download_photo(gate, kitchen.household_id, url, seconds=left())
    except FetchRefused as refused:
        if refused.problem == FetchProblem.PHOTO_SWITCHED_OFF:
            return ReviewPhoto(state="off", message=refused.message)
        return ReviewPhoto(state="failed", message=refused.message)
    except Exception as error:  # anything the download didn't expect: the photo only
        log.warning(
            "Couldn't fetch a photo: %s, %s", LABELS[Connection.RECIPE_PHOTOS], _kind(error)
        )
        return ReviewPhoto(state="failed", message=page_fetch.MESSAGES[FetchProblem.CANT_REACH])
    row = _store_waiting(kitchen, cleaned)
    if row is None:
        return ReviewPhoto(state="failed", message=photos.TOO_MANY_WAITING)
    return ReviewPhoto(state="downloaded", photo=photo_view(row))


def _store_waiting(kitchen: Kitchen, cleaned: Cleaned) -> RecipePhoto | None:
    """Keep a downloaded photo like an upload that no recipe has taken yet (10 at most per
    household). None if the household already has 10 waiting."""
    from sqlalchemy import func

    from mealwright.shopping import lock_household

    lock_household(kitchen)
    waiting = (
        kitchen.db.scalar(
            select(func.count())
            .select_from(RecipePhoto)
            .where(
                RecipePhoto.household_id == kitchen.household_id,
                RecipePhoto.recipe_id.is_(None),
                RecipePhoto.draft_id.is_(None),  # drafts' photos don't count (cabledrawer 22 Oct)
            )
        )
        or 0
    )
    if waiting >= MAX_WAITING:
        kitchen.db.rollback()
        return None
    store = photos.store_of(kitchen.db)
    key = photos.new_key()
    size = photos.write(store, kitchen.household_id, key, cleaned)
    row = RecipePhoto(
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
    kitchen.db.add(row)
    try:
        kitchen.db.commit()
    except Exception:
        photos.remove_files(store, kitchen.household_id, key)
        raise
    return row


# --- Pasted text ------------------------------------------------------------------------------


def _from_text(kitchen: Kitchen, text: str) -> ImportReview:
    try:
        pasted = read_pasted(text)
    except PastedTooLong as too_long:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "text_too_long", str(too_long)
        ) from None
    if not pasted.ingredients and not pasted.steps:
        raise Problem(status.HTTP_422_UNPROCESSABLE_CONTENT, "no_recipe", NO_RECIPE_IN_TEXT)
    found = _Found(
        name=pasted.name,
        lines=[(line, False) for line in pasted.ingredients],
        steps=[(step, False) for step in pasted.steps],
        lines_cut=pasted.lines_cut > 0,
        steps_cut=pasted.steps_cut > 0,
        left_out=[LeftOutOut(heading=left.heading, lines=left.lines) for left in pasted.left_out],
    )
    return _review(
        kitchen, found, ReviewSource(kind="text", url=None, site=None), ReviewPhoto(state="none")
    )


# --- The review -------------------------------------------------------------------------------


def _review(
    kitchen: Kitchen, found: _Found, source: ReviewSource, photo: ReviewPhoto
) -> ImportReview:
    ingredients = kitchen_of(kitchen.db, kitchen.household_id)
    places = _food_places(kitchen)
    lines: list[ReviewLine] = []
    counts = {"matched": 0, "to_confirm": 0, "needs_you": 0, "staple": 0}
    for text, heading in found.lines[:MAX_LINES]:
        line = _line(ingredients, places, text, heading)
        if line.label is not None:
            counts[line.label] += 1
        lines.append(line)
    steps: list[ReviewStep] = []
    shortened = 0
    for text, heading in found.steps[:MAX_STEPS]:
        limit = 200 if heading else MAX_STEP_CHARS
        if len(text) > limit:
            text = cut_text(text, limit).rstrip()
            shortened += 0 if heading else 1
        if text:
            steps.append(ReviewStep(kind="step" if not heading else "heading", text=text))
    return ImportReview(
        source=source,
        name=cut_text(found.name, 200).rstrip(),
        description=found.description,
        author=cut_text(found.author, 200).rstrip() if found.author else None,
        time_minutes=found.time_minutes,
        serves=found.serves,
        makes=_makes(found.makes),
        tags=list(found.tags),
        nutrition=_nutrition(found.nutrition),
        photo=photo,
        lines=lines,
        steps=steps,
        counts=ReviewCounts(**counts),
        lines_cut=found.lines_cut,
        steps_cut=found.steps_cut,
        steps_shortened=shortened,
        left_out=found.left_out,
    )


def _makes(makes: tuple[Decimal, str] | None) -> ReviewMakes | None:
    """What the page says it makes, in plain units. `MakesIn` checks it as Save will (and
    reads the amount in thousandths), so it is turned back into units here."""
    if makes is None:
        return None
    try:
        checked = MakesIn.model_validate({"amount": makes[0], "unit": makes[1]})
    except ValidationError:
        return None  # left out, never guessed
    if checked.amount is None:
        return None
    return ReviewMakes(amount=checked.amount / 1000, unit=checked.unit)


def _nutrition(values: dict[str, Decimal | None]) -> NutritionIn:
    try:
        return NutritionIn(**{k: v for k, v in values.items() if k in NutritionIn.model_fields})
    except ValidationError:
        return NutritionIn()


def _food_places(kitchen: Kitchen) -> dict[int, str]:
    """Ingredient id → the name of its usual place."""
    names = {
        place.id: place.name
        for place in kitchen.db.scalars(
            select(Place).where(Place.household_id == kitchen.household_id)
        )
    }
    return {
        food_id: names[place_id]
        for food_id, place_id in kitchen.db.execute(
            select(Food.id, Food.place_id).where(
                Food.household_id == kitchen.household_id, Food.place_id.is_not(None)
            )
        )
        if place_id in names
    }


def _line(
    ingredients: KnownIngredients, places: dict[int, str], text: str, heading: bool
) -> ReviewLine:
    written = cut_text(text, MAX_WRITTEN).rstrip()
    if heading:
        words = cut_text(" ".join(text.split()), MAX_WORDS).rstrip() or "Ingredients"
        return ReviewLine(
            kind="heading",
            written=written,
            words=words,
            amount=None,
            amount_text=None,
            unit=None,
            size=None,
            note=None,
            readable=True,
            label=None,
            food=None,
            place=None,
            matched_by=None,
            counts=False,
            new_ingredient=None,
            learn_name=None,
        )
    read = read_line(text, ingredients.size_words)
    match = match_line(ingredients, read)
    return _review_line(ingredients, places, written, read, match)


def _review_line(
    ingredients: KnownIngredients,
    places: dict[int, str],
    written: str,
    read: ReadLine,
    match: Match,
) -> ReviewLine:
    size = None
    if match.size_id is not None:
        for kept in ingredients.foods:
            for each in kept.sizes:
                if each.id == match.size_id:
                    size = SizeRef(id=each.id, name=each.name, plural=each.plural)
    amount_milli = None
    unit = read.unit
    note = read.note
    if read.readable:
        words = cut_text(read.name_as_written or read.name, MAX_WORDS).rstrip()
        if read.amount is not None:
            amount_milli = int(read.amount * 1000)
        if read.size_word and size is None:
            # A size word the ingredient has no size for ("a sprig", "1 bunch"): the count
            # would mean something else, so the amount goes in the note instead.
            said = " ".join(part for part in (amount_text(amount_milli), read.size_word) if part)
            note = ", ".join(part for part in (said, note) if part)
            amount_milli, unit = None, None
        if read.chosen:  # the amount was picked from several: keep the line as written
            note = f"as written: {working_text(read.text)}"
        if amount_milli is None:
            unit = None
    else:
        words = cut_text(working_text(read.text) or read.text, MAX_WORDS).rstrip()
        unit = None
    note = cut_text(note, MAX_NOTE).rstrip() if note else None
    food = None
    if match.food_id is not None and match.food_name is not None:
        food = Ref(id=match.food_id, name=match.food_name)
    guess = match.new_ingredient
    place = None
    if guess.place_id is not None:
        for home in ingredients.places:
            if home.id == guess.place_id:
                place = Ref(id=home.id, name=home.name)
    learn = read.name if read.readable else None
    return ReviewLine(
        kind="ingredient",
        written=written,
        words=words,
        amount=amount_milli / 1000 if amount_milli is not None else None,
        amount_text=amount_text(amount_milli),
        unit=unit,
        size=size,
        note=note,
        readable=read.readable,
        label=match.label,
        food=food,
        place=places.get(match.food_id)
        if match.label in ("matched", "staple") and match.food_id
        else None,
        matched_by=match.matched_by,
        counts=match.counts and size_ok(read, size),
        new_ingredient=NewIngredientOut(name=guess.name, counted_as=guess.counted_as, place=place),
        learn_name=cut_text(learn, 100).rstrip() if learn else None,
    )


def size_ok(read: ReadLine, size: SizeRef | None) -> bool:
    """A line with a size word counts only if the ingredient has that size."""
    return read.size_word is None or size is not None or read.unit is not None


# --- Save -------------------------------------------------------------------------------------


@dataclass
class Saved:
    recipe: Recipe
    change: Change
    new_foods: list[Food]
    learned: int


def _at(index: int, problem: Problem) -> Problem:
    problem.extra["line"] = index
    return problem


def _place(kitchen: Kitchen, place_id: int | None) -> int | None:
    if place_id is None:
        return None
    place = kitchen.db.get(Place, place_id)
    if place is None or place.household_id != kitchen.household_id:
        raise not_found("That place")
    return place.id


def save(kitchen: Kitchen, body: ImportSave) -> Saved:
    """Make the recipe, its new ingredients and staples, and the other names it learns, all in
    this one transaction (the caller holds the household's lock and commits). One change in
    Recent changes, `recipe_imported`, takes the whole save back."""
    from mealwright import recipes

    db = kitchen.db
    source = _source(body.source_url)
    # Saving from a draft: it must be this household's, there to see (else a plain 404, before
    # anything is made).
    draft = drafts.find(kitchen, body.draft_id) if body.draft_id is not None else None

    # What the lines link to, checked before anything is made.
    existing: dict[int, Food] = {}
    for index, line in enumerate(body.lines):
        link = line.link
        if line.kind == "heading" or link is None or link.kind != "ingredient":
            continue
        try:
            existing[link.food_id or 0] = find_food(kitchen, link.food_id or 0)
        except Problem as problem:
            raise _at(index, problem) from None

    with FoodEdit(kitchen, [food.id for food in existing.values()]) as edit:
        made: dict[str, Food] = {}  # folded name → the ingredient made for it
        for index, line in enumerate(body.lines):
            link = line.link
            if line.kind == "heading" or link is None or link.kind == "ingredient":
                continue
            key = fold(link.name or "")
            if key in made:
                continue
            owner = name_owner(kitchen, link.name or "")
            if owner is not None:
                raise _at(index, name_taken(link.name or "", owner))
            try:
                place_id = _place(kitchen, link.place_id)
            except Problem as problem:
                raise _at(index, problem) from None
            row = table().match(link.name or "")
            food = Food(
                household_id=kitchen.household_id,
                name=link.name or "",
                counted_as=link.counted_as or (row.counted_as if row else "weight"),
                staple=link.kind == "staple",
                place_id=place_id,
                aisle=row.aisle if row and row.aisle else DEFAULT_AISLE,
                table_key=row.key if row else None,
            )
            db.add(food)
            db.flush()
            edit.also(food.id)
            made[key] = food

        learned = _learn(kitchen, body, existing)
        recipe_lines = []
        for line in body.lines:
            link = line.link
            food_id: int | None = None
            if line.kind != "heading" and link is not None:
                food_id = (
                    link.food_id if link.kind == "ingredient" else made[fold(link.name or "")].id
                )
            recipe_lines.append(
                {
                    "kind": line.kind,
                    "words": line.words,
                    "amount": None if line.amount is None else Decimal(line.amount) / 1000,
                    "unit": line.unit,
                    "size_id": line.size_id if food_id is not None else None,
                    "food_id": food_id,
                    "note": line.note,
                }
            )
        try:
            recipe_in = RecipeIn.model_validate(
                {
                    "name": body.name,
                    "description": body.description,
                    "time_minutes": body.time_minutes,
                    "serves": body.serves,
                    "makes": (
                        None
                        if body.makes is None
                        else {
                            "amount": Decimal(body.makes.amount or 0) / 1000,
                            "unit": body.makes.unit,
                        }
                    ),
                    "tags": body.tags,
                    "nutrition": body.nutrition.model_dump(),
                    "lines": recipe_lines,
                    "steps": [step.model_dump() for step in body.steps],
                    **({"photo_id": body.photo_id} if body.photo_id is not None else {}),
                }
            )
        except ValidationError as invalid:
            raise _invalid(invalid) from None
        taken: int | None = None  # the draft's photo that becomes the recipe's
        if draft is not None and body.photo_id is not None:
            # The draft's photo becomes the recipe's (nothing else takes a draft's photo).
            kept = db.get(RecipePhoto, body.photo_id)
            if kept is not None and kept.draft_id == draft.id:
                kept.draft_id = None
                taken = kept.id
                db.flush()
        recipe = recipes.save(kitchen, None, recipe_in, remember_key=False)
        recipe.source_url = source
        recipe.imported_at = utcnow()
        recipe.source_author = _author(body.source_author)
        db.flush()
        if draft is not None:
            # What Undo needs to bring the draft back (cabledrawer 24 Oct, question 36): kept in
            # this change's own record, so there is nothing else to store.
            edit.extra["draft"] = drafts.snapshot(draft, taken)
            drafts.delete_for_good(db, [draft.id])  # it is a recipe now
        edit.extra["recipe_id"] = recipe.id
        new_foods = list(made.values())
        change = edit.record("recipe_imported", _summary(recipe, new_foods, learned), None)
    return Saved(recipe=recipe, change=change, new_foods=new_foods, learned=learned)


def _summary(recipe: Recipe, new_foods: list[Food], learned: int) -> str:
    parts = []
    if new_foods:
        parts.append(f"{len(new_foods)} new ingredient{'' if len(new_foods) == 1 else 's'}")
    if learned:
        parts.append(f"{learned} other name{'' if learned == 1 else 's'}")
    return f"Imported {recipe.name}" + (f", with {' and '.join(parts)}" if parts else "")


def _source(url: str | None) -> str | None:
    """The web address to keep: a link as it's requested (http or https, nothing else)."""
    if not url or not url.strip():
        return None
    try:
        return page_fetch.tidy_link(url)
    except FetchRefused:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "bad_source",
            page_fetch.MESSAGES[FetchProblem.BAD_LINK],
        ) from None


def _author(name: str | None) -> str | None:
    if not name:
        return None
    return cut_text(" ".join(working_text(name).split()), 200).rstrip() or None


def _invalid(error: ValidationError) -> Problem:
    """A recipe the server won't take: the first thing wrong, in plain words (as the editor's
    own save would say), and which line or step it is."""
    first = error.errors()[0]
    where = [part for part in first["loc"]]
    detail = str(first["msg"]).removeprefix("Value error, ")
    extra: dict[str, object] = {}
    if len(where) >= 2 and where[0] == "lines" and isinstance(where[1], int):
        extra["line"] = where[1]
    if len(where) >= 2 and where[0] == "steps" and isinstance(where[1], int):
        extra["step"] = where[1]
    return Problem(status.HTTP_422_UNPROCESSABLE_CONTENT, "invalid_recipe", detail, **extra)


def _learn(
    kitchen: Kitchen,
    body: ImportSave,
    existing: dict[int, Food],
) -> int:
    """Add the names "Same as …" taught as other names of the ingredients they were chosen
    for. A name the ingredient (or any other) already has is skipped, never stolen."""
    db = kitchen.db
    taken: set[str] = set()
    for food in db.scalars(
        select(Food).where(
            Food.household_id == kitchen.household_id,
            Food.removed_at.is_(None),
            Food.merged_into_id.is_(None),
        )
    ):
        taken.add(fold(food.name))
    for row in db.scalars(select(FoodName).where(FoodName.household_id == kitchen.household_id)):
        taken.add(fold(row.name))
    learned = 0
    for line in body.lines:
        link = line.link
        if line.kind == "heading" or link is None or link.kind != "ingredient" or not link.learn:
            continue
        food = existing[link.food_id or 0]
        key = fold(link.learn)
        if key in taken or not key:
            continue
        taken.add(key)
        db.add(FoodName(household_id=kitchen.household_id, food_id=food.id, name=link.learn))
        db.flush()
        refresh_table_key(kitchen, food)
        learned += 1
    return learned
