"""Settings → About → Report a problem (spec section 7, "Bug reports", cabledrawer 17 Oct; plan row X2).

The server builds the report with personal details already removed and never sends it anywhere.
Each kind of personal detail is planted in the log and must not come back.
"""

import os
import time
import unicodedata
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update

from mealwright import __version__, problem_report
from mealwright.auth import hash_password
from mealwright.config import Settings
from mealwright.logs import FILE_NAME
from mealwright.models import FoodName, Household, ImportDraft, Login, OwnNetworkEntry, Recipe
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
