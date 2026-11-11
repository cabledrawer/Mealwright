"""JSON shapes for recipes (docs/dev/api-0.4-recipes.md)."""

import re
from datetime import datetime
from decimal import Decimal
from fractions import Fraction
from typing import Annotated, Any, Literal

from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    WithJsonSchema,
    field_validator,
    model_validator,
)

from mealwright.amounts import MAX_AMOUNT_TEXT
from mealwright.api.v1.schemas import Ref, ShortAmount, Who
from mealwright.errors import StoredInt
from mealwright.names import clean_name, one_line, text_block
from mealwright.step_waits import MAX_WAIT_MINUTES, OVERNIGHT_MINUTES

# --- What people may type -------------------------------------------------------------------

MAX_LINES = 200  # ingredient lines and headings together
MAX_STEPS = 100  # steps and headings together
MAX_STEP_CHARS = 5_000
MAX_TAGS = 20
MAX_TAG_CHARS = 40

# The units a line may use (cabledrawer 19 Oct, question 16): the rest is "the ingredient's own
# sizes" (size_id) or a plain count (no unit).
LINE_UNITS = ("g", "kg", "ml", "l", "tsp", "tbsp", "cup", "pinch")
UNIT_ALIASES = {
    "g": "g",
    "gram": "g",
    "grams": "g",
    "gm": "g",
    "gms": "g",
    "kg": "kg",
    "kilo": "kg",
    "kilos": "kg",
    "kilogram": "kg",
    "kilograms": "kg",
    "ml": "ml",
    "millilitre": "ml",
    "millilitres": "ml",
    "milliliter": "ml",
    "milliliters": "ml",
    "l": "l",
    "litre": "l",
    "litres": "l",
    "liter": "l",
    "liters": "l",
    "tsp": "tsp",
    "teaspoon": "tsp",
    "teaspoons": "tsp",
    "tbsp": "tbsp",
    "tablespoon": "tbsp",
    "tablespoons": "tbsp",
    "cup": "cup",
    "cups": "cup",
    "pinch": "pinch",
    "pinches": "pinch",
}
MAKES_UNITS = ("g", "kg", "ml", "l")
MAX_AMOUNT_MILLI = 1_000_000_000  # 1,000,000 of a unit, as in the pantry

GLYPHS = {
    "¼": Fraction(1, 4),
    "½": Fraction(1, 2),
    "¾": Fraction(3, 4),
    "⅓": Fraction(1, 3),
    "⅔": Fraction(2, 3),
    "⅛": Fraction(1, 8),
    "⅜": Fraction(3, 8),
    "⅝": Fraction(5, 8),
    "⅞": Fraction(7, 8),
    "⅕": Fraction(1, 5),
    "⅖": Fraction(2, 5),
    "⅗": Fraction(3, 5),
    "⅘": Fraction(4, 5),
    "⅙": Fraction(1, 6),
    "⅚": Fraction(5, 6),
}
_GLYPH_TEXT = {
    125: "⅛",
    250: "¼",
    333: "⅓",
    375: "⅜",
    500: "½",
    625: "⅝",
    667: "⅔",
    750: "¾",
    875: "⅞",
}
BAD_AMOUNT = "Type an amount like 200, 1.5, ½ or 1½, or leave it empty."


_DECIMAL = re.compile(r"^(\d+)(?:\.(\d+))?$")
_GLYPH_AMOUNT = re.compile(rf"^(?:(\d+)\s*)?([{''.join(GLYPHS)}])$")
_SLASH_AMOUNT = re.compile(r"^(?:(\d+)\s+)?(\d+)\s*/\s*(\d+)$")


def fraction_of(text: str) -> Fraction:
    """200, 1.5, ½, 1½, 1 ½, 1/2 or 1 1/2 as an exact fraction (ValueError otherwise)."""
    text = text.strip().replace("\u2044", "/").replace("\u2215", "/")
    if found := _DECIMAL.match(text):
        return Fraction(Decimal(text))
    if found := _GLYPH_AMOUNT.match(text):
        return Fraction(int(found[1] or 0)) + GLYPHS[found[2]]
    if (found := _SLASH_AMOUNT.match(text)) and int(found[3]) > 0:
        return Fraction(int(found[1] or 0)) + Fraction(int(found[2]), int(found[3]))
    raise ValueError(BAD_AMOUNT)


def parse_amount(value: Any) -> int | None:
    """What someone typed as an amount, in thousandths: 1½ is 1500. Empty is None (no
    amount). Numbers and text are both fine. Zero and negatives are refused, and so is
    text longer than MAX_AMOUNT_TEXT, before it is parsed."""
    if value is None:
        return None
    if isinstance(value, bool):
        raise ValueError(BAD_AMOUNT)
    if isinstance(value, int | float | Decimal):
        try:
            fraction = Fraction(Decimal(str(value)))
        except ArithmeticError:
            raise ValueError(BAD_AMOUNT) from None
    elif isinstance(value, str):
        if len(value) > MAX_AMOUNT_TEXT:
            raise ValueError(BAD_AMOUNT)
        if not value.strip():
            return None
        fraction = fraction_of(value)
    else:
        raise ValueError(BAD_AMOUNT)
    milli = int(fraction * 1000 + Fraction(1, 2))  # halves round up
    if milli <= 0:
        raise ValueError("Use an amount above 0, or leave it empty.")
    if milli > MAX_AMOUNT_MILLI:
        raise ValueError("That’s too much: at most 1,000,000.")
    return milli


def amount_text(milli: int | None) -> str | None:
    """1500 → "1½", 500 → "½", 200000 → "200", 1200 → "1.2"."""
    if milli is None:
        return None
    whole, part = divmod(milli, 1000)
    if part == 0:
        return str(whole)
    if part in _GLYPH_TEXT:
        return f"{whole or ''}{_GLYPH_TEXT[part]}"
    return f"{milli / 1000:.3f}".rstrip("0").rstrip(".")


def parse_line_unit(value: Any) -> str | None:
    """g, kg, ml, l, tsp, tbsp, cup or pinch (also "grams", "tablespoons"…). Empty, or
    "count": no unit (a count: "10 shallots")."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("Pick a unit from the list.")
    word = one_line(value).strip().lower()
    if word in ("", "count", "item", "items", "whole"):
        return None
    code = UNIT_ALIASES.get(word)
    if code is None:
        raise ValueError(
            "Pick g, kg, ml, l, tsp, tbsp, cup or pinch, or one of the ingredient\u2019s own sizes."
        )
    return code


def parse_makes_unit(value: str) -> str:
    """g, kg, ml or l, or a count word ("dosas", "portions")."""
    word = clean_name(value)
    if not word:
        raise ValueError("Say what it makes, like litres, g or dosas.")
    code = UNIT_ALIASES.get(word.lower())
    return code if code in MAKES_UNITS else word


Milli = Annotated[
    int | None,
    BeforeValidator(parse_amount),
    WithJsonSchema(
        {
            "anyOf": [{"type": "number"}, {"type": "string", "examples": ["1½"]}, {"type": "null"}],
            "description": "A number, or text such as 1½, ½ or 1 1/2. Empty or null: no amount.",
        },
        mode="validation",
    ),
]
LineUnit = Annotated[str | None, BeforeValidator(parse_line_unit)]


def _tidy(value: str | None) -> str | None:
    """A one-line optional text: refused if it hides something, trimmed, empty is None."""
    if value is None:
        return None
    cleaned = " ".join(one_line(value).split())
    return cleaned or None


# --- Input ------------------------------------------------------------------------------------


class RecipeLineIn(BaseModel):
    """One ingredient line, or a heading. Send `id` for a line the recipe already has, so
    it keeps its identity (and an ingredient merge can follow it); leave it out for a new
    line."""

    id: StoredInt | None = None
    kind: Literal["ingredient", "heading"] = "ingredient"
    # The recipe's own words ("thuvaram paruppu"). May be empty when `food_id` or
    # `recipe_id` is given: it then starts as that ingredient's or recipe's name.
    words: Annotated[str, Field(max_length=200)] = ""
    amount: Milli = None
    unit: LineUnit = None
    size_id: StoredInt | None = None  # one of the linked ingredient's own sizes ("1 packet")
    food_id: StoredInt | None = None
    recipe_id: StoredInt | None = None  # another recipe used as an ingredient
    note: Annotated[str, Field(max_length=200)] | None = None
    # Optional (R3): adding the recipe to the plan asks whether it will be used.
    optional: bool = False

    @field_validator("words")
    @classmethod
    def _words(cls, value: str) -> str:
        return " ".join(one_line(value).split())

    @field_validator("note")
    @classmethod
    def _note(cls, value: str | None) -> str | None:
        return _tidy(value)

    @model_validator(mode="after")
    def _make_sense(self) -> RecipeLineIn:
        if self.kind == "heading":
            if not self.words:
                raise ValueError("Type the heading.")
            if (
                any(
                    part is not None
                    for part in (
                        self.amount,
                        self.unit,
                        self.size_id,
                        self.food_id,
                        self.recipe_id,
                        self.note,
                    )
                )
                or self.optional
            ):
                raise ValueError("A heading has only words.")
            return self
        if self.food_id is not None and self.recipe_id is not None:
            raise ValueError("A line is linked to an ingredient or to a recipe, not both.")
        if self.size_id is not None:
            if self.unit is not None:
                raise ValueError("Pick a unit or one of the ingredient\u2019s own sizes, not both.")
            if self.food_id is None:
                raise ValueError("A size belongs to a linked ingredient.")
        if self.recipe_id is not None and self.size_id is not None:
            raise ValueError("A recipe has no sizes.")
        if not self.words and self.food_id is None and self.recipe_id is None:
            raise ValueError("Type what it is, or pick an ingredient.")
        return self


WaitKind = Literal["marinate", "soak", "ferment", "rest", "chill", "prove"]


class StepWaitIn(BaseModel):
    """A step that waits (M1): marinate, soak, ferment... for a range of minutes, or a range that
    ends at "overnight" (which counts as 12 hours). `max_minutes` left out: one length."""

    kind: WaitKind
    min_minutes: Annotated[int, Field(ge=1, le=MAX_WAIT_MINUTES)]
    max_minutes: Annotated[int, Field(ge=1, le=MAX_WAIT_MINUTES)] | None = None
    overnight: bool = False

    @model_validator(mode="after")
    def _range(self) -> StepWaitIn:
        longest = self.max_minutes or self.min_minutes
        if self.overnight:
            longest = max(longest, OVERNIGHT_MINUTES)
        if longest < self.min_minutes:
            raise ValueError("The longest wait can't be shorter than the shortest.")
        self.max_minutes = longest
        return self


class StepWaitOut(BaseModel):
    kind: str  # one of the kinds, or "wait" for a recipe whose waits are of different kinds
    min_minutes: int
    max_minutes: int
    overnight: bool


HandsKind = Literal["hands", "waiting"]
EquipmentKind = Literal["hob", "pressure", "oven", "none"]


class StepTimingIn(BaseModel):
    """What a person set by hand for Batch cook (Experimental): hands-on or waiting, the minutes,
    and the equipment. A value left out or null is not set by hand: it is guessed from the step's
    words (and stays a guess, even when the words change)."""

    hands: HandsKind | None = None
    minutes: Annotated[int, Field(ge=1, le=MAX_WAIT_MINUTES)] | None = None
    equipment: EquipmentKind | None = None


class StepTimingOut(BaseModel):
    """A step's timing as it is now: each value, and whether it is still a guess (true) or was
    set by hand (false). Null for a heading."""

    hands: HandsKind
    minutes: int
    equipment: EquipmentKind
    hands_guessed: bool
    minutes_guessed: bool
    equipment_guessed: bool


class RecipeStepIn(BaseModel):
    kind: Literal["step", "heading"] = "step"
    text: Annotated[str, Field(min_length=1, max_length=MAX_STEP_CHARS)]
    # An Optional step (R3): shown with "Optional step"; a heading is never optional.
    optional: bool = False
    # The step waits (M1): null for none. A heading never waits.
    wait: StepWaitIn | None = None
    # What was set by hand for Batch cook (B1). Left out: the step keeps what its old self had
    # (the same words). Null, or a value left out inside it: guessed from the words.
    timing: StepTimingIn | None = None
    # Which ingredient lines this step uses, set by hand (0.7, for Cook mode's per-step
    # ingredients): positions in this save's `lines`, counting from 0, so a new line can be
    # linked in the same save. Left out (null): the step keeps the links it had, if it is
    # the same step (same words) and the line is still in the recipe. [] : none.
    # In range is checked against `lines` in RecipeIn; StoredInt refuses a huge one as bad_number.
    lines: list[StoredInt] | None = Field(
        default=None,
        max_length=MAX_LINES,
        description=(
            "The ingredient lines this step uses, set by hand: positions in this save's"
            " `lines`, counting from 0. Left out or null: the step keeps the links it had if"
            " its words are unchanged and the line is still in the recipe. [] : none."
        ),
    )

    @model_validator(mode="after")
    def _check(self) -> RecipeStepIn:
        if self.kind == "heading":
            self.text = " ".join(one_line(self.text).split())
            if len(self.text) > 200:
                raise ValueError("A heading is at most 200 characters.")
            if self.optional or self.wait is not None or self.timing is not None:
                raise ValueError("A heading has only words.")
        else:
            self.text = text_block(self.text).strip()
        if not self.text:
            raise ValueError("Type the step.")
        if self.lines is not None:
            if self.kind == "heading" and self.lines:
                raise ValueError("A heading has no ingredients.")
            self.lines = list(dict.fromkeys(self.lines))
        return self


class MakesIn(BaseModel):
    amount: Milli
    unit: Annotated[str, Field(min_length=1, max_length=30)]

    @field_validator("unit")
    @classmethod
    def _unit(cls, value: str) -> str:
        return parse_makes_unit(value)

    @model_validator(mode="after")
    def _needs_amount(self) -> MakesIn:
        if self.amount is None:
            raise ValueError("Type how much it makes.")
        return self


Nutrient = Annotated[
    Decimal | None, Field(ge=0, le=100_000, max_digits=12, decimal_places=3), ShortAmount
]


class NutritionIn(BaseModel):
    """Per serving. Empty (null) means unknown, and is never stored as 0; type 0 for zero."""

    kcal: Nutrient = None
    protein: Nutrient = None
    carbs: Nutrient = None
    fat: Nutrient = None
    fibre: Nutrient = None


MAX_METHOD_NAME = 60


def _ids_once(lines: list[RecipeLineIn]) -> None:
    ids = [line.id for line in lines if line.id is not None]
    if len(ids) != len(set(ids)):
        raise ValueError("The same line is in the recipe twice.")


def _step_lines_in_range(lines: list[RecipeLineIn], steps: list[RecipeStepIn]) -> None:
    for step in steps:
        for index in step.lines or []:
            if not 0 <= index < len(lines) or lines[index].kind != "ingredient":
                raise ValueError("A step can only use the recipe's own ingredient lines.")


class SecondMethodIn(BaseModel):
    """The recipe's second way of cooking it (M2): its own name, time, ingredient
    lines and steps. A recipe has at most two methods. The first is the recipe's own `lines`,
    `steps` and `time_minutes`."""

    name: Annotated[str, Field(min_length=1, max_length=MAX_METHOD_NAME)]
    time_minutes: Annotated[int, Field(ge=1, le=14_400)] | None = None
    lines: list[RecipeLineIn] = Field(default_factory=list, max_length=MAX_LINES)
    steps: list[RecipeStepIn] = Field(default_factory=list, max_length=MAX_STEPS)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        cleaned = clean_name(value)
        if not cleaned:
            raise ValueError("Type a name for this way of cooking it.")  # proposed, for cabledrawer
        return cleaned

    @model_validator(mode="after")
    def _check(self) -> SecondMethodIn:
        _ids_once(self.lines)
        _step_lines_in_range(self.lines, self.steps)
        return self


class RecipeIn(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=200)]
    description: Annotated[str, Field(max_length=200)] | None = None
    time_minutes: Annotated[int, Field(ge=1, le=14_400)] | None = None
    # A new recipe starts at 4; send null for a recipe with no servings (a batter, a powder).
    serves: Annotated[int, Field(ge=1, le=99)] | None = 4
    makes: MakesIn | None = None
    made_ahead: bool = False
    # Only when `made_ahead` makes a new ingredient: its name (default: the recipe's name).
    homemade_name: Annotated[str, Field(max_length=100)] | None = None
    tags: list[Annotated[str, Field(min_length=1, max_length=MAX_TAG_CHARS)]] = Field(
        default_factory=list, max_length=MAX_TAGS
    )
    nutrition: NutritionIn = Field(default_factory=NutritionIn)
    # The person looked at the figures (the editor opened from "Update nutrition") and kept
    # them: they count as set now, which clears "Nutrition possibly out of date".
    nutrition_checked: bool = False
    lines: list[RecipeLineIn] = Field(default_factory=list, max_length=MAX_LINES)
    steps: list[RecipeStepIn] = Field(default_factory=list, max_length=MAX_STEPS)
    # Two cooking methods (M2): `lines`, `steps` and `time_minutes` above are the first method.
    # `method_name` names it (needed once there is a second one); `second_method` is the other.
    # Left out: the second method stays as it is (an old client that knows nothing of methods
    # never loses it). null: remove it.
    method_name: Annotated[str, Field(max_length=MAX_METHOD_NAME)] | None = None
    second_method: SecondMethodIn | None = None
    source_note: Annotated[str, Field(max_length=500)] | None = None
    # The recipe's photo: the id from `POST /recipes/photos`, or the one it has already.
    # Left out: the photo stays as it is. null: no photo (the one it had is deleted on
    # Save). A new id: that photo replaces it. (cabledrawer 20 Oct: the editor's "Remove photo"
    # sends null; leaving the field out never removes it.)
    photo_id: StoredInt | None = Field(
        default=None,
        description=(
            "The id from `POST /recipes/photos`, or the photo’s own id. Left out: the photo"
            " stays as it is. null: no photo (the one it had is deleted on save). A new id:"
            " that photo replaces it. To remove the photo, send null: leaving the field out"
            " never removes it."
        ),
    )

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        cleaned = clean_name(value)
        if not cleaned:
            raise ValueError("Type a name.")
        return cleaned

    @field_validator("description", "source_note")
    @classmethod
    def _one_line(cls, value: str | None) -> str | None:
        return _tidy(value)

    @field_validator("homemade_name")
    @classmethod
    def _homemade(cls, value: str | None) -> str | None:
        return _tidy(value)

    @field_validator("tags")
    @classmethod
    def _tags(cls, values: list[str]) -> list[str]:
        seen: dict[str, str] = {}
        for value in values:
            cleaned = clean_name(value)
            if not cleaned:
                raise ValueError("A tag needs a word.")
            seen.setdefault(cleaned.casefold(), cleaned)
        return list(seen.values())

    @field_validator("method_name")
    @classmethod
    def _method_name(cls, value: str | None) -> str | None:
        return clean_name(value) or None if value is not None else None

    @model_validator(mode="after")
    def _ids_once(self) -> RecipeIn:
        _ids_once(self.lines)
        _step_lines_in_range(self.lines, self.steps)
        if self.second_method is not None:
            if not self.method_name:
                raise ValueError(
                    "Name the first way of cooking it too, so Cook mode can ask which."
                )  # proposed, for cabledrawer
            if self.method_name.casefold() == self.second_method.name.casefold():
                raise ValueError("The two ways of cooking it need different names.")
        return self


class RecipeUpdate(RecipeIn):
    """The whole recipe, as the editor saved it. `version` is the version it opened."""

    version: Annotated[StoredInt, Field(ge=1)]
    # "Save mine anyway": sent with the newer `version` from the 409 `recipe_changed`.
    overwrite: bool = False


# --- Output -----------------------------------------------------------------------------------


class SizeRef(BaseModel):
    id: int
    name: str
    plural: str


# 0.5.1, spec section 6 (25 Oct): the screens show the full name for a linked line.
class LineFoodRef(Ref):
    """The ingredient a line is linked to, with its other names, so a screen can tell that
    words like "thu" are only the start of one ("thuvaram paruppu") and show the ingredient's
    own name instead."""

    other_names: list[str]


class RecipeLineOut(BaseModel):
    id: int
    kind: Literal["ingredient", "heading"]
    words: str
    amount: float | None
    amount_text: str | None  # "1½"
    unit: str | None  # g, kg, ml, l, tsp, tbsp, cup, pinch; null: a count (or a size)
    size: SizeRef | None
    food: LineFoodRef | None
    recipe: Ref | None
    # ingredient · recipe · recipe_removed (the recipe was deleted; Undo puts the link back)
    # · none (not linked: pick an ingredient). Null for a heading.
    link: Literal["ingredient", "recipe", "recipe_removed", "none"] | None
    note: str | None
    optional: bool = False


class StepLineOut(BaseModel):
    """One ingredient line a step uses (0.7, for Cook mode's per-step ingredients)."""

    line_id: int
    line: int  # its position in the recipe's `lines`, counting from 0, as a save sends it
    kind: Literal["guessed", "by_hand"]


class RecipeStepOut(BaseModel):
    id: int
    kind: Literal["step", "heading"]
    text: str
    optional: bool = False
    wait: StepWaitOut | None = None  # M1: marinate, soak, ferment...
    timing: StepTimingOut | None = None  # B1: hands-on or waiting, minutes, equipment
    lines: list[StepLineOut] = Field(default_factory=list)


class MethodRef(BaseModel):
    """A cooking method, for the switch (M2): its name, its time and whether it was used last.
    The first method's lines and steps are the recipe's own; the second's are `second_method`."""

    id: int
    name: str  # empty for the only method of a recipe
    time_minutes: int | None
    wait: StepWaitOut | None = None
    used_last: bool = False


class SecondMethodOut(MethodRef):
    lines: list[RecipeLineOut]
    steps: list[RecipeStepOut]


class MakesOut(BaseModel):
    amount: float
    amount_text: str
    unit: str


class NutritionOut(BaseModel):
    kcal: float | None
    protein: float | None
    carbs: float | None
    fat: float | None
    fibre: float | None
    # R3: some ingredient line changed after these figures were typed or read from a page, so
    # they may be out of date ("Nutrition possibly out of date"). False when none are set.
    possibly_out_of_date: bool = False


class PhotoOut(BaseModel):
    """`url` is the large copy (longest side at most 1600 px), `list_url` the small one
    for the recipe list (shortest side 156 px). Both are JPEGs. A new photo always gets a
    new id, so a URL always shows the same picture."""

    id: int
    width: int
    height: int
    url: str
    list_width: int
    list_height: int
    list_url: str


class SourceOut(BaseModel):
    """Where an imported recipe came from. The server never
    visits `url` again: opening it is the person's own click."""

    url: str
    site: str  # the address without "www.": "bbcgoodfood.com"
    imported_at: datetime
    author: str | None


class RecipeOut(BaseModel):
    id: int
    name: str
    description: str | None
    # The time in whole minutes: the active time when `wait` is not null (a recipe made before
    # waits keeps its single time and has no wait).
    time_minutes: int | None
    # All the steps' waits added up (M1), null when no step waits.
    wait: StepWaitOut | None = None
    serves: int | None
    makes: MakesOut | None
    made_ahead: bool
    homemade: Ref | None  # its own pantry ingredient, once saved with Made ahead on
    tags: list[str]
    nutrition: NutritionOut
    # The first method's lines and steps (the recipe as it always was).
    lines: list[RecipeLineOut]
    steps: list[RecipeStepOut]
    # The ways of cooking it (M2): one, or two. A recipe with two has `second_method` too.
    methods: list[MethodRef] = Field(default_factory=list)
    second_method: SecondMethodOut | None = None
    source_note: str | None
    source: SourceOut | None  # null for a recipe that wasn't imported from a link
    photo: PhotoOut | None
    used_by: list[Ref]  # recipes that use this one as an ingredient
    version: int
    created_at: datetime
    updated_at: datetime
    updated_by: Who


class RecipeBrief(BaseModel):
    id: int
    name: str
    description: str | None
    time_minutes: int | None
    wait: StepWaitOut | None = None  # all the steps' waits added up (M1)
    serves: int | None
    makes: MakesOut | None
    made_ahead: bool
    tags: list[str]
    ingredient_count: int
    # How many of its ingredient lines are Optional (R3): adding it to the plan asks about them.
    optional_count: int = 0
    # How many ways of cooking it (M2): 1, or 2.
    method_count: int = 1
    photo: PhotoOut | None
    version: int
    updated_at: datetime


class RecipeList(BaseModel):
    total: int
    recipes: list[RecipeBrief]
    next: str | None


class TagOut(BaseModel):
    id: int
    name: str
    recipes: int  # how many recipes use it


class TagList(BaseModel):
    tags: list[TagOut]


class Blocked(BaseModel):
    id: int
    name: str
    reason: str  # "Sambar powder can not use Sambar, because Sambar uses Sambar powder."
    chain: list[str]  # ["Sambar", "Sambar powder"]


class BlockedList(BaseModel):
    recipes: list[Blocked]
