# Mealwright build plan for Claude Code

Written 17 Oct 2026 from the finished planning spec (`docs/spec.md`). Owner: cabledrawer. This plan tells Claude Code what to build, in what order, and when to stop and check with cabledrawer.

## How to use this plan

- Work **one milestone at a time**, in order. Each milestone ends as a working, tested slice of the app, tagged `v0.N.0`.
- At the start of a milestone, read its section here, the spec sections it names, and the mockup files it lists. Write a short plan, show it to cabledrawer, and wait for his OK.
- Inside a milestone, work in small commits on a branch, and open pull requests with `tea`. Run `./check` before every pull request and paste its summary into the description. Each commit builds, passes tests, and is made with `git commit -s --trailer "Assisted-by: Claude Code"`: cabledrawer is the author and signs off (cabledrawer 17 Oct), and the trailer records the AI help.
- At the end of a milestone, go through its **Done when** list, update `CHANGELOG.md`, bump the version, open the release pull request, and **stop**. cabledrawer merges it and creates the `v0.N.0` tag (only he can push to `main` or create `v*` tags). Give cabledrawer a short summary and what to try by hand. Don't start the next milestone until he says so.
- If the spec and this plan disagree, the spec wins. If something isn't in either, ask cabledrawer rather than guess, and record his answer in `docs/spec.md`, credited to him.
- 0.x versions are not published (no public image, no release). cabledrawer may build and run them on his own homelab.
- **Code home during 0.x (cabledrawer 17 Oct): cabledrawer's own Forgejo** on his homelab, as a private repo. Repo: `https://<code server>/tess/mealwright` (the address is in `CLAUDE.local.md`, git-ignored). Use plain `git` over **HTTPS** (SSH is off on that Forgejo) and the `tea` CLI for pull requests and issues (not `gh`). Claude Code pushes as the restricted `claude` account, with a token limited to repository and issue access; `main` and `v*` tags are protected. **No self-hosted CI runner during 0.x (cabledrawer 17 Oct):** running untrusted build code on the homelab needs more isolation than it's worth for a one-person project. Instead, run `./check` before every pull request and paste its summary into the PR description. 0.x images are never pushed to any registry; cabledrawer builds each one, copies it to the test bed with `scp` and loads it with `docker load` (cabledrawer 18 Oct). The test bed is a test VM, not the code server's machine; Claude Code stays on WSL, and the move to the test VM's machine is on hold (cabledrawer 28 Oct; spec section 9). CI starts at 1.0 on GitHub Actions. GitHub becomes the public home at 1.0.0 (see 0.9 and 1.0).
- **When to run `./check` (cabledrawer 17 Oct, from 0.3):** while working, run only the test file for the change plus lint and type checks for that side; run `./check --fast` after a chunk of work or a round of review fixes; run the full `./check` before opening each pull request, again on the final commit after the last fixes, for release pull requests, and whenever a dependency, lock file or the Dockerfile changes. The checker trusts a pasted summary whose commit matches the pull request's latest commit, and runs only the screenshot review and that feature's browser tests. See spec section 9.
- **Models and effort (cabledrawer 17 Oct, from 0.3):** the lead runs on Opus at the usual effort. Helpers start fresh for each pull request and close when it merges. Use Opus at high effort for the hardest, riskiest work (in 0.3: the sync design, the server sync code, the device's offline queue, and the checker's reviews of those) and Sonnet for everything else. If usage gets tight, move the lead to Sonnet before taking Opus off the risky work. Helpers read only the spec sections their pull request needs, not the whole spec.
- **Working method from 0.8 (cabledrawer 6 Nov; replaces "the lead runs on Opus" above):** Sonnet wherever possible, for the lead and every builder. Opus only for the reviews of security, sync, offline, sign-in, import, database and stock work. The lead's sessions only code and debug: planning, sorting findings, wording for the spec, BUILD-PLAN and `words.md`, hand-test lists and release notes are done with cabledrawer outside the repo and reach the lead as well-defined briefs, with any doc wording ready to commit unchanged. If a brief is unclear, ask cabledrawer rather than decide. Everything else in "Faster working" still holds.
- **Lead sessions (cabledrawer 6 Nov):** every wave starts in a new lead session; a larger wave is split into several sessions, each planned beforehand with its PRs and brief. An overnight run may build several PRs in one session; they are reviewed and merged in the morning, then that session ends and a new one starts. Two hand-over points a day: a session winds up by 05:30 and is ready to hand over by 06:00 (overnight), or winds up by 18:00 and is ready to hand over by 18:30 (day).
- **Docs-only pull requests with agreed wording (cabledrawer 6 Nov):** when a pull request only commits wording cabledrawer has already agreed (written outside the repo), it gets no reviewer and no `./check` (cabledrawer 6 Nov: `./check` has no docs-only step); the helper outside the repo checks the diff against the agreed wording before cabledrawer merges.
- **Working lessons (cabledrawer 18 Oct, from 0.3):** see spec section 9, "Working lessons from 0.3": summaries for long design docs; decisions copied into `progress.md` and checked by the checker; all product questions before the first code pull request; side-by-side pull requests only when they don't overlap; mockups changed only before a screen is built.
- **Keeping the UI good (cabledrawer 18 Oct, from 0.4):** follow spec "UX — CORE → Keeping the UI good". At the start of each milestone, sort the friction log (fix now, later, Not planned). Use the wording in `docs/dev/words.md`. Build every state of a screen, not just the full one. Add new components to `/dev/gallery`. End each milestone with a paper-cuts pull request before the release pull request.
- **Faster working (cabledrawer 18 Oct, from 0.4):** see spec section 9, "Faster working": side by side only when pull requests touch separate parts; first ready merges first; up to three helpers with at most two builders; light and full review levels (the pull request says which); every full `./check` goes through the shared lock; added 19 Oct (cabledrawer 19 Oct): the lead (Opus, usual effort) is the only one cabledrawer talks to, and a fresh helper is started per pull request and closed when it merges; full review also covers permissions, imports, uploads (recipe photos too) and the outbound gate, and its verdict has a Security section; Opus at high effort for the security audit and its review and for any builder or checker on a full-review PR touching sign-in, households, sync or uploads, Sonnet otherwise (if usage gets tight, back to two helpers first); helpers only stop their own runs, by their own process, never with a broad command; helpers report in 10 lines or fewer and read only the spec sections their brief names; branch protection is on (`main` changes only through a pull request cabledrawer merges, and a local pre-commit check refuses commits on `main`; don't change or bypass either).

## Reference material in this repo

- `docs/spec.md` is the source of truth. It covers the ethos, UX principles, scope, data model, security, release and roadmap.
- `docs/mockups/*.dc.html` holds the mockup screens: phone and desktop, light and dark. They were exported from cabledrawer's design canvas, so they use the canvas's own tags (`<sc-if>`, `{{…}}`) and won't render perfectly on their own. Read them as markup with inline styles: exact colours, sizes, spacing, wording and layout. `docs/mockups/canvas.json` lists every file with its title. They are a **visual reference**, not code to copy. Their links show the intended navigation. cabledrawer can show the live canvas if something is unclear.
- `docs/brand/` has the logo SVGs. Colours and wordmark are in spec section 3 and `docs/brand/README.md`.

Mockup file names (light → dark): Sign in `SignIn-*` · Onboarding `Onboard-*` · Today `Main` / `Desktop-Today` / `Dark-Phone-Today` / `Dark-Today` · Plan week `Plan` / `Desktop-Plan` / `Dark-Phone-Plan` / `Dark-Plan` · Month `Month-*` · Shopping `Shop` / `Desktop-Shop` / `Dark-Phone-Shop` / `Dark-Shop` · Pantry `Phone-Pantry` / `Desktop-Pantry` / `Dark-Phone-Pantry` / `Dark-Pantry` · All recipes `Recipes-Phone` · Recipe page `Recipe` / `Desktop-Recipe` / `Dark-Phone-Recipe` / `Dark-Recipe` · Cook once `CookOnce-*` · Cook mode `CookMode-*` · Cooked it `Cooked-*` · Import review `Phone-Import` / `Desktop-Import` / `Dark-Phone-Import` / `Dark-Import` · Drafts `Drafts-*` · Ingredients `Ingredients-*` · Settings `Settings-*`.

## Order and why

The shopping list's offline sync is the biggest technical risk (spec section 6), so it comes early (0.3), straight after the pantry it feeds. Recipes, import and the plan follow. Cooking ties everything together. Settings, integrations and release work come last.

| Version | Milestone |
|---|---|
| 0.1.0 | Foundation: repo, build, app shell, sign-in, safety rails |
| 0.2.0 | Foods, pantry, history and undo |
| 0.3.0 | Shopping list and offline sync |
| 0.4.0 | Recipes |
| 0.5.0 | Recipe import and drafts |
| 0.6.0 | Meal plan, batch cooks and Today |
| 0.7.0 | 0.6.0 fixes; importer consistency (back in 0.7.0, cabledrawer 30 Oct); Cooking: Cook mode, "Cooked it", deductions; Plan redesign; navigation |
| 0.8.0 | Everyday features: 0.7.0 leftovers, Shopping and Pantry, recipes, two cooking methods and multi-day cooking, Batch cook (Experimental) (cabledrawer 2 Nov) |
| 0.9.0 | What a tester needs: people and sign-in, the rest of Settings, onboarding, starter packs, backups, logs, update check, Report a problem, hardening, install docs (cabledrawer 2 Nov) |
| 0.9.5 | Finishing for the public: Mealie importer, accessibility, speed, the rest of the docs, a public-safe repo, GitHub prep, upgrade tests, polish, pre-release checks (cabledrawer 2 Nov) |
| trial | Private trial with 2–3 invited self-hosters, about a month, after 0.9.5; fixes as 0.9.x (cabledrawer 2 Nov) |
| 1.0.0 | First public release |

**Working pace (cabledrawer 18 Oct):** all of a milestone's questions in one sitting at its start, pull requests side by side when they don't overlap, and light review for low-risk pull requests. Not cut: the security audit, the full `./check` before every merge, and the two-device and household tests.

---

## 0.1.0 Foundation

**Goal:** an empty but real Mealwright you can install, sign in to and click around, with every safety rail built in from day one.

**Build:**

- Repo layout: `backend/` (Python, FastAPI), `frontend/` (SvelteKit, static build), `docs/`, `Dockerfile`, `compose.example.yaml`. Licence file AGPL-3.0. `README.md` stub, `CONTRIBUTING.md` (DCO, ethos rules, AI-help disclosure, "phone breaks ties"), `SECURITY.md` (private reporting), `CHANGELOG.md`.
- Backend: FastAPI, SQLAlchemy 2, Alembic (first migration now; every schema change from now on is a migration), SQLite on a mounted `/data` volume. Every table carries `household_id`. Public versioned API under `/api/v1` with generated OpenAPI. The web app uses **only** this API.
- `GET /api/v1/version` returns the version (so Diun and Renovate work).
- **Outbound gate** (spec section 7): one module through which every outgoing HTTP request must go. It checks the household's Privacy switches and blocks anything not switched on. A test fails if any other code opens a network connection (block sockets in the test suite and allow only the gate). Turn off library telemetry.
- **Strict CSP** and security headers. All fonts (Plus Jakarta Sans, Newsreader), icons and scripts bundled. No CDN anywhere.
- Auth: local logins with Argon2, secure session cookies, "Remember this device" (30 days), slow-down after repeated wrong guesses. No default admin: the first visitor creates the admin account (onboarding step 1).
- Frontend: design tokens for the light and dark themes taken from the mockups (colours, radii, type scale, spacing); one switch component; the app shell with bottom tabs on phone and a collapsible sidebar on desktop (logo, five pages, theme button, avatar); the Auto · Light · Dark switch in plain sight (UX principle 13); vertical scrolling only (principle 14); empty pages for Today, Plan, Shopping, Pantry and Recipes.
- Screens: Sign in (`SignIn-*`), plus a first-run "Create admin account" step from Onboarding (`Onboard-*`, first step only).
- ~~CI with Forgejo Actions~~: dropped for 0.x (cabledrawer 17 Oct, see above). Instead, a `./check` script at the repo root that runs every check below, fails on any error, and ends with a clear pass/fail summary. Plus `docs/dev/test-on-homelab.md` for cabledrawer: build the image in WSL from the tag, save it to a file, copy it to the server with `scp`, and load and run it there with `docker load` (no registry).
- Checks in `./check`, run before every pull request: lint, type-check, backend and frontend tests, outbound-gate test, licence allow-list check (spec section 8), dependency vulnerability scan (pip-audit and osv-scanner), code scan (Bandit, not Semgrep: cabledrawer 17 Oct), image build and scan (Trivy). From 0.6 the scanners run only when a pull request changes a library, a lock file or the Dockerfile, and always on a release pull request (cabledrawer 25 Oct, spec section 8). Use open tools only; nothing GitHub-specific (no Dependabot or CodeQL).
- Image builds during 0.x are **amd64 only** (arm64 under emulation is slow; it's added in 0.9). Images are never pushed to any registry; cabledrawer copies them to the test bed (a test VM, cabledrawer 28 Oct) with `scp` and `docker load`. Claude Code never pushes images. Never push anywhere public.
- Docker: one container serving the API and the static frontend; non-root user; health check.

**Done when:**

- `docker compose up` on a fresh volume → create admin → sign in → see the empty shell on phone and desktop widths, light and dark.
- `./check` passes, including the outbound-gate test, the licence check, the scanners, and the Trivy and no-telemetry checks on the built image.
- Following `docs/dev/test-on-homelab.md`, cabledrawer can build a `0.1.0` image, copy it to the test bed with `scp`, and load and run it there.
- A test proves the CSP blocks an external script.

**cabledrawer checks:** install it on his homelab and sign in from phone and desktop.

**The non-technical prototype test** (`docs/prototype-test-plan.md`) runs at 0.9, with the private trial (cabledrawer 19 Oct; spec section 8, "Real use from 0.3").

---

## 0.2.0 Foods, pantry, history and undo

**Spec:** section 2 (Foods and units, Pantry), section 6 (Foods and units, Stock, History and undo, Everything Mealwright stores).

**Build:**

- Data: food (name, other names, pantry unit, usual place, preferred shop, staple flag, running-low level, weight of one item, weight of a cup), sale units (packet = 500 g, dozen = 12, loaf = 20 slices), "can use instead" links, merge history, stock lots (each packet with its own use-by), places (Fridge, Freezer, Cupboard, Spice rack; renameable), shops (with aisle order).
- Stored in g, ml or count; shown "as sold" ("about 750 g · 1½ packets").
- Conversions: bundled offline table plus the household's own "ask once" answers on top. Household answers always win. **Check the table's licence before bundling** and note the source in `docs/`.
- Change log for every stock change (who, what, before → after), Undo for 7 days, history kept 12 months then thinned to monthly totals (both adjustable later in Settings).
- Screens: Pantry (`*Pantry*`): places as tabs on phone and columns on desktop, packets grouped with dates, ¼ · ½ · ¾ · Full quick picks, Use soon (Used / Binned / To freezer), staples chips, Recent changes with Undo. Ingredients (`Ingredients-*`): list, search by any name, filters, the editor, merge, "can use instead". The ingredient editor is one component opened from anywhere.
- Undo toast pattern (principle 6) and optimistic updates (principle 8), used from here on.

**Done when:** tests cover unit maths (as-sold display, conversions, oldest packet used first, never below zero); a food can be added, stocked, partly used, merged and undone; the screens match the mockups in all four versions.

---

## 0.3.0 Shopping list and offline sync

**Spec:** section 6 "Offline shopping-list sync" (read it all), UX principle 16, section 7 (sign-out wipe).

**Build:**

- Lists: one main list per household, plus extra lists. Items carry a phone-made ID, food, shop, amount, source (plan or typed), hand-edited flag, ticked by/when, put-away place, deleted marker and version.
- Sync protocol in `/api/v1` (part of the public API, so phone apps can use it later): the device queues actions (tick, untick, add, change amount, delete, put away), each with its own ID. The server applies them in the order it receives them, using a server counter. A repeated ID is ignored. Only the server changes the pantry.
- Rules: a tick sticks; both ticked offline = two purchases plus a "Did you buy 2?" card; deleted stays deleted; put-away is queued with the tick; no conflict pop-ups; queues older than 3 days are still applied.
- Ticking moves the item into the pantry (default place, or the one chosen). "Different pack?" on ticked items adds a new sale unit.
- Live updates over Server-Sent Events.
- PWA: installable, service worker caching the app shell, the shopping list and recently viewed recipes; an offline queue in IndexedDB.
- Connection status: "Offline — N changes waiting" bar, "Back online — all saved" toast.
- Signing out wipes the device's offline copy, with a warning if changes haven't been sent yet.
- Screen: Shopping (`Shop`, `Desktop-Shop`, dark versions): split by shop, list picker, put-away panel on desktop, offline bar, "Did you buy 2?" card. The staples check card comes in 0.6 with list generation.

**Done when:** automated tests simulate two devices offline (same item ticked twice, tick vs untick, delete vs edit, replayed queue, a 3-day-old queue) and the pantry ends up right every time; a manual test with two phones in aeroplane mode passes.

**cabledrawer checks:** two phones, one shop, aeroplane mode.

**How 0.3 is built (cabledrawer 17 Oct):** pull requests in this order; at most two helpers at once.

| PR | What | Model |
|---|---|---|
| 0 | Housekeeping: `./check --fast`, CLAUDE.md tidy-up, a 0.3 version of `e2e/REVIEW.md` | Sonnet |
| 1 | Sync design doc, `docs/dev/sync-protocol.md` (no code). **Stop for cabledrawer's OK.** | Opus, high |
| 2 | Shopping lists: tables, migration, plain online API | Sonnet |
| 3 | Server sync: action queue, ordering, repeated IDs, tick → pantry, "Did you buy 2?", the simulated two-device tests | Opus, high |
| 4 | Shopping screen working online (runs alongside 3) | Sonnet |
| 5 | Live updates (SSE), installable app and offline caching | Sonnet |
| 6 | Device offline queue, replay, offline bar, sign-out wipe | Opus, high |
| 7 | 0.3.0 release pull request | Sonnet |

After PR 1, helpers read `docs/dev/sync-protocol.md` plus the spec sections their pull request needs. Most sync scenarios are fast backend tests; only two or three end-to-end offline tests run in the browser.

**From here on (cabledrawer 17 Oct, spec section 8 "Lessons"):** cabledrawer's household uses Mealwright for real every week and keeps a friction log (anything annoying or confusing). Every milestone lead reads it when its milestone starts and raises anything that affects its screens. Run the non-technical prototype test before 0.4 starts if at all possible.

---

## 0.4.0 Recipes

**Spec:** section 2 (Recipes), section 6 (Recipes), Layout decisions (Recipes navigation, Recipe page).

**How 0.4 is built:**

- **PR 0a, security audit (Opus high; cabledrawer 18 Oct):** as spec section 8 "Security along the way". Side by side with PR 0b.
- **PR 0b, Keeping the UI good set-up** (as in `ui-quality-decision.md`).
- PR 0a also adds HSTS (https mode only) and the 30-day longest sign-in (cabledrawer 19 Oct, spec section 7).
- From 0.4: the checker adds a security section for PRs touching sign-in, permissions, households, sync, imports, uploads or the outbound gate; every release PR includes a short security pass.

**Build:**

- First pull request (before any recipe screen), spec "Keeping the UI good": `docs/dev/words.md` (cabledrawer approves it); the `/dev/gallery` page with the existing components, kept out of the image; a "stress" shot in the review screenshot script; the browser code size limit in `./check`; saved screenshots for Pantry and Shopping; the reduced-motion rule; keyboard-only tests for the built desktop screens. No new libraries; if one seems needed, stop and ask.
- Data: recipe (title, servings, steps, photos, tags, nutrition per serving, source URL / import date / source note, version number), ingredients pointing to a food **or another recipe**, original wording kept, a homemade link (a recipe made ahead gets its own pantry food). Guard against loops.
- Manual create and edit, photos (resized, stored on the volume), tags, search, scaling servings, nutrition fields (unknown shows as unknown, never zero).
- Screens: All recipes on phone (`Recipes-Phone`: search, Import button placeholder, filters, Drafts and Ingredients buttons), Recipe page (`Recipe`), desktop three-pane Recipes (`Desktop-Recipe`) with the sidebar tree (All recipes · Drafts · Ingredients). "From: <site>" credit. Keep-screen-awake switch (Wake Lock).
- Tapping any ingredient opens the ingredient editor from 0.2.

**Done when:** a recipe with a recipe inside it can be created, scaled and searched; the loop guard is tested; the screens match the mockups.

- The recipe screens pass the states check (empty, loading, failed, offline, one, many, long names, 200% text), use the word list, and their components are in the gallery; the milestone ends with a paper-cuts pull request.
- **In the 0.4 paper-cuts PR (PR 7), from the hand-test fix reviews (cabledrawer 21 Oct):** after a slow start, ask the server again who is signed in; signing out clears the household's shops and places held in memory, so nothing carries over to the next person; a small "Edit ingredient" link in the Shopping amount box to the ingredient editor.

---

## 0.5.0 Recipe import and drafts

**Spec:** section 2 (Recipes), section 7 (private-network block, allow list), Layout decisions (Import review), section 6 gaps (Import drafts).

**Build:**

- URL import **through the outbound gate**, only when the Privacy switch "Recipe import from links" is on. SSRF protection: block private, internal and loopback addresses (after DNS resolution and on every redirect) unless they are on the admin's allow list.
- Parse schema.org Recipe, including NutritionInformation. Download images and store them locally (photo download has its own Privacy switch); never hotlink.
- Paste-text import using the same ingredient parser.
- Ingredient parser: amount, unit, food and note, matched against foods by name and other names.
- Screen: Import review (`*Import*`): as written → how Mealwright reads it → what's in your kitchen; matched / to confirm / needs you / staple; "Same as <food>" vs "New food"; Save · Save & plan it; "Nothing is saved until you choose."
- Leaving without saving → "Save as draft?" → Drafts (`Drafts-*`), kept 15 days, then deleted quietly.
- Today's first-day state links to import (finished in 0.6).
- **Paper-cuts pull request, from cabledrawer's hand test (cabledrawer 20 Oct):**
  - Phone Pantry: a card per place (icon, "Fridge · 6 items", jump chips, empty places folded). Mockup: `PantryPlaces-Phone` and its dark version in `docs/mockups/`.
  - Show a purchase date on pantry rows with no use-by ("bought 20 Oct"): a 0.5 paper cut (cabledrawer 21 Oct). It is already stored (`stock_lot.added_at`, sent by the Pantry API as each lot's `added_on`, and `addedWords` in `frontend/src/lib/dates.ts` already words it), so it only needs showing. "Added" is when the stock went in. cabledrawer 21 Oct: "Both catches are accepted for now (an offline tick is dated when the phone sends it; “Different pack?” dates the new pack that day)."
  - The `e2e/tests/live.spec.ts` connection-bar tests fail only when the whole browser suite runs (under load) and pass when run alone (seen on #49 and 0.4's paper cuts): find out why and fix it (cabledrawer 21 Oct: "The live.spec.ts connection-bar test that fails only under load: add it to the 0.5 paper cuts.").
  - Two browser tests that time out only when the whole suite runs, and pass 3 times out of 3 run alone: the Pantry open-pack test (`e2e/tests/pantry.spec.ts:193`, desktop 0.2) and the phone offline-bar test (`e2e/tests/live.spec.ts:196`, phone 0.3 live). Both were accepted for #50's full check (cabledrawer 21 Oct, for that night only: "if the only failures are the Pantry open-pack test and the phone offline-bar test, and each passes 3 times run alone, accept the check, say so in the PR, and add both to the 0.5 paper cuts."). Find out why they're slow under load and fix them.
  - **Moved out of the paper cuts into a small PR of its own, next after the docs PR (cabledrawer 22 Oct):** "three browser tests now time out only in full checks (Pantry open-pack, the phone offline-bar test, and this Shopping accessibility test). Move the "slow tests under load" fix out of PR 7 into a small PR of its own, next after #53: find why they're slow when the machine is busy and fix all three, Sonnet builder, light review. When it merges, the slow-test rule ends and any timeout counts as a failure again. Until then the rule covers these three tests only." The Shopping test is `e2e/tests/shopping.spec.ts:657` (desktop 0.3, "ticked states pass the accessibility checks in both themes"). The `live.spec.ts` connection-bar item above goes in the same PR.
  - **Also in that PR (cabledrawer 22 Oct):** "The desktop version of the offline-bar test joins the slow-test rule on the same terms (so the rule now covers four: Pantry open-pack, the phone and desktop offline-bar tests, and the Shopping accessibility test). It ends when the slow-tests PR merges." And: "the slow-tests PR (0b) also makes every test run clean up its own /tmp folders (browser-test and pytest), with a test or check that proves nothing is left behind. Note in the PR that /tmp is a tmpfs here, so leftovers also use memory, which may be part of why tests were slow under load."
  - Shopping's pack sheet: "Other" can send 1004.9999999999999 for 1005, which the server refuses (found while capping amounts in 0.4.0; older than 0.4). cabledrawer 21 Oct: "the Shopping "Other" 1004.9999 bug goes on the 0.5 paper cuts".
  - Two photo deletes whose failure still logs the full error, which names the file's path and the household's folder number: the hourly tidy-up's sweep of leftover files that have no photo record (`sweep_files`, called from `drop_waiting_photos`; the error reaches the `log.exception` in `jobs.py`), and the clean-up after an upload fails part-way (`remove_files` in the `finally` of the upload in `api/v1/photos.py`, and `write()`'s own clean-up in `photos.py`), whose error reaches the server's own error log. Log only the kind of error, as deleting after a saved change already does (found by the 0.4.0 release review; cabledrawer 22 Oct: "The two log lines that still record a file's location go on the 0.5 small fixes.").
  - Undo's remaining restore steps check the household themselves, as `_restore_recipe_line` and `_restore_recipe_home` already do: `_restore_field`, `_restore_name`, `_restore_size`, `_restore_stand_in`, `_restore_conversion` and `_restore_lot` in `backend/src/mealwright/history.py`. They can't be reached from another household today, because what they put back comes only from the household's own Undo record (found by the 0.4.0 release review). cabledrawer 22 Oct: "The household check on the remaining Undo steps (_restore_field, _name, _size, _stand_in, _conversion, _lot) goes on the 0.5 small fixes too."
  - With the source links: bring back the recipe editor's hint under Source, "A web address shows as a link you can open yourself. Mealwright never visits it." (cabledrawer 21 Oct: "hide the “A web address shows as a link you can open yourself” hint until 0.5, when links arrive").
  - Phone swipes (cabledrawer 21 Oct, decided at the 0.5 kickoff): see spec "Layout decisions", "Phone swipes". Shopping's move to another shop or list is a new offline "move" change with a full review (cabledrawer 22 Oct).
  - From the friction log (cabledrawer 21 Oct, "fix now in 0.5" if the 0.4.0 hand test still shows them; cabledrawer 22 Oct: "fix all three"): Pantry search as one list across places, each result with its place and "also called thuvaram paruppu"; the Ctrl+Z toast saying what was undone, not just "Undone"; "Today" with a capital on Use soon ("Lemon · Today").

**Done when:** a test suite of structure-only test pages (the layout of 8 commonly used recipe sites and the awkward shapes, with our own made-up text and no photos; never fetched in tests) parses correctly (cabledrawer 21 Oct: this replaces "saved real-world recipe pages", see spec section 6, "Recipe import, decided for 0.5"); the real-recipe check has run on ~80 real recipes (10 per site × 8) and its report is with cabledrawer; SSRF tests cover private IPs, DNS rebinding and redirects; with the Privacy switch off, import is refused.

---

## 0.6.0 Meal plan, batch cooks and Today

**First step: the SvelteKit 3 upgrade (cabledrawer 24 Oct).** "SvelteKit 3: the first step of 0.6.0, right after I tag v0.5.0, as its own PR, brought to me first as a plan with every library it changes; the scanner exceptions expire 23 Nov 2026 as a backstop." The two exceptions are in `frontend/osv-scanner.toml` (spec section 8, cabledrawer 23 Oct, question 27).

**Spec:** section 2 (Meal plan, Shopping list), section 6 (Plan and batch cooks), UX "Meal planner interactions", Layout decisions (Plan, Month, Meals, Today, Cook once, Plan phone long-press).

**Build:**

- Data: meal slots (rename, reorder, on/off), meals (date + slot, status), meal items (recipe, tub or plain food), batch cooks (recipe, cook date, tub count, spread pattern, prep note, colour), tubs (amount in quarters, place or meal, member, use-by).
- Week view (`Plan`, `Desktop-Plan`) and Month view (`Month-*`). Desktop: drag to move, Alt-drag to copy, drop for leftovers, recipe tray below the grid. Phone: long-press sheet (Whose tub? · Move to… · Copy to… · To freezer · Remove). Undo on everything.
- "Cook once, eat for…" (`CookOnce-*`): tub count, patterns (Lunches · Lunch & dinner · Dinners · I'll pick), who's eating, extras to the freezer, preview where you can add or remove tubs.
- Tub use-by defaults (3 days fridge, 3 months freezer), editable.
- Shopping list generation: plan − stock − staples, with "can use instead" stand-ins counted; plan-made items keyed by food + shop; hand edits never overwritten; staples check card (Got it / dismiss).
- Today (`Main`, `Desktop-Today`): tubs left / use soon / to buy, eating today, use soon, next cook, "Did you cook <meal>?" card (Cooked it · Didn't · Move it), first-day empty state.

- **Recipe import, from the 0.5 real-recipe check (cabledrawer 21 Oct):** "testing is 10 different recipies from each of the sites - if fails or fiddly modify in 0.6.0 and try again fails agin - switch in 0.7.0". Fix what the 0.5 check and cabledrawer's 0.5.0 hand test found, then run the check script on all 80 again.
- **Pints (cabledrawer 24 Oct):** read "pint" as a UK pint (568 ml) on UK sites and in pasted text; on US sites (for example Allrecipes) pints stay in the note, as in 0.5. How the app tells a UK site from a US one is decided when 0.6 is planned (spec section 6, "Reading choices, kept"). Nothing changes in 0.5.

**Done when:** a week can be planned by drag (desktop) and long-press (phone); a batch cook spreads tubs correctly, skips filled meals and lets you place them by hand; regenerating the list never duplicates items or overwrites hand edits (tested).

---

## 0.7.0 0.6.0 fixes, cooking, the Plan redesign and navigation

**Scope and order (cabledrawer 28 Oct):** the 0.6.0 bugs first (there is no 0.6.1: "let fix everything in 0.7.0 and test together") → importer consistency (below) → cooking → the Plan redesign → navigation. 0.7.0 is hand-tested as a whole. **Change of order (cabledrawer 30 Oct):** importer consistency, planned on 28 Oct for 0.7.1, moves back into 0.7.0 and comes straight after the 0.6.0 bugs, before cooking, because cabledrawer is starting real use with his own recipes; there is no separate 0.7.1 (cabledrawer 31 Oct: "There's no 0.7.1: the importer moved into 0.7.0 (C1 and C2 are merged)."). **The 0.7 open questions** (K2 to the release) were answered on 31 Oct; the answers are in the spec, section 6, "Answers to the 0.7 open questions".

**Spec:** section 6, "Decided for 0.7.0"; section 2 "Cooking — how deduction works" (all 8 points), section 6 (Plan and batch cooks: cooked record, recipe edited after planning; Recipes: recipes inside recipes), Layout decisions (Cook mode, "Cooked it" review), section 6 gaps (Cook mode ingredients, with the Experimental icon).

**Build:**

- **The 0.6.0 bugs (cabledrawer 28 Oct):** F50 leftovers dates, F58 Cook once and the shopping list (with F56), F48 a tub's use-by from the plan, F22 photos through a reverse proxy, F36 the recipe editor's line order, F45 Month "+N more", F61/F63/F62/F60 shopping amounts, F67 server down (with F68), and the small fixes F16, F44, F41, F73, F46, F75. F5 and F7 go with importer consistency (below).
- Cook mode (`CookMode-*`): big text, one step at a time, timers, screen kept awake, "Show ingredients" sheet, experimental per-step ingredients (guessed, labelled, off unless switched on; fixable when editing the recipe).
- Deduction engine: scale, convert only when units differ, soonest-expiring packet first, fridge and cupboard before freezer, staples never deducted, never below zero (offer "add to list"), "ask once" questions with "Remember for next time", stand-ins via "can use instead", inner recipes taken from the pantry (offer "Make it first?").
- "Cooked it" review (`Cooked-*`): every proposed change with Before → After, a Use switch, Used/Left plus stepper for count foods, "Bought some — used them" for missing items, tubs made and where they go. Confirm → one change-log group with Undo.
- Cooked record: a snapshot of the recipe as cooked plus its stock changes. Future meals follow the latest recipe.
- Batch cooks deduct once on the cook day and create the tubs; eating a tub uses the tub (¼ steps).
- **From cabledrawer's hand test (cabledrawer 20 Oct):**
  - A restock date for each staple: a date line on restocked chips, in the ingredient editor, and a column on Ingredients. The words "Restocked · staples aren’t counted" are already on the Shopping rows (0.4).
  - Ready choices in the "How much?" sheet for a new ingredient (nothing to choose from yet when an ingredient has no sizes).

- **Recipe import (cabledrawer 28 Oct):** no recipe-scrapers in 0.7; Allrecipes keeps "paste the text instead". cabledrawer: "okay for now, revisit after 0.9.0 real world testing". (This replaces the 21 Oct plan to switch page reading to recipe-scrapers in 0.7.)
- **The Plan redesign (cabledrawer 28 Oct; mockups `PlanEat07-Phone`, `PlanCook07-*`, `PlanCards07-Desktop`, `Leftovers07-Phone`, `Month07-Desktop`):** the Both · Eat · Cook switch; separate COOK and EAT cards with drag on the computer; fixed portions per batch, "Leftovers on…" for several meals, "No portions left" → Cook more / Add anyway; Serves − N + and who's eating on a meal (F57); week cells as tall as their content (F42); Month on one screen (F47); tap any day (F52, F53); F49, F65, F39, F40.
- **Navigation (cabledrawer 28 Oct):** F1 "New recipe" in the sidebar, F2 the Settings cog, F76 Ingredients in the sidebar and the phone's Pantry · Ingredients switch.
- The Experimental icon (a small pink flask, `Experimental07`) marks Cook mode's per-step ingredients.
- **From the review of v0.6.0 (cabledrawer 28 Oct, review of v0.6.0; spec section 6, "From the 28 Oct review of v0.6.0"):**
  - Server down: F67's cause (a 502/503/504 from the proxy counts as "can't reach"; a dropped live stream alone never shows the bar; `cantReach()` everywhere; no overlapping or background-tab checks; no repeat toasts after a reload), with a 502-from-the-proxy test (unit and browser).
  - A safety copy of the database before every upgrade (keep the last 3); the docs say to stop the container before copying the data folder.
  - "Cooked it": one row per recipe in a meal with several. Cook mode: on-screen timers with a sound (no alarm when locked or in the background, said so); "Keep screen awake" moves into Cook mode; **Cook now** on the recipe page.
  - Plan: a "Note" item (eating out); **Plan it** on the recipe page; the phone Plan opens at today; one pass at 768–1100 px on every Plan screen; moving cards with the keyboard (Move to… / Copy to…).
  - The version number in the sidebar foot. Refusing to start with a non-SQLite database address or more than one worker.
  - Paper cuts: the recipe editor keeps an unsaved draft in the tab, with a reload test; Duplicate on the recipe page; a stale-answer guard in `FoodModel.load()`; "0 tubs left" not orange; SECURITY.md claims no encryption that doesn't exist yet. Two PRs (cabledrawer 29 and 30 Oct): PC1 the recipe screens (draft, Duplicate), PC2 the rest (with the friction-log cuts), plus two B3 leftovers (cabledrawer 30 Oct): "+ Add to pantry" and the import messages by cause, and the "Try now" timing case (spec, Server down (F67)).
  - Release PR: the PNG line in `docs/brand/README.md`. No CHANGELOG link footers in 0.x (cabledrawer 31 Oct: "No CHANGELOG footer links to the private Forgejo: add them at 1.0, pointing at GitHub."). A v0.7.0-beta.1 tag for cabledrawer's full hand test once everything up to the paper cuts is merged (cabledrawer 31 Oct).

- **From cabledrawer's real use of v0.7.0-alpha.2 (cabledrawer 31 Oct; spec section 6, "From cabledrawer's real use of v0.7.0-alpha.2"):** A3 the alpha.2 fixes (F87–F97, F89 as a note "2 cloves"); A4 import Check fixes (F103, F104, F105, F108, F109, F112, F115; F111 last); a small PR for the pantry, Shopping and Plan cards (F114, F116, F119, F122, F123); F101 "+ Place"; F106 with K3 (and K3 counts stock in every place, as Shopping does); F113 the sidebar's Import item last. Cook mode (K4) only has to not break on a recipe with two method sections; the Plan redesign keeps Serves − N + in the meal's menu, also for meals planned before the update.

**Done when:** the 0.6.0 bugs are fixed with a test each; the deduction engine has thorough unit tests (each of the 8 rules, stand-ins, inner recipes, ask-once); cook → review → confirm → undo works end to end; the Plan redesign works on phone and computer in both themes.

**cabledrawer checks:** cook a real sambar with it, and the 0.6.0 findings again.

---

## 0.7.0, importer consistency (cabledrawer 28 Oct; in 0.7.0 before cooking, cabledrawer 30 Oct)

**Spec:** section 6, "Decided for 0.7.0" (Importer consistency); section 6, Recipes (import).

**Build:** cabledrawer: "the importer lacks consistency". The same thing written two ways gives the same result: the ingredient reader (amounts in words and after the name, names that pick up units or two items, "or" and "+" lines, varieties, headings, footnotes, page junk, several links, pints banner: F3, F7, F8, F9, F11, F12, F15, F17, F18, F19, F20, F23, F25, F26, F28, F31, F32, F33, F34, F35; plus "one and a half cups", "a dozen", quarts and fluid ounces, and a list page holding one recipe card; Add an item reads pack words like "2 packets milk", cabledrawer 30 Oct) and the Check screen (fix amount, unit and note, F30.6; a status dot; the same choices on every line incl. Treat as staple, F21; F4, F5, F6, F10, F13, F29). Also (cabledrawer 28 Oct, review of v0.6.0): converted amounts to a cook's precision (340 g; two decimals only below 10 g or ml); tags tidied on import (capitals and a small synonym table); recipe-name patterns ("How to Make …", "(Authentic … Recipe)"); ingredient names' capitals tidied on save; names like "Beef stock made with 1 stock shot or cube". ("Nutrition possibly out of date" moved to 0.8, cabledrawer 31 Oct.) Add an item reads pack words ("2 packets milk") with the ingredient reader (cabledrawer 30 Oct).

**Done when:** each finding has a reader test with both ways of writing it giving the same result.

**cabledrawer checks:** imports a handful of the 0.6.0 hand-test recipes again.

---

## 0.8.0 Everyday features

**Shape (cabledrawer 2 Nov):** 0.8 is the features cabledrawer needs for everyday use: the Shopping redesign, Pantry, Stocktake, pack sizes, two cooking methods and multi-day cooking, several links at once, tag management and Batch cook (Experimental). Settings only where these need it. People and sign-in, the rest of Settings, onboarding and backups moved to 0.9.0.

**Order, in waves (cabledrawer 6 Nov).** Each wave depends on the one before; mockups come before their wave's screens (dark first).

1. **Kickoff (docs only):** this section, the spec's "Decided for 0.8.0" and the working method (spec section 9).
2. **What 0.7.0 left** (then **`v0.8.0-alpha.1`**, so the F159 fix reaches cabledrawer's everyday copy early; cabledrawer 6 Nov): F159–F164 (spec, "Decided for 0.8.0"), F158 and its two side items, F127, F131, F133, F134, F135, F137, F139, F140, F142, F144, F145, F148, F149, F150, F151 (with the importer's doubled "((optional))"), F153, F154, putting shopping away giving one Undo per item instead of per press, Cook mode's label flicker while the plan loads, the lead's 0.7 follow-ups and the flaky tests (spec section 6, "Decided for 0.7.0", the "To 0.8" lines).
3. **Shopping and Pantry**, then an alpha for cabledrawer's everyday use:
   - **From the 0.6.0 hand test (cabledrawer 28 Oct):** the Shopping redesign (F59: a "plan shopping" view on the computer and an "in the shop" view on the phone; cabledrawer likes today's phone Shopping screen); shops added and managed from the Shopping screen and in Settings → Shops & places (F74); a shorter list (F54); put-away rows (F72, plus clearing one item, and swipes on the phone); the rest of F60. Pantry and Use soon: F64 quick actions and "Passed 3 days ago" on Today, F66 a compact Pantry on the computer, F78 the phone Use soon card, F79 the "How much?" sheet.
   - F117, F120 and F121
     - F117, with the Shopping redesign: "Add as bought" in Shopping's "Add an item" box, straight into the pantry (usual place, Change, Undo), working offline like a tick; "Already have it" on each list row: takes it off the list and puts the amount at home into the pantry (asks how much, starting from the list's amount), recorded as "found at home", not "bought".
     - F120, with the Shopping redesign: with a known size, what to buy in whole packs plus the need ("Ghee · 1 jar (500 g) · 120 g needed"); with no size, common pack sizes from the bundled offline table ("200 g · 500 g · 1 kg"); a tap makes it the Usual size.
     - F121: a "Pack" column on Ingredients ("jar · 500 g"; several sizes → the Usual one plus "+1"), a line under the name on the phone, "Add a pack" with the same suggestions when none.
   - F118: a Stocktake for filling the pantry from what's already at home: place by place; per ingredient None · ¼ · ½ · ¾ · Full or Staple; the pack size asked once if unknown; stop and carry on later.
   - From the review of v0.6.0
     - Pantry: best-before (cupboard: dimmed, "probably fine", no To freezer) apart from use-by (fridge: red); one rule for rolling up packets everywhere (Today, Pantry, Use soon); Today's week strip shows the dinner's name.
     - Shopping: buying amounts (rounded to packs or bunches from known sizes; tiny long-life amounts offered as staples); recipes inside recipes expanded on the list.
   - **The Settings screen (cabledrawer 6 Nov):** the page and its sections in the spec order, building only **Appearance, Amounts (incl. tub use-by, remembered sizes), Meal slots, and Shops & places** now; Household, Privacy, Sign-in, Your data and About come in 0.9.0 with their features.
   - **Tag: `v0.8.0-alpha.2` after this wave** (cabledrawer 6 Nov), for real use.
4. **Recipes:**
   - F110: several links read one after another, each into its own draft (Recipes → Drafts); one failing link doesn't stop the rest; the same switch and server-only fetching as now.
   - "Nutrition possibly out of date" on an imported recipe, only when its ingredient lines or Serves actually change (cabledrawer 31 Oct: "only when the ingredient lines or Serves actually change. If that needs a database change, take it out of C1 and put it in BUILD-PLAN 0.8"). Needs a database change: a save must record whether the lines or Serves changed.
   - Recipes: tag chips in one row with "more", and a screen to manage and merge tags.
5. **Two cooking methods and multi-day cooking**. Screens wait for cabledrawer's mockups.
   - F107 + F124 together: recipes with two cooking methods (Cook mode asks "How are you cooking it today?"; steps, timers and the time follow the pick) and multi-day cooking: "(1) A step can carry a wait ("Marinate · 4–24 h", "Ferment · 8–12 h", "Soak · overnight"), suggested by the importer and confirmed on the Check screen. (2) The time splits ("30 min active · plus 12 h fermenting"). (3) The plan works backwards: the Cook view and Today show it the day before ("Start tonight: soak and grind the dosa batter (for Sat breakfast)"). (4) Cook mode starts at the right step on day two. In-app only, no notifications." Screens wait for cabledrawer's mockups.
6. **Batch cook (Experimental), last** (cabledrawer 6 Nov), built on wave 5's waiting steps and timings: spec section 6, "Batch cook (Experimental)". If 0.8 runs long, Batch cook moves to 0.8.5 rather than hold up the release (cabledrawer 6 Nov).

**Each wave's screens** get the 768–1100 px pass (from the review of v0.6.0) as they are built.

**Release:** at most two betas (cabledrawer 6 Nov), then `v0.8.0`. Every 0.x tag is a pre-release.

**Done when (cabledrawer 6 Nov):** each finding in wave 2 has a test; Shopping works on the phone in the shop (offline as before) and on the computer for planning; Stocktake can stop and carry on; a recipe with two methods and an overnight step cooks right on both days; Batch cook never schedules two hands-on tasks at once or more hob rings than the kitchen has.

**cabledrawer checks (cabledrawer 6 Nov):** a week of real use on the alpha (shopping, putting away, a stocktake), then the beta hand test: a dosa batter started the night before, and a Batch cook session.

---

## 0.9.0 What a tester needs

**Shape (cabledrawer 2 Nov):** everything a private-trial tester needs to install, sign in, set up and trust Mealwright with their data.

**Build:**

- Members (profiles without logins), Admin/Member roles, portions assigned to members. Optional "Who's this?" picker for shared logins.
- OIDC sign-in with Authlib (PKCE, refresh tokens), auto-create on first login, group → role mapping, option to turn off password logins (Sign in then shows only the SSO button).
- API tokens: read-only or full, optional expiry.
- Full Onboarding (`Onboard-*`): admin account, then Amounts, Household and Shops; Skip always available after the admin step.
- Settings (`Settings-*`), every section in the spec order: Appearance, Amounts (incl. tub use-by, remembered sizes), Household, Meal slots, Shops & places, Privacy (every outside connection with its own switch), Sign-in, Your data, About. (the sections 0.8 didn't build: Household, Privacy, Sign-in, Your data, About)
- Secrets (the SSO client secret) encrypted at rest.
- Passwords and the sign-in cookie (spec section 7, "Decided after the 0.4 security audit", cabledrawer 19 Oct): new passwords need at least 12 characters (existing ones keep working); new passwords are checked against a bundled, offline list of leaked passwords under a licence on the allow list (never an online lookup) (lead's note: cabledrawer approves the list and its licence first); the sign-in cookie gets the `__Host-` name, which signs everyone out once (say so in the release notes) and can't work in plain-http mode (decide with cabledrawer what that mode does).
- **Not before 1.0 (cabledrawer 18 Oct):** notifications (ntfy/Apprise) are not built before 1.0. The Settings → Notifications section and anything that would call ntfy/Apprise are not built before 1.0.
- Backups: daily, keep 7, into the data volume (adjustable). Export everything (optional password encryption).
- Logs: errors and sign-ins only, 14 days, never content.
- Updates: version-age note (no connection), admin "Check now", optional daily check (off by default, in Privacy). Requests go through the outbound gate and send nothing about the install.
- "Report a problem" (About): report built on the server, shown in full with personal details removed, editable; Open on GitHub (pre-filled issue in the user's browser), Copy, or Download.
- **The Undo-window setting (cabledrawer 28 Oct):** if `undo_days` becomes a setting and is raised, Undo of a recipe Save older than the old window brings the recipe back without its draft. Decide with cabledrawer when the setting is built.
- Starter ingredient packs (spec section 2, cabledrawer 18 Oct): the optional onboarding step and the "Add a starter pack" button on Ingredients, with the four packs bundled as data files in the repo. cabledrawer agrees the item lists before the first code pull request.
- From the review of v0.6.0
  - Sign-in: a limit on Argon2 (a few hashes at a time); a per-username lock-out capped at about 60 s; change password; a sessions list; sign out everywhere; a one-time setup code for the first run; `X-Forwarded-Host` when a proxy is trusted; a one-time warning when `X-Forwarded-For` arrives from a proxy that isn't trusted.
  - Household: a roles table (Admin and Member) written before Settings is built; a local `reset-admin` command; removing a person; "Delete everything / start again"; restore written down (how, photos, a warning about backups on the same disk).
  - Update check and About: "new version ready — close every tab"; a total-time limit on `OutboundGate.request()`; About with the USDA credit, font licences and the AGPL source link.

**Also from the old 0.9.0 (cabledrawer 2 Nov: hardening and install docs come here):**

- Database file readable only by Mealwright (spec section 7, "Decided after the 0.4 security audit", cabledrawer 19 Oct): `mealwright.db` becomes readable only by the `mealwright` user, together with the backup docs (lead's note: once it's clear how backup tools read `/data`).
- Install docs, HTTPS (cabledrawer 17 Oct): say plainly that HTTPS is required for sign-in on other devices, the installable app, offline shopping and keep-screen-awake, and why. Give short, tested reverse-proxy examples for Caddy, Traefik, nginx and Nginx Proxy Manager, each showing HTTPS, the forwarded headers and the matching `MEALWRIGHT_TRUSTED_PROXIES` value. (lead's note: say to give Mealwright its own host name, because HSTS covers every port on that name, so another plain-http service on the same name would be forced to https.)
- Compose hardening (no-new-privileges, cap_drop, read_only with tmpfs, init, a memory limit, a commented `user:` line); Dockerfile OCI labels and layer order; `uv lock --check` in the build; SBOM and provenance.

**Done when:** a member-only household, an SSO-only household and a mixed one all work; with every Privacy switch off, the outbound-gate test proves nothing leaves; backup → restore works on a fresh container.

**cabledrawer checks:** a hand test including a restore on a fresh container.

---

## 0.9.5 Finishing for the public

**Shape (cabledrawer 2 Nov):** the Mealie importer, accessibility, speed, the rest of the docs, a public-safe repo, GitHub prep, upgrade tests, polish and the pre-release checklist. Hardening and the install docs moved to 0.9.0.

**Build:**

- Mealie importer (recipes, foods, nutrition fields).
- Accessibility pass to WCAG AA: contrast in both themes, keyboard, screen reader labels, large text.
- Performance pass: fast on a Raspberry Pi 4 class device and an older phone.
- Docs: install (Docker / compose, both image names), upgrade, backups, SSO setup, reverse proxy, the API, and the **README Privacy section** listing every possible outbound connection. README notes that Mealwright is a spare-time project with replies taking about a week, plus the AI disclosure.
- Prepare the move to GitHub (ready but unused): GitHub Actions workflows in `.github/workflows/` that run the same checks as `./check` (CI starts here, at 1.0: cabledrawer 17 Oct); add arm64 to image builds; a release workflow that, on a `v1.*` tag on GitHub, builds multi-arch and pushes to GHCR and Docker Hub with tags 1.2.3 / 1.2 / 1 / latest, and creates the GitHub release from `CHANGELOG.md`. Write `docs/dev/move-to-github.md` for cabledrawer: create the GitHub repo, set a push mirror in Forgejo, add secrets, turn on private vulnerability reporting, issue form and Discussions.
- Pre-release checklist from spec section 8: licence allow list green and the food table checked by hand; a manual network-watch run with every Privacy switch off; trademark search (UK, EU, US) recorded by cabledrawer; scanners clean; web-app security checklist gone through.
- **The 1.0 promise (spec section 8):** document and version the export format in `docs/`; add upgrade tests: a saved database from each earlier 0.x tag upgrades cleanly to the latest, with the 0.9 database kept as a fixture for later tests.
- **Plan for stepping away:** `docs/dev/architecture.md` (how the pieces fit together, in plain words) and `docs/dev/build-and-release.md` (how to build, test, tag and publish), so someone else could carry on or fork cleanly.
- **README "Not planned" section:** built from spec section 1 non-goals, the ethos hard rules, "Not in v1" and spec section 8.
- **From the review of v0.6.0 (cabledrawer 28 Oct, review of v0.6.0):**
  - A repo safe to make public: homelab names and local paths move out of tracked files into a git-ignored local file, then a `./check` step fails on them.
  - Browser tests in the pinned Playwright image; fonts latin and latin-ext only; a healthcheck that touches the database; no `Server` header; THIRD-PARTY-NOTICES.md.
  - Docs: install, upgrade, backup, reverse proxy, a table of environment variables, CONTRIBUTING. The install docs say "one worker only" (Mealwright can't see gunicorn's forked workers; no lock file; cabledrawer 30 Oct).
  - `./check` extras: hadolint, compose config, shellcheck, a smoke run of the built image, and an upgrade test from a saved real database for each tag.
  - The arm64 image question at the 0.9 kickoff.
  - The service worker's cache heals itself; a replayed change with the same key checks the body too; recipe-list hints only for the page shown; a print layout for the shopping list and recipes; an optional sample recipe pack; scaling edge cases written down as "roughly right".

**Done when:** every "v1.0 must have" item in spec section 2 is built and ticked off in a checklist in `docs/`; the pre-release checklist is complete.

**Then the private trial (cabledrawer 2 Nov):** cabledrawer asks the self-hosting community for a review and runs a private trial with two or three invited self-hosters for about a month (how they get the build is decided before the trial; no public image or release), and fixes what comes back as 0.9.x patches. The non-technical prototype test (`docs/prototype-test-plan.md`) runs alongside the trial (cabledrawer 19 Oct).

---

## 1.0.0 First public release

cabledrawer decides when. He makes the GitHub repo public. The development history goes to GitHub, cleaned (cabledrawer 30 Oct: "GitHub at 1.0 gets the development history, cleaned (not "starts fresh")."), replacing the 28 Oct "start fresh with one clean commit". Then he tags `v1.0.0`; the GitHub pipeline publishes the images and the release. After that, version numbers follow spec section 8: patch for security and tiny fixes, minor for smaller features, major for big functionality or anything needing user action. Features are bundled into minor releases about once a month at most; security fixes go out whenever needed. Every release is tested upgrading from a 1.0.0 database (the 1.0 promise).

At 1.0, `CHANGELOG.md` gets link footers for every version, pointing at GitHub (cabledrawer 31 Oct: "No CHANGELOG footer links to the private Forgejo: add them at 1.0, pointing at GitHub.").

## After 1.0.0

Plans after 1.0 are kept outside the repo.
