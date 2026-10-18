"""Browser security rules sent with every response (spec section 7).

The Content Security Policy lets pages load files only from the household's own
server, so no CDN, tracker or injected script can be added, even by accident.
The other headers stop the app being framed by other sites, stop browsers guessing
file types, send no referrer to other sites (e.g. when following a recipe's source
link), and switch off browser features the app never uses, such as location.
"""

from collections.abc import Iterable

from starlette.types import ASGIApp, Message, Receive, Scope, Send


def content_security_policy(script_hashes: Iterable[str] = ()) -> str:
    """The policy. `script_hashes` ('sha256-…') allow specific inline scripts by their
    exact content; the frontend build will need this for its start-up script."""
    scripts = " ".join(["'self'", *(f"'{h}'" for h in script_hashes)])
    directives = {
        "default-src": "'self'",
        "script-src": scripts,
        "style-src": "'self'",
        "img-src": "'self' data: blob:",  # data:/blob: for photo previews before upload
        "font-src": "'self'",
        "connect-src": "'self'",  # the API and live updates, same server only
        "manifest-src": "'self'",
        "worker-src": "'self'",  # the offline service worker (0.3)
        "media-src": "'none'",
        "object-src": "'none'",
        "frame-src": "'none'",
        "frame-ancestors": "'none'",  # no other site may show Mealwright in a frame
        "base-uri": "'none'",
        "form-action": "'self'",
    }
    return "; ".join(f"{name} {value}" for name, value in directives.items())


# Browser features. Everything off except the screen wake lock, which keeps the screen
# on while cooking (spec: "Keep screen awake"). Location is never allowed (ethos).
PERMISSIONS_POLICY = ", ".join(
    [
        "geolocation=()",
        "camera=()",  # barcode scanning would need camera=(self)
        "microphone=()",
        "payment=()",
        "usb=()",
        "bluetooth=()",
        "serial=()",
        "hid=()",
        "midi=()",
        "magnetometer=()",
        "gyroscope=()",
        "accelerometer=()",
        "display-capture=()",
        "browsing-topics=()",
        "screen-wake-lock=(self)",
    ]
)


def security_headers(script_hashes: Iterable[str] = ()) -> list[tuple[bytes, bytes]]:
    headers = {
        "content-security-policy": content_security_policy(script_hashes),
        "permissions-policy": PERMISSIONS_POLICY,
        "referrer-policy": "no-referrer",
        "x-content-type-options": "nosniff",
        "x-frame-options": "DENY",
        "cross-origin-opener-policy": "same-origin",
        "cross-origin-resource-policy": "same-origin",
    }
    return [(name.encode(), value.encode()) for name, value in headers.items()]


class SecurityHeadersMiddleware:
    """Adds the security headers to every HTTP response.

    A plain ASGI middleware, so streamed responses (live updates in 0.3) aren't buffered.
    """

    def __init__(self, app: ASGIApp, script_hashes: Iterable[str] = ()) -> None:
        self.app = app
        self.headers = security_headers(script_hashes)
        self.names = {name for name, _ in self.headers}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                existing = [
                    (name, value)
                    for name, value in message.get("headers", [])
                    if name.lower() not in self.names
                ]
                extra = list(self.headers)
                if scope.get("path", "").startswith("/api"):
                    # The browser's own cache never keeps anything about a household
                    # (sync protocol section 12).
                    existing = [(n, v) for n, v in existing if n.lower() != b"cache-control"]
                    extra.append((b"cache-control", b"no-store"))
                message["headers"] = existing + extra
            await send(message)

        await self.app(scope, receive, send_with_headers)
