# Setting up the Forgejo runner

Written 17 Oct 2026 for milestone 0.1, revised the same day after cabledrawer's review. cabledrawer does this setup; Claude Code doesn't touch the servers.

CI for Mealwright runs on Forgejo Actions (Forgejo 16.0.6 on the home server) with one `forgejo-runner`. This guide covers:

1. where the runner should run: the NAS or the home server
2. setting it up on the NAS (recommended)
3. how the NAS reaches Forgejo, and the Authelia rules
4. the private image registry, and why it needs a stored token
5. never auto-updating Mealwright images on the homelab
6. switching on the status-check rule for `main`

Appendix A keeps the home server setup, in case you choose it later.

Version numbers and config keys change between runner releases. Wherever this guide says "check", compare it with the release notes or with what `forgejo-runner generate-config` prints for your version.

## 1. Where the runner runs

CI jobs run whatever workflow code is on the branch being tested, including branches pushed by the `claude` account. Building Docker images needs a Docker daemon. The usual way to give jobs one, without handing over the host's own Docker socket, is a **Docker-in-Docker (`dind`) container, which must run `privileged`**. A hostile or buggy job that reaches `dind` can break out onto whatever machine `dind` runs on. Where the runner lives decides what such a breakout could reach.

| | **NAS, inside a small VM** (recommended) | **NAS, as containers** | **home server, as containers** |
|---|---|---|---|
| A breakout from `dind` reaches | the VM only | the NAS host and everything stored on it | the other apps, Forgejo, Authelia |
| Reaching Forgejo | over the LAN through Caddy (HTTPS), Authelia bypassed for the NAS's address only | same | directly on a Docker network at `http://forgejo:3000` |
| Authelia rules needed | NAS address only, for the runner's and jobs' paths | same | `/v2/` only |
| `ROOT_URL` problems (checkout, registry login) | none, since everything uses the normal URL | none | needs workarounds (see Appendix A) |
| Effect on other services | uses NAS CPU and RAM; doesn't compete with the home server | same | competes with the other apps for CPU |
| Setup effort | most: create a VM first | least | medium |

**Recommendation: a small VM on the NAS** (2 vCPU, 4 GB RAM, about 40 GB disk, Debian with Docker). A VM is a real security boundary between CI jobs and anything you care about. Running as containers directly on the NAS is better than the home server only if the NAS doesn't hold anything more sensitive. A NAS often holds backups of the other apps, and if so a breakout there is as bad as one on the home server.

**cabledrawer to confirm before choosing:**

- the NAS model and OS, and whether it can run VMs (most NAS systems can: Synology Virtual Machine Manager, TrueNAS, Unraid, or Proxmox)
- its CPU architecture. 0.x images are amd64 only, so an ARM NAS would have to build under emulation, which is slow.
- what it stores (are home server backups on it?)
- free RAM for a 4 GB VM

The rest of this guide assumes the VM. The steps are the same for plain containers on the NAS, using the NAS's own Docker.

## 2. Runner on the NAS

### 2.1 Compose file

In the VM (or on the NAS), put this in `/opt/forgejo-runner/compose.yaml`:

```yaml
services:
  docker-in-docker:
    image: docker:<version>-dind          # pin a current version
    hostname: docker-in-docker
    privileged: true                      # contained by the VM
    restart: unless-stopped
    command: ["dockerd", "-H", "tcp://0.0.0.0:2375", "--tls=false"]
    volumes:
      - ci-dind:/var/lib/docker
    networks: [ci]

  runner:
    image: code.forgejo.org/forgejo/runner:<version>   # pin the current release
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
    ipam:
      config:
        - subnet: 172.29.250.0/24   # fixed, so firewall and Authelia rules can name it
```

Notes:

- Port 2375 is plain HTTP with no TLS, so **never publish it** (no `ports:`).
- Create the data folder owned by UID 1000 before starting: `mkdir data && sudo chown 1000:1000 data`.
- Jobs reach the outside world through the VM's NAT, so Caddy and Authelia see every request from CI as coming from the VM's LAN address.
- **Give the VM a fixed LAN address** (a DHCP reservation). This guide calls it `<runner-ip>`. If you run containers directly on the NAS instead, `<runner-ip>` is `192.168.1.50`.

### 2.2 Name resolution and TLS

From inside the VM, check both of these before registering:

```bash
getent hosts git.example.org         # should be the home server's LAN address
curl -sI https://git.example.org/    # should succeed with no certificate error
```

If Caddy uses its own internal CA instead of a public certificate, the runner and the job images need that CA. Tell Claude Code, and the workflows will add it.

### 2.3 Config and registration

1. Write a default config:

   ```bash
   docker compose run --rm runner forgejo-runner generate-config > data/config.yml
   ```

2. Edit these values in `data/config.yml` (check the key names against the generated file):

   ```yaml
   runner:
     file: .runner
     capacity: 1
     labels:
       - "ubuntu-latest:docker://node:24-bookworm"
   cache:
     enabled: true
   container:
     network: ci          # job containers join the ci network
     privileged: false    # job containers are never privileged
     valid_volumes: []    # jobs can't mount host paths
     docker_host: "-"     # don't mount any Docker socket into jobs
   ```

   The `ubuntu-latest` label keeps workflow files the same as GitHub Actions, so they port easily at 1.0. `node:24-bookworm` has the Node that JavaScript actions need. Python is installed in each job with uv. Only the image-build job is given `DOCKER_HOST: tcp://docker-in-docker:2375`, in the workflow itself.

3. Get a registration token at **repository** level, so the runner only takes Mealwright's jobs: open the repo, then **Settings → Actions → Runners → Create new runner**.

4. Register using the normal address. This needs the Authelia rule from section 3 first.

   ```bash
   docker compose run --rm runner forgejo-runner register --no-interactive \
     --instance https://git.example.org \
     --token <registration token> \
     --name nas-ci \
     --labels "ubuntu-latest:docker://node:24-bookworm"
   ```

   This writes `data/.runner`. Treat it like a password.

5. Start it with `docker compose up -d`. The runner should show as idle under **Settings → Actions → Runners**.

## 3. Reaching Forgejo, and the Authelia rules

With the runner on the NAS, everything uses `https://git.example.org` through Caddy. The runner protocol, checkout, the job's API calls and the registry all match Forgejo's `ROOT_URL`, so no workarounds are needed. Authelia must let these requests through without its login, **but only from the right networks**. Forgejo still checks its own tokens on every one of them.

Today, `/v2/` redirects to Authelia (checked 17 Oct: `302` to `auth.example.org`). Plain requests to `/api/v1/` get `403`, while `tea` with a token works. So there's already some token rule; fit these rules alongside it, **above** any broader rule for the domain, because Authelia uses the first rule that matches.

```yaml
access_control:
  rules:
    # Container registry: CI pushes and homelab pulls. LAN and ci subnet only.
    - domain: git.example.org
      resources:
        - '^/v2/'
      networks:
        - 192.168.1.0/24        # LAN (includes the runner VM / NAS)
        - 172.29.250.0/24       # ci network (needed only for the home server setup in Appendix A)
      policy: bypass

    # Runner and CI jobs. The runner's address only.
    - domain: git.example.org
      resources:
        - '^/api/actions/'                                        # runner ↔ Forgejo
        - '^/api/actions_pipeline/'                               # cache and artifacts
        - '^/api/v1/repos/tess/mealwright([/?]|$)'             # API calls made by actions
        - '^/tess/mealwright(\.git)?/(info/refs|git-upload-pack)'  # checkout (read only)
      networks:
        - <runner-ip>/32
      policy: bypass
```

Notes:

- No `git-receive-pack` for the runner: CI never pushes code.
- On Authelia 4.38 and later you can name the networks once under `definitions.network` and refer to them by name. Plain CIDRs work too.
- **Check that Caddy sees real client addresses.** If Caddy runs in Docker, requests can arrive from the Docker gateway (for example `172.17.0.1`) instead of the real client. Then a `networks:` rule doesn't do what it says. After setting the rules up, make one request from the NAS and one from a phone on mobile data, and check the remote IP in Authelia's log for each. The phone must still be sent to the Authelia login.
- After the rules are in: from the runner, `curl -i https://git.example.org/v2/` should return `401` from Forgejo. From outside the LAN, it should still redirect to Authelia.

If a checkout or action fails with a redirect to `auth.example.org`, Authelia's log shows which path was blocked. Add that path to the runner rule, not to a broader rule.

Actions such as `actions/checkout` are downloaded by the runner from `data.forgejo.org`. That's an outbound connection from your CI, not from Mealwright. To avoid it, mirror the few actions the workflows use into your Forgejo, and set `[actions] DEFAULT_ACTIONS_URL`.

## 4. The private image registry

### The automatic job token can't push images (Forgejo 16.0.6)

Checked in the source for `v16.0.6`, `services/packages/perm.go` (`DeterminePackageAccessMode`):

- A job's automatic token (`FORGEJO_TOKEN` / `GITHUB_TOKEN`) signs in as the built-in **Actions** user (`services/auth/method/action_task_token.go`), and has no token scope.
- The package permission check has `// TODO: ActionUser permission check` and no special case for that user. For a package owned by a **user** (Mealwright's package belongs to `tess`), write access goes only to that user. Anyone else gets read at most, or nothing for a private account.

So on this version, a workflow can't push to `tess/mealwright` with the automatic token. A stored secret is needed. Recheck this when you upgrade Forgejo: the TODO suggests it may change.

This also means **a bot account wouldn't work either**. Write access to the repo doesn't give write access to packages owned by a user account. The two options are:

1. **Your own token, scoped to packages only (simplest).** Create a token on your account with only **`write:package`**. Add it to the repo under **Settings → Actions → Secrets** as `REGISTRY_TOKEN`, with `REGISTRY_USER` = `tess`.
2. **An organisation (tighter).** Move the repo to an organisation (for example `mealwright`), and create a `ci-bot` user in a team that has **Packages: Write** and nothing else. The stored token can then only write that organisation's packages, never anything else under your name. It's more setup, and the repo URL changes.

Either way, **Forgejo has no protected environments**: a workflow on any branch in this repo, including one pushed by `claude`, can read repo secrets. Keep the token to `write:package` only. The worst case is then an unwanted image in your private registry. Section 5 makes sure that can't reach your homelab by itself.

### Pulling on the homelab

Pull by exact version, with a token that has only **`read:package`**:

```bash
docker login git.example.org
docker pull git.example.org/tess/mealwright:0.1.0
```

## 5. Never auto-update Mealwright from the private registry

**The homelab must never update Mealwright images by itself.** 0.x images are development builds. Any branch workflow could, in principle, push an image to the private registry (see section 4), and an automatic update would then run it next to your real services without you looking.

- Pin an **exact version** in compose (`…/mealwright:0.1.0`), never `latest` or a moving tag such as `0.1`.
- **Watchtower** (or similar): exclude the container with the label `com.centurylinklabs.watchtower.enable=false`, or run Watchtower with `--label-enable` so it only touches containers you opt in.
- **Diun** is fine: it only notifies. **Renovate**: no auto-merge for Mealwright images.
- Update by hand: check that the tag matches a `v0.*` tag you created, change the version in compose, then `docker compose pull && docker compose up -d`.

## 6. Turn on the status-check rule for `main`

Wait until the first CI run on a pull request is green. Then:

1. Go to **Settings → Branches**, and edit the protection rule for `main`.
2. Switch on **Enable status check**.
3. Add the check names to require. They appear after the first run, in the form `<workflow name> / <job name> (<event>)`. A pattern such as `ci / *` covers every job in the `ci` workflow.
4. Save. Pull requests can then only be merged into `main` once CI is green.

## Quick check after setup

- [ ] The runner shows as idle in the repo's runner list.
- [ ] There's no Docker socket in the runner or in jobs: `docker compose exec runner ls /var/run/docker.sock` fails.
- [ ] A test pull request runs CI and checks out the code.
- [ ] From the runner: `curl -i https://git.example.org/v2/` gives `401` from Forgejo. From a phone on mobile data, it redirects to Authelia.
- [ ] After `v0.1.0` is tagged, the image is under **Packages**, and the homelab can pull it by exact version.
- [ ] No automatic updater touches the Mealwright container (section 5).
- [ ] The status-check rule is on for `main`.

## Appendix A: runner on the home server (not chosen)

This was the first version of this guide. cabledrawer put it on hold on 17 Oct, because a privileged `dind` would share the home server with the other apps. It's kept here for comparison.

- Same compose file as section 2.1, on the home server, plus `--insecure-registry=forgejo:3000` on `dockerd`. Forgejo's container joins the `ci` network as an external network, with the alias `forgejo`.
- Register with `--instance http://forgejo:3000`. Runner traffic never goes through Caddy.
- Workflows check out with `github-server-url: http://forgejo:3000`, because the default checkout URL follows `ROOT_URL` and would go through Authelia.
- Artifact upload also follows `ROOT_URL`. Avoid artifacts, or add `/api/actions_pipeline/` to a bypass for the `ci` subnet.
- Registry login at `forgejo:3000` is still sent to `ROOT_URL/v2/token` (`https://git.example.org/v2/token`). So the `/v2/` bypass in section 3 still needs the `ci` subnet (`172.29.250.0/24`).
- **Risk:** a breakout from `dind` reaches the home server host and everything on it.
