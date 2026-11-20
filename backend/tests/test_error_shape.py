"""Every error answer is `{detail, code}`: one status and one code per situation (0.9.5-beta.3,
D2; docs/dev/api-endpoints.md section 1.1)."""

from typing import Any

from conftest import ADMIN, SETUP_CODE
from fastapi.testclient import TestClient

from mealwright.errors import ALREADY_SET_UP, CANT_DO_HERE, OTHER_SITE, SIGN_IN

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
