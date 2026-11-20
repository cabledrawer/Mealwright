"""Fixing Mealie drafts by ingredient (spec section 6, "Fixing Mealie drafts by ingredient",
cabledrawer 15 Nov, 0.9.5-beta.2).

The lines of the household's Mealie drafts that nobody has answered are grouped by the
ingredient they name, across every draft, most-used first. One answer for a group (an
ingredient the household has, a new one with its pantry place, or plain text) goes into every
draft that uses it, in one change with one Undo (7 days). The answers are written on the drafts
at once; the drafts they complete are then saved, and brought back by Undo, in short locked
stretches (the time budget of Save all), the change recording each stretch as it is done.
A draft whose lines are all answered is saved as a recipe and leaves Drafts; it joins its
import's results, so the import's own Undo
still takes it out. Nothing is saved until the person answers; "Skip for now" is only the
screen's: the server keeps nothing for it.

How a group is told apart: by the name as read (`learn_name`, else `words`, else the line as
written), keyed the way matching keys names (`ingredient_match._key`: case, accents, brackets
and plurals folded, so egg and eggs, chilli and chillies are one group). An unanswered line is an
ingredient line with a name that has no choice and is not matched or a staple (the same test
`drafts._progress` makes). The grouping reads each draft's stored JSON once, with no query per
draft (about 700 drafts must stay quick).

Proposed, for cabledrawer (the spec doesn't say; the safest reading, listed in the PR):

- A draft the person had already changed on the review screen (a new ingredient, a staple or
  another recipe chosen on a line, or the name, serves, minutes or pints changed) is not saved
  by an answer: its lines are answered, but it stays in Drafts for the review screen's Save, so
  nothing the person chose is lost.
- "An ingredient I have" ties the lines to it and does not teach it the line's words as another
  name; "plain text" is the review's "Made in this recipe" (words only).
- A new ingredient whose name the household already has is that ingredient (nothing is made
  twice, and Undo leaves it alone).
- A new ingredient made here is marked "from Mealie" with the draft's import, so that import's
  Undo handles it like the others.
- The answer counts as a change to each draft it goes into: its 15 days start again.
- Undo takes a saved recipe back to Drafts unless it was changed, cooked or planned since (then
  it stays, and the message says so), as the import's Undo does.
"""

import base64
import json
import logging
import time
import zlib
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select

from mealwright import drafts
from mealwright.api.v1.context import Kitchen
from mealwright.api.v1.draft_schemas import DraftChoice, DraftChoices
from mealwright.api.v1.group_schemas import GroupAnswer, IngredientGroup, IngredientGroups
from mealwright.api.v1.import_schemas import ImportReview
from mealwright.api.v1.schemas import Ref
from mealwright.conversions import guess_aisle, table
from mealwright.errors import not_found
from mealwright.foods import shop_choices
from mealwright.history import already_undone, record
from mealwright.ingredient_match import _key
from mealwright.models import (
    Change,
    Food,
    ImportDraft,
    MealieImport,
    Place,
    Recipe,
    RecipePhoto,
    as_utc,
    utcnow,
)
from mealwright.names import cut_text, fold
from mealwright.pack_sizes import usual_shop_id

log = logging.getLogger(__name__)

KIND = "mealie_drafts_answered"  # listed in `change_kinds.RECIPES`
SUGGEST_FOR = 40  # the first groups get a fresh look at the household's ingredients
EXAMPLES = 2
EXAMPLE_CHARS = 100
LIST_LIMIT = 50  # groups shown before "Show all"
MAX_LIMIT = 5_000
READY_STATES = ("saved", "saved_all", "answered")


# --- Reading a draft's stored lines ------------------------------------------------------------


def _name_key(line: dict[str, Any]) -> tuple[str, str]:
    """(key, name) of a line's ingredient as read."""
    name = str(line.get("learn_name") or line.get("words") or line.get("written") or "").strip()
    return _key(name)[:300], name[:100]


def _many(count: int, word: str) -> str:
    """ "1 draft", "3 drafts"."""
    return f"{count} {word}{'' if count == 1 else 's'}"


def _food_id(value: Any) -> int | None:
    return value.get("id") if isinstance(value, dict) and isinstance(value.get("id"), int) else None


def _lines_of(draft: ImportDraft) -> list[Any]:
    lines = draft.review.get("lines") if isinstance(draft.review, dict) else None
    return lines if isinstance(lines, list) else []


def _choices_of(draft: ImportDraft) -> dict[int, dict[str, Any]]:
    raw = draft.choices.get("lines") if isinstance(draft.choices, dict) else None
    out: dict[int, dict[str, Any]] = {}
    for key, value in (raw if isinstance(raw, dict) else {}).items():
        try:
            if isinstance(value, dict):
                out[int(key)] = value
        except ValueError:
            continue
    return out


def _foods_used(rows: list[ImportDraft]) -> set[int]:
    ids: set[int] = set()
    for draft in rows:
        for line in _lines_of(draft):
            if isinstance(line, dict) and (found := _food_id(line.get("food"))) is not None:
                ids.add(found)
        for choice in _choices_of(draft).values():
            if (found := _food_id(choice.get("food"))) is not None:
                ids.add(found)
    return ids


def _alive(kitchen: Kitchen, ids: set[int]) -> set[int]:
    """Of these ingredient ids, the ones that are still an ingredient (followed through merges:
    a merged one stands for the one it went into). One read for all the drafts."""
    alive: set[int] = set()
    seen: dict[int, Food] = {}
    wanted = set(ids)
    while wanted:
        found = {
            food.id: food
            for food in kitchen.db.scalars(
                select(Food).where(Food.household_id == kitchen.household_id, Food.id.in_(wanted))
            )
        }
        seen.update(found)
        wanted = {
            food.merged_into_id
            for food in found.values()
            if food.merged_into_id is not None and food.merged_into_id not in seen
        } - set(seen)
    for food_id in ids:
        food, hops = seen.get(food_id), 0
        while food is not None and food.merged_into_id is not None and hops < 50:
            food, hops = seen.get(food.merged_into_id), hops + 1
        if food is not None and food.removed_at is None and food.merged_into_id is None:
            alive.add(food_id)
    return alive


def unanswered(draft: ImportDraft, alive: set[int]) -> list[tuple[int, dict[str, Any]]]:
    """(index, line) of the draft's ingredient lines still waiting for an answer."""
    choices = _choices_of(draft)
    waiting: list[tuple[int, dict[str, Any]]] = []
    for index, line in enumerate(_lines_of(draft)):
        if not isinstance(line, dict) or line.get("kind") != "ingredient":
            continue
        if not str(line.get("written") or "").strip() and not str(line.get("words") or "").strip():
            continue  # a line added on Check and never named is not saved (F187)
        choice = choices.get(index)
        if choice is not None:
            food = _food_id(choice.get("food"))
            if food is None or food in alive:
                continue
        elif line.get("label") in ("matched", "staple"):
            food = _food_id(line.get("food"))
            if food is not None and food in alive:
                continue
        waiting.append((index, line))
    return waiting


# --- The groups ---------------------------------------------------------------------------------


@dataclass
class _Group:
    key: str
    drafts: set[int] = field(default_factory=set)
    lines: int = 0
    names: Counter[str] = field(default_factory=Counter)
    examples: list[str] = field(default_factory=list)
    guesses: Counter[tuple[int, str]] = field(default_factory=Counter)
    new_name: str = ""
    new_place: Ref | None = None


def mealie_rows(kitchen: Kitchen) -> list[ImportDraft]:
    from mealwright.mealie_import import mealie_drafts

    return mealie_drafts(kitchen)


def _scan(kitchen: Kitchen, rows: list[ImportDraft]) -> dict[str, _Group]:
    alive = _alive(kitchen, _foods_used(rows))
    groups: dict[str, _Group] = {}
    for draft in rows:
        for _index, line in unanswered(draft, alive):
            key, name = _name_key(line)
            if not key:
                continue
            group = groups.get(key)
            if group is None:
                group = groups[key] = _Group(key)
                new = line.get("new_ingredient")
                if isinstance(new, dict):
                    group.new_name = str(new.get("name") or "")[:100]
                    place = new.get("place")
                    if isinstance(place, dict) and isinstance(place.get("id"), int):
                        group.new_place = Ref(id=place["id"], name=str(place.get("name") or ""))
            group.drafts.add(draft.id)
            group.lines += 1
            group.names[name] += 1
            written = cut_text(str(line.get("written") or name), EXAMPLE_CHARS).strip()
            if written and len(group.examples) < EXAMPLES and written not in group.examples:
                group.examples.append(written)
            guess = _food_id(line.get("food"))
            if line.get("label") == "to_confirm" and guess is not None and guess in alive:
                group.guesses[(guess, str(line["food"].get("name") or ""))] += 1
    return groups


def _ranked(groups: dict[str, _Group]) -> list[_Group]:
    return sorted(groups.values(), key=lambda g: (-len(g.drafts), g.key))


def _fresh_suggestions(kitchen: Kitchen, wanted: list[_Group]) -> dict[str, Ref]:
    """What matching makes of each group's first example against the household's ingredients as
    they are now (a draft is read once, when it is made)."""
    from mealwright import recipe_import
    from mealwright.ingredient_match import kitchen_of
    from mealwright.pints import PINT_ML

    if not wanted:
        return {}
    ingredients = kitchen_of(kitchen.db, kitchen.household_id)
    places = recipe_import._food_places(kitchen)
    found: dict[str, Ref] = {}
    for group in wanted:
        text = group.examples[0] if group.examples else group.names.most_common(1)[0][0]
        try:
            reads = recipe_import._lines(ingredients, places, text, False, PINT_ML["uk"])
        except ValueError, ArithmeticError:  # a line the reader can't take: no suggestion
            reads = []
        for read, _pints in reads:
            if read.label in ("matched", "staple", "to_confirm") and read.food is not None:
                found[group.key] = read.food
                break
    return found


def listing(kitchen: Kitchen, limit: int = LIST_LIMIT) -> IngredientGroups:
    rows = mealie_rows(kitchen)
    ranked = _ranked(_scan(kitchen, rows))
    shown = ranked[: max(1, min(limit, MAX_LIMIT))]
    fresh = _fresh_suggestions(kitchen, shown[:SUGGEST_FOR])
    out = []
    for group in shown:
        suggestion = fresh.get(group.key)
        if suggestion is None and group.guesses:
            (food_id, name), _n = group.guesses.most_common(1)[0]
            suggestion = Ref(id=food_id, name=name)
        name = group.names.most_common(1)[0][0]
        out.append(
            IngredientGroup(
                key=group.key,
                name=name,
                drafts=len(group.drafts),
                lines=group.lines,
                examples=group.examples,
                suggestion=suggestion,
                new_name=group.new_name or name[:1].upper() + name[1:],
                new_place=group.new_place,
            )
        )
    places = [
        Ref(id=place.id, name=place.name)
        for place in kitchen.db.scalars(
            select(Place)
            .where(Place.household_id == kitchen.household_id)
            .order_by(Place.position, Place.id)
        )
    ]
    return IngredientGroups(
        groups=out,
        total=len(ranked),
        drafts=len(rows),
        recipes_ready=_recipes_ready(kitchen),
        places=places,
    )


def _recipes_ready(kitchen: Kitchen) -> int:
    """Mealie recipes already in Recipes (saved by the import, by Save all or by an answer),
    not deleted since."""
    from mealwright.mealie_import import _ids_where

    ids: list[int] = []
    for results in kitchen.db.scalars(
        select(MealieImport.results).where(
            MealieImport.household_id == kitchen.household_id, MealieImport.state != "undone"
        )
    ):
        for entry in results or []:
            if entry.get("state") in READY_STATES and entry.get("recipe_id"):
                ids.append(int(entry["recipe_id"]))
    return len(
        _ids_where(
            kitchen.db,
            Recipe.id,
            ids,
            Recipe.household_id == kitchen.household_id,
            Recipe.removed_at.is_(None),
        )
    )


# --- Answering a group ----------------------------------------------------------------------------


@dataclass
class Answered:
    change: Change
    drafts: int
    moved: int
    ingredient: Ref | None
    todo: list[int] = field(default_factory=list)  # drafts the answer completed


def _answer_food(
    kitchen: Kitchen, answer: GroupAnswer, group: _Group, import_id: int | None
) -> tuple[Food | None, bool]:
    """(the ingredient every line is tied to, whether this answer made it)."""
    db = kitchen.db
    if answer.kind == "text":
        return None, False
    if answer.kind == "ingredient":
        food = db.get(Food, answer.food_id or 0)
        hops = 0
        while food is not None and food.merged_into_id is not None and hops < 50:
            food, hops = db.get(Food, food.merged_into_id), hops + 1
        if (
            food is None
            or food.household_id != kitchen.household_id
            or food.removed_at is not None
            or food.merged_into_id is not None
        ):
            raise not_found("That ingredient")
        return food, False
    name = answer.name or ""
    for food in db.scalars(
        select(Food).where(
            Food.household_id == kitchen.household_id,
            Food.removed_at.is_(None),
            Food.merged_into_id.is_(None),
        )
    ):
        if fold(food.name) == fold(name):
            return food, False
    if answer.place_id is not None:
        place = db.get(Place, answer.place_id)
        if place is None or place.household_id != kitchen.household_id:
            raise not_found("That place")
    found = table().match(name)
    food = Food(
        household_id=kitchen.household_id,
        name=name,
        staple=False,
        counted_as=group_counted_as(group, found),
        shop_id=usual_shop_id([name], shop_choices(kitchen)),
        aisle=guess_aisle(name, found),
        table_key=found.key if found else None,
        place_id=answer.place_id,
        mealie_import_id=import_id,
    )
    db.add(food)
    db.flush()
    return food, True


def group_counted_as(group: _Group, found: Any) -> str:
    return found.counted_as if found else "weight"


def _applied(
    draft: ImportDraft, indexes: list[int], choice: DraftChoice
) -> tuple[ImportReview, DraftChoices] | None:
    try:
        review = ImportReview.model_validate(draft.review)
        choices = DraftChoices.model_validate(draft.choices)
    except ValidationError:
        return None
    lines = dict(choices.lines)
    for index in indexes:
        lines[index] = choice
    return review, choices.model_copy(update={"lines": lines})


def _may_save(choices: DraftChoices, before: DraftChoices) -> bool:
    """A draft the person had changed on the review screen is left for its own Save."""
    if any(getattr(before, name) is not None for name in ("name", "serves", "minutes", "pints")):
        return False
    return all(c.kind in ("ingredient", "here") for c in choices.lines.values())


def _saved_review(review: ImportReview, choices: DraftChoices, draft: ImportDraft) -> ImportReview:
    """The review as it is saved: lines answered with an ingredient are tied to it; every other
    line the person answered is words only (`_read` is false for it)."""
    lines = list(review.lines)
    for index, choice in choices.lines.items():
        line = lines[index]
        if choice.kind == "ingredient" and choice.food is not None:
            lines[index] = line.model_copy(
                update={"food": choice.food, "label": "matched", "place": None}
            )
        else:
            lines[index] = line.model_copy(update={"food": None, "label": "needs_you"})
    return review.model_copy(update={"lines": lines, "name": draft.name or review.name})


def _remaining(review: ImportReview, choices: DraftChoices) -> list[int]:
    """The ingredient lines of the draft that still have no answer."""
    return [
        i
        for i, line in enumerate(review.lines)
        if line.kind == "ingredient"
        and (line.written.strip() or line.words.strip())
        and i not in choices.lines
        and not (line.label in ("matched", "staple") and line.food is not None)
    ]


def answer(kitchen: Kitchen, body: GroupAnswer) -> Answered:
    """Apply one answer to every Mealie draft that uses the group: the answers are written on
    the drafts and the change is recorded, all at once. The caller holds the household's lock and
    commits (with the change's own Idempotency-Key), then calls `finish`, which saves the drafts
    this answer completed in short locked stretches."""
    from mealwright.shopping import bump_foods

    db = kitchen.db
    rows = mealie_rows(kitchen)
    alive = _alive(kitchen, _foods_used(rows))
    group = _Group(body.key)
    users: list[tuple[ImportDraft, list[int]]] = []
    for draft in rows:
        hits = [i for i, line in unanswered(draft, alive) if _name_key(line)[0] == body.key]
        if hits:
            users.append((draft, hits))
            first = _lines_of(draft)[hits[0]]
            if not group.names:
                group.names[_name_key(first)[1]] += 1
    if not users:
        raise not_found("That ingredient")
    import_id = users[0][0].mealie_import_id
    food, made = _answer_food(kitchen, body, group, import_id)
    ref = Ref(id=food.id, name=food.name) if food is not None else None
    choice = (
        DraftChoice(kind="ingredient", food=ref) if ref is not None else DraftChoice(kind="here")
    )
    if made and food is not None:
        bump_foods(kitchen, [food.id])
    now = utcnow()
    complete: list[int] = []  # drafts every line of which is now answered: saved by `finish`
    partial: list[dict[str, Any]] = []
    for draft, hits in users:
        before = _choices_of(draft)
        applied = _applied(draft, hits, choice)
        if applied is None:
            continue
        review, choices = applied
        before_model = DraftChoices.model_validate(draft.choices)
        review, choices = drafts.freshen(kitchen, review, choices)
        if not _remaining(review, choices) and _may_save(choices, before_model):
            complete.append(draft.id)
        total, checked = drafts._progress(review, choices)
        draft.choices = choices.model_dump(mode="json")
        draft.lines_total, draft.lines_checked = total, checked
        draft.updated_at = now
        # What each line's choice was before (null: none): all Undo needs for a draft that
        # stays a draft, and for one `finish` saves (it is moved to "saved" then).
        partial.append({"draft_id": draft.id, "lines": {str(i): before.get(i) for i in hits}})
    db.flush()
    name = group.names.most_common(1)[0][0] if group.names else body.key
    change = record(
        kitchen,
        "mealie_drafts_answered",
        _summary(name, len(partial), 0),
        None,
        {
            "name": name,
            "choice": choice.model_dump(mode="json"),
            "made_food": food.id if made and food is not None else None,
            "saved": [],
            "partial": partial,
            # The drafts this answer completed and `finish` has not yet looked at (each is
            # taken off once looked at, saved or not): what a stop leaves for the next answer.
            "completed": list(complete),
        },
    )
    return Answered(change, len(partial), 0, ref, complete)


def _summary(name: str, count: int, moved: int) -> str:
    summary = f"Answered “{cut_text(name, 60)}” in {_many(count, 'draft')}"
    if moved:
        summary += f" · {_many(moved, 'recipe')} moved to Recipes"
    return summary


def finish(kitchen: Kitchen, done: Answered) -> Answered:
    """Save the drafts the answer completed, each short stretch under the household's lock with
    the same time budget as Save all (`mealie_import.HOLD_SECONDS`), the lock let go between
    stretches. Each stretch records, in the same commit as its recipes, which drafts it moved
    (from the change's `partial` to its `saved`), so the change always says exactly what was
    done, and Undo takes back just that, even if a later stretch fails. A draft that changed
    since (answered again, deleted, saved) is left alone. Commits."""
    from mealwright import mealie_import, recipes
    from mealwright.shopping import lock_household

    db = kitchen.db
    change_id = done.change.id
    todo = done.todo
    moved = 0
    at = 0
    while at < len(todo):
        lock_household(kitchen)
        began, first = time.monotonic(), at
        change = db.get(Change, change_id)
        if change is None or change.undone_by_change_id is not None:
            db.commit()
            break
        db.refresh(change)
        data = change.undo_data or {}
        before = {int(e["draft_id"]): e["lines"] for e in data.get("partial", [])}
        items: list[dict[str, Any]] = []
        while at < len(todo) and (
            at == first or time.monotonic() - began < mealie_import.HOLD_SECONDS
        ):
            draft_id = todo[at]
            at += 1
            if draft_id not in before:
                continue  # taken back (Undo) or already moved
            item = _save_one(kitchen, draft_id, before[draft_id], recipes, mealie_import._save)
            if item is not None:
                items.append(item)
        _results_say(kitchen, items, "answered")
        looked = set(todo[first:at])
        moved_ids = {item["draft_id"] for item in items}
        saved = [*data.get("saved", []), *items]
        moved = len(saved)
        count = len(saved) + len(data.get("partial", [])) - len(moved_ids)  # drafts it went into
        change.summary = _summary(str(data.get("name", "")), count, moved)
        change.undo_data = {
            **data,
            "saved": saved,
            "partial": [e for e in data.get("partial", []) if e["draft_id"] not in moved_ids],
            "completed": [i for i in data.get("completed", []) if i not in looked],
        }
        db.commit()
        if at < len(todo):
            mealie_import._pause()
    change = db.get(Change, change_id)
    if change is not None:
        db.refresh(change)
        moved = len((change.undo_data or {}).get("saved", []))
        done = Answered(change, done.drafts, moved, done.ingredient, [])
    return done


LEFT_BEHIND_CHANGES = 3  # the newest answers looked at when finishing what a stop left


def finish_left_behind(kitchen: Kitchen) -> int:
    """Finish an answer a stop interrupted (round 2, L3): the answers and the change are
    committed first and the completed drafts are saved after, in short stretches (`finish`), so a
    server stopped between the two leaves the drafts that answer completed still in Drafts. The
    change keeps their ids in `completed` (written in the same commit as the answers; `finish`
    takes each off once it has looked at it, saved or not), so this touches only those drafts:
    never one the answer did not complete, never one answered or changed since (its
    `updated_at` is later than the change), and each at most once, because the list is emptied
    here. When nothing is left behind it costs one small query. `finish` looks at each draft
    again and only moves one still complete, so a draft is never moved twice and Undo brings it
    back as for any other. Called before the next answer is applied (never on a GET). Returns how
    many drafts were moved."""
    from mealwright.household import UNDO_WINDOW
    from mealwright.shopping import lock_household

    db = kitchen.db
    moved = 0
    changes = db.scalars(
        select(Change)
        .where(
            Change.household_id == kitchen.household_id,
            Change.kind == KIND,
            Change.undone_by_change_id.is_(None),
            Change.at > utcnow() - UNDO_WINDOW,
        )
        .order_by(Change.id.desc())
        .limit(LEFT_BEHIND_CHANGES)
    ).all()
    for change in changes:
        left = [int(i) for i in (change.undo_data or {}).get("completed", [])]
        if not left:
            continue
        mine = {int(e["draft_id"]) for e in (change.undo_data or {}).get("partial", [])}
        waiting = set(
            db.scalars(
                select(ImportDraft.id).where(
                    ImportDraft.id.in_(left),
                    *drafts.live(kitchen.household_id, utcnow()),
                    ImportDraft.mealie_import_id.is_not(None),
                    ImportDraft.lines_total > 0,
                    ImportDraft.lines_checked >= ImportDraft.lines_total,
                    ImportDraft.updated_at <= change.at,
                )
            )
        )
        todo = [i for i in left if i in waiting and i in mine]
        if todo:
            before = len((change.undo_data or {}).get("saved", []))
            done = finish(kitchen, Answered(change, 0, 0, None, todo))
            moved += max(0, done.moved - before)
        # What was not finished (changed since, gone, answered less) is let go for good.
        lock_household(kitchen)
        again = db.get(Change, change.id)
        if again is not None:
            db.refresh(again)
            if (again.undo_data or {}).get("completed"):
                again.undo_data = {**(again.undo_data or {}), "completed": []}
        db.commit()
    return moved


def _save_one(
    kitchen: Kitchen,
    draft_id: int,
    lines_before: dict[str, Any],
    recipes: Any,
    save: Any,
) -> dict[str, Any] | None:
    """One completed draft, looked at again inside its stretch: saved as a recipe only if it is
    still a live Mealie draft every line of which is answered and the person has changed
    nothing else on the review screen."""
    db = kitchen.db
    draft = db.scalar(
        select(ImportDraft).where(
            ImportDraft.id == draft_id,
            *drafts.live(kitchen.household_id, utcnow()),
            ImportDraft.mealie_import_id.is_not(None),
        )
    )
    if draft is None:
        return None
    try:
        review = ImportReview.model_validate(draft.review)
        choices = DraftChoices.model_validate(draft.choices)
    except ValidationError:
        return None
    review, choices = drafts.freshen(kitchen, review, choices)
    if _remaining(review, choices) or not _may_save(choices, choices):
        return None
    # The draft as it was before this answer, which is what Undo brings back.
    lines = dict(choices.lines)
    for key, was in lines_before.items():
        if was is None:
            lines.pop(int(key), None)
        else:
            lines[int(key)] = DraftChoice.model_validate(was)
    original = choices.model_copy(update={"lines": lines})
    return _save_complete(kitchen, draft, review, choices, original, recipes, save)


def _compact(copy: dict[str, Any]) -> dict[str, Any]:
    """A draft's copy as Undo needs it and no more: what the item already says (the draft's id
    and its import) and empty values are left out, and the rest is packed (zlib, then base64
    text), which makes the review about a fifth of its size. The names stay readable outside the
    pack, so the problem report's scrubber still finds them."""
    rest = {
        k: v
        for k, v in copy.items()
        if k not in ("id", "mealie_import_id", "name", "started_by_name")
        and not (k in ("source_text", "site", "photo_id", "started_by_login_id") and not v)
    }
    packed = zlib.compress(json.dumps(rest, separators=(",", ":")).encode())
    return {
        "name": copy.get("name", ""),
        "started_by_name": copy.get("started_by_name", ""),
        "z": base64.b64encode(packed).decode("ascii"),
    }


def _expanded(item: dict[str, Any]) -> dict[str, Any]:
    """The copy as `drafts.bring_back` takes it (a record from before the copy was packed is
    read as it is)."""
    saved = dict(item["draft"])
    if "z" in saved:
        saved.update(json.loads(zlib.decompress(base64.b64decode(saved.pop("z")))))
    return {
        "source_text": "",
        "site": None,
        "photo_id": None,
        "started_by_login_id": None,
        "id": item.get("draft_id"),
        "mealie_import_id": item.get("import_id"),
        **saved,
    }


def _save_complete(
    kitchen: Kitchen,
    draft: ImportDraft,
    review: ImportReview,
    choices: DraftChoices,
    original: DraftChoices,
    recipes: Any,
    save: Any,
) -> dict[str, Any] | None:
    """The draft as a recipe, in its own savepoint; the draft's copy goes in the change so Undo can
    bring it back. None: it couldn't be saved (it stays a draft with its answers)."""
    from mealwright.mealie_import import _read  # the one rule, as Save all and the import use

    db = kitchen.db
    photo = db.scalar(select(RecipePhoto).where(RecipePhoto.draft_id == draft.id))
    import_id, draft_id = draft.mealie_import_id, draft.id
    copy = drafts.snapshot(draft, photo.id if photo is not None else None)
    copy["choices"] = original.model_dump(mode="json")
    copy["lines_total"], copy["lines_checked"] = drafts._progress(review, original)
    final = _saved_review(review, choices, draft)
    try:
        with db.begin_nested():
            if photo is not None:
                photo.draft_id = None
                db.flush()
            recipe = save(
                kitchen,
                final,
                photo.id if photo is not None else None,
                [_read(line) for line in final.lines],
            )
            db.delete(draft)
            db.flush()
    except Exception as why:
        # Only the kind of error: what it says may hold the person's own words.
        log.warning(
            "A Mealie draft answered by ingredient couldn't be saved; kept as a draft (%s)",
            type(why).__name__,
        )
        return None
    return {
        "recipe_id": recipe.id,
        "version": recipe.version,
        "draft_id": draft_id,
        "import_id": import_id,
        "draft": _compact(copy),
    }


def _results_say(kitchen: Kitchen, items: list[dict[str, Any]], state: str) -> None:
    """The import's results hold each recipe, so its own Undo knows the ones saved here."""
    by_import: dict[int, dict[int, dict[str, Any]]] = {}
    for item in items:
        if item.get("import_id") is not None:
            by_import.setdefault(item["import_id"], {})[item["draft_id"]] = item
    for import_id, mine in by_import.items():
        row = kitchen.db.get(MealieImport, import_id)
        if row is None or row.household_id != kitchen.household_id:
            continue
        kitchen.db.refresh(row)
        updated: list[dict[str, Any]] = []
        for entry in row.results:
            hit = mine.get(entry.get("draft_id", -1))
            if hit is not None and state == "answered":
                entry = {
                    **entry,
                    "state": "answered",
                    "recipe_id": hit["recipe_id"],
                    "version": hit["version"],
                }
            elif hit is not None:
                entry = {
                    key: value
                    for key, value in entry.items()
                    if key not in ("recipe_id", "version")
                } | {"state": "draft"}
            updated.append(entry)
        row.results = updated


# --- Undo ---------------------------------------------------------------------------------


UNDO_BATCH = 10  # recipes looked at together inside one stretch of an Undo


def _walk(
    kitchen: Kitchen,
    change_id: int,
    key: str,
    handle: Callable[[list[dict[str, Any]], dict[str, int]], list[dict[str, Any]]],
    stretched: bool,
) -> None:
    """Go through the items of the change under `key` that are not `done`, `UNDO_BATCH` at a
    time. `handle` takes some items and the running counts and answers each item as it should be
    kept. Stretched (the Undo's own request): each stretch is locked for about
    `mealie_import.HOLD_SECONDS`, then committed with the items it did marked `done`, and the lock
    is let go before the next; so a stop part-way leaves a change that says exactly what is
    still to undo, and the Undo carries on when asked again."""
    from mealwright import mealie_import
    from mealwright.shopping import lock_household

    db = kitchen.db
    first_look = db.get(Change, change_id)
    if first_look is None:
        return
    pending = [
        k for k, i in enumerate((first_look.undo_data or {}).get(key, [])) if not i.get("done")
    ]
    at = 0
    while at < len(pending):
        if stretched:
            lock_household(kitchen)
        change = db.get(Change, change_id)
        if change is None:
            return
        db.refresh(change)
        data = change.undo_data or {}
        items = list(data.get(key, []))
        counts = dict(data.get("progress") or {})
        began, first = time.monotonic(), at
        while at < len(pending) and (
            not stretched or at == first or time.monotonic() - began < mealie_import.HOLD_SECONDS
        ):
            chunk = pending[at : at + UNDO_BATCH]
            at += len(chunk)
            # Another Undo of the same change may have done some between stretches.
            chunk = [k for k in chunk if not items[k].get("done")]
            if not chunk:
                continue
            for k, new in zip(chunk, handle([items[k] for k in chunk], counts), strict=True):
                items[k] = new
        change.undo_data = {**data, key: items, "progress": counts}
        db.flush()
        if stretched:
            db.commit()
            if at < len(pending):
                mealie_import._pause()


def undo(kitchen: Kitchen, change: Change, stretched: bool = False) -> Change:
    """Put a group's answers back to unanswered: the answered lines of drafts that stayed drafts
    lose their answer (unless the person changed it since), recipes moved to Recipes come back
    to Drafts (unless changed, cooked or planned since), and the ingredient this answer made
    goes only if nothing else (a recipe, the pantry, a draft's answer) uses it.

    `stretched`: in short locked stretches, committing as it goes (see `_walk`); the caller
    has not written anything yet, and commits the last stretch with the Undo's own record."""
    from mealwright.history import bump_recipes_by
    from mealwright.mealie_import import _kept_recipes, _used_foods_of
    from mealwright.recipes import _users_of
    from mealwright.shopping import bump_foods, lock_household

    db = kitchen.db
    change_id = change.id
    since = as_utc(change.at)
    chosen = (change.undo_data or {}).get("choice", {})

    def recipes_back(items: list[dict[str, Any]], counts: dict[str, int]) -> list[dict[str, Any]]:
        now = utcnow()
        versions = {int(i["recipe_id"]): int(i.get("version") or 0) for i in items}
        stays = _kept_recipes(db, versions, since)
        returned: list[dict[str, Any]] = []
        out: list[dict[str, Any]] = []
        for item in items:
            recipe = db.get(Recipe, int(item["recipe_id"]))
            if (
                recipe is None
                or recipe.household_id != kitchen.household_id
                or recipe.removed_at is not None
            ):
                counts["gone"] = counts.get("gone", 0) + 1  # nothing to bring back
            elif recipe.id in stays:
                counts["kept"] = counts.get("kept", 0) + 1
            else:
                recipe.removed_at = now
                db.flush()
                bump_recipes_by(kitchen, {recipe.id, *_users_of(kitchen, recipe.id)})
                drafts.bring_back(kitchen, recipe.id, _expanded(item))
                returned.append(item)
                counts["back"] = counts.get("back", 0) + 1
            out.append({k: v for k, v in item.items() if k != "draft"} | {"done": True})
        _results_say(kitchen, returned, "draft")
        return out

    def answers_off(items: list[dict[str, Any]], counts: dict[str, int]) -> list[dict[str, Any]]:
        now = utcnow()
        for item in items:
            _unanswer(kitchen, item, chosen, now)
        return [{**item, "done": True} for item in items]

    _walk(kitchen, change_id, "saved", recipes_back, stretched)
    _walk(kitchen, change_id, "partial", answers_off, stretched)

    if stretched:
        lock_household(kitchen)
    change = db.get(Change, change_id) or change
    db.refresh(change)
    if change.undone_by_change_id is not None:
        # Two Undos at once (a retry, or two people): the first to get here records it.
        raise already_undone()
    data = change.undo_data or {}
    counts = data.get("progress") or {}
    back, kept, gone = (int(counts.get(k, 0)) for k in ("back", "kept", "gone"))
    foods = 0
    made = data.get("made_food")
    if isinstance(made, int):
        food = db.get(Food, made)
        if food is not None and food.household_id == kitchen.household_id and not food.removed_at:
            db.flush()
            if not _used_foods_of(db, kitchen.household_id, food.mealie_import_id or 0, [made]):
                food.removed_at = utcnow()
                db.flush()
                bump_foods(kitchen, [made])
                foods = 1
    message = f"“{data.get('name', '')}” is unanswered again."
    if back:
        verb = "is" if back == 1 else "are"
        message += f" {_many(back, 'recipe')} {verb} back in Drafts."
    # Words proposed, for cabledrawer (the spec doesn't give them).
    if gone:
        message += (
            f" {_many(gone, 'recipe')} {'was' if gone == 1 else 'were'} already out of Recipes"
            " (deleted, or the import was undone), so nothing was brought back for"
            f" {'it' if gone == 1 else 'them'}."
        )
    if kept:
        message += (
            f" {kept} {'stays' if kept == 1 else 'stay'} in Recipes:"
            f" {'it was' if kept == 1 else 'they were'} changed, cooked or planned since."
        )
    undone = record(
        kitchen,
        "undo",
        f"Undid: {change.summary}",
        None,
        {
            "result": "done" if not kept else "partly",
            "message": message,
            "undoes_kind": change.kind,
            "undoes_at": as_utc(change.at).isoformat(),
            "foods_removed": foods,
        },
    )
    undone.undoes_change_id = change.id
    change.undone_by_change_id = undone.id
    db.flush()
    return undone


def _unanswer(kitchen: Kitchen, item: dict[str, Any], chosen: Any, now: datetime) -> None:
    """One draft that stayed a draft: its lines this answer answered are unanswered again,
    unless the person changed one since."""
    db = kitchen.db
    draft = db.get(ImportDraft, item["draft_id"])
    if draft is None or draft.household_id != kitchen.household_id or draft.removed_at:
        return
    choices = DraftChoices.model_validate(draft.choices)
    lines = dict(choices.lines)
    for key, was in item["lines"].items():
        index = int(key)
        now_choice = lines.get(index)
        if now_choice is None or now_choice.model_dump(mode="json") != chosen:
            continue  # changed since: leave what the person chose
        if was is None:
            del lines[index]
        else:
            lines[index] = DraftChoice.model_validate(was)
    choices = choices.model_copy(update={"lines": lines})
    try:
        review = ImportReview.model_validate(draft.review)
        draft.lines_total, draft.lines_checked = drafts._progress(review, choices)
    except ValidationError:
        pass
    draft.choices = choices.model_dump(mode="json")
    draft.updated_at = now


def drop_copies(db: Any, household_id: int, before: datetime) -> int:
    """After the undo window the drafts' copies kept in the change are no use: dropped (called
    from the hourly tidy-up, `drafts.drop_save_copies`)."""
    dropped = 0
    for change in db.scalars(
        select(Change).where(
            Change.household_id == household_id,
            Change.kind == KIND,
            Change.at < before,
            Change.undo_data.is_not(None),
        )
    ):
        data = change.undo_data or {}
        if any("draft" in item for item in data.get("saved", [])):
            change.undo_data = {
                **data,
                "saved": [{k: v for k, v in i.items() if k != "draft"} for i in data["saved"]],
            }
            dropped += 1
    return dropped
