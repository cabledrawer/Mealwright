"""The Pantry: adding, using, binning, freezing and moving stock, Use soon, and Undo."""

from datetime import date, timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

API = "/api/v1"


def food(kitchen: TestClient, name: str, **extra: Any) -> dict[str, Any]:
    response = kitchen.post(f"{API}/foods", json={"name": name, **extra})
    assert response.status_code == 201, response.text
    found: dict[str, Any] = response.json()["food"]
    return found


def size(kitchen: TestClient, food_id: int, name: str, amount: float) -> None:
    response = kitchen.post(f"{API}/foods/{food_id}/sizes", json={"name": name, "amount": amount})
    assert response.status_code == 201, response.text


def add(kitchen: TestClient, food_id: int, amount: float, unit: str, **extra: Any) -> Any:
    body = {"food_id": food_id, "amount": {"amount": amount, "unit": unit}, **extra}
    response = kitchen.post(f"{API}/stock", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def place(kitchen: TestClient, name: str) -> int:
    return next(p["id"] for p in kitchen.get(f"{API}/places").json() if p["name"] == name)


def today(kitchen: TestClient) -> date:
    return date.fromisoformat(kitchen.get(f"{API}/household").json()["today"])


def pantry(kitchen: TestClient, **params: str) -> Any:
    return kitchen.get(f"{API}/pantry", params=params).json()


def group(kitchen: TestClient, name: str) -> dict[str, Any]:
    for found in pantry(kitchen)["places"]:
        for item in found["groups"]:
            if item["food"]["name"] == name:
                result: dict[str, Any] = item
                return result
    raise AssertionError(f"{name} not in the pantry")


@pytest.fixture
def toor(kitchen: TestClient) -> dict[str, Any]:
    found = food(kitchen, "Toor dal")
    size(kitchen, found["id"], "packet", 500)
    return found


# --- Adding ---------------------------------------------------------------------------------


def test_two_packets_make_two_lots(kitchen: TestClient, toor: dict[str, Any]) -> None:
    body = add(kitchen, toor["id"], 2, "packets")
    assert body["change"]["summary"] == "Added 2\u00a0packets Toor dal → Cupboard"
    [made] = body["groups"]
    assert made["place"]["name"] == "Cupboard"  # no usual place: Cupboard
    assert made["stock"]["display"] == "2\u00a0packets · 1\u00a0kg"
    assert made["lots_count"] == 2
    assert [lot["stock"]["display"] for lot in made["lots"]] == ["1\u00a0packet · 500\u00a0g"] * 2


def test_half_a_packet_and_typed_grams(kitchen: TestClient, toor: dict[str, Any]) -> None:
    body = add(kitchen, toor["id"], 1.5, "packet")
    assert [lot["stock"]["amount"] for lot in body["groups"][0]["lots"]] == [500.0, 250.0]
    assert body["groups"][0]["stock"]["display"] == "1½\u00a0packets · about 750\u00a0g"
    body = add(kitchen, toor["id"], 200, "g")
    assert body["groups"][0]["stock"]["display"] == "2\u00a0packets · about 950\u00a0g"
    assert body["groups"][0]["lots"][-1]["size_id"] is None  # typed grams: no size


def test_goes_to_the_usual_place(kitchen: TestClient) -> None:
    paneer = food(kitchen, "Paneer", place_id=place(kitchen, "Fridge"))
    body = add(kitchen, paneer["id"], 200, "g", use_by="2030-01-01")
    assert body["groups"][0]["place"]["name"] == "Fridge"
    assert body["groups"][0]["use_by"] == "2030-01-01"


def test_staples_are_not_counted(kitchen: TestClient) -> None:
    salt = food(kitchen, "Salt", staple=True)
    response = kitchen.post(
        f"{API}/stock", json={"food_id": salt["id"], "amount": {"amount": 1, "unit": "kg"}}
    )
    assert response.status_code == 409
    assert response.json()["code"] == "staple"


def test_eggs_by_the_dozen(kitchen: TestClient) -> None:
    eggs = food(kitchen, "Eggs")
    size(kitchen, eggs["id"], "dozen", 12)
    add(kitchen, eggs["id"], 1, "dozen")
    kitchen.post(f"{API}/foods/{eggs['id']}/used", json={"amount": {"amount": 3, "unit": "count"}})
    assert group(kitchen, "Eggs")["stock"]["display"] == "9\u00a0left · bought as a dozen"


def test_cups_need_a_weight(kitchen: TestClient, toor: dict[str, Any]) -> None:
    response = kitchen.post(
        f"{API}/stock", json={"food_id": toor["id"], "amount": {"amount": 1, "unit": "cup"}}
    )
    assert response.status_code == 409
    assert response.json()["ask"]["kind"] == "weight_per_ml"


# --- Using, binning, what's left ------------------------------------------------------------


def test_set_left_with_quick_picks(kitchen: TestClient, toor: dict[str, Any]) -> None:
    lot = add(kitchen, toor["id"], 1, "packet")["groups"][0]["lots"][0]
    body = kitchen.post(f"{API}/stock/{lot['id']}/left", json={"fraction": 0.5}).json()
    assert body["groups"][0]["lots"][0]["stock"]["display"] == "½\u00a0packet · about 250\u00a0g"
    assert body["groups"][0]["lots"][0]["open"] is True
    assert body["change"]["summary"] == "Toor dal: 1\u00a0packet → about ½\u00a0packet"
    body = kitchen.post(f"{API}/stock/{lot['id']}/left", json={"fraction": 1}).json()
    assert body["groups"][0]["lots"][0]["open"] is False
    body = kitchen.post(
        f"{API}/stock/{lot['id']}/left", json={"amount": {"amount": 120, "unit": "g"}}
    ).json()
    assert body["groups"][0]["stock"]["amount"] == 120.0


def test_fraction_needs_a_size(kitchen: TestClient) -> None:
    spinach = food(kitchen, "Spinach")
    lot = add(kitchen, spinach["id"], 200, "g")["groups"][0]["lots"][0]
    response = kitchen.post(f"{API}/stock/{lot['id']}/left", json={"fraction": 0.5})
    assert response.status_code == 422


def test_used_never_below_zero(kitchen: TestClient) -> None:
    spinach = food(kitchen, "Spinach")
    lot = add(kitchen, spinach["id"], 200, "g")["groups"][0]["lots"][0]
    body = kitchen.post(
        f"{API}/stock/{lot['id']}/used", json={"amount": {"amount": 300, "unit": "g"}}
    ).json()
    assert body["groups"][0]["stock"]["amount"] == 0.0
    assert body["groups"][0]["lots"] == []
    assert body["short_by"]["amount"] == 100.0
    assert body["change"]["summary"] == "Used 200\u00a0g Spinach"
    assert kitchen.post(f"{API}/stock/{lot['id']}/used").status_code == 404  # empty now


def test_used_all_and_binned(kitchen: TestClient, toor: dict[str, Any]) -> None:
    lots = add(kitchen, toor["id"], 2, "packet")["groups"][0]["lots"]
    body = kitchen.post(f"{API}/stock/{lots[0]['id']}/used").json()
    assert body["change"]["summary"] == "Used 1\u00a0packet Toor dal"
    body = kitchen.post(f"{API}/stock/{lots[1]['id']}/binned").json()
    assert body["change"]["kind"] == "binned"
    assert body["groups"][0]["lots_count"] == 0


def test_food_used_takes_the_oldest_first(kitchen: TestClient) -> None:
    milk = food(kitchen, "Milk")
    size(kitchen, milk["id"], "bottle", 1000)
    day = today(kitchen)
    later = add(kitchen, milk["id"], 1, "bottle", use_by=str(day + timedelta(days=5)))
    sooner = add(kitchen, milk["id"], 1, "bottle", use_by=str(day + timedelta(days=2)))
    body = kitchen.post(
        f"{API}/foods/{milk['id']}/used", json={"amount": {"amount": 1.5, "unit": "l"}}
    ).json()
    by_id = {lot["id"]: lot["stock"]["amount"] for lot in body["groups"][0]["lots"]}
    sooner_id = sooner["groups"][0]["lots"][0]["id"]
    assert sooner_id not in by_id  # used up first
    assert by_id[later["groups"][0]["lots"][-1]["id"]] == 500.0


def test_food_used_leaves_the_freezer_alone(kitchen: TestClient) -> None:
    peas = food(kitchen, "Garden peas")
    add(kitchen, peas["id"], 300, "g", place_id=place(kitchen, "Freezer"))
    add(kitchen, peas["id"], 100, "g", place_id=place(kitchen, "Fridge"))
    body = kitchen.post(
        f"{API}/foods/{peas['id']}/used", json={"amount": {"amount": 250, "unit": "g"}}
    ).json()
    assert body["short_by"]["amount"] == 150.0
    freezer = kitchen.post(
        f"{API}/foods/{peas['id']}/used",
        json={"amount": {"amount": 100, "unit": "g"}, "place_id": place(kitchen, "Freezer")},
    ).json()
    assert freezer["groups"][0]["stock"]["amount"] == 200.0


def test_food_left_down_and_up(kitchen: TestClient) -> None:
    onion = food(kitchen, "Onion")
    add(kitchen, onion["id"], 5, "count")
    url = f"{API}/foods/{onion['id']}/left"
    body = kitchen.post(url, json={"amount": {"amount": 3, "unit": "count"}}).json()
    assert body["groups"][0]["stock"]["display"] == "3\u00a0left"
    assert body["change"]["summary"] == "Onion: 5 → 3"
    body = kitchen.post(url, json={"amount": {"amount": 4, "unit": "count"}}).json()
    assert body["groups"][0]["stock"]["amount"] == 4.0
    same = kitchen.post(url, json={"amount": {"amount": 4, "unit": "count"}})
    assert same.status_code == 409


# --- Freezer, moving, dates -------------------------------------------------------------------


def test_to_freezer(kitchen: TestClient) -> None:
    paneer = food(kitchen, "Paneer", place_id=place(kitchen, "Fridge"))
    lot = add(kitchen, paneer["id"], 200, "g")["groups"][0]["lots"][0]
    body = kitchen.post(f"{API}/stock/{lot['id']}/to-freezer").json()
    day = today(kitchen)
    month = (day.month + 2) % 12 + 1
    year = day.year + (day.month + 2) // 12
    frozen = next(g for g in body["groups"] if g["place"]["name"] == "Freezer")
    assert frozen["lots"][0]["frozen_on"] == str(day)
    assert date.fromisoformat(frozen["use_by"]).replace(day=1) == date(year, month, 1)
    assert body["change"]["summary"].startswith("Paneer → Freezer, use by ")
    fridge = next(g for g in body["groups"] if g["place"]["name"] == "Fridge")
    assert fridge["lots"] == []
    again = kitchen.post(f"{API}/stock/{lot['id']}/to-freezer")
    assert again.status_code == 409


def test_move_and_use_by(kitchen: TestClient) -> None:
    spinach = food(kitchen, "Spinach")
    lot = add(kitchen, spinach["id"], 200, "g")["groups"][0]["lots"][0]
    body = kitchen.post(
        f"{API}/stock/{lot['id']}/move", json={"place_id": place(kitchen, "Fridge")}
    ).json()
    assert body["change"]["summary"] == "Moved Spinach → Fridge"
    body = kitchen.patch(f"{API}/stock/{lot['id']}", json={"use_by": "2030-03-04"}).json()
    assert body["change"]["summary"] == "Spinach: use by 4 Mar"
    assert body["groups"][0]["use_by"] == "2030-03-04"


# --- The Pantry screen ----------------------------------------------------------------------------


def test_pantry_groups_by_place(kitchen: TestClient, toor: dict[str, Any]) -> None:
    day = today(kitchen)
    paneer = food(kitchen, "Paneer", place_id=place(kitchen, "Fridge"))
    size(kitchen, paneer["id"], "pack", 200)
    add(kitchen, paneer["id"], 1, "pack", use_by=str(day + timedelta(days=1)))
    add(kitchen, paneer["id"], 1, "pack", use_by=str(day + timedelta(days=6)))
    add(kitchen, toor["id"], 1, "packet")
    food(kitchen, "Salt", staple=True)

    shown = pantry(kitchen)
    assert [p["name"] for p in shown["places"]] == ["Fridge", "Freezer", "Cupboard", "Spice rack"]
    fridge = shown["places"][0]
    assert fridge["items"] == 1
    paneer_group = fridge["groups"][0]
    assert paneer_group["stock"]["display"] == "2\u00a0packs · 400\u00a0g"
    assert paneer_group["dates_count"] == 2
    assert paneer_group["days_left"] == 1
    assert paneer_group["use_soon"] is True
    assert [lot["days_left"] for lot in paneer_group["lots"]] == [1, 6]  # oldest first
    assert shown["counts"] == {"items": 2, "tubs": 0, "use_soon": 1, "running_low": 0}
    assert [s["name"] for s in shown["staples"]] == ["Salt"]
    assert pantry(kitchen, filter="staples")["places"][0]["groups"] == []
    assert pantry(kitchen, filter="use_soon")["places"][2]["groups"] == []


def test_running_low(kitchen: TestClient, toor: dict[str, Any]) -> None:
    kitchen.patch(
        f"{API}/foods/{toor['id']}", json={"running_low_at": {"amount": 0.5, "unit": "packet"}}
    )
    lot = add(kitchen, toor["id"], 1, "packet")["groups"][0]["lots"][0]
    assert group(kitchen, "Toor dal")["running_low"] is False
    kitchen.post(f"{API}/stock/{lot['id']}/left", json={"fraction": 0.5})
    assert group(kitchen, "Toor dal")["running_low"] is True
    low = pantry(kitchen, filter="running_low")
    assert low["counts"]["running_low"] == 1
    assert low["places"][2]["groups"][0]["food"]["name"] == "Toor dal"


def test_use_soon_is_two_days_in_the_households_time_zone(kitchen: TestClient) -> None:
    kitchen.post(f"{API}/household/from-browser", json={"time_zone": "Pacific/Kiritimati"})
    day = today(kitchen)  # UTC+14: often already tomorrow in UTC terms
    spinach = food(kitchen, "Spinach")
    for days in (-1, 0, 1, 2, 3):
        add(kitchen, spinach["id"], 100, "g", use_by=str(day + timedelta(days=days)))
    soon = kitchen.get(f"{API}/pantry/use-soon").json()
    assert soon["today"] == str(day)
    assert [lot["days_left"] for lot in soon["lots"]] == [-1, 0, 1, 2]
    assert [(lot["position"], lot["of"]) for lot in soon["lots"]] == [
        (1, 5),
        (2, 5),
        (3, 5),
        (4, 5),
    ]


def test_editor_shows_the_stock(kitchen: TestClient, toor: dict[str, Any]) -> None:
    add(kitchen, toor["id"], 1.5, "packet")
    shown = kitchen.get(f"{API}/foods/{toor['id']}").json()
    assert shown["stock"]["display"] == "1½\u00a0packets · about 750\u00a0g"


def test_cannot_remove_a_food_with_stock(kitchen: TestClient, toor: dict[str, Any]) -> None:
    add(kitchen, toor["id"], 1, "packet")
    response = kitchen.delete(f"{API}/foods/{toor['id']}")
    assert response.status_code == 409
    assert response.json()["code"] == "in_use"


# --- Recent changes and Undo ------------------------------------------------------------------


def test_recent_changes_for_the_pantry(kitchen: TestClient, toor: dict[str, Any]) -> None:
    lot = add(kitchen, toor["id"], 1, "packet")["groups"][0]["lots"][0]
    kitchen.post(f"{API}/stock/{lot['id']}/left", json={"fraction": 0.5})
    listed = kitchen.get(f"{API}/changes", params={"area": "pantry"}).json()["changes"]
    assert [c["kind"] for c in listed] == ["set_left", "added"]
    [line] = listed[0]["lines"]
    assert line["food"]["name"] == "Toor dal"
    assert line["before"]["display"] == "1\u00a0packet · 500\u00a0g"
    assert line["after"]["display"] == "½\u00a0packet · about 250\u00a0g"
    assert line["place_before"]["name"] == line["place_after"]["name"] == "Cupboard"


def test_undo_used(kitchen: TestClient) -> None:
    spinach = food(kitchen, "Spinach")
    lot = add(kitchen, spinach["id"], 200, "g")["groups"][0]["lots"][0]
    used = kitchen.post(f"{API}/stock/{lot['id']}/used").json()
    body = kitchen.post(f"{API}/changes/{used['change']['id']}/undo").json()
    assert body["result"] == "done"
    assert body["groups"][0]["stock"]["amount"] == 200.0
    undo_rows = kitchen.get(f"{API}/changes", params={"area": "pantry"}).json()["changes"]
    assert undo_rows[0]["summary"] == "Undid: Used 200\u00a0g Spinach"


def test_undo_reverses_just_that_change(kitchen: TestClient, toor: dict[str, Any]) -> None:
    lot = add(kitchen, toor["id"], 1, "packet")["groups"][0]["lots"][0]
    half = kitchen.post(f"{API}/stock/{lot['id']}/left", json={"fraction": 0.5}).json()
    kitchen.post(f"{API}/stock/{lot['id']}/used", json={"amount": {"amount": 50, "unit": "g"}})
    body = kitchen.post(f"{API}/changes/{half['change']['id']}/undo").json()
    assert body["result"] == "done"
    assert body["groups"][0]["stock"]["amount"] == 450.0  # 500 - 50: the later use stays


def test_undo_partly_when_used_since(kitchen: TestClient, toor: dict[str, Any]) -> None:
    added = add(kitchen, toor["id"], 1, "packet")
    lot = added["groups"][0]["lots"][0]
    kitchen.post(f"{API}/stock/{lot['id']}/left", json={"amount": {"amount": 150, "unit": "g"}})
    body = kitchen.post(f"{API}/changes/{added['change']['id']}/undo").json()
    assert body["result"] == "partly"
    assert (
        body["message"] == "Took back 150\u00a0g of the 500\u00a0g: the rest has been used since."
    )
    assert body["groups"][0]["stock"]["amount"] == 0.0


def test_undo_move_and_freezer(kitchen: TestClient) -> None:
    paneer = food(kitchen, "Paneer", place_id=place(kitchen, "Fridge"))
    lot = add(kitchen, paneer["id"], 200, "g", use_by="2030-01-01")["groups"][0]["lots"][0]
    frozen = kitchen.post(f"{API}/stock/{lot['id']}/to-freezer").json()
    body = kitchen.post(f"{API}/changes/{frozen['change']['id']}/undo").json()
    assert body["result"] == "done"
    back = group(kitchen, "Paneer")
    assert back["place"]["name"] == "Fridge"
    assert back["use_by"] == "2030-01-01"
    assert back["lots"][0]["frozen_on"] is None


def test_undo_move_after_moving_again_is_nothing(kitchen: TestClient) -> None:
    spinach = food(kitchen, "Spinach")
    lot = add(kitchen, spinach["id"], 200, "g")["groups"][0]["lots"][0]
    moved = kitchen.post(
        f"{API}/stock/{lot['id']}/move", json={"place_id": place(kitchen, "Fridge")}
    ).json()
    kitchen.post(f"{API}/stock/{lot['id']}/move", json={"place_id": place(kitchen, "Freezer")})
    body = kitchen.post(f"{API}/changes/{moved['change']['id']}/undo").json()
    assert body["result"] == "nothing"
    assert group(kitchen, "Spinach")["place"]["name"] == "Freezer"


def test_retried_add_is_not_added_twice(kitchen: TestClient, toor: dict[str, Any]) -> None:
    body = {"food_id": toor["id"], "amount": {"amount": 1, "unit": "packet"}}
    headers = {"Idempotency-Key": "add-toor-1"}
    first = kitchen.post(f"{API}/stock", json=body, headers=headers)
    again = kitchen.post(f"{API}/stock", json=body, headers=headers)
    assert (first.status_code, again.status_code) == (201, 200)
    assert again.json()["change"]["id"] == first.json()["change"]["id"]
    assert group(kitchen, "Toor dal")["lots_count"] == 1


# --- Merging and counting differently, with stock ---------------------------------------------


def test_merge_moves_stock_and_undo_brings_it_back(kitchen: TestClient) -> None:
    moringa = food(kitchen, "Moringa", counted_as="weight")
    drumsticks = food(kitchen, "Drumsticks", counted_as="weight")
    add(kitchen, moringa["id"], 300, "g")
    merged = kitchen.post(
        f"{API}/foods/{moringa['id']}/merge", json={"into_id": drumsticks["id"]}
    ).json()
    assert merged["food"]["stock"]["amount"] == 300.0
    assert group(kitchen, "Drumsticks")["stock"]["amount"] == 300.0
    lot_id = group(kitchen, "Drumsticks")["lots"][0]["id"]
    kitchen.post(f"{API}/stock/{lot_id}/used", json={"amount": {"amount": 100, "unit": "g"}})
    body = kitchen.post(f"{API}/changes/{merged['change']['id']}/undo").json()
    assert body["result"] == "done"
    assert group(kitchen, "Moringa")["stock"]["amount"] == 200.0  # what's left comes back


def test_merge_converts_stock(kitchen: TestClient) -> None:
    onion = food(kitchen, "Onion")  # counted by number, 110 g each in the table
    small = food(kitchen, "Small onions", counted_as="weight")
    add(kitchen, small["id"], 330, "g")
    merged = kitchen.post(f"{API}/foods/{small['id']}/merge", json={"into_id": onion["id"]}).json()
    assert merged["food"]["stock"]["display"] == "3\u00a0left"
    kitchen.post(f"{API}/changes/{merged['change']['id']}/undo")
    assert group(kitchen, "Small onions")["stock"]["amount"] == 330.0


def test_counting_differently_converts_stock(kitchen: TestClient, toor: dict[str, Any]) -> None:
    add(kitchen, toor["id"], 1, "packet")
    answer = {"kind": "weight_per_ml", "food_id": toor["id"], "grams": 200}
    changed = kitchen.patch(
        f"{API}/foods/{toor['id']}", json={"counted_as": "volume", "answers": [answer]}
    ).json()
    assert changed["food"]["stock"]["amount"] == 625.0
    kitchen.post(f"{API}/changes/{changed['change']['id']}/undo")
    assert group(kitchen, "Toor dal")["stock"]["amount"] == 500.0


def test_used_with_nothing_left_records_nothing(kitchen: TestClient) -> None:
    ghee = food(kitchen, "Ghee")
    add(kitchen, ghee["id"], 500, "g", place_id=place(kitchen, "Freezer"))
    response = kitchen.post(
        f"{API}/foods/{ghee['id']}/used", json={"amount": {"amount": 50, "unit": "g"}}
    )
    assert response.status_code == 409
    assert response.json() == {"detail": "There's no Ghee left.", "code": "nothing_left"}
    kinds = [
        c["kind"]
        for c in kitchen.get(f"{API}/changes", params={"area": "pantry"}).json()["changes"]
    ]
    assert kinds == ["added"]


def test_none_left(kitchen: TestClient) -> None:
    onion = food(kitchen, "Onion")
    add(kitchen, onion["id"], 3, "count")
    add(kitchen, onion["id"], 2, "count")
    add(kitchen, onion["id"], 4, "count", place_id=place(kitchen, "Freezer"))
    body = kitchen.post(
        f"{API}/foods/{onion['id']}/left", json={"amount": {"amount": 0, "unit": "count"}}
    ).json()
    assert body["change"]["summary"] == "Onion: 5 → 0"
    assert body["groups"][0]["lots"] == []
    assert group(kitchen, "Onion")["place"]["name"] == "Freezer"  # the freezer is left alone
    undo = kitchen.post(f"{API}/changes/{body['change']['id']}/undo").json()
    assert undo["result"] == "done"
    assert kitchen.get(f"{API}/foods/{onion['id']}").json()["stock"]["amount"] == 9.0


def test_an_undo_has_lines_of_what_it_put_back(kitchen: TestClient, toor: dict[str, Any]) -> None:
    added = add(kitchen, toor["id"], 1, "packet")
    lot = added["groups"][0]["lots"][0]
    kitchen.post(f"{API}/stock/{lot['id']}/left", json={"amount": {"amount": 150, "unit": "g"}})
    undo = kitchen.post(f"{API}/changes/{added['change']['id']}/undo").json()
    assert undo["result"] == "partly"
    rows = kitchen.get(f"{API}/changes", params={"area": "pantry"}).json()["changes"]
    assert rows[0]["kind"] == "undo"
    [line] = rows[0]["lines"]
    # Only what it actually took back: 150 g → 0, not 500 g.
    assert (line["before"]["amount"], line["after"]["amount"]) == (150.0, 0.0)
    assert line["lot_id"] == lot["id"]


def test_an_undo_of_a_move_has_lines(kitchen: TestClient) -> None:
    spinach = food(kitchen, "Spinach")
    lot = add(kitchen, spinach["id"], 200, "g")["groups"][0]["lots"][0]
    moved = kitchen.post(
        f"{API}/stock/{lot['id']}/move", json={"place_id": place(kitchen, "Fridge")}
    ).json()
    kitchen.post(f"{API}/changes/{moved['change']['id']}/undo")
    row = kitchen.get(f"{API}/changes", params={"area": "pantry"}).json()["changes"][0]
    [line] = row["lines"]
    assert (line["place_before"]["name"], line["place_after"]["name"]) == ("Fridge", "Cupboard")
    assert line["before"]["amount"] == line["after"]["amount"] == 200.0


def test_names_appear_exactly_as_typed(kitchen: TestClient) -> None:
    masala = food(kitchen, "MDH sambar masala")
    size(kitchen, masala["id"], "box", 100)
    lot = add(kitchen, masala["id"], 1, "box")
    assert lot["change"]["summary"] == "Added 1\u00a0box MDH sambar masala → Cupboard"
    lot_id = lot["groups"][0]["lots"][0]["id"]
    used = kitchen.post(f"{API}/stock/{lot_id}/used").json()
    assert used["change"]["summary"] == "Used 1\u00a0box MDH sambar masala"
    empty = kitchen.post(
        f"{API}/foods/{masala['id']}/used", json={"amount": {"amount": 5, "unit": "g"}}
    )
    assert empty.json()["detail"] == "There's no MDH sambar masala left."
    asked = kitchen.post(
        f"{API}/stock", json={"food_id": masala["id"], "amount": {"amount": 1, "unit": "tbsp"}}
    ).json()
    assert asked["ask"]["question"] == "About how much does 1\u00a0cup of MDH sambar masala weigh?"
    summaries = [c["summary"] for c in kitchen.get(f"{API}/changes").json()["changes"]]
    assert not any("mdh" in summary for summary in summaries)


def _totals(kitchen: TestClient) -> list[dict[str, Any]]:
    row = kitchen.get(f"{API}/changes", params={"area": "pantry"}).json()["changes"][0]
    totals: list[dict[str, Any]] = row["totals"]
    return totals


def test_recent_changes_totals_two_packets(kitchen: TestClient) -> None:
    paneer = food(kitchen, "Paneer", place_id=place(kitchen, "Fridge"))
    size(kitchen, paneer["id"], "pack", 200)
    add(kitchen, paneer["id"], 2, "pack")
    [total] = _totals(kitchen)
    assert total["name"] == "Paneer"
    assert total["place_before"] is None
    assert total["place_after"]["name"] == "Fridge"
    assert (total["before"]["display"], total["after"]["display"]) == (
        "0\u00a0g",
        "2\u00a0packs · 400\u00a0g",
    )


def test_recent_changes_totals_a_move(kitchen: TestClient) -> None:
    spinach = food(kitchen, "Spinach")
    lot = add(kitchen, spinach["id"], 200, "g")["groups"][0]["lots"][0]
    kitchen.post(f"{API}/stock/{lot['id']}/move", json={"place_id": place(kitchen, "Fridge")})
    [total] = _totals(kitchen)
    assert (total["place_before"]["name"], total["place_after"]["name"]) == ("Cupboard", "Fridge")
    assert total["before"]["display"] == total["after"]["display"] == "200\u00a0g"


def test_recent_changes_totals_a_partial_undo(kitchen: TestClient, toor: dict[str, Any]) -> None:
    added = add(kitchen, toor["id"], 2, "packet")
    lot = added["groups"][0]["lots"][0]
    kitchen.post(f"{API}/stock/{lot['id']}/left", json={"amount": {"amount": 100, "unit": "g"}})
    undo = kitchen.post(f"{API}/changes/{added['change']['id']}/undo").json()
    assert undo["result"] == "partly"
    [total] = _totals(kitchen)
    assert total["before"]["display"] == "1¼\u00a0packets · about 600\u00a0g"  # 100 g + 500 g
    assert total["after"]["display"] == "0\u00a0g"


def test_summaries_for_counted_ingredients(kitchen: TestClient) -> None:
    """ "5 left" belongs in the pantry list; a summary says "Added 5 Onion"."""
    onion = food(kitchen, "Onion")
    added = add(kitchen, onion["id"], 5, "count")
    assert added["change"]["summary"] == "Added 5\u00a0Onion → Cupboard"
    lot = added["groups"][0]["lots"][0]["id"]
    used = kitchen.post(
        f"{API}/stock/{lot}/used", json={"amount": {"amount": 2, "unit": "count"}}
    ).json()
    assert used["change"]["summary"] == "Used 2\u00a0Onion"
    binned = kitchen.post(
        f"{API}/stock/{lot}/binned", json={"amount": {"amount": 1, "unit": "count"}}
    ).json()
    assert binned["change"]["summary"] == "Binned 1\u00a0Onion"
    left = kitchen.post(
        f"{API}/foods/{onion['id']}/left", json={"amount": {"amount": 1, "unit": "count"}}
    ).json()
    assert left["change"]["summary"] == "Onion: 2 → 1"
    by_food = kitchen.post(
        f"{API}/foods/{onion['id']}/used", json={"amount": {"amount": 0.5, "unit": "count"}}
    ).json()
    assert by_food["change"]["summary"] == "Used ½\u00a0Onion"

    bread = food(kitchen, "Bread", counted_as="count")
    kitchen.patch(f"{API}/foods/{bread['id']}", json={"count_word": "slice"})
    added = add(kitchen, bread["id"], 5, "count")
    assert added["change"]["summary"] == "Added 5\u00a0slices of Bread → Cupboard"
    lot = added["groups"][0]["lots"][0]["id"]
    used = kitchen.post(
        f"{API}/stock/{lot}/used", json={"amount": {"amount": 1, "unit": "count"}}
    ).json()
    assert used["change"]["summary"] == "Used 1\u00a0slice of Bread"
    left = kitchen.post(
        f"{API}/foods/{bread['id']}/left", json={"amount": {"amount": 2, "unit": "count"}}
    ).json()
    assert left["change"]["summary"] == "Bread: 4\u00a0slices → 2\u00a0slices"
