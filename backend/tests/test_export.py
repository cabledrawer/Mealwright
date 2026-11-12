"""Export everything (0.9, D1; spec section 7, "Export"): one zip, Admins only, read back.

The round trip: what goes in comes out (rows and photo files, byte for byte); passwords and
sign-ins never do; one household never sees another's; the format says what it is.
"""

import io
import json
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from photo_kit import jpeg, uploaded

from mealwright import export
from mealwright.auth import COOKIE, hash_password
from mealwright.db import Base
from mealwright.models import Login
from mealwright.photos import household_folder

API = "/api/v1/export"
ADMIN_PASSWORD = "correct horse battery"


@pytest.fixture
def member(kitchen: TestClient) -> Iterator[TestClient]:
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(
            Login(
                household_id=1,
                username="wren",
                name="Wren",
                password_hash=hash_password("wren's own password"),
                role="member",
            )
        )
        db.commit()
    with TestClient(kitchen.app, base_url="https://testserver") as other:
        body = {"username": "wren", "password": "wren's own password"}
        assert other.post("/api/v1/session", json=body).status_code == 200
        yield other


def _export(client: TestClient) -> tuple[dict, dict[str, bytes], bytes]:  # type: ignore[type-arg]
    response = client.get(API)
    assert response.status_code == 200, response.text
    assert response.headers["content-type"] == "application/zip"
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["content-disposition"].startswith(
        'attachment; filename="mealwright-export-'
    )
    doc, photos = export.read(io.BytesIO(response.content))
    return doc, photos, response.content


def _photo_store(client: TestClient) -> Path:
    return Path(client.app.state.settings.data_dir) / "photos"  # type: ignore[attr-defined]


def test_the_round_trip_brings_back_rows_and_photos(kitchen: TestClient) -> None:
    photo = uploaded(kitchen, jpeg())
    recipe = kitchen.post(
        "/api/v1/recipes", json={"name": "Dal with ümlauts and ½ tsp", "photo_id": photo["id"]}
    )
    assert recipe.status_code == 201, recipe.text
    doc, photos, _ = _export(kitchen)

    assert doc["format"] == "mealwright-export"
    assert doc["version"] == 1
    assert doc["household_id"] == 1
    assert doc["database_revision"]
    # Every household table is there (even when empty), except the sign-ins, sign-in links,
    # API tokens and the kept old names.
    expected = {t.name for t in Base.metadata.sorted_tables} - {
        "session",
        "join_link",
        "api_token",
        "former_name",
    }
    assert set(doc["tables"]) == expected
    names = [row["name"] for row in doc["tables"]["recipe"]]
    assert names == ["Dal with ümlauts and ½ tsp"]
    assert [row["id"] for row in doc["tables"]["household"]] == [1]

    # The photo files come back byte for byte.
    folder = household_folder(_photo_store(kitchen), 1)
    on_disk = {p.name: p.read_bytes() for p in folder.iterdir() if p.suffix == ".jpg"}
    assert on_disk
    assert photos == on_disk


def test_tables_come_in_an_order_they_can_be_put_back_in() -> None:
    """A table comes after the tables it points at. The one exception (the format says so):
    `change` and `list_tick` point at each other, through `change.tick_id`."""
    order = [t.name for t in Base.metadata.sorted_tables]
    forward = set()
    for table in Base.metadata.sorted_tables:
        for key in table.foreign_keys:
            if order.index(key.column.table.name) > order.index(table.name):
                forward.add((table.name, key.constraint.name, key.use_alter))
    assert {(t, alter) for t, _, alter in forward} <= {("change", True)}
    assert {name for _, name, _ in forward} <= {
        c.name
        for c in Base.metadata.tables["change"].foreign_key_constraints
        if "tick_id" in c.column_keys
    }


def test_no_password_and_no_sign_in_ever_leaves(kitchen: TestClient) -> None:
    doc, _, raw = _export(kitchen)
    logins = doc["tables"]["login"]
    assert [login["username"] for login in logins] == ["tess"]
    assert all("password_hash" not in login for login in logins)
    assert "session" not in doc["tables"]
    assert "join_link" not in doc["tables"]  # sign-in links (0.9 A1) are sign-ins too
    assert doc["left_out"]["tables"] == {
        "session": "who is signed in where (sign-in cookies)",
        "join_link": "sign-in links made for people",
        "api_token": "API tokens, which only an admin at the screen makes",
        "former_name": "old names kept for 15 days so Report a problem can remove them (proposed)",
    }
    assert "login.password_hash" in doc["left_out"]["columns"]
    assert "sso_settings.client_secret_sealed" in doc["left_out"]["columns"]
    assert "login.sso_refused_at" in doc["left_out"]["columns"]
    assert b"$argon2" not in raw
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        text = archive.read(export.DOCUMENT)
    assert b"$argon2" not in text
    assert ADMIN_PASSWORD.encode() not in text
    cookie = kitchen.cookies.get(COOKIE)
    assert cookie
    assert cookie.encode() not in text


def test_one_household_never_sees_anothers(kitchen: TestClient, neighbour: TestClient) -> None:
    assert kitchen.post("/api/v1/recipes", json={"name": "Ours"}).status_code == 201
    uploaded(kitchen, jpeg())
    assert neighbour.post("/api/v1/recipes", json={"name": "Next door's"}).status_code == 201
    doc, photos, _ = _export(neighbour)
    assert doc["household_id"] == 2
    assert [row["name"] for row in doc["tables"]["recipe"]] == ["Next door's"]
    assert [row["username"] for row in doc["tables"]["login"]] == ["neighbour"]
    for table, rows in doc["tables"].items():
        owner = "id" if table == "household" else "household_id"
        assert all(row[owner] == 2 for row in rows), table
    assert photos == {}


def test_a_member_cannot_export(member: TestClient) -> None:
    response = member.get(API)
    assert response.status_code == 403
    assert response.json()["detail"] == "Only the household’s admin can change this."


def test_signed_out_cannot_export(client: TestClient) -> None:
    assert client.get(API).status_code == 401


def test_a_file_that_isnt_an_export_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "other.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr(export.DOCUMENT, json.dumps({"format": "something else"}))
    with pytest.raises(ValueError, match="isn't a Mealwright export"):
        export.read(path)


def test_the_stream_is_a_valid_zip_with_photos_stored_as_they_are(tmp_path: Path) -> None:
    photo = tmp_path / ("a" * 32 + ".jpg")
    photo.write_bytes(jpeg())
    gone = tmp_path / ("b" * 32 + ".jpg")  # listed, then removed before it was sent
    doc = {"format": export.FORMAT, "version": 1, "tables": {}}
    data = b"".join(export.zip_stream(doc, [photo, gone]))
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.testzip() is None
        assert archive.namelist() == [export.DOCUMENT, "photos/" + photo.name]
        assert archive.getinfo("photos/" + photo.name).compress_type == zipfile.ZIP_STORED
        assert archive.read("photos/" + photo.name) == photo.read_bytes()


def test_only_photo_files_are_taken(tmp_path: Path) -> None:
    folder = household_folder(tmp_path, 1)
    folder.mkdir(parents=True)
    keep = ["c" * 32 + ".jpg", "c" * 32 + "-list.jpg"]
    for name in [*keep, "c" * 32 + ".jpg.part", "notes.txt", "../x.jpg".replace("/", "_")]:
        (folder / name).write_bytes(b"x")
    assert [p.name for p in export.photo_files(tmp_path, 1)] == sorted(keep)
    assert export.photo_files(tmp_path, 9) == []


def test_no_token_and_no_single_sign_on_secret_ever_leaves(kitchen: TestClient) -> None:
    """O2 review r1, finding 2 (proposed, for cabledrawer): the export leaves out API tokens (their
    SHA-256 is as good as the token to anyone who could guess its form) and the single sign-on
    client secret (the admin types it again if this is ever put back)."""
    from mealwright import api_tokens
    from mealwright.models import SsoSettings

    made = kitchen.post("/api/v1/api-tokens", json={"name": "Home Assistant", "scope": "read"})
    assert made.status_code == 201, made.text
    token = made.json()["token"]
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        db.add(
            SsoSettings(
                household_id=1,
                issuer="https://id.example.org",
                client_id="mealwright",
                client_secret_sealed="sealed-secret-blob",
                button_name="Authentik",
                redirect_uri="https://testserver/auth/callback",
                group_claim="groups",
                group_roles=[],
                anyone_else="none",
                make_accounts=True,
                password_sign_in=True,
            )
        )
        db.commit()
    doc, _, raw = _export(kitchen)
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        text = archive.read(export.DOCUMENT).decode()
    assert "api_token" not in doc["tables"]
    assert api_tokens.token_hash(token) not in text
    assert token not in text
    assert "sealed-secret-blob" not in text
    [row] = doc["tables"]["sso_settings"]  # the rest of the setup is exported
    assert row["issuer"] == "https://id.example.org"
    assert "client_secret_sealed" not in row
