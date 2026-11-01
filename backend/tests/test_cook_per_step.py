"""Cook mode's per-step ingredients switch as a household setting (0.7 K4; cabledrawer 1 Nov).
Off by default; once on it stays on for the household. Proposed, for cabledrawer: any signed-in
person of the household may change it (it changes only what Cook mode shows), while the pint
stays admins only."""

from fastapi.testclient import TestClient
from sync_kit import ok, person

from mealwright.models import Household

API = "/api/v1"


def test_it_starts_off_and_shows_in_the_household(kitchen: TestClient) -> None:
    assert ok(kitchen.get(f"{API}/household"))["cook_per_step"] is False


def test_an_admin_can_switch_it_on_and_it_stays(kitchen: TestClient) -> None:
    changed = ok(kitchen.patch(f"{API}/household", json={"cook_per_step": True}))
    assert changed["cook_per_step"] is True
    assert ok(kitchen.get(f"{API}/household"))["cook_per_step"] is True
    assert ok(kitchen.patch(f"{API}/household", json={}))["cook_per_step"] is True


def test_a_member_can_change_it_but_still_not_the_pint(kitchen: TestClient) -> None:
    wren = person(kitchen)
    assert ok(wren.patch(f"{API}/household", json={"cook_per_step": True}))["cook_per_step"]
    assert ok(kitchen.get(f"{API}/household"))["cook_per_step"] is True
    refused = wren.patch(f"{API}/household", json={"pints": "us"})
    assert refused.status_code == 403
    assert refused.json()["code"] == "admins_only"
    both = wren.patch(f"{API}/household", json={"pints": "us", "cook_per_step": False})
    assert both.status_code == 403
    assert ok(kitchen.get(f"{API}/household"))["pints"] == "uk"
    assert ok(kitchen.get(f"{API}/household"))["cook_per_step"] is True


def test_only_true_or_false_is_taken(kitchen: TestClient) -> None:
    for value in ("yes", [1], {"a": 1}):
        body = {"cook_per_step": value}
        assert kitchen.patch(f"{API}/household", json=body).status_code == 422
    assert ok(kitchen.get(f"{API}/household"))["cook_per_step"] is False


def test_one_household_changing_it_never_changes_anothers(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    ok(kitchen.patch(f"{API}/household", json={"cook_per_step": True}))
    assert ok(neighbour.get(f"{API}/household"))["cook_per_step"] is False
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        found = [h.cook_per_step for h in db.query(Household).order_by(Household.id)]
    assert found == [True, False]


def test_signed_out_cannot_change_it(client: TestClient) -> None:
    assert client.patch(f"{API}/household", json={"cook_per_step": True}).status_code == 401
