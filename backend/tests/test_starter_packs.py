"""Starter ingredient packs (0.8, R4; cabledrawer 7 Nov): the seven packs, adding a pack with
some items unticked, "Already have" by name or other name, one Undo, staples, and what each
new ingredient comes with."""

from collections.abc import Iterator
from typing import Any

import pytest
from fastapi.testclient import TestClient

from mealwright import starter_packs
from mealwright.auth import hash_password
from mealwright.household import add_default_places
from mealwright.models import Household, Login
from mealwright.pack_sizes import table as pack_table

API = "/api/v1"
NEIGHBOUR = {"username": "neighbour", "password": "next door's own password"}


@pytest.fixture
def neighbour(kitchen: TestClient) -> Iterator[TestClient]:
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
        yield other


def packs(client: TestClient) -> dict[str, dict[str, Any]]:
    response = client.get(f"{API}/starter-packs")
    assert response.status_code == 200, response.text
    return {pack["id"]: pack for pack in response.json()["packs"]}


def keys(pack: dict[str, Any]) -> list[str]:
    return [item["key"] for item in pack["items"]]


def add(client: TestClient, pack_id: str, chosen: list[str], **kw: Any) -> Any:
    return client.post(f"{API}/starter-packs/{pack_id}/add", json={"keys": chosen}, **kw)


def food_named(client: TestClient, name: str) -> dict[str, Any] | None:
    for food in client.get(f"{API}/foods", params={"limit": 500}).json()["foods"]:
        if food["name"] == name:
            found: dict[str, Any] = client.get(f"{API}/foods/{food['id']}").json()
            return found
    return None


def test_every_key_in_the_packs_file_is_in_the_pack_size_table() -> None:
    rows = pack_table().rows
    assert starter_packs.items()
    assert [item.key for item in starter_packs.items() if item.key not in rows] == []
    # Each item is found again by its own name, so its sizes and shop come from its own row.
    for item in starter_packs.items():
        matched = pack_table().match(item.name)
        assert matched is not None and matched.key == item.key, item.key


def test_the_seven_packs_list_in_order_with_their_items(kitchen: TestClient) -> None:
    listed = packs(kitchen)
    assert [p["name"] for p in listed.values()] == [
        "Everyday basics",
        "Indian",
        "Chinese",
        "Japanese",
        "Middle Eastern",
        "Household",
        "Baking",
    ]
    assert all(p["items"] and p["already_have"] == 0 for p in listed.values())
    assert any(i["name"] == "toor dal" for i in listed["indian"]["items"])
    assert all(i["staple"] for i in listed["household"]["items"])
    assert not any(i["staple"] for i in listed["baking"]["items"])


def test_adding_with_two_unticked_adds_the_rest_as_one_change(kitchen: TestClient) -> None:
    chosen = keys(packs(kitchen)["indian"])
    left_out = chosen[:2]
    response = add(kitchen, "indian", chosen[2:])
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["added"] == len(chosen) - 2
    assert body["skipped"] == 0
    assert body["change"]["summary"] == (
        f"Added the Indian starter pack: {len(chosen) - 2} ingredients"
    )
    assert body["change"]["can_undo"] is True
    names = {f["name"] for f in kitchen.get(f"{API}/foods", params={"limit": 500}).json()["foods"]}
    by_key = {item.key: item.name for item in starter_packs.items()}
    assert by_key[chosen[2]] in names
    assert not any(by_key[key] in names for key in left_out)
    after = packs(kitchen)["indian"]
    assert after["already_have"] == len(chosen) - 2


def test_the_change_shows_once_in_recent_changes(kitchen: TestClient) -> None:
    chosen = keys(packs(kitchen)["baking"])
    add(kitchen, "baking", chosen)
    rows = kitchen.get(f"{API}/changes", params={"area": "ingredients"}).json()["changes"]
    mine = [r for r in rows if "starter pack" in r["summary"]]
    assert [r["summary"] for r in mine] == [
        f"Added the Baking starter pack: {len(chosen)} ingredients"
    ]


def test_one_undo_removes_the_whole_addition(kitchen: TestClient) -> None:
    chosen = keys(packs(kitchen)["chinese"])
    body = add(kitchen, "chinese", chosen).json()
    assert packs(kitchen)["chinese"]["already_have"] == len(chosen)
    undo = kitchen.post(f"{API}/changes/{body['change']['id']}/undo")
    assert undo.status_code == 200, undo.text
    assert packs(kitchen)["chinese"]["already_have"] == 0
    listed = kitchen.get(f"{API}/foods", params={"limit": 500}).json()["foods"]
    assert listed == []


def test_an_ingredient_there_by_its_other_name_is_skipped(kitchen: TestClient) -> None:
    # "Thuvaram paruppu" is one of toor dal's other names in the table.
    toor = pack_table().rows["toor_dal"]
    other = next(n for n in toor.names if n.lower() != "toor dal")
    assert kitchen.post(f"{API}/foods", json={"name": other}).status_code == 201
    indian = packs(kitchen)["indian"]
    item = next(i for i in indian["items"] if i["key"] == "toor_dal")
    assert item["already_have"] is True
    assert item["have_as"] == other
    body = add(kitchen, "indian", keys(indian)).json()
    assert body["skipped"] >= 1
    assert body["added"] == len(indian["items"]) - body["skipped"]
    assert food_named(kitchen, "toor dal") is None


def test_an_ingredient_there_by_its_own_name_is_skipped(kitchen: TestClient) -> None:
    kitchen.post(f"{API}/foods", json={"name": "Plain flour"})
    baking = packs(kitchen)["baking"]
    item = next(i for i in baking["items"] if i["key"] == "plain_flour")
    assert item["already_have"] is True and item["have_as"] is None
    body = add(kitchen, "baking", keys(baking)).json()
    assert body["added"] == len(baking["items"]) - 1 and body["skipped"] == 1


def test_adding_a_pack_twice_has_nothing_new_the_second_time(kitchen: TestClient) -> None:
    chosen = keys(packs(kitchen)["japanese"])
    assert add(kitchen, "japanese", chosen).status_code == 201
    again = add(kitchen, "japanese", chosen)
    assert again.status_code == 422
    assert again.json()["code"] == "nothing_to_add"


def test_a_key_from_another_pack_or_none_at_all_is_refused(kitchen: TestClient) -> None:
    baking = packs(kitchen)["baking"]
    other = next(
        i["key"] for i in packs(kitchen)["indian"]["items"] if i["key"] not in keys(baking)
    )
    refused = add(kitchen, "baking", [other])
    assert refused.status_code == 422 and refused.json()["code"] == "not_in_pack"
    assert add(kitchen, "baking", []).json()["code"] == "nothing_to_add"
    assert add(kitchen, "no-such-pack", []).status_code == 404


def test_household_items_come_in_as_staples(kitchen: TestClient) -> None:
    household = packs(kitchen)["household"]
    assert add(kitchen, "household", keys(household)).status_code == 201
    first = household["items"][0]["name"]
    food = food_named(kitchen, first)
    assert food is not None and food["staple"] is True
    # A staple is not bought by a pack, so it has no pack sizes to suggest.
    assert food["pack_suggestions"] == []


def test_each_new_ingredient_comes_with_its_counting_aisle_sizes_shop_and_names(
    kitchen: TestClient,
) -> None:
    indian = kitchen.post(f"{API}/shops", json={"name": "Indian grocer"}).json()["id"]
    assert add(kitchen, "indian", ["toor_dal", "ghee", "idli_rice"]).status_code == 201
    ghee = food_named(kitchen, "ghee")
    assert ghee is not None
    assert ghee["counted_as"] == "weight"
    assert ghee["aisle"] == "tins_jars"  # the food-conversions aisle
    assert ghee["shop"]["id"] == indian  # a world-aisle ingredient with a cuisine → that shop
    assert ghee["pack_suggestions"][0]["pack"] == "jar"  # the usual sizes (suggested)
    assert {n["name"] for n in ghee["other_names"]} == {"clarified butter", "nei"}
    assert not ghee["staple"]
    # Not in the conversion table: counted as its pack sizes are, aisle Other.
    dal = food_named(kitchen, "toor dal")
    assert dal is not None and dal["counted_as"] == "weight" and dal["aisle"] == "other"
    assert dal["shop"]["id"] == indian
    row = pack_table().rows["toor_dal"]
    assert {n["name"].lower() for n in dal["other_names"]} >= {
        n.lower() for n in row.names if n.lower() != "toor dal"
    }


def test_it_adds_ingredients_only(kitchen: TestClient) -> None:
    add(kitchen, "everyday-basics", keys(packs(kitchen)["everyday-basics"]))
    pantry = kitchen.get(f"{API}/pantry").json()
    assert pantry["counts"]["items"] == 0 and pantry["counts"]["tubs"] == 0
    lists = kitchen.get(f"{API}/shopping/lists").json()
    assert all(not row.get("items") for row in lists["lists"])


def test_the_same_change_id_twice_adds_once(kitchen: TestClient) -> None:
    chosen = keys(packs(kitchen)["japanese"])
    first = add(kitchen, "japanese", chosen, headers={"Idempotency-Key": "pack-1"})
    second = add(kitchen, "japanese", chosen, headers={"Idempotency-Key": "pack-1"})
    assert first.status_code == 201
    assert second.status_code == 200
    assert second.headers["Idempotent-Replayed"] == "true"
    assert second.json()["change"]["id"] == first.json()["change"]["id"]
    assert second.json()["added"] == first.json()["added"]


def test_another_household_neither_sees_nor_is_skipped_by_these(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    chosen = keys(packs(kitchen)["baking"])
    add(kitchen, "baking", chosen)
    assert packs(neighbour)["baking"]["already_have"] == 0
    assert add(neighbour, "baking", chosen).json()["added"] == len(chosen)
    # Undoing one household's change is not the other's to do.
    mine = kitchen.get(f"{API}/changes").json()["changes"][0]
    assert neighbour.post(f"{API}/changes/{mine['id']}/undo").status_code == 404


def test_what_is_there_already_is_read_under_the_household_lock(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two phones adding at once: each must see what the other added (review r1 L1)."""
    from mealwright.api.v1 import starter_packs as api
    from mealwright.shopping import LOCKED

    seen: list[bool] = []
    real = api._have

    def watched(k: Any) -> Any:
        seen.append(k.db.info.get(LOCKED) is not None)
        return real(k)

    pack = packs(kitchen)["baking"]
    monkeypatch.setattr(api, "_have", watched)
    assert add(kitchen, "baking", keys(pack)[:1]).status_code == 201
    assert seen == [True]
