"""A "Who's this?" pick goes on while the tablet is used, not only while changes are saved
(Pe5)."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import API, db, ok, person

from mealwright.models import Session, utcnow


def _tablet_with_joss_picked(kitchen: TestClient) -> tuple[TestClient, int]:
    tablet = person(kitchen, name="Kitchen tablet", username="tablet")
    people = ok(kitchen.get(f"{API}/people"))["people"]
    tablet_id = next(p["id"] for p in people if p["name"] == "Kitchen tablet")
    ok(kitchen.patch(f"{API}/people/{tablet_id}", json={"shared": True}))
    ok(kitchen.put(f"{API}/people/ask-whos-this", json={"on": True}))
    ok(kitchen.post(f"{API}/people", json={"name": "Joss"}), 201)
    people = ok(kitchen.get(f"{API}/people"))["people"]
    joss = next(p["id"] for p in people if p["name"] == "Joss")
    ok(tablet.put(f"{API}/whos-this", json={"member_id": joss}))
    return tablet, joss


def _set_pick_age(kitchen: TestClient, minutes: float) -> None:
    with db(kitchen) as session:
        for row in session.scalars(select(Session).where(Session.member_id.is_not(None))):
            row.picked_at = utcnow() - timedelta(minutes=minutes)
            row.last_seen_at = utcnow()
        session.commit()


def _picked_ago(kitchen: TestClient) -> timedelta:
    with db(kitchen) as session:
        row = session.scalars(select(Session).where(Session.member_id.is_not(None))).one()
        picked = row.picked_at
        assert picked is not None
        return utcnow() - (picked if picked.tzinfo else picked.replace(tzinfo=utcnow().tzinfo))


def test_reading_on_the_tablet_keeps_the_pick_going(kitchen: TestClient) -> None:
    tablet, _ = _tablet_with_joss_picked(kitchen)
    _set_pick_age(kitchen, 25)
    ok(tablet.get(f"{API}/recipes"))  # only looking: no change saved
    assert _picked_ago(kitchen) < timedelta(minutes=1)


def test_a_pick_that_has_already_run_out_is_not_brought_back_by_reading(
    kitchen: TestClient,
) -> None:
    tablet, _ = _tablet_with_joss_picked(kitchen)
    _set_pick_age(kitchen, 31)
    ok(tablet.get(f"{API}/recipes"))
    assert _picked_ago(kitchen) > timedelta(minutes=30)
    ok(tablet.patch(f"{API}/household", json={"cook_per_step": True}))
    who = ok(kitchen.get(f"{API}/changes"))["changes"][0]["who"]
    assert who["name"] == "Kitchen tablet" and who["member_id"] is None
