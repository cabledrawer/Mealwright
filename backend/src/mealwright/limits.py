"""The biggest request body the server will take (security audit, 0.4).

FastAPI reads a request's whole body before it checks the sign-in, and uvicorn has no
limit of its own, so without this anyone who can reach the server could make it hold
huge bodies in memory. The biggest real body is a full sync batch: 100 "clear ticked"
actions of 500 items each, about 3.4 MB with the longest IDs the server takes. Bodies
are counted as they arrive, so a missing or wrong Content-Length doesn't get round it.

One route takes more: a recipe photo upload may be up to 15 MB (cabledrawer 19 Oct). Only that
route, and only for that method. Mealie's backup file may be up to 1 GB (0.9.5, proposed, for
cabledrawer): it is streamed to a file, never held in memory.
"""

from typing import Any

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY_BYTES = 4 * 1024 * 1024
TOO_BIG = "That’s too much to send in one go."
MAX_PHOTO_BYTES = 15 * 1024 * 1024
PHOTO_TOO_BIG = "That photo is bigger than 15 MB."
MAX_MEALIE_BYTES = 1024 * 1024 * 1024
MEALIE_TOO_BIG = "That file is bigger than 1 GB. Mealwright can’t read it."

# (method, path) → (the most it takes, what to say, code). Exact paths only.
BIGGER = {
    ("POST", "/api/v1/recipes/photos"): (MAX_PHOTO_BYTES, PHOTO_TOO_BIG, "photo_too_big"),
    ("POST", "/api/v1/mealie-imports"): (MAX_MEALIE_BYTES, MEALIE_TOO_BIG, "mealie_too_big"),
}


def _without_answers(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _without_answers(v) for k, v in value.items() if k != "answers"}
    if isinstance(value, list):
        return [_without_answers(v) for v in value]
    return value


def body_hash(raw: bytes) -> str:
    """The hash of a request body, kept with its change (0.9.5, proposed, for cabledrawer). JSON is
    hashed the way the shopping sync hashes an action's payload (`shopping.payload_hash`: keys
    sorted, no spaces), so the same JSON with its keys in another order is the same body; no
    body, or a body that isn't JSON (or is nested too deep to read), is the SHA-256 of its bytes.

    Every `answers` key, at any depth, is left out first: the answers to an "ask once" question
    are sent only on the attempt that follows the question, and the app's "Try again" or an
    older queued copy of the change may send the same change without them. The change was saved
    once with them, so that is the same change, not another one (0.9.5 fix round 1)."""
    import hashlib
    import json

    from mealwright import shopping

    if raw.strip():
        try:
            return shopping.payload_hash(_without_answers(json.loads(raw)))
        except ValueError, RecursionError:  # nested too deep to read: hashed as bytes (T4)
            pass
    return hashlib.sha256(raw).hexdigest()


def _over(value: bytes, limit: int) -> bool:
    """Whether a Content-Length of ASCII digits is above the limit. Very long digit strings are
    over without being turned into a number (Python refuses an int of thousands of digits)."""
    digits = value.lstrip(b"0")
    return len(digits) > 18 or int(digits or b"0") > limit


class BodyTooBig(HTTPException):
    """Raised while the body is read; an HTTPException, so FastAPI passes it on as is."""

    def __init__(self, detail: str = TOO_BIG, code: str = "body_too_big") -> None:
        super().__init__(413, detail)
        self.code = code


def too_big_response(detail: str = TOO_BIG, code: str = "body_too_big") -> JSONResponse:
    return JSONResponse({"detail": detail, "code": code}, status_code=413)


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        limit, detail, code = BIGGER.get(
            (scope.get("method", ""), scope.get("path", "")),
            (self.max_bytes, TOO_BIG, "body_too_big"),
        )
        for name, value in scope.get("headers", []):
            if name == b"content-length" and value.isdigit() and _over(value, limit):
                await too_big_response(detail, code)(scope, receive, send)
                return
        received = 0
        started = False
        # With an Idempotency-Key the body is hashed as it arrives, for the route to compare a
        # key sent again (`body_hash`). Only keyed requests are held, up to the limit.
        # The photo upload takes no key and may be 15 MB: its body is never held here.
        keyed = (scope.get("method", ""), scope.get("path", "")) not in BIGGER and any(
            name == b"idempotency-key" for name, _ in scope.get("headers", [])
        )
        chunks: list[bytes] = []

        async def counted() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise BodyTooBig(detail, code)
                if keyed:
                    chunks.append(message.get("body", b""))
                    if not message.get("more_body", False):
                        scope.setdefault("state", {})["body_hash"] = body_hash(b"".join(chunks))
            return message

        async def watched(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counted, watched)
        except BodyTooBig as error:
            if started:
                raise
            await too_big_response(str(error.detail), error.code)(scope, receive, send)
