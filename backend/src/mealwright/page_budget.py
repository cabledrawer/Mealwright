"""A time and memory budget for reading one page (spec section 6, "A work budget for each
page").

The reader has limits of its own for every slow or greedy page found so far (long numbers,
deep nesting, repeated references and more; see `page_reader`). This is the safety net for
the ones nobody has found yet: `read_within_budget` reads the page in a short-lived child
process, and stops it if it uses more than `MAX_CPU_SECONDS` of processor time, takes longer
than `MAX_WALL_SECONDS` by the clock, or needs more than `MAX_MEMORY`. A check inside the
reader's own loops couldn't do that: it can't stop one long call inside Python itself (one
`json.loads` or `int()` on a huge text), but a process can be stopped whatever it's doing.

- **Processor time** is the main limit (the child limits its own, `RLIMIT_CPU`; the system
  ends it when it is used up). It counts the work the page needs, not how busy the machine is:
  a Raspberry Pi that is also doing other things reads the same page in the same processor
  time, even if it takes longer by the clock.
- **The clock** is the backstop: the server waits at most `MAX_WALL_SECONDS` from the start
  (starting the child included), then kills the child and waits for it to end, so no process
  is left behind. It catches a child that is stuck rather than working.
- **Memory:** before it reads, the child limits its own memory (`RLIMIT_AS`, all the memory
  the process has, Python itself included) to `MAX_MEMORY`. Past it, Python raises
  MemoryError and the child stops.
- The child can't write a core file (`RLIMIT_CORE` 0), and it switches on the network guard
  (`network_guard.install_network_guard`) before it reads anything: it starts fresh, so it doesn't
  have the server's guard, and even a bug in the reader couldn't open a connection.
- **Two at a time** (cabledrawer 23 Oct, question 22): at most `MAX_AT_ONCE` pages are read at
  once for the whole server (each child may use `MAX_MEMORY`). A third waits its turn; the
  wait counts within the import's own 30 seconds, and a read that can't start in time raises
  `PageBusy`. A place is always given back, however the read ends.
- **The import's 30 seconds:** the caller says how long the
  whole call may take (`within_seconds`, what the import has left after its fetch). The wait
  for a place and the read share it: the clock limit is cut to what is left once a place is
  free, a read with less than `MIN_READ_SECONDS` left isn't started (`PageBusy`: the wait used
  it up), and a child that has answered is given no more time than is left to end.
- The child gets the page's text and address, and sends back the reader's result. It does no
  network and no database work.

It's started with "spawn" (a fresh Python), never "fork": the server has threads, and a
fork can copy a lock another thread holds. Standard library only.
"""

import contextlib
import logging
import math
import multiprocessing
import resource
import signal
import threading
import time
from multiprocessing.connection import Connection

from mealwright import page_reader
from mealwright.page_reader import PageRecipe

log = logging.getLogger(__name__)

# The budget for one page (docs/dev/recipe-import.md, "The work budget"). The realistic big
# test page (5 MB, shaped like a real recipe blog with its scripts, menus, comments and a
# 200-ingredient recipe: tests/test_page_budget.py) needs about 1.2 seconds of processor time
# (0.1 of it to start the child) and 88 MB of memory in all, Python itself included, on a fast
# PC (measured 23 Oct). A Raspberry Pi 4 class board is perhaps 4 to 5 times slower, so
# 5 to 6 seconds there (an estimate, not measured): the processor limit is set above twice
# that, and the clock limit above the processor limit.
MAX_CPU_SECONDS = 12.0
MAX_WALL_SECONDS = 15.0
MAX_MEMORY = 384 * 1024 * 1024

# The sentence a screen shows (docs/dev/words.md, "Fetching a recipe page"; approved by
# cabledrawer 23 Oct). `page_fetch.MESSAGES` holds it too, under `Problem.CANT_READ`.
CANT_READ = "Couldn’t read that page. Paste the recipe’s text instead."

# At most this many pages are read at once, for the whole server (one process, so a plain
# semaphore does it). Standard library only.
MAX_AT_ONCE = 2
# The longest a read waits for its turn: the import's own 30 seconds (the caller passes what is
# left of them).
MAX_WAIT_SECONDS = 30.0
BUSY = "Mealwright is busy reading another page. Try again in a moment."
# A read that starts with less time than this left would only be stopped by the clock: the
# realistic big test page needs about 1.2 seconds of processor time on a fast PC.
MIN_READ_SECONDS = 2.0
_places = threading.BoundedSemaphore(MAX_AT_ONCE)

# How long the parent waits for a child that has already answered to end by itself, before it
# is killed. (It has nothing left to do but exit.)
_EXIT_SECONDS = 2.0

_spawn = multiprocessing.get_context("spawn")


class PageUnreadable(Exception):
    """Reading a page went over its budget or failed. `reason` is "time", "memory" or "crash"
    (the child ended without an answer, or its answer couldn't be sent); `message` is the
    sentence a screen shows."""

    def __init__(self, reason: str) -> None:
        super().__init__(CANT_READ)
        self.reason = reason
        self.message = CANT_READ


class PageBusy(PageUnreadable):
    """Two other pages are being read and the wait for a place ran out. `message` is the
    sentence a screen shows."""

    def __init__(self) -> None:
        super().__init__("busy")
        self.message = BUSY


def read_within_budget(
    html: str,
    url: str,
    *,
    cpu_seconds: float | None = None,
    wall_seconds: float | None = None,
    memory: int | None = None,
    wait_seconds: float | None = None,
    within_seconds: float | None = None,
) -> PageRecipe | None:
    """`page_reader.read_page(html, url)`, in a child process with a budget of `cpu_seconds`
    of processor time, `wall_seconds` by the clock and `memory` bytes (`MAX_CPU_SECONDS`,
    `MAX_WALL_SECONDS` and `MAX_MEMORY` unless a test changes them). Raises PageUnreadable if
    it goes over, or the child ends without a usable answer; anything else the reader raises
    is raised here too. If two other pages are being read, it waits up to `wait_seconds`
    (`MAX_WAIT_SECONDS`) for its turn, then raises PageBusy. `within_seconds`: the most the
    whole call (the wait and the read) may take, if the caller has a limit of its own (the
    import's 30 seconds, less what it has already used): the wait and the clock limit are cut
    to it, and a read with less than `MIN_READ_SECONDS` left once it has a place raises
    PageBusy."""
    began = time.monotonic()
    wait = MAX_WAIT_SECONDS if wait_seconds is None else wait_seconds
    if within_seconds is not None:
        wait = min(wait, within_seconds)
    if not _places.acquire(timeout=max(0.0, wait)):
        log.warning("Couldn't read a page: %s, busy with other pages", _label())
        raise PageBusy
    try:
        wall = MAX_WALL_SECONDS if wall_seconds is None else wall_seconds
        if within_seconds is not None:
            left = within_seconds - (time.monotonic() - began)
            if left < MIN_READ_SECONDS:  # the wait took the time the read needs
                log.warning("Couldn't read a page: %s, busy with other pages", _label())
                raise PageBusy
            wall = min(wall, left)
        return _read(html, url, cpu_seconds, wall, memory)
    finally:
        _places.release()


def _read(
    html: str,
    url: str,
    cpu_seconds: float | None,
    wall_seconds: float | None,
    memory: int | None,
) -> PageRecipe | None:
    cpu_seconds = MAX_CPU_SECONDS if cpu_seconds is None else cpu_seconds
    wall_seconds = MAX_WALL_SECONDS if wall_seconds is None else wall_seconds
    memory = MAX_MEMORY if memory is None else memory
    deadline = time.monotonic() + wall_seconds
    receive, send = _spawn.Pipe(duplex=False)
    child = _spawn.Process(
        target=_read_in_child,
        args=(send, html, url, cpu_seconds, memory),
        name="page reader",
        daemon=True,
    )
    answer: tuple[str, object] | None = None
    exitcode: int | None = None
    try:
        child.start()
        send.close()  # only the child holds it now, so its end shows here if it dies
        if receive.poll(max(0.0, deadline - time.monotonic())):
            try:
                answer = receive.recv()
            except EOFError, OSError:
                answer = None  # the child ended without answering
    finally:
        if child.pid is not None:  # it started
            if answer is not None:
                # It has answered: it only has to end. A child that doesn't within a moment
                # is killed like any other, so the server never waits on it for ever.
                child.join(max(0.0, min(_EXIT_SECONDS, deadline - time.monotonic())))
            if child.is_alive():
                child.kill()  # out of time (a child that already ended is left as it is)
                child.join()  # wait for it to end, so no process is left behind
            exitcode = child.exitcode
            child.close()
        receive.close()
        send.close()
    if answer is None:
        # Out of time by the clock, or ended by the system. Ended by the processor-time limit
        # (SIGXCPU, or SIGKILL after it) is time too; any other end is a crash.
        over_time = exitcode in {-signal.SIGKILL, -signal.SIGXCPU}
        raise _over_budget("time" if over_time else "crash")
    kind, value = answer
    if kind == "memory":
        raise _over_budget("memory")
    if kind == "failed":  # the result couldn't be sent back
        raise _over_budget("crash")
    if kind == "raised":
        raise value if isinstance(value, BaseException) else _over_budget("crash")
    return value if isinstance(value, PageRecipe) else None


_WORDS = {
    "time": "over its time limit",
    "memory": "over its memory limit",
    "crash": "the reader stopped",
}


def _label() -> str:
    # Here, not at the top: the child imports this module, and the gate's module would bring
    # the database code with it.
    from mealwright.outbound import LABELS, Connection

    return LABELS[Connection.RECIPE_IMPORT]


def _over_budget(reason: str) -> PageUnreadable:
    # The connection's plain label and the reason only, never the page's address.
    log.warning("Couldn't read a page: %s, %s", _label(), _WORDS[reason])
    return PageUnreadable(reason)


def _prepare_child(cpu_seconds: float, memory: int) -> None:
    """What the child does before it touches the page: no core file, its own memory and
    processor-time limits, and the network guard."""
    _lower_limit(resource.RLIMIT_CORE, 0)
    _lower_limit(resource.RLIMIT_AS, memory)
    # The soft limit ends the child with SIGXCPU; the hard one, 2 seconds later, with SIGKILL
    # in case something got in the way of the first.
    soft = math.ceil(cpu_seconds)
    _lower_limit(resource.RLIMIT_CPU, soft, soft + 2)
    # Imported here: it brings the database code with it, which only this one needs.
    from mealwright.network_guard import install_network_guard

    install_network_guard()


def _read_in_child(send: Connection, html: str, url: str, cpu_seconds: float, memory: int) -> None:
    """The child process: set its own limits, read the page, send the result back."""
    _prepare_child(cpu_seconds, memory)
    answer: tuple[str, object]
    try:
        answer = ("read", page_reader.read_page(html, url))
    except MemoryError:
        answer = ("memory", None)
    except Exception as error:  # sent back and raised in the server, as if read there
        answer = ("raised", error)
    del html
    try:
        send.send(answer)
    except Exception:  # a result too big to send, or one that can't be pickled
        # If this fails too, the server has gone or the pipe is broken: nothing more to do.
        with contextlib.suppress(Exception):
            send.send(("failed", None))
    send.close()


def _lower_limit(kind: int, soft: int, hard: int | None = None) -> None:
    """Lower a resource limit (never raise it past what the system already allows)."""
    hard = soft if hard is None else hard
    _, allowed = resource.getrlimit(kind)
    if allowed != resource.RLIM_INFINITY:
        soft, hard = min(soft, allowed), min(hard, allowed)
    resource.setrlimit(kind, (soft, hard))
