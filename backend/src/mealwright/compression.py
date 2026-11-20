"""Gzip for the API's JSON answers (0.9.5 speed work; proposed, for cabledrawer).

A page opens with several answers of tens of kilobytes of JSON (the shopping list's copy is
120 KB), which gzip makes about eight times smaller. Only:

- `GET` answers with status 200 and a JSON body of 1 KB or more, to a client that sends
  `Accept-Encoding: gzip`;
- never the live updates stream, never a download (`Content-Disposition`), never an answer
  already encoded, never photos or other files (not JSON), never an answer to a request that
  changes something (`POST`, `PUT`, `PATCH`, `DELETE`), and never what is under `NEVER`: the
  API tokens, the sign-in server's settings, backups and the data download. No `GET` answer
  carries a secret next to text the caller chose (the one answer that holds a token, making
  it, is a `POST`; a client secret is never sent back), so the "BREACH" attack, which needs
  both in one compressed answer, has nothing here; those paths are left out anyway.

The built web app's files are not compressed here: they are compressed once, at build time,
and sent as they are (`mealwright.frontend`). Level 4: much of the size saving for little of a
small server's processor time.
"""

import gzip

from starlette.types import ASGIApp, Message, Receive, Scope, Send

MIN_BYTES = 1000
LEVEL = 4
# Held back to be compressed: more than this and the answer goes out as it is, not buffered.
MOST_BUFFERED = 4 * 1024 * 1024
NEVER = (
    "/api/v1/events",
    "/api/v1/api-tokens",
    "/api/v1/sso",
    "/api/v1/your-data",
)


def accepted_encodings(header: str) -> set[str]:
    """The encodings an Accept-Encoding header allows (those named without q=0, lower case;
    `*` is not expanded: a browser that wants br or gzip names it)."""
    allowed: set[str] = set()
    for part in header.split(","):
        name, _, params = part.strip().partition(";")
        quality = 1.0
        for param in params.split(";"):
            key, _, value = param.strip().partition("=")
            if key.strip().lower() == "q":
                try:
                    quality = float(value)
                except ValueError:
                    quality = 0.0
        if quality > 0 and name.strip():
            allowed.add(name.strip().lower())
    return allowed


def accepts_gzip(header: str) -> bool:
    """Does an Accept-Encoding header allow gzip?"""
    return "gzip" in accepted_encodings(header)


class JsonGzipMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["method"] != "GET":
            await self.app(scope, receive, send)
            return
        path: str = scope["path"]
        if not path.startswith("/api/") or any(path.startswith(never) for never in NEVER):
            await self.app(scope, receive, send)
            return
        wants = False
        for name, value in scope["headers"]:
            if name == b"accept-encoding":
                wants = accepts_gzip(value.decode("latin-1"))
        start: Message | None = None
        chunks: list[bytes] = []
        size = 0
        passing = False

        async def hold(message: Message) -> None:
            nonlocal start, size, passing
            if passing:
                await send(message)
                return
            if message["type"] == "http.response.start":
                headers = MutableHeaders(message["headers"])
                json = headers.get("content-type", "").startswith("application/json")
                if json:  # the answer depends on what the client accepts, whichever way it goes
                    headers.add_vary("Accept-Encoding")
                if (
                    not wants
                    or not json
                    or message["status"] != 200
                    or "content-encoding" in headers
                    or "content-disposition" in headers
                ):
                    passing = True
                    await send({**message, "headers": headers.raw()})
                    return
                start = {**message, "headers": headers.raw()}
                return
            if start is None:  # pragma: no cover (a body always follows its start)
                await send(message)
                return
            chunks.append(message.get("body", b""))
            size += len(chunks[-1])
            more = message.get("more_body", False)
            if more and size <= MOST_BUFFERED:
                return
            body = b"".join(chunks)
            if more or size < MIN_BYTES:  # too big to hold, or too small to bother with
                passing = True
                await send(start)
                await send({"type": "http.response.body", "body": body, "more_body": more})
                return
            packed = gzip.compress(body, compresslevel=LEVEL, mtime=0)
            headers = MutableHeaders(start["headers"])
            headers["content-encoding"] = "gzip"
            headers["content-length"] = str(len(packed))
            passing = True
            await send({**start, "headers": headers.raw()})
            await send({"type": "http.response.body", "body": packed})

        await self.app(scope, receive, hold)


class MutableHeaders:
    """The raw header list of a response, with the few edits this module makes."""

    def __init__(self, raw: list[tuple[bytes, bytes]]) -> None:
        self._items: list[tuple[bytes, bytes]] = list(raw)

    def get(self, name: str, default: str = "") -> str:
        for key, value in self._items:
            if key.decode("latin-1").lower() == name:
                return value.decode("latin-1")
        return default

    def __contains__(self, name: str) -> bool:
        return any(key.decode("latin-1").lower() == name for key, _ in self._items)

    def __setitem__(self, name: str, value: str) -> None:
        self._items = [(k, v) for k, v in self._items if k.decode("latin-1").lower() != name]
        self._items.append((name.encode("latin-1"), value.encode("latin-1")))

    def add_vary(self, token: str) -> None:
        current = self.get("vary")
        if token.lower() in [part.strip().lower() for part in current.split(",")]:
            return
        self["vary"] = f"{current}, {token}" if current else token

    def raw(self) -> list[tuple[bytes, bytes]]:
        return self._items
