# How to restore Mealwright from a backup

Mealwright backs its database up by itself, daily at 03:00 by default, into the `backups`
folder inside its data folder (Settings › Backups & your data). This page says how to put one of those
backups back. `backend/scripts/restore_test.sh` follows these steps on a fresh container and
checks that signing in shows the data.

Below, `<folder>` is the folder holding `compose.yaml` and the `data` folder (the data folder
is `/data` inside the container).

## What a backup holds

- **The database**: every recipe, plan, list, pantry item, person, login and setting. One file,
  `data/backups/backup-<date>-<time>.db` (the date and time in UTC).
- **The single sign-on client secret opens only with `data/secret.key`.** A backup keeps the secret sealed; on a new server without that key file, Mealwright can't open it, password sign-in works again, and an admin types the secret again in Settings › Sign-in for everyone. An admin who has only ever signed in with single sign-on has no password: run the `reset-admin` command for them first. An export leaves the secret out altogether, and API tokens too: make new ones.
- **The photos, when "Include photos" was on** (it is on unless an admin switched it off in
  Settings › Backups & your data): a folder beside the database file with the same name and `-photos` in
  place of `.db`, for example `data/backups/backup-<date>-<time>-photos`. It holds the recipe
  photos as they were when the backup was made, in the same `photos/<number>/` layout as
  `data/photos`. A backup made before 0.9.5, one made with "Include photos" off, or one made when
  there were no photos has **no** photos folder. Restoring such a backup **keeps the photos
  already on the server**; a recipe whose photo file is missing just shows no photo (a plain
  coloured square in the list, nothing on the recipe's page), and nothing else is affected. If the
  disk itself is lost, those photos come back only from a copy of the whole data folder, so copy the
  data folder (or at least `backups` and `photos`) to another disk or your NAS as well. Backups on
  the same disk as Mealwright go when the disk goes.
- **The photo folders are mostly links, not copies.** Mealwright makes them
  with hard links, so a photo that hasn't changed takes no extra room however many backups hold it.
  A copy of the `backups` folder to another disk is a full copy of the photos in it: use `tar` or
  `restic`, or `rsync -aH`, which keep the links together on the way (plain `rsync -a` copies each
  one in full, once per backup).
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
  the same way, with their own `-photos` folders (the safety copy before an upgrade follows the "Include photos" choice; the one before Delete everything always has them).
  A `before-delete-everything-…` copy always has its photos folder, whatever "Include photos"
  says, because Delete everything removes the photos for good: it is the
  way to bring them back.

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

4. **Put the photos back, if the backup has a photos folder** (the same name as the `.db` file
   you picked, with `-photos` in place of `.db`). `cp -an` adds the ones that are missing
   and skips the ones already there (the live files and the backup's are often the same file,
   which plain `cp -a` refuses with an error): a photo is never changed once saved, so a file with
   the same name is the same photo, the restored database finds every photo it points to, and
   newer photos stay (harmless). Newer `cp` versions print a harmless warning about `-n`; the
   command still succeeds. Skip this step when there is no such folder:

   ```bash
   sudo mkdir -p data/photos
   sudo cp -an data/backups/backup-<date>-<time>-photos/. data/photos/
   sudo chown -R 10001:10001 data/photos
   ```

5. **Start it, and check.**

   ```bash
   docker compose up -d
   docker compose logs -f
   ```

   Sign in with the password you had **when the backup was made**. Everything is as it was at
   that time; whatever changed after it is gone. A database put back from a copy (a backup, the
   copy before an upgrade or before Delete everything) signs every device out, stops every API
   token and cancels every sign-in or reset link the first time it starts, so a cookie, token or
   link stopped after the copy was made doesn't work again: everyone signs in again, and you
   make new API tokens. Once all is well, you can delete the
   `data/before-restore-…` folder.

   **After a restore**, everything else is as it was in the copy, logins and passwords
   included. Do again what you did after the copy was made: delete people you deleted, unlink
   or refuse single sign-on accounts you unlinked or refused, change any password that leaked,
   and check the switches in Settings › Outside connections.

   Only copies Mealwright made carry the mark that ends the sign-ins. A copy of the data folder
   made another way (a `tar` of `data`, a snapshot of the server) doesn't: after restoring
   one, use Sign out everywhere else and delete the API tokens yourself. A safety copy put back
   under an older version keeps its mark, so the sign-ins end at the next upgrade instead.

## Restore on a new server (the disk died)

1. Install Mealwright as in [install.md](install.md), with the **same
   version or a newer one**, but don't start it yet.
2. Copy your copy of the data folder into `<folder>/data`. Then put the newest
   `data/backups/backup-….db` in as `mealwright.db`, and delete any copied `mealwright.db-wal`
   and `mealwright.db-shm` (a copy of the database taken while Mealwright was running may be
   half-written; the backup file is not). If the backup has a photos folder
   (`backup-<date>-<time>-photos`), copy its contents into `<folder>/data/photos` too (a plain
   copy of the folders; if your copy of `data/photos` is newer, it is already more complete, so
   add only what is missing). If you have only a backup file, make `<folder>/data` with the
   backup in it as `mealwright.db`, and the photos folder from the backup (or your own copy of
   `photos`) as `<folder>/data/photos`.
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
