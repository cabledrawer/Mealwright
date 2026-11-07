"""Pack suggestions and the suggested Usual shop on the foods API (F120, F121; cabledrawer 7 Nov)."""

from typing import Any

from fastapi.testclient import TestClient

from mealwright.amounts import NBSP

API = "/api/v1"


def add(kitchen: TestClient, name: str, **extra: Any) -> dict[str, Any]:
    response = kitchen.post(f"{API}/foods", json={"name": name, **extra})
    assert response.status_code == 201, response.text
    food: dict[str, Any] = response.json()["food"]
    return food


def shop(kitchen: TestClient, name: str) -> int:
    response = kitchen.post(f"{API}/shops", json={"name": name})
    assert response.status_code == 201, response.text
    return int(response.json()["id"])


def listed(kitchen: TestClient, food_id: int) -> dict[str, Any]:
    foods = kitchen.get(f"{API}/foods").json()["foods"]
    return next(f for f in foods if f["id"] == food_id)


def test_the_editor_gets_the_tables_sizes_with_its_pack_word(kitchen: TestClient) -> None:
    ghee = add(kitchen, "Ghee")
    first = ghee["pack_suggestions"][0]
    assert first["pack"] == "jar"
    assert first["name"] == "jar"
    assert first["amount"] > 0
    assert first["display"].startswith("jar · ")
    fetched = kitchen.get(f"{API}/foods/{ghee['id']}").json()
    assert fetched["pack_suggestions"] == ghee["pack_suggestions"]


def test_a_name_the_table_does_not_know_gets_the_generic_sizes(kitchen: TestClient) -> None:
    food = add(kitchen, "Mystery dust")
    assert [s["amount"] for s in food["pack_suggestions"]] == [100, 250, 500, 1000]
    assert food["pack_suggestions"][0]["pack"] is None
    assert food["pack_suggestions"][0]["name"] == "pack"
    assert food["pack_suggestions"][0]["display"] == f"pack · 100{NBSP}g"


def test_a_count_ingredient_is_suggested_whole_numbers(kitchen: TestClient) -> None:
    food = add(kitchen, "Mystery thing", counted_as="count")
    assert [s["amount"] for s in food["pack_suggestions"]] == [1, 2, 6, 12]
    assert food["pack_suggestions"][3]["display"] == "pack · 12"


def test_a_staple_has_no_suggestions(kitchen: TestClient) -> None:
    assert add(kitchen, "Ghee", staple=True)["pack_suggestions"] == []


def test_a_tap_makes_the_suggestion_the_usual_size(kitchen: TestClient) -> None:
    ghee = add(kitchen, "Ghee")
    first, second = ghee["pack_suggestions"][:2]
    one = kitchen.post(
        f"{API}/foods/{ghee['id']}/sizes",
        json={"name": first["name"], "amount": first["amount"]},
    ).json()["food"]
    assert [s["usual"] for s in one["sizes"]] == [True]
    # A tapped second suggestion on an ingredient with a size takes the Usual place.
    two = kitchen.post(
        f"{API}/foods/{ghee['id']}/sizes",
        json={"name": second["name"], "amount": second["amount"], "usual": True},
    ).json()["food"]
    assert [(s["name"], s["usual"]) for s in two["sizes"]] == [
        (first["name"], False),
        (second["name"], True),
    ]
    # A size it has is no longer suggested.
    amounts = [s["amount"] for s in two["pack_suggestions"]]
    assert first["amount"] not in amounts
    assert second["amount"] not in amounts


def test_the_list_has_the_pack_column_data(kitchen: TestClient) -> None:
    ghee = add(kitchen, "Ghee")
    none_yet = listed(kitchen, ghee["id"])
    assert none_yet["pack"] is None
    assert none_yet["more_sizes"] == []
    assert none_yet["pack_suggestions"] == ghee["pack_suggestions"]

    sizes = ghee["pack_suggestions"]
    for pick in sizes[:2]:
        kitchen.post(
            f"{API}/foods/{ghee['id']}/sizes", json={"name": pick["name"], "amount": pick["amount"]}
        )
    row = listed(kitchen, ghee["id"])
    assert row["pack"]["name"] == sizes[0]["name"]
    assert row["pack"]["usual"] is True
    assert [s["name"] for s in row["more_sizes"]] == [sizes[1]["name"]]
    assert row["pack_suggestions"] == []  # only an ingredient with no size gets them


def test_a_new_ingredient_gets_the_suggested_shop(kitchen: TestClient) -> None:
    tesco = shop(kitchen, "Tesco")
    indian = shop(kitchen, "Indian grocer")
    # Supermarket and world-aisle things: the first shop.
    assert add(kitchen, "Plain flour")["shop"]["id"] == tesco
    # A specialist thing: the shop that names a kind of grocer.
    assert add(kitchen, "Curry leaves")["shop"]["id"] == indian
    # No table row: nothing suggested.
    assert add(kitchen, "Mystery dust")["shop"] is None


def test_a_shop_in_the_request_is_never_replaced(kitchen: TestClient) -> None:
    tesco = shop(kitchen, "Tesco")
    indian = shop(kitchen, "Indian grocer")
    assert add(kitchen, "Plain flour", shop_id=indian)["shop"]["id"] == indian
    # Sent as null: no shop was asked for, so none is suggested.
    assert add(kitchen, "Basmati rice", shop_id=None)["shop"] is None
    assert tesco != indian


def test_no_shops_means_no_suggestion(kitchen: TestClient) -> None:
    assert add(kitchen, "Plain flour")["shop"] is None


def test_another_household_cannot_use_my_shop_or_my_ingredient(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    mine = shop(kitchen, "Tesco")
    refused = neighbour.post(f"{API}/foods", json={"name": "Flour", "shop_id": mine})
    assert refused.status_code == 404
    ghee = add(kitchen, "Ghee")
    cant = neighbour.post(
        f"{API}/foods/{ghee['id']}/sizes", json={"name": "jar", "amount": 500, "usual": True}
    )
    assert cant.status_code == 404
    assert neighbour.get(f"{API}/foods/{ghee['id']}").status_code == 404
    # The neighbour's own suggestions use the neighbour's shops only.
    own = shop(neighbour, "Aldi")
    assert add(neighbour, "Plain flour")["shop"]["id"] == own
    assert own != mine


def test_undo_of_an_added_pack_takes_it_back(kitchen: TestClient) -> None:
    ghee = add(kitchen, "Ghee")
    pick = ghee["pack_suggestions"][0]
    body = kitchen.post(
        f"{API}/foods/{ghee['id']}/sizes",
        json={"name": pick["name"], "amount": pick["amount"], "usual": True},
    ).json()
    undone = kitchen.post(f"{API}/changes/{body['change']['id']}/undo")
    assert undone.status_code == 200, undone.text
    assert kitchen.get(f"{API}/foods/{ghee['id']}").json()["sizes"] == []
