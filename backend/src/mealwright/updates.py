"""Knowing about new versions (spec section 7, "Updates", cabledrawer 17 Oct): three levels.

1. **No connection, always on.** The app knows the day its version was released (`RELEASED`,
   written into the code with each release, next to the CHANGELOG's date; a test keeps the two
   the same). Settings › About works out how old it is and, after a while, says where new
   versions are listed. Opening that link is the person's own click.
2. **Check now (admins).** One plain GET of the public release list (`RELEASE_LIST_URL`)
   through the outbound gate, as `Connection.UPDATE_CHECK`: no query string, no cookies, and
   the only header we choose is the user agent, which is just "Mealwright". Nothing about the
   install or the version is sent; the answer is compared here, on the server.
3. **The daily check (off by default).** The same request once a day, while the Privacy switch
   "Check for updates daily" is on (`daily_check`, run by the scheduler in mealwright.jobs).

Check now always works for an admin when pressed (the note beside it says it asks GitHub's
release list); the Privacy switch controls only the automatic daily check (cabledrawer 12 Nov).
Check now asks the gate for that one request as a person's press (`pressed=True`, allowed for
`Connection.UPDATE_CHECK` only); every other rule of the gate still applies to it.

The last answer is kept in memory, per household, until the server restarts (cabledrawer 12 Nov,
accepted as built: no database change). After a restart the daily check runs again within the hour.

Log lines say what happened in plain words and never the address (as for every connection).
"""

import json
import logging
import re
import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from mealwright import __version__
from mealwright.models import Household, utcnow
from mealwright.outbound import (
    Connection,
    OutboundBlocked,
    OutboundFailed,
    OutboundGate,
    switches,
)

log = logging.getLogger(__name__)

# The day this version was released. The release PR sets it with the CHANGELOG's date
# (tests/test_updates.py checks they match).
RELEASED = date(2026, 11, 21)

# Mealwright's public home on GitHub (cabledrawer 15 and 21 Nov). The check stays off until the
# user turns it on in Settings > Outside connections; the request goes through the outbound gate.
# PLACEHOLDER_OWNER is a name GitHub can't have (a user name never has an underscore): a build
# whose list still names it asks nothing and answers "couldn't check" (security review r1;
# cabledrawer 12 Nov).
OWNER = "cabledrawer"
PLACEHOLDER_OWNER = "placeholder_until_1_0"
RELEASES_PAGE = f"https://github.com/{OWNER}/mealwright/releases"
RELEASE_LIST_URL = f"https://api.github.com/repos/{OWNER}/mealwright/releases"

# The release list is about 30 releases with their notes; anything bigger isn't read.
MAX_LIST_BYTES = 2 * 1024 * 1024
# GitHub's release list nests 5 deep (the list, a release, its assets, an asset, its
# uploader). Deeper answers are refused before they are parsed: how deep Python's JSON reader
# gets before it gives up depends on the build and its stack size, and an answer that parsed
# on one build was read as "up to date" (T4, 22 Nov).
MAX_LIST_DEPTH = 10
# A string runs to its closing quote, or to the end of an unfinished text: every quote
# starts a match, so the search never goes back over the text (no slow worst case).
_JSON_STRING = re.compile(rb'"[^"\\]*+(?:\\.?[^"\\]*+)*+(?:"|\Z)', re.DOTALL)
# Bytes to delete with `bytes.translate`, which holds no list of pieces in memory (T4
# security pass r1: deleting them one regex match at a time took 150 MB for a 2 MB answer).
# Every byte but quotes, backslashes and brackets becomes a space (not deleted: "\n" must
# stay an escape, not become an escaped quote).
_TO_STRUCTURE = bytes(byte if byte in b'"\\[]{}' else ord(" ") for byte in range(256))
_NOT_BRACKETS = bytes(byte for byte in range(256) if byte not in b"[]{}")
_ONE_BRACKET_KIND = bytes.maketrans(b"{}", b"[]")
# The longest one check may take, start to finish.
CHECK_TIME_LIMIT = 20.0
# Check now again within this long gives the answer just had, without connecting, so a busy
# finger can't send GitHub a stream of requests (cabledrawer 12 Nov). A failed answer is kept
# too: otherwise each press after a failure would connect again.
RECHECK_AFTER = timedelta(minutes=1)
# The daily check runs when the last answer is at least this old (a little under a day, so it
# doesn't drift later by an hour each day).
DAILY_AFTER = timedelta(hours=23)

Outcome = Literal["up_to_date", "newer", "failed"]


@dataclass(frozen=True)
class CheckResult:
    outcome: Outcome
    # The newest version found, as its tag ("v0.9.1"); only with "newer".
    latest: str | None
    checked_at: datetime


# --- Versions --------------------------------------------------------------------------------

_STAGES = {"alpha": 0, "a": 0, "beta": 1, "b": 1, "rc": 2}
_FINAL = 3
_PYTHON_FORM = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:(a|b|rc)(\d+))?$")
_TAG_FORM = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-(alpha|beta|rc)\.(\d+))?$")

Key = tuple[int, int, int, int, int]


def _key(found: re.Match[str]) -> Key:
    major, minor, patch, stage, number = found.groups()
    if stage is None:
        return (int(major), int(minor), int(patch), _FINAL, 0)
    return (int(major), int(minor), int(patch), _STAGES[stage], int(number))


def running_key(version: str = __version__) -> Key | None:
    """The running version ("0.9.0" or "0.9.0b1"), to compare; None if it isn't one we know."""
    found = _PYTHON_FORM.match(version)
    return _key(found) if found else None


def tag_key(tag: str) -> Key | None:
    """A release's tag ("v0.9.1", "v0.9.0-beta.1"), to compare; None for any other tag."""
    found = _TAG_FORM.match(tag) if len(tag) <= 40 else None
    return _key(found) if found else None


def _too_deep(body: bytes, depth: int) -> bool:
    """Do the JSON text's lists and objects nest more than `depth` deep? Worked out without
    parsing, and in little memory: the strings are taken out (one at a time, into one
    buffer), then everything but the brackets, then each round takes out the innermost empty
    pairs. Brackets that don't pair up count as too deep (the text isn't JSON anyway); a
    brace closed by a bracket counts as a pair here, and `json.loads` refuses it."""
    text = body.translate(_TO_STRUCTURE)
    outside = bytearray()
    end = 0
    for string in _JSON_STRING.finditer(text):
        outside += text[end : string.start()]
        end = string.end()
    outside += text[end:]
    brackets = bytes(outside).translate(_ONE_BRACKET_KIND, _NOT_BRACKETS)
    for _ in range(depth):
        if not brackets:
            return False
        brackets = brackets.replace(b"[]", b"")
    return bool(brackets)


def newest(body: bytes, running: Key) -> str | None:
    """The tag of the newest release in GitHub's release list that is newer than `running`,
    or None. Pre-releases count only while the running version is one too (cabledrawer 12
    Nov, accepted as built); drafts never. Raises ValueError if the answer isn't a release
    list: not UTF-8 JSON, nested deeper than MAX_LIST_DEPTH, or not a list."""
    # Strictly UTF-8 (UnicodeDecodeError is a ValueError): `json.loads` would also read
    # UTF-16 and UTF-32, where the depth check's bytes don't mean what it thinks (T4 review).
    text = body.decode("utf-8-sig")
    if _too_deep(body, MAX_LIST_DEPTH):
        raise ValueError("nested too deep")
    releases = json.loads(text)
    if not isinstance(releases, list):
        raise ValueError("not a list")
    pre = running[3] != _FINAL
    best: tuple[Key, str] | None = None
    for release in releases:
        if not isinstance(release, dict):
            continue
        tag = release.get("tag_name")
        if not isinstance(tag, str) or release.get("draft") is not False:
            continue
        prerelease = release.get("prerelease")
        if not isinstance(prerelease, bool) or (prerelease and not pre):
            continue
        key = tag_key(tag)
        if key is None or (key[3] != _FINAL and not pre):
            continue
        if key > running and (best is None or key > best[0]):
            best = (key, f"v{key[0]}.{key[1]}.{key[2]}" + _suffix(key))
    return best[1] if best else None


def _suffix(key: Key) -> str:
    if key[3] == _FINAL:
        return ""
    stage = {0: "alpha", 1: "beta", 2: "rc"}[key[3]]
    return f"-{stage}.{key[4]}"


# --- The check -------------------------------------------------------------------------------


def _now() -> datetime:
    return utcnow()


class UpdateChecks:
    """Checks the release list, and keeps each household's last answer."""

    def __init__(
        self,
        gate: OutboundGate,
        clock: Callable[[], datetime] = _now,
        version: str = __version__,
    ) -> None:
        self._gate = gate
        self._clock = clock
        self._version = version
        self._results: dict[int, CheckResult] = {}
        self._lock = threading.Lock()
        # One check at a time per household: a second one waits and gets the first one's answer.
        self._running: dict[int, threading.Lock] = {}
        # How many checks each household has had answered, so a waiting check can tell that
        # the one it waited for has answered.
        self._answered: dict[int, int] = {}

    def last(self, household_id: int) -> CheckResult | None:
        with self._lock:
            return self._results.get(household_id)

    def forget(self, household_id: int) -> None:
        """Drop a deleted household's last answer (and its counters)."""
        with self._lock:
            self._results.pop(household_id, None)
            self._answered.pop(household_id, None)

    def _keep(self, household_id: int, result: CheckResult) -> CheckResult:
        with self._lock:
            self._results[household_id] = result
            self._answered[household_id] = self._answered.get(household_id, 0) + 1
        return result

    def _one_at_a_time(self, household_id: int) -> threading.Lock:
        with self._lock:
            return self._running.setdefault(household_id, threading.Lock())

    def check_now(self, household_id: int) -> CheckResult:
        """An admin's Check now: one request (whatever the daily switch says), unless another
        check answered while this one waited for it (that answer), or an answer came within
        RECHECK_AFTER, failed or not (that answer again)."""
        running = self._one_at_a_time(household_id)
        with self._lock:
            answered = self._answered.get(household_id, 0)
        with running:
            with self._lock:
                last = self._results.get(household_id)
                waited = self._answered.get(household_id, 0) != answered
            if last is not None and waited:
                return last
            if last is not None and self._clock() - last.checked_at < RECHECK_AFTER:
                return last
            return self._check(household_id, pressed=True)

    def _check(self, household_id: int, *, pressed: bool = False) -> CheckResult:
        now = self._clock()
        running = running_key(self._version)
        if running is None:  # a test build's own version text: nothing to compare with
            log.warning("Update check: this build's version can't be compared")
            return self._keep(household_id, CheckResult("failed", None, now))
        url = RELEASE_LIST_URL  # read here, so a test can point it at its own list
        if f"/{PLACEHOLDER_OWNER}/" in url:
            log.warning(
                "Update check: nothing was asked, because Mealwright's public release list "
                "starts with version 1.0"
            )
            return self._keep(household_id, CheckResult("failed", None, now))
        try:
            response = self._gate.request(
                household_id,
                Connection.UPDATE_CHECK,
                url,
                max_bytes=MAX_LIST_BYTES,
                time_limit=CHECK_TIME_LIMIT,
                pressed=pressed,
            )
        except OutboundFailed as failed:
            log.warning("Update check: couldn't reach the release list (%s)", failed.kind)
            return self._keep(household_id, CheckResult("failed", None, now))
        except OutboundBlocked as blocked:
            if not pressed and not self._gate.is_allowed(household_id, Connection.UPDATE_CHECK):
                # The daily switch was turned off just now: nothing was asked, nothing kept.
                return CheckResult("failed", None, now)
            log.warning("Update check: the answer was refused (%s)", type(blocked).__name__)
            return self._keep(household_id, CheckResult("failed", None, now))
        if response.status != 200:
            log.warning("Update check: the release list answered %d", response.status)
            return self._keep(household_id, CheckResult("failed", None, now))
        try:
            latest = newest(response.body, running)
        except ValueError, RecursionError:
            log.warning("Update check: the release list couldn't be read")
            return self._keep(household_id, CheckResult("failed", None, now))
        if latest is None:
            return self._keep(household_id, CheckResult("up_to_date", None, now))
        log.info("Update check: a newer version is out")
        return self._keep(household_id, CheckResult("newer", latest, now))

    def daily_check(self, factory: sessionmaker[Session]) -> None:
        """The daily check (the scheduler runs this every hour): for each household with the
        switch on whose last answer is missing or at least DAILY_AFTER old, one request. A
        household with the switch off is never checked. Never raises."""
        try:
            with factory() as db:
                due = [
                    household.id
                    for household in db.scalars(select(Household))
                    if switches(db, household.id)[Connection.UPDATE_CHECK]
                ]
        except Exception:
            log.exception("Couldn't start the daily update check (will try again within the hour)")
            return
        for household_id in due:
            # Not at the same time as a Check now, which would make two requests.
            with self._one_at_a_time(household_id):
                last = self.last(household_id)
                if last is not None and self._clock() - last.checked_at < DAILY_AFTER:
                    continue
                try:
                    self._check(household_id)
                except Exception:
                    log.exception("The daily update check failed (will try again within the hour)")
