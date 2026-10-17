# Setting up the Forgejo runner on the home server

Written 17 Oct 2026 for milestone 0.1. cabledrawer does this setup; Claude Code doesn't touch the server.

CI for Mealwright runs on Forgejo Actions, using a `forgejo-runner` container on the home server. This guide covers:

1. the layout and why it looks like this
2. running the runner and a Docker-in-Docker sidecar with compose
3. registering the runner with Forgejo
4. reaching Forgejo on the Docker network instead of through Caddy and Authelia
5. pushing images to the private registry, and pulling them on the home server
6. switching on the status-check rule for `main` once CI is green

Version numbers and config keys change between runner releases. Wherever this guide says "check", compare it with the release notes or with what `forgejo-runner generate-config` prints for your version.

## 1. The layout

```text
              ci network (Docker bridge, not published)
  ┌──────────────────────────────────────────────────────────────┐
  │  forgejo (alias)    forgejo-runner    docker-in-docker       │
  │  :3000 http          polls Forgejo     dockerd on :2375       │
  │                      starts jobs ───▶  job containers run here│
  └──────────────────────────────────────────────────────────────┘
        │
        └── also on your existing proxy network ── Caddy ── Authelia ── git.example.org
```

The design choices:

- **Jobs never touch the host's Docker socket.** Pull requests from branches run whatever workflow code is on that branch, including branches pushed by the `claude` account. If a job could reach `/var/run/docker.sock`, it could control every container on the home server, including Forgejo and Authelia. So the runner and its jobs use a separate Docker daemon in a Docker-in-Docker (`dind`) container instead.
- **Jobs run on their own `ci` network.** They can reach Forgejo and the `dind` daemon, but not your other homelab services.
- **The runner talks to Forgejo directly at `http://forgejo:3000`**, never through Caddy, so Authelia never sees CI traffic for git or the API.

### The risk that remains

The `dind` container has to run as `privileged`, and any job that sets `DOCKER_HOST` can use it. A hostile workflow on a branch could use that to break out onto the host. This is acceptable for 0.x, because only you and the `claude` account can push branches, and the repo is private. Before outside contributors can trigger CI (at 1.0, on GitHub), this must be revisited. GitHub-hosted runners solve it there.

To narrow it further, you could use the `docker:<version>-dind-rootless` image. It still needs `privileged`, but the daemon runs as a non-root user inside. Check that image builds still work before you switch.

## 2. Compose file

Put this in its own folder on the home server, for example `/opt/forgejo-runner/compose.yaml`:

```yaml
services:
  docker-in-docker:
    image: docker:<version>-dind          # pin a current version, e.g. docker:28-dind
    container_name: ci-dind
    hostname: docker-in-docker
    privileged: true
    restart: unless-stopped
    command:
      - dockerd
      - -H
      - tcp://0.0.0.0:2375
      - --tls=false
      - --insecure-registry=forgejo:3000
    volumes:
      - ci-dind:/var/lib/docker
    networks: [ci]

  runner:
    image: code.forgejo.org/forgejo/runner:<version>   # pin the current release
    container_name: forgejo-runner
    user: "1000:1000"
    restart: unless-stopped
    depends_on: [docker-in-docker]
    environment:
      DOCKER_HOST: tcp://docker-in-docker:2375
    command: forgejo-runner daemon --config /data/config.yml
    volumes:
      - ./data:/data
    networks: [ci]

volumes:
  ci-dind:

networks:
  ci:
    name: ci
```

Notes:

- Port 2375 is plain HTTP with no TLS, so **never publish it** (no `ports:`). It's only reachable on the `ci` network.
- `--insecure-registry=forgejo:3000` lets image builds push to Forgejo's registry over the internal HTTP address.
- Create the data folder owned by UID 1000 before starting: `mkdir data && sudo chown 1000:1000 data`.

### Join Forgejo to the `ci` network

In Forgejo's own compose file, add the `ci` network as a second, external network. Give it the alias `forgejo` if the service has a different name:

```yaml
services:
  forgejo:
    # …existing settings…
    networks:
      default: {}          # or whatever network Caddy uses today
      ci:
        aliases: [forgejo]

networks:
  ci:
    external: true
```

Bring the runner stack up first (it creates the `ci` network), then recreate Forgejo.

## 3. Generate the config and register

1. Write a default config, then edit it:

   ```bash
   docker compose run --rm runner forgejo-runner generate-config > data/config.yml
   ```

2. In `data/config.yml`, set these values (check the key names against the file you generated):

   ```yaml
   runner:
     file: .runner
     capacity: 1                  # one job at a time; the home server is shared
     labels:
       - "ubuntu-latest:docker://node:24-bookworm"
   cache:
     enabled: true                # jobs reach the runner's cache over the ci network
   container:
     network: ci                  # job containers join the ci network
     privileged: false            # job containers are never privileged
     valid_volumes: []            # jobs can't mount host paths
     docker_host: "-"             # don't mount any Docker socket into jobs
   ```

   About the label: `ubuntu-latest` keeps the workflow files the same as GitHub Actions, so they port easily at 1.0. `node:24-bookworm` has the Node that JavaScript actions such as `actions/checkout` need. Python is installed in each job with uv. Only the image-build job is given `DOCKER_HOST: tcp://docker-in-docker:2375`, in the workflow itself.

3. Get a registration token. Create the runner at **repository** level, so it only runs Mealwright's jobs: open the repo, then **Settings → Actions → Runners → Create new runner**, and copy the token.

4. Register, using the internal address:

   ```bash
   docker compose run --rm runner forgejo-runner register --no-interactive \
     --instance http://forgejo:3000 \
     --token <registration token> \
     --name home-server \
     --labels "ubuntu-latest:docker://node:24-bookworm"
   ```

   This writes `data/.runner`. Treat it like a password.

5. Start it: `docker compose up -d`. The runner should show as idle under **Settings → Actions → Runners**.

## 4. Reaching Forgejo without Caddy and Authelia

The runner itself is fine: it was registered with `http://forgejo:3000`. Two other things follow Forgejo's `ROOT_URL` (`https://git.example.org`) unless you deal with them:

- **Checking out the code.** `actions/checkout` clones from `github.server_url`, which is the public URL. Mealwright's workflows pass the internal address instead:

  ```yaml
  - uses: actions/checkout@v4
    with:
      github-server-url: http://forgejo:3000
  ```

  Claude Code will write the workflows this way, so you don't need to change anything for this.

- **Artifact upload and download.** These also use the public URL. Mealwright's 0.x workflows won't use artifacts, so this doesn't matter yet.

Actions such as `actions/checkout` are downloaded by the runner from `data.forgejo.org` (Forgejo's `DEFAULT_ACTIONS_URL`). That's an outbound connection from your CI, not from Mealwright. If you'd rather avoid it, mirror the few actions the workflows use into your Forgejo, and point `[actions] DEFAULT_ACTIONS_URL` at it.

## 5. The private image registry

### Credentials for CI

Forgejo's automatic job token may not be allowed to push packages, so create a token just for this:

1. Create a token with only the **`write:package`** scope. Make it on your account, or on a separate bot account that has write access to `tess/mealwright`.
2. Add it to the repo under **Settings → Actions → Secrets** as `REGISTRY_TOKEN`, with the account name as `REGISTRY_USER`.

The image job runs only on `v0.*` tags, and only you can create those. **But Forgejo has no protected environments:** a workflow on any branch in this repo can read repo secrets. The `claude` account can push branches, so in practice it could read `REGISTRY_TOKEN`. That's why the token should do nothing except write packages. The worst case is an image pushed to your private registry, which is another reason to check, before you deploy, that the tag you pull came from a run on a tag you created.

### Why `/v2/` needs an Authelia bypass

CI logs in to the registry at `forgejo:3000`, but the registry tells Docker to fetch its login token from `ROOT_URL` + `/v2/token`, which is `https://git.example.org/v2/token`. That request goes through Caddy, and Authelia blocks it. So the registry paths need to skip Authelia. This is safe, because Forgejo's registry checks its own tokens.

My HTTPS pushes as `claude` already work, so you probably have a similar bypass for git already. Add the registry paths to it in Authelia's `access_control`:

```yaml
- domain: git.example.org
  resources:
    - '^/v2/.*$'
  policy: bypass
```

Check: after this, `curl -i https://git.example.org/v2/` should return `401` with a `WWW-Authenticate` header from Forgejo, not a redirect to Authelia.

### Pulling on the home server

With the bypass in place, pull the normal way:

```bash
docker login git.example.org
docker pull git.example.org/tess/mealwright:0.1.0
```

Use a token with only **`read:package`** for this login.

## 6. Turn on the status-check rule for `main`

Wait until the first CI run on a pull request is green. Then:

1. Go to **Settings → Branches**, and edit the protection rule for `main`.
2. Switch on **Enable status check**.
3. Add the check names to require. They appear after the first run, in the form `<workflow name> / <job name> (<event>)`. A pattern such as `ci / *` covers every job in the `ci` workflow.
4. Save. From now on, pull requests can't be merged into `main` until CI is green.

## Quick check after setup

- [ ] `forgejo-runner` shows as idle in the repo's runner list.
- [ ] `docker exec forgejo-runner ls /var/run/docker.sock` fails (no host socket in the runner).
- [ ] A test pull request runs CI and checks out the code over `http://forgejo:3000`.
- [ ] `curl -i https://git.example.org/v2/` returns `401` from Forgejo, not Authelia.
- [ ] After `v0.1.0` is tagged, the image is under **Packages** on your Forgejo profile, and the home server can pull it.
- [ ] The status-check rule is on for `main`.
