"""Numbers too big for the database are refused, never a server error (security audit, 0.4).

SQLite stores whole numbers up to 2^63 - 1. A bigger ID or cursor used to reach the
database and fail with a 500 there; in a sync batch it failed the whole batch instead of
refusing just that change.
"""

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sync_kit import action, main_id, new_id, send

API = "/api/v1"
HUGE = 10**30


@pytest.fixture
def quiet_client(kitchen: TestClient) -> TestClient:
    """The same app, but a server error comes back as a 500 rather than raising."""
    quiet = TestClient(kitchen.app, base_url="https://testserver", raise_server_exceptions=False)
    quiet.cookies = kitchen.cookies
    return quiet


@pytest.mark.parametrize(
    ("method", "url", "body"),
    [
        ("GET", f"{API}/foods/{HUGE}", None),
        ("PATCH", f"{API}/foods/{HUGE}", {"staple": True}),
        ("POST", f"{API}/changes/{HUGE}/undo", None),
        ("GET", f"{API}/changes?before={HUGE}", None),
        ("GET", f"{API}/changes?food_id={HUGE}", None),
        ("POST", f"{API}/foods", {"name": "Butter", "place_id": HUGE}),
        ("POST", f"{API}/foods", {"name": "Butter", "shop_id": HUGE}),
        ("POST", f"{API}/stock/{HUGE}/used", {}),
        ("DELETE", f"{API}/conversions/{HUGE}", None),
    ],
)
def test_a_huge_number_is_refused(
    kitchen: TestClient, quiet_client: TestClient, method: str, url: str, body: Any
) -> None:
    response = quiet_client.request(method, url, json=body)
    assert response.status_code in {404, 422}, (url, response.status_code, response.text)
    assert response.json().get("code") in {"bad_number", "not_found"}, response.text


ITEM = "00000000-0000-4000-8000-000000000001"


@pytest.mark.parametrize(
    "fields",
    [
        {"kind": "tick", "item_id": ITEM, "seen": HUGE},
        {"kind": "dismiss_note", "note_id": HUGE},
        {"kind": "answer_double_tick", "question_id": HUGE, "answer": "two"},
        {"kind": "add", "item_id": ITEM, "food_id": HUGE},
        {"kind": "add", "item_id": ITEM, "food_id": 1, "size_id": HUGE},
        {"kind": "add", "item_id": ITEM, "food_id": 1, "shop_id": HUGE},
        {"kind": "set_amount", "item_id": ITEM, "amount": 1, "size_id": HUGE},
        {"kind": "put_away", "item_id": ITEM, "place_id": HUGE, "tick_ids": []},
        {
            "kind": "different_pack",
            "item_id": ITEM,
            "tick_id": "t1",
            "count": 1,
            "pack": 1,
            "size_id": HUGE,
        },
    ],
)
def test_a_huge_number_in_a_batch_refuses_only_that_change(
    kitchen: TestClient, quiet_client: TestClient, fields: dict[str, Any]
) -> None:
    fields = dict(fields)
    if fields["kind"] == "add":
        fields["list_id"] = main_id(kitchen)
    seen = fields.pop("seen", 0)
    bad = action(fields.pop("kind"), seen, **fields)
    good = action("create_list", list_id=new_id(), name="Party")
    first, second = send(quiet_client, bad, good)["results"]
    assert first["status"] == "refused" and first["reason"] == "bad_action", first
    assert second["status"] == "applied", second
