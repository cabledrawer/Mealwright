# Backing up Mealwright

This is a separate page from [restore.md](restore.md), which says how to put a backup back. This one says what to back up and how.

## What lives in the data folder

Everything Mealwright keeps is in one folder, `/data` inside the container (the folder you mount, `./data` in `compose.example.yaml`):

| What | Where | What it is |
| --- | --- | --- |
| The database | `mealwright.db` (and, while it runs, `mealwright.db-wal` and `mealwright.db-shm`) | Every recipe, plan, list, pantry item, person, login and setting. |
| Recipe photos | `photos/` | The photo files. They are **not** in the database. |
| Mealwright's own backups | `backups/` | See below. |
| The key for secrets | `secret.key` | Made the first time a secret is stored (the single sign-on client secret). Without it, a backup can't open that secret. Back it up, and keep it as private as the database. |
| The log | `logs/` | Errors and sign-in lines, kept for 14 days. Leave it out of copies. |

Only the user Mealwright runs as (UID 10001) can read these files. See [hardening.md](hardening.md) for how a backup tool on the host reads them.

## Mealwright backs up its database by itself

Settings → Your data shows it. An admin can change how often and how many.

- **How often:** daily at 03:00 (the default), twice a day (03:00 and 15:00) or weekly (Mondays, 03:00). The time is the household's own.
- **Keep:** "Last 7" by default. An admin can choose from the last 1 to the last 30. Older ones are deleted.
- **Back up now** makes one straight away.
- **Where:** `data/backups/backup-<date>-<time>.db` (the date and time in UTC). Each is one whole file that opens on its own, made while Mealwright is running and safe to copy.
- **A server that was off at 03:00** backs up when it starts. After a failed backup it tries again an hour later, and Settings → Your data says the last one failed.
- Mealwright also keeps other copies in the same folder, which the "Keep" setting never deletes: `pre-upgrade-….db` (made before a version changes the database; the newest three are kept, see [upgrade.md](upgrade.md)) and `before-delete-everything-….db` (made before Delete everything).

**These cover the database only.** Photos are files in `data/photos`, so they are in no backup file.

**They sit on the same disk as Mealwright.** If that disk dies, they go too. Copy them somewhere else.

## Copying everything safely

You want one copy that holds the database, the photos and `secret.key`, kept on another disk or machine. Choose one:

**1. Stop Mealwright, then copy the whole folder.** The safest way: nothing is writing while you copy.

```bash
cd <folder>
docker compose stop mealwright
sudo tar -C <folder> --exclude=data/logs -czf "<another disk>/mealwright-data-$(date +%Y%m%d-%H%M).tar.gz" data
docker compose start mealwright
```

`<folder>` is the folder holding `compose.yaml` and `data`. `<another disk>` is where the copy goes. Mealwright is off for as long as the copy takes.

**2. Copy while it runs.** A tool such as restic, borg or rsync can copy `data/photos`, `data/secret.key` and `data/backups` while Mealwright runs. Don't rely on the copied `mealwright.db`: a copy taken while Mealwright runs can catch it and its `-wal` and `-shm` files at different moments. The newest file in `backups/` is whole, so a restore uses that. If you want a fresh one first, press Back up now. A backup tool on the host needs to run as root or as UID 10001 (see [hardening.md](hardening.md)).

Either way, leave out `logs`, and keep at least the last three copies. A copy that never left the server isn't a backup against the server being lost.

## Export is not a backup

Settings → Your data → Export everything gives a zip of your recipes, plans, lists, pantry, people and settings, with the photos, so you can read your data without Mealwright. It leaves out passwords, API tokens, who is signed in where, and the single sign-on secret. It is made for taking your data away, not for restoring a server. The format is in `docs/export-format.md`.

TODO(cabledrawer): I found no screen or command in the code that loads an export back into Mealwright. Is that right for 0.9.5? If so, say it here in your own words.

## Test your backup

A backup you have never tried to restore may not work. Try [restore.md](restore.md) on a spare machine now and then.
