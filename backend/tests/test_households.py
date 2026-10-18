"""One household can never see or change another's ingredients, places, shops, pantry or
changes (spec section 6: every record belongs to a household).

Two real households, each with its own admin and session. Household 1 has an ingredient
(with other names, a size and a stand-in), a shop, stock and changes. From household 2,
every /api/v1 endpoint that takes an id is tried, reading and writing, with household 1's
ids, in the path and in the body. The endpoints are listed from the app itself, so a new
endpoint with an id and no case here fails the test. Household 1's data must be exactly
the same afterwards.
"""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from mealwright.auth import hash_password
from mealwright.db import Base
from mealwright.household import add_default_places
from mealwright.models import Household, Login

API = "/api/v1"
NEIGHBOUR = {"username": "neighbour", "password": "next door's own password"}


@pytest.fixture
def neighbour(kitchen: TestClient) -> Iterator[TestClient]:
    """Household 2, with its own admin, signed in on its own client."""
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(Household(id=2, name="Next door"))
        db.flush()
        add_default_places(db, 2)
        db.add(
            Login(
                household_id=2,
                username=NEIGHBOUR["username"],
                name="Neighbour",
                password_hash=hash_password(NEIGHBOUR["password"]),
                role="admin",
            )
        )
        db.commit()
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        assert other.post(f"{API}/session", json=NEIGHBOUR).status_code == 200
        assert other.get(f"{API}/me").json()["username"] == "neighbour"
        yield other


def ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


@pytest.fixture
def mine(kitchen: TestClient) -> dict[str, Any]:
    """Household 1's data, and the ids to attack it with."""
    toor = ok(kitchen.post(f"{API}/foods", json={"name": "Toor dal"}), 201)["food"]
    moong = ok(kitchen.post(f"{API}/foods", json={"name": "Moong dal"}), 201)["food"]
    named = ok(
        kitchen.post(f"{API}/foods/{toor['id']}/other-names", json={"name": "arhar dal"}),
        201,
    )
    sized = ok(
        kitchen.post(f"{API}/foods/{toor['id']}/sizes", json={"name": "packet", "amount": 500}),
        201,
    )
    ok(kitchen.post(f"{API}/foods/{toor['id']}/stand-ins", json={"food_id": moong["id"]}), 201)
    ok(kitchen.patch(f"{API}/foods/{toor['id']}", json={"cup_weight": 200}))
    shop = ok(kitchen.post(f"{API}/shops", json={"name": "Spice Bazaar"}), 201)
    ok(kitchen.patch(f"{API}/foods/{toor['id']}", json={"shop_id": shop["id"]}))
    places = {p["name"]: p["id"] for p in ok(kitchen.get(f"{API}/places"))}
    added = ok(
        kitchen.post(
            f"{API}/stock",
            json={
                "food_id": toor["id"],
                "amount": {"amount": 2, "unit": "packet"},
                "use_by": "2030-01-01",
            },
        ),
        201,
    )
    conversions = ok(kitchen.get(f"{API}/conversions"))
    lists = ok(kitchen.get(f"{API}/shopping/lists"))["lists"]
    extra = ok(kitchen.post(f"{API}/shopping/lists", json={"name": "Party"}), 201)
    item = ok(
        kitchen.post(
            f"{API}/shopping/lists/{lists[0]['id']}/items",
            json={"food_id": toor["id"], "amount": {"amount": 1, "unit": "packet"}},
        ),
        201,
    )
    return {
        "list_id": lists[0]["id"],
        "extra_list_id": extra["shopping_list"]["id"],
        "item_id": item["item"]["id"],
        "food_id": toor["id"],
        "other_food_id": moong["id"],
        "name_id": named["food"]["other_names"][0]["id"],
        "size_id": sized["food"]["sizes"][0]["id"],
        "stand_in_id": moong["id"],
        "lot_id": added["groups"][0]["lots"][0]["id"],
        "change_id": added["change"]["id"],
        "conversion_id": conversions[0]["id"],
        "shop_id": shop["id"],
        "place_id": places["Fridge"],
    }


def snapshot(kitchen: TestClient) -> dict[str, list[tuple[Any, ...]]]:
    """Every row of household 1, in every table, exactly as stored."""
    rows: dict[str, list[tuple[Any, ...]]] = {}
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        for table in Base.metadata.sorted_tables:
            column = "id" if table.name == "household" else "household_id"
            found = db.execute(
                text(f'SELECT * FROM "{table.name}" WHERE {column} = 1 ORDER BY 1, 2')  # noqa: S608
            ).all()
            rows[table.name] = [tuple(row) for row in found]
    return rows


# Every endpoint with an id in its path: a request that would work on household 1's own
# data (so a 404 means "not yours", not "bad request").
PATH_CASES: dict[tuple[str, str], dict[str, Any] | None] = {
    ("GET", "/api/v1/foods/{food_id}"): None,
    ("PATCH", "/api/v1/foods/{food_id}"): {"staple": True},
    ("DELETE", "/api/v1/foods/{food_id}"): None,
    ("GET", "/api/v1/foods/{food_id}/convert"): None,
    ("POST", "/api/v1/foods/{food_id}/left"): {"amount": {"amount": 0, "unit": "g"}},
    ("POST", "/api/v1/foods/{food_id}/used"): {"amount": {"amount": 10, "unit": "g"}},
    ("POST", "/api/v1/foods/{food_id}/merge"): {"into_id": 0},
    ("POST", "/api/v1/foods/{food_id}/not-the-same"): {"food_id": 0},
    ("POST", "/api/v1/foods/{food_id}/other-names"): {"name": "tuvar"},
    ("DELETE", "/api/v1/foods/{food_id}/other-names/{name_id}"): None,
    ("POST", "/api/v1/foods/{food_id}/sizes"): {"name": "bag", "amount": 1000},
    ("PATCH", "/api/v1/foods/{food_id}/sizes/{size_id}"): {"usual": True},
    ("DELETE", "/api/v1/foods/{food_id}/sizes/{size_id}"): None,
    ("POST", "/api/v1/foods/{food_id}/split"): {"other_name_id": 0},
    ("POST", "/api/v1/foods/{food_id}/stand-ins"): {"food_id": 0},
    ("DELETE", "/api/v1/foods/{food_id}/stand-ins/{stand_in_id}"): None,
    ("PATCH", "/api/v1/stock/{lot_id}"): {"use_by": "2031-01-01"},
    ("POST", "/api/v1/stock/{lot_id}/used"): {},
    ("POST", "/api/v1/stock/{lot_id}/binned"): {},
    ("POST", "/api/v1/stock/{lot_id}/left"): {"fraction": 0.5},
    ("POST", "/api/v1/stock/{lot_id}/move"): {"place_id": 0},
    ("POST", "/api/v1/stock/{lot_id}/to-freezer"): {},
    ("POST", "/api/v1/changes/{change_id}/undo"): None,
    ("DELETE", "/api/v1/conversions/{conversion_id}"): None,
    ("GET", "/api/v1/shopping/lists/{list_id}"): None,
    ("PATCH", "/api/v1/shopping/lists/{list_id}"): {"name": "Mine now"},
    ("DELETE", "/api/v1/shopping/lists/{extra_list_id}"): None,
    ("POST", "/api/v1/shopping/lists/{list_id}/items"): {"food_id": 0},
    ("POST", "/api/v1/shopping/lists/{list_id}/clear-ticked"): {},
    ("PATCH", "/api/v1/shopping/items/{item_id}"): {"amount": {"amount": 3, "unit": "g"}},
    ("DELETE", "/api/v1/shopping/items/{item_id}"): None,
}


def endpoints_with_ids(client: TestClient) -> set[tuple[str, str]]:
    paths = client.app.openapi()["paths"]  # type: ignore[attr-defined]
    found = {
        (method.upper(), path)
        for path, methods in paths.items()
        if "{" in path
        for method in methods
    }
    # DELETE of a list is tried on an extra list (the main list can't be removed).
    return found


def test_every_endpoint_with_an_id_has_a_case(kitchen: TestClient) -> None:
    wanted = {(method, path.replace("{extra_list_id}", "{list_id}")) for method, path in PATH_CASES}
    assert endpoints_with_ids(kitchen) == wanted


def fill(path: str, ids: dict[str, Any]) -> str:
    return path.format(**ids)


def request(client: TestClient, method: str, url: str, body: Any) -> Any:
    if method == "GET":
        params = {"amount": 1, "unit": "cup"} if url.endswith("/convert") else None
        return client.get(url, params=params)
    return client.request(method, url, json=body)


def test_household_ids_in_the_path_are_404(
    kitchen: TestClient, neighbour: TestClient, mine: dict[str, Any]
) -> None:
    before = snapshot(kitchen)
    # Household 2 has its own ingredient, so body ids can point at something real there.
    theirs = ok(neighbour.post(f"{API}/foods", json={"name": "Ghee"}), 201)["food"]
    for (method, path), body in sorted(PATH_CASES.items()):
        if isinstance(body, dict):
            body = {k: (theirs["id"] if v == 0 else v) for k, v in body.items()}
        response = request(neighbour, method, fill(path, mine), body)
        assert response.status_code == 404, (method, path, response.status_code, response.text)
        assert response.json().get("code") == "not_found", (method, path, response.text)
    assert snapshot(kitchen) == before


def test_household_ids_in_the_body_are_404(
    kitchen: TestClient, neighbour: TestClient, mine: dict[str, Any]
) -> None:
    before = snapshot(kitchen)
    ghee = ok(neighbour.post(f"{API}/foods", json={"name": "Ghee"}), 201)["food"]
    ok(neighbour.post(f"{API}/foods/{ghee['id']}/other-names", json={"name": "nei"}), 201)
    lot = ok(
        neighbour.post(
            f"{API}/stock", json={"food_id": ghee["id"], "amount": {"amount": 100, "unit": "g"}}
        ),
        201,
    )["groups"][0]["lots"][0]
    own = f"{API}/foods/{ghee['id']}"
    attempts = [
        (
            "POST",
            f"{API}/stock",
            {"food_id": mine["food_id"], "amount": {"amount": 1, "unit": "g"}},
        ),
        (
            "POST",
            f"{API}/stock",
            {
                "food_id": ghee["id"],
                "amount": {"amount": 1, "unit": "g"},
                "place_id": mine["place_id"],
            },
        ),
        (
            "POST",
            f"{API}/stock",
            {"food_id": ghee["id"], "amount": {"amount": 1, "size_id": mine["size_id"]}},
        ),
        # An "ask once" size answer about household 1's ingredient (kind=size).
        (
            "POST",
            f"{API}/stock",
            {
                "food_id": ghee["id"],
                "amount": {
                    "amount": 1,
                    "unit": "loaf",
                    "answers": [
                        {"kind": "size", "food_id": mine["food_id"], "name": "loaf", "amount": 20}
                    ],
                },
            },
        ),
        ("POST", f"{API}/foods", {"name": "Butter", "place_id": mine["place_id"]}),
        ("POST", f"{API}/foods", {"name": "Butter", "aisle": "dairy", "shop_id": mine["shop_id"]}),
        ("POST", f"{API}/shopping/lists/{{own_list}}/items", {"food_id": mine["food_id"]}),
        (
            "POST",
            f"{API}/shopping/lists/{{own_list}}/items",
            {"food_id": ghee["id"], "shop_id": mine["shop_id"]},
        ),
        (
            "POST",
            f"{API}/shopping/lists/{{own_list}}/items",
            {"food_id": ghee["id"], "amount": {"amount": 1, "size_id": mine["size_id"]}},
        ),
        ("POST", f"{API}/shopping/lists/{mine['list_id']}/items", {"food_id": ghee["id"]}),
        ("POST", f"{API}/shopping/lists", {"id": mine["extra_list_id"], "name": "Copy"}),
        ("POST", f"{API}/foods", {"name": "Butter", "shop_id": mine["shop_id"]}),
        ("PATCH", own, {"place_id": mine["place_id"]}),
        ("PATCH", own, {"shop_id": mine["shop_id"]}),
        ("POST", f"{own}/stand-ins", {"food_id": mine["food_id"]}),
        ("POST", f"{own}/not-the-same", {"food_id": mine["food_id"]}),
        ("POST", f"{own}/merge", {"into_id": mine["food_id"]}),
        ("POST", f"{API}/foods/{mine['food_id']}/merge", {"into_id": ghee["id"]}),
        ("POST", f"{own}/split", {"other_name_id": mine["name_id"]}),
        ("DELETE", f"{own}/other-names/{mine['name_id']}", None),
        ("PATCH", f"{own}/sizes/{mine['size_id']}", {"usual": True}),
        ("DELETE", f"{own}/sizes/{mine['size_id']}", None),
        ("DELETE", f"{own}/stand-ins/{mine['stand_in_id']}", None),
        ("POST", f"{API}/stock/{lot['id']}/move", {"place_id": mine["place_id"]}),
        (
            "POST",
            f"{own}/used",
            {"amount": {"amount": 1, "unit": "g"}, "place_id": mine["place_id"]},
        ),
        (
            "POST",
            f"{own}/left",
            {"amount": {"amount": 1, "unit": "g"}, "place_id": mine["place_id"]},
        ),
        (
            "PATCH",
            own,
            {
                "running_low_at": {
                    "amount": 1,
                    "unit": "cup",
                    "answers": [
                        {"kind": "weight_per_ml", "food_id": mine["food_id"], "grams": 100}
                    ],
                }
            },
        ),
    ]
    own_list = ok(neighbour.get(f"{API}/shopping/lists"))["lists"][0]["id"]
    for method, url, body in attempts:
        url = url.replace("{own_list}", own_list)
        response = neighbour.request(method, url, json=body)
        if url.endswith("/shopping/lists") and body and "id" in body:
            # Reusing another household's list ID is refused, and says nothing about it.
            assert response.status_code == 409, response.text
            assert response.json()["code"] == "id_taken"
            continue
        assert response.status_code == 404, (method, url, body, response.text)
        assert response.json().get("code") == "not_found", (method, url, response.text)
    assert snapshot(kitchen) == before


def test_lists_and_search_show_nothing_of_the_other_household(
    kitchen: TestClient, neighbour: TestClient, mine: dict[str, Any]
) -> None:
    for query in (
        {},
        {"q": "dal"},
        {"q": "arhar"},
        {"filter": "staples"},
        {"filter": "maybe_same"},
    ):
        listed = ok(neighbour.get(f"{API}/foods", params=query))
        assert listed["foods"] == [] and listed["total"] == 0, query
        assert listed["counts"]["all"] == 0
    assert ok(neighbour.get(f"{API}/shops")) == []
    their_places = ok(neighbour.get(f"{API}/places"))
    assert [p["name"] for p in their_places] == ["Fridge", "Freezer", "Cupboard", "Spice rack"]
    assert mine["place_id"] not in {p["id"] for p in their_places}
    pantry = ok(neighbour.get(f"{API}/pantry"))
    assert all(place["groups"] == [] for place in pantry["places"])
    assert pantry["counts"]["items"] == 0 and pantry["staples"] == []
    assert ok(neighbour.get(f"{API}/pantry/use-soon"))["lots"] == []
    assert ok(neighbour.get(f"{API}/changes"))["changes"] == []
    assert ok(neighbour.get(f"{API}/changes", params={"food_id": mine["food_id"]}))["changes"] == []
    assert ok(neighbour.get(f"{API}/changes", params={"area": "ingredients"}))["changes"] == []
    assert ok(neighbour.get(f"{API}/conversions")) == []
    # Cursors: the next page after or before household 1's own ids is still empty.
    assert ok(neighbour.get(f"{API}/foods", params={"after": "0"}))["foods"] == []
    assert ok(neighbour.get(f"{API}/foods", params={"after": "1"}))["foods"] == []
    newest = ok(kitchen.get(f"{API}/changes", params={"limit": 1}))["changes"][0]["id"]
    assert ok(neighbour.get(f"{API}/changes", params={"before": newest + 1}))["changes"] == []
    # Shopping lists: only their own main list, with nothing on it.
    theirs = ok(neighbour.get(f"{API}/shopping/lists"))["lists"]
    assert [(x["name"], x["main"], x["to_buy"]) for x in theirs] == [("This week", True, 0)]
    assert theirs[0]["id"] != mine["list_id"]
    view = ok(neighbour.get(f"{API}/shopping/lists/{theirs[0]['id']}"))
    assert view["shops"] == []
    assert ok(neighbour.get(f"{API}/household"))["name"] == "Next door"
    # The same names are free next door.
    ok(neighbour.post(f"{API}/foods", json={"name": "Toor dal"}), 201)
    ok(neighbour.post(f"{API}/shops", json={"name": "Spice Bazaar"}), 201)
    # And household 1 still sees only its own.
    names = [f["name"] for f in ok(kitchen.get(f"{API}/foods"))["foods"]]
    assert names == ["Moong dal", "Toor dal"]


def test_the_same_change_id_in_both_households(kitchen: TestClient, neighbour: TestClient) -> None:
    headers = {"Idempotency-Key": "same-key-in-two-households"}
    first = kitchen.post(f"{API}/foods", json={"name": "Toor dal"}, headers=headers)
    second = neighbour.post(f"{API}/foods", json={"name": "Ghee"}, headers=headers)
    assert (first.status_code, second.status_code) == (201, 201)
    assert "Idempotent-Replayed" not in second.headers
    assert second.json()["food"]["name"] == "Ghee"
    assert first.json()["change"]["id"] != second.json()["change"]["id"]
    # A retry in each household gets its own change back.
    again = neighbour.post(f"{API}/foods", json={"name": "Ghee"}, headers=headers)
    assert again.json()["change"]["id"] == second.json()["change"]["id"]
    again = kitchen.post(f"{API}/foods", json={"name": "Toor dal"}, headers=headers)
    assert again.json()["change"]["id"] == first.json()["change"]["id"]


def test_the_other_household_cannot_undo(
    kitchen: TestClient, neighbour: TestClient, mine: dict[str, Any]
) -> None:
    before = snapshot(kitchen)
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        from mealwright.models import Change

        ids = list(db.scalars(select(Change.id).where(Change.household_id == 1)))
    assert ids
    for change_id in ids:
        response = neighbour.post(f"{API}/changes/{change_id}/undo")
        assert response.status_code == 404, response.text
    assert snapshot(kitchen) == before
    # Household 1 can still undo its own.
    undo = ok(kitchen.post(f"{API}/changes/{mine['change_id']}/undo"))
    assert undo["result"] == "done"


def test_ingredient_changes_never_cross_households(
    kitchen: TestClient, neighbour: TestClient, mine: dict[str, Any]
) -> None:
    """Both households have ingredient changes, and Undos of them. Each asks for its own
    `area=ingredients` list, and gets only its own, with no cursor trick getting round it."""
    # Household 1: an edit, then its Undo.
    edit = ok(kitchen.patch(f"{API}/foods/{mine['food_id']}", json={"staple": True}))["change"]
    ok(kitchen.post(f"{API}/changes/{edit['id']}/undo"))
    theirs = ok(neighbour.post(f"{API}/foods", json={"name": "Neighbour's okra"}), 201)
    ok(neighbour.patch(f"{API}/foods/{theirs['food']['id']}", json={"staple": True}))

    def ask(client: TestClient, **params: Any) -> list[dict[str, Any]]:
        listed = ok(client.get(f"{API}/changes", params={"area": "ingredients", **params}))
        return listed["changes"]

    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        from mealwright.models import Change

        owner = {c.id: c.household_id for c in db.scalars(select(Change))}
    assert set(owner.values()) == {1, 2}
    ours, other = ask(kitchen), ask(neighbour)
    assert ours and other
    assert {owner[c["id"]] for c in ours} == {1}
    assert {owner[c["id"]] for c in other} == {2}
    assert [c["summary"] for c in other] == [
        "Neighbour's okra is now a staple",
        "Added Neighbour's okra",
    ]
    assert all("okra" not in c["summary"] for c in ours)
    assert all("Toor" not in c["summary"] and "Moong" not in c["summary"] for c in other)
    # Paging, a food filter and the "mine" filter don't leak either.
    assert ask(neighbour, food_id=mine["food_id"]) == []
    assert ask(neighbour, before=10**6, limit=100) == other
    # The neighbour cannot undo household 1's change through its own list either.
    assert neighbour.post(f"{API}/changes/{edit['id']}/undo").status_code == 404
