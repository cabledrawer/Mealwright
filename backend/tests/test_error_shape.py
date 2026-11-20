"""Every error answer is `{detail, code}`: one status and one code per situation (0.9.5-beta.3,
D2; docs/dev/api-endpoints.md section 1.1)."""

import re
from datetime import timedelta
from typing import Any

from conftest import ADMIN, SETUP_CODE
from fastapi.testclient import TestClient
from sqlalchemy import update

from mealwright.errors import (
    ALREADY_SET_UP,
    CANT_DO_HERE,
    NOTHING_TO_CHANGE,
    ONE_FIELD,
    OTHER_SITE,
    SIGN_IN,
)
from mealwright.history import too_old_sentence
from mealwright.models import Change, Household, utcnow

API = "/api/v1"


def _problem(answer: Any, status: int, code: str) -> dict[str, Any]:
    assert answer.status_code == status, answer.text
    body = answer.json()
    assert body["code"] == code
    assert isinstance(body["detail"], str | list) and body["detail"]
    return body


def test_signed_out_is_one_code_everywhere(client: TestClient) -> None:
    for path in ("/me", "/foods", "/events"):
        body = _problem(client.get(f"{API}{path}"), 401, "signed_out")
        assert body["detail"] == SIGN_IN


def test_a_wrong_sign_in_has_a_code_and_never_says_which_was_wrong(client: TestClient) -> None:
    client.post(f"{API}/setup", json={**ADMIN, "setup_code": SETUP_CODE})
    client.delete(f"{API}/session")
    wrong = client.post(f"{API}/session", json={"username": ADMIN["username"], "password": "x"})
    unknown = client.post(f"{API}/session", json={"username": "nobody", "password": "x"})
    assert _problem(wrong, 401, "wrong_sign_in") == _problem(unknown, 401, "wrong_sign_in")


def test_setting_up_twice_and_another_site(kitchen: TestClient) -> None:
    again = kitchen.post(f"{API}/setup", json={**ADMIN, "setup_code": SETUP_CODE})
    assert _problem(again, 409, "already_set_up")["detail"] == ALREADY_SET_UP
    other = kitchen.post(
        f"{API}/foods", json={"name": "Toor dal"}, headers={"origin": "https://elsewhere.test"}
    )
    assert _problem(other, 403, "other_site")["detail"] == OTHER_SITE


def test_fastapis_own_errors_have_the_shape_too(kitchen: TestClient) -> None:
    missing = _problem(kitchen.get(f"{API}/no-such-thing"), 404, "not_found")
    assert missing["detail"] == "That isn’t here any more."
    wrong_method = _problem(kitchen.put(f"{API}/foods"), 405, "cant_do_here")
    assert wrong_method["detail"] == CANT_DO_HERE
    invalid = _problem(kitchen.post(f"{API}/foods", json={}), 422, "invalid")
    assert {"type", "loc", "msg"} <= set(invalid["detail"][0])


def test_a_new_thing_with_a_used_name_is_one_code_carrying_the_one_there_is(
    kitchen: TestClient,
) -> None:
    """BE1: "+ New" with a name the household already has (ignoring case) is refused the same
    way everywhere: 409 `name_taken`, carrying what already has the name."""
    food = kitchen.post(f"{API}/foods", json={"name": "Toor dal"}).json()["food"]
    again = _problem(kitchen.post(f"{API}/foods", json={"name": "toor DAL"}), 409, "name_taken")
    assert again["food_id"] == food["id"]

    place = kitchen.post(f"{API}/places", json={"name": "Garage", "kind": "cupboard"}).json()
    again = kitchen.post(f"{API}/places", json={"name": "garage", "kind": "fridge"})
    assert _problem(again, 409, "name_taken")["place"] == place

    shop = kitchen.post(f"{API}/shops", json={"name": "Aldi"}).json()
    again = _problem(kitchen.post(f"{API}/shops", json={"name": "ALDI"}), 409, "name_taken")
    assert again["shop"] == {"id": shop["id"], "name": "Aldi"}

    slot = kitchen.post(f"{API}/meal-slots", json={"name": "Elevenses"}).json()
    again = kitchen.post(f"{API}/meal-slots", json={"name": "elevenses"})
    assert _problem(again, 409, "name_taken")["slot"] == {"id": slot["id"], "name": "Elevenses"}

    kitchen.post(f"{API}/people", json={"name": "Asha"})
    again = _problem(kitchen.post(f"{API}/people", json={"name": "asha"}), 409, "name_taken")
    assert again["member"]["name"] == "Asha"


def test_a_move_or_change_to_where_it_already_is_is_one_code(kitchen: TestClient) -> None:
    """BE2: asking for what is already so (a packet into the place it is in, or into the freezer
    it is in, an amount it already has, a name the ingredient already has) is 409
    `already_there`; a meal moved to its own slot too (test_today.py)."""
    food = kitchen.post(f"{API}/foods", json={"name": "Spinach"}).json()["food"]
    url = f"{API}/foods/{food['id']}"
    body = {"food_id": food["id"], "amount": {"amount": 200, "unit": "g"}}
    added = kitchen.post(f"{API}/stock", json=body)
    assert added.status_code == 201, added.text
    [group] = added.json()["groups"]
    lot = group["lots"][0]
    here = kitchen.post(f"{API}/stock/{lot['id']}/move", json={"place_id": group["place"]["id"]})
    assert _problem(here, 409, "already_there")["detail"].startswith("That’s already in ")
    same = kitchen.post(f"{url}/set-left", json={"amount": {"amount": 200, "unit": "g"}})
    assert _problem(same, 409, "already_there")["detail"] == "That’s how much there is already."
    kitchen.post(f"{API}/stock/{lot['id']}/freeze")
    frozen = kitchen.post(f"{API}/stock/{lot['id']}/freeze")
    assert _problem(frozen, 409, "already_there")["detail"] == "That’s already in the freezer."
    named = kitchen.post(f"{url}/other-names", json={"name": "spinach"})
    assert _problem(named, 409, "already_there")["detail"] == "Spinach already has that name."


def test_too_late_to_undo_is_one_sentence_with_the_households_window(kitchen: TestClient) -> None:
    """BE7: one "too late" sentence, built from the household's own undo window."""
    change = kitchen.post(f"{API}/foods", json={"name": "Toor dal"}).json()["change"]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.execute(update(Household).values(undo_days=14))
        db.execute(
            update(Change).where(Change.id == change["id"]).values(at=utcnow() - timedelta(days=15))
        )
        db.commit()
    late = _problem(kitchen.post(f"{API}/changes/{change['id']}/undo"), 410, "too_old")
    assert late["detail"] == "Too late to undo: changes can be undone for 14 days."
    assert too_old_sentence(1) == "Too late to undo: changes can be undone for 1 day."


def test_nothing_sent_is_one_of_two_codes(kitchen: TestClient) -> None:
    """BE26: a request with nothing to change is 422 `nothing_to_change`; one that must carry
    exactly one field is 422 `one_field`."""
    slot = kitchen.post(f"{API}/meal-slots", json={"name": "Elevenses"}).json()
    empty = _problem(
        kitchen.patch(f"{API}/meal-slots/{slot['id']}", json={}), 422, "nothing_to_change"
    )
    assert empty["detail"] == NOTHING_TO_CHANGE
    food = kitchen.post(f"{API}/foods", json={"name": "Toor dal"}).json()["food"]
    two = kitchen.patch(f"{API}/foods/{food['id']}", json={"name": "Dal", "staple": True})
    assert _problem(two, 422, "one_field")["detail"] == ONE_FIELD
    blank = kitchen.post(f"{API}/recipes/import", json={"text": "  "})
    assert (
        _problem(blank, 422, "nothing_to_change")["detail"] == "Paste a link or the recipe’s text."
    )


# Routes the walk leaves out: signing out ends the walk's own sign-in, and the live stream
# never ends while signed in (it is walked signed out, above, where it answers 401).
_NOT_WALKED = {("DELETE", "/api/v1/session"), ("GET", "/api/v1/events")}


def _walk(client: TestClient) -> tuple[int, list[str]]:
    """Send every route of the API a request it must refuse (ids that aren't there, an empty
    body) and list every refusal that isn't `{detail, code}`."""
    refused, wrong = 0, []
    paths = client.app.openapi()["paths"]  # type: ignore[attr-defined]
    for path, operations in paths.items():
        for method in sorted(m.upper() for m in operations):
            if (method, path) in _NOT_WALKED:
                continue
            url = re.sub(r"\{[^}]+\}", "999999", path)
            body = {} if method in {"POST", "PUT", "PATCH"} else None
            answer = client.request(method, url, json=body)
            if answer.status_code < 400:
                continue
            refused += 1
            try:
                shown = answer.json()
            except ValueError:
                shown = None
            if not (isinstance(shown, dict) and shown.get("code") and shown.get("detail")):
                wrong.append(f"{method} {path}: {answer.status_code} {answer.text[:80]}")
    return refused, wrong


def test_every_route_refuses_with_a_detail_and_a_code(client: TestClient) -> None:
    """D2 point 2: walk every /api/v1 route signed out, then as an admin of a set-up
    household, and check that every refusal is a Problem with a `code`."""
    refused, wrong = _walk(client)
    assert wrong == []
    assert refused > 150  # every route but the open few refuses someone signed out
    client.post(f"{API}/setup", json={**ADMIN, "setup_code": SETUP_CODE})
    refused, wrong = _walk(client)
    assert wrong == []
    assert refused > 100  # no such ids, empty bodies


def test_a_replay_is_200_whichever_route_answers_it(kitchen: TestClient) -> None:
    """BE15: a request sent again with the same `Idempotency-Key` makes nothing new, so it
    answers 200 with `Idempotent-Replayed: true`, even from a route whose first answer is 201."""
    for path, body in (("/shops", {"name": "Aldi"}), ("/people", {"name": "Asha"})):
        key = {"Idempotency-Key": f"5f0c4c1e-0000-4000-8000-00000000000{len(path)}"}
        first = kitchen.post(f"{API}{path}", json=body, headers=key)
        assert first.status_code == 201, first.text
        assert "idempotent-replayed" not in first.headers
        again = kitchen.post(f"{API}{path}", json=body, headers=key)
        assert again.status_code == 200, again.text
        assert again.headers["idempotent-replayed"] == "true"
        # The same answer; the change's time is left out (a replay reads it back from the
        # database, without its zone).
        assert {**again.json(), "change": None} == {**first.json(), "change": None}
