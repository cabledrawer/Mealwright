"""The reads a page makes when it opens stay a fixed number of statements however big the
household is (0.9.5 speed work), and still give the answers they gave when they asked the
database about one ingredient, one packet or one line at a time.

The second part compares each answer with a copy saved from the code before it was changed
(tests/golden_reads, made from the same seeded household). To make the copies again after a
change that is meant to alter an answer: `WRITE_GOLDEN=1 pytest tests/test_load_queries.py`."""

import json
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from load_kit import API, normalised, page_load_reads, seed, statements
from sync_kit import ok

GOLDEN = Path(__file__).parent / "golden_reads"

# The most statements each read may make, on a household of 6 and on one of 18 ingredients (and
# so on: the same number for both). Measured when this was written, with a little room.
CEILING = {
    "setup": 2,
    "me": 2,
    "household": 4,
    "drafts": 5,
    "tags": 5,
    "meal_slots": 5,
    "plan_day": 30,
    "plan_six_weeks": 30,
    "plan_people": 5,
    "tubs_left": 5,
    "recipes": 20,
    "recipe": 18,
    "recipe_stock": 16,
    "shopping_changes": 20,
    "shopping_lists": 9,
    "shopping_list": 14,
    "pantry": 16,
    "pantry_search": 17,
    "pantry_use_soon": 14,
    "today": 48,
    "stocktake": 10,
    "places": 5,
    "foods": 14,
    "shops": 5,
}


@pytest.mark.parametrize("size", [6, 18])
def test_a_page_load_read_asks_the_database_a_fixed_number_of_times(
    kitchen: TestClient, size: int
) -> None:
    reads = page_load_reads(seed(kitchen, size))
    assert set(reads) == set(CEILING)
    over = {
        name: n
        for name, path in reads.items()
        if (n := statements(kitchen, API + path)) > CEILING[name]
    }
    assert not over, f"more statements than allowed at {size} ingredients: {over}"


def test_the_answers_are_the_ones_the_one_at_a_time_queries_gave(kitchen: TestClient) -> None:
    ids = seed(kitchen, 8)
    reads = page_load_reads(ids)
    GOLDEN.mkdir(exist_ok=True)
    wrong = []
    for name, path in reads.items():
        got = normalised(ok(kitchen.get(API + path)), ids["day0"])
        file = GOLDEN / f"{name}.json"
        if os.environ.get("WRITE_GOLDEN"):
            file.write_text(json.dumps(got, sort_keys=True, indent=0) + "\n")
        elif json.loads(file.read_text()) != json.loads(json.dumps(got, sort_keys=True)):
            wrong.append(name)
    assert not wrong, f"answers changed: {wrong}"
