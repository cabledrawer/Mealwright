"""More of what the batched reads must still answer exactly as the one-at-a-time ones did (the
copies in tests/golden_reads, made from the code at the commit "shellcheck: warnings and above;
./check's own 8 warnings fixed …" (15 Nov 2026), before 0.9.5's speed work, twice
with the same result): pack sizes, other
names, an "already have it" purchase, a merged ingredient, an incremental catch-up with a removed
line, the answer to a batch of changes, and a second household whose own ingredients and list
never show in the first one's answers. `WRITE_GOLDEN=1` makes the copies again."""

import json
import os
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient
from load_kit import API, normalised, seed, seed_more, statements
from sync_kit import action, ok, send

GOLDEN = Path(__file__).parent / "golden_reads"


def reads(ids: dict[str, Any], more: dict[str, Any]) -> dict[str, str]:
    return {
        "more_changes_all": "/shopping/sync?since=0",
        "more_changes_since": f"/shopping/sync?since={more['before']}",
        "more_list": f"/shopping/lists/{ids['list']}",
        "more_lists": "/shopping/lists",
        "more_pantry": "/pantry",
        "more_use_soon": "/pantry/use-soon",
        "more_foods": "/foods?limit=500",
        "more_today": "/today",
    }


def check(name: str, got: Any, today: Any) -> bool:
    got = normalised(got, today)
    file = GOLDEN / f"{name}.json"
    if os.environ.get("WRITE_GOLDEN"):
        file.write_text(json.dumps(got, sort_keys=True, indent=0) + "\n")
        return True
    return bool(json.loads(file.read_text()) == json.loads(json.dumps(got, sort_keys=True)))


def household(kitchen: TestClient) -> tuple[dict[str, Any], dict[str, Any]]:
    ids = seed(kitchen, 10)
    return ids, seed_more(kitchen, ids)


def test_the_odd_cases_answer_as_they_always_did(kitchen: TestClient) -> None:
    ids, more = household(kitchen)
    wrong = []
    for name, path in reads(ids, more).items():
        if not check(name, ok(kitchen.get(API + path)), ids["day0"]):
            wrong.append(name)
    assert not wrong, f"answers changed: {wrong}"


def test_the_answer_to_a_batch_of_changes_is_as_it_always_was(kitchen: TestClient) -> None:
    ids, more = household(kitchen)
    line = more["lines"][3]
    answer = send(
        kitchen,
        action("tick", counter_of(kitchen), item_id=line),
        action("set_amount", counter_of(kitchen), item_id=more["lines"][4], amount=7),
        since=more["before"],
    )
    assert check("more_batch_answer", answer, ids["day0"])


def counter_of(kitchen: TestClient) -> int:
    from sync_kit import counter

    return counter(kitchen)


def test_a_second_household_never_shows_in_the_first_ones_answers(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    ids, more = household(kitchen)
    # The neighbour has an ingredient of the same name, with stock and a list line of its own.
    theirs = ok(neighbour.post(f"{API}/foods", json={"name": "Ingredient 000"}), 201)["food"]
    ok(
        neighbour.post(
            f"{API}/stock",
            json={"food_id": theirs["id"], "amount": {"amount": 999, "unit": "g"}},
        ),
        201,
    )
    lists = ok(neighbour.get(f"{API}/shopping/lists"))["lists"]
    ok(
        neighbour.post(
            f"{API}/shopping/lists/{lists[0]['id']}/items",
            json={"food_id": theirs["id"], "amount": {"amount": 111, "unit": "g"}},
        ),
        201,
    )
    # And the first household's own answers are the same as without a neighbour.
    wrong = []
    for name, path in reads(ids, more).items():
        if not check(name, ok(kitchen.get(API + path)), ids["day0"]):
            wrong.append(name)
    assert not wrong, f"answers changed by a neighbour: {wrong}"


CEILING = {
    "more_changes_all": 22,
    "more_changes_since": 22,
    "more_list": 26,
    "more_lists": 9,
    "more_pantry": 18,
    "more_use_soon": 16,
    "more_foods": 16,
    "more_today": 48,
}


def test_the_odd_cases_still_ask_the_database_a_fixed_number_of_times(
    kitchen: TestClient,
) -> None:
    ids, more = household(kitchen)
    over = {
        name: n
        for name, path in reads(ids, more).items()
        if (n := statements(kitchen, API + path)) > CEILING[name]
    }
    assert not over, over
