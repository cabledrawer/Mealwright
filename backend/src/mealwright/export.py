"""Export everything (spec section 7; the format: docs/dev/export-format.md, version 1).

One zip file with everything a household keeps:

- `mealwright-export.json`: a versioned JSON document with every row of every household table,
  read in one database snapshot, so it is consistent even while people keep using Mealwright.
- `photos/<name>.jpg`: the household's recipe photo files, as stored (large and list copies).

Some things are left out on purpose (cabledrawer 12 Nov; the last two proposed, for cabledrawer), and
the document says so in `left_out`: the `session` table (who is signed in where: a stolen copy
must never sign anyone in), the `join_link` table (sign-in links made for people, 0.9 A1),
`login.password_hash` (a copy of the file must not let anyone try passwords offline), the
`api_token` table (0.9 O2) and `sso_settings.client_secret_sealed` (the single sign-on client
secret; the admin types it again).

The zip is written as it is sent (streamed), never kept on the server. Nothing here makes a
network connection.
"""

import json
import re
import zipfile
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from alembic.migration import MigrationContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from mealwright import __version__
from mealwright.db import Base
from mealwright.models import utcnow
from mealwright.photos import household_folder

FORMAT = "mealwright-export"
VERSION = 1
DOCUMENT = "mealwright-export.json"
PHOTOS = "photos/"

# Left out of every export (see the module's note).
# `join_link` (0.9 A1) joined when D1 met the people work: a sign-in link is a sign-in too
# (cabledrawer 12 Nov).
LEFT_OUT_TABLES = {
    "session": "who is signed in where (sign-in cookies)",
    "join_link": "sign-in links made for people",
    # O2 review r1, finding 2 (proposed, for cabledrawer): only a token's SHA-256 is kept, but that
    # is all it takes to tell a made-up token from a real one, so it doesn't leave either.
    "api_token": "API tokens, which only an admin at the screen makes",
}
LEFT_OUT_COLUMNS = {
    ("login", "password_hash"): "passwords, even scrambled",
    # The admin types the client secret again if an export is ever put back (proposed, for
    # cabledrawer; the rest of the single sign-on setup is exported).
    ("sso_settings", "client_secret_sealed"): "the single sign-on client secret",
}

_PHOTO_FILE = re.compile(r"^[0-9a-f]{32}(-list)?\.jpg$")
_CHUNK = 64 * 1024


def _value(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):  # pragma: no cover (no table holds bytes today)
        return value.hex()
    return value


def document(db: Session, household_id: int) -> dict[str, Any]:
    """Every household row, table by table, in the order they can be put back (a table comes
    after the tables it points at). Read in one transaction: one consistent snapshot."""
    connection = db.connection()  # starts the read transaction: all tables from one snapshot
    revision = MigrationContext.configure(connection).get_current_revision()
    tables: dict[str, list[dict[str, Any]]] = {}
    for table in Base.metadata.sorted_tables:
        if table.name in LEFT_OUT_TABLES:
            continue
        owner = table.c.id if table.name == "household" else table.c.household_id
        columns = [c for c in table.columns if (table.name, c.name) not in LEFT_OUT_COLUMNS]
        primary = list(table.primary_key.columns)
        rows = connection.execute(
            select(*columns).where(owner == household_id).order_by(*primary)
        ).mappings()
        tables[table.name] = [{key: _value(value) for key, value in row.items()} for row in rows]
    return {
        "format": FORMAT,
        "version": VERSION,
        "app_version": __version__,
        "database_revision": revision,
        "exported_at": utcnow().isoformat(),
        "household_id": household_id,
        "left_out": {
            "tables": dict(LEFT_OUT_TABLES),
            "columns": {
                f"{table}.{column}": why for (table, column), why in LEFT_OUT_COLUMNS.items()
            },
        },
        "tables": tables,
    }


def photo_files(store: Path, household_id: int) -> list[Path]:
    """The household's photo files (never a half-written upload or anything else)."""
    folder = household_folder(store, household_id)
    try:
        return sorted(p for p in folder.iterdir() if _PHOTO_FILE.match(p.name) and p.is_file())
    except OSError:  # no photos yet
        return []


class _Pipe:
    """A write-only file the zip writes into; what it holds is handed on piece by piece."""

    def __init__(self) -> None:
        self.parts: list[bytes] = []

    def write(self, data: bytes) -> int:
        if data:
            self.parts.append(bytes(data))
        return len(data)

    def flush(self) -> None:
        pass

    def close(self) -> None:
        pass

    def take(self) -> bytes:
        out = b"".join(self.parts)
        self.parts.clear()
        return out


def zip_stream(doc: dict[str, Any], photos: list[Path]) -> Iterator[bytes]:
    """The export file, piece by piece. A photo removed meanwhile is skipped."""
    pipe = _Pipe()
    with zipfile.ZipFile(pipe, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(DOCUMENT, json.dumps(doc, ensure_ascii=False, indent=1))
        yield pipe.take()
        for path in photos:
            try:
                source = path.open("rb")
            except OSError:
                continue
            with source:
                info = zipfile.ZipInfo(PHOTOS + path.name, date_time=_zip_time(path))
                info.compress_type = zipfile.ZIP_STORED  # a JPEG doesn't get smaller
                with archive.open(info, "w") as entry:
                    while chunk := source.read(_CHUNK):
                        entry.write(chunk)
                        yield pipe.take()
            yield pipe.take()
    yield pipe.take()


def _zip_time(path: Path) -> tuple[int, int, int, int, int, int]:
    try:
        moment = datetime.fromtimestamp(path.stat().st_mtime)  # zip times are local
    except OSError:
        moment = datetime(1980, 1, 1)
    if moment.year < 1980:
        moment = datetime(1980, 1, 1)
    return (moment.year, moment.month, moment.day, moment.hour, moment.minute, moment.second)


def file_name(day: date) -> str:
    return f"mealwright-export-{day.isoformat()}.zip"


def read(path_or_file: Any) -> tuple[dict[str, Any], dict[str, bytes]]:
    """Read an export back: its document and its photos (name to bytes). For tests and for
    whoever brings the data back in; refuses a file that isn't a Mealwright export."""
    with zipfile.ZipFile(path_or_file) as archive:
        doc = json.loads(archive.read(DOCUMENT))
        if doc.get("format") != FORMAT or not isinstance(doc.get("version"), int):
            raise ValueError("That isn't a Mealwright export.")
        photos = {
            name.removeprefix(PHOTOS): archive.read(name)
            for name in archive.namelist()
            if name.startswith(PHOTOS) and not name.endswith("/")
        }
    return doc, photos
