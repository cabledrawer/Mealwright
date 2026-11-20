"""JSON shapes for import drafts (docs/dev/recipe-import.md, "Drafts")."""

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, TypeAdapter, field_validator, model_validator

from mealwright.api.v1.import_schemas import CountedAs, ImportReview
from mealwright.api.v1.recipe_schemas import MAX_LINES, MAX_STEP_CHARS, MAX_STEPS, MAX_TAGS
from mealwright.api.v1.schemas import ChangeOut, Ref
from mealwright.errors import NAME_THE_NEW_INGREDIENT, PICK_AN_INGREDIENT, PICK_THE_MAKER, StoredInt
from mealwright.moment import Moment
from mealwright.names import clean_name

# What the box can hold: pasted text is refused over 100,000 characters (docs/dev/recipe-import.md),
# and a link is far shorter.
MAX_SOURCE_CHARS = 100_000
# The review as a draft keeps it, with the choices made on it, counted as it is stored. The
# real biggest review (200 lines, 100 steps of 5,000 characters) is about 0.7 MB; this leaves
# room and stops anything larger being stored.
MAX_REVIEW_BYTES = 2_000_000


def stored_size(model: BaseModel) -> int:
    """How much the database holds for this: the draft's columns are JSON written with
    `json.dumps` and its default `ensure_ascii=True`, so an emoji is 12 characters there
    (1 as typed). Counting characters of `model_dump_json()` would let about 12 MB through."""
    return len(json.dumps(model.model_dump(mode="json")))


_STORED = TypeAdapter(StoredInt)


def _numbers_fit(data: Any) -> None:
    """Every whole number anywhere in the request fits what the database stores. A draft keeps
    a whole review, whose numbers (an ingredient's id, a photo's id, the counts) are looked up
    or stored, so each one is checked where the request is read, as `StoredInt` does for a
    plain field: too big is 422 `bad_number`, never an error from the database."""
    stack = [data]
    while stack:
        item = stack.pop()
        if isinstance(item, bool):
            continue
        if isinstance(item, int):
            _STORED.validate_python(item)
        elif isinstance(item, dict):
            stack.extend(item.values())
        elif isinstance(item, list):
            stack.extend(item)


class DraftChoice(BaseModel):
    """What one line was set to on the review (the screen's own `Choice`), kept as it was.

    - `ingredient`: an ingredient the household has (`food`); `learn` adds the line's words as
      another name of it on Save ("Same as Onions").
    - `new` and `staple`: a new ingredient or staple, made only on Save (`name`, `counted_as`,
      `place_id`).
    - `here`: "Made in this recipe" (F108): the line is made earlier in the same recipe, so it is
      saved as words only, never tied to an ingredient and never taken from the pantry.
    - `recipe` (0.8, F188): the line uses another recipe (`recipe`); `place_id` is where the
      pantry keeps it, set on that recipe's made-ahead ingredient on Save when it has none."""

    kind: Literal["ingredient", "new", "staple", "here", "recipe"]
    food: Ref | None = None
    recipe: Ref | None = None
    learn: bool = False
    name: Annotated[str, Field(max_length=100)] | None = None
    counted_as: CountedAs = "weight"
    place_id: StoredInt | None = None

    @field_validator("name")
    @classmethod
    def _tidy(cls, value: str | None) -> str | None:
        return None if value is None else clean_name(value)

    @model_validator(mode="after")
    def _make_sense(self) -> DraftChoice:
        if self.kind == "ingredient" and self.food is None:
            raise ValueError(PICK_AN_INGREDIENT)
        if self.kind == "here" and (self.food is not None or self.name or self.learn):
            raise ValueError("Made in this recipe has no ingredient, name or learned name.")
        if self.kind == "recipe" and (self.recipe is None or self.food is not None or self.learn):
            raise ValueError(PICK_THE_MAKER)
        if self.kind in ("new", "staple") and not self.name:
            raise ValueError(NAME_THE_NEW_INGREDIENT)
        return self


class DraftChoices(BaseModel):
    """Every choice so far: the boxes on top of the review (as typed, so a half-typed number
    is kept too) and a choice for each line the person has settled. A line with no entry here
    has no choice yet (a matched line needs none)."""

    # null: left as read (the review's own).
    name: Annotated[str, Field(max_length=200)] | None = None
    serves: Annotated[str, Field(max_length=10)] | None = None
    minutes: Annotated[str, Field(max_length=10)] | None = None
    # The pints switch on a US recipe ("us" or "uk"); null: left as the review read it.
    pints: Literal["uk", "us"] | None = None
    # The line's place in the review → its choice. (JSON keys are text; the screen's are numbers.)
    lines: dict[int, DraftChoice] = Field(default_factory=dict, max_length=MAX_LINES)


class DraftIn(BaseModel):
    """What the review screen sends to keep a draft: the box's text, the review as the server
    sent it, and the choices made on it. The server checks the shape and the sizes, and that
    the photo is the household's own; Save checks everything again when the recipe is saved."""

    text: Annotated[str, Field(min_length=1, max_length=MAX_SOURCE_CHARS)]
    review: ImportReview
    choices: DraftChoices = Field(default_factory=DraftChoices)

    @model_validator(mode="before")
    @classmethod
    def _numbers(cls, data: Any) -> Any:
        _numbers_fit(data)
        return data

    @model_validator(mode="after")
    def _fits(self) -> DraftIn:
        review = self.review
        if (
            len(review.lines) > MAX_LINES
            or len(review.steps) > MAX_STEPS
            or len(review.tags) > MAX_TAGS
            or any(len(step.text) > MAX_STEP_CHARS for step in review.steps)
            or stored_size(review) + stored_size(self.choices) > MAX_REVIEW_BYTES
        ):
            raise ValueError("That draft is too big to keep.")
        for index in self.choices.lines:
            if not 0 <= index < len(review.lines) or review.lines[index].kind != "ingredient":
                raise ValueError("A choice is for a line that isn’t there.")
        return self


class DraftSource(BaseModel):
    kind: Literal["link", "text", "mealie"]
    site: str | None  # "bbcgoodfood.com"; null for pasted text


class DraftBrief(BaseModel):
    """A draft in the Drafts list: "Chettinad kuzhambu · From bbcgoodfood.com · started by
    Remy · 13 days left · 6 of 9 ingredients checked"."""

    id: int
    name: str
    source: DraftSource
    started_by: str
    started_at: Moment
    updated_at: Moment  # the last time anyone changed it: the 15 days count from here
    expires_at: Moment
    days_left: int  # 15 for a draft changed just now; 1 on its last day
    lines_total: int  # ingredient lines
    lines_checked: int  # tied to an ingredient (matched, or chosen)
    # The first few lines still to check, as written (0.9.5: the "From Mealie" rows).
    waiting: list[str] = Field(default_factory=list)


class DraftList(BaseModel):
    drafts: list[DraftBrief]
    count: int


class DraftOut(DraftBrief):
    """A draft to carry on with: the text in the box, what Mealwright read, and the choices.
    Ingredients that have gone since it was kept (removed or merged away) are no longer
    offered: their lines are back to "needs you" and their choices are dropped."""

    text: str
    review: ImportReview
    choices: DraftChoices


class DraftRemoved(BaseModel):
    change: ChangeOut  # carries the Undo (7 days)
