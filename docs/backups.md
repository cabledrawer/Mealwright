# Backing up Mealwright

This is a separate page from [restore.md](restore.md), which says how to put a backup back. This one says what to back up and how.

## What lives in the data folder

Everything Mealwright keeps is in one folder, `/data` inside the container (the folder you mount, `./data` in `compose.example.yaml`):

| What | Where | What it is |
| --- | --- | --- |
| The database | `mealwright.db` (and, while it runs, `mealwright.db-wal` and `mealwright.db-shm`) | Every recipe, plan, list, pantry item, person, login and setting. |
| Recipe photos | `photos/` | The photo files. They are **not** in the database. |
| Mealwright's own backups | `backups/` | See below. They hold the photos too, unless you switch that off. |
| The key for secrets | `secret.key` | Made the first time a secret is stored (the single sign-on client secret). Without it, a backup can't open that secret. Back it up, and keep it as private as the database. |
| The log | `logs/` | Errors and sign-in lines, kept for 14 days. Leave it out of copies. |

Only the user Mealwright runs as (UID 10001) can read these files. See [hardening.md](hardening.md) for how a backup tool on the host reads them.

## Mealwright backs up its database by itself

Settings → Your data shows it. An admin can change how often and how many.

- **How often:** daily at 03:00 (the default), twice a day (03:00 and 15:00) or weekly (Mondays, 03:00). The time is the household's own.
- **Keep:** "Last 7" by default. An admin can choose from the last 1 to the last 30. Older ones are deleted.
- **Back up now** makes one straight away.
- **Include photos** (on by default; an admin can switch it off) puts the recipe photos in each backup. The switch is in Settings → Your data, next to How often and Keep, and it applies to the daily and by-hand backups and to the safety copy made before an upgrade. It changes the backups made from then on, not the ones already there.
- **Where:** `data/backups/backup-<date>-<time>.db` (the date and time in UTC). Each is one whole file that opens on its own, made while Mealwright is running and safe to copy. With photos, a folder of the same name with `-photos` in place of `.db` sits beside it (`backup-<date>-<time>-photos`), in the same layout as `data/photos`. It is deleted with its backup when old ones are trimmed.
- **A server that was off at 03:00** backs up when it starts. After a failed backup it tries again an hour later, and Settings → Your data says the last one failed.
- Mealwright also keeps other copies in the same folder, which the "Keep" setting never deletes: `pre-upgrade-….db` (made before a version changes the database; the newest three are kept, see [upgrade.md](upgrade.md)) and `before-delete-everything-….db` (made before Delete everything).

**The photos are in a folder beside the backup, not in the `.db` file.** With Include photos on (the usual) every backup, and the safety copies before an upgrade and before Delete everything, has one. With it off, a backup holds everything but the photos, and restoring it keeps the photos already on the server; a recipe whose photo file is missing just shows no photo.

One tiny gap (proposed, for cabledrawer): a photo saved and deleted again within the few milliseconds a backup takes to copy the database can be missing from that backup's folder; restoring shows it as a missing photo. Symbolic links in the photos folder are skipped, never followed.

**What a backup costs in room** (proposed, for cabledrawer). The photo folders are made with hard links: a photo file is never changed once saved, so a backup's folder points at the same file on the disk, and a photo that hasn't changed takes no extra room however many backups hold it. A photo you delete stays on the disk until the last backup that holds it is trimmed. Where a link can't be made (the backups folder is on another disk or a share that can't), the photo is copied instead, and each backup then takes the full size of the photos. If the disk is too full, the backup fails with one plain line on the screen and the log, nothing half-made is left, and the older backups stay.

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

**2. Copy while it runs.** A tool such as restic, borg or rsync can copy `data/photos`, `data/secret.key` and `data/backups` while Mealwright runs. The photo folders in `backups` are hard links to the files in `photos`: restic and borg handle that well, `tar` keeps the links, and `rsync` needs `-H` (`rsync -aH`) or it writes each backup's photos out in full. Don't rely on the copied `mealwright.db`: a copy taken while Mealwright runs can catch it and its `-wal` and `-shm` files at different moments. The newest file in `backups/` is whole, so a restore uses that. If you want a fresh one first, press Back up now. A backup tool on the host needs to run as root or as UID 10001 (see [hardening.md](hardening.md)).

Either way, leave out `logs`, and keep at least the last three copies. A copy that never left the server isn't a backup against the server being lost.

## Export is not a backup

Settings → Your data → Export everything gives a zip of your recipes, plans, lists, pantry, people and settings, with the photos, so you can read your data without Mealwright. It leaves out passwords, API tokens, who is signed in where, and the single sign-on secret. It is made for taking your data away, not for restoring a server. The format is in `docs/export-format.md`.

TODO(cabledrawer): I found no screen or command in the code that loads an export back into Mealwright. Is that right for 0.9.5? If so, say it here in your own words.

## Test your backup

A backup you have never tried to restore may not work. Try [restore.md](restore.md) on a spare machine now and then.
