"""Reading a Mealie backup file (cabledrawer 13 Nov: "Mealie importer is file only (Mealie's export
zip; never a network fetch)").

What it reads, and what it assumes about Mealie's layout, is in docs/dev/recipe-import.md,
"Import from Mealie" (proposed, for cabledrawer: written from Mealie's own export code, not from a
real file). In short: a zip with `database.json` at the top (each of Mealie's database tables,
by name, as a list of rows) and the recipe photos at `data/recipes/<recipe id>/images/`.

The file is someone else's, so it is read as if it could be hostile:

- **Nothing is unpacked.** The zip is our own stored copy of the upload (the caller's path);
  members are read by name into memory, never written out, and no name from the zip is ever
  used as a path on disk.
- **Sizes:** at most `MAX_MEMBERS` members, `MAX_TOTAL_BYTES` unpacked in all (as the zip says),
  `MAX_DATABASE_BYTES` for `database.json` and `MAX_PHOTO_BYTES` for each photo (the photo
  upload's own limit). Every read stops at its limit whatever the zip claims, so a zip bomb
  is cut off, not unpacked. Only "stored" and "deflated" members are read, never encrypted
  ones.
- **The JSON** is at most `MAX_DATABASE_BYTES` and nested at most `MAX_JSON_DEPTH` deep, and
  only the columns listed here are taken, each only when it has the expected type (a row or
  value of the wrong type is skipped).
- **A work budget:** the zip's index and `database.json` are read in a short-lived child
  process with its own processor-time, clock and memory limits and the network guard on,
  exactly like the recipe page reader (`page_budget`), but with a bigger budget: a whole
  Mealie file is far bigger than one page. One file is read at a time for the whole server.
- **Photos** are read one at a time by the caller (`MealiePhotos`), only after the child has
  checked the file, and cleaned exactly like an upload (`photos.clean`): nothing of the
  original file is kept.

Nothing here connects to anything, and nothing touches the database.
"""

import contextlib
import json
import logging
import multiprocessing
import re
import threading
import time
import zipfile
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from multiprocessing.connection import Connection
from pathlib import Path
from typing import TYPE_CHECKING

from mealwright import page_reader
from mealwright.page_reader import PageLine, PageRecipe

if TYPE_CHECKING:  # photos brings Pillow and the database code; the child needs neither
    from mealwright.photos import Cleaned

log = logging.getLogger(__name__)

# Limits (proposed, for cabledrawer 13 Nov: no real Mealie file to measure yet).
MAX_FILE_BYTES = 1024 * 1024 * 1024  # the upload itself (photos make most of it)
MAX_MEMBERS = 50_000  # files in the zip (Mealie keeps 3 copies of each photo)
MAX_TOTAL_BYTES = 4 * 1024 * 1024 * 1024  # everything in the zip, unpacked, as it says
MAX_DATABASE_BYTES = 32 * 1024 * 1024  # database.json, unpacked
MAX_PHOTO_BYTES = 15 * 1024 * 1024  # one photo: the photo upload's own limit (limits.py)
MAX_JSON_DEPTH = 16  # a Mealie row is 3 deep (file, table, row) plus a few for JSON columns
MAX_RECIPES = 5_000
MAX_FOODS = 20_000
# All the recipes together, as the reader hands them back (proposed, for cabledrawer; round 1,
# S-M5): the reader's own memory limit doesn't cover the copy the server keeps for the whole
# import, so a small file that names one long ingredient a million times is refused instead.
# A big real Mealie backup (5,000 recipes of 15 lines and 10 steps) is about 125,000 lines.
MAX_BOOK_LINES = 250_000
MAX_BOOK_TEXT = 24_000_000  # UTF-8 bytes: memory goes by bytes (round 2, S3)
MAX_TAGS = page_reader.MAX_TAGS

# The child's budget. Reading database.json for a few hundred recipes is well under a second
# on a fast PC; the limits leave room for a big file on a small board.
MAX_CPU_SECONDS = 60.0
MAX_WALL_SECONDS = 90.0
MAX_MEMORY = 768 * 1024 * 1024
MAX_WAIT_SECONDS = 60.0
_EXIT_SECONDS = 2.0
_one_at_a_time = threading.BoundedSemaphore(1)
_spawn = multiprocessing.get_context("spawn")

DATABASE = "database.json"
_READABLE = (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED)
_PHOTO = re.compile(
    r"^data/recipes/([0-9A-Fa-f-]{32,36})/images/original\.(?:webp|jpe?g|png)$", re.ASCII
)
_KEY = re.compile(r"^[0-9a-z_]{1,64}$", re.ASCII)

# What isn't brought in (cabledrawer 13 Nov), counted for the preview: Mealie's table names.
LEFT_OUT_TABLES = {
    "meal_plans": "group_meal_plans",
    "shopping_lists": "shopping_lists",
    "users": "users",
    "cookbooks": "cookbooks",
}

# Words (proposed, for cabledrawer 13 Nov; docs/dev/words.md section 81).
MESSAGES = {
    "not_zip": "That isn't a Mealie backup file. Choose the .zip file Mealie made.",
    "not_mealie": "That isn't a Mealie backup file. Choose the .zip file Mealie made.",
    "too_big": "That Mealie file is too big for Mealwright to read.",
    "too_many": f"That file has more than {MAX_RECIPES:,} recipes. Mealwright can't read it.",
    "unreadable": "Mealwright couldn't read that Mealie file. Try making a new backup in Mealie.",
    "busy": "Mealwright is busy reading another Mealie file. Try again in a moment.",
}


class MealieFileProblem(Exception):
    """The file can't be read. `reason` is a key of MESSAGES; `message` is the sentence a
    screen shows."""

    def __init__(self, reason: str) -> None:
        super().__init__(MESSAGES[reason])
        self.reason = reason
        self.message = MESSAGES[reason]


@dataclass(frozen=True)
class MealieFood:
    key: str  # Mealie's id, lower case, no dashes
    name: str


@dataclass(frozen=True)
class MealieRecipe:
    key: str  # Mealie's id, lower case, no dashes
    page: PageRecipe  # what the recipe says, in the page reader's shape (photo_url is None)
    source: str | None  # Mealie's "original URL", if any
    foods: tuple[str, ...]  # keys of the Mealie foods its ingredient lines use
    photo: str | None  # the zip member with its photo
    photo_bytes: int  # that photo's size as the zip says (0 without one)


@dataclass(frozen=True)
class MealieBook:
    recipes: tuple[MealieRecipe, ...]
    foods: tuple[MealieFood, ...]  # only the ones some recipe uses
    left_out: dict[str, int]  # meal_plans, shopping_lists, users, cookbooks: how many


# --- Reading, in a child process ------------------------------------------------------------


def read_file(
    path: Path,
    *,
    cpu_seconds: float = MAX_CPU_SECONDS,
    wall_seconds: float = MAX_WALL_SECONDS,
    memory: int = MAX_MEMORY,
    wait_seconds: float = MAX_WAIT_SECONDS,
) -> MealieBook:
    """Read the Mealie backup zip at `path` (our own stored copy) within the budget. Raises
    MealieFileProblem."""
    if path.stat().st_size > MAX_FILE_BYTES:
        raise MealieFileProblem("too_big")
    if not _one_at_a_time.acquire(timeout=max(0.0, wait_seconds)):
        raise MealieFileProblem("busy")
    try:
        return _in_child(str(path), cpu_seconds, wall_seconds, memory)
    finally:
        _one_at_a_time.release()


def _in_child(path: str, cpu_seconds: float, wall_seconds: float, memory: int) -> MealieBook:
    deadline = time.monotonic() + wall_seconds
    receive, send = _spawn.Pipe(duplex=False)
    child = _spawn.Process(
        target=_child, args=(send, path, cpu_seconds, memory), name="mealie reader", daemon=True
    )
    answer: tuple[str, object] | None = None
    try:
        child.start()
        send.close()
        if receive.poll(max(0.0, deadline - time.monotonic())):
            try:
                answer = receive.recv()
            except EOFError, OSError:
                answer = None
            except Exception:
                answer = ("failed", None)
    finally:
        if child.pid is not None:
            if answer is not None:
                child.join(max(0.0, min(_EXIT_SECONDS, deadline - time.monotonic())))
            if child.is_alive():
                child.kill()
                child.join()
            child.close()
        receive.close()
        send.close()
    if answer is None:
        log.warning("Couldn't read a Mealie file: over its time limit or the reader stopped")
        raise MealieFileProblem("unreadable")
    kind, value = answer
    if kind == "memory":
        log.warning("Couldn't read a Mealie file: over its memory limit")
        raise MealieFileProblem("too_big")
    if kind == "problem" and isinstance(value, str) and value in MESSAGES:
        raise MealieFileProblem(value)
    if kind == "read" and isinstance(value, MealieBook):
        return value
    log.warning("Couldn't read a Mealie file: the reader stopped")
    raise MealieFileProblem("unreadable")


def _child(send: Connection, path: str, cpu_seconds: float, memory: int) -> None:
    from mealwright.page_budget import _prepare_child

    _prepare_child(cpu_seconds, memory)
    answer: tuple[str, object]
    try:
        answer = ("read", read_now(Path(path)))
    except MealieFileProblem as problem:
        answer = ("problem", problem.reason)
    except MemoryError:
        answer = ("memory", None)
    except Exception:  # anything else the file causes is an unreadable file, nothing more
        answer = ("problem", "unreadable")
    try:
        send.send(answer)
    except Exception:
        with contextlib.suppress(Exception):
            send.send(("failed", None))
    send.close()


def read_now(path: Path) -> MealieBook:
    """The reading itself, in this process, without the budget (the child's work; tests use
    it directly)."""
    try:
        with zipfile.ZipFile(path) as zipped:
            members = zipped.infolist()
            if len(members) > MAX_MEMBERS:
                raise MealieFileProblem("too_big")
            if sum(m.file_size for m in members) > MAX_TOTAL_BYTES:
                raise MealieFileProblem("too_big")
            found = [m for m in members if m.filename == DATABASE]
            if len(found) != 1 or not _readable(found[0]):
                raise MealieFileProblem("not_mealie")
            if found[0].file_size > MAX_DATABASE_BYTES:
                raise MealieFileProblem("too_big")
            raw = read_member(zipped, found[0], MAX_DATABASE_BYTES)
            photos = _photos(members)
    except zipfile.BadZipFile, zipfile.LargeZipFile, EOFError, NotImplementedError:
        raise MealieFileProblem("not_zip") from None
    if raw is None:
        raise MealieFileProblem("too_big")
    try:
        tables = json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError, ValueError, RecursionError:
        raise MealieFileProblem("not_mealie") from None
    del raw
    if not isinstance(tables, dict) or not _shallow(tables):
        raise MealieFileProblem("not_mealie")
    return _book(tables, photos)


def _readable(member: zipfile.ZipInfo) -> bool:
    return not member.flag_bits & 0x1 and member.compress_type in _READABLE


def read_member(zipped: zipfile.ZipFile, member: zipfile.ZipInfo, limit: int) -> bytes | None:
    """The member's bytes, or None if it unpacks to more than `limit` (whatever the zip says
    its size is): the read stops there, so a zip bomb is never unpacked."""
    chunks: list[bytes] = []
    total = 0
    with zipped.open(member) as stream:
        while True:
            chunk = stream.read(min(1024 * 1024, limit + 1 - total))
            if not chunk:
                break
            total += len(chunk)
            if total > limit:
                return None
            chunks.append(chunk)
    return b"".join(chunks)


def _shallow(value: object) -> bool:
    """Nested at most MAX_JSON_DEPTH deep (checked without recursion)."""
    stack: list[tuple[object, int]] = [(value, 1)]
    while stack:
        item, depth = stack.pop()
        if depth > MAX_JSON_DEPTH:
            return False
        if isinstance(item, dict):
            stack.extend((v, depth + 1) for v in item.values() if isinstance(v, (dict, list)))
        elif isinstance(item, list):
            stack.extend((v, depth + 1) for v in item if isinstance(v, (dict, list)))
    return True


def _photos(members: list[zipfile.ZipInfo]) -> dict[str, tuple[str, int]]:
    """Recipe key -> (member name, size), for photos that can be read within the limit."""
    found: dict[str, tuple[str, int]] = {}
    names: dict[str, int] = {}
    for member in members:
        names[member.filename] = names.get(member.filename, 0) + 1
    for member in members:
        match = _PHOTO.match(member.filename)
        if match is None or names[member.filename] != 1 or not _readable(member):
            continue
        if member.file_size > MAX_PHOTO_BYTES:
            continue
        key = _key(match.group(1))
        if key is not None and key not in found:
            found[key] = (member.filename, member.file_size)
    return found


# --- Mealie's tables --------------------------------------------------------------------------


def _rows(tables: dict[str, object], name: str) -> list[dict[str, object]]:
    rows = tables.get(name)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _key(value: object) -> str | None:
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    text = str(value).strip().lower().replace("-", "")
    return text if _KEY.match(text) else None


def _text(value: object, limit: int = page_reader.MAX_LINE_TEXT) -> str:
    if not isinstance(value, str):
        return ""
    return page_reader._cut(page_reader._one_line(value[: limit * 4]), limit)


def _number(value: object) -> Decimal | None:
    if isinstance(value, bool) or not isinstance(value, (int, float, str)):
        return None
    try:
        number = Decimal(str(value).strip()[: page_reader.MAX_NUMBER_TEXT])
    except InvalidOperation:
        return None
    return number if number.is_finite() else None


def _position(row: dict[str, object]) -> int:
    value = row.get("position")
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _book(tables: dict[str, object], photos: dict[str, tuple[str, int]]) -> MealieBook:
    if not isinstance(tables.get("recipes"), list):
        raise MealieFileProblem("not_mealie")
    recipe_rows = _rows(tables, "recipes")
    if len(recipe_rows) > MAX_RECIPES:
        raise MealieFileProblem("too_many")
    foods = {
        key: name
        for row in _rows(tables, "ingredient_foods")[:MAX_FOODS]
        if (key := _key(row.get("id"))) and (name := _text(row.get("name"), 100))
    }
    units = {
        key: name
        for row in _rows(tables, "ingredient_units")
        if (key := _key(row.get("id"))) and (name := _unit_name(row))
    }
    tags = {
        key: name
        for row in _rows(tables, "tags")
        if (key := _key(row.get("id"))) and (name := _text(row.get("name"), 40))
    }
    lines: dict[str, list[dict[str, object]]] = {}
    for row in _rows(tables, "recipes_ingredients"):
        if key := _key(row.get("recipe_id")):
            lines.setdefault(key, []).append(row)
    steps: dict[str, list[dict[str, object]]] = {}
    for row in _rows(tables, "recipe_instructions"):
        if key := _key(row.get("recipe_id")):
            steps.setdefault(key, []).append(row)
    nutrition: dict[str, dict[str, object]] = {}
    for row in _rows(tables, "recipe_nutrition"):
        if key := _key(row.get("recipe_id")):
            nutrition.setdefault(key, row)
    tagged: dict[str, list[str]] = {}
    for row in _rows(tables, "recipes_to_tags"):
        owner, tag = _key(row.get("recipe_id")), _key(row.get("tag_id"))
        if owner and tag in tags:
            tagged.setdefault(owner, []).append(tags[tag])
    recipes: list[MealieRecipe] = []
    used: set[str] = set()
    seen: set[str] = set()
    lines_left, text_left = MAX_BOOK_LINES, MAX_BOOK_TEXT
    for row in recipe_rows:
        key = _key(row.get("id"))
        if key is None or key in seen:
            continue
        seen.add(key)
        recipe = _recipe(
            key, row, lines.get(key, []), steps.get(key, []), nutrition.get(key, {}),
            tagged.get(key, []), foods, units, photos.get(key),
        )  # fmt: skip
        page = recipe.page
        lines_left -= len(page.ingredients) + len(page.steps)
        text_left -= (
            _bytes(page.name)
            + _bytes(page.description or "")
            + sum(_bytes(line.text) for line in (*page.ingredients, *page.steps))
            + sum(_bytes(tag) for tag in page.tags)
            + _bytes(recipe.source or "")
        )
        if lines_left < 0 or text_left < 0:
            raise MealieFileProblem("too_big")
        used.update(recipe.foods)
        recipes.append(recipe)
    left_out = {
        word: len(rows) if isinstance(rows := tables.get(table), list) else 0
        for word, table in LEFT_OUT_TABLES.items()
    }
    return MealieBook(
        recipes=tuple(recipes),
        foods=tuple(MealieFood(key, name) for key, name in foods.items() if key in used),
        left_out=left_out,
    )


def _bytes(text: str) -> int:
    return len(text.encode("utf-8"))


def _unit_name(row: dict[str, object]) -> str:
    short = _text(row.get("abbreviation"), 30)
    if row.get("use_abbreviation") is True and short:
        return short
    return _text(row.get("name"), 30) or short


def _recipe(
    key: str,
    row: dict[str, object],
    line_rows: list[dict[str, object]],
    step_rows: list[dict[str, object]],
    facts: dict[str, object],
    tags: list[str],
    foods: dict[str, str],
    units: dict[str, str],
    photo: tuple[str, int] | None,
) -> MealieRecipe:
    # A recipe with no name is still brought in: it waits in Drafts as "Untitled recipe"
    # (drafts.NO_NAME), never dropped without a word (round 1, review 6).
    name = _text(row.get("name"), page_reader.MAX_NAME)
    ingredients: list[PageLine] = []
    named: list[str | None] = []  # the Mealie food of each entry of `ingredients`, if any
    for line in sorted(line_rows, key=_position):
        if (title := _text(line.get("title"), page_reader.MAX_HEADING)) != "":
            ingredients.append(PageLine(text=title, heading=True))
            named.append(None)
        text, food = _ingredient(line, foods, units)
        if text:
            ingredients.append(PageLine(text=text, heading=False))
            named.append(food)
    # Only the foods of the lines that are kept, once each, in order (round 2, S2: no list
    # searched for every line, and not the foods of lines cut off below).
    used = dict.fromkeys(food for food in named[: page_reader.MAX_LINES] if food)
    steps: list[PageLine] = []
    for step in sorted(step_rows, key=_position):
        if (title := _text(step.get("title"), page_reader.MAX_HEADING)) != "":
            steps.append(PageLine(text=title, heading=True))
        if text := _text(step.get("text")):
            steps.append(PageLine(text=text, heading=False))
    serves, makes = _yield(row)
    description = _text(row.get("description"), page_reader.MAX_DESCRIPTION) or None
    page = PageRecipe(
        name=name,
        description=description,
        author=None,  # Mealie's user is a person in someone else's app: never brought in
        total_minutes=_total_minutes(row),
        serves=serves,
        makes=makes,
        nutrition={
            ours: page_reader._nutrient(facts.get(theirs), energy=ours == "kcal")
            for ours, theirs in _NUTRITION.items()
        },
        tags=tuple(dict.fromkeys(tags))[:MAX_TAGS],
        photo_url=None,
        ingredients=tuple(ingredients[: page_reader.MAX_LINES]),
        steps=tuple(steps[: page_reader.MAX_STEPS]),
        lines_cut=len(ingredients) > page_reader.MAX_LINES,
        steps_cut=len(steps) > page_reader.MAX_STEPS,
    )
    source = row.get("org_url")
    return MealieRecipe(
        key=key,
        page=page,
        source=source.strip()[:2000] if isinstance(source, str) and source.strip() else None,
        foods=tuple(used),
        photo=photo[0] if photo else None,
        photo_bytes=photo[1] if photo else 0,
    )


_NUTRITION = {
    "kcal": "calories",
    "protein": "protein_content",
    "carbs": "carbohydrate_content",
    "fat": "fat_content",
    "fibre": "fiber_content",
}


def _ingredient(
    line: dict[str, object], foods: dict[str, str], units: dict[str, str]
) -> tuple[str, str | None]:
    """The line as text ("200 g flour, sifted") and the key of its Mealie food, if any. A
    line with a food or unit is put together from its parts; otherwise its note, or the text
    it was first typed as."""
    food = _key(line.get("food_id"))
    food = food if food in foods else None
    unit = _key(line.get("unit_id"))
    unit_name = units.get(unit) if unit else None
    note = _text(line.get("note"))
    if food or unit_name:
        parts: list[str] = []
        amount = _number(line.get("quantity"))
        if amount is not None and 0 < amount <= 1_000_000:
            parts.append(_amount_text(amount))
        if unit_name:
            parts.append(unit_name)
        if food:
            parts.append(foods[food])
        text = " ".join(parts)
        if note:
            text = f"{text}, {note}"
        return page_reader._cut(text, page_reader.MAX_LINE_TEXT), food
    return note or _text(line.get("original_text")), None


def _amount_text(amount: Decimal) -> str:
    rounded = amount.quantize(Decimal("0.001"))
    text = format(rounded.normalize(), "f")
    return text


def _yield(row: dict[str, object]) -> tuple[int | None, tuple[Decimal, str] | None]:
    servings = _number(row.get("recipe_servings"))
    serves: int | None = None
    if servings is not None and servings == servings.to_integral_value():
        serves = int(servings) if 1 <= servings <= page_reader.MAX_SERVES else None
    text = _text(row.get("recipe_yield"), 100)
    quantity = _number(row.get("recipe_yield_quantity"))
    if text and quantity is not None and 0 < quantity <= 1_000_000 and not text[:1].isdigit():
        text = f"{_amount_text(quantity)} {text}"
    if not text:
        return serves, None
    read_serves, makes = page_reader._yield(page_reader._Recipe({"recipeYield": text}, {}))
    return serves or read_serves, makes


_WORD_TIME = re.compile(
    r"(\d{1,6}(?:[.,]\d{1,3})?)\s*(days?|d|hours?|hrs?|hr|h|minutes?|mins?|m)\b", re.IGNORECASE
)
_WORD_JOINS = re.compile(r"^(?:\s|,|and|&)*$", re.IGNORECASE)
_WORD_MINUTES = {"d": 1440, "h": 60, "m": 1}


def minutes(value: object) -> int | None:
    """Mealie's times are typed in by hand: "PT1H30M", "45", "1 hour 30 minutes", "1h 30m"."""
    found = page_reader._minutes(value)
    if found is not None or not isinstance(value, str) or len(value) > 100:
        return found
    total = Decimal(0)
    end = 0
    for match in _WORD_TIME.finditer(value):
        if not _WORD_JOINS.match(value[end : match.start()]):
            return None
        size = _WORD_MINUTES[match.group(2)[0].lower()]
        total += Decimal(match.group(1).replace(",", ".")) * size
        end = match.end()
    if end == 0 or not _WORD_JOINS.match(value[end:]):
        return None
    result = int(total.to_integral_value())
    return result if 0 < result <= page_reader.MAX_MINUTES else None


def _total_minutes(row: dict[str, object]) -> int | None:
    total = minutes(row.get("total_time"))
    if total is not None:
        return total
    cook = minutes(row.get("perform_time")) or minutes(row.get("cook_time"))
    parts = [m for m in (minutes(row.get("prep_time")), cook) if m]
    if not parts or sum(parts) > page_reader.MAX_MINUTES:
        return None
    return sum(parts)


# --- Photos -------------------------------------------------------------------------------------


class MealiePhotos:
    """The photos of a file `read_file` has already checked, read one at a time:

    with MealiePhotos(path) as photos:
        cleaned = photos.cleaned(recipe.photo)
    """

    def __init__(self, path: Path) -> None:
        self._zip = zipfile.ZipFile(path)

    def __enter__(self) -> MealiePhotos:
        return self

    def __exit__(self, *_: object) -> None:
        self._zip.close()

    def raw(self, member: str) -> bytes | None:
        if _PHOTO.match(member) is None:
            return None
        try:
            info = self._zip.getinfo(member)
            if not _readable(info) or info.file_size > MAX_PHOTO_BYTES:
                return None
            return read_member(self._zip, info, MAX_PHOTO_BYTES)
        except KeyError, zipfile.BadZipFile, EOFError, NotImplementedError, OSError:
            return None

    def cleaned(self, member: str | None) -> Cleaned | None:
        """The photo cleaned exactly like an upload (`photos.clean`), or None if there is
        none or it isn't a photo Mealwright can use."""
        from mealwright import photos

        data = self.raw(member) if member else None
        if data is None:
            return None
        try:
            return photos.clean(data)
        except photos.NotAPhoto, photos.TooManyPixels:
            return None
