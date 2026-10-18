"""The biggest request body the server will take (security audit, 0.4).

FastAPI reads a request's whole body before it checks the sign-in, and uvicorn has no
limit of its own, so without this anyone who can reach the server could make it hold
huge bodies in memory. The biggest real body is a full sync batch: 100 "clear ticked"
actions of 500 items each, about 3.4 MB with the longest IDs the server takes. Bodies
are counted as they arrive, so a missing or wrong Content-Length doesn't get round it.
"""

from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

MAX_BODY_BYTES = 4 * 1024 * 1024
TOO_BIG = "That's too much to send in one go."


class BodyTooBig(HTTPException):
    """Raised while the body is read; an HTTPException, so FastAPI passes it on as is."""

    def __init__(self) -> None:
        super().__init__(413, TOO_BIG)


def too_big_response() -> JSONResponse:
    return JSONResponse({"detail": TOO_BIG, "code": "body_too_big"}, status_code=413)


class BodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        for name, value in scope.get("headers", []):
            if name == b"content-length" and value.isdigit() and int(value) > self.max_bytes:
                await too_big_response()(scope, receive, send)
                return
        received = 0
        started = False

        async def counted() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise BodyTooBig
            return message

        async def watched(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counted, watched)
        except BodyTooBig:
            if started:
                raise
            await too_big_response()(scope, receive, send)
