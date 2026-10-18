# Reviewing a pull request

The checklist the checker applies to every PR before it reaches cabledrawer. A PR passes
only when every box is ticked or the gap is written up in the review with a reason.
This is the 0.3 version (cabledrawer 17 Oct).

## How a review runs (cabledrawer 17 Oct, from 0.3)

- **One full review per PR.** After the builder's fixes, review only what changed.
- **Screenshots:** early rounds take phone-light and desktop-dark only. All four
  (phone and desktop, light and dark) are taken only in the final review.
- **Don't re-run `./check`** if the PR description has a pasted summary whose commit
  matches the PR's latest commit, it says PASS, and it was a full run (not `--fast`).
  Otherwise ask for a full run.
- **Run only** `review/screens.ts` and that feature's browser tests, not the whole suite.
- **Model:** Opus at high effort reviews the sync PRs (1, 3 and 6); Sonnet reviews the rest.
- Anything about live updates or offline behaviour is checked with **two browser
  contexts** (two devices), never one page.

## Tools

```sh
cd e2e
npm ci && npx playwright install chromium-headless-shell

# That feature's browser tests only (the whole suite is part of the full ./check)
E2E_APP_PORT=18300 npx playwright test tests/<feature>.spec.ts

# Screenshots: the app beside its mockup, phone 390×844 and desktop 1440×900,
# light and dark. Writes e2e/review-shots/<name>/ (git-ignored). Not part of ./check.
# Early rounds: phone-light and desktop-dark only. Final review: all four.
E2E_APP_PORT=18300 node review/screens.ts --screen Shopping --path /shopping --serve
node review/screens.ts --screen Shopping               # mockups only
# --prepare file.ts: seed(api) adds test data; prepare(page, shot) clicks things open
# --stress: after the normal shots, adds 200+ items and very long names (the --prepare
#   module's stress(api)) and takes stress-<size>-<theme>.png with the text at 200%
E2E_APP_PORT=18300 node review/screens.ts --path /shopping --serve --prepare review/seed-shots.ts --stress
# The component gallery (development only, not in the built app): starts the Vite dev server
node review/screens.ts --gallery
```

`tests/a11y.ts` has `checkPage(page)`: axe with the WCAG 2.0/2.1/2.2 A and AA rules in
light and dark, and on the phone project 44 × 44 px touch targets and no sideways
scroll. New pages go into `tests/a11y.spec.ts`; new states (a sheet open, a toast
showing) get their own `checkPage` call in the feature's tests.

## Checklist

**Keeping the UI good (from 0.4)**
- [ ] On-screen text matches `docs/dev/words.md`.
- [ ] Every state of a new screen is covered (spec "Keeping the UI good", item 2), including the stress shot.
- [ ] Any new component or kind of component is in `/dev/gallery`.
- [ ] Saved screenshots changed only where the pull request says it meant to.
- [ ] Reduced motion respected; keyboard-only path works with a visible focus ring.

**Spec**
- [ ] Matches `docs/spec.md` and the spec sections the PR's milestone names (for sync
      PRs, section 6 "Offline shopping-list sync" and `docs/dev/sync-protocol.md`),
      including every "Decided ... (cabledrawer 17 Oct)" block. Where code and spec disagree,
      the spec wins.
- [ ] Parts that depend on later milestones are hidden, not stubbed: list generation
      and the staples check card (0.6); tubs (0.6); "Used in N recipes", "Not in any
      recipe", "Recipes for these" (0.4).
- [ ] Anything the spec doesn't cover is listed under "What cabledrawer needs to check".
- [ ] Every new table has `household_id`; every schema change is an Alembic migration.
- [ ] The web app uses only public `/api/v1` endpoints, and they're in the OpenAPI.

**Ethos**
- [ ] No outgoing network calls outside the outbound gate (`grep -rnE "httpx|requests|urllib|socket|aiohttp|fetch\(" backend/src`; the socket-blocking test still runs).
- [ ] No CDN, Google Fonts or other outside asset; the CSP is unchanged or stricter.
      `review/screens.ts` prints any request to an outside address.
- [ ] No telemetry, analytics, crash reporting, location access.
- [ ] New dependencies: named in the PR, licence on the allow list, versions pinned and
      at least two weeks old, cabledrawer asked first.

**UX**
- [ ] Plain words: "cupboard", "use soon", "packets", "waiting changes"; never "items",
      "units", "lots", "entities", "quantity", "SKU", "location", "sync", "queue", "conflict". Wording matches the mockup unless the
      spec says otherwise.
- [ ] Undo, not "Are you sure?": no confirm dialogs. Every change shows an Undo toast;
      Ctrl+Z on desktop undoes your own last change.
- [ ] Optimistic updates: the screen changes before the server answers, and rolls back
      with a calm message if it fails (test with the request held or failing).
- [ ] One switch component (`Switch.svelte`) for every on/off; no checkboxes.
- [ ] WCAG AA contrast in light and dark (`checkPage`), dark is the designed theme from
      the mockups, not inverted.
- [ ] Touch targets ≥ 44 px on phone (`checkPage`).
- [ ] Vertical scrolling only: nothing scrolls sideways at 390 px (`checkPage`), not even
      with long food names, many places or many packets.
- [ ] Keyboard: every action reachable with Tab, visible focus, Enter/Space work, Escape
      closes sheets and returns focus; sheets trap focus while open.
- [ ] Screenshots match the mockups (`review/screens.ts`; two versions early, all four
      in the final review), with differences either fixed or explained in the PR.

**Tests and checks**
- [ ] Tests for every feature, including the edge cases below that the PR touches.
- [ ] No test weakened: `git diff main -- '*test*' '*spec*' e2e/` shows no deleted
      assertions, loosened expectations, new `skip`/`only`/`fixme`, longer timeouts
      without reason, or excluded axe rules without a comment.
- [ ] A full `./check` passed on the PR's latest commit and its summary is pasted into the
      PR (commit matches, says PASS, not `--fast`).
- [ ] Commits small, each builds; signed off by cabledrawer with `Assisted-by: Claude Code`.
- [ ] PR starts with "What cabledrawer needs to check"; `CHANGELOG.md` updated.

**Security (from 0.4)**
- [ ] For PRs touching sign-in, permissions, households, sync, imports, uploads or the outbound gate: a "Security" heading in the verdict. Check: every new endpoint requires sign-in and checks the household; there's a test trying the wrong household and signed-out access; errors don't reveal other households' data; nothing new leaves the outbound gate.

## What to look at for 0.3

Shopping (mockups `Shop`, `Desktop-Shop`, `Dark-Phone-Shop`, `Dark-Shop`)
- [ ] The list is split by shop, with a heading per shop; the list picker switches
      between the main list and extra lists.
- [ ] Desktop: the put-away panel beside the list, where a ticked item goes (default
      place, or the one chosen). Phone: put-away is a sheet or inline choice, not a panel.
- [ ] Ticking moves the food into the pantry; the pantry screen shows it without a
      reload. "Different pack?" on a ticked item adds a new way it's sold.
- [ ] "Did you buy 2?" card appears when the same item was ticked on two devices; both
      purchases are kept; the card needs no confirm dialog and has Undo.
- [ ] Deleted stays deleted; a tick sticks; no conflict pop-ups anywhere.
- [ ] Hidden, not stubbed: the staples check card (0.6).

Connection status
- [ ] Offline bar reads "Offline — N changes waiting" (N counts down as changes are sent;
      singular "1 change waiting"). Phone: above the bottom tabs. Desktop: at the foot of
      the sidebar; when the sidebar is collapsed, a dot instead.
- [ ] After reconnecting, a "Back online — all saved" toast, which goes away by itself.
- [ ] The bar and toast pass `checkPage` (contrast in both themes, 44 px targets, no
      sideways scroll) and don't cover the bottom tabs.
- [ ] Signing out with unsent changes warns first, then wipes the device's offline copy.

Live updates and offline (always two browser contexts)
- [ ] A change in context A shows in context B without a reload.
- [ ] Offline in B (`context.setOffline(true)`): ticking, adding, editing and deleting
      still work and the bar counts them; going back online sends them in order and the
      pantry ends up right.
- [ ] Same item ticked twice offline, tick vs untick, delete vs edit, a repeated queue
      and a queue older than 3 days: all end in the right state (mostly backend tests;
      two or three in the browser).
- [ ] A repeated action ID is ignored, never applied twice.

Carried over from 0.2 (touch only if the PR changes it)
- [ ] Pantry stock rules, undo (7 days, household time zone, Ctrl+Z), merge, units and
      rounding, use soon dates: their tests still pass unchanged.

## Where 0.3 differs from the mockups (the spec wins)

Fill this in per PR as rulings are made. PR 4 (Shopping):
- Shop tabs end with **All**, which is the starting view, so a newly added item is never hidden
  in another shop's tab (cabledrawer's decision 6, 18 Oct; the mockup starts on the first shop).
- The list picker says "Main list · 12" (the mockup adds "built from the plan", which waits for 0.6).
- Aisle headings use the spec's names (Veg & fruit, Dry goods…), not the mockup's.
- Checkboxes have a 44 px tap area around the 22 px box; buttons are 44 px tall, not 36 px.
- Taking an item off the list is "Remove from list" inside the amount editor (tap the amount)
  (cabledrawer's decision 7, 18 Oct).
- "How do you count it?" has no mockup yet (the put-away toast's Change button is in the phone mockup).

Hidden in 0.3: list generation from the
plan, the staples check card, tubs, "Recipes for these".

## Mockup notes (what builders tend to miss)

Colours come from `docs/mockups/*.dc.html`; most are already tokens in
`frontend/src/lib/styles/tokens.css`. New colours must meet AA in both themes.

- **Shopping:** read `docs/mockups/Shop*.dc.html` and `Dark-*Shop*.dc.html` for exact
  colours, sizes and wording before judging a screenshot; add what the builders keep
  missing here as it turns up.
