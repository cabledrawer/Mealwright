"""A household of a chosen size, and a count of the SQL statements a request makes (0.9.5 speed
work). Used by the tests that keep the reads a page makes on load to a fixed number of
statements, however many ingredients, list lines or meals the household has."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import event
from sync_kit import counter, ok, one

API = "/api/v1"


def seed(kitchen: TestClient, size: int) -> dict[str, Any]:
    """`size` ingredients (weights, volumes and counts, two places, some with a use-by date,
    some with two packets), `size` lines on the main list (some from a recipe's plan), `size`
    // 2 recipes that use them, and a meal in each slot of `size` // 2 days."""
    places = ok(kitchen.get(f"{API}/places"))
    place_ids = [p["id"] for p in places]
    day0 = date.fromisoformat(ok(kitchen.get(f"{API}/household"))["today"])
    foods: list[dict[str, Any]] = []
    kinds = ["weight", "volume", "count"]
    for i in range(size):
        counted = kinds[i % 3]
        made = ok(
            kitchen.post(
                f"{API}/foods",
                json={
                    "name": f"Ingredient {i:03d}",
                    "counted_as": counted,
                    "place_id": place_ids[i % 2],
                },
            ),
            201,
        )["food"]
        foods.append(made)
        unit = {"weight": "g", "volume": "ml", "count": "count"}[counted]
        for pack in range(1 + (i % 2)):
            body: dict[str, Any] = {
                "food_id": made["id"],
                "amount": {"amount": 100 + 50 * pack + i, "unit": unit},
                "place_id": place_ids[(i + pack) % len(place_ids)],
            }
            if i % 3 == 0:
                body["use_by"] = (day0 + timedelta(days=i % 9)).isoformat()
            ok(kitchen.post(f"{API}/stock", json=body), 201)
    for i in range(max(2, size // 3)):  # staples: not counted in the pantry, shown in its staples
        ok(
            kitchen.post(
                f"{API}/foods",
                json={"name": f"Staple {i:03d}", "counted_as": "weight", "staple": True},
            ),
            201,
        )
    lists = ok(kitchen.get(f"{API}/shopping/lists"))["lists"]
    main = next(row["id"] for row in lists if row["main"])
    for i, made in enumerate(reversed(foods)):
        unit = {"weight": "g", "volume": "ml", "count": "count"}[made["counted_as"]]
        line = ok(
            kitchen.post(
                f"{API}/shopping/lists/{main}/items",
                json={"food_id": made["id"], "amount": {"amount": 200 + i, "unit": unit}},
            ),
            201,
        )
        if i % 3 == 0:  # a third of the lines are ticked
            one(
                kitchen,
                "tick",
                counter(kitchen),
                item_id=(line.get("item") or line.get("line") or {})["id"],
            )
    recipes: list[dict[str, Any]] = []
    for r in range(max(1, size // 2)):
        picked = [foods[(r * 2 + k) % size] for k in range(3)]
        lines = [
            {
                "words": f.get("name", "x").lower(),
                "food_id": f["id"],
                "amount": 1 if f["counted_as"] == "count" else 100,
                "unit": {"weight": "g", "volume": "ml", "count": "count"}[f["counted_as"]],
            }
            for f in picked
        ]
        recipes.append(
            ok(
                kitchen.post(
                    f"{API}/recipes",
                    json={
                        "name": f"Dish {r:03d}",
                        "serves": 4,
                        "time_minutes": 30,
                        "lines": lines,
                        "steps": [{"text": "Cook it."}],
                    },
                ),
                201,
            )
        )
    slots = ok(kitchen.get(f"{API}/meal-slots"))
    slot_ids = [s["id"] for s in slots if s["name"] in ("Breakfast", "Lunch", "Dinner")]
    for d in range(max(1, size // 2)):
        for k, slot in enumerate(slot_ids):
            ok(
                kitchen.post(
                    f"{API}/plan/items",
                    json={
                        "date": (day0 + timedelta(days=d)).isoformat(),
                        "slot_id": slot,
                        "recipe_id": recipes[(d * 3 + k) % len(recipes)]["id"],
                    },
                ),
                201,
            )
    return {"day0": day0, "list": main, "foods": foods, "recipes": recipes, "places": place_ids}


@contextmanager
def counting(kitchen: TestClient) -> Iterator[dict[str, int]]:
    """The number of SQL statements run inside the block, as {"n": ...}."""
    engine = kitchen.app.state.engine  # type: ignore[attr-defined]
    seen = {"n": 0}

    def count(*_: Any) -> None:
        seen["n"] += 1

    event.listen(engine, "before_cursor_execute", count)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", count)


def statements(kitchen: TestClient, path: str) -> int:
    """How many statements one GET makes (the second call, so one-off start-up reads and
    compiled-statement caching are out of it)."""
    ok(kitchen.get(path))
    with counting(kitchen) as seen:
        ok(kitchen.get(path))
    return seen["n"]


# --- What a page asks for when it opens -----------------------------------------------------------


def page_load_reads(ids: dict[str, Any]) -> dict[str, str]:
    """Every GET the app's pages make when they open (name -> path), for a household made by
    `seed`."""
    day = ids["day0"].isoformat()
    week_end = (ids["day0"] + timedelta(days=41)).isoformat()
    recipe = ids["recipes"][0]["id"]
    return {
        "setup": "/setup",
        "me": "/me",
        "household": "/household",
        "drafts": "/recipes/drafts",
        "tags": "/recipes/tags",
        "meal_slots": "/meal-slots",
        "plan_day": f"/plan?from={day}&to={day}",
        "plan_six_weeks": f"/plan?from={day}&to={week_end}",
        "plan_people": "/plan/people",
        "tubs_left": "/plan/tubs-left",
        "recipes": "/recipes?limit=50",
        "recipe": f"/recipes/{recipe}",
        "recipe_stock": f"/recipes/{recipe}/stock",
        "shopping_changes": "/shopping/changes?since=0",
        "shopping_lists": "/shopping/lists",
        "shopping_list": f"/shopping/lists/{ids['list']}",
        "pantry": "/pantry",
        "pantry_search": "/pantry?q=ingredient",
        "pantry_use_soon": "/pantry/use-soon",
        "today": "/today",
        "stocktake": "/stocktake",
        "places": "/places",
        "foods": "/foods?limit=500",
        "shops": "/shops",
    }


_UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
_STAMP = re.compile(r"\d{4}-\d{2}-\d{2}T[\d:.]+(?:Z|[+-]\d{2}:?\d{2})?")
_DAY = re.compile(r"\d{4}-\d{2}-\d{2}")
_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_WEEKDAY = re.compile(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun)\b")


def normalised(answer: Any, today: date) -> Any:
    """An answer with what changes from one run to the next made steady: IDs made at random
    become U1, U2 (in the order they appear), moments become "<moment>", days become their
    distance from today ("D+3"), and day names ("Sun, Mon") their distance from today's day of
    the week ("W+0, W+1"), so the answers don't depend on which day the tests run. Everything
    else is kept as it is."""
    seen: dict[str, str] = {}

    def text(value: str) -> str:
        value = _STAMP.sub("<moment>", value)
        value = _DAY.sub(lambda m: f"D{(date.fromisoformat(m.group()) - today).days:+d}", value)
        value = _WEEKDAY.sub(
            lambda m: f"W+{(_WEEKDAYS.index(m.group()) - today.weekday()) % 7}", value
        )
        return _UUID.sub(lambda m: seen.setdefault(m.group(), f"U{len(seen) + 1}"), value)

    def walk(value: Any) -> Any:
        if isinstance(value, dict):
            return {text(k): walk(v) for k, v in value.items()}
        if isinstance(value, list):
            return [walk(v) for v in value]
        return text(value) if isinstance(value, str) else value

    return walk(answer)


# --- A household with the odd cases: sizes, other names, "already have it", a merge, a removal ----


def seed_more(kitchen: TestClient, ids: dict[str, Any]) -> dict[str, Any]:
    """On top of `seed`: pack sizes (some usual, one pair with none usual), other names, a line
    "already have it" at home (a found-at-home purchase), two ingredients merged (their list lines
    move), and a line removed (a tombstone, for a phone catching up). Returns the counter before
    the removal and merge, so a read `since` it has the incremental answer."""
    foods = ids["foods"]
    unit = {"weight": "g", "volume": "ml", "count": "count"}
    for i, made in enumerate(foods[:6]):
        size_unit = unit[made["counted_as"]]
        ok(
            kitchen.post(
                f"{API}/foods/{made['id']}/sizes",
                json={
                    "name": "packet",
                    "amount": {"amount": 500 if size_unit != "count" else 12, "unit": size_unit},
                    **({"usual": True} if i % 2 == 0 else {}),
                },
            ),
            201,
        )
        ok(
            kitchen.post(
                f"{API}/foods/{made['id']}/other-names", json={"name": f"Also called {i:03d}"}
            ),
            201,
        )
    answer = ok(kitchen.get(f"{API}/shopping/changes?since=0"))
    lines = [row["id"] for row in answer["items"]]
    one(
        kitchen,
        "found_at_home",
        counter(kitchen),
        item_id=lines[1],
        amount=150,
    )
    before = counter(kitchen)
    one(kitchen, "delete", before, item_id=lines[2])
    # Two ingredients merged. The line of the one that goes is taken off first: two lines of one
    # ingredient would be shown in an order that depends on their random IDs.
    gone = next(row["id"] for row in answer["items"] if row["food_id"] == foods[-1]["id"])
    one(kitchen, "delete", counter(kitchen), item_id=gone)
    ok(kitchen.post(f"{API}/foods/{foods[-1]['id']}/merge", json={"into_id": foods[-4]["id"]}))
    return {"before": before, "lines": lines}
