"""Drafts: imports left unfinished, kept for 15 days (docs/dev/recipe-import.md, "Drafts").

A draft belongs to the household; anyone in it can read, change, delete or carry on with it.
Every query is for the signed-in household only, so another household's draft is a plain
"not found". Nothing here changes Ingredients."""

from typing import Annotated

from fastapi import APIRouter, Query, Response, status

from mealwright import drafts, mealie_answers
from mealwright.api.v1.context import Here
from mealwright.api.v1.draft_schemas import DraftIn, DraftList, DraftOut, DraftRemoved
from mealwright.api.v1.group_schemas import GroupAnswer, GroupAnswered, IngredientGroups
from mealwright.auth import SameOrigin
from mealwright.errors import StoredInt
from mealwright.foods import change_out
from mealwright.history import commit, record, replayed
from mealwright.shopping import lock_household

router = APIRouter(tags=["recipes"], dependencies=[SameOrigin])


@router.get("/recipes/drafts")
def list_drafts(kitchen: Here) -> DraftList:
    """The household's drafts, the one changed last first: what each is (name, where it came
    from, who started it), how many days it has left and how far the checking has got. A draft
    more than 15 days past its last change, or deleted, is not listed."""
    found = drafts.listing(kitchen)
    return DraftList(drafts=found, count=len(found))


@router.post(
    "/recipes/drafts",
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "`too_many_drafts`: the household has 50 drafts."}},
)
def create_draft(body: DraftIn, kitchen: Here, response: Response) -> DraftOut:
    """Keep a review as a draft ("Save as draft?"): send the text from the box, the review
    as the server sent it and the choices so far. The review's downloaded photo becomes the
    draft's. Nothing in Ingredients changes. At 50 drafts this answers 409 `too_many_drafts`
    ("You have 50 drafts. Finish or delete one first."), and no old draft is deleted to make
    room. A retry with the same `Idempotency-Key` keeps nothing more."""
    lock_household(kitchen)
    earlier = replayed(kitchen)
    if earlier is None:
        draft = drafts.create(kitchen, body)
        # Remembers the request's key, so a retry doesn't make a second draft.
        record(
            kitchen,
            "draft_saved",
            f"Kept the {draft.name} draft",
            None,
            {"draft_id": draft.id, "name": draft.name},
        )
        earlier = commit(kitchen)
        if earlier is None:
            return drafts.detail(kitchen, draft)
    response.status_code = status.HTTP_200_OK
    response.headers["Idempotent-Replayed"] = "true"
    return drafts.detail(
        kitchen, drafts.find(kitchen, (earlier.undo_data or {}).get("draft_id", 0))
    )


@router.get("/recipes/drafts/by-food")
def drafts_by_ingredient(
    kitchen: Here, limit: Annotated[int, Query(ge=1, le=mealie_answers.MAX_LIMIT)] = 50
) -> IngredientGroups:
    # Spec: "Fixing Mealie drafts by ingredient" (cabledrawer 15 Nov).
    """Fixing Mealie drafts by ingredient: the lines of the household's
    drafts from Mealie that are still unanswered, grouped by the ingredient they name across all
    drafts, most-used first (the first `limit`; `total` is every group). Each group has its draft
    count, two lines as written and, where matching has one, an ingredient it may be. Changes
    nothing."""
    return mealie_answers.listing(kitchen, limit)


@router.post(
    "/recipes/drafts/by-food/answer",
    responses={404: {"description": "No draft from Mealie uses that ingredient any more."}},
)
def answer_by_ingredient(body: GroupAnswer, kitchen: Here, response: Response) -> GroupAnswered:
    """One answer for a group, applied to every draft from Mealie that uses it: an ingredient
    the household has (`ingredient`), a new one with its pantry place (`new`), or plain text
    (`text`: shown in the recipe, never on the shopping list or taken from the pantry). A draft
    whose lines are all answered is saved as a recipe and leaves Drafts. One change, with an Undo
    (`POST /changes/{id}/undo`, 7 days) that puts the answers back, brings those recipes back to
    Drafts, and takes out an ingredient it made only if nothing else uses it."""
    # First finish what a stop left (Final, #260 round 2 L3): drafts an earlier answer completed
    # but the server stopped before moving them to Recipes.
    mealie_answers.finish_left_behind(kitchen)
    earlier = replayed(kitchen)
    if earlier is None:
        lock_household(kitchen)
        done = mealie_answers.answer(kitchen, body)
        earlier = commit(kitchen)
        if earlier is None:
            # The answers and the change are in; the recipes it completes are saved in short
            # locked stretches, so a long answer never holds the lock for seconds.
            done = mealie_answers.finish(kitchen, done)
            return GroupAnswered(
                change=change_out(kitchen, done.change),
                drafts=done.drafts,
                moved=done.moved,
                food=done.ingredient,
            )
    response.headers["Idempotent-Replayed"] = "true"
    data = earlier.undo_data or {}
    return GroupAnswered(
        change=change_out(kitchen, earlier),
        drafts=len(data.get("saved", [])) + len(data.get("partial", [])),
        moved=len(data.get("saved", [])),
        food=(data.get("choice") or {}).get("food"),
    )


@router.get("/recipes/drafts/{draft_id}")
def get_draft(draft_id: StoredInt, kitchen: Here) -> DraftOut:
    """A draft to carry on with: the text from the box, what Mealwright read and the choices.
    Ingredients removed since are no longer offered (their lines are back to "needs you"),
    renamed ones show their new name. Opening a draft changes nothing."""
    return drafts.detail(kitchen, drafts.find(kitchen, draft_id))


@router.put("/recipes/drafts/{draft_id}")
def update_draft(draft_id: StoredInt, body: DraftIn, kitchen: Here) -> DraftOut:
    """Replace what the draft keeps (the same body as making one). It counts as a change: the
    15 days start again. Two people changing one draft at once: the last save wins."""
    lock_household(kitchen)
    draft = drafts.find(kitchen, draft_id)
    drafts.update(kitchen, draft, body)
    kitchen.db.commit()
    return drafts.detail(kitchen, draft)


@router.delete("/recipes/drafts/{draft_id}")
def delete_draft(draft_id: StoredInt, kitchen: Here, response: Response) -> DraftRemoved:
    """Delete a draft, at once, with no question. It is hidden, and can be undone for 7 days
    (`POST /changes/{id}/undo`); then it is deleted for good with its photo."""
    earlier = replayed(kitchen)
    if earlier is None:
        lock_household(kitchen)
        change = drafts.remove(kitchen, drafts.find(kitchen, draft_id))
        earlier = commit(kitchen)
        if earlier is None:
            return DraftRemoved(change=change_out(kitchen, change))
    response.headers["Idempotent-Replayed"] = "true"
    return DraftRemoved(change=change_out(kitchen, earlier))
