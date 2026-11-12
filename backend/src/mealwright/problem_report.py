"""Settings → About → Report a problem (spec section 7, "Bug reports", cabledrawer 17 Oct).

The server builds a short report and hands it to the web app; it never sends it anywhere and
makes no connection for it. The person reads all of it, changes or removes any line, and sends
it themselves (Open on GitHub in their own browser, Copy, or Download).

What it holds: the app version, the browser and device type (from the request's User-Agent,
reduced to the browser's name, its major version and the kind of device), and the recent errors
from the log file (`mealwright.logs`): proposed, for cabledrawer, the last `ERRORS_KEPT` error lines
written in the last `ERRORS_WITHIN`, each reduced to its time, the part of the app that wrote it,
its message and the kind of error (never the traceback).

Personal details are removed here, on the server, before the web app sees the lines
(`Scrubber`): every username, person and household name, recipe, ingredient, shop, place,
list and tag name kept on this server (the log is the whole server's, so every household's),
the server's own address, host name and port, any IP address, link or e-mail address, files
under the data folder, and anything a log line quotes.
"""

import os
import platform
import re
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from mealwright import __version__, models
from mealwright.logs import FILE_NAME
from mealwright.updates import RELEASES_PAGE

# The project's new-issue page, from the same placeholder repository as the releases page
# (mealwright.updates; both become the real one at 1.0). Opened by the person's own click.
NEW_ISSUE_PAGE = RELEASES_PAGE.removesuffix("/releases") + "/issues/new"

# Proposed, for cabledrawer: the last 20 error lines from the last 24 hours.
ERRORS_KEPT = 20
ERRORS_WITHIN = timedelta(hours=24)
# Only the end of each log file is read: errors are the newest lines, and a big file stays cheap.
TAIL_BYTES = 2 * 1024 * 1024
# A longer message is cut here, with "…".
LINE_LIMIT = 300

# 2026-10-17T18:21:50Z ERROR mealwright.jobs: Couldn't thin the history …
_RECORD = re.compile(r"^(\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ) ([A-Z]+) ([\w.\-]+): ?(.*)$")
_ERROR_LEVELS = {"ERROR", "CRITICAL"}
# The last line of a traceback: "sqlite3.OperationalError: database is locked".
_EXCEPTION = re.compile(r"^([A-Za-z_][\w.]*)(?::|$)")


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
    """The kind of error a traceback ended with: the last part of its name only."""
    if not any(line.startswith("Traceback") for line in following):
        return None
    for line in reversed(following):
        if line and not line[0].isspace():
            found = _EXCEPTION.match(line)
            if found and not line.startswith("Traceback"):
                return found.group(1).rsplit(".", 1)[-1]
    return None


def recent_errors(folder: Path, now: datetime | None = None) -> list[LogError]:
    """The last ERRORS_KEPT error lines of the last ERRORS_WITHIN, oldest first."""
    now = now or datetime.now(UTC)
    since = now - ERRORS_WITHIN
    found: list[LogError] = []
    try:
        paths = [path for path in folder.glob(f"{FILE_NAME}*") if path.is_file()]
    except OSError:
        return []
    for path in paths:
        try:
            if datetime.fromtimestamp(path.stat().st_mtime, UTC) < since:
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

_URL = re.compile(r"\b[a-z][a-z0-9+.\-]*://[^\s<>\"']+|\bwww\.[^\s<>\"']+", re.IGNORECASE)
_EMAIL = re.compile(r"[\w.+\-]+@[\w\-]+(?:\.[\w\-]+)+")
_IPV4 = re.compile(r"(?<![\w.])(?:\d{1,3}\.){3}\d{1,3}(?::\d{1,5})?(?![\w.])")
_IPV6 = re.compile(
    r"(?<![\w:])\[?[0-9a-f]{0,4}(?::[0-9a-f]{0,4}){2,7}\]?(?::\d{1,5})?(?![\w:])", re.I
)
# Quoted words: quote marks that aren't inside a word ("Couldn't" and "Mabel's" aren't quotes).
_QUOTED = re.compile(
    r"(?<!\w)(?:'[^'\n]*'|\"[^\"\n]*\"|\u2018[^\u2019\n]*\u2019|\u201c[^\u201d\n]*\u201d)(?!\w)"
)


def _ipv6(found: re.Match[str]) -> str:
    text = found.group(0)
    # A time ("12:41:07") has colons too: an address has "::" or a letter a to f.
    if "::" in text or re.search(r"[a-f]", text, re.IGNORECASE):
        return "[address]"
    return text


def _phrases(pattern_words: Iterable[str]) -> re.Pattern[str] | None:
    words = {
        word.strip()
        for word in pattern_words
        if word and len(word.strip()) >= 2 and re.search(r"[^\W\d_]", word)
    }
    if not words:
        return None
    alternatives = "|".join(re.escape(word) for word in sorted(words, key=len, reverse=True))
    return re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)


# Short everyday words that are never removed on their own (they are inside a whole name).
_EVERYDAY = frozenset(
    (
        "about",
        "after",
        "again",
        "also",
        "baked",
        "best",
        "big",
        "black",
        "blue",
        "brown",
        "cold",
        "dark",
        "days",
        "does",
        "done",
        "each",
        "every",
        "fast",
        "fine",
        "fresh",
        "from",
        "full",
        "good",
        "green",
        "half",
        "have",
        "hers",
        "home",
        "into",
        "just",
        "kind",
        "large",
        "last",
        "left",
        "like",
        "little",
        "long",
        "made",
        "make",
        "many",
        "mine",
        "more",
        "most",
        "much",
        "next",
        "nice",
        "none",
        "only",
        "other",
        "over",
        "plain",
        "quick",
        "real",
        "really",
        "right",
        "same",
        "side",
        "slow",
        "small",
        "some",
        "such",
        "than",
        "that",
        "their",
        "them",
        "then",
        "there",
        "these",
        "they",
        "this",
        "those",
        "very",
        "well",
        "were",
        "what",
        "when",
        "where",
        "which",
        "white",
        "with",
        "your",
    )
)


def _name_parts(name: str) -> list[str]:
    """A name, and each word of it of four letters or more that isn't an everyday word: a
    log line may name "paruppu" without "Thuvaram" (proposed, for cabledrawer)."""
    name = " ".join(name.split())
    if not name:
        return []
    parts = [name]
    for word in re.findall(r"[^\W\d_][\w’'-]*", name):
        bare = word.strip("’'-")
        if len(bare) >= 4 and bare.casefold() not in _EVERYDAY:
            parts.append(bare)
    return parts


# What each kind of name is replaced with (proposed, for cabledrawer).
_NAME_COLUMNS: tuple[tuple[str, tuple[Any, ...]], ...] = (
    (
        "[name]",
        (
            models.Login.username,
            models.Login.name,
            models.Household.name,
        ),
    ),
    (
        "[recipe]",
        (
            models.Recipe.name,
            models.Recipe.description,
            models.Recipe.source_author,
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


@dataclass(frozen=True)
class ServerAddress:
    """How this server is reached and named, as far as the request and the machine say."""

    hosts: tuple[str, ...]
    ports: tuple[int, ...]


class Scrubber:
    """Removes personal details from one log message."""

    def __init__(self, db: Session, server: ServerAddress, data_dir: Path) -> None:
        # One pattern for every name, longest first, so a person's name inside a longer
        # ingredient name ("Neighbour's sourdough") can't leave the rest of it behind. A name
        # that is two kinds at once gets the first kind's word.
        self._name_kinds: dict[str, str] = {}
        for replacement, columns in _NAME_COLUMNS:
            for column in columns:
                for value in db.scalars(select(column)):
                    for phrase in _name_parts(value or ""):
                        self._name_kinds.setdefault(phrase.casefold(), replacement)
        self._names = _phrases(self._name_kinds)
        sites: list[str] = []
        sites.extend(site for site in db.scalars(select(models.ImportDraft.site)) if site)
        for link in db.scalars(select(models.Recipe.source_url)):
            host = urlsplit(link or "").hostname
            if host:
                sites.append(host)
        own = [entry for entry in db.scalars(select(models.OwnNetworkEntry.value)) if entry]
        self._sites = _phrases(sites)
        self._server = _phrases([*server.hosts, *own])
        ports = sorted({str(port) for port in server.ports})
        self._ports = (
            re.compile(rf"(?:(?<=:)|(?<=\bport ))(?:{'|'.join(ports)})(?!\d)", re.IGNORECASE)
            if ports
            else None
        )
        folders = sorted({str(data_dir).rstrip("/") or "/data", "/data"}, key=len, reverse=True)
        roots = "|".join(re.escape(folder) for folder in folders)
        self._files = re.compile(rf"(?<![\w/])(?:{roots})(?:/[^\s'\":,;)\]]*)?(?!\w)")

    def __call__(self, text: str) -> str:
        text = _URL.sub("[link]", text)
        text = _EMAIL.sub("[e-mail]", text)
        text = self._files.sub("[file]", text)
        if self._server is not None:
            text = self._server.sub("[server]", text)
        if self._sites is not None:
            text = self._sites.sub("[site]", text)
        text = _IPV4.sub("[address]", text)
        text = _IPV6.sub(_ipv6, text)
        if self._ports is not None:
            text = self._ports.sub("[port]", text)
        if self._names is not None:
            text = self._names.sub(
                lambda found: self._name_kinds.get(found.group(0).casefold(), "[removed]"), text
            )
        text = _QUOTED.sub("[text]", text)
        return text


def server_address(request_host: str | None, request_port: int | None, port: int) -> ServerAddress:
    hosts = [host for host in (request_host, platform.node()) if host]
    ports = [p for p in (request_port, port) if p]
    return ServerAddress(hosts=tuple(hosts), ports=tuple(ports))


_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def error_line(error: LogError, scrub: Scrubber) -> str:
    """ "12 Nov 12:41 UTC mealwright.jobs: Couldn't thin the history (OperationalError)"."""
    message = scrub(error.message)
    if len(message) > LINE_LIMIT:
        message = message[: LINE_LIMIT - 1] + "…"
    kind = f" ({error.kind})" if error.kind else ""
    when = f"{error.at.day} {_MONTHS[error.at.month - 1]} {error.at:%H:%M} UTC"
    return f"{when} {error.logger}: {message}{kind}"


def version_line() -> str:
    return f"Mealwright {__version__}"
