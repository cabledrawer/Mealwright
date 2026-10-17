"""The public, versioned API. The web app uses only this."""

from fastapi import APIRouter

from mealwright.api.v1 import account, changes, foods, kitchen, version

router = APIRouter(prefix="/api/v1")
router.include_router(version.router)
router.include_router(account.router)
router.include_router(kitchen.router)
router.include_router(foods.router)
router.include_router(changes.router)
