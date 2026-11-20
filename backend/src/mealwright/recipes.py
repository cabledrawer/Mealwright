"""Recipes: saving them, the loop guard, Undo of a delete, and describing them for the web
app (docs/dev/api-0.4-recipes.md).

A recipe is saved whole, never piece by piece ("nothing changes until Save"). Its lines
keep their ids across saves, so an ingredient merge, or removing an ingredient, can find
and follow them. A deleted recipe stays hidden for the undo window (7 days), then goes for
good; the lines of other recipes that used it keep their words meanwhile, marked "recipe
removed", and Undo brings the link back by itself.
"""

from collections import deque
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, cast
from urllib.parse import urlsplit

from fastapi import status
from sqlalchemy import Select, delete, func, select, update
from sqlalchemy.orm import Session as DbSession

from mealwright import events, methods, step_timings, step_waits
from mealwright.api.v1.context import Kitchen
from mealwright.api.v1.recipe_schemas import (
    Blocked,
    LineFoodRef,
    MakesOut,
    MethodRef,
    NutritionOut,
    PhotoOut,
    RecipeBrief,
    RecipeIn,
    RecipeLineIn,
    RecipeLineOut,
    RecipeOut,
    RecipeStepIn,
    RecipeStepOut,
    SecondMethodOut,
    SizeRef,
    SourceOut,
    StepLineOut,
    StepTimingIn,
    StepTimingOut,
    StepWaitIn,
    StepWaitOut,
    amount_text,
)
from mealwright.api.v1.schemas import Ref, Who
from mealwright.errors import Problem, not_found
from mealwright.foods import make_food, name_owner, name_taken, suggested_shop
from mealwright.foods import visible as food_visible
from mealwright.history import Tally, as_utc, bump_recipes, bump_recipes_by, record, too_old
from mealwright.household import undo_window
from mealwright.models import (
    Change,
    Food,
    FoodName,
    FoodSize,
    Household,
    MealItem,
    Recipe,
    RecipeLine,
    RecipeMethod,
    RecipePhoto,
    RecipeStep,
    RecipeStepLine,
    RecipeTag,
    Tag,
    utcnow,
)
from mealwright.names import fold
from mealwright.photos import copy_file as photos_copy_file
from mealwright.photos import delete_after_commit, delete_quietly, new_key, store_of
from mealwright.photos import log as photos_log
from mealwright.photos import paths as photo_paths

CANT = "can\u2019t"


# --- Finding ----------------------------------------------------------------------------------


def find(kitchen: Kitchen, recipe_id: int) -> Recipe:
    """A recipe in this household that hasn't been deleted (else 404)."""
    recipe = kitchen.db.get(Recipe, recipe_id)
    if recipe is None or recipe.household_id != kitchen.household_id or recipe.removed_at:
        raise not_found("That recipe")
    return recipe


def live_recipes(kitchen: Kitchen) -> dict[int, Recipe]:
    return {
        recipe.id: recipe
        for recipe in kitchen.db.scalars(
            select(Recipe).where(
                Recipe.household_id == kitchen.household_id, Recipe.removed_at.is_(None)
            )
        )
    }


# --- The loop guard (cabledrawer 19 Oct, questions 19 and 20)
# --------------------------------------


def uses_graph(kitchen: Kitchen, also_live: int | None = None) -> dict[int, set[int]]:
    """Which recipe uses which, among recipes that haven't been deleted (and `also_live`,
    a recipe about to be brought back by Undo)."""
    live = {also_live} if also_live is not None else set()
    live |= set(
        kitchen.db.scalars(
            select(Recipe.id).where(
                Recipe.household_id == kitchen.household_id, Recipe.removed_at.is_(None)
            )
        )
    )
    graph: dict[int, set[int]] = {}
    for recipe_id, sub_id in kitchen.db.execute(
        select(RecipeLine.recipe_id, RecipeLine.sub_recipe_id).where(
            RecipeLine.household_id == kitchen.household_id,
            RecipeLine.sub_recipe_id.is_not(None),
        )
    ):
        if recipe_id in live and sub_id in live:
            graph.setdefault(recipe_id, set()).add(sub_id)
    return graph


def reaching(graph: dict[int, set[int]], target: int) -> dict[int, int]:
    """One search backwards from `target`: every recipe that uses it, directly or through
    others, with the next recipe on its shortest chain towards it. Following the links from
    a recipe gives its chain: [recipe, next, …, target]."""
    used_by: dict[int, list[int]] = {}
    for user, used in graph.items():
        for sub in used:
            used_by.setdefault(sub, []).append(user)
    toward: dict[int, int] = {}
    queue = deque([target])
    while queue:
        here = queue.popleft()
        for user in sorted(used_by.get(here, ())):
            if user != target and user not in toward:
                toward[user] = here
                queue.append(user)
    return toward


def chain_from(toward: dict[int, int], start: int, target: int) -> list[int]:
    chain = [start]
    while chain[-1] != target:
        chain.append(toward[chain[-1]])
    return chain


def loop_sentence(names: list[str]) -> str:
    """names = [Sambar, Rasam powder, Sambar powder] (Sambar uses Rasam powder, which uses
    Sambar powder) → "Sambar powder can\u2019t use Sambar, because Sambar uses Rasam powder,
    which uses Sambar powder." """
    first, rest = names[0], names[1:]
    because = f"{first} uses {rest[0]}" + "".join(f", which uses {name}" for name in rest[1:])
    return f"{names[-1]} {CANT} use {first}, because {because}."


def blocked_for(kitchen: Kitchen, recipe: Recipe) -> list[Blocked]:
    """The recipes this recipe can't use, and why: itself, and every recipe that already
    uses it (directly or through others)."""
    toward = reaching(uses_graph(kitchen), recipe.id)
    names = {rid: r.name for rid, r in live_recipes(kitchen).items()}
    blocked = [
        Blocked(
            id=recipe.id,
            name=recipe.name,
            reason=f"A recipe {CANT} use itself.",
            chain=[recipe.name],
        )
    ]
    for other_id in toward:
        words = [names.get(i, "") for i in chain_from(toward, other_id, recipe.id)]
        blocked.append(
            Blocked(
                id=other_id,
                name=names[other_id],
                reason=loop_sentence(words),
                chain=words,
            )
        )
    return sorted(blocked, key=lambda b: (b.id != recipe.id, fold(b.name)))


def check_loops(
    kitchen: Kitchen,
    recipe: Recipe | None,
    picks: list[tuple[int, Recipe]],
    restoring: bool = False,
) -> None:
    """Every save checks again, because someone may have changed the other recipe
    meanwhile. `picks` is (line number, recipe used). `restoring`: the recipe is deleted
    and Undo is bringing it back, so it counts as there."""
    if recipe is None:  # a brand-new recipe has no one using it yet, and can't use itself
        return
    toward = reaching(uses_graph(kitchen, also_live=recipe.id if restoring else None), recipe.id)
    for index, used in picks:
        if used.id == recipe.id:
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "recipe_self",
                f"A recipe {CANT} use itself.",
                line=index,
                recipe_id=used.id,
            )
        if used.id in toward:
            chain = chain_from(toward, used.id, recipe.id)
            names = [(kitchen.db.get(Recipe, i) or used).name for i in chain]
            raise Problem(
                status.HTTP_409_CONFLICT,
                "recipe_loop",
                loop_sentence(names),
                line=index,
                recipe_id=used.id,
                chain=names,
            )


# --- Saving -----------------------------------------------------------------------------------


def _milli(value: Decimal | None) -> int | None:
    return None if value is None else int(value * 1000 + Decimal("0.5"))


class _Resolved:
    """A line's links, checked."""

    def __init__(
        self,
        food: Food | None,
        used: Recipe | None,
        size: FoodSize | None,
    ) -> None:
        self.food, self.used, self.size = food, used, size


def _at_line(index: int, problem: Problem) -> Problem:
    problem.extra["line"] = index
    return problem


def _resolve(
    kitchen: Kitchen, existing: dict[int, RecipeLine], lines_in: list[RecipeLineIn]
) -> list[_Resolved]:
    """Check each line's links. `existing`: the lines the method has now, by id."""
    from mealwright.foods import find as find_food

    db = kitchen.db
    resolved: list[_Resolved] = []
    for index, line in enumerate(lines_in):
        old = existing.get(line.id) if line.id is not None else None
        if line.id is not None and old is None:
            raise _at_line(index, not_found("That line"))
        food = used = size = None
        try:
            if line.food_id is not None:
                food = find_food(kitchen, line.food_id)
            if line.recipe_id is not None:
                used = db.get(Recipe, line.recipe_id)
                if used is None or used.household_id != kitchen.household_id:
                    raise not_found("That recipe")
                if used.removed_at and not (old and old.sub_recipe_id == used.id):
                    raise not_found("That recipe")
            if line.size_id is not None:
                size = db.get(FoodSize, line.size_id)
                if size is None or food is None or size.food_id != food.id:
                    raise not_found("That size")
        except Problem as problem:
            raise _at_line(index, problem) from None
        resolved.append(_Resolved(food, used, size))
    return resolved


def _rows_of(
    db: DbSession,
    model: Any,
    recipe: Recipe | None,
    all_methods: list[RecipeMethod],
    position: int,
) -> list[Any]:
    """The lines (or steps) the recipe's method at `position` has now, in order."""
    if recipe is None:
        return []
    if position >= max(len(all_methods), 1):
        return []
    method = all_methods[position] if all_methods else None
    rows = db.scalars(
        select(model).where(model.recipe_id == recipe.id).order_by(model.position, model.id)
    )
    return [row for row in rows if methods.in_method(row, all_methods, method)]


def save(
    kitchen: Kitchen, recipe: Recipe | None, body: RecipeIn, *, remember_key: bool = True
) -> Recipe:
    """Create the recipe, or replace everything in it (the caller holds the household's
    lock, and has checked the version). Adds 1 to the version. `remember_key`: record the
    request's Idempotency-Key here (an import records its own change, which takes it)."""
    db = kitchen.db
    all_methods = methods.methods_of(db, recipe.id) if recipe is not None else []
    first_rows = {row.id: row for row in _rows_of(db, RecipeLine, recipe, all_methods, 0)}
    second_rows = {row.id: row for row in _rows_of(db, RecipeLine, recipe, all_methods, 1)}
    resolved = _resolve(kitchen, first_rows, body.lines)
    check_loops(
        kitchen,
        recipe,
        [(i, r.used) for i, r in enumerate(resolved) if r.used is not None],
    )
    second_sent = "second_method" in body.model_fields_set
    second_in = body.second_method if second_sent else None
    resolved_second: list[_Resolved] = []
    if second_in is not None:
        try:
            resolved_second = _resolve(kitchen, second_rows, second_in.lines)
            check_loops(
                kitchen,
                recipe,
                [(i, r.used) for i, r in enumerate(resolved_second) if r.used is not None],
            )
        except Problem as problem:
            problem.extra["method"] = 1
            raise
    now = utcnow()
    name = kitchen.login.name  # read first: loading it may flush
    creating = recipe is None
    if recipe is None:
        recipe = Recipe(
            household_id=kitchen.household_id,
            name=body.name,
            version=0,
            created_at=now,
            updated_at=now,
            updated_by_name=name,
            made_ahead=False,
        )
        db.add(recipe)
    recipe.name = body.name
    recipe.description = body.description
    if recipe.time_minutes != body.time_minutes:
        recipe.time_is_work_only = False  # a Time typed by hand follows the plain L6 rule
    recipe.time_minutes = body.time_minutes
    recipe.serves = body.serves
    recipe.makes_milli = body.makes.amount if body.makes else None
    recipe.makes_unit = body.makes.unit if body.makes else None
    recipe.source_note = body.source_note
    figures = (
        _milli(body.nutrition.kcal),
        _milli(body.nutrition.protein),
        _milli(body.nutrition.carbs),
        _milli(body.nutrition.fat),
        _milli(body.nutrition.fibre),
    )
    # The figures count as set now when the recipe is new, when one was typed over, or when
    # the person looked at them and kept them ("Update nutrition", then Save).
    if creating or figures != _figures(recipe) or body.nutrition_checked:
        recipe.nutrition_set_at = now
    (
        recipe.kcal_milli,
        recipe.protein_milli,
        recipe.carbs_milli,
        recipe.fat_milli,
        recipe.fibre_milli,
    ) = figures
    recipe.version += 1
    recipe.updated_at = now
    recipe.updated_by_login_id = kitchen.login.id
    recipe.updated_by_name = name
    db.flush()
    # Remember the request's Idempotency-Key, the way every other write does, so a retry is
    # recognised. Only when there is one. First, so the made-ahead ingredient's own change
    # below carries no key.
    if remember_key and kitchen.idempotency_key is not None:
        kitchen.key_once = True
        record(
            kitchen,
            "recipe_created" if creating else "recipe_saved",
            f"Saved {recipe.name}",
            None,
            {"recipe_id": recipe.id, "name": recipe.name},
        )

    before = None if creating else _line_signature(db, recipe.id)
    first = _first_method(kitchen, recipe, all_methods, body)
    lines = _save_lines(kitchen, recipe, first, body.lines, resolved, first_rows)
    _save_steps(
        kitchen, recipe, first, body.steps, lines, _rows_of(db, RecipeStep, recipe, all_methods, 0)
    )
    if second_sent:
        _save_second(
            kitchen, recipe, all_methods, second_in, resolved_second, second_rows, first, body
        )
    elif len(all_methods) > 1:
        first.name = body.method_name or first.name
    if before != _line_signature(db, recipe.id):
        recipe.lines_changed_at = now
    _save_tags(kitchen, recipe, body.tags)
    _save_made_ahead(kitchen, recipe, body)
    if "photo_id" in body.model_fields_set:  # left out: the photo stays as it is
        _save_photo(kitchen, recipe, body.photo_id)
    db.flush()
    return recipe


def _figures(recipe: Recipe) -> tuple[int | None, ...]:
    return (
        recipe.kcal_milli,
        recipe.protein_milli,
        recipe.carbs_milli,
        recipe.fat_milli,
        recipe.fibre_milli,
    )


def _line_key(row: RecipeLine) -> tuple[Any, ...]:
    """What makes an ingredient line a different one for the nutrition note: not its note and
    not whether it is Optional."""
    return (
        row.kind,
        row.words,
        row.amount_milli,
        row.unit,
        row.size_id,
        row.food_id,
        row.sub_recipe_id,
    )


def _line_signature(db: DbSession, recipe_id: int) -> list[tuple[Any, ...]]:
    return [
        _line_key(row)
        for row in db.scalars(
            select(RecipeLine)
            .where(RecipeLine.recipe_id == recipe_id)
            .order_by(RecipeLine.method_id, RecipeLine.position, RecipeLine.id)
        )
    ]


def nutrition_out_of_date(recipe: Recipe) -> bool:
    """Some ingredient line changed after the nutrition figures were set (R3). A recipe with no
    figures, or from before this was recorded, never says it."""
    if all(value is None for value in _figures(recipe)):
        return False
    if recipe.nutrition_set_at is None or recipe.lines_changed_at is None:
        return False
    return as_utc(recipe.lines_changed_at) > as_utc(recipe.nutrition_set_at)


def _copy_name(kitchen: Kitchen, source: Recipe) -> str:
    """ "Sambar (copy)"; if a recipe has that name already (or, for a Made ahead recipe, an
    ingredient does), "Sambar (copy 2)", then "(copy 3)" and so on. Cut to 200 characters."""
    taken = {fold(r.name) for r in live_recipes(kitchen).values()}
    n = 1
    while True:
        suffix = " (copy)" if n == 1 else f" (copy {n})"
        name = source.name[: 200 - len(suffix)].rstrip() + suffix
        busy = fold(name) in taken or (
            source.made_ahead and name_owner(kitchen, name[:100].strip()) is not None
        )
        if not busy:
            return name
        n += 1


def duplicate(kitchen: Kitchen, source: Recipe) -> Recipe:
    """A copy of the recipe named "Sambar (copy)": everything in the recipe itself (words,
    lines, steps and their ingredient links, tags, nutrition, where it came from, the photo
    as a file of its own) and nothing of what happened to it (cooked history, the plan). The
    caller holds the household's lock. Made ahead is copied; the copy's own pantry ingredient
    takes the copy's name. A name already used by a recipe (or that ingredient) gets
    "(copy 2)", "(copy 3)"... instead, so a second copy never fails."""
    db = kitchen.db
    now = utcnow()
    login_name = kitchen.login.name  # read first: loading it may flush
    copy = Recipe(
        household_id=kitchen.household_id,
        name=_copy_name(kitchen, source),
        description=source.description,
        time_minutes=source.time_minutes,
        time_is_work_only=source.time_is_work_only,
        serves=source.serves,
        makes_milli=source.makes_milli,
        makes_unit=source.makes_unit,
        made_ahead=False,
        kcal_milli=source.kcal_milli,
        protein_milli=source.protein_milli,
        carbs_milli=source.carbs_milli,
        fat_milli=source.fat_milli,
        fibre_milli=source.fibre_milli,
        source_note=source.source_note,
        source_url=source.source_url,
        imported_at=source.imported_at,
        source_author=source.source_author,
        # The copy's figures and lines are the same as the original's, so the note is too.
        nutrition_set_at=source.nutrition_set_at,
        lines_changed_at=source.lines_changed_at,
        version=1,
        created_at=now,
        updated_at=now,
        updated_by_login_id=kitchen.login.id,
        updated_by_name=login_name,
    )
    db.add(copy)
    db.flush()
    if kitchen.idempotency_key is not None:
        kitchen.key_once = True
        record(
            kitchen,
            "recipe_created",
            f"Saved {copy.name}",
            None,
            {"recipe_id": copy.id, "name": copy.name},
        )

    # Both methods are copied, each with its lines and steps (a line or step with no method is
    # in the first).
    new_method: dict[int | None, int] = {}
    source_methods = methods.methods_of(db, source.id)
    for method in cast("list[RecipeMethod | None]", source_methods or [None]):
        made = RecipeMethod(
            household_id=kitchen.household_id,
            recipe_id=copy.id,
            position=method.position if method else 0,
            name=method.name if method else "",
            time_minutes=method.time_minutes if method else source.time_minutes,
            time_is_work_only=(method.time_is_work_only if method else source.time_is_work_only),
        )
        db.add(made)
        db.flush()
        new_method[method.id if method else None] = made.id
        if method is not None and method.position == 0:
            new_method[None] = made.id
    new_line: dict[int, int] = {}
    for line in db.scalars(
        select(RecipeLine).where(RecipeLine.recipe_id == source.id).order_by(RecipeLine.position)
    ):
        row = RecipeLine(
            household_id=kitchen.household_id,
            recipe_id=copy.id,
            method_id=new_method.get(line.method_id),
            position=line.position,
            kind=line.kind,
            words=line.words,
            amount_milli=line.amount_milli,
            unit=line.unit,
            size_id=line.size_id,
            food_id=line.food_id,
            sub_recipe_id=line.sub_recipe_id,
            note=line.note,
            optional=line.optional,
        )
        db.add(row)
        db.flush()
        new_line[line.id] = row.id
    for step in db.scalars(
        select(RecipeStep).where(RecipeStep.recipe_id == source.id).order_by(RecipeStep.position)
    ):
        new_step = RecipeStep(
            household_id=kitchen.household_id,
            recipe_id=copy.id,
            method_id=new_method.get(step.method_id),
            position=step.position,
            kind=step.kind,
            text=step.text,
            optional=step.optional,
            wait_kind=step.wait_kind,
            wait_min_minutes=step.wait_min_minutes,
            wait_max_minutes=step.wait_max_minutes,
            wait_overnight=step.wait_overnight,
            **timing_columns_of(step),
        )
        db.add(new_step)
        db.flush()
        for link in db.scalars(select(RecipeStepLine).where(RecipeStepLine.step_id == step.id)):
            if link.line_id in new_line:
                db.add(
                    RecipeStepLine(
                        household_id=kitchen.household_id,
                        step_id=new_step.id,
                        line_id=new_line[link.line_id],
                        kind=link.kind,
                    )
                )
    for tag_id in db.scalars(select(RecipeTag.tag_id).where(RecipeTag.recipe_id == source.id)):
        db.add(RecipeTag(household_id=kitchen.household_id, recipe_id=copy.id, tag_id=tag_id))
    if source.made_ahead:
        _link_homemade(kitchen, copy, source.makes_unit, None)
    _copy_photo(kitchen, source, copy)
    db.flush()
    return copy


def _copy_photo(kitchen: Kitchen, source: Recipe, copy: Recipe) -> None:
    """The copy gets the photo as files and a record of its own, so removing or replacing the
    photo on one recipe never touches the other. A missing file means no photo on the copy."""
    db = kitchen.db
    photo = db.scalar(select(RecipePhoto).where(RecipePhoto.recipe_id == source.id))
    if photo is None:
        return
    store = store_of(db)
    key = new_key()
    from_large, from_small = photo_paths(store, photo.household_id, photo.file_key)
    to_large, to_small = photo_paths(store, photo.household_id, key)
    copied: list[Path] = []
    try:
        for before, after in ((from_large, to_large), (from_small, to_small)):
            # Listed before copying, so a copy that fails halfway leaves no part-written file.
            copied.append(after)
            photos_copy_file(before, after)
    except OSError as e:
        for path in copied:
            delete_quietly(path)
        photos_log.warning("Couldn't copy a recipe's photo for its copy: %s", type(e).__name__)
        return
    db.add(
        RecipePhoto(
            household_id=photo.household_id,
            recipe_id=copy.id,
            file_key=key,
            width=photo.width,
            height=photo.height,
            list_width=photo.list_width,
            list_height=photo.list_height,
            bytes=photo.bytes,
            added_by_name=kitchen.login.name,
        )
    )


def _save_photo(kitchen: Kitchen, recipe: Recipe, photo_id: int | None) -> None:
    """Attach the photo the editor uploaded, keep the one it had, or (null) have none. A
    photo that's replaced or cleared is deleted, its files once the save is committed
    (cabledrawer 20 Oct). Only an upload of this household that's not on any recipe yet can
    be attached; anything else is refused like an id that doesn't exist."""
    db = kitchen.db
    current = db.scalar(select(RecipePhoto).where(RecipePhoto.recipe_id == recipe.id))
    if current is not None and current.id == photo_id:
        return
    new = None
    if photo_id is not None:
        new = db.get(RecipePhoto, photo_id)
        if (
            new is None
            or new.household_id != kitchen.household_id
            or new.recipe_id is not None
            or new.draft_id is not None  # a draft's photo: only saving that draft takes it
        ):
            raise not_found("That photo")
    if current is not None:
        delete_photo(db, current)
        db.flush()  # the recipe's one photo place is free before the new one takes it
    if new is not None:
        new.recipe_id = recipe.id


def delete_photo(db: DbSession, photo: RecipePhoto) -> None:
    """Delete the record now and the files once this is committed."""
    delete_after_commit(db, photo.household_id, [photo.file_key])
    db.delete(photo)


def _first_method(
    kitchen: Kitchen, recipe: Recipe, all_methods: list[RecipeMethod], body: RecipeIn
) -> RecipeMethod:
    """The recipe's first method, made when it has none, with the time and name of this save."""
    db = kitchen.db
    first = all_methods[0] if all_methods else None
    if first is None:
        first = RecipeMethod(household_id=kitchen.household_id, recipe_id=recipe.id, position=0)
        db.add(first)
    if first.time_minutes != body.time_minutes:
        first.time_is_work_only = False
    first.time_minutes = body.time_minutes
    # A recipe with one way of cooking it has no method name.
    first.name = body.method_name or "" if body.second_method is not None else first.name
    if "second_method" in body.model_fields_set and body.second_method is None:
        first.name = ""
    db.flush()
    return first


def _save_second(
    kitchen: Kitchen,
    recipe: Recipe,
    all_methods: list[RecipeMethod],
    second_in: Any,
    resolved: list[_Resolved],
    old_rows: dict[int, RecipeLine],
    first: RecipeMethod,
    body: RecipeIn,
) -> None:
    """Save, change or remove the recipe's second method (M2)."""
    db = kitchen.db
    second = all_methods[1] if len(all_methods) > 1 else None
    if second_in is None:
        if second is not None:
            remove_method(kitchen, second)
        return
    if second is None:
        second = RecipeMethod(household_id=kitchen.household_id, recipe_id=recipe.id, position=1)
        db.add(second)
    second.name = second_in.name
    if second.time_minutes != second_in.time_minutes:
        second.time_is_work_only = False
    second.time_minutes = second_in.time_minutes
    db.flush()
    lines = _save_lines(kitchen, recipe, second, second_in.lines, resolved, old_rows)
    old_steps = _rows_of(db, RecipeStep, recipe, all_methods, 1) if all_methods[1:] else []
    _save_steps(kitchen, recipe, second, second_in.steps, lines, old_steps)


def remove_method(kitchen: Kitchen, method: RecipeMethod) -> None:
    """Take a method out with its lines and steps; a meal that was set to cook with it goes back
    to the recipe's first method."""
    db = kitchen.db
    step_ids = select(RecipeStep.id).where(RecipeStep.method_id == method.id)
    db.execute(delete(RecipeStepLine).where(RecipeStepLine.step_id.in_(step_ids)))
    line_ids = select(RecipeLine.id).where(RecipeLine.method_id == method.id)
    db.execute(delete(RecipeStepLine).where(RecipeStepLine.line_id.in_(line_ids)))
    db.execute(delete(RecipeStep).where(RecipeStep.method_id == method.id))
    db.execute(delete(RecipeLine).where(RecipeLine.method_id == method.id))
    db.execute(update(MealItem).where(MealItem.method_id == method.id).values(method_id=None))
    events.note_plan(db, kitchen.household_id)
    db.delete(method)
    db.flush()


def _save_lines(
    kitchen: Kitchen,
    recipe: Recipe,
    method: RecipeMethod,
    lines_in: list[RecipeLineIn],
    resolved: list[_Resolved],
    old: dict[int, RecipeLine],
) -> list[RecipeLine]:
    """Write one method's lines; returns them in order."""
    db = kitchen.db
    kept: set[int] = set()
    rows: list[RecipeLine] = []
    for position, (line, links) in enumerate(zip(lines_in, resolved, strict=True)):
        row = old.get(line.id) if line.id is not None else None
        if row is None:
            row = RecipeLine(household_id=kitchen.household_id, recipe_id=recipe.id)
            db.add(row)
        else:
            kept.add(row.id)
        rows.append(row)
        row.method_id = method.id
        row.position = position
        row.kind = line.kind
        row.words = line.words or (
            links.food.name if links.food else links.used.name if links.used else ""
        )
        row.amount_milli = line.amount
        row.unit = line.unit
        row.size_id = links.size.id if links.size else None
        row.food_id = links.food.id if links.food else None
        row.sub_recipe_id = links.used.id if links.used else None
        row.note = line.note
        row.optional = line.optional and line.kind == "ingredient"
    for line_id, row in old.items():
        if line_id not in kept:
            db.delete(row)
    db.flush()
    return rows


def _save_steps(
    kitchen: Kitchen,
    recipe: Recipe,
    method: RecipeMethod,
    steps_in: list[RecipeStepIn],
    lines: list[RecipeLine],
    old_steps: list[RecipeStep],
) -> None:
    """Replace one method's steps, and their ingredient links. A step sent with `lines` gets
    exactly those, set by hand. A step sent without keeps the links it had (guessed or by hand)
    when the method had a step with the same words before and the line is still there; any
    other link goes with its old step."""
    db = kitchen.db
    old_links: dict[int, list[RecipeStepLine]] = {}
    if old_steps:
        for link in db.scalars(
            select(RecipeStepLine).where(
                RecipeStepLine.step_id.in_([step.id for step in old_steps])
            )
        ):
            old_links.setdefault(link.step_id, []).append(link)
    # The same words, in order: the first unused old step with them.
    by_words: dict[tuple[str, str], list[int]] = {}
    for old_step in old_steps:
        by_words.setdefault((old_step.kind, old_step.text), []).append(old_step.id)
    still_there = {line.id for line in lines if line.kind == "ingredient"}
    carried: list[list[tuple[int, str]]] = []
    # A step sent without `wait` keeps the wait its old self had (a client that knows nothing of
    # waits must not take them off); `"wait": null` takes it off.
    old_waits: dict[int, dict[str, object]] = {
        old_step.id: wait_columns_of(old_step) for old_step in old_steps
    }
    kept_waits: list[dict[str, object] | None] = []
    old_timings: dict[int, dict[str, object]] = {
        old_step.id: timing_columns_of(old_step) for old_step in old_steps
    }
    kept_timings: list[dict[str, object] | None] = []
    for step in steps_in:
        same = by_words.get((step.kind, step.text))
        old_id = same.pop(0) if same else None
        before = old_links.get(old_id, []) if old_id is not None else []
        carried.append([(link.line_id, link.kind) for link in before])
        kept_waits.append(old_waits[old_id] if old_id is not None else None)
        kept_timings.append(old_timings[old_id] if old_id is not None else None)
    if old_steps:
        db.execute(delete(RecipeStep).where(RecipeStep.id.in_([s.id for s in old_steps])))
        for old_step in old_steps:
            db.expunge(old_step)
    db.flush()
    for position, (step, kept, old_wait, old_timing) in enumerate(
        zip(steps_in, carried, kept_waits, kept_timings, strict=True)
    ):
        row = RecipeStep(
            household_id=kitchen.household_id,
            recipe_id=recipe.id,
            method_id=method.id,
            position=position,
            kind=step.kind,
            text=step.text,
            optional=step.optional,
            **(
                old_wait
                if old_wait is not None and "wait" not in step.model_fields_set
                else wait_columns(step.wait)
            ),
            **(
                old_timing
                if old_timing is not None and "timing" not in step.model_fields_set
                else timing_columns(step.timing)
            ),
        )
        db.add(row)
        db.flush()
        if step.lines is not None:
            wanted = [(lines[index].id, "by_hand") for index in step.lines]
        else:
            wanted = [(line_id, kind) for line_id, kind in kept if line_id in still_there]
        for line_id, kind in wanted:
            db.add(
                RecipeStepLine(
                    household_id=kitchen.household_id,
                    step_id=row.id,
                    line_id=line_id,
                    kind=kind,
                )
            )
    db.flush()


def _save_tags(kitchen: Kitchen, recipe: Recipe, names: list[str]) -> None:
    db = kitchen.db
    tags = {
        fold(tag.name): tag
        for tag in db.scalars(select(Tag).where(Tag.household_id == kitchen.household_id))
    }
    wanted: dict[int, Tag] = {}
    for name in names:
        tag = tags.get(fold(name))
        if tag is None:
            tag = Tag(household_id=kitchen.household_id, name=name)
            db.add(tag)
            db.flush()
            tags[fold(name)] = tag
        wanted[tag.id] = tag
    linked = {
        link.tag_id: link
        for link in db.scalars(select(RecipeTag).where(RecipeTag.recipe_id == recipe.id))
    }
    for tag_id, link in linked.items():
        if tag_id not in wanted:
            db.delete(link)
    for tag_id in wanted:
        if tag_id not in linked:
            db.add(RecipeTag(household_id=kitchen.household_id, recipe_id=recipe.id, tag_id=tag_id))
    db.flush()
    drop_unused_tags(kitchen.db, kitchen.household_id)


def drop_unused_tags(db: DbSession, household_id: int) -> None:
    """A tag no recipe has any more is forgotten, so it never comes back as a suggestion."""
    used = select(RecipeTag.tag_id).where(RecipeTag.household_id == household_id)
    db.execute(delete(Tag).where(Tag.household_id == household_id, Tag.id.not_in(used)))


MADE_AHEAD_COUNTED: dict[str, Literal["weight", "volume"]] = {
    "g": "weight",
    "kg": "weight",
    "ml": "volume",
    "l": "volume",
}


def homemade_food(kitchen: Kitchen, recipe: Recipe) -> Food | None:
    """The recipe's own pantry ingredient, if it has one that still exists."""
    if recipe.homemade_food_id is None:
        return None
    food = kitchen.db.get(Food, recipe.homemade_food_id)
    if food is None or food.household_id != kitchen.household_id or not food_visible(food):
        return None
    return food


def _save_made_ahead(kitchen: Kitchen, recipe: Recipe, body: RecipeIn) -> None:
    """Made ahead (cabledrawer 19 Oct, question 18 and "Decided" 2). On: the recipe gets its own
    pantry ingredient (made once, by the existing ingredient code, so it shows in
    Ingredients' Recent changes with Undo). Off: the link goes and the ingredient stays."""
    if not body.made_ahead:
        recipe.made_ahead = False
        recipe.homemade_food_id = None
        return
    _link_homemade(kitchen, recipe, body.makes.unit if body.makes else None, body.homemade_name)


def _link_homemade(
    kitchen: Kitchen, recipe: Recipe, unit: str | None, homemade_name: str | None
) -> None:
    """Made ahead is on: link the recipe's own pantry ingredient, making it if it has none."""
    recipe.made_ahead = True
    if homemade_food(kitchen, recipe) is not None:
        return
    counted = MADE_AHEAD_COUNTED.get(unit or "") or ("count" if unit else None)
    name = (homemade_name or recipe.name)[:100].strip()
    # Made ahead off, then on again: the ingredient that was kept (with any pantry stock it
    # still has) is linked back, as long as no other recipe has it as its own (cabledrawer 19
    # Oct, R3). Otherwise a name another ingredient has is refused (`name_taken`).
    kept = name_owner(kitchen, name)
    if kept is not None:
        holder = made_ahead_of(kitchen, kept.id)
        if holder is not None and holder.id != recipe.id:
            raise name_taken(name, kept)
        recipe.homemade_food_id = kept.id
        return
    change = make_food(kitchen, name, counted_as=counted, shop_id=suggested_shop(kitchen, name))
    recipe.homemade_food_id = change.food_id


# --- Deleting and Undo ------------------------------------------------------------------------


def _users_of(kitchen: Kitchen, recipe_id: int) -> set[int]:
    """The other recipes with a line that uses this one."""
    return {
        rid
        for rid in kitchen.db.scalars(
            select(RecipeLine.recipe_id).where(RecipeLine.sub_recipe_id == recipe_id)
        )
        if rid != recipe_id
    }


def remove(kitchen: Kitchen, recipe: Recipe) -> Change:
    """Delete a recipe: hidden at once, gone for good after the undo window. Lines of other
    recipes that use it keep their words and say "recipe removed"."""
    recipe.removed_at = utcnow()
    bump_recipes_by(kitchen, _users_of(kitchen, recipe.id))
    return record(
        kitchen,
        "recipe_removed",
        f"Deleted {recipe.name}",
        None,
        # The name too: the summary says it, and a purge removes the recipe's own row, so the
        # report scrubber reads the name from here (fix4, review r3).
        {"recipe_id": recipe.id, "name": recipe.name},
    )


def undo_removal(kitchen: Kitchen, change: Change) -> Change:
    """Undo a delete: the recipe comes back, and the lines that used it are linked again
    (they never lost the link)."""
    data = change.undo_data or {}
    recipe = kitchen.db.get(Recipe, data.get("recipe_id", 0))
    if recipe is None or recipe.household_id != kitchen.household_id:
        raise too_old(kitchen.household.undo_days)
    # While it was deleted, recipes that use it (or ones it uses) may have been changed so
    # that bringing it back would make a loop: the same check as a save, with the same words.
    picks = []
    for line in kitchen.db.scalars(
        select(RecipeLine)
        .where(RecipeLine.recipe_id == recipe.id, RecipeLine.sub_recipe_id.is_not(None))
        .order_by(RecipeLine.position)
    ):
        used = kitchen.db.get(Recipe, line.sub_recipe_id or 0)
        if used is not None and used.removed_at is None:
            picks.append((line.position, used))
    check_loops(kitchen, recipe, picks, restoring=True)
    recipe.removed_at = None
    bump_recipes_by(kitchen, _users_of(kitchen, recipe.id))
    undo = record(
        kitchen,
        "undo",
        f"Undid: {change.summary}",
        None,
        {
            "result": "done",
            "message": f"{recipe.name} is back in Recipes.",
            "recipe_id": recipe.id,
            "undoes_kind": change.kind,
            "undoes_at": as_utc(change.at).isoformat(),
        },
    )
    undo.undoes_change_id = change.id
    change.undone_by_change_id = undo.id
    kitchen.db.flush()
    return undo


def _import_to_undo(kitchen: Kitchen, data: dict[str, Any]) -> Recipe | None:
    """The recipe an import's Undo would take back: this household's, and still there."""
    recipe = kitchen.db.get(Recipe, data.get("recipe_id", 0))
    if (
        recipe is None
        or recipe.household_id != kitchen.household_id
        or recipe.removed_at is not None
    ):
        return None
    return recipe


def check_import_undo(kitchen: Kitchen, data: dict[str, Any]) -> None:
    """Before an Undo of a Save from a draft does anything: if it would bring the draft back
    and the household already has 50 drafts, refuse the whole Undo (nothing is half undone)."""
    from mealwright import drafts

    if data.get("draft") and _import_to_undo(kitchen, data) is not None:
        drafts.make_room(kitchen)


def undo_import(kitchen: Kitchen, data: dict[str, Any], tally: Tally) -> str | None:
    """Undo of an import takes the recipe back: it is hidden like a deleted one (and deleted
    for good after the undo window, photo and all). Its new ingredients and other names are
    taken back by the same Undo (`undo_foods`). If the recipe was saved from a draft, the draft
    comes back too, with its choices and photo (spec section 6, question 36); returns the
    sentence that says so."""
    from mealwright import drafts

    recipe = _import_to_undo(kitchen, data)
    # The sections the same save made their own recipes (F190) go with it: one Undo. They are
    # taken back even if the main recipe was deleted since (they would be left behind alone).
    taken = False
    for section_id in data.get("section_recipe_ids", []):
        section = _import_to_undo(kitchen, {"recipe_id": section_id})
        if section is not None:
            section.removed_at = utcnow()
            bump_recipes_by(kitchen, _users_of(kitchen, section.id))
            taken = True
    if recipe is None:
        if taken:
            tally.done += 1
        else:
            tally.skipped += 1  # already deleted, or gone
        return None
    recipe.removed_at = utcnow()
    bump_recipes_by(kitchen, _users_of(kitchen, recipe.id))
    tally.done += 1
    saved = data.get("draft")
    return drafts.bring_back(kitchen, recipe.id, saved) if saved else None


def purge_removed_recipes(db: DbSession, household: Household, now: datetime | None = None) -> int:
    """Delete recipes removed longer ago than the undo window, entirely (a little past it,
    so a delete can't vanish while its Undo is still offered). Lines of other recipes that
    used one lose the link and keep their words; planned meals keep its name (cabledrawer 26 Oct).
    Returns how many went."""
    from datetime import timedelta

    from mealwright.shopping import lock_db

    now = now or utcnow()
    cutoff = now - undo_window(household) - timedelta(hours=1)
    lock_db(db, household)
    ids = list(
        db.scalars(
            select(Recipe.id).where(
                Recipe.household_id == household.id,
                Recipe.removed_at.is_not(None),
                Recipe.removed_at < cutoff,
            )
        )
    )
    if not ids:
        db.commit()
        return 0
    users = set(
        db.scalars(select(RecipeLine.recipe_id).where(RecipeLine.sub_recipe_id.in_(ids)))
    ) - set(ids)
    bump_recipes(db, household.id, users, None, "Mealwright")
    db.execute(
        update(RecipeLine).where(RecipeLine.sub_recipe_id.in_(ids)).values(sub_recipe_id=None)
    )
    # Its name as it is now (it may have been renamed since it was planned).
    db.execute(
        update(MealItem)
        .where(MealItem.recipe_id.in_(ids), MealItem.household_id == household.id)
        .values(
            name=select(Recipe.name).where(Recipe.id == MealItem.recipe_id).scalar_subquery(),
            recipe_id=None,
        )
    )
    # A link from another household's meal was never valid: it goes, and takes no name with it.
    db.execute(delete(MealItem).where(MealItem.recipe_id.in_(ids)))
    events.note_plan(db, household.id)  # planned meals show the recipe's name only now
    keys = list(db.scalars(select(RecipePhoto.file_key).where(RecipePhoto.recipe_id.in_(ids))))
    if keys:
        delete_after_commit(db, household.id, keys)  # the files, once this is committed
    db.execute(
        delete(RecipeStepLine).where(
            RecipeStepLine.step_id.in_(select(RecipeStep.id).where(RecipeStep.recipe_id.in_(ids)))
        )
    )
    for table in (RecipeLine, RecipeStep, RecipeTag, RecipePhoto):
        db.execute(delete(table).where(table.recipe_id.in_(ids)))
    db.execute(delete(Recipe).where(Recipe.id.in_(ids)))
    drop_unused_tags(db, household.id)
    db.commit()
    return len(ids)


def drop_waiting_photos(db: DbSession, household: Household, now: datetime | None = None) -> int:
    """Delete uploads that no recipe took within a day (cabledrawer 20 Oct), and files in the
    household's photo folder that have no record (after a crash, say). Returns how many
    uploads went. Local only: nothing here makes a network connection."""
    from datetime import timedelta

    from mealwright.photos import WAITING_HOURS, store_of, sweep_files
    from mealwright.photos import log as photos_log
    from mealwright.shopping import lock_db

    now = now or utcnow()
    lock_db(db, household)
    old = list(
        db.scalars(
            select(RecipePhoto).where(
                RecipePhoto.household_id == household.id,
                RecipePhoto.recipe_id.is_(None),
                RecipePhoto.draft_id.is_(None),  # a draft's photo goes with the draft
                RecipePhoto.added_at < now - timedelta(hours=WAITING_HOURS),
            )
        )
    )
    for photo in old:
        delete_photo(db, photo)
    db.commit()
    known = set(
        db.scalars(select(RecipePhoto.file_key).where(RecipePhoto.household_id == household.id))
    )
    db.commit()
    try:
        sweep_files(store_of(db), household.id, known, now.timestamp())
    except OSError as e:
        # The folder couldn't be read. The error's text carries its path, so only the kind of
        # error is logged; the next hourly run tries again.
        photos_log.warning(
            "Couldn't sweep the photo files with no record (will try again within the hour): %s",
            type(e).__name__,
        )
    return len(old)


# --- Ingredients that recipes use -------------------------------------------------------------


def recipe_counts(kitchen: Kitchen) -> dict[int, int]:
    """Ingredient id → how many recipes (not deleted) have a line for it."""
    rows = kitchen.db.execute(
        select(RecipeLine.food_id, func.count(func.distinct(RecipeLine.recipe_id)))
        .join(Recipe, Recipe.id == RecipeLine.recipe_id)
        .where(
            Recipe.household_id == kitchen.household_id,
            Recipe.removed_at.is_(None),
            RecipeLine.food_id.is_not(None),
        )
        .group_by(RecipeLine.food_id)
    )
    return {food_id: count for food_id, count in rows if food_id is not None}


def recipes_using(kitchen: Kitchen, food_id: int) -> list[Ref]:
    """The recipes (not deleted) that have a line for this ingredient, A to Z."""
    rows = kitchen.db.execute(
        select(Recipe.id, Recipe.name)
        .join(RecipeLine, RecipeLine.recipe_id == Recipe.id)
        .where(
            Recipe.household_id == kitchen.household_id,
            Recipe.removed_at.is_(None),
            RecipeLine.food_id == food_id,
        )
        .distinct()
    )
    return sorted((Ref(id=i, name=n) for i, n in rows), key=lambda r: (fold(r.name), r.id))


def made_ahead_of(kitchen: Kitchen, food_id: int) -> Recipe | None:
    """A recipe (not deleted) whose own pantry ingredient this is."""
    return kitchen.db.scalar(
        select(Recipe)
        .where(
            Recipe.household_id == kitchen.household_id,
            Recipe.removed_at.is_(None),
            Recipe.made_ahead.is_(True),
            Recipe.homemade_food_id == food_id,
        )
        .order_by(Recipe.id)
        .limit(1)
    )


# --- Describing -------------------------------------------------------------------------------


def _float(milli: int | None) -> float | None:
    return None if milli is None else milli / 1000


def makes_out(recipe: Recipe) -> MakesOut | None:
    if recipe.makes_milli is None or recipe.makes_unit is None:
        return None
    return MakesOut(
        amount=recipe.makes_milli / 1000,
        amount_text=cast(str, amount_text(recipe.makes_milli)),
        unit=recipe.makes_unit,
    )


def photo_view(photo: RecipePhoto) -> PhotoOut:
    url = f"/api/v1/recipes/photos/{photo.id}"
    return PhotoOut(
        id=photo.id,
        width=photo.width,
        height=photo.height,
        url=f"{url}/large",
        list_width=photo.list_width,
        list_height=photo.list_height,
        list_url=f"{url}/list",
    )


def photo_out(db: DbSession, recipe_id: int) -> PhotoOut | None:
    photo = db.scalar(select(RecipePhoto).where(RecipePhoto.recipe_id == recipe_id))
    return photo_view(photo) if photo else None


def tags_of(kitchen: Kitchen, recipe_ids: list[int]) -> dict[int, list[str]]:
    found: dict[int, list[str]] = {i: [] for i in recipe_ids}
    for recipe_id, name in kitchen.db.execute(
        select(RecipeTag.recipe_id, Tag.name)
        .join(Tag, Tag.id == RecipeTag.tag_id)
        .where(RecipeTag.recipe_id.in_(recipe_ids))
    ):
        found[recipe_id].append(name)
    for names in found.values():
        names.sort(key=fold)
    return found


def site_of(url: str) -> str:
    """The web address's site, as shown: "https://www.bbcgoodfood.com/x" → "bbcgoodfood.com"."""
    host = urlsplit(url).hostname or ""
    return host.removeprefix("www.")


def source_out(recipe: Recipe) -> SourceOut | None:
    if recipe.source_url is None:
        return None
    return SourceOut(
        url=recipe.source_url,
        site=site_of(recipe.source_url),
        imported_at=as_utc(recipe.imported_at or recipe.created_at),
        author=recipe.source_author,
    )


def wait_columns(wait: StepWaitIn | None) -> dict[str, object]:
    """The step's wait columns for a save: all empty when it doesn't wait."""
    if wait is None:
        return {
            "wait_kind": None,
            "wait_min_minutes": None,
            "wait_max_minutes": None,
            "wait_overnight": False,
        }
    return {
        "wait_kind": wait.kind,
        "wait_min_minutes": wait.min_minutes,
        "wait_max_minutes": wait.max_minutes,
        "wait_overnight": wait.overnight,
    }


def wait_columns_of(step: RecipeStep) -> dict[str, object]:
    """The wait columns a step has now, to carry over to its replacement."""
    return {
        "wait_kind": step.wait_kind,
        "wait_min_minutes": step.wait_min_minutes,
        "wait_max_minutes": step.wait_max_minutes,
        "wait_overnight": step.wait_overnight,
    }


def timing_columns(timing: StepTimingIn | None) -> dict[str, object]:
    """The columns for what was set by hand for Batch cook: empty means guessed."""
    return {
        "timing_hands": timing.hands if timing else None,
        "timing_minutes": timing.minutes if timing else None,
        "timing_equipment": timing.equipment if timing else None,
    }


def timing_columns_of(step: RecipeStep) -> dict[str, object]:
    """What a step has set by hand now, to carry over to its replacement."""
    return {
        "timing_hands": step.timing_hands,
        "timing_minutes": step.timing_minutes,
        "timing_equipment": step.timing_equipment,
    }


def timing_out(step: RecipeStep) -> StepTimingOut | None:
    timing = step_timings.of_step(step)
    if timing is None:
        return None
    return StepTimingOut(
        hands=timing.hands,
        minutes=timing.minutes,
        equipment=timing.equipment,
        hands_guessed=timing.hands_guessed,
        minutes_guessed=timing.minutes_guessed,
        equipment_guessed=timing.equipment_guessed,
    )


def wait_out(wait: step_waits.Wait | None) -> StepWaitOut | None:
    if wait is None:
        return None
    return StepWaitOut(
        kind=wait.kind,
        min_minutes=wait.min_minutes,
        max_minutes=wait.max_minutes,
        overnight=wait.overnight,
    )


def _method_out(
    kitchen: Kitchen, rows: list[RecipeLine], step_rows: list[RecipeStep]
) -> tuple[list[RecipeLineOut], list[RecipeStepOut]]:
    """One method's lines and steps, as the recipe page reads them."""
    db = kitchen.db
    foods = {
        food.id: food
        for food in db.scalars(
            select(Food).where(Food.id.in_({r.food_id for r in rows if r.food_id}))
        )
    }
    other_names: dict[int, list[str]] = {}
    for name in db.scalars(
        select(FoodName)
        .where(FoodName.food_id.in_(foods.keys()))
        .order_by(FoodName.name, FoodName.id)
    ):
        other_names.setdefault(name.food_id, []).append(name.name)
    subs = {
        sub.id: sub
        for sub in db.scalars(
            select(Recipe).where(Recipe.id.in_({r.sub_recipe_id for r in rows if r.sub_recipe_id}))
        )
    }
    sizes = {
        size.id: size
        for size in db.scalars(
            select(FoodSize).where(FoodSize.id.in_({r.size_id for r in rows if r.size_id}))
        )
    }
    lines = []
    for row in rows:
        food = foods.get(row.food_id) if row.food_id else None
        if food is not None and not food_visible(food):
            food = None
        sub = subs.get(row.sub_recipe_id) if row.sub_recipe_id else None
        size = sizes.get(row.size_id) if row.size_id else None
        link: Literal["ingredient", "recipe", "recipe_removed", "none"] | None
        if row.kind == "heading":
            link = None
        elif food is not None:
            link = "ingredient"
        elif sub is not None:
            link = "recipe_removed" if sub.removed_at else "recipe"
        else:
            link = "none"
        lines.append(
            RecipeLineOut(
                id=row.id,
                kind=cast(Literal["ingredient", "heading"], row.kind),
                words=row.words,
                amount=_float(row.amount_milli),
                amount_text=amount_text(row.amount_milli),
                unit=row.unit,
                size=SizeRef(id=size.id, name=size.name, plural=size.plural) if size else None,
                food=(
                    LineFoodRef(
                        id=food.id, name=food.name, other_names=other_names.get(food.id, [])
                    )
                    if food
                    else None
                ),
                recipe=Ref(id=sub.id, name=sub.name) if sub else None,
                link=link,
                note=row.note,
                optional=row.optional,
            )
        )
    position_of = {line.id: index for index, line in enumerate(lines)}
    step_lines: dict[int, list[StepLineOut]] = {}
    if step_rows:
        for uses in db.scalars(
            select(RecipeStepLine)
            .where(RecipeStepLine.step_id.in_([s.id for s in step_rows]))
            .order_by(RecipeStepLine.id)
        ):
            if uses.line_id in position_of:
                step_lines.setdefault(uses.step_id, []).append(
                    StepLineOut(
                        line_id=uses.line_id,
                        line=position_of[uses.line_id],
                        kind=cast(Literal["guessed", "by_hand"], uses.kind),
                    )
                )
    steps = [
        RecipeStepOut(
            id=s.id,
            kind=cast(Literal["step", "heading"], s.kind),
            text=s.text,
            optional=s.optional,
            wait=wait_out(step_waits.of_step(s)),
            timing=timing_out(s),
            lines=sorted(step_lines.get(s.id, []), key=lambda uses: uses.line),
        )
        for s in step_rows
    ]
    return lines, steps


def recipe_out(kitchen: Kitchen, recipe: Recipe) -> RecipeOut:
    db = kitchen.db
    all_methods = methods.methods_of(db, recipe.id)
    rows = _rows_of(db, RecipeLine, recipe, all_methods, 0)
    step_rows = _rows_of(db, RecipeStep, recipe, all_methods, 0)
    lines, steps = _method_out(kitchen, rows, step_rows)
    first_wait = step_waits.total(step_rows)
    method_refs: list[MethodRef] = []
    second: SecondMethodOut | None = None
    last = methods.used_last(all_methods)
    for position, method in enumerate(all_methods):
        method_rows = rows if position == 0 else _rows_of(db, RecipeLine, recipe, all_methods, 1)
        method_steps = (
            step_rows if position == 0 else _rows_of(db, RecipeStep, recipe, all_methods, 1)
        )
        wait = first_wait if position == 0 else step_waits.total(method_steps)
        ref = MethodRef(
            id=method.id,
            name=method.name,
            time_minutes=recipe.time_minutes if position == 0 else method.time_minutes,
            wait=wait_out(wait),
            used_last=len(all_methods) > 1 and method is last,
        )
        method_refs.append(ref)
        if position == 1:
            second_lines, second_steps = _method_out(kitchen, method_rows, method_steps)
            second = SecondMethodOut(**ref.model_dump(), lines=second_lines, steps=second_steps)
    homemade = homemade_food(kitchen, recipe)
    used_by = db.execute(
        select(Recipe.id, Recipe.name)
        .join(RecipeLine, RecipeLine.recipe_id == Recipe.id)
        .where(
            Recipe.household_id == kitchen.household_id,
            Recipe.removed_at.is_(None),
            RecipeLine.sub_recipe_id == recipe.id,
        )
        .distinct()
    )
    return RecipeOut(
        id=recipe.id,
        name=recipe.name,
        description=recipe.description,
        time_minutes=recipe.time_minutes,
        wait=wait_out(first_wait),
        serves=recipe.serves,
        makes=makes_out(recipe),
        made_ahead=recipe.made_ahead,
        homemade=Ref(id=homemade.id, name=homemade.name) if homemade else None,
        tags=tags_of(kitchen, [recipe.id])[recipe.id],
        nutrition=NutritionOut(
            kcal=_float(recipe.kcal_milli),
            protein=_float(recipe.protein_milli),
            carbs=_float(recipe.carbs_milli),
            fat=_float(recipe.fat_milli),
            fibre=_float(recipe.fibre_milli),
            possibly_out_of_date=nutrition_out_of_date(recipe),
        ),
        lines=lines,
        steps=steps,
        methods=method_refs,
        second_method=second,
        source_note=recipe.source_note,
        source=source_out(recipe),
        photo=photo_out(db, recipe.id),
        used_by=sorted((Ref(id=i, name=n) for i, n in used_by), key=lambda r: (fold(r.name), r.id)),
        version=recipe.version,
        created_at=as_utc(recipe.created_at),
        updated_at=as_utc(recipe.updated_at),
        updated_by=Who(login_id=recipe.updated_by_login_id, name=recipe.updated_by_name),
    )


def waits_of(db: DbSession, recipe_ids: list[int] | Select[Any]) -> dict[int, StepWaitOut]:
    """All the steps' waits added up, for each of these recipes that has one (M1). A recipe with
    two methods answers for its first (M2): the list shows the recipe's own time."""
    if isinstance(recipe_ids, list) and not recipe_ids:
        return {}
    first = {
        recipe_id: method_id
        for recipe_id, method_id in db.execute(
            select(RecipeMethod.recipe_id, RecipeMethod.id).where(
                RecipeMethod.recipe_id.in_(recipe_ids), RecipeMethod.position == 0
            )
        )
    }
    steps: dict[int, list[RecipeStep]] = {}
    for step in db.scalars(
        select(RecipeStep).where(
            RecipeStep.recipe_id.in_(recipe_ids), RecipeStep.wait_kind.is_not(None)
        )
    ):
        if step.method_id is None or step.method_id == first.get(step.recipe_id):
            steps.setdefault(step.recipe_id, []).append(step)
    found: dict[int, StepWaitOut] = {}
    for recipe_id, rows in steps.items():
        out = wait_out(step_waits.total(rows))
        if out is not None:
            found[recipe_id] = out
    return found


def brief_list(kitchen: Kitchen, recipes: list[Recipe]) -> list[RecipeBrief]:
    ids = [r.id for r in recipes]
    tags = tags_of(kitchen, ids)
    found = methods.of_recipes(kitchen.db, ids)
    # The first method's lines are the recipe's own count (a recipe with two methods has a
    # second set of lines, which the list doesn't count twice).
    counts: dict[int, int] = {}
    optional: dict[int, int] = {}
    for recipe_id, method_id, is_optional in kitchen.db.execute(
        select(RecipeLine.recipe_id, RecipeLine.method_id, RecipeLine.optional).where(
            RecipeLine.recipe_id.in_(ids), RecipeLine.kind == "ingredient"
        )
    ):
        # How many are Optional counts every method: the plan's question asks after the pick.
        if is_optional:
            optional[recipe_id] = optional.get(recipe_id, 0) + 1
        if method_id is not None and found.get(recipe_id) and method_id != found[recipe_id][0].id:
            continue
        counts[recipe_id] = counts.get(recipe_id, 0) + 1
    photos = {
        p.recipe_id: photo_view(p)
        for p in kitchen.db.scalars(select(RecipePhoto).where(RecipePhoto.recipe_id.in_(ids)))
    }
    waits = waits_of(kitchen.db, ids)
    return [
        RecipeBrief(
            id=r.id,
            name=r.name,
            description=r.description,
            time_minutes=r.time_minutes,
            wait=waits.get(r.id),
            serves=r.serves,
            makes=makes_out(r),
            made_ahead=r.made_ahead,
            tags=tags[r.id],
            ingredient_count=counts.get(r.id, 0),
            optional_count=optional.get(r.id, 0),
            method_count=max(len(found.get(r.id, [])), 1),
            photo=photos.get(r.id),
            version=r.version,
            updated_at=as_utc(r.updated_at),
        )
        for r in recipes
    ]


def conflict(recipe: Recipe) -> Problem:
    """Someone else saved the recipe after this editor opened it."""
    who = recipe.updated_by_name or "Someone"
    return Problem(
        status.HTTP_409_CONFLICT,
        "recipe_changed",
        f"{who} changed this recipe after you opened it.",
        changed_by={"login_id": recipe.updated_by_login_id, "name": recipe.updated_by_name},
        changed_at=as_utc(recipe.updated_at).isoformat(),
        version=recipe.version,
    )
