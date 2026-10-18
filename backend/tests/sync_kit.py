"""Helpers for the sync tests (docs/dev/sync-protocol.md section 14): a second person, a
batch, the catching-up answer. Time travel is done by editing rows."""

import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi.testclient import TestClient

from mealwright.auth import hash_password
from mealwright.models import Household, Login

API = "/api/v1"
PHONE_A = "0b6c3f0e-7c1a-4f7e-9d0b-2f7a3c1e5d42"  # Tess's phone
PHONE_B = "1c7d4a1f-8d2b-4a8f-8e1c-3a8b4d2f6e53"  # Tess's other phone
PHONE_R = "2d8e5b2a-9e3c-4b9a-9f2d-4b9c5e3a7f64"  # Wren's phone
WREN_PASSWORD = "wren's long password"


def db(client: TestClient) -> Any:
    return client.app.state.sessionmaker()  # type: ignore[attr-defined]


def ok(response: Any, status: int = 200) -> Any:
    assert response.status_code == status, response.text
    return response.json()


def new_id() -> str:
    return str(uuid.uuid4())


def now() -> str:
    return datetime.now(UTC).isoformat()


def food(client: TestClient, name: str, **extra: Any) -> dict[str, Any]:
    made: dict[str, Any] = ok(client.post(f"{API}/foods", json={"name": name, **extra}), 201)
    return dict(made["food"])


def main_id(client: TestClient) -> str:
    lists = ok(client.get(f"{API}/shopping/lists"))["lists"]
    return str(next(row["id"] for row in lists if row["main"]))


def counter(client: TestClient) -> int:
    with db(client) as session:
        return int(session.get(Household, 1).list_seq)


def login_id(client: TestClient) -> int:
    return int(ok(client.get(f"{API}/me"))["id"])


def person(kitchen: TestClient, name: str = "Wren", username: str = "wren") -> TestClient:
    """A second login in the household, signed in on its own client (S0)."""
    with db(kitchen) as session:
        session.add(
            Login(
                household_id=1,
                username=username,
                name=name,
                password_hash=hash_password(WREN_PASSWORD),
                role="member",
            )
        )
        session.commit()
    other = TestClient(kitchen.app, base_url="https://testserver")
    ok(other.post(f"{API}/session", json={"username": username, "password": WREN_PASSWORD}))
    return other


def action(kind: str, seen: int = 0, **fields: Any) -> dict[str, Any]:
    return {
        "id": fields.pop("id", None) or new_id(),
        "kind": kind,
        "made_at": now(),
        "seen": seen,
        **fields,
    }


def send(
    client: TestClient,
    *actions: dict[str, Any],
    device: str = PHONE_A,
    since: int = 0,
    login: int | None = None,
    sent_at: str | None = None,
    status: int = 200,
) -> Any:
    body = {
        "protocol": 1,
        "device_id": device,
        "login_id": login if login is not None else login_id(client),
        "since": since,
        "sent_at": sent_at or now(),
        "actions": list(actions),
    }
    return ok(client.post(f"{API}/shopping/actions", json=body), status)


def one(client: TestClient, kind: str, seen: int = 0, device: str = PHONE_A, **fields: Any) -> Any:
    """Send one action; return its result (the batch answer is in result["_answer"])."""
    answer = send(client, action(kind, seen, **fields), device=device)
    result = dict(answer["results"][0])
    result["_answer"] = answer
    return result


def changes(client: TestClient, since: int = 0, device: str | None = None) -> Any:
    query = f"?since={since}" + (f"&device_id={device}" if device else "")
    return ok(client.get(f"{API}/shopping/changes{query}"))


def item_row(answer: Any, item_id: str) -> Any:
    return next(row for row in answer["items"] if row["id"] == item_id)
