"""Places, shops, units and the household's settings (docs/dev/api-0.2.md 4.1, 4.5, 6.3)."""

from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field, StrictBool, field_validator
from sqlalchemy import func, select

from mealwright import amounts
from mealwright.api.v1.context import Here
from mealwright.api.v1.schemas import ChangeOut, Ref
from mealwright.auth import SameOrigin
from mealwright.errors import StoredInt, not_found
from mealwright.foods import change_out, find
from mealwright.history import FoodEdit, commit, replayed
from mealwright.household import cup_ml, places, today, valid_time_zone
from mealwright.models import Food, FoodConversion, Shop
from mealwright.names import clean_name, fold
from mealwright.pints import household_pints

router = APIRouter(tags=["kitchen"], dependencies=[SameOrigin])


# --- Places and shops -----------------------------------------------------------------------


class PlaceOut(BaseModel):
    id: int
    name: str
    kind: Literal["fridge", "freezer", "cupboard"]


@router.get("/places")
def list_places(kitchen: Here) -> list[PlaceOut]:
    """Where food lives at home, in order. Renaming and adding come in Settings (0.8)."""
    return [
        PlaceOut(id=p.id, name=p.name, kind=p.kind)  # type: ignore[arg-type]
        for p in places(kitchen.db, kitchen.household_id)
    ]


@router.get("/shops")
def list_shops(kitchen: Here) -> list[Ref]:
    rows = kitchen.db.scalars(
        select(Shop)
        .where(Shop.household_id == kitchen.household_id)
        .order_by(Shop.position, Shop.id)
    )
    return [Ref(id=s.id, name=s.name) for s in rows]


class NewShop(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=60)]

    @field_validator("name")
    @classmethod
    def _clean(cls, value: str) -> str:
        value = clean_name(value)
        if not value:
            raise ValueError("Type the shop’s name.")
        return value


@router.post("/shops", status_code=status.HTTP_201_CREATED)
def add_shop(body: NewShop, kitchen: Here, response: Response) -> Ref:
    """ "+ Shop": add a shop by name. A name that's already there gives that shop (200)."""
    existing = list(
        kitchen.db.scalars(select(Shop).where(Shop.household_id == kitchen.household_id))
    )
    for shop in existing:
        if fold(shop.name) == fold(body.name):
            response.status_code = status.HTTP_200_OK
            return Ref(id=shop.id, name=shop.name)
    shop = Shop(
        household_id=kitchen.household_id,
        name=body.name,
        position=max((s.position for s in existing), default=-1) + 1,
    )
    kitchen.db.add(shop)
    kitchen.db.commit()
    return Ref(id=shop.id, name=shop.name)


# --- Household --------------------------------------------------------------------------------


class HouseholdOut(BaseModel):
    name: str
    time_zone: str | None
    cup_ml: int | None
    cup_ml_used: int
    pints: Literal["uk", "us"]
    cook_per_step: bool
    undo_days: int
    history_months: int
    use_soon_days: int
    tub_fridge_days: int
    tub_freezer_months: int
    plan_ahead_days: int
    week_starts_on: int
    today: date


class FromBrowser(BaseModel):
    """What the admin's browser says, sent once after sign-in (never location)."""

    time_zone: Annotated[str, Field(min_length=1, max_length=64)] | None = None
    cup_ml: Literal[240, 250] | None = None

    @field_validator("time_zone")
    @classmethod
    def _zone(cls, value: str | None) -> str | None:
        if value is not None and not valid_time_zone(value):
            raise ValueError("That isn’t a time zone Mealwright knows.")
        return value


def _household(kitchen: Here) -> HouseholdOut:
    household = kitchen.household
    return HouseholdOut(
        name=household.name,
        time_zone=household.time_zone,
        cup_ml=household.cup_ml,
        cup_ml_used=cup_ml(household),
        pints=household_pints(household.pints),
        cook_per_step=household.cook_per_step,
        undo_days=household.undo_days,
        history_months=household.history_months,
        use_soon_days=household.use_soon_days,
        tub_fridge_days=household.tub_fridge_days,
        tub_freezer_months=household.tub_freezer_months,
        plan_ahead_days=household.plan_ahead_days,
        week_starts_on=household.week_starts_on,
        today=today(household),
    )


@router.get("/household")
def get_household(kitchen: Here) -> HouseholdOut:
    return _household(kitchen)


class HouseholdChange(BaseModel):
    """A setting changed on purpose. Only what is sent changes. The pint is for admins only;
    `cook_per_step` may be changed by any signed-in person of the household."""

    # Which pint a recipe's "pint" is: "uk" (568 ml) or "us" (473 ml) (0.6; proposed, for cabledrawer).
    pints: Literal["uk", "us"] | None = None
    # Cook mode's per-step ingredients (Experimental; 0.7 K4, cabledrawer 1 Nov). Proposed, for
    # cabledrawer: any signed-in person of the household may change this one (it changes only what
    # Cook mode shows), while `pints` stays admins only.
    cook_per_step: StrictBool | None = None


@router.patch("/household")
def change_household(body: HouseholdChange, kitchen: Here) -> HouseholdOut:
    """Changes the signed-in person's own household's settings: the pint (`pints`, admins
    only) and Cook mode's per-step ingredients (`cook_per_step`, any person of the household).
    Answers with the settings as stored."""
    if body.pints is not None:
        kitchen.admin_only()
        kitchen.household.pints = body.pints
    if body.cook_per_step is not None:
        kitchen.household.cook_per_step = body.cook_per_step
    kitchen.db.commit()
    return _household(kitchen)


@router.post("/household/from-browser")
def fill_in_from_browser(body: FromBrowser, kitchen: Here) -> HouseholdOut:
    """Admins only. The web app calls this after sign-in with the browser's time zone and
    cup size. Each is stored only while the household has none: once set, it's never
    changed silently (an admin opening the app from abroad changes nothing). Changing them
    on purpose comes with Settings (0.8). Answers with the settings as stored."""
    kitchen.admin_only()
    household = kitchen.household
    if household.time_zone is None and body.time_zone is not None:
        household.time_zone = body.time_zone
    if household.cup_ml is None and body.cup_ml is not None:
        household.cup_ml = body.cup_ml
    kitchen.db.commit()
    return _household(kitchen)


# --- Units and remembered conversions -----------------------------------------------------------


class UnitOut(BaseModel):
    unit: str
    kind: Literal["weight", "volume", "count"]
    amount: float  # in g, ml or items


@router.get("/units")
def list_units(kitchen: Here) -> list[UnitOut]:
    """The units Mealwright understands, with the household's own cup size."""
    cup = cup_ml(kitchen.household)
    found = [
        UnitOut(unit=u, kind="weight", amount=float(v)) for u, v in amounts.WEIGHT_UNITS.items()
    ]
    found += [
        UnitOut(unit=u, kind="volume", amount=float(v)) for u, v in amounts.VOLUME_UNITS.items()
    ]
    found.append(UnitOut(unit="cup", kind="volume", amount=float(cup)))
    found.append(UnitOut(unit="count", kind="count", amount=1.0))
    return found


class RememberedOut(BaseModel):
    id: int
    food: Ref
    kind: Literal["weight_per_ml", "item_weight"]
    display: str  # "1 cup = 200 g"
    answered_by: str
    answered_at: datetime


@router.get("/conversions")
def list_conversions(kitchen: Here) -> list[RememberedOut]:
    """The household's remembered "ask once" answers (Settings → Amounts, 0.8)."""
    cup = cup_ml(kitchen.household)
    rows = kitchen.db.execute(
        select(FoodConversion, Food)
        .join(Food, Food.id == FoodConversion.food_id)
        .where(
            FoodConversion.household_id == kitchen.household_id,
            Food.removed_at.is_(None),
            Food.merged_into_id.is_(None),
        )
        .order_by(func.lower(Food.name), FoodConversion.kind)
    ).all()
    result = []
    for row, food in rows:
        if row.kind == "weight_per_ml":
            grams = amounts.exact_text(row.value_milli * cup, "weight")
            display = f"1{amounts.NBSP}cup = {grams}"
        else:
            display = f"1 = {amounts.exact_text(row.value_milli, 'weight')}"
        result.append(
            RememberedOut(
                id=row.id,
                food=Ref(id=food.id, name=food.name),
                kind=row.kind,  # type: ignore[arg-type]
                display=display,
                answered_by=row.answered_by_name,
                answered_at=row.answered_at,
            )
        )
    return result


class Forgotten(BaseModel):
    change: ChangeOut | None


@router.delete("/conversions/{conversion_id}")
def forget_conversion(conversion_id: StoredInt, kitchen: Here, response: Response) -> Forgotten:
    """Forget a remembered answer: the table is used again, or the question asked again."""
    earlier = replayed(kitchen)
    if earlier is None:
        row = kitchen.db.get(FoodConversion, conversion_id)
        if row is None or row.household_id != kitchen.household_id:
            raise not_found("That answer")
        food = find(kitchen, row.food_id)
        what = (
            f"weight of 1{amounts.NBSP}cup of" if row.kind == "weight_per_ml" else "weight of one"
        )
        with FoodEdit(kitchen, [food.id]) as edit:
            kitchen.db.delete(row)
        change = edit.record("food_edited", f"Forgot your {what} {food.name}", food.id)
        earlier = commit(kitchen)
        if earlier is None:
            return Forgotten(change=change_out(kitchen, change))
    response.headers["Idempotent-Replayed"] = "true"
    return Forgotten(change=change_out(kitchen, earlier))
