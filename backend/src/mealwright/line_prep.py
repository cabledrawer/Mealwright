# ruff: noqa: RUF001, RUF002, RUF003  (look-alike dashes and signs are the point of this file)
"""Tidying the text of an import before it is read (0.7.0, "importer consistency").

Pure text in, plain values out: no database, no network. The same thing written two ways must
give the same result (cabledrawer 28 Oct), so the small rules for page clutter live here, in one
place, each with its finding number:

- `strip_footnotes` (F17): "(Note 5)", "((Note 1))", "(, full fat)".
- `is_page_junk` (F33): a recipe card's buttons that came along with pasted text.
- `is_ingredient_heading` (F34) and `is_step_heading` (F23): section names in both lists.
- `serving_heading` (F19): a heading whose lines are for serving, so they are optional.
- `clean_recipe_name` (F9 and the name patterns): "Victoria sandwich recipe", "How to Make …".
- `tidy_tags`: capitals, and a small table of tags that mean the same.
- `tidy_ingredient_name`: capitals of a new ingredient's name.
- `kitchen_round`: converted amounts as a cook would write them.
"""

import re
from decimal import ROUND_HALF_UP, Decimal

# --- Footnote marks (F17) ---------------------------------------------------------------------

_NOTE_MARK = re.compile(r"\(\s*(?:see\s+)?notes?\s*\d+[^()]*\)", re.IGNORECASE)
_EMPTY_BRACKET = re.compile(r"\(\s*[,;]?\s*\)")
_NOTE_NUMBER = re.compile(r"\[\s*\d{1,3}\s*\]")


def strip_footnotes(text: str) -> str:
    """The text without the site's footnote marks: "(Note 5)", "((Note 1))", "[3]", and the
    brackets they leave empty or starting with a comma. "( OR 1 tbsp oil (Note 3))" becomes
    "(OR 1 tbsp oil)". A text with none is returned as it was."""
    if "(" not in text and "[" not in text:
        return text
    found = text
    for _ in range(4):  # nested marks come out one layer at a time
        before = found
        found = _NOTE_MARK.sub(" ", found)
        found = _EMPTY_BRACKET.sub(" ", found)
        if found == before:
            break
    found = _NOTE_NUMBER.sub(" ", found)
    found = re.sub(r"\(\s*[,;]\s*", "(", found)
    found = re.sub(r"\(\s+", "(", found)
    found = re.sub(r"\s+\)", ")", found)
    return " ".join(found.split()) if found != text else text


# --- Page junk (F33) --------------------------------------------------------------------------

_JUNK = re.compile(
    r"(?:cook\s+mode|prevent\s+your\s+(?:screen|phone|device)\s+from\s+(?:going|turning)\s+dark"
    r"|print(?:\s+recipe)?|jump\s+to\s+(?:recipe|video)|save\s+recipe|pin\s+recipe|rate\s+this"
    r"\s+recipe|add\s+to\s+(?:my\s+)?(?:favou?rites|shopping\s+list|meal\s+plan)|us\s+customary"
    r"|metric|imperial|ingredients?|instructions?|directions?|method|servings?)",
    re.IGNORECASE,
)
# The recipe card's scale buttons: "½x1×2×", "1x 2x 3x".
_SCALE_BUTTONS = re.compile(r"(?:[\d½¼¾⅓⅔]*\s*[x×]\s*){2,}", re.IGNORECASE)


def is_page_junk(text: str) -> bool:
    """A line that is the page's own button or label, not part of the recipe: "Cook Mode",
    "Prevent your screen from going dark", the "½x1×2×" scale buttons. Whole lines only, so a
    real line that merely contains one of these words stays."""
    line = " ".join(text.split()).strip(" \t:•-")
    if not line:
        return False
    if _SCALE_BUTTONS.fullmatch(line):
        return True
    return bool(_JUNK.fullmatch(line))


# --- Section headings (F34, F23, F19) ---------------------------------------------------------

_FOR_THE = re.compile(
    r"(?:for|to)\s+(?:the\s+)?(?!taste\b)[^\W\d_][\w'’&-]*(?:\s+[^\W\d_][\w'’&-]*){0,4}\s*:?",
    re.IGNORECASE,
)
_SERVING = re.compile(
    r"(?:for\s+(?:the\s+)?|to\s+)?(?:serving|serve|garnish(?:ing)?|topping|toppings|decorating)"
    r"|(?:optional|extras)",
    re.IGNORECASE,
)
_ABBREVIATED = re.compile(
    r"(?:abbreviated|short|quick|summary|the\s+short\s+version)(?:\s+(?:recipe|version|method))?",
    re.IGNORECASE,
)
_FULL = re.compile(r"(?:full|detailed|complete)(?:\s+(?:recipe|version|method))?", re.IGNORECASE)


def is_ingredient_heading(text: str) -> bool:
    """ "For the Lamb", "For the Garnish:", "To assemble": a section name among the ingredients.
    A line with a digit, a comma or an amount is never one, and "to taste" is not a heading."""
    line = " ".join(text.split()).strip()
    if not line or len(line) > 60 or any(c.isdigit() for c in line) or "," in line:
        return False
    return bool(_FOR_THE.fullmatch(line))


def serving_heading(heading: str) -> bool:
    """Is this heading about serving ("For serving", "To garnish", "Optional")? The lines under
    it are optional (F19)."""
    line = " ".join(heading.split()).strip(" :")
    return bool(_SERVING.fullmatch(line))


def is_step_heading(text: str) -> bool:
    """A step that is only a section title: SHOUTED WORDS ("FULL RECIPE") or a short phrase
    ending in a colon with no full stop. It takes no step number (F23)."""
    line = " ".join(text.split()).strip()
    if not line or len(line) > 50 or line.endswith((".", "!", "?")):
        return False
    letters = [c for c in line if c.isalpha()]
    if len(letters) >= 4 and all(c.isupper() for c in letters) and len(line.split()) <= 6:
        return True
    return line.endswith(":") and len(line.split()) <= 6


def is_abbreviated_heading(text: str) -> bool:
    return bool(_ABBREVIATED.fullmatch(" ".join(text.split()).strip(" :")))


def is_full_heading(text: str) -> bool:
    return bool(_FULL.fullmatch(" ".join(text.split()).strip(" :")))


# --- Recipe names (F9 and the patterns) -------------------------------------------------------

_HOW_TO = re.compile(r"^\s*how\s+to\s+(?:make|cook|bake|prepare|do)\s+", re.IGNORECASE)
_RECIPE_BRACKET = re.compile(r"\s*[\(\[][^()\[\]]*\brecipe\b[^()\[\]]*[\)\]]\s*", re.IGNORECASE)
_RECIPE_TAIL = re.compile(r"\s*(?:[-–—|:]\s*[^-–—|:]*)?\brecipe\s*!*\s*$", re.IGNORECASE)
_BRACKET_PUFF = re.compile(
    r"\s*[\(\[]\s*(?:authentic|easy|best|simple|quick|classic|traditional|foolproof)\b[^()\[\]]*"
    r"[\)\]]\s*$",
    re.IGNORECASE,
)


def clean_recipe_name(name: str) -> str:
    """A recipe's name without the site's search words: "Classic Victoria sandwich recipe" is
    "Classic Victoria sandwich"; "How to Make Butter Chicken (Authentic Indian Recipe)" is "Butter
    Chicken". The user can still change it on Check. A name that would be empty stays as it was."""
    found = " ".join(name.split())
    cleaned = _HOW_TO.sub("", found)
    cleaned = _RECIPE_BRACKET.sub(" ", cleaned)
    cleaned = _BRACKET_PUFF.sub("", cleaned)
    cleaned = _RECIPE_TAIL.sub("", cleaned)
    cleaned = " ".join(cleaned.split()).strip(" -–—|:")
    if not any(c.isalpha() for c in cleaned):
        return found
    return cleaned[:1].upper() + cleaned[1:]


# --- Tags -------------------------------------------------------------------------------------

# Words that mean the same: every word on the right becomes the one on the left. Proposed, for
# cabledrawer: short on purpose.
TAG_SYNONYMS: dict[str, tuple[str, ...]] = {
    "Main": ("mains", "main course", "main dish", "main meal", "entree", "entrée", "dinner mains"),
    "Starter": ("starters", "appetiser", "appetizer", "appetisers", "appetizers"),
    "Side": ("sides", "side dish", "side dishes"),
    "Dessert": ("desserts", "pudding", "puddings", "sweet"),
    "Snack": ("snacks", "nibbles"),
    "Breakfast": ("breakfasts", "brunch"),
    "Vegetarian": ("veggie", "veg", "vegetarian friendly"),
    "Vegan": ("plant based", "plant-based"),
    "Gluten free": ("gluten-free", "gf"),
    "Dairy free": ("dairy-free", "df"),
    "Soup": ("soups",),
    "Salad": ("salads",),
    "Baking": ("bakes", "bake"),
    "Quick": ("quick and easy", "fast", "speedy"),
}
_SYNONYM_OF = {word: tag for tag, words in TAG_SYNONYMS.items() for word in (tag.lower(), *words)}
MAX_TAG = 40


def tidy_tags(tags: list[str]) -> list[str]:
    """Tags with a capital to start, synonyms joined ("mains" and "Main course" are "Main"),
    and each shown once, in the order first seen."""
    found: list[str] = []
    seen: set[str] = set()
    for raw in tags:
        text = " ".join(raw.replace("_", " ").split()).strip(" ,;.#")
        if not text:
            continue
        key = text.lower()
        tag = _SYNONYM_OF.get(key) or (text if text.isupper() and len(text) <= 4 else None)
        if tag is None:
            tag = text[:1].upper() + text[1:].lower() if text.islower() or text.isupper() else text
            tag = tag[:1].upper() + tag[1:]
        tag = tag[:MAX_TAG].rstrip()
        if tag.lower() not in seen:
            seen.add(tag.lower())
            found.append(tag)
    return found


# --- Ingredient names -------------------------------------------------------------------------


def tidy_ingredient_name(name: str) -> str:
    """A new ingredient's name with the capitals tidied: a capital to start and the rest as it
    reads in a sentence ("KASHMIRI CHILLIES" and "Kashmiri Chillies" are "Kashmiri chillies").
    A name with a mix of cases that isn't every-word-capitalised is left alone ("iPhone case",
    "Worcestershire sauce")."""
    text = " ".join(name.split())
    words = text.split()
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return text
    shouting = all(c.isupper() for c in letters) and len(letters) > 3
    title_case = (
        len(words) >= 2
        and all(w[:1].isupper() for w in words if w[:1].isalpha())
        and not all(c.isupper() for c in letters)
        and all(w[1:].islower() or not w[1:].isalpha() for w in words if w[:1].isalpha())
    )
    if shouting or title_case:
        text = text.lower()
    return text[:1].upper() + text[1:]


# --- Amounts ----------------------------------------------------------------------------------


def kitchen_round(value: Decimal) -> Decimal:
    """A converted amount in g or ml as a cook would write it: 396.9 is 397 and 340.2 is 340;
    two decimals only below 10 (5.67 g), never 1.136 kg's last digits."""
    if value >= 10:
        return value.quantize(Decimal(1), rounding=ROUND_HALF_UP)
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP).normalize()
