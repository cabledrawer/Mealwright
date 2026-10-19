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


# Characters that show nothing (or change how the text around them is drawn) are refused in
# every name and in recipe text (security audit, 19 Oct): they can hide one name behind
# another, or flip the order text is shown in. Refused: control characters, the direction
# marks, overrides and isolates (U+202A to 202E, U+2066 to 2069) and other invisible
# format characters. Allowed: the two joiners, which Tamil, Malayalam and other Indian
# scripts and emoji sequences need; the emoji tag characters (U+E0020 to E007F), which flag
# emoji such as Scotland's are spelled with; and variation selectors (they are not format
# characters).
_JOINERS = {"\u200c", "\u200d"}
_EMOJI_TAGS = range(0xE0020, 0xE0080)


def has_hidden(value: str, newlines: bool = False) -> bool:
    """Does the text hold a tab, a line break (unless `newlines`), another control
    character, or an invisible formatting character?"""
    for char in value:
        if char in _JOINERS or ord(char) in _EMOJI_TAGS or (newlines and char == "\n"):
            continue
        if unicodedata.category(char) in ("Cc", "Cf", "Cs", "Zl", "Zp"):
            return True
    return False


HIDDEN_ONE_LINE = "That has a tab, a line break or a hidden character in it. Take it out."
HIDDEN_TEXT = "That has a hidden character in it. Take it out."


def one_line(value: str) -> str:
    """The shared check for a one-line field (a name, a tag, a note): refused if it has a
    tab, a line break or any hidden character. Raises ValueError, which the API turns into
    a 422 with this sentence. The text is returned unchanged."""
    if has_hidden(value):
        raise ValueError(HIDDEN_ONE_LINE)
    return value


def text_block(value: str) -> str:
    """The shared check for text that may run over several lines (a method step): line
    breaks are fine (a Windows line break becomes a plain one), other hidden characters
    are refused."""
    value = value.replace("\r\n", "\n")
    if has_hidden(value, newlines=True):
        raise ValueError(HIDDEN_TEXT)
    return value


def clean_name(value: str) -> str:
    """`one_line`, then `clean`: for every name someone types."""
    return clean(one_line(value))


def size_name(value: str) -> str:
    """A name for a way a food is sold ("packet", "tub", "dozen"): tidied, and with letters
    in it, so "1" can't become "1 1" in the pantry."""
    value = clean_name(value)
    if not any(c.isalpha() for c in value):
        raise ValueError("Give the size a name, like tub or packet.")
    return value
