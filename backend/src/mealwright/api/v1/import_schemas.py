"""JSON shapes for importing a recipe (docs/dev/recipe-import.md, "The import's API")."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from mealwright.amounts import MAX_AMOUNT
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
    StepWaitIn,
)
from mealwright.api.v1.schemas import ChangeOut, Ref
from mealwright.errors import StoredInt
from mealwright.names import clean_name

# Sections of one recipe that may be made their own recipes in one save (F190).
MAX_OWN_RECIPES = 5

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


class PintReading(BaseModel):
    """What a line that says pints comes to in each kind of pint, in ml (568 ml a UK pint, 473
    ml a US pint). The line's `amount` is one of them; the review's switch picks the other."""

    uk_ml: Annotated[float, Field(ge=0, le=MAX_AMOUNT, allow_inf_nan=False)]
    us_ml: Annotated[float, Field(ge=0, le=MAX_AMOUNT, allow_inf_nan=False)]


class ReviewPints(BaseModel):
    """Pints on this review (0.6; spec "Reading choices, kept").

    - `household`: the household's own pint ("uk" until Settings says otherwise).
    - `us_site`: the page looks American (a listed site, or the page says en-US).
    - `reading`: the pint the lines were read with. A US site is read with US pints when the
      household's are UK (the review shows the switch for it); otherwise the household's own.
    The screen shows the switch when `us_site` and `household` is "uk"."""

    household: Literal["uk", "us"] = "uk"
    us_site: bool = False
    reading: Literal["uk", "us"] = "uk"


class OwnRecipeNote(BaseModel):
    """A section heading the person made its own recipe on Check (0.8, F190): what the new Made
    ahead recipe is called and how much it makes. Only the screen sets it (it is kept in a
    draft); the server never sends it. Save takes the section back as `own_recipes`."""

    name: Annotated[str, Field(min_length=1, max_length=200)]
    amount: Annotated[float, Field(gt=0, le=MAX_AMOUNT, allow_inf_nan=False)]
    unit: Annotated[str, Field(min_length=1, max_length=30)]

    @field_validator("name", "unit")
    @classmethod
    def _tidy(cls, value: str) -> str:
        value = clean_name(value)
        if not value:
            raise ValueError("Give the recipe a name.")
        return value


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
    # null unless the line says pints: its amount in each kind of pint.
    pint_ml: PintReading | None = None
    # The line is Optional (R3): "(optional)" was in it, or it is under a "For serving" heading.
    # The person can switch it on or off on the review; Save sends it to the recipe's line.
    optional: bool = False
    # A heading made its own recipe on Check (F190): kept in a draft, never sent by the server.
    own: OwnRecipeNote | None = None
    # The other choice of an "or" line (F217, 0.8): "1 large shrak or 2 medium flat bread" is the
    # shrak, with the flat bread here as a line of its own. Check offers "Use this instead", which
    # swaps the two on the screen; this line's note already holds the other choice, so Save needs
    # nothing new. Never set on the alternative itself.
    alternative: ReviewLine | None = None


class ReviewMakes(BaseModel):
    """What the recipe makes, in plain units (24 cookies is 24), as the recipe shows it. Save
    takes the same two fields back (as `MakesIn`, which reads the amount like any other)."""

    amount: float
    unit: str


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
    kind: Literal["link", "text", "mealie"]  # "mealie": a recipe from an Import from Mealie
    url: str | None  # where the page was in the end, after any redirects
    site: str | None  # "bbcgoodfood.com"


class ReviewStep(BaseModel):
    kind: Literal["step", "heading"]
    text: str
    # The step says it is optional ("(optional)", "Optional: …"): the word is taken out of the
    # text and the step is Optional instead (R3). The person can switch it on or off.
    optional: bool = False
    # A wait the reader suggests from the words ("marinate for 4 hours or overnight"), M1. It is
    # only a suggestion: Check asks "Yes, it waits", "Change" or "No wait", and Save sends back
    # what was kept (`ImportSave.steps[].wait`).
    wait: StepWaitIn | None = None
    # The person said "Yes, it waits" to the suggestion (kept with a draft; Save never sends it).
    wait_confirmed: bool = False


class ReviewSecondMethod(BaseModel):
    """The page's second way of cooking it (M2): "Stovetop" and "Instant Pot" sections of the
    method. The review's own `steps` are the first way's; the ingredients are shared (both ways
    start with a copy of them, and the person can change them in the editor)."""

    name: str
    steps: list[ReviewStep]


class ImportReview(BaseModel):
    """Everything the review screen shows. Nothing is saved yet (except a waiting photo)."""

    source: ReviewSource
    name: str
    description: str | None
    author: str | None
    time_minutes: int | None
    # The page's own total time, before any suggested wait was taken off `time_minutes` (M1): when
    # the person says "No wait" or changes a wait, Check works the time out again from this.
    page_time_minutes: int | None = None
    serves: int | None
    makes: ReviewMakes | None
    tags: list[str]
    nutrition: NutritionIn
    photo: ReviewPhoto
    lines: list[ReviewLine]
    steps: list[ReviewStep]
    # Two ways of cooking it found in the method (M2): the first's name, and the second.
    method_name: str | None = None
    second_method: ReviewSecondMethod | None = None
    counts: ReviewCounts
    lines_cut: bool  # the page had more than 200 ingredient lines: the first 200 are here
    steps_cut: bool  # the page had more than 100 steps: the first 100 are here
    steps_shortened: int  # steps cut to 5,000 characters
    left_out: list[LeftOutOut]
    pints: ReviewPints = Field(default_factory=ReviewPints)
    # Several links were pasted: only the first is read, one at a time. How many were left
    # unread (0 for a single link or pasted text).
    more_links: int = 0


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
    - `own_recipe` (0.8, F190): the line uses the recipe this same save makes from a section
      (`own_recipes[own_recipe]` of the save).
    - `recipe` (0.8, F188): the line uses another recipe of the household (`recipe_id`), the same
      link as a recipe line made in the editor. `place_id` is where the pantry keeps it: it is
      set on that recipe's own made-ahead ingredient when that has no usual place yet.
    A line with no link is saved with its words only ("not linked")."""

    kind: Literal["ingredient", "new", "staple", "recipe", "own_recipe"]
    food_id: StoredInt | None = None
    recipe_id: StoredInt | None = None
    own_recipe: StoredInt | None = None
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
        if self.kind == "recipe" and self.recipe_id is None:
            raise ValueError("Pick the recipe that makes it.")
        if self.kind == "own_recipe" and self.own_recipe is None:
            raise ValueError("Pick the recipe that makes it.")
        return self


class ImportLineIn(BaseModel):
    kind: Literal["ingredient", "heading"] = "ingredient"
    words: Annotated[str, Field(max_length=200)] = ""
    amount: Milli = None
    unit: LineUnit = None
    size_id: StoredInt | None = None
    note: Annotated[str, Field(max_length=200)] | None = None
    link: ImportLinkIn | None = None
    optional: bool = False  # R3: the review's Optional switch


class ImportSecondMethod(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=60)]
    steps: list[RecipeStepIn] = Field(default_factory=list, max_length=MAX_STEPS)


class ImportOwnRecipe(BaseModel):
    """A section made its own recipe (0.8, F190): a new Made ahead recipe saved
    in the same save as the main one, which uses it as one line (a line whose link is
    `own_recipe` with this recipe's place in `own_recipes`). Its lines are checked like the main
    recipe's (a link may be an ingredient, a new ingredient or another recipe, never another
    section recipe); the two are saved together or not at all."""

    name: Annotated[str, Field(min_length=1, max_length=200)]
    makes: MakesIn
    lines: list[ImportLineIn] = Field(default_factory=list, max_length=MAX_LINES)
    steps: list[RecipeStepIn] = Field(default_factory=list, max_length=MAX_STEPS)

    @field_validator("name")
    @classmethod
    def _tidy(cls, value: str) -> str:
        value = clean_name(value)
        if not value:
            raise ValueError("Give the recipe a name.")
        return value


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
    # Two ways of cooking it (M2): the first one's name, and the second. Both start with the
    # ingredient lines above; the time is the page's single time for both.
    method_name: Annotated[str, Field(max_length=60)] | None = None
    second_method: ImportSecondMethod | None = None
    # Sections made their own recipes (F190): saved with this one, all or nothing. Each is used
    # by a line of `lines` whose link is `own_recipe`. One Undo takes them all back.
    own_recipes: list[ImportOwnRecipe] = Field(default_factory=list, max_length=MAX_OWN_RECIPES)
    # Where it came from: the web address (a link import only) and the page's author.
    source_url: Annotated[str, Field(max_length=2000)] | None = None
    source_author: Annotated[str, Field(max_length=200)] | None = None
    # The waiting photo the review holds (`photo.photo.id`), or the photo the draft is keeping.
    photo_id: StoredInt | None = None
    # Saving from a draft: its id. The draft is deleted in the same transaction, and its photo
    # (`photo_id`) becomes the recipe's.
    draft_id: StoredInt | None = None

    @model_validator(mode="after")
    def _own_recipes_fit(self) -> ImportSave:
        used: set[int] = set()
        for line in self.lines:
            link = line.link
            if line.kind == "heading" or link is None or link.kind != "own_recipe":
                continue
            if link.own_recipe is None or link.own_recipe >= len(self.own_recipes):
                raise ValueError("That section’s recipe isn’t in this save.")
            used.add(link.own_recipe)
        for own in self.own_recipes:
            for line in own.lines:
                if line.link is not None and line.link.kind == "own_recipe":
                    raise ValueError("A section’s own recipe can’t use another one.")
        if used != set(range(len(self.own_recipes))):
            raise ValueError("A section made its own recipe needs the line that uses it.")
        return self


class ImportSaved(BaseModel):
    recipe: Ref
    change: ChangeOut  # the one entry in Recent changes; its Undo takes the whole save back
    new_ingredients: list[Ref]
    learned: int  # other names added
