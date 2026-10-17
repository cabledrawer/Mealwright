"""The outbound gate and the network guard (spec section 7)."""

import ast
import logging
import socket
import socketserver
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import ClassVar
from urllib.parse import urlsplit

import pytest
from sqlalchemy.orm import Session, sessionmaker

from mealwright import migrate
from mealwright.config import Settings
from mealwright.db import make_engine, make_sessionmaker
from mealwright.main import create_app
from mealwright.models import Household
from mealwright.outbound import (
    LABELS,
    USER_AGENT,
    Connection,
    OutboundBlocked,
    OutboundGate,
    set_switch,
    switches,
)

SRC = Path(__file__).parent.parent / "src" / "mealwright"
SCRIPTS = Path(__file__).parent.parent / "scripts"


# --- A small local web server to talk to -----------------------------------------


class _Server(HTTPServer):
    def server_bind(self) -> None:
        # HTTPServer normally looks up its own host name, which the guard refuses.
        socketserver.TCPServer.server_bind(self)
        self.server_name, self.server_port = "localhost", self.server_address[1]


class _Handler(BaseHTTPRequestHandler):
    hits: ClassVar[list[dict[str, str]]] = []

    def do_GET(self) -> None:
        type(self).hits.append(dict(self.headers.items()))
        if self.path == "/redirect":
            self.send_response(302)
            self.send_header("Location", "/hello")
            self.end_headers()
            return
        body = b"x" * 2048 if self.path == "/big" else b"hello"
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args: object) -> None:
        pass


@pytest.fixture
def server() -> Iterator[str]:
    _Handler.hits = []
    httpd = _Server(("127.0.0.1", 0), _Handler)
    thread = threading.Thread(target=httpd.serve_forever, args=(0.02,), daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()


@pytest.fixture
def sessions(tmp_path: Path) -> sessionmaker[Session]:
    engine = make_engine(f"sqlite:///{tmp_path / 'test.db'}")
    migrate.upgrade(engine)
    factory = make_sessionmaker(engine)
    with factory() as session:
        session.add(Household(id=1, name="Home"))
        session.commit()
    return factory


@pytest.fixture
def gate(sessions: sessionmaker[Session]) -> OutboundGate:
    return OutboundGate(sessions)


def switch(sessions: sessionmaker[Session], connection: Connection, on: bool) -> None:
    with sessions() as session:
        set_switch(session, 1, connection, on)
        session.commit()


# --- Privacy switches ------------------------------------------------------------------


def test_every_switch_starts_off(sessions: sessionmaker[Session]) -> None:
    with sessions() as session:
        assert switches(session, 1) == dict.fromkeys(Connection, False)


def test_switch_on_and_off(sessions: sessionmaker[Session]) -> None:
    switch(sessions, Connection.RECIPE_IMPORT, True)
    with sessions() as session:
        assert switches(session, 1)[Connection.RECIPE_IMPORT] is True
        assert switches(session, 1)[Connection.RECIPE_PHOTOS] is False
    switch(sessions, Connection.RECIPE_IMPORT, False)
    with sessions() as session:
        assert switches(session, 1)[Connection.RECIPE_IMPORT] is False


def test_switch_for_unknown_household(sessions: sessionmaker[Session]) -> None:
    with sessions() as session, pytest.raises(ValueError):
        set_switch(session, 99, Connection.RECIPE_IMPORT, True)


# --- The gate ---------------------------------------------------------------------------


def test_blocked_when_switched_off(gate: OutboundGate, server: str) -> None:
    with pytest.raises(OutboundBlocked):
        gate.request(1, Connection.RECIPE_IMPORT, f"{server}/hello")
    assert _Handler.hits == []  # nothing was sent at all


def test_blocked_line_names_only_the_switch(
    gate: OutboundGate, server: str, caplog: pytest.LogCaptureFixture
) -> None:
    """A site name can show what someone was cooking, so it's never logged (cabledrawer 17 Oct)."""
    url = f"{server}/recipes/grandmas-secret-sambar?from=search"
    with caplog.at_level(logging.DEBUG), pytest.raises(OutboundBlocked) as blocked:
        gate.request(1, Connection.RECIPE_IMPORT, url)
    assert caplog.messages == ["Blocked outgoing connection: recipe import is switched off"]
    host = urlsplit(server).hostname or ""
    for secret in (url, host, "sambar", "recipes/"):
        assert secret not in caplog.text
        assert secret not in str(blocked.value)


def test_every_switch_has_plain_words() -> None:
    assert set(LABELS) == set(Connection)
    assert all("_" not in label for label in LABELS.values())


def test_switch_is_per_connection(
    gate: OutboundGate, sessions: sessionmaker[Session], server: str
) -> None:
    switch(sessions, Connection.RECIPE_PHOTOS, True)
    with pytest.raises(OutboundBlocked):
        gate.request(1, Connection.RECIPE_IMPORT, f"{server}/hello")
    assert _Handler.hits == []


def test_unknown_household_is_blocked(gate: OutboundGate, server: str) -> None:
    with pytest.raises(OutboundBlocked):
        gate.request(99, Connection.RECIPE_IMPORT, f"{server}/hello")


def test_allowed_when_switched_on(
    gate: OutboundGate, sessions: sessionmaker[Session], server: str
) -> None:
    switch(sessions, Connection.RECIPE_IMPORT, True)
    response = gate.request(1, Connection.RECIPE_IMPORT, f"{server}/hello")
    assert (response.status, response.body) == (200, b"hello")
    sent = _Handler.hits[0]
    assert sent["User-Agent"] == USER_AGENT
    assert "Cookie" not in sent


def test_redirects_are_not_followed(
    gate: OutboundGate, sessions: sessionmaker[Session], server: str
) -> None:
    switch(sessions, Connection.RECIPE_IMPORT, True)
    response = gate.request(1, Connection.RECIPE_IMPORT, f"{server}/redirect")
    assert response.status == 302
    assert response.headers["Location"] == "/hello"
    assert len(_Handler.hits) == 1


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/x", "data:,hi"])
def test_only_http_and_https(gate: OutboundGate, sessions: sessionmaker[Session], url: str) -> None:
    switch(sessions, Connection.RECIPE_IMPORT, True)
    with pytest.raises(OutboundBlocked):
        gate.request(1, Connection.RECIPE_IMPORT, url)


def test_response_size_limit(
    gate: OutboundGate, sessions: sessionmaker[Session], server: str
) -> None:
    switch(sessions, Connection.RECIPE_IMPORT, True)
    with pytest.raises(OutboundBlocked):
        gate.request(1, Connection.RECIPE_IMPORT, f"{server}/big", max_bytes=1024)


# --- The network guard (on for the whole test suite, see conftest.py) ------------------


def test_guard_blocks_direct_connections(server: str) -> None:
    port = int(server.rsplit(":", 1)[1])
    with pytest.raises(OutboundBlocked):
        socket.create_connection(("127.0.0.1", port), timeout=2)
    assert _Handler.hits == []


def test_guard_blocks_urllib(server: str) -> None:
    with pytest.raises(urllib.error.URLError) as caught:
        urllib.request.urlopen(f"{server}/hello", timeout=2)  # noqa: S310
    assert isinstance(caught.value.reason, OutboundBlocked)
    assert _Handler.hits == []


def test_guard_blocks_dns_lookups() -> None:
    with pytest.raises(OutboundBlocked):
        socket.getaddrinfo("example.com", 443)
    with pytest.raises(OutboundBlocked):
        socket.gethostbyname("example.com")


def test_guard_allows_local_lookups() -> None:
    socket.getaddrinfo("127.0.0.1", 80)
    socket.getaddrinfo(None, 80)
    socket.getaddrinfo("localhost", 80)


def test_guard_blocks_udp() -> None:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as udp, pytest.raises(OutboundBlocked):
        udp.sendto(b"hi", ("127.0.0.1", 9))


def test_guard_allows_unix_sockets(tmp_path: Path) -> None:
    path = str(tmp_path / "s")
    with socket.socket(socket.AF_UNIX) as listener:
        listener.bind(path)
        listener.listen(1)
        with socket.socket(socket.AF_UNIX) as client:
            client.connect(path)


def test_app_has_the_gate(settings: Settings) -> None:
    app = create_app(settings)
    assert isinstance(app.state.outbound, OutboundGate)


# --- Only the gate may import networking modules ---------------------------------------

NETWORK_MODULES = {
    "socket",
    "ssl",
    "http.client",
    "urllib.request",
    "urllib3",
    "httpx",
    "httpcore",
    "requests",
    "aiohttp",
    "websockets",
    "smtplib",
    "ftplib",
    "imaplib",
    "poplib",
    "xmlrpc.client",
}
ALLOWED_FILES = {SRC / "outbound.py"}


def _imports(path: Path) -> set[str]:
    found: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
        if isinstance(node, ast.Import):
            found.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            found.add(node.module)
            found.update(f"{node.module}.{alias.name}" for alias in node.names)
    return found


def _is_network(module: str) -> bool:
    return any(module == m or module.startswith(m + ".") for m in NETWORK_MODULES)


def test_only_the_gate_imports_network_modules() -> None:
    offenders = {
        f"{path.relative_to(SRC.parent.parent)}: {module}"
        for path in [*SRC.rglob("*.py"), *SCRIPTS.rglob("*.py")]
        if path not in ALLOWED_FILES
        for module in _imports(path)
        if _is_network(module)
    }
    assert not offenders, f"use mealwright.outbound instead: {sorted(offenders)}"


def test_import_check_catches_a_network_import(tmp_path: Path) -> None:
    sample = tmp_path / "sample.py"
    sample.write_text("from urllib import request\nimport httpx.client\n")
    assert {m for m in _imports(sample) if _is_network(m)} == {"urllib.request", "httpx.client"}
