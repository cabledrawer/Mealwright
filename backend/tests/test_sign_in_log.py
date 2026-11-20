"""One way to log sign-in and privacy events (0.9.5-beta.3, D4, BE24 and BE25).

Every such line is on the `mealwright.sign_in` logger; it names the person who did it, and the
person it was done to, by username, never by their name; a refusal is a warning and a success
is info. No password, token, link or address is ever in it.
"""

import logging

import pytest
from fastapi.testclient import TestClient
from sync_kit import API, ok
from test_people import _add, _fresh, _join
from test_privacy import LIST, SWITCHES

from mealwright import auth, privacy_changes, sso_accounts
from mealwright.api.v1 import privacy, your_data
from mealwright.api.v1 import sso as sso_api

SIGN_IN = "mealwright.sign_in"


def test_every_sign_in_and_privacy_module_logs_on_the_one_logger() -> None:
    for module in (auth, privacy, privacy_changes, sso_accounts, sso_api):
        assert module.log.name == SIGN_IN, module.__name__
    assert your_data.sign_in_log.name == SIGN_IN


def test_links_are_logged_by_username_with_who_made_them(
    kitchen: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    lorna = _add(kitchen, "Lorna Doone", portion_quarters=3)
    with caplog.at_level(logging.INFO, logger=SIGN_IN):
        token = _join(kitchen, lorna, "lorna")
        joined = {"token": token, "password": "lorna's first password"}
        ok(_fresh(kitchen).post(f"{API}/join", json=joined))
        reset = ok(kitchen.post(f"{API}/people/{lorna}/reset-password"), 201)
    lines = [r for r in caplog.records if r.name == SIGN_IN and "link made" in r.getMessage()]
    assert [r.getMessage() for r in lines] == [
        "Sign-in link made for lorna by tess",
        "Reset link made for lorna by tess",
    ]
    assert all(r.levelno == logging.INFO for r in lines)
    for secret in (token, reset["path"].removeprefix("/reset#"), "first password"):
        assert secret not in caplog.text
    assert "Lorna Doone" not in caplog.text  # her name, never: her username


def test_privacy_changes_are_info_on_the_one_logger_by_username(
    kitchen: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger=SIGN_IN):
        kitchen.put(f"{SWITCHES}/recipe_import", json={"on": True})
        kitchen.post(LIST, json={"value": "wiki.home.example"})
    lines = [r for r in caplog.records if r.name == SIGN_IN]
    assert [r.getMessage() for r in lines] == [
        "Privacy: recipe import switched on by tess",
        "Your own network: added by tess",
    ]
    assert all(r.levelno == logging.INFO for r in lines)
    assert "wiki.home.example" not in caplog.text
