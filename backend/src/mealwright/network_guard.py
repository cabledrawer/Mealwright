"""The network guard: refuse network connections and DNS lookups made outside the outbound
gate (spec section 7, "Runtime guard").

A Python audit hook that sees every `socket.connect`, UDP send and DNS lookup, by our code or by
any library, and refuses it unless the gate itself is connecting (`gate_open()`). Audit hooks
can't be removed, so `install_network_guard()` installs it once per process. It covers
Python-level networking (the socket module, which urllib, httpx, asyncio and most libraries
use). C libraries with their own networking aren't covered.

This module is small and imports no networking module and no database code on purpose: the
page-reading child process switches the guard on too (`page_budget`), and importing the whole
gate there would cost it about two thirds of a second of processor time on every page. It never
imports `socket` itself: a socket's family is read from the object the hook is given.

A reverse lookup (`socket.gethostbyaddr`, `socket.getnameinfo`) is refused too, whatever the
address: `getnameinfo`'s audit event carries only the address, not the flags, so a numeric-only
call can't be told apart, and even a loopback address other than 127.0.0.1 asks the system's DNS
server. Nothing in the app needs it.

Only new connections and sends to an address are refused. A write on a connection that already
exists (a reply going out) is not a connection and is never blocked: `socket.send` fires no
event, and `socket.sendmsg` with no address is how asyncio finishes a large reply. Note that
`OutboundBlocked` is an `OSError`, and asyncio treats an `OSError` on its write path as a dead
socket and closes it without a word in the log. When the hook once refused such a write (F22,
0.6.0), replies bigger than the send buffer were cut off silently.

`mealwright.outbound` re-exports `install_network_guard`.
"""

import contextvars
import ipaddress
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any


class OutboundBlocked(PermissionError):
    """An outgoing connection was refused."""


# True only while the gate itself is connecting. The network guard checks it.
inside_gate: contextvars.ContextVar[bool] = contextvars.ContextVar(
    "mealwright_inside_gate", default=False
)


@contextmanager
def gate_open() -> Iterator[None]:
    token = inside_gate.set(True)
    try:
        yield
    finally:
        inside_gate.reset(token)


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
    if not event.startswith("socket.") or inside_gate.get():
        return
    # `socket.sendmsg` with no address is a write on a socket that already exists (asyncio uses it
    # to finish sending a large reply); with an address it is a UDP send, blocked like sendto.
    if event in {"socket.connect", "socket.sendto"} or (
        event == "socket.sendmsg" and len(args) > 1 and not _no_address(args[1])
    ):
        sock = args[0]
        if getattr(getattr(sock, "family", None), "name", None) == "AF_UNIX":
            return
        raise OutboundBlocked(f"network connection outside the outbound gate ({event})")
    if event in {"socket.getaddrinfo", "socket.gethostbyname", "socket.gethostbyname_ex"}:
        if not _is_local_name(args[0] if args else None):
            raise OutboundBlocked(f"DNS lookup outside the outbound gate ({event})")
    elif event in {"socket.gethostbyaddr", "socket.getnameinfo"}:
        raise OutboundBlocked("reverse DNS lookup outside the outbound gate")


def _no_address(address: object) -> bool:
    """Only None or a plain empty tuple mean "no address": an address object made to look empty
    (a tuple subclass whose truth is False) is still an address."""
    return address is None or (type(address) is tuple and len(address) == 0)


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
