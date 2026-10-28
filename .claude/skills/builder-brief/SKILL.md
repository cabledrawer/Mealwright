---
name: builder-brief
description: Write the brief for a builder of one Mealwright pull request, from its row in the milestone's PR plan, including exporting its mockups. Use when a PR is about to start and a builder will build it.
---

# Brief a builder

The lead writes one brief per builder, saves it in the session scratchpad as `brief-<branch-short>.md`, and starts the saved `builder` helper type with it (`model: opus` only where the milestone plan says so). The builder's own rules are in `.claude/agents/builder.md` and `<main checkout>/docs/dev/handover/helper-rules.md` (see CLAUDE.local.md: Where things are) (not tracked; it is only in the main checkout, so give its full path); the brief adds what is special to this PR.

## Before writing it

- At most two builders at once; a PR runs beside another only if the milestone plan says they don't overlap.
- Make the worktree from the right base: `git worktree add -b <branch> ../mw-<short> <base>` (`origin/main`, or the branch it stacks on). Check that no other helper's worktree uses that branch.
- **Mockups:** copy the screens this PR builds from `<sync>/mockups-<milestone>/` into the worktree's `docs/mockups/`, unchanged (same file names, light and dark, phone and desktop where drawn). `canvas.json` is not changed. Commit them first, on their own: `Mockups: <Screen> (<which versions>), unchanged`. Never edit the design canvas artifact.

## The brief, in this order

1. **Title line:** `# Brief: build PR <letter> "<title>" (<branch>): builder, <model>`.
2. **Worktree and base:** the path, the branch, the base commit, and "run `pwd` first; work only here".
3. **Ports and image:** its own `E2E_APP_PORT` and `CHECK_IMAGE=mealwright:check-<short>`, different from every other helper's.
4. **First read:** `<main checkout>/docs/dev/handover/helper-rules.md` (not tracked; it is only in the main checkout, so give its full path) (with this session's scratchpad path in its `flock` line), `CLAUDE.md` (and `frontend/CLAUDE.md` for screens), the summary at the top of `docs/dev/words.md`, and only the spec sections the PR needs, by heading. The mockups by file name.
5. **cabledrawer's decisions for this PR, word for word** (copied from `docs/dev/progress.md`), and the F-numbers it fixes (each fixed with the `hand-test-fix` steps).
6. **What to build:** a numbered list, in commit order. For each: what must be true when it's done, and the test that shows it.
7. **Stays in bounds:** no new library or lock-file change; no database change unless the brief says so (then an Alembic migration with upgrade and downgrade tests); no API shape change unless the brief says so; no outgoing connection; no CSP change. Anything the spec doesn't cover: stop and ask the lead.
8. **Working rules (cabledrawer, 0.6 lessons):** one command per tool call; never look in `node_modules` or `.svelte-kit`; stop only the test servers and runs it started, by their own PID; run the formatter after editing a script; a failing test means find the cause, never just rerun it.
9. **./check:** single test files and `./check --fast` while working. The full `./check` is the lead's, in a frozen copy, behind the lock; the builder doesn't run it.
10. **Report:** "in 10 lines or fewer: branch, last commit, what's done, tests added, `./check --fast` result on which commit, open questions. Then stop."

Keep the brief under about 60 lines. Point to files rather than pasting them.
