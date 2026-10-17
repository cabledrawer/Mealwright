"""The outbound gate: the only way Mealwright connects to anything outside the server.

Spec section 7: every outgoing connection passes through one place, which checks the
household's Privacy switches (Settings → Privacy). Anything not switched on is blocked.

Two parts:

- `OutboundGate.request()` makes an HTTP(S) request for one kind of connection, only if
  that connection's switch is on. It sends no cookies, never follows redirects by itself
  (callers check each hop, e.g. for SSRF in recipe import), and its user agent is just
  "Mealwright", with no version or anything about the install (spec section 7).
- `install_network_guard()` adds a Python audit hook that refuses every network
  connection, UDP send or DNS lookup made *outside* the gate, by our code or by any
  library. It's installed when the app starts and for the whole test suite.

This is the only module allowed to import networking modules; a test checks that.
"""

import contextvars
import ipaddress
import logging
import socket
import sys
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from enum import StrEnum
from typing import Any
from urllib.parse import urlsplit

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from mealwright.models import Household, OutboundSwitch

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


class OutboundBlocked(PermissionError):
    """An outgoing connection was refused."""


@dataclass(frozen=True)
class OutboundResponse:
    status: int
    headers: dict[str, str]
    body: bytes
    url: str


# True only while the gate itself is connecting. The network guard checks it.
_inside_gate: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "mealwright_inside_gate", default=False
)


@contextmanager
def _gate_open() -> Iterator[None]:
    token = _inside_gate.set(True)
    try:
        yield
    finally:
        _inside_gate.reset(token)


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


class OutboundGate:
    def __init__(self, sessions: sessionmaker[Session]) -> None:
        self._sessions = sessions
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

    def is_allowed(self, household_id: int, connection: Connection) -> bool:
        with self._sessions() as session:
            return switches(session, household_id)[connection]

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
        if not self.is_allowed(household_id, connection):
            # Log the switch only, never the address or site (see LABELS).
            log.warning("Blocked outgoing connection: %s is switched off", LABELS[connection])
            raise OutboundBlocked(f"{LABELS[connection]} is switched off in Settings → Privacy")
        if urlsplit(url).scheme not in {"http", "https"}:
            raise OutboundBlocked("only http and https addresses are allowed")

        request = urllib.request.Request(url, data=body, method=method)  # noqa: S310 (scheme checked above)
        for name, value in (headers or {}).items():
            request.add_header(name, value)
        request.add_header("User-Agent", USER_AGENT)

        with _gate_open():
            try:
                response = self._opener.open(request, timeout=TIMEOUT_SECONDS)
            except urllib.error.HTTPError as error:  # 3xx (not followed), 4xx, 5xx
                response = error
            with response:
                data = response.read(max_bytes + 1)
                if len(data) > max_bytes:
                    raise OutboundBlocked(f"response is larger than {max_bytes} bytes")
                return OutboundResponse(
                    status=response.status,
                    headers=dict(response.headers.items()),
                    body=data,
                    url=url,
                )


# --- The network guard ---------------------------------------------------------------

_guard_installed = False


def install_network_guard() -> None:
    """Refuse network connections and DNS lookups made outside the gate.

    Audit hooks can't be removed, so this is installed once per process. It covers
    Python-level networking (the socket module, which urllib, httpx, asyncio and
    most libraries use). C libraries with their own networking aren't covered.
    """
    global _guard_installed
    if not _guard_installed:
        sys.addaudithook(_audit)
        _guard_installed = True


def _audit(event: str, args: tuple[Any, ...]) -> None:
    if not event.startswith("socket.") or _inside_gate.get():
        return
    if event in {"socket.connect", "socket.sendto", "socket.sendmsg"}:
        sock = args[0]
        if getattr(sock, "family", None) == socket.AF_UNIX:
            return
        raise OutboundBlocked(f"network connection outside the outbound gate ({event})")
    if event in {"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyname_ex"}:
        if not _is_local_name(args[0] if args else None):
            raise OutboundBlocked(f"DNS lookup outside the outbound gate ({event})")
    elif event == "socket.gethostbyaddr":
        raise OutboundBlocked("reverse DNS lookup outside the outbound gate")


def _is_local_name(host: object) -> bool:
    """Lookups that never leave the machine: no host, an IP literal, or localhost."""
    if host is None or host in {"", b"", "localhost", b"localhost"}:
        return True
    text = host.decode() if isinstance(host, bytes) else str(host)
    try:
        ipaddress.ip_address(text.strip("[]").split("%")[0])
    except ValueError:
        return False
    return True
