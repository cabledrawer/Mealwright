"""Full Onboarding (0.9 U2; spec "Layout decisions": Onboarding, section 2 "Onboarding"): whether
the household has finished or skipped it is stored once, per household, on the server."""

from fastapi.testclient import TestClient
from sync_kit import API, ok, person
from test_settings_lists import latest, member, undo  # noqa: F401 (member is a fixture)


def test_a_fresh_install_has_not_finished_onboarding(kitchen: TestClient) -> None:
    assert ok(kitchen.get(f"{API}/household"))["onboarding_done"] is False


def test_finishing_onboarding_is_kept_for_the_whole_household(kitchen: TestClient) -> None:
    before = ok(kitchen.get(f"{API}/changes"))
    assert ok(kitchen.patch(f"{API}/household", json={"onboarding_done": True}))["onboarding_done"]
    assert ok(kitchen.get(f"{API}/household"))["onboarding_done"] is True
    # Anyone else in the household, a second admin too, sees it done: it never shows again.
    wren = person(kitchen)
    assert ok(wren.get(f"{API}/household"))["onboarding_done"] is True
    # Nothing to undo, so nothing in Recent changes.
    assert ok(kitchen.get(f"{API}/changes"))["changes"] == before["changes"]
    # Sending it again changes nothing.
    assert ok(kitchen.patch(f"{API}/household", json={"onboarding_done": True}))["onboarding_done"]


def test_onboarding_cannot_be_opened_again(kitchen: TestClient) -> None:
    ok(kitchen.patch(f"{API}/household", json={"onboarding_done": True}))
    r = kitchen.patch(f"{API}/household", json={"onboarding_done": False})
    assert r.status_code == 422, r.text
    assert ok(kitchen.get(f"{API}/household"))["onboarding_done"] is True


def test_each_household_has_its_own(kitchen: TestClient, neighbour: TestClient) -> None:
    ok(kitchen.patch(f"{API}/household", json={"onboarding_done": True}))
    assert ok(neighbour.get(f"{API}/household"))["onboarding_done"] is False


# --- Amounts (Onboarding's Amounts step and Settings › Amounts are the same setting) -----------


def test_amounts_start_as_written_and_the_choice_is_kept(kitchen: TestClient) -> None:
    assert ok(kitchen.get(f"{API}/household"))["amounts_shown"] == "as_written"
    assert (
        ok(kitchen.patch(f"{API}/household", json={"amounts_shown": "metric"}))["amounts_shown"]
        == "metric"
    )
    assert ok(kitchen.get(f"{API}/household"))["amounts_shown"] == "metric"


def test_cups_are_not_a_choice_before_1_0(kitchen: TestClient) -> None:
    for wrong in ("cups", "us", "", None):
        r = kitchen.patch(f"{API}/household", json={"amounts_shown": wrong})
        if wrong is None:
            assert ok(r)["amounts_shown"] == "as_written"  # nothing sent, nothing changed
        else:
            assert r.status_code == 422, (wrong, r.text)
    assert ok(kitchen.get(f"{API}/household"))["amounts_shown"] == "as_written"


def test_amounts_are_in_recent_changes_and_only_an_admin_changes_or_undoes_them(
    member: TestClient,  # noqa: F811
    kitchen: TestClient,
) -> None:
    refused = member.patch(f"{API}/household", json={"amounts_shown": "metric"})
    assert refused.status_code == 403, refused.text
    ok(kitchen.patch(f"{API}/household", json={"amounts_shown": "metric"}))
    top = latest(kitchen)
    assert top["kind"] == "amounts_shown_changed"
    assert top["summary"] == "Changed amounts to grams and ml (was as the recipe says)"
    assert top["can_undo"] is True
    assert latest(member)["can_undo"] is False
    assert undo(member, top).status_code == 403
    assert ok(undo(kitchen, top))["result"] == "done"
    assert ok(kitchen.get(f"{API}/household"))["amounts_shown"] == "as_written"
    # Saving the choice it already is records nothing.
    before = len(ok(kitchen.get(f"{API}/changes"))["changes"])
    ok(kitchen.patch(f"{API}/household", json={"amounts_shown": "as_written"}))
    assert len(ok(kitchen.get(f"{API}/changes"))["changes"]) == before


def test_a_stale_amounts_change_cannot_be_undone(kitchen: TestClient) -> None:
    ok(kitchen.patch(f"{API}/household", json={"amounts_shown": "metric"}))
    first = latest(kitchen)
    ok(kitchen.patch(f"{API}/household", json={"amounts_shown": "as_written"}))
    refused = undo(kitchen, first)
    assert refused.status_code == 409 and refused.json()["code"] == "cannot_undo"
    assert ok(kitchen.get(f"{API}/household"))["amounts_shown"] == "as_written"


def test_another_households_amounts_are_their_own(
    kitchen: TestClient, neighbour: TestClient
) -> None:
    ok(neighbour.patch(f"{API}/household", json={"amounts_shown": "metric"}))
    assert ok(kitchen.get(f"{API}/household"))["amounts_shown"] == "as_written"
    assert undo(kitchen, latest(neighbour)).status_code == 404
