# Trying a Mealwright 0.x build on your own server

Step-by-step instructions for running a Mealwright 0.x build on a home server. In this file, replace anything in `<angle brackets>` with your own value:

| Placeholder | Means |
|---|---|
| `<version>` | The exact version, for example `0.3.0` (never `latest`) |
| `<server>` | The address of the machine that runs Mealwright |
| `<user>` | Your login on that machine |
| `<folder>` | The folder on the server that holds Mealwright's `compose.yaml`, `data` and `backups` |
| `<proxy folder>` | The folder of your reverse proxy's own compose project |
| `<subnet>` | A free private range for Mealwright's own Docker network |

There is no CI runner during 0.x (cabledrawer 17 Oct). Images are built on your own computer, copied to the server as a file, and loaded there. **Images are never pushed to any registry: not a public one, not a private one (cabledrawer 18 Oct).** A registry is not used in 0.x. **Claude Code never builds, copies or pushes images for you.**

Each command goes in a terminal on the machine named in that section.

---

## 1. Build the image (on your computer, in WSL)

Use a released tag, so you always know exactly what you are running.

```bash
cd <your copy of the Mealwright repository>
git fetch --tags
git archive v<version> | docker build -t mealwright:<version> \
  --build-arg VERSION=<version> \
  --build-arg CREATED="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --build-arg REVISION="$(git rev-parse v<version>^{commit})" -
```

The three build arguments only fill in the image's labels (version, build time, commit); leave them out and the labels say "unknown". The build stops if `backend/uv.lock` doesn't match `backend/pyproject.toml`.

`git archive` builds from exactly what is in the tag, nothing else from your working folder. The build ends with a line like `naming to docker.io/library/mealwright:<version> done`.

## 2. Save it to a file

```bash
docker save mealwright:<version> | gzip > mealwright-<version>.tar.gz
ls -lh mealwright-<version>.tar.gz     # should be tens of megabytes, not tiny
```

## 3. Copy it to the server

```bash
scp mealwright-<version>.tar.gz <user>@<server>:<folder>/
```

---

## 4. On the server

Every start-up applies database changes (migrations) for the new version. An older version can't read a database a newer version has changed. **So back up the data folder before every update. Going back needs that backup.**

### 4.1 Stop Mealwright and back up the data

Stopping it first makes sure the database is copied in a consistent state. The backup leaves out the logs, because they hold sign-in lines and are not needed to restore Mealwright.

```bash
cd <folder>
OLD=$(grep -oE 'image: *mealwright:[^ ]+' compose.yaml | cut -d: -f3)
echo "Current version: $OLD"
docker compose stop mealwright
sudo tar -C <folder> --exclude=data/logs -czf "backups/data-$OLD-$(date +%Y%m%d-%H%M).tar.gz" data
sudo chmod 600 backups/data-*.tar.gz
ls -lh backups/       # the new backup should be there, and not tiny
```

(Skip the stop and the backup only on the very first install, when there is no data yet.) Keep at least the last three backups.

**Stop the container before copying the data folder by hand** (cabledrawer 28 Oct). While Mealwright runs, the database keeps recent changes in a second file beside it (`mealwright.db-wal`), so a copy of a running data folder can miss them or not open at all.

**Mealwright's own safety copy (from 0.7.0, cabledrawer 28 Oct).** Before it upgrades the database on start-up, Mealwright copies it to `data/backups/pre-upgrade-<revision>-<date>.db` (the date and time in UTC). Once the upgrade has worked, it keeps the last three. While an upgrade keeps failing, it makes no new copy and deletes none: the file `data/backups/upgrade-failed` names the copy from before the first try, and that copy is kept even after the upgrade works (cabledrawer 31 Oct). The log then says, for example: "Database upgrade failed. Your data from before is safe in /data/backups/pre-upgrade-….db. Mealwright didn't start." and points to section 5. A new install, or a start-up with nothing to upgrade, makes no copy. If the copy can't be made (a full disk, a folder it can't write), Mealwright doesn't upgrade or start, and the log says why. From 0.9.5 the copy also gets a photos folder beside it (`pre-upgrade-<revision>-<date>-photos`, hard links to the live photo files, so it takes almost no extra room), unless an admin switched "Include photos" off in Settings → Your data; the choice is read before the upgrade, from the database as it was. If the photos can't be added (a full disk), Mealwright doesn't upgrade or start and says so. This copy is a second line of defence, on the same disk: keep making the backup above.

### 4.2 Load the image

```bash
cd <folder>
docker load < mealwright-<version>.tar.gz
```

It says `Loaded image: mealwright:<version>`.

### 4.3 Compose file

First time only: create `<folder>/compose.yaml`. Mealwright runs inside the container as its own user, number 10001, so give that user the data folder:

```bash
mkdir -p <folder>/data <folder>/backups
sudo chown 10001:10001 <folder>/data
```

```yaml
services:
  mealwright:
    # Exact version, never "latest". Change it by hand to update.
    image: mealwright:<version>
    # The image was loaded from a file. Never try to pull it from anywhere.
    pull_policy: never
    container_name: mealwright
    restart: unless-stopped
    environment:
      # Believe the visitor address your reverse proxy passes on, but only from
      # Mealwright's own network. The sign-in slow-down needs it to see who is guessing.
      MEALWRIGHT_TRUSTED_PROXIES: "<subnet>"
    volumes:
      - ./data:/data
    # Mealwright keeps its own log in data/logs and deletes it after 14 days. Docker's
    # copy holds start-up messages, warnings and errors only, capped at 2 files of 1 MB.
    logging:
      driver: json-file
      options:
        max-size: "1m"
        max-file: "2"
    labels:
      # Never let an auto-updater touch this container.
      - com.centurylinklabs.watchtower.enable=false

networks:
  default:
    ipam:
      config:
        - subnet: <subnet>   # a fixed private range, named in MEALWRIGHT_TRUSTED_PROXIES
```

To update: edit the `image:` line to the new exact version (keep `pull_policy: never`).

The example above leaves out the hardening lines (`security_opt`, `cap_drop`, `read_only` with a `tmpfs`, `init`, `mem_limit`). Add them from `compose.example.yaml` once the first start works; `docs/hardening.md` says what each does.

Notes:

- **Mealwright has its own Docker network** (named after the folder, `…_default`). It can't reach your other apps, and they can't reach it. Only your reverse proxy joins it (4.5). Don't add a `networks:` list to the service.
- **No `ports:`.** It is only reachable through the reverse proxy.
- **HTTPS is required.** Signing in, installing the app on your phone, offline shopping and keep-screen-awake all need HTTPS, which the reverse proxy provides. On a plain `http://` address Mealwright says so instead of signing you in. (For a quick test on your own network only, `MEALWRIGHT_ALLOW_PLAIN_HTTP: "true"` allows plain HTTP; Mealwright then logs a warning.)
- **No time zone setting needed.** Mealwright takes the household's time zone from the admin's browser the first time the admin opens it, and keeps it. Until that first visit, dates follow UTC.
- **Health check:** the image checks itself every 30 seconds. `docker ps` shows `(healthy)` once it is ready.
- **Data** lives in `<folder>/data`. That folder is everything Mealwright knows, so make sure your backup tool includes it, but leave out `data/logs`.
- If something watches for new images, that is fine as long as it only tells you. Never let it update or auto-merge Mealwright.

### 4.4 Logs

- **Where:** Mealwright writes its own log to `<folder>/data/logs/mealwright.log`. Each night just after midnight (UTC) it starts a new file and deletes files last written more than 14 days ago (spec section 7). Every line has a time (UTC).
- **What:** errors and sign-ins only. Sign-in lines (anything with a username or an address) go only to this file, never to `docker logs`.
- **Reading it:** only Mealwright's own user can read the file, so use `sudo`:

  ```bash
  sudo less <folder>/data/logs/mealwright.log
  ```

  (In `less`: `G` jumps to the end, `q` quits.)
- **Backups:** leave `data/logs` out of any backup, as the commands above do. With `rsync`, add `--exclude=logs/` when copying the `data` folder.

### 4.5 Reverse proxy

Mealwright needs a site in your reverse proxy that passes to `mealwright:8080`, with Mealwright's own login and any `Remote-*` headers removed (Mealwright doesn't read those headers; removing them means no visitor can pretend to be signed in through them).

The proxy has to join Mealwright's Docker network. In the **proxy's** compose file, add the network to the proxy service's `networks:` list and as an external network at the bottom, next to the ones it already joins:

```yaml
services:
  <proxy service>:
    networks:
      - default
      - mealwright_default

networks:
  mealwright_default:
    external: true
```

(`docker network ls` shows the network's real name once Mealwright has started; it is named after `<folder>`.)

Order matters: **start Mealwright first** (4.6), so its network exists, **then recreate the proxy** in `<proxy folder>`:

```bash
cd <proxy folder>
docker compose up -d
```

This briefly takes everything behind the proxy offline (a few seconds). Do it at a quiet moment. If your proxy's configuration file is a single-file bind mount, an editor that saves by replacing the file leaves the container looking at the old one; restart the proxy container after editing.

### 4.6 Start it

```bash
cd <folder>
docker compose up -d
docker compose logs -f        # watch it start; press Ctrl+C to stop watching
docker ps                     # mealwright should say (healthy) within about 30 seconds
```

Then check the version at `https://<your Mealwright address>/api/v1/version`: it must show `<version>`.

**First install: create the admin account straight away.** Until the admin account exists, the first person to open the address becomes the admin (spec section 7). Open the address, create your account, then check that setup is closed:

```bash
curl -s https://<your Mealwright address>/api/v1/setup
```

It must say `"needs_setup":false`.

---

## 5. Going back to the previous version

Use this if the new version doesn't start or doesn't work. **Anything you changed in Mealwright after updating is lost**, because you go back to the backup taken just before the update. The old image with the new data won't start, or may damage the data, so always go back with both together.

**After going back to 0.8, Undo of 0.9 people changes does nothing** (cabledrawer 13 Nov). Going back from the backup above leaves no 0.9 changes to undo. Only if the 0.9 changes to people (added, removed, a sign-in link made) are still in Recent changes, because the data was not put back from a backup, does 0.8 show an Undo for them, say "Undone." and change nothing.

```bash
cd <folder>
docker compose stop mealwright

# Keep the newer data aside rather than deleting it, in case it is needed.
sudo mv data "data-broken-$(date +%Y%m%d-%H%M)"

# Restore the backup from just before the update (pick the right file).
ls -lh backups/
sudo tar -C <folder> -xzf backups/data-<old version>-<date>.tar.gz
```

Then put the old tag back: edit `compose.yaml` and set the `image:` line to the **old** version, the one in the backup's file name. The old image is still on the server from when you loaded it (`docker images mealwright` lists them); if you removed it, load its `.tar.gz` again (4.2). Start it:

```bash
docker compose up -d
docker compose logs -f
```

**If you have no backup from just before the update** (proposed, for cabledrawer): Mealwright's own safety copy holds the database, and the photos too unless "Include photos" was off (a `-photos` folder with the same name beside it). Instead of the `mv` and `tar` lines above, put the copy the log names in place of the database, and remove the two files beside it that belong to the failed upgrade:

```bash
cd <folder>
sudo cp data/mealwright.db "backups/mealwright-broken-$(date +%Y%m%d-%H%M).db"   # keep the failed one aside
sudo cp data/backups/pre-upgrade-<revision>-<date>.db data/mealwright.db
sudo rm -f data/mealwright.db-wal data/mealwright.db-shm
sudo mkdir -p data/photos   # photos: skip the next line if there is no -photos folder beside the copy
sudo cp -an data/backups/pre-upgrade-<revision>-<date>-photos/. data/photos/
sudo rm -f data/backups/upgrade-failed   # the copy you just restored is no longer "the copy from before the first try"
```

Check `/api/v1/version` shows the old version. Tell Claude Code what went wrong with the new one, and include the end of `docker compose logs` from the failed start if you still have it. Once it is sorted, you can delete the `data-broken-…` folder.
