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

```bash
sudo mkdir -p /opt/mealwright/data /opt/mealwright/backups
cd /opt/mealwright
```

Mealwright runs inside the container as its own user, number 10001, so give that user the data folder:

```bash
sudo chown 10001:10001 /opt/mealwright/data
```

(To double-check the number: `docker run --rm --entrypoint id git.example.org/tess/mealwright:<TAG>` prints `uid=10001(mealwright) …`.)

### 4.3 Compose file

Create `/opt/mealwright/compose.yaml`:

```yaml
services:
  mealwright:
    # Exact version, never "latest". Change it by hand to update (section 5).
    image: git.example.org/tess/mealwright:<TAG>
    container_name: mealwright
    restart: unless-stopped
    environment:
      # Only Caddy can reach Mealwright on its network, so believe the visitor address
      # Caddy passes on. The sign-in slow-down needs it to see who is guessing.
      MEALWRIGHT_TRUSTED_PROXIES: "*"
    volumes:
      - ./data:/data
    networks:
      - mealwright
    labels:
      # Never let Watchtower (or similar) update this container.
      - com.centurylinklabs.watchtower.enable=false

networks:
  mealwright:
    name: mealwright
```

Notes:

- **Mealwright has its own network**, `mealwright`, so it can't reach your other apps and they can't reach it. Only Caddy joins it (next step).
- **No `ports:`.** It's only reachable through Caddy.
- **HTTPS is required.** Mealwright's sign-in cookie only travels over HTTPS, which Caddy provides. Opening it on a plain `http://` address won't keep you signed in.
- **Health check:** the image checks itself every 30 seconds. `docker ps` shows `(healthy)` once it's ready.
- **Data** lives in `/opt/mealwright/data`. That folder is everything Mealwright knows, so make sure your backup tool includes `/opt/mealwright`.
- If Diun watches this container, that's fine, because Diun only tells you about new images. Renovate, if you use it, must never auto-merge a Mealwright change.

### 4.4 Caddy and Authelia

Do this the same way as your other apps.

1. Let Caddy reach Mealwright. In Caddy's compose file, add the network:

   ```yaml
   services:
     caddy:
       networks:
         # …the networks it already has…
         - mealwright
   networks:
     mealwright:
       external: true
   ```

2. Add a site to the Caddyfile. Copy the Authelia part from one of your existing apps, so it matches exactly. The shape is:

   ```
   mealwright.example.org {
       # the same Authelia forward_auth lines (or import) as your other apps
       reverse_proxy mealwright:8080
   }
   ```

3. Add `mealwright.example.org` to your local DNS the same way as your other apps.
4. In Authelia's `access_control`, give `mealwright.example.org` the same policy as your other apps (for example `two_factor`).

Mealwright also has its own login. For now you'll sign in twice: Authelia, then Mealwright. That's expected.

### 4.5 Start it

The `mealwright` network has to exist before Caddy can join it, so start Mealwright first:

```bash
cd /opt/mealwright
docker compose up -d
docker compose logs -f        # watch it start; press Ctrl+C to stop watching
```

Then restart Caddy, so it joins the network and loads the new site.

**Check it's running.** `docker ps` should show `mealwright` as `(healthy)` within about 30 seconds. Then open `https://mealwright.example.org/api/v1/version` in your browser. After the Authelia login, it shows the version, for example `{"version":"0.1.0"}`. Then open `https://mealwright.example.org/`, create the admin account, and sign in.

---

## 5. Update to a new version

Every start-up applies database changes (migrations) for the new version. The old version can't read a database that a newer version has changed. **So back up the data folder before every update. Going back needs that backup.**

1. Build and push the new image in WSL (sections 2 and 3). Note the new tag.
2. On the home server, **stop Mealwright and back up the data**. Stopping it first makes sure the database is copied in a consistent state.

   ```bash
   cd /opt/mealwright
   OLD=$(grep -oE 'tess/mealwright:[^ ]+' compose.yaml | cut -d: -f2)
   echo "Current version: $OLD"
   docker compose stop mealwright
   sudo tar -C /opt/mealwright -czf "backups/data-$OLD-$(date +%Y%m%d-%H%M).tar.gz" data
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

Keep at least the last three backups. Delete older ones from `/opt/mealwright/backups` when you're happy.

---

## 6. Roll back to the previous version

Use this if the new version doesn't start or doesn't work. **Anything you changed in Mealwright after updating will be lost**, because you go back to the backup taken just before the update.

```bash
cd /opt/mealwright
docker compose stop mealwright

# Keep the newer data aside rather than deleting it, in case it's needed.
sudo mv data "data-broken-$(date +%Y%m%d-%H%M)"

# Restore the backup from just before the update (pick the right file).
ls -lh backups/
sudo tar -C /opt/mealwright -xzf backups/data-<OLD>-<date>.tar.gz
```

Then edit `compose.yaml` and set the `image:` tag back to the **old** version, the one in the backup's file name. Start it:

```bash
docker compose up -d
docker compose logs -f
```

Check `/api/v1/version` shows the old version. Tell Claude Code what went wrong with the new one, and include the end of `docker compose logs` from the failed start if you still have it. Once it's sorted, you can delete the `data-broken-…` folder.

**Always roll back the image and the data together.** The old image with the new data won't start, or may damage the data.
