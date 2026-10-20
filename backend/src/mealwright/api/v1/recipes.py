"""Recipes: list, read, create, save, delete with Undo, tag suggestions and the loop guard
(docs/dev/api-0.4-recipes.md). Online only in 0.4: nothing here touches the shopping sync."""

from typing import Annotated

from fastapi import APIRouter, Query, Response, status
from pydantic import BaseModel
from sqlalchemy import func, select

from mealwright import recipe_list, recipes
from mealwright.api.v1.context import Here
from mealwright.api.v1.recipe_list_schemas import RecipePage
from mealwright.api.v1.recipe_schemas import (
    BlockedList,
    RecipeIn,
    RecipeOut,
    RecipeUpdate,
    TagList,
    TagOut,
)
from mealwright.api.v1.schemas import ChangeOut
from mealwright.auth import SameOrigin
from mealwright.foods import change_out
from mealwright.history import commit, replayed
from mealwright.models import Recipe, RecipeTag, Tag
from mealwright.names import fold
from mealwright.shopping import lock_household

router = APIRouter(tags=["recipes"], dependencies=[SameOrigin])


class RecipeRemoved(BaseModel):
    change: ChangeOut  # carries the Undo (7 days)


@router.get("/recipes")
def list_recipes(
    kitchen: Here,
    limit: Annotated[int, Query(ge=1, le=500)] = 50,
    after: Annotated[str | None, Query(pattern=r"^\d{1,9}$")] = None,
    q: Annotated[str, Query(max_length=100)] = "",
    tag: Annotated[str | None, Query(max_length=40)] = None,
    can_cook_now: bool = False,
) -> RecipePage:
    """Every recipe, A to Z (ignoring case and accents), each with its stock hints.
    `q` searches recipe names, tags and ingredient names (other names too), never the
    method; `tag` keeps one tag; `can_cook_now` keeps recipes with nothing missing. They
    work together. Recipes that were deleted and can still be undone are not listed."""
    return recipe_list.page(
        kitchen,
        q=q,
        tag=tag,
        can_cook_now=can_cook_now,
        start=int(after) if after else 0,
        limit=limit,
    )


@router.get("/recipes/tags")
def suggest_tags(kitchen: Here, q: Annotated[str, Query(max_length=40)] = "") -> TagList:
    """Tags the household uses, for suggestions while typing a tag. A tag that no recipe has
    any more is not listed. Names starting with `q` come first."""
    rows = kitchen.db.execute(
        select(Tag.name, func.count(func.distinct(RecipeTag.recipe_id)))
        .join(RecipeTag, RecipeTag.tag_id == Tag.id)
        .join(Recipe, Recipe.id == RecipeTag.recipe_id)
        .where(Tag.household_id == kitchen.household_id, Recipe.removed_at.is_(None))
        .group_by(Tag.id)
    )
    needle = fold(q.strip())
    found = [
        (0 if fold(name).startswith(needle) else 1, fold(name), TagOut(name=name, recipes=count))
        for name, count in rows
        if needle in fold(name)
    ]
    found.sort(key=lambda item: (item[0], item[1]))
    return TagList(tags=[item[2] for item in found])


@router.post("/recipes", status_code=status.HTTP_201_CREATED)
def create_recipe(body: RecipeIn, kitchen: Here, response: Response) -> RecipeOut:
    """Make a recipe. Only the name is needed. A new recipe serves 4 unless you say
    otherwise. With `made_ahead`, its own pantry ingredient is made too. A retry with the
    same `Idempotency-Key` makes nothing more and answers with the recipe as it is now."""
    lock_household(kitchen)
    earlier = replayed(kitchen)
    if earlier is None:
        recipe = recipes.save(kitchen, None, body)
        earlier = commit(kitchen)
        if earlier is None:
            return recipes.recipe_out(kitchen, recipe)
    response.status_code = status.HTTP_200_OK
    response.headers["Idempotent-Replayed"] = "true"
    return recipes.recipe_out(
        kitchen, recipes.find(kitchen, (earlier.undo_data or {}).get("recipe_id", 0))
    )


@router.get("/recipes/{recipe_id}")
def get_recipe(recipe_id: int, kitchen: Here) -> RecipeOut:
    return recipes.recipe_out(kitchen, recipes.find(kitchen, recipe_id))


@router.put("/recipes/{recipe_id}")
def update_recipe(
    recipe_id: int, body: RecipeUpdate, kitchen: Here, response: Response
) -> RecipeOut:
    """Replace everything in the recipe at once ("nothing changes until Save"). Send the
    `version` the editor opened. If someone saved the recipe since, nothing is saved:
    409 `recipe_changed` says who ("Wren changed this recipe after you opened it.") and
    carries the current `version`. "Save mine anyway" is the same request sent again with
    that newer `version` and `overwrite: true`. Every save adds 1 to the version."""
    lock_household(kitchen)
    earlier = replayed(kitchen)
    if earlier is None:
        recipe = recipes.find(kitchen, recipe_id)
        if body.version != recipe.version:
            raise recipes.conflict(recipe)
        recipes.save(kitchen, recipe, body)
        earlier = commit(kitchen)
        if earlier is None:
            return recipes.recipe_out(kitchen, recipe)
    response.headers["Idempotent-Replayed"] = "true"
    return recipes.recipe_out(kitchen, recipes.find(kitchen, recipe_id))


@router.delete("/recipes/{recipe_id}")
def delete_recipe(recipe_id: int, kitchen: Here, response: Response) -> RecipeRemoved:
    """Delete a recipe, at once, with no question. It can be undone for 7 days
    (`POST /changes/{id}/undo`). Recipes that use it keep the line's words, marked
    "recipe removed"; Undo puts the link back."""
    earlier = replayed(kitchen)
    if earlier is None:
        lock_household(kitchen)
        recipe = recipes.find(kitchen, recipe_id)
        change = recipes.remove(kitchen, recipe)
        earlier = commit(kitchen)
        if earlier is None:
            return RecipeRemoved(change=change_out(kitchen, change))
    response.headers["Idempotent-Replayed"] = "true"
    return RecipeRemoved(change=change_out(kitchen, earlier))


@router.get("/recipes/{recipe_id}/cannot-use")
def recipes_it_cannot_use(recipe_id: int, kitchen: Here) -> BlockedList:
    """The recipes this recipe can't use as an ingredient, and why (itself, and every
    recipe that already uses it), so the editor can grey them out before Save. The server
    checks again on every save."""
    return BlockedList(recipes=recipes.blocked_for(kitchen, recipes.find(kitchen, recipe_id)))
