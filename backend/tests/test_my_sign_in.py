"""Settings, Sign-in (PR A2): change your password, where you're signed in, signing out one
device or everywhere else."""

import logging
from collections.abc import Iterator

import pytest
from conftest import ADMIN
from fastapi.testclient import TestClient
from sqlalchemy import select

from mealwright.devices import device_label
from mealwright.models import Login, Session

IPHONE = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) AppleWebKit/605.1.15 "
    "(KHTML, like Gecko) Version/18.1 Mobile/15E148 Safari/604.1"
)
PC_CHROME = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)
IPAD = (
    "Mozilla/5.0 (iPad; CPU OS 18_1 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) "
    "Version/18.1 Mobile/15E148 Safari/604.1"
)
NEW = "a brand new kitchen password"
SIGN_IN = {"username": ADMIN["username"], "password": ADMIN["password"], "remember": True}


@pytest.mark.parametrize(
    ("user_agent", "label"),
    [
        (IPHONE, "iPhone · Safari"),
        (PC_CHROME, "PC · Chrome"),
        (IPAD, "iPad · Safari"),
        (
            "Mozilla/5.0 (Linux; Android 15; Pixel 9) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Mobile Safari/537.36",
            "Android phone · Chrome",
        ),
        (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:132.0) Gecko/20100101 Firefox/132.0",
            "Mac · Firefox",
        ),
        (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
            "PC · Edge",
        ),
        (
            "Mozilla/5.0 (X11; Linux x86_64; rv:132.0) Gecko/20100101 Firefox/132.0",
            "Linux · Firefox",
        ),
        ("curl/8.5.0", None),
        ("", None),
        (None, None),
    ],
)
def test_device_names(user_agent: str | None, label: str | None) -> None:
    assert device_label(user_agent) == label


def test_only_the_short_device_name_is_kept(kitchen: TestClient) -> None:
    other = TestClient(kitchen.app, base_url="https://testserver", headers={"User-Agent": IPHONE})
    assert other.post("/api/v1/session", json=SIGN_IN).status_code == 200
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        devices = db.scalars(select(Session.device)).all()
    assert "iPhone · Safari" in devices
    assert not any(d and "Mozilla" in d for d in devices)


@pytest.fixture
def devices(kitchen: TestClient) -> Iterator[dict[str, TestClient]]:
    """Tess signed in on three devices: this test client (the PC), an iPhone and an iPad."""
    others = {}
    for name, agent in (("iphone", IPHONE), ("ipad", IPAD)):
        other = TestClient(
            kitchen.app, base_url="https://testserver", headers={"User-Agent": agent}
        )
        assert other.post("/api/v1/session", json=SIGN_IN).status_code == 200
        others[name] = other
    yield {"pc": kitchen, **others}


def test_where_youre_signed_in(devices: dict[str, TestClient]) -> None:
    answer = devices["iphone"].get("/api/v1/me/sign-in")
    assert answer.status_code == 200
    body = answer.json()
    assert body["has_password"] is True
    assert body["password_changed_at"] is None  # set at setup: no date yet
    sessions = body["sessions"]
    assert len(sessions) == 3
    assert sessions[0]["this_device"] is True  # this device first
    assert sessions[0]["device"] == "iPhone · Safari"
    assert sessions[0]["remember"] is True
    assert [s["this_device"] for s in sessions[1:]] == [False, False]
    assert {s["device"] for s in sessions[1:]} == {"iPad · Safari", None}  # the test client
    assert all(s["last_used_at"].endswith(("Z", "+00:00")) for s in sessions)


def test_only_your_own_sessions_are_listed(
    devices: dict[str, TestClient], neighbour: TestClient
) -> None:
    mine = {s["id"] for s in devices["pc"].get("/api/v1/me/sign-in").json()["sessions"]}
    theirs = {s["id"] for s in neighbour.get("/api/v1/me/sign-in").json()["sessions"]}
    assert len(theirs) == 1
    assert not mine & theirs
    # Someone else's session can't be ended: it reads as already gone.
    (their_id,) = theirs
    assert devices["pc"].delete(f"/api/v1/me/sessions/{their_id}").status_code == 404
    assert neighbour.get("/api/v1/me").status_code == 200


def test_sign_out_one_device(devices: dict[str, TestClient]) -> None:
    sessions = devices["pc"].get("/api/v1/me/sign-in").json()["sessions"]
    ipad = next(s for s in sessions if s["device"] == "iPad · Safari")
    answer = devices["pc"].delete(f"/api/v1/me/sessions/{ipad['id']}")
    assert answer.status_code == 200
    assert ipad["id"] not in {s["id"] for s in answer.json()["sessions"]}
    assert devices["ipad"].get("/api/v1/me").status_code == 401
    assert devices["iphone"].get("/api/v1/me").status_code == 200
    # Again: already gone.
    assert devices["pc"].delete(f"/api/v1/me/sessions/{ipad['id']}").status_code == 404


def test_this_device_is_signed_out_with_sign_out_not_here(devices: dict[str, TestClient]) -> None:
    sessions = devices["pc"].get("/api/v1/me/sign-in").json()["sessions"]
    here = next(s for s in sessions if s["this_device"])
    answer = devices["pc"].delete(f"/api/v1/me/sessions/{here['id']}")
    assert answer.status_code == 409
    assert answer.json()["code"] == "this_device"
    assert devices["pc"].get("/api/v1/me").status_code == 200


def test_sign_out_everywhere_else(devices: dict[str, TestClient]) -> None:
    answer = devices["iphone"].delete("/api/v1/me/sessions/others")
    assert answer.status_code == 200
    (only,) = answer.json()["sessions"]
    assert only["this_device"] is True
    assert devices["iphone"].get("/api/v1/me").status_code == 200
    assert devices["pc"].get("/api/v1/me").status_code == 401
    assert devices["ipad"].get("/api/v1/me").status_code == 401


def test_sign_out_everywhere_else_ends_their_live_updates(
    devices: dict[str, TestClient], monkeypatch: pytest.MonkeyPatch
) -> None:
    ended: list[int] = []
    events = devices["pc"].app.state.events  # type: ignore[attr-defined]
    monkeypatch.setattr(events, "end_session", ended.append)
    sessions = devices["pc"].get("/api/v1/me/sign-in").json()["sessions"]
    devices["pc"].delete("/api/v1/me/sessions/others")
    assert sorted(ended) == sorted(s["id"] for s in sessions if not s["this_device"])


def test_change_password_signs_out_the_other_devices(devices: dict[str, TestClient]) -> None:
    body = {"current_password": ADMIN["password"], "new_password": NEW, "sign_out_others": True}
    answer = devices["iphone"].put("/api/v1/me/password", json=body)
    assert answer.status_code == 200
    assert answer.json()["password_changed_at"] is not None
    assert len(answer.json()["sessions"]) == 1
    assert devices["iphone"].get("/api/v1/me").status_code == 200  # still signed in here
    assert devices["pc"].get("/api/v1/me").status_code == 401
    assert devices["ipad"].get("/api/v1/me").status_code == 401
    # The new password signs in; the old one doesn't.
    fresh = TestClient(devices["pc"].app, base_url="https://testserver")
    old = {"username": ADMIN["username"], "password": ADMIN["password"]}
    assert fresh.post("/api/v1/session", json=old).status_code == 401
    assert fresh.post("/api/v1/session", json={**old, "password": NEW}).status_code == 200


def test_change_password_can_keep_the_other_devices(devices: dict[str, TestClient]) -> None:
    body = {"current_password": ADMIN["password"], "new_password": NEW, "sign_out_others": False}
    answer = devices["iphone"].put("/api/v1/me/password", json=body)
    assert answer.status_code == 200
    assert len(answer.json()["sessions"]) == 3
    assert devices["pc"].get("/api/v1/me").status_code == 200


def test_signing_out_others_is_the_default(devices: dict[str, TestClient]) -> None:
    body = {"current_password": ADMIN["password"], "new_password": NEW}
    assert devices["iphone"].put("/api/v1/me/password", json=body).status_code == 200
    assert devices["pc"].get("/api/v1/me").status_code == 401


def test_change_password_needs_the_current_one(
    kitchen: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    body = {"current_password": "not my password", "new_password": NEW}
    with caplog.at_level(logging.INFO, logger="mealwright"):
        answer = kitchen.put("/api/v1/me/password", json=body)
    assert answer.status_code == 422
    assert answer.json() == {
        "detail": "That isn’t your current password.",
        "code": "wrong_password",
    }
    assert "Password change refused for tess" in caplog.text
    assert "not my password" not in caplog.text and NEW not in caplog.text
    # Nothing changed.
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        login = db.scalars(select(Login)).one()
        assert login.password_changed_at is None
    assert kitchen.get("/api/v1/me").status_code == 200


def test_wrong_current_passwords_count_towards_the_pause(kitchen: TestClient) -> None:
    body = {"current_password": "not my password", "new_password": NEW}
    for _ in range(5):
        assert kitchen.put("/api/v1/me/password", json=body).status_code == 422
    paused = kitchen.put(
        "/api/v1/me/password", json={**body, "current_password": ADMIN["password"]}
    )
    assert paused.status_code == 429
    assert paused.json()["code"] == "username_paused"
    assert int(paused.headers["retry-after"]) > 0


def test_a_new_password_needs_12_characters(kitchen: TestClient) -> None:
    body = {"current_password": ADMIN["password"], "new_password": "eleven-char"}
    answer = kitchen.put("/api/v1/me/password", json=body)
    assert answer.status_code == 422
    assert answer.json() == {"detail": "Use at least 12 characters.", "code": "password_too_short"}


def test_these_need_sign_in(client: TestClient) -> None:
    assert client.get("/api/v1/me/sign-in").status_code == 401
    assert client.delete("/api/v1/me/sessions/others").status_code == 401
    assert client.delete("/api/v1/me/sessions/1").status_code == 401
    body = {"current_password": "x", "new_password": NEW}
    assert client.put("/api/v1/me/password", json=body).status_code == 401


def test_other_sites_cant_change_your_password(kitchen: TestClient) -> None:
    body = {"current_password": ADMIN["password"], "new_password": NEW}
    evil = {"Origin": "https://evil.example"}
    assert kitchen.put("/api/v1/me/password", json=body, headers=evil).status_code == 403
    assert kitchen.delete("/api/v1/me/sessions/others", headers=evil).status_code == 403


def test_in_the_api_description(client: TestClient) -> None:
    paths = client.get("/api/v1/openapi.json").json()["paths"]
    assert "get" in paths["/api/v1/me/sign-in"]
    assert "put" in paths["/api/v1/me/password"]
    assert "delete" in paths["/api/v1/me/sessions/others"]
    assert "delete" in paths["/api/v1/me/sessions/{sign_in_id}"]
