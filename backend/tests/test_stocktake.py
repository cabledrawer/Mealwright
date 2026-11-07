"""The Stocktake (F118, 0.8): place by place, each answer its own change with Undo, the pack
size asked once, staples, and the progress kept on the server for the household."""

from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select

from mealwright.models import Change, Food, StockLot

API = "/api/v1"
STOCKTAKE = f"{API}/stocktake"


def place(kitchen: TestClient, name: str) -> int:
    return next(p["id"] for p in kitchen.get(f"{API}/places").json() if p["name"] == name)


def food(kitchen: TestClient, name: str, **extra: Any) -> dict[str, Any]:
    response = kitchen.post(f"{API}/foods", json={"name": name, **extra})
    assert response.status_code == 201, response.text
    found: dict[str, Any] = response.json()["food"]
    return found


def packet(kitchen: TestClient, food_id: int, name: str = "bag", amount: float = 1000) -> None:
    response = kitchen.post(f"{API}/foods/{food_id}/sizes", json={"name": name, "amount": amount})
    assert response.status_code == 201, response.text


def add(kitchen: TestClient, food_id: int, amount: float, unit: str, where: int) -> None:
    body = {"food_id": food_id, "amount": {"amount": amount, "unit": unit}, "place_id": where}
    assert kitchen.post(f"{API}/stock", json=body).status_code == 201


def rows(kitchen: TestClient, place_id: int) -> dict[str, Any]:
    response = kitchen.get(f"{STOCKTAKE}/places/{place_id}")
    assert response.status_code == 200, response.text
    return {r["food"]["name"]: r for r in response.json()["rows"]}


def answer(
    kitchen: TestClient, place_id: int, food_id: int, body: dict[str, Any], **kw: Any
) -> Any:
    return kitchen.post(f"{STOCKTAKE}/places/{place_id}/foods/{food_id}/answer", json=body, **kw)


def total(kitchen: TestClient, food_id: int, place_id: int) -> int:
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        return sum(
            lot.amount_milli
            for lot in db.scalars(
                select(StockLot).where(StockLot.food_id == food_id, StockLot.place_id == place_id)
            )
        )


# --- Places and who is in them ------------------------------------------------------------


def test_places_come_in_the_settings_order_and_start_at_the_first(kitchen: TestClient) -> None:
    found = kitchen.get(STOCKTAKE).json()
    names = [p["name"] for p in found["places"]]
    assert names == [p["name"] for p in kitchen.get(f"{API}/places").json()]
    assert found["current_place_id"] == found["places"][0]["id"]
    assert (found["started"], found["complete"]) == (False, False)
    detail = kitchen.get(f"{STOCKTAKE}/places/{found['places'][2]['id']}").json()
    assert (detail["number"], detail["of"]) == (3, len(names))
    assert detail["previous"]["name"] == names[1]
    assert detail["next"]["name"] == names[3]
    first = kitchen.get(f"{STOCKTAKE}/places/{found['places'][0]['id']}").json()
    assert first["previous"] is None


def test_a_place_lists_what_is_kept_there_or_has_stock_there_a_to_z(kitchen: TestClient) -> None:
    cupboard, fridge = place(kitchen, "Cupboard"), place(kitchen, "Fridge")
    food(kitchen, "Toor dal", place_id=cupboard)
    food(kitchen, "Milk", place_id=fridge)
    flour = food(kitchen, "Atta")  # no usual place, but some on a shelf
    add(kitchen, flour["id"], 500, "g", cupboard)
    removed = food(kitchen, "Old tin", place_id=cupboard)
    assert kitchen.delete(f"{API}/foods/{removed['id']}").status_code == 200
    assert list(rows(kitchen, cupboard)) == ["Atta", "Toor dal"]
    assert list(rows(kitchen, fridge)) == ["Milk"]


# --- Answers --------------------------------------------------------------------------------


def test_a_fraction_of_the_pack_is_saved_and_undone(kitchen: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    dal = food(kitchen, "Toor dal", place_id=cupboard)
    packet(kitchen, dal["id"], "bag", 1000)
    before = rows(kitchen, cupboard)["Toor dal"]
    assert before["answered"] is False and before["answer"] is None
    assert before["pack"]["name"] == "bag"
    done = answer(kitchen, cupboard, dal["id"], {"fraction": 0.5})
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["change"]["kind"] == "stocktake"
    assert body["change"]["summary"] == "Stocktake: Toor dal ½\u00a0bag in the Cupboard"
    assert total(kitchen, dal["id"], cupboard) == 500_000
    assert body["row"]["answered"] is True
    assert body["row"]["answer"] == {"fraction": "0.5", "more": 0, "count": None}
    assert (body["answered"], body["total"]) == (1, 1)
    # Undo: the amount is back, and the row is unanswered again.
    undone = kitchen.post(f"{API}/changes/{body['change']['id']}/undo")
    assert undone.status_code == 200, undone.text
    assert total(kitchen, dal["id"], cupboard) == 0
    again = rows(kitchen, cupboard)["Toor dal"]
    assert again["answered"] is False and again["answer"] is None


def test_full_more_packets_and_none(kitchen: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    dal = food(kitchen, "Toor dal", place_id=cupboard)
    packet(kitchen, dal["id"], "bag", 1000)
    full = answer(kitchen, cupboard, dal["id"], {"fraction": 1}).json()
    assert (
        full["row"]["answer"]["fraction"] == "1"
        and total(kitchen, dal["id"], cupboard) == 1_000_000
    )
    # Several packets: the count besides the open one, then its fraction.
    three = answer(kitchen, cupboard, dal["id"], {"fraction": 0.25, "more": 2}).json()
    assert total(kitchen, dal["id"], cupboard) == 2_250_000
    assert three["row"]["answer"] == {"fraction": "0.25", "more": 2, "count": None}
    assert three["change"]["summary"].startswith("Stocktake: Toor dal ")
    two = answer(kitchen, cupboard, dal["id"], {"fraction": 1, "more": 1}).json()
    assert total(kitchen, dal["id"], cupboard) == 2_000_000
    assert two["row"]["answer"] == {"fraction": "1", "more": 1, "count": None}
    none = answer(kitchen, cupboard, dal["id"], {"fraction": 0}).json()
    assert total(kitchen, dal["id"], cupboard) == 0
    assert none["change"]["summary"] == "Stocktake: no Toor dal in the Cupboard"
    assert none["row"]["answer"] == {"fraction": "0", "more": 0, "count": None}


def test_an_answer_that_changes_nothing_has_no_change_but_counts_as_done(
    kitchen: TestClient,
) -> None:
    cupboard = place(kitchen, "Cupboard")
    dal = food(kitchen, "Toor dal", place_id=cupboard)
    body = answer(kitchen, cupboard, dal["id"], {"fraction": 0}).json()
    assert body["change"] is None
    assert (body["answered"], body["total"]) == (1, 1)
    assert body["row"]["answered"] is True


def test_an_answer_only_touches_its_own_place(kitchen: TestClient) -> None:
    cupboard, freezer = place(kitchen, "Cupboard"), place(kitchen, "Freezer")
    peas = food(kitchen, "Peas", place_id=cupboard)
    packet(kitchen, peas["id"], "bag", 500)
    add(kitchen, peas["id"], 500, "g", freezer)
    answer(kitchen, cupboard, peas["id"], {"fraction": 0.5})
    assert total(kitchen, peas["id"], cupboard) == 250_000
    assert total(kitchen, peas["id"], freezer) == 500_000
    answer(kitchen, cupboard, peas["id"], {"fraction": 0})
    assert total(kitchen, peas["id"], freezer) == 500_000
    # And the freezer's row shows its own stock.
    assert rows(kitchen, freezer)["Peas"]["stock"]["amount"] == 500


def test_an_ingredient_counted_one_by_one_takes_a_count(kitchen: TestClient) -> None:
    fridge = place(kitchen, "Fridge")
    eggs = food(kitchen, "Eggs", counted_as="count", place_id=fridge)
    row = rows(kitchen, fridge)["Eggs"]
    assert row["pack"] is None and row["pack_suggestions"] == []
    body = answer(kitchen, fridge, eggs["id"], {"count": 6}).json()
    assert total(kitchen, eggs["id"], fridge) == 6_000
    assert body["row"]["answer"] == {"fraction": None, "more": 0, "count": "6"}
    down = answer(kitchen, fridge, eggs["id"], {"count": 4}).json()
    assert total(kitchen, eggs["id"], fridge) == 4_000
    assert down["change"]["kind"] == "stocktake"
    assert answer(kitchen, fridge, eggs["id"], {"fraction": 0.5}).status_code == 422


def test_a_count_for_a_weighed_ingredient_is_refused(kitchen: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    rice = food(kitchen, "Rice", place_id=cupboard)
    response = answer(kitchen, cupboard, rice["id"], {"count": 2})
    assert (response.status_code, response.json()["code"]) == (422, "not_counted")


def test_only_the_four_picks_are_taken(kitchen: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    rice = food(kitchen, "Rice", place_id=cupboard)
    packet(kitchen, rice["id"], "bag", 1000)
    assert answer(kitchen, cupboard, rice["id"], {"fraction": 0.3}).status_code == 422
    assert answer(kitchen, cupboard, rice["id"], {}).status_code == 422
    assert answer(kitchen, cupboard, rice["id"], {"fraction": 1, "count": 1}).status_code == 422
    assert answer(kitchen, cupboard, rice["id"], {"fraction": 1, "more": 99}).status_code == 422
    assert total(kitchen, rice["id"], cupboard) == 0


def test_a_retried_answer_is_saved_once(kitchen: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    dal = food(kitchen, "Toor dal", place_id=cupboard)
    packet(kitchen, dal["id"], "bag", 1000)
    headers = {"Idempotency-Key": "stocktake-dal-1"}
    first = answer(kitchen, cupboard, dal["id"], {"fraction": 0.5}, headers=headers)
    again = answer(kitchen, cupboard, dal["id"], {"fraction": 0.5}, headers=headers)
    assert (first.status_code, again.status_code) == (200, 200)
    assert again.headers["Idempotent-Replayed"] == "true"
    assert again.json()["change"]["id"] == first.json()["change"]["id"]
    assert total(kitchen, dal["id"], cupboard) == 500_000
    # The same ID for something else is refused.
    rice = food(kitchen, "Rice", place_id=cupboard)
    packet(kitchen, rice["id"], "bag", 1000)
    other = answer(kitchen, cupboard, rice["id"], {"fraction": 1}, headers=headers)
    assert (other.status_code, other.json()["code"]) == (409, "key_reused")
    assert total(kitchen, rice["id"], cupboard) == 0


def test_answers_show_in_recent_changes_as_stocktake(kitchen: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    dal = food(kitchen, "Toor dal", place_id=cupboard)
    packet(kitchen, dal["id"], "bag", 1000)
    answer(kitchen, cupboard, dal["id"], {"fraction": 0.5})
    listed = kitchen.get(f"{API}/changes", params={"area": "pantry"}).json()["changes"]
    assert listed[0]["kind"] == "stocktake"
    assert listed[0]["summary"] == "Stocktake: Toor dal ½\u00a0bag in the Cupboard"
    assert listed[0]["can_undo"] is True


# --- The pack size, asked once --------------------------------------------------------------


def test_a_fraction_needs_a_pack_size_and_the_size_is_asked_once(kitchen: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    tamarind = food(kitchen, "Tamarind", place_id=cupboard)
    row = rows(kitchen, cupboard)["Tamarind"]
    assert row["pack"] is None and row["pack_suggestions"]  # S2's common sizes
    refused = answer(kitchen, cupboard, tamarind["id"], {"fraction": 0.5})
    assert (refused.status_code, refused.json()["code"]) == (422, "needs_size")
    assert answer(kitchen, cupboard, tamarind["id"], {"fraction": 0}).status_code == 200  # None
    pick = row["pack_suggestions"][0]
    made = kitchen.post(
        f"{STOCKTAKE}/places/{cupboard}/foods/{tamarind['id']}/size",
        json={"name": pick["name"], "amount": pick["amount"]},
    )
    assert made.status_code == 200, made.text
    body = made.json()
    assert body["change"]["kind"] == "stocktake"
    assert body["row"]["pack"]["usual"] is True
    assert body["row"]["pack_suggestions"] == []
    ok = answer(kitchen, cupboard, tamarind["id"], {"fraction": 0.5})
    assert ok.status_code == 200 and ok.json()["row"]["answer"]["fraction"] == "0.5"
    # Not asked again: it has a size now.
    again = kitchen.post(
        f"{STOCKTAKE}/places/{cupboard}/foods/{tamarind['id']}/size",
        json={"name": "tub", "amount": 100},
    )
    assert (again.status_code, again.json()["code"]) == (409, "has_size")
    # Undo of the size takes it away again.
    assert kitchen.post(f"{API}/changes/{body['change']['id']}/undo").status_code == 200
    assert rows(kitchen, cupboard)["Tamarind"]["pack"] is None


def test_a_size_typed_with_a_unit_becomes_the_usual_size(kitchen: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    jaggery = food(kitchen, "Jaggery", place_id=cupboard)
    made = kitchen.post(
        f"{STOCKTAKE}/places/{cupboard}/foods/{jaggery['id']}/size",
        json={"name": "block", "amount": {"amount": 1, "unit": "kg"}},
    )
    assert made.status_code == 200, made.text
    assert made.json()["row"]["pack"]["amount"] == 1000
    found = kitchen.get(f"{API}/foods/{jaggery['id']}").json()
    assert [(s["name"], s["usual"]) for s in found["sizes"]] == [("block", True)]


def test_a_counted_ingredient_or_a_staple_has_no_pack_to_ask(kitchen: TestClient) -> None:
    fridge, cupboard = place(kitchen, "Fridge"), place(kitchen, "Cupboard")
    eggs = food(kitchen, "Eggs", counted_as="count", place_id=fridge)
    salt = food(kitchen, "Salt", staple=True, place_id=cupboard)
    for where, found in ((fridge, eggs), (cupboard, salt)):
        response = kitchen.post(
            f"{STOCKTAKE}/places/{where}/foods/{found['id']}/size",
            json={"name": "bag", "amount": 500},
        )
        assert (response.status_code, response.json()["code"]) == (422, "no_pack")


# --- Staples --------------------------------------------------------------------------------


def test_its_a_staple_is_recorded_and_undone(kitchen: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    sambar = food(kitchen, "Sambar powder", place_id=cupboard)
    made = kitchen.post(f"{STOCKTAKE}/places/{cupboard}/foods/{sambar['id']}/staple")
    assert made.status_code == 200, made.text
    body = made.json()
    assert body["change"]["kind"] == "stocktake"
    assert body["change"]["summary"] == "Stocktake: Sambar powder is a staple in the Cupboard"
    assert body["row"]["staple"] is True and body["row"]["answered"] is True
    assert body["row"]["answer"] is None
    assert kitchen.get(f"{API}/foods/{sambar['id']}").json()["staple"] is True
    # A staple isn't counted, and can't be made one twice.
    refused = answer(kitchen, cupboard, sambar["id"], {"fraction": 0.5})
    assert (refused.status_code, refused.json()["code"]) == (409, "staple")
    twice = kitchen.post(f"{STOCKTAKE}/places/{cupboard}/foods/{sambar['id']}/staple")
    assert (twice.status_code, twice.json()["code"]) == (409, "already_staple")
    # Undo: not a staple, row unanswered again.
    assert kitchen.post(f"{API}/changes/{body['change']['id']}/undo").status_code == 200
    assert kitchen.get(f"{API}/foods/{sambar['id']}").json()["staple"] is False
    assert rows(kitchen, cupboard)["Sambar powder"]["answered"] is False


def test_a_staple_row_says_when_it_was_restocked(kitchen: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    rice = food(kitchen, "Basmati rice", staple=True, place_id=cupboard)
    row = rows(kitchen, cupboard)["Basmati rice"]
    assert row["staple"] is True and row["restocked_on"] is None
    patched = kitchen.patch(f"{API}/foods/{rice['id']}", json={"restocked_on": "2026-10-31"})
    assert patched.status_code == 200, patched.text
    row = rows(kitchen, cupboard)["Basmati rice"]
    assert row["restocked_on"] == "2026-10-31"
    assert row["restocked_days_ago"] is not None
    assert row["pack"] is None and row["pack_suggestions"] == []


# --- Something else ---------------------------------------------------------------------------


def test_something_else_joins_the_place_and_stays_when_asked_again(kitchen: TestClient) -> None:
    cupboard, fridge = place(kitchen, "Cupboard"), place(kitchen, "Fridge")
    jam = food(kitchen, "Jam", place_id=fridge)
    assert "Jam" not in rows(kitchen, cupboard)
    made = kitchen.post(f"{STOCKTAKE}/places/{cupboard}/foods", json={"food_id": jam["id"]})
    assert made.status_code == 201, made.text
    assert made.json()["row"]["added"] is True and made.json()["change"] is None
    again = kitchen.post(f"{STOCKTAKE}/places/{cupboard}/foods", json={"food_id": jam["id"]})
    assert again.status_code == 201
    listed = kitchen.get(f"{STOCKTAKE}/places/{cupboard}").json()
    assert [r["food"]["name"] for r in listed["rows"]].count("Jam") == 1
    assert (listed["answered"], listed["total"]) == (0, 1)
    # It is only for this stocktake's place: the fridge still has it as its own.
    assert rows(kitchen, fridge)["Jam"]["added"] is False
    assert kitchen.get(f"{API}/foods/{jam['id']}").json()["place"]["name"] == "Fridge"


# --- Progress is kept for the household ---------------------------------------------------------


def test_stop_and_carry_on_reopens_at_the_first_place_not_finished(kitchen: TestClient) -> None:
    found = kitchen.get(STOCKTAKE).json()
    ids = [p["id"] for p in found["places"]]
    fridge = ids[0]
    toor = food(kitchen, "Toor dal", place_id=ids[2])
    packet(kitchen, toor["id"], "bag", 1000)
    # Place 1 is finished, place 2 is left half-way: carry on at place 2.
    assert kitchen.post(f"{STOCKTAKE}/places/{fridge}/finish").status_code == 200
    answer(kitchen, ids[2], toor["id"], {"fraction": 0.5})
    after = kitchen.get(STOCKTAKE).json()
    assert after["current_place_id"] == ids[1]
    assert after["started"] is True and after["places"][0]["finished"] is True
    assert [p["answered"] for p in after["places"]][2] == 1
    # Finishing again changes nothing; finishing place 2 moves on to place 3.
    assert kitchen.post(f"{STOCKTAKE}/places/{fridge}/finish").status_code == 200
    moved = kitchen.post(f"{STOCKTAKE}/places/{ids[1]}/finish").json()
    assert moved["current_place_id"] == ids[2]
    assert moved["complete"] is False
    # An unfinished place is not "finished" because of the places after it.
    for pid in ids[2:]:
        done = kitchen.post(f"{STOCKTAKE}/places/{pid}/finish").json()
    assert (done["current_place_id"], done["complete"]) == (None, True)


def test_a_second_phone_carries_on_from_the_same_place(kitchen: TestClient) -> None:
    ids = [p["id"] for p in kitchen.get(STOCKTAKE).json()["places"]]
    assert kitchen.post(f"{STOCKTAKE}/places/{ids[0]}/finish").status_code == 200
    with TestClient(kitchen.app, base_url="https://testserver") as phone:
        body = {"username": "tess", "password": "correct horse battery"}
        assert phone.post(f"{API}/session", json=body).status_code == 200
        assert phone.get(STOCKTAKE).json()["current_place_id"] == ids[1]
        # What the second phone finishes, the first sees.
        assert phone.post(f"{STOCKTAKE}/places/{ids[1]}/finish").status_code == 200
    assert kitchen.get(STOCKTAKE).json()["current_place_id"] == ids[2]


def test_restart_forgets_the_progress_but_not_the_stock(kitchen: TestClient) -> None:
    ids = [p["id"] for p in kitchen.get(STOCKTAKE).json()["places"]]
    cupboard = place(kitchen, "Cupboard")
    dal = food(kitchen, "Toor dal", place_id=cupboard)
    packet(kitchen, dal["id"], "bag", 1000)
    answer(kitchen, cupboard, dal["id"], {"fraction": 0.5})
    for pid in ids:
        kitchen.post(f"{STOCKTAKE}/places/{pid}/finish")
    assert kitchen.get(STOCKTAKE).json()["complete"] is True
    fresh = kitchen.post(f"{STOCKTAKE}/restart").json()
    assert (fresh["started"], fresh["complete"]) == (False, False)
    assert fresh["current_place_id"] == ids[0]
    assert rows(kitchen, cupboard)["Toor dal"]["answered"] is False
    assert total(kitchen, dal["id"], cupboard) == 500_000


# --- Households -----------------------------------------------------------------------------


def test_nothing_crosses_into_another_household(kitchen: TestClient, neighbour: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    dal = food(kitchen, "Toor dal", place_id=cupboard)
    packet(kitchen, dal["id"], "bag", 1000)
    answer(kitchen, cupboard, dal["id"], {"fraction": 0.5})
    kitchen.post(f"{STOCKTAKE}/places/{cupboard}/finish")
    theirs = neighbour.get(STOCKTAKE).json()
    assert (theirs["started"], theirs["complete"]) == (False, False)
    assert all(p["answered"] == 0 for p in theirs["places"])
    their_cupboard = next(p["id"] for p in theirs["places"] if p["name"] == "Cupboard")
    assert "Toor dal" not in rows(neighbour, their_cupboard)
    # Their ids against our place, and our ids against theirs: not found.
    assert neighbour.get(f"{STOCKTAKE}/places/{cupboard}").status_code == 404
    assert neighbour.post(f"{STOCKTAKE}/places/{cupboard}/finish").status_code == 404
    assert answer(neighbour, cupboard, dal["id"], {"fraction": 1}).status_code == 404
    assert answer(neighbour, their_cupboard, dal["id"], {"fraction": 1}).status_code == 404
    assert (
        neighbour.post(f"{STOCKTAKE}/places/{their_cupboard}/foods/{dal['id']}/staple").status_code
        == 404
    )
    assert (
        neighbour.post(
            f"{STOCKTAKE}/places/{their_cupboard}/foods", json={"food_id": dal["id"]}
        ).status_code
        == 404
    )
    assert total(kitchen, dal["id"], cupboard) == 500_000
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        assert db.scalars(select(Food).where(Food.household_id == 2)).all() == []
        assert db.scalars(select(Change).where(Change.household_id == 2)).all() == []


def test_the_stocktake_needs_a_signed_in_person(client: TestClient) -> None:
    assert client.get(STOCKTAKE).status_code == 401
    assert client.post(f"{STOCKTAKE}/restart").status_code in (401, 403)


def test_removing_a_place_takes_its_stocktake_progress_with_it(kitchen: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    shelf = kitchen.post(f"{API}/places", json={"name": "Garage shelf", "kind": "cupboard"})
    assert shelf.status_code == 201, shelf.text
    shelf_id = shelf.json()["id"]
    jam = food(kitchen, "Jam", place_id=shelf_id)
    answer(kitchen, shelf_id, jam["id"], {"fraction": 0})
    assert kitchen.post(f"{STOCKTAKE}/places/{shelf_id}/finish").status_code == 200
    removed = kitchen.delete(f"{API}/places/{shelf_id}", params={"move_to": cupboard})
    assert removed.status_code == 200, removed.text
    after = kitchen.get(STOCKTAKE).json()
    assert shelf_id not in [p["id"] for p in after["places"]]
    assert kitchen.get(f"{STOCKTAKE}/places/{shelf_id}").status_code == 404
    # What it held moved on, and shows in the Cupboard's list.
    assert "Jam" in rows(kitchen, cupboard)


# --- Review round 1 ---------------------------------------------------------------------------


def dated_packs(kitchen: TestClient, food_id: int, where: int, days: list[int]) -> list[int]:
    """One 1 kg bag per date (days from today), added one at a time: their lot ids."""
    ids: list[int] = []
    for day in days:
        use_by = (date.today() + timedelta(days=day)).isoformat()
        body = {
            "food_id": food_id,
            "amount": {"amount": 1, "unit": "bag"},
            "place_id": where,
            "use_by": use_by,
        }
        response = kitchen.post(f"{API}/stock", json=body)
        assert response.status_code == 201, response.text
        ids.append(response.json()["groups"][0]["lots"][-1]["id"])
    return ids


def lots(kitchen: TestClient, food_id: int, place_id: int) -> dict[int, tuple[int, Any]]:
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        found = db.scalars(
            select(StockLot).where(StockLot.food_id == food_id, StockLot.place_id == place_id)
        )
        return {lot.id: (lot.amount_milli, lot.use_by) for lot in found}


def test_the_row_says_how_many_packets_are_there_before_any_pick(kitchen: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    dal = food(kitchen, "Toor dal", place_id=cupboard)
    packet(kitchen, dal["id"], "bag", 1000)
    dated_packs(kitchen, dal["id"], cupboard, [3, 5, 9])
    row = rows(kitchen, cupboard)["Toor dal"]
    assert row["answered"] is False and row["answer"] is None
    assert (row["fraction_now"], row["more_now"]) == ("1", 2)


def test_an_answer_that_matches_what_is_there_keeps_every_packet_and_date(
    kitchen: TestClient,
) -> None:
    cupboard = place(kitchen, "Cupboard")
    dal = food(kitchen, "Toor dal", place_id=cupboard)
    packet(kitchen, dal["id"], "bag", 1000)
    ids = dated_packs(kitchen, dal["id"], cupboard, [3, 5, 9])
    before = lots(kitchen, dal["id"], cupboard)
    same = answer(kitchen, cupboard, dal["id"], {"fraction": 1, "more": 2}).json()
    assert same["change"] is None  # nothing to change
    assert lots(kitchen, dal["id"], cupboard) == before
    assert same["row"]["answered"] is True
    # Three quarters of the open one: only one packet changes, the dates stay.
    down = answer(kitchen, cupboard, dal["id"], {"fraction": 0.75, "more": 2}).json()
    after = lots(kitchen, dal["id"], cupboard)
    assert set(after) == set(ids)  # no packet made or lost
    assert [after[i][1] for i in ids] == [before[i][1] for i in ids]
    assert sum(a for a, _ in after.values()) == 2_750_000
    assert sum(after[i][0] != before[i][0] for i in ids) == 1
    assert down["row"]["answer"] == {"fraction": "0.75", "more": 2, "count": None}


def test_half_then_three_quarters_fills_the_open_packet_and_keeps_every_date(
    kitchen: TestClient,
) -> None:
    """S6 review r2 M1: going up from ½ tops up the part-used packet, never a new undated one."""
    cupboard = place(kitchen, "Cupboard")
    dal = food(kitchen, "Toor dal", place_id=cupboard)
    packet(kitchen, dal["id"], "bag", 1000)
    ids = dated_packs(kitchen, dal["id"], cupboard, [3, 5, 9])
    answer(kitchen, cupboard, dal["id"], {"fraction": 0.5, "more": 2})
    answer(kitchen, cupboard, dal["id"], {"fraction": 0.75, "more": 2})
    after = {i: v for i, v in lots(kitchen, dal["id"], cupboard).items() if v[0] > 0}
    assert set(after) == set(ids)
    assert all(use_by is not None for _, use_by in after.values())
    assert sum(a for a, _ in after.values()) == 2_750_000


def test_a_staple_is_left_out_of_the_places_total(kitchen: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    rice = food(kitchen, "Basmati rice", staple=True, place_id=cupboard)
    dal = food(kitchen, "Toor dal", place_id=cupboard)
    packet(kitchen, dal["id"], "bag", 1000)
    shown = kitchen.get(f"{STOCKTAKE}/places/{cupboard}").json()
    assert (shown["answered"], shown["total"]) == (0, 1)
    assert [r["food"]["name"] for r in shown["rows"]] == ["Basmati rice", "Toor dal"]
    done = answer(kitchen, cupboard, dal["id"], {"fraction": 0.5}).json()
    assert (done["answered"], done["total"]) == (1, 1)  # "1 of 1 done", reachable
    step = next(p for p in kitchen.get(STOCKTAKE).json()["places"] if p["id"] == cupboard)
    assert (step["answered"], step["total"]) == (1, 1)
    assert rice["id"] != dal["id"]


def test_answering_again_with_the_same_value_keeps_the_first_undo(kitchen: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    dal = food(kitchen, "Toor dal", place_id=cupboard)
    packet(kitchen, dal["id"], "bag", 1000)
    first = answer(kitchen, cupboard, dal["id"], {"fraction": 0.5}).json()
    again = answer(kitchen, cupboard, dal["id"], {"fraction": 0.5}).json()
    assert again["change"] is None
    undone = kitchen.post(f"{API}/changes/{first['change']['id']}/undo")
    assert undone.status_code == 200, undone.text
    row = rows(kitchen, cupboard)["Toor dal"]
    assert row["answered"] is False and row["answer"] is None


def test_the_picks_read_stock_that_changed_since_to_the_nearest_quarter(
    kitchen: TestClient,
) -> None:
    cupboard = place(kitchen, "Cupboard")
    dal = food(kitchen, "Toor dal", place_id=cupboard)
    packet(kitchen, dal["id"], "bag", 1000)
    add(kitchen, dal["id"], 1100, "g", cupboard)  # 1.1 bags
    now = rows(kitchen, cupboard)["Toor dal"]
    assert (now["fraction_now"], now["more_now"]) == ("1", 0)  # not "None" with a hidden count
    add(kitchen, dal["id"], 1600, "g", cupboard)  # 2.7 bags
    now = rows(kitchen, cupboard)["Toor dal"]
    assert (now["fraction_now"], now["more_now"]) == ("0.75", 2)
    assert answer(kitchen, cupboard, dal["id"], {"fraction": 0.75, "more": 2}).status_code == 200


def test_a_counted_row_carries_its_word(kitchen: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    tins = food(kitchen, "Tinned tomatoes", counted_as="count", place_id=cupboard)
    assert kitchen.patch(f"{API}/foods/{tins['id']}", json={"count_word": "tin"}).status_code == 200
    food(kitchen, "Onion", counted_as="count", place_id=cupboard)
    found = rows(kitchen, cupboard)
    assert (
        found["Tinned tomatoes"]["count_word"],
        found["Tinned tomatoes"]["count_word_plural"],
    ) == (
        "tin",
        "tins",
    )
    assert found["Onion"]["count_word"] is None


# --- cabledrawer's answers, 7 Nov ----------------------------------------------------------------


def test_a_tin_is_counted_whole_and_a_jar_keeps_the_picks(kitchen: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    milk = food(kitchen, "Chickpeas", place_id=cupboard)
    packet(kitchen, milk["id"], "tin", 400)
    jam = food(kitchen, "Jam", place_id=cupboard)
    packet(kitchen, jam["id"], "jar", 450)
    add(kitchen, milk["id"], 800, "g", cupboard)  # 2 tins
    found = rows(kitchen, cupboard)
    tin, jar = found["Chickpeas"], found["Jam"]
    assert (tin["counted"], tin["count_now"]) == (True, "2")
    assert (tin["count_word"], tin["count_word_plural"]) == ("tin", "tins")
    assert (tin["fraction_now"], tin["more_now"], tin["pack_suggestions"]) == (None, 0, [])
    assert (jar["counted"], jar["count_now"], jar["count_word"]) == (False, None, None)
    # A tin takes a count of whole tins, and no fractions.
    refused = answer(kitchen, cupboard, milk["id"], {"fraction": 0.5})
    assert refused.status_code == 422, refused.text
    done = answer(kitchen, cupboard, milk["id"], {"count": 3}).json()
    assert total(kitchen, milk["id"], cupboard) == 1_200_000
    assert done["row"]["answer"] == {"fraction": None, "more": 0, "count": "3"}
    assert done["row"]["count_now"] == "3"
    assert done["change"]["summary"].startswith("Stocktake: Chickpeas ")
    undone = kitchen.post(f"{API}/changes/{done['change']['id']}/undo")
    assert undone.status_code == 200, undone.text
    assert total(kitchen, milk["id"], cupboard) == 800_000
    # A jar keeps its fractions, and refuses a count.
    assert answer(kitchen, cupboard, jam["id"], {"fraction": 0.5}).status_code == 200
    assert answer(kitchen, cupboard, jam["id"], {"count": 2}).status_code == 422


def test_a_tin_count_is_rounded_to_whole_tins(kitchen: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    beans = food(kitchen, "Beans", place_id=cupboard)
    packet(kitchen, beans["id"], "tin", 400)
    add(kitchen, beans["id"], 600, "g", cupboard)  # 1.5 tins: reads as 2
    assert rows(kitchen, cupboard)["Beans"]["count_now"] == "2"
    answer(kitchen, cupboard, beans["id"], {"count": 1.4})
    assert total(kitchen, beans["id"], cupboard) == 400_000
    answer(kitchen, cupboard, beans["id"], {"count": 2.5})  # half up, as the row reads
    assert total(kitchen, beans["id"], cupboard) == 1_200_000


def test_a_pack_size_of_tin_picked_while_counting_makes_the_row_counted(
    kitchen: TestClient,
) -> None:
    cupboard = place(kitchen, "Cupboard")
    peas = food(kitchen, "Peas", place_id=cupboard)
    before = rows(kitchen, cupboard)["Peas"]
    assert before["counted"] is False and before["pack"] is None
    size = {"name": "tin", "amount": {"amount": 400, "unit": "g"}}
    done = kitchen.post(f"{STOCKTAKE}/places/{cupboard}/foods/{peas['id']}/size", json=size)
    assert done.status_code == 200, done.text
    assert done.json()["row"]["counted"] is True
    assert done.json()["row"]["pack"]["name"] == "tin"


def test_next_records_every_unanswered_row_as_checked_and_leaves_the_stock(
    kitchen: TestClient,
) -> None:
    cupboard = place(kitchen, "Cupboard")
    dal = food(kitchen, "Toor dal", place_id=cupboard)
    packet(kitchen, dal["id"], "bag", 1000)
    add(kitchen, dal["id"], 700, "g", cupboard)
    atta = food(kitchen, "Atta", place_id=cupboard)  # no pack size, no stock
    rice = food(kitchen, "Rice", staple=True, place_id=cupboard)
    said = food(kitchen, "Salt", place_id=cupboard)
    packet(kitchen, said["id"], "bag", 1000)
    add(kitchen, said["id"], 1000, "g", cupboard)
    answer(kitchen, cupboard, said["id"], {"fraction": 0.5})  # answered by hand
    changes = changes_count(kitchen)
    stock = {f["id"]: total(kitchen, f["id"], cupboard) for f in (dal, atta, rice, said)}
    shown = kitchen.get(f"{STOCKTAKE}/places/{cupboard}").json()
    assert (shown["answered"], shown["total"]) == (1, 3)
    assert kitchen.post(f"{STOCKTAKE}/places/{cupboard}/finish").status_code == 200
    after = kitchen.get(f"{STOCKTAKE}/places/{cupboard}").json()
    assert (after["answered"], after["total"]) == (3, 3)
    assert all(r["answered"] for r in after["rows"] if not r["staple"])
    assert {f["id"]: total(kitchen, f["id"], cupboard) for f in (dal, atta, rice, said)} == stock
    assert changes_count(kitchen) == changes  # nothing in Recent changes for an unchanged row
    # Stop, carry on later: the place is finished, the stocktake reopens at the next one.
    reopened = kitchen.get(STOCKTAKE).json()
    step = next(p for p in reopened["places"] if p["id"] == cupboard)
    assert step["finished"] is True and reopened["current_place_id"] != cupboard
    # Sending it again changes nothing.
    assert kitchen.post(f"{STOCKTAKE}/places/{cupboard}/finish").status_code == 200
    assert changes_count(kitchen) == changes


def changes_count(kitchen: TestClient) -> int:
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        return len(db.scalars(select(Change.id)).all())


def test_next_after_an_undone_answer_counts_that_row_as_checked_too(kitchen: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    dal = food(kitchen, "Toor dal", place_id=cupboard)
    packet(kitchen, dal["id"], "bag", 1000)
    first = answer(kitchen, cupboard, dal["id"], {"fraction": 0.5}).json()
    kitchen.post(f"{API}/changes/{first['change']['id']}/undo")
    assert rows(kitchen, cupboard)["Toor dal"]["answered"] is False
    kitchen.post(f"{STOCKTAKE}/places/{cupboard}/finish")
    assert rows(kitchen, cupboard)["Toor dal"]["answered"] is True
    assert total(kitchen, dal["id"], cupboard) == 0
