"""Report a problem's scrubber knows API token names, single sign-on group names and the
sign-in server's host."""

# ruff: noqa: F811, F401
from pathlib import Path
from typing import Any, cast

from fastapi.testclient import TestClient
from test_sso_api import API, SETUP, admin, idp

from mealwright.problem_report import Scrubber, ServerAddress, scrubber_for

LINE = (
    "Couldn't reach auth.marsh.family for group marsh-family-admins "
    "(token Marsh NAS backup, asked by tess)"
)


def _setup_and_token(admin: TestClient) -> None:
    setup = {**SETUP, "issuer": "https://auth.marsh.family", "client_secret": ""}
    setup["group_roles"] = [{"group": "marsh-family-admins", "role": "admin"}]
    assert admin.put(f"{API}/sso/settings", json=setup).status_code == 200
    made = admin.post(f"{API}/api-tokens", json={"name": "Marsh NAS backup", "scope": "read"})
    assert made.status_code == 201


def test_the_scrubber_removes_token_names_group_names_and_the_sign_in_servers_host(
    admin: TestClient, settings: Any
) -> None:
    _setup_and_token(admin)
    with cast(Any, admin.app).state.sessionmaker() as db:
        scrub = Scrubber(db, ServerAddress(("testserver",), (443,)), Path(settings.data_dir))
    cleaned = scrub(LINE)
    assert "tess" not in cleaned
    assert "marsh" not in cleaned.lower(), cleaned
    assert "[server]" in cleaned and "[removed]" in cleaned


def test_a_kept_scrubber_is_built_again_when_a_token_or_the_sign_in_setup_is_saved(
    admin: TestClient, settings: Any
) -> None:
    server = ServerAddress(("testserver",), (443,))
    with cast(Any, admin.app).state.sessionmaker() as db:
        before = scrubber_for(db, server, Path(settings.data_dir))
    assert "marsh" in before(LINE).lower()
    _setup_and_token(admin)
    with cast(Any, admin.app).state.sessionmaker() as db:
        after = scrubber_for(db, server, Path(settings.data_dir))
    assert "marsh" not in after(LINE).lower()
