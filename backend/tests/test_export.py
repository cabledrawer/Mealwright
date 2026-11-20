"""Export everything (0.9, D1; spec section 7, "Export"): one zip, Admins only, read back.

The round trip: what goes in comes out (rows and photo files, byte for byte); passwords and
sign-ins never do; one household never sees another's; the format says what it is.
"""

import io
import json
import os
import threading
import zipfile
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from photo_kit import jpeg, uploaded

from mealwright import export, export_crypto
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
    # API tokens, the kept old names and the single sign-on accounts.
    expected = {t.name for t in Base.metadata.sorted_tables} - {
        "session",
        "join_link",
        "api_token",
        "former_name",
        "sso_account",
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
        "former_name": "old names kept for 15 days so Report a problem can remove them",
        "sso_account": "single sign-on sign-ins waiting for an admin, refused or unlinked",
    }
    assert "sso_account" not in doc["tables"]  # single sign-on sign-ins (0.9.5) too
    assert "login.password_hash" in doc["left_out"]["columns"]
    assert "sso_settings.client_secret_sealed" in doc["left_out"]["columns"]
    assert "login.sso_refused_at" in doc["left_out"]["columns"]
    # When a sign-in or reset link was used is sign-in data too (0.9.5).
    assert "login.link_used_at" in doc["left_out"]["columns"]
    assert all("link_used_at" not in login for login in logins)
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
    with pytest.raises(ValueError, match="isn’t a Mealwright export"):
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


def _rows(*keys: str) -> dict[str, object]:
    return {"tables": {"recipe_photo": [{"file_key": key} for key in keys]}}


def test_only_the_photos_of_the_exported_rows_are_taken(tmp_path: Path) -> None:
    """B7 low: the list comes from the recipe_photo rows, not the folder."""
    folder = household_folder(tmp_path, 1)
    folder.mkdir(parents=True)
    keep = ["c" * 32 + ".jpg", "c" * 32 + "-list.jpg"]
    stray = ["d" * 32 + ".jpg", "d" * 32 + "-list.jpg"]
    for name in [*keep, *stray, "c" * 32 + ".jpg.part", "notes.txt"]:
        (folder / name).write_bytes(b"x")
    doc = _rows("c" * 32, "e" * 32, "../../etc/passwd", "not a key")  # one row has no files
    assert [p.name for p in export.photo_files(tmp_path, 1, doc)] == sorted(keep)
    assert export.photo_files(tmp_path, 9, doc) == []


def test_a_symbolic_link_is_never_followed_into_the_export(tmp_path: Path) -> None:
    folder = household_folder(tmp_path, 1)
    folder.mkdir(parents=True)
    secret = tmp_path / "secret.jpg"
    secret.write_bytes(b"not for the export")
    (folder / ("a" * 32 + ".jpg")).symlink_to(secret)
    (folder / ("a" * 32 + "-list.jpg")).write_bytes(jpeg())
    assert [p.name for p in export.photo_files(tmp_path, 1, _rows("a" * 32))] == [
        "a" * 32 + "-list.jpg"
    ]
    # A link put in the place of a listed file after the list was made is skipped too.
    doc = {"format": export.FORMAT, "version": 1, "tables": {}}
    data = b"".join(export.zip_stream(doc, [folder / ("a" * 32 + ".jpg")]))
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.namelist() == [export.DOCUMENT]


def test_no_token_and_no_single_sign_on_secret_ever_leaves(kitchen: TestClient) -> None:
    """O2 review r1, finding 2 (cabledrawer 13 Nov): the export leaves out API tokens (their
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


# --- The optional password (0.9.5, cabledrawer 13 Nov; docs/export-format.md, "The encrypted file")
# --

SEALED_PASSWORD = "lorna and noor's passphrase"


def _open_sealed(content: bytes, password: str = SEALED_PASSWORD) -> bytes:
    return b"".join(export_crypto.decrypt(io.BytesIO(content), password))


def test_with_a_password_the_file_is_encrypted_and_opens_to_the_same_export(
    kitchen: TestClient,
) -> None:
    photo = uploaded(kitchen, jpeg())  # a recipe_photo row, so its file is exported
    sealed = kitchen.post(API, json={"password": SEALED_PASSWORD})
    assert sealed.status_code == 200, sealed.text
    assert sealed.headers["content-type"] == "application/octet-stream"
    assert sealed.headers["cache-control"] == "no-store"
    assert sealed.headers["content-disposition"].startswith(
        'attachment; filename="mealwright-export-'
    )
    assert sealed.headers["content-disposition"].endswith('.zip.mwenc"')
    body = sealed.content
    assert body.startswith(export_crypto.MAGIC)
    assert b"mealwright-export.json" not in body  # no zip entry name in the clear
    assert b"PK\x03\x04" not in body
    doc, photos = export.read(io.BytesIO(_open_sealed(body)))
    assert doc["format"] == "mealwright-export"
    assert photo["id"]
    large = [n for n in photos if not n.endswith("-list.jpg")]
    assert len(large) == 1 and large[0][:-4] + "-list.jpg" in photos  # its two copies
    folder = household_folder(_photo_store(kitchen), 1)
    assert photos[large[0]] == (folder / large[0]).read_bytes()


def test_without_a_password_the_export_is_exactly_the_plain_zip(kitchen: TestClient) -> None:
    _doc, _photos, raw = _export(kitchen)
    assert raw.startswith(b"PK\x03\x04")
    assert not raw.startswith(export_crypto.MAGIC)


def test_a_wrong_password_does_not_open_it(kitchen: TestClient) -> None:
    body = kitchen.post(API, json={"password": SEALED_PASSWORD}).content
    with pytest.raises(export_crypto.CantOpen) as error:
        _open_sealed(body, "some other passphrase")
    assert str(error.value) == export_crypto.WRONG_WORDS


@pytest.mark.parametrize("password", ["", "short", "1234567", "é" * 3 + "x"])
def test_a_password_that_is_too_short_is_refused_without_echoing_it(
    kitchen: TestClient, password: str
) -> None:
    response = kitchen.post(API, json={"password": password})
    assert response.status_code == 422
    assert response.json()["code"] == "password_length"
    assert "8 to 1,024 characters" in response.json()["detail"]
    assert password not in response.text or password == ""


def test_the_longest_password_is_accepted_and_one_more_is_refused(kitchen: TestClient) -> None:
    longest = "p" * 1024
    ok = kitchen.post(API, json={"password": longest})
    assert ok.status_code == 200
    assert b"".join(export_crypto.decrypt(io.BytesIO(ok.content), longest))
    assert kitchen.post(API, json={"password": longest + "p"}).status_code == 422
    huge = kitchen.post(API, json={"password": "p" * 10_000})
    assert huge.status_code == 422
    assert "pppp" not in huge.text


def test_a_lone_surrogate_in_the_password_is_a_plain_refusal(kitchen: TestClient) -> None:
    response = kitchen.post(
        API,
        content='{"password": "\\ud800 and more letters"}',
        headers={"content-type": "application/json"},
    )
    assert response.status_code == 422


def test_a_missing_or_null_password_is_refused_not_exported_in_the_clear(
    kitchen: TestClient,
) -> None:
    assert kitchen.post(API, json={}).status_code == 422
    assert kitchen.post(API, json={"password": None}).status_code == 422


def test_the_password_in_the_address_is_not_taken(kitchen: TestClient) -> None:
    response = kitchen.post(f"{API}?password={SEALED_PASSWORD}", json={})
    assert response.status_code == 422
    assert SEALED_PASSWORD not in response.text


def test_a_member_cannot_export_with_a_password(member: TestClient) -> None:
    response = member.post(API, json={"password": SEALED_PASSWORD})
    assert response.status_code == 403
    assert SEALED_PASSWORD not in response.text


def test_signed_out_cannot_export_with_a_password(client: TestClient) -> None:
    assert client.post(API, json={"password": SEALED_PASSWORD}).status_code == 401


def test_the_password_is_nowhere_in_the_database(kitchen: TestClient) -> None:
    kitchen.post(API, json={"password": SEALED_PASSWORD})
    with kitchen.app.state.sessionmaker() as db:  # type: ignore[attr-defined]
        from sqlalchemy import text

        for table in Base.metadata.sorted_tables:
            rows = db.execute(text(f'SELECT * FROM "{table.name}"')).all()  # noqa: S608
            assert SEALED_PASSWORD not in repr(rows), table.name


def test_a_second_export_while_a_key_is_being_made_gets_429_before_any_key_work(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[int] = []
    real = export_crypto._key

    def counted(*args: object) -> bytes:
        calls.append(1)
        return real(*args)  # type: ignore[arg-type]

    monkeypatch.setattr(export_crypto, "_key", counted)
    assert export_crypto._MAKING_A_KEY.acquire(blocking=False)  # a key is being made
    try:
        busy = kitchen.post(API, json={"password": SEALED_PASSWORD})
        assert busy.status_code == 429
        assert busy.json()["code"] == "export_busy"
        assert busy.json()["detail"] == "An export is being made. Try again in a moment."
        assert SEALED_PASSWORD not in busy.text
        assert calls == []
        assert kitchen.get(API).status_code == 200  # the plain export has no such limit
    finally:
        export_crypto._MAKING_A_KEY.release()
    assert kitchen.post(API, json={"password": SEALED_PASSWORD}).status_code == 200


def test_a_stalled_download_does_not_keep_anyone_else_out(kitchen: TestClient) -> None:
    """A client that reads a little and stops holds nothing but its own stream."""
    with kitchen.stream("POST", API, json={"password": SEALED_PASSWORD}) as slow:
        assert slow.status_code == 200
        next(slow.iter_bytes(chunk_size=16))  # reads a little and stalls, still open
        second = kitchen.post(API, json={"password": SEALED_PASSWORD})
        assert second.status_code == 200


def test_a_refused_password_does_not_keep_the_place(kitchen: TestClient) -> None:
    assert kitchen.post(API, json={"password": "short"}).status_code == 422
    assert kitchen.post(API, json={"password": SEALED_PASSWORD}).status_code == 200


def test_an_error_while_making_the_key_does_not_keep_the_place(
    kitchen: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def boom(*_a: object) -> bytes:
        raise MemoryError("no room")

    with monkeypatch.context() as patch:
        patch.setattr(export_crypto, "_key", boom)
        with pytest.raises(MemoryError):
            kitchen.post(API, json={"password": SEALED_PASSWORD})
    assert kitchen.post(API, json={"password": SEALED_PASSWORD}).status_code == 200


def test_a_link_in_place_of_the_households_folder_is_not_followed(tmp_path: Path) -> None:
    """PR #258 L2: the check looked only at the last part of the path, so a link standing where
    the household's photo folder should be was followed to whatever it points at."""
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    (elsewhere / ("a" * 32 + ".jpg")).write_bytes(b"not for the export")
    (elsewhere / ("a" * 32 + "-list.jpg")).write_bytes(jpeg())
    store = tmp_path / "store"
    store.mkdir()
    household_folder(store, 1).symlink_to(elsewhere, target_is_directory=True)
    assert export.photo_files(store, 1, _rows("a" * 32)) == []
    # Swapped in after the list was made: the file is skipped when it is opened.
    doc = {"format": export.FORMAT, "version": 1, "tables": {}}
    data = b"".join(export.zip_stream(doc, [household_folder(store, 1) / ("a" * 32 + ".jpg")]))
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert archive.namelist() == [export.DOCUMENT]


def test_a_link_at_the_photos_root_itself_still_exports(tmp_path: Path) -> None:
    """`/data/photos` pointing elsewhere is a normal setup: it keeps working."""
    real = tmp_path / "bigger-disk"
    folder = household_folder(real, 1)
    folder.mkdir(parents=True)
    (folder / ("a" * 32 + ".jpg")).write_bytes(jpeg())
    (folder / ("a" * 32 + "-list.jpg")).write_bytes(jpeg())
    store = tmp_path / "photos"
    store.symlink_to(real, target_is_directory=True)
    found = export.photo_files(store, 1, _rows("a" * 32))
    assert [p.name for p in found] == ["a" * 32 + "-list.jpg", "a" * 32 + ".jpg"]
    doc = {"format": export.FORMAT, "version": 1, "tables": {}}
    data = b"".join(export.zip_stream(doc, found))
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        assert sorted(archive.namelist()) == sorted(
            [export.DOCUMENT, "photos/" + "a" * 32 + ".jpg", "photos/" + "a" * 32 + "-list.jpg"]
        )


def test_a_file_that_resolves_outside_the_photos_root_is_skipped(tmp_path: Path) -> None:
    store = tmp_path / "store"
    household_folder(store, 1).mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    for name in ("a" * 32 + ".jpg", "a" * 32 + "-list.jpg"):
        (outside / name).write_bytes(jpeg())
        (household_folder(store, 1) / name).symlink_to(outside / name)
    assert export.photo_files(store, 1, _rows("a" * 32)) == []


def test_a_pipe_put_in_place_of_a_photo_is_skipped_and_the_export_finishes(
    tmp_path: Path,
) -> None:
    """PR #258 review: a named pipe swapped in for a photo after the list was made held the
    export for ever (opening one waits for a writer). It is opened without waiting and skipped."""
    store = tmp_path / "store"
    folder = household_folder(store, 1)
    folder.mkdir(parents=True)
    name = "a" * 32
    os.mkfifo(folder / (name + ".jpg"))
    (folder / (name + "-list.jpg")).write_bytes(jpeg())
    doc = {"format": export.FORMAT, "version": 1, "tables": {}}
    out: list[bytes] = []

    def run() -> None:
        both = [folder / (name + ".jpg"), folder / (name + "-list.jpg")]
        out.append(b"".join(export.zip_stream(doc, both)))

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    worker.join(timeout=10)
    assert not worker.is_alive(), "the export hung on a pipe"
    with zipfile.ZipFile(io.BytesIO(out[0])) as archive:
        assert sorted(archive.namelist()) == [export.DOCUMENT, "photos/" + name + "-list.jpg"]
