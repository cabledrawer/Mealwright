"""A replayed request answers 200 (0.9.5-beta.3, D2, BE15; docs/dev/api-endpoints.md 1.2).

A retry with an `Idempotency-Key` already used makes nothing new, so it is never "201 Created",
whichever route answers it: every replay is `200` with `Idempotent-Replayed: true`. The routes
mark a replay with that header; this turns a 201 that carries it into a 200, in one place.
"""

from starlette.types import ASGIApp, Message, Receive, Scope, Send

REPLAYED = b"idempotent-replayed"


class ReplayIsOkMiddleware:
    """A plain ASGI middleware, so streamed answers aren't buffered."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_replay_as_ok(message: Message) -> None:
            if (
                message["type"] == "http.response.start"
                and message["status"] == 201  # Created
                and any(name.lower() == REPLAYED for name, _ in message.get("headers", []))
            ):
                message = {**message, "status": 200}
            await send(message)

        await self.app(scope, receive, send_replay_as_ok)
