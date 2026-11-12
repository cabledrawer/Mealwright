"""What reaches the log (0.9, D1; spec section 7, "Logs", cabledrawer 17 Oct): errors and sign-ins
only, never what people cook, buy or type.

One household's busy day through the API, with every logger listening at its most talkative.
Not one log line (or traceback) may hold a password, a recipe's words, a shopping list's
words, a typed link's site, or a username that isn't a real account; and the sign-in lines are
there, so the test isn't passing on an empty log.
"""

import logging

import pytest
from conftest import SETUP_CODE
from fastapi.testclient import TestClient

API = "/api/v1"
PASSWORD = "Admin-password-6172"
NEW_PASSWORD_TRY = "Wrong-guess-5521"
TYPED_IN_USERNAME_BOX = "Password-in-the-username-box-9083"
RECIPE = "Secret saffron biryani 7731"
STEP = "Soak the rice in rosewater 4420"
LINE = "3 pods of hidden cardamom 1189"
LIST = "Surprise party list 3302"
INGREDIENT = "Hidden pistachio 4410"
NOTE = "for Grandma's birthday 8857"
SITE = "secret-recipes-site.example"

NEVER = [
    PASSWORD,
    NEW_PASSWORD_TRY,
    TYPED_IN_USERNAME_BOX,
    RECIPE,
    STEP,
    LINE,
    LIST,
    INGREDIENT,
    NOTE,
    SITE,
    "rosewater",
    "pistachio",
    "cardamom",
    "biryani",
]


def ok(response: object, status: int = 200) -> object:
    assert response.status_code == status, response.text  # type: ignore[attr-defined]
    return response.json()  # type: ignore[attr-defined]


def test_no_password_and_nothing_people_cook_or_buy_reaches_the_log(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.DEBUG):
        admin = {
            "name": "Tess",
            "username": "tess",
            "password": PASSWORD,
            "setup_code": SETUP_CODE,
        }
        ok(client.post(f"{API}/setup", json=admin), 201)

        # Sign-ins: a wrong password, a password typed into the username box, then the right one.
        client.delete(f"{API}/session")
        wrong = {"username": "tess", "password": NEW_PASSWORD_TRY}
        assert client.post(f"{API}/session", json=wrong).status_code == 401
        typed = {"username": TYPED_IN_USERNAME_BOX, "password": PASSWORD}
        assert client.post(f"{API}/session", json=typed).status_code == 401
        ok(client.post(f"{API}/session", json={"username": "tess", "password": PASSWORD}))

        # What people cook, buy and type.
        recipe = ok(
            client.post(
                f"{API}/recipes",
                json={
                    "name": RECIPE,
                    "description": NOTE,
                    "steps": [{"text": STEP}],
                    "lines": [{"words": LINE}],
                },
            ),
            201,
        )
        food = ok(client.post(f"{API}/foods", json={"name": INGREDIENT}), 201)["food"]  # type: ignore[index]
        lists = ok(client.post(f"{API}/shopping/lists", json={"name": LIST}), 201)
        list_id = lists["shopping_list"]["id"]  # type: ignore[index]
        ok(
            client.post(
                f"{API}/shopping/lists/{list_id}/items",
                json={"food_id": food["id"]},
            ),
            201,
        )
        ok(
            client.post(
                f"{API}/stock",
                json={"food_id": food["id"], "amount": {"amount": 200, "unit": "g"}},
            ),
            201,
        )
        # A link to import while the switch is off: the "Blocked" warning names the switch only.
        refused = client.post(
            f"{API}/recipes/import", json={"text": f"https://{SITE}/biryani-7731"}
        )
        assert refused.status_code == 403

        # Your data: Back up now, the export, and Delete everything with wrong words and a
        # wrong password, then for real.
        ok(client.post(f"{API}/backups"))
        assert client.get(f"{API}/export").status_code == 200
        everything = f"{API}/delete-everything"
        wrong_words = {"words": RECIPE, "password": PASSWORD}
        assert client.post(everything, json=wrong_words).status_code == 422
        wrong_password = {"words": "delete everything", "password": NEW_PASSWORD_TRY}
        assert client.post(everything, json=wrong_password).status_code == 403
        right = {"words": "delete everything", "password": PASSWORD}
        assert client.post(everything, json=right).status_code == 204
        assert recipe  # made, and now gone

    text = caplog.text.casefold()  # every line, with any traceback's text
    for secret in NEVER:
        assert secret.casefold() not in text, f"{secret!r} reached the log"
    # The sign-in lines are there: the log was listening.
    messages = caplog.messages
    assert "Sign-in failed for tess from testclient" in messages
    assert "Sign-in failed for unknown user from testclient" in messages
    assert "Signed in: tess from testclient" in messages
    assert "Delete everything: wrong password for tess" in messages
    assert "Blocked outgoing connection: recipe import is switched off" in messages
    assert any(m.startswith("Deleted everything (by tess)") for m in messages)
