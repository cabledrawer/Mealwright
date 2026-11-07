"""Use by or Best before (0.8, cabledrawer 7 Nov): the default, the locked ones, changing it, and
what each does to Use soon."""

from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from test_pantry import API, add, food, place, today

from mealwright.date_kinds import USE_BY
from mealwright.pack_sizes import table


def kind_of(kitchen: TestClient, food_id: int) -> tuple[str, bool]:
    shown = kitchen.get(f"{API}/foods/{food_id}").json()
    return shown["date_kind"], shown["date_kind_locked"]


def edit(kitchen: TestClient, food_id: int, **body: Any) -> Any:
    return kitchen.patch(f"{API}/foods/{food_id}", json=body)


def soon(kitchen: TestClient) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = kitchen.get(f"{API}/pantry/use-soon").json()["lots"]
    return rows


def test_every_table_row_says_use_by_or_best_before() -> None:
    assert {row.dates for row in table().rows.values()} == {"use by", "best before"}


def test_the_default_comes_from_the_pack_size_table_first(kitchen: TestClient) -> None:
    cupboard = place(kitchen, "Cupboard")
    fridge = place(kitchen, "Fridge")
    # The table says use by (milk) even when it is kept in a cupboard; best before (toor dal)
    # even in the fridge.
    assert kind_of(kitchen, food(kitchen, "Milk", place_id=cupboard)["id"]) == ("use_by", True)
    assert kind_of(kitchen, food(kitchen, "Toor dal", place_id=fridge)["id"]) == (
        "best_before",
        False,
    )
    # Another name of a table row matches too.
    other = food(kitchen, "Thuvaram paruppu")
    kitchen.post(f"{API}/foods/{other['id']}/other-names", json={"name": "toor dal"})
    assert kind_of(kitchen, other["id"]) == ("best_before", False)


def test_with_no_table_row_it_follows_where_it_is_kept(kitchen: TestClient) -> None:
    assert kind_of(
        kitchen, food(kitchen, "Homemade pickle", place_id=place(kitchen, "Fridge"))["id"]
    ) == (
        "use_by",
        False,
    )
    assert kind_of(
        kitchen, food(kitchen, "Odd tin", place_id=place(kitchen, "Cupboard"))["id"]
    ) == (
        "best_before",
        False,
    )
    assert kind_of(
        kitchen, food(kitchen, "Odd bottle", place_id=place(kitchen, "Spice rack"))["id"]
    ) == (
        "best_before",
        False,
    )
    assert kind_of(kitchen, food(kitchen, "Odd thing")["id"]) == ("best_before", False)


def test_only_meat_fish_and_chilled_dairy_are_locked_to_use_by(kitchen: TestClient) -> None:
    for name in ("Chicken breast", "Milk", "Paneer", "Salmon", "Double cream"):
        item = food(kitchen, name, place_id=place(kitchen, "Cupboard"))
        assert kind_of(kitchen, item["id"]) == ("use_by", True), name
    chicken = food(kitchen, "Chicken thighs")
    refused = edit(kitchen, chicken["id"], date_kind="best_before")
    assert refused.status_code == 422
    assert refused.json()["code"] == "date_kind_locked"
    assert kind_of(kitchen, chicken["id"]) == ("use_by", True)


def test_other_use_by_rows_start_use_by_but_can_be_switched(kitchen: TestClient) -> None:
    for name in ("Idli batter", "Tofu", "Spinach"):
        # Idli batter is put in the Dairy aisle: still not chilled dairy.
        item = food(kitchen, name, aisle="dairy" if name == "Idli batter" else "veg_fruit")
        assert table().match(name).dates == "use by"  # type: ignore[union-attr]
        assert kind_of(kitchen, item["id"]) == ("use_by", False), name
        switched = edit(kitchen, item["id"], date_kind="best_before")
        assert switched.status_code == 200, name
        assert kind_of(kitchen, item["id"]) == ("best_before", False), name


def test_butter_and_eggs_are_best_before_and_switchable(kitchen: TestClient) -> None:
    for name in ("Butter", "Eggs"):
        item = food(kitchen, name)
        assert kind_of(kitchen, item["id"]) == ("best_before", False), name
        assert edit(kitchen, item["id"], date_kind="use_by").status_code == 200
        assert kind_of(kitchen, item["id"]) == ("use_by", False), name


def test_a_dairy_aisle_food_with_no_table_row_is_not_locked(kitchen: TestClient) -> None:
    for name, aisle in (("Cave cheese", "dairy"), ("Mystery steak", "meat_fish")):
        item = food(kitchen, name, aisle=aisle)
        assert table().match(name) is None
        assert kind_of(kitchen, item["id"])[1] is False, name
        assert edit(kitchen, item["id"], date_kind="use_by").status_code == 200
        assert edit(kitchen, item["id"], date_kind="best_before").status_code == 200


def test_it_can_be_changed_and_undone(kitchen: TestClient) -> None:
    pickle = food(kitchen, "Homemade pickle", place_id=place(kitchen, "Cupboard"))
    changed = edit(kitchen, pickle["id"], date_kind="use_by")
    assert changed.status_code == 200
    assert changed.json()["change"]["summary"] == "Homemade pickle is now Use by"
    assert kind_of(kitchen, pickle["id"]) == ("use_by", False)
    # The choice is kept when it is moved to a place that would give the other default.
    edit(kitchen, pickle["id"], place_id=place(kitchen, "Fridge"))
    edit(kitchen, pickle["id"], place_id=place(kitchen, "Cupboard"))
    assert kind_of(kitchen, pickle["id"]) == ("use_by", False)
    assert edit(kitchen, pickle["id"], date_kind="use_by").json()["change"] is None
    back = kitchen.post(f"{API}/changes/{changed.json()['change']['id']}/undo")
    assert back.status_code == 200, back.text
    assert kind_of(kitchen, pickle["id"]) == ("best_before", False)


def test_setting_the_default_again_changes_nothing(kitchen: TestClient) -> None:
    jar = food(kitchen, "Odd jar", place_id=place(kitchen, "Cupboard"))
    again = edit(kitchen, jar["id"], date_kind="best_before")
    assert again.status_code == 200
    assert again.json()["change"] is None


def test_a_bad_date_type_is_refused(kitchen: TestClient) -> None:
    jar = food(kitchen, "Odd jar")
    assert edit(kitchen, jar["id"], date_kind="whenever").status_code == 422
    assert edit(kitchen, jar["id"], date_kind=None).status_code == 422


def test_a_lot_and_its_group_carry_the_date_type(kitchen: TestClient) -> None:
    day = today(kitchen)
    milk = food(kitchen, "Milk")
    body = add(kitchen, milk["id"], 1, "l", use_by=str(day + timedelta(days=5)))
    [group] = body["groups"]
    assert group["date_kind"] == "use_by"
    assert [lot["date_kind"] for lot in group["lots"]] == ["use_by"]


def test_use_soon_counts_a_best_before_date_only_once_it_has_passed(kitchen: TestClient) -> None:
    day = today(kitchen)
    dal = food(kitchen, "Toor dal")  # best before
    milk = food(kitchen, "Milk")  # use by
    for item in (dal, milk):
        for days in (-3, 0, 2, 9):
            add(kitchen, item["id"], 100, "g", use_by=str(day + timedelta(days=days)))
    rows = soon(kitchen)
    # Milk: one row for the three Use by dates that are soon, dated by the soonest.
    milk_row = next(r for r in rows if r["food"]["name"] == "Milk")
    assert (milk_row["days_left"], milk_row["lots_count"], milk_row["date_kind"]) == (
        -3,
        3,
        "use_by",
    )
    # Toor dal: only the passed one counts, so one packet, and it says Best before.
    dal_row = next(r for r in rows if r["food"]["name"] == "Toor dal")
    assert (dal_row["days_left"], dal_row["lots_count"], dal_row["date_kind"]) == (
        -3,
        1,
        "best_before",
    )
    shown = kitchen.get(f"{API}/pantry").json()
    groups = {g["food"]["name"]: g for p in shown["places"] for g in p["groups"]}
    assert [lot["use_soon"] for lot in groups["Toor dal"]["lots"]] == [True, False, False, False]
    assert [lot["use_soon"] for lot in groups["Milk"]["lots"]] == [True, True, True, False]
    assert shown["counts"]["use_soon"] == 2  # one row each


def test_a_best_before_packet_not_yet_passed_is_not_use_soon(kitchen: TestClient) -> None:
    day = today(kitchen)
    dal = food(kitchen, "Toor dal")
    add(kitchen, dal["id"], 100, "g", use_by=str(day + timedelta(days=1)))
    assert soon(kitchen) == []
    assert kitchen.get(f"{API}/pantry").json()["counts"]["use_soon"] == 0
    filtered = kitchen.get(f"{API}/pantry", params={"filter": "use_soon"}).json()
    assert all(p["groups"] == [] for p in filtered["places"])


def test_a_frozen_packet_has_the_freezers_date_and_its_old_use_by_no_longer_counts(
    kitchen: TestClient,
) -> None:
    day = today(kitchen)
    paneer = food(kitchen, "Paneer", place_id=place(kitchen, "Fridge"))
    lot = add(kitchen, paneer["id"], 200, "g", use_by=str(day))["groups"][0]["lots"][0]
    assert [r["place"]["name"] for r in soon(kitchen)] == ["Fridge"]
    kitchen.post(f"{API}/stock/{lot['id']}/to-freezer")
    assert soon(kitchen) == []  # the freezer life is months away
    assert kind_of(kitchen, paneer["id"])[0] == USE_BY
