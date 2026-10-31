"""What was cooked (0.7 K1): the cooked record of a meal item or a batch cook. And "Cooked it"
(K2): the proposal of what it would take from the pantry, and the confirm that takes it, each for a
meal item and for a batch cook. The review screen that uses them is K3."""

from collections.abc import Callable
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field, model_validator

from mealwright import batches, cooked, cooking, deduction, foods, plan
from mealwright.api.v1.context import Here, Kitchen
from mealwright.api.v1.schemas import AmountIn, Answer, ChangeOut, ShortAmount, Who
from mealwright.auth import SameOrigin
from mealwright.errors import Problem, StoredInt
from mealwright.foods import change_out
from mealwright.history import as_utc, commit, replayed
from mealwright.models import Change, CookedRecord
from mealwright.shopping import lock_household

router = APIRouter(tags=["plan"], dependencies=[SameOrigin])


class CookedOut(BaseModel):
    """The record of what was cooked. `snapshot` is the recipe as it was then (its amounts
    are the recipe's own, for `snapshot.servings`); `portions` is how many were cooked;
    `change_id` is the change in Recent changes with its stock changes (null once the
    tidy-up has deleted that change). `recipe_id` is null once the recipe is deleted for
    good; the snapshot keeps its name."""

    id: int
    meal_item_id: int | None
    batch_id: int | None
    recipe_id: int | None
    portions: int
    snapshot: cooked.Snapshot
    change_id: int | None
    cooked_at: datetime
    cooked_by: Who


def _not_cooked() -> Problem:
    # Proposed, for cabledrawer (an API message, not shown on a screen).
    return Problem(status.HTTP_404_NOT_FOUND, "not_cooked", "It hasn’t been cooked yet.")


def cooked_out(record: CookedRecord) -> CookedOut:
    return CookedOut(
        id=record.id,
        meal_item_id=record.meal_item_id,
        batch_id=record.batch_id,
        recipe_id=record.recipe_id,
        portions=record.portions,
        snapshot=cooked.read(record),
        change_id=record.change_id,
        cooked_at=as_utc(record.cooked_at),
        cooked_by=Who(login_id=record.cooked_by_login_id, name=record.cooked_by_name),
    )


@router.get("/plan/items/{plan_item_id}/cooked")
def get_item_cooked(plan_item_id: StoredInt, kitchen: Here) -> CookedOut:
    """What was cooked for this meal item. 404 when it hasn't been cooked."""
    item = plan.find_item(kitchen, plan_item_id)
    record = cooked.for_meal_item(kitchen.db, kitchen.household_id, item.id)
    if record is None:
        raise _not_cooked()
    return cooked_out(record)


@router.get("/plan/batches/{plan_batch_id}/cooked")
def get_batch_cooked(plan_batch_id: StoredInt, kitchen: Here) -> CookedOut:
    """What was cooked for this batch cook. 404 when it hasn't been cooked."""
    batch = batches.find_batch(kitchen, plan_batch_id)
    record = cooked.for_batch(kitchen.db, kitchen.household_id, batch.id)
    if record is None:
        raise _not_cooked()
    return cooked_out(record)


# --- "Cooked it": the proposal, and the confirm (0.7 K2) ---------------------------------------


class ChoiceAmount(BaseModel):
    """An amount typed on a row, in the ingredient's own units or one of its sizes. Zero is
    allowed ("none left")."""

    amount: Annotated[
        Decimal, Field(ge=0, le=1_000_000, max_digits=13, decimal_places=3), ShortAmount
    ]
    unit: Annotated[str, Field(min_length=1, max_length=40)] | None = None
    size_id: StoredInt | None = None

    @model_validator(mode="after")
    def _one_unit(self) -> ChoiceAmount:
        if (self.unit is None) == (self.size_id is None):
            raise ValueError("Give either a unit or a size_id.")
        return self


class ChoiceIn(BaseModel):
    """What the person chose on one row of the review (`key` is the row's `key`). Rows not
    mentioned are as proposed."""

    key: Annotated[str, Field(min_length=1, max_length=40)]
    use: bool = Field(default=True, description="The row's Use switch.")
    used: ChoiceAmount | None = Field(default=None, description="How much was used.")
    left: ChoiceAmount | None = Field(default=None, description="How much is left instead.")
    from_freezer: bool = Field(
        default=False, description="Take from the freezer too, when the rest isn't enough."
    )
    add_to_list: bool = Field(
        default=True, description="Put what is missing on the shopping list (ticked to start)."
    )

    @model_validator(mode="after")
    def _one_amount(self) -> ChoiceIn:
        if self.used is not None and self.left is not None:
            raise ValueError("Say how much was used or how much is left, not both.")
        return self


class CookPreviewIn(BaseModel):
    portions: Annotated[int, Field(ge=1, le=cooking.MOST_PORTIONS)] | None = Field(
        default=None,
        description="How many portions were cooked. Left out: the meal's own servings (a batch:"
        " the cook-day eaters plus a portion for each tub).",
    )
    answers: list[Answer] = Field(
        default_factory=list,
        max_length=5,
        description="Replies to the questions an earlier proposal asked.",
    )


class CookIn(CookPreviewIn):
    choices: list[ChoiceIn] = Field(default_factory=list, max_length=200)


def _choices(kitchen: Kitchen, given: list[ChoiceIn]) -> dict[str, deduction.Choice]:
    out: dict[str, deduction.Choice] = {}
    for one in given:
        if one.key in out:
            raise Problem(
                status.HTTP_422_UNPROCESSABLE_CONTENT,
                "twice",
                "An ingredient can be chosen only once.",  # proposed, for cabledrawer
            )
        amounts: dict[str, int | None] = {"used_milli": None, "left_milli": None}
        for name, typed in (("used_milli", one.used), ("left_milli", one.left)):
            if typed is None:
                continue
            if not (one.key.startswith("food:") and one.key[5:].isdigit()):
                raise Problem(
                    status.HTTP_422_UNPROCESSABLE_CONTENT,
                    "no_ingredient",
                    "There’s no ingredient to take that from.",
                )
            food = foods.find(kitchen, int(one.key[5:]))
            if typed.amount == 0:
                amounts[name] = 0
            else:
                value = AmountIn(amount=typed.amount, unit=typed.unit, size_id=typed.size_id)
                amounts[name] = foods.resolve(kitchen, food, value).milli
        out[one.key] = deduction.Choice(
            use=one.use,
            used_milli=amounts["used_milli"],
            left_milli=amounts["left_milli"],
            from_freezer=one.from_freezer,
            add_to_list=one.add_to_list,
        )
    return out


@router.post("/plan/items/{plan_item_id}/cook/preview")
def preview_item_cook(
    plan_item_id: StoredInt, body: CookPreviewIn, kitchen: Here
) -> deduction.ProposalOut:
    """What "Cooked it" would take from the pantry for this recipe in a meal: a row for each
    ingredient, with the packets it would use (the one that goes off first, the freezer left
    alone), what is missing, and the questions to answer first (send them back in `answers`).
    Changes nothing."""
    item = plan.find_item(kitchen, plan_item_id)
    return deduction.proposal_out(
        kitchen, cooking.preview_item(kitchen, item, body.portions, body.answers)
    )


@router.post("/plan/batches/{plan_batch_id}/cook/preview")
def preview_batch_cook(
    plan_batch_id: StoredInt, body: CookPreviewIn, kitchen: Here
) -> deduction.ProposalOut:
    """The same for a batch cook, worked out once for the cook-day eaters and the tubs."""
    batch = batches.find_batch(kitchen, plan_batch_id)
    return deduction.proposal_out(
        kitchen, cooking.preview_batch(kitchen, batch, body.portions, body.answers)
    )


class CookedWrite(BaseModel):
    """What a confirm answers: the change (it carries the Undo) and the record it wrote. `cooked`
    is null when the change has since been undone."""

    change: ChangeOut
    cooked: CookedOut | None


def _written(kitchen: Kitchen, change: Change) -> CookedWrite:
    data = change.undo_data or {}
    record = kitchen.db.get(CookedRecord, data.get("cooked_record_id", 0))
    if record is not None and record.household_id != kitchen.household_id:
        record = None  # pragma: no cover (an id only this household's own change holds)
    return CookedWrite(
        change=change_out(kitchen, change),
        cooked=cooked_out(record) if record is not None else None,
    )


def _confirm(kitchen: Kitchen, response: Response, make: Callable[[], Change]) -> CookedWrite:
    """One confirm: the household's lock, a retry with the same `Idempotency-Key` answers from
    the first change, and the commit."""
    lock_household(kitchen)
    earlier = replayed(kitchen)
    if earlier is None:
        change = make()
        earlier = commit(kitchen)
        if earlier is None:
            response.status_code = status.HTTP_201_CREATED
            return _written(kitchen, change)
    if earlier.kind != "cooked":
        raise Problem(
            status.HTTP_409_CONFLICT,
            "key_reused",
            "That change ID was already used for something else.",
        )
    response.status_code = status.HTTP_200_OK
    response.headers["Idempotent-Replayed"] = "true"
    return _written(kitchen, earlier)


@router.post("/plan/items/{plan_item_id}/cook", status_code=status.HTTP_201_CREATED)
def cook_item(
    plan_item_id: StoredInt, body: CookIn, kitchen: Here, response: Response
) -> CookedWrite:
    """Cooked it, for one recipe in a meal: take the ingredients out of the pantry as chosen
    (rows not mentioned are as proposed), as one change with its Undo, and write the cooked
    record. A second confirm for the same item is refused. A retry with the same
    `Idempotency-Key` takes nothing more."""
    return _confirm(
        kitchen,
        response,
        lambda: cooking.cook_item(
            kitchen,
            plan.find_item(kitchen, plan_item_id),
            body.portions,
            body.answers,
            _choices(kitchen, body.choices),
        ),
    )


@router.post("/plan/batches/{plan_batch_id}/cook", status_code=status.HTTP_201_CREATED)
def cook_batch(
    plan_batch_id: StoredInt, body: CookIn, kitchen: Here, response: Response
) -> CookedWrite:
    """Cooked it, for a batch cook: the ingredients are taken once, for the cook-day eaters
    and the tubs together. The tubs are the ones Cook once made. A second confirm is refused."""
    return _confirm(
        kitchen,
        response,
        lambda: cooking.cook_batch(
            kitchen,
            batches.find_batch(kitchen, plan_batch_id),
            body.portions,
            body.answers,
            _choices(kitchen, body.choices),
        ),
    )
