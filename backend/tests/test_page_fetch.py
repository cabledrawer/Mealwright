"""Fetching recipe pages and photos safely (spec section 6, "Recipe import, decided for 0.5",
and section 7). Name look-ups and connections are faked: nothing here goes online."""

import contextlib
import logging
import shutil
import socket
import ssl
import threading
import time
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from ipaddress import ip_address
from pathlib import Path
from typing import Any, cast

import photo_kit
import pytest
from sqlalchemy.orm import Session, sessionmaker

from mealwright import migrate, network_guard, outbound, page_fetch
from mealwright.db import make_engine, make_sessionmaker
from mealwright.limits import MAX_PHOTO_BYTES
from mealwright.models import Household, OwnNetworkEntry
from mealwright.outbound import (
    Connection,
    OutboundBlocked,
    OutboundGate,
    WrongContentType,
    set_switch,
)
from mealwright.page_fetch import (
    MAX_PAGE_BYTES,
    MESSAGES,
    FetchRefused,
    Problem,
    download_photo,
    fetch_page,
)

PAGE = b"<!doctype html><title>Tomato rasam</title><p>A made-up page.</p>"
PUBLIC = "93.184.216.34"
PUBLIC_6 = "2606:4700::1"


@dataclass
class Reply:
    status: int = 200
    headers: dict[str, str] = field(
        default_factory=lambda: {"Content-Type": "text/html; charset=utf-8"}
    )
    body: bytes = PAGE
    pause: float = 0.0  # seconds between the headers and the body


@dataclass
class Request:
    address: str
    port: int
    line: str
    headers: dict[str, str]


type Site = Callable[[Request], Reply]


class FakeTLS:
    """Stands in for the TLS context: notes the name each connection asks for."""

    def __init__(self) -> None:
        self.names: list[str | None] = []

    def wrap_socket(
        self, sock: socket.socket, server_hostname: str | None = None, **_options: object
    ) -> Any:
        self.names.append(server_hostname)
        return sock


class FakeNet:
    """Name look-ups and web servers, all in memory (a socket pair per connection)."""

    def __init__(self) -> None:
        self.dns: dict[str, list[str] | Callable[[], list[str]] | Exception] = {}
        self.sites: dict[tuple[str, int], Site] = {}
        self.lookups: list[str] = []
        self.connections: list[tuple[str, int]] = []
        self.requests: list[Request] = []

    def page(self, address: str, reply: Reply | Site | None = None, port: int = 443) -> None:
        if callable(reply):
            self.sites[(address, port)] = reply
        else:
            answer = reply or Reply()
            self.sites[(address, port)] = lambda _request: answer

    def lookup(self, host: str, port: int) -> list[str]:
        self.lookups.append(host)
        answer = self.dns.get(host)
        if answer is None:
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
        if isinstance(answer, Exception):
            raise answer
        return answer() if callable(answer) else answer

    def open_socket(self, address: str, port: int, timeout: float | None) -> socket.socket:
        self.connections.append((address, port))
        site = self.sites.get((address, port))
        if site is None:
            raise ConnectionRefusedError(111, "Connection refused")
        client, server = socket.socketpair()
        threading.Thread(
            target=self._serve, args=(server, site, address, port), daemon=True
        ).start()
        client.settimeout(timeout)
        return client

    def _serve(self, server: socket.socket, site: Site, address: str, port: int) -> None:
        with server:
            data = b""
            while b"\r\n\r\n" not in data:
                chunk = server.recv(65536)
                if not chunk:
                    return
                data += chunk
            lines = data.split(b"\r\n\r\n")[0].decode("latin-1").split("\r\n")
            headers = {
                k.strip().lower(): v.strip() for k, v in (h.split(":", 1) for h in lines[1:])
            }
            request = Request(address, port, lines[0], headers)
            self.requests.append(request)
            reply = site(request)
            head = [f"HTTP/1.1 {reply.status} Whatever"]
            head += [f"{k}: {v}" for k, v in reply.headers.items()]
            head += [f"Content-Length: {len(reply.body)}", "Connection: close", "", ""]
            try:
                server.sendall("\r\n".join(head).encode("latin-1"))
                if reply.pause:
                    time.sleep(reply.pause)
                server.sendall(reply.body)
            except OSError:
                pass  # the client stopped reading


@pytest.fixture(scope="module")
def template(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """One migrated database with both switches on, copied for each test (it's quicker)."""
    path = tmp_path_factory.mktemp("template") / "test.db"
    engine = make_engine(f"sqlite:///{path}")
    migrate.upgrade(engine)
    factory = make_sessionmaker(engine)
    with factory() as session:
        session.add_all([Household(id=1, name="Home"), Household(id=2, name="Next door")])
        session.commit()
        for household in (1, 2):
            set_switch(session, household, Connection.RECIPE_IMPORT, True)
            set_switch(session, household, Connection.RECIPE_PHOTOS, True)
        session.commit()
    engine.dispose()
    return path


@pytest.fixture
def sessions(template: Path, tmp_path: Path) -> sessionmaker[Session]:
    path = tmp_path / "test.db"
    shutil.copyfile(template, path)
    return make_sessionmaker(make_engine(f"sqlite:///{path}"))


@pytest.fixture
def tls() -> FakeTLS:
    return FakeTLS()


@pytest.fixture
def gate(sessions: sessionmaker[Session], tls: FakeTLS) -> OutboundGate:
    return OutboundGate(sessions, tls=cast(Any, tls))


@pytest.fixture
def net(monkeypatch: pytest.MonkeyPatch) -> FakeNet:
    fake = FakeNet()
    monkeypatch.setattr(outbound, "_lookup", fake.lookup)
    monkeypatch.setattr(outbound, "_open_socket", fake.open_socket)
    return fake


def switch(
    sessions: sessionmaker[Session], connection: Connection, on: bool, household: int = 1
) -> None:
    with sessions() as session:
        set_switch(session, household, connection, on)
        session.commit()


def listing(sessions: sessionmaker[Session], kind: str, value: str, household: int = 1) -> None:
    """Put an entry straight into the table, past the checks `own_network.add` makes."""
    with sessions() as session:
        session.add(OwnNetworkEntry(household_id=household, kind=kind, value=value))
        session.commit()


def refused(gate: OutboundGate, url: str, household: int = 1) -> Problem:
    with pytest.raises(FetchRefused) as caught:
        fetch_page(gate, household, url)
    return caught.value.problem


# --- The switch ----------------------------------------------------------------------------


def test_switched_off_is_refused_before_any_look_up(
    gate: OutboundGate,
    net: FakeNet,
    sessions: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    switch(sessions, Connection.RECIPE_IMPORT, False)
    net.dns["recipes.example"] = [PUBLIC]
    net.page(PUBLIC)
    with caplog.at_level(logging.DEBUG), pytest.raises(FetchRefused) as caught:
        fetch_page(gate, 1, "https://recipes.example/sambar")
    assert caught.value.problem is Problem.SWITCHED_OFF
    assert caught.value.message == "Importing from links is switched off"
    assert net.lookups == [] and net.connections == []
    assert caplog.messages == ["Blocked outgoing connection: recipe import is switched off"]


def test_switched_off_is_refused_even_for_a_bad_link(
    gate: OutboundGate, net: FakeNet, sessions: sessionmaker[Session]
) -> None:
    switch(sessions, Connection.RECIPE_IMPORT, False)
    assert refused(gate, "not a link") is Problem.SWITCHED_OFF


def test_one_households_switch_doesnt_open_anothers(
    gate: OutboundGate, net: FakeNet, sessions: sessionmaker[Session]
) -> None:
    switch(sessions, Connection.RECIPE_IMPORT, False, household=2)
    net.dns["recipes.example"] = [PUBLIC]
    net.page(PUBLIC)
    assert fetch_page(gate, 1, "https://recipes.example/").html
    assert refused(gate, "https://recipes.example/", household=2) is Problem.SWITCHED_OFF


def test_the_pinned_request_checks_the_switch_too(
    gate: OutboundGate, net: FakeNet, sessions: sessionmaker[Session]
) -> None:
    switch(sessions, Connection.RECIPE_IMPORT, False)
    net.page(PUBLIC)
    with pytest.raises(OutboundBlocked):
        gate.get_pinned(1, Connection.RECIPE_IMPORT, "https://recipes.example/", ip_address(PUBLIC))
    with pytest.raises(OutboundBlocked):
        gate.look_up(1, Connection.RECIPE_IMPORT, "recipes.example", 443)
    assert net.lookups == [] and net.connections == []


def test_the_pinned_request_refuses_port_0(gate: OutboundGate, net: FakeNet) -> None:
    net.page(PUBLIC, port=80)
    with pytest.raises(OutboundBlocked):
        gate.get_pinned(
            1, Connection.RECIPE_IMPORT, "http://recipes.example:0/", ip_address(PUBLIC)
        )
    assert net.connections == []


# --- An ordinary page ----------------------------------------------------------------------


def test_a_public_page_is_fetched_from_the_checked_address(
    gate: OutboundGate, net: FakeNet, tls: FakeTLS
) -> None:
    net.dns["www.recipes.example"] = [PUBLIC]
    net.page(PUBLIC)
    page = fetch_page(gate, 1, "https://www.recipes.example/rasam?print=1#method")
    assert page.html == PAGE.decode()
    assert page.url == "https://www.recipes.example/rasam?print=1"
    assert net.connections == [(PUBLIC, 443)]
    # The TLS name and the Host header are the host name, not the address.
    assert tls.names == ["www.recipes.example"]
    [request] = net.requests
    assert request.line == "GET /rasam?print=1 HTTP/1.1"
    assert request.headers["host"] == "www.recipes.example"
    assert request.headers["user-agent"] == "Mealwright"
    assert "cookie" not in request.headers


def test_plain_http_and_ipv6(gate: OutboundGate, net: FakeNet, tls: FakeTLS) -> None:
    net.dns["old.recipes.example"] = [PUBLIC_6]
    net.page(PUBLIC_6, port=80)
    assert fetch_page(gate, 1, "http://old.recipes.example/").html
    assert net.connections == [(PUBLIC_6, 80)]
    assert tls.names == []  # no TLS on plain http


def test_a_public_address_link_is_fetched_without_a_look_up(
    gate: OutboundGate, net: FakeNet
) -> None:
    net.page(PUBLIC)
    assert fetch_page(gate, 1, f"https://{PUBLIC}/").html
    assert net.lookups == []
    assert net.requests[0].headers["host"] == PUBLIC


def test_the_next_address_is_tried_when_one_cant_be_reached(
    gate: OutboundGate, net: FakeNet
) -> None:
    net.dns["recipes.example"] = [PUBLIC_6, PUBLIC]  # no server on the IPv6 one
    net.page(PUBLIC)
    assert fetch_page(gate, 1, "https://recipes.example/").html
    assert net.connections == [(PUBLIC_6, 443), (PUBLIC, 443)]


def test_international_names_and_paths_are_encoded(gate: OutboundGate, net: FakeNet) -> None:
    net.dns["xn--bcher-kva.example"] = [PUBLIC]
    net.page(PUBLIC)
    page = fetch_page(gate, 1, "https://Bücher.example/rezept/käse spätzle?q=süß")
    assert net.lookups == ["xn--bcher-kva.example"]
    assert net.requests[0].headers["host"] == "xn--bcher-kva.example"
    assert net.requests[0].line == ("GET /rezept/k%C3%A4se%20sp%C3%A4tzle?q=s%C3%BC%C3%9F HTTP/1.1")
    assert page.url.startswith("https://xn--bcher-kva.example/rezept/k%C3%A4se")


@pytest.mark.parametrize(
    "link",
    [
        "",
        "recipes.example/rasam",
        "ftp://recipes.example/rasam",
        "file:///etc/passwd",
        "javascript:alert(1)",
        "data:text/html,<p>hi</p>",
        "https://user:secret@recipes.example/",
        "https://user@recipes.example/",
        "http://[fe80::1%25eth0]/",
        "https://recipes.example:99999/",
        "https://recipes.example:0/",  # port 0 is never a site's port (not "the usual one")
        "http://recipes.example:00/",
        "https://recipes.example:port/",
        "http://2130706433/",  # 127.0.0.1 written as one number
        "http://127.1/",
        "http://0x7f.0.0.1/",
        "https:///nothing",
        "https://bad_name!.example/",
    ],
)
def test_bad_links_are_refused_before_any_look_up(
    gate: OutboundGate, net: FakeNet, link: str
) -> None:
    assert refused(gate, link) is Problem.BAD_LINK
    assert net.lookups == [] and net.connections == []


def test_a_name_that_cant_be_found(gate: OutboundGate, net: FakeNet) -> None:
    assert refused(gate, "https://nowhere.example/") is Problem.CANT_REACH
    net.dns["empty.example"] = []
    assert refused(gate, "https://empty.example/") is Problem.CANT_REACH
    assert net.connections == []


def test_a_server_that_refuses(gate: OutboundGate, net: FakeNet) -> None:
    net.dns["down.example"] = [PUBLIC]
    assert refused(gate, "https://down.example/") is Problem.CANT_REACH


def test_a_tls_problem(
    gate: OutboundGate, net: FakeNet, tls: FakeTLS, monkeypatch: pytest.MonkeyPatch
) -> None:
    def bad_certificate(
        sock: socket.socket, server_hostname: str | None = None, **_options: object
    ) -> Any:
        raise ssl.SSLCertVerificationError("certificate verify failed: Hostname mismatch")

    monkeypatch.setattr(tls, "wrap_socket", bad_certificate)
    net.dns["recipes.example"] = [PUBLIC]
    net.page(PUBLIC)
    assert refused(gate, "https://recipes.example/") is Problem.CANT_REACH


def test_the_real_tls_context_checks_the_host_name(sessions: sessionmaker[Session]) -> None:
    context = OutboundGate(sessions)._tls
    assert isinstance(context, ssl.SSLContext)
    assert context.check_hostname is True
    assert context.verify_mode == ssl.CERT_REQUIRED


@pytest.mark.parametrize("status", [404, 410, 500, 503])
def test_an_error_page_isnt_a_recipe_page(gate: OutboundGate, net: FakeNet, status: int) -> None:
    net.dns["recipes.example"] = [PUBLIC]
    net.page(PUBLIC, Reply(status=status))
    assert refused(gate, "https://recipes.example/") is Problem.SITE_ERROR


def test_a_slow_site_runs_out_of_time(
    gate: OutboundGate, net: FakeNet, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(outbound, "TIMEOUT_SECONDS", 0.3)
    net.dns["slow.example"] = [PUBLIC]
    net.page(PUBLIC, Reply(pause=2))
    started = time.monotonic()
    assert refused(gate, "https://slow.example/") is Problem.TIMEOUT
    assert time.monotonic() - started < 1.5


def test_a_site_that_trickles_still_runs_out_of_time(
    gate: OutboundGate, net: FakeNet, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The time limit is for the whole answer, not for each read."""
    monkeypatch.setattr(outbound, "TIMEOUT_SECONDS", 0.5)

    def trickle(server: socket.socket, site: Site, address: str, port: int) -> None:
        with server:
            data = b""
            while b"\r\n\r\n" not in data:
                data += server.recv(65536)
            try:
                server.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n")
                for _ in range(30):  # 10 bytes every 0.1 s: each read is quick
                    server.sendall(b"x" * 10)
                    time.sleep(0.1)
            except OSError:
                pass

    net.dns["drip.example"] = [PUBLIC]
    net.page(PUBLIC)
    monkeypatch.setattr(net, "_serve", trickle)
    started = time.monotonic()
    assert refused(gate, "https://drip.example/") is Problem.TIMEOUT
    assert time.monotonic() - started < 1.5


def _dripping(
    net: FakeNet, monkeypatch: pytest.MonkeyPatch, send: Callable[[socket.socket], None]
) -> None:
    """The site reads the request, then answers with `send` (which may take its time)."""

    def serve(server: socket.socket, site: Site, address: str, port: int) -> None:
        with server:
            data = b""
            while b"\r\n\r\n" not in data:
                data += server.recv(65536)
            with contextlib.suppress(OSError):  # the gate cut the connection
                send(server)

    net.dns["drip.example"] = [PUBLIC]
    net.page(PUBLIC)
    monkeypatch.setattr(net, "_serve", serve)


def _drip(server: socket.socket, byte: bytes, times: int = 40) -> None:
    for _ in range(times):  # a byte every 0.1 s: no single wait is long
        server.sendall(byte)
        time.sleep(0.1)


def _runs_out_of_time(gate: OutboundGate, link: str = "https://drip.example/") -> None:
    started = time.monotonic()
    assert refused(gate, link) is Problem.TIMEOUT
    assert time.monotonic() - started < 1.5  # the limit is 0.5 s; the drip takes 4 s


def test_headers_that_trickle_run_out_of_time(
    gate: OutboundGate, net: FakeNet, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(outbound, "TIMEOUT_SECONDS", 0.5)

    def send(server: socket.socket) -> None:
        server.sendall(b"HTTP/1.1 200 OK\r\nX-Slow: ")
        _drip(server, b"x")
        server.sendall(b"\r\nContent-Type: text/html\r\nContent-Length: 2\r\n\r\nok")

    _dripping(net, monkeypatch, send)
    _runs_out_of_time(gate)


def test_a_status_line_that_trickles_runs_out_of_time(
    gate: OutboundGate, net: FakeNet, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(outbound, "TIMEOUT_SECONDS", 0.5)

    def send(server: socket.socket) -> None:
        server.sendall(b"HTTP/1.1 200 ")
        _drip(server, b"O")
        server.sendall(b"K\r\nContent-Type: text/html\r\nContent-Length: 2\r\n\r\nok")

    _dripping(net, monkeypatch, send)
    _runs_out_of_time(gate)


def test_a_chunk_size_line_that_trickles_runs_out_of_time(
    gate: OutboundGate, net: FakeNet, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(outbound, "TIMEOUT_SECONDS", 0.5)

    def send(server: socket.socket) -> None:
        server.sendall(
            b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nTransfer-Encoding: chunked\r\n\r\n"
        )
        _drip(server, b"0")  # a chunk-size line that never ends
        server.sendall(b"2\r\nok\r\n0\r\n\r\n")

    _dripping(net, monkeypatch, send)
    _runs_out_of_time(gate)


def test_a_body_that_trickles_byte_by_byte_runs_out_of_time(
    gate: OutboundGate, net: FakeNet, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(outbound, "TIMEOUT_SECONDS", 0.5)

    def send(server: socket.socket) -> None:
        server.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nContent-Length: 100\r\n\r\n")
        _drip(server, b"x")

    _dripping(net, monkeypatch, send)
    _runs_out_of_time(gate)


def test_a_tls_handshake_that_trickles_runs_out_of_time(
    sessions: sessionmaker[Session], net: FakeNet, monkeypatch: pytest.MonkeyPatch
) -> None:
    """With the real TLS code: the site starts a handshake record and never finishes it."""
    monkeypatch.setattr(outbound, "TIMEOUT_SECONDS", 0.5)
    real = OutboundGate(sessions)  # the real TLS context

    def serve(server: socket.socket, site: Site, address: str, port: int) -> None:
        with server, contextlib.suppress(OSError):
            server.recv(65536)  # the ClientHello
            server.sendall(b"\x16\x03\x03\x40\x00")  # a 16 KB handshake record is coming
            _drip(server, b"\x00")

    net.dns["drip.example"] = [PUBLIC]
    net.page(PUBLIC)
    monkeypatch.setattr(net, "_serve", serve)
    _runs_out_of_time(real)


@pytest.mark.parametrize("link", ["https://drip.example/", "http://drip.example/"])
def test_a_connection_made_after_the_time_limit_stops_at_once(
    gate: OutboundGate, net: FakeNet, monkeypatch: pytest.MonkeyPatch, link: str
) -> None:
    """The watchdog fires while connecting, before there's a socket to cut: the request
    still stops, rather than letting the headers trickle in for as long as they like."""
    monkeypatch.setattr(outbound, "TIMEOUT_SECONDS", 0.2)

    def send(server: socket.socket) -> None:
        server.sendall(b"HTTP/1.1 200 OK\r\nX-Slow: ")
        _drip(server, b"x")
        server.sendall(b"\r\nContent-Type: text/html\r\nContent-Length: 2\r\n\r\nok")

    _dripping(net, monkeypatch, send)
    net.page(PUBLIC, port=80)
    quick = net.open_socket

    def slow_connect(address: str, port: int, timeout: float | None) -> socket.socket:
        time.sleep(0.5)  # the watchdog fires at 0.2 s, while this is still connecting
        return quick(address, port, timeout)

    monkeypatch.setattr(outbound, "_open_socket", slow_connect)
    started = time.monotonic()
    assert refused(gate, link) is Problem.TIMEOUT
    assert time.monotonic() - started < 1.5  # the drip takes 4 s


def test_the_whole_fetch_has_a_time_limit_across_redirects(
    gate: OutboundGate, net: FakeNet, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Each hop is quick enough on its own, but together they take too long."""
    monkeypatch.setattr(page_fetch, "MAX_FETCH_SECONDS", 0.5)
    hops: list[str] = []

    def site(request: Request) -> Reply:
        hops.append(request.line)
        if len(hops) <= 5:
            return Reply(
                status=302, headers={"Location": f"/hop{len(hops)}"}, body=b"moved", pause=0.2
            )
        return Reply()

    net.dns["recipes.example"] = [PUBLIC]
    net.page(PUBLIC, site)
    started = time.monotonic()
    assert refused(gate, "https://recipes.example/") is Problem.TIMEOUT
    assert time.monotonic() - started < 1.0
    assert len(hops) < 6


def test_a_fetch_that_has_run_out_of_time_looks_nothing_up(
    gate: OutboundGate, net: FakeNet, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(page_fetch, "MAX_FETCH_SECONDS", 0)
    net.dns["recipes.example"] = [PUBLIC]
    net.page(PUBLIC)
    assert refused(gate, "https://recipes.example/") is Problem.TIMEOUT
    assert net.lookups == [] and net.connections == []


def test_a_quick_answer_isnt_cut_later(
    gate: OutboundGate, net: FakeNet, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The watchdog stops with the request: nothing is cut after it has finished."""
    monkeypatch.setattr(outbound, "TIMEOUT_SECONDS", 0.2)
    net.dns["recipes.example"] = [PUBLIC]
    net.page(PUBLIC)
    for _ in range(3):
        assert fetch_page(gate, 1, "https://recipes.example/").html == PAGE.decode()
    time.sleep(0.3)
    assert threading.active_count() < 20


# --- Sizes and kinds -----------------------------------------------------------------------


def test_a_page_of_5_mb_is_fine_and_a_bigger_one_is_refused(
    gate: OutboundGate, net: FakeNet
) -> None:
    net.dns["big.example"] = [PUBLIC]
    net.page(PUBLIC, Reply(body=b"a" * MAX_PAGE_BYTES))
    assert len(fetch_page(gate, 1, "https://big.example/").html) == MAX_PAGE_BYTES
    net.page(PUBLIC, Reply(body=b"a" * (MAX_PAGE_BYTES + 1)))
    with pytest.raises(FetchRefused) as caught:
        fetch_page(gate, 1, "https://big.example/")
    assert caught.value.problem is Problem.PAGE_TOO_BIG
    assert caught.value.message == "That page is bigger than 5 MB."


def test_a_big_page_without_a_length_stops_being_read(
    gate: OutboundGate, net: FakeNet, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Reading stops just past 5 MB, whatever the site says about its length."""
    net.dns["endless.example"] = [PUBLIC]
    sent: list[int] = []

    def endless(server: socket.socket, site: Site, address: str, port: int) -> None:
        with server:
            data = b""
            while b"\r\n\r\n" not in data:
                data += server.recv(65536)
            try:
                server.sendall(b"HTTP/1.1 200 OK\r\nContent-Type: text/html\r\n\r\n")
                for _ in range(1000):  # up to 64 MB
                    server.sendall(b"a" * 65536)
                    sent.append(65536)
            except OSError:
                pass

    net.page(PUBLIC)
    monkeypatch.setattr(net, "_serve", endless)
    assert refused(gate, "https://endless.example/") is Problem.PAGE_TOO_BIG
    time.sleep(0.2)
    assert sum(sent) < 8 * 1024 * 1024


@pytest.mark.parametrize(
    "kind",
    ["text/html", "text/html; charset=UTF-8", "TEXT/HTML", "application/xhtml+xml; charset=utf-8"],
)
def test_web_pages_are_read(gate: OutboundGate, net: FakeNet, kind: str) -> None:
    net.dns["recipes.example"] = [PUBLIC]
    net.page(PUBLIC, Reply(headers={"Content-Type": kind}))
    assert fetch_page(gate, 1, "https://recipes.example/").html == PAGE.decode()


@pytest.mark.parametrize(
    "headers",
    [
        {"Content-Type": "application/json"},
        {"Content-Type": "application/pdf"},
        {"Content-Type": "text/plain"},
        {"Content-Type": "image/jpeg"},
        {"Content-Type": "application/octet-stream"},
        {},
    ],
)
def test_anything_else_isnt_a_web_page(
    gate: OutboundGate, net: FakeNet, headers: dict[str, str]
) -> None:
    net.dns["recipes.example"] = [PUBLIC]
    net.page(PUBLIC, Reply(headers=headers))
    with pytest.raises(FetchRefused) as caught:
        fetch_page(gate, 1, "https://recipes.example/recipe.pdf")
    assert caught.value.problem is Problem.NOT_A_PAGE
    assert caught.value.message == "This link isn’t a web page."


def test_the_gate_asks_about_the_kind_before_reading(gate: OutboundGate, net: FakeNet) -> None:
    net.page(PUBLIC, Reply(headers={"Content-Type": "application/json"}))
    with pytest.raises(WrongContentType):
        gate.get_pinned(
            1,
            Connection.RECIPE_IMPORT,
            "https://recipes.example/",
            ip_address(PUBLIC),
            accept=lambda kind: kind == "text/html",
        )


@pytest.mark.parametrize(
    ("headers", "body", "text"),
    [
        (
            {"Content-Type": "text/html; charset=iso-8859-1"},
            "Crème brûlée".encode("latin-1"),
            "Crème brûlée",
        ),
        (
            {"Content-Type": "text/html"},
            b'<meta charset="windows-1252"><p>\x93Rasam\x94',
            '<meta charset="windows-1252"><p>“Rasam”',
        ),
        (
            {"Content-Type": "text/html"},
            b'<meta http-equiv="Content-Type" content="text/html; charset=ISO-8859-1"><p>caf\xe9',
            '<meta http-equiv="Content-Type" content="text/html; charset=ISO-8859-1"><p>café',
        ),
        ({"Content-Type": "text/html"}, "﻿தக்காளி ரசம்".encode(), "தக்காளி ரசம்"),
        ({"Content-Type": "text/html"}, "टमाटर".encode(), "टमाटर"),
        ({"Content-Type": "text/html"}, b"bad \xff byte", "bad � byte"),
        ({"Content-Type": "text/html; charset=nonsense"}, "naïve".encode(), "naïve"),
    ],
)
def test_the_page_is_decoded_by_its_charset(
    gate: OutboundGate, net: FakeNet, headers: dict[str, str], body: bytes, text: str
) -> None:
    net.dns["recipes.example"] = [PUBLIC]
    net.page(PUBLIC, Reply(headers=headers, body=body))
    assert fetch_page(gate, 1, "https://recipes.example/").html == text


@pytest.mark.parametrize(
    "charset",
    [
        "zlib",
        "base64",
        "rot13",
        "hex",
        "uu",
        "bz2",
        "quopri",
        "idna",
        "punycode",
        "unicode_escape",
        "raw_unicode_escape",
        "utf-7",
        "undefined",
        "no-such-charset",
    ],
)
@pytest.mark.parametrize("where", ["header", "meta"])
def test_a_charset_that_isnt_a_text_encoding_is_read_as_utf_8(
    gate: OutboundGate, net: FakeNet, charset: str, where: str
) -> None:
    """Never an error past FetchRefused, and nothing is unpacked: the bytes are UTF-8."""
    body = "<p>naïve \\u0041 +AGE- eJw=</p>".encode() + b"\xff\x00"
    if where == "header":
        headers = {"Content-Type": f"text/html; charset={charset}"}
    else:
        headers = {"Content-Type": "text/html"}
        body = f'<meta charset="{charset}">'.encode() + body
    net.dns["recipes.example"] = [PUBLIC]
    net.page(PUBLIC, Reply(headers=headers, body=body))
    assert fetch_page(gate, 1, "https://recipes.example/").html == body.decode(
        "utf-8", errors="replace"
    )


# --- Addresses that are blocked ------------------------------------------------------------

OWN_NETWORK = [
    "10.0.0.1",
    "172.16.5.4",
    "192.168.1.20",
    "100.64.0.1",  # shared (CGNAT)
    "224.0.0.1",  # multicast
    "240.0.0.1",  # reserved
    "255.255.255.255",
    "fc00::1",  # unique-local
    "fd12:3456::1",
    "fec0::1",
    "ff02::1",  # multicast
    "2001:db8::1",
    "::ffff:192.168.1.20",  # IPv4-mapped
    "::ffff:10.0.0.1",
    "::192.168.1.20",  # IPv4-compatible
    "64:ff9b::c0a8:114",  # NAT64
    "2002:c0a8:114::1",  # 6to4
]
ALWAYS = [
    "127.0.0.1",
    "127.0.1.1",
    "0.0.0.0",  # noqa: S104 (an address to refuse, not one to listen on)
    "169.254.169.254",
    "169.254.1.1",
    "100.100.100.200",
    "::1",
    "::",
    "fe80::1",
    "fd00:ec2::254",
    "::ffff:127.0.0.1",
    "::ffff:169.254.169.254",
    "::127.0.0.1",
    "64:ff9b::a9fe:a9fe",
]


@pytest.mark.parametrize("address", OWN_NETWORK)
def test_a_name_on_the_own_network_is_refused(
    gate: OutboundGate, net: FakeNet, address: str
) -> None:
    net.dns["sneaky.example"] = [address]
    net.page(address)
    assert refused(gate, "https://sneaky.example/") is Problem.OWN_NETWORK
    assert net.connections == []


@pytest.mark.parametrize("address", ALWAYS)
def test_a_name_on_this_server_or_metadata_is_refused(
    gate: OutboundGate, net: FakeNet, address: str
) -> None:
    net.dns["sneaky.example"] = [address]
    net.page(address)
    assert refused(gate, "https://sneaky.example/") is Problem.ALWAYS_BLOCKED
    assert net.connections == []


@pytest.mark.parametrize("address", OWN_NETWORK + ALWAYS)
def test_an_address_link_is_refused_without_a_look_up(
    gate: OutboundGate, net: FakeNet, address: str
) -> None:
    host = f"[{address}]" if ":" in address else address
    assert refused(gate, f"http://{host}/latest/meta-data/") in {
        Problem.OWN_NETWORK,
        Problem.ALWAYS_BLOCKED,
    }
    assert net.lookups == [] and net.connections == []


@pytest.mark.parametrize("name", ["localhost", "LOCALHOST", "localhost.", "app.localhost"])
def test_localhost_is_refused_by_name(gate: OutboundGate, net: FakeNet, name: str) -> None:
    net.dns[name.lower().rstrip(".")] = [PUBLIC]
    assert refused(gate, f"http://{name}/") is Problem.ALWAYS_BLOCKED
    assert net.lookups == []


def test_every_address_of_a_name_is_checked(gate: OutboundGate, net: FakeNet) -> None:
    net.dns["mixed.example"] = [PUBLIC, "192.168.1.20"]
    net.page(PUBLIC)
    assert refused(gate, "https://mixed.example/") is Problem.OWN_NETWORK
    net.dns["mixed.example"] = [PUBLIC_6, PUBLIC, "169.254.169.254"]
    assert refused(gate, "https://mixed.example/") is Problem.ALWAYS_BLOCKED
    assert net.connections == []


def test_a_name_that_rebinds_is_fetched_from_the_address_that_was_checked(
    gate: OutboundGate, net: FakeNet
) -> None:
    """The name answers with a public address, then (for anyone asking again) a private one.
    The connection goes to the checked public address; the name is never looked up twice."""
    answers = [[PUBLIC], ["192.168.1.1"]]
    net.dns["rebind.example"] = lambda: answers.pop(0) if len(answers) > 1 else answers[0]
    net.page(PUBLIC)
    net.page("192.168.1.1", Reply(body=b"<p>the router's admin page</p>"))
    assert fetch_page(gate, 1, "https://rebind.example/").html == PAGE.decode()
    assert net.lookups == ["rebind.example"]
    assert net.connections == [(PUBLIC, 443)]
    assert net.requests[0].headers["host"] == "rebind.example"


def test_a_name_that_rebinds_on_a_redirect_is_checked_again(
    gate: OutboundGate, net: FakeNet
) -> None:
    answers = [[PUBLIC], ["192.168.1.1"]]
    net.dns["rebind.example"] = lambda: answers.pop(0) if len(answers) > 1 else answers[0]
    net.page(PUBLIC, Reply(status=302, headers={"Location": "/again"}))
    net.page("192.168.1.1")
    assert refused(gate, "https://rebind.example/") is Problem.OWN_NETWORK
    assert net.connections == [(PUBLIC, 443)]


# --- Redirects -----------------------------------------------------------------------------


def redirect(to: str, status: int = 302) -> Reply:
    return Reply(status=status, headers={"Location": to})


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirects_are_followed(gate: OutboundGate, net: FakeNet, status: int) -> None:
    net.dns["short.example"] = ["151.101.0.5"]
    net.dns["recipes.example"] = [PUBLIC]
    net.page("151.101.0.5", redirect("https://recipes.example/rasam", status))
    net.page(PUBLIC)
    page = fetch_page(gate, 1, "https://short.example/r/1")
    assert page.url == "https://recipes.example/rasam"
    assert page.html == PAGE.decode()
    assert net.requests[1].headers["host"] == "recipes.example"


def test_a_relative_redirect(gate: OutboundGate, net: FakeNet) -> None:
    net.dns["recipes.example"] = [PUBLIC]

    def site(request: Request) -> Reply:
        return redirect("../print/rasam") if "old" in request.line else Reply()

    net.page(PUBLIC, site)
    assert fetch_page(gate, 1, "https://recipes.example/old/rasam").url == (
        "https://recipes.example/print/rasam"
    )


@pytest.mark.parametrize(
    ("to", "problem"),
    [
        ("http://192.168.1.1/admin", Problem.OWN_NETWORK),
        ("http://router.example/", Problem.OWN_NETWORK),
        ("http://[fd12::1]/", Problem.OWN_NETWORK),
        ("http://localhost:8000/api/v1/", Problem.ALWAYS_BLOCKED),
        ("http://127.0.0.1/", Problem.ALWAYS_BLOCKED),
        ("http://169.254.169.254/latest/meta-data/", Problem.ALWAYS_BLOCKED),
        ("http://100.100.100.200/latest/meta-data/", Problem.ALWAYS_BLOCKED),
        ("http://[fd00:ec2::254]/", Problem.ALWAYS_BLOCKED),
        ("http://metadata.example/", Problem.ALWAYS_BLOCKED),
        ("file:///etc/passwd", Problem.BAD_LINK),
        ("gopher://recipes.example/", Problem.BAD_LINK),
        ("ftp://recipes.example/", Problem.BAD_LINK),
        ("https://recipes.example:8443/", Problem.ODD_PORT),
        ("http://recipes.example:22/", Problem.ODD_PORT),
    ],
)
def test_a_redirect_gets_every_check(
    gate: OutboundGate, net: FakeNet, to: str, problem: Problem
) -> None:
    net.dns["short.example"] = [PUBLIC]
    net.dns["recipes.example"] = ["151.101.0.5"]
    net.dns["router.example"] = ["192.168.1.1"]
    net.dns["metadata.example"] = ["169.254.169.254"]
    net.page(PUBLIC, redirect(to))
    for address in ("192.168.1.1", "127.0.0.1", "169.254.169.254", "100.100.100.200"):
        net.page(address, port=80)
    net.page("151.101.0.5", port=8443)
    net.page("151.101.0.5", port=22)
    assert refused(gate, "https://short.example/") is problem
    assert net.connections == [(PUBLIC, 443)]


def test_five_redirects_are_followed_and_a_sixth_is_refused(
    gate: OutboundGate, net: FakeNet
) -> None:
    net.dns["hops.example"] = [PUBLIC]

    def hops(request: Request) -> Reply:
        hop = int(request.line.split()[1].strip("/") or 0)
        return redirect(f"/{hop + 1}") if hop < limit else Reply()

    net.page(PUBLIC, hops)
    limit = 5
    assert fetch_page(gate, 1, "https://hops.example/0").url == "https://hops.example/5"
    net.connections.clear()
    limit = 6
    assert refused(gate, "https://hops.example/0") is Problem.TOO_MANY_REDIRECTS
    assert len(net.connections) == 6  # the 6th redirect isn't followed


@pytest.mark.parametrize("to", ["http://[abc", "http://[::1/x", "http://[::1]:99999999/"])
def test_a_redirect_to_an_address_that_cannot_be_used_is_refused_as_a_bad_link(
    gate: OutboundGate, net: FakeNet, to: str
) -> None:
    net.dns["recipes.example"] = [PUBLIC]
    net.page(PUBLIC, redirect(to))
    assert refused(gate, "https://recipes.example/") is Problem.BAD_LINK
    with pytest.raises(FetchRefused) as caught:
        download_photo(gate, 1, "https://recipes.example/photo.jpg")
    assert caught.value.problem is Problem.BAD_LINK


def test_a_redirect_address_python_cannot_split_is_a_bad_link_and_not_in_the_log(
    gate: OutboundGate, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A Location with a character that is invalid once normalised (NFKC): `urlsplit` raises
    ValueError. (Over real HTTP the header's bytes are Latin-1 text, so this is built here.)"""
    secret = "http://secret℀host.example/"

    def hop(*_args: object, **_kwargs: object) -> outbound.OutboundResponse:
        return outbound.OutboundResponse(302, {"Location": secret}, b"", "")

    monkeypatch.setattr(page_fetch, "_one_hop", hop)
    with caplog.at_level(logging.DEBUG):
        assert refused(gate, "https://recipes.example/") is Problem.BAD_LINK
    assert "secret" not in caplog.text


@pytest.mark.parametrize("status", [401, 403, 429])
def test_a_site_that_says_no_gets_its_own_plain_sentence(
    gate: OutboundGate, net: FakeNet, status: int
) -> None:
    """Allrecipes refused the 0.5 check's request (#36). The request is not changed; the
    sentence says what happened and the way on."""
    net.dns["recipes.example"] = [PUBLIC]
    net.page(PUBLIC, Reply(status=status))
    with pytest.raises(FetchRefused) as caught:
        fetch_page(gate, 1, "https://recipes.example/")
    assert caught.value.problem is Problem.SITE_REFUSED
    assert caught.value.message == (
        "That site wouldn’t let Mealwright read the page. Paste the recipe’s text instead."
    )
    assert caught.value.message == MESSAGES[Problem.SITE_REFUSED]


def test_a_photo_the_site_says_no_to_is_still_just_not_sent(
    gate: OutboundGate, net: FakeNet
) -> None:
    net.dns["images.recipes.example"] = [PUBLIC]
    net.page(PUBLIC, Reply(status=403))
    with pytest.raises(FetchRefused) as caught:
        download_photo(gate, 1, "https://images.recipes.example/rasam.jpg")
    assert caught.value.problem is Problem.SITE_ERROR


def test_a_redirect_without_an_address(gate: OutboundGate, net: FakeNet) -> None:
    net.dns["recipes.example"] = [PUBLIC]
    net.page(PUBLIC, Reply(status=302, headers={}))
    assert refused(gate, "https://recipes.example/") is Problem.SITE_ERROR


# --- Ports ---------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "link",
    [
        "https://recipes.example:443/",
        "http://recipes.example:80/",
        "https://recipes.example:80/",
        "http://recipes.example:443/",
    ],
)
def test_the_normal_ports(gate: OutboundGate, net: FakeNet, link: str) -> None:
    net.dns["recipes.example"] = [PUBLIC]
    net.page(PUBLIC, port=80)
    net.page(PUBLIC, port=443)
    assert fetch_page(gate, 1, link).html


@pytest.mark.parametrize("port", [8080, 8443, 22, 25, 6379, 1])
def test_an_unusual_port_is_refused(gate: OutboundGate, net: FakeNet, port: int) -> None:
    net.dns["recipes.example"] = [PUBLIC]
    net.page(PUBLIC, port=port)
    assert refused(gate, f"http://recipes.example:{port}/") is Problem.ODD_PORT
    assert net.connections == []


# --- The household's own network list ------------------------------------------------------


def test_a_listed_name_is_fetched_on_its_own_network(
    gate: OutboundGate, net: FakeNet, sessions: sessionmaker[Session]
) -> None:
    listing(sessions, "name", "wiki.home.example")
    net.dns["wiki.home.example"] = ["192.168.1.20", "fd12::20"]
    net.page("192.168.1.20", port=8080)
    assert fetch_page(gate, 1, "http://Wiki.Home.Example:8080/recipes/rasam").html
    assert net.connections == [("192.168.1.20", 8080)]
    # Another name with the same address isn't listed.
    net.dns["other.home.example"] = ["192.168.1.20"]
    assert refused(gate, "http://other.home.example:8080/") is Problem.OWN_NETWORK


def test_a_listed_range_opens_its_addresses(
    gate: OutboundGate, net: FakeNet, sessions: sessionmaker[Session]
) -> None:
    listing(sessions, "range", "192.168.1.0/24")
    net.dns["nas.lan"] = ["192.168.1.30"]
    net.page("192.168.1.30", port=80)
    net.page("192.168.1.30", port=5000)
    assert fetch_page(gate, 1, "http://nas.lan/").html
    assert fetch_page(gate, 1, "http://192.168.1.30/").html
    assert fetch_page(gate, 1, "http://[::ffff:192.168.1.30]/").html
    assert fetch_page(gate, 1, "http://nas.lan:5000/").html  # every address is listed
    net.dns["nas.lan"] = ["192.168.2.30"]
    assert refused(gate, "http://nas.lan/") is Problem.OWN_NETWORK
    net.dns["nas.lan"] = ["192.168.1.30", "192.168.2.30"]
    assert refused(gate, "http://nas.lan/") is Problem.OWN_NETWORK


def test_a_listed_public_address_opens_an_unusual_port(
    gate: OutboundGate, net: FakeNet, sessions: sessionmaker[Session]
) -> None:
    listing(sessions, "address", PUBLIC)
    net.dns["recipes.example"] = [PUBLIC]
    net.page(PUBLIC, port=8080)
    assert fetch_page(gate, 1, "http://recipes.example:8080/").html
    net.dns["recipes.example"] = [PUBLIC, "151.101.0.9"]
    assert refused(gate, "http://recipes.example:8080/") is Problem.ODD_PORT


@pytest.mark.parametrize(
    ("kind", "value", "address"),
    [
        ("name", "localhost", "127.0.0.1"),
        ("name", "wiki.home.example", "127.0.0.1"),
        ("name", "wiki.home.example", "169.254.169.254"),
        ("name", "wiki.home.example", "100.100.100.200"),
        ("name", "wiki.home.example", "fd00:ec2::254"),
        ("name", "wiki.home.example", "::1"),
        ("range", "127.0.0.0/8", "127.0.0.1"),
        ("range", "169.254.0.0/16", "169.254.169.254"),
        ("range", "100.64.0.0/10", "100.100.100.200"),
        ("range", "fd00::/8", "fd00:ec2::254"),
        ("range", "fe80::/10", "fe80::1"),
        ("address", "100.100.100.200", "100.100.100.200"),
    ],
)
def test_this_server_and_metadata_stay_blocked_when_listed(
    gate: OutboundGate,
    net: FakeNet,
    sessions: sessionmaker[Session],
    kind: str,
    value: str,
    address: str,
) -> None:
    """`own_network.add` refuses these entries; the fetch refuses them anyway."""
    listing(sessions, kind, value)
    name = value if kind == "name" else "wiki.home.example"
    net.dns[name] = [address]
    net.page(address, port=80)
    assert refused(gate, f"http://{name}/") is Problem.ALWAYS_BLOCKED
    host = f"[{address}]" if ":" in address else address
    assert refused(gate, f"http://{host}/") is Problem.ALWAYS_BLOCKED
    assert net.connections == []


def test_one_households_list_never_opens_anothers_fetches(
    gate: OutboundGate, net: FakeNet, sessions: sessionmaker[Session]
) -> None:
    listing(sessions, "range", "192.168.1.0/24", household=2)
    listing(sessions, "name", "wiki.home.example", household=2)
    net.dns["wiki.home.example"] = ["192.168.1.20"]
    net.page("192.168.1.20", port=80)
    assert fetch_page(gate, 2, "http://wiki.home.example/").html
    assert refused(gate, "http://wiki.home.example/", household=1) is Problem.OWN_NETWORK
    assert refused(gate, "http://192.168.1.20/", household=1) is Problem.OWN_NETWORK


# --- Log lines -----------------------------------------------------------------------------


def test_no_log_line_names_the_address_or_host(
    gate: OutboundGate,
    net: FakeNet,
    sessions: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A site name can show what someone was cooking, so it's never logged."""
    net.dns["secret-sambar.example"] = [PUBLIC]
    net.dns["home-router.example"] = ["192.168.77.1"]
    net.dns["meta-secret.example"] = ["169.254.169.254"]
    net.dns["slowsambar.example"] = ["151.101.0.77"]
    net.page(PUBLIC, redirect("http://home-router.example/sambar-admin"))
    net.page("151.101.0.77", Reply(status=500))
    links = [
        "https://secret-sambar.example/grandmas-sambar?from=search",
        "https://meta-secret.example/sambar",
        "http://192.168.77.1/sambar",
        "http://[fd12:77::1]/sambar",
        "https://secret-sambar.example:8077/sambar",
        "ftp://secret-sambar.example/sambar",
        "https://slowsambar.example/sambar",
        "https://nowhere-sambar.example/sambar",
    ]
    with caplog.at_level(logging.DEBUG):
        for link in links:
            with pytest.raises(FetchRefused) as caught:
                fetch_page(gate, 1, link)
            assert "sambar" not in str(caught.value)
        switch(sessions, Connection.RECIPE_IMPORT, False)
        with pytest.raises(FetchRefused):
            fetch_page(gate, 1, links[0])
        with pytest.raises(FetchRefused):
            download_photo(gate, 1, "https://meta-secret.example/sambar.jpg")
    assert caplog.records, "refusals are logged"
    for record in caplog.records:
        line = record.getMessage()
        assert line.startswith("Blocked outgoing connection: recipe ")
        for secret in (
            "sambar",
            "example",
            "192.168",
            "fd12",
            "169.254",
            "203.0.113",
            "93.184",
            "8077",
        ):
            assert secret not in line
    assert (
        "Blocked outgoing connection: recipe import, address on the own network that isn't listed"
        in caplog.messages
    )
    assert (
        "Blocked outgoing connection: recipe import, unusual port that isn't listed"
        in caplog.messages
    )


# --- The main photo ------------------------------------------------------------------------


def test_a_photo_is_downloaded_and_cleaned(gate: OutboundGate, net: FakeNet) -> None:
    net.dns["images.recipes.example"] = [PUBLIC]
    net.page(
        PUBLIC,
        Reply(headers={"Content-Type": "image/jpeg"}, body=photo_kit.jpeg(orientation=6)),
    )
    cleaned = download_photo(gate, 1, "https://images.recipes.example/rasam.jpg")
    opened = photo_kit.opened(cleaned.large)
    assert opened.format == "JPEG"
    assert opened.size == (300, 400)  # turned the right way up
    for secret in photo_kit.SECRETS:
        assert secret not in cleaned.large
    assert net.requests[0].headers["host"] == "images.recipes.example"


def test_the_photo_switch_is_its_own(
    gate: OutboundGate,
    net: FakeNet,
    sessions: sessionmaker[Session],
    caplog: pytest.LogCaptureFixture,
) -> None:
    switch(sessions, Connection.RECIPE_PHOTOS, False)
    net.dns["images.recipes.example"] = [PUBLIC]
    net.page(PUBLIC, Reply(headers={"Content-Type": "image/png"}, body=photo_kit.png()))
    with caplog.at_level(logging.DEBUG), pytest.raises(FetchRefused) as caught:
        download_photo(gate, 1, "https://images.recipes.example/rasam.png")
    assert caught.value.problem is Problem.PHOTO_SWITCHED_OFF
    assert caught.value.message == "Photo not downloaded"
    assert net.lookups == [] and net.connections == []
    assert caplog.messages == ["Blocked outgoing connection: recipe photos is switched off"]
    # The page switch doesn't need the photo switch, and the photo switch works alone.
    net.dns["recipes.example"] = [PUBLIC]
    switch(sessions, Connection.RECIPE_PHOTOS, True)
    switch(sessions, Connection.RECIPE_IMPORT, False)
    assert download_photo(gate, 1, "https://images.recipes.example/rasam.png").large


@pytest.mark.parametrize(
    ("kind", "body", "problem"),
    [
        ("text/html", PAGE, Problem.NOT_A_PHOTO),
        ("application/octet-stream", b"x", Problem.NOT_A_PHOTO),
        ("image/gif", photo_kit.gif(), Problem.NOT_A_PHOTO),
        ("image/svg+xml", photo_kit.SVG, Problem.NOT_A_PHOTO),
        ("image/jpeg", photo_kit.TEXT, Problem.NOT_A_PHOTO),
        ("image/png", photo_kit.png_header_only(8000, 7000), Problem.TOO_MANY_PIXELS),
    ],
)
def test_a_photo_that_cant_be_used(
    gate: OutboundGate, net: FakeNet, kind: str, body: bytes, problem: Problem
) -> None:
    net.dns["images.recipes.example"] = [PUBLIC]
    net.page(PUBLIC, Reply(headers={"Content-Type": kind}, body=body))
    with pytest.raises(FetchRefused) as caught:
        download_photo(gate, 1, "https://images.recipes.example/photo")
    assert caught.value.problem is problem


def test_a_photo_over_15_mb_is_refused(gate: OutboundGate, net: FakeNet) -> None:
    net.dns["images.recipes.example"] = [PUBLIC]
    net.page(
        PUBLIC, Reply(headers={"Content-Type": "image/jpeg"}, body=b"\xff" * (MAX_PHOTO_BYTES + 1))
    )
    with pytest.raises(FetchRefused) as caught:
        download_photo(gate, 1, "https://images.recipes.example/huge.jpg")
    assert caught.value.problem is Problem.PHOTO_TOO_BIG
    assert caught.value.message == "That photo is bigger than 15 MB."


@pytest.mark.parametrize(
    ("link", "problem"),
    [
        ("http://192.168.1.1/photo.jpg", Problem.OWN_NETWORK),
        ("http://169.254.169.254/photo.jpg", Problem.ALWAYS_BLOCKED),
        ("http://localhost/photo.jpg", Problem.ALWAYS_BLOCKED),
        ("https://images.recipes.example:8443/photo.jpg", Problem.ODD_PORT),
        ("data:image/png;base64,AAAA", Problem.BAD_LINK),
        ("https://moved.example/photo.jpg", Problem.OWN_NETWORK),
    ],
)
def test_a_photo_gets_the_same_address_checks(
    gate: OutboundGate, net: FakeNet, link: str, problem: Problem
) -> None:
    net.dns["images.recipes.example"] = [PUBLIC]
    net.dns["moved.example"] = ["151.101.0.5"]
    net.page("151.101.0.5", redirect("http://10.1.2.3/photo.jpg"))
    with pytest.raises(FetchRefused) as caught:
        download_photo(gate, 1, link)
    assert caught.value.problem is problem


# --- The name look-up counts towards the time too ------------------------------------------


class StuckResolver:
    """A name look-up that never answers until the test lets it go."""

    def __init__(self) -> None:
        self.release = threading.Event()
        self.asked: list[str] = []

    def lookup(self, host: str, port: int) -> list[str]:
        self.asked.append(host)
        self.release.wait(30)  # the test lets go at the end; this is only a safety net
        return [PUBLIC]


def let_go(resolver: StuckResolver) -> None:
    """Answer the stuck look-ups and wait for them to end. The running count is shared:
    one still counted when the next test starts its 16 makes that test's cap one short."""
    resolver.release.set()
    for thread in threading.enumerate():
        if thread.name == "name-look-up":
            thread.join(5)
    assert outbound._look_ups_running == 0


@pytest.fixture
def stuck(monkeypatch: pytest.MonkeyPatch) -> Iterator[StuckResolver]:
    resolver = StuckResolver()
    monkeypatch.setattr(outbound, "_lookup", resolver.lookup)
    yield resolver
    let_go(resolver)  # a late answer is thrown away


def test_a_look_up_waits_at_most_the_time_left(gate: OutboundGate, stuck: StuckResolver) -> None:
    started = time.monotonic()
    with pytest.raises(outbound.OutboundFailed) as caught:
        gate.look_up(
            1, Connection.RECIPE_IMPORT, "slow.example", 443, deadline=time.monotonic() + 0.3
        )
    assert caught.value.kind == "timeout"
    assert 0.25 < time.monotonic() - started < 1.0
    assert stuck.asked == ["slow.example"]


def test_a_look_up_with_no_time_left_looks_nothing_up(
    gate: OutboundGate, stuck: StuckResolver
) -> None:
    with pytest.raises(outbound.OutboundFailed) as caught:
        gate.look_up(
            1, Connection.RECIPE_IMPORT, "slow.example", 443, deadline=time.monotonic() - 1
        )
    assert caught.value.kind == "timeout"
    assert stuck.asked == []


def test_a_look_up_without_a_deadline_has_the_gates_own_limit(
    gate: OutboundGate, stuck: StuckResolver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(outbound, "TIMEOUT_SECONDS", 0.3)
    started = time.monotonic()
    with pytest.raises(outbound.OutboundFailed) as caught:
        gate.look_up(1, Connection.RECIPE_IMPORT, "slow.example", 443)
    assert caught.value.kind == "timeout"
    assert time.monotonic() - started < 1.0


def test_a_late_answer_is_thrown_away(gate: OutboundGate, stuck: StuckResolver) -> None:
    with pytest.raises(outbound.OutboundFailed):
        gate.look_up(
            1, Connection.RECIPE_IMPORT, "slow.example", 443, deadline=time.monotonic() + 0.1
        )
    stuck.release.set()  # the worker finishes now; nobody is waiting, and nothing breaks
    for thread in threading.enumerate():
        if thread.name == "name-look-up":
            thread.join(2)
    assert not any(t.name == "name-look-up" for t in threading.enumerate())


def test_past_sixteen_stuck_look_ups_a_new_one_times_out_at_once(
    gate: OutboundGate, stuck: StuckResolver, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The cap on stuck look-ups: 16 threads waiting on the resolver, then no more started."""
    assert outbound._look_ups_running == 0  # none left over from another test
    monkeypatch.setattr(outbound, "MAX_STUCK_PER_HOUSEHOLD", outbound.MAX_STUCK_LOOK_UPS)
    for number in range(outbound.MAX_STUCK_LOOK_UPS):
        with pytest.raises(outbound.OutboundFailed) as caught:
            gate.look_up(
                1,
                Connection.RECIPE_IMPORT,
                f"slow{number}.example",
                443,
                deadline=time.monotonic() + 0.05,
            )
        assert caught.value.kind == "timeout"
    asked = len(stuck.asked)
    started = time.monotonic()
    with pytest.raises(outbound.OutboundFailed) as caught:
        gate.look_up(1, Connection.RECIPE_IMPORT, "one-more.example", 443)  # 15 s if not capped
    assert caught.value.kind == "timeout"
    assert time.monotonic() - started < 1
    assert len(stuck.asked) == asked  # nothing was started for it
    stuck.release.set()
    for thread in threading.enumerate():
        if thread.name == "name-look-up":
            thread.join(2)
    # Once they have finished, look-ups work again.
    assert gate.look_up(1, Connection.RECIPE_IMPORT, "ok.example", 443) == [ip_address(PUBLIC)]


def test_one_household_cant_use_up_the_others_look_ups(
    gate: OutboundGate, stuck: StuckResolver
) -> None:
    """Past 4 stuck look-ups, a household's next one times out at once; another household's
    is still started (0.6 PR 8 security L1)."""
    for number in range(outbound.MAX_STUCK_PER_HOUSEHOLD):
        with pytest.raises(outbound.OutboundFailed):
            gate.look_up(
                1,
                Connection.RECIPE_IMPORT,
                f"slow{number}.example",
                443,
                deadline=time.monotonic() + 0.05,
            )
    asked = len(stuck.asked)
    with pytest.raises(outbound.OutboundFailed) as caught:
        gate.look_up(1, Connection.RECIPE_IMPORT, "one-more.example", 443)
    assert caught.value.kind == "timeout"
    assert len(stuck.asked) == asked  # nothing was started for household 1
    with pytest.raises(outbound.OutboundFailed):
        gate.look_up(
            2, Connection.RECIPE_IMPORT, "next-door.example", 443, deadline=time.monotonic() + 0.05
        )
    assert stuck.asked[-1] == "next-door.example"  # household 2's was started
    stuck.release.set()
    for thread in threading.enumerate():
        if thread.name == "name-look-up":
            thread.join(2)
    assert outbound._look_ups_running == 0 and outbound._look_ups_by_household == {}


def test_a_thread_start_that_fails_otherwise_still_gives_its_place_back(
    gate: OutboundGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Not only RuntimeError: any failed start takes its count back (0.6 PR 8 security L2)."""

    def refuse(self: threading.Thread) -> None:
        raise MemoryError

    before = outbound._look_ups_running
    with monkeypatch.context() as patched:
        patched.setattr(threading.Thread, "start", refuse)
        with pytest.raises(MemoryError):
            gate.look_up(1, Connection.RECIPE_IMPORT, "recipes.example", 443)
    assert outbound._look_ups_running == before
    assert 1 not in outbound._look_ups_by_household


def test_a_thread_that_cannot_start_is_unreachable_not_a_crash(
    gate: OutboundGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    def refuse(self: threading.Thread) -> None:
        raise RuntimeError("can't start new thread")

    before = outbound._look_ups_running
    with monkeypatch.context() as patched:
        patched.setattr(threading.Thread, "start", refuse)
        with pytest.raises(outbound.OutboundFailed) as caught:
            gate.look_up(1, Connection.RECIPE_IMPORT, "recipes.example", 443)
    assert caught.value.kind == "unreachable"
    # The count wasn't left raised by the failed start.
    assert outbound._look_ups_running == before


def test_a_quick_look_up_still_works_and_runs_inside_the_gate(
    gate: OutboundGate, monkeypatch: pytest.MonkeyPatch
) -> None:
    seen: list[bool] = []

    def lookup(host: str, port: int) -> list[str]:
        seen.append(network_guard.inside_gate.get())  # the worker's own thread
        return [PUBLIC, PUBLIC, PUBLIC_6]

    monkeypatch.setattr(outbound, "_lookup", lookup)
    found = gate.look_up(
        1, Connection.RECIPE_IMPORT, "recipes.example", 443, deadline=time.monotonic() + 5
    )
    assert found == [ip_address(PUBLIC), ip_address(PUBLIC_6)]
    assert seen == [True]
    assert not network_guard.inside_gate.get()  # and the caller's gate is still shut


def test_a_failed_look_up_is_still_unreachable(
    gate: OutboundGate, net: FakeNet, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(outbound.OutboundFailed) as caught:
        gate.look_up(1, Connection.RECIPE_IMPORT, "nowhere.example", 443)
    assert caught.value.kind == "unreachable"


def test_an_import_whose_look_up_hangs_ends_within_its_time(
    gate: OutboundGate, stuck: StuckResolver, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The import has 30 seconds in all; here a short stand-in, so the test is quick. The
    gate's own 15 seconds per step are far longer than the import's time left."""
    monkeypatch.setattr(page_fetch, "MAX_FETCH_SECONDS", 0.4)
    started = time.monotonic()
    assert refused(gate, "https://slow.example/sambar") is Problem.TIMEOUT
    assert 0.3 < time.monotonic() - started < 1.5
    assert stuck.asked == ["slow.example"]


def test_a_photo_look_up_that_hangs_ends_within_its_time(
    gate: OutboundGate, stuck: StuckResolver, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(page_fetch, "MAX_FETCH_SECONDS", 0.4)
    started = time.monotonic()
    with pytest.raises(FetchRefused) as caught:
        download_photo(gate, 1, "https://slow.example/sambar.jpg")
    assert caught.value.problem is Problem.TIMEOUT
    assert time.monotonic() - started < 1.5


def test_a_look_up_gets_only_what_the_import_has_left(
    gate: OutboundGate, stuck: StuckResolver
) -> None:
    """`seconds` (what the caller has left of the import) is passed on to the look-up."""
    started = time.monotonic()
    with pytest.raises(FetchRefused) as caught:
        fetch_page(gate, 1, "https://slow.example/sambar", seconds=0.3)
    assert caught.value.problem is Problem.TIMEOUT
    assert time.monotonic() - started < 1.0


def test_a_redirects_look_up_is_timed_too(
    gate: OutboundGate, net: FakeNet, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The first hop answers; the name the redirect points to never does."""
    resolver = StuckResolver()

    def lookup(host: str, port: int) -> list[str]:
        return net.lookup(host, port) if host == "first.example" else resolver.lookup(host, port)

    monkeypatch.setattr(outbound, "_lookup", lookup)
    monkeypatch.setattr(page_fetch, "MAX_FETCH_SECONDS", 0.5)
    net.dns["first.example"] = [PUBLIC]
    net.page(PUBLIC, redirect("https://second.example/sambar"))
    started = time.monotonic()
    try:
        assert refused(gate, "https://first.example/") is Problem.TIMEOUT
        assert time.monotonic() - started < 1.5
        assert resolver.asked == ["second.example"]
    finally:
        let_go(resolver)


def test_a_quick_look_up_still_fetches_within_the_time(
    gate: OutboundGate, net: FakeNet, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(page_fetch, "MAX_FETCH_SECONDS", 5)
    net.dns["recipes.example"] = [PUBLIC]
    net.page(PUBLIC)
    assert fetch_page(gate, 1, "https://recipes.example/").html


def test_a_stuck_look_up_logs_no_name_or_address(
    gate: OutboundGate,
    stuck: StuckResolver,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    monkeypatch.setattr(page_fetch, "MAX_FETCH_SECONDS", 0.3)
    with caplog.at_level(logging.DEBUG):
        assert refused(gate, "https://secret-sambar.example/grandmas-sambar") is Problem.TIMEOUT
    stuck.release.set()
    for thread in threading.enumerate():
        if thread.name == "name-look-up":
            thread.join(2)
    for record in caplog.records:
        line = record.getMessage()
        assert "sambar" not in line and "example" not in line and PUBLIC not in line
