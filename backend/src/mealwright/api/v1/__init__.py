"""The public, versioned API. The web app uses only this."""

from fastapi import APIRouter

from mealwright.api.v1 import (
    account,
    changes,
    events,
    foods,
    kitchen,
    pantry,
    photos,
    recipes,
    shopping,
    sync,
    version,
)

router = APIRouter(prefix="/api/v1")
router.include_router(version.router)
router.include_router(account.router)
router.include_router(kitchen.router)
router.include_router(foods.router)
router.include_router(pantry.router)
router.include_router(recipes.router)
router.include_router(photos.router)
router.include_router(shopping.router)
router.include_router(sync.router)
router.include_router(events.router)
router.include_router(changes.router)
