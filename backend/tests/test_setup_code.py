"""The first-run setup code (PR A2): only someone who can read the server's log can create the
admin account on a fresh install."""

import logging

import pytest
from conftest import ADMIN, SETUP_CODE
from fastapi.testclient import TestClient

from mealwright import setup_code
from mealwright.config import Settings
from mealwright.main import create_app
from mealwright.setup_code import new_code  # the real one: conftest swaps in a known code

WRONG = (
    "That isn’t the setup code. Mealwright prints it in its log when it starts, "
    "and again after Delete everything."
)


def test_a_code_looks_like_this() -> None:
    code = new_code()
    groups = code.split("-")
    assert [len(g) for g in groups] == [4, 4, 4]
    assert set(code.replace("-", "")) <= set(setup_code.ALPHABET)
    assert not set("01ILO") & set(setup_code.ALPHABET)
    assert len({new_code() for _ in range(50)}) == 50


def test_typed_any_case_with_or_without_dashes() -> None:
    assert setup_code.matches("K7QM-3XRT-P9WA", "k7qm 3xrt p9wa")
    assert setup_code.matches("K7QM-3XRT-P9WA", "K7QM3XRTP9WA")
    assert not setup_code.matches("K7QM-3XRT-P9WA", "K7QM-3XRT-P9WB")
    assert not setup_code.matches("K7QM-3XRT-P9WA", "")
    assert not setup_code.matches("K7QM-3XRT-P9WA", "K7QM-3XRT-P9WÄ")
    assert not setup_code.matches(None, "anything")


def test_the_code_is_in_the_log_at_start_up(
    settings: Settings, caplog: pytest.LogCaptureFixture
) -> None:
    with (
        caplog.at_level(logging.WARNING, logger="mealwright"),
        TestClient(create_app(settings), base_url="https://testserver"),
    ):
        pass
    lines = [r for r in caplog.records if r.name == "mealwright.setup"]
    assert len(lines) == 1
    assert SETUP_CODE in lines[0].getMessage()
    assert "setup code" in lines[0].getMessage()


def test_no_code_once_set_up(kitchen: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    assert kitchen.app.state.setup_code is None  # type: ignore[attr-defined]
    settings = kitchen.app.state.settings  # type: ignore[attr-defined]
    with (
        caplog.at_level(logging.WARNING, logger="mealwright"),
        TestClient(create_app(settings), base_url="https://testserver") as again,
    ):
        assert again.app.state.setup_code is None  # type: ignore[attr-defined]
    assert not [r for r in caplog.records if r.name == "mealwright.setup"]


def test_setup_needs_the_code(client: TestClient) -> None:
    without = {k: v for k, v in ADMIN.items() if k != "setup_code"}
    assert client.post("/api/v1/setup", json=without).status_code == 422
    wrong = client.post("/api/v1/setup", json=ADMIN | {"setup_code": "ABCD-EFGH-JKMN"})
    assert wrong.status_code == 403
    assert wrong.json() == {"detail": WRONG, "code": "wrong_setup_code"}
    assert client.get("/api/v1/setup").json()["needs_setup"] is True
    right = client.post("/api/v1/setup", json=ADMIN | {"setup_code": SETUP_CODE.lower()})
    assert right.status_code == 201
    # Used up: the next start-up makes none, and this one forgets it.
    assert client.app.state.setup_code is None  # type: ignore[attr-defined]


def test_wrong_codes_are_slowed_down(client: TestClient) -> None:
    wrong = ADMIN | {"setup_code": "ABCD-EFGH-JKMN"}
    for _ in range(5):
        assert client.post("/api/v1/setup", json=wrong).status_code == 403
    # Even the right code waits now: guessing is as slow as guessing a password.
    paused = client.post("/api/v1/setup", json=ADMIN)
    assert paused.status_code == 429
    assert paused.json()["code"] == "too_many_tries"
    assert int(paused.headers["retry-after"]) > 0


def test_the_code_is_never_echoed(client: TestClient, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger="mealwright"):
        answer = client.post("/api/v1/setup", json=ADMIN | {"setup_code": "NOPE-NOPE-NOPE"})
    assert "NOPE" not in answer.text
    assert "NOPE" not in caplog.text
    assert SETUP_CODE not in client.get("/api/v1/setup").text
