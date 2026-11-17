# ruff: noqa: F811  (the fixtures come from test_recipe_import.py and are used by name)
"""F245: the Drafts list with ~700 drafts (a Mealie import) must stay quick."""

import time
from typing import Any

from drafts_kit import clone_drafts
from fastapi.testclient import TestClient
from sqlalchemy import event
from test_drafts import kept, listed
from test_recipe_import import PASTED, pantry, review, web  # noqa: F401


def test_the_list_of_700_drafts_is_quick_and_asks_the_database_a_few_times(
    kitchen: TestClient, pantry: dict[str, Any], web: Any
) -> None:
    shown = review(kitchen, PASTED)
    assert any(line["label"] == "needs_you" for line in shown["lines"])
    # A Mealie recipe is longer than the sample: 30 lines, matched and waiting.
    shown["lines"] = [dict(shown["lines"][n % len(shown["lines"])]) for n in range(30)]
    kept(kitchen, shown)
    clone_drafts(kitchen, 700)
    queries: list[str] = []
    engine = kitchen.app.state.sessionmaker.kw["bind"]  # type: ignore[attr-defined]

    def note(*args: Any) -> None:
        queries.append(args[2])

    event.listen(engine, "before_cursor_execute", note)
    started = time.perf_counter()
    try:
        found = listed(kitchen)
    finally:
        event.remove(engine, "before_cursor_execute", note)
    took = time.perf_counter() - started
    print(f"700 drafts: {took:.2f}s, {len(queries)} queries")
    assert len(found) == 701
    assert len(queries) < 40, len(queries)
    assert took < 3, took
