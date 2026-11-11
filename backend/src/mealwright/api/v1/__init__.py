"""The public, versioned API. The web app uses only this."""

from fastapi import APIRouter

from mealwright.api.v1 import (
    account,
    batch_cook,
    batches,
    changes,
    cooked,
    drafts,
    events,
    foods,
    imports,
    kitchen,
    my_sign_in,
    pantry,
    people,
    photos,
    plan,
    privacy,
    recipes,
    shopping,
    shopping_plan,
    starter_packs,
    stocktake,
    sync,
    today,
    version,
    your_data,
)

router = APIRouter(prefix="/api/v1")
router.include_router(version.router)
router.include_router(account.router)
router.include_router(my_sign_in.router)
router.include_router(kitchen.router)
router.include_router(foods.router)
router.include_router(starter_packs.router)
router.include_router(pantry.router)
router.include_router(stocktake.router)
router.include_router(plan.router)
router.include_router(batches.router)
router.include_router(batch_cook.router)
router.include_router(cooked.router)
router.include_router(today.router)
router.include_router(imports.router)
router.include_router(drafts.router)
router.include_router(recipes.router)
router.include_router(photos.router)
router.include_router(privacy.router)
router.include_router(people.router)
router.include_router(shopping.router)
router.include_router(shopping_plan.router)
router.include_router(sync.router)
router.include_router(events.router)
router.include_router(changes.router)
router.include_router(your_data.router)
