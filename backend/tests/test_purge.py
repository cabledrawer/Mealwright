"""Removed ingredients are deleted for good once their Undo has run out (7 days)."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import func, select, update

from mealwright import jobs
from mealwright.auth import hash_password
from mealwright.history import purge_removed, thin
from mealwright.models import (
    Change,
    ChangeLine,
    ChangeMonth,
    Food,
    FoodMerge,
    FoodName,
    FoodSize,
    FoodStandIn,
    Household,
    Login,
    StockLot,
    utcnow,
)

API = "/api/v1"


def db(kitchen: TestClient) -> Any:
    return kitchen.app.state.sessionmaker()  # type: ignore[attr-defined]


def food(kitchen: TestClient, name: str, **extra: Any) -> dict[str, Any]:
    found: dict[str, Any] = kitchen.post(f"{API}/foods", json={"name": name, **extra}).json()[
        "food"
    ]
    return found


def used_up(kitchen: TestClient, food_id: int, grams: int) -> None:
    body = {"food_id": food_id, "amount": {"amount": grams, "unit": "g"}}
    lot = kitchen.post(f"{API}/stock", json=body).json()["groups"][0]["lots"][0]
    kitchen.post(f"{API}/stock/{lot['id']}/used")


def remove(kitchen: TestClient, food_id: int) -> dict[str, Any]:
    response = kitchen.delete(f"{API}/foods/{food_id}")
    assert response.status_code == 200, response.text
    change: dict[str, Any] = response.json()["change"]
    return change


def removed_days_ago(kitchen: TestClient, food_id: int, days: float) -> None:
    with db(kitchen) as session:
        session.execute(
            update(Food)
            .where(Food.id == food_id)
            .values(removed_at=utcnow() - timedelta(days=days))
        )
        session.commit()


def purge(kitchen: TestClient, household_id: int = 1) -> int:
    with db(kitchen) as session:
        purged: int = purge_removed(session, session.get(Household, household_id))
        return purged


def exists(kitchen: TestClient, food_id: int) -> bool:
    with db(kitchen) as session:
        return session.get(Food, food_id) is not None


def test_not_before_the_undo_window_ends(kitchen: TestClient) -> None:
    toor = food(kitchen, "Toor dal")
    change = remove(kitchen, toor["id"])
    removed_days_ago(kitchen, toor["id"], 6.9)
    assert purge(kitchen) == 0
    assert exists(kitchen, toor["id"])
    # Still undoable, and Undo still works.
    assert kitchen.post(f"{API}/changes/{change['id']}/undo").json()["result"] == "done"


def test_deleted_for_good_after_seven_days(kitchen: TestClient) -> None:
    toor = food(kitchen, "Toor dal")
    moong = food(kitchen, "Moong dal")
    kitchen.post(f"{API}/foods/{toor['id']}/other-names", json={"name": "arhar dal"})
    kitchen.post(f"{API}/foods/{toor['id']}/sizes", json={"name": "packet", "amount": 500})
    kitchen.post(f"{API}/foods/{toor['id']}/stand-ins", json={"food_id": moong["id"]})
    kitchen.post(f"{API}/foods/{moong['id']}/stand-ins", json={"food_id": toor["id"]})
    kitchen.patch(f"{API}/foods/{toor['id']}", json={"cup_weight": 200})
    kitchen.post(f"{API}/foods/{toor['id']}/not-the-same", json={"food_id": moong["id"]})
    used_up(kitchen, toor["id"], 500)
    remove(kitchen, toor["id"])
    removed_days_ago(kitchen, toor["id"], 8)

    assert purge(kitchen) == 1
    assert not exists(kitchen, toor["id"])
    with db(kitchen) as session:
        for model, column in (
            (FoodName, FoodName.food_id),
            (FoodSize, FoodSize.food_id),
            (StockLot, StockLot.food_id),
            (ChangeLine, ChangeLine.food_id),
        ):
            assert (
                session.scalar(select(func.count()).select_from(model).where(column == toor["id"]))
                == 0
            )
        assert session.scalar(select(func.count()).select_from(FoodStandIn)) == 0
    # The other ingredient is untouched, and the name is free again.
    assert kitchen.get(f"{API}/foods/{moong['id']}").json()["stand_ins"] == []
    assert kitchen.get(f"{API}/foods/{toor['id']}").status_code == 404
    assert kitchen.post(f"{API}/foods", json={"name": "Toor dal"}).status_code == 201
    assert purge(kitchen) == 0  # safe to run again


def test_history_still_reads(kitchen: TestClient) -> None:
    toor = food(kitchen, "Toor dal")
    moong = food(kitchen, "Moong dal")
    used_up(kitchen, toor["id"], 500)
    used_up(kitchen, moong["id"], 300)
    remove(kitchen, toor["id"])
    removed_days_ago(kitchen, toor["id"], 8)
    with db(kitchen) as session:  # it all happened over a week ago
        session.execute(update(Change).values(at=utcnow() - timedelta(days=8)))
        session.commit()
    purge(kitchen)

    changes = kitchen.get(f"{API}/changes").json()["changes"]
    summaries = [c["summary"] for c in changes]
    assert "Removed Toor dal from Ingredients" in summaries
    assert "Used 500 g Toor dal" in summaries
    assert "Added 500 g Toor dal → Cupboard" in summaries
    toor_rows = [c for c in changes if "Toor dal" in c["summary"]]
    assert all(c["lines"] == [] and c["totals"] == [] for c in toor_rows)
    assert all(c["can_undo"] is False for c in toor_rows)
    moong_used = next(c for c in changes if c["summary"] == "Used 300 g Moong dal")
    assert moong_used["totals"][0]["name"] == "Moong dal"
    assert kitchen.get(f"{API}/changes", params={"food_id": moong["id"]}).json()["changes"]


def test_month_totals_still_read(kitchen: TestClient) -> None:
    toor = food(kitchen, "Toor dal")
    moong = food(kitchen, "Moong dal")
    used_up(kitchen, toor["id"], 500)
    used_up(kitchen, moong["id"], 300)
    with db(kitchen) as session:
        session.execute(update(Change).values(at=utcnow() - timedelta(days=400)))
        session.commit()
        thin(session, session.get(Household, 1))
    remove(kitchen, toor["id"])
    removed_days_ago(kitchen, toor["id"], 8)
    purge(kitchen)
    with db(kitchen) as session:
        rows = {
            (row.food_id, row.kind): (row.amount_milli, row.changes)
            for row in session.scalars(select(ChangeMonth))
        }
    assert rows == {
        (moong["id"], "added"): (300_000, 1),
        (moong["id"], "used"): (-300_000, 1),
    }


def test_merged_in_ingredients_go_with_it(kitchen: TestClient) -> None:
    moringa = food(kitchen, "Moringa", counted_as="weight")
    drumsticks = food(kitchen, "Drumsticks", counted_as="weight")
    kitchen.post(f"{API}/foods/{moringa['id']}/merge", json={"into_id": drumsticks["id"]})
    remove(kitchen, drumsticks["id"])
    removed_days_ago(kitchen, drumsticks["id"], 8)
    assert purge(kitchen) == 2
    assert not exists(kitchen, moringa["id"])
    with db(kitchen) as session:
        assert session.scalar(select(func.count()).select_from(FoodMerge)) == 0
    assert kitchen.get(f"{API}/foods/{moringa['id']}").status_code == 404


def test_only_that_households_ingredients(kitchen: TestClient) -> None:
    toor = food(kitchen, "Toor dal")
    remove(kitchen, toor["id"])
    removed_days_ago(kitchen, toor["id"], 8)
    with db(kitchen) as session:
        session.add(Household(id=2, name="Next door", undo_days=30))
        session.flush()
        session.add(
            Login(
                household_id=2,
                username="neighbour",
                name="Neighbour",
                password_hash=hash_password("next door password"),
                role="admin",
            )
        )
        session.add(
            Food(
                id=500,
                household_id=2,
                name="Toor dal",
                counted_as="weight",
                removed_at=utcnow() - timedelta(days=8),
            )
        )
        session.commit()
    # Next door keeps removals for 30 days: purging there touches nothing.
    assert purge(kitchen, household_id=2) == 0
    assert exists(kitchen, 500) and exists(kitchen, toor["id"])
    # Purging here leaves next door's alone.
    assert purge(kitchen, household_id=1) == 1
    assert exists(kitchen, 500)


def test_the_job_runs_for_every_household(kitchen: TestClient) -> None:
    toor = food(kitchen, "Toor dal")
    remove(kitchen, toor["id"])
    removed_days_ago(kitchen, toor["id"], 8)
    jobs.purge_removed_ingredients(kitchen.app.state.sessionmaker)  # type: ignore[attr-defined]
    assert not exists(kitchen, toor["id"])
