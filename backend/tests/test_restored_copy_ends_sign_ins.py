"""A database put back from a copy ends the sign-ins kept in it (B7 R5, Fable break-it review of
0.9.5-beta.1): a token, cookie or link stopped after the copy was made must not work again."""

import shutil
import sqlite3
from collections.abc import Iterator
from contextlib import closing, contextmanager
from pathlib import Path

from conftest import ADMIN
from fastapi.testclient import TestClient
from sqlalchemy import Engine

from mealwright import backups
from mealwright.config import Settings
from mealwright.main import create_app

API = "/api/v1"


@contextmanager
def _started(settings: Settings) -> Iterator[TestClient]:
    """The app running, as one start of the container; stopped (connections closed) after."""
    with TestClient(create_app(settings), base_url="https://testserver") as app:
        yield app
    app.app.state.engine.dispose()  # type: ignore[attr-defined]


def _one(path: Path, sql: str) -> object:
    with closing(sqlite3.connect(path)) as raw:
        return raw.execute(sql).fetchone()[0]


def _token_works(app: TestClient, token: str) -> bool:
    other = TestClient(app.app, base_url="https://testserver")
    other.headers["Authorization"] = f"Bearer {token}"
    return other.get(f"{API}/people").status_code == 200


def test_a_restored_copy_signs_everyone_out_and_stops_its_tokens(settings: Settings) -> None:
    database = settings.data_dir / "mealwright.db"
    folder = settings.data_dir / backups.FOLDER
    with _started(settings) as app:
        assert app.post(f"{API}/setup", json=ADMIN).status_code == 201
        made = app.post(f"{API}/api-tokens", json={"name": "Leaked", "scope": "full"})
        token = made.json()["token"]
        token_id = app.get(f"{API}/api-tokens").json()["tokens"][0]["id"]
        engine: Engine = app.app.state.engine  # type: ignore[attr-defined]
        with engine.begin() as connection:  # a reset link not yet used (review r1 L4)
            connection.exec_driver_sql(
                "INSERT INTO join_link (household_id, login_id, kind, token_hash, created_at,"
                " expires_at) VALUES (1, 1, 'reset', 'x', '2026-11-16 00:00:00',"
                " '2999-01-01 00:00:00')"
            )
        copy = backups.back_up(engine, folder, 7).path
        assert _one(copy, "SELECT count(*) FROM join_link") == 1
        # Leaked: the admin stops the token after the backup was made.
        assert app.delete(f"{API}/api-tokens/{token_id}").status_code == 204
        assert not _token_works(app, token)
        cookies = dict(app.cookies)
    # The copy carries the mark; the live database doesn't.
    assert _one(copy, "PRAGMA user_version") == backups.COPY_MARK
    assert _one(database, "PRAGMA user_version") == 0

    # A plain restart keeps everyone signed in.
    with _started(settings) as app:
        app.cookies.update(cookies)
        assert app.get(f"{API}/people").status_code == 200

    # Restore, as docs/restore.md says: the copy put in place of the database.
    for extra in ("-wal", "-shm"):
        (settings.data_dir / f"mealwright.db{extra}").unlink(missing_ok=True)
    shutil.copyfile(copy, database)
    with _started(settings) as app:
        assert not _token_works(app, token)
        app.cookies.update(cookies)
        assert app.get(f"{API}/people").status_code == 401
    assert _one(database, "PRAGMA user_version") == 0  # once only: the mark is cleared
    assert _one(database, "SELECT count(*) FROM session") == 0
    assert _one(database, "SELECT count(*) FROM join_link") == 0
    assert _one(database, "SELECT count(*) FROM api_token WHERE revoked_at IS NULL") == 0
