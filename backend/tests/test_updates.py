"""Knowing about new versions (spec section 7, "Updates"; plan row X1).

Level 1 (how old this version is) never connects. Check now and the daily check send one plain
GET to the public release list through the outbound gate, and only while the Privacy switch
"Check for updates daily" is on.
"""

import json
import logging
import re
import socketserver
import threading
import time
import tracemalloc
from collections.abc import Callable, Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st
from sqlalchemy.orm import Session, sessionmaker

from mealwright import __version__, migrate, updates
from mealwright.db import make_engine, make_sessionmaker
from mealwright.models import Household
from mealwright.outbound import Connection, OutboundGate, OutboundResponse, set_switch
from mealwright.updates import (
    DAILY_AFTER,
    PLACEHOLDER_OWNER,
    RECHECK_AFTER,
    RELEASE_LIST_URL,
    RELEASED,
    RELEASES_PAGE,
    CheckResult,
    UpdateChecks,
    newest,
    running_key,
    tag_key,
)

API = "/api/v1"
ROOT = Path(__file__).parent.parent.parent


# --- A fake release list on this machine -----------------------------------------------------


class _Server(HTTPServer):
    def server_bind(self) -> None:
        # HTTPServer normally looks up its own host name, which the guard refuses.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "localhost", self.server_address[1]


class _Releases(BaseHTTPRequestHandler):
    hits: ClassVar[list[tuple[str, dict[str, str]]]] = []
    status: ClassVar[int] = 200
    body: ClassVar[bytes] = b"[]"

    def do_GET(self) -> None:
        type(self).hits.append((self.path, dict(self.headers.items())))
        self.send_response(type(self).status)
        self.send_header("Content-Length", str(len(type(self).body)))
        self.end_headers()
        self.wfile.write(type(self).body)

    def log_message(self, *args: object) -> None:
        pass


def release(tag: str, *, prerelease: bool = False, draft: bool = False) -> dict[str, object]:
    return {"tag_name": tag, "prerelease": prerelease, "draft": draft, "body": "notes"}


def serve(releases: object, status: int = 200) -> None:
    _Releases.body = json.dumps(releases).encode() if not isinstance(releases, bytes) else releases
    _Releases.status = status


@pytest.fixture
def release_list(monkeypatch: pytest.MonkeyPatch) -> Iterator[list[tuple[str, dict[str, str]]]]:
    """The release list, served here; the check is pointed at it. Yields the requests it got."""
    _Releases.hits = []
    serve([])
    httpd = _Server(("127.0.0.1", 0), _Releases)
    thread = threading.Thread(target=httpd.serve_forever, args=(0.02,), daemon=True)
    thread.start()
    monkeypatch.setattr(
        updates, "RELEASE_LIST_URL", f"http://127.0.0.1:{httpd.server_address[1]}/releases"
    )
    yield _Releases.hits
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def sessions(tmp_path: Path) -> sessionmaker[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    migrate.upgrade(engine)
    factory = make_sessionmaker(engine)
    with factory() as session:
        session.add(Household(id=1, name="Home"))
        session.add(Household(id=2, name="Next door"))
        session.commit()
    return factory


def switch(sessions: sessionmaker[Session], on: bool, household_id: int = 1) -> None:
    with sessions() as session:
        set_switch(session, household_id, Connection.UPDATE_CHECK, on)
        session.commit()


class Clock:
    def __init__(self) -> None:
        self.now = datetime(2026, 12, 1, 9, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.now


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def checks(sessions: sessionmaker[Session], clock: Clock) -> UpdateChecks:
    return UpdateChecks(OutboundGate(sessions), clock=clock, version="0.9.0")


# --- Level 1: the release day, written in with the release -----------------------------------


def test_the_release_day_is_the_changelogs_day_for_this_version() -> None:
    """The release PR sets RELEASED with the CHANGELOG's date; this keeps the two the same."""
    found = re.match(r"^(\d+\.\d+\.\d+)(?:(a|b|rc)(\d+))?$", __version__)
    assert found, __version__
    stage = {"a": "alpha", "b": "beta", "rc": "rc"}
    tag = found[1] + (f"-{stage[found[2]]}.{found[3]}" if found[2] else "")
    changelog = (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")
    dated = re.search(rf"^## \[{re.escape(tag)}\] - (\d{{4}}-\d{{2}}-\d{{2}})$", changelog, re.M)
    assert dated, f"no CHANGELOG entry for {tag}"
    assert RELEASED.isoformat() == dated[1]


def test_the_release_list_is_a_plain_address_on_githubs_public_api() -> None:
    parts = urlsplit(RELEASE_LIST_URL)
    assert (parts.scheme, parts.netloc) == ("https", "api.github.com")
    assert parts.query == "" and parts.fragment == ""
    page = urlsplit(RELEASES_PAGE)
    assert (page.scheme, page.netloc) == ("https", "github.com")
    assert parts.path.split("/")[2] == page.path.split("/")[1] == "cabledrawer"


def test_the_web_app_knows_the_same_placeholder_owner_as_the_server() -> None:
    # About shows a note instead of a link while the owner is the placeholder; if the two texts
    # drifted apart the row would link to nowhere. Both change together at 1.0.
    words = Path(__file__).resolve().parents[2] / "frontend" / "src" / "lib" / "aboutWords.ts"
    found = re.search(r"const PLACEHOLDER_OWNER = '([^']+)'", words.read_text())
    assert found is not None
    assert found.group(1) == PLACEHOLDER_OWNER


# --- Reading the release list ----------------------------------------------------------------


def test_versions_compare_in_release_order() -> None:
    assert running_key("0.9.0") == tag_key("v0.9.0")
    assert running_key("0.9.0b1") == tag_key("v0.9.0-beta.1")
    assert running_key("0.9.0a3") == tag_key("v0.9.0-alpha.3")
    order = ["v0.8.0", "v0.9.0-alpha.1", "v0.9.0-beta.1", "v0.9.0-rc.1", "v0.9.0", "v0.10.0"]
    keys = [tag_key(tag) for tag in order]
    assert keys == sorted(keys)  # type: ignore[type-var]
    assert running_key("0.9.0.dev1") is None
    assert tag_key("nightly") is None
    assert tag_key("v" + "1" * 50 + ".0.0") is None


def test_the_newest_newer_release_is_found() -> None:
    body = json.dumps([release("v0.9.1"), release("v0.10.0"), release("v0.8.0")]).encode()
    assert newest(body, (0, 9, 0, 3, 0)) == "v0.10.0"


def test_nothing_newer_is_none() -> None:
    body = json.dumps([release("v0.9.0"), release("v0.8.0")]).encode()
    assert newest(body, (0, 9, 0, 3, 0)) is None


def test_pre_releases_count_only_while_running_one() -> None:
    body = json.dumps(
        [release("v0.10.0-beta.1", prerelease=True), release("v0.9.1"), release("v0.10.0-rc.1")]
    ).encode()
    assert newest(body, (0, 9, 0, 3, 0)) == "v0.9.1"  # 0.9.0: final releases only
    assert newest(body, (0, 9, 0, 1, 1)) == "v0.10.0-rc.1"  # 0.9.0b1: pre-releases too


def test_drafts_and_odd_entries_are_skipped() -> None:
    body = json.dumps(
        [
            release("v9.0.0", draft=True),
            {"tag_name": "v8.0.0"},  # no draft or prerelease: not trusted
            {"tag_name": 7, "draft": False, "prerelease": False},
            {"tag_name": "v6.0.0", "draft": "no", "prerelease": False},
            "v5.0.0",
            None,
            release("latest"),
            release("v0.9.2"),
        ]
    ).encode()
    assert newest(body, (0, 9, 0, 3, 0)) == "v0.9.2"


@pytest.mark.parametrize("body", [b"{}", b'{"message": "Not Found"}', b"not json", b"\xff"])
def test_an_answer_that_isnt_a_release_list_is_refused(body: bytes) -> None:
    with pytest.raises(ValueError):
        newest(body, (0, 9, 0, 3, 0))


# --- Check now -------------------------------------------------------------------------------


def test_check_now_sends_one_plain_request(
    checks: UpdateChecks, sessions: sessionmaker[Session], release_list: list
) -> None:
    switch(sessions, True)
    serve([release("v0.9.1")])
    result = checks.check_now(1)
    assert (result.outcome, result.latest) == ("newer", "v0.9.1")
    assert len(release_list) == 1
    path, headers = release_list[0]
    assert path == "/releases"  # no query string
    # Nothing about the install: the only header chosen is the user agent.
    assert {name.lower() for name in headers} <= {"host", "user-agent", "accept-encoding"}
    assert headers["User-Agent"] == "Mealwright"
    assert "0.9.0" not in json.dumps(headers)


def test_up_to_date(
    checks: UpdateChecks, sessions: sessionmaker[Session], release_list: list
) -> None:
    switch(sessions, True)
    serve([release("v0.9.0"), release("v0.10.0-beta.1", prerelease=True)])
    assert checks.check_now(1).outcome == "up_to_date"
    assert checks.last(1) is not None and checks.last(1).outcome == "up_to_date"  # type: ignore[union-attr]


def test_check_now_works_with_the_switch_off_and_the_daily_check_does_not(
    checks: UpdateChecks, sessions: sessionmaker[Session], release_list: list
) -> None:
    """cabledrawer 12 Nov: Check now always works for an admin when pressed; the daily switch only
    controls the automatic check. One request, through the gate, and the answer is shown."""
    serve([release("v0.9.1")])
    checks.daily_check(sessions)
    assert release_list == []  # the automatic check stays off
    result = checks.check_now(1)
    assert (result.outcome, result.latest) == ("newer", "v0.9.1")
    assert len(release_list) == 1


@pytest.mark.parametrize(
    ("answer", "status"),
    [
        ([release("v1.0.0")], 500),
        ([release("v1.0.0")], 404),
        (b"<html>rate limited</html>", 200),
        ({"message": "Not Found"}, 200),
        (b"[" * 100_000 + b"]" * 100_000, 200),
        (b"[" * 11 + b"]" * 11, 200),  # deeper than a release list ever is
    ],
)
def test_an_answer_that_cant_be_used_is_couldnt_check(
    checks: UpdateChecks,
    sessions: sessionmaker[Session],
    release_list: list,
    answer: object,
    status: int,
) -> None:
    switch(sessions, True)
    serve(answer, status)
    result = checks.check_now(1)
    assert (result.outcome, result.latest) == ("failed", None)


def _on_a_big_stack[T](work: Callable[[], T]) -> T:
    """`work` run in a thread with a 256 MB stack, as on a build or machine with a big one
    (GitHub's check run read 100,000 nested lists without running out)."""
    found: list[T] = []
    old = threading.stack_size(256 * 1024 * 1024)
    try:
        thread = threading.Thread(target=lambda: found.append(work()))
        thread.start()
        thread.join()
    finally:
        threading.stack_size(old)
    assert found, "the work raised"
    return found[0]


def test_a_deep_answer_is_couldnt_check_even_where_python_could_read_it() -> None:
    """T4 (22 Nov): Python 3.14 reads JSON as deep as its stack allows, so the same answer
    raised on one build and was read as an empty release list ("up to date") on another.
    It is refused before it is parsed, whatever the stack."""
    deep = b"[" * 100_000 + b"]" * 100_000
    running = updates.running_key("0.9.0")
    assert running is not None
    assert _on_a_big_stack(lambda: json.loads(deep)) is not None  # this stack can read it

    def refused() -> str:
        with pytest.raises(ValueError, match="too deep"):
            updates.newest(deep, running)
        return "refused"

    assert _on_a_big_stack(refused) == "refused"
    with pytest.raises(ValueError, match="too deep"):
        updates.newest(deep, running)


@pytest.mark.parametrize("encoding", ["utf-16-le", "utf-16-be", "utf-16", "utf-32-le"])
def test_a_deep_answer_in_another_encoding_is_couldnt_check(encoding: str) -> None:
    """T4 security pass r1: `json.loads` reads UTF-16 and UTF-32 by itself, and there one
    byte of a character can look like a quote to the depth check, hiding the deep part. Only
    UTF-8 is read."""
    deep = ('["\u2200",' + "[" * 200_000 + "]" * 200_000 + ',"\u2200"]').encode(encoding)
    running = updates.running_key("0.9.0")
    assert running is not None

    def refused() -> str:
        with pytest.raises(ValueError):
            updates.newest(deep, running)
        return "refused"

    assert _on_a_big_stack(refused) == "refused"


def test_a_release_list_with_a_byte_order_mark_is_read() -> None:
    running = updates.running_key("1.0.0")
    assert running is not None
    body = b"\xef\xbb\xbf" + json.dumps([release("v1.1.0")]).encode()
    assert updates.newest(body, running) == "v1.1.0"


@pytest.mark.parametrize("escape", ["\\n", "\\u0022", "\\\\", '\\"'])
def test_an_escape_cannot_hide_a_deep_part(escape: str) -> None:
    """A string ending in an escape (a newline, a quote) still ends at its closing quote."""
    deep = f'["a{escape}", ' + "[" * 11 + "]" * 11 + "]"
    assert json.loads(deep)  # it is JSON
    running = updates.running_key("0.9.0")
    assert running is not None
    with pytest.raises(ValueError, match="too deep"):
        updates.newest(deep.encode(), running)


_TRICKY_TEXT = st.text(alphabet='"\\[]{}nu0 a\n\u2200', max_size=8)
_JSON_VALUES = st.recursive(
    st.none() | st.integers() | _TRICKY_TEXT,
    lambda inner: st.lists(inner, max_size=3) | st.dictionaries(_TRICKY_TEXT, inner, max_size=3),
    max_leaves=40,
)


def _depth(value: object) -> int:
    if isinstance(value, list):
        return 1 + max(map(_depth, value), default=0)
    if isinstance(value, dict):
        return 1 + max(map(_depth, value.values()), default=0)
    return 0


@settings(max_examples=2000, deadline=None)
@given(_JSON_VALUES, st.integers(min_value=0, max_value=12), st.booleans())
def test_the_depth_check_agrees_with_the_real_depth(value: object, depth: int, plain: bool) -> None:
    """Brackets, quotes and escapes in strings never change the depth found (T4 security
    pass r1)."""
    body = json.dumps(value, ensure_ascii=plain).encode()
    assert updates._too_deep(body, depth) == (_depth(value) > depth), body


def test_a_real_release_list_is_not_too_deep() -> None:
    """GitHub's list nests 5 deep (assets, their uploader); brackets in notes don't count."""
    full = {
        **release("v1.2.0"),
        "body": 'Fixed [[[[[[[[[[[[ and {{{{{{{{{{{{ and \\"[[[[[[[[[[[[',
        "assets": [{"name": "x", "uploader": {"login": "cabledrawer", "ids": [[1]]}}],
        "reactions": {"+1": 2},
    }
    running = updates.running_key("1.0.0")
    assert running is not None
    assert updates.newest(json.dumps([full, release("v1.1.0")]).encode(), running) == "v1.2.0"


@pytest.mark.parametrize(
    "body",
    [
        b'"' + b'\\"' * 1_000_000,  # one string that never ends: every quote is escaped
        b'"' * 2_000_000,
        b"[" * 1_000_000 + b"]" * 1_000_000,
        b"[]" * 1_000_000,
    ],
)
def test_the_depth_check_is_quick_on_any_answer(body: bytes) -> None:
    running = updates.running_key("1.0.0")
    assert running is not None
    start = time.process_time()
    with pytest.raises(ValueError):
        updates.newest(body, running)
    assert time.process_time() - start < 2


@pytest.mark.parametrize(
    "body",
    [b'"' * 2_000_000, b"[ ]" * 700_000, b"[{}]" * 500_000, b'"\\"' * 700_000, b'"a"[' * 500_000],
    ids=["quotes", "spaced-pairs", "mixed-pairs", "escaped-quotes", "strings-and-brackets"],
)
def test_the_depth_check_needs_little_memory(body: bytes) -> None:
    """T4 security pass r1: taking out everything but the brackets one match at a time
    held a list as long as the answer (150 MB for 2 MB of `[ ]`)."""
    tracemalloc.start()
    try:
        updates._too_deep(body, updates.MAX_LIST_DEPTH)
        peak = tracemalloc.get_traced_memory()[1]
    finally:
        tracemalloc.stop()
    assert peak < 3 * len(body) + 1_000_000, peak


def test_a_list_too_big_is_not_read(
    checks: UpdateChecks,
    sessions: sessionmaker[Session],
    release_list: list,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(updates, "MAX_LIST_BYTES", 1024)
    switch(sessions, True)
    serve([release("v1.0.0")] + [release("v0.1.0")] * 100)
    assert checks.check_now(1).outcome == "failed"


def test_a_site_that_cant_be_reached_is_couldnt_check(
    checks: UpdateChecks, sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    import socket

    with socket.create_server(("127.0.0.1", 0)) as closed:
        port = closed.getsockname()[1]
    monkeypatch.setattr(updates, "RELEASE_LIST_URL", f"http://127.0.0.1:{port}/releases")
    switch(sessions, True)
    assert checks.check_now(1).outcome == "failed"


def test_check_now_again_within_a_minute_gives_the_same_answer(
    checks: UpdateChecks, sessions: sessionmaker[Session], release_list: list, clock: Clock
) -> None:
    switch(sessions, True)
    serve([release("v0.9.1")])
    first = checks.check_now(1)
    clock.now += timedelta(seconds=30)
    assert checks.check_now(1) == first
    assert len(release_list) == 1
    clock.now += timedelta(seconds=31)
    checks.check_now(1)
    assert len(release_list) == 2


def test_after_couldnt_check_check_now_asks_again_after_a_minute(
    checks: UpdateChecks, sessions: sessionmaker[Session], release_list: list, clock: Clock
) -> None:
    switch(sessions, True)
    serve([], 503)
    assert checks.check_now(1).outcome == "failed"
    serve([release("v0.9.1")])
    clock.now += timedelta(seconds=30)
    assert checks.check_now(1).outcome == "failed"  # the answer just had, failed included
    assert len(release_list) == 1
    clock.now += timedelta(seconds=31)
    assert checks.check_now(1).outcome == "newer"
    assert len(release_list) == 2


def test_check_now_25_times_against_a_list_that_isnt_there_asks_once(
    checks: UpdateChecks, sessions: sessionmaker[Session], release_list: list
) -> None:
    """A failed answer is kept for a minute too, so pressing Check now again and again (or a
    script doing it) can't send the release list a stream of requests (security review r1)."""
    switch(sessions, True)
    serve({"message": "Not Found"}, 404)
    outcomes = {checks.check_now(1).outcome for _ in range(25)}
    assert outcomes == {"failed"}
    assert len(release_list) == 1


def test_eight_checks_at_once_ask_once_and_all_get_its_answer(
    checks: UpdateChecks,
    sessions: sessionmaker[Session],
    release_list: list,
    clock: Clock,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Checks that wait for one already running get that check's answer, even a failed one,
    and even when it took longer than the minute an answer is kept (security review r1)."""
    switch(sessions, True)
    asked: list[str] = []
    started, go = threading.Event(), threading.Event()

    def slow(*args: object, **options: object) -> OutboundResponse:
        asked.append("release list")
        started.set()
        assert go.wait(10)
        clock.now += timedelta(minutes=2)  # past RECHECK_AFTER: only waiting keeps it
        return OutboundResponse(status=404, headers={}, body=b"", url=updates.RELEASE_LIST_URL)

    monkeypatch.setattr(checks._gate, "request", slow)
    results: list[CheckResult] = []

    def press() -> None:
        results.append(checks.check_now(1))

    presses = [threading.Thread(target=press) for _ in range(8)]
    presses[0].start()
    assert started.wait(10)
    for other in presses[1:]:
        other.start()
    time.sleep(0.5)  # the other seven are waiting for the first
    go.set()
    for each in presses:
        each.join(10)
    assert asked == ["release list"]
    assert len(results) == 8
    assert {(r.outcome, r.checked_at) for r in results} == {("failed", results[0].checked_at)}


def test_the_switch_makes_no_difference_to_check_now(
    checks: UpdateChecks, sessions: sessionmaker[Session], release_list: list, clock: Clock
) -> None:
    serve([release("v0.9.1")])
    assert checks.check_now(1).outcome == "newer"
    switch(sessions, True)
    clock.now += RECHECK_AFTER
    assert checks.check_now(1).outcome == "newer"
    assert len(release_list) == 2


def test_turning_the_switch_off_does_not_stop_check_now_or_its_recheck_rule(
    checks: UpdateChecks, sessions: sessionmaker[Session], release_list: list, clock: Clock
) -> None:
    switch(sessions, True)
    serve([release("v0.9.1")])
    checks.check_now(1)
    switch(sessions, False)
    assert checks.check_now(1).outcome == "newer"  # the answer just had
    assert len(release_list) == 1
    clock.now += RECHECK_AFTER
    assert checks.check_now(1).outcome == "newer"  # asked again, switch or not
    assert len(release_list) == 2


def test_each_household_keeps_its_own_answer(
    checks: UpdateChecks, sessions: sessionmaker[Session], release_list: list
) -> None:
    switch(sessions, True)
    serve([release("v0.9.1")])
    checks.check_now(1)
    assert checks.last(2) is None


def test_while_the_release_list_is_the_placeholder_nothing_connects(
    checks: UpdateChecks,
    sessions: sessionmaker[Session],
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
    clock: Clock,
) -> None:
    """Until 1.0 the release list doesn't exist, so asking for it could only get "not found":
    with the switch on, Check now and the daily check connect nowhere and say "couldn't
    check" (security review r1; cabledrawer 12 Nov)."""
    asked: list[object] = []
    monkeypatch.setattr(
        updates,
        "RELEASE_LIST_URL",
        f"https://api.github.com/repos/{PLACEHOLDER_OWNER}/mealwright/releases",
    )
    monkeypatch.setattr(checks._gate, "request", lambda *args, **options: asked.append(args))
    assert checks.check_now(1).outcome == "failed"  # the switch is off: pressed all the same
    clock.now += RECHECK_AFTER
    switch(sessions, True)
    with caplog.at_level(logging.INFO, logger="mealwright.updates"):
        assert checks.check_now(1).outcome == "failed"
    assert "nothing was asked" in caplog.text
    assert "github" not in caplog.text.lower()
    clock.now += timedelta(days=1)
    checks.daily_check(sessions)
    assert checks.last(1) is not None and checks.last(1).checked_at == clock.now  # type: ignore[union-attr]
    assert asked == []


def test_a_build_with_an_odd_version_never_connects(
    sessions: sessionmaker[Session], release_list: list
) -> None:
    switch(sessions, True)
    odd = UpdateChecks(OutboundGate(sessions), version="0.0.0+local")
    assert odd.check_now(1).outcome == "failed"
    assert release_list == []


# --- The daily check -------------------------------------------------------------------------


def test_the_daily_check_skips_a_household_with_the_switch_off(
    checks: UpdateChecks, sessions: sessionmaker[Session], release_list: list
) -> None:
    checks.daily_check(sessions)
    assert release_list == []
    assert checks.last(1) is None


def test_the_daily_check_asks_once_a_day(
    checks: UpdateChecks, sessions: sessionmaker[Session], release_list: list, clock: Clock
) -> None:
    switch(sessions, True)
    serve([release("v0.9.1")])
    checks.daily_check(sessions)
    assert len(release_list) == 1
    assert checks.last(1) is not None and checks.last(1).outcome == "newer"  # type: ignore[union-attr]
    assert checks.last(2) is None  # its switch is off
    clock.now += DAILY_AFTER - timedelta(minutes=1)
    checks.daily_check(sessions)
    assert len(release_list) == 1
    clock.now += timedelta(minutes=1)
    checks.daily_check(sessions)
    assert len(release_list) == 2


def test_the_daily_check_never_raises(
    checks: UpdateChecks, sessions: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    switch(sessions, True)

    def broken(household_id: int) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(checks, "_check", broken)
    checks.daily_check(sessions)


# --- The API ---------------------------------------------------------------------------------


def test_about_says_the_version_and_its_day_without_connecting(
    kitchen: TestClient, release_list: list
) -> None:
    body = kitchen.get(f"{API}/updates").json()
    assert body == {
        "version": __version__,
        "released_on": RELEASED.isoformat(),
        "releases_page": RELEASES_PAGE,
        "can_check": True,
        "daily": False,
        "last": None,
    }
    kitchen.put(f"{API}/privacy/switches/update_check", json={"on": True})
    assert kitchen.get(f"{API}/updates").json()["daily"] is True
    assert release_list == []


def test_a_member_sees_the_version_but_not_the_check(
    kitchen: TestClient, member: TestClient, release_list: list
) -> None:
    kitchen.put(f"{API}/privacy/switches/update_check", json={"on": True})
    serve([release("v99.0.0")])
    kitchen.post(f"{API}/updates/check")
    body = member.get(f"{API}/updates").json()
    assert (body["can_check"], body["daily"], body["last"]) == (False, None, None)
    assert body["version"] == __version__
    response = member.post(f"{API}/updates/check")
    assert response.status_code == 403
    assert len(release_list) == 1  # the admin's check only


def test_an_admin_checks_now(kitchen: TestClient, release_list: list) -> None:
    kitchen.put(f"{API}/privacy/switches/update_check", json={"on": True})
    serve([release("v99.0.0")])
    response = kitchen.post(f"{API}/updates/check")
    assert response.status_code == 200
    last = response.json()["last"]
    assert (last["outcome"], last["latest"]) == ("newer", "v99.0.0")
    assert kitchen.get(f"{API}/updates").json()["last"] == last
    assert len(release_list) == 1


def test_check_now_with_the_switch_off_makes_the_one_request(
    kitchen: TestClient, release_list: list
) -> None:
    """cabledrawer 12 Nov: the daily switch only controls the automatic check."""
    serve([release("v99.0.0")])
    assert kitchen.get(f"{API}/updates").json()["daily"] is False
    response = kitchen.post(f"{API}/updates/check")
    assert response.status_code == 200
    assert response.json()["last"]["outcome"] == "newer"
    assert len(release_list) == 1


def test_check_now_needs_the_same_site(kitchen: TestClient, release_list: list) -> None:
    kitchen.put(f"{API}/privacy/switches/update_check", json={"on": True})
    response = kitchen.post(
        f"{API}/updates/check", headers={"Origin": "https://somewhere-else.example"}
    )
    assert response.status_code == 403
    assert release_list == []


def test_no_database_connection_is_held_while_check_now_waits(
    kitchen: TestClient, release_list: list, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Check now's wait on the release list (up to 20 s) holds no database connection, so a few
    slow checks can't use up the pool other requests and sign-in need (security review r1)."""
    kitchen.put(f"{API}/privacy/switches/update_check", json={"on": True})
    pool = kitchen.app.state.sessionmaker.kw["bind"].pool  # type: ignore[attr-defined]
    gate: OutboundGate = kitchen.app.state.outbound  # type: ignore[attr-defined]
    real = gate.request
    open_during: list[int] = []

    def waiting(*args: object, **options: object) -> OutboundResponse:
        open_during.append(pool.checkedout())
        return real(*args, **options)  # type: ignore[arg-type]

    monkeypatch.setattr(gate, "request", waiting)
    response = kitchen.post(f"{API}/updates/check")
    assert response.status_code == 200
    assert response.json()["last"]["outcome"] == "up_to_date"
    assert open_during == [0]
