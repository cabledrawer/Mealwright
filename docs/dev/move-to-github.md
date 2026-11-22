# Moving to GitHub (steps for cabledrawer)

**Where things stand (cabledrawer 22 Nov).** The repo is public on GitHub (`github.com/cabledrawer/mealwright`) for a public trial of 0.9.5; development stays in a private repository that pushes `main` to GitHub. Issues and Discussions are open, outside pull requests wait for 1.0, and security reports use private vulnerability reporting. A 0.9.5 image goes to GHCR only, by the manual workflow `trial-image.yml`. Docker Hub, `release.yml` and the rest of this page's 1.0 steps are still to come.

**Done for the trial:** the public repo and the push from the private repo (sections 1 and 2 below). **To switch on for the trial (section 4):** private vulnerability reporting, before the repo is public or as soon as it is, because `SECURITY.md` gives it as the only way to report a problem; Discussions, because `CONTRIBUTING.md` points ideas there; the Actions settings (allowed actions, workflow permissions read-only, approval for all outside collaborators), because the repo is public and `check.yml` runs on pull requests; and the `v*` tag ruleset, so only you can make release tags.

**Running the trial image:** on GitHub, Actions, `trial-image`, Run workflow, tag `v0.9.5`. The first time, open the new package (your profile, Packages, mealwright, Package settings) and set its visibility to Public: a package made by a workflow is private until you do. Details in [build-and-release.md](build-and-release.md).

**Still for 1.0:** the Docker Hub name and secrets (section 3), the `release.yml` placeholders, branch protection on `main` and the required `check` and `image` status checks, the first release (section 5) and the CHANGELOG link footers.

Everything for the move is already in the repo; `release.yml` does nothing until a `v1.*` tag, and `trial-image.yml` does nothing until you run it by hand: `.github/workflows/check.yml`, `.github/workflows/release.yml`, `.github/workflows/trial-image.yml`, `.github/ISSUE_TEMPLATE/`, and `scripts/changelog-section.sh`. This page is the list of what only you can do. Replace `<owner>` with your GitHub name or organisation.

## How the workflows are kept off Forgejo now

Forgejo Actions reads `.github/workflows` when a repo has no `.forgejo/workflows` folder. Two things stop that:

1. `.forgejo/workflows/` exists (it holds only a note), so Forgejo looks there and finds nothing to run.
2. Every job in all the GitHub workflows starts with `if: github.server_url == 'https://github.com'`, so on any other server each job is skipped, even if the first point failed.

There is also no runner on your Forgejo, so nothing could queue. Belt and braces: in the Forgejo repo, Settings, Repository, leave "Enable Actions" off.

## Before you start

1. Finish the pre-release checklist (BUILD-PLAN, 0.9.5), including the trademark search.
2. Replace the placeholders. This lists them:
   ```
   grep -rn '<owner>' .github docs README.md
   ```
   In `.github/workflows/release.yml` set `GHCR_IMAGE` to `ghcr.io/<owner>/mealwright` and `DOCKERHUB_IMAGE` to `docker.io/<your Docker Hub name>/mealwright` (lower case). Until you do, a release cannot push anywhere.
3. The actions are already pinned. Each `uses:` line in `.github/workflows/check.yml` and `release.yml` names a full 40-character commit hash, with the version it came from in a comment (`uses: actions/checkout@<40 characters>  # v4.2.2`). To move one to a newer version: pick the newest release at least two weeks old, get its commit with `git ls-remote https://github.com/<owner>/<action> refs/tags/<tag> 'refs/tags/<tag>^{}'` (when a second line ending `^{}` appears, that line's hash is the commit; otherwise the one line is), replace the hash, and change the version in the comment. Never put a bare version tag back.
4. Prepare the cleaned history, as BUILD-PLAN 1.0.0 says.

## 1. Make the GitHub repo

On github.com: New repository, name `mealwright`, Public, with no README, licence or .gitignore (the repo has its own). Or with the GitHub CLI:

```
gh repo create <owner>/mealwright --public --description "Self-hosted meal planning, pantry and shopping"
```

## 2. Push to it, and keep it in step from Forgejo

First push by hand (this sends the cleaned history and tags):

```
git remote add github https://github.com/<owner>/mealwright.git
git push github main --tags
```

Then, so Forgejo keeps GitHub up to date: on Forgejo open the repo, Settings, Repository, Mirror settings, Add push mirror. Address `https://github.com/<owner>/mealwright.git`, username your GitHub name, password a GitHub fine-grained token limited to this repo with only "Contents: Read and write". Turn on "Sync when commits are pushed". Only you push to `main`; the `claude` account cannot.

**The mirror and workflow files (facts):**

- GitHub refuses a push that adds or changes a file under `.github/workflows/` when the token lacks the "Workflows" permission. With the Contents-only token above, a `main` that contains a workflow change (such as `trial-image.yml`) does not arrive through the mirror.
- A Forgejo push mirror sends every branch and every tag, so any branch pushed to the private repo (work in progress included) appears in the public repo.

**Proposed, for cabledrawer:** keep the mirror token Contents-only, and push a workflow change by hand from your own computer (`git push github main`); the mirror then carries on. Do not give the mirror token "Workflows": with it, a workflow file on any mirrored branch could run on GitHub with its own permissions and publish an image or a release, getting round trial-image.yml's guards.

**Proposed, for cabledrawer:** because the mirror sends every branch, limit it to `main` and `v*` tags if your Forgejo version offers a branch filter on the push mirror; if it does not, treat every branch pushed to the private repo as public.

## 3. Add the secrets

On GitHub: repo, Settings, Secrets and variables, Actions, New repository secret. Only two, both for Docker Hub:

| Name | Value |
| --- | --- |
| `DOCKERHUB_USERNAME` | your Docker Hub name |
| `DOCKERHUB_TOKEN` | a Docker Hub access token (Account settings, Personal access tokens) with "Read and write" on the `mealwright` repository only |

GHCR needs no secret: the release uses the run's own token. After the first release, open the package on GitHub (your profile, Packages, mealwright, Package settings) and set its visibility to Public.

## 4. Settings to switch on

- **Private vulnerability reporting:** repo, Settings, Code security, "Private vulnerability reporting", Enable. `SECURITY.md` already points people there.
- **Issue form:** nothing to switch on. `.github/ISSUE_TEMPLATE/bug.yml` is picked up by itself. It asks for no personal data and tells people never to paste secrets or unread logs. Replace `<owner>` in `.github/ISSUE_TEMPLATE/config.yml`.
- **Discussions:** repo, Settings, General, Features, tick Discussions. Add a category "Ideas" and one "Q&A".
- **Actions:** repo, Settings, Actions, General: allow GitHub's own and verified creators' actions only, set "Workflow permissions" to "Read repository contents", and leave "Allow GitHub Actions to create and approve pull requests" off. For pull requests from forks, choose "Require approval for all outside collaborators".
- **Branch protection on `main`:** repo, Settings, Branches, Add rule for `main`: require a pull request, require the status checks `check` and `image` to pass (they appear after the first run), block force pushes and deletion. If the Forgejo mirror pushes to `main`, add your account to the bypass list, or GitHub will refuse the mirror.
- **Tag protection:** Settings, Rules, Rulesets, a new tag ruleset for `v*`: only you may create them.

## 5. First release

1. Check `CHANGELOG.md` has a `## [1.0.0]` section (the release notes are cut from it; the workflow fails if it is missing or empty).
2. Tag and push:
   ```
   git tag v1.0.0
   git push github v1.0.0
   ```
3. Watch Actions, then check the image has both architectures:
   ```
   docker buildx imagetools inspect ghcr.io/<owner>/mealwright:1.0.0
   ```

Tags made: `1.0.0`, `1.0`, `1` and `latest`. A tag with a dash, like `v1.1.0-rc.1`, gets only its own exact tag, is marked pre-release on GitHub, and never takes `latest`.

Make a tag only on a commit whose `check` run is green: the release workflow does not run the checks again.

## What the workflows never do

No telemetry, and nothing about an installation is sent. `check.yml` runs `./check`, which downloads dependencies and vulnerability databases, as it does on your computer. The release only pushes the image and makes the release.

## At 1.0, also

Add the CHANGELOG link footers pointing at GitHub (BUILD-PLAN, 1.0.0).
