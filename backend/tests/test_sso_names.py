"""A name from the sign-in server is tidied, and made different, like a typed one."""

# ruff: noqa: F811, F401
from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from test_sso_api import API, admin, browser, fresh_cache, idp, sign_in


def test_a_name_from_the_sign_in_server_is_tidied_and_kept_apart_like_a_typed_one(
    admin: TestClient, idp: FakeProvider
) -> None:
    """Settings → Household refuses a second "Tess" (409 name_taken) and tidies line breaks.
    A first single sign-on sign-in makes a person with whatever name the sign-in server sends."""
    typed = admin.post(f"{API}/people", json={"name": "tess"})
    assert typed.status_code == 409
    one = browser(admin)
    answer, _ = sign_in(one, idp, sub="u1", extra={"preferred_username": "kk", "name": "Tess"})
    assert answer.status_code == 200, answer.text
    two = browser(admin)
    answer, _ = sign_in(
        two, idp, sub="u2", extra={"preferred_username": "odd", "name": "Asha\nRao‮ (admin)"}
    )
    assert answer.status_code == 200, answer.text
    names = [p["name"] for p in admin.get(f"{API}/people").json()["people"]]
    assert names.count("Tess") == 1, names
    assert "Tess (kk)" in names, names
    assert "Asha Roe (admin)" in names, names
