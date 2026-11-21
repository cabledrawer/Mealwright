"""Single sign-on in Recent changes (release security pass beta.3; proposed, for cabledrawer): the
sign-in server's usernames are for an admin at a screen, as on Settings › People. A member and
every API token (an admin's full one too) read the same line without the username, in the list,
in the answer about one change, and nothing of it goes out on the live updates."""

# ruff: noqa: F811, F401
import asyncio
from typing import Any, cast

import pytest
from fake_idp import FakeProvider
from fastapi.testclient import TestClient
from sqlalchemy import update
from test_api_tokens import _app, _make
from test_events import broadcaster, heard, run
from test_sso_api import API, admin, browser, idp, person_here, sign_in
from test_sso_waiting import _member_id, _wait, member

from mealwright import sso_changes
from mealwright.models import Change, Login, Member, utcnow

USERNAMES = ("lorna.s", "kit.k", "zed.x", "asha.k")

FOR_ADMIN = [
    "Unlinked Lorna from lorna.s at your sign-in server",
    "Refused zed.x at your sign-in server",
    "Added Kit K, linked to kit.k at your sign-in server",
    "Linked Lorna to lorna.s at your sign-in server",
    "Linked Asha to asha.k at your sign-in server, automatically",
]
FOR_EVERYONE = [
    "Unlinked Lorna from your sign-in server",
    "Refused a sign-in at your sign-in server",
    "Added Kit K, linked to your sign-in server",
    "Linked Lorna to your sign-in server",
    "Linked Asha to your sign-in server, automatically",
]


def _history(admin: TestClient, idp: FakeProvider) -> None:
    """An automatic link, a link by hand, a new person, a refusal and an unlink."""
    person_here(admin, "asha.k")
    with cast(Any, admin.app).state.sessionmaker() as db:
        db.execute(update(Login).where(Login.username == "asha.k").values(name="Asha"))
        db.execute(update(Member).where(Member.name == "Asha.k").values(name="Asha"))
        db.commit()
    auto, _ = sign_in(browser(admin), idp, sub="asha-1", extra={"preferred_username": "asha.k"})
    assert auto.status_code == 200, auto.text
    person_here(admin, "lorna")
    lorna = _member_id(admin, "Lorna")
    linked = _wait(admin, idp)
    assert admin.post(
        f"{API}/people/sso-accounts/{linked}/link", json={"member_id": lorna}
    ).is_success
    kit = _wait(admin, idp, sub="kit-1", preferred_username="kit.k", name="Kit K")
    assert admin.post(f"{API}/people/sso-accounts/{kit}/link", json={"member_id": None}).is_success
    zed = _wait(admin, idp, sub="zed-1", preferred_username="zed.x", name="Zed X")
    assert admin.post(f"{API}/people/sso-accounts/{zed}/refuse").is_success
    assert admin.delete(f"{API}/people/{lorna}/sso").is_success


def _sign_in_lines(client: TestClient) -> list[dict[str, Any]]:
    answer = client.get(f"{API}/changes", params={"limit": 100})
    assert answer.status_code == 200, answer.text
    return [c for c in answer.json()["changes"] if c["kind"] == "person_login"]


def _caller(admin: TestClient, member: TestClient, who: str) -> TestClient:
    return member if who == "member" else _app(admin, _make(admin, who.split()[0]))


def test_an_admin_reads_the_sign_in_servers_usernames(admin: TestClient, idp: FakeProvider) -> None:
    _history(admin, idp)
    assert [c["summary"] for c in _sign_in_lines(admin)] == FOR_ADMIN


@pytest.mark.parametrize("who", ["member", "read token", "full token"])
def test_everyone_else_reads_them_without_the_username(
    admin: TestClient, idp: FakeProvider, member: TestClient, who: str
) -> None:
    _history(admin, idp)
    caller = _caller(admin, member, who)
    lines = _sign_in_lines(caller)
    assert [c["summary"] for c in lines] == FOR_EVERYONE
    everything = caller.get(f"{API}/changes", params={"limit": 100})
    people = caller.get(f"{API}/people")
    assert all(username not in everything.text for username in USERNAMES), everything.text
    # Settings › People shows Mealwright's own usernames (made from kit.k and asha.k here), never
    # one that is only the sign-in server's.
    assert all(username not in people.text for username in ("lorna.s", "zed.x")), people.text
    # The answer about one of them (an Undo asked for: there is none) names no username either.
    for line in lines:
        answer = caller.post(f"{API}/changes/{line['id']}/undo")
        assert answer.status_code in (403, 409), answer.text
        assert all(username not in answer.text for username in USERNAMES)


def test_the_live_updates_carry_no_username(admin: TestClient, idp: FakeProvider) -> None:
    async def scenario() -> list[str]:
        sub = broadcaster(admin).subscribe(1)
        await asyncio.to_thread(_history, admin, idp)
        said: list[str] = []
        while True:
            try:
                said.append(repr(await heard(sub, 0.3)))
            except TimeoutError:
                return said

    said = run(scenario())  # sign-in changes aren't announced at all today; any that is, by number
    assert all(username not in line for line in said for username in USERNAMES), said


# A line written before this keeps only the admin's sentence: the username is cut out by its
# pattern. A name with " to " in it is cut short there rather than show any of the username.
OLD = [
    ("Linked Lorna to lorna.s at your sign-in server", "Linked Lorna to your sign-in server"),
    (
        "Linked Asha to asha.k at your sign-in server, automatically",
        "Linked Asha to your sign-in server, automatically",
    ),
    (
        "Added Kit K, linked to kit.k at your sign-in server",
        "Added Kit K, linked to your sign-in server",
    ),
    ("Refused zed.x at your sign-in server", "Refused a sign-in at your sign-in server"),
    (
        "Unlinked Lorna from lorna.s at your sign-in server",
        "Unlinked Lorna from your sign-in server",
    ),
    ("Linked Back to Front to zed.x at your", "Linked Back to your sign-in server"),
    ("Made a sign-in link for Lorna", "Made a sign-in link for Lorna"),
    ("Something else about zed.x", sso_changes.SOME_CHANGE),
]


def test_a_line_made_before_this_is_cut_the_same_way(admin: TestClient, member: TestClient) -> None:
    with cast(Any, admin.app).state.sessionmaker() as db:
        for summary, _ in OLD:
            db.add(
                Change(
                    household_id=1,
                    request="before",
                    kind="person_login",
                    login_name="Admin",
                    at=utcnow(),
                    summary=summary,
                )
            )
        db.commit()
    expected = [shown for _, shown in reversed(OLD)]
    assert [c["summary"] for c in _sign_in_lines(member)] == expected
    assert [c["summary"] for c in _sign_in_lines(admin)] == [s for s, _ in reversed(OLD)]
