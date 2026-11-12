"""Knowing about new versions (spec section 7, "Updates"; plan row X1).

Level 1 (how old this version is) never connects. Check now and the daily check send one plain
GET to the public release list through the outbound gate, and only while the Privacy switch
"Check for updates daily" is on.
"""

import json
import re
import socketserver
import threading
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from mealwright import __version__, migrate, updates
from mealwright.auth import hash_password
from mealwright.db import make_engine, make_sessionmaker
from mealwright.models import Household, Login
from mealwright.outbound import Connection, OutboundGate, OutboundResponse, set_switch
from mealwright.updates import (
    DAILY_AFTER,
    RELEASE_LIST_URL,
    RELEASED,
    RELEASES_PAGE,
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
    # Until 1.0 both are placeholders naming an owner GitHub can't have (for cabledrawer).
    assert parts.path.split("/")[2] == page.path.split("/")[1] == "placeholder_until_1_0"


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


def test_with_the_switch_off_nothing_connects(checks: UpdateChecks, release_list: list) -> None:
    result = checks.check_now(1)
    assert result.outcome == "off"
    assert release_list == []


@pytest.mark.parametrize(
    ("answer", "status"),
    [
        ([release("v1.0.0")], 500),
        ([release("v1.0.0")], 404),
        (b"<html>rate limited</html>", 200),
        ({"message": "Not Found"}, 200),
        (b"[" * 100_000 + b"]" * 100_000, 200),
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


def test_after_couldnt_check_check_now_asks_again(
    checks: UpdateChecks, sessions: sessionmaker[Session], release_list: list
) -> None:
    switch(sessions, True)
    serve([], 503)
    assert checks.check_now(1).outcome == "failed"
    serve([release("v0.9.1")])
    assert checks.check_now(1).outcome == "newer"
    assert len(release_list) == 2


def test_turning_the_switch_off_stops_a_kept_answer(
    checks: UpdateChecks, sessions: sessionmaker[Session], release_list: list
) -> None:
    switch(sessions, True)
    serve([release("v0.9.1")])
    checks.check_now(1)
    switch(sessions, False)
    assert checks.check_now(1).outcome == "off"
    assert len(release_list) == 1


def test_each_household_keeps_its_own_answer(
    checks: UpdateChecks, sessions: sessionmaker[Session], release_list: list
) -> None:
    switch(sessions, True)
    serve([release("v0.9.1")])
    checks.check_now(1)
    assert checks.last(2) is None


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


@pytest.fixture
def member(kitchen: TestClient) -> Iterator[TestClient]:
    """A second login in the same household, with the Member role."""
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(
            Login(
                household_id=1,
                username="wren",
                name="Wren",
                password_hash=hash_password("wren's own password"),
                role="member",
            )
        )
        db.commit()
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        response = other.post(
            f"{API}/session", json={"username": "wren", "password": "wren's own password"}
        )
        assert response.status_code == 200
        yield other


def test_about_says_the_version_and_its_day_without_connecting(
    kitchen: TestClient, release_list: list
) -> None:
    body = kitchen.get(f"{API}/updates").json()
    assert body == {
        "version": __version__,
        "released": RELEASED.isoformat(),
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


def test_check_now_with_the_switch_off_says_off_and_never_connects(
    kitchen: TestClient, release_list: list
) -> None:
    response = kitchen.post(f"{API}/updates/check")
    assert response.status_code == 200
    assert response.json()["last"]["outcome"] == "off"
    assert release_list == []


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
