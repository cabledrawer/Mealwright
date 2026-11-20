"""Batch cook's suggestions (0.8 wave 6, B2; cabledrawer 28 Oct and 11 Nov): picked only from the
household's own recipes, favouring shared prep, then Use soon ingredients, then what was not
cooked in the last 14 days, then what the kitchen can do; the why line, the times together and one
by one, swap, Show me others, the switch, and ids from another household."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sync_kit import ok, person
from test_plan import slot_ids
from test_plan_writes import D1, plan_recipe
from test_recipe_list import fresh, stock, today
from test_recipes import food, make

from mealwright import step_timings
from mealwright.batch_suggest import Equipment, together_minutes
from mealwright.models import BatchCook, CookedRecord, utcnow

API = "/api/v1"

CHOP = "Chop the {} finely."
SIMMER = "Simmer for {} minutes."


def recipe(
    kitchen: TestClient,
    name: str,
    foods: list[dict[str, Any]],
    steps: list[str] | None = None,
    **extra: Any,
) -> dict[str, Any]:
    """A recipe whose ingredient lines say how each is prepared ("1 onion, finely chopped")."""
    lines = [
        {"words": f"1 {f['name'].lower()}, finely chopped", "food_id": f["id"], "amount": 1}
        for f in foods
    ]
    return make(
        kitchen,
        name,
        lines=lines,
        steps=[
            {"text": text} for text in (steps or ["Chop everything.", "Simmer for 10 minutes."])
        ],
        **extra,
    )


def suggest(kitchen: TestClient, **params: Any) -> dict[str, Any]:
    found: dict[str, Any] = ok(kitchen.get(f"{API}/batch-cook/suggestions", params=params))
    return found


def names(found: dict[str, Any]) -> list[str]:
    return [p["name"] for p in found["picks"]]


def cooked(kitchen: TestClient, recipe_id: int, days_ago: int) -> None:
    """The recipe was cooked this many days ago (a batch and its cooked record)."""
    when = utcnow() - timedelta(days=days_ago)
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        batch = BatchCook(
            household_id=1,
            recipe_id=recipe_id,
            recipe_name="x",
            cooked_on=when.date(),
            tub_count=1,
        )
        db.add(batch)
        db.flush()
        db.add(
            CookedRecord(
                household_id=1,
                batch_id=batch.id,
                recipe_id=recipe_id,
                portions=1,
                snapshot={},
                cooked_at=when,
            )
        )
        db.commit()


# --- The preferences, in their order ------------------------------------------------------------


def test_shared_prep_comes_first(kitchen: TestClient) -> None:
    onion, tomato, mango = (food(kitchen, n) for n in ("Onion", "Tomato", "Mango"))
    recipe(kitchen, "Aloo", [mango])
    recipe(kitchen, "Sambar", [onion, tomato])
    recipe(kitchen, "Rasam", [onion, tomato])
    found = suggest(kitchen, count=2)
    assert sorted(names(found)) == ["Rasam", "Sambar"]


def test_shared_prep_beats_use_soon_and_not_cooked_lately(kitchen: TestClient) -> None:
    onion, mango, spinach = (
        food(kitchen, "Onion"),
        food(kitchen, "Mango"),
        fresh(kitchen, "Spinach"),
    )
    stock(kitchen, spinach["id"], 200, "g", use_by=today(kitchen).isoformat())
    a = recipe(kitchen, "A onion curry", [onion])
    b = recipe(kitchen, "B onion dal", [onion])
    recipe(kitchen, "C spinach", [spinach])
    d = recipe(kitchen, "D mango", [mango])
    cooked(kitchen, a["id"], 3)
    cooked(kitchen, b["id"], 3)
    assert d["id"]  # never cooked, but shares nothing
    assert sorted(names(suggest(kitchen, count=2))) == ["A onion curry", "B onion dal"]


def test_use_soon_comes_second(kitchen: TestClient) -> None:
    mango, rice, spinach = food(kitchen, "Mango"), food(kitchen, "Rice"), fresh(kitchen, "Spinach")
    stock(kitchen, spinach["id"], 200, "g", use_by=(today(kitchen) + timedelta(days=2)).isoformat())
    recipe(kitchen, "A mango", [mango])
    recipe(kitchen, "B rice", [rice])
    recipe(kitchen, "C spinach", [spinach])
    found = suggest(kitchen, count=2)
    assert "C spinach" in names(found)
    pick = next(p for p in found["picks"] if p["name"] == "C spinach")
    assert pick["use_soon"] == {"foods": ["Spinach"], "days_left": 2}
    assert "Uses your Use soon spinach" in pick["why"]


def test_not_cooked_in_the_last_14_days_comes_third(kitchen: TestClient) -> None:
    mango, rice, peas, plum = (food(kitchen, n) for n in ("Mango", "Rice", "Peas", "Plum"))
    a = recipe(kitchen, "A mango", [mango])
    recipe(kitchen, "B rice", [rice])
    c = recipe(kitchen, "C peas", [peas])
    d = recipe(kitchen, "D plum", [plum])
    cooked(kitchen, a["id"], 3)  # cooked lately
    cooked(kitchen, c["id"], 15)  # not lately: 15 days ago
    found = suggest(kitchen, count=3)
    assert "A mango" not in names(found) and "D plum" in names(found)
    assert d["id"] and "C peas" in names(found)
    pick = next(p for p in found["picks"] if p["name"] == "B rice")
    assert pick["why"].endswith("not cooked in the last 14 days.")
    # Cooked lately: the same recipe, and no such line.
    again = suggest(kitchen, count=4)
    liked = next(p for p in again["picks"] if p["name"] == "A mango")
    assert "not cooked" not in liked["why"]


def test_what_the_kitchen_can_do_comes_last_and_a_recipe_it_cannot_do_waits(
    kitchen: TestClient,
) -> None:
    rice, peas, plum = (food(kitchen, n) for n in ("Rice", "Peas", "Plum"))
    recipe(kitchen, "A cake", [plum], ["Mix the batter.", "Bake in the oven for 40 minutes."])
    recipe(kitchen, "B rice", [rice])
    recipe(kitchen, "C peas", [peas])
    assert "A cake" in names(suggest(kitchen, count=3))
    ok(kitchen.patch(f"{API}/household/kitchen", json={"oven": False}))
    assert names(suggest(kitchen, count=2)) == ["B rice", "C peas"]
    # With nothing else to pick, it is still offered (the set is filled, not left short).
    assert sorted(names(suggest(kitchen, count=3))) == ["A cake", "B rice", "C peas"]


def test_the_why_line_names_the_shared_prep_the_wait_and_the_other_recipe(
    kitchen: TestClient,
) -> None:
    onion, tomato, leaf = (
        food(kitchen, "Onion"),
        food(kitchen, "Tomato"),
        food(kitchen, "Curry leaf"),
    )
    recipe(
        kitchen,
        "Chicken chettinad",
        [onion, tomato, leaf],
        ["Chop the onion and tomato.", "Marinate the chicken for 30 minutes.", "Fry the masala."],
    )
    recipe(
        kitchen,
        "Sambar",
        [onion, tomato, leaf],
        ["Chop the onion.", "Pressure cook the dal for 3 whistles."],
    )
    found = suggest(kitchen, count=2)
    why = {p["name"]: p["why"] for p in found["picks"]}
    assert why["Chicken chettinad"].startswith(
        "Shares curry leaf, onion and tomato prep with Sambar; waits while you work on the others"
    )
    assert why["Sambar"].startswith(
        "Shares curry leaf, onion and tomato prep with Chicken chettinad; "
        "pressure cooker runs while you chop for the others"
    )


def test_a_recipe_with_nothing_to_say_still_fits_the_kitchen(kitchen: TestClient) -> None:
    for name, ingredient in (("Plain", "Salt"), ("Other", "Rice")):
        made = recipe(kitchen, name, [food(kitchen, ingredient)], ["Stir."])
        cooked(kitchen, made["id"], 1)
    assert [p["why"] for p in suggest(kitchen, count=2)["picks"]] == ["Fits your kitchen."] * 2


def test_a_staple_is_never_shared_prep(kitchen: TestClient) -> None:
    salt = food(kitchen, "Salt", staple=True)
    rice = food(kitchen, "Rice")
    recipe(kitchen, "A", [salt], ["Stir."])
    recipe(kitchen, "B", [salt], ["Stir."])
    recipe(kitchen, "C", [rice], ["Stir."])
    assert all("Shares" not in p["why"] for p in suggest(kitchen, count=3)["picks"])


# --- The times ----------------------------------------------------------------------------------


def _timing(hands: str, minutes: int, equipment: str) -> step_timings.Timing:
    return step_timings.Timing(hands, minutes, equipment, False, False, False)  # type: ignore[arg-type]


KIT = Equipment(hob_rings=4, pressure_cookers=1, oven=True)


def test_waiting_overlaps_and_hands_never_do() -> None:
    a = [_timing("hands", 10, "none"), _timing("waiting", 30, "pressure")]
    b = [_timing("hands", 10, "none"), _timing("waiting", 30, "hob")]
    one_by_one = sum(s.minutes for r in (a, b) for s in r)
    together = together_minutes([a, b], KIT)
    assert one_by_one == 80
    # Both chop (20 min of hands, one after the other), the waits overlap: 10 + 10 + 30.
    assert together == 50


def test_never_more_than_the_kitchen_has() -> None:
    simmer = [_timing("waiting", 20, "hob")]
    one_ring = Equipment(hob_rings=1, pressure_cookers=0, oven=False)
    assert together_minutes([simmer, simmer, simmer], KIT) == 20
    assert together_minutes([simmer, simmer, simmer], one_ring) == 60
    cooker = [_timing("waiting", 20, "pressure")]
    # No pressure cooker: the pot goes on a ring; an oven missing the same.
    assert together_minutes([cooker, cooker], one_ring) == 40
    assert together_minutes([cooker, cooker], Equipment(4, 2, True)) == 20
    assert together_minutes([[_timing("waiting", 20, "oven")]] * 2, KIT) == 40


def test_together_is_never_longer_than_one_by_one() -> None:
    chop = [_timing("hands", 15, "none")]
    assert together_minutes([chop, chop, chop], KIT) == 45
    assert together_minutes([], KIT) == 0


def test_the_times_in_the_answer(kitchen: TestClient) -> None:
    rice, peas = food(kitchen, "Rice"), food(kitchen, "Peas")
    recipe(kitchen, "A", [rice], ["Chop the rice.", "Pressure cook for 20 minutes."])
    recipe(kitchen, "B", [peas], ["Chop the peas.", "Boil for 20 minutes."])
    found = suggest(kitchen, count=2)
    assert found["one_by_one_minutes"] == sum(p["minutes"] for p in found["picks"])
    assert found["together_minutes"] < found["one_by_one_minutes"]
    assert {p["minutes"] for p in found["picks"]} == {25}


# --- Swap, others, the day ---------------------------------------------------------------------


def test_the_same_data_gives_the_same_picks(kitchen: TestClient) -> None:
    for n in range(6):
        recipe(kitchen, f"R{n}", [food(kitchen, f"Food{n}")])
    assert suggest(kitchen) == suggest(kitchen)


def test_swap_keeps_the_others_and_never_offers_the_swapped_one(kitchen: TestClient) -> None:
    for n in range(6):
        recipe(kitchen, f"R{n}", [food(kitchen, f"Food{n}")])
    first = suggest(kitchen, count=3)
    ids = [p["recipe_id"] for p in first["picks"]]
    swapped = suggest(kitchen, count=3, keep=ids[1:], skip=[ids[0]])
    got = [p["recipe_id"] for p in swapped["picks"]]
    assert set(got) >= set(ids[1:]) and ids[0] not in got and len(got) == 3


def test_show_me_others_is_a_fresh_set_while_there_are_others(kitchen: TestClient) -> None:
    for n in range(6):
        recipe(kitchen, f"R{n}", [food(kitchen, f"Food{n}")])
    first = [p["recipe_id"] for p in suggest(kitchen, count=3)["picks"]]
    second = [p["recipe_id"] for p in suggest(kitchen, count=3, skip=first)["picks"]]
    assert not set(first) & set(second) and len(second) == 3
    # Fewer left than asked: the set is filled from the skipped ones, best first.
    third = [p["recipe_id"] for p in suggest(kitchen, count=3, skip=first + second)["picks"]]
    assert len(third) == 3


def test_fewer_recipes_than_asked(kitchen: TestClient) -> None:
    recipe(kitchen, "Only", [food(kitchen, "Rice")])
    found = suggest(kitchen, count=3)
    assert names(found) == ["Only"] and found["pool"] == 1 and found["count"] == 3
    nothing = suggest(kitchen)
    assert nothing["picks"] and nothing["together_minutes"] >= 0


def test_a_recipe_with_no_steps_is_not_offered(kitchen: TestClient) -> None:
    make(kitchen, "No steps")
    assert suggest(kitchen)["picks"] == [] and suggest(kitchen)["pool"] == 0
    assert suggest(kitchen)["together_minutes"] == 0


def test_a_removed_recipe_is_not_offered(kitchen: TestClient) -> None:
    gone = recipe(kitchen, "Gone", [food(kitchen, "Rice")])
    recipe(kitchen, "Here", [food(kitchen, "Peas")])
    ok(kitchen.delete(f"{API}/recipes/{gone['id']}"))
    assert names(suggest(kitchen)) == ["Here"]


def test_the_default_day_is_the_next_day_with_no_cooking_planned(kitchen: TestClient) -> None:
    a = recipe(kitchen, "A", [food(kitchen, "Rice")])
    now = today(kitchen)
    assert suggest(kitchen)["date"] == now.isoformat()
    slots = slot_ids(kitchen)
    plan_recipe(kitchen, a["id"], now, slots["Dinner"])
    found = suggest(kitchen)
    assert found["date"] == (now + timedelta(days=1)).isoformat()
    assert found["free_days"][0] == found["date"] and len(found["free_days"]) == 3
    assert suggest(kitchen, date=D1.isoformat())["date"] == D1.isoformat()
    # A day with only an ingredient planned has no cooking.
    assert (now + timedelta(days=1)).isoformat() in found["free_days"]


def test_the_answer_has_the_kitchen_and_whether_it_was_asked(kitchen: TestClient) -> None:
    recipe(kitchen, "A", [food(kitchen, "Rice")])
    assert suggest(kitchen)["kitchen"] == {
        "hob_rings": 4,
        "pressure_cookers": 1,
        "oven": True,
        "asked": False,
    }
    ok(kitchen.patch(f"{API}/household/kitchen", json={"hob_rings": 2}))
    assert suggest(kitchen)["kitchen"]["asked"] is True


def test_bad_questions_are_refused(kitchen: TestClient) -> None:
    for params in ({"count": 1}, {"count": 5}, {"date": "not a day"}, {"date": "1999-01-01"}):
        assert kitchen.get(f"{API}/batch-cook/suggestions", params=params).status_code == 422


# --- The switch and the other household ---------------------------------------------------------


def test_an_admin_can_hide_batch_cook_and_the_suggestions_are_then_refused(
    kitchen: TestClient,
) -> None:
    assert ok(kitchen.get(f"{API}/household"))["batch_cook"] is True
    assert ok(kitchen.patch(f"{API}/household", json={"batch_cook": False}))["batch_cook"] is False
    refused = kitchen.get(f"{API}/batch-cook/suggestions")
    assert refused.status_code == 409 and refused.json()["code"] == "batch_cook_hidden"
    assert "switched off" in refused.json()["detail"]
    assert ok(kitchen.patch(f"{API}/household", json={"batch_cook": True}))["batch_cook"] is True
    assert kitchen.get(f"{API}/batch-cook/suggestions").status_code == 200


def test_only_an_admin_can_hide_it(kitchen: TestClient) -> None:
    wren = person(kitchen)
    assert wren.patch(f"{API}/household", json={"batch_cook": False}).status_code == 403
    assert ok(kitchen.get(f"{API}/household"))["batch_cook"] is True
    assert wren.get(f"{API}/batch-cook/suggestions").status_code == 200


def test_the_other_households_recipes_are_never_picked_or_kept(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    mine = recipe(kitchen, "Mine", [food(kitchen, "Rice")])
    theirs = recipe(neighbour, "Theirs", [food(neighbour, "Rice")])
    recipe(neighbour, "Theirs too", [food(neighbour, "Peas")])
    found = suggest(kitchen, count=2, keep=[theirs["id"]], skip=[theirs["id"]])
    assert names(found) == ["Mine"] and found["pool"] == 1
    assert names(suggest(neighbour, count=2, keep=[mine["id"]])) == ["Theirs", "Theirs too"]
    assert suggest(neighbour, count=3)["pool"] == 2


def test_it_is_signed_in_only(client: TestClient) -> None:
    assert client.get(f"{API}/batch-cook/suggestions").status_code in (401, 403)


def test_the_pressure_clause_uses_the_mockups_words_and_a_capital_when_first(
    kitchen: TestClient,
) -> None:
    cooker = recipe(kitchen, "Dal", [food(kitchen, "Toor")], ["Pressure cook for 3 whistles."])
    plain = recipe(kitchen, "Rice", [food(kitchen, "Basmati")], ["Stir."])
    for made in (cooker, plain):
        cooked(kitchen, made["id"], 1)
    why = {p["name"]: p["why"] for p in suggest(kitchen, count=2)["picks"]}
    assert why["Dal"] == "Pressure cooker runs while you chop for the others."


# --- Whole-0.8 review fixes (RF3): S3 ------------------------------------------------------------


def test_the_times_of_a_session_read_only_its_own_recipes_and_say_what_the_suggestions_did(
    kitchen: TestClient,
) -> None:
    """S3: `times_for` timed the 2 to 4 chosen recipes by reading every recipe's steps. It reads
    only theirs now, and gives the same minutes as the suggestions for the same recipes."""
    from sqlalchemy import event

    from mealwright import batch_suggest
    from mealwright.api.v1.context import Kitchen
    from mealwright.models import Household, Login

    rice, peas = food(kitchen, "Rice"), food(kitchen, "Peas")
    a = recipe(kitchen, "A", [rice], ["Chop the rice.", "Pressure cook for 20 minutes."])
    b = recipe(kitchen, "B", [peas], ["Chop the peas.", "Boil for 20 minutes."])
    for n in range(5):
        recipe(kitchen, f"Other {n}", [food(kitchen, f"Veg {n}")])
    found = suggest(kitchen, count=2, keep=[a["id"], b["id"]])
    assert {p["recipe_id"] for p in found["picks"]} == {a["id"], b["id"]}
    read: list[str] = []
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        here = Kitchen(
            db=db,
            login=db.query(Login).first(),
            household=db.get(Household, 1),
            idempotency_key=None,
            request="",
        )
        event.listen(db.get_bind(), "before_cursor_execute", lambda *args: read.append(args[2]))
        together, one_by_one = batch_suggest.times_for(here, [a["id"], b["id"]])
    assert (together, one_by_one) == (found["together_minutes"], found["one_by_one_minutes"])
    steps_read = [
        q for q in read if "FROM recipe_step " in q and "recipe_step.recipe_id IN" not in q
    ]
    assert steps_read == []  # every read of steps was narrowed to the chosen recipes


def test_a_steps_guess_is_kept_so_the_next_request_does_not_make_it_again() -> None:
    step_timings.guess.cache_clear()
    first = step_timings.guess("Simmer for 25 minutes.")
    again = step_timings.guess("Simmer for 25 minutes.")
    assert first == again and step_timings.guess.cache_info().hits == 1
