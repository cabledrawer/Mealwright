"""F125 (cabledrawer 3 Nov): "Undo of "Cooked it" from Pantry → Recent changes must also undo the
meal's "Cooked" (one change, one Undo, as the toast does)."

One "Cooked it" is the pantry's `cooked` change (the review's confirm) and the meal's
`plan_cooked` answer that follows it (with any tubs it made). Recent changes lists only the
first, so the server keeps them together: the Undo of either takes back both, whichever way it
comes (Recent changes, the toast, Ctrl+Z, the sync log). A tub of it that "Eat it on…" then put
on a meal comes off that meal with them."""

from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import PHONE_A, ok, one
from test_cooking import amounts, cook
from test_deduction import recipe_of
from test_history import wren  # noqa: F401 (a fixture)
from test_plan import db_of, slot_ids
from test_recipe_list import line, stock
from test_recipes import food, make

from mealwright.models import Change, CookedRecord, Household, Meal, SyncAction, Tub

API = "/api/v1"


def eaten_today(client: TestClient, in_stock: int = 800) -> tuple[dict[str, Any], int, int]:
    """Zorba dal in the pantry and a curry of it planned for today's lunch."""
    dal = food(client, "Zorba dal")
    stock(client, dal["id"], in_stock, "g")
    recipe = recipe_of(client, [line(dal["id"], 200, "g")])
    planned = ok(
        client.post(
            f"{API}/plan/items",
            json={
                "date": date.today().isoformat(),
                "slot_id": slot_ids(client)["Lunch"],
                "recipe_id": recipe["id"],
                "servings": 2,
            },
        ),
        201,
    )
    return dal, int(planned["meal_id"]), int(planned["item_id"])


def answer_cooked(client: TestClient, meal_id: int, tubs: int = 0) -> dict[str, Any]:
    body: dict[str, Any] = {"leftovers": {"count": tubs}} if tubs else {}
    result: dict[str, Any] = ok(client.post(f"{API}/plan/meals/{meal_id}/cooked", json=body))
    return result


def undo(client: TestClient, change_id: int) -> Any:
    return client.post(f"{API}/changes/{change_id}/undo")


def status_of(client: TestClient, meal_id: int) -> str | None:
    with db_of(client) as db:
        meal = db.get(Meal, meal_id)
        return meal.status if meal is not None else None


def tubs(client: TestClient) -> int:
    with db_of(client) as db:
        return len(db.scalars(select(Tub)).all())


def undone(client: TestClient, change_id: int) -> bool:
    with db_of(client) as db:
        change = db.get(Change, change_id)
        assert change is not None
        return change.undone_by_change_id is not None


def pantry_list(client: TestClient) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = ok(client.get(f"{API}/changes?area=pantry"))["changes"]
    return changes


def test_recent_changes_undo_of_cooked_it_also_takes_back_the_meals_cooked(
    kitchen: TestClient,
) -> None:
    dal, meal, item = eaten_today(kitchen)
    pantry = ok(cook(kitchen, item), 201)["change"]
    answer = answer_cooked(kitchen, meal, tubs=2)["change"]
    assert status_of(kitchen, meal) == "cooked" and tubs(kitchen) == 2
    # One "Cooked it", one entry in Pantry → Recent changes.
    listed = [c for c in pantry_list(kitchen) if c["kind"] in ("cooked", "plan_cooked")]
    assert [c["id"] for c in listed] == [pantry["id"]]

    said = ok(undo(kitchen, pantry["id"]))
    assert said["result"] == "done"
    assert amounts(kitchen, dal["id"]) == [800_000]
    assert status_of(kitchen, meal) == "planned"  # asked about again
    assert tubs(kitchen) == 0  # the tubs it made are gone
    assert undone(kitchen, answer["id"])
    with db_of(kitchen) as db:
        assert db.scalars(select(CookedRecord)).all() == []
    # The Undo row is the one Recent changes shows, and its answer says so.
    assert pantry_list(kitchen)[0]["id"] == said["change"]["id"]
    # The toast's own Undo of the answer finds it already undone: nothing is done twice.
    again = undo(kitchen, answer["id"])
    assert again.status_code == 409 and again.json()["code"] == "already_undone"
    assert amounts(kitchen, dal["id"]) == [800_000]


def test_the_meals_undo_takes_back_the_pantry_too(kitchen: TestClient) -> None:
    dal, meal, item = eaten_today(kitchen)
    pantry = ok(cook(kitchen, item), 201)["change"]
    answer = answer_cooked(kitchen, meal)["change"]
    assert ok(undo(kitchen, answer["id"]))["result"] == "done"
    assert status_of(kitchen, meal) == "planned"
    assert amounts(kitchen, dal["id"]) == [800_000]
    assert undone(kitchen, pantry["id"])
    # Cooked it can be done again, as after any Undo of it.
    assert cook(kitchen, item).status_code == 201


def test_a_retried_undo_answers_from_the_first(kitchen: TestClient) -> None:
    dal, meal, item = eaten_today(kitchen)
    pantry = ok(cook(kitchen, item), 201)["change"]
    answer_cooked(kitchen, meal)
    key = {"Idempotency-Key": "undo-cooked-1"}
    first = ok(kitchen.post(f"{API}/changes/{pantry['id']}/undo", headers=key))
    retry = kitchen.post(f"{API}/changes/{pantry['id']}/undo", headers=key)
    assert retry.status_code == 200 and retry.headers.get("Idempotent-Replayed") == "true"
    assert retry.json()["change"]["id"] == first["change"]["id"]
    assert amounts(kitchen, dal["id"]) == [800_000]


def test_a_partly_undone_pantry_says_so_from_either_undo(kitchen: TestClient) -> None:
    dal, meal, item = eaten_today(kitchen, in_stock=200)
    ok(cook(kitchen, item), 201)  # takes the whole packet
    answer = answer_cooked(kitchen, meal)["change"]
    with db_of(kitchen) as db:
        from mealwright.models import StockLot

        for lot in db.scalars(select(StockLot).where(StockLot.food_id == dal["id"])):
            db.delete(lot)  # the packet is thrown away since
        db.commit()
    said = ok(undo(kitchen, answer["id"]))
    assert said["result"] != "done"
    assert status_of(kitchen, meal) == "planned"


def test_eat_it_on_comes_off_its_meal_with_the_undo_of_cooked_it(kitchen: TestClient) -> None:
    _dal, meal, item = eaten_today(kitchen)
    pantry = ok(cook(kitchen, item), 201)["change"]
    answer_cooked(kitchen, meal, tubs=1)
    with db_of(kitchen) as db:
        tub = db.scalars(select(Tub)).one().id
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    body = {"date": tomorrow, "slot_id": slot_ids(kitchen)["Dinner"]}
    placed = ok(kitchen.post(f"{API}/plan/tubs/{tub}/place", json=body))
    assert ok(undo(kitchen, pantry["id"]))["result"] == "done"
    assert undone(kitchen, placed["change"]["id"])
    assert tubs(kitchen) == 0 and status_of(kitchen, meal) == "planned"
    with db_of(kitchen) as db:
        assert db.get(Meal, placed["meal_id"]) is None  # the meal it made for the tub went


def test_undo_of_eat_it_on_alone_leaves_the_cooking(kitchen: TestClient) -> None:
    _dal, meal, item = eaten_today(kitchen)
    pantry = ok(cook(kitchen, item), 201)["change"]
    answer = answer_cooked(kitchen, meal, tubs=1)["change"]
    with db_of(kitchen) as db:
        tub = db.scalars(select(Tub)).one().id
    tomorrow = (date.today() + timedelta(days=1)).isoformat()
    body = {"date": tomorrow, "slot_id": slot_ids(kitchen)["Dinner"]}
    placed = ok(kitchen.post(f"{API}/plan/tubs/{tub}/place", json=body))
    assert ok(undo(kitchen, placed["change"]["id"]))["result"] == "done"
    assert not undone(kitchen, pantry["id"]) and not undone(kitchen, answer["id"])
    assert tubs(kitchen) == 1 and status_of(kitchen, meal) == "cooked"


def test_separate_presses_stay_separate(kitchen: TestClient) -> None:
    dal, meal, item = eaten_today(kitchen)
    pantry = ok(cook(kitchen, item), 201)["change"]
    stock(kitchen, dal["id"], 100, "g")  # something else in between: another press
    answer = answer_cooked(kitchen, meal)["change"]
    assert ok(undo(kitchen, answer["id"]))["result"] == "done"
    assert not undone(kitchen, pantry["id"]) and status_of(kitchen, meal) == "planned"
    assert sum(amounts(kitchen, dal["id"])) == 800_000 - 100_000 + 100_000  # cooking stands


def test_a_meal_answered_before_its_review_stays_separate(kitchen: TestClient) -> None:
    _dal, meal, item = eaten_today(kitchen)
    answer = answer_cooked(kitchen, meal)["change"]
    pantry = ok(cook(kitchen, item), 201)["change"]
    assert ok(undo(kitchen, pantry["id"]))["result"] == "done"
    assert not undone(kitchen, answer["id"]) and status_of(kitchen, meal) == "cooked"


def test_another_logins_cooked_is_not_joined(kitchen: TestClient, wren: TestClient) -> None:  # noqa: F811
    _dal, meal, item = eaten_today(kitchen)
    pantry = ok(cook(kitchen, item), 201)["change"]
    answer = answer_cooked(wren, meal)["change"]
    assert ok(undo(wren, answer["id"]))["result"] == "done"
    assert not undone(kitchen, pantry["id"])


def test_a_sync_undo_of_cooked_it_also_takes_back_the_meals_cooked(kitchen: TestClient) -> None:
    with db_of(kitchen) as db:
        # The list looks at no day, so the plan lists nothing: the review's shortfall is the
        # list change that gives the cooking its sync-log row (as `far_curry` does).
        db.scalars(select(Household)).one().plan_ahead_days = 0
        db.commit()
    dal = food(kitchen, "Zorba dal")
    stock(kitchen, dal["id"], 60, "g")  # short: the review puts the rest on the list
    recipe = recipe_of(kitchen, [line(dal["id"], 200, "g")])
    planned = ok(
        kitchen.post(
            f"{API}/plan/items",
            json={
                "date": date.today().isoformat(),
                "slot_id": slot_ids(kitchen)["Lunch"],
                "recipe_id": recipe["id"],
                "servings": 2,
            },
        ),
        201,
    )
    pantry = ok(cook(kitchen, planned["item_id"]), 201)["change"]
    answer_cooked(kitchen, planned["meal_id"])
    with db_of(kitchen) as db:
        action_id = (
            db.scalars(select(SyncAction).where(SyncAction.change_id == pantry["id"])).one().id
        )
    assert one(kitchen, "undo", 0, PHONE_A, undoes=action_id)["status"] == "applied"
    assert amounts(kitchen, dal["id"]) == [60_000]
    assert status_of(kitchen, planned["meal_id"]) == "planned"


def test_a_meal_with_a_batch_and_a_recipe_is_one_row_with_one_undo(kitchen: TestClient) -> None:
    """Review 1, L1: a meal of a Cook once batch and an ordinary recipe records two `cooked`
    changes in one press (the meal's recipes, then the batch). Recent changes shows them as one
    row, with the whole press's amounts and one Undo; the Undo's own rows are one row too."""
    dal = food(kitchen, "Zorba dal")
    stock(kitchen, dal["id"], 900, "g")
    items = []
    for name in ("Zorba sambar", "Zorba rasam"):
        planned = ok(
            kitchen.post(
                f"{API}/plan/items",
                json={
                    "date": date.today().isoformat(),
                    "slot_id": slot_ids(kitchen)["Dinner"],
                    "recipe_id": make(kitchen, name, serves=4, lines=[line(dal["id"], 200, "g")])[
                        "id"
                    ],
                    "servings": 4,
                },
            ),
            201,
        )
        items.append(planned["item_id"])
    meal = int(planned["meal_id"])
    batch = ok(
        kitchen.post(
            f"{API}/plan/items/{items[0]}/batch", json={"tub_count": 2, "pattern": "pick"}
        ),
        201,
    )["batch_id"]
    # The review's one Confirm: the meal's recipes, then the batch, then the meal's answer.
    own = ok(
        kitchen.post(f"{API}/plan/meals/{meal}/cook", json={"items": [{"item_id": items[1]}]}), 201
    )
    ok(kitchen.post(f"{API}/plan/batches/{batch}/cook", json={}), 201)
    answer_cooked(kitchen, meal)
    left = sum(amounts(kitchen, dal["id"]))
    assert left < 700_000  # both took some

    listed = [c for c in pantry_list(kitchen) if c["kind"] == "cooked"]
    assert [c["id"] for c in listed] == [own["change"]["id"]]
    totals = [t for t in listed[0]["totals"] if t["food_id"] == dal["id"]]
    assert [(t["before"]["amount"], t["after"]["amount"]) for t in totals] == [(900, left / 1000)]

    said = ok(undo(kitchen, own["change"]["id"]))
    assert said["result"] == "done"
    assert sum(amounts(kitchen, dal["id"])) == 900_000
    assert status_of(kitchen, meal) == "planned"
    rows = pantry_list(kitchen)
    assert [c["id"] for c in rows if c["kind"] == "undo"] == [said["change"]["id"]]
    # The Undo row reads the whole press back, as the pantry is now (review 2, M).
    undo_row = next(c for c in rows if c["kind"] == "undo")
    back = [t for t in undo_row["totals"] if t["food_id"] == dal["id"]]
    assert [(t["before"]["amount"], t["after"]["amount"]) for t in back] == [(left / 1000, 900)]
    assert [c["id"] for c in rows if c["kind"] == "cooked"] == [own["change"]["id"]]
    assert not any(c["can_undo"] for c in rows if c["kind"] == "cooked")


def all_list(client: TestClient, query: str = "") -> dict[str, Any]:
    """Settings › Recent changes: every kind of change, not one area."""
    return dict(ok(client.get(f"{API}/changes{query}")))


def test_settings_recent_changes_has_one_row_for_one_cooked_it(kitchen: TestClient) -> None:
    """cabledrawer 7 Nov: "fold it into one row (one action, one Undo)". The meal's answer
    (`plan_cooked`) is not a row of its own beside the pantry's `cooked`, and nor is its Undo."""
    _dal, meal, item = eaten_today(kitchen)
    pantry = ok(cook(kitchen, item), 201)["change"]
    answer = answer_cooked(kitchen, meal, tubs=1)["change"]
    cooked = [c for c in all_list(kitchen)["changes"] if c["kind"] in ("cooked", "plan_cooked")]
    assert [c["id"] for c in cooked] == [pantry["id"]]
    assert cooked[0]["can_undo"]

    said = ok(undo(kitchen, pantry["id"]))
    assert said["result"] == "done" and undone(kitchen, answer["id"])
    rows = all_list(kitchen)["changes"]
    assert [c["id"] for c in rows if c["kind"] == "undo"] == [said["change"]["id"]]
    assert [c["id"] for c in rows if c["kind"] in ("cooked", "plan_cooked")] == [pantry["id"]]


def test_a_cooked_it_is_never_split_across_pages(kitchen: TestClient) -> None:
    """Newest first, a page of two: the Cooked it row is whole on the page where its first
    change is, and the answer that came after it is not shown alone on the page before."""
    _dal, meal, item = eaten_today(kitchen)
    pantry = ok(cook(kitchen, item), 201)["change"]
    answer = answer_cooked(kitchen, meal)["change"]
    for name in ("Corner shop", "Market"):  # a shop's removal is a change of its own
        shop = ok(kitchen.post(f"{API}/shops", json={"name": name}), 201)
        ok(kitchen.delete(f"{API}/shops/{shop['id']}"))
    first = all_list(kitchen, "?limit=2")
    assert pantry["id"] not in [c["id"] for c in first["changes"]]
    assert answer["id"] not in [c["id"] for c in first["changes"]]
    second = all_list(kitchen, f"?limit=50&before={first['next']}")
    ids = [c["id"] for c in second["changes"]]
    assert pantry["id"] in ids and answer["id"] not in ids
