"""Shopping lists: the plain online API (docs/dev/sync-protocol.md sections 3 and 5.7).

Reading is grouped the way the Shopping screen shows it: by shop ("Any shop" last), then
aisle in the default order, with ticked items folded into "In the trolley" at the end of
each shop. Every write records a Change for Undo (POST /changes/{id}/undo), like 0.2.

Ticking and the pantry side, notes and "Did you buy 2?", and the sync endpoints that
catch a phone up come in the next pull request; they use the same writes (mealwright.shopping).
"""

from collections.abc import Callable
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select

from mealwright import shopping
from mealwright.aisles import AISLE_KEYS, AISLE_LABELS, DEFAULT_AISLE
from mealwright.amounts import MAX_MILLI
from mealwright.api.v1.context import Here, Kitchen
from mealwright.api.v1.schemas import AmountIn, AmountOut, ChangeOut, Ref, Who
from mealwright.auth import SameOrigin
from mealwright.errors import Problem
from mealwright.foods import amount_out, change_out, find, resolve
from mealwright.history import commit, replayed
from mealwright.models import Change, Food, FoodSize, ListItem, Place, Shop, ShoppingList
from mealwright.names import clean, fold

router = APIRouter(tags=["shopping"], dependencies=[SameOrigin])

UUID = Annotated[
    str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
]
ListName = Annotated[str, Field(min_length=1, max_length=60)]

ANY_SHOP = "Any shop"


# --- Shapes --------------------------------------------------------------------------------------


class ListOut(BaseModel):
    id: str
    name: str
    main: bool
    to_buy: int  # items not ticked yet
    ticked: int  # items in the trolley


class ListsOut(BaseModel):
    lists: list[ListOut]


class ItemOut(BaseModel):
    id: str
    list_id: str
    food: Ref
    amount: AmountOut | None
    shop: Ref | None
    aisle: str
    aisle_name: str
    ticked_at: datetime | None
    ticked_by: Who | None
    put_away_place: Ref | None
    hand_edited: bool
    source: str
    added_by: str
    version: int


class AisleGroup(BaseModel):
    aisle: str
    name: str
    items: list[ItemOut]


class ShopGroup(BaseModel):
    shop: Ref | None  # null: "Any shop"
    name: str
    aisles: list[AisleGroup]
    in_trolley: list[ItemOut]  # ticked items, folded away


class ListView(BaseModel):
    shopping_list: ListOut
    shops: list[ShopGroup]


class ListWrite(BaseModel):
    shopping_list: ListOut | None
    change: ChangeOut | None


class ItemWrite(BaseModel):
    item: ItemOut | None
    merged: bool  # joined a line that was already there; its amounts were added up
    change: ChangeOut | None


class ClearWrite(BaseModel):
    cleared: list[str]  # item IDs
    change: ChangeOut | None


# --- Building the shapes -------------------------------------------------------------------------


def _counts(kitchen: Kitchen) -> dict[str, tuple[int, int]]:
    rows = kitchen.db.scalars(
        select(ListItem).where(
            ListItem.household_id == kitchen.household_id,
            ListItem.deleted_at.is_(None),
            ListItem.merged_into_id.is_(None),
        )
    )
    counts: dict[str, list[int]] = {}
    for item in rows:
        entry = counts.setdefault(item.list_id, [0, 0])
        entry[1 if item.ticked_at is not None else 0] += 1
    return {key: (a, b) for key, (a, b) in counts.items()}


def list_out(kitchen: Kitchen, shopping_list: ShoppingList) -> ListOut:
    to_buy, ticked = _counts(kitchen).get(shopping_list.id, (0, 0))
    return ListOut(
        id=shopping_list.id,
        name=shopping_list.name,
        main=shopping_list.main,
        to_buy=to_buy,
        ticked=ticked,
    )


def _item_out(kitchen: Kitchen, item: ListItem, food: Food, shops: dict[int, Shop]) -> ItemOut:
    size = kitchen.db.get(FoodSize, item.size_id) if item.size_id else None
    shop = shops.get(item.shop_id) if item.shop_id else None
    place = item.put_away_place_id
    aisle = food.aisle if food.aisle in AISLE_KEYS else DEFAULT_AISLE
    place_row = kitchen.db.get(Place, place) if place else None
    return ItemOut(
        id=item.id,
        list_id=item.list_id,
        food=Ref(id=food.id, name=food.name),
        amount=(
            amount_out(food, item.amount_milli, size) if item.amount_milli is not None else None
        ),
        shop=Ref(id=shop.id, name=shop.name) if shop else None,
        aisle=aisle,
        aisle_name=AISLE_LABELS[aisle],
        ticked_at=item.ticked_at,
        ticked_by=(
            Who(login_id=item.ticked_by_login_id, name=item.ticked_by_name or "")
            if item.ticked_at is not None
            else None
        ),
        put_away_place=Ref(id=place_row.id, name=place_row.name) if place_row else None,
        hand_edited=item.hand_edited,
        source=item.source,
        added_by=item.added_by_name,
        version=item.version,
    )


def _shops(kitchen: Kitchen) -> dict[int, Shop]:
    return {
        shop.id: shop
        for shop in kitchen.db.scalars(
            select(Shop)
            .where(Shop.household_id == kitchen.household_id)
            .order_by(Shop.position, Shop.id)
        )
    }


def _aisle_order(shop: Shop | None) -> list[str]:
    """The shop's own aisle order, else the default; aisles it leaves out come after."""
    own = [key for key in (shop.aisle_order or []) if key in AISLE_KEYS] if shop else []
    return own + [key for key in AISLE_KEYS if key not in own]


def _item_out_one(kitchen: Kitchen, item: ListItem) -> ItemOut:
    food = find(kitchen, item.food_id)
    return _item_out(kitchen, item, food, _shops(kitchen))


def _visible_food(kitchen: Kitchen, food_id: int) -> Food | None:
    try:
        return find(kitchen, food_id)
    except Problem:
        return None


def list_view(kitchen: Kitchen, shopping_list: ShoppingList) -> ListView:
    shops = _shops(kitchen)
    items = list(
        kitchen.db.scalars(
            select(ListItem).where(
                ListItem.household_id == kitchen.household_id,
                ListItem.list_id == shopping_list.id,
                ListItem.deleted_at.is_(None),
                ListItem.merged_into_id.is_(None),
            )
        )
    )
    by_shop: dict[int | None, list[tuple[ListItem, Food]]] = {}
    for item in items:
        food = _visible_food(kitchen, item.food_id)
        if food is None:  # an ingredient that's gone: nothing to show
            continue
        by_shop.setdefault(item.shop_id if item.shop_id in shops else None, []).append((item, food))
    groups: list[ShopGroup] = []
    ordered: list[int | None] = [sid for sid in shops if sid in by_shop]
    if None in by_shop:
        ordered.append(None)  # "Any shop" last
    for shop_id in ordered:
        shop = shops.get(shop_id) if shop_id is not None else None
        pairs = sorted(by_shop[shop_id], key=lambda pair: (fold(pair[1].name), pair[0].id))
        outs = [(_item_out(kitchen, i, f, shops), i) for i, f in pairs]
        aisles = []
        for key in _aisle_order(shop):
            members = [o for o, i in outs if o.aisle == key and i.ticked_at is None]
            if members:
                aisles.append(AisleGroup(aisle=key, name=AISLE_LABELS[key], items=members))
        groups.append(
            ShopGroup(
                shop=Ref(id=shop.id, name=shop.name) if shop else None,
                name=shop.name if shop else ANY_SHOP,
                aisles=aisles,
                in_trolley=[o for o, i in outs if i.ticked_at is not None],
            )
        )
    return ListView(shopping_list=list_out(kitchen, shopping_list), shops=groups)


# --- Writing -------------------------------------------------------------------------------------


def _write[T, R](
    kitchen: Kitchen,
    response: Response,
    apply: Callable[[], T],
    build: Callable[..., R],
) -> R:
    """Apply a write once: a retry with the same Idempotency-Key gets the original answer
    (docs/dev/api-0.2.md 1.2)."""
    earlier = replayed(kitchen)
    if earlier is None:
        result = apply()
        earlier = commit(kitchen)
        if earlier is None:
            return build(result)
    response.status_code = status.HTTP_200_OK
    response.headers["Idempotent-Replayed"] = "true"
    return build(None, earlier)


# --- Lists ---------------------------------------------------------------------------------------


@router.get("/shopping/lists")
def get_lists(kitchen: Here) -> ListsOut:
    """The household's lists: the main list first, then the extra lists in the order made."""
    lists = shopping.live_lists(kitchen)
    kitchen.db.commit()  # the main list may have just been made
    return ListsOut(lists=[list_out(kitchen, row) for row in lists])


@router.get("/shopping/lists/{list_id}")
def get_list(list_id: str, kitchen: Here) -> ListView:
    """One list, grouped by shop and aisle."""
    return list_view(kitchen, shopping.find_list(kitchen, list_id))


class NewList(BaseModel):
    id: UUID | None = None  # a phone-made ID, if the phone is making the list
    name: ListName

    _clean = field_validator("name")(lambda value: clean(value) or _blank())


def _blank() -> str:
    raise ValueError("Please type a name.")


class RenameList(BaseModel):
    name: ListName

    _clean = field_validator("name")(lambda value: clean(value) or _blank())


@router.post("/shopping/lists", status_code=status.HTTP_201_CREATED)
def create_list(body: NewList, kitchen: Here, response: Response) -> ListWrite:
    """Make an extra list."""

    def apply() -> tuple[ShoppingList, Change]:
        shopping.ensure_main_list(kitchen.db, kitchen.household_id)
        return shopping.make_list(kitchen, body.name, body.id)

    def build(result: Any, replay: Change | None = None) -> ListWrite:
        if result is not None:
            made, change = result
            return ListWrite(
                shopping_list=list_out(kitchen, made), change=change_out(kitchen, change)
            )
        if replay is None:  # pragma: no cover (a replay always has its change)
            raise RuntimeError("no change")
        ops = (replay.undo_data or {}).get("shopping", [])
        row = kitchen.db.get(ShoppingList, ops[0]["list_id"]) if ops else None
        return ListWrite(
            shopping_list=list_out(kitchen, row) if row is not None else None,
            change=change_out(kitchen, replay),
        )

    return _write(kitchen, response, apply, build)


@router.patch("/shopping/lists/{list_id}")
def rename_list(list_id: str, body: RenameList, kitchen: Here, response: Response) -> ListWrite:
    """Rename a list. The main list can be renamed too."""
    shopping_list = shopping.find_list(kitchen, list_id)

    def apply() -> Any:
        return shopping.rename_list(kitchen, shopping_list, body.name)

    def build(change: Any, replay: Any = None) -> ListWrite:
        used = replay or change
        return ListWrite(
            shopping_list=list_out(kitchen, shopping_list),
            change=change_out(kitchen, used) if used is not None else None,
        )

    return _write(kitchen, response, apply, build)


@router.delete("/shopping/lists/{list_id}")
def remove_list(list_id: str, kitchen: Here, response: Response) -> ListWrite:
    """Remove an extra list, with Undo. The main list can never be removed."""
    shopping_list = shopping.find_list(kitchen, list_id)

    def apply() -> Any:
        return shopping.remove_list(kitchen, shopping_list)

    def build(change: Any, replay: Any = None) -> ListWrite:
        return ListWrite(shopping_list=None, change=change_out(kitchen, replay or change))

    return _write(kitchen, response, apply, build)


# --- Items ---------------------------------------------------------------------------------------


class NewItem(BaseModel):
    id: UUID | None = None  # a phone-made ID
    food_id: int
    # Omitted or null: one of its usual size, or 1 if counted in items (otherwise none).
    amount: AmountIn | None = None
    # Omitted: the ingredient's usual shop. Null: "Any shop".
    shop_id: int | None = None


class ItemAmount(BaseModel):
    amount: AmountIn


class ClearTicked(BaseModel):
    item_ids: list[UUID] | None = Field(default=None, max_length=500)  # default: all ticked


def _resolved_amount(kitchen: Kitchen, food: Food, value: AmountIn) -> tuple[int, FoodSize | None]:
    resolved = resolve(kitchen, food, value)
    if resolved.milli > MAX_MILLI:  # pragma: no cover (resolve checks)
        raise ValueError
    return resolved.milli, resolved.size


@router.post("/shopping/lists/{list_id}/items", status_code=status.HTTP_201_CREATED)
def add_item(list_id: str, body: NewItem, kitchen: Here, response: Response) -> ItemWrite:
    """Add an ingredient to a list. If the same ingredient is already a line on that list for
    that shop and isn't ticked, the amounts are added to that line instead (`merged`)."""
    shopping_list = shopping.find_list(kitchen, list_id)

    def apply() -> tuple[ListItem, Any, bool]:
        food = find(kitchen, body.food_id)
        if "shop_id" in body.model_fields_set:
            shop_id = shopping.check_shop(kitchen, body.shop_id).id if body.shop_id else None
        else:
            shop_id = food.shop_id
        if body.amount is None:
            item, change, merged = shopping.add_item(
                kitchen, shopping_list, food, amount_milli=None, size=None, blank=True,
                shop_id=shop_id, item_id=body.id,
            )  # fmt: skip
        else:
            milli, size = _resolved_amount(kitchen, food, body.amount)
            item, change, merged = shopping.add_item(
                kitchen, shopping_list, food, amount_milli=milli, size=size, blank=False,
                shop_id=shop_id, item_id=body.id,
            )  # fmt: skip
        return item, change, merged

    def build(result: Any, replay: Any = None) -> ItemWrite:
        if result is not None:
            item, change, merged = result
            return ItemWrite(
                item=_item_out_one(kitchen, item), merged=merged, change=change_out(kitchen, change)
            )
        return ItemWrite(item=None, merged=False, change=change_out(kitchen, replay))

    return _write(kitchen, response, apply, build)


@router.patch("/shopping/items/{item_id}")
def change_amount(item_id: str, body: ItemAmount, kitchen: Here, response: Response) -> ItemWrite:
    """Change how much to buy. An item someone already took off the list gives `409
    item_deleted`; only Undo brings it back."""
    item = shopping.find_item(kitchen, item_id)

    def apply() -> Any:
        food = find(kitchen, item.food_id)
        if item.deleted_at is not None:
            raise shopping.deleted(item)
        milli, size = _resolved_amount(kitchen, food, body.amount)
        return shopping.set_amount(kitchen, item, food, milli, size)

    def build(change: Any, replay: Any = None) -> ItemWrite:
        used = replay or change
        return ItemWrite(
            item=_item_out_one(kitchen, item),
            merged=False,
            change=change_out(kitchen, used) if used is not None else None,
        )

    return _write(kitchen, response, apply, build)


@router.delete("/shopping/items/{item_id}")
def delete_item(item_id: str, kitchen: Here, response: Response) -> ItemWrite:
    """Take an item off the list (it leaves a hidden tombstone). Deleting it again does
    nothing. Undo brings it back."""
    item = shopping.find_item(kitchen, item_id)

    def apply() -> Any:
        return shopping.delete_item(kitchen, item, find(kitchen, item.food_id))

    def build(change: Any, replay: Any = None) -> ItemWrite:
        used = replay or change
        return ItemWrite(
            item=None, merged=False, change=change_out(kitchen, used) if used is not None else None
        )

    return _write(kitchen, response, apply, build)


@router.post("/shopping/lists/{list_id}/clear-ticked")
def clear_ticked(list_id: str, body: ClearTicked, kitchen: Here, response: Response) -> ClearWrite:
    """Remove the ticked items from the list in one go, with one Undo."""
    shopping_list = shopping.find_list(kitchen, list_id)

    def apply() -> Any:
        return shopping.clear_ticked(kitchen, shopping_list, body.item_ids)

    def build(result: Any, replay: Any = None) -> ClearWrite:
        if result is not None:
            items, change = result
            return ClearWrite(
                cleared=[i.id for i in items],
                change=change_out(kitchen, change) if change is not None else None,
            )
        ids = [
            i for op in (replay.undo_data or {}).get("shopping", []) for i in op.get("item_ids", [])
        ]
        return ClearWrite(cleared=ids, change=change_out(kitchen, replay))

    return _write(kitchen, response, apply, build)
