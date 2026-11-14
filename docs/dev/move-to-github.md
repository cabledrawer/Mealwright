# Moving to GitHub at 1.0 (steps for cabledrawer)

Everything for the move is already in the repo and does nothing until then: `.github/workflows/check.yml`, `.github/workflows/release.yml`, `.github/ISSUE_TEMPLATE/`, and `scripts/changelog-section.sh`. This page is the list of what only you can do. Replace `<owner>` with your GitHub name or organisation.

## How the workflows are kept off Forgejo now

Forgejo Actions reads `.github/workflows` when a repo has no `.forgejo/workflows` folder. Two things stop that:

1. `.forgejo/workflows/` exists (it holds only a note), so Forgejo looks there and finds nothing to run.
2. Every job in both GitHub workflows starts with `if: github.server_url == 'https://github.com'`, so on any other server each job is skipped, even if the first point failed.

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
