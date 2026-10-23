"""JSON shapes for importing a recipe (docs/dev/recipe-import.md, "The import's API")."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from mealwright.api.v1.recipe_schemas import (
    MAX_LINES,
    MAX_STEPS,
    MAX_TAG_CHARS,
    MAX_TAGS,
    LineUnit,
    MakesIn,
    Milli,
    NutritionIn,
    PhotoOut,
    RecipeStepIn,
    SizeRef,
)
from mealwright.api.v1.schemas import ChangeOut, Ref
from mealwright.errors import StoredInt
from mealwright.names import clean_name

Label = Literal["matched", "to_confirm", "needs_you", "staple"]
CountedAs = Literal["weight", "volume", "count"]


class ImportStart(BaseModel):
    """What the one box holds: a link, or pasted recipe text. Mealwright works out which."""

    text: Annotated[str, Field(max_length=200_000)]
    # "Import again as a copy": skip the "You already have this recipe" check.
    again: bool = False


# --- What came across (the review) -----------------------------------------------------------


class NewIngredientOut(BaseModel):
    """The first guess for "New ingredient" and "Treat as staple", changeable on the screen.
    Nothing is created until Save."""

    name: str
    counted_as: CountedAs
    place: Ref | None  # the household's Cupboard, or null if it has none


class ReviewLine(BaseModel):
    """One ingredient line (or a heading) as written, as read, and what it is in the kitchen.
    `words`, `amount`, `unit`, `note` and `size` are what the saved line will hold; send them
    back to Save as they are."""

    kind: Literal["ingredient", "heading"]
    written: str  # the line as written on the page or in the pasted text
    words: str  # the name as written ("thuvaram paruppu"), for the recipe line
    amount: float | None
    amount_text: str | None
    unit: str | None
    size: SizeRef | None
    note: str | None
    readable: bool  # false: no name could be read ("Needs you")
    # null for a heading.
    label: Label | None
    food: Ref | None  # matched or staple: the ingredient; to_confirm: the best guess
    place: str | None  # where the ingredient lives ("Cupboard"), for matched and staple
    matched_by: str | None  # the words of the line that matched
    counts: bool  # counts towards stock (staples and "to taste" never do)
    new_ingredient: NewIngredientOut | None
    learn_name: str | None  # what "Same as …" adds as another name of the ingredient


class ReviewCounts(BaseModel):
    matched: int
    to_confirm: int
    needs_you: int
    staple: int


class LeftOutOut(BaseModel):
    """A note or tip in pasted text that was left out: "4 lines after “Tips” were left out"."""

    heading: str
    lines: int


class ReviewPhoto(BaseModel):
    """What happened to the page's main photo.

    - `downloaded`: held as a waiting photo until Save (`photo` is set).
    - `off`: "Download recipe photos" is switched off; the screen says "Photo not downloaded"
      and links to Settings → Privacy.
    - `none`: nothing to download (pasted text, or the page has no photo).
    - `failed`: the download was refused or didn't work; `message` says why.
    """

    state: Literal["downloaded", "off", "none", "failed"]
    photo: PhotoOut | None = None
    message: str | None = None


class ReviewSource(BaseModel):
    kind: Literal["link", "text"]
    url: str | None  # where the page was in the end, after any redirects
    site: str | None  # "bbcgoodfood.com"


class ReviewStep(BaseModel):
    kind: Literal["step", "heading"]
    text: str


class ImportReview(BaseModel):
    """Everything the review screen shows. Nothing is saved yet (except a waiting photo)."""

    source: ReviewSource
    name: str
    description: str | None
    author: str | None
    time_minutes: int | None
    serves: int | None
    makes: MakesIn | None
    tags: list[str]
    nutrition: NutritionIn
    photo: ReviewPhoto
    lines: list[ReviewLine]
    steps: list[ReviewStep]
    counts: ReviewCounts
    lines_cut: bool  # the page had more than 200 ingredient lines: the first 200 are here
    steps_cut: bool  # the page had more than 100 steps: the first 100 are here
    steps_shortened: int  # steps cut to 5,000 characters
    left_out: list[LeftOutOut]


class AlreadyImported(BaseModel):
    """409 `already_imported`: the household already has a recipe from this address."""

    recipe: Ref
    imported_at: str
    site: str
    photo: PhotoOut | None


# --- Save ------------------------------------------------------------------------------------


class ImportLinkIn(BaseModel):
    """How a line is tied to an ingredient when it is saved.

    - `ingredient`: an ingredient the household has (`food_id`). `learn` adds that name as another
      name of the ingredient ("Same as Onions" for "red onion").
    - `new`: a new ingredient (`name`, `counted_as`, `place_id`), made on Save.
    - `staple`: a new staple ingredient: the line never counts.
    A line with no link is saved with its words only ("not linked")."""

    kind: Literal["ingredient", "new", "staple"]
    food_id: StoredInt | None = None
    learn: Annotated[str, Field(max_length=100)] | None = None
    name: Annotated[str, Field(max_length=100)] | None = None
    counted_as: CountedAs = "weight"
    place_id: StoredInt | None = None

    @field_validator("name", "learn")
    @classmethod
    def _tidy(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return clean_name(value) or None

    @model_validator(mode="after")
    def _make_sense(self) -> ImportLinkIn:
        if self.kind == "ingredient" and self.food_id is None:
            raise ValueError("Pick an ingredient.")
        if self.kind in ("new", "staple") and not self.name:
            raise ValueError("Type a name for the new ingredient.")
        return self


class ImportLineIn(BaseModel):
    kind: Literal["ingredient", "heading"] = "ingredient"
    words: Annotated[str, Field(max_length=200)] = ""
    amount: Milli = None
    unit: LineUnit = None
    size_id: StoredInt | None = None
    note: Annotated[str, Field(max_length=200)] | None = None
    link: ImportLinkIn | None = None


class ImportSave(BaseModel):
    """The reviewed recipe, saved whole. The server checks all of it again, as for any recipe."""

    name: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=200)] | None = None
    time_minutes: Annotated[int, Field(ge=1, le=14_400)] | None = None
    serves: Annotated[int, Field(ge=1, le=99)] | None = None
    makes: MakesIn | None = None
    tags: list[Annotated[str, Field(min_length=1, max_length=MAX_TAG_CHARS)]] = Field(
        default_factory=list, max_length=MAX_TAGS
    )
    nutrition: NutritionIn = Field(default_factory=NutritionIn)
    lines: list[ImportLineIn] = Field(default_factory=list, max_length=MAX_LINES)
    steps: list[RecipeStepIn] = Field(default_factory=list, max_length=MAX_STEPS)
    # Where it came from: the web address (a link import only) and the page's author.
    source_url: Annotated[str, Field(max_length=2000)] | None = None
    source_author: Annotated[str, Field(max_length=200)] | None = None
    # The waiting photo the review holds (`photo.photo.id`).
    photo_id: StoredInt | None = None


class ImportSaved(BaseModel):
    recipe: Ref
    change: ChangeOut  # the one entry in Recent changes; its Undo takes the whole save back
    new_ingredients: list[Ref]
    learned: int  # other names added
