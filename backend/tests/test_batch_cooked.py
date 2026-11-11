"""One Cooked it for a whole Batch cook session (0.8 wave 6, B3; cabledrawer 28 Oct and 11 Nov): every
recipe's stock taken as ONE change with one Undo, the tubs per recipe, and the stock after Cooked
it and after Undo the same as doing each recipe's Cooked it alone and undoing it."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import ok
from test_plan import db_of, slot_ids
from test_plan_writes import D1
from test_recipe_list import stock
from test_recipes import food, make

from mealwright.models import CookedRecord, Food, StockLot

API = "/api/v1"


def session_of(client: TestClient, household_id: int = 1) -> tuple[int, list[int]]:
    """Sambar and Chicken chettinad sharing onions and coconut, with stock for both, as one
    session on D1. Returns the session and its batch ids."""
    onion = food(client, "Onion", counted_as="count")
    dal = food(client, "Toor dal")
    chicken = food(client, "Chicken")
    stock(client, onion["id"], 6, "count")
    stock(client, onion["id"], 3, "count")  # a second packet, so the order matters
    stock(client, dal["id"], 500, "g")
    stock(client, chicken["id"], 700, "g")
    sambar = make(
        client,
        "Sambar",
        serves=4,
        lines=[
            {"words": "200 g toor dal", "food_id": dal["id"], "amount": 200, "unit": "g"},
            {"words": "2 onions", "food_id": onion["id"], "amount": 2},
        ],
        steps=[{"text": "Chop the onions."}, {"text": "Pressure cook the dal."}],
    )
    chettinad = make(
        client,
        "Chicken chettinad",
        serves=4,
        lines=[
            {"words": "500 g chicken", "food_id": chicken["id"], "amount": 500, "unit": "g"},
            {"words": "5 onions", "food_id": onion["id"], "amount": 5},
        ],
        steps=[{"text": "Chop the onions."}, {"text": "Simmer for 20 minutes."}],
    )
    body = {
        "date": D1.isoformat(),
        "slot_id": slot_ids(client, household_id)["Dinner"],
        "recipes": [
            {"recipe_id": sambar["id"], "tub_count": 2},
            {"recipe_id": chettinad["id"], "tub_count": 3},
        ],
    }
    made = ok(client.post(f"{API}/batch-cook/sessions", json=body), 201)
    found = ok(client.get(f"{API}/batch-cook/sessions/{made['session_id']}"))
    return int(made["session_id"]), [r["batch_id"] for r in found["recipes"]]


def pantry(client: TestClient) -> dict[str, list[int]]:
    """Each ingredient's packets, by name, oldest first (thousandths)."""
    with db_of(client) as db:
        names = {f.id: f.name for f in db.scalars(select(Food))}
        out: dict[str, list[int]] = {}
        for lot in db.scalars(select(StockLot).order_by(StockLot.id)):
            out.setdefault(names[lot.food_id], []).append(lot.amount_milli)
        return out


def test_one_cooked_it_takes_the_same_stock_as_each_recipe_alone_and_undo_gives_it_back(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    session, _ = session_of(kitchen)
    _, alone = session_of(neighbour, 2)
    start = pantry(kitchen)
    assert pantry(neighbour) == start

    preview = ok(kitchen.post(f"{API}/batch-cook/sessions/{session}/cook/preview", json={}))
    assert [i["recipe_name"] for i in preview["items"]] == ["Sambar", "Chicken chettinad"]
    assert [i["tub_count"] for i in preview["items"]] == [2, 3]
    assert pantry(kitchen) == start  # the preview changes nothing

    done = ok(kitchen.post(f"{API}/batch-cook/sessions/{session}/cook", json={}), 201)
    assert done["change"]["kind"] == "cooked" and done["change"]["can_undo"] is True
    assert len(done["cooked"]) == 2  # a record for each recipe, one change
    assert {c["snapshot"]["name"] for c in done["cooked"]} == {"Sambar", "Chicken chettinad"}

    changes: list[dict[str, Any]] = []
    for batch in alone:
        changes.append(ok(neighbour.post(f"{API}/plan/batches/{batch}/cook", json={}), 201))
    after = pantry(kitchen)
    assert after != start
    assert after == pantry(neighbour)  # the same as cooking each alone

    ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))
    for each in reversed(changes):
        ok(neighbour.post(f"{API}/changes/{each['change']['id']}/undo"))
    assert pantry(kitchen) == start == pantry(neighbour)
    with db_of(kitchen) as db:
        assert db.scalars(select(CookedRecord)).all() == []  # it can be cooked again


def test_it_is_one_group_in_recent_changes(kitchen: TestClient) -> None:
    session, _ = session_of(kitchen)
    done = ok(kitchen.post(f"{API}/batch-cook/sessions/{session}/cook", json={}), 201)
    listed = ok(kitchen.get(f"{API}/changes", params={"area": "pantry"}))["changes"]
    cooked = [c for c in listed if c["kind"] == "cooked"]
    assert [c["id"] for c in cooked] == [done["change"]["id"]]
    assert "Sambar" in cooked[0]["summary"] and "Chicken chettinad" in cooked[0]["summary"]


def test_a_second_cooked_it_is_refused_and_takes_nothing(kitchen: TestClient) -> None:
    session, _ = session_of(kitchen)
    ok(kitchen.post(f"{API}/batch-cook/sessions/{session}/cook", json={}), 201)
    after = pantry(kitchen)
    again = kitchen.post(f"{API}/batch-cook/sessions/{session}/cook", json={})
    assert again.status_code == 409 and again.json()["code"] == "already_cooked"
    assert pantry(kitchen) == after


def test_asking_for_a_recipe_already_cooked_refuses_all_and_takes_nothing(
    kitchen: TestClient,
) -> None:
    session, batches = session_of(kitchen)
    ok(kitchen.post(f"{API}/plan/batches/{batches[0]}/cook", json={}), 201)  # Sambar, alone
    after = pantry(kitchen)
    refused = kitchen.post(
        f"{API}/batch-cook/sessions/{session}/cook",
        json={"items": [{"batch_id": batches[0]}, {"batch_id": batches[1]}]},
    )
    assert refused.status_code == 409 and refused.json()["code"] == "already_cooked"
    assert pantry(kitchen) == after  # Chicken chettinad was not taken either


def test_a_recipe_cooked_alone_is_left_out_of_the_session_cooked_it_not_a_reason_to_refuse(
    kitchen: TestClient,
) -> None:
    """Review B3 round 1, fix 2: as Cooked it does for a meal, what was cooked already or removed
    is skipped, flagged, and the rest is cooked."""
    session, batches = session_of(kitchen)
    ok(kitchen.post(f"{API}/plan/batches/{batches[0]}/cook", json={}), 201)  # Sambar, alone
    flags = {
        r["recipe_name"]: r["left_out"]
        for r in ok(kitchen.post(f"{API}/batch-cook/sessions/{session}/schedule", json={}), 201)[
            "recipes"
        ]
    }
    assert flags == {"Sambar": "cooked", "Chicken chettinad": None}
    preview = ok(kitchen.post(f"{API}/batch-cook/sessions/{session}/cook/preview", json={}))
    assert [i["recipe_name"] for i in preview["items"]] == ["Chicken chettinad"]
    assert [(r["recipe_name"], r["left_out"]) for r in preview["left_out"]] == [
        ("Sambar", "cooked")
    ]
    done = ok(kitchen.post(f"{API}/batch-cook/sessions/{session}/cook", json={}), 201)
    assert [c["snapshot"]["name"] for c in done["cooked"]] == ["Chicken chettinad"]
    # Everything cooked now: said so, not an empty review.
    again = kitchen.post(f"{API}/batch-cook/sessions/{session}/cook/preview", json={})
    assert again.status_code == 409 and again.json()["code"] == "already_cooked"


def test_a_removed_recipe_is_left_out_too(kitchen: TestClient) -> None:
    session, _ = session_of(kitchen)
    recipes = ok(kitchen.get(f"{API}/batch-cook/sessions/{session}"))["recipes"]
    gone = next(r for r in recipes if r["recipe_name"] == "Sambar")["recipe_id"]
    ok(kitchen.delete(f"{API}/recipes/{gone}"))
    preview = ok(kitchen.post(f"{API}/batch-cook/sessions/{session}/cook/preview", json={}))
    assert [i["recipe_name"] for i in preview["items"]] == ["Chicken chettinad"]
    assert [r["left_out"] for r in preview["left_out"]] == ["removed"]


def test_a_retry_with_the_same_key_takes_nothing_more(kitchen: TestClient) -> None:
    session, _ = session_of(kitchen)
    headers = {"Idempotency-Key": "11111111-1111-4111-8111-111111111111"}
    first = ok(
        kitchen.post(f"{API}/batch-cook/sessions/{session}/cook", json={}, headers=headers), 201
    )
    after = pantry(kitchen)
    second = kitchen.post(f"{API}/batch-cook/sessions/{session}/cook", json={}, headers=headers)
    assert second.status_code == 200 and second.json()["change"]["id"] == first["change"]["id"]
    assert pantry(kitchen) == after


def test_only_some_recipes_and_their_own_portions_can_be_asked_for(kitchen: TestClient) -> None:
    session, batches = session_of(kitchen)
    preview = ok(
        kitchen.post(
            f"{API}/batch-cook/sessions/{session}/cook/preview",
            json={"items": [{"batch_id": batches[1], "portions": 8}]},
        )
    )
    assert [i["recipe_name"] for i in preview["items"]] == ["Chicken chettinad"]
    assert preview["items"][0]["proposal"]["portions"] == 8
    twice = kitchen.post(
        f"{API}/batch-cook/sessions/{session}/cook/preview",
        json={"items": [{"batch_id": batches[0]}, {"batch_id": batches[0]}]},
    )
    assert twice.status_code == 422 and twice.json()["code"] == "twice"
    strange = kitchen.post(
        f"{API}/batch-cook/sessions/{session}/cook/preview", json={"items": [{"batch_id": 9999}]}
    )
    assert strange.status_code == 404


def test_the_tubs_of_each_recipe_are_counted_by_where_they_are(kitchen: TestClient) -> None:
    session, _ = session_of(kitchen)
    preview = ok(kitchen.post(f"{API}/batch-cook/sessions/{session}/cook/preview", json={}))
    for item in preview["items"]:
        assert sum(t["count"] for t in item["tubs"]) == item["tub_count"]


def test_the_other_household_and_the_switch(kitchen: TestClient, neighbour: TestClient) -> None:
    session, _ = session_of(kitchen)
    assert (
        neighbour.post(f"{API}/batch-cook/sessions/{session}/cook/preview", json={}).status_code
        == 404
    )
    assert neighbour.post(f"{API}/batch-cook/sessions/{session}/cook", json={}).status_code == 404
    ok(kitchen.patch(f"{API}/household", json={"batch_cook": False}))
    hidden = kitchen.post(f"{API}/batch-cook/sessions/{session}/cook", json={})
    assert hidden.status_code == 409 and hidden.json()["code"] == "batch_cook_hidden"


def test_another_households_batch_cook_is_not_found_in_my_session(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    session, mine = session_of(kitchen)
    _, theirs = session_of(neighbour, 2)
    before = pantry(kitchen)
    for path in ("cook/preview", "cook"):
        refused = kitchen.post(
            f"{API}/batch-cook/sessions/{session}/{path}",
            json={"items": [{"batch_id": mine[0]}, {"batch_id": theirs[0]}]},
        )
        assert refused.status_code == 404 and refused.json()["code"] == "not_found"
    assert pantry(kitchen) == before


# --- Whole-0.8 review fixes (RF3): C3 ------------------------------------------------------------


def test_a_session_cooked_before_its_day_counts_the_tubs_from_today_and_cooks_the_meal(
    kitchen: TestClient,
) -> None:
    """C3 (against F159): a session on D1 cooked today: the tubs' use-by counts from today, the
    cook-day meal is cooked at once (not "planned" for 5 minutes), one Undo gives it all back."""
    from sqlalchemy import select
    from test_plan_writes import view

    from mealwright.models import Tub

    sid, _ = session_of(kitchen)

    def use_bys() -> list[Any]:
        with db_of(kitchen) as db:
            return sorted(t.use_by for t in db.scalars(select(Tub)) if t.use_by is not None)

    def meal_status() -> str:
        meal = next(m for m in view(kitchen)["meals"] if m["date"] == D1.isoformat())
        return str(meal["status"])

    before = use_bys()
    assert before and meal_status() == "planned"
    done = ok(kitchen.post(f"{API}/batch-cook/sessions/{sid}/cook", json={}), 201)
    after = use_bys()
    assert len(after) == len(before) and all(a < b for a, b in zip(after, before, strict=True))
    assert meal_status() == "cooked"
    ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))
    assert use_bys() == before
    assert meal_status() == "planned"


# --- Whole-0.8 review fixes (RF3): C6 ------------------------------------------------------------


def biryani_session(
    client: TestClient, **choice: Any
) -> tuple[int, dict[str, Any], dict[str, Any]]:
    """Biryani (cashews are an optional line, with an optional step that uses them) and Dal, as a
    session on D1; `choice` goes on Biryani's entry (`optional_use`, `method_id`)."""
    rice, nuts, dal_food = food(client, "Rice"), food(client, "Cashew"), food(client, "Toor dal")
    for each, amount in ((rice, 1000), (nuts, 200), (dal_food, 500)):
        stock(client, each["id"], amount, "g")
    biryani = make(
        client,
        "Biryani",
        serves=4,
        lines=[
            {"words": "400 g rice", "food_id": rice["id"], "amount": 400, "unit": "g"},
            {
                "words": "50 g cashew",
                "food_id": nuts["id"],
                "amount": 50,
                "unit": "g",
                "optional": True,
            },
        ],
        steps=[
            {"text": "Simmer the rice for 15 minutes."},
            {"text": "Fry the cashews for the top.", "lines": [1], "optional": True},
            {"text": "Garnish with coriander.", "optional": True},
        ],
    )
    dal = make(
        client,
        "Dal",
        serves=4,
        lines=[{"words": "200 g toor dal", "food_id": dal_food["id"], "amount": 200, "unit": "g"}],
        steps=[{"text": "Simmer the dal for 20 minutes."}],
    )
    if choice.get("optional_use") == ["cashew"]:  # the line's id is not known until now
        choice["optional_use"] = [biryani["lines"][1]["id"]]
    body = {
        "date": D1.isoformat(),
        "slot_id": slot_ids(client)["Dinner"],
        "recipes": [
            {"recipe_id": biryani["id"], "tub_count": 2, **choice},
            {"recipe_id": dal["id"], "tub_count": 2},
        ],
    }
    made = ok(client.post(f"{API}/batch-cook/sessions", json=body), 201)
    return int(made["session_id"]), biryani, dal


def titles(client: TestClient, session_id: int) -> list[str]:
    made = ok(client.post(f"{API}/batch-cook/sessions/{session_id}/schedule"), 201)
    return [str(t["title"]) for t in made["tasks"]]


def test_the_optional_ingredients_left_out_are_neither_cooked_in_batch_mode_nor_taken(
    kitchen: TestClient,
) -> None:
    """C6: the pick `optional_use: []` leaves the cashews out: their step is not in the schedule
    (the garnish step has no ingredient, so it stays) and Cooked it takes no cashews."""
    sid, _, _ = biryani_session(kitchen, optional_use=[])
    names = titles(kitchen, sid)
    assert not any("cashew" in t.lower() for t in names)
    assert any("garnish" in t.lower() for t in names)
    done = ok(kitchen.post(f"{API}/batch-cook/sessions/{sid}/cook", json={}), 201)
    assert pantry(kitchen)["Cashew"] == [200_000]
    ok(kitchen.post(f"{API}/changes/{done['change']['id']}/undo"))


def test_the_optional_ingredients_kept_show_in_batch_mode_and_are_taken(
    kitchen: TestClient,
) -> None:
    """No pick sent (every optional line counts) or the cashew line picked: the step is there and
    the cashews are taken."""
    sid, _, _ = biryani_session(kitchen, optional_use=["cashew"])
    assert any("cashew" in t.lower() for t in titles(kitchen, sid))
    ok(kitchen.post(f"{API}/batch-cook/sessions/{sid}/cook", json={}), 201)
    assert pantry(kitchen)["Cashew"] == [162_500]  # 37.5 g: 50 g scaled to the 3 portions


def test_with_no_pick_sent_every_optional_ingredient_counts_as_before(
    kitchen: TestClient,
) -> None:
    sid, _, _ = biryani_session(kitchen)
    assert any("cashew" in t.lower() for t in titles(kitchen, sid))


def test_a_session_recipe_takes_the_way_of_cooking_it_was_asked_for(kitchen: TestClient) -> None:
    """C6: `method_id` on a session's recipe plans the meal in that way (the one used last when
    none is sent, as adding to the plan does); a method that isn't the recipe's is refused."""
    from test_plan_writes import view
    from test_recipes import save

    a = make(kitchen, "Two ways", steps=[{"text": "Fry."}, {"text": "Simmer for 10 minutes."}])
    fresh_a = ok(kitchen.get(f"{API}/recipes/{a['id']}"))
    saved = ok(
        save(
            kitchen,
            fresh_a,
            method_name="Stovetop",
            second_method={
                "name": "Instant Pot",
                "time_minutes": 10,
                "lines": [],
                "steps": [{"text": "Pressure cook."}],
            },
        )
    )
    other = saved["methods"][1]["id"]
    b = make(kitchen, "Plain", steps=[{"text": "Simmer for 10 minutes."}])

    def body(**choice: Any) -> dict[str, Any]:
        return {
            "date": D1.isoformat(),
            "slot_id": slot_ids(kitchen)["Dinner"],
            "recipes": [
                {"recipe_id": a["id"], "tub_count": 2, **choice},
                {"recipe_id": b["id"], "tub_count": 2},
            ],
        }

    refused = kitchen.post(f"{API}/batch-cook/sessions", json=body(method_id=other + 999))
    assert refused.status_code == 422, refused.text
    ok(kitchen.post(f"{API}/batch-cook/sessions", json=body(method_id=other)), 201)
    items = [i for m in view(kitchen)["meals"] for i in m["items"] if i["recipe"]]
    assert [i["method"] for i in items if i["recipe"]["name"] == "Two ways"] == ["Instant Pot"]
