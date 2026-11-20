# Mealwright export format, version 1

Settings › Backups & your data › **Export everything** (Admins only) gives one zip file,
`mealwright-export-YYYY-MM-DD.zip`. It holds everything of one household, so the data can be
read without Mealwright or brought into another program. (Spec section 7, "Export".)

## Summary

- `mealwright-export.json`: every row of every household table, as JSON, read in one database
  snapshot.
- `photos/`: the household's recipe photos, as Mealwright stores them.
- Left out on purpose (cabledrawer 12 Nov): sign-ins (the `session` table, and the
  `join_link` table of sign-in links made for people), passwords (`login.password_hash`),
  API tokens (the `api_token` table; only an admin at the screen makes them, so make them
  again) and the single sign-on client secret (sealed with `secret.key`; type it again on a
  new server; these two cabledrawer 13 Nov), and (cabledrawer 13 Nov) `login.sso_refused_at`
  (this server's own mark of a refused login) and the `former_name` table (old names kept for 15 days so Report a problem
  can remove them), and (0.9.5) `login.link_used_at` (when a sign-in or Reset password link
  was last used) and the `sso_account` table (single sign-on sign-ins waiting for an admin,
  refused or unlinked). Whoever restores from an export sets passwords again (cabledrawer 13 Nov).
- Optional password (cabledrawer 13 Nov; built in 0.9.5): with a password the zip is sent
  encrypted, as `mealwright-export-YYYY-MM-DD.zip.mwenc` (see "The encrypted file"). Without
  one the file is the plain zip described here, byte for byte as before. The password can't be
  recovered: Mealwright keeps it nowhere.
- A full copy for disaster recovery is a backup, not an export: see `docs/restore.md`.

## The zip

| Entry | What |
|---|---|
| `mealwright-export.json` | The document below, UTF-8. Always the first entry. |
| `photos/<32 hex>.jpg` | A recipe photo, large copy. Stored as is (not compressed again). |
| `photos/<32 hex>-list.jpg` | The same photo's small copy for lists. |

A photo's name is the `file_key` of its row in the `recipe_photo` table.

## The document

```json
{
  "format": "mealwright-export",
  "version": 1,
  "app_version": "0.9.0",
  "database_revision": "b2f7c4e8a915",
  "exported_at": "2026-11-13T10:00:00+00:00",
  "household_id": 1,
  "left_out": {
    "tables": {
      "session": "who is signed in where (sign-in cookies)",
      "join_link": "sign-in links made for people",
      "api_token": "API tokens, which only an admin at the screen makes",
      "former_name": "old names kept for 15 days so Report a problem can remove them",
      "sso_account": "single sign-on sign-ins waiting for an admin, refused or unlinked"
    },
    "columns": {
      "login.password_hash": "passwords, even scrambled",
      "sso_settings.client_secret_sealed": "the single sign-on client secret",
      "login.sso_refused_at": "the mark of a login the sign-in server refused",
      "login.link_used_at": "when a sign-in or reset link was last used"
    }
  },
  "tables": {
    "household": [{"id": 1, "name": "Home", "...": "..."}],
    "login": [{"id": 1, "household_id": 1, "username": "sam", "...": "..."}],
    "recipe": []
  }
}
```

- `format` is always `"mealwright-export"`. A reader refuses anything else.
- `version` is this page's version: 1. It changes only when the layout of the file changes, not
  when a table gains a column (that is what `database_revision` says).
- `database_revision` is the database's Alembic revision. A table's columns are those of
  `backend/src/mealwright/models.py` at that revision.
- `tables` has one key per table, even when the table is empty. Each row is an object, one key
  per column, named as in the database.
  - Only the household's own rows: `household.id`, and `household_id` in every other table, is
    `household_id` above. Another household's rows are never in it.
  - Rows are in primary-key order.
  - Tables come in an order they can be put back in: a table after the tables it points at. One
    exception: `change` and `list_tick` point at each other (`change.tick_id`). Put them back
    with foreign key checks off, or fill `change.tick_id` after `list_tick`.

### Values

| Database type | In JSON |
|---|---|
| Whole number, true or false, text | As is (`true`/`false`, numbers, strings). |
| Decimal (amounts) | A string, e.g. `"0.25"`, so nothing is rounded. |
| Date | `"YYYY-MM-DD"`. |
| Date and time | ISO 8601. Times with a zone are UTC (`+00:00`). |
| JSON columns | The JSON itself. |
| Empty | `null`. |

## The encrypted file (encryption format 1; 0.9.5)

The format below follows cabledrawer's decision of 13 Nov: an optional password that
encrypts the file. The choices of cipher, key derivation and costs are the builder's.

Settings › Backups & your data › **Export everything** has an optional **Password** box. With a password
the screen asks the server for the file with `POST /api/v1/export` and a JSON body
`{"password": "..."}`; the password travels in the body only (never in the address), is
never stored or logged, and is 8 to 1,024 characters (counted after Unicode NFC). An admin only,
as the plain export. The answer is `application/octet-stream`, named
`mealwright-export-YYYY-MM-DD.zip.mwenc`, and it holds the plain zip above, encrypted. `GET
/api/v1/export` (no password) is unchanged.

**Layout** (all numbers big-endian):

| Bytes | What |
|---|---|
| 0 to 7 | Magic `MWEXPORT`. |
| 8 | Encrypted-file format version: `1`. |
| 9 | Key derivation: `1` = Argon2id (version 1.3). |
| 10 | Cipher: `1` = AES-256-GCM. |
| 11 to 14 | Argon2id passes (time cost), `3`. |
| 15 to 18 | Argon2id memory in KiB, `65536` (64 MiB). |
| 19 to 22 | Argon2id lanes (parallelism), `1`. |
| 23 to 38 | Salt, 16 random bytes (new for every file). |
| 39 to 42 | Plain bytes per chunk, `65536` (the last chunk may be shorter). |
| 43 on | Chunks. |

That is the **header**: 43 bytes. The key is the 32-byte Argon2id output for the password (as
UTF-8, after Unicode NFC) and the salt.

**Chunks.** Each chunk is AES-256-GCM output: the encrypted bytes, then the 16-byte tag.
Chunk 0 is a fixed "key check": the 17 bytes `mealwright export`. Chunks 1, 2, 3 and on hold
the plain zip, cut into pieces of the chunk size above; the last piece (which may be shorter,
or empty) is the last chunk. Chunk *n*:

- nonce (12 bytes): four zero bytes, then *n* as 8 bytes. A new key for every file and a
  counter for the nonce mean no nonce is ever used twice under one key;
- additional authenticated data: the whole 43-byte header, then *n* as 8 bytes, then one byte,
  `1` for the last chunk and `0` for every other.

So a changed header, a changed, moved, repeated or dropped chunk, a file cut short (even at a
chunk's end) or bytes added after the last chunk is noticed: no chunk then opens. A file is
good only when its last chunk, marked last, opens and nothing follows it. The file can be
written as it is made: nothing but the current chunk and the one before it are held, so a large
export (many photos) is never held whole.

**Costs.** 64 MiB, 3 passes and 1 lane take about 0.2 s on a desktop processor (6 cores,
measured). A Raspberry Pi 4 was not at hand; it is expected to take about 5 to 8
times as long, 1 to 2 s, and 64 MiB is within what a 2 GB Pi spares. The costs are in the header, so a
later version may raise them. A reader accepts only 1 to 10 passes, 8 MiB to 256 MiB, 1 to 4
lanes and chunks of 1 KiB to 1 MiB, and refuses anything else before doing any work, so a
hostile file can't ask for gigabytes or hours.

**Wrong password or damage.** When chunk 0 doesn't open, the password is wrong (or the header
was changed). When a later chunk doesn't open, or the last chunk is missing, the file is
damaged or cut short. A reader says so in one plain sentence each and writes nothing to the
household before the whole file has been checked.

**Opening one by hand** (needs Python and `cryptography` 44 or newer on OpenSSL 3.2 or newer
for Argon2id; `argon2-cffi`'s `argon2.low_level.hash_secret_raw` gives the same key). It
writes the plain zip, or stops with an error. Test: `backend/tests/test_export_crypto.py` runs
this very snippet.

```python
import struct
import unicodedata

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.argon2 import Argon2id


def open_export(source_path, zip_path, password):
    head = struct.Struct(">8sBBBIII16sI")
    with open(source_path, "rb") as source:
        header = source.read(head.size)
        magic, version, kdf, cipher, t, m, p, salt, chunk = head.unpack(header)
        if (magic, version, kdf, cipher) != (b"MWEXPORT", 1, 1, 1):
            raise ValueError("not an encrypted export")
        if not (1 <= t <= 10 and 8192 <= m <= 262144 and 1 <= p <= 4):
            raise ValueError("costs out of range")
        if not 1024 <= chunk <= 1048576:
            raise ValueError("chunk size out of range")
        secret = unicodedata.normalize("NFC", password).encode("utf-8")
        key = Argon2id(salt=salt, length=32, iterations=t, lanes=p, memory_cost=m).derive(secret)
        aes = AESGCM(key)

        def read_chunk(size):
            return source.read(size)

        def nonce(n):
            return b"\x00\x00\x00\x00" + n.to_bytes(8, "big")

        def aad(n, last):
            return header + n.to_bytes(8, "big") + (b"\x01" if last else b"\x00")

        # Chunk 0: the key check (a wrong password fails here).
        check = aes.decrypt(nonce(0), read_chunk(17 + 16), aad(0, False))
        if check != b"mealwright export":
            raise ValueError("wrong password")
        # The rest: a chunk is the last one when nothing follows it.
        with open(zip_path, "wb") as out:
            n, current = 1, read_chunk(chunk + 16)
            while True:
                following = read_chunk(chunk + 16) if current else b""
                last = not following
                out.write(aes.decrypt(nonce(n), current, aad(n, last)))
                if last:
                    break
                n, current = n + 1, following


# open_export("mealwright-export-2026-11-14.zip.mwenc", "export.zip", "your password")
```

If it raises, the file is damaged, cut short or the password is wrong; delete `export.zip`.

## Reading one

`mealwright.export.read(path)` returns the document and the photos (name to bytes); the test
`backend/tests/test_export.py` exports a household and reads it back. Any zip tool opens the
file; any JSON reader reads the document.

## Changes

- Encrypted file, format 1 (0.9.5): the optional password, in its own section above. The zip
  and the document are unchanged (still version 1).
- Version 1 (0.9.0): first version.
