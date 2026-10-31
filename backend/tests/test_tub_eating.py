"""Eating a tub (0.7 K2; spec section 2, point 7, and "Stock", Tubs): the tub is used, never the
ingredients again; one whole tub by default, in quarter steps; what is left stays where it is."""

from datetime import date, timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_deduction import plan_item, recipe_of
from test_plan import db_of
from test_recipe_list import line, stock
from test_recipes import food

from mealwright.models import StockLot, Tub

API = "/api/v1"
DAY = date.today() + timedelta(days=2)


def tubs_of_a_batch(client: TestClient) -> tuple[dict[str, Any], list[int]]:
    dal = food(client, "Zorba dal")
    stock(client, dal["id"], 2000, "g")
    item = plan_item(client, recipe_of(client, [line(dal["id"], 200, "g")]))
    ok(client.post(f"{API}/plan/items/{item}/batch", json={"tub_count": 3, "pattern": "pick"}), 201)
    left = ok(client.get(f"{API}/plan/tubs-left"))["tubs"]
    return dal, [t["id"] for t in left]


def quarters(client: TestClient, tub_id: int) -> int:
    with db_of(client) as db:
        tub = db.get(Tub, tub_id)
        assert tub is not None
        return tub.amount_quarters


def eat(client: TestClient, tub_id: int, **body: Any) -> Any:
    return client.post(f"{API}/plan/tubs/{tub_id}/eat", json=body)


def test_a_whole_tub_is_eaten_by_default_and_the_ingredients_are_not_touched(
    kitchen: TestClient,
) -> None:
    dal, tubs = tubs_of_a_batch(kitchen)
    done = ok(eat(kitchen, tubs[0]))
    assert done["change"]["summary"] == "Ate Zorba curry tub" and done["change"]["can_undo"]
    assert [quarters(kitchen, t) for t in tubs] == [0, 4, 4]
    with db_of(kitchen) as db:
        assert [lot.amount_milli for lot in db.scalars(select(StockLot))] == [2_000_000]
    # An eaten tub is no longer a tub left.
    assert tubs[0] not in [t["id"] for t in ok(kitchen.get(f"{API}/plan/tubs-left"))["tubs"]]
    assert dal["id"]


def test_quarters_can_be_eaten_and_what_is_left_stays_where_it_is(kitchen: TestClient) -> None:
    _, tubs = tubs_of_a_batch(kitchen)
    before = ok(kitchen.get(f"{API}/plan/tubs-left"))["tubs"][0]
    done = ok(eat(kitchen, tubs[0], quarters=2))
    assert done["change"]["summary"] == "Ate ½ of Zorba curry tub"
    assert quarters(kitchen, tubs[0]) == 2
    after = next(t for t in ok(kitchen.get(f"{API}/plan/tubs-left"))["tubs"] if t["id"] == tubs[0])
    assert (after["place_id"], after["use_by"], after["amount_quarters"]) == (
        before["place_id"],
        before["use_by"],
        2,
    )
    # "A whole tub" now means what is left of it.
    done = ok(eat(kitchen, tubs[0]))
    assert done["change"]["summary"] == "Ate Zorba curry tub" and quarters(kitchen, tubs[0]) == 0


def test_more_than_is_left_and_an_empty_tub_are_refused(kitchen: TestClient) -> None:
    _, tubs = tubs_of_a_batch(kitchen)
    ok(eat(kitchen, tubs[0], quarters=3))
    too_much = eat(kitchen, tubs[0], quarters=2)
    assert (too_much.status_code, too_much.json()["code"]) == (422, "too_much")
    assert too_much.json()["detail"] == "There’s only ¼ of that tub left."
    assert eat(kitchen, tubs[0], quarters=0).status_code == 422
    assert eat(kitchen, tubs[0], quarters=5).status_code == 422
    ok(eat(kitchen, tubs[0]))
    empty = eat(kitchen, tubs[0])
    assert (empty.status_code, empty.json()["code"]) == (409, "tub_eaten")
    assert quarters(kitchen, tubs[0]) == 0


def test_undo_gives_the_quarters_back(kitchen: TestClient) -> None:
    _, tubs = tubs_of_a_batch(kitchen)
    done = ok(eat(kitchen, tubs[0], quarters=3))
    undone = ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))
    assert undone["result"] == "done" and quarters(kitchen, tubs[0]) == 4


def test_undo_gives_back_what_it_ate_even_after_the_tub_was_eaten_from_again(
    kitchen: TestClient,
) -> None:
    _, tubs = tubs_of_a_batch(kitchen)
    first = ok(eat(kitchen, tubs[0], quarters=1))
    ok(eat(kitchen, tubs[0], quarters=1))
    undone = ok(kitchen.post(f"{API}/changes/{first['change']['id']}/undo"))
    assert undone["result"] == "done" and quarters(kitchen, tubs[0]) == 3  # the stock rule


def test_a_retry_with_the_same_key_eats_once(kitchen: TestClient) -> None:
    _, tubs = tubs_of_a_batch(kitchen)
    headers = {"Idempotency-Key": "eat-1"}
    url = f"{API}/plan/tubs/{tubs[0]}/eat"
    one = kitchen.post(url, json={"quarters": 1}, headers=headers)
    two = kitchen.post(url, json={"quarters": 1}, headers=headers)
    assert one.status_code == two.status_code == 200
    assert two.headers["Idempotent-Replayed"] == "true"
    assert quarters(kitchen, tubs[0]) == 3


def test_no_body_means_the_whole_tub(kitchen: TestClient) -> None:
    _, tubs = tubs_of_a_batch(kitchen)
    ok(kitchen.post(f"{API}/plan/tubs/{tubs[0]}/eat"))
    assert quarters(kitchen, tubs[0]) == 0


def test_another_households_tub_is_not_found(kitchen: TestClient, neighbour: TestClient) -> None:
    _, tubs = tubs_of_a_batch(kitchen)
    assert eat(neighbour, tubs[0]).status_code == 404
    assert quarters(kitchen, tubs[0]) == 4
