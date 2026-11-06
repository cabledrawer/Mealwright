"""Pantry → Recent changes stays quick with many "Cooked it" presses of many parts (0.7
security review, L1): the page folds each press's later parts into its first row, and does it in
a fixed number of queries per press, however many parts the press has."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sync_kit import ok
from test_plan import db_of
from test_recipe_list import stock
from test_recipes import food

from mealwright.models import Change, ChangeLine, Login, StockLot, utcnow

API = "/api/v1"


def seed(kitchen: TestClient, presses: int, parts: int) -> None:
    """`presses` presses of `parts` pantry changes each (one packet line apiece), then the
    meal's answer, joined the way together.join_answer joins them."""
    with db_of(kitchen) as db:
        lot = db.scalars(select(StockLot)).first()
        login = db.scalars(select(Login)).first()
        assert lot is not None and login is not None
        for press in range(presses):
            made: list[Change] = []
            for part in range(parts + 1):
                answer = part == parts
                change = Change(
                    household_id=1,
                    kind="plan_cooked" if answer else "cooked",
                    login_id=login.id,
                    login_name=login.name,
                    food_id=None if answer else lot.food_id,
                    at=utcnow(),
                    summary=f"Cooked press {press}" if not answer else "Cooked it",
                )
                db.add(change)
                db.flush()
                made.append(change)
                if not answer:
                    db.add(
                        ChangeLine(
                            household_id=1,
                            change_id=change.id,
                            food_id=lot.food_id,
                            lot_id=lot.id,
                            amount_before_milli=10_000,
                            amount_after_milli=5_000,
                            place_before_id=lot.place_id,
                            place_after_id=lot.place_id,
                            total_before_milli=10_000,
                            total_after_milli=5_000,
                        )
                    )
            ids = [c.id for c in made]
            for change in made:
                change.undo_data = {"together": ids}
        db.commit()


def read(kitchen: TestClient) -> tuple[list[dict[str, Any]], int]:
    engine = kitchen.app.state.engine  # type: ignore[attr-defined]
    counted: list[str] = []

    def note(*args: Any) -> None:
        counted.append(str(args[2]))

    event.listen(engine, "before_cursor_execute", note)
    try:
        body = ok(kitchen.get(f"{API}/changes", params={"area": "pantry", "limit": 100}))
    finally:
        event.remove(engine, "before_cursor_execute", note)
    return body["changes"], len(counted)


def test_a_press_is_one_row_however_many_parts_it_has(kitchen: TestClient) -> None:
    stock(kitchen, food(kitchen, "Zorba dal")["id"], 900, "g")
    seed(kitchen, presses=3, parts=21)
    changes, _ = read(kitchen)
    cooked = [c for c in changes if c["kind"] == "cooked"]
    assert len(cooked) == 3  # each press's later parts are folded into its first row
    for row in cooked:
        assert len(row["lines"]) == 21
        assert len(row["totals"]) == 1


def test_the_queries_do_not_grow_with_the_parts_of_a_press(kitchen: TestClient) -> None:
    stock(kitchen, food(kitchen, "Zorba dal")["id"], 900, "g")
    seed(kitchen, presses=4, parts=2)
    _, few = read(kitchen)
    with db_of(kitchen) as db:
        for change in db.scalars(select(Change).where(Change.kind.in_(["cooked", "plan_cooked"]))):
            db.delete(change)  # its lines go with it
        db.commit()
    seed(kitchen, presses=4, parts=21)
    _, many = read(kitchen)
    assert many == few
