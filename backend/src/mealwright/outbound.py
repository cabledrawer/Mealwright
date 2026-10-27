"""The outbound gate: the only way Mealwright connects to anything outside the server.

Spec section 7: every outgoing connection passes through one place, which checks the
household's Privacy switches (Settings → Privacy). Anything not switched on is blocked.

Two parts:

- `OutboundGate.request()` makes an HTTP(S) request for one kind of connection, only if
  that connection's switch is on. It sends no cookies, never follows redirects by itself
  (callers check each hop, e.g. for SSRF in recipe import), and its user agent is just
  "Mealwright", with no version or anything about the install (spec section 7).
- `OutboundGate.look_up()` and `OutboundGate.get_pinned()` are the two halves of a request
  whose address the caller checks first (recipe import, `mealwright.page_fetch`): look the
  name up, check every address, then connect to exactly the address that was checked,
  while the Host header and the TLS name (SNI and the certificate check) stay the host
  name. So a name can't pass the check with a public address and then be fetched from a
  private one (DNS rebinding).
- `install_network_guard()` (it lives in `mealwright.network_guard`, a small module of its own,
  so the page-reading child can switch it on without importing all of this) adds a Python audit
  hook that refuses every network connection, UDP send or DNS lookup made *outside* the gate, by
  our code or by any library. It's installed when the app starts and for the whole test suite.

This is the only module allowed to import networking modules; a test checks that.
"""

import http.client
import ipaddress
import logging
import socket
import ssl
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from mealwright.models import Household, OutboundSwitch
from mealwright.network_guard import OutboundBlocked as OutboundBlocked  # (re-exported)
from mealwright.network_guard import gate_open
from mealwright.network_guard import install_network_guard as install_network_guard

log = logging.getLogger(__name__)

USER_AGENT = "Mealwright"  # no version and nothing about the install
TIMEOUT_SECONDS = 15
MAX_RESPONSE_BYTES = 10 * 1024 * 1024


class Connection(StrEnum):
    """Every kind of outside connection Mealwright can make. Each has its own switch."""

    RECIPE_IMPORT = "recipe_import"  # fetch a recipe page the user asked for (0.5)
    RECIPE_PHOTOS = "recipe_photos"  # download that recipe's photos (0.5)
    UPDATE_CHECK = "update_check"  # GitHub's public release list (0.8)
    NOTIFICATIONS = "notifications"  # the household's own Apprise targets (0.8)
    SINGLE_SIGN_ON = "single_sign_on"  # the household's own identity provider (0.8)


# Each switch in plain words, as Settings → Privacy will name it. Log lines about a
# connection use these only, never the address: a site name can show what someone was
# cooking, and logs never record what people cook, buy or type (cabledrawer 17 Oct).
LABELS = {
    Connection.RECIPE_IMPORT: "recipe import",
    Connection.RECIPE_PHOTOS: "recipe photos",
    Connection.UPDATE_CHECK: "the update check",
    Connection.NOTIFICATIONS: "notifications",
    Connection.SINGLE_SIGN_ON: "single sign-on",
}


class ResponseTooLarge(OutboundBlocked):
    """The answer was bigger than the caller allows; reading stopped there."""


class WrongContentType(OutboundBlocked):
    """The answer isn't the kind the caller asked for; its body wasn't read."""


class OutboundFailed(Exception):
    """A connection that was allowed didn't work. `kind` says how, in a word ("timeout",
    "unreachable", "tls" or "bad_answer"); nothing else is kept, because the library's own
    message can name the host."""

    def __init__(self, kind: str) -> None:
        super().__init__(kind)
        self.kind = kind


@dataclass(frozen=True)
class OutboundResponse:
    status: int
    headers: dict[str, str]
    body: bytes
    url: str


# --- Privacy switches ----------------------------------------------------------


def switches(session: Session, household_id: int) -> dict[Connection, bool]:
    """Every connection's switch for a household. Missing rows mean off."""
    rows = session.scalars(
        select(OutboundSwitch).where(OutboundSwitch.household_id == household_id)
    ).all()
    stored = {row.connection: row.enabled for row in rows}
    return {connection: stored.get(connection.value, False) for connection in Connection}


def set_switch(session: Session, household_id: int, connection: Connection, on: bool) -> None:
    """Turn one switch on or off. The caller commits."""
    if session.get(Household, household_id) is None:
        raise ValueError(f"no household {household_id}")
    row = session.get(OutboundSwitch, (household_id, connection.value))
    if row is None:
        session.add(
            OutboundSwitch(household_id=household_id, connection=connection.value, enabled=on)
        )
    else:
        row.enabled = on


# --- The gate --------------------------------------------------------------------


class _NoRedirects(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args: Any, **kwargs: Any) -> None:
        return None  # hand the 3xx back to the caller


def _lookup(host: str, port: int) -> list[str]:
    """Every address a name has (only ever called inside the gate)."""
    found = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM, proto=socket.IPPROTO_TCP)
    return [str(info[4][0]) for info in found]


# How many name look-ups may be stuck at once. A look-up that is still going when its time is up
# keeps its thread until the resolver gives up, so a stuck resolver could pile threads up; past
# this many, a new look-up gets the usual "took too long" answer at once and starts nothing.
MAX_STUCK_LOOK_UPS = 16
_look_ups_running = 0
_look_ups_lock = threading.Lock()


def _look_up_within(host: str, port: int, seconds: float) -> list[str]:
    """`_lookup(host, port)`, waited for at most `seconds` (OutboundFailed("timeout") after).

    `getaddrinfo` can't be cut short, so it runs on a worker thread and, if it is still
    going when time is up, we stop waiting for it and throw its answer away when it comes.
    That thread isn't killed: the system resolver's own limit ends it (a few seconds to a
    minute or so, depending on the machine's settings), and it holds nothing but the name.
    It is a daemon thread, so it never keeps the server from stopping. Worst case, one
    import leaves two such threads behind (its page and its photo; a timeout on the page
    ends the import), and they pile up only as fast as imports are started while the
    resolver is stuck.

    At most `MAX_STUCK_LOOK_UPS` look-ups run at once; past that, OutboundFailed("timeout") at
    once, the answer a look-up that never finishes gets anyway. If the system can't start
    another thread, OutboundFailed("unreachable").

    The worker opens the gate itself: the guard's "inside the gate" flag is per thread
    context, and a new thread doesn't inherit the caller's."""
    global _look_ups_running
    done = threading.Event()
    outcome: list[list[str] | Exception] = []

    def work() -> None:
        global _look_ups_running
        try:
            with gate_open():
                outcome.append(_lookup(host, port))
        except Exception as error:  # handed to the waiting caller (thrown away if late)
            outcome.append(error)
        finally:
            with _look_ups_lock:
                _look_ups_running -= 1
            done.set()

    with _look_ups_lock:
        if _look_ups_running >= MAX_STUCK_LOOK_UPS:
            raise OutboundFailed("timeout")
        _look_ups_running += 1
    try:
        threading.Thread(target=work, name="name-look-up", daemon=True).start()
    except RuntimeError:  # no thread to be had: the same as not reaching the name
        with _look_ups_lock:
            _look_ups_running -= 1
        raise OutboundFailed("unreachable") from None
    if not done.wait(seconds):
        raise OutboundFailed("timeout")
    answer = outcome[0]
    if isinstance(answer, OSError | UnicodeError):
        raise OutboundFailed("unreachable") from None
    if isinstance(answer, Exception):
        raise answer
    return answer


def _open_socket(address: str, port: int, timeout: float | None) -> socket.socket:
    """A TCP connection to exactly this address (only ever called inside the gate)."""
    return socket.create_connection((address, port), timeout=timeout)


class _PinnedHTTP(http.client.HTTPConnection):
    """Plain HTTP to one checked address; the Host header is still the host name."""

    def __init__(self, host: str, port: int, address: str, timeout: float) -> None:
        super().__init__(host, port, timeout=timeout)
        self._address = address
        self.raw: socket.socket | None = None
        self.cut = False  # set by the watchdog when time runs out

    def connect(self) -> None:
        self.sock = self.raw = _open_socket(self._address, self.port, self.timeout)
        _stop_if_cut(self)


class _PinnedHTTPS(http.client.HTTPSConnection):
    """HTTPS to one checked address; the Host header, SNI and certificate check all use
    the host name."""

    def __init__(
        self, host: str, port: int, address: str, timeout: float, tls: ssl.SSLContext
    ) -> None:
        super().__init__(host, port, timeout=timeout, context=tls)
        self._address = address
        self._tls = tls
        self.raw: socket.socket | None = None
        self.cut = False  # set by the watchdog when time runs out

    def connect(self) -> None:
        plain = _open_socket(self._address, self.port, self.timeout)
        try:
            wrapped = self._tls.wrap_socket(
                plain, server_hostname=self.host, do_handshake_on_connect=False
            )
        except BaseException:
            plain.close()
            raise
        # The socket is known before the handshake, so the watchdog can cut a handshake
        # that trickles too.
        self.sock = self.raw = wrapped
        _stop_if_cut(self)
        if isinstance(wrapped, ssl.SSLSocket):
            wrapped.do_handshake()


def _stop_if_cut(pinned: _PinnedHTTP | _PinnedHTTPS) -> None:
    """Called once the socket is stored. If the watchdog fired while connecting, it found
    no socket to cut, so the request stops here instead of carrying on without a limit.
    The watchdog sets `cut` before it looks for the socket and the socket is stored before
    `cut` is read, so one of the two always sees the other."""
    if pinned.cut:
        raise TimeoutError


class _Watchdog:
    """Cuts the connection when the time limit is reached, wherever the request has got to
    (connecting, the TLS handshake, the status line, the headers, a chunk-size line or the
    body). A socket timeout only limits each wait, so without this a site sending a byte
    every few seconds could hold a request for as long as it liked."""

    def __init__(self, pinned: _PinnedHTTP | _PinnedHTTPS, seconds: float) -> None:
        self._pinned = pinned
        self._lock = threading.Lock()
        self._done = False
        self.expired = False
        self._timer = threading.Timer(seconds, self._cut)
        self._timer.daemon = True

    def __enter__(self) -> _Watchdog:
        self._timer.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self._timer.cancel()
        with self._lock:
            self._done = True  # the connection is about to be closed: never cut it after

    def _cut(self) -> None:
        with self._lock:
            if self._done:
                return
            self.expired = True
            self._pinned.cut = True  # before looking for the socket: see _stop_if_cut
            raw = self._pinned.raw
            if raw is not None:
                with suppress(OSError):
                    # The plain socket's own shutdown wakes a read that is waiting, even
                    # inside TLS (SSLSocket.shutdown would try to unwrap it first).
                    socket.socket.shutdown(raw, socket.SHUT_RDWR)


class OutboundGate:
    def __init__(self, sessions: sessionmaker[Session], tls: ssl.SSLContext | None = None) -> None:
        self._sessions = sessions
        # Certificates are checked against the host name, with the system's trusted list.
        self._tls = tls if tls is not None else ssl.create_default_context()
        # No proxies from the environment, no cookies, no automatic redirects.
        self._opener = urllib.request.OpenerDirector()
        for handler in (
            urllib.request.UnknownHandler(),
            urllib.request.HTTPHandler(),
            urllib.request.HTTPSHandler(),
            urllib.request.HTTPDefaultErrorHandler(),
            urllib.request.HTTPErrorProcessor(),
            _NoRedirects(),
        ):
            self._opener.add_handler(handler)

    @property
    def sessions(self) -> sessionmaker[Session]:
        """The database, for callers that check the household's own network list."""
        return self._sessions

    def is_allowed(self, household_id: int, connection: Connection) -> bool:
        with self._sessions() as session:
            return switches(session, household_id)[connection]

    def check_switch(self, household_id: int, connection: Connection) -> None:
        """Raise OutboundBlocked (and log it) unless the connection's switch is on."""
        if not self.is_allowed(household_id, connection):
            # Log the switch only, never the address or site (see LABELS).
            log.warning("Blocked outgoing connection: %s is switched off", LABELS[connection])
            raise OutboundBlocked(f"{LABELS[connection]} is switched off in Settings → Privacy")

    def request(
        self,
        household_id: int,
        connection: Connection,
        url: str,
        *,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        body: bytes | None = None,
        max_bytes: int = MAX_RESPONSE_BYTES,
    ) -> OutboundResponse:
        self.check_switch(household_id, connection)
        if urlsplit(url).scheme not in {"http", "https"}:
            raise OutboundBlocked("only http and https addresses are allowed")

        request = urllib.request.Request(url, data=body, method=method)  # noqa: S310 (scheme checked above)
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        request.add_header("User-Agent", USER_AGENT)

        with gate_open():
            try:
                response = self._opener.open(request, timeout=TIMEOUT_SECONDS)
            except urllib.error.HTTPError as error:  # 3xx (not followed), 4xx, 5xx
                response = error
            with response:
                data = response.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise ResponseTooLarge(f"response is larger than {max_bytes} bytes")
                return OutboundResponse(
                    status=response.status,
                    headers=dict(response.headers.items()),
                    body=data,
                    url=url,
                )

    def look_up(
        self,
        household_id: int,
        connection: Connection,
        host: str,
        port: int,
        *,
        deadline: float | None = None,
    ) -> list[ipaddress.IPv4Address | ipaddress.IPv6Address]:
        """Every address a host name has, in the resolver's order, without repeats. Only if
        the connection's switch is on; nothing is looked up otherwise.

        The look-up waits at most the gate's time limit, or until `deadline` (a
        `time.monotonic()` value, for a caller's limit across several steps) if that comes
        first; past it, OutboundFailed("timeout"). With no time left, nothing is looked up."""
        self.check_switch(household_id, connection)
        own = time.monotonic() + TIMEOUT_SECONDS
        deadline = own if deadline is None else min(own, deadline)
        left = deadline - time.monotonic()
        if left <= 0:
            raise OutboundFailed("timeout")
        found = _look_up_within(host, port, left)
        addresses: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = []
        for text in found:
            try:
                address = ipaddress.ip_address(text)
            except ValueError:
                continue
            if address not in addresses:
                addresses.append(address)
        return addresses

    def get_pinned(
        self,
        household_id: int,
        connection: Connection,
        url: str,
        address: ipaddress.IPv4Address | ipaddress.IPv6Address,
        *,
        max_bytes: int = MAX_RESPONSE_BYTES,
        accept: Callable[[str], bool] | None = None,
        deadline: float | None = None,
    ) -> OutboundResponse:
        """GET `url` from exactly `address`, which the caller has already checked. The Host
        header and the TLS name stay the URL's host name. Redirects are handed back, not
        followed. `accept`, if given, is asked about a successful answer's content type
        ("text/html"; "" if there's none) before its body is read: False raises
        WrongContentType. Reading stops past `max_bytes` (ResponseTooLarge).

        Everything (connecting, the TLS handshake, the headers and the whole body) must
        finish within the gate's time limit, or by `deadline` (a `time.monotonic()` value,
        for a caller's limit across several requests) if that comes first. Otherwise the
        connection is cut and OutboundFailed("timeout") is raised. A connection that fails
        raises OutboundFailed, which never carries the library's own message."""
        self.check_switch(household_id, connection)
        parts = urlsplit(url)
        host = parts.hostname
        if parts.scheme not in {"http", "https"} or not host:
            raise OutboundBlocked("only http and https addresses are allowed")
        port = parts.port if parts.port is not None else (443 if parts.scheme == "https" else 80)
        selector = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        if port == 0:
            raise OutboundBlocked("port 0 can't be used")
        own = time.monotonic() + TIMEOUT_SECONDS
        deadline = own if deadline is None else min(own, deadline)
        left = deadline - time.monotonic()
        if left <= 0:
            raise OutboundFailed("timeout")
        pinned: _PinnedHTTP | _PinnedHTTPS
        if parts.scheme == "https":
            pinned = _PinnedHTTPS(host, port, str(address), left, self._tls)
        else:
            pinned = _PinnedHTTP(host, port, str(address), left)
        with gate_open(), _Watchdog(pinned, left) as watchdog:

            def failed(kind: str) -> OutboundFailed:
                # A cut connection fails in many ways; they all mean time ran out.
                return OutboundFailed("timeout" if watchdog.expired else kind)

            try:
                pinned.request("GET", selector, headers={"User-Agent": USER_AGENT})
                response = pinned.getresponse()
                headers = dict(response.headers.items())
                if accept is not None and 200 <= response.status < 300:
                    kind = (
                        response.headers.get_content_type()
                        if response.headers.get("Content-Type")
                        else ""
                    )
                    if not accept(kind):
                        raise WrongContentType("the answer isn't the kind asked for")
                body = _read(response, pinned.raw, max_bytes, deadline)
                if watchdog.expired:
                    raise TimeoutError  # cut: the body may be only part of the answer
                return OutboundResponse(status=response.status, headers=headers, body=body, url=url)
            except OutboundBlocked:
                if watchdog.expired:
                    raise failed("timeout") from None
                raise
            except TimeoutError:
                raise failed("timeout") from None
            except ssl.SSLError, ssl.CertificateError:
                raise failed("tls") from None
            except http.client.HTTPException, ValueError:
                raise failed("bad_answer") from None
            except OSError:
                raise failed("unreachable") from None
            finally:
                pinned.close()


def _read(
    response: http.client.HTTPResponse,
    raw: socket.socket | None,
    max_bytes: int,
    deadline: float,
) -> bytes:
    """The body, up to `max_bytes`, read before `deadline`."""
    chunks: list[bytes] = []
    total = 0
    while True:
        left = deadline - time.monotonic()
        if left <= 0:
            raise TimeoutError
        if response.isclosed():
            return b"".join(chunks)  # the whole answer has arrived
        if raw is not None:
            # Each read may only wait for what's left of the time limit.
            raw.settimeout(min(left, TIMEOUT_SECONDS))
        chunk = response.read1(64 * 1024)
        if not chunk:
            return b"".join(chunks)
        total += len(chunk)
        if total > max_bytes:
            raise ResponseTooLarge(f"response is larger than {max_bytes} bytes")
        chunks.append(chunk)
