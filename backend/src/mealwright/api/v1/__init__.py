"""The public, versioned API. The web app uses only this."""

from fastapi import APIRouter

from mealwright.api.v1 import version

router = APIRouter(prefix="/api/v1")
router.include_router(version.router)
