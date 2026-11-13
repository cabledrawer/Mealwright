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


def _names_for(admin: TestClient, taken: list[str], name: str, username: str) -> str:
    from typing import Any, cast

    from mealwright import sso_accounts
    from mealwright.models import Member

    with cast(Any, admin.app).state.sessionmaker() as db:
        for other in taken:
            db.add(Member(household_id=1, name=other))
        db.commit()
        return sso_accounts._member_name(db, 1, name, username)


def test_a_long_name_ending_in_a_flag_is_cut_clean(admin: TestClient) -> None:
    """whole-0.9 fix A review, finding 4: cut like every other name, never in the middle of a
    flag (a tag flag's tag characters are refused when left on their own)."""
    flag = "\U0001f3f4" + "".join(chr(0xE0000 + ord(c)) for c in "gbsct") + "\U000e007f"
    name = "N" * 97 + flag
    made = _names_for(admin, [], name, "nn")
    assert made == "N" * 97
    assert not any(0xE0000 <= ord(c) <= 0xE007F for c in made)
    clash = _names_for(admin, [made], name, "nn")
    assert len(clash) <= 100 and clash.endswith(" (nn)")
    assert not any(0xE0000 <= ord(c) <= 0xE007F for c in clash)


def test_a_name_taken_with_its_username_too_gets_a_number(admin: TestClient) -> None:
    taken = ["Ayla", "Ayla (ayla)"]
    assert _names_for(admin, taken, "Ayla", "ayla") == "Ayla (ayla) 2"
    assert _names_for(admin, [*taken, "Ayla (ayla) 2"], "Ayla", "ayla") == "Ayla (ayla) 3"
