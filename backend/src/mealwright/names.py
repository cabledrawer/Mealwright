"""Matching food names: search, "Maybe the same" and the bundled conversion table.

No fuzzy-matching library (spec section 6, "Decided for 0.2"): just simple, predictable
rules that work offline.
"""

import re
import unicodedata

_BRACKETS = re.compile(r"\([^()]*\)|\[[^\[\]]*\]")  # no nested "(": a run of them is linear
_NOT_WORD = re.compile(r"[^a-z0-9%]+")


def fold(text: str) -> str:
    """Lower case without accents, for search: "Jalapeño" → "jalapeno"."""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(c for c in decomposed if not unicodedata.combining(c)).strip()


def search_match(name: str, others: list[str], needle: str) -> tuple[int, str | None] | None:
    """Does a typed search find this food? `needle` is already folded. Returns how well
    (-1 the name or another name is exactly it, 0 name starts with it, 1 name contains it, 2 an
    other name starts with it, 3 an other name contains it; lower is better) and which other name
    matched, or None for no match. Used by Ingredients and by Pantry, so both find the same
    things; only Ingredients sorts by the rank. An exact match comes first so that the screen's
    "+ New ingredient" offer (F97), which looks at the first page only, never misses it."""
    folded = fold(name)
    if folded == needle:
        return -1, None
    for other in others:
        if fold(other) == needle:
            return -1, other
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
# scripts and emoji sequences need; the emoji tag characters, but only inside a flag emoji
# (a black flag, tag letters, then the cancel tag: how Scotland's and Wales's flags are
# spelled); and variation selectors (they are not format characters).
_JOINERS = {"\u200c", "\u200d"}
_FLAG = 0x1F3F4  # the black flag, which a flag emoji such as Scotland's starts with
# A flag's tag is a region code: 2 to 6 lowercase letters or digits (gbsct, gbeng, gbwls).
_TAG_LETTERS = (*range(0xE0030, 0xE003A), *range(0xE0061, 0xE007B))
_TAG_LENGTH = range(2, 7)
_CANCEL_TAG = 0xE007F


def _flag_end(value: str, start: int) -> int:
    """If a flag emoji sequence starts at `start` (the black flag, 2 to 6 tag letters or
    digits, then the cancel tag), where it ends; else `start`. Tag characters are otherwise refused:
    on their own they spell invisible ASCII text."""
    if ord(value[start]) != _FLAG:
        return start
    end = start + 1
    while end < len(value) and ord(value[end]) in _TAG_LETTERS:
        end += 1
    if end - start - 1 in _TAG_LENGTH and end < len(value) and ord(value[end]) == _CANCEL_TAG:
        return end + 1
    return start


def has_hidden(value: str, newlines: bool = False) -> bool:
    """Does the text hold a tab, a line break (unless `newlines`), another control
    character, or an invisible formatting character?"""
    index = 0
    while index < len(value):
        char = value[index]
        end = _flag_end(value, index)
        if end > index:
            index = end
            continue
        index += 1
        if char in _JOINERS or (newlines and char == "\n"):
            continue
        if unicodedata.category(char) in ("Cc", "Cf", "Cs", "Zl", "Zp"):
            return True
    return False


def without_hidden(value: str) -> str:
    """The text with hidden characters taken out, for pasted text, where refusing would only
    annoy. The same characters `has_hidden` finds go (the joiners and flag emoji stay).
    Windows and old Mac line breaks, and the Unicode line and paragraph separators, become
    plain line breaks; a tab becomes a space; other control characters are dropped."""
    kept: list[str] = []
    index = 0
    while index < len(value):
        char = value[index]
        end = _flag_end(value, index)
        if end > index:
            kept.append(value[index:end])
            index = end
            continue
        index += 1
        if char == "\r":
            if value[index : index + 1] == "\n":
                index += 1
            kept.append("\n")
        elif char in "\n\u2028\u2029\x0b\x0c\x85":
            kept.append("\n")
        elif char == "\t":
            kept.append(" ")
        elif char in _JOINERS or unicodedata.category(char) not in ("Cc", "Cf", "Cs", "Zl", "Zp"):
            kept.append(char)
    return "".join(kept)


_SKIN_TONES = range(0x1F3FB, 0x1F400)  # the five skin tone modifiers
_INDICATORS = range(0x1F1E6, 0x1F200)  # regional indicators: two make a country flag


def _is_indicator(char: str) -> bool:
    return ord(char) in _INDICATORS


def cut_text(value: str, limit: int) -> str:
    """The text cut to at most `limit` characters without splitting what belongs together:
    a flag emoji (a country flag's two letters, or a black flag's tag characters, which are
    refused if left on their own), a letter and the marks on it, a skin tone, or the parts of
    a joined sequence. Backs off to before the broken piece. If that would leave nothing (a
    text of only marks), it is cut at the limit instead, so a text is never cut to empty."""
    if len(value) <= limit:
        return value
    cut = limit
    while cut > 0:
        # Inside a flag? Back off to where it starts.
        flag = value.rfind(chr(_FLAG), 0, cut)
        if flag >= 0 and flag < cut < _flag_end(value, flag):
            cut = flag
            continue
        # Between the two letters of a country flag? (An odd number of indicators before the
        # cut, and one after it.)
        if _is_indicator(value[cut]) and _is_indicator(value[cut - 1]):
            start = cut
            while start > 0 and _is_indicator(value[start - 1]):
                start -= 1
            if (cut - start) % 2 == 1:
                cut -= 1
                continue
        # The next character belongs to the one before it (a mark, a joiner, a variation
        # selector, a skin tone).
        after = value[cut]
        if (
            after in _JOINERS
            or ord(after) in _SKIN_TONES
            or unicodedata.category(after) in ("Mn", "Mc", "Me")
        ):
            cut -= 1
            continue
        if value[cut - 1] in _JOINERS:
            cut -= 1
            continue
        break
    if cut == 0 and unicodedata.category(value[0]) in ("Mn", "Mc", "Me"):
        return value[:limit]
    return value[:cut]


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
