"""Places, shops, units, remembered answers and the household's settings."""

import threading
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
    assert kitchen.get(f"{API}/places").json()["places"] == [
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
    # A name it already has is refused and carries that shop, as "+ Place" is (BE1).
    again = kitchen.post(f"{API}/shops", json={"name": "tesco"})
    assert again.status_code == 409
    assert again.json() == {
        "detail": "There’s already a shop called Tesco.",
        "code": "name_taken",
        "shop": tesco,
    }
    kitchen.post(f"{API}/shops", json={"name": "Lidl"})
    assert [s["name"] for s in kitchen.get(f"{API}/shops").json()["shops"]] == ["Tesco", "Lidl"]


def test_add_a_place(kitchen: TestClient) -> None:
    response = kitchen.post(f"{API}/places", json={"name": "  Garage   fridge ", "kind": "fridge"})
    assert response.status_code == 201
    made = response.json()
    assert made == {"id": made["id"], "name": "Garage fridge", "kind": "fridge"}
    listed = kitchen.get(f"{API}/places").json()["places"]
    assert [p["name"] for p in listed] == [
        "Fridge",
        "Freezer",
        "Cupboard",
        "Spice rack",
        "Garage fridge",
    ]
    assert listed[-1] == made
    # The next one goes after it.
    kitchen.post(f"{API}/places", json={"name": "Chest freezer", "kind": "freezer"})
    assert kitchen.get(f"{API}/places").json()["places"][-1]["name"] == "Chest freezer"


def test_a_place_name_the_household_has_is_a_409_with_that_place(kitchen: TestClient) -> None:
    response = kitchen.post(f"{API}/places", json={"name": "fridge", "kind": "cupboard"})
    assert response.status_code == 409
    body = response.json()
    assert body["code"] == "name_taken"
    assert body["place"] == {"id": 1, "name": "Fridge", "kind": "fridge"}
    assert len(kitchen.get(f"{API}/places").json()["places"]) == 4


@pytest.mark.parametrize(
    "body",
    [
        {"name": "", "kind": "cupboard"},
        {"name": "   ", "kind": "cupboard"},
        {"name": "x" * 41, "kind": "cupboard"},
        {"name": "Pantry", "kind": "garage"},
        {"name": "Pantry"},
        {"kind": "cupboard"},
    ],
)
def test_a_bad_place_is_refused(kitchen: TestClient, body: dict[str, str]) -> None:
    assert kitchen.post(f"{API}/places", json=body).status_code == 422
    assert len(kitchen.get(f"{API}/places").json()["places"]) == 4


def test_a_forty_character_place_name_is_fine(kitchen: TestClient) -> None:
    made = kitchen.post(f"{API}/places", json={"name": "y" * 40, "kind": "cupboard"})
    assert made.status_code == 201


def test_a_member_can_add_a_place(member: TestClient) -> None:
    made = member.post(f"{API}/places", json={"name": "Larder", "kind": "cupboard"})
    assert made.status_code == 201


def test_places_are_the_households_own(kitchen: TestClient, neighbour: TestClient) -> None:
    made = kitchen.post(f"{API}/places", json={"name": "Garage", "kind": "cupboard"})
    assert made.status_code == 201
    # Another household's "Garage" is never matched: the same name is new for them.
    theirs = neighbour.post(f"{API}/places", json={"name": "garage", "kind": "freezer"})
    assert theirs.status_code == 201
    assert theirs.json()["id"] != made.json()["id"]
    assert theirs.json()["kind"] == "freezer"
    ours = [p["name"] for p in kitchen.get(f"{API}/places").json()["places"]]
    their_names = [p["name"] for p in neighbour.get(f"{API}/places").json()["places"]]
    assert "Garage" in ours and "garage" not in ours
    assert "garage" in their_names and "Garage" not in their_names
    # A 409 only ever names the caller's own place.
    clash = neighbour.post(f"{API}/places", json={"name": "Garage", "kind": "cupboard"})
    assert clash.status_code == 409
    assert clash.json()["place"]["id"] == theirs.json()["id"]


def test_a_household_has_at_most_fifty_places(kitchen: TestClient, neighbour: TestClient) -> None:
    # 4 places to start with; the 50th is the last that is let in (proposed, for cabledrawer).
    for number in range(46):
        made = kitchen.post(f"{API}/places", json={"name": f"Shelf {number}", "kind": "cupboard"})
        assert made.status_code == 201
    assert len(kitchen.get(f"{API}/places").json()["places"]) == 50
    refused = kitchen.post(f"{API}/places", json={"name": "One too many", "kind": "cupboard"})
    assert refused.status_code == 409
    assert refused.json()["code"] == "too_many_places"
    assert refused.json()["detail"] == (
        "You have 50 places, the most Mealwright keeps. Rename or remove one in Settings."
    )
    assert len(kitchen.get(f"{API}/places").json()["places"]) == 50
    # A name the household already has still gives that place, so the screen can pick it.
    again = kitchen.post(f"{API}/places", json={"name": "shelf 3", "kind": "cupboard"})
    assert again.status_code == 409
    assert again.json()["code"] == "name_taken"
    # Another household is not held back by this one's places.
    theirs = neighbour.post(f"{API}/places", json={"name": "One too many", "kind": "cupboard"})
    assert theirs.status_code == 201


def _at_once(kitchen: TestClient, path: str, bodies: list[dict[str, str]]) -> list[int]:
    """Two phones of the same login send their POSTs at the same moment."""
    start = threading.Barrier(len(bodies))
    codes: list[int] = []

    def send(body: dict[str, str]) -> None:
        other = TestClient(kitchen.app, base_url="https://testserver")
        other.cookies.update(kitchen.cookies)
        start.wait()
        codes.append(other.post(f"{API}{path}", json=body).status_code)

    threads = [threading.Thread(target=send, args=(body,)) for body in bodies]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return sorted(codes)


def test_two_phones_adding_the_fiftieth_place_at_once_keep_the_cap(kitchen: TestClient) -> None:
    for number in range(45):
        kitchen.post(f"{API}/places", json={"name": f"Shelf {number}", "kind": "cupboard"})
    for turn in range(5):
        assert len(kitchen.get(f"{API}/places").json()["places"]) == 49
        codes = _at_once(
            kitchen,
            "/places",
            [
                {"name": f"Garage {turn}", "kind": "fridge"},
                {"name": f"Shed {turn}", "kind": "freezer"},
            ],
        )
        assert codes == [201, 409]
        assert len(kitchen.get(f"{API}/places").json()["places"]) == 50
        with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
            last = db.scalars(select(Place).order_by(Place.position.desc())).first()
            assert last is not None
            db.delete(last)
            db.commit()


@pytest.mark.parametrize(("path", "body"), [("/places", {"kind": "cupboard"}), ("/shops", {})])
def test_two_phones_adding_the_same_name_at_once_make_one(
    kitchen: TestClient, path: str, body: dict[str, str]
) -> None:
    for turn in range(5):
        name = f"Corner {turn}"
        codes = _at_once(kitchen, path, [{"name": name, **body}, {"name": name.upper(), **body}])
        assert codes in ([200, 201], [201, 409])
        names = [row["name"] for row in kitchen.get(f"{API}{path}").json()[path.strip("/")]]
        assert len([n for n in names if n.lower() == name.lower()]) == 1


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
    url = f"{API}/household/fill-from-browser"
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

    kitchen.post(f"{API}/household/fill-from-browser", json={"time_zone": "Pacific/Kiritimati"})
    expected = datetime.now(UTC).astimezone(ZoneInfo("Pacific/Kiritimati")).date().isoformat()
    assert kitchen.get(f"{API}/household").json()["today"] == expected


@pytest.mark.parametrize(
    "body",
    [
        {"time_zone": "Mars/Olympus"},
        {"time_zone": "localtime"},
        {"time_zone": "Factory"},
        {"time_zone": "posixrules"},
        {"time_zone": "GB"},
        {"cup_ml": 200},
    ],
)
def test_browser_values_are_checked(kitchen: TestClient, body: dict[str, object]) -> None:
    assert kitchen.post(f"{API}/household/fill-from-browser", json=body).status_code == 422
    assert kitchen.get(f"{API}/household").json()["time_zone"] is None


def test_only_admins_set_the_time_zone(member: TestClient) -> None:
    response = member.post(
        f"{API}/household/fill-from-browser", json={"time_zone": "Europe/London"}
    )
    assert response.status_code == 403
    assert response.json()["code"] == "admins_only"
    assert member.get(f"{API}/household").json()["time_zone"] is None


def test_cup_size_changes_the_cup(kitchen: TestClient) -> None:
    food = kitchen.post(f"{API}/foods", json={"name": "Toor dal"}).json()["food"]
    kitchen.patch(f"{API}/foods/{food['id']}", json={"cup_weight": 200})
    kitchen.post(f"{API}/household/fill-from-browser", json={"cup_ml": 240})
    shown = kitchen.get(f"{API}/foods/{food['id']}").json()["cup_weight"]
    assert shown == {"grams": 192.0, "from": "you", "cup_ml": 240}  # 0.8 g/ml times 240 ml
    units = {u["unit"]: u["amount"] for u in kitchen.get(f"{API}/units").json()["units"]}
    assert units["cup"] == 240.0 and units["tbsp"] == 15.0 and units["tsp"] == 5.0


def test_remembered_answers(kitchen: TestClient) -> None:
    food = kitchen.post(f"{API}/foods", json={"name": "Toor dal"}).json()["food"]
    kitchen.patch(f"{API}/foods/{food['id']}", json={"cup_weight": 200})
    remembered = kitchen.get(f"{API}/conversions").json()["conversions"]
    assert [(r["food"]["name"], r["display"], r["answered_by"]) for r in remembered] == [
        ("Toor dal", "1\u00a0cup = 200\u00a0g", "Tess")
    ]
    forgotten = kitchen.delete(f"{API}/conversions/{remembered[0]['id']}").json()
    assert forgotten["change"]["can_undo"] is True
    assert kitchen.get(f"{API}/conversions").json()["conversions"] == []
    kitchen.post(f"{API}/changes/{forgotten['change']['id']}/undo")
    assert len(kitchen.get(f"{API}/conversions").json()["conversions"]) == 1


def test_another_households_ids_are_404(kitchen: TestClient) -> None:
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalar(select(Place).where(Place.id == 1)) is not None
    assert kitchen.patch(f"{API}/foods/1", json={"place_id": 999}).status_code == 404


@pytest.mark.parametrize("zone", ["UTC", "Europe/London", "America/Argentina/Buenos_Aires"])
def test_real_time_zones_are_accepted(kitchen: TestClient, zone: str) -> None:
    response = kitchen.post(f"{API}/household/fill-from-browser", json={"time_zone": zone})
    assert response.json()["time_zone"] == zone
