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
from typing import Literal, cast

from fastapi import status
from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session as DbSession

from mealwright.api.v1.context import Kitchen
from mealwright.api.v1.recipe_schemas import (
    Blocked,
    MakesOut,
    NutritionOut,
    PhotoOut,
    RecipeBrief,
    RecipeIn,
    RecipeLineOut,
    RecipeOut,
    RecipeStepOut,
    SizeRef,
    amount_text,
)
from mealwright.api.v1.schemas import Ref, Who
from mealwright.errors import Problem, not_found
from mealwright.foods import make_food
from mealwright.foods import visible as food_visible
from mealwright.history import as_utc, record
from mealwright.household import undo_window
from mealwright.models import (
    Change,
    Food,
    FoodSize,
    Household,
    Recipe,
    RecipeLine,
    RecipePhoto,
    RecipeStep,
    RecipeTag,
    Tag,
    utcnow,
)
from mealwright.names import fold

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


# --- The loop guard (cabledrawer 19 Oct, questions 19 and 20) --------------------------------------


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


def path_between(graph: dict[int, set[int]], start: int, goal: int) -> list[int] | None:
    """The shortest chain of "uses" from `start` to `goal` ([start, …, goal]), or None."""
    parent: dict[int, int | None] = {start: None}
    queue = deque([start])
    while queue:
        here = queue.popleft()
        if here == goal:
            chain = []
            step: int | None = here
            while step is not None:
                chain.append(step)
                step = parent[step]
            return chain[::-1]
        for nxt in sorted(graph.get(here, ())):
            if nxt not in parent:
                parent[nxt] = here
                queue.append(nxt)
    return None


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
    graph = uses_graph(kitchen)
    names = {rid: r.name for rid, r in live_recipes(kitchen).items()}
    blocked = [
        Blocked(
            id=recipe.id,
            name=recipe.name,
            reason=f"A recipe {CANT} use itself.",
            chain=[recipe.name],
        )
    ]
    for other_id in names:
        if other_id == recipe.id:
            continue
        chain = path_between(graph, other_id, recipe.id)
        if chain is not None:
            words = [names[i] for i in chain]
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
    graph = uses_graph(kitchen, also_live=recipe.id if restoring else None)
    for index, used in picks:
        if used.id == recipe.id:
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "recipe_self",
                f"A recipe {CANT} use itself.",
                line=index,
                recipe_id=used.id,
            )
        chain = path_between(graph, used.id, recipe.id)
        if chain is not None:
            names = [
                (kitchen.db.get(Recipe, i) or used).name for i in chain
            ]  # used … recipe (its stored name)
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


def _resolve(kitchen: Kitchen, recipe: Recipe | None, body: RecipeIn) -> list[_Resolved]:
    from mealwright.foods import find as find_food

    db = kitchen.db
    existing = {}
    if recipe is not None:
        existing = {
            line.id: line
            for line in db.scalars(select(RecipeLine).where(RecipeLine.recipe_id == recipe.id))
        }
    resolved: list[_Resolved] = []
    for index, line in enumerate(body.lines):
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


def save(kitchen: Kitchen, recipe: Recipe | None, body: RecipeIn) -> Recipe:
    """Create the recipe, or replace everything in it (the caller holds the household's
    lock, and has checked the version). Adds 1 to the version."""
    db = kitchen.db
    resolved = _resolve(kitchen, recipe, body)
    check_loops(
        kitchen,
        recipe,
        [(i, r.used) for i, r in enumerate(resolved) if r.used is not None],
    )
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
    recipe.time_minutes = body.time_minutes
    recipe.serves = body.serves
    recipe.makes_milli = body.makes.amount if body.makes else None
    recipe.makes_unit = body.makes.unit if body.makes else None
    recipe.source_note = body.source_note
    recipe.kcal_milli = _milli(body.nutrition.kcal)
    recipe.protein_milli = _milli(body.nutrition.protein)
    recipe.carbs_milli = _milli(body.nutrition.carbs)
    recipe.fat_milli = _milli(body.nutrition.fat)
    recipe.fibre_milli = _milli(body.nutrition.fibre)
    recipe.version += 1
    recipe.updated_at = now
    recipe.updated_by_login_id = kitchen.login.id
    recipe.updated_by_name = name
    db.flush()
    # Remember the request's Idempotency-Key, the way every other write does, so a retry is
    # recognised. First, so the made-ahead ingredient's own change below carries no key.
    kitchen.key_once = True
    record(
        kitchen,
        "recipe_created" if creating else "recipe_saved",
        f"Saved {recipe.name}",
        None,
        {"recipe_id": recipe.id},
    )

    _save_lines(kitchen, recipe, body, resolved)
    db.execute(delete(RecipeStep).where(RecipeStep.recipe_id == recipe.id))
    for position, step in enumerate(body.steps):
        db.add(
            RecipeStep(
                household_id=kitchen.household_id,
                recipe_id=recipe.id,
                position=position,
                kind=step.kind,
                text=step.text,
            )
        )
    _save_tags(kitchen, recipe, body.tags)
    _save_made_ahead(kitchen, recipe, body)
    db.flush()
    return recipe


def _save_lines(
    kitchen: Kitchen, recipe: Recipe, body: RecipeIn, resolved: list[_Resolved]
) -> None:
    db = kitchen.db
    old = {
        line.id: line
        for line in db.scalars(select(RecipeLine).where(RecipeLine.recipe_id == recipe.id))
    }
    kept: set[int] = set()
    for position, (line, links) in enumerate(zip(body.lines, resolved, strict=True)):
        row = old.get(line.id) if line.id is not None else None
        if row is None:
            row = RecipeLine(household_id=kitchen.household_id, recipe_id=recipe.id)
            db.add(row)
        else:
            kept.add(row.id)
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
    for line_id, row in old.items():
        if line_id not in kept:
            db.delete(row)
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
    recipe.made_ahead = True
    if homemade_food(kitchen, recipe) is not None:
        return
    unit = body.makes.unit if body.makes else None
    counted = MADE_AHEAD_COUNTED.get(unit or "") or ("count" if unit else None)
    name = (body.homemade_name or recipe.name)[:100].strip()
    change = make_food(kitchen, name, counted_as=counted)
    recipe.homemade_food_id = change.food_id


# --- Deleting and Undo ------------------------------------------------------------------------


def remove(kitchen: Kitchen, recipe: Recipe) -> Change:
    """Delete a recipe: hidden at once, gone for good after the undo window. Lines of other
    recipes that use it keep their words and say "recipe removed"."""
    recipe.removed_at = utcnow()
    return record(
        kitchen,
        "recipe_removed",
        f"Deleted {recipe.name}",
        None,
        {"recipe_id": recipe.id},
    )


def undo_removal(kitchen: Kitchen, change: Change) -> Change:
    """Undo a delete: the recipe comes back, and the lines that used it are linked again
    (they never lost the link)."""
    data = change.undo_data or {}
    recipe = kitchen.db.get(Recipe, data.get("recipe_id", 0))
    if recipe is None or recipe.household_id != kitchen.household_id:
        raise Problem(status.HTTP_410_GONE, "too_old", "That's too long ago to undo.")
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


def purge_removed_recipes(db: DbSession, household: Household, now: datetime | None = None) -> int:
    """Delete recipes removed longer ago than the undo window, entirely (a little past it,
    so a delete can't vanish while its Undo is still offered). Lines of other recipes that
    used one lose the link and keep their words. Returns how many went."""
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
    db.execute(
        update(RecipeLine).where(RecipeLine.sub_recipe_id.in_(ids)).values(sub_recipe_id=None)
    )
    for table in (RecipeLine, RecipeStep, RecipeTag, RecipePhoto):
        db.execute(delete(table).where(table.recipe_id.in_(ids)))
    db.execute(delete(Recipe).where(Recipe.id.in_(ids)))
    drop_unused_tags(db, household.id)
    db.commit()
    return len(ids)


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


def photo_out(db: DbSession, recipe_id: int) -> PhotoOut | None:
    photo = db.scalar(select(RecipePhoto).where(RecipePhoto.recipe_id == recipe_id))
    return PhotoOut(id=photo.id, width=photo.width, height=photo.height) if photo else None


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


def recipe_out(kitchen: Kitchen, recipe: Recipe) -> RecipeOut:
    db = kitchen.db
    rows = list(
        db.scalars(
            select(RecipeLine)
            .where(RecipeLine.recipe_id == recipe.id)
            .order_by(RecipeLine.position, RecipeLine.id)
        )
    )
    foods = {
        food.id: food
        for food in db.scalars(
            select(Food).where(Food.id.in_({r.food_id for r in rows if r.food_id}))
        )
    }
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
                food=Ref(id=food.id, name=food.name) if food else None,
                recipe=Ref(id=sub.id, name=sub.name) if sub else None,
                link=link,
                note=row.note,
            )
        )
    steps = [
        RecipeStepOut(id=s.id, kind=cast(Literal["step", "heading"], s.kind), text=s.text)
        for s in db.scalars(
            select(RecipeStep)
            .where(RecipeStep.recipe_id == recipe.id)
            .order_by(RecipeStep.position, RecipeStep.id)
        )
    ]
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
        ),
        lines=lines,
        steps=steps,
        source_note=recipe.source_note,
        photo=photo_out(db, recipe.id),
        used_by=sorted((Ref(id=i, name=n) for i, n in used_by), key=lambda r: (fold(r.name), r.id)),
        version=recipe.version,
        created_at=as_utc(recipe.created_at),
        updated_at=as_utc(recipe.updated_at),
        updated_by=Who(login_id=recipe.updated_by_login_id, name=recipe.updated_by_name),
    )


def brief_list(kitchen: Kitchen, recipes: list[Recipe]) -> list[RecipeBrief]:
    ids = [r.id for r in recipes]
    tags = tags_of(kitchen, ids)
    counts = {
        recipe_id: count
        for recipe_id, count in kitchen.db.execute(
            select(RecipeLine.recipe_id, func.count())
            .where(RecipeLine.recipe_id.in_(ids), RecipeLine.kind == "ingredient")
            .group_by(RecipeLine.recipe_id)
        )
    }
    photos = {
        p.recipe_id: PhotoOut(id=p.id, width=p.width, height=p.height)
        for p in kitchen.db.scalars(select(RecipePhoto).where(RecipePhoto.recipe_id.in_(ids)))
    }
    return [
        RecipeBrief(
            id=r.id,
            name=r.name,
            description=r.description,
            time_minutes=r.time_minutes,
            serves=r.serves,
            makes=makes_out(r),
            made_ahead=r.made_ahead,
            tags=tags[r.id],
            ingredient_count=counts.get(r.id, 0),
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
