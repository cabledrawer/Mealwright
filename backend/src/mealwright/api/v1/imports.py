"""Importing a recipe from a link or pasted text: the review, and Save
(docs/dev/recipe-import.md, "The import's API")."""

from typing import Any

from fastapi import APIRouter, Request, Response, status

from mealwright import recipe_import, recipes
from mealwright.api.v1.context import Here, Kitchen
from mealwright.api.v1.import_schemas import (
    AlreadyImported,
    ImportReview,
    ImportSave,
    ImportSaved,
    ImportStart,
)
from mealwright.api.v1.schemas import Ref
from mealwright.auth import SameOrigin
from mealwright.errors import KEY_REUSED, Problem
from mealwright.foods import change_out
from mealwright.history import commit, replayed
from mealwright.models import Change, Food
from mealwright.shopping import lock_household

router = APIRouter(tags=["recipes"], dependencies=[SameOrigin])


@router.post(
    "/recipes/import",
    responses={
        403: {"description": "`import_switched_off`: Recipe import from links is off."},
        409: {
            "model": AlreadyImported,
            "description": "`already_imported`: the household already has this recipe.",
        },
        422: {
            "description": "A sentence in `detail` and a `code`: `not_a_page`, `bad_link`,"
            " `cant_reach`, `cant_read`, `busy`, `cant_open_link`"
            " (a member's answer for a link on this server or your own network, or on an unusual"
            " port), `no_recipe`, `text_too_long` and the rest of"
            " docs/dev/recipe-import.md."
        },
    },
)
def start_import(body: ImportStart, kitchen: Here, request: Request) -> ImportReview:
    """Read a link or pasted recipe text and answer with the review: what came across, each
    line as written → how it was read → what is in your kitchen, with its label and best
    guess, the counts, and what was left out. **Nothing is saved** except a downloaded main
    photo, which waits like an uploaded one until Save.

    A link needs "Recipe import from links" to be on; pasted text always works (it goes
    nowhere). A link the household already imported answers 409 `already_imported` (send
    `again: true` to import it again as a copy). The photo is only downloaded while "Download
    recipe photos" is on."""
    return recipe_import.start(kitchen, request.app.state.outbound, body.text, body.again)


def _saved(kitchen: Kitchen, change: Change) -> ImportSaved:
    data: dict[str, Any] = change.undo_data or {}
    recipe = recipes.find(kitchen, data.get("recipe_id", 0))
    foods = data.get("foods", {})
    made = sorted(
        int(key.split(":")[0])
        for key, (old, _new) in foods.get("fields", {}).items()
        if key.endswith(":exists") and old is None
    )
    news = [
        Ref(id=food.id, name=food.name)
        for food in (kitchen.db.get(Food, food_id) for food_id in made)
        if food is not None and food.household_id == kitchen.household_id
    ]
    learned = sum(1 for old, _new in foods.get("names", {}).values() if old is None)
    return ImportSaved(
        recipe=Ref(id=recipe.id, name=recipe.name),
        change=change_out(kitchen, change),
        new_ingredients=news,
        learned=learned,
    )


@router.post("/recipes/import/save", status_code=status.HTTP_201_CREATED)
def save_import(body: ImportSave, kitchen: Here, response: Response) -> ImportSaved:
    """Save the reviewed recipe: the recipe, its new ingredients, its new staples and the
    other names it learned, all in one go. Recent changes gets **one** entry, `recipe_imported`,
    whose Undo takes the whole save back. A retry with the same `Idempotency-Key` saves
    nothing more."""
    lock_household(kitchen)
    earlier = replayed(kitchen)
    if earlier is None:
        saved = recipe_import.save(kitchen, body)
        earlier = commit(kitchen)
        if earlier is None:
            return _saved(kitchen, saved.change)
    if earlier.kind != "recipe_imported":
        raise Problem(
            status.HTTP_409_CONFLICT,
            "key_reused",
            KEY_REUSED,
        )
    response.status_code = status.HTTP_200_OK
    response.headers["Idempotent-Replayed"] = "true"
    return _saved(kitchen, earlier)
