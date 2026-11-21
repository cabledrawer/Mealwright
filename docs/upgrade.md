# Upgrading Mealwright

Upgrading means: back up, change the version in your compose file, pull the new image, restart. Mealwright updates its own database when it starts. This page also says how to go back.

Below, `<folder>` is the folder holding `compose.yaml` and the `data` folder (the data folder is `/data` inside the container).

## Before you start

1. **Read the CHANGELOG** for the version you are moving to (`CHANGELOG.md` in the project). It says what changed and whether anything needs your attention.
2. **Back up first.** See [backups.md](backups.md). The short way: stop Mealwright and copy the whole data folder, photos included.

   ```bash
   cd <folder>
   docker compose stop mealwright
   sudo tar -C <folder> --exclude=data/logs -czf "<another disk>/mealwright-data-<current version>-$(date +%Y%m%d-%H%M).tar.gz" data
   ```

   `<another disk>` is where the copy goes. The file name carries your current version (`mealwright-data-<current version>-<date>.tar.gz`), so you know which version it belongs to.

   **Why stop it first:** while Mealwright runs, the database keeps recent changes in a second file beside it (`mealwright.db-wal`). A copy of a running data folder can miss them.

## Upgrade

1. Change the `image:` line in `compose.yaml` to the new version. Always use an exact version, never `latest`:

   ```yaml
   image: <registry>/<owner>/mealwright:<new version>
   ```

   `<registry>/<owner>` is where you get the image: GHCR (`ghcr.io/<owner>/mealwright`) or Docker Hub (`docker.io/<owner>/mealwright`). Both carry the same versions.

   **Testing a 0.x version?** The images are not published before 1.0.0. A test version is loaded from a file (`docker load`), its image is just `mealwright:<new version>`, and `docker compose pull` does nothing for it: follow `docs/dev/test-on-homelab.md`, section 4, instead of steps 1 and 2 here.

2. Pull the new image and start it:

   ```bash
   cd <folder>
   docker compose pull
   docker compose up -d
   docker compose logs -f
   ```

3. Check it. Open Settings › About: it shows the version. The address `/api/v1/version` on your Mealwright also answers with the version, for tools that watch for updates.

## What happens when it starts

- **Mealwright upgrades its own database.** On every start it applies any database changes the new version needs. You do nothing.
- **It makes a safety copy first.** Before it changes the database, it copies it to `data/backups/pre-upgrade-<revision>-<date>-<time>.db` (the date and time in UTC). Once the upgrade has worked, it keeps the newest three of these. A new install, or a start with nothing to upgrade, makes no copy.
- **If the copy can't be made** (a full disk, a folder it can't write), Mealwright doesn't upgrade and doesn't start. The log says why. Fix that, then start it again.
- **If the upgrade itself fails,** Mealwright doesn't start. The log says "Database upgrade failed. Your data from before is safe in …" and names the clean copy. The file `data/backups/upgrade-failed` also names it. While an upgrade keeps failing, no new copy is made and none is deleted, so the clean one stays safe.
- **The safety copy holds the photos too,** unless an admin switched "Include photos" off in Settings › Backups & your data (it is on by default). They are in a folder beside the copy, `data/backups/pre-upgrade-<revision>-<date>-<time>-photos`, made with hard links, so they take almost no extra room. The copy is not a replacement for a copy of the whole data folder on another disk, which is the only protection if the disk is lost.
- **Mealwright runs as one worker.** An upgrade doesn't change that. See [install.md](install.md).

## Going back

An older version can't read a database a newer version has changed, and Mealwright has no downgrade command. Going back means putting back the backup you took before upgrading, **together with the old image**. Anything you changed after upgrading is lost. One thing to know: if you go back to 0.9.0 and then upgrade again, a login number from before can be used again, because 0.9.0 doesn't remember the ones it used.

**After going back to 0.8, Undo of 0.9 people changes does nothing** (cabledrawer 13 Nov). If the 0.9 changes to people (added, deleted, a sign-in link made) are still in Recent changes because the data wasn't put back from a backup, 0.8 shows an Undo for them, says "Undone." and changes nothing. Going back to 0.8 also leaves any `-photos` folders in `data/backups`: 0.8 doesn't know them and never trims them, so delete them by hand when you no longer need them. Going back from a backup avoids the first problem: the changes are not there at all.

1. Stop it:

   ```bash
   cd <folder>
   docker compose stop mealwright
   ```

2. Keep the new data aside, then put the backup back (use the file you made before upgrading):

   ```bash
   sudo mv data "data-after-upgrade-$(date +%Y%m%d-%H%M)"
   sudo tar -C <folder> -xzf "<another disk>/mealwright-data-<date>.tar.gz"
   sudo chown -R 10001:10001 data
   ```

3. Set the `image:` line in `compose.yaml` back to the **old** version, then start it:

   ```bash
   docker compose pull
   docker compose up -d
   docker compose logs -f
   ```

**If you have no backup of the whole folder,** Mealwright's own copies hold the database, and the photos too when "Include photos" was on. Follow [restore.md](restore.md): it says how to put one of the `pre-upgrade-…` or `backup-…` files in place, and its photos folder with it. Without a photos folder, the photos stay where they are. Then set the old version in `compose.yaml` as above.

**If the upgrade failed and Mealwright won't start,** the data is still the old version's, with a clean copy beside it. Set the old version in `compose.yaml` and start it. If it still won't start, use the copy the log names, as in [restore.md](restore.md).
