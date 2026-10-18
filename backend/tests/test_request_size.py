"""No request body bigger than the biggest real one (security audit, 0.4; ASVS 12.1.1).

FastAPI reads a request's whole body before it checks the sign-in, so without a limit
anyone who can reach the server could make it hold huge bodies in memory. The biggest
real body is a full sync batch: 100 "clear ticked" actions of 500 items each.
"""

import json
from collections.abc import Iterator
from typing import Any

from fastapi.testclient import TestClient
from sync_kit import PHONE_A, action, login_id, main_id, now

from mealwright.limits import MAX_BODY_BYTES

API = "/api/v1"
TOO_BIG = "That's too much to send in one go."


def biggest_real_batch(client: TestClient) -> bytes:
    list_id = main_id(client)
    actions = [
        action(
            "clear_ticked",
            list_id=list_id,
            # Item IDs are UUIDs; 64 characters is the longest the server takes.
            item_ids=[f"{n:064d}" for n in range(500)],
        )
        for _ in range(100)
    ]
    body = {
        "protocol": 1,
        "device_id": PHONE_A,
        "login_id": login_id(client),
        "since": 0,
        "sent_at": now(),
        "actions": actions,
    }
    return json.dumps(body).encode()


def post(client: TestClient, content: bytes | Iterator[bytes], **headers: str) -> Any:
    return client.post(
        f"{API}/shopping/actions",
        content=content,
        headers={"Content-Type": "application/json", **headers},
    )


def test_the_biggest_real_batch_fits(kitchen: TestClient) -> None:
    body = biggest_real_batch(kitchen)
    assert len(body) < MAX_BODY_BYTES
    response = post(kitchen, body)
    assert response.status_code == 200, response.text[:300]
    assert len(response.json()["results"]) == 100


def test_a_body_over_the_limit_is_refused(kitchen: TestClient) -> None:
    body = b'{"protocol": 1, "padding": "' + b"x" * MAX_BODY_BYTES + b'"}'
    response = post(kitchen, body)
    assert response.status_code == 413
    assert response.json() == {"detail": TOO_BIG, "code": "body_too_big"}
    assert "content-security-policy" in response.headers


def test_refused_before_the_sign_in_check(client: TestClient) -> None:
    """Signed out, a huge body is still refused for its size, not read and parsed."""
    response = post(client, b"[" + b"0," * MAX_BODY_BYTES + b"0]")
    assert response.status_code == 413


def test_a_body_without_a_length_is_counted_as_it_arrives(kitchen: TestClient) -> None:
    def chunks() -> Iterator[bytes]:
        yield b'{"padding": "'
        for _ in range(MAX_BODY_BYTES // 65536 + 1):
            yield b"x" * 65536
        yield b'"}'

    response = post(kitchen, chunks())
    assert response.status_code == 413
    assert response.json()["code"] == "body_too_big"


def test_a_length_that_lies_is_still_counted(kitchen: TestClient) -> None:
    body = b'{"padding": "' + b"x" * MAX_BODY_BYTES + b'"}'
    response = post(kitchen, iter([body]), **{"Content-Length": "10"})
    assert response.status_code == 413


def test_every_method_with_a_body_is_limited(kitchen: TestClient) -> None:
    big = b'{"name": "' + b"x" * MAX_BODY_BYTES + b'"}'
    for method, path in (
        ("POST", f"{API}/foods"),
        ("PATCH", f"{API}/foods/1"),
        ("PUT", f"{API}/me/preferences"),
        ("POST", f"{API}/session"),
        ("POST", f"{API}/setup"),
    ):
        response = kitchen.request(
            method, path, content=big, headers={"Content-Type": "application/json"}
        )
        assert response.status_code == 413, (method, path, response.status_code)
