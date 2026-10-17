"""Places, shops, units, remembered answers and the household's settings."""

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from mealwright import migrate
from mealwright.auth import hash_password
from mealwright.db import make_engine
from mealwright.models import Login, Place

API = "/api/v1"


@pytest.fixture
def member(kitchen: TestClient) -> Iterator[TestClient]:
    """A second login in the same household, with the Member role."""
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(
            Login(
                household_id=1,
                username="wren",
                name="Wren",
                password_hash=hash_password("wren's own password"),
                role="member",
            )
        )
        db.commit()
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        response = other.post(
            f"{API}/session", json={"username": "wren", "password": "wren's own password"}
        )
        assert response.status_code == 200
        yield other


def test_four_default_places(kitchen: TestClient) -> None:
    assert kitchen.get(f"{API}/places").json() == [
        {"id": 1, "name": "Fridge", "kind": "fridge"},
        {"id": 2, "name": "Freezer", "kind": "freezer"},
        {"id": 3, "name": "Cupboard", "kind": "cupboard"},
        {"id": 4, "name": "Spice rack", "kind": "cupboard"},
    ]


def test_migration_adds_places_to_an_existing_household(tmp_path: object) -> None:
    from pathlib import Path

    from sqlalchemy import text

    engine = make_engine(f"sqlite:///{Path(str(tmp_path)) / 'old.db'}")
    migrate.upgrade(engine, "d60b64f1e4ff")  # 0.1.0
    with engine.begin() as connection:
        connection.execute(
            text("INSERT INTO household (id, name, created_at) VALUES (1, 'Home', '2026-10-01')")
        )
    migrate.upgrade(engine)
    with engine.connect() as connection:
        names = connection.execute(select(Place.name).order_by(Place.position)).scalars().all()
    assert names == ["Fridge", "Freezer", "Cupboard", "Spice rack"]


def test_shop_by_name(kitchen: TestClient) -> None:
    response = kitchen.post(f"{API}/shops", json={"name": " Tesco "})
    assert response.status_code == 201
    tesco = response.json()
    assert tesco["name"] == "Tesco"
    again = kitchen.post(f"{API}/shops", json={"name": "tesco"})
    assert again.status_code == 200
    assert again.json() == tesco
    kitchen.post(f"{API}/shops", json={"name": "Lidl"})
    assert [s["name"] for s in kitchen.get(f"{API}/shops").json()] == ["Tesco", "Lidl"]


def test_household_settings(kitchen: TestClient) -> None:
    household = kitchen.get(f"{API}/household").json()
    assert household["time_zone"] is None  # until the admin's browser sends it: UTC
    assert household["cup_ml"] is None
    assert household["cup_ml_used"] == 250
    assert (household["undo_days"], household["history_months"], household["use_soon_days"]) == (
        7,
        12,
        2,
    )


def test_time_zone_is_set_once_from_the_browser(kitchen: TestClient) -> None:
    url = f"{API}/household/from-browser"
    first = kitchen.post(url, json={"time_zone": "Europe/London", "cup_ml": 240}).json()
    assert first["time_zone"] == "Europe/London"
    assert first["cup_ml_used"] == 240
    # Opening the app from abroad changes nothing: the stored values come back.
    again = kitchen.post(url, json={"time_zone": "Asia/Kolkata", "cup_ml": 250})
    assert again.status_code == 200
    assert again.json()["time_zone"] == "Europe/London"
    assert again.json()["cup_ml"] == 240
    assert kitchen.get(f"{API}/household").json()["time_zone"] == "Europe/London"


def test_household_today_follows_its_time_zone(kitchen: TestClient) -> None:
    from datetime import UTC, datetime
    from zoneinfo import ZoneInfo

    kitchen.post(f"{API}/household/from-browser", json={"time_zone": "Pacific/Kiritimati"})
    expected = datetime.now(UTC).astimezone(ZoneInfo("Pacific/Kiritimati")).date().isoformat()
    assert kitchen.get(f"{API}/household").json()["today"] == expected


@pytest.mark.parametrize("body", [{"time_zone": "Mars/Olympus"}, {"cup_ml": 200}])
def test_browser_values_are_checked(kitchen: TestClient, body: dict[str, object]) -> None:
    assert kitchen.post(f"{API}/household/from-browser", json=body).status_code == 422
    assert kitchen.get(f"{API}/household").json()["time_zone"] is None


def test_only_admins_set_the_time_zone(member: TestClient) -> None:
    response = member.post(f"{API}/household/from-browser", json={"time_zone": "Europe/London"})
    assert response.status_code == 403
    assert response.json()["code"] == "admins_only"
    assert member.get(f"{API}/household").json()["time_zone"] is None


def test_cup_size_changes_the_cup(kitchen: TestClient) -> None:
    food = kitchen.post(f"{API}/foods", json={"name": "Toor dal"}).json()["food"]
    kitchen.patch(f"{API}/foods/{food['id']}", json={"cup_weight": 200})
    kitchen.post(f"{API}/household/from-browser", json={"cup_ml": 240})
    shown = kitchen.get(f"{API}/foods/{food['id']}").json()["cup_weight"]
    assert shown == {"grams": 192.0, "from": "you", "cup_ml": 240}  # 0.8 g/ml times 240 ml
    units = {u["unit"]: u["amount"] for u in kitchen.get(f"{API}/units").json()}
    assert units["cup"] == 240.0 and units["tbsp"] == 15.0 and units["tsp"] == 5.0


def test_remembered_answers(kitchen: TestClient) -> None:
    food = kitchen.post(f"{API}/foods", json={"name": "Toor dal"}).json()["food"]
    kitchen.patch(f"{API}/foods/{food['id']}", json={"cup_weight": 200})
    remembered = kitchen.get(f"{API}/conversions").json()
    assert [(r["food"]["name"], r["display"], r["answered_by"]) for r in remembered] == [
        ("Toor dal", "1 cup = 200 g", "Tess")
    ]
    forgotten = kitchen.delete(f"{API}/conversions/{remembered[0]['id']}").json()
    assert forgotten["change"]["can_undo"] is True
    assert kitchen.get(f"{API}/conversions").json() == []
    kitchen.post(f"{API}/changes/{forgotten['change']['id']}/undo")
    assert len(kitchen.get(f"{API}/conversions").json()) == 1


def test_another_households_ids_are_404(kitchen: TestClient) -> None:
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalar(select(Place).where(Place.id == 1)) is not None
    assert kitchen.patch(f"{API}/foods/1", json={"place_id": 999}).status_code == 404
