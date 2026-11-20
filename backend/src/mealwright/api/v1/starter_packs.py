"""Starter ingredient packs (0.8, cabledrawer 7 Nov; docs/dev/api-endpoints.md section 4.9).

`GET /starter-packs` lists the seven packs with their items, each marked as already there
when the household has it by name or other name. `POST /starter-packs/{id}/add` makes the
chosen ingredients in one change: one Undo takes them all away again. Ingredients only:
no stock, no list items."""

from typing import Annotated

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select

from mealwright import starter_packs
from mealwright.aisles import DEFAULT_AISLE
from mealwright.api.v1.context import Here, Kitchen
from mealwright.api.v1.schemas import ChangeOut
from mealwright.auth import SameOrigin
from mealwright.errors import Problem, not_found
from mealwright.foods import all_foods, change_out, shop_choices
from mealwright.history import FoodEdit, commit, replayed
from mealwright.models import Change, Food, FoodName
from mealwright.names import fold
from mealwright.pack_sizes import usual_shop_id
from mealwright.shopping import lock_household
from mealwright.starter_packs import StarterItem

router = APIRouter(tags=["foods"], dependencies=[SameOrigin])


class StarterItemOut(BaseModel):
    key: str
    name: str
    already_have: bool  # the household has it by this name or another name
    have_as: str | None  # what the household calls it, when that isn't this name
    staple: bool  # added as a staple ("Don't count it")


class StarterPackOut(BaseModel):
    id: str
    name: str
    items: list[StarterItemOut]
    already_have: int  # how many items are skipped


class StarterPacksOut(BaseModel):
    packs: list[StarterPackOut]


class AddPack(BaseModel):
    keys: list[Annotated[str, Field(max_length=100)]] = Field(max_length=500)


class AddedPackOut(BaseModel):
    added: int
    skipped: int  # chosen, but the household already had it
    change: ChangeOut


def _have(kitchen: Kitchen) -> dict[str, str]:
    """Every name and other name of the household's ingredients, folded → what it's called."""
    foods = {food.id: food.name for food in all_foods(kitchen)}
    have = {fold(name): name for name in foods.values()}
    for other in kitchen.db.scalars(
        select(FoodName).where(FoodName.household_id == kitchen.household_id)
    ):
        if other.food_id in foods:
            have.setdefault(fold(other.name), foods[other.food_id])
    return have


def _owner(item: StarterItem, have: dict[str, str]) -> str | None:
    """What the household calls this ingredient, if it has it under any of its names."""
    for name in (item.name, *item.other_names()):
        found = have.get(fold(name))
        if found is not None:
            return found
    return None


def _item_out(item: StarterItem, have: dict[str, str]) -> StarterItemOut:
    owner = _owner(item, have)
    return StarterItemOut(
        key=item.key,
        name=item.name,
        already_have=owner is not None,
        have_as=owner if owner is not None and fold(owner) != fold(item.name) else None,
        staple=item.staple,
    )


@router.get("/starter-packs")
def list_packs(kitchen: Here) -> StarterPacksOut:
    """The seven packs, each ingredient marked "Already have" when it is there already."""
    have = _have(kitchen)
    packs: list[StarterPackOut] = []
    for pack_id, name in starter_packs.PACKS:
        out = [_item_out(item, have) for item in starter_packs.pack_items(pack_id)]
        packs.append(
            StarterPackOut(
                id=pack_id,
                name=name,
                items=out,
                already_have=sum(1 for item in out if item.already_have),
            )
        )
    return StarterPacksOut(packs=packs)


def _made(
    kitchen: Kitchen, pack_id: str, chosen: list[StarterItem], have: dict[str, str], skipped: int
) -> Change | None:
    """Make the ingredients that aren't there yet, all in one change (None: none to make)."""
    shops = shop_choices(kitchen)
    todo = [item for item in chosen if _owner(item, have) is None]
    if not todo:
        return None
    # An ingredient's own name is never another ingredient's other name in the same pack
    # (kasuri methi's "methi leaves" is also the name of methi leaves).
    own = {fold(item.name): item.key for item in todo}
    others_of = {
        item.key: [n for n in item.other_names() if own.get(fold(n), item.key) == item.key]
        for item in todo
    }
    with FoodEdit(kitchen, []) as edit:
        for item in todo:
            others = others_of[item.key]
            conversion = item.conversion_row()
            # The table's aisle (cabledrawer 7 Nov): Household-pack items are food staples and
            # take their own aisle, never the Household aisle (that is for cleaning things).
            aisle = item.pack_row().aisle or DEFAULT_AISLE
            food = Food(
                household_id=kitchen.household_id,
                name=item.name,
                counted_as=starter_packs.counted_as(item),
                staple=item.staple,
                shop_id=usual_shop_id([item.name, *others], shops),
                aisle=aisle,
                table_key=conversion.key if conversion else None,
            )
            kitchen.db.add(food)
            kitchen.db.flush()
            for other in others:
                kitchen.db.add(
                    FoodName(household_id=kitchen.household_id, food_id=food.id, name=other)
                )
            edit.also(food.id)
    count = len(todo)
    things = "ingredient" if count == 1 else "ingredients"
    name = starter_packs.pack_name(pack_id)
    edit.extra["starter_pack"] = {"pack": pack_id, "added": count, "skipped": skipped}
    return edit.record("food_created", f"Added the {name} starter pack: {count} {things}", None)


def _answer(kitchen: Kitchen, change: Change) -> AddedPackOut:
    data = (change.undo_data or {}).get("starter_pack", {})
    return AddedPackOut(
        added=int(data.get("added", 0)),
        skipped=int(data.get("skipped", 0)),
        change=change_out(kitchen, change),
    )


@router.post("/starter-packs/{pack_id}/add", status_code=status.HTTP_201_CREATED)
def add_pack(pack_id: str, body: AddPack, kitchen: Here, response: Response) -> AddedPackOut:
    """Add the chosen ingredients of a pack (`keys`, each one of the pack's). Ones the
    household already has, by name or another name, are skipped. One change, one Undo."""
    if starter_packs.pack_name(pack_id) is None:
        raise not_found("That starter pack")
    earlier = replayed(kitchen)
    if earlier is not None:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
        return _answer(kitchen, earlier)
    in_pack = {item.key: item for item in starter_packs.pack_items(pack_id)}
    unknown = [key for key in body.keys if key not in in_pack]
    if unknown:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "not_in_pack",
            "That ingredient isn’t in this starter pack.",
            keys=unknown,
        )
    chosen = [in_pack[key] for key in dict.fromkeys(body.keys)]
    # The lock first, so two phones adding at once can't both miss what the other adds.
    lock_household(kitchen)
    have = _have(kitchen)
    skipped = sum(1 for item in chosen if _owner(item, have) is not None)
    change = _made(kitchen, pack_id, chosen, have, skipped)
    if change is None:
        raise Problem(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "nothing_to_add",
            "There’s nothing new to add: you already have these ingredients.",
        )
    committed = commit(kitchen)
    if committed is not None:
        response.status_code = status.HTTP_200_OK
        response.headers["Idempotent-Replayed"] = "true"
        return _answer(kitchen, committed)
    return _answer(kitchen, change)
