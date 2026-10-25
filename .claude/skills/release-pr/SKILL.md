---
name: release-pr
description: Make Mealwright's release PR at the end of a milestone (0.N.0) or for a patch (0.N.1) - version, CHANGELOG, security pass, full ./check with the scanners - then stop for cabledrawer to merge and tag. Use when the milestone's last feature PR has merged.
---

# The release PR

Only cabledrawer merges, tags (`v0.N.0`) and publishes. The lead never pushes `main`, makes a tag, builds or pushes an image for release, or publishes anything.

1. **Start from the new main**, after the milestone's last PR has merged: `git fetch origin && git checkout -b m0.N/release-0.N.0 origin/main`.
2. **Version:** `version = "0.N.0"` in `backend/pyproject.toml`. That's the only place it's written; `/api/v1/version` and the About screen read it. Then `uv lock --offline` in `backend/` updates the one version line in `backend/uv.lock`. Never open the lock file: check with `git diff --stat` that exactly one line of it changed. If the lock-file deny rule refuses the command, stop and ask cabledrawer (he ran the 0.5.0 one himself).
3. **CHANGELOG:** a new `## [0.N.0] - <date>` entry at the top. **Append only: never read `CHANGELOG.md` whole** (read the first entry with `sed -n` up to the previous heading). Write it for cabledrawer, in plain words: one opening line (what the milestone is; whether the database changes, and if so the backup steps from `docs/dev/test-on-homelab.md`), then **Added**, **Changed**, **Fixed**, **Security**, **Tests** as needed. Every claim must match code or a test. Feature PRs may already have added lines under the version: tidy them, don't duplicate.
4. **Security pass:** brief the `security-checker` helper with the `security-review` skill on `git diff v<previous>..HEAD` (the whole milestone, item 10 included). Fix what it finds (two rounds at most; an open high or security finding is a stop for cabledrawer). Write it to `<sync>/reviews/release-0.N.0-security-pass.md` (see CLAUDE.local.md: Where things are).
5. **Full `./check` on the final commit,** in the background, behind the lock (see the `pr-open` skill). A release PR always runs the scanners (`./check` sees the version change in `backend/pyproject.toml`; `CHECK_SCANNERS=1` forces them anyway). The result must be PASS on the PR's last commit.
6. **Open the PR** with the `pr-open` skill. In "What cabledrawer needs to check", add:
   - whether the database changes (and that the backup steps are in the CHANGELOG);
   - the hand test for the milestone, short and numbered, in plain words;
   - the commands for after he merges, each with what it does: tag it, then build the image from the tag and copy it to the server as in `docs/dev/test-on-homelab.md` (no registry in 0.x).
7. **Stop.** Update `docs/dev/progress.md` ("release PR open, waiting for cabledrawer to merge and tag"), and don't start the next milestone until cabledrawer says so.
