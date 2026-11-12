"""Settings → About → Report a problem (spec section 7, "Bug reports", cabledrawer 17 Oct; plan row X2).

The server builds the report with personal details already removed and never sends it anywhere.
Each kind of personal detail is planted in the log and must not come back.
"""

import os
import re
import time
import unicodedata
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, update

from mealwright import __version__, problem_report
from mealwright.auth import hash_password
from mealwright.config import Settings
from mealwright.logs import FILE_NAME
from mealwright.models import (
    FoodName,
    Household,
    ImportDraft,
    Login,
    Member,
    OwnNetworkEntry,
    Recipe,
)
from mealwright.outbound import Connection, OutboundGate
from mealwright.problem_report import (
    ERRORS_KEPT,
    NEW_ISSUE_PAGE,
    LogError,
    Scrubber,
    ServerAddress,
    browser_words,
    error_line,
    recent_errors,
)
from mealwright.updates import RELEASES_PAGE

API = "/api/v1"


def stamp(at: datetime) -> str:
    return at.strftime("%Y-%m-%dT%H:%M:%SZ")


def log_folder(settings: Settings) -> Path:
    folder = settings.data_dir / "logs"
    folder.mkdir(exist_ok=True)
    return folder


def write_log(folder: Path, lines: list[str], name: str = FILE_NAME) -> Path:
    path = folder / name
    with path.open("a", encoding="utf-8") as file:
        file.write("\n".join(lines) + "\n")
    return path


def error(
    message: str, *, ago: timedelta = timedelta(minutes=5), name: str = "mealwright.x"
) -> str:
    return f"{stamp(datetime.now(UTC) - ago)} ERROR {name}: {message}"


# --- The browser and device ----------------------------------------------------------------


IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1"
)
ANDROID_CHROME = (
    "Mozilla/5.0 (Linux; Android 14; Pixel 8 Build/AP1A) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.6778.81 Mobile Safari/537.36"
)
WINDOWS_EDGE = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36 Edg/131.0.2903.70"
)
MAC_FIREFOX = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.6; rv:132.0) Gecko/20100101 Firefox/132.0"
LINUX_CHROME = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)
SAMSUNG = (
    "Mozilla/5.0 (Linux; Android 14; SM-S921B) AppleWebKit/537.36 (KHTML, like Gecko) "
    "SamsungBrowser/26.0 Chrome/122.0.0.0 Mobile Safari/537.36"
)
IPAD_FIREFOX = (
    "Mozilla/5.0 (iPad; CPU OS 17_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "FxiOS/132.0 Mobile/15E148 Safari/605.1.15"
)


@pytest.mark.parametrize(
    ("agent", "words"),
    [
        (IPHONE, "Safari 18 · iPhone"),
        (ANDROID_CHROME, "Chrome 131 · Android phone"),
        (WINDOWS_EDGE, "Edge 131 · Windows"),
        (MAC_FIREFOX, "Firefox 132 · Mac"),
        (LINUX_CHROME, "Chrome 130 · Linux"),
        (SAMSUNG, "Samsung Internet 26 · Android phone"),
        (IPAD_FIREFOX, "Firefox 132 · iPad"),
        ("curl/8.5.0", "Unknown browser"),
        ("", "Unknown browser"),
        (None, "Unknown browser"),
    ],
)
def test_the_browser_is_its_name_major_version_and_kind_of_device(
    agent: str | None, words: str
) -> None:
    assert browser_words(agent) == words


def test_the_browser_line_never_names_the_phone_model_or_exact_version() -> None:
    words = browser_words(ANDROID_CHROME)
    assert "Pixel" not in words
    assert "6778" not in words
    assert "14" not in words


# --- Recent errors from the log --------------------------------------------------------------


def test_only_errors_of_the_last_day_are_read(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    write_log(
        tmp_path,
        [
            f"{stamp(now - timedelta(hours=30))} ERROR mealwright.old: Too old",
            f"{stamp(now - timedelta(hours=2))} INFO mealwright.sign_in: Signed in",
            f"{stamp(now - timedelta(hours=2))} WARNING mealwright.y: Only a warning",
            f"{stamp(now - timedelta(hours=1))} ERROR mealwright.jobs: Recent",
            f"{stamp(now - timedelta(minutes=1))} CRITICAL mealwright.z: Very bad",
        ],
    )
    found = recent_errors(tmp_path, now)
    assert [(e.logger, e.message) for e in found] == [
        ("mealwright.jobs", "Recent"),
        ("mealwright.z", "Very bad"),
    ]


def test_at_most_the_last_twenty_errors(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    lines = [
        f"{stamp(now - timedelta(minutes=60 - n))} ERROR mealwright.x: Error {n}" for n in range(30)
    ]
    write_log(tmp_path, lines)
    found = recent_errors(tmp_path, now)
    assert ERRORS_KEPT == 20
    assert [e.message for e in found] == [f"Error {n}" for n in range(10, 30)]


def test_yesterdays_file_is_read_too_and_old_files_are_not(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    write_log(
        tmp_path,
        [f"{stamp(now - timedelta(hours=20))} ERROR mealwright.x: Before midnight"],
        f"{FILE_NAME}.2026-11-11",
    )
    old = write_log(
        tmp_path,
        [f"{stamp(now - timedelta(hours=1))} ERROR mealwright.x: In a file last written long ago"],
        f"{FILE_NAME}.2026-10-01",
    )
    two_days_ago = time.time() - 2 * 24 * 3600
    os.utime(old, (two_days_ago, two_days_ago))
    write_log(tmp_path, [f"{stamp(now - timedelta(hours=1))} ERROR mealwright.x: After midnight"])
    assert [e.message for e in recent_errors(tmp_path, now)] == [
        "Before midnight",
        "After midnight",
    ]


def test_a_traceback_gives_only_the_kind_of_error(tmp_path: Path) -> None:
    now = datetime.now(UTC)
    write_log(
        tmp_path,
        [
            f"{stamp(now - timedelta(minutes=3))} ERROR uvicorn.error: "
            "Exception in ASGI application",
            "Traceback (most recent call last):",
            '  File "/app/src/mealwright/recipes.py", line 12, in save',
            "    name = secret_recipe_variable",
            "sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) near 'Granny pie'",
            f"{stamp(now - timedelta(minutes=2))} ERROR mealwright.x: No traceback here",
        ],
    )
    found = recent_errors(tmp_path, now)
    assert [(e.message, e.kind) for e in found] == [
        ("Exception in ASGI application", "OperationalError"),
        ("No traceback here", None),
    ]


def traceback_log(folder: Path, tail: list[str]) -> list[LogError]:
    now = datetime.now(UTC)
    write_log(
        folder,
        [
            f"{stamp(now - timedelta(minutes=3))} ERROR uvicorn.error: Exception in ASGI app",
            "Traceback (most recent call last):",
            '  File "/app/src/mealwright/x.py", line 1, in f',
            "    raise ValueError(text)",
            *tail,
        ],
    )
    return recent_errors(folder, now)


def test_the_kind_is_the_first_line_after_the_last_frame(tmp_path: Path) -> None:
    """Review r1: a multi-line error message's last line is not the kind of error."""
    found = traceback_log(tmp_path, ["ValueError: couldn't read the line", "Tess: 2 cups"])
    assert [e.kind for e in found] == ["ValueError"]


def test_the_kind_is_the_errors_class_not_a_later_line(tmp_path: Path) -> None:
    found = traceback_log(
        tmp_path,
        [
            "pydantic_core._pydantic_core.ValidationError: 1 validation error for Choices",
            "names.Mabel",
            "  Input should be a valid string [type=string_type]",
        ],
    )
    assert [e.kind for e in found] == ["ValidationError"]


def test_a_kind_that_is_not_a_class_name_is_just_error(tmp_path: Path) -> None:
    found = traceback_log(tmp_path, ["Tess Marsh's pantry: 2 cups"])
    assert [e.kind for e in found] == ["error"]


def test_the_kind_is_scrubbed_too() -> None:
    scrub = Scrubber(FakeDB({"Login.name": ["Ramaswamy"]}), NO_SERVER, Path("/data"))
    at = datetime(2026, 11, 12, 12, 41, tzinfo=UTC)
    line = error_line(LogError(at, "mealwright.x", "Broke", "Ramaswamy"), scrub)
    assert "Ramaswamy" not in line
    assert line.endswith("Broke ([name])")


def test_no_log_folder_is_no_errors(tmp_path: Path) -> None:
    assert recent_errors(tmp_path / "missing") == []


# --- The API ----------------------------------------------------------------------------------


@pytest.fixture
def kitchen(kitchen: TestClient) -> TestClient:
    """The conftest kitchen, set up two days ago: the log's recent errors only count from the
    set-up (review r1), and these tests write errors from minutes ago."""
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(update(Household).values(created_at=datetime.now(UTC) - timedelta(days=2)))
        db.commit()
    return kitchen


@pytest.fixture
def neighbour(neighbour: TestClient) -> TestClient:
    """The next-door household, set up two days ago too."""
    with neighbour.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(update(Household).values(created_at=datetime.now(UTC) - timedelta(days=2)))
        db.commit()
    return neighbour


@pytest.fixture
def member(kitchen: TestClient) -> Iterator[TestClient]:
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(
            Login(
                household_id=1,
                username="wren_user",
                name="Ramaswamy",
                password_hash=hash_password("wren's own password"),
                role="member",
            )
        )
        db.commit()
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        body = {"username": "wren_user", "password": "wren's own password"}
        assert other.post(f"{API}/session", json=body).status_code == 200
        yield other


def report(client: TestClient, **headers: str) -> dict:
    response = client.get(f"{API}/problem-report", headers=headers)
    assert response.status_code == 200, response.text
    body: dict = response.json()
    return body


def test_the_report_has_the_version_browser_and_issue_page(kitchen: TestClient) -> None:
    body = report(kitchen, **{"User-Agent": IPHONE})
    assert body == {
        "version": f"Mealwright {__version__}",
        "browser": "Safari 18 · iPhone",
        "errors": [],
        "errors_included": True,
        "new_issue_page": NEW_ISSUE_PAGE,
    }


def test_the_issue_page_is_the_releases_pages_project() -> None:
    assert RELEASES_PAGE.endswith("/releases")
    assert RELEASES_PAGE.removesuffix("/releases") + "/issues/new" == NEW_ISSUE_PAGE
    assert NEW_ISSUE_PAGE.startswith("https://github.com/")


def test_an_admins_report_has_the_recent_errors(kitchen: TestClient, settings: Settings) -> None:
    write_log(log_folder(settings), [error("Couldn't thin the history", name="mealwright.jobs")])
    errors = report(kitchen)["errors"]
    assert len(errors) == 1
    assert errors[0].endswith("UTC mealwright.jobs: Couldn't thin the history")


def test_a_members_report_has_no_errors_from_the_log(
    kitchen: TestClient, member: TestClient, settings: Settings
) -> None:
    write_log(log_folder(settings), [error("Something broke for next door")])
    body = report(member)
    assert (body["errors"], body["errors_included"]) == ([], False)
    assert body["version"] == f"Mealwright {__version__}"


def test_the_report_needs_sign_in(client: TestClient) -> None:
    assert client.get(f"{API}/problem-report").status_code == 401


def test_making_the_report_never_connects(
    kitchen: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Every Privacy switch on, and still nothing goes through the outbound gate (and the
    suite's network guard fails any connection made around it)."""
    for connection in Connection:
        kitchen.put(f"{API}/privacy/switches/{connection.value}", json={"on": True})
    asked: list[object] = []
    monkeypatch.setattr(OutboundGate, "request", lambda *args, **kw: asked.append(args))
    write_log(log_folder(settings), [error("See https://example.org/x for more")])
    report(kitchen)
    assert asked == []


# --- Personal details are removed ----------------------------------------------------------------


# "Tess Marsh" in Tamil, "Tess Sutton" in Hindi and "Bikash Ray" in Bengali.
TAMIL = "டெஸ்ஸா ரென்"
HINDI = "टेस्सा सटन"
BENGALI = "বিকাশ রায়"


@pytest.fixture
def planted(kitchen: TestClient, neighbour: TestClient) -> TestClient:
    """A kitchen with names of every kind, in this household and next door."""

    def ok(response: object, code: int = 201) -> dict:
        assert response.status_code == code, response.text  # type: ignore[attr-defined]
        return response.json()  # type: ignore[attr-defined]

    recipe = ok(kitchen.post(f"{API}/recipes", json={"name": "Granny Mabel's lasagne"}))
    ok(neighbour.post(f"{API}/recipes", json={"name": "Next-door goulash"}))
    food = ok(kitchen.post(f"{API}/foods", json={"name": "Thuvaram paruppu"}))["food"]
    ok(neighbour.post(f"{API}/foods", json={"name": "Neighbour's sourdough"}))
    ok(kitchen.post(f"{API}/shopping/lists", json={"name": "Diwali party"}))
    ok(kitchen.post(f"{API}/shops", json={"name": "Patel Brothers"}))
    # Review r2: names with numbers in them, and recipe names that start with a contraction.
    ok(kitchen.post(f"{API}/shopping/lists", json={"name": "Diwali 2025 party"}))
    ok(neighbour.post(f"{API}/shopping/lists", json={"name": "Week 2026-11-09 shop"}))
    for name in [
        "Christmas 2025 surprise for Granddad",
        "Ayla birthday cake 1,000 layers",
        "It's a Wrap",
        "Today's Special",
        "Let's Eat",
    ]:
        ok(kitchen.post(f"{API}/recipes", json={"name": name}))
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(FoodName(household_id=1, food_id=food["id"], name="Arhar dal"))
        db.execute(
            update(Recipe)
            .where(Recipe.id == recipe["id"])
            .values(source_url="https://www.secret-cooking-site.example/lasagne")
        )
        db.add(
            ImportDraft(
                household_id=1,
                source_kind="link",
                source_text="",
                site="another-cooking-site.example",
                name="Draft paneer tikka",
                review={},
                choices={},
            )
        )
        db.add(
            OwnNetworkEntry(
                household_id=1, kind="name", value="nas.lan", added_by_name="Vance Hale"
            )
        )
        for household, username, name in [
            (1, "jos", "Jos\u00e9 \u00d8rsted"),
            (2, "smu", "Stra\u00dfe M\u00fcller"),
            (1, "ipk", "\u0130pek Y\u0131lmaz"),
            (2, "awong", "Amy Wong"),
            (1, "rli", "Raj Li"),
            (2, "amd", "Anne-Marie Dupont"),
            # Review r2, M1: scripts whose words hold vowel signs and joiners.
            (1, "tw2", TAMIL),
            (2, "ts3", HINDI),
            (1, "bkr", BENGALI),
        ]:
            db.add(
                Login(
                    household_id=household,
                    username=username,
                    name=name,
                    password_hash=None,
                    role="member",
                )
            )
        for name in [
            "Thinly sliced beef with seeds removed",
            "Rest an hour, then check and start again",
        ]:
            db.add(Recipe(household_id=1, name=name))
        db.add(
            Recipe(
                household_id=2,
                name="Plain sponge",
                description="Bake at 180 degrees for 1 1/2 hours then hide it from Ayla",
            )
        )
        db.execute(update(Login).where(Login.username == "tess").values(name="Tess Marsh"))
        db.execute(update(Household).where(Household.id == 1).values(name="The Marshes"))
        db.commit()
    return kitchen


# Each kind of personal detail: what is planted in a log line, and what it becomes.
PLANTED = [
    ("a username", "Sign-in for tess failed", "tess", "[name]"),
    ("a person's name", "Tess Marsh's phone gave up", "Tess Marsh", "[name]"),
    ("a household's name", "Household The Marshes broke", "The Marshes", "[name]"),
    ("next door's username", "Sign-in for neighbour failed", "neighbour", "[name]"),
    ("a recipe", "Couldn't save Granny Mabel's lasagne", "lasagne", "[recipe]"),
    ("next door's recipe", "Couldn't save Next-door goulash now", "goulash", "[recipe]"),
    ("an import draft", "Draft paneer tikka stuck", "paneer", "[recipe]"),
    ("an ingredient", "Thuvaram paruppu had no size", "Thuvaram", "[ingredient]"),
    ("an ingredient's other name", "Arhar dal matched twice", "Arhar", "[ingredient]"),
    ("next door's ingredient", "Neighbour's sourdough went", "sourdough", "[ingredient]"),
    ("one word of a person's name", "Mrs Marsh again", "Marsh", "[name]"),
    ("a shopping list", "List Diwali party refused", "Diwali", "[removed]"),
    ("a shop", "Patel Brothers has no aisle", "Patel", "[removed]"),
    (
        "a recipe site",
        "Fetch from www.secret-cooking-site.example timed out",
        "secret-cooking",
        None,
    ),
    ("an import site", "another-cooking-site.example said no", "another-cooking-site", "[site]"),
    (
        "the server's host name",
        "Bad Host mealwright.marsh.example seen",
        "marsh.example",
        "[server]",
    ),
    ("the server's port", "Listening on mealwright.marsh.example:8443 failed", "8443", "[port]"),
    ("an own-network host", "nas.lan didn't answer", "nas.lan", "[server]"),
    ("an IPv4 address", "From 192.168.1.23 refused", "192.168.1.23", "[address]"),
    ("an IPv6 address", "From fe80::1c2b:3aff:fe4d:5e6f refused", "fe80", "[address]"),
    ("a link", "Got https://example.org/recipes/42?who=me back", "example.org", "[link]"),
    ("an e-mail address", "Mail to cook@marsh.example bounced", "cook@", "[e-mail]"),
    ("a file in the data folder", "Can't read /data/photos/ab12.jpg now", "/data/photos", "[file]"),
    ("quoted text", "Bad words 'my secret note' given", "my secret note", "[text]"),
    ("curly-quoted text", "Bad words \u2018my secret note\u2019 given", "secret", "[text]"),
    # Review r1, item 1: names as stored, any capitals, any way of writing an accent.
    ("a name with \u00df", "Stra\u00dfe M\u00fcller is locked out", "Stra\u00dfe", "[name]"),
    ("a name with \u00df in capitals", "STRASSE M\u00dcLLER is locked out", "STRASSE", "[name]"),
    ("a name with \u0130", "\u0130pek Y\u0131lmaz is locked out", "\u0130pek", "[name]"),
    ("a name with \u0131", "\u0130pek Y\u0131lmaz is locked out", "Y\u0131lmaz", "[name]"),
    ("a name with \u0130 in small letters", "ipek yilmaz is locked out", "ipek", "[name]"),
    (
        "a name with a combining accent",
        "Sign-in for " + unicodedata.normalize("NFD", "Jos\u00e9") + " failed",
        "Jos",
        "[name]",
    ),
    ("a name in capitals", "Sign-in for JOS\u00c9 \u00d8RSTED failed", "\u00d8RSTED", "[name]"),
    # Item 2: every word of a person's name, at any boundary that isn't a letter.
    ("a short first name with 's", "Amy's phone gave up", "Amy", "[name]"),
    ("a short first name", "Raj is locked out", "Raj", "[name]"),
    ("half of a hyphened name", "Marie is locked out", "Marie", "[name]"),
    ("a name with an s", "The Tesss phone gave up", "Tess", "[name]"),
    ("a name before an underscore", "Couldn't write tess_backup.db", "tess", "[name]"),
    ("a name after an underscore", "No row for user_tess", "tess", "[name]"),
    ("a name before a digit", "No row for tess2", "tess", "[name]"),
    ("two names run together", "No row for TessMarsh", "Marsh", "[name]"),
    ("a removed person's name", "Vance renamed it", "Vance", "[name]"),
    ("a person-like word in a recipe's name", "Mabel said no", "Mabel", "[name]"),
    # Item 4: addresses.
    ("an IPv4 address ending a sentence", "Refused 192.168.1.23.", "192.168", "[address]"),
    ("an IPv6 address of digits", "From 2001:470:1:2:3:4:5:6 refused", "2001:470", "[address]"),
    ("four groups of digits", "Prefix 2001:470:1234:5678 refused", "2001:470", "[address]"),
    # Item 6.
    (
        "a link without a scheme",
        "Fetch from recipes.example.org/grannys-secret-pie?who=ayla timed out",
        "grannys",
        "[link]",
    ),
    ("a host name under .arpa", "Proxy at caddy.home.arpa didn't answer", "caddy", "[link]"),
    ("a host name under .local", "Seen from ashas-macbook.local", "ashas-macbook", "[link]"),
    ("a path in a home folder", "Can't open /home/ayla/mealwright/backup.db", "ayla", "[file]"),
    ("a Windows path", "Can't open C:\\Users\\Ayla\\mealwright\\x.db", "Ayla", "[file]"),
    ("a data path with a space", "Can't read /data/photos/Ayla Roe/x.jpg now", "Roe", "[file]"),
    ("a password", "login failed password=hunter2secret", "hunter2", "[secret]"),
    ("a cookie", "Cookie mw_session=AbCdEf0123456789AbCdEf0123456789 rejected", "AbCdEf", None),
    ("a long hex run", "Session " + "9f86d081884c7d65" * 4 + " expired", "9f86d081", "[secret]"),
    (
        "a JWT",
        "Bad token eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJhc2hhIn0.c2lnbmF0dXJl",
        "eyJhbGci",
        "[secret]",
    ),
    ("a base64 run", "Bad key AbCdEf0123456789AbCdEf01 seen", "AbCdEf01", "[secret]"),
    ("a user at a host", "Mail to ayla@nas bounced", "ayla", "[e-mail]"),
    ("any port=", "bind failed port=9999", "9999", "[port]"),
    (
        "quoted text with an apostrophe",
        "Couldn't save 'Auntie Shanti's biryani' now",
        "Shanti",
        "[text]",
    ),
    (
        "curly quotes with an apostrophe",
        "Save \u2018Auntie Shanti\u2019s pie\u2019 now",
        "Shanti",
        None,
    ),
    ("low-high quotes", "Save \u201eAuntie Shanti biryani\u201c now", "Shanti", "[text]"),
    ("guillemets", "Save \u00abAuntie Shanti biryani\u00bb now", "Shanti", "[text]"),
    # Review r2, M1: a word is its letters with their vowel signs and joiners.
    ("a Tamil name", f"Sign-in for {TAMIL} failed", TAMIL.split()[0], "[name]"),
    ("a Tamil family name", f"Sign-in for {TAMIL} failed", TAMIL.split()[1], "[name]"),
    ("a Tamil name alone", f"Sign-in for {TAMIL.split()[0]} failed", TAMIL.split()[0], "[name]"),
    ("a Hindi name", f"Sign-in for {HINDI.split()[0]} failed", HINDI.split()[0], "[name]"),
    ("a Hindi family name", f"{HINDI.split()[1]} is locked out", HINDI.split()[1], "[name]"),
    ("a Bengali name", f"Sign-in for {BENGALI} failed", BENGALI.split()[0], "[name]"),
    ("a Bengali family name", f"{BENGALI.split()[1]} again", BENGALI.split()[1][:2], "[name]"),
    # M2: numbers between the words of a name don't keep it.
    ("a list with a year", "List Diwali 2025 party refused", "Diwali", "[removed]"),
    ("a list with a date", "List Week 2026-11-09 shop refused", "Week", "[removed]"),
    (
        "a recipe with a year",
        "Couldn't save Christmas 2025 surprise for Granddad now",
        "Granddad",
        "[recipe]",
    ),
    ("a recipe with 1,000", "Ayla birthday cake 1,000 layers failed", "birthday", "[recipe]"),
    (
        "a description with 1 1/2",
        "Bake at 180 degrees for 1 1/2 hours then hide it from Ayla",
        "Ayla",
        "[recipe]",
    ),
    # M5: a word in brackets.
    ("a username in brackets", "No user [tess] in names=[Marsh]", "tess", "[name]"),
    ("a name in brackets", "No user [tess] in names=[Marsh]", "Marsh", "[name]"),
    # M6: a long quote, and a quote that is never closed.
    (
        "a long quoted note",
        "Bad note 'call Ayla on 07700 900123 before " + "the party " * 30 + "starts' given",
        "07700",
        "[text]",
    ),
    ("an unclosed quote", "Couldn't save 'Auntie Shanti biryani", "Shanti", "[text]"),
    ("an unclosed double quote", "Couldn't save \"Auntie Shanti biryani", "Shanti", "[text]"),
    # L8: secrets after a colon, and keys with "api" before them.
    ("a password after a colon", "login failed password: hunter2secret", "hunter2", "[secret]"),
    ("an apikey", "Bad apikey=abc123XYZ given", "abc123", "[secret]"),
    ("an api_key after a colon", "Bad api_key: abc123XYZ given", "abc123", "[secret]"),
    ("a token after a colon", "Refresh token: abc123XYZ expired", "abc123", "[secret]"),
    # Review r3, N1: "Basic"/"Bearer" after a colon is not the secret; what follows it is.
    ("basic after a colon", "Authorization: Basic dXNlcjpwYXNz sent", "dXNlcjpwYXNz", "[secret]"),
    ("bearer after a proxy colon", "Proxy-Authorization: Bearer abc123XYZ", "abc123", "[secret]"),
    ("bearer after token colon", "Refresh token: bearer abc123XYZ expired", "abc123", "[secret]"),
    ("bearer after auth=", "Bad auth=Bearer abc123XYZ given", "abc123", "[secret]"),
    # Review r4, 1: "Bearer"/"Basic" before a key name doesn't hide the key's value.
    ("bearer before token=", "Invalid bearer token=hunter2x", "hunter2x", "[secret]"),
    ("bearer before token colon", "Invalid bearer token: hunter2x", "hunter2x", "[secret]"),
    ("basic before auth colon", "Basic auth: hunter2x sent", "hunter2x", "[secret]"),
    ("basic before a quoted password", "Basic password='hunter2x'", "hunter2x", "[secret]"),
    ("basic before mw_session=", "basic mw_session=hunter2x", "hunter2x", "[secret]"),
    ("bearer before apikey=", "Bearer apikey=hunter2x", "hunter2x", "[secret]"),
]


@pytest.mark.parametrize(
    ("kind", "line", "secret", "becomes"), PLANTED, ids=[kind for kind, *_ in PLANTED]
)
def test_personal_details_are_removed(
    planted: TestClient,
    settings: Settings,
    kind: str,
    line: str,
    secret: str,
    becomes: str | None,
) -> None:
    write_log(log_folder(settings), [error(line)])
    errors = report(planted, host="mealwright.marsh.example:8443")["errors"]
    assert len(errors) == 1
    assert secret.lower() not in errors[0].lower(), kind
    if becomes is not None:
        assert becomes in errors[0], (kind, errors[0])


def test_a_file_in_this_servers_own_data_folder_is_removed(
    kitchen: TestClient, settings: Settings
) -> None:
    write_log(log_folder(settings), [error(f"Can't open {settings.data_dir}/backups/x.db")])
    line = report(kitchen)["errors"][0]
    assert str(settings.data_dir) not in line
    assert "backups" not in line
    assert "[file]" in line


def test_a_time_in_a_message_is_kept(kitchen: TestClient, settings: Settings) -> None:
    write_log(log_folder(settings), [error("Job late at 12:41:07 again")])
    assert "12:41:07" in report(kitchen)["errors"][0]


def test_a_long_message_is_cut(kitchen: TestClient, settings: Settings) -> None:
    write_log(log_folder(settings), [error("x" * 1000)])
    line = report(kitchen)["errors"][0]
    assert line.endswith("…")
    assert len(line) < problem_report.LINE_LIMIT + 60


# Review r1, item 2: recipe titles, ingredient names, descriptions, notes and line words are
# removed as whole phrases only, never word by word.
@pytest.mark.parametrize(
    "line",
    [
        "Couldn't tidy removed ingredients (will try again within the hour)",
        "Couldn't thin the history (will try again within the hour)",
        "Job late at 12:41:07 again",
        "sqlite3.OperationalError: database is locked",
        # Review r2, (a): "It's a Wrap", "Today's Special" and "Let's Eat" name no one.
        "Couldn't save it; today it failed; let it go",
    ],
)
def test_everyday_words_in_unrelated_lines_are_kept(
    planted: TestClient, settings: Settings, line: str
) -> None:
    write_log(log_folder(settings), [error(line)])
    assert report(planted)["errors"][0].endswith(f"mealwright.x: {line}")


def test_a_whole_recipe_title_is_removed_with_its_plural(
    planted: TestClient, settings: Settings
) -> None:
    write_log(log_folder(settings), [error("Out of Thuvaram paruppus; Granny Mabel's lasagnes")])
    line = report(planted)["errors"][0]
    assert "paruppu" not in line
    assert "lasagne" not in line
    assert line.endswith("Out of [ingredient]; [recipe]")


# --- Speed (review r1, item 5) --------------------------------------------------------------


class FakeDB:
    """Answers each column's select with the given values (by "Model.column")."""

    def __init__(self, values: dict[str, list[str]]) -> None:
        self.values = values

    def scalars(self, statement: object) -> list[str]:
        column = statement.column_descriptions[0]  # type: ignore[attr-defined]
        return self.values.get(f"{column['entity'].__name__}.{column['name']}", [])

    def get_bind(self) -> object:
        return self


NO_SERVER = ServerAddress(hosts=("mealwright.example",), ports=(8443,))


def words(n: int, seed: int) -> list[str]:
    syllables = ["ka", "ri", "mo", "ta", "pe", "lu", "sha", "nti", "bra", "dol", "mi", "ne"]
    out = []
    for i in range(n):
        x = i * 7919 + seed
        out.append(
            " ".join("".join(syllables[(x >> k) % 12] for k in range(j, j + 3)) for j in range(3))
        )
    return out


def test_a_hundred_thousand_names_are_quick() -> None:
    db = FakeDB(
        {
            "Recipe.name": words(40_000, 1),
            "RecipeLine.words": words(40_000, 2),
            "Login.name": words(20_000, 3),
        }
    )
    message = "Couldn't thin the history (will try again within the hour) for row 12345 " * 30
    started = time.perf_counter()
    scrub = Scrubber(db, NO_SERVER, Path("/data"))  # type: ignore[arg-type]
    at = datetime(2026, 11, 12, 12, 41, tzinfo=UTC)
    lines = [error_line(LogError(at, "mealwright.x", message, None), scrub) for _ in range(20)]
    took = time.perf_counter() - started
    assert len(lines) == 20
    assert took < 2.0, took


@pytest.mark.parametrize(
    "make",
    [
        lambda n: "a" * n,
        lambda n: "a." * (n // 2),
        lambda n: "a:" * (n // 2),
        lambda n: " '" * (n // 2),
        lambda n: "a@" * (n // 2),
        lambda n: "/a b" * (n // 4),
        lambda n: "x=" * (n // 2),
    ],
    ids=["letters", "dots", "colons", "quotes", "at signs", "paths", "equals"],
)
def test_an_80_kb_line_is_quick(make: object) -> None:
    scrub = Scrubber(FakeDB({"Login.name": ["Tess Marsh"]}), NO_SERVER, Path("/data"))  # type: ignore[arg-type]
    at = datetime(2026, 11, 12, 12, 41, tzinfo=UTC)
    text = make(80_000)  # type: ignore[operator]
    started = time.perf_counter()
    line = error_line(LogError(at, "mealwright.x", text, None), scrub)
    took = time.perf_counter() - started
    assert len(line) < problem_report.LINE_LIMIT + 60
    assert took < 2.0, took
    # Each scrubbing step is linear too, even on the whole line.
    started = time.perf_counter()
    scrub(text)
    assert time.perf_counter() - started < 2.0


def test_the_scrubber_is_kept_between_reports(
    planted: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    write_log(log_folder(settings), [error("Sign-in for tess failed")])
    built: list[object] = []
    real = Scrubber.__init__

    def counting(self: Scrubber, *args: object) -> None:
        built.append(self)
        real(self, *args)  # type: ignore[arg-type]

    monkeypatch.setattr(Scrubber, "__init__", counting)
    for _ in range(3):
        assert "[name]" in report(planted)["errors"][0]
    assert len(built) == 1
    # After SCRUBBER_KEPT it is built again, so new names are removed too.
    now = time.monotonic() + problem_report.SCRUBBER_KEPT + 1
    monkeypatch.setattr(problem_report, "_now", lambda: now)
    report(planted)
    assert len(built) == 2


def test_a_name_added_since_the_scrubber_was_built_is_removed(
    planted: TestClient, neighbour: TestClient, settings: Settings
) -> None:
    """Review r2, M3: the kept scrubber is built again once a name may have changed, in any
    household, even within SCRUBBER_KEPT."""
    folder = log_folder(settings)
    write_log(folder, [error("Sign-in for tess failed")])
    assert "[name]" in report(neighbour)["errors"][0]  # built and kept
    with planted.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(
            Login(
                household_id=1,
                username="zebedee",
                name="Zebedee Quux",
                password_hash=None,
                role="member",
            )
        )
        db.commit()
    assert planted.post(f"{API}/recipes", json={"name": "Zebedee surprise cake"}).status_code == 201
    write_log(folder, [error("Sign-in for zebedee failed; Zebedee Quux; Zebedee surprise cake")])
    line = report(neighbour)["errors"][-1]
    assert "zebedee" not in line.lower(), line
    assert "quux" not in line.lower(), line
    # A rename, written straight to the table.
    with planted.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(update(Login).where(Login.username == "rli").values(name="Raj Wobblesworth"))
        db.commit()
    write_log(folder, [error("Wobblesworth is locked out")])
    line = report(neighbour)["errors"][-1]
    assert "wobblesworth" not in line.lower(), line


def test_one_scrubber_is_built_whatever_the_host(
    planted: TestClient, settings: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review r2, M4: the request's host and port are applied to each report, not kept."""
    monkeypatch.setattr(problem_report, "_kept", {})
    write_log(log_folder(settings), [error("Bad Host kitchen-box-3 on port 1003 seen")])
    built: list[object] = []
    real = Scrubber.__init__

    def counting(self: Scrubber, *args: object) -> None:
        built.append(self)
        real(self, *args)  # type: ignore[arg-type]

    monkeypatch.setattr(Scrubber, "__init__", counting)
    for n in range(50):
        line = report(planted, host=f"kitchen-box-{n}:{1000 + n}")["errors"][0]
        if n == 3:
            assert "kitchen-box-3" not in line, line
            assert "[server]" in line, line
        else:
            assert "kitchen-box-3" in line, line
    assert len(built) == 1
    assert len(problem_report._kept) == 1


def test_a_message_cut_at_the_read_limit_keeps_no_half_word() -> None:
    """Review r2, L7: a message longer than MESSAGE_READ is cut back to its last space, so no
    part of a key, address or name is left at the end."""
    scrub = Scrubber(FakeDB({"Login.name": ["Tess Marsh"]}), NO_SERVER, Path("/data"))  # type: ignore[arg-type]
    at = datetime(2026, 11, 12, 12, 41, tzinfo=UTC)
    tail = "sid 9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822c x"
    for cut_in in range(1, len(tail)):
        size = problem_report.MESSAGE_READ - cut_in
        pad = "https://e.example/" + "a" * (size - 19) + " "  # one [link]
        line = error_line(LogError(at, "m.x", pad + tail, None), scrub)
        assert "9f86" not in line, (cut_in, line)


def test_a_name_committed_after_a_report_was_built_is_removed(
    planted: TestClient, neighbour: TestClient, settings: Settings
) -> None:
    """Review r3, N2: a report built between a name's write and its commit can't see the row,
    so the commit makes the next report build again."""
    folder = log_folder(settings)
    write_log(folder, [error("Sign-in for tess failed")])
    assert "[name]" in report(neighbour)["errors"][0]
    with planted.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(
            Login(
                household_id=1,
                username="xylophia",
                name="Xylophia Racewin",
                password_hash=None,
                role="member",
            )
        )
        db.flush()  # written, not yet committed
        report(neighbour)  # built now, without the new name
        db.commit()
    write_log(folder, [error("Sign-in for Xylophia Racewin failed")])
    line = report(neighbour)["errors"][-1]
    assert "racewin" not in line.lower(), line


def test_the_s_after_a_removed_name_does_not_open_a_quote(
    planted: TestClient, settings: Settings
) -> None:
    """Review r3, N3: "Vance's" becomes "[name]'s", and that apostrophe is not a quote."""
    write_log(
        log_folder(settings), [error("Tess: Vance's phone couldn't sync (OperationalError)")]
    )
    line = report(planted)["errors"][0]
    assert "phone couldn't sync" in line, line
    assert "vance" not in line.lower(), line


def test_a_report_built_while_a_name_commits_is_built_again(
    planted: TestClient, neighbour: TestClient, settings: Settings
) -> None:
    """Review r4, 3: SQLAlchemy's "commit" event fires before the database commits, so a report
    built in that gap can't see the new name; the next report must be built again."""
    folder = log_folder(settings)
    write_log(folder, [error("Sign-in for tess failed")])
    assert "[name]" in report(neighbour)["errors"][0]
    engine = planted.app.state.engine  # type: ignore[attr-defined]
    built: list[bool] = []

    def in_the_gap(connection: object) -> None:
        if not built:
            built.append(True)
            report(neighbour)  # the new name isn't committed yet

    event.listen(engine, "commit", in_the_gap)
    try:
        with planted.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            db.add(
                Login(
                    household_id=1,
                    username="quillon",
                    name="Quillon Brasswick",
                    password_hash=None,
                    role="member",
                )
            )
            db.commit()
    finally:
        event.remove(engine, "commit", in_the_gap)
    assert built
    write_log(folder, [error("Sign-in for Quillon Brasswick failed")])
    line = report(neighbour)["errors"][-1]
    assert "brasswick" not in line.lower(), line


def test_a_quote_straight_after_a_link_is_still_a_quote() -> None:
    """Review r4, 7: only "[name]'s" and "[name]'" are kept; a quote opening right after "]"
    (a link, a file, an index) is still removed."""
    scrub = Scrubber(FakeDB({"Login.name": ["Tess Marsh"]}), NO_SERVER, Path("/data"))  # type: ignore[arg-type]
    assert "Zelda" not in scrub('see https://e.example/x"Zelda Quimby" failed')
    assert "Zelda" not in scrub("bad tags[0]'Zelda Quimby' given")
    kept = scrub("Tess Marsh's list 'plans' failed")
    assert "[name]'s list " in kept, kept
    assert "plans" not in kept, kept


def test_a_person_without_a_login_is_removed_too(
    planted: TestClient, neighbour: TestClient, settings: Settings
) -> None:
    """People of the household (0.9 A1) are names too, with or without a login: a child added
    in Settings → Household never signs in, and must still not be named in a report. Added
    after the scrubber was built, so it is also built again for a new person."""
    folder = log_folder(settings)
    write_log(folder, [error("Sign-in for tess failed")])
    assert "[name]" in report(neighbour)["errors"][0]  # built and kept
    added = planted.post(f"{API}/people", json={"name": "Anoushka Quibbleton"})
    assert added.status_code == 201, added.text
    write_log(folder, [error("Couldn't save the portion for Anoushka Quibbleton (Anoushka)")])
    line = report(neighbour)["errors"][-1]
    assert "anoushka" not in line.lower(), line
    assert "quibbleton" not in line.lower(), line


def test_a_renamed_person_is_removed_by_the_old_name_and_the_new(
    kitchen: TestClient, neighbour: TestClient, settings: Settings
) -> None:
    """Review r1 (beta join): the old name stays in history (a change's login name, the undo
    data of "added" and "renamed"), so a renamed person, with a login or without, is removed
    by both names."""
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(
            update(Login).where(Login.household_id == 1).values(name="Ravindranath Pemberton")
        )
        db.execute(
            update(Member).where(Member.household_id == 1).values(name="Ravindranath Pemberton")
        )
        db.commit()
    child = kitchen.post(f"{API}/people", json={"name": "Anoushka Quibbleton"})
    assert child.status_code == 201, child.text
    people = {p["name"]: p["id"] for p in kitchen.get(f"{API}/people").json()["people"]}
    renames = {
        "Anoushka Quibbleton": "Zephyrine Wattlesworth",  # no login
        "Ravindranath Pemberton": "Octavian Fennimore",  # signs in
    }
    for old, new in renames.items():
        done = kitchen.patch(f"{API}/people/{people[old]}", json={"name": new})
        assert done.status_code == 200, done.text
    log = "Failed for " + " and ".join(f"{old} / {new}" for old, new in renames.items())
    write_log(log_folder(settings), [error(log)])
    line = report(neighbour)["errors"][-1].lower()
    for word in ("anoushka", "quibbleton", "zephyrine", "wattlesworth"):
        assert word not in line, line
    for word in ("ravindranath", "pemberton", "octavian", "fennimore"):
        assert word not in line, line


# Columns with "name" in them that are not a person's name, and what each is.
_NOT_A_PERSON: dict[str, str] = {
    "food_size.name": "a size word of an ingredient (tin, bunch)",
    "api_token.name": "the admin's label for an app (Home Assistant), never a person",
    "sso_settings.button_name": "the sign-in button's text (Authentik), the admin's own word",
}


def test_every_name_column_is_classified_for_reports() -> None:
    """A guard: a column with "name" in its name must be removed from reports as a person's
    name (the people columns), as a phrase, or be listed above as not a person's name. A new
    `*_by_name` or `login_name` column must be a person's."""
    from mealwright.models import Base

    people = {f"{c.table.name}.{c.name}" for c in problem_report._PEOPLE_COLUMNS}
    phrases = {
        f"{c.table.name}.{c.name}" for _, cols in problem_report._PHRASE_COLUMNS for c in cols
    }
    found = {
        f"{table.name}.{column.name}"
        for table in Base.metadata.tables.values()
        for column in table.columns
        if "name" in column.name
    }
    assert found - people - phrases - set(_NOT_A_PERSON) == set()
    for key in found:
        if key.endswith("_by_name") or key.endswith(".login_name"):
            assert key in people, key


def test_errors_from_before_delete_everything_are_not_in_the_report(
    kitchen: TestClient, settings: Settings
) -> None:
    """Review r1 (beta join): Delete everything starts a new install, so a line from the old
    one must not reach the new one's report; a line from after the new setup does."""
    from conftest import ADMIN

    folder = log_folder(settings)
    write_log(folder, [error("Old install broke", ago=timedelta(minutes=5))])
    assert any("Old install" in line for line in report(kitchen)["errors"])
    body = {"words": "delete everything", "password": ADMIN["password"]}
    assert kitchen.post(f"{API}/delete-everything", json=body).status_code == 204
    assert kitchen.post(f"{API}/setup", json=ADMIN).status_code == 201
    # Stamped 2 s after the set-up: a line in the set-up's own second is left out (review r2).
    write_log(folder, [error("New install broke", ago=timedelta(seconds=-2))])
    lines = report(kitchen)["errors"]
    assert not any("Old install" in line for line in lines), lines
    assert any("New install" in line for line in lines), lines


def test_a_households_old_name_is_removed_after_a_rename(
    kitchen: TestClient, neighbour: TestClient, settings: Settings
) -> None:
    """Review r2 (beta join), M: a rename keeps the old name in the undo data and the summary
    of its change (`household_renamed`); that name is still a household's, so it is removed
    from the own household's report and from the neighbour's."""
    done = kitchen.patch(f"{API}/household", json={"name": "Thistlewick Burrow"})
    assert done.status_code == 200, done.text
    write_log(log_folder(settings), [error("Sign-in for tess failed")])
    assert "[name]" in report(neighbour)["errors"][0]  # built and kept, with the first name
    done = kitchen.patch(f"{API}/household", json={"name": "Home"})
    assert done.status_code == 200, done.text
    write_log(log_folder(settings), [error("Couldn't save for Thistlewick Burrow")])
    for client in (kitchen, neighbour):
        line = report(client)["errors"][-1].lower()
        assert "thistlewick" not in line, line
        assert "burrow" not in line, line


def test_every_undo_name_is_handled() -> None:
    """A guard (review r2, sweep): every kind of change that keeps a name in its undo data is
    found by `undo_names`. The shapes below are what the code writes today (each from the
    function named); a new kind with a "name" key must be added here and handled there."""
    shapes = {
        "household_renamed (kitchen_changes)": ({"name": {"old": "Aaa", "new": "Bbb"}}, 2),
        "person_added / person_changed (people)": (
            {"person": {"old": {"name": "Aaa"}, "new": {"name": "Bbb"}}},
            2,
        ),
        "tag merge (recipe_tags)": (
            {"source": {"id": 1, "name": "Aaa"}, "target": {"id": 2, "name": "Bbb"}},
            2,
        ),
        "shop_removed / place_removed (removals)": ({"removed": {"id": 1, "name": "Aaa"}}, 1),
        "shop_renamed / place_renamed (api/v1/kitchen, kitchen_changes)": (
            {"shop": {"id": 1, "old": "Aaa", "new": "Bbb"}},
            2,
        ),
        "plan changes (plan): a removed free-text item": (
            {"plan": [{"op": "remove_item", "item": {"id": 1, "name": "Aaa"}}]},
            1,
        ),
        "list_renamed (shopping)": (
            {"shopping": [{"op": "list_name", "list_id": 1, "old": "Aaa", "new": "Bbb"}]},
            2,
        ),
        "food changes (history)": (
            {
                "fields": {"1:name": "Aaa", "1:aisle": "Bbb"},
                "names": {"7": {"food_id": 1, "name": "Ccc"}},
                "sizes": {"3": {"name": "tin"}},
                "conversions": {"1:cup": {"answered_by_name": "Ddd"}},
            },
            3,
        ),
        "draft removed (drafts)": ({"draft": {"name": "Aaa", "started_by_name": "Bbb"}}, 2),
    }
    for kind, (data, count) in shapes.items():
        found = list(problem_report.undo_names(data))
        assert len(found) == count, (kind, found)


# The modules that write a Change (`record(` / `Change(`), each checked for names in its undo
# data in review r2 (every kind listed above comes from one of them). A new module that
# records changes must be checked the same way and added here.
_RECORDS_CHANGES = {
    "api/v1/changes.py", "api/v1/drafts.py", "api/v1/foods.py", "api/v1/kitchen.py",
    "api/v1/pantry.py", "api/v1/starter_packs.py", "api/v1/stocktake.py", "cooking.py",
    "drafts.py", "foods.py", "history.py", "kitchen_changes.py", "people.py", "plan.py",
    "recipe_import.py", "recipe_tags.py", "recipes.py", "removals.py", "shopping.py",
    "stock.py", "ticks.py",
}  # fmt: skip


def test_every_module_that_records_changes_has_been_checked_for_names() -> None:
    import re

    root = Path(problem_report.__file__).parent
    found = {
        str(path.relative_to(root))
        for path in root.rglob("*.py")
        if re.search(r"(?<![\w.])(?:edit\.|self\.)?record\(|\bChange\(", path.read_text())
    }
    found.discard("models.py")
    assert found - _RECORDS_CHANGES == set(), found - _RECORDS_CHANGES


@pytest.mark.parametrize(
    "column", ["Change.login_name", "ListTick.login_name", "SyncAction.login_name"]
)
def test_a_name_kept_only_by_a_change_tick_or_queued_action_is_removed(column: str) -> None:
    """Review r2, L: the name a person had when they did a change, a tick or a queued action
    (kept after a rename) may sit nowhere else; each of the three columns is pinned on its
    own, with that name in no other column."""
    scrub = Scrubber(FakeDB({column: ["Quentin Thorne"]}), NO_SERVER, Path("/data"))  # type: ignore[arg-type]
    line = scrub("Couldn't save for Quentin Thorne (Quentin)")
    assert "quentin" not in line.lower(), line
    assert "thorne" not in line.lower(), line


def test_a_line_in_the_same_second_as_the_new_set_up_is_left_out(tmp_path: Path) -> None:
    """Review r2, L: log times are whole seconds, so a set-up at 12:00:00.4 rounds UP to
    12:00:01: a line stamped 12:00:00 was written before it (the old install's), and a line
    at 12:00:01 is the new one's."""
    now = datetime.now(UTC)  # the file's own time must be inside the window too
    set_up = (now - timedelta(minutes=10)).replace(microsecond=400_000)
    write_log(
        tmp_path,
        [
            f"{stamp(set_up)} ERROR mealwright.old: Written before the set-up",
            f"{stamp(set_up + timedelta(seconds=1))} ERROR mealwright.new: After it",
        ],
    )
    found = recent_errors(tmp_path, now, installed=set_up)
    assert [error.message for error in found] == ["After it"]


# --- Every change that renames or removes something with a name (fix4, review r3) ------------
#
# Each scenario writes the real rows through the API, renames, removes, merges or purges, and
# returns the OLD names. The test then logs an error that holds them and builds the report for
# the household and for a neighbour: none may be there.


def _ok(response: Any, *codes: int) -> Any:
    assert response.status_code in (codes or (200, 201, 204)), response.text
    return response.json() if response.content else None


def _purge_all(client: TestClient) -> None:
    """Everything that was removed, purged for good (the nightly job, run a month on)."""
    from mealwright.jobs import purge_removed_ingredients

    purge_removed_ingredients(
        client.app.state.sessionmaker,  # type: ignore[attr-defined]
        datetime.now(UTC) + timedelta(days=60),
    )


def _person(k: TestClient, name: str) -> int:
    made = _ok(k.post(f"{API}/people", json={"name": name}))
    return int(next(p["id"] for p in made["people"] if p["name"] == name))


def _s_person_renamed(k: TestClient) -> list[str]:
    _ok(k.patch(f"{API}/people/{_person(k, 'Anoushka Quibbleton')}", json={"name": "Joss"}))
    return ["Anoushka Quibbleton"]


def _s_person_removed(k: TestClient) -> list[str]:
    _ok(k.delete(f"{API}/people/{_person(k, 'Zebediah Fairweather')}"))
    return ["Zebediah Fairweather"]


def _s_household_renamed(k: TestClient) -> list[str]:
    _ok(k.patch(f"{API}/household", json={"name": "Thistlewick Burrow"}))
    _ok(k.patch(f"{API}/household", json={"name": "Home"}))
    return ["Thistlewick Burrow"]


def _s_food_renamed(k: TestClient) -> list[str]:
    food = _ok(k.post(f"{API}/foods", json={"name": "Aunty Priyamvada chutney"}))["food"]
    _ok(k.patch(f"{API}/foods/{food['id']}", json={"name": "Chutney"}))
    return ["Aunty Priyamvada chutney"]


def _s_food_merged(k: TestClient) -> list[str]:
    a = _ok(k.post(f"{API}/foods", json={"name": "Ottolenghi tahini"}))["food"]
    b = _ok(k.post(f"{API}/foods", json={"name": "Tahini"}))["food"]
    _ok(k.post(f"{API}/foods/{a['id']}/merge", json={"into_id": b["id"]}))
    _purge_all(k)
    return ["Ottolenghi tahini"]


def _s_food_removed_and_purged(k: TestClient) -> list[str]:
    food = _ok(k.post(f"{API}/foods", json={"name": "Gooseberry fool powder"}))["food"]
    _ok(k.delete(f"{API}/foods/{food['id']}"))
    _purge_all(k)
    return ["Gooseberry fool powder"]


def _s_recipe_deleted_and_purged(k: TestClient) -> list[str]:
    made = _ok(k.post(f"{API}/recipes", json={"name": "Hortensia's rhubarb crumble"}))
    _ok(k.delete(f"{API}/recipes/{made['id']}"))
    _purge_all(k)
    return ["Hortensia's rhubarb crumble"]


def _s_slot_renamed(k: TestClient) -> list[str]:
    slots = _ok(k.get(f"{API}/meal-slots"))
    first = (slots if isinstance(slots, list) else slots["slots"])[0]["id"]
    _ok(k.patch(f"{API}/meal-slots/{first}", json={"name": "Ravindra tiffin box"}))
    _ok(k.patch(f"{API}/meal-slots/{first}", json={"name": "Brekkie"}))
    return ["Ravindra tiffin box"]


def _s_list_renamed(k: TestClient) -> list[str]:
    made = _ok(k.post(f"{API}/shopping/lists", json={"name": "Wilhelmina's feast"}))
    _ok(k.patch(f"{API}/shopping/lists/{made['shopping_list']['id']}", json={"name": "Weekly"}))
    return ["Wilhelmina's feast"]


def _s_list_removed(k: TestClient) -> list[str]:
    made = _ok(k.post(f"{API}/shopping/lists", json={"name": "Bartholomew banquet"}))
    _ok(k.delete(f"{API}/shopping/lists/{made['shopping_list']['id']}"))
    return ["Bartholomew banquet"]


def _s_shop_renamed(k: TestClient) -> list[str]:
    made = _ok(k.post(f"{API}/shops", json={"name": "Mrs Pemberley's emporium"}))
    _ok(k.patch(f"{API}/shops/{made['id']}", json={"name": "Corner shop"}))
    return ["Mrs Pemberley's emporium"]


def _s_shop_removed(k: TestClient) -> list[str]:
    made = _ok(k.post(f"{API}/shops", json={"name": "Ignatius greengrocer"}))
    _ok(k.delete(f"{API}/shops/{made['id']}"))
    return ["Ignatius greengrocer"]


def _s_place_renamed(k: TestClient) -> list[str]:
    made = _ok(k.post(f"{API}/places", json={"name": "Cornelius cellar", "kind": "cupboard"}))
    _ok(k.patch(f"{API}/places/{made['id']}", json={"name": "Cellar"}))
    return ["Cornelius cellar"]


def _s_place_removed(k: TestClient) -> list[str]:
    made = _ok(k.post(f"{API}/places", json={"name": "Fenella larder", "kind": "cupboard"}))
    _ok(k.delete(f"{API}/places/{made['id']}"))
    return ["Fenella larder"]


def _s_tag_merged(k: TestClient) -> list[str]:
    _ok(k.post(f"{API}/recipes", json={"name": "Plain one", "tags": ["Gwendolyn favourites"]}))
    _ok(k.post(f"{API}/recipes", json={"name": "Plain two", "tags": ["Keepers"]}))
    tags = {t["name"]: t["id"] for t in _ok(k.get(f"{API}/recipes/tags"))["tags"]}
    _ok(
        k.post(
            f"{API}/recipes/tags/{tags['Gwendolyn favourites']}/merge",
            json={"into": tags["Keepers"]},
        )
    )
    return ["Gwendolyn favourites"]


def _s_plan_note_removed(k: TestClient) -> list[str]:
    from datetime import date

    slots = _ok(k.get(f"{API}/meal-slots"))
    slot = (slots if isinstance(slots, list) else slots["slots"])[0]["id"]
    day = (date.today() + timedelta(days=3)).isoformat()
    made = _ok(
        k.post(
            f"{API}/plan/items",
            json={"date": day, "slot_id": slot, "note": "Dinner at Wilkinson's"},
        )
    )
    plan = _ok(k.get(f"{API}/plan", params={"from": day, "to": day}))
    item = plan["meals"][0]["items"][0]["id"]
    _ok(k.delete(f"{API}/plan/items/{item}"))
    assert made
    return ["Dinner at Wilkinson's"]


# Change kind -> the scenario that writes a real row of it and then makes its name old.
_SCENARIOS: dict[str, Any] = {
    "person_added": _s_person_renamed,
    "person_changed": _s_person_renamed,
    "person_removed": _s_person_removed,
    "household_renamed": _s_household_renamed,
    "food_created": _s_food_removed_and_purged,
    "food_edited": _s_food_renamed,
    "food_removed": _s_food_removed_and_purged,
    "merged": _s_food_merged,
    "recipe_created": _s_recipe_deleted_and_purged,
    "recipe_removed": _s_recipe_deleted_and_purged,
    "plan_slot": _s_slot_renamed,
    "plan_removed": _s_plan_note_removed,
    "list_made": _s_list_removed,
    "list_renamed": _s_list_renamed,
    "list_removed": _s_list_removed,
    "shop_added": _s_shop_removed,
    "shop_renamed": _s_shop_renamed,
    "shop_removed": _s_shop_removed,
    "place_added": _s_place_removed,
    "place_renamed": _s_place_renamed,
    "place_removed": _s_place_removed,
    "tags_merged": _s_tag_merged,
    # in tests/test_drafts.py::test_a_deleted_and_purged_drafts_name_is_not_in_a_report
    "draft_saved": "test_drafts",
    "draft_removed": "test_drafts",
}
# Kinds that keep no name, and why. The names of ingredients are kept in the snapshots of
# the changes that made, renamed, merged or removed them (the kinds above); the others name
# an ingredient or a plan item only by ID.
_KEEPS_NO_NAME: dict[str, str] = {
    "amounts_shown_changed": "a setting: two words from a fixed list",
    "batch_cook_switch": "a setting: on or off",
    "cook_step_changed": "a setting: on or off",
    "kitchen_changed": "numbers of hob rings and cookers, and whether there is an oven",
    "pints_changed": "a setting: uk or us",
    "setting_kept": "keeps only the request's key",
    "whos_this_switch": "a setting: on or off",
    "undo": "its message and summary repeat the undone change's, whose own data holds the name",
    "split": "an ingredient made its own again: its name is in the snapshot of its other changes",
    "stocktake": "names an ingredient by ID; its name is in its own created change",
    "food_back": "names an ingredient by ID",
    "used": "names an ingredient by ID",
    "added": "names an ingredient by ID",
    "binned": "names an ingredient by ID",
    "set_left": "names an ingredient by ID",
    "use_by": "names an ingredient by ID",
    "to_freezer": "names an ingredient by ID",
    "moved": "names an ingredient by ID",
    "found": "names an ingredient by ID",
    "shopped": "names an ingredient by ID",
    "repacked": "names an ingredient by ID",
    "cooked": "names recipes by ID; their names are in the recipe's own changes",
    "item_added": "a list line, by ID and ingredient ID",
    "item_amount": "a list line, by ID",
    "item_deleted": "a list line, by ID",
    "item_moved": "a list line, by ID",
    "item_place": "a list line, by ID",
    "recipe_saved": "its name is in recipe_created's data: the same code writes both",
    "recipe_imported": "the recipe's name and its sections' names are kept under name and"
    " section_names (undo_names reads every string), checked in the shape test",
    "plan_added": "an item by ID",
    "plan_batch": "a batch by ID; its recipe_name is read by undo_names",
    "plan_batch_removed": "recipe_name is read by undo_names (shape test)",
    "plan_batch_session": "recipes by ID",
    "plan_batch_session_changed": "recipe_name is read by undo_names (shape test)",
    "plan_batch_session_removed": "recipe_name is read by undo_names (shape test)",
    "plan_cooked": "meals by ID",
    "plan_copied": "days by date",
    "plan_didnt": "meals by ID",
    "plan_eaters": "people by ID",
    "plan_leftovers": "meals by ID",
    "plan_method": "a method by ID",
    "plan_moved": "meals by ID and dates",
    "plan_moveit": "meals by ID and dates",
    "plan_optional": "an item by ID",
    "plan_servings": "an item by ID and a number",
    "plan_start": "an item by ID and a time",
    "plan_started": "an item by ID and a time",
    "plan_tub": "a tub by ID",
}


@pytest.mark.parametrize(
    "scenario",
    sorted({f for f in _SCENARIOS.values() if callable(f)}, key=lambda f: f.__name__),
)
def test_no_old_name_reaches_a_report(
    scenario: Any, kitchen: TestClient, neighbour: TestClient, settings: Settings
) -> None:
    """Review r3 (fix4): a name that was changed, removed, merged or purged is still a name.
    For each real change, the old names are logged in an error and must not be in the report
    of the household or of a neighbour."""
    write_log(log_folder(settings), [error("Sign-in for tess failed")])
    assert "[name]" in report(neighbour)["errors"][0]  # a Scrubber was built and kept first
    olds = scenario(kitchen)
    write_log(
        log_folder(settings),
        [error(f"Couldn't save {old}", ago=timedelta(seconds=-2)) for old in olds],
    )
    for client in (kitchen, neighbour):
        text = "\n".join(report(client)["errors"]).lower()
        for old in olds:
            for word in re.findall(r"[a-z]{4,}", old.lower()):
                assert word not in text.replace("couldn't save", ""), (scenario.__name__, text)


def test_every_kind_of_change_is_covered() -> None:
    """A guard: every kind of change the code writes is either run through the API above (or
    in test_drafts.py) with its old names logged and checked, or listed as keeping no name,
    with the reason. The kinds are read from the code (a kind written as a string where a
    change is recorded); the places that pass a kind in a variable are counted, so a new one
    fails here and is looked at."""
    import ast

    root = Path(problem_report.__file__).parent
    static: set[str] = set()
    dynamic: set[str] = set()
    for path in root.rglob("*.py"):
        if "migrations" in path.parts:
            continue
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", "")
            if name in ("record", "record_back", "done", "_finish") and node.args:
                is_edit = isinstance(func, ast.Attribute) and name in ("record", "done")
                where = 0 if is_edit or name in ("done", "_finish") else 1
                if name == "_finish":
                    where = 1
                if len(node.args) <= where:
                    continue
                arg = node.args[where]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    static.add(arg.value)
                else:
                    dynamic.add(f"{path.relative_to(root)}:{name}")
    known = set(_SCENARIOS) | set(_KEEPS_NO_NAME)
    assert static - known == set(), static - known
    assert set(_SCENARIOS) & set(_KEEPS_NO_NAME) == set()
    # Where a kind is passed in a variable (the kinds are among those above, found by
    # running the suite): a new such place must be looked at.
    assert dynamic == _DYNAMIC_KINDS, dynamic ^ _DYNAMIC_KINDS
    for kind, reason in _KEEPS_NO_NAME.items():
        assert reason, kind


# The places that pass the kind on in a variable or by another position (their kinds are among
# those in the two tables above; checked by running the suite and listing the kinds it wrote).
_DYNAMIC_KINDS: set[str] = {
    "api/v1/changes.py:record_back",
    "api/v1/pantry.py:record",
    "api/v1/people.py:_finish",
    "batches.py:_finish",
    "history.py:record",
    "kitchen_changes.py:record",
    "people.py:record",
    "plan.py:_finish",
    "plan.py:record",
    "recipe_tags.py:record",
    "recipes.py:record",
    "shopping.py:record",
    "shopping.py:record_back",
    "stock.py:record",
    "ticks.py:record",
}


def test_an_old_household_name_is_removed_as_a_whole_not_word_by_word(
    kitchen: TestClient, neighbour: TestClient, settings: Settings
) -> None:
    """Review r3 (fix4), L: a household once called "Our Kitchen" is removed as that phrase
    ([household]); "Kitchen" alone, as in "Kitchen timer failed", stays. A one-word old name
    is still a word."""
    _ok(kitchen.patch(f"{API}/household", json={"name": "Our Kitchen"}))
    _ok(kitchen.patch(f"{API}/household", json={"name": "Burrow"}))
    _ok(kitchen.patch(f"{API}/household", json={"name": "Home"}))
    write_log(
        log_folder(settings),
        [
            error("Kitchen timer failed", ago=timedelta(seconds=-2)),
            error("Couldn't save Our Kitchen", ago=timedelta(seconds=-2)),
            error("Couldn't save Burrow", ago=timedelta(seconds=-2)),
        ],
    )
    for client in (kitchen, neighbour):
        lines = report(client)["errors"]
        text = "\n".join(lines)
        assert "Kitchen timer failed" in text, lines
        assert "Couldn't save [household]" in text, lines
        assert "burrow" not in text.lower(), lines
