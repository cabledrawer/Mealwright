"""A name from the sign-in server is tidied, and made different, like a typed one, for a new
person made from a waiting single sign-on sign-in ("Who is this?", Pe3/M2)."""

# ruff: noqa: F811, F401
import logging

import pytest
from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from test_sso_api import API, admin, browser, idp, sign_in, waits


def test_a_username_and_name_from_the_sign_in_server_are_one_clean_line_everywhere(
    admin: TestClient, idp: FakeProvider, caplog: pytest.LogCaptureFixture
) -> None:
    """Line breaks and a right-to-left control character in what the sign-in server sends:
    cleaned once, so the log, "Who is this?", the new person and Recent changes get one tidy
    line (security pass, fix round 1)."""
    caplog.set_level(logging.INFO)
    odd = {"preferred_username": "noor\nINFO forged line‮", "name": "Noor\nRoe‮ (admin)"}
    answer, _ = sign_in(browser(admin), idp, person=False, extra=odd)
    assert waits(answer)
    assert "\n" not in answer.json()["username"] and "‮" not in answer.json()["username"]
    waiting = admin.get(f"{API}/people").json()["waiting"]
    assert [w["username"] for w in waiting] == ["noor INFO forged line"]
    assert all("\n" not in r.getMessage() for r in caplog.records)
    made = admin.post(
        f"{API}/people/sso-accounts/{waiting[0]['id']}/link", json={"member_id": None}
    )
    assert made.status_code == 200, made.text
    names = [p["name"] for p in made.json()["people"]]
    assert "Noor Roe (admin)" in names, names
    summaries = [c["summary"] for c in admin.get(f"{API}/changes").json()["changes"]]
    assert all("\n" not in x and "‮" not in x for x in summaries)
    assert "noor INFO forged line" in summaries[0]


def _names_for(admin: TestClient, taken: list[str], name: str, username: str) -> str:
    from typing import Any, cast

    from mealwright import sso_accounts
    from mealwright.models import Member

    with cast(Any, admin.app).state.sessionmaker() as db:
        for other in taken:
            db.add(Member(household_id=1, name=other))
        db.commit()
        return sso_accounts.member_name(db, 1, name, username)


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
