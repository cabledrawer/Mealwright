"""JSON shapes shared by the kitchen endpoints (docs/dev/api-0.2.md)."""

from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

CountedAsName = Literal["weight", "volume", "count"]
Number = Annotated[Decimal, Field(max_digits=15, decimal_places=3)]
PositiveNumber = Annotated[Decimal, Field(gt=0, max_digits=15, decimal_places=3)]


class Ref(BaseModel):
    id: int
    name: str


class Who(BaseModel):
    login_id: int | None
    name: str


class Undone(BaseModel):
    at: datetime
    who: Who


class ChangeOut(BaseModel):
    id: int
    kind: str
    at: datetime
    who: Who
    summary: str
    can_undo: bool
    undo_until: datetime
    undone: Undone | None


class SizeOut(BaseModel):
    id: int
    name: str
    plural: str
    amount: float
    display: str  # "Packet = 500 g"
    usual: bool
    added_when_shopping: bool


class SizeBrief(BaseModel):
    id: int | None
    name: str
    plural: str
    amount: float


class AsSoldOut(BaseModel):
    count: float
    size: SizeBrief


class AmountOut(BaseModel):
    amount: float
    unit: Literal["g", "ml", "count"]
    as_sold: AsSoldOut | None
    about: bool
    short: str  # "1½ packets"
    display: str  # "1½ packets · about 750 g"


class Answer(BaseModel):
    """A reply to an "ask once" question (docs/dev/api-0.2.md section 4.4)."""

    kind: Literal["weight_per_ml", "item_weight", "size"]
    food_id: int
    # weight_per_ml: grams in one household cup; item_weight: grams in one item.
    grams: PositiveNumber | None = None
    # size: its name ("loaf") and how many base units it holds (20 slices, 500 g).
    name: Annotated[str, Field(min_length=1, max_length=40)] | None = None
    amount: PositiveNumber | None = None
    remember: bool = True

    @model_validator(mode="after")
    def _complete(self) -> Answer:
        if self.kind == "size":
            if self.name is None or self.amount is None:
                raise ValueError("A size answer needs a name and an amount.")
        elif self.grams is None:
            raise ValueError("Please give the weight in grams.")
        return self


class AmountIn(BaseModel):
    """An amount someone typed: {"amount": 2, "unit": "packet"}, {"amount": 250,
    "unit": "g"} or {"amount": 1, "size_id": 12}."""

    amount: PositiveNumber
    unit: Annotated[str, Field(min_length=1, max_length=40)] | None = None
    size_id: int | None = None
    answers: list[Answer] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def _one_unit(self) -> AmountIn:
        if (self.unit is None) == (self.size_id is None):
            raise ValueError("Give either a unit or a size_id.")
        return self


class Ask(BaseModel):
    food_id: int
    food_name: str
    kind: Literal["weight_per_ml", "item_weight", "size"]
    question: str
    unit: str  # what the answer is in: g, ml or a count word
    per: str  # cup, item, or the size name
    cup_ml: int
    suggested: float | None
    name: str | None = None  # for kind "size": the size being asked about
