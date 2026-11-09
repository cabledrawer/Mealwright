---
name: lead-rules
description: Working rules for the lead Claude Code session (monitoring, fix briefs, reviews, tests, checks, commits, handover). Read at the start of every lead session and before opening or fixing a PR.
---

# Lead rules (cabledrawer)

Each rule exists because something went wrong. They add to `CLAUDE.md` and to "How to use this plan" in `docs/BUILD-PLAN.md` (which has the check rules for a line of pull requests). If a session prompt from cabledrawer says otherwise, the prompt wins for that session.

## 1. Monitoring (save tokens, catch stalls)
- Act when a helper, test run or review finishes (background-task notices), plus a safety check every 30 minutes. Never just wait for a helper to report.
- No progress for 30 minutes (no new output, no new commit): take over, find out why, finish or restart the work, tell cabledrawer. Also stop any helper command that has produced no output for 30 minutes, even if the work looks finished.
- Never end your turn while work is left; wait inside your turn. If one item is blocked, start the next.
- Status line only when something changed, a PR is ready, or you need cabledrawer. No "still running" messages.

## 2. Fix briefs cover the whole problem
- Before a fix brief, list every place with the same problem yourself, not only the reviewer's lines. The builder reports every place it changed.
- Every PR has a "Sweep:" line: what was swept, how, how many places.

## 3. Every fix round is reviewed
- At least a quick Sonnet review of just the fixes. Opus for security, sync, offline, sign-in, import, database and stock (the outbound gate counts as security).
- **Review rounds in the Opus areas (cabledrawer 9 Nov):** Opus does round 1; round 2 (confirming the fixes) is Sonnet, unless round 1 found a High or a security issue. The release security pass is always Opus. At most two review rounds; after that only High or security findings are fixed, the rest go on the follow-up list.
- Then the full check. A passing check is not a review.
- Your own code changes get a checker review before cabledrawer merges, never a self-review.
- Docs-only pull requests with wording cabledrawer agreed need no reviewer and no `./check`.

## 4. Reviewers run tests
- A helper blocked by a rule or a failing command stops and says so. Never accept a review that couldn't run its tests.

## 5. No surprises in the full check
- When behaviour changes, update old tests that expect the old behaviour before the final check.
- Run every related test file (computer, phone, Safari's engine) before the full check.
- No fixed short waits in tests; wait for the thing to happen. Never make a flaky test pass by weakening it.
- Page size limit 144 KiB: check pages again after joining branches; load rarely-opened parts on first use rather than raising the limit.

## 6. Facts before questions
- Check the code before telling cabledrawer how the app behaves; cite the file or spec line in every question.
- Decisions you take while he's away: mark "proposed, for cabledrawer", pick the safest option, carry on, list them in the summary.

## 7. Nothing lost, nothing stuck
- Builders commit work in progress at least every 30 minutes and before any long test run.
- Nothing may wait for typing: helpers run git with `GIT_EDITOR=true` and `--no-edit`, never interactive commands.
- **The state file (cabledrawer 9 Nov):** cabledrawer's session prompt names a live state file and a log beside it. The live file holds only what is true now (main, the current line with each PR's tip, review and check state, open questions for cabledrawer, next step): rewrite it, don't append, and keep it under 3 KB. Handovers, cabledrawer's answers and flaky tests go at the end of the log, newest last. Update both after every step.
- **Briefs (cabledrawer 9 Nov):** read the brief and its files from the path the session prompt gives; don't copy them into the repo or elsewhere.

## 8. Scanners first
- Before a series of full runs, run the scanners once; a new warning goes to cabledrawer first.

## 9. Screens before merge (cabledrawer 9 Nov)
- For every PR that changes a screen, save screenshots of each changed screen at 428, 768, 1100 and 1300 px wide, dark theme only, in the screenshots folder the session prompt names (one folder per PR, files named `<screen>-<width>.png`). List them in the PR description. cabledrawer's helper compares them with the mockups before he merges.

## 10. Hand over in time
- At the wind-up time cabledrawer gives, when the session compacts, or after about 8 merged PRs: write the handover at the end of the state log and rewrite the live state file, commit everything, make sure no helper runs, tell cabledrawer "ready for a new session".

## cabledrawer's standing rules
- One full `./check` at a time, nothing beside it. At most three helpers, at most two building.
- No sudo, no new libraries, no merging, no tags. cabledrawer merges (Rebase then fast-forward) and tags.
- A PR that must move onto a new main gets a new branch and PR; say which old PR to close.
- Commits: author cabledrawer, `-s`, trailer "Assisted-by: Claude Code" only (no Co-Authored-By). No personal details (home domain, IP addresses, machine names, home paths) in new commits or files.
- Every decision goes into the spec, credited to cabledrawer. Ethos: no telemetry, no location, no phoning home, no CDNs; outbound off until the user turns it on.
- Tell cabledrawer when a PR is ready: number, branch, what it does, check result, the review's last verdict, the sweep line.
