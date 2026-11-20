"""A moment in an API answer, always sent with its zone (0.9.5-beta.3, D4, BE6).

SQLite gives a stored time back without its zone. Sent as it is, "2026-11-20T10:00:00" reads in a
browser as the browser's own local time, which is wrong by the person's offset from UTC. Every
datetime field of an answer model is a `Moment`: it is given UTC (`models.as_utc`) when the model
is made, so it goes out as "2026-11-20T10:00:00Z" however it was read. A test walks every route's
answer model for a plain `datetime` (tests/test_times_in_answers.py).
"""

from datetime import datetime
from typing import Annotated

from pydantic.functional_validators import AfterValidator

from mealwright.models import as_utc

Moment = Annotated[datetime, AfterValidator(as_utc)]
