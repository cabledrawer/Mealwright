"""Invisible control characters are refused in every name someone types, new and old
(security audit, 19 Oct): tabs and line breaks in a one-line field, and anything that
shows nothing or flips the order text is drawn in. One shared check, in mealwright.names.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sync_kit import action, new_id, ok, send

from mealwright.names import has_hidden, one_line, text_block

API = "/api/v1"

# What gets refused: a tab, a line break, NUL, an escape, a zero-width space, a
# right-to-left override, a byte-order mark, a line separator.
BAD = ["Toor\tdal", "Toor\ndal", "Toor\x00dal", "Toor\x1bdal", "Toor\u200bdal", "Toor\u202edal"]
BAD += ["\ufeffToor", "Toor\u2028dal", "Toor\rdal"]


def refused(response: Any) -> None:
    assert response.status_code == 422, response.text
    assert "hidden character" in response.text or "tab" in response.text, response.text


def test_the_shared_check() -> None:
    for text in BAD:
        assert has_hidden(text), repr(text)
        with pytest.raises(ValueError, match="hidden character"):
            one_line(text)
    # Plain text, accents, Tamil with its joiners, emoji with a joiner: all fine.
    for fine in ["Toor dal", "Jalapeño", "துவரம் பருப்பு", "ക്ക് ", "👩\u200d🍳 chef", "½ cup"]:
        assert not has_hidden(fine), repr(fine)
        assert one_line(fine) == fine


def test_text_blocks_may_keep_their_line_breaks() -> None:
    assert text_block("Fry.\nAdd salt.") == "Fry.\nAdd salt."
    assert text_block("Fry.\r\nAdd salt.") == "Fry.\nAdd salt."
    for bad in ["Fry\tit", "Fry\x00", "Fry\u202e", "Fry\rit", "Fry\u2028it"]:
        with pytest.raises(ValueError, match="hidden character"):
            text_block(bad)


@pytest.mark.parametrize("bad", BAD)
def test_ingredient_names_refuse_hidden_characters(kitchen: TestClient, bad: str) -> None:
    refused(kitchen.post(f"{API}/foods", json={"name": bad}))
    food = ok(kitchen.post(f"{API}/foods", json={"name": "Toor dal"}), 201)["food"]
    url = f"{API}/foods/{food['id']}"
    refused(kitchen.patch(url, json={"name": bad}))  # renaming an old name
    refused(kitchen.patch(url, json={"count_word": bad}))
    refused(kitchen.post(f"{url}/other-names", json={"name": bad}))
    refused(kitchen.post(f"{url}/sizes", json={"name": bad, "amount": 500}))
    # Nothing was stored.
    assert ok(kitchen.get(url))["name"] == "Toor dal"
    assert ok(kitchen.get(url))["other_names"] == []
    assert ok(kitchen.get(url))["sizes"] == []


def test_size_names_and_answers_refuse_hidden_characters(kitchen: TestClient) -> None:
    food = ok(kitchen.post(f"{API}/foods", json={"name": "Toor dal"}), 201)["food"]
    url = f"{API}/foods/{food['id']}"
    size = ok(kitchen.post(f"{url}/sizes", json={"name": "packet", "amount": 500}), 201)
    size_id = size["food"]["sizes"][0]["id"]
    refused(kitchen.patch(f"{url}/sizes/{size_id}", json={"name": "pack\tet"}))
    answer = {"kind": "size", "food_id": food["id"], "name": "lo\naf", "amount": 20}
    stock = {"food_id": food["id"], "amount": {"amount": 1, "unit": "loaf", "answers": [answer]}}
    refused(kitchen.post(f"{API}/stock", json=stock))


def test_whitespace_only_rename_is_a_plain_422_not_a_crash(kitchen: TestClient) -> None:
    food = ok(kitchen.post(f"{API}/foods", json={"name": "Toor dal"}), 201)["food"]
    response = kitchen.patch(f"{API}/foods/{food['id']}", json={"name": "   "})
    assert response.status_code == 422, response.text


def test_shop_and_list_names_refuse_hidden_characters(kitchen: TestClient) -> None:
    refused(kitchen.post(f"{API}/shops", json={"name": "Spice\tBazaar"}))
    refused(kitchen.post(f"{API}/shopping/lists", json={"name": "Party\nlist"}))
    made = ok(kitchen.post(f"{API}/shopping/lists", json={"name": "Party"}), 201)
    list_id = made["shopping_list"]["id"]
    refused(kitchen.patch(f"{API}/shopping/lists/{list_id}", json={"name": "Par\u200bty"}))
    assert [s["name"] for s in ok(kitchen.get(f"{API}/shops"))] == []


def test_the_offline_queue_refuses_hidden_characters_in_names(kitchen: TestClient) -> None:
    answer = send(kitchen, action("create_list", list_id=new_id(), name="Par\tty"))
    result = answer["results"][0]
    assert result["status"] == "refused" and result["reason"] == "bad_action", result
    assert "hidden character" in result["message"] or "tab" in result["message"]


def test_your_name_at_set_up_refuses_hidden_characters(client: TestClient) -> None:
    body = {"name": "Kri\tshna", "username": "tess", "password": "correct horse battery"}
    refused(client.post(f"{API}/setup", json=body))
    body["name"] = "Tess"
    assert client.post(f"{API}/setup", json=body).status_code == 201


def test_old_names_still_read_fine(kitchen: TestClient) -> None:
    """A name stored before the check keeps working; only writing a new one is checked."""
    from mealwright.models import Food

    food = ok(kitchen.post(f"{API}/foods", json={"name": "Toor dal"}), 201)["food"]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.get(Food, food["id"]).name = "Old\tname"  # type: ignore[union-attr]
        db.commit()
    assert ok(kitchen.get(f"{API}/foods/{food['id']}"))["name"] == "Old\tname"
    # Renaming it to something clean works; to something with a hidden character doesn't.
    refused(kitchen.patch(f"{API}/foods/{food['id']}", json={"name": "New\tname"}))
    assert ok(kitchen.patch(f"{API}/foods/{food['id']}", json={"name": "New name"}))["food"]
