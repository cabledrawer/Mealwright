"""Places, shops, units and the household's settings (docs/dev/api-0.2.md 4.1, 4.5, 6.3)."""

from datetime import date, datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field, StrictBool, field_validator
from sqlalchemy import func, select

from mealwright import amounts, removals
from mealwright.api.v1.context import Here, Kitchen
from mealwright.api.v1.schemas import ChangeOut, Ref
from mealwright.auth import SameOrigin
from mealwright.errors import Problem, StoredInt, not_found
from mealwright.foods import change_out, find
from mealwright.history import FoodEdit, commit, record, replayed
from mealwright.household import cup_ml, places, today, valid_time_zone
from mealwright.models import Food, FoodConversion, Place, Shop
from mealwright.names import clean_name, fold
from mealwright.pints import household_pints
from mealwright.shopping import lock_db

router = APIRouter(tags=["kitchen"], dependencies=[SameOrigin])


# --- Places and shops -----------------------------------------------------------------------


class PlaceOut(BaseModel):
    id: int
    name: str
    kind: Literal["fridge", "freezer", "cupboard"]


@router.get("/places")
def list_places(kitchen: Here) -> list[PlaceOut]:
    """Where food lives at home, in order."""
    return [
        PlaceOut(id=p.id, name=p.name, kind=p.kind)  # type: ignore[arg-type]
        for p in places(kitchen.db, kitchen.household_id)
    ]


class NewPlace(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=40)]
    kind: Literal["fridge", "freezer", "cupboard"]

    @field_validator("name")
    @classmethod
    def _clean(cls, value: str) -> str:
        value = clean_name(value)
        if not value:
            raise ValueError("Type the place’s name.")
        return value


# A household keeps at most this many places (proposed, for cabledrawer): a typo-and-retry loop or
# a runaway client can't fill the list the pickers show. Asked in words.md.
MAX_PLACES = 50


@router.post("/places", status_code=status.HTTP_201_CREATED)
def add_place(body: NewPlace, kitchen: Here) -> PlaceOut:
    """ "+ Place": add a place, last in the order. `kind` (fridge, freezer or cupboard) drives
    the rules ("freezer last"). A name the household already has (ignoring case) is a 409
    `place_exists` that carries that place, so the screen just picks it. Not logged as a change,
    like "+ Shop". Under the household's lock, so two phones at once can't pass the cap or
    add one name twice."""
    lock_db(kitchen.db, kitchen.household)
    existing = places(kitchen.db, kitchen.household_id)
    for old in existing:
        if fold(old.name) == fold(body.name):
            raise Problem(
                status.HTTP_409_CONFLICT,
                "place_exists",
                f"There’s already a place called {old.name}.",
                place={"id": old.id, "name": old.name, "kind": old.kind},
            )
    if len(existing) >= MAX_PLACES:
        raise Problem(
            status.HTTP_409_CONFLICT,
            "too_many_places",
            f"You have {MAX_PLACES} places, the most Mealwright keeps. "
            "Rename or remove one in Settings.",
        )
    place = Place(
        household_id=kitchen.household_id,
        name=body.name,
        kind=body.kind,
        position=max((p.position for p in existing), default=-1) + 1,
    )
    kitchen.db.add(place)
    kitchen.db.commit()
    return PlaceOut(id=place.id, name=place.name, kind=place.kind)  # type: ignore[arg-type]


class RenamePlace(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=40)]

    @field_validator("name")
    @classmethod
    def _clean(cls, value: str) -> str:
        value = clean_name(value)
        if not value:
            raise ValueError("Type the place’s name.")
        return value


def _find_place(kitchen: Kitchen, place_id: int) -> Place:
    place = kitchen.db.get(Place, place_id)
    if place is None or place.household_id != kitchen.household_id:
        raise not_found("That place")
    return place


@router.patch("/places/{place_id}")
def rename_place(place_id: StoredInt, body: RenamePlace, kitchen: Here) -> PlaceOut:
    """Rename a place. Its kind (and so its rules) stays. A name another place of the
    household has (ignoring case) is a 409 `place_exists`. Anyone in the household can."""
    lock_db(kitchen.db, kitchen.household)
    place = _find_place(kitchen, place_id)
    for other in places(kitchen.db, kitchen.household_id):
        if other.id != place.id and fold(other.name) == fold(body.name):
            raise Problem(
                status.HTTP_409_CONFLICT,
                "place_exists",
                f"There’s already a place called {other.name}.",
                place={"id": other.id, "name": other.name, "kind": other.kind},
            )
    place.name = body.name
    kitchen.db.commit()
    return PlaceOut(id=place.id, name=place.name, kind=place.kind)  # type: ignore[arg-type]


class Order(BaseModel):
    ids: Annotated[list[StoredInt], Field(max_length=200)]


@router.put("/places/order")
def order_places(body: Order, kitchen: Here) -> list[PlaceOut]:
    """Put the places in this order: every id of the household's places, once each. Answers
    with the places in their new order."""
    lock_db(kitchen.db, kitchen.household)
    existing = places(kitchen.db, kitchen.household_id)
    if sorted(body.ids) != sorted(p.id for p in existing):
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "not_all_places",
            "Send every place once, in the order you want.",  # proposed, for cabledrawer
        )
    by_id = {p.id: p for p in existing}
    for position, place_id in enumerate(body.ids):
        by_id[place_id].position = position
    kitchen.db.commit()
    return list_places(kitchen)


class Removed(BaseModel):
    change: ChangeOut | None


@router.delete("/places/{place_id}")
def remove_place(
    place_id: StoredInt,
    kitchen: Here,
    response: Response,
    move_to: StoredInt | None = None,
) -> Removed:
    """Remove a place, once nothing is in it. With things in it: 409 `place_not_empty`
    (carries `things`, how many); send `move_to` (another place's id) and they go there first.
    The household's last Fridge and last Freezer can't go: 409 `last_of_kind`. Undo (the
    answer's `change`) makes the place again and puts back what moved. Anyone in the
    household can."""
    earlier = replayed(kitchen)
    if earlier is None:
        lock_db(kitchen.db, kitchen.household)
        place = _find_place(kitchen, place_id)
        target = None
        if move_to is not None:
            if move_to == place.id:
                raise Problem(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "same_place",
                    "Pick a different place to move them to.",  # proposed, for cabledrawer
                )
            target = _find_place(kitchen, move_to)
        change = removals.remove_place(kitchen, place, target)
        earlier = commit(kitchen)
        if earlier is None:
            return Removed(change=change_out(kitchen, change))
    response.headers["Idempotent-Replayed"] = "true"
    return Removed(change=change_out(kitchen, earlier))


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
    """ "+ Shop": add a shop by name. A name that's already there gives that shop (200).
    Under the household's lock, so two phones at once can't add one name twice."""
    earlier = replayed(kitchen)
    if earlier is not None:
        added = (earlier.undo_data or {}).get("shop") or {}
        response.headers["Idempotent-Replayed"] = "true"
        return Ref(id=added.get("id", 0), name=added.get("new", ""))
    lock_db(kitchen.db, kitchen.household)
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
    kitchen.db.flush()
    # In Recent changes, with an Undo (F225, cabledrawer 10 Nov).
    record(
        kitchen,
        "shop_added",
        f"Added the shop {shop.name}",
        None,
        {"shop": {"id": shop.id, "new": shop.name}},
    )
    earlier = commit(kitchen)
    if earlier is not None:
        added = (earlier.undo_data or {}).get("shop") or {}
        response.headers["Idempotent-Replayed"] = "true"
        return Ref(id=added.get("id", 0), name=added.get("new", ""))
    return Ref(id=shop.id, name=shop.name)


class RenameShop(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=60)]

    @field_validator("name")
    @classmethod
    def _clean(cls, value: str) -> str:
        value = clean_name(value)
        if not value:
            raise ValueError("Type the shop’s name.")
        return value


def _find_shop(kitchen: Kitchen, shop_id: int) -> Shop:
    shop = kitchen.db.get(Shop, shop_id)
    if shop is None or shop.household_id != kitchen.household_id:
        raise not_found("That shop")
    return shop


@router.patch("/shops/{shop_id}")
def rename_shop(shop_id: StoredInt, body: RenameShop, kitchen: Here, response: Response) -> Ref:
    """Rename a shop. A name another shop has (ignoring case) is a 409 `shop_exists` that
    carries that shop. Anyone in the household can."""
    earlier = replayed(kitchen)
    if earlier is not None:
        renamed = (earlier.undo_data or {}).get("shop") or {}
        response.headers["Idempotent-Replayed"] = "true"
        return Ref(id=renamed.get("id", shop_id), name=renamed.get("new", body.name))
    lock_db(kitchen.db, kitchen.household)
    shop = _find_shop(kitchen, shop_id)
    for other in kitchen.db.scalars(select(Shop).where(Shop.household_id == kitchen.household_id)):
        if other.id != shop.id and fold(other.name) == fold(body.name):
            raise Problem(
                status.HTTP_409_CONFLICT,
                "shop_exists",
                f"There’s already a shop called {other.name}.",
                shop={"id": other.id, "name": other.name},
            )
    old = shop.name
    if old == body.name:
        return Ref(id=shop.id, name=shop.name)  # nothing changed: nothing to list
    shop.name = body.name
    record(
        kitchen,
        "shop_renamed",
        f"Renamed the shop {old} to {shop.name}",
        None,
        {"shop": {"id": shop.id, "old": old, "new": shop.name}},
    )
    earlier = commit(kitchen)
    if earlier is not None:
        response.headers["Idempotent-Replayed"] = "true"
    return Ref(id=shop.id, name=shop.name)


@router.put("/shops/order")
def order_shops(body: Order, kitchen: Here) -> list[Ref]:
    """Put the shops in the order you visit them: every id of the household's shops, once
    each. Answers with the shops in their new order."""
    lock_db(kitchen.db, kitchen.household)
    existing = list(
        kitchen.db.scalars(select(Shop).where(Shop.household_id == kitchen.household_id))
    )
    if sorted(body.ids) != sorted(s.id for s in existing):
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "not_all_shops",
            "Send every shop once, in the order you want.",  # proposed, for cabledrawer
        )
    by_id = {s.id: s for s in existing}
    for position, shop_id in enumerate(body.ids):
        by_id[shop_id].position = position
    kitchen.db.commit()
    return list_shops(kitchen)


@router.delete("/shops/{shop_id}")
def remove_shop(shop_id: StoredInt, kitchen: Here, response: Response) -> Removed:
    """Remove a shop. Its ingredients, and the lines to buy in it, go to "Any shop". Undo (the
    answer's `change`) makes the shop again and puts them back. Anyone in the household can."""
    earlier = replayed(kitchen)
    if earlier is None:
        lock_db(kitchen.db, kitchen.household)
        change = removals.remove_shop(kitchen, _find_shop(kitchen, shop_id))
        earlier = commit(kitchen)
        if earlier is None:
            return Removed(change=change_out(kitchen, change))
    response.headers["Idempotent-Replayed"] = "true"
    return Removed(change=change_out(kitchen, earlier))


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


# --- The household's kitchen, for Batch cook (Experimental; 0.8 wave 6, B1) -----------------------

MOST_HOB_RINGS = 12
MOST_PRESSURE_COOKERS = 6


class KitchenOut(BaseModel):
    """The equipment Batch cook plans around. `asked` is false until the household has saved it
    once (Batch cook asks on first use); the first values are the usual ones, not an answer."""

    hob_rings: int
    pressure_cookers: int
    oven: bool
    asked: bool


class KitchenChange(BaseModel):
    """Only what is sent changes. Any save counts as asking: `asked` becomes true."""

    hob_rings: Annotated[int, Field(ge=1, le=MOST_HOB_RINGS)] | None = None
    pressure_cookers: Annotated[int, Field(ge=0, le=MOST_PRESSURE_COOKERS)] | None = None
    oven: StrictBool | None = None


def _kitchen_out(kitchen: Here) -> KitchenOut:
    household = kitchen.household
    return KitchenOut(
        hob_rings=household.kitchen_hob_rings,
        pressure_cookers=household.kitchen_pressure_cookers,
        oven=household.kitchen_oven,
        asked=household.kitchen_asked,
    )


@router.get("/household/kitchen")
def get_kitchen(kitchen: Here) -> KitchenOut:
    """The household's hob rings, pressure cookers and oven, and whether it was asked yet."""
    return _kitchen_out(kitchen)


@router.patch("/household/kitchen")
def change_kitchen(body: KitchenChange, kitchen: Here) -> KitchenOut:
    """Saves the kitchen's equipment (Your kitchen, or Settings, Kitchen). Any signed-in person
    of the household may (proposed, for cabledrawer: like Cook mode's per-step switch, it changes
    only what Batch cook plans). Answers with the kitchen as stored."""
    household = kitchen.household
    if body.hob_rings is not None:
        household.kitchen_hob_rings = body.hob_rings
    if body.pressure_cookers is not None:
        household.kitchen_pressure_cookers = body.pressure_cookers
    if body.oven is not None:
        household.kitchen_oven = body.oven
    household.kitchen_asked = True
    kitchen.db.commit()
    return _kitchen_out(kitchen)


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
