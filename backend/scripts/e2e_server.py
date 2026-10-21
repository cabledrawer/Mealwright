"""Start Mealwright for the browser tests, on their fixed date and time (test-only).

e2e/serve.mjs runs this instead of `python -m mealwright`, with E2E_CLOCK_SHIFT_MS set to how
far the tests' fixed moment is from now (e2e/tests/clock.ts). It moves the server's clock by
that much before the server starts, so the server's "today" and every time it stores agree
with the browser's clock in the tests, whatever the real date.

Only this script reads that variable. It is not part of the installed package and is not in
the Docker image, so a real install can't be started with a moved clock
(tests/test_test_clock.py).
"""

import os
from collections.abc import Mapping
from datetime import timedelta

from mealwright import models
from mealwright.__main__ import main

VARIABLE = "E2E_CLOCK_SHIFT_MS"


def move_the_clock(environ: Mapping[str, str]) -> timedelta:
    """Move the server's clock by E2E_CLOCK_SHIFT_MS milliseconds; give back how far."""
    shift = timedelta(milliseconds=int(environ[VARIABLE]))
    models.TEST_CLOCK_SHIFT = shift
    return shift


if __name__ == "__main__":
    move_the_clock(os.environ)
    main()
