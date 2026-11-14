# Build, check and release

How to build Mealwright, run its checks, and make a release, without asking anyone. Replace anything in `<angle brackets>` with your own value. Where the code and this page disagree, the code wins: fix this page. How the parts fit together is in [architecture.md](architecture.md).

## What you need

Linux (WSL on Windows works), Git, Docker, Python 3.14 with [uv](https://docs.astral.sh/uv/), and Node 24 with npm. These are the versions the `Dockerfile` and `backend/pyproject.toml` use. TODO(cabledrawer): a list of the exact tool versions on the development machine, if you want one here.

## Build and run on your computer

Install the libraries from the lock files (never edit the lock files by hand):

```bash
cd backend && uv sync --frozen        # Python libraries into backend/.venv
cd ../frontend && npm ci              # web app libraries
```

Build the web app, then start the server with a scratch data folder:

```bash
cd frontend && npm run build                        # writes frontend/build
cd ../backend && MEALWRIGHT_DATA_DIR=<scratch folder> MEALWRIGHT_FRONTEND_DIR=../frontend/build \
  MEALWRIGHT_ALLOW_PLAIN_HTTP=true uv run python -m mealwright
```

It listens on port 8080 (`MEALWRIGHT_PORT`). The first start prints a one-time setup code in its output; the first-admin form needs it. Plain http is for trying it out on your own machine only ([environment.md](../environment.md)). TODO(cabledrawer): does `npm run dev` (port 5173) talk to a running backend? `frontend/vite.config.ts` has no proxy, so this page only describes the build above.

Build the image the way a release does (see "Getting a 0.x image to a server" below). A plain `docker build -t mealwright:test .` also works; the version labels then say "unknown". The Dockerfile has three stages (web app, Python environment, the small image that runs); base images are pinned by digest.

## `./check`

`./check` at the repo root replaces CI during 0.x. Run it before every pull request. It prints only failures and a short summary. Its header comment is the full manual (`sed -n 1,100p check`).

| Where | What |
| --- | --- |
| `.check/summary.md` | The table you paste into the pull request |
| `.check/check.log` | The whole run |
| `.check/logs/<step>.log` | Each step's own output |

What the full run does (step names from the script):

1. Installs the libraries and builds the web app.
2. Backend: `ruff format`, `ruff check`, `mypy`, the pytest suite, the licence allow list (`backend/scripts/check_licences.py`), the no-telemetry test (`backend/scripts/check_no_telemetry.py`).
3. Web app: svelte-check, ESLint and Prettier, Vitest unit tests, the build, the size limit, the fonts (only latin and latin-ext files in the build), the licence check, and `THIRD-PARTY-NOTICES.md` being up to date. After a library changes, run the web build, then `cd backend && uv run --frozen python -I scripts/third_party_notices.py` to write the file again.
4. Browser tests (Playwright, three streams side by side: desktop, phone, WebKit), plus the e2e type check and the scripts' own tests.
5. Scanners (pip-audit, Bandit, osv-scanner, then Trivy on the image), only when the branch changes a library, a lock file, the Dockerfile, the scanner settings or `./check` itself, and always on a release PR. `CHECK_SCANNERS=1` forces them.
6. The Docker image: build it, check it holds no telemetry and no component gallery, save it for Trivy.

Modes and settings (all in the header comment):

| Command | What it does |
| --- | --- |
| `./check` | The full run. About 35 minutes. The only run that counts for a pull request. |
| `./check --fast` | Lint, types, only the backend tests your changes can touch, frontend unit tests, the outbound-gate test, licences. Skips images, scanners and browser tests. Prints the `--browser-files` command for the browser specs your change touches. Not valid for a PR. |
| `./check --fast --all` | The same, with all backend tests. |
| `./check --browser-files <spec> ...` | Only those browser spec files (`e2e/tests/<name>.spec.ts`; the name is enough), on all three streams. `--update-snapshots` saves new screenshots. |
| `./check --rerun-failed` | Runs again only the browser tests that failed in this copy's last full run. |
| `./check --scan-only` | The scanners and Trivy on a fresh image, no tests. Good for a weekly run. |

Useful settings, set before the command (the full list is in the header):

- `CHECK_SCANNERS=1`: run the scanners anyway.
- `CHECK_IMAGE=<tag>` and `E2E_APP_PORT=<port>`: the image tag (default `mealwright:check`) and the first test-server port (default 18080). A second copy of the repo needs its own of each.
- `CHECK_LOCK_WAIT=0`: refuse instead of waiting when another check holds the lock.
- `CHECK_STOP_EARLY=0`: run the browser tests even after an earlier step failed. The summary then says NOT valid for a pull request.

Rules for running it:

- Only one check runs on a machine at a time: `./check` takes a machine-wide lock itself. Do not wrap it in `flock` (it exits with 75).
- Do not run it in the copy of the repo where you are still editing. Use a frozen copy of the commit. Do not switch branches in the folder while it runs.
- Do not run browser tests at the same time as a full check.
- It needs Docker and free disk space (about 1.5 GB in the temp folder).
- Never chain `./check` and a `git push` in one command: read the result first. The summary pasted into the PR must say PASS on the PR's last commit.
- A new backend test file or browser spec must be added to `e2e/test-map.json`. From `e2e/`, `node scripts/test-map.mjs validate` tells you if one is missing.

## Branches and pull requests

- One branch per feature, named like `m0.9.5/dev-docs`. One pull request per feature; small commits inside it, each building and passing.
- During 0.x the code is on cabledrawer's private Forgejo. Use Git over HTTPS and the `tea` command-line tool (not `gh`). Contributors push branches; only the owner pushes `main` or makes `v*` tags.
- Every commit is signed off (DCO) and notes AI help:

  ```bash
  git commit -s --trailer "Assisted-by: <tool name>"   # -s adds the Signed-off-by line
  git push -u origin <branch>                          # publishes your branch (never main)
  tea pr create --base main --head <branch> --title "<title>" --description "$(cat <body file>)"
  ```

- The PR description starts with "What cabledrawer needs to check" (new libraries and licences, anything touching privacy or outbound connections, any change from the plan or spec; or "Nothing needs a decision."), then the `./check` summary. See `.claude/skills/pr-open/SKILL.md` and [CONTRIBUTING.md](../../CONTRIBUTING.md).
- The owner merges, usually in batches, one at a time (rebase, then fast-forward).
- A new library needs the owner's OK first, a licence on the allow list (CLAUDE.md), and a version released at least two weeks earlier.

## Versions and the CHANGELOG

- **While building (0.x):** one `0.N.0` per milestone. Test builds before it are tagged `v0.N.0-alpha.M` and `v0.N.0-beta.M` (see the headings in `CHANGELOG.md`). Every 0.x tag is a pre-release.
- **From 1.0.0:** plain MAJOR.MINOR.PATCH ([spec.md](../spec.md) section 8). 1.0.0 to 2.0.0 is major new functionality; 1.0.0 to 1.1.0 is a smaller feature upgrade; 1.0.0 to 1.0.1 is security fixes and tiny updates. Anything that makes a person act before updating (a manual database step, a removed or renamed setting) goes to the next major version, with the steps in the release notes. 1.x versions upgrade in place with no manual steps. After 1.0, new features come in minor releases about once a month at most; security fixes go out whenever needed.
- **Where the version lives:** `version = "..."` in `backend/pyproject.toml`, only there. `/api/v1/version`, the About screen and the sidebar read it (the web app gets it at build time through `frontend/vite.config.ts`). `backend/uv.lock` also carries one version line for the project; `uv lock --offline` in `backend/` updates it.
- **Pre-release spelling:** the CHANGELOG and tags say `0.9.0-beta.1`; `backend/pyproject.toml` uses Python's own form, `0.9.0b1` (as in the v0.9.0-beta.1 release; `0.8.0a1` for an alpha).
- **CHANGELOG.md** is "Keep a Changelog" style, newest first, appended to and never rewritten whole. Each version has a `## [x.y.z] - <date>` heading and an opening plain-English line (what the release is, and whether the database changes, with the backup steps). Then **Added**, **Changed**, **Fixed**, **Security**, **Tests** as needed. Every line must match the code or a test. Feature PRs may add lines under the coming version; the release PR tidies them. `scripts/changelog-section.sh <version>` prints one version's section (the GitHub release notes use it).

## The release PR

Only the owner merges, tags and publishes. Steps, from `.claude/skills/release-pr/SKILL.md`:

1. Start from the new `main` after the last feature PR has merged:

   ```bash
   git fetch origin && git checkout -b m0.N/release-0.N.0 origin/main   # a new branch from main
   ```

2. Set the version in `backend/pyproject.toml`, then run `uv lock --offline` in `backend/`. Check with `git diff --stat` that exactly one line of `backend/uv.lock` changed. Do not open the lock file.
3. Add the CHANGELOG entry (above).
4. Do a security pass on everything since the last release (`git diff v<previous>..HEAD`), using `.claude/skills/security-review/SKILL.md`. Fix what it finds. An open high or security finding stops the release.
5. Run the full `./check` on the final commit. A release PR always runs the scanners (it changes the version in `backend/pyproject.toml`). It must say PASS on the PR's last commit.
6. Open the PR. In "What cabledrawer needs to check", say whether the database changes (and that the backup steps are in the CHANGELOG), give a short numbered hand test, and list the commands for after the merge.
7. Stop. The owner merges, then makes the tag (`git tag v<version>` on the merged commit). Nobody else tags or publishes.

## Getting a 0.x image to a server

There is no registry and no CI runner in 0.x. The image is built on a computer you control, from the tag, saved to a file and copied to the server. Full steps, including backing up `/data` first and going back to the previous version, are in [test-on-homelab.md](test-on-homelab.md). In short:

```bash
git fetch --tags                                       # get the tag
git archive v<version> | docker build -t mealwright:<version> \
  --build-arg VERSION=<version> \
  --build-arg CREATED="$(date -u +%Y-%m-%dT%H:%M:%SZ)" \
  --build-arg REVISION="$(git rev-parse v<version>^{commit})" -   # builds from exactly the tag's files
docker save mealwright:<version> | gzip > mealwright-<version>.tar.gz   # the image as one file
scp mealwright-<version>.tar.gz <user>@<server>:<folder>/               # copy it to the server
```

On the server: stop Mealwright, copy `data/` aside, `docker load` the file, point `compose.yaml` at the new version, start it. Updates run database migrations on start, after a safety copy; an older version cannot read a newer database, so the backup is what lets you go back ([upgrade.md](../upgrade.md), [restore.md](../restore.md)). Never push an image to any registry in 0.x.

## Releasing 1.x (after the move to GitHub)

At 1.0 the code moves to GitHub, and the work already in the repo starts running: `.github/workflows/check.yml` runs `./check` on every pull request and push to `main`, and `.github/workflows/release.yml` builds and publishes the image when a tag `v1.*` is pushed. The steps for the move (making the repo, secrets, settings, protecting `main` and the `v*` tags) are in [move-to-github.md](move-to-github.md). The release then goes like this:

1. Make the release PR as above. `CHANGELOG.md` must have a `## [1.x.y]` section: the release notes are cut from it, and the workflow fails if it is missing or empty.
2. After the owner merges it (on a commit whose `check` run is green; the release workflow does not run the checks again):

   ```bash
   git tag v1.2.3                  # the tag names the release
   git push github v1.2.3          # the push starts the release workflow
   ```

3. The workflow builds amd64 and arm64 and pushes `ghcr.io/<owner>/mealwright` and `docker.io/<owner>/mealwright` with the tags `1.2.3`, `1.2`, `1` and `latest`. A tag with a dash (`v1.3.0-rc.1`) gets only its exact tag, is marked pre-release and never takes `latest`.
4. Check both architectures are in the image:

   ```bash
   docker buildx imagetools inspect ghcr.io/<owner>/mealwright:1.2.3   # lists the platforms
   ```

The workflows send nothing about an installation anywhere. The actions in both workflows are pinned to full commit hashes; [move-to-github.md](move-to-github.md) section "Before you start" says how to move a pin.

## If something is missing here

Add it to this page in the same PR that makes it true. Related: [architecture.md](architecture.md), [browser-tests.md](browser-tests.md), [forgejo-runner.md](forgejo-runner.md) (on hold).
