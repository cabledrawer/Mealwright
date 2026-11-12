"""The reverse proxy's other headers (PR A2).

uvicorn's ProxyHeadersMiddleware (main.py) applies X-Forwarded-For and X-Forwarded-Proto from
MEALWRIGHT_TRUSTED_PROXIES. This adds the two things it doesn't do:

- X-Forwarded-Host from a trusted proxy becomes the request's Host, so the same-site checks
  compare the browser's Origin with the address the browser used, when a proxy passes its own
  upstream name as Host. Only a plain host name or address, with an optional port, is taken;
  anything else is ignored. The proxy must set this header itself, replacing any a visitor
  sent (the README gives nginx's line). The Host is used only for that check: Mealwright
  never builds links from it.
- X-Forwarded-For from an address that isn't trusted (the usual case: a proxy in front and
  MEALWRIGHT_TRUSTED_PROXIES not set) logs one warning per process, saying how to set it.
  Without it, every visitor looks like the proxy, and the sign-in slow-down counts them together.
  The warning names no address.
"""

import ipaddress
import logging
import re

from starlette.types import ASGIApp, Receive, Scope, Send

log = logging.getLogger("mealwright.proxy")

# A host name, IPv4 address or [IPv6] address, with an optional port.
_HOST = re.compile(
    r"^(?:[A-Za-z0-9](?:[A-Za-z0-9.-]{0,252})|\[[0-9A-Fa-f:.]{2,45}\])(?::\d{1,5})?$"
)

UNTRUSTED_WARNING = (
    "A request came through a reverse proxy (it sent X-Forwarded-For), but the proxy isn't "
    "trusted, so every visitor looks like the proxy and wrong passwords from one person slow "
    "down everyone. Set MEALWRIGHT_TRUSTED_PROXIES to the proxy's address or network (for "
    "example 172.28.10.0/24) and restart Mealwright. This is said once each time Mealwright "
    "starts."
)


class TrustedProxies:
    """MEALWRIGHT_TRUSTED_PROXIES, as uvicorn reads it: addresses and networks,
    comma-separated, or "*" for anyone."""

    def __init__(self, setting: str) -> None:
        parts = [p.strip() for p in setting.split(",") if p.strip()]
        self.everyone = "*" in parts
        self.networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        self.names: set[str] = set()  # e.g. a unix socket path or a name uvicorn would accept
        for part in parts:
            if part == "*":
                continue
            try:
                self.networks.append(ipaddress.ip_network(part, strict=False))
            except ValueError:
                self.names.add(part)

    def __contains__(self, host: str | None) -> bool:
        if host is None:
            return False
        if self.everyone or host in self.names:
            return True
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            return False
        return any(address in network for network in self.networks)


def _last(value: bytes) -> str:
    """The last of a comma-separated header: the one the trusted proxy itself added."""
    return value.decode("latin-1").split(",")[-1].strip()


class ForwardedMiddleware:
    """Runs outside uvicorn's ProxyHeadersMiddleware, so it sees the proxy's own address."""

    def __init__(self, app: ASGIApp, trusted: str) -> None:
        self.app = app
        self.trusted = TrustedProxies(trusted)
        self.warned = False

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] in ("http", "websocket"):
            client = scope.get("client")
            peer = client[0] if client else None
            headers: list[tuple[bytes, bytes]] = scope["headers"]
            if peer in self.trusted:
                forwarded = [v for k, v in headers if k == b"x-forwarded-host"]
                host = _last(forwarded[-1]) if forwarded else ""
                if host and _HOST.match(host):
                    scope = dict(scope)
                    scope["headers"] = [(k, v) for k, v in headers if k != b"host"] + [
                        (b"host", host.encode("latin-1"))
                    ]
            elif not self.warned and any(k == b"x-forwarded-for" for k, _ in headers):
                self.warned = True
                log.warning(UNTRUSTED_WARNING)
        await self.app(scope, receive, send)
