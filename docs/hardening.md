# Hardening: who can read your data, and how the container is locked down

## The data folder is private (0.9)

Everything Mealwright keeps is in `/data` (the folder you mount). Each time it starts,
Mealwright sets every file in it to mode 0600 and every folder to 0700, so only the user it
runs as (`mealwright`, UID 10001) can read or write them: the database `mealwright.db` and
its `-wal` and `-shm` files, `backups/`, `photos/` and `logs/`. Files made by an older
version with wider permissions are fixed on the first start. New files get the same mode
because the server sets a private umask (077) before it makes anything.

The folder you mount must belong to UID 10001 (see `compose.example.yaml`). If it doesn't,
Mealwright can't change the modes, logs one warning and carries on.

### How a backup tool on the host reads `/data`

Because the files are private to UID 10001, other host users can't read them. Pick one:

- **Run the backup tool as root** on the host (the usual way: a root cron job, restic or
  borg run by root). Root reads the files whatever their mode.
- **Run it as UID 10001** (a host user or `docker run --user 10001:10001`) if you don't
  want root involved.
- Or **use Mealwright's own backups** (Settings › Backups & your data), which are written into
  `/data/backups` and copied out the same way.

Don't loosen the modes to make a backup tool work: the next start sets them back.

## The compose example is locked down (0.9)

`compose.example.yaml` gives the container only what it needs:

| Setting | What it does |
| --- | --- |
| `security_opt: no-new-privileges:true` | Nothing in the container can gain more rights than it started with. |
| `cap_drop: [ALL]` | Drops every Linux capability. Mealwright needs none: it serves on port 8080 as an ordinary user. Nothing had to be added back. |
| `read_only: true` + `tmpfs: /tmp` | The container's own files can't be changed. Only `/data` (your folder) and a small in-memory `/tmp` are writable. |
| `init: true` | A tiny first process that forwards stop signals and clears finished child processes. |
| `mem_limit: 512m` | A runaway can't take all the server's memory. Raise it for a very big library. |
| `# user:` (commented) | Use it only when the data folder can't belong to UID 10001. Set `user:` to the folder's owner; the folder and the user must match. |

Tested on the 0.9 image: with exactly these settings (and a plain-http test setting on a
loopback port) the container starts, reports healthy, answers `/api/v1/health`, creates the
first account (a database write) and keeps `/data` at 0700/0600.

## The image: labels, layer order, a locked build (0.9)

- **Labels** (OCI): title, description, licence (`AGPL-3.0-only`, as in `pyproject.toml`),
  source (a placeholder until the public repository exists), and version, created and
  revision from the build arguments `VERSION`, `CREATED` and `REVISION`. See
  `docs/dev/test-on-homelab.md` for the command. Nothing personal goes in them.
- **Layer order:** the web app's libraries and the backend's libraries are installed from
  their package and lock files alone, before the app's own code is copied in, so a code
  change doesn't install them all again. The labels come last, so a new version number
  doesn't either.
- **Locked build:** the backend is installed with `uv sync --locked`, so a `uv.lock` that
  doesn't match `pyproject.toml` stops the build.

## SBOM and provenance (release build only)

An SBOM (a list of everything inside the image) and a provenance record (how and from
which commit it was built) are attached by BuildKit while the image is built. They are not
made by `./check` and are not in the ordinary `docker build` used for the homelab test.

The release build, from a tag, on your own computer. It writes an OCI file; nothing is
pushed anywhere:

```bash
docker buildx create --name mealwright-release --driver docker-container   # once
git archive v<version> | docker buildx build --builder mealwright-release \
  --sbom=true --provenance=mode=max \
  --build-arg VERSION=<version> \
  --build-arg CREATED="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --build-arg REVISION="$(git rev-parse v<version>^{commit})" \
  --output type=oci,dest=mealwright-<version>.oci.tar -
```

Two things to know first. The ordinary `docker` build driver can't attach these records;
the `docker-container` driver above can. And the SBOM step makes BuildKit pull its own
scanner image (`docker/buildkit-syft-scanner`) from Docker Hub, which is an image
Mealwright's checks don't use today. That is cabledrawer's call: this repository doesn't add it.
