"""The real-recipe check script (backend/scripts/import_check.py, a dev-only tool).

Everything here uses made-up pages (tests/import_pages/) and a fake fetcher or a fake network.
Nothing goes online, and no real address appears.
"""

import importlib.util
import json
import socket
import subprocess
import sys
import threading
from collections.abc import Callable
from pathlib import Path
from types import ModuleType

import pytest

from mealwright import outbound, page_budget, page_reader
from mealwright.outbound import USER_AGENT, Connection
from mealwright.page_fetch import FetchedPage, FetchRefused, Problem

BACKEND = Path(__file__).parent.parent
PAGES = Path(__file__).parent / "import_pages"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location(
        "import_check", BACKEND / "scripts" / "import_check.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["import_check"] = module  # dataclasses look their own module up here
    spec.loader.exec_module(module)
    return module


check = _load()


def page(name: str) -> FetchedPage:
    return FetchedPage(url="https://site.example/recipe", html=(PAGES / name).read_text("utf-8"))


def recipe_page(ingredients: list[str], title: str = "A made-up dish") -> FetchedPage:
    data = {
        "@context": "https://schema.org",
        "@type": "Recipe",
        "name": title,
        "image": "https://site.example/secret-photo-name.jpg",
        "recipeIngredient": ingredients,
        "recipeInstructions": [{"@type": "HowToStep", "text": "Mix it well."}],
    }
    html = (
        f'<html><body><script type="application/ld+json">{json.dumps(data)}</script></body></html>'
    )
    return FetchedPage(url="https://site.example/x", html=html)


def entry(number: int = 1, address: str = "https://a.example/one", group: str = "Site A") -> object:
    return check.Entry(number, group, address, "a note")


def fetcher(pages: dict[str, FetchedPage | Exception]) -> Callable[[str], FetchedPage]:
    def fetch(address: str) -> FetchedPage:
        answer = pages[address]
        if isinstance(answer, BaseException):
            raise answer
        return answer

    return fetch


# --- The list ------------------------------------------------------------------------------------


LIST = """# Title of the list

> A note about the list.

## Site A
- https://a.example/one — tomato soup
- https://a.example/two — dal

## Site B
- https://b.example/one
- not an address — oops
this line is odd
- ftp://b.example/file — wrong kind of address
"""


def test_the_list_gives_groups_and_recipes_and_counts_odd_lines() -> None:
    parsed = check.parse_list(LIST)
    assert [(e.number, e.group, e.address, e.note) for e in parsed.entries] == [
        (1, "Site A", "https://a.example/one", "tomato soup"),
        (2, "Site A", "https://a.example/two", "dal"),
        (3, "Site B", "https://b.example/one", ""),
    ]
    # Blank lines, ">" lines and "# " lines are skipped quietly; the other three are counted.
    assert parsed.odd_lines == (11, 12, 13)


def test_a_recipe_before_any_heading_has_a_placeholder_group() -> None:
    parsed = check.parse_list("- https://a.example/one — x\n")
    assert parsed.entries[0].group == check.NO_GROUP


# --- One address, each kind of result ------------------------------------------------------------


def test_a_page_with_a_recipe_is_read() -> None:
    outcome = check.check_one(
        entry(), fetcher({"https://a.example/one": page("dotdash.html")}), page_reader.read_page
    )
    assert outcome.kind == check.READ
    assert outcome.title == "Slow Cooker Pulled Jackfruit"
    assert outcome.ingredients_read == 6
    assert outcome.ingredients_unread == 0
    assert outcome.steps == 4
    assert outcome.photo_named is True


def test_a_page_with_no_recipe_data() -> None:
    outcome = check.check_one(
        entry(), fetcher({"https://a.example/one": page("no_recipe.html")}), page_reader.read_page
    )
    assert outcome.kind == check.NO_RECIPE


@pytest.mark.parametrize(
    ("problem", "kind"),
    [
        (Problem.SITE_ERROR, check.REFUSED),
        (Problem.ALWAYS_BLOCKED, check.BLOCKED),
        (Problem.OWN_NETWORK, check.BLOCKED),
        (Problem.SWITCHED_OFF, check.BLOCKED),
        (Problem.CANT_REACH, check.COULDNT),
        (Problem.TIMEOUT, check.COULDNT),
        (Problem.NOT_A_PAGE, check.COULDNT),
        (Problem.TOO_MANY_REDIRECTS, check.COULDNT),
    ],
)
def test_a_refused_fetch_is_a_row_with_the_apps_problem(problem: Problem, kind: str) -> None:
    outcome = check.check_one(
        entry(), fetcher({"https://a.example/one": FetchRefused(problem)}), page_reader.read_page
    )
    assert (outcome.kind, outcome.problem) == (kind, str(problem))


def test_a_page_over_its_reading_budget_couldnt_be_read() -> None:
    def too_slow(_html: str, _url: str) -> None:
        raise page_budget.PageUnreadable("time")

    outcome = check.check_one(
        entry(), fetcher({"https://a.example/one": page("dotdash.html")}), too_slow
    )
    assert outcome.kind == check.COULDNT
    assert "cant_read" in outcome.problem


def test_an_unexpected_failure_is_a_row_naming_only_the_error_class() -> None:
    boom = RuntimeError("https://a.example/one fell over")
    outcome = check.check_one(
        entry(), fetcher({"https://a.example/one": boom}), page_reader.read_page
    )
    assert outcome.kind == check.COULDNT
    assert outcome.problem == "error: RuntimeError"
    assert "a.example" not in outcome.problem


def test_lines_the_reader_cant_read_and_number_words_it_doesnt_know() -> None:
    lines = ["2 tbsp", "2 onions", "1 pint milk", "quarter lemon", "two eggs", "salt"]
    outcome = check.check_one(
        entry(), fetcher({"https://a.example/one": recipe_page(lines)}), page_reader.read_page
    )
    assert outcome.kind == check.READ
    assert outcome.unread_lines == ("2 tbsp",)
    assert outcome.ingredients_read == 5
    assert outcome.unknown_words == ("2", "tbsp", "1", "pint", "quarter")


# --- The run: spacing, failures, Ctrl-C ----------------------------------------------------------


class FakeClock:
    """A clock that only moves when something sleeps or `tick` is called."""

    def __init__(self) -> None:
        self.now = 1000.0
        self.slept: list[float] = []

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)
        self.now += seconds


def entries_for(*addresses: str) -> list[object]:
    return [check.Entry(i, "G", a, "") for i, a in enumerate(addresses, start=1)]


def test_www_and_the_bare_host_are_the_same_site() -> None:
    assert check.site_of("https://www.Example.com/a") == check.site_of("https://example.com/b")
    assert check.site_of("https://www.example.com/a") == "example.com"
    assert check.site_of("https://wwwx.example.com/a") != check.site_of("https://example.com/a")
    fake = FakeClock()
    asked: list[tuple[str, float]] = []

    def fetch(address: str) -> FetchedPage:
        asked.append((address, fake.now))
        return page("dotdash.html")

    check.run_check(
        entries_for("https://www.example.com/1", "https://example.com/2"),
        fetch,
        page_reader.read_page,
        check.Spacer(fake.clock, fake.sleep),
    )
    assert fake.slept == [pytest.approx(5.0)]  # the second waited for the first


def test_one_request_every_five_seconds_per_site() -> None:
    fake = FakeClock()
    asked: list[tuple[str, float]] = []

    def fetch(address: str) -> FetchedPage:
        asked.append((address, fake.now))
        fake.now += 1.0  # each request takes a second
        return page("dotdash.html")

    addresses = [
        "https://a.example/1",
        "https://a.example/2",
        "https://b.example/1",  # another site: no waiting
        "https://A.example/3",  # the same site, any case
    ]
    run = check.run_check(
        entries_for(*addresses),
        fetch,
        page_reader.read_page,
        check.Spacer(fake.clock, fake.sleep),
    )
    assert len(run.outcomes) == 4
    times = dict(asked)
    # Five seconds after the first request ended (it took 1), not after it started.
    assert times["https://a.example/2"] - 1001.0 == pytest.approx(5.0)
    assert times["https://b.example/1"] == times["https://a.example/2"] + 1.0
    assert times["https://A.example/3"] - (times["https://a.example/2"] + 1.0) >= 5.0
    assert fake.slept == [pytest.approx(5.0), pytest.approx(4.0)]


def test_one_failure_never_stops_the_run() -> None:
    pages: dict[str, FetchedPage | Exception] = {
        "https://a.example/1": FetchRefused(Problem.SITE_ERROR),
        "https://b.example/1": RuntimeError("x"),
        "https://c.example/1": page("dotdash.html"),
    }
    run = check.run_check(entries_for(*pages), fetcher(pages), page_reader.read_page)
    assert [o.kind for o in run.outcomes] == [check.REFUSED, check.COULDNT, check.READ]
    assert run.interrupted is False


def test_ctrl_c_keeps_what_is_done_and_the_report_says_so() -> None:
    def fetch(address: str) -> FetchedPage:
        if address.endswith("/3"):
            raise KeyboardInterrupt
        return page("dotdash.html")

    parsed = check.parse_list(
        "## One\n- https://a.example/1\n- https://b.example/2\n## Two\n"
        "- https://c.example/3\n- https://d.example/4\n"
    )
    run = check.run_check(parsed.entries, fetch, page_reader.read_page)
    assert run.interrupted is True
    assert len(run.outcomes) == 2
    report = check.render_report(run, parsed, "24 Oct 2026")
    assert "Stopped early (Ctrl-C)" in report
    assert "2 of 4 addresses" in report
    assert "- **One:** 2 address(es): 2 read" in report
    assert "- **Two:** 2 address(es): 2 not reached" in report


# --- The report ----------------------------------------------------------------------------------


def test_the_report_has_the_table_group_counts_and_unread_lines() -> None:
    parsed = check.parse_list(
        "## Site A\n- https://a.example/1 — soup\n- https://a.example/2\n"
        "## Site B\n- https://b.example/1\n- https://b.example/2\nodd line\n"
    )
    pages: dict[str, FetchedPage | Exception] = {
        "https://a.example/1": recipe_page(["2 tbsp", "salt"]),
        "https://a.example/2": page("no_recipe.html"),
        "https://b.example/1": FetchRefused(Problem.SITE_ERROR),
        "https://b.example/2": FetchRefused(Problem.CANT_REACH),
    }
    run = check.run_check(
        parsed.entries,
        fetcher(pages),
        page_reader.read_page,
        check.Spacer(FakeClock().clock, FakeClock().sleep),
    )
    report = check.render_report(run, parsed, "24 Oct 2026")
    assert (
        "| 1 | Site A | read | yes: A made-up dish | 1 | 1 | 1 | yes | https://a.example/1 |"
        in report
    )
    assert "| 2 | Site A | no recipe data | - | - | - | - | - | https://a.example/2 |" in report
    assert "refused by the site (site_error)" in report
    assert "couldn't read (cant_reach)" in report
    assert "- **Site A:** 2 address(es): 1 read, 1 no recipe data" in report
    assert "- **Site B:** 2 address(es): 1 refused by the site, 1 couldn't read" in report
    assert "1 line(s) in the list were ignored" in report
    assert "line 7" in report
    assert "- not read: 2 tbsp" in report
    assert "Note in the list: soup" in report
    assert "what it read" in report  # says why that column is left out


def test_the_report_has_no_page_text_and_no_photo_address() -> None:
    long_title = "A very long made-up recipe title that goes on and on and on"
    fetched = recipe_page(["1 cup barbecue sauce"], title=long_title)
    entries = entries_for("https://a.example/1")
    run = check.run_check(
        entries,
        fetcher({"https://a.example/1": fetched}),
        page_reader.read_page,
    )
    report = check.render_report(run, check.ParsedList(tuple(entries), ()), "24 Oct 2026")
    assert "secret-photo-name" not in report
    assert "site.example" not in report
    assert "Mix it well" not in report
    assert long_title[:40] in report
    assert long_title[:41] not in report

    run = check.run_check(
        entries,
        fetcher({"https://a.example/1": page("dotdash.html")}),
        page_reader.read_page,
    )
    report = check.render_report(run, check.ParsedList(tuple(entries), ()), "24 Oct 2026")
    for text in ("jackfruit.jpg", "everydaydish.example", "Young jackfruit cooked", "slow cooker"):
        assert text not in report


def test_odd_cells_cant_break_the_table() -> None:
    fetched = recipe_page(["salt"], title="Salt | pepper\nand more")
    entries = entries_for("https://a.example/1")
    run = check.run_check(entries, fetcher({"https://a.example/1": fetched}), page_reader.read_page)
    report = check.render_report(run, check.ParsedList(tuple(entries), ()), "x")
    assert "yes: Salt \\| pepper and more" in report


# --- The real fetcher, on a fake network ---------------------------------------------------------


def test_the_real_fetcher_uses_the_gate_with_only_the_import_switch_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    seen: list[dict[str, str]] = []
    connections: list[tuple[str, int]] = []
    body = (PAGES / "dotdash.html").read_bytes()

    def lookup(host: str, port: int) -> list[str]:
        assert host == "dishes.example"
        return ["93.184.216.34"]

    def open_socket(address: str, port: int, timeout: float | None) -> socket.socket:
        connections.append((address, port))
        client, server = socket.socketpair()

        def serve() -> None:
            with server:
                data = b""
                while b"\r\n\r\n" not in data:
                    data += server.recv(65536)
                lines = data.decode("latin-1").split("\r\n\r\n")[0].split("\r\n")
                seen.append({k.lower(): v for k, v in (h.split(": ", 1) for h in lines[1:])})
                head = (
                    "HTTP/1.1 200 OK\r\nContent-Type: text/html; charset=utf-8\r\n"
                    f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n"
                )
                server.sendall(head.encode() + body)

        threading.Thread(target=serve, daemon=True).start()
        client.settimeout(timeout)
        return client

    monkeypatch.setattr(outbound, "_lookup", lookup)
    monkeypatch.setattr(outbound, "_open_socket", open_socket)

    with check.real_fetcher() as fetch:
        fetched = fetch("http://dishes.example/recipe")
    assert fetched.url == "http://dishes.example/recipe"
    assert connections == [("93.184.216.34", 80)]
    assert seen[0]["user-agent"] == USER_AGENT
    assert "cookie" not in seen[0]


def test_only_recipe_import_is_switched_on_in_the_throwaway_database(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    gates: list[outbound.OutboundGate] = []

    class Spy(outbound.OutboundGate):
        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, **kwargs)  # type: ignore[arg-type]
            gates.append(self)

    monkeypatch.setattr(check, "OutboundGate", Spy)
    with check.real_fetcher(), gates[0].sessions() as session:
        assert outbound.switches(session, 1) == {
            connection: connection == Connection.RECIPE_IMPORT for connection in Connection
        }
    source = (BACKEND / "scripts" / "import_check.py").read_text(encoding="utf-8")
    assert "download_photo" not in source


# --- The command ---------------------------------------------------------------------------------


def test_the_command_writes_the_report_and_names_no_address_on_screen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    list_path = tmp_path / "urls.md"
    list_path.write_text(
        "## Site A\n- https://a.example/1 — soup\n## Site B\n- https://b.example/1\nodd\n",
        encoding="utf-8",
    )
    report_path = tmp_path / "report.md"
    pages: dict[str, FetchedPage | Exception] = {
        "https://a.example/1": page("dotdash.html"),
        "https://b.example/1": FetchRefused(Problem.SITE_ERROR),
    }

    class FakeFetcher:
        def __enter__(self) -> Callable[[str], FetchedPage]:
            return fetcher(pages)

        def __exit__(self, *_exc: object) -> None:
            return None

    monkeypatch.setattr(check, "real_fetcher", FakeFetcher)
    code = check.main(["--list", str(list_path), "--report", str(report_path)])
    assert code == 0
    report = report_path.read_text(encoding="utf-8")
    assert "| 1 | Site A | read | yes: Slow Cooker Pulled Jackfruit |" in report
    assert "refused by the site (site_error)" in report
    screen = capsys.readouterr().out
    assert "[1/2] read" in screen
    assert "example" not in screen


def test_the_command_stops_on_an_empty_list(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    list_path = tmp_path / "urls.md"
    list_path.write_text("## Site\nnothing here\n", encoding="utf-8")
    assert check.main(["--list", str(list_path), "--report", str(tmp_path / "r.md")]) == 1
    assert not (tmp_path / "r.md").exists()
    assert "no addresses" in capsys.readouterr().err


def test_the_defaults_are_in_the_sync_folder_outside_the_repo(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MEALWRIGHT_SYNC_DIR", "/sync-folder")
    assert check.default_paths() == (
        Path("/sync-folder/import-check/urls.md"),
        Path("/sync-folder/import-check-0.5.md"),
    )
    monkeypatch.delenv("MEALWRIGHT_SYNC_DIR")
    assert check.default_paths()[0] == Path("repo-sync/import-check/urls.md")
    assert check.GAP_SECONDS == 5.0


def test_the_script_is_not_in_the_image() -> None:
    dockerfile = (BACKEND.parent / "Dockerfile").read_text(encoding="utf-8")
    final_stage = dockerfile.rsplit("\nFROM ", 1)[1]
    assert "scripts" not in final_stage
    assert "import_check" not in final_stage


@pytest.mark.parametrize(
    "start",
    [
        # The way it is run: `uv run python scripts/import_check.py`.
        ["{script}", "--help"],
        # The way the page reader's own process loads it (`multiprocessing`'s spawn reads the
        # main script again under this name before it reads a page).
        ["-c", "import runpy; runpy.run_path({script!r}, run_name='__mp_main__')"],
    ],
)
def test_the_script_starts_in_a_fresh_python(start: list[str]) -> None:
    """The tests above load the script after pytest has loaded the app, which hid an import
    loop: on its own, the script stopped before reading any page (24 Oct)."""
    script = str(BACKEND / "scripts" / "import_check.py")
    args = [part.format(script=script) for part in start]
    done = subprocess.run(  # noqa: S603
        [sys.executable, *args],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    assert done.returncode == 0, done.stderr
