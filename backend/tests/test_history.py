"""Recent changes and Undo: just that change, partly when it must, within the window."""

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, update

from mealwright import history
from mealwright.api.v1.context import Kitchen
from mealwright.auth import hash_password
from mealwright.household import add_default_places
from mealwright.models import (
    Change,
    Food,
    FoodConversion,
    FoodName,
    FoodSize,
    FoodStandIn,
    Household,
    Login,
    Place,
    Recipe,
    RecipeLine,
    StockLot,
    utcnow,
)

API = "/api/v1"


def add(kitchen: TestClient, name: str, **extra: Any) -> dict[str, Any]:
    body: dict[str, Any] = kitchen.post(f"{API}/foods", json={"name": name, **extra}).json()
    return body


def undo(client: TestClient, change_id: int, **headers: str) -> Any:
    return client.post(f"{API}/changes/{change_id}/undo", headers=headers)


@pytest.fixture
def remy(kitchen: TestClient) -> Iterator[TestClient]:
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(
            Login(
                household_id=1,
                username="remy",
                name="Remy",
                password_hash=hash_password("remy's own password"),
                role="member",
            )
        )
        db.commit()
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        other.post(f"{API}/session", json={"username": "remy", "password": "remy's own password"})
        yield other


def test_undo_reverses_just_that_change(kitchen: TestClient) -> None:
    food = add(kitchen, "Toor dal")["food"]
    staple = kitchen.patch(f"{API}/foods/{food['id']}", json={"staple": True}).json()["change"]
    kitchen.patch(f"{API}/foods/{food['id']}", json={"name": "Tuvar dal"})

    response = undo(kitchen, staple["id"])
    assert response.status_code == 200
    body = response.json()
    assert body["result"] == "done"
    assert body["message"] == "Undone."
    assert body["change"]["kind"] == "undo"
    assert body["change"]["summary"] == "Undid: Toor dal is now a staple"
    assert body["change"]["can_undo"] is False
    assert body["undone"]["undone"]["who"]["name"] == "Tess"
    # The later rename stays.
    assert body["food"]["name"] == "Tuvar dal"
    assert body["food"]["staple"] is False


def test_partly_undone_when_changed_since(kitchen: TestClient) -> None:
    food = add(kitchen, "Toor dal")["food"]
    url = f"{API}/foods/{food['id']}"
    first = kitchen.patch(url, json={"name": "Tuvar dal"}).json()["change"]
    kitchen.patch(url, json={"name": "Arhar dal"})
    body = undo(kitchen, first["id"]).json()
    assert body["result"] == "nothing"
    assert body["food"]["name"] == "Arhar dal"

    sized = kitchen.post(f"{url}/sizes", json={"name": "packet", "amount": 500}).json()
    size_id = sized["food"]["sizes"][0]["id"]
    kitchen.patch(f"{url}/sizes/{size_id}", json={"amount": 400})
    two = kitchen.post(f"{url}/other-names", json={"name": "toor"}).json()["change"]
    assert undo(kitchen, two["id"]).json()["result"] == "done"
    # The size was added and then changed: undoing the add leaves it alone.
    body = undo(kitchen, sized["change"]["id"]).json()
    assert body["result"] == "nothing"
    assert body["food"]["sizes"][0]["amount"] == 400.0


def test_undo_twice(kitchen: TestClient) -> None:
    change = add(kitchen, "Toor dal")["change"]
    assert undo(kitchen, change["id"]).status_code == 200
    again = undo(kitchen, change["id"])
    assert again.status_code == 409
    assert again.json()["code"] == "already_undone"


def test_an_undo_cannot_be_undone(kitchen: TestClient) -> None:
    change = add(kitchen, "Toor dal")["change"]
    undo_change = undo(kitchen, change["id"]).json()["change"]
    response = undo(kitchen, undo_change["id"])
    assert response.status_code == 409
    assert response.json()["code"] == "cannot_undo"


def test_too_old_to_undo(kitchen: TestClient) -> None:
    change = add(kitchen, "Toor dal")["change"]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(
            update(Change).where(Change.id == change["id"]).values(at=utcnow() - timedelta(days=8))
        )
        db.commit()
    response = undo(kitchen, change["id"])
    assert response.status_code == 410
    assert response.json()["code"] == "too_old"
    listed = kitchen.get(f"{API}/changes").json()["changes"]
    assert listed[0]["can_undo"] is False


def test_anyone_can_undo_anyones_change(kitchen: TestClient, remy: TestClient) -> None:
    change = add(kitchen, "Toor dal")["change"]
    body = undo(remy, change["id"]).json()
    assert body["result"] == "done"
    assert body["change"]["who"]["name"] == "Remy"


def test_undo_retry(kitchen: TestClient) -> None:
    change = add(kitchen, "Toor dal")["change"]
    first = undo(kitchen, change["id"], **{"Idempotency-Key": "undo-1"})
    again = undo(kitchen, change["id"], **{"Idempotency-Key": "undo-1"})
    assert again.status_code == 200
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["change"]["id"] == first.json()["change"]["id"]


def test_recent_changes(kitchen: TestClient, remy: TestClient) -> None:
    toor = add(kitchen, "Toor dal")["food"]
    add(remy, "Onion")
    kitchen.patch(f"{API}/foods/{toor['id']}", json={"staple": True})

    listed = kitchen.get(f"{API}/changes").json()
    assert [c["summary"] for c in listed["changes"]] == [
        "Toor dal is now a staple",
        "Added Onion",
        "Added Toor dal",
    ]
    assert listed["changes"][1]["who"]["name"] == "Remy"

    mine = kitchen.get(f"{API}/changes", params={"mine": True, "limit": 1}).json()
    assert [c["summary"] for c in mine["changes"]] == ["Toor dal is now a staple"]
    assert mine["next"] is not None
    older = kitchen.get(
        f"{API}/changes", params={"mine": True, "limit": 1, "before": mine["next"]}
    ).json()
    assert [c["summary"] for c in older["changes"]] == ["Added Toor dal"]

    by_food = kitchen.get(f"{API}/changes", params={"food_id": toor["id"]}).json()
    assert len(by_food["changes"]) == 2
    assert kitchen.get(f"{API}/changes", params={"area": "pantry"}).json()["changes"] == []


def test_another_households_change_is_404(kitchen: TestClient) -> None:
    assert undo(kitchen, 12345).status_code == 404


def test_undo_remove_when_the_name_is_taken_again(kitchen: TestClient) -> None:
    food = add(kitchen, "Toor dal")["food"]
    removed = kitchen.delete(f"{API}/foods/{food['id']}").json()["change"]
    add(kitchen, "Toor dal")
    body = undo(kitchen, removed["id"]).json()
    assert body["result"] == "nothing"
    assert kitchen.get(f"{API}/foods/{food['id']}").status_code == 404


def test_undo_merge_after_more_changes_is_partly(kitchen: TestClient) -> None:
    moringa = add(kitchen, "Moringa")["food"]
    kitchen.post(f"{API}/foods/{moringa['id']}/sizes", json={"name": "bundle", "amount": 300})
    drumsticks = add(kitchen, "Drumsticks")["food"]
    merged = kitchen.post(
        f"{API}/foods/{moringa['id']}/merge", json={"into_id": drumsticks["id"]}
    ).json()
    size_id = merged["food"]["sizes"][0]["id"]
    kitchen.patch(f"{API}/foods/{drumsticks['id']}/sizes/{size_id}", json={"amount": 250})
    body = undo(kitchen, merged["change"]["id"]).json()
    assert body["result"] == "partly"
    assert body["message"] == "Put back what could be: some of it has changed again since."
    back = kitchen.get(f"{API}/foods/{moringa['id']}").json()
    assert back["id"] == moringa["id"]  # the food itself came back
    assert back["sizes"] == []  # the size was changed since, so it stays where it is


def test_recent_changes_for_ingredients_only(kitchen: TestClient) -> None:
    toor = add(kitchen, "Toor dal")["food"]
    moong = add(kitchen, "Moong dal")["food"]
    staple = kitchen.patch(f"{API}/foods/{toor['id']}", json={"staple": True}).json()["change"]
    kitchen.post(f"{API}/foods/{moong['id']}/merge", json={"into_id": toor["id"]})
    onion = add(kitchen, "Onion")["food"]
    kitchen.delete(f"{API}/foods/{onion['id']}")
    # A stock change and its Undo: not an ingredient change.
    rice = add(kitchen, "Rice")["food"]
    stocked = kitchen.post(
        f"{API}/stock", json={"food_id": rice["id"], "amount": {"amount": 200, "unit": "g"}}
    ).json()["change"]
    undo(kitchen, stocked["id"])

    def summaries(area: str) -> list[str]:
        listed = kitchen.get(f"{API}/changes", params={"area": area}).json()["changes"]
        return [c["summary"] for c in listed]

    assert summaries("ingredients") == [
        "Added Rice",
        "Removed Onion from Ingredients",
        "Added Onion",
        "Merged Moong dal into Toor dal",
        "Toor dal is now a staple",
        "Added Moong dal",
        "Added Toor dal",
    ]
    assert summaries("pantry") == [
        "Undid: Added 200\u00a0g Rice → Cupboard",
        "Added 200\u00a0g Rice → Cupboard",
    ]

    # An Undo of an ingredient change shows up in the ingredient list, and nowhere else.
    assert undo(kitchen, staple["id"]).json()["result"] == "done"
    assert summaries("ingredients")[0] == "Undid: Toor dal is now a staple"
    assert "Undid: Toor dal is now a staple" not in summaries("pantry")
    row = kitchen.get(f"{API}/changes", params={"area": "ingredients"}).json()["changes"][0]
    assert row["kind"] == "undo" and row["can_undo"] is False


def test_undo_through_the_ingredient_list(kitchen: TestClient) -> None:
    toor = add(kitchen, "Toor dal")["food"]
    kitchen.patch(f"{API}/foods/{toor['id']}", json={"staple": True})
    row = kitchen.get(f"{API}/changes", params={"area": "ingredients"}).json()["changes"][0]
    assert row["can_undo"] is True
    assert undo(kitchen, row["id"]).json()["result"] == "done"
    assert kitchen.get(f"{API}/foods/{toor['id']}").json()["staple"] is False
    again = kitchen.get(f"{API}/changes", params={"area": "ingredients"}).json()["changes"]
    assert [c["kind"] for c in again][:2] == ["undo", "food_edited"]
    assert again[1]["undone"] is not None


def test_ingredient_list_is_in_the_openapi_schema(kitchen: TestClient) -> None:
    assert kitchen.get(f"{API}/changes", params={"area": "recipes"}).status_code == 422
    schema = kitchen.get(f"{API}/openapi.json").json()
    parameters = schema["paths"]["/api/v1/changes"]["get"]["parameters"]
    area = next(p for p in parameters if p["name"] == "area")
    values = next(a for a in area["schema"]["anyOf"] if "enum" in a)["enum"]
    assert values == ["pantry", "ingredients"]


# --- A hand-made Undo record can't reach into another household ---------------------------


@pytest.mark.parametrize("restore", ["recipe_lines", "recipe_homes"])
def test_an_undo_record_pointing_at_another_households_recipe_changes_nothing(
    kitchen: TestClient, restore: str
) -> None:
    mine = add(kitchen, "Toor dal")["food"]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(Household(id=2, name="Next door"))
        db.flush()
        recipe = Recipe(household_id=2, name="Their dal", version=1)
        db.add(recipe)
        db.flush()
        line = RecipeLine(household_id=2, recipe_id=recipe.id, position=0, words="dal")
        db.add(line)
        db.commit()
        recipe_id, line_id = recipe.id, line.id

        asking = Kitchen(
            db=db,
            login=db.scalars(select(Login)).one(),
            household=db.get(Household, 1),  # type: ignore[arg-type]
            idempotency_key=None,
            request="POST /api/v1/changes/1/undo",
        )
        key = str(line_id if restore == "recipe_lines" else recipe_id)
        value = {"food_id": mine["id"], "size_id": None}
        # Like a record that doesn't fit: not put back, and nothing changed.
        assert history._RESTORE[restore](asking, key, value) is False
        assert history._RESTORE[restore](asking, key, None) is True
        db.commit()

        theirs = db.get(Recipe, recipe_id)
        assert theirs is not None
        assert theirs.homemade_food_id is None and theirs.version == 1
        assert db.get(RecipeLine, line_id).food_id is None  # type: ignore[union-attr]


@pytest.mark.parametrize("restore", ["field", "names", "sizes", "stand_ins", "conversions", "lots"])
def test_an_undo_record_pointing_at_another_households_ingredient_changes_nothing(
    kitchen: TestClient, restore: str
) -> None:
    """Every restore step checks the household itself (found by the 0.4.0 release review):
    a record that names a row of another household, or sends one of mine to it, puts nothing
    back and changes nothing."""
    mine = add(kitchen, "Toor dal")["food"]["id"]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(Household(id=2, name="Next door"))
        db.flush()
        add_default_places(db, 2)
        theirs = Food(household_id=2, name="Ghee", counted_as="weight")
        other = Food(household_id=2, name="Butter", counted_as="weight")
        db.add_all([theirs, other])
        db.flush()
        name = FoodName(household_id=2, food_id=theirs.id, name="clarified butter")
        size = FoodSize(
            household_id=2, food_id=theirs.id, name="jar", plural="jars", amount_milli=500_000
        )
        link = FoodStandIn(household_id=2, food_id=theirs.id, stand_in_id=other.id)
        conversion = FoodConversion(
            household_id=2,
            food_id=theirs.id,
            kind="cup",
            value_milli=240_000,
            answered_by_name="Them",
        )
        place = db.scalars(select(Place).where(Place.household_id == 2)).first()
        assert place is not None
        lot = StockLot(household_id=2, food_id=theirs.id, place_id=place.id, amount_milli=1000)
        db.add_all([name, size, link, conversion, lot])
        db.commit()
        asking = Kitchen(
            db=db,
            login=db.scalars(select(Login)).one(),
            household=db.get(Household, 1),  # type: ignore[arg-type]
            idempotency_key=None,
            request="POST /api/v1/changes/1/undo",
        )
        step = history._RESTORE
        if restore == "field":
            for field, value in (("exists", None), ("removed", True), ("name", "Hacked")):
                assert history._restore_field(asking, f"{theirs.id}:{field}", value) is False
            their_food = db.get(Food, theirs.id)
            assert their_food is not None
            assert their_food.name == "Ghee" and their_food.removed_at is None
        elif restore == "names":
            assert step["names"](asking, str(name.id), None) is False  # delete theirs
            assert step["names"](asking, str(name.id), {"food_id": mine, "name": "x"}) is False
            assert (
                step["names"](asking, "9999", {"food_id": theirs.id, "name": "mine now"}) is False
            )
            assert db.get(FoodName, name.id) is not None
            assert db.scalars(select(FoodName).where(FoodName.food_id == mine)).first() is None
        elif restore == "sizes":
            assert step["sizes"](asking, str(size.id), None) is False
            assert step["sizes"](asking, str(size.id), {"food_id": mine, "name": "hack"}) is False
            fields = {
                "food_id": theirs.id,
                "name": "jar",
                "plural": "jars",
                "amount_milli": 1,
                "usual": False,
                "added_when_shopping": False,
                "position": 0,
            }
            assert step["sizes"](asking, "9998", fields) is False  # one of mine from theirs
            assert db.get(FoodSize, size.id) is not None and db.get(FoodSize, 9998) is None
        elif restore == "stand_ins":
            assert step["stand_ins"](asking, f"{theirs.id}:{other.id}", False) is False
            assert step["stand_ins"](asking, f"{mine}:{theirs.id}", True) is False
            assert db.get(FoodStandIn, (theirs.id, other.id)) is not None
            assert db.get(FoodStandIn, (mine, theirs.id)) is None
        elif restore == "conversions":
            assert step["conversions"](asking, f"{theirs.id}:cup", None) is False
            changed = {"value_milli": 1, "answered_by_name": "Me"}
            assert step["conversions"](asking, f"{theirs.id}:cup", changed) is False
            assert step["conversions"](asking, f"{theirs.id}:tbsp", changed) is False
            row = db.scalars(select(FoodConversion).where(FoodConversion.food_id == theirs.id))
            assert [(r.kind, r.value_milli) for r in row] == [("cup", 240_000)]
        else:
            put = {"food_id": mine, "size_id": None}
            assert step["lots"](asking, str(lot.id), put) is False  # theirs, sent to mine
            assert step["lots"](asking, str(lot.id), None) is False
            mine_lot = StockLot(household_id=1, food_id=mine, place_id=1, amount_milli=1000)
            db.add(mine_lot)
            db.flush()
            there = {"food_id": theirs.id, "size_id": size.id}
            assert step["lots"](asking, str(mine_lot.id), there) is False  # mine, sent to theirs
            assert mine_lot.food_id == mine
            assert db.get(StockLot, lot.id).food_id == theirs.id  # type: ignore[union-attr]
        db.rollback()
