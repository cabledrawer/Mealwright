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
    'event: batch_cook\ndata: {"session_id": 7}\n\n'
    'event: plan\ndata: {"change_id": 816}\n\n'
    ": keep-alive\n\n"
    "event: signed_out\ndata: {}\n\n"
)
# (A stream closed because its sign-in opened too many gets `event: replaced` instead.)


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
                "{cursor}` after a commit that raised the household’s list counter, "
                "`pantry {change_id}` after a stock change, `batch_cook {session_id}` after a "
                "Batch cook schedule or its progress changed, `plan {change_id}` after a planned "
                "meal, its items, eaters, tubs, batches or the meal slots changed, a `: keep-alive` "
                "comment every "
                "25 seconds, and `signed_out` (then the stream closes) when the sign-in "
                "runs out. Numbers only, never names. Only this household’s events. The "
                "stream is not activity: it never extends the sign-in. One sign-in may "
                "hold 10 streams open; opening another closes its oldest, which is "
                "sent `replaced` first (the web app then stays quiet, without "
                "reconnecting, until its tab is looked at again)."
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

    def signed_in() -> tuple[int, int] | None:
        with factory() as db:
            found = peek_session(db, token)
            return None if found is None else (found.login.household_id, found.session.id)

    who = await run_in_threadpool(signed_in)
    if who is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in.")
    household_id, session_id = who
    # Subscribe first, then read the counter: a change in between is announced again
    # with a cursor at least as high, never missed. Past the limit for one sign-in, this
    # closes that sign-in's oldest stream.
    subscription = broadcaster.subscribe(household_id, session_id)

    def counter_if_still_signed_in() -> int | None:
        # Asked again after subscribing: a sign-out between the first check and the
        # subscription told no stream of ours, so this stream would stay open until the
        # next check, 25 seconds later.
        cursor = _counter(factory, household_id)
        return cursor if _still_signed_in(factory, token or "") else None

    try:
        cursor = await run_in_threadpool(counter_if_still_signed_in)
    except BaseException:
        broadcaster.unsubscribe(subscription)
        raise
    if cursor is None:
        broadcaster.unsubscribe(subscription)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Please sign in.")
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
