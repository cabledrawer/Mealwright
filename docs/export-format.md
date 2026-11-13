# Mealwright export format, version 1

Settings → Your data → **Export everything** (Admins only) gives one zip file,
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
  can remove them). Whoever restores from an export sets passwords again (cabledrawer 13 Nov).
- Optional password encryption (cabledrawer's decision) is **not built yet**. It comes in a later
  version of this page; an export today is a plain zip, so keep it somewhere safe.
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
      "former_name": "old names kept for 15 days so Report a problem can remove them"
    },
    "columns": {
      "login.password_hash": "passwords, even scrambled",
      "sso_settings.client_secret_sealed": "the single sign-on client secret",
      "login.sso_refused_at": "the mark of a login the sign-in server refused"
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

## Reading one

`mealwright.export.read(path)` returns the document and the photos (name to bytes); the test
`backend/tests/test_export.py` exports a household and reads it back. Any zip tool opens the
file; any JSON reader reads the document.

## Changes

- Version 1 (0.9.0): first version.
