"""Managing tags: rename, and merge one tag into another with Undo (spec "Decided for 0.8.0",
cabledrawer 9 Nov). A tag is a name the household made up (`Tag`), linked to recipes
(`RecipeTag`); a tag no recipe has stops showing. A rename is not in Recent changes, like a
shop's or a place's rename; a merge is, with its own Undo."""

from fastapi import status
from sqlalchemy import delete, select

from mealwright.api.v1.context import Kitchen
from mealwright.errors import Problem, not_found
from mealwright.history import as_utc, bump_recipes_by, record
from mealwright.models import Change, Recipe, RecipeTag, Tag
from mealwright.names import fold

KIND = "tags_merged"


def count_of(kitchen: Kitchen, tag_id: int) -> int:
    """How many recipes show this tag (not the deleted ones)."""
    return len(
        kitchen.db.scalars(
            select(RecipeTag.recipe_id)
            .join(Recipe, Recipe.id == RecipeTag.recipe_id)
            .where(RecipeTag.tag_id == tag_id, Recipe.removed_at.is_(None))
        ).all()
    )


def find(kitchen: Kitchen, tag_id: int) -> Tag:
    tag = kitchen.db.get(Tag, tag_id)
    if tag is None or tag.household_id != kitchen.household_id:
        raise not_found("That tag")
    return tag


def recipes_with(kitchen: Kitchen, tag_id: int) -> list[int]:
    """The recipes with this tag, the deleted ones too (their link waits for Undo)."""
    return list(
        kitchen.db.scalars(
            select(RecipeTag.recipe_id)
            .where(RecipeTag.household_id == kitchen.household_id, RecipeTag.tag_id == tag_id)
            .order_by(RecipeTag.recipe_id)
        )
    )


def _exists(name: str, other: Tag) -> Problem:
    return Problem(
        status.HTTP_409_CONFLICT,
        "tag_exists",
        f"There’s already a tag called {other.name}. Use Merge into… to join them.",
        tag={"id": other.id, "name": other.name},
    )


def rename(kitchen: Kitchen, tag: Tag, name: str) -> Tag:
    """A name another tag has (ignoring case and accents) is a 409 `tag_exists` that carries
    that tag: it is refused, and the person is pointed to Merge."""
    for other in kitchen.db.scalars(select(Tag).where(Tag.household_id == kitchen.household_id)):
        if other.id != tag.id and fold(other.name) == fold(name):
            raise _exists(name, other)
    tag.name = name
    bump_recipes_by(kitchen, recipes_with(kitchen, tag.id))
    return tag


def merge(kitchen: Kitchen, source: Tag, target: Tag) -> Change:
    """Every recipe with `source` gets `target` (a recipe with both keeps one), and `source`
    goes. The change keeps which recipes had `source` and which of them only gained `target`
    here, so Undo puts back exactly that."""
    if source.id == target.id:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT, "same_tag", "Pick a different tag to merge into."
        )
    db = kitchen.db
    had = recipes_with(kitchen, source.id)
    already = set(recipes_with(kitchen, target.id))
    gained = [recipe_id for recipe_id in had if recipe_id not in already]
    for recipe_id in gained:
        db.add(RecipeTag(household_id=kitchen.household_id, recipe_id=recipe_id, tag_id=target.id))
    db.execute(delete(RecipeTag).where(RecipeTag.tag_id == source.id))
    name, into = source.name, target.name
    db.execute(delete(Tag).where(Tag.id == source.id))
    bump_recipes_by(kitchen, had)
    db.flush()
    return record(
        kitchen,
        KIND,
        f"Merged tag {name} into {into}",
        None,
        {
            "source": {"id": source.id, "name": name},
            "target": {"id": target.id, "name": into},
            "had": had,
            "gained": gained,
        },
    )


def undo_merge(kitchen: Kitchen, change: Change) -> Change:
    """The merged tag comes back with the recipes that had it. The recipes that only got the
    other tag from the merge lose it again (unless it has gone already). If a tag with the old
    name exists again, it is refused: rename or merge that one first."""
    db = kitchen.db
    data = change.undo_data or {}
    source, target = data["source"], data["target"]
    for other in db.scalars(select(Tag).where(Tag.household_id == kitchen.household_id)):
        if fold(other.name) == fold(source["name"]):
            raise Problem(
                status.HTTP_409_CONFLICT,
                "tag_exists",
                f"There’s already a tag called {other.name}. Rename or merge it first.",
                tag={"id": other.id, "name": other.name},
            )
    db.add(Tag(id=source["id"], household_id=kitchen.household_id, name=source["name"]))
    db.flush()
    alive = set(
        db.scalars(
            select(Recipe.id).where(
                Recipe.household_id == kitchen.household_id, Recipe.id.in_(data["had"])
            )
        )
    )
    for recipe_id in data["had"]:
        if recipe_id in alive:
            db.add(
                RecipeTag(
                    household_id=kitchen.household_id, recipe_id=recipe_id, tag_id=source["id"]
                )
            )
    gained = [recipe_id for recipe_id in data["gained"] if recipe_id in alive]
    if gained:
        db.execute(
            delete(RecipeTag).where(
                RecipeTag.tag_id == target["id"], RecipeTag.recipe_id.in_(gained)
            )
        )
    bump_recipes_by(kitchen, list(alive))
    undo = record(
        kitchen,
        "undo",
        f"Undid: {change.summary}",
        None,
        {
            "result": "done",
            "message": f"{source['name']} is back, on the recipes that had it.",
            "undoes_kind": change.kind,
            "undoes_at": as_utc(change.at).isoformat(),
        },
    )
    undo.undoes_change_id = change.id
    change.undone_by_change_id = undo.id
    db.flush()
    return undo
