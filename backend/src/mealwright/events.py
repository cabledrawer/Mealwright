"""Live updates: the in-process broadcaster and the commit hooks that feed it
(docs/dev/sync-protocol.md section 10).

- Nothing is sent before the commit. While a request writes, the database session only
  notes "this household's lists changed" or "this household's stock changed"; the note is
  turned into events after the commit and thrown away on a rollback.
- Events carry numbers only (a counter, a change ID), never names or contents. A device
  that hears `shopping` asks `GET /shopping/changes` for the details, as any request.
- One broadcaster per server process (the container runs one). Writes may happen on a
  threadpool thread, so events are handed to each stream's own event loop thread-safely.
"""

import asyncio
import contextlib
import logging
import threading
from dataclasses import dataclass

from sqlalchemy import Connection, Engine, event, func, inspect, select
from sqlalchemy.orm import Session, SessionTransaction, sessionmaker

from mealwright.models import Change, Household, StockLot

log = logging.getLogger(__name__)

PENDING = "mealwright.pending_events"
SHOPPING = "shopping"
PANTRY = "pantry"


@dataclass(frozen=True)
class Event:
    name: str  # "hello", "shopping", "pantry" or "signed_out"
    data: dict[str, int]


class Subscription:
    """One open stream. Events arrive in `queue`; a `None` means the server is stopping."""

    def __init__(self, household_id: int, loop: asyncio.AbstractEventLoop) -> None:
        self.household_id = household_id
        self.loop = loop
        self.queue: asyncio.Queue[Event | None] = asyncio.Queue()

    def put(self, item: Event | None) -> None:
        with contextlib.suppress(RuntimeError):  # the stream's loop has already closed
            self.loop.call_soon_threadsafe(self.queue.put_nowait, item)


class Broadcaster:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscriptions: set[Subscription] = set()
        self._closed = False

    def subscribe(self, household_id: int) -> Subscription:
        subscription = Subscription(household_id, asyncio.get_running_loop())
        with self._lock:
            self._subscriptions.add(subscription)
            if self._closed:
                subscription.put(None)
        return subscription

    def unsubscribe(self, subscription: Subscription) -> None:
        with self._lock:
            self._subscriptions.discard(subscription)

    def publish(self, household_id: int, item: Event) -> None:
        """To this household's streams only."""
        with self._lock:
            targets = [s for s in self._subscriptions if s.household_id == household_id]
        for subscription in targets:
            subscription.put(item)

    def close(self) -> None:
        """The server is stopping: end every stream so shutdown isn't held up."""
        with self._lock:
            self._closed = True
            targets = list(self._subscriptions)
        for subscription in targets:
            subscription.put(None)

    def count(self) -> int:
        with self._lock:
            return len(self._subscriptions)


# --- Noting changes while a request writes --------------------------------------------------


def _note(session: Session, kind: str, household_id: int) -> None:
    session.info.setdefault(PENDING, {}).setdefault(kind, set()).add(household_id)


def _after_flush(session: Session, _context: object) -> None:
    for obj in session.dirty:
        if (
            isinstance(obj, Household)
            and session.is_modified(obj)
            and inspect(obj).attrs.list_seq.history.has_changes()
        ):
            _note(session, SHOPPING, obj.id)
    for obj in (*session.new, *session.dirty, *session.deleted):
        if isinstance(obj, StockLot):
            _note(session, PANTRY, obj.household_id)


def _read_events(connection: Connection, pending: dict[str, set[int]]) -> list[tuple[int, Event]]:
    """The numbers to announce, read fresh after the commit so they are exactly what is
    stored (a refused action's counter number never leaks out)."""
    out: list[tuple[int, Event]] = []
    for household_id in sorted(pending.get(SHOPPING, ())):
        cursor = connection.scalar(select(Household.list_seq).where(Household.id == household_id))
        if cursor is not None:
            out.append((household_id, Event(SHOPPING, {"cursor": int(cursor)})))
    for household_id in sorted(pending.get(PANTRY, ())):
        latest = connection.scalar(
            select(func.max(Change.id)).where(Change.household_id == household_id)
        )
        out.append((household_id, Event(PANTRY, {"change_id": int(latest or 0)})))
    return out


def install(factory: sessionmaker[Session], broadcaster: Broadcaster) -> None:
    """Hook the application's sessions up to the broadcaster."""
    event.listen(factory, "after_flush", _after_flush)

    def announce(session: Session, transaction: SessionTransaction) -> None:
        """The whole transaction is over. A commit leaves the note for us to announce (a
        rollback has already thrown it away); a savepoint ending is not the end."""
        if transaction.parent is not None:
            return
        pending = session.info.pop(PENDING, None)
        if not pending:
            return
        try:
            bind = session.get_bind()
            engine = bind if isinstance(bind, Engine) else bind.engine
            with engine.connect() as connection:
                found = _read_events(connection, pending)
        except Exception:  # live updates must never fail a save
            log.warning("Could not announce a change to open screens", exc_info=True)
            return
        for household_id, item in found:
            broadcaster.publish(household_id, item)

    def forget(session: Session) -> None:
        session.info.pop(PENDING, None)

    event.listen(factory, "after_rollback", forget)
    event.listen(factory, "after_transaction_end", announce)
