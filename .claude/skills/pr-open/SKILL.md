---
name: pr-open
description: Run the full ./check, push a branch and open (or update) its pull request on cabledrawer's Forgejo with the body Mealwright needs. Use when a PR's work and review are done.
---

# Open a pull request

## 1. The full ./check on the final commit

- `git status --short` is clean (nothing uncommitted that the check would miss), and `df -h /tmp` shows at least 1.5 GB free (else wait). If Docker isn't running, write it in `docs/dev/progress.md` and wait.
- Run it in the background, behind the shared lock, with your own port and image:

  ```sh
  flock <scratchpad>/full-check.lock env E2E_APP_PORT=<port> CHECK_IMAGE=mealwright:check-<name> ./check > <scratchpad>/check-<hash>.log 2>&1
  ```

  It takes about 35 minutes. Never chain it with `git push` or `tea` in one command: read the result first. Any timeout is a failure.
- It prints a short summary and the failures. The table to paste is in `.check/summary.md`; every step's full log is in `.check/logs/`.
- On a failure: read the printed lines, fix with a test, commit, and run the full check again. The pasted summary must say **PASS** on the PR's **last commit** (same hash).

## 2. Push and open

- `git push -u origin <branch>` (HTTPS; `--force-with-lease` only on your own branch after a rebase). Never push `main`.
- New PR: `tea pr create --base main --head <branch> --title "<title>" --description "$(cat <scratchpad>/<body>.md)"`. Update: `tea pr edit <N> --description "$(cat <body>.md)"`. Use `tea`, never `gh`.

## 3. The body, in this order

1. `## What cabledrawer needs to check`, in plain English for someone who isn't a developer: new libraries and their licences; anything about privacy or outside connections; any change from the plan or spec; readings you made where the spec was silent ("say if you'd rather have it another way"); a short numbered hand test if the PR changes screens. If none: "Nothing needs a decision."
2. cabledrawer's decisions for this PR, word for word, if any.
3. `## Review`: the level (light or full, and why), the range reviewed, each finding (number, H/M/L, security yes/no, what was done: **Fixed** in `<hash>`, or left and why), and what was checked and fine.
4. `## Summary`: what's in the PR, commit by commit or as a short table.
5. The `./check` summary from `.check/summary.md` (with its commit hash).
6. `AI help: written with Claude Code (<models and roles>). cabledrawer is the author and signs off every commit.`
7. Last line: `🤖 Generated with [Claude Code](https://claude.com/claude-code)`

## 4. After it's open

- Append the review to `<sync>/reviews/pr<N>-review.md` (see CLAUDE.local.md: Where things are) (never overwrite).
- Update `docs/dev/progress.md`: PR number, branch, last commit, check result, what's waiting for cabledrawer.
- cabledrawer merges one PR at a time (rebase, then fast-forward). Keep working on the next piece unless you need a decision, or it's the end of a milestone. After each merge, the next PR gets a fresh full `./check` on the new main.
