# How to restore Mealwright from a backup

Mealwright backs its database up by itself, daily at 03:00 by default, into the `backups`
folder inside its data folder (Settings → Your data). This page says how to put one of those
backups back. `backend/scripts/restore_test.sh` follows these steps on a fresh container and
checks that signing in shows the data.

Below, `<folder>` is the folder holding `compose.yaml` and the `data` folder (the data folder
is `/data` inside the container).

## What a backup holds

- **The database**: every recipe, plan, list, pantry item, person, login and setting. One file,
  `data/backups/backup-<date>-<time>.db` (the date and time in UTC).
- **The single sign-on client secret opens only with `data/secret.key`** (proposed, for cabledrawer). A backup keeps the secret sealed; on a new server without that key file, Mealwright can't open it, password sign-in works again, and an admin types the secret again in Settings → Sign-in → Single sign-on. An admin who has only ever signed in with single sign-on has no password: run the `reset-admin` command for them first (proposed, for cabledrawer). An export leaves the secret out altogether, and API tokens too: make new ones.
- **Not the photos.** Recipe photos are files in `data/photos`. A restore leaves them where they
  are. If the disk itself is lost, the photos come back only from a copy of the whole data
  folder, so copy the data folder (or at least `backups` and `photos`) to another disk or your
  NAS as well. Backups on the same disk as Mealwright go when the disk goes.
- **Mealwright's own backups are the safe copy of the database.** A copy of the data folder
  taken while Mealwright runs can catch `mealwright.db` and its `-wal` and `-shm` files at
  different moments. The files in `backups` are whole and complete, so a restore uses the newest
  of those, not the copied `mealwright.db`.
- **Leave out `logs`.** `data/logs` holds the sign-in lines, which Mealwright keeps for 14 days
  only; a copy would keep them for longer. For example (`<another disk>` is where the copy goes):

  ```bash
  sudo tar -C <folder> --exclude=data/logs -czf "<another disk>/mealwright-data-$(date +%Y%m%d-%H%M).tar.gz" data
  ```

  With `rsync`, add `--exclude=logs/`.
- Other copies in the same folder: `pre-upgrade-….db` (made before a version upgrades the
  database) and `before-delete-everything-….db` (made before Delete everything). They restore
  the same way.

## Restore on the same server

1. **Stop Mealwright**, so nothing writes to the database while you swap it:

   ```bash
   cd <folder>
   docker compose stop mealwright
   ```

2. **Pick the backup.** The newest is first. Pick a `backup-…` file (or a
   `before-delete-everything-…` one, to undo a Delete everything):

   ```bash
   sudo ls -lt data/backups/
   ```

3. **Keep the current database aside, then put the backup in its place.** The two files
   beside the database (`-wal` and `-shm`) belong to the current one and go aside with it.

   ```bash
   STAMP=$(date +%Y%m%d-%H%M)
   sudo mkdir -p "data/before-restore-$STAMP"
   sudo mv data/mealwright.db data/mealwright.db-wal data/mealwright.db-shm "data/before-restore-$STAMP/" 2>/dev/null
   sudo cp data/backups/backup-<date>-<time>.db data/mealwright.db
   sudo chown 10001:10001 data/mealwright.db
   sudo chmod 600 data/mealwright.db
   ```

   (`mv` says nothing when a `-wal` or `-shm` file isn't there; that is fine.)

4. **Start it, and check.**

   ```bash
   docker compose up -d
   docker compose logs -f
   ```

   Sign in with the password you had **when the backup was made**. Everything is as it was at
   that time; whatever changed after it is gone. API tokens deleted or stopped since the backup work
   again: delete them again (proposed, for cabledrawer). Once all is well, you can delete the
   `data/before-restore-…` folder.

## Restore on a new server (the disk died)

1. Install Mealwright as in `docs/dev/test-on-homelab.md` (section 4), with the **same
   version or a newer one**, but don't start it yet.
2. Copy your copy of the data folder into `<folder>/data`. Then put the newest
   `data/backups/backup-….db` in as `mealwright.db`, and delete any copied `mealwright.db-wal`
   and `mealwright.db-shm` (a copy of the database taken while Mealwright was running may be
   half-written; the backup file is not). If you have only a backup file, make `<folder>/data`
   with the backup in it as `mealwright.db`, and your copy of `photos` beside it.
3. Give it to Mealwright's user:

   ```bash
   sudo chown -R 10001:10001 <folder>/data
   sudo chmod 600 <folder>/data/mealwright.db
   ```
4. Start it (`docker compose up -d`) and sign in. A backup from an older version is upgraded
   when Mealwright starts. A backup from a **newer** version does not open in an older one.

## If it doesn't start

`docker compose logs` says why. Put the database you kept aside back
(`data/before-restore-…/mealwright.db`) and start again, then ask for help with the log lines.
