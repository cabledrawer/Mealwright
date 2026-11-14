"""A person's login says whether they sign in, by password or by single sign-on (Pe4)."""

from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import select
from sync_kit import API, db, ok, person

from mealwright import sso_accounts
from mealwright.models import SsoSettings
from mealwright.sso import Identity

ISSUER = "https://auth.example.test"


def _login_of(client: TestClient, name: str) -> dict[str, Any]:
    people = ok(client.get(f"{API}/people"))["people"]
    return dict(next(p for p in people if p["name"] == name)["login"])


def test_a_login_by_password_or_by_single_sign_on_signs_in_and_a_waiting_link_does_not(
    kitchen: TestClient,
) -> None:
    person(kitchen)  # Wren, with a password
    # Noor, given a login "noor" here; her sign-in server account of that username links to it.
    ok(kitchen.post(f"{API}/people", json={"name": "Noor"}), 201)
    noor_id = next(p for p in ok(kitchen.get(f"{API}/people"))["people"] if p["name"] == "Noor")
    ok(
        kitchen.post(
            f"{API}/people/{noor_id['id']}/login", json={"username": "noor", "role": "member"}
        ),
        201,
    )
    with db(kitchen) as session:
        session.add(
            SsoSettings(
                household_id=1,
                issuer=ISSUER,
                client_id="mealwright",
                client_secret_sealed="sealed",
                button_name="Authentik",
                redirect_uri="https://testserver/auth/callback",
                group_roles=[],
                anyone_else="member",
                password_sign_in=True,
            )
        )
        session.commit()
        row = session.scalar(select(SsoSettings))
        identity = Identity(
            issuer=ISSUER,
            subject="sub-noor",
            username="noor",
            email=None,
            name="Noor",
            groups=[],
            refresh_token=None,
        )
        sso_accounts.login_for(session, row, identity, kitchen.app.state.settings.data_dir)
        session.commit()
    ok(kitchen.post(f"{API}/people", json={"name": "Child"}), 201)
    child = next(p for p in ok(kitchen.get(f"{API}/people"))["people"] if p["name"] == "Child")
    ok(
        kitchen.post(
            f"{API}/people/{child['id']}/login", json={"username": "child", "role": "member"}
        ),
        201,
    )
    assert _login_of(kitchen, "Wren")["signs_in"] is True
    noor = _login_of(kitchen, "Noor")
    assert noor["signs_in"] is True
    assert noor["has_password"] is False
    waiting = _login_of(kitchen, "Child")
    assert waiting["signs_in"] is False and waiting["link_pending"] is True
