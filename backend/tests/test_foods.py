"""Foods: the Ingredients screen, the editor, other names, sizes, stand-ins, merge, split."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

API = "/api/v1"


def add(kitchen: TestClient, name: str, **extra: Any) -> dict[str, Any]:
    response = kitchen.post(f"{API}/foods", json={"name": name, **extra})
    assert response.status_code == 201, response.text
    food: dict[str, Any] = response.json()["food"]
    return food


def patch(kitchen: TestClient, food_id: int, **field: Any) -> dict[str, Any]:
    response = kitchen.patch(f"{API}/foods/{food_id}", json=field)
    assert response.status_code == 200, response.text
    body: dict[str, Any] = response.json()
    return body


def place_id(kitchen: TestClient, name: str) -> int:
    return next(p["id"] for p in kitchen.get(f"{API}/places").json() if p["name"] == name)


# --- Create and read -------------------------------------------------------------------------


def test_needs_sign_in(client: TestClient) -> None:
    assert client.get(f"{API}/foods").status_code == 401


def test_create_food(kitchen: TestClient) -> None:
    response = kitchen.post(f"{API}/foods", json={"name": "  Toor   dal "})
    assert response.status_code == 201
    body = response.json()
    food = body["food"]
    assert food["name"] == "Toor dal"
    assert food["counted_as"] == "weight"  # not in the table: by weight
    assert food["counted_as_display"] == "Weight"
    assert food["cup_weight"] is None
    assert body["change"]["kind"] == "food_created"
    assert body["change"]["summary"] == "Added Toor dal"
    assert body["change"]["can_undo"] is True
    assert body["change"]["who"]["name"] == "Tess"


def test_table_sets_how_its_counted(kitchen: TestClient) -> None:
    eggs = add(kitchen, "Eggs")
    assert eggs["counted_as"] == "count"
    assert eggs["item_weight"] == {"grams": 50.0, "from": "table", "cup_ml": None}
    flour = add(kitchen, "Plain flour")
    assert flour["cup_weight"]["from"] == "table"
    assert flour["cup_weight"]["cup_ml"] == 250


def test_name_must_be_new(kitchen: TestClient) -> None:
    first = add(kitchen, "Toor dal")
    response = kitchen.post(f"{API}/foods", json={"name": "TOOR DAL"})
    assert response.status_code == 409
    assert response.json() == {
        "detail": "There’s already an ingredient called Toor dal.",
        "code": "name_taken",
        "food_id": first["id"],
    }


def test_blank_name_refused(kitchen: TestClient) -> None:
    assert kitchen.post(f"{API}/foods", json={"name": "   "}).status_code == 422


def test_unknown_food_is_404(kitchen: TestClient) -> None:
    response = kitchen.get(f"{API}/foods/999")
    assert response.status_code == 404
    assert response.json()["code"] == "not_found"


# --- List, search, filters -------------------------------------------------------------------


def test_search_by_any_name(kitchen: TestClient) -> None:
    toor = add(kitchen, "Toor dal")
    kitchen.post(f"{API}/foods/{toor['id']}/other-names", json={"name": "arhar dal"})
    add(kitchen, "Moong dal")
    add(kitchen, "Daliya")
    add(kitchen, "Onion")

    found = kitchen.get(f"{API}/foods", params={"q": "dal"}).json()
    # Names starting with "dal" first, then names containing it.
    assert [f["name"] for f in found["foods"]] == ["Daliya", "Moong dal", "Toor dal"]
    assert found["counts"]["all"] == 4

    by_other = kitchen.get(f"{API}/foods", params={"q": "ARHAR"}).json()["foods"]
    assert [(f["name"], f["matched_name"]) for f in by_other] == [("Toor dal", "arhar dal")]


def test_f97_an_exact_name_or_other_name_comes_first_even_past_the_first_page(
    kitchen: TestClient,
) -> None:
    """The Ingredients page offers "+ New ingredient" from the first page only, so an ingredient
    named exactly what was typed (or with that other name) must be on it, however many names
    merely contain the text."""
    for number in range(60):  # more than a page of names that contain "chilli flakes"
        add(kitchen, f"Zz chilli flakes {number:02d}")
    hot = add(kitchen, "Zzz hot flakes")
    kitchen.post(f"{API}/foods/{hot['id']}/other-names", json={"name": "Chilli flakes"})
    page = kitchen.get(f"{API}/foods", params={"q": "chilli flakes", "limit": 50}).json()
    assert page["next"] is not None
    assert (page["foods"][0]["name"], page["foods"][0]["matched_name"]) == (
        "Zzz hot flakes",
        "Chilli flakes",
    )
    # Spaces and accents count the same on both sides: two spaces still find "Chilli flakes",
    # and "jalapeno" finds the other name "Jalape\u00f1o" first, past 60 names that contain it.
    page = kitchen.get(f"{API}/foods", params={"q": "chilli  flakes", "limit": 50}).json()
    assert page["foods"][0]["id"] == hot["id"]
    for number in range(60):
        add(kitchen, f"Zz jalapeno {number:02d}")
    pepper = add(kitchen, "Zzz green pepper")
    kitchen.post(f"{API}/foods/{pepper['id']}/other-names", json={"name": "Jalape\u00f1o"})
    page = kitchen.get(f"{API}/foods", params={"q": "jalapeno", "limit": 50}).json()
    assert page["next"] is not None and page["foods"][0]["id"] == pepper["id"]
    # No exact match: nothing is out of order (names that start with it, then contain it).
    page = kitchen.get(f"{API}/foods", params={"q": "zz chilli", "limit": 3}).json()
    assert [f["name"] for f in page["foods"]] == [f"Zz chilli flakes {n:02d}" for n in range(3)]


def test_staples_filter(kitchen: TestClient) -> None:
    salt = add(kitchen, "Salt", staple=True)
    add(kitchen, "Toor dal")
    listed = kitchen.get(f"{API}/foods", params={"filter": "staples"}).json()
    assert [f["id"] for f in listed["foods"]] == [salt["id"]]
    assert listed["foods"][0]["counted_as_display"] == "Staple"
    assert listed["counts"]["staples"] == 1


def test_paging(kitchen: TestClient) -> None:
    for name in ("A", "B", "C"):
        add(kitchen, name)
    first = kitchen.get(f"{API}/foods", params={"limit": 2}).json()
    assert [f["name"] for f in first["foods"]] == ["A", "B"]
    second = kitchen.get(f"{API}/foods", params={"limit": 2, "after": first["next"]}).json()
    assert [f["name"] for f in second["foods"]] == ["C"]
    assert second["next"] is None


def test_maybe_the_same(kitchen: TestClient) -> None:
    moringa = add(kitchen, "Drumsticks (moringa)")
    drumsticks = add(kitchen, "Drumstick")
    toor = add(kitchen, "Toor dal")
    tuvar = add(kitchen, "Tuvar dal")
    kitchen.post(f"{API}/foods/{toor['id']}/other-names", json={"name": "Tuvar dal"})

    listed = kitchen.get(f"{API}/foods", params={"filter": "maybe_same"}).json()
    assert listed["counts"]["maybe_same"] == 4  # foods
    assert listed["counts"]["maybe_same_pairs"] == 2
    same = {f["name"]: [m["name"] for m in f["maybe_same"]] for f in listed["foods"]}
    assert same["Drumsticks (moringa)"] == ["Drumstick"]
    assert same["Tuvar dal"] == ["Toor dal"]
    # The same length: the newer food (Tuvar dal) would be merged away.
    assert kitchen.get(f"{API}/foods/{toor['id']}").json()["maybe_same"] == [
        {"id": tuvar["id"], "name": "Tuvar dal", "merge_into": toor["id"], "merge_this": False}
    ]
    # The longer name goes.
    moringa_entry = next(f for f in listed["foods"] if f["id"] == moringa["id"])["maybe_same"]
    assert moringa_entry[0]["merge_into"] == drumsticks["id"]
    assert moringa_entry[0]["merge_this"] is True

    assert (
        kitchen.post(
            f"{API}/foods/{drumsticks['id']}/not-the-same", json={"food_id": moringa["id"]}
        ).status_code
        == 204
    )
    listed = kitchen.get(f"{API}/foods", params={"filter": "maybe_same"}).json()
    assert {f["name"] for f in listed["foods"]} == {"Toor dal", "Tuvar dal"}


# --- Editing, one field at a time ------------------------------------------------------------


def test_one_field_at_a_time(kitchen: TestClient) -> None:
    food = add(kitchen, "Toor dal")
    response = kitchen.patch(f"{API}/foods/{food['id']}", json={"name": "A", "staple": True})
    assert response.status_code == 422
    assert response.json()["code"] == "one_field"


def test_edit_fields(kitchen: TestClient) -> None:
    food = add(kitchen, "Toor dal")
    cupboard = place_id(kitchen, "Cupboard")
    shop = kitchen.post(f"{API}/shops", json={"name": "Spice Bazaar"}).json()

    body = patch(kitchen, food["id"], place_id=cupboard)
    assert body["food"]["place"] == {"id": cupboard, "name": "Cupboard"}
    assert body["change"]["summary"] == "Toor dal now lives in Cupboard"

    body = patch(kitchen, food["id"], shop_id=shop["id"])
    assert body["food"]["shop"]["name"] == "Spice Bazaar"

    body = patch(kitchen, food["id"], staple=True)
    assert body["food"]["staple"] is True
    assert body["change"]["summary"] == "Toor dal is now a staple"

    body = patch(kitchen, food["id"], name="Tuvar dal")
    assert body["food"]["name"] == "Tuvar dal"
    assert body["food"]["last_change"]["summary"] == "Renamed Toor dal to Tuvar dal"

    body = patch(kitchen, food["id"], place_id=None)
    assert body["food"]["place"] is None


def test_nothing_changed_records_nothing(kitchen: TestClient) -> None:
    food = add(kitchen, "Toor dal")
    body = patch(kitchen, food["id"], staple=False)
    assert body["change"] is None
    assert body["food"]["name"] == "Toor dal"


def test_rename_clash(kitchen: TestClient) -> None:
    add(kitchen, "Onion")
    food = add(kitchen, "Red onion")
    response = kitchen.patch(f"{API}/foods/{food['id']}", json={"name": "onion"})
    assert response.status_code == 409


def test_count_word(kitchen: TestClient) -> None:
    bread = add(kitchen, "Bread", counted_as="count")
    body = patch(kitchen, bread["id"], count_word="slice")
    assert body["food"]["count_word_plural"] == "slices"
    assert body["food"]["counted_as_display"] == "Slices"


def test_cup_weight_is_the_households_answer(kitchen: TestClient) -> None:
    food = add(kitchen, "Toor dal")
    body = patch(kitchen, food["id"], cup_weight=200)
    assert body["food"]["cup_weight"] == {"grams": 200.0, "from": "you", "cup_ml": 250}
    assert body["change"]["summary"] == "Weight of 1\u00a0cup of Toor dal is now 200\u00a0g"
    converted = kitchen.get(
        f"{API}/foods/{food['id']}/convert", params={"amount": 1, "unit": "cup"}
    ).json()
    assert converted == {
        "amount": 200.0,
        "unit": "g",
        "from": "you",
        "display": "200\u00a0g",
        "ask": None,
    }
    body = patch(kitchen, food["id"], cup_weight=None)
    assert body["food"]["cup_weight"] is None


def test_household_answer_beats_the_table(kitchen: TestClient) -> None:
    flour = add(kitchen, "Plain flour")
    body = patch(kitchen, flour["id"], cup_weight=140)
    assert body["food"]["cup_weight"]["from"] == "you"
    assert body["food"]["cup_weight"]["grams"] == 140.0


def test_running_low_in_sizes(kitchen: TestClient) -> None:
    food = add(kitchen, "Toor dal")
    kitchen.post(f"{API}/foods/{food['id']}/sizes", json={"name": "packet", "amount": 500})
    body = patch(kitchen, food["id"], running_low_at={"amount": 0.5, "unit": "packet"})
    low = body["food"]["running_low_at"]
    assert low["amount"] == 250.0
    assert low["short"] == "½\u00a0packet"
    assert body["change"]["summary"] == "Toor dal runs low at ½\u00a0packet"


def test_running_low_for_a_count_never_says_left(kitchen: TestClient) -> None:
    """A whole thing's level reads "runs low at 6", not "6 left" (job 3 review, M1)."""
    food = add(kitchen, "Spring onions", counted_as="count")
    body = patch(kitchen, food["id"], running_low_at={"amount": 6, "unit": "count"})
    assert body["change"]["summary"] == "Spring onions runs low at 6"


def test_counted_as_change_converts_sizes(kitchen: TestClient) -> None:
    food = add(kitchen, "Toor dal")
    kitchen.post(f"{API}/foods/{food['id']}/sizes", json={"name": "packet", "amount": 500})
    response = kitchen.patch(f"{API}/foods/{food['id']}", json={"counted_as": "volume"})
    assert response.status_code == 409
    asked = response.json()
    assert asked["code"] == "ask_once"
    assert asked["ask"]["question"] == "About how much does 1\u00a0cup of Toor dal weigh?"
    assert asked["ask"]["suggested"] == 200.0

    answer = {"kind": "weight_per_ml", "food_id": food["id"], "grams": 200, "remember": True}
    body = patch(kitchen, food["id"], counted_as="volume", answers=[answer])
    assert body["food"]["counted_as"] == "volume"
    assert body["food"]["sizes"][0]["amount"] == 625.0  # 500 g at 0.8 g/ml
    assert body["food"]["cup_weight"]["from"] == "you"


def test_counting_by_number_asks_for_the_weight_of_one(kitchen: TestClient) -> None:
    food = add(kitchen, "Toor dal")
    kitchen.post(f"{API}/foods/{food['id']}/sizes", json={"name": "packet", "amount": 500})
    response = kitchen.patch(f"{API}/foods/{food['id']}", json={"counted_as": "count"})
    assert response.status_code == 409
    asked = response.json()["ask"]
    assert asked["kind"] == "item_weight"
    assert asked["question"] == "Toor dal: about how much does one weigh?"
    assert asked["suggested"] is None
    unchanged = kitchen.get(f"{API}/foods/{food['id']}").json()
    assert unchanged["counted_as"] == "weight"
    assert unchanged["sizes"][0]["display"] == "Packet = 500\u00a0g"

    answer = {"kind": "item_weight", "food_id": food["id"], "grams": 50}
    body = patch(kitchen, food["id"], counted_as="count", answers=[answer])
    assert body["food"]["sizes"][0]["display"] == "Packet = 10"


# --- Ask once --------------------------------------------------------------------------------


def test_convert_asks_once_when_unknown(kitchen: TestClient) -> None:
    onion = add(kitchen, "Shallot", counted_as="count")
    converted = kitchen.get(
        f"{API}/foods/{onion['id']}/convert", params={"amount": 100, "unit": "g"}
    ).json()
    assert converted["amount"] is None
    assert converted["ask"]["kind"] == "item_weight"
    assert converted["ask"]["question"] == "Shallot: about how much does one weigh?"
    assert converted["ask"]["suggested"] is None  # no table entry: nothing to guess from


def test_slices_in_a_loaf_asked_once(kitchen: TestClient) -> None:
    bread = add(kitchen, "Bread", counted_as="count")
    patch(kitchen, bread["id"], count_word="slice")
    response = kitchen.patch(
        f"{API}/foods/{bread['id']}", json={"running_low_at": {"amount": 1, "unit": "loaf"}}
    )
    assert response.status_code == 409
    asked = response.json()["ask"]
    assert asked["kind"] == "size"
    assert asked["question"] == "About how many slices in a loaf of Bread?"
    assert asked["suggested"] == 20.0

    answer = {"kind": "size", "food_id": bread["id"], "name": "loaf", "amount": 20}
    body = patch(
        kitchen, bread["id"], running_low_at={"amount": 1, "unit": "loaf", "answers": [answer]}
    )
    assert body["food"]["sizes"][0]["display"] == "Loaf = 20\u00a0slices"
    assert body["food"]["running_low_at"]["amount"] == 20.0


def test_answer_not_remembered(kitchen: TestClient) -> None:
    food = add(kitchen, "Jaggery")
    answer = {"kind": "weight_per_ml", "food_id": food["id"], "grams": 180, "remember": False}
    body = patch(
        kitchen, food["id"], running_low_at={"amount": 1, "unit": "cup", "answers": [answer]}
    )
    assert body["food"]["running_low_at"]["amount"] == 180.0
    assert body["food"]["cup_weight"] is None


# --- Other names and sizes -------------------------------------------------------------------


def test_other_names(kitchen: TestClient) -> None:
    food = add(kitchen, "Toor dal")
    response = kitchen.post(f"{API}/foods/{food['id']}/other-names", json={"name": "arhar dal"})
    assert response.status_code == 201
    names = response.json()["food"]["other_names"]
    assert [n["name"] for n in names] == ["arhar dal"]
    again = kitchen.post(f"{API}/foods/{food['id']}/other-names", json={"name": "Arhar Dal"})
    assert (again.status_code, again.json()["code"]) == (409, "already_there")
    own = kitchen.post(f"{API}/foods/{food['id']}/other-names", json={"name": "toor dal"})
    assert (own.status_code, own.json()["code"]) == (409, "already_there")
    response = kitchen.delete(f"{API}/foods/{food['id']}/other-names/{names[0]['id']}")
    assert response.json()["food"]["other_names"] == []


def test_other_name_matches_the_table(kitchen: TestClient) -> None:
    food = add(kitchen, "Maida flour")
    assert food["cup_weight"] is None
    response = kitchen.post(f"{API}/foods/{food['id']}/other-names", json={"name": "plain flour"})
    assert response.json()["food"]["cup_weight"]["from"] == "table"


def test_sizes(kitchen: TestClient) -> None:
    food = add(kitchen, "Toor dal")
    packet = kitchen.post(
        f"{API}/foods/{food['id']}/sizes", json={"name": "Packet", "amount": 500}
    ).json()["food"]["sizes"][0]
    assert packet["display"] == "Packet = 500\u00a0g"
    assert packet["usual"] is True
    body = kitchen.post(
        f"{API}/foods/{food['id']}/sizes",
        json={"name": "bag", "amount": {"amount": 1, "unit": "kg"}},
    ).json()
    bag = body["food"]["sizes"][1]
    assert bag["display"] == "Bag = 1\u00a0kg" and bag["usual"] is False
    assert body["food"]["counted_as_display"] == "Packets · 500\u00a0g"

    body = kitchen.patch(f"{API}/foods/{food['id']}/sizes/{bag['id']}", json={"usual": True}).json()
    assert [s["usual"] for s in body["food"]["sizes"]] == [False, True]
    assert body["food"]["counted_as_display"] == "Bags · 1\u00a0kg"

    body = kitchen.delete(f"{API}/foods/{food['id']}/sizes/{bag['id']}").json()
    assert [(s["name"], s["usual"]) for s in body["food"]["sizes"]] == [("Packet", True)]


def test_size_plural(kitchen: TestClient) -> None:
    bread = add(kitchen, "Bread", counted_as="count")
    size = kitchen.post(
        f"{API}/foods/{bread['id']}/sizes", json={"name": "loaf", "amount": 20}
    ).json()["food"]["sizes"][0]
    assert size["plural"] == "loaves"


# --- Can use instead -------------------------------------------------------------------------


def test_stand_ins(kitchen: TestClient) -> None:
    onion = add(kitchen, "Onion")
    red = add(kitchen, "Red onion")
    body = kitchen.post(f"{API}/foods/{onion['id']}/stand-ins", json={"food_id": red["id"]}).json()
    assert body["food"]["stand_ins"] == [{"id": red["id"], "name": "Red onion", "both_ways": False}]
    assert body["change"]["summary"] == "Red onion can be used instead of Onion"
    assert kitchen.get(f"{API}/foods/{red['id']}").json()["stands_in_for"][0]["name"] == "Onion"
    listed = kitchen.get(f"{API}/foods", params={"q": "onion"}).json()["foods"]
    assert listed[0]["stand_ins"] == [{"id": red["id"], "name": "Red onion"}]

    body = kitchen.post(
        f"{API}/foods/{onion['id']}/stand-ins", json={"food_id": red["id"], "both_ways": True}
    ).json()
    assert body["food"]["stand_ins"][0]["both_ways"] is True

    body = kitchen.delete(f"{API}/foods/{onion['id']}/stand-ins/{red['id']}").json()
    assert body["food"]["stand_ins"] == []
    assert body["food"]["stands_in_for"][0]["name"] == "Red onion"  # the other way stays


def test_no_self_stand_in(kitchen: TestClient) -> None:
    onion = add(kitchen, "Onion")
    response = kitchen.post(f"{API}/foods/{onion['id']}/stand-ins", json={"food_id": onion["id"]})
    assert response.status_code == 422


# --- Merge, undo merge, split ----------------------------------------------------------------


def test_merge_moves_everything(kitchen: TestClient) -> None:
    moringa = add(kitchen, "Drumsticks (moringa)", counted_as="count")
    kitchen.post(f"{API}/foods/{moringa['id']}/other-names", json={"name": "murungakkai"})
    kitchen.post(f"{API}/foods/{moringa['id']}/sizes", json={"name": "bundle", "amount": 6})
    sambar = add(kitchen, "Sambar veg")
    kitchen.post(f"{API}/foods/{sambar['id']}/stand-ins", json={"food_id": moringa["id"]})
    drumsticks = add(kitchen, "Drumsticks")

    response = kitchen.post(
        f"{API}/foods/{moringa['id']}/merge", json={"into_id": drumsticks["id"]}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    food = body["food"]
    assert food["id"] == drumsticks["id"]
    assert sorted(n["name"] for n in food["other_names"]) == [
        "Drumsticks (moringa)",
        "murungakkai",
    ]
    assert [s["name"] for s in food["sizes"]] == ["bundle"]
    assert food["stands_in_for"] == [{"id": sambar["id"], "name": "Sambar veg", "both_ways": False}]
    assert body["change"]["summary"] == "Merged Drumsticks (moringa) into Drumsticks"

    # The merged-away food is gone from lists, but its old id still finds the food.
    names = [f["name"] for f in kitchen.get(f"{API}/foods").json()["foods"]]
    assert "Drumsticks (moringa)" not in names
    old = kitchen.get(f"{API}/foods/{moringa['id']}").json()
    assert old["id"] == drumsticks["id"]
    assert old["merged_from"] == {"id": moringa["id"], "name": "Drumsticks (moringa)"}

    # Undo restores both foods exactly.
    undo = kitchen.post(f"{API}/changes/{body['change']['id']}/undo").json()
    assert undo["result"] == "done"
    back = kitchen.get(f"{API}/foods/{moringa['id']}").json()
    assert back["id"] == moringa["id"]
    assert [n["name"] for n in back["other_names"]] == ["murungakkai"]
    assert [s["name"] for s in back["sizes"]] == ["bundle"]
    assert back["stands_in_for"][0]["name"] == "Sambar veg"
    after = kitchen.get(f"{API}/foods/{drumsticks['id']}").json()
    assert after["other_names"] == [] and after["sizes"] == [] and after["stands_in_for"] == []


def test_merge_between_count_and_weight_asks(kitchen: TestClient) -> None:
    onion = add(kitchen, "Onion")  # count, 110 g each in the table
    shallot = add(kitchen, "Small onions", counted_as="weight")
    kitchen.post(f"{API}/foods/{shallot['id']}/sizes", json={"name": "bag", "amount": 330})
    body = kitchen.post(f"{API}/foods/{shallot['id']}/merge", json={"into_id": onion["id"]}).json()
    assert body["food"]["sizes"][0]["amount"] == 3.0  # 330 g of 110 g onions

    garlic = add(kitchen, "Wild garlic", counted_as="count")
    leaves = add(kitchen, "Garlic leaves", counted_as="weight")
    kitchen.post(f"{API}/foods/{leaves['id']}/sizes", json={"name": "bunch", "amount": 100})
    response = kitchen.post(f"{API}/foods/{leaves['id']}/merge", json={"into_id": garlic["id"]})
    assert response.status_code == 409
    assert response.json()["ask"]["kind"] == "item_weight"
    answer = {"kind": "item_weight", "food_id": garlic["id"], "grams": 50}
    response = kitchen.post(
        f"{API}/foods/{leaves['id']}/merge", json={"into_id": garlic["id"], "answers": [answer]}
    )
    assert response.status_code == 200
    assert response.json()["food"]["sizes"][0]["amount"] == 2.0


def test_split_revives_a_merged_food(kitchen: TestClient) -> None:
    moringa = add(kitchen, "Moringa")
    drumsticks = add(kitchen, "Drumsticks")
    merged = kitchen.post(
        f"{API}/foods/{moringa['id']}/merge", json={"into_id": drumsticks["id"]}
    ).json()
    name_id = merged["food"]["other_names"][0]["id"]
    response = kitchen.post(
        f"{API}/foods/{drumsticks['id']}/split", json={"other_name_id": name_id}
    )
    assert response.status_code == 201
    body = response.json()
    assert body["food"]["id"] == moringa["id"]  # same id, so old links point to it again
    assert body["change"]["summary"] == "Made Moringa its own ingredient again"
    assert kitchen.get(f"{API}/foods/{drumsticks['id']}").json()["other_names"] == []

    # Undoing the split merges them back.
    kitchen.post(f"{API}/changes/{body['change']['id']}/undo")
    assert kitchen.get(f"{API}/foods/{moringa['id']}").json()["id"] == drumsticks["id"]


def test_split_a_plain_other_name(kitchen: TestClient) -> None:
    onion = add(kitchen, "Onion", place_id=place_id(kitchen, "Cupboard"))
    named = kitchen.post(f"{API}/foods/{onion['id']}/other-names", json={"name": "Red onion"})
    name_id = named.json()["food"]["other_names"][0]["id"]
    body = kitchen.post(f"{API}/foods/{onion['id']}/split", json={"other_name_id": name_id}).json()
    assert body["food"]["name"] == "Red onion"
    assert body["food"]["counted_as"] == "count"
    assert body["food"]["place"]["name"] == "Cupboard"
    # F54 sweep: a split-off name is not left in the Other pile.
    assert body["food"]["aisle"] == onion["aisle"]
    assert body["food"]["aisle"] not in (None, "other")

    undo = kitchen.post(f"{API}/changes/{body['change']['id']}/undo").json()
    assert undo["result"] == "done"
    names = [f["name"] for f in kitchen.get(f"{API}/foods").json()["foods"]]
    assert names == ["Onion"]
    assert kitchen.get(f"{API}/foods/{onion['id']}").json()["other_names"][0]["name"] == "Red onion"


def test_cannot_merge_into_itself(kitchen: TestClient) -> None:
    food = add(kitchen, "Onion")
    response = kitchen.post(f"{API}/foods/{food['id']}/merge", json={"into_id": food["id"]})
    assert response.status_code == 422


# --- Remove ----------------------------------------------------------------------------------


def test_remove_and_undo(kitchen: TestClient) -> None:
    food = add(kitchen, "Typo fod")
    body = kitchen.delete(f"{API}/foods/{food['id']}").json()
    assert body["food"] is None
    assert body["change"]["summary"] == "Removed Typo fod from Ingredients"
    assert kitchen.get(f"{API}/foods/{food['id']}").status_code == 404
    kitchen.post(f"{API}/changes/{body['change']['id']}/undo")
    assert kitchen.get(f"{API}/foods/{food['id']}").json()["name"] == "Typo fod"


# --- Retries -----------------------------------------------------------------------------------


def test_retry_is_not_applied_twice(kitchen: TestClient) -> None:
    headers = {"Idempotency-Key": "4b1f6c1e-6a47-4c43-9d6e-0d6f0a0c9b11"}
    first = kitchen.post(f"{API}/foods", json={"name": "Toor dal"}, headers=headers)
    again = kitchen.post(f"{API}/foods", json={"name": "Toor dal"}, headers=headers)
    assert first.status_code == 201
    assert again.status_code == 200
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["change"]["id"] == first.json()["change"]["id"]
    assert kitchen.get(f"{API}/foods").json()["total"] == 1


def test_key_reused_for_something_else(kitchen: TestClient) -> None:
    headers = {"Idempotency-Key": "same-key"}
    food = kitchen.post(f"{API}/foods", json={"name": "Toor dal"}, headers=headers).json()
    response = kitchen.patch(
        f"{API}/foods/{food['food']['id']}", json={"staple": True}, headers=headers
    )
    assert response.status_code == 409
    assert response.json()["code"] == "key_reused"


@pytest.mark.parametrize("key", ["", "x" * 65, "has space"])
def test_bad_key(kitchen: TestClient, key: str) -> None:
    response = kitchen.post(f"{API}/foods", json={"name": "A"}, headers={"Idempotency-Key": key})
    assert response.status_code == 422


def test_failed_request_can_be_retried_with_the_same_key(kitchen: TestClient) -> None:
    food = add(kitchen, "Jaggery")
    headers = {"Idempotency-Key": "ask-then-answer"}
    url = f"{API}/foods/{food['id']}"
    cup = {"running_low_at": {"amount": 1, "unit": "cup"}}
    first = kitchen.patch(url, json=cup, headers=headers)
    assert first.status_code == 409
    answer = {"kind": "weight_per_ml", "food_id": food["id"], "grams": 180}
    second = kitchen.patch(
        url,
        json={"running_low_at": {"amount": 1, "unit": "cup", "answers": [answer]}},
        headers=headers,
    )
    assert second.status_code == 200
    assert second.json()["food"]["running_low_at"]["amount"] == 180.0


# --- Limits (nothing may overflow the stored numbers) ----------------------------------------


def test_huge_size_with_a_conversion_is_refused_not_a_crash(kitchen: TestClient) -> None:
    food = add(kitchen, "Milk drink", counted_as="volume")
    url = f"{API}/foods/{food['id']}"
    huge = kitchen.post(f"{url}/sizes", json={"name": "tank", "amount": "999999999999.999"})
    assert huge.status_code == 422
    kitchen.post(f"{url}/sizes", json={"name": "tank", "amount": 1_000_000})
    patch(kitchen, food["id"], cup_weight=2_000)
    response = kitchen.patch(url, json={"counted_as": "weight"})
    # 1,000,000 ml at 8 g/ml would be 8,000,000 g: over the limit, so refused plainly.
    assert response.status_code == 422
    assert response.json()["code"] == "too_big"
    assert kitchen.get(url).json()["counted_as"] == "volume"


@pytest.mark.parametrize(
    "field",
    [
        {"cup_weight": 2_001},
        {"item_weight": 50_001},
        {"running_low_at": {"amount": 1_000_001, "unit": "g"}},
        {"running_low_at": {"amount": 1_001, "unit": "kg"}},
    ],
)
def test_limits(kitchen: TestClient, field: dict[str, Any]) -> None:
    food = add(kitchen, "Toor dal")
    response = kitchen.patch(f"{API}/foods/{food['id']}", json=field)
    assert response.status_code == 422


def test_answer_limits(kitchen: TestClient) -> None:
    food = add(kitchen, "Jaggery")
    answer = {"kind": "weight_per_ml", "food_id": food["id"], "grams": 2_001}
    response = kitchen.patch(
        f"{API}/foods/{food['id']}",
        json={"running_low_at": {"amount": 1, "unit": "cup", "answers": [answer]}},
    )
    assert response.status_code == 422


def test_largest_amounts_are_fine(kitchen: TestClient) -> None:
    food = add(kitchen, "Flour sack")
    body = patch(kitchen, food["id"], running_low_at={"amount": 1_000, "unit": "kg"})
    assert body["food"]["running_low_at"]["display"] == "1000\u00a0kg"


def test_maybe_the_same_keeps_the_food_with_stock(kitchen: TestClient) -> None:
    short = add(kitchen, "Drumstick")
    longer = add(kitchen, "Drumsticks (moringa)")
    body = {"food_id": longer["id"], "amount": {"amount": 3, "unit": "count"}}
    assert kitchen.post(f"{API}/stock", json=body).status_code == 201
    entry = kitchen.get(f"{API}/foods/{short['id']}").json()["maybe_same"][0]
    assert entry["merge_into"] == longer["id"]  # it has stock, so it stays
    assert entry["merge_this"] is True


@pytest.mark.parametrize("name", ["1", "  12 ", "½", "1/2", "-", "500 500"])
def test_a_size_name_must_have_letters(kitchen: TestClient, name: str) -> None:
    toor = add(kitchen, "Toor dal")
    response = kitchen.post(f"{API}/foods/{toor['id']}/sizes", json={"name": name, "amount": 500})
    assert response.status_code == 422
    assert "Give the size a name, like tub or packet." in response.text
    # Renaming a size to a number is refused too, and nothing was added.
    kitchen.post(f"{API}/foods/{toor['id']}/sizes", json={"name": "packet", "amount": 500})
    size_id = kitchen.get(f"{API}/foods/{toor['id']}").json()["sizes"][0]["id"]
    renamed = kitchen.patch(f"{API}/foods/{toor['id']}/sizes/{size_id}", json={"name": name})
    assert renamed.status_code == 422
    assert [s["name"] for s in kitchen.get(f"{API}/foods/{toor['id']}").json()["sizes"]] == [
        "packet"
    ]


def test_a_size_answer_needs_a_real_name_too(kitchen: TestClient) -> None:
    bread = add(kitchen, "Bread", counted_as="count")
    answer = {"kind": "size", "food_id": bread["id"], "name": "20", "amount": 20}
    response = kitchen.post(
        f"{API}/stock",
        json={
            "food_id": bread["id"],
            "amount": {"amount": 1, "unit": "loaf", "answers": [answer]},
        },
    )
    assert response.status_code == 422
    assert "Give the size a name" in response.text


def test_guess_how_a_new_ingredient_is_counted(kitchen: TestClient) -> None:
    known = kitchen.get(f"{API}/foods/guess", params={"name": "Onion"}).json()
    assert known["from_table"] is True
    unknown = kitchen.get(f"{API}/foods/guess", params={"name": "Zzyzx blorp"}).json()
    assert unknown == {"counted_as": "weight", "from_table": False}


def test_guess_counts_lemons_onions_and_eggs_one_by_one_even_with_words_before(
    kitchen: TestClient,
) -> None:
    # F195: "Alpha2 lemons" was guessed by weight, though lemons, onions and eggs are the New
    # ingredient box's own examples of One by one.
    for name in (
        "lemons",
        "Lemon",
        "Alpha2 lemons",
        "Unwaxed lemons",
        "Red onions",
        "Spring onions",
        "Free range eggs",
        "Large eggs",
    ):
        answer = kitchen.get(f"{API}/foods/guess", params={"name": name}).json()
        assert answer == {"counted_as": "count", "from_table": True}, name


def test_guess_goes_by_the_last_words_not_the_first(kitchen: TestClient) -> None:
    # Mango chutney is not a mango, and lemon juice is its own row (by volume).
    chutney = kitchen.get(f"{API}/foods/guess", params={"name": "Mango chutney"}).json()
    assert chutney["counted_as"] != "count"
    juice = kitchen.get(f"{API}/foods/guess", params={"name": "Fresh lemon juice"}).json()
    assert juice["counted_as"] == "volume"


def test_guess_skips_names_of_several_things(kitchen: TestClient) -> None:
    # Review: "and", "of" and "with" mean the last word is not the whole ingredient.
    for name in ("Cheese and onion", "Bag of onions", "Eggs with bacon", "Lemon and herb"):
        answer = kitchen.get(f"{API}/foods/guess", params={"name": name}).json()
        assert answer["counted_as"] != "count" or answer["from_table"] is False, name
    # Still matched: a name that only ends in a counted ingredient.
    for name in ("Unwaxed lemons", "Free range eggs", "Red onions"):
        answer = kitchen.get(f"{API}/foods/guess", params={"name": name}).json()
        assert answer == {"counted_as": "count", "from_table": True}, name


def test_guess_needs_sign_in(client: TestClient) -> None:
    assert client.get(f"{API}/foods/guess", params={"name": "Onion"}).status_code == 401
