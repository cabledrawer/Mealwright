"""The real-recipe check (0.5; dev-only, run by hand, never in `./check` or the image).

Reads a markdown list of recipe addresses, fetches each page the way the app does, reads the
recipe and the ingredient lines, and writes a report of what it found. It only reports: it has
no pass mark. Spec section 6, "Real-recipe test" and "The 80 real recipes".

    cd backend
    uv run python scripts/import_check.py [--list URLS.md] [--report REPORT.md]

The list (default `import-check/urls.md` in the sync folder, outside the repo; the folder is
`$MEALWRIGHT_SYNC_DIR`, or `repo-sync` in the current folder):

    ## BBC Good Food            <- a heading starts a group (a site)
    - https://... — tomato soup  <- an address, then " — " and a note
    > a note                     <- lines starting with ">" or "# ", and blank lines, are skipped
    anything else                <- ignored, and counted in the report

What it does for each address, one at a time, and at most one request every 5 seconds per site:

1. `page_fetch.fetch_page` through a real `OutboundGate` (the app's user agent, limits and
   address checks) on a throwaway database where only "Recipe import from links" is on.
2. `page_budget.read_within_budget`, then `ingredient_reader.read_line` on each ingredient line.

No photo is downloaded: the report says only whether the page names one. Nothing of a page is
saved, and the report holds no page text beyond the first 40 characters of the title and the
ingredient lines the reader couldn't read. All network use is in `page_fetch` (the suite's
"no direct networking" test scans this folder).
"""

import argparse
import os
import re
import sys
import tempfile
import time
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlsplit

# The app's API package first: `ingredient_reader` reaches into it and it reaches back, so
# loading `ingredient_reader` first stops on an import loop (the app itself always loads
# the API first). The page reader's own process loads this script again, so it matters there
# too.
import mealwright.api.v1  # noqa: F401
from mealwright import migrate, page_budget
from mealwright.db import make_engine, make_sessionmaker
from mealwright.ingredient_reader import ReadLine, read_line
from mealwright.models import Household
from mealwright.outbound import Connection, OutboundGate, install_network_guard, set_switch
from mealwright.page_fetch import FetchedPage, FetchRefused, Problem, fetch_page
from mealwright.page_reader import PageRecipe



def default_paths() -> tuple[Path, Path]:
    """The list and the report, in the sync folder (outside the repo): $MEALWRIGHT_SYNC_DIR, else ./repo-sync."""
    sync = Path(os.environ.get("MEALWRIGHT_SYNC_DIR", "repo-sync"))
    return sync / "import-check" / "urls.md", sync / "import-check-0.5.md"


# At most one request every this many seconds to one site.
GAP_SECONDS = 5.0
TITLE_CHARS = 40
LINE_CHARS = 120
NO_GROUP = "(no group)"

# The result column. The words after "read" are the app's own kinds of problem
# (`page_fetch.Problem`), grouped; the code itself is shown beside them.
READ = "read"
NO_RECIPE = "no recipe data"
REFUSED = "refused by the site"
BLOCKED = "blocked"
COULDNT = "couldn't read"
KINDS = (READ, NO_RECIPE, REFUSED, BLOCKED, COULDNT)

_KIND_OF_PROBLEM = {
    Problem.SITE_ERROR: REFUSED,
    Problem.SITE_REFUSED: REFUSED,
    Problem.SWITCHED_OFF: BLOCKED,
    Problem.PHOTO_SWITCHED_OFF: BLOCKED,
    Problem.BAD_LINK: BLOCKED,
    Problem.ALWAYS_BLOCKED: BLOCKED,
    Problem.OWN_NETWORK: BLOCKED,
    Problem.ODD_PORT: BLOCKED,
}

_NUMBER_WORDS = frozenset(
    {
        *("one", "two", "three", "four", "five", "six"),
        *("seven", "eight", "nine", "ten", "eleven", "twelve"),
        *("half", "quarter", "dozen"),
    }
)
_LEADING_NUMBER = re.compile(r"^\s*([\d¼½¾⅐-⅞][\d¼½¾⅐-⅞.,/\-\u2013]*)\s*([^\W\d_]+)?")
_FIRST_WORD = re.compile(r"^\s*([^\W\d_]+)")


# --- The list -----------------------------------------------------------------------------------


@dataclass(frozen=True)
class Entry:
    number: int  # 1, 2, 3… in list order
    group: str
    address: str
    note: str


@dataclass(frozen=True)
class ParsedList:
    entries: tuple[Entry, ...]
    odd_lines: tuple[int, ...]  # line numbers (from 1) of lines that were ignored


def parse_list(text: str) -> ParsedList:
    """Headings (`## `) are groups; `- <address> — <note>` lines are recipes; blank lines and
    lines starting with `>` or `# ` are notes, skipped quietly; anything else is ignored and
    its line number kept so the report can count it."""
    entries: list[Entry] = []
    odd: list[int] = []
    group = NO_GROUP
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.strip()
        if not line or line.startswith(">") or line.startswith("# "):
            continue
        if line.startswith("## "):
            group = line[3:].strip() or NO_GROUP
            continue
        if line.startswith("- "):
            address, _, note = line[2:].strip().partition(" — ")
            address = address.strip()
            if re.match(r"https?://\S+$", address, re.IGNORECASE):
                entries.append(Entry(len(entries) + 1, group, address, note.strip()))
                continue
        odd.append(number)
    return ParsedList(tuple(entries), tuple(odd))


# --- Checking one address -----------------------------------------------------------------------


@dataclass(frozen=True)
class Outcome:
    entry: Entry
    kind: str
    problem: str = ""  # the app's problem code, or "error: <class name>"
    title: str = ""
    ingredients_read: int = 0
    ingredients_unread: int = 0
    steps: int = 0
    photo_named: bool = False
    unread_lines: tuple[str, ...] = ()
    unknown_words: tuple[str, ...] = ()


type Fetcher = Callable[[str], FetchedPage]
type Reader = Callable[[str, str], PageRecipe | None]


def unknown_words(line: ReadLine) -> list[str]:
    """Words that probably stopped the reader finding an amount: on a line that starts with a
    number or a number word but has no amount, the number as written and the word after it.
    A rough guide; the reader doesn't say which words it didn't know."""
    if line.amount is not None:
        return []
    found: list[str] = []
    number = _LEADING_NUMBER.match(line.text)
    if number is not None:
        found.append(number.group(1))
        if number.group(2):
            found.append(number.group(2).lower())
    else:
        first = _FIRST_WORD.match(line.text)
        if first is not None and first.group(1).lower() in _NUMBER_WORDS:
            found.append(first.group(1).lower())
    return found


def check_one(entry: Entry, fetch: Fetcher, read: Reader) -> Outcome:
    """Fetch and read one address. Never raises (except for Ctrl-C): a failure is a result."""
    try:
        page = fetch(entry.address)
    except FetchRefused as refused:
        kind = _KIND_OF_PROBLEM.get(refused.problem, COULDNT)
        return Outcome(entry, kind, problem=str(refused.problem))
    except Exception as error:  # one failure never stops the run
        return Outcome(entry, COULDNT, problem=f"error: {type(error).__name__}")
    try:
        recipe = read(page.html, page.url)
    except page_budget.PageUnreadable as unreadable:
        return Outcome(entry, COULDNT, problem=f"{Problem.CANT_READ} ({unreadable.reason})")
    except Exception as error:
        return Outcome(entry, COULDNT, problem=f"error: {type(error).__name__}")
    if recipe is None:
        return Outcome(entry, NO_RECIPE)

    unread: list[str] = []
    words: list[str] = []
    done = 0
    for item in recipe.ingredients:
        if item.heading:
            continue
        line = read_line(item.text)
        if line.readable:
            done += 1
        else:
            unread.append(_short(item.text))
        for word in unknown_words(line):
            if word not in words:
                words.append(word)
    return Outcome(
        entry,
        READ,
        title=recipe.name,
        ingredients_read=done,
        ingredients_unread=len(unread),
        steps=sum(1 for step in recipe.steps if not step.heading),
        photo_named=recipe.photo_url is not None,
        unread_lines=tuple(unread),
        unknown_words=tuple(words),
    )


def _short(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= LINE_CHARS else text[: LINE_CHARS - 1] + "…"


# --- The run: one at a time, spaced per site ----------------------------------------------------


def site_of(address: str) -> str:
    """The key for "one site": the host in lower case, with a leading "www." dropped, so
    www.example.com and example.com are one site and share the 5-second gap (#60)."""
    host = (urlsplit(address).hostname or "").lower()
    return host.removeprefix("www.")


class Spacer:
    """At most one request every `gap` seconds to one site: waits (with the injected `sleep`)
    until `gap` seconds after the last request to that site ended."""

    def __init__(
        self,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        gap: float = GAP_SECONDS,
    ) -> None:
        self._clock = clock
        self._sleep = sleep
        self._gap = gap
        self._last: dict[str, float] = {}

    def wait(self, site: str) -> None:
        last = self._last.get(site)
        if last is not None:
            remaining = last + self._gap - self._clock()
            if remaining > 0:
                self._sleep(remaining)

    def done(self, site: str) -> None:
        self._last[site] = self._clock()


@dataclass
class Run:
    entries: tuple[Entry, ...]
    outcomes: list[Outcome] = field(default_factory=list)
    interrupted: bool = False


def run_check(
    entries: Sequence[Entry],
    fetch: Fetcher,
    read: Reader,
    spacer: Spacer | None = None,
    progress: Callable[[str], None] = lambda _message: None,
) -> Run:
    """Every entry in order. Ctrl-C stops the run and keeps what is done so far."""
    spacer = spacer or Spacer()
    run = Run(tuple(entries))
    try:
        for entry in entries:
            site = site_of(entry.address)
            spacer.wait(site)
            try:
                outcome = check_one(entry, fetch, read)
            finally:
                spacer.done(site)
            run.outcomes.append(outcome)
            # The number and the result only: never an address.
            progress(f"[{entry.number}/{len(entries)}] {outcome.kind}")
    except KeyboardInterrupt:
        run.interrupted = True
    return run


# --- The report ---------------------------------------------------------------------------------


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _title_cell(title: str) -> str:
    if not title:
        return "no"
    shown = " ".join(title.split())
    cut = shown[:TITLE_CHARS] + ("…" if len(shown) > TITLE_CHARS else "")
    return f"yes: {_cell(cut)}"


def render_report(run: Run, parsed: ParsedList, when: str) -> str:
    out: list[str] = ["# Real-recipe check, 0.5", ""]
    out.append(
        f"Run on {when}. Reports only: there is no pass mark. Pages were fetched one at a time,"
        f" at most one request every {GAP_SECONDS:g} seconds per site, with the app's own"
        " fetching rules and user agent. No photo was downloaded, and nothing of any page was"
        " saved."
    )
    out.append("")
    if run.interrupted:
        out.append(
            f"**Stopped early (Ctrl-C):** {len(run.outcomes)} of {len(run.entries)} addresses"
            " were done; the rest are not in this report."
        )
        out.append("")
    if parsed.odd_lines:
        numbers = ", ".join(str(n) for n in parsed.odd_lines)
        out.append(
            f"{len(parsed.odd_lines)} line(s) in the list were ignored (not a heading, an"
            f" address line or a note): line {numbers}."
        )
    else:
        out.append("No lines in the list were ignored.")
    out.append("")
    out.append(
        'The "what it read" column (JSON-LD or microdata) is left out: the page reader does not'
        " say which it used, and the check does not change the reader."
    )
    out.append("")

    out.append("## Summary")
    out.append("")
    out.append(
        "| # | Group | Result | Title found | Ingredients read | Not read | Steps |"
        " Photo named | Address |"
    )
    out.append("|---|---|---|---|---|---|---|---|---|")
    for o in run.outcomes:
        result = o.kind + (f" ({o.problem})" if o.problem else "")
        if o.kind == READ:
            numbers = f"{o.ingredients_read} | {o.ingredients_unread} | {o.steps}"
            title, photo = _title_cell(o.title), "yes" if o.photo_named else "no"
        else:
            numbers, title, photo = "- | - | -", "-", "-"
        out.append(
            f"| {o.entry.number} | {_cell(o.entry.group)} | {_cell(result)} | {title} |"
            f" {numbers} | {photo} | {_cell(o.entry.address)} |"
        )
    out.append("")

    out.append("## By group")
    out.append("")
    groups: dict[str, list[Entry]] = {}
    for entry in run.entries:
        groups.setdefault(entry.group, []).append(entry)
    by_number = {o.entry.number: o for o in run.outcomes}
    for name, members in groups.items():
        counts = Counter(by_number[e.number].kind for e in members if e.number in by_number)
        parts = [f"{counts[kind]} {kind}" for kind in KINDS if counts[kind]]
        missing = sum(1 for e in members if e.number not in by_number)
        if missing:
            parts.append(f"{missing} not reached")
        out.append(f"- **{_cell(name)}:** {len(members)} address(es): {', '.join(parts) or 'none'}")
    out.append("")

    out.append("## What the reader could not read")
    out.append("")
    out.append(
        "Per recipe: the ingredient lines it could not read, and, for lines that start with a"
        " number but got no amount, the number and the word after it (a guide to unit or"
        " number words it did not know)."
    )
    out.append("")
    shown = False
    for o in run.outcomes:
        if o.kind != READ or not (o.unread_lines or o.unknown_words):
            continue
        shown = True
        out.append(f"### {o.entry.number}. {_cell(o.entry.group)}")
        out.append("")
        if o.entry.note:
            out.append(f"Note in the list: {_cell(o.entry.note)}")
            out.append("")
        for text in o.unread_lines:
            out.append(f"- not read: {_cell(text)}")
        if o.unknown_words:
            out.append(f"- words not known: {_cell(', '.join(o.unknown_words))}")
        out.append("")
    if not shown:
        out.append("Nothing to list.")
        out.append("")
    return "\n".join(out)


# --- The real fetcher ---------------------------------------------------------------------------


@contextmanager
def real_fetcher() -> Iterator[Fetcher]:
    """`fetch_page` through a real OutboundGate, on a throwaway database in which household 1
    has only "Recipe import from links" switched on."""
    with tempfile.TemporaryDirectory(prefix="mealwright-import-check-") as folder:
        engine = make_engine(f"sqlite:///{Path(folder) / 'check.db'}")
        try:
            migrate.upgrade(engine)
            sessions = make_sessionmaker(engine)
            with sessions() as session:
                session.add(Household(id=1, name="Import check"))
                session.commit()
                set_switch(session, 1, Connection.RECIPE_IMPORT, True)
                session.commit()
            gate = OutboundGate(sessions)
            yield lambda address: fetch_page(gate, 1, address)
        finally:
            engine.dispose()


# --- The command --------------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> int:
    default_list, default_report = default_paths()
    parser = argparse.ArgumentParser(description="Check the recipe reader on real pages.")
    parser.add_argument("--list", type=Path, default=default_list, help="the markdown list")
    parser.add_argument("--report", type=Path, default=default_report, help="where to write")
    args = parser.parse_args(argv)

    parsed = parse_list(args.list.read_text(encoding="utf-8"))
    if not parsed.entries:
        print("The list has no addresses.", file=sys.stderr)
        return 1
    print(f"{len(parsed.entries)} addresses; one at a time, 5 seconds apart per site.")
    install_network_guard()
    with real_fetcher() as fetch:
        run = run_check(parsed.entries, fetch, page_budget.read_within_budget, progress=print)
    when = datetime.now(UTC).strftime("%d %b %Y")
    args.report.write_text(render_report(run, parsed, when), encoding="utf-8")
    note = " (stopped early)" if run.interrupted else ""
    print(f"Report written{note}.")
    return 130 if run.interrupted else 0


if __name__ == "__main__":
    sys.exit(main())
