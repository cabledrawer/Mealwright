"""Start Mealwright for the browser tests, on their fixed date and time (test-only).

e2e/serve.mjs runs this instead of `python -m mealwright`, with E2E_CLOCK_SHIFT_MS set to how
far the tests' fixed moment is from now (e2e/tests/clock.ts). It moves the server's clock by
that much before the server starts, so the server's "today" and every time it stores agree
with the browser's clock in the tests, whatever the real date.

With E2E_SETUP_CODE set (every test server, e2e/serve.mjs and e2e/tests/clock.ts), the
first-run setup code is that instead of a random one (PR A2), so the tests can create the
admin without reading the server's output.

The update check never asks GitHub from the browser tests: its release list is the
placeholder address, so Check now answers "couldn't check" without any request (T4, 22 Nov:
since the list named the real home, the tests' answer depended on what GitHub had published).

Only this script reads those variables. It is not part of the installed package and is not in
the Docker image, so a real install can't be started with a moved clock or a known setup code
(tests/test_test_clock.py).
"""

import os
from collections.abc import Mapping
from datetime import timedelta

from mealwright import models, setup_code, updates
from mealwright.__main__ import main

VARIABLE = "E2E_CLOCK_SHIFT_MS"
SETUP_CODE_VARIABLE = "E2E_SETUP_CODE"


def move_the_clock(environ: Mapping[str, str]) -> timedelta:
    """Move the server's clock by E2E_CLOCK_SHIFT_MS milliseconds; give back how far."""
    shift = timedelta(milliseconds=int(environ[VARIABLE]))
    models.TEST_CLOCK_SHIFT = shift
    return shift


def know_the_setup_code(environ: Mapping[str, str]) -> None:
    """Make E2E_SETUP_CODE the first-run setup code."""
    code = environ[SETUP_CODE_VARIABLE]
    setup_code.new_code = lambda: code


def ask_github_nothing() -> None:
    """Point the update check at the placeholder release list, which it never asks."""
    updates.RELEASE_LIST_URL = (
        f"https://api.github.com/repos/{updates.PLACEHOLDER_OWNER}/mealwright/releases"
    )


if __name__ == "__main__":
    ask_github_nothing()
    if VARIABLE in os.environ:
        move_the_clock(os.environ)
    if SETUP_CODE_VARIABLE in os.environ:
        know_the_setup_code(os.environ)
    main()
