"""Fill one database through ONE old release's own public API (a dev script, not shipped, not
run by the tests). `make_databases.py` runs this file with that release's own Python
environment and its own code, so the database is exactly what that release writes.

    <that release's python> fill_one.py <where to put the .sqlite file> <tag>

What it makes depends on which routes the release has (it asks the release's own OpenAPI
list): an admin; from 0.2 shops, ingredients, stock and a second login; from 0.3 a shopping
list with ticked lines; from 0.4 recipes; from 0.6 a plan with meals and (batch cook) tubs; from
0.8 a batch-cook session; from 0.9 a second person with a login. No network is used: the
app runs in this process behind FastAPI's test client.
"""

import json
import sqlite3
import sys
import tempfile
import uuid
import warnings
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

warnings.simplefilter("ignore")

from fastapi.testclient import TestClient  # noqa: E402

from mealwright.config import Settings  # noqa: E402
from mealwright.main import create_app  # noqa: E402

API = "/api/v1"
PASSWORD = "correct horse battery"
SECOND_PASSWORD = "second person's long password"


def ok(response: Any, status: int | None = 200) -> Any:
    """The answer's body; `status` None accepts any success."""
    good = response.status_code < 300 if status is None else response.status_code == status
    assert good, f"{response.request.url}: {response.status_code} {response.text[:400]}"
    return response.json() if response.content else None


def main(target: Path, tag: str) -> None:
    data_dir = Path(tempfile.mkdtemp(prefix="up"))
    try:
        settings = Settings(data_dir=data_dir, run_jobs=False)
    except Exception:
        settings = Settings(data_dir=data_dir)
    app = create_app(settings)
    with TestClient(app, base_url="https://testserver") as client:
        paths = set(app.openapi()["paths"])
        has = lambda path: f"{API}{path}" in paths  # noqa: E731
        made: dict[str, Any] = {"tag": tag}
        fill(client, app, has, made)
    db = data_dir / "mealwright.db"
    with sqlite3.connect(db) as connection:
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        connection.execute("PRAGMA journal_mode=DELETE")
        connection.execute("VACUUM")
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(db.read_bytes())
    made["bytes"] = target.stat().st_size
    print(json.dumps(made))


def fill(client: TestClient, app: Any, has: Any, made: dict[str, Any]) -> None:
    body = {"name": "Sam", "username": "sam", "password": PASSWORD}
    code = getattr(app.state, "setup_code", None)
    if code:
        body["setup_code"] = code
    ok(client.post(f"{API}/setup", json=body), 201)

    if not has("/foods"):
        return  # 0.1: an admin and nothing else yet
    # 0.9.5-beta.3 (D3) renamed some routes: use whichever this release has.
    browser = "/household/fill-from-browser" if has("/household/fill-from-browser") else None
    browser = browser or "/household/from-browser"
    ok(client.post(f"{API}{browser}", json={"time_zone": "Europe/London"}))
    shops = {
        name: ok(client.post(f"{API}/shops", json={"name": name}), 201)
        for name in ("Corner shop", "Big supermarket")
    }
    shop_id = {name: row.get("id") or row["shop"]["id"] for name, row in shops.items()}
    places = {row["name"]: row["id"] for row in ok(client.get(f"{API}/places"))}
    foods: dict[str, int] = {}
    for name, counted, staple, place, shop in (
        ("Red lentils", "weight", False, "Cupboard", "Big supermarket"),
        ("Onion", "count", False, "Cupboard", "Corner shop"),
        ("Tinned tomatoes", "count", False, "Cupboard", "Big supermarket"),
        ("Paneer", "weight", False, "Fridge", "Corner shop"),
        ("Spinach", "weight", False, "Fridge", "Corner shop"),
        ("Rice", "weight", False, "Cupboard", "Big supermarket"),
        ("Salt", "weight", True, "Spice rack", "Big supermarket"),
        ("Milk", "volume", False, "Fridge", "Corner shop"),
    ):
        row = ok(
            client.post(
                f"{API}/foods",
                json={
                    "name": name,
                    "counted_as": counted,
                    "staple": staple,
                    "place_id": places[place],
                    "shop_id": shop_id[shop],
                },
            ),
            201,
        )
        foods[name] = (row.get("food") or row)["id"]
    today = date.today()
    for name, amount, unit, place, use_by in (
        ("Red lentils", "500", "g", "Cupboard", None),
        ("Paneer", "225", "g", "Fridge", str(today + timedelta(days=5))),
        ("Milk", "1", "l", "Fridge", str(today + timedelta(days=3))),
        ("Onion", "4", "count", "Cupboard", None),
        ("Rice", "1", "kg", "Cupboard", None),
    ):
        amount_body: dict[str, Any] = {"amount": amount}
        if unit:
            amount_body["unit"] = unit
        ok(
            client.post(
                f"{API}/stock",
                json={
                    "food_id": foods[name],
                    "amount": amount_body,
                    "place_id": places[place],
                    "use_by": use_by,
                },
            ),
            201,
        )
    made["foods"] = len(foods)

    if has("/shopping/lists"):
        shopping(client, foods, shop_id, made)
    recipes: dict[str, int] = {}
    if has("/recipes"):
        recipes = make_recipes(client, foods, made)
    second_login(client, app, has, made)
    if has("/plan") and recipes:
        plan(client, has, recipes, made)
    if has("/batch-cook/sessions") and recipes:
        batch_session(client, recipes, made)
    from_plan = [p for p in ("/shopping/add-from-plan", "/shopping/from-plan") if has(p)]
    if from_plan and recipes:
        ok(client.post(f"{API}{from_plan[0]}"), None)


def shopping(
    client: TestClient, foods: dict[str, int], shop_id: dict[str, int], made: dict[str, Any]
) -> None:
    lists = ok(client.get(f"{API}/shopping/lists"))["lists"]
    main_list = next(row["id"] for row in lists if row["main"])
    extra = ok(client.post(f"{API}/shopping/lists", json={"name": "Party"}), 201)
    made["extra_list"] = extra["shopping_list"]["id"]
    items: dict[str, str] = {}
    for name, amount, unit in (
        ("Spinach", "300", "g"),
        ("Tinned tomatoes", "3", "count"),
        ("Milk", "2", "l"),
        ("Rice", "1", "kg"),
    ):
        amount_body: dict[str, Any] = {"amount": amount}
        if unit:
            amount_body["unit"] = unit
        row = ok(
            client.post(
                f"{API}/shopping/lists/{main_list}/items",
                json={"food_id": foods[name], "amount": amount_body},
            ),
            201,
        )
        items[name] = (row.get("item") or row)["id"]
    stamp = datetime.now(UTC).isoformat()
    for name in ("Milk", "Rice"):
        answer = ok(
            client.post(
                f"{API}/shopping/actions",
                json={
                    "protocol": 1,
                    "device_id": "0b6c3f0e-7c1a-4f7e-9d0b-2f7a3c1e5d42",
                    "login_id": 1,
                    "since": 0,
                    "sent_at": stamp,
                    "actions": [
                        {
                            "id": str(uuid.uuid4()),
                            "kind": "tick",
                            "made_at": stamp,
                            "seen": 0,
                            "item_id": items[name],
                        }
                    ],
                },
            )
        )
        made.setdefault("tick_results", []).append(answer["results"][0].get("status", "?"))
    made["list_items"] = len(items)


def make_recipes(client: TestClient, foods: dict[str, int], made: dict[str, Any]) -> dict[str, int]:
    def line(name: str, amount: str, unit: str | None) -> dict[str, Any]:
        return {
            "words": name.lower(),
            "amount": amount,
            "unit": unit,
            "food_id": foods[name],
        }

    recipes = {}
    for name, makes, lines, steps, tags in (
        (
            "Dal",
            4,
            [
                line("Red lentils", "250", "g"),
                line("Onion", "2", "count"),
                line("Tinned tomatoes", "1", "count"),
            ],
            ["Fry the onion.", "Add the lentils and tomatoes and simmer for 25 minutes."],
            ["dinner", "batch"],
        ),
        (
            "Saag paneer",
            3,
            [line("Paneer", "225", "g"), line("Spinach", "300", "g"), line("Onion", "1", "count")],
            ["Fry the paneer.", "Wilt the spinach and stir it all together."],
            ["dinner"],
        ),
        (
            "Rice and milk",
            2,
            [line("Rice", "200", "g"), line("Milk", "500", "ml")],
            ["Simmer the rice in the milk until thick."],
            [],
        ),
    ):
        payload = {
            "name": name,
            "serves": makes,
            "time_minutes": 40,
            "tags": tags,
            "lines": [dict(row, kind="ingredient") for row in lines],
            "steps": [{"text": text} for text in steps],
        }
        row = ok(client.post(f"{API}/recipes", json=payload), 201)
        recipes[name] = (row.get("recipe") or row)["id"]
    made["recipes"] = len(recipes)
    return recipes


def second_login(client: TestClient, app: Any, has: Any, made: dict[str, Any]) -> None:
    """From 0.9 a person is made through the API. Before that no release has a route for a
    second login, so one row is added with that release's own models, as its tests do."""
    if has("/people"):
        person = ok(
            client.post(f"{API}/people", json={"name": "Lorna", "portion_quarters": 4}), 201
        )
        person_id = next(row["id"] for row in person["people"] if row["name"] == "Lorna")
        ok(
            client.post(
                f"{API}/people/{person_id}/login", json={"username": "lorna", "role": "member"}
            ),
            None,
        )
        made["second"] = "lorna (a person)"
        return
    from mealwright.auth import hash_password
    from mealwright.models import Login

    with app.state.sessionmaker() as db:
        db.add(
            Login(
                household_id=1,
                username="lorna",
                name="Lorna",
                password_hash=hash_password(SECOND_PASSWORD),
                role="member",
            )
        )
        db.commit()
    made["second"] = "lorna (a login row)"


def plan(client: TestClient, has: Any, recipes: dict[str, int], made: dict[str, Any]) -> None:
    slots = ok(client.get(f"{API}/meal-slots"))
    slots = slots if isinstance(slots, list) else slots["slots"]
    dinner = next(row["id"] for row in slots if row["name"] == "Dinner")
    lunch = next(row["id"] for row in slots if row["name"] == "Lunch")
    today = date.today()
    placed = 0
    for offset, slot, name in (
        (0, dinner, "Saag paneer"),
        (1, dinner, "Rice and milk"),
        (2, lunch, "Dal"),
    ):
        ok(
            client.post(
                f"{API}/plan/items",
                json={
                    "date": str(today + timedelta(days=offset)),
                    "slot_id": slot,
                    "recipe_id": recipes[name],
                },
            ),
            None,
        )
        placed += 1
    made["plan_items"] = placed
    # A batch cook with tubs: the dal, five tubs.
    item = ok(
        client.post(
            f"{API}/plan/items",
            json={
                "date": str(today + timedelta(days=3)),
                "slot_id": dinner,
                "recipe_id": recipes["Dal"],
            },
        ),
        None,
    )
    item_id = item["item_id"]
    if item_id is not None:
        ok(client.post(f"{API}/plan/items/{item_id}/batch", json={"tub_count": 4}), None)
        made["tubs"] = 4


def batch_session(client: TestClient, recipes: dict[str, int], made: dict[str, Any]) -> None:
    slots = ok(client.get(f"{API}/meal-slots"))
    slots = slots if isinstance(slots, list) else slots["slots"]
    dinner = next(row["id"] for row in slots if row["name"] == "Dinner")
    when = str(date.today() + timedelta(days=5))
    ok(
        client.post(
            f"{API}/batch-cook/sessions",
            json={
                "date": when,
                "slot_id": dinner,
                "recipes": [
                    {"recipe_id": recipes["Saag paneer"], "tub_count": 2},
                    {"recipe_id": recipes["Dal"], "tub_count": 2},
                ],
            },
        ),
        None,
    )
    made["batch_sessions"] = 1


if __name__ == "__main__":
    main(Path(sys.argv[1]), sys.argv[2])
