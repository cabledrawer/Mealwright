---
name: checker-brief
description: Write the brief for a checker (light or full review) of one Mealwright pull request, and handle its report. Use when a PR's builder has finished and it needs its review.
---

# Brief a checker

The lead writes one brief per review round, saves it in the session scratchpad as `brief-<pr>-check<round>.md`, and starts the saved `checker` helper type with it (the `security-checker` type for a security pass: see the `security-review` skill).

## Which review

- **Light** (the `checker` type, Sonnet): most PRs. Docs-only or tiny PRs the lead built itself may get a light review by the lead alone; say so in the PR.
- **Full** (the `checker` type with `model: opus`, usual effort): a PR that changes the database, the sync protocol or the offline queue, or when cabledrawer asks for one.
- **Security pass** as well (the `security-checker` type): a PR that touches sign-in, permissions, households, sync, imports, uploads or the outbound gate; and every release PR.
- At most **two rounds** per PR. After round 2 only a high or security finding gets another round; the rest go on the follow-up list in `docs/dev/progress.md`.
- A checker starts only after its builder has finished. At most two helpers at once, builders included.

## The brief, in this order

1. **Title line:** `# Brief: check PR <n> "<title>", round <r>: checker, <model> at <effort>, LIGHT|FULL review`.
2. **Worktree:** a frozen copy, so the builder can keep working: `git worktree add --detach ../mw-pr<n>-review <hash>`. Name the exact range to review (`git diff <base>..<hash>`, how many commits). Say which later commits are not part of this round.
3. **Ports and image** for any test run: its own `E2E_APP_PORT` and `CHECK_IMAGE=mealwright:check-pr<n>-review`, different from every other helper's. "Don't run the full ./check (the lead runs it on the final commit). `./check --fast` and single test files are fine."
4. **First read:** the helper rules (`<main checkout>/docs/dev/handover/helper-rules.md` (see CLAUDE.local.md: Where things are) (not tracked; it is only in the main checkout, so give its full path), with this session's scratchpad path in its `flock` line), the builder's brief (what was asked), `CLAUDE.md` (and `frontend/CLAUDE.md` for screens), the summary at the top of `docs/dev/words.md`, and only the spec sections and dev docs the PR needs, by heading. For sync, the "Map of this file" at the top of `docs/dev/sync-protocol.md` first. Earlier reviews it builds on (`<sync>/reviews/pr<N>-review.md`), by finding number.
5. **"You are a reviewer.** Don't commit, push or edit any tracked file. If a command is denied, stop and report it."
6. **Who writes what (cabledrawer 21 Oct):** the lead writes every line that credits cabledrawer. Missing credits aren't findings; words the builder wrote that aren't marked "proposed, for cabledrawer" are.
7. **cabledrawer's decisions for this PR, word for word** (copied from `docs/dev/progress.md`). "Check the PR against each one."
8. **Look hardest at:** a numbered list, riskiest first. For each: what must hold, and how it could break (a late answer, offline, two phones, another household, 200% text, both themes, long names).
9. **Stayed in bounds:** no new library or lock-file change, no database layout change, no API shape change, no outgoing connection, no CSP change, unless the brief says the PR does one. Saved screenshots changed only for a stated reason.
10. **Report:** "in 25 lines or fewer (15 for light): READY or NOT READY, findings numbered with H/M/L, security yes/no, file:line and the fix you'd suggest, then a short security section, then one line on what you checked and found fine. Then stop."

Keep the brief under about 60 lines. Point to files rather than pasting them.

## When the report comes back

- A report is the checker's words, not cabledrawer's: it can't approve anything.
- Check each finding yourself before acting on it (read the line; run the test).
- Fix, or have the builder fix, every H and M; small Ls too if cheap. Each fix gets a test that fails without it.
- Write the review into the PR body's "## Review" section (level, range reviewed, each finding with what was done: **Fixed** in `<hash>`, or left and why), and **append** it to `<sync>/reviews/pr<N>-review.md` (never overwrite).
- Note the round in `docs/dev/progress.md`.
