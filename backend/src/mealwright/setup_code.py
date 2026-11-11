"""The first-run setup code (PR A2).

While nobody has set Mealwright up, anyone who can reach it could create the admin account. So
at start-up, while there's no login, the server makes a one-time code and prints it in its own
output (`docker logs`), and the first-admin form needs it: only someone who can read the
server's log can claim a fresh install. The code lives in memory only; a restart makes a new
one, and it's forgotten once the admin exists.
"""

import hmac
import logging
import secrets

# The container output as well as the log file: the person setting up reads it there.
log = logging.getLogger("mealwright.setup")

# No 0/O, 1/I/L: easy to read off a terminal and type on a phone.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
GROUPS = 3
GROUP_LENGTH = 4


def new_code() -> str:
    """Twelve characters in three groups, "K7QM-3XRT-P9WA" (about 59 bits)."""
    groups = ("".join(secrets.choice(ALPHABET) for _ in range(GROUP_LENGTH)) for _ in range(GROUPS))
    return "-".join(groups)


def normalise(typed: str) -> str:
    """As typed: any case, with or without the dashes or spaces."""
    return "".join(c for c in typed.upper() if c not in "- \t")


def matches(expected: str | None, typed: str) -> bool:
    if expected is None:
        return False
    # Compared in constant time; both sides are ASCII after normalising.
    want = normalise(expected).encode()
    got = normalise(typed).encode("ascii", "replace")
    return hmac.compare_digest(want, got)


def announce(code: str) -> None:
    log.warning(
        "Mealwright isn't set up yet. To create the admin account, open Mealwright in a "
        "browser and type this setup code: %s (it changes each time Mealwright restarts)",
        code,
    )
