"""Live updates: Server-Sent Events from our own server (sync protocol section 10)."""

import asyncio
import json
import time
from collections.abc import AsyncIterator, Callable
from typing import Any

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from mealwright.auth import COOKIE, peek_session
from mealwright.events import Broadcaster, Event, Subscription
from mealwright.models import Household

router = APIRouter(tags=["live updates"])

RETRY_MS = 5000
HEADERS = {"Cache-Control": "no-store", "X-Accel-Buffering": "no"}

EXAMPLE = (
    "retry: 5000\n\n"
    'event: hello\ndata: {"cursor": 1052}\n\n'
    'event: shopping\ndata: {"cursor": 1053}\n\n'
    'event: pantry\ndata: {"change_id": 815}\n\n'
    ": keep-alive\n\n"
    "event: signed_out\ndata: {}\n\n"
)


def frame(item: Event) -> str:
    return f"event: {item.name}\ndata: {json.dumps(item.data)}\n\n"


def _counter(factory: sessionmaker[Session], household_id: int) -> int:
    with factory() as db:
        value = db.scalar(select(Household.list_seq).where(Household.id == household_id))
        return int(value or 0)


def _still_signed_in(factory: sessionmaker[Session], token: str) -> bool:
    """Read-only: asking never extends the sign-in."""
    with factory() as db:
        return peek_session(db, token) is not None


async def stream(
    factory: sessionmaker[Session],
    subscription: Subscription,
    unsubscribe: Callable[[Subscription], None],
    token: str,
    cursor: int,
    keepalive: float,
) -> AsyncIterator[str]:
    try:
        yield f"retry: {RETRY_MS}\n\n"
        yield frame(Event("hello", {"cursor": cursor}))
        due = time.monotonic() + keepalive
        while True:
            wait = max(due - time.monotonic(), 0)
            try:
                item = await asyncio.wait_for(subscription.queue.get(), timeout=wait)
            except TimeoutError:
                # The sign-in is checked without extending it: an open screen is not
                # activity (cabledrawer 18 Oct).
                if not await run_in_threadpool(_still_signed_in, factory, token):
                    yield frame(Event("signed_out", {}))
                    return
                yield ": keep-alive\n\n"
                due = time.monotonic() + keepalive
                continue
            if item is None:  # the server is stopping
                return
            yield frame(item)
    finally:
        unsubscribe(subscription)


@router.get(
    "/events",
    response_class=StreamingResponse,
    responses={
        200: {
            "description": (
                "A stream of Server-Sent Events: `hello {cursor}` on connect, `shopping "
                "{cursor}` after a commit that raised the household's list counter, "
                "`pantry {change_id}` after a stock change, a `: keep-alive` comment every "
                "25 seconds, and `signed_out` (then the stream closes) when the sign-in "
                "runs out. Numbers only, never names. Only this household's events. The "
                "stream is not activity: it never extends the sign-in."
            ),
            "content": {"text/event-stream": {"schema": {"type": "string"}, "example": EXAMPLE}},
        },
        401: {"description": "Not signed in."},
    },
)
async def get_events(request: Request) -> StreamingResponse:
    """Live updates for open screens (Server-Sent Events, same server only)."""
    app: Any = request.app
    factory: sessionmaker[Session] = app.state.sessionmaker
    token = request.cookies.get(COOKIE)

    broadcaster: Broadcaster = app.state.events

    def household() -> int | None:
        with factory() as db:
            found = peek_session(db, token)
            return None if found is None else found.login.household_id

    household_id = await run_in_threadpool(household)
    if household_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in.")
    # Subscribe first, then read the counter: a change in between is announced again
    # with a cursor at least as high, never missed.
    subscription = broadcaster.subscribe(household_id)
    try:
        cursor = await run_in_threadpool(_counter, factory, household_id)
    except BaseException:
        broadcaster.unsubscribe(subscription)
        raise
    return StreamingResponse(
        stream(
            factory,
            subscription,
            broadcaster.unsubscribe,
            token or "",
            cursor,
            app.state.settings.events_keepalive_seconds,
        ),
        media_type="text/event-stream",
        headers=HEADERS,
    )
