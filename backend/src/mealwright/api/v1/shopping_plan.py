"""The shopping list built from the plan (0.6 PR 5; docs/dev/api-endpoints.md section 6.3b).

The list itself is read and written like any other (`/shopping/...`): plan-made items have
`source = "plan"`. These endpoints bring it up to date and run the "Check you have these"
card for staples. "+ Add" on the card is the ordinary `add` action; "Got it" is here."""

from fastapi import APIRouter
from pydantic import BaseModel, Field, StrictBool

from mealwright import shop_from_plan
from mealwright.api.v1.context import Here, Kitchen
from mealwright.api.v1.schemas import Ref
from mealwright.auth import SameOrigin
from mealwright.errors import StoredInt
from mealwright.foods import find

router = APIRouter(tags=["shopping"], dependencies=[SameOrigin])


class StapleOut(BaseModel):
    food: Ref
    used_in: list[str]  # the recipes that use it, A to Z


class FromPlanOut(BaseModel):
    days: int  # how far ahead the list looks: the household's `plan_ahead_days`
    from_plan: int  # lines of the main list the plan made
    changed: bool  # the list was changed by this call
    staples: list[StapleOut]  # "Check you have these"


def _out(kitchen: Kitchen, outcome: shop_from_plan.Outcome) -> FromPlanOut:
    return FromPlanOut(
        days=outcome.worked.days,
        from_plan=outcome.plan_items,
        changed=outcome.changed,
        staples=[
            StapleOut(food=Ref(id=s.food.id, name=s.food.name), used_in=s.used_in)
            for s in shop_from_plan.staples_card(kitchen, outcome.worked)
        ],
    )


@router.post("/shopping/add-from-plan")
def from_plan(kitchen: Here) -> FromPlanOut:
    """Bring the main list up to date with the plan and the pantry (it is also done after
    every plan write), and give back the staples card. Changes nothing when the list is already
    right."""
    outcome = shop_from_plan.refresh(kitchen)
    answer = _out(kitchen, outcome)
    kitchen.db.commit()
    return answer


class StaplePatch(BaseModel):
    """D3 (BE14): one way to set one thing, a PATCH on it (was `PUT` and `DELETE`
    `/shopping/staples/{food_id}/got-it`)."""

    got_it: StrictBool = Field(
        description='true: "Got it" on the staples card, the staple stays off the card until'
        " the plan's use of it changes; saying it twice changes nothing more. false: its Undo,"
        " the staple is on the card again."
    )


@router.patch("/shopping/staples/{food_id}")
def edit_staple(food_id: StoredInt, body: StaplePatch, kitchen: Here) -> FromPlanOut:
    """ "Got it" on the staples card, or taking it back. Answers the card as it is now."""
    food = find(kitchen, food_id)
    worked = (
        shop_from_plan.got_it(kitchen, food)
        if body.got_it
        else shop_from_plan.not_got_it(kitchen, food)
    )
    answer = _out(kitchen, worked)
    kitchen.db.commit()
    return answer
