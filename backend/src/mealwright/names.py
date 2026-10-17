"""Matching food names: search, "Maybe the same" and the bundled conversion table.

No fuzzy-matching library (spec section 6, "Decided for 0.2"): just simple, predictable
rules that work offline.
"""

import re
import unicodedata

_BRACKETS = re.compile(r"\([^)]*\)|\[[^\]]*\]")
_NOT_WORD = re.compile(r"[^a-z0-9%]+")


def fold(text: str) -> str:
    """Lower case without accents, for search: "Jalapeño" → "jalapeno"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c)).strip()


def search_match(name: str, others: list[str], needle: str) -> tuple[int, str | None] | None:
    """Does a typed search find this food? `needle` is already folded. Returns how well
    (0 name starts with it, 1 name contains it, 2 an other name starts with it, 3 an other
    name contains it; lower is better) and which other name matched, or None for no match.
    Used by Ingredients and by Pantry, so both find the same things."""
    folded = fold(name)
    if folded.startswith(needle):
        return 0, None
    if needle in folded:
        return 1, None
    best: tuple[int, str | None] | None = None
    for other in others:
        other_folded = fold(other)
        if needle in other_folded:
            rank = 2 if other_folded.startswith(needle) else 3
            if best is None or rank < best[0]:
                best = (rank, other)
    return best


def singular(word: str) -> str:
    if len(word) <= 3 or word.endswith("ss"):
        return word
    if word.endswith("ies"):
        return word[:-3] + "y"
    if word.endswith(("oes", "ches", "shes", "sses", "xes")):
        return word[:-2]
    if word.endswith("s"):
        return word[:-1]
    return word


def normalise(name: str) -> str:
    """The key two names must share to count as the same: lower case, no accents, nothing
    in brackets, no punctuation, and each word made singular.

    "Drumsticks (moringa)" → "drumstick"; "Tomatoes" → "tomato"; "Self-raising flour" →
    "self raising flour"; "Confectioners' sugar" → "confectioner sugar".
    """
    text = _BRACKETS.sub(" ", fold(name)).replace("'", "").replace("\u2019", "")
    words = _NOT_WORD.sub(" ", text).split()
    return " ".join(singular(word) for word in words)


def clean(name: str) -> str:
    """Tidy a name someone typed: trim and collapse spaces."""
    return " ".join(name.split())


def size_name(value: str) -> str:
    """A name for a way a food is sold ("packet", "tub", "dozen"): tidied, and with letters
    in it, so "1" can't become "1 1" in the pantry."""
    value = clean(value)
    if not any(c.isalpha() for c in value):
        raise ValueError("Give the size a name, like tub or packet.")
    return value
