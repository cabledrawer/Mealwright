---
name: security-review
description: Mealwright's security pass, for a PR that touches sign-in, permissions, households, sync, imports, uploads or the outbound gate, and for every release PR. Use to brief the security-checker helper, or to do the pass yourself.
---

# Security pass

Run by the `security-checker` helper type (Opus, high effort), read-only, on a frozen worktree (`git worktree add --detach ../mw-pr<n>-sec <hash>`) with its own `E2E_APP_PORT` and `CHECK_IMAGE`. The brief follows the `checker-brief` skill, with this list in place of "Look hardest at". Name the PR's risky files and say which items below apply.

## What to attack

1. **Households.** Every query that reads or changes data filters by the signed-in member's `household_id`, including ids that arrive in bodies, queued offline changes, Undo records, cursors and photo paths. Try another household's ids on every new route and change type.
2. **Sign-in and sessions.** Routes that need a session refuse without one (401, not data). Signing out clears what the browser holds. Nothing from one login shows to another. The allowed signed-out routes (`/version`, `/setup`, `/session`, `openapi.json`) give nothing private: no usernames, no names (cabledrawer's name in a schema's docstring would leak through `openapi.json`).
3. **Permissions.** Admin-only actions check the role on the server, not only in the screen.
4. **Sync and the offline queue.** A replayed, reordered, duplicated or forged change can't touch another household, double-apply, or wedge the queue. Idempotency keys hold. Check against `docs/dev/sync-protocol.md` (the map at the top, then the clash rules).
5. **Input size and slow paths.** Long strings, deep nesting, huge numbers, many items: anything quadratic or unbounded (regexes, `Decimal`/`Fraction` parsing, JSON-LD, HTML). Measure with a scratch script: time and peak memory. Amount text is capped at 20 characters.
6. **Imports and the outbound gate.** Every outgoing request goes through `backend/src/mealwright/outbound.py` and is blocked unless its Privacy switch is on. No `httpx`, `requests`, `urllib` or sockets anywhere else (the no-telemetry test checks this; confirm new code didn't sidestep it). Redirects, DNS answers and "your own network" addresses (private ranges, `0x`/octal forms, IPv6-mapped) can't reach the home network unless listed. Size and time limits hold per hop. Recipe pages are read inside the work budget (`read_within_budget`).
7. **Uploads and photos.** Type is checked from the bytes, size is capped before decoding, decompression bombs and huge or odd colour profiles are refused, metadata (location!) is stripped, files land only under `/data` with server-made names. Photos are downloaded and kept locally, never hotlinked.
8. **Logs and errors.** Logs never hold a recipe page's address, a draft's text, passwords, tokens, household ids in paths, or exception text with user data. A 500 gives nothing away.
9. **Ethos.** No telemetry or analytics, no location access, no CDN or third-party asset at runtime, the CSP is unchanged and strict.
10. **Libraries** (a release, or a PR that changes a library or lock file): every new or changed version is on the licence allow list and at least two weeks old (or names the security warning it fixes, cabledrawer 20 Oct). The full `./check` runs the scanners in that case; read their output.

## Report

Under 25 lines: SAFE or NOT SAFE, then findings numbered with H/M/L, file:line, the attack (who, what input, what they get, measured), and the fix. Then what you tried that held, one line each.

The lead checks each finding, fixes every H and M with a test that fails without the fix, writes the pass into the PR body, and appends it to `<sync>/reviews/pr<N>-review.md` (see CLAUDE.local.md: Where things are) (for a release, `release-<version>-security-pass.md`). A high or security finding still open after round 2 is a stop: tell cabledrawer.
