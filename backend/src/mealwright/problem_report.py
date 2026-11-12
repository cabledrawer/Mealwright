"""Settings → About → Report a problem (spec section 7, "Bug reports", cabledrawer 17 Oct).

The server builds a short report and hands it to the web app; it never sends it anywhere and
makes no connection for it. The person reads all of it, changes or removes any line, and sends
it themselves (Open on GitHub in their own browser, Copy, or Download).

What it holds: the app version, the browser and device type (from the request's User-Agent,
reduced to the browser's name, its major version and the kind of device), and the recent errors
from the log file (`mealwright.logs`): cabledrawer 12 Nov, the last `ERRORS_KEPT` error lines
written in the last `ERRORS_WITHIN`, each reduced to its time, the part of the app that wrote it,
its message and the kind of error (never the traceback).

Personal details are removed here, on the server, before the web app sees the lines
(`Scrubber`): every word of every username, person's and household's name kept on this
server (the log is the whole server's, so every household's), every recipe, ingredient, shop,
place, list and tag name as a whole phrase, the server's own address, host name and port, any
IP address, link, host name, e-mail address, file path, password, token or key, and anything
a log line quotes.
"""

import copy
import os
import platform
import re
import threading
import time
import unicodedata
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import Pool

from mealwright import __version__, models
from mealwright.former_names import REPLACEMENTS, TITLE_KINDS
from mealwright.logs import FILE_NAME
from mealwright.updates import RELEASES_PAGE

# The project's new-issue page, from the same placeholder repository as the releases page
# (mealwright.updates; both become the real one at 1.0). Opened by the person's own click.
NEW_ISSUE_PAGE = RELEASES_PAGE.removesuffix("/releases") + "/issues/new"

# cabledrawer 12 Nov: the last 20 error lines from the last 24 hours.
ERRORS_KEPT = 20
ERRORS_WITHIN = timedelta(hours=24)
# Only the end of each log file is read: errors are the newest lines, and a big file stays cheap.
TAIL_BYTES = 2 * 1024 * 1024
# A longer message is cut here, with "…".
LINE_LIMIT = 300
# Only this much of a message is scrubbed (and so read at all): scrubbing a huge line is slow.
MESSAGE_READ = 2000
# How long a built Scrubber is used again before it is built afresh, in seconds.
SCRUBBER_KEPT = 60.0

# 2026-10-17T18:21:50Z ERROR mealwright.jobs: Couldn't thin the history …
_RECORD = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ) ([A-Z]+) ([\w.\-]+): ?(.*)$")
_ERROR_LEVELS = {"ERROR", "CRITICAL"}
# The last line of a traceback: "sqlite3.OperationalError: database is locked".
_EXCEPTION = re.compile(r"^([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)(?::|$)")
#   File "/app/src/mealwright/recipes.py", line 12, in save
_FRAME = re.compile(r'^\s+File "')


# --- The browser and device ---------------------------------------------------------------

# Checked in this order: Edge, Opera and Samsung Internet also say "Chrome", and Chrome also
# says "Safari".
_BROWSERS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Edge", re.compile(r"\bEdg(?:e|A|iOS)?/(\d+)")),
    ("Opera", re.compile(r"\b(?:OPR|OPT)/(\d+)")),
    ("Samsung Internet", re.compile(r"\bSamsungBrowser/(\d+)")),
    ("Firefox", re.compile(r"\b(?:Firefox|FxiOS)/(\d+)")),
    ("Chrome", re.compile(r"\b(?:Chrome|CriOS)/(\d+)")),
    ("Safari", re.compile(r"\bVersion/(\d+)[\d.]* (?:Mobile/\S+ )?Safari/")),
)

_DEVICES: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("iPhone", re.compile(r"\biPhone\b")),
    ("iPad", re.compile(r"\biPad\b")),
    ("Android phone", re.compile(r"\bAndroid\b.*\bMobile\b")),
    ("Android tablet", re.compile(r"\bAndroid\b")),
    ("Chromebook", re.compile(r"\bCrOS\b")),
    ("Windows", re.compile(r"\bWindows\b")),
    ("Mac", re.compile(r"\bMacintosh\b|\bMac OS X\b")),
    ("Linux", re.compile(r"\bLinux\b|\bX11\b")),
)


def browser_words(user_agent: str | None) -> str:
    """ "Safari 18 · iPhone": the browser's name and major version and the kind of device,
    never the full User-Agent (which names exact versions and sometimes the phone model)."""
    agent = (user_agent or "")[:1000]
    browser = "Unknown browser"
    for name, pattern in _BROWSERS:
        found = pattern.search(agent)
        if found:
            browser = f"{name} {int(found.group(1))}"
            break
    device = next((name for name, pattern in _DEVICES if pattern.search(agent)), None)
    return f"{browser} · {device}" if device else browser


# --- Recent errors from the log -----------------------------------------------------------


@dataclass(frozen=True)
class LogError:
    at: datetime
    logger: str
    message: str
    # The kind of error from a traceback ("OperationalError"), if the line had one.
    kind: str | None


def _tail(path: Path) -> str:
    with path.open("rb") as file:
        size = file.seek(0, os.SEEK_END)
        file.seek(max(0, size - TAIL_BYTES))
        data = file.read()
    text = data.decode("utf-8", errors="replace")
    if size > TAIL_BYTES:
        text = text.partition("\n")[2]  # the first line read is most likely cut
    return text


def _records(text: str) -> Iterable[tuple[str, str, str, str, list[str]]]:
    current: tuple[str, str, str, str, list[str]] | None = None
    for line in text.splitlines():
        found = _RECORD.match(line)
        if found:
            if current is not None:
                yield current
            when, level, logger, message = found.groups()
            current = (when, level, logger, message, [])
        elif current is not None:
            current[4].append(line)
    if current is not None:
        yield current


def _kind(following: list[str]) -> str | None:
    """The kind of error a traceback ended with: the last part of its name only.

    It is the first unindented line after the traceback's last frame (an error's message can
    run on over more lines after it), and only if that line starts with a class's name
    ("sqlite3.OperationalError: …"); otherwise just "error". It is scrubbed like the message.
    """
    if not any(line.startswith("Traceback") for line in following):
        return None
    frames = [index for index, line in enumerate(following) if _FRAME.match(line)]
    if not frames:
        return "error"
    for line in following[frames[-1] + 1 :]:
        if line and not line[0].isspace():
            found = _EXCEPTION.match(line)
            return found.group(1).rsplit(".", 1)[-1] if found else "error"
    return "error"


def recent_errors(
    folder: Path, now: datetime | None = None, installed: datetime | None = None
) -> list[LogError]:
    """The last ERRORS_KEPT error lines of the last ERRORS_WITHIN, oldest first. Lines from
    before `installed` (when this household was set up, so after "Delete everything" the new
    set-up) are left out: they belong to the install that was deleted."""
    now = now or datetime.now(UTC)
    since = now - ERRORS_WITHIN
    if installed is not None:
        if installed.tzinfo is None:
            installed = installed.replace(tzinfo=UTC)
        # Log times are whole seconds: round the set-up UP, so a line stamped in the same second
        # as the set-up (written before it, truncated) is left out.
        whole = installed.replace(microsecond=0)
        if installed.microsecond:
            whole += timedelta(seconds=1)
        since = max(since, whole)
    found: list[LogError] = []
    try:
        paths = [path for path in folder.glob(f"{FILE_NAME}*") if path.is_file()]
    except OSError:
        return []
    for path in paths:
        try:
            # (a second of slack: `since` may be rounded up to the next whole second)
            if datetime.fromtimestamp(path.stat().st_mtime, UTC) < since - timedelta(seconds=1):
                continue  # last written before the window: nothing in it is recent
            text = _tail(path)
        except OSError:
            continue
        for when, level, logger, message, following in _records(text):
            if level not in _ERROR_LEVELS:
                continue
            at = datetime.strptime(when, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
            if since <= at <= now + timedelta(minutes=5):
                found.append(LogError(at, logger, message, _kind(following)))
    found.sort(key=lambda error: error.at)
    return found[-ERRORS_KEPT:]


# --- Removing personal details --------------------------------------------------------------
#
# Every pattern here is linear: no nested or unbounded repeats that can backtrack, so even a
# huge line costs little (and only MESSAGE_READ characters of it are read).

_URL = re.compile(
    r"(?<![a-z0-9+.\-])[a-z][a-z0-9+.\-]{0,30}://[^\s<>\"']*|(?<![\w.\-])www\.[^\s<>\"']+",
    re.IGNORECASE,
)
# "password=…", "password: …", "mw_session=…", "apikey=…": the name stays, the value goes.
_SECRET_VALUE = re.compile(
    r"(?<![a-z])((?:api[_\-]?)?(?:password|passwd|pwd|token|secret|cookie|session|key|auth)"
    r"[a-z_\-]{0,30})(\s{0,3}[=:]\s{0,3}(?:(?:bearer|basic)\s{1,3})?)(?:\"[^\"\n]{0,300}\"|'[^'\n]{0,300}'|[^\s,;&)\]]+)",
    re.IGNORECASE,
)
_BEARER = re.compile(r"(?<![a-z])(bearer|basic)\s{1,3}[\w\-.~+/]+=*", re.IGNORECASE)
_JWT = re.compile(r"(?<![\w\-])eyJ[\w\-]{5,}\.[\w\-]{5,}\.[\w\-]*")
# Also "user@host" with no dot.
_EMAIL = re.compile(
    r"[\w.+\-]{1,64}@(?:\[[0-9a-f:.]{1,45}\]|[\w\-]{1,63}(?:\.[\w\-]{1,63}){0,10})",
    re.IGNORECASE,
)
# A host name without a scheme ("recipes.example.org/pie", "caddy.home.arpa"), with any port
# and path after it. Kept unless it is a known site or ends in one of _TLDS: module names
# ("sqlalchemy.exc", "mealwright.jobs") look the same.
_HOST = re.compile(
    r"(?<![\w.\-@/\\])((?:[a-z0-9](?:[a-z0-9\-]{0,61}[a-z0-9])?\.){1,10}([a-z][a-z0-9\-]{0,62}))"
    r"(?![\w\-]|\.[a-z0-9])((?::\d{1,5})?(?:/[^\s<>\"']*)?)",
    re.IGNORECASE,
)
_TLDS = frozenset(
    (
        *("com", "net", "org", "edu", "gov", "mil", "int", "io", "co", "uk", "de", "fr", "nl"),
        *("be", "ch", "at", "it", "es", "se", "no", "dk", "fi", "pl", "cz", "ie", "eu", "us"),
        *("ca", "au", "nz", "in", "jp", "cn", "br", "ru", "info", "biz", "dev", "me", "tv"),
        *("xyz", "online", "site", "cloud", "email", "local", "localdomain", "lan", "home"),
        *("arpa", "internal", "intranet", "corp", "example", "test", "invalid", "localhost"),
        "onion",
    )
)
# Any absolute path: Unix (a part may hold up to four spaces when another "/" follows it, so
# "/data/photos/Ayla Roe/x.jpg" goes whole), Windows and network shares.
_PART = r"[^\s/\\'\"<>:;,()\[\]|?*]+"
_PATH = re.compile(
    rf"(?<![\w/.~\]\[])~?/(?:{_PART}(?: {_PART}){{0,4}}/)*{_PART}"
    rf"|(?<![\w\\])[a-z]:\\(?:{_PART}(?: {_PART}){{0,4}}\\)*(?:{_PART})?"
    rf"|(?<![\w\\])\\\\{_PART}(?:\\{_PART}){{0,30}}",
    re.IGNORECASE,
)
_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?(?!\w|\.\d)")
_IPV6 = re.compile(
    r"(?<![\w:])\[?[0-9a-f]{0,4}(?::[0-9a-f]{0,4}){2,7}\]?(?::\d{1,5})?(?![\w:])", re.I
)
# "port=8443", "port 8443": any port, not just this server's.
_ANY_PORT = re.compile(r"(?<![a-z])(port)(\s{0,3}[=:]\s{0,3}|\s{1,3})\d{1,5}(?!\d)", re.I)
# A run of 20 or more characters that could be a key, a hash or a token (see _long_run).
_LONG_RUN = re.compile(r"(?<![\w+/=\-])[A-Za-z0-9+/_\-]{20,}={0,2}")
_HEX = frozenset("0123456789abcdefABCDEF-")
# Quoted words: quote marks that aren't inside a word ("Couldn't" and "Mabel's" aren't quotes, nor
# is the "'s" or "'" after a removed name, "[name]'s"; any other quote after "]" still is),
# and an apostrophe inside a quote ("'Auntie Shanti's biryani'") doesn't end it. A quote that is
# never closed runs to the end of the line.
_Q = MESSAGE_READ
_QUOTED = re.compile(
    rf"(?<!\w)(?:(?!(?<=\])'s?(?!\w))'(?:[^'\n]|'(?=\w)){{0,{_Q}}}(?:'|(?=\n|\Z))"
    rf"|\u2018(?:[^\u2019\n]|\u2019(?=\w)){{0,{_Q}}}(?:\u2019|(?=\n|\Z))"
    rf"|\"[^\"\n]{{0,{_Q}}}(?:\"|(?=\n|\Z))"
    rf"|\u201c[^\u201d\n]{{0,{_Q}}}(?:\u201d|(?=\n|\Z))"
    rf"|\u201e[^\u201c\u201d\n]{{0,{_Q}}}(?:[\u201c\u201d]|(?=\n|\Z))"
    rf"|\u00ab[^\u00bb\n]{{0,{_Q}}}(?:\u00bb|(?=\n|\Z))"
    rf"|\u203a[^\u2039\n]{{0,{_Q}}}(?:\u2039|(?=\n|\Z))"
    rf"|\u2039[^\u203a\n]{{0,{_Q}}}(?:\u203a|(?=\n|\Z))"
    rf"|`[^`\n]{{0,{_Q}}}(?:`|(?=\n|\Z)))(?!\w)"
)


def _mark_ranges() -> str:
    """Every combining mark (Unicode category M: accents, and the vowel signs and viramas of
    Tamil, Hindi, Bengali and other scripts), as ranges for a character class."""
    ranges: list[str] = []
    start = previous = -2
    for code in (*range(0x20000), *range(0xE0100, 0xE01F0)):
        if not unicodedata.category(chr(code)).startswith("M"):
            continue
        if code != previous + 1:
            if start >= 0:
                ranges.append(f"\\U{start:08x}-\\U{previous:08x}")
            start = code
        previous = code
    ranges.append(f"\\U{start:08x}-\\U{previous:08x}")
    return "".join(ranges)


# A word: a run of letters with their combining marks and the zero-width (non-)joiners, so
# "டெஸ்ஸா" and "टेस्सा" are one word each. Anything else is a boundary, so "tess_backup.db",
# "user_tess" and "tess2" each hold the word "tess".
_WORD_CHAR = rf"(?:[^\W\d_]|[{_mark_ranges()}\u200c\u200d])"
_WORD = re.compile(rf"{_WORD_CHAR}+")
# "Granny Mabel's lasagne": a capitalised word before 's in a recipe's or ingredient's name is
# most likely a person's, and is removed on its own like one (cabledrawer 12 Nov).
_POSSESSIVE = re.compile(r"(?<![^\W\d_])([^\W\d_]{2,})['\u2019]s(?![^\W\d_])")
# Words of household names that are never removed on their own ("The Marshes").
_JOINING = frozenset({"the", "and", "of"})
# Words before 's in a recipe's name that are never a person's ("It's a Wrap", "Today's
# Special", "Let's Eat").
_NOT_PEOPLE = frozenset(
    (
        *("it", "let", "that", "what", "here", "there", "where", "who", "how", "he", "she"),
        *("today", "tonight", "tomorrow", "yesterday", "one", "this", "everyone"),
        *("everybody", "someone", "somebody", "nobody", "anyone", "anybody"),
    )
)
# Between two words of one phrase in a log line: a few characters that aren't letters or
# digits ("Diwali 2025 party", "Week 2026-11-09 shop": the digits don't count).
_GAP = 4
# The scrubber's own words: these are never looked up as names.
_OWN_WORDS = re.compile(
    r"\[(?:name|recipe|ingredient|removed|site|link|server|port|address|e-mail|file|secret"
    r"|text)\]"
)


def _joins(gap: str) -> bool:
    """Whether the text between two words can be inside one phrase: at most _GAP characters
    that aren't digits, and no line end or bracket."""
    if len(gap) > _GAP and len(gap) - sum(char.isdecimal() for char in gap) > _GAP:
        return False
    return not any(char in "\n[]" for char in gap)


def _ipv6(found: re.Match[str]) -> str:
    text = found.group(0)
    # A time ("12:41:07") has colons too: an address has "::", a letter a to f, or 4+ groups.
    if "::" in text or re.search(r"[a-f]", text, re.IGNORECASE) or text.count(":") >= 3:
        return "[address]"
    return text


def _long_run(found: re.Match[str]) -> str:
    text = found.group(0)
    core = text.rstrip("=")
    hex_digits = sum(char != "-" for char in core)
    if set(core) <= _HEX and hex_digits >= 20 and any(char.isdigit() for char in core):
        return "[secret]"
    if (
        any(char.isdigit() for char in core)
        and any(char.isupper() for char in core)
        and any(char.islower() for char in core)
    ):
        return "[secret]"
    return text


def _key(word: str) -> str:
    """How a word is looked up: any capitals, and an accent written either way ("Jos\u00e9",
    "JOSE", "Jose" with a combining accent all match), "\u00df" as "ss", and the Turkish
    dotted and dotless i as "i"."""
    if word.isascii():
        return word.lower()
    folded = unicodedata.normalize("NFD", word.casefold())
    return (
        "".join(char for char in folded if not unicodedata.combining(char))
        .replace("\u0131", "i")
        .replace("\u200c", "")
        .replace("\u200d", "")
    )


def _variants(key: str) -> tuple[str, ...]:
    """The word, and without a plural or possessive "s" or "es" ("Tesss", "paruppus")."""
    if len(key) > 4 and key.endswith("es"):
        return (key, key[:-1], key[:-2])
    if len(key) > 3 and key.endswith("s"):
        return (key, key[:-1])
    return (key,)


def _keys(text: str) -> tuple[str, ...]:
    return tuple(_key(word) for word in _WORD.findall(unicodedata.normalize("NFC", text)))


def _phrases(pattern_words: Iterable[str]) -> re.Pattern[str] | None:
    """One pattern for a few host names (this server's, its own network's)."""
    words = {
        word.strip()
        for word in pattern_words
        if word and len(word.strip()) >= 2 and re.search(r"[^\W_]", word)
    }
    if not words:
        return None
    alternatives = "|".join(re.escape(word) for word in sorted(words, key=len, reverse=True))
    return re.compile(rf"(?<![\w.\-])(?:{alternatives})(?![\w\-]|\.\w)", re.IGNORECASE)


# People: every word of these is removed on its own, wherever it is (cabledrawer 12 Nov).
_PEOPLE_COLUMNS: tuple[Any, ...] = (
    models.Login.username,
    models.Login.name,
    # The household's people (0.9 A1), with or without a login, and whoever added them.
    models.Member.name,
    models.Member.created_by_name,
    models.Household.name,
    models.Recipe.source_author,
    # People who have left or been renamed are still named here.
    models.OwnNetworkEntry.added_by_name,
    models.FoodConversion.answered_by_name,
    models.ShoppingList.created_by_name,
    models.ListItem.ticked_by_name,
    models.ListItem.added_by_name,
    models.ListItem.deleted_by_name,
    models.DoubleTick.answered_by_name,
    models.Recipe.updated_by_name,
    models.RecipePhoto.added_by_name,
    models.ImportDraft.started_by_name,
    models.CookedRecord.cooked_by_name,
    # Who did each change, tick and queued action, by the name they had then (review r1).
    models.Change.login_name,
    models.ListTick.login_name,
    models.SyncAction.login_name,
)

# Everything else is removed only as a whole phrase (its last word may have an "s"), so the
# everyday words in it ("hour", "removed") stay in other lines. What each is replaced with
# (cabledrawer 12 Nov); a phrase that is two kinds at once gets the first kind's word.
_PHRASE_COLUMNS: tuple[tuple[str, tuple[Any, ...]], ...] = (
    (
        "[recipe]",
        (
            models.Recipe.name,
            models.Recipe.description,
            models.RecipeLine.words,
            models.RecipeLine.note,
            models.RecipeMethod.name,
            models.BatchCook.recipe_name,
            models.ImportDraft.name,
            models.MealItem.name,
            models.Tag.name,
        ),
    ),
    (
        "[ingredient]",
        (
            models.Food.name,
            models.FoodName.name,
        ),
    ),
    (
        "[removed]",
        (
            models.Shop.name,
            models.Place.name,
            models.ShoppingList.name,
            models.MealSlot.name,
        ),
    ),
)
# Names whose possessive words are people's ("Granny Mabel's lasagne").
_TITLE_COLUMNS = {
    models.Recipe.name,
    models.BatchCook.recipe_name,
    models.ImportDraft.name,
    models.MealItem.name,
    models.Food.name,
    models.FoodName.name,
}
# A phrase longer than this many words can't fit in MESSAGE_READ characters.
_LONGEST_PHRASE = MESSAGE_READ // 2


@dataclass(frozen=True)
class ServerAddress:
    """How this server is reached and named, as far as the request and the machine say."""

    hosts: tuple[str, ...]
    ports: tuple[int, ...]


# What the undo data of a change keeps (review r2 and r3). It is plain JSON, and a name that
# has since changed, merged or gone can sit anywhere in it, under any key a future change adds.
# So it is deny-by-default: EVERY string in it is a name to remove, unless its key is listed
# here as one that never holds a name, with the reason. A new kind with a new name key is then
# removed without anyone remembering to list it; a new key that holds a code or a plain word
# (so that removing it would blank that word everywhere) must be listed, or the report loses
# that word (tests/test_problem_report.py::test_every_kind_of_change_is_covered).
UNDO_NOT_NAMES: dict[str, str] = {
    "op": "the kind of step (add_item, move_meal, list_name…)",
    "kind": "a kind of change, place, row or step (fridge, step, tub…)",
    "undoes_kind": "a kind of change",
    "result": "done or nothing",
    "action": "an action's ID",
    "id": "an ID",
    "status": "a state word (planned, cooked…)",
    "state": "a state word (downloaded, none…)",
    "label": "a state word (matched, staple…)",
    "pattern": "a batch cook pattern word (pick, dinners)",
    "equipment": "hob, oven or pressure",
    "hands": "hands or waiting",
    "colour": "a colour word",
    "unit": "a unit (cup, tsp, g)",
    "counted_as": "weight, volume or count",
    "aisle": "an aisle word (dairy, spices…)",
    "date_kind": "use_by or best_before",
    "household": "the pint word (uk, us)",
    "reading": "a reading word (uk, us)",
    "source_kind": "link or text",
    "from": "a state or a date",
    "to": "a state or a date",
    "amount_text": "an amount (a number or fraction)",
    "count_word": "a size word (bunch, tin): everyday words, not names",
    "count_word_plural": "a size word (bunches, tins)",
    "plural": "a size word (packets, boxes)",
    "text": "a recipe's own method text, not a name",
    "title": "a method step's own text, not a name",
    "note": "a recipe line's own note (sliced, to taste), not a name",
    "heading": "a recipe's own section heading (Tips), not a name",
    "description": "a recipe's own prose, not a name",
    "written": "a recipe line as written, not a name",
    "source_text": "text a person pasted, kept as a draft, not a name",
    "url": "a link or a path: removed as a link anyway",
    "list_url": "a path",
}
# Keys that end like these hold an ID, a time or a day.
_NOT_NAME_ENDINGS = ("_id", "_ids", "_at", "_day", "_on", "_from", "_to", "_url", "_made_at")
# A string that is only an ID, a time, a day, a number or a hash is never a name.
_CODE = re.compile(
    r"^(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"  # a UUID
    r"|[0-9a-f]{32,}"  # a hash
    r"|\d{4}-\d\d-\d\d(?:[T ][\d:.+Z-]*)?"  # a day or a time
    r"|[\d.,/:+\-\s]+"  # numbers
    r"|/.*)$",  # a path
    re.IGNORECASE,
)
# A longer string is a sentence or a text, not a name; it would never match a log line anyway.
_LONGEST_UNDO_NAME = 20  # words


def _undo_label(path: tuple[str, ...], key: str, op: object) -> str | None:
    """The word that replaces a name found in undo data, from where it sits; None means a
    person's or a one-word household's (every word of it is removed)."""
    if key.endswith("_by_name") or key == "login_name" or "person" in path:
        return None
    if op == "slot_name":
        return "[meal]"
    if key.endswith(":name") or "names" in path or "fields" in path or "foods" in path:
        return "[ingredient]"
    if key in ("recipe_name", "words", "matched_by", "learn_name", "tags", "author"):
        return "[recipe]" if key != "author" else None
    for step in reversed(path):
        if step in ("shop", "place"):
            return f"[{step}]"
        if step in ("source", "target", "tag"):
            return "[recipe]"
    return "[removed]"


def undo_names(data: Any, _path: tuple[str, ...] = ()) -> Iterable[tuple[str, str | None]]:
    """The names in one change's undo data: (the name, the word that replaces it), where None
    means a person's: every word of it is removed. Everything that is a string and is not on
    the list of keys that never hold a name is a name. A household's old and new names (a
    "name" holding {"old", "new"}) come out as ("...", "[household]")."""
    if isinstance(data, list):
        for item in data:
            yield from undo_names(item, _path)
        return
    if not isinstance(data, dict):
        return
    op = data.get("op")
    for key, value in data.items():
        if key == "sizes":
            continue  # a size's words (tin, bunch) are not names
        field = key.rsplit(":", 1)[-1]  # an ingredient's snapshot: "12:aisle"
        if field in UNDO_NOT_NAMES or field.endswith(_NOT_NAME_ENDINGS):
            continue
        if isinstance(value, str | list):
            # A string, or a list of them ("Old", "New" as ["Old", "New"], or [None, "New"]).
            for part in value if isinstance(value, list) else [value]:
                if isinstance(part, str):
                    if not _CODE.match(part) and len(part.split()) <= _LONGEST_UNDO_NAME:
                        yield part, _undo_label(_path, key, op)
                elif isinstance(part, dict | list):
                    yield from undo_names(part, (*_path, key))
        elif key == "name" and isinstance(value, dict) and set(value) <= {"old", "new"}:
            for part in value.values():
                if isinstance(part, str):
                    yield part, "[household]"
        else:
            yield from undo_names(value, (*_path, key))


class Scrubber:
    """Removes personal details from one log message."""

    def __init__(self, db: Session, server: ServerAddress, data_dir: Path) -> None:
        # One word: a person's, or a one-word name of another kind. Looked up word by word.
        self._words: dict[str, str] = {}
        # Phrases of two words or more, by their first two words: (the rest, replacement),
        # longest first.
        self._phrases: dict[tuple[str, str], list[tuple[tuple[str, ...], str]]] = {}
        for column in _PEOPLE_COLUMNS:
            for value in db.scalars(select(column).distinct()):
                self._add_person(value)
        for replacement, columns in _PHRASE_COLUMNS:
            for column in columns:
                for value in db.scalars(select(column)):
                    if not value:
                        continue
                    if column in _TITLE_COLUMNS:
                        for found in _POSSESSIVE.finditer(unicodedata.normalize("NFC", value)):
                            word = found.group(1)
                            if word[0].isupper() and _key(word) not in _NOT_PEOPLE:
                                self._add_person(word)
                    self._add_phrase(_keys(value), replacement)
        # The names a person, household, shop, place, list, tag, meal or ingredient had before it
        # was renamed, merged or removed, kept in the undo data of the changes that did it
        # (review r1, r2, r3). After the columns, so a name that is also in a column keeps that
        # column's word.
        for data in db.scalars(select(models.Change.undo_data)):
            for name, label in undo_names(data):
                keys = _keys(name)
                if label is None or (label == "[household]" and len(keys) == 1):
                    self._add_person(name)  # a person's every word; a one-word household
                else:
                    self._add_phrase(keys, label)
        # Names kept by the session hook (mealwright.former_names) whenever a row's name changed
        # or the row was deleted, whatever path did it, for as long as log lines live. Every
        # household's, like the columns above: a line is server-wide. The second net, for what
        # happened before the hook existed (fix4).
        for former_kind, former_name in db.execute(
            select(models.FormerName.kind, models.FormerName.name)
        ):
            self._add_former(former_kind, former_name)
        for options in self._phrases.values():
            options.sort(key=lambda option: len(option[0]), reverse=True)
        self._sites: set[str] = set()
        for site in db.scalars(select(models.ImportDraft.site)):
            if site:
                self._sites.add(site.casefold().removeprefix("www."))
        for link in db.scalars(select(models.Recipe.source_url)):
            host = urlsplit(link or "").hostname
            if host:
                self._sites.add(host.casefold().removeprefix("www."))
        self._own = [entry for entry in db.scalars(select(models.OwnNetworkEntry.value)) if entry]
        self._address(server, data_dir)

    def at(self, server: ServerAddress, data_dir: Path) -> Scrubber:
        """This Scrubber for one request: the same names, with this request's host and port."""
        scrubber = copy.copy(self)
        scrubber._address(server, data_dir)
        return scrubber

    def _address(self, server: ServerAddress, data_dir: Path) -> None:
        self._server = _phrases([*server.hosts, *self._own])
        ports = sorted({str(port) for port in server.ports})
        self._ports = (
            re.compile(rf"(?:(?<=:)|(?<=\bport ))(?:{'|'.join(ports)})(?!\d)", re.IGNORECASE)
            if ports
            else None
        )
        # The data folder, also when it is given as a relative path.
        folders = sorted({str(data_dir).rstrip("/") or "/data", "/data"}, key=len, reverse=True)
        roots = "|".join(re.escape(folder) for folder in folders)
        self._files = re.compile(rf"(?<![\w/])(?:{roots})(?:/[^\s'\":,;)\]]*)?(?!\w)")

    def _add_former(self, kind: str, name: str) -> None:
        replacement = REPLACEMENTS.get(kind, "[removed]")
        keys = _keys(name)
        if kind in TITLE_KINDS:
            for found in _POSSESSIVE.finditer(unicodedata.normalize("NFC", name)):
                word = found.group(1)
                if word[0].isupper() and _key(word) not in _NOT_PEOPLE:
                    self._add_person(word)
        if replacement is None or (kind == "household" and len(keys) == 1):
            self._add_person(name)  # a person's every word; a one-word household
        else:
            self._add_phrase(keys, replacement)

    def _add_person(self, name: str | None) -> None:
        for key in _keys(name or ""):
            if len(key) >= 2 and key not in _JOINING:
                self._words.setdefault(key, "[name]")

    def _add_phrase(self, keys: tuple[str, ...], replacement: str) -> None:
        if not keys or len(keys) > _LONGEST_PHRASE or len("".join(keys)) < 2:
            return
        if len(keys) == 1:
            self._words.setdefault(keys[0], replacement)
            return
        options = self._phrases.setdefault((keys[0], keys[1]), [])
        option = (keys[2:], replacement)
        if option not in options:
            options.append(option)

    def _word(self, key: str) -> str | None:
        for variant in _variants(key):
            found = self._words.get(variant)
            if found is not None:
                return found
        return None

    def _host(self, found: re.Match[str]) -> str:
        host = found.group(1).casefold().removeprefix("www.")
        labels = host.split(".")
        if any(".".join(labels[start:]) in self._sites for start in range(len(labels) - 1)):
            return "[site]"
        if found.group(2).casefold() in _TLDS:
            return "[link]"
        return found.group(0)

    def _names(self, text: str) -> str:
        words = [
            (found.start(), found.end(), found.group(0), _key(found.group(0)))
            for found in _WORD.finditer(text)
        ]
        # Whether a word and the next one can be two words of one phrase.
        joined = [_joins(text[words[n][1] : words[n + 1][0]]) for n in range(len(words) - 1)]
        # Where the scrubber's own words are ("[link]", "[e-mail]").
        own = {at for found in _OWN_WORDS.finditer(text) for at in range(*found.span())}
        out: list[str] = []
        done = 0
        n = 0
        while n < len(words):
            start, _, word, key = words[n]
            if start in own:
                n += 1
                continue
            last, replacement = self._phrase_at(words, joined, n)
            if replacement is None:
                replacement = self._word(key) or self._joined_words(word)
            if replacement is not None:
                out.append(text[done:start])
                out.append(replacement)
                done = words[last][1]
            n = last + 1
        out.append(text[done:])
        return "".join(out)

    def _phrase_at(
        self, words: list[tuple[int, int, str, str]], joined: list[bool], n: int
    ) -> tuple[int, str | None]:
        """The longest phrase starting at word n: its last word and its replacement."""
        if n + 1 >= len(words) or not joined[n]:
            return n, None
        first, second = words[n][3], words[n + 1][3]
        for variant in _variants(second):
            for rest, replacement in self._phrases.get((first, variant), ()):
                if variant != second and rest:
                    continue  # only a phrase's last word may have an "s"
                last = n + 1 + len(rest)
                if last >= len(words) or not all(joined[n + 1 : last]):
                    continue
                if all(words[n + 2 + k][3] == part for k, part in enumerate(rest[:-1])) and (
                    not rest or rest[-1] in _variants(words[last][3])
                ):
                    return last, replacement
        return n, None

    def _joined_words(self, word: str) -> str | None:
        """ "TessMarsh": names run together, each with a capital."""
        cuts = [0] + [
            at for at in range(1, len(word)) if word[at - 1].islower() and word[at].isupper()
        ]
        if len(cuts) == 1:
            return None
        parts = [word[a:b] for a, b in zip(cuts, [*cuts[1:], len(word)], strict=True)]
        replaced = [self._word(_key(part)) for part in parts]
        if not any(replaced):
            return None
        return "".join(r or part for r, part in zip(replaced, parts, strict=True))

    def __call__(self, text: str) -> str:
        text = _URL.sub("[link]", text)
        text = _JWT.sub("[secret]", text)
        # Key=value first, so "bearer token=x" keeps no part of x; "Authorization: Basic x" is
        # caught there too ("Basic " is part of the separator), and a bare "Bearer x" after.
        text = _SECRET_VALUE.sub(r"\1\2[secret]", text)
        text = _BEARER.sub(r"\1 [secret]", text)
        text = _EMAIL.sub("[e-mail]", text)
        text = _PATH.sub("[file]", text)
        text = self._files.sub("[file]", text)
        if self._server is not None:
            text = self._server.sub("[server]", text)
        text = _HOST.sub(self._host, text)
        text = _IPV4.sub("[address]", text)
        text = _IPV6.sub(_ipv6, text)
        if self._ports is not None:
            text = self._ports.sub("[port]", text)
        text = _ANY_PORT.sub(r"\1\2[port]", text)
        text = _LONG_RUN.sub(_long_run, text)
        text = self._names(text)
        text = _QUOTED.sub("[text]", text)
        return text


def server_address(request_host: str | None, request_port: int | None, port: int) -> ServerAddress:
    hosts = [host for host in (request_host, platform.node()) if host]
    ports = [p for p in (request_port, port) if p]
    return ServerAddress(hosts=tuple(hosts), ports=tuple(ports))


def _now() -> float:
    return time.monotonic()


# The tables that hold a name the Scrubber removes. A write to any of them, in any household,
# means the kept Scrubber may miss a name, so the next report builds it afresh.
_NAME_TABLES = frozenset(
    column.class_.__table__.name
    for column in (
        *_PEOPLE_COLUMNS,
        *(column for _, columns in _PHRASE_COLUMNS for column in columns),
        models.ImportDraft.site,
        models.Recipe.source_url,
        models.OwnNetworkEntry.value,
        models.FormerName.name,
    )
)
# Read by the next "Report a problem" before it uses a kept Scrubber.
_writes = 0
# Statements that never change a row.
_READ_ONLY = frozenset({"SELECT", "PRAGMA", "SAVEPOINT", "RELEASE", "BEGIN", "COMMIT", "ROLLBACK"})


def _changes_names(statement: str, context: Any) -> bool:
    """Whether a statement may add, change or remove a name the Scrubber removes. When it
    can't tell (written as plain SQL), any statement that isn't a read counts."""
    compiled = getattr(context, "compiled", None)
    if compiled is None or getattr(context, "is_text", False):
        words = statement.split(None, 1)
        return not words or words[0].upper() not in _READ_ONLY
    if context.isddl:
        return True
    if not (context.isinsert or context.isupdate or context.isdelete):
        return False
    table = getattr(getattr(compiled, "statement", None), "table", None)
    name = getattr(table, "name", None)
    return name is None or name in _NAME_TABLES


_NAME_WRITTEN = "mealwright_name_written"
_NAME_COMMITTED = "mealwright_name_committed"


@event.listens_for(Engine, "after_cursor_execute")
def _note_write(
    connection: object,
    cursor: object,
    statement: str,
    parameters: object,
    context: Any,
    executemany: bool,
) -> None:
    global _writes
    if _changes_names(statement, context):
        with _kept_lock:
            _writes += 1
        connection.info[_NAME_WRITTEN] = True  # type: ignore[attr-defined]


def _gone(connection: Any) -> bool:
    """A dropped or closed connection: its `info` can't be read (review r4, 6)."""
    return bool(connection.invalidated or connection.closed)


def _count_committed(info: dict[str, Any]) -> None:
    global _writes
    if info.pop(_NAME_COMMITTED, False):
        with _kept_lock:
            _writes += 1


@event.listens_for(Engine, "commit")
def _note_commit(connection: Any) -> None:
    """Count a name write again when it is committed: a report built between the write and
    its commit couldn't see the new row but saw the count, so it must be built again. The
    "commit" event fires before the database commits (review r4, 3), so the write is counted
    once more after it is done: when the connection goes back to the pool or starts again."""
    global _writes
    if _gone(connection):
        return
    if connection.info.pop(_NAME_WRITTEN, False):
        with _kept_lock:
            _writes += 1
        connection.info[_NAME_COMMITTED] = True


@event.listens_for(Engine, "begin")
def _note_begin(connection: Any) -> None:
    if not _gone(connection):
        _count_committed(connection.info)


@event.listens_for(Pool, "checkin")
def _note_checkin(dbapi_connection: object, record: Any) -> None:
    if record is not None:
        _count_committed(record.info)


@event.listens_for(Engine, "rollback")
def _note_rollback(connection: Any) -> None:
    if not _gone(connection):
        connection.info.pop(_NAME_WRITTEN, None)


# The built Scrubber of each database, kept for at most SCRUBBER_KEPT seconds and only while no
# name may have changed: (when built, the write count then, the Scrubber). One for the whole
# install: it already covers every household, and the request's host and port are added to it
# for each report (Scrubber.at).
_kept: dict[str, tuple[float, int, Scrubber]] = {}
_kept_lock = threading.Lock()


def scrubber_for(db: Session, server: ServerAddress, data_dir: Path) -> Scrubber:
    """A Scrubber for this request. The names in it are built again when any household's names
    may have changed since (a write to a table that holds one) and at least every
    SCRUBBER_KEPT seconds; otherwise the kept one is used."""
    key = str(getattr(db.get_bind(), "url", ""))
    now = _now()
    with _kept_lock:
        kept = _kept.get(key)
        if kept is not None and now - kept[0] < SCRUBBER_KEPT and kept[1] == _writes:
            return kept[2].at(server, data_dir)
    # Read before building: a write while it is built makes the next report build again.
    writes = _writes
    scrubber = Scrubber(db, server, data_dir)
    with _kept_lock:
        for old in [k for k, (at, _, _) in _kept.items() if now - at >= SCRUBBER_KEPT]:
            del _kept[old]
        _kept[key] = (now, writes, scrubber)
    return scrubber


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _read(message: str) -> str:
    """The start of a message, written one way (NFC), cut back to its last space so it never
    ends in part of a word, name, address or key."""
    message = unicodedata.normalize("NFC", message)
    if len(message) <= MESSAGE_READ:
        return message
    start = message[: MESSAGE_READ + 1]
    cut = max(start.rfind(space) for space in " \t\n")
    return start[:cut] if cut >= 0 else ""


def error_line(error: LogError, scrub: Scrubber) -> str:
    """ "12 Nov 12:41 UTC mealwright.jobs: Couldn't thin the history (OperationalError)"."""
    message = scrub(_read(error.message))
    if len(message) > LINE_LIMIT:
        message = message[: LINE_LIMIT - 1] + "…"
    kind = f" ({scrub(_read(error.kind))})" if error.kind else ""
    when = f"{error.at.day} {_MONTHS[error.at.month - 1]} {error.at:%H:%M} UTC"
    return f"{when} {error.logger}: {message}{kind}"


def version_line() -> str:
    return f"Mealwright {__version__}"
