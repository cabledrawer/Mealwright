"""JSON shapes for fixing Mealie drafts by ingredient (spec section 6, "Fixing Mealie drafts by
ingredient", cabledrawer 15 Nov, 0.9.5-beta.2)."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from mealwright.api.v1.schemas import ChangeOut, Ref
from mealwright.errors import NAME_THE_NEW_INGREDIENT, PICK_AN_INGREDIENT, StoredInt
from mealwright.names import clean_name


class IngredientGroup(BaseModel):
    """The lines of the household's Mealie drafts that name one ingredient and are still
    unanswered, across every draft ("soya sauce", in 46 drafts)."""

    key: str  # the name as read, folded: what an answer names the group by
    name: str  # as read ("soya sauce")
    drafts: int  # how many drafts use it
    lines: int  # how many lines (a draft can write it twice)
    examples: list[str]  # up to two of the lines as written
    # An ingredient the household has that it may be ("Soy sauce"), where matching has one.
    suggestion: Ref | None
    # The first guess for a new ingredient, as the review gives one: its name, how it is
    # counted and where it is kept.
    new_name: str
    new_place: Ref | None


class IngredientGroups(BaseModel):
    groups: list[IngredientGroup]  # most-used first (the first `limit`)
    total: int  # every group still unanswered
    drafts: int  # Mealie drafts waiting
    recipes_ready: int  # Mealie recipes already in Recipes (proposed, for cabledrawer)
    places: list[Ref]  # the household's places, for "Where it's kept"


class WrittenLine(BaseModel):
    written: str  # one way the group's lines are written ("2 tbsp soya sauce")
    count: int  # how many unanswered lines write it this way


# F259: the route and its 200-line cap are proposed, for cabledrawer.
class GroupLines(BaseModel):
    """Every way one group's unanswered lines are written, most-used first: what "+ more" under
    the group's two examples shows (F259)."""

    key: str
    lines: list[WrittenLine]  # the first 200
    total: int  # every different way it is written


class GroupAnswer(BaseModel):
    """One answer for a whole group: an ingredient the household has (`ingredient`, with
    `food_id`), a new one (`new`, with `name` and `place_id`), or plain text (`text`: shown in
    the recipe, never on the shopping list or taken from the pantry)."""

    key: Annotated[str, Field(min_length=1, max_length=300)]
    kind: Literal["ingredient", "new", "text"]
    food_id: StoredInt | None = None
    name: Annotated[str, Field(max_length=100)] | None = None
    place_id: StoredInt | None = None

    @model_validator(mode="after")
    def _make_sense(self) -> GroupAnswer:
        if self.kind == "ingredient" and self.food_id is None:
            raise ValueError(PICK_AN_INGREDIENT)
        if self.kind == "new":
            self.name = clean_name(self.name or "")
            if not self.name:
                raise ValueError(NAME_THE_NEW_INGREDIENT)
        return self


class GroupAnswered(BaseModel):
    change: ChangeOut  # carries the Undo (7 days)
    drafts: int  # drafts the answer went into
    moved: int  # of them, recipes now in Recipes
    food: Ref | None  # the ingredient every line is tied to; null for plain text
