# Setting up the Forgejo runner

Written 17 Oct 2026 for milestone 0.1, revised the same day after cabledrawer's review. cabledrawer does this setup; Claude Code doesn't touch the servers.

CI for Mealwright runs on Forgejo Actions (Forgejo 16.0.6 on the home server) with one `forgejo-runner`. **Decided (cabledrawer 17 Oct): the runner runs in a KVM VM on the NAS**, using libvirt and macvtap networking. This guide covers:

1. why a VM on the NAS
2. creating the VM, with automatic security updates
3. checking the VM's network: it reaches Forgejo but not the NAS host
4. installing and registering the runner in the VM
5. the Authelia rules
6. the private image registry, and why it needs a stored token
7. never auto-updating Mealwright images on the homelab
8. switching on the status-check rule for `main`
9. the NFS mount on the home server: `nosuid,nodev`, and the checks to do before adding `noexec`

Appendix A covers plain containers on the NAS, and Appendix B the home server. Neither was chosen; they're kept for comparison.

Version numbers and config keys change between runner releases. Wherever this guide says "check", compare it with the release notes or with what `forgejo-runner generate-config` prints for your version.

## 1. Why a VM on the NAS

CI jobs run whatever workflow code is on the branch being tested, including branches pushed by the `claude` account. Building Docker images needs a Docker daemon. The usual way to give jobs one, without handing over the host's own Docker socket, is a **Docker-in-Docker (`dind`) container, which must run `privileged`**. A hostile or buggy job that reaches `dind` can break out onto whatever machine `dind` runs on.

The NAS (cabledrawer 17 Oct): a plain Linux server with Docker (no NAS OS), amd64, with a few GB of RAM free, KVM support. It runs a VPN client (with its credentials), download clients and a media server. The home server's backups aren't on it (the backup tool sends them to offsite storage). But **the home server mounts the NAS's `/mnt/pool` over NFS at `/mnt/share`**, so whoever controls the NAS controls files the home server reads.

| | **NAS, in a KVM VM** (chosen) | NAS, as containers (Appendix A) | home server, as containers (Appendix B) |
|---|---|---|---|
| A breakout from `dind` reaches | the VM only. Getting further needs a separate VM escape, which is much rarer. The VM is just another device on the LAN, and macvtap stops it reaching the NAS host. | the NAS host as root: **a VPN client (with its credentials), download clients, a media server**, all of `/mnt/pool`, and through NFS, **files the home server reads at `/mnt/share`** | the other apps, Forgejo, Authelia, and the backup tool with its credentials |
| Reaching Forgejo | over the LAN through Caddy (HTTPS), Authelia bypassed for the VM's address only | same, for `192.168.1.50` | directly on a Docker network at `http://forgejo:3000` |
| `ROOT_URL` problems (checkout, registry login) | none, since everything uses the normal URL | none | needs workarounds |
| Effect on other services | 4 GB RAM and 2 of the processor's cores; doesn't compete with the home server | shares the NAS with the media server and the downloaders | competes with the other apps for CPU |
| Setup effort | one KVM VM with libvirt. **No Proxmox.** | least | medium |

## 2. Create the VM

### 2.1 Install KVM and libvirt on the NAS

```bash
sudo apt install --no-install-recommends qemu-system-x86 qemu-utils libvirt-daemon-system virtinst
```

### 2.2 Disk

Keep the VM's disk on the NAS's system disk, not under `/mnt/pool`:

```bash
sudo mkdir -p /var/lib/libvirt/images/ci && cd /var/lib/libvirt/images/ci
# Check the exact file name at https://cloud-images.ubuntu.com/releases/26.04/release/
sudo wget https://cloud-images.ubuntu.com/releases/26.04/release/ubuntu-26.04-server-cloudimg-amd64.img
sudo qemu-img create -f qcow2 -F qcow2 -b ubuntu-26.04-server-cloudimg-amd64.img ci-runner.qcow2 40G
```

### 2.3 First-boot settings, including automatic security updates

Write `user-data.yaml` in the same folder:

```yaml
#cloud-config
hostname: ci-runner
users:
  - name: tess
    groups: [sudo]
    shell: /bin/bash
    sudo: ALL=(ALL) NOPASSWD:ALL
    ssh_authorized_keys:
      - ssh-ed25519 AAAA…   # your public key
package_update: true
package_upgrade: true
packages:
  - docker.io
  - docker-compose-v2
  - unattended-upgrades
write_files:
  # Turn on daily package-list refresh and unattended upgrades.
  - path: /etc/apt/apt.conf.d/20auto-upgrades
    content: |
      APT::Periodic::Update-Package-Lists "1";
      APT::Periodic::Unattended-Upgrade "1";
      APT::Periodic::AutocleanInterval "7";
  # Security updates (Ubuntu's default) plus -updates, which is where docker.io
  # fixes often land. Reboot at 04:00 when an update needs it (kernel, libc).
  - path: /etc/apt/apt.conf.d/52unattended-upgrades-local
    content: |
      Unattended-Upgrade::Allowed-Origins {
        "${distro_id}:${distro_codename}-updates";
      };
      Unattended-Upgrade::Automatic-Reboot "true";
      Unattended-Upgrade::Automatic-Reboot-Time "04:00";
runcmd:
  - [systemctl, enable, --now, docker]
  - [systemctl, enable, --now, unattended-upgrades]
```

Notes:

- Unattended upgrades update the VM's own packages: the kernel, Docker and the OS. The runner and `dind` containers update only when you change the pinned versions in the compose file.
- A reboot stops any CI job that's running, and it gets marked failed; re-run it. The runner and `dind` come back by themselves (`restart: unless-stopped`).
- The NAS host's own updates are separate. If they reboot the NAS, the VM starts again because of `virsh autostart`.

### 2.4 Create the VM

Find the NAS's LAN interface name with `ip -br link` (for example `enp2s0`), then:

```bash
sudo virt-install --name ci-runner --memory 4096 --vcpus 2 \
  --disk /var/lib/libvirt/images/ci/ci-runner.qcow2 --import \
  --osinfo detect=on,require=off \
  --network type=direct,source=<nas-lan-interface>,source_mode=bridge,model=virtio \
  --cloud-init user-data=user-data.yaml \
  --graphics none --noautoconsole
sudo virsh autostart ci-runner
```

Notes:

- `type=direct` (macvtap) puts the VM straight on the LAN with its own address. A side effect is that **the VM and the NAS host can't reach each other over the network**, which is what we want here. To manage the VM, SSH to it from another machine on the LAN, or use `sudo virsh console ci-runner` on the NAS.
- Give the VM a DHCP reservation on your router. That address is `<runner-ip>` in the rest of this guide.
- Don't add the VM's address to the NFS exports.

### 2.5 Check the updates are set up

In the VM:

```bash
cloud-init status --wait                          # should end with "status: done"
systemctl is-enabled unattended-upgrades          # enabled
apt-config dump | grep -E 'Periodic::(Update-Package-Lists|Unattended-Upgrade)'   # both "1"
sudo unattended-upgrade --dry-run --debug 2>&1 | grep -i 'allowed origins'        # lists -security and -updates
```

## 3. Check the VM's network

Do this before installing the runner. **The VM must reach Forgejo on the home server, and must not reach the NAS host.** Run these in the VM:

```bash
# 1. Forgejo on the home server: these should work
getent hosts git.example.org                   # the home server's LAN address
curl -sS -o /dev/null -w '%{http_code}\n' https://git.example.org/
#    → 200 or 302 (Authelia), and no certificate error

# 2. The NAS host: all of these should FAIL (time out or "no route to host")
ping -c 2 -W 2 192.168.1.50
nc -zv -w 3 192.168.1.50 22      # SSH
nc -zv -w 3 192.168.1.50 2049    # NFS
nc -zv -w 3 192.168.1.50 111     # rpcbind
```

If any NAS check succeeds, the VM isn't on macvtap. Run `sudo virsh domiflist ci-runner` on the NAS: the type should be `direct`.

If Caddy uses its own internal CA instead of a public certificate, the `curl` will fail with a certificate error. The runner and the job images then need that CA; tell Claude Code, and the workflows will add it.

Run the same checks again after section 4, from a container started **inside `dind`**, where CI jobs actually run. Run this in `/opt/forgejo-runner`:

```bash
docker compose exec -e DOCKER_HOST=tcp://localhost:2375 docker-in-docker \
  docker run --rm alpine sh -c '
    wget -q -O /dev/null https://git.example.org/ && echo "Forgejo reachable: OK"
    nc -w 3 192.168.1.50 22 </dev/null && echo "NAS REACHABLE: NOT OK" || echo "NAS blocked: OK"'
```

`wget` may report a redirect to Authelia; that's fine. What matters is that it connects without a certificate error, and that the second line says `NAS blocked: OK`.

The VM can still reach the rest of the LAN, as any device can. Limiting what jobs can reach (only the home server on 443, DNS and the internet) is a possible later hardening step, using nftables rules in Docker's `DOCKER-USER` chain. It isn't needed for 0.x.

## 4. The runner in the VM

### 4.1 Compose file

In the VM, put this in `/opt/forgejo-runner/compose.yaml`:

```yaml
services:
  docker-in-docker:
    image: docker:<version>-dind          # pin a current version
    hostname: docker-in-docker
    privileged: true                      # contained by the VM (section 1)
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
- Job containers run inside `dind`, not on the VM's own Docker. They leave through `dind` and then the VM's NAT, so Caddy and Authelia see every request from CI as coming from the VM's LAN address.

### 4.2 Config and registration

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
     network: ""          # a new network for each job, inside dind
     privileged: false    # job containers are never privileged
     valid_volumes: []    # jobs can't mount host paths
     docker_host: "-"     # don't mount any Docker socket into jobs
   ```

   The `ubuntu-latest` label keeps workflow files the same as GitHub Actions, so they port easily at 1.0. `node:24-bookworm` has the Node that JavaScript actions need. Python is installed in each job with uv. Only the image-build job is given `DOCKER_HOST: tcp://docker-in-docker:2375`, in the workflow itself.

3. Get a registration token at **repository** level, so the runner only takes Mealwright's jobs: open the repo, then **Settings → Actions → Runners → Create new runner**.

4. Register using the normal address. This needs the Authelia rules from section 5 first.

   ```bash
   docker compose run --rm runner forgejo-runner register --no-interactive \
     --instance https://git.example.org \
     --token <registration token> \
     --name ci-runner \
     --labels "ubuntu-latest:docker://node:24-bookworm"
   ```

   This writes `data/.runner`. Treat it like a password.

5. Start it with `docker compose up -d`. The runner should show as idle under **Settings → Actions → Runners**.

## 5. The Authelia rules

From the VM, everything uses `https://git.example.org` through Caddy. The runner protocol, checkout, the job's API calls and the registry all match Forgejo's `ROOT_URL`, so no workarounds are needed. Authelia must let these requests through without its login, **but only from the right networks**. Forgejo still checks its own tokens on every one of them.

Today, `/v2/` redirects to Authelia (checked 17 Oct: `302` to `auth.example.org`). Plain requests to `/api/v1/` get `403`, while `tea` with a token works. So there's already some token rule; fit these rules alongside it, **above** any broader rule for the domain, because Authelia uses the first rule that matches.

```yaml
access_control:
  rules:
    # Container registry: CI pushes and homelab pulls. LAN and ci subnet only.
    - domain: git.example.org
      resources:
        - '^/v2/'
      networks:
        - 192.168.1.0/24        # LAN, including the runner VM
        # - 172.29.250.0/24     # ci subnet: only needed for the home server setup (Appendix B)
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
- With the runner in the VM, CI traffic reaches Caddy from the VM's LAN address, because jobs leave through the VM's NAT. So the `/v2/` rule only needs the LAN. The `ci` subnet line is left commented out: it only matters if `dind` runs on the home server itself (Appendix B). An enabled range that nothing uses would only widen the bypass.
- On Authelia 4.38 and later you can name the networks once under `definitions.network` and refer to them by name. Plain CIDRs work too.
- **Check that Caddy sees real client addresses.** If Caddy runs in Docker, requests can arrive from the Docker gateway (for example `172.17.0.1`) instead of the real client. Then a `networks:` rule doesn't do what it says. After setting the rules up, make one request from the VM and one from a phone on mobile data, and check the remote IP in Authelia's log for each. The phone must still be sent to the Authelia login.
- After the rules are in: from the runner, `curl -i https://git.example.org/v2/` should return `401` from Forgejo. From outside the LAN, it should still redirect to Authelia.

If a checkout or action fails with a redirect to `auth.example.org`, Authelia's log shows which path was blocked. Add that path to the runner rule, not to a broader rule.

Actions such as `actions/checkout` are downloaded by the runner from `data.forgejo.org`. That's an outbound connection from your CI, not from Mealwright. To avoid it, mirror the few actions the workflows use into your Forgejo, and set `[actions] DEFAULT_ACTIONS_URL`.

## 6. The private image registry

### The automatic job token can't push images (Forgejo 16.0.6)

Checked in the source for `v16.0.6`, `services/packages/perm.go` (`DeterminePackageAccessMode`):

- A job's automatic token (`FORGEJO_TOKEN` / `GITHUB_TOKEN`) signs in as the built-in **Actions** user (`services/auth/method/action_task_token.go`), and has no token scope.
- The package permission check has `// TODO: ActionUser permission check` and no special case for that user. For a package owned by a **user** (Mealwright's package belongs to `tess`), write access goes only to that user. Anyone else gets read at most, or nothing for a private account.

So on this version, a workflow can't push to `tess/mealwright` with the automatic token. A stored secret is needed. Recheck this when you upgrade Forgejo: the TODO suggests it may change.

This also means **a bot account wouldn't work either**. Write access to the repo doesn't give write access to packages owned by a user account. The two options are:

1. **Your own token, scoped to packages only (simplest).** Create a token on your account with only **`write:package`**. Add it to the repo under **Settings → Actions → Secrets** as `REGISTRY_TOKEN`, with `REGISTRY_USER` = `tess`.
2. **An organisation (tighter).** Move the repo to an organisation (for example `mealwright`), and create a `ci-bot` user in a team that has **Packages: Write** and nothing else. The stored token can then only write that organisation's packages, never anything else under your name. It's more setup, and the repo URL changes.

Either way, **Forgejo has no protected environments**: a workflow on any branch in this repo, including one pushed by `claude`, can read repo secrets. Keep the token to `write:package` only. The worst case is then an unwanted image in your private registry. Section 7 makes sure that can't reach your homelab by itself.

### Pulling on the homelab

Pull by exact version, with a token that has only **`read:package`**:

```bash
docker login git.example.org
docker pull git.example.org/tess/mealwright:0.1.0
```

## 7. Never auto-update Mealwright from the private registry

**The homelab must never update Mealwright images by itself.** 0.x images are development builds. Any branch workflow could, in principle, push an image to the private registry (see section 6), and an automatic update would then run it next to your real services without you looking.

- Pin an **exact version** in compose (`…/mealwright:0.1.0`), never `latest` or a moving tag such as `0.1`.
- **Watchtower** (or similar): exclude the container with the label `com.centurylinklabs.watchtower.enable=false`, or run Watchtower with `--label-enable` so it only touches containers you opt in.
- **Diun** is fine: it only notifies. **Renovate**: no auto-merge for Mealwright images.
- Update by hand: check that the tag matches a `v0.*` tag you created, change the version in compose, then `docker compose pull && docker compose up -d`.

## 8. Turn on the status-check rule for `main`

Wait until the first CI run on a pull request is green. Then:

1. Go to **Settings → Branches**, and edit the protection rule for `main`.
2. Switch on **Enable status check**.
3. Add the check names to require. They appear after the first run, in the form `<workflow name> / <job name> (<event>)`. A pattern such as `ci / *` covers every job in the `ci` workflow.
4. Save. Pull requests can then only be merged into `main` once CI is green.

## 9. The NFS mount on the home server

### `nosuid,nodev` is a requirement

The home server mounts the NAS's `/mnt/pool` at `/mnt/share` with **`nosuid,nodev`** (done 17 Oct). **This must stay**, whatever happens to the runner. It stops a compromised NAS from planting setuid programs or device files that would give root on the home server.

It doesn't stop planted *content*. Anything on the home server that reads or runs files from `/mnt/share` must treat them as untrusted.

### Before adding `noexec`: the exact checks

`noexec` stops programs on the share from being **run directly** on the home server, including inside containers that bind-mount it. It doesn't stop an interpreter reading a script from the share (`bash /mnt/share/x.sh`, `python …`), so checks 3 and 4 matter as much as the option itself. Run these on the home server:

```bash
# 0. Current options. Note them down; you'll need them for step 6.
findmnt -no SOURCE,OPTIONS /mnt/share

# 1. Programs running from the share right now. Should print nothing.
sudo ls -l /proc/[0-9]*/exe 2>/dev/null | grep -F /mnt/share

# 2. Libraries loaded from the share right now. Should print nothing.
sudo grep -lF /mnt/share /proc/[0-9]*/maps 2>/dev/null

# 3. Containers that bind-mount the share, and where it appears inside them.
docker ps --format '{{.Names}}' | xargs -r docker inspect \
  --format '{{.Name}}{{range .Mounts}}{{if eq .Type "bind"}} {{.Source}} -> {{.Destination}}{{end}}{{end}}' \
  | grep -F share

# 4. Config, cron jobs, systemd units and scripts that mention the share.
sudo grep -rIlF --exclude-dir=.cache /mnt/share \
  /etc /var/spool/cron /root /home /opt 2>/dev/null
```

How to read them:

- **Steps 1 and 2** only see host processes. Containers report paths as they appear inside the container, so they're covered by step 3.
- **Step 3:** for each container listed, check that it only *reads* files there (photos, documents, media) and never runs a program from the destination path. Read-only media libraries (an Immich external library, a Paperless consume folder) are fine with `noexec`.
- **Step 4:** for each file listed, check whether it runs something stored on the share, for example a backup hook or a cron job calling `/mnt/share/…/script.sh`. Anything like that must move off the share. That's needed for safety anyway, not just for `noexec`.
- Add any other folders where your compose files live to step 4, if they aren't under `/home` or `/opt`.

If all four are clean:

```bash
# 5. Try it until the next reboot, without changing fstab.
sudo mount -o remount,noexec /mnt/share
findmnt -no OPTIONS /mnt/share        # now includes noexec

# Leave it for a day or two (including a nightly backup run), then look for failures:
journalctl --since "-2 days" -p warning | grep -iE 'permission denied|share'
```

To undo it straight away: `sudo mount -o remount,exec /mnt/share`.

**Step 6:** if nothing broke, make it permanent. Add `noexec` next to `nosuid,nodev`, wherever the mount is defined (`/etc/fstab` or a systemd `.mount` unit). Then remount, or reboot, and check with `findmnt -no OPTIONS /mnt/share` that all three are present.

## Quick check after setup

- [ ] `cloud-init status` in the VM is `done`, and the update checks in section 2.5 pass.
- [ ] From the VM, Forgejo is reachable and the NAS host isn't (section 3), also from a container inside `dind`.
- [ ] The VM's address isn't in the NAS's NFS exports.
- [ ] The runner shows as idle in the repo's runner list.
- [ ] There's no Docker socket in the runner or in jobs: `docker compose exec runner ls /var/run/docker.sock` fails.
- [ ] A test pull request runs CI and checks out the code.
- [ ] From the VM: `curl -i https://git.example.org/v2/` gives `401` from Forgejo. From a phone on mobile data, it redirects to Authelia.
- [ ] After `v0.1.0` is tagged, the image is under **Packages**, and the homelab can pull it by exact version.
- [ ] No automatic updater touches the Mealwright container (section 7).
- [ ] The status-check rule is on for `main`.
- [ ] On the home server, `findmnt -no OPTIONS /mnt/share` shows `nosuid` and `nodev` (and `noexec`, once section 9 is done).

## Appendix A: plain containers on the NAS (not chosen)

cabledrawer leaned towards this for 0.x, then chose the VM (17 Oct). Kept for comparison.

- Same compose file and config as section 4, run with the NAS's own Docker. `<runner-ip>` is `192.168.1.50`.
- A breakout from `dind` reaches the NAS host as root: a VPN client (with its credentials), download clients, a media server, all of `/mnt/pool`, and through NFS, files the home server reads at `/mnt/share`.
- If it were ever used, the conditions would be: the NFS mount keeps `nosuid,nodev`; jobs are never privileged and never mount host paths; and it's revisited before anyone else's code can run in CI.

## Appendix B: runner on the home server (not chosen)

This was the first version of this guide. cabledrawer put it on hold on 17 Oct, because a privileged `dind` would share the home server with the other apps. It's kept here for comparison.

- Same compose file as section 4.1, on the home server, plus `--insecure-registry=forgejo:3000` on `dockerd`. Forgejo's container joins the `ci` network as an external network, with the alias `forgejo`.
- Register with `--instance http://forgejo:3000`. Runner traffic never goes through Caddy.
- Workflows check out with `github-server-url: http://forgejo:3000`, because the default checkout URL follows `ROOT_URL` and would go through Authelia.
- Artifact upload also follows `ROOT_URL`. Avoid artifacts, or add `/api/actions_pipeline/` to a bypass for the `ci` subnet.
- Registry login at `forgejo:3000` is still sent to `ROOT_URL/v2/token` (`https://git.example.org/v2/token`). So the `/v2/` bypass in section 5 would need the `ci` subnet line (`172.29.250.0/24`) switched on.
- **Risk:** a breakout from `dind` reaches the home server host and everything on it.
