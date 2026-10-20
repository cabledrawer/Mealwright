"""Recipe photos: upload, show, and delete an upload that wasn't saved
(docs/dev/api-0.4-recipes.md section 2.6).

A photo is uploaded on its own and answered with its id at once; the recipe's Save
attaches it (`photo_id`), so nothing on the recipe changes until Save (cabledrawer 20 Oct).
"""

import threading
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select

from mealwright import photos
from mealwright.api.v1.context import Here, Kitchen
from mealwright.api.v1.recipe_schemas import PhotoOut
from mealwright.auth import SameOrigin
from mealwright.errors import Problem, not_found
from mealwright.limits import MAX_PHOTO_BYTES
from mealwright.models import Recipe, RecipePhoto, utcnow
from mealwright.recipes import delete_photo, photo_view
from mealwright.shopping import lock_household

router = APIRouter(tags=["recipes"], dependencies=[SameOrigin])

_PHOTO_BODY = {
    "requestBody": {
        "required": True,
        "description": "The photo file itself, as the request body (not a form). At most "
        f"{MAX_PHOTO_BYTES // (1024 * 1024)} MB and 40 megapixels.",
        "content": {
            kind: {"schema": {"type": "string", "format": "binary"}}
            for kind in ("image/jpeg", "image/png", "image/webp")
        },
    }
}


async def _photo_bytes(request: Request) -> bytes:
    # Declared after the sign-in, so a signed-out request is refused before the body is
    # read. The body limit (15 MB on this route only) is checked as it arrives.
    return await request.body()


PhotoBytes = Annotated[bytes, Depends(_photo_bytes)]


def _waiting(kitchen: Kitchen) -> int:
    return (
        kitchen.db.scalar(
            select(func.count())
            .select_from(RecipePhoto)
            .where(
                RecipePhoto.household_id == kitchen.household_id,
                RecipePhoto.recipe_id.is_(None),
            )
        )
        or 0
    )


# Uploads still being worked on, per photo folder and household. They count toward the
# 10 waiting from the start. The server is one process, like `photos.clean`'s one at a time.
_IN_HAND: dict[tuple[str, int], int] = {}
_IN_HAND_LOCK = threading.Lock()


def _in_hand(place: tuple[str, int]) -> int:
    with _IN_HAND_LOCK:
        return _IN_HAND.get(place, 0)


def _take(place: tuple[str, int]) -> None:
    with _IN_HAND_LOCK:
        _IN_HAND[place] = _IN_HAND.get(place, 0) + 1


def _give_back(place: tuple[str, int]) -> None:
    with _IN_HAND_LOCK:
        left = _IN_HAND.get(place, 0) - 1
        if left > 0:
            _IN_HAND[place] = left
        else:
            _IN_HAND.pop(place, None)


def _too_many_waiting() -> Problem:
    return Problem(status.HTTP_409_CONFLICT, "too_many_photos_waiting", photos.TOO_MANY_WAITING)


def _own(kitchen: Kitchen, photo_id: int) -> RecipePhoto:
    """The household's own photo, or 404 exactly as for an id that doesn't exist."""
    photo = kitchen.db.get(RecipePhoto, photo_id)
    if photo is None or photo.household_id != kitchen.household_id:
        raise not_found("That photo")
    return photo


@router.post(
    "/recipes/photos",
    status_code=status.HTTP_201_CREATED,
    openapi_extra=_PHOTO_BODY,
    responses={
        409: {"description": "`too_many_photos_waiting`: 10 uploads aren't saved yet."},
        413: {"description": "`photo_too_big`: over 15 MB."},
        422: {"description": "`not_a_photo` or `too_many_pixels`."},
    },
)
def upload_photo(kitchen: Here, data: PhotoBytes) -> PhotoOut:
    """Upload a photo for a recipe: send the JPEG, PNG or WebP file itself as the body.
    What it is is read from the file, never its name. It's cleaned straight away (turned
    upright, every hidden detail such as the place it was taken removed, colours made
    sRGB, see-through parts white) and kept as two JPEGs; the file sent is not kept.

    The answer has the photo's id; send it as `photo_id` when saving the recipe. An upload
    that no recipe has taken within 24 hours is deleted. A household can have at most 10
    uploads waiting to be saved. A retry uploads it again (there's no Idempotency-Key here):
    the extra one is deleted after 24 hours like any unsaved upload."""
    store = photos.store_of(kitchen.db)
    place = (str(store), kitchen.household_id)
    # Its place among the 10 is taken before the photo is worked on, so uploads sent at
    # once can't all pass the count; it's given back if the upload fails.
    lock_household(kitchen)
    if _waiting(kitchen) + _in_hand(place) >= photos.MAX_WAITING:
        raise _too_many_waiting()
    _take(place)
    held, key, saved = True, None, False
    try:
        kitchen.db.commit()  # nothing held while the photo is worked on
        try:
            cleaned = photos.clean(data)
        except photos.TooManyPixels:
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "too_many_pixels", photos.TOO_MANY_PIXELS
            ) from None
        except photos.NotAPhoto:
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT, "not_a_photo", photos.NOT_A_PHOTO
            ) from None
        del data
        key = photos.new_key()
        size = photos.write(store, kitchen.household_id, key, cleaned)
        lock_household(kitchen)
        # The record takes over from the place under the household's lock, so no other
        # upload counts this one twice, or not at all.
        _give_back(place)
        held = False
        if _waiting(kitchen) >= photos.MAX_WAITING:  # only if something went wrong
            raise _too_many_waiting()
        photo = RecipePhoto(
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
        kitchen.db.add(photo)
        kitchen.db.commit()
        saved = True
    finally:
        if held:
            _give_back(place)
        if key is not None and not saved:
            photos.remove_files(store, kitchen.household_id, key)
    return photo_view(photo)


@router.get(
    "/recipes/photos/{photo_id}/{copy}",
    response_class=FileResponse,
    responses={200: {"content": {"image/jpeg": {}}, "description": "The JPEG."}},
)
def photo_file(photo_id: int, copy: Literal["large", "list"], kitchen: Here) -> FileResponse:
    """A photo's large copy or its list copy, for members of the household only. An
    upload not saved yet can be shown too (the editor's preview); a photo of a deleted
    recipe can't, until the delete is undone."""
    photo = _own(kitchen, photo_id)
    if photo.recipe_id is not None:
        recipe = kitchen.db.get(Recipe, photo.recipe_id)
        if recipe is None or recipe.removed_at is not None:
            raise not_found("That photo")
    large, small = photos.paths(photos.store_of(kitchen.db), photo.household_id, photo.file_key)
    path = large if copy == "large" else small
    if not path.is_file():
        raise not_found("That photo")
    return FileResponse(
        path, media_type="image/jpeg", headers={"X-Content-Type-Options": "nosniff"}
    )


@router.delete(
    "/recipes/photos/{photo_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    responses={409: {"description": "`photo_in_use`: the photo is on a recipe."}},
)
def delete_unsaved_photo(photo_id: int, kitchen: Here) -> Response:
    """Delete an upload that isn't saved on a recipe, for an editor that's cancelled. A
    photo on a recipe isn't deleted here: save the recipe without it."""
    # Agreed by cabledrawer, 20 Oct (spec section 6, Photos).
    lock_household(kitchen)
    photo = _own(kitchen, photo_id)
    if photo.recipe_id is not None:
        raise Problem(
            status.HTTP_409_CONFLICT,
            "photo_in_use",
            "That photo is on a recipe. Take it off in the recipe, then save.",
        )
    delete_photo(kitchen.db, photo)
    kitchen.db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
