"""A JSON body with a lone surrogate (the escape "\\ud800", half of an emoji and no other
half) is a mistake in the request, not a fault in the server: it gets a 422, never a 500
(0.5 PR 7 review of #61, finding 7)."""

import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sync_kit import API, action, login_id, new_id, now, s0

LONE = "\\ud800"


def post(client: TestClient, path: str, raw: str) -> Any:
    return client.post(f"{API}{path}", content=raw, headers={"content-type": "application/json"})


@pytest.mark.parametrize(
    ("path", "raw"),
    [
        ("/foods", '{"name": "' + LONE + '"}'),
        ("/shopping/lists", '{"name": "' + LONE + '"}'),
        ("/recipes/import", '{"text": "' + LONE + '"}'),
        (
            "/setup",
            '{"name": "' + LONE + '", "username": "x", "password": "correct horse battery"}',
        ),
    ],
)
def test_a_lone_surrogate_in_a_body_is_a_422_not_a_500(
    kitchen: TestClient, path: str, raw: str
) -> None:
    answer = post(kitchen, path, raw)
    assert answer.status_code in (409, 422), answer.text  # 409: setup is done already
    assert LONE not in answer.text and "\ud800" not in answer.text


def test_a_lone_surrogate_in_a_synced_action_is_refused_not_a_500(kitchen: TestClient) -> None:
    s = s0(kitchen)
    body = {
        "protocol": 1,
        "device_id": new_id(),
        "login_id": login_id(kitchen),
        "since": 0,
        "sent_at": now(),
        "actions": [action("create_list", list_id=new_id(), name="X")],
    }
    raw = json.dumps(body).replace('"name": "X"', '"name": "' + LONE + '"')
    assert LONE in raw and s.main
    answer = post(kitchen, "/shopping/actions", raw)
    assert answer.status_code < 500, answer.text
