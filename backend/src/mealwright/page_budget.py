"""A time and memory budget for reading one page (spec section 6, "A work budget for each
page").

The reader has limits of its own for every slow or greedy page found so far (long numbers,
deep nesting, repeated references and more; see `page_reader`). This is the safety net for
the ones nobody has found yet: `read_within_budget` reads the page in a short-lived child
process, and stops it if it takes longer than `MAX_SECONDS` or needs more than `MAX_MEMORY`.
A check inside the reader's own loops couldn't do that: it can't stop one long call inside
Python itself (one `json.loads` or `int()` on a huge text), but a process can be stopped
whatever it's doing.

- **Time:** the server waits at most `MAX_SECONDS` from the start (starting the child
  included), then kills the child and waits for it to end, so no process is left behind.
  The child also limits its own processor time to a second or two more, in case the server
  itself is stopped meanwhile.
- **Memory:** before it reads, the child limits its own memory (`RLIMIT_AS`, all the memory
  the process has, Python itself included) to `MAX_MEMORY`. Past it, Python raises
  MemoryError and the child stops.
- The child gets the page's text and address, and sends back the reader's result. It does
  no network and no database work: it imports only `page_reader`.

It's started with "spawn" (a fresh Python), never "fork": the server has threads, and a
fork can copy a lock another thread holds. Standard library only.
"""

import logging
import math
import multiprocessing
import resource
import signal
import time
from multiprocessing.connection import Connection

from mealwright import page_reader
from mealwright.page_reader import PageRecipe

log = logging.getLogger(__name__)

# The budget for one page (docs/dev/recipe-import.md, "The work budget"). The realistic big
# test page (5 MB, shaped like a real recipe blog with its scripts, menus, comments and a
# 200-ingredient recipe: tests/test_page_budget.py) takes about 1 second in the child,
# starting it included, and 88 MB of memory in all, Python itself included; these are about
# 5 and 4 times that, and never less than 5 seconds and 256 MB.
MAX_SECONDS = 5.0
MAX_MEMORY = 384 * 1024 * 1024

# The sentence a screen shows (docs/dev/words.md, "Fetching a recipe page"; proposed, for
# cabledrawer). `page_fetch.MESSAGES` holds it too, under `Problem.CANT_READ`.
CANT_READ = "Couldn’t read that page. Paste the recipe’s text instead."

_spawn = multiprocessing.get_context("spawn")


class PageUnreadable(Exception):
    """Reading a page went over its budget. `reason` is "time" or "memory"; `message` is
    the sentence a screen shows."""

    def __init__(self, reason: str) -> None:
        super().__init__(CANT_READ)
        self.reason = reason
        self.message = CANT_READ


def read_within_budget(
    html: str, url: str, *, seconds: float | None = None, memory: int | None = None
) -> PageRecipe | None:
    """`page_reader.read_page(html, url)`, in a child process with a budget of `seconds`
    and `memory` bytes (`MAX_SECONDS` and `MAX_MEMORY` unless a test lowers them). Raises
    PageUnreadable if it goes over; anything else the reader raises is raised here too."""
    seconds = MAX_SECONDS if seconds is None else seconds
    memory = MAX_MEMORY if memory is None else memory
    deadline = time.monotonic() + seconds
    receive, send = _spawn.Pipe(duplex=False)
    child = _spawn.Process(
        target=_read_in_child,
        args=(send, html, url, seconds, memory),
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
            except EOFError:
                answer = None  # the child ended without answering
    finally:
        if child.pid is not None:  # it started
            if answer is None:
                child.kill()  # out of time (a child that already ended is left as it is)
            child.join()  # wait for it to end, so no process is left behind
            exitcode = child.exitcode
            child.close()
        receive.close()
        send.close()
    if answer is None:
        # Out of time, or ended by the system. Ended by its processor-time limit is time too;
        # any other end (MemoryError before it could answer, say) is memory.
        over_time = exitcode in {-signal.SIGKILL, -signal.SIGXCPU}
        raise _over_budget("time" if over_time else "memory")
    kind, value = answer
    if kind == "memory":
        raise _over_budget("memory")
    if kind == "raised":
        raise value if isinstance(value, BaseException) else RuntimeError(str(value))
    return value if isinstance(value, PageRecipe) else None


def _over_budget(reason: str) -> PageUnreadable:
    # Here, not at the top: the child imports this module, and the gate's module would bring
    # the database code with it.
    from mealwright.outbound import LABELS, Connection

    # The connection's plain label and the reason only, never the page's address.
    log.warning(
        "Couldn't read a page: %s, over its %s limit", LABELS[Connection.RECIPE_IMPORT], reason
    )
    return PageUnreadable(reason)


def _read_in_child(send: Connection, html: str, url: str, seconds: float, memory: int) -> None:
    """The child process: set its own limits, read the page, send the result back."""
    _lower_limit(resource.RLIMIT_AS, memory)
    _lower_limit(resource.RLIMIT_CPU, math.ceil(seconds) + 1)
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
    except Exception as error:  # an error that can't be sent as it is
        send.send(("raised", f"{type(error).__name__} while reading a page"))
    send.close()


def _lower_limit(kind: int, limit: int) -> None:
    """Lower a resource limit (never raise it past what the system already allows)."""
    _, hard = resource.getrlimit(kind)
    if hard != resource.RLIM_INFINITY:
        limit = min(limit, hard)
    resource.setrlimit(kind, (limit, hard if kind == resource.RLIMIT_CPU else limit))
