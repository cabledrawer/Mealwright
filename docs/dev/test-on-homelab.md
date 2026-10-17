# Testing Mealwright on the homelab

Written 17 Oct 2026 for cabledrawer. Step-by-step instructions for trying a Mealwright 0.x build on the home server:

1. One-time setup: tokens and the Authelia rule for the registry
2. Build the image in WSL
3. Push it to Forgejo's registry (only you do this)
4. Run it on the home server
5. Update to a new version
6. Roll back to the previous version

There's no CI runner during 0.x (cabledrawer 17 Oct), so images are built on your WSL machine and pushed by you. **Claude Code never pushes images.**

Throughout, replace anything in `<angle brackets>` with your own value. Each command goes in a terminal on the machine named in that section.

**Already done on the home server (cabledrawer 17 Oct):** the Caddy site (tier D), DNS and the certificate, and the folder `~/mealwright/data`. Those steps are marked **Done** below.

---

## 1. One-time setup

### 1.1 Two Forgejo tokens

In Forgejo, open your avatar menu → **Settings → Applications → Generate new token**. Create two:

| Token name | Scope | Used where |
|---|---|---|
| `mealwright-push` | **package: Read and write** (nothing else) | in WSL, for a minute at a time, when you push |
| `mealwright-pull` | **package: Read** (nothing else) | on the home server, when you pull |

Forgejo shows each token only once. Save both in your password manager.

### 1.2 Who can pull the images without a login

Forgejo's packages follow your account's visibility (**Settings → Profile → Visibility**):

- **Public:** anyone who can reach the registry can pull Mealwright images without logging in.
- **Limited** or **Private:** a login is needed to pull.

**Your profile stays Public, and that's acceptable for this setup (cabledrawer 17 Oct).** The `/v2/` rule in step 1.3 only lets in devices on your LAN, and only your household uses the LAN. The images become public at 1.0 anyway. If either of those changes, for example guests on the LAN, switch to **Limited**.

### 1.3 Let the registry through Authelia, from the LAN only

Docker can't log in through Authelia's login page. So the registry's address, `/v2/`, has to skip Authelia, **but only for devices on your LAN**. Forgejo still asks for a token on every request.

On the home server, add this to Authelia's `configuration.yml` under `access_control: rules:`. Put it **above** any other rule for `git.example.org`, because Authelia uses the first rule that matches:

```yaml
    - domain: git.example.org
      resources:
        - '^/v2/'
      networks:
        - 192.168.1.0/24      # your LAN only
      policy: bypass
```

Restart Authelia, using the same command you normally use for it, for example `docker compose restart authelia` in its folder.

**Check it worked.** From WSL:

```bash
curl -i https://git.example.org/v2/
```

- Good: the first line says `401`, and there's a line starting `www-authenticate: Bearer realm="https://git.example.org/v2/token"`. That's Forgejo asking for a token.
- Not working yet: `302` with a `location:` pointing at `auth.example.org`. Authelia is still in the way.

**Check it stays closed from outside.** On your phone, switch Wi-Fi off and open `https://git.example.org/v2/` in the browser. It must show the Authelia login page. If it doesn't, Caddy is probably passing Docker's internal address instead of the phone's real one. Stop and ask Claude Code before going further.

---

## 2. Build the image in WSL

In a WSL terminal:

```bash
cd ~/mealwright
git switch main
git pull
./check
```

The last line of `./check` must say **RESULT: PASS**. If it says FAIL, don't build. Tell Claude Code which steps failed.

Choose the image tag. Always use an exact version, never `latest`:

- **For a release** (after you've tagged it, e.g. `v0.1.0`): the tag is just the version.

  ```bash
  git switch --detach v0.1.0
  TAG=0.1.0
  ```

- **For a test build between releases:** the version plus the commit, so you always know exactly what's running.

  ```bash
  TAG="$(grep -m1 '^version' backend/pyproject.toml | cut -d'"' -f2)-$(git rev-parse --short HEAD)"
  echo "$TAG"     # e.g. 0.1.0.dev0-57c7393
  ```

Build it:

```bash
docker build -t "git.example.org/tess/mealwright:$TAG" .
```

It ends with a line like `naming to git.example.org/tess/mealwright:0.1.0 done`. If you switched to a release tag, go back afterwards with `git switch main`.

---

## 3. Push it to Forgejo (only you)

Do this when Claude Code isn't in the middle of a task. While you're logged in, your push token sits in Docker's settings on this machine, so log out straight after pushing.

### 3.1 Log in

```bash
docker login git.example.org -u tess
```

When it asks for a password, paste the **`mealwright-push`** token. Don't put the token on the command line itself, or it ends up in your shell history. It should say `Login Succeeded`.

### 3.2 Push

```bash
docker push "git.example.org/tess/mealwright:$TAG"
```

### 3.3 Log out straight away

```bash
docker logout git.example.org
grep -c example ~/.docker/config.json
```

`docker logout` should say `Removing login credentials`. The `grep` must print `0`, which means the token is gone from this machine. If the file doesn't exist, that's fine too.

### 3.4 Check it arrived

The image now shows in Forgejo under your profile → **Packages**.

Because your profile is Public (step 1.2), pulling it from the LAN works even while logged out. That's expected. From outside the LAN, the Authelia rule still blocks it.

---

## 4. Run it on the home server

### 4.1 Pull the image

On the home server:

```bash
docker login git.example.org -u tess        # paste the mealwright-pull token
docker pull git.example.org/tess/mealwright:<TAG>
docker logout git.example.org
```

### 4.2 Folders

**Done (cabledrawer 17 Oct):** Mealwright lives in `~/mealwright`, with its data in `~/mealwright/data`.

Mealwright runs inside the container as its own user, **number 10001**, so give that user the data folder, and make a folder for backups:

```bash
cd ~/mealwright
sudo chown 10001:10001 data
mkdir -p backups
```

(To double-check the number: `docker run --rm --entrypoint id git.example.org/tess/mealwright:<TAG>` prints `uid=10001(mealwright) …`.)

### 4.3 Compose file

Create `~/mealwright/compose.yaml`:

```yaml
services:
  mealwright:
    # Exact version, never "latest". Change it by hand to update (section 5).
    image: git.example.org/tess/mealwright:<TAG>
    container_name: mealwright
    restart: unless-stopped
    environment:
      # Believe the visitor address Caddy passes on, but only from Mealwright's own
      # network (Caddy joins it below). The sign-in slow-down needs it to see who is
      # guessing; a made-up address from a visitor is ignored.
      MEALWRIGHT_TRUSTED_PROXIES: "172.28.10.0/24"
    volumes:
      - ./data:/data
    # Mealwright keeps its own log in data/logs and deletes it after 14 days. Docker
    # keeps a copy of the same lines, which can only be limited by size, not by age:
    # here 2 files of 1 MB (thousands of lines). On a quiet server that copy can hold
    # lines older than 14 days until it fills; "docker compose up -d" after an update
    # starts it afresh.
    logging:
      driver: json-file
      options:
        max-size: "1m"
        max-file: "2"
    labels:
      # Never let Watchtower (or similar) update this container.
      - com.centurylinklabs.watchtower.enable=false
    # No "networks:" here: Mealwright uses only this project's own network, which
    # Docker names mealwright_default (after the folder), like Paperless's.

networks:
  default:
    ipam:
      config:
        - subnet: 172.28.10.0/24   # a fixed range, named in MEALWRIGHT_TRUSTED_PROXIES
```

**Logs (from 0.1.1):** Mealwright writes its own log to `data/logs/mealwright.log`, with a time on every line. Each night it starts a new file and deletes files older than 14 days (spec section 7). It holds errors and sign-ins only, and only Mealwright's own user can read it (use `sudo` to look). Docker keeps a copy of the same lines; the `logging:` lines above limit that copy to 2 MB, but Docker can only limit by size, so on a quiet server it may hold lines older than 14 days. If you already run 0.1.0, add those lines to your `compose.yaml` and run `docker compose up -d` again. To read the log: `docker logs mealwright`, or open the file in the data folder.

If `docker compose up` says the range is already in use, choose another free one, such as `172.30.43.0/24`, and change it in both places.

Notes:

- **Mealwright has its own network**, `mealwright_default`, the same pattern as Paperless. It can't reach your other apps, and they can't reach it. Only Caddy joins it (next step).
- **Mealwright must not join `apps_default`** or any other project's network. Don't add a `networks:` list to the service.
- **No `ports:`.** It's only reachable through Caddy.
- **HTTPS is required.** Signing in, installing the app on your phone, offline shopping and keep-screen-awake all need HTTPS, which Caddy provides. On a plain `http://` address, Mealwright says so instead of signing you in. (For a quick test on your own network only, `MEALWRIGHT_ALLOW_PLAIN_HTTP: "true"` allows plain HTTP; Mealwright then logs a warning.)
- **Health check:** the image checks itself every 30 seconds. `docker ps` shows `(healthy)` once it's ready.
- **Data** lives in `~/mealwright/data`. That folder is everything Mealwright knows, so make sure your backup tool includes it.
- If Diun watches this container, that's fine, because Diun only tells you about new images. Renovate, if you use it, must never auto-merge a Mealwright change.

### 4.4 Caddy, DNS and the certificate

**Done (cabledrawer 17 Oct):**

- The Caddy site `mealwright.example.org` → `mealwright:8080`, **tier D**: Mealwright's own login, no Authelia in front, and Caddy strips any `Remote-*` headers. Mealwright doesn't read those headers anyway; stripping them means no visitor can pretend to be signed in through them.
- The wildcard DNS name and certificate already cover `mealwright.example.org`.

**To do: Caddy joins Mealwright's network.** Caddy is its own compose project and joins other projects' networks as external ones (today `proxy_default`, `apps_default` and `docs_default`). Mealwright's network gets added the same way. In **Caddy's** compose file, add two things, next to the matching `docs_default` lines:

1. In the Caddy service's `networks:` list, add one line:

   ```yaml
         - mealwright_default
   ```

2. In the top-level `networks:` section at the bottom of the file, add:

   ```yaml
     mealwright_default:
       external: true
   ```

When you're done, the relevant parts look like this (your file has more in it; leave the rest as it is):

```yaml
services:
  caddy:
    # …
    networks:
      - default
      - apps_default
      - docs_default
      - mealwright_default

networks:
  apps_default:
    external: true
  docs_default:
    external: true
  mealwright_default:
    external: true
```

Don't bring Caddy up yet. Its compose file now refers to `mealwright_default`, which only exists once Mealwright has been started (section 4.5).

**Editing the Caddyfile:** your Caddyfile is a **single-file bind mount**. Tools that save by replacing the file, like `sed -i` and many editors, leave the container still looking at the old file, so `caddy reload` won't see the change. After editing it that way, restart Caddy:

```bash
docker restart caddy
```

(Docker attaches a single-file mount to the file itself, and a replaced file is a new file. A restart attaches the new one.)

### 4.5 Start it, and create the admin straight away

Order matters: **Mealwright first**, so its network exists, **then recreate Caddy**, so it joins that network.

1. Start Mealwright. This also creates the network `mealwright_default`:

   ```bash
   cd ~/mealwright
   docker compose up -d
   docker compose logs -f        # watch it start; press Ctrl+C to stop watching
   ```

2. Recreate Caddy in its own folder, so it picks up the new network:

   ```bash
   cd <Caddy's folder>
   docker compose up -d
   ```

   **This briefly takes all your sites offline** (a few seconds), because Caddy is recreated, not just reloaded. Do it at a quiet moment.

3. Check that both are on the network:

   ```bash
   docker network inspect mealwright_default --format '{{range .Containers}}{{.Name}} {{end}}'
   ```

   It should list both `mealwright` and `caddy`. Mealwright shouldn't appear on any other network:

   ```bash
   docker inspect mealwright --format '{{range $name, $_ := .NetworkSettings.Networks}}{{$name}} {{end}}'
   ```

   This should print only `mealwright_default`.

**Create the admin account straight away.** With tier D there's no Authelia in front, so until the admin account exists, the first person to open the address becomes the admin. That's how first-run setup works (spec section 7). Open `https://mealwright.example.org/`, create your account and sign in. Then check that setup is closed:

```bash
curl -s https://mealwright.example.org/api/v1/setup
```

It must say `"needs_setup":false`.

**Check it's running.** `docker ps` should show `mealwright` as `(healthy)` within about 30 seconds, and `https://mealwright.example.org/api/v1/version` shows the version, for example `{"version":"0.1.0"}`.

---

## 5. Update to a new version

Every start-up applies database changes (migrations) for the new version. The old version can't read a database that a newer version has changed. **So back up the data folder before every update. Going back needs that backup.**

1. Build and push the new image in WSL (sections 2 and 3). Note the new tag.
2. On the home server, **stop Mealwright and back up the data**. Stopping it first makes sure the database is copied in a consistent state.

   ```bash
   cd ~/mealwright
   OLD=$(grep -oE 'tess/mealwright:[^ ]+' compose.yaml | cut -d: -f2)
   echo "Current version: $OLD"
   docker compose stop mealwright
   sudo tar -C ~/mealwright -czf "backups/data-$OLD-$(date +%Y%m%d-%H%M).tar.gz" data
   ls -lh backups/       # the new backup should be there, and not tiny
   ```

3. Pull the new image (as in step 4.1, with the new tag).
4. Edit `compose.yaml`: change the tag in the `image:` line to the new one.
5. Start it, and watch the log for errors:

   ```bash
   docker compose up -d
   docker compose logs -f
   ```

6. Check `https://mealwright.example.org/api/v1/version` shows the new version.

Keep at least the last three backups. Delete older ones from `~/mealwright/backups` when you're happy.

---

## 6. Roll back to the previous version

Use this if the new version doesn't start or doesn't work. **Anything you changed in Mealwright after updating will be lost**, because you go back to the backup taken just before the update.

```bash
cd ~/mealwright
docker compose stop mealwright

# Keep the newer data aside rather than deleting it, in case it's needed.
sudo mv data "data-broken-$(date +%Y%m%d-%H%M)"

# Restore the backup from just before the update (pick the right file).
ls -lh backups/
sudo tar -C ~/mealwright -xzf backups/data-<OLD>-<date>.tar.gz
```

Then edit `compose.yaml` and set the `image:` tag back to the **old** version, the one in the backup's file name. Start it:

```bash
docker compose up -d
docker compose logs -f
```

Check `/api/v1/version` shows the old version. Tell Claude Code what went wrong with the new one, and include the end of `docker compose logs` from the failed start if you still have it. Once it's sorted, you can delete the `data-broken-…` folder.

**Always roll back the image and the data together.** The old image with the new data won't start, or may damage the data.
