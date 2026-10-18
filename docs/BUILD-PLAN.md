# Mealwright build plan for Claude Code

Written 17 Oct 2026 from the finished planning spec (`docs/spec.md`). Owner: cabledrawer. This plan tells Claude Code what to build, in what order, and when to stop and check with cabledrawer.

## How to use this plan

- Work **one milestone at a time**, in order. Each milestone ends as a working, tested slice of the app, tagged `v0.N.0`.
- At the start of a milestone, read its section here, the spec sections it names, and the mockup files it lists. Write a short plan, show it to cabledrawer, and wait for his OK.
- Inside a milestone, work in small commits on a branch, and open pull requests with `tea`. Run `./check` before every pull request and paste its summary into the description. Each commit builds, passes tests, and is made with `git commit -s --trailer "Assisted-by: Claude Code"`: cabledrawer is the author and signs off (cabledrawer 17 Oct), and the trailer records the AI help.
- At the end of a milestone, go through its **Done when** list, update `CHANGELOG.md`, bump the version, open the release pull request, and **stop**. cabledrawer merges it and creates the `v0.N.0` tag (only he can push to `main` or create `v*` tags). Give cabledrawer a short summary and what to try by hand. Don't start the next milestone until he says so.
- If the spec and this plan disagree, the spec wins. If something isn't in either, ask cabledrawer rather than guess, and record his answer in `docs/spec.md`, credited to him.
- 0.x versions are not published (no public image, no release). cabledrawer may build and run them on his own homelab.
- **Code home during 0.x (cabledrawer 17 Oct): cabledrawer's own Forgejo** on his homelab, as a private repo. Repo: `https://git.example.org/tess/mealwright`. Use plain `git` over **HTTPS** (SSH is off on that Forgejo) and the `tea` CLI for pull requests and issues (not `gh`). Claude Code pushes as the restricted `claude` account, with a token limited to repository and issue access; `main` and `v*` tags are protected. **No self-hosted CI runner during 0.x (cabledrawer 17 Oct):** running untrusted build code on the homelab needs more isolation than it's worth for a one-person project. Instead, run `./check` before every pull request and paste its summary into the PR description. 0.x images are never pushed to any registry; cabledrawer builds each one, copies it to the home server with `scp` and loads it with `docker load` (cabledrawer 18 Oct). CI starts at 1.0 on GitHub Actions. GitHub becomes the public home at 1.0.0 (see 0.9 and 1.0).
- **When to run `./check` (cabledrawer 17 Oct, from 0.3):** while working, run only the test file for the change plus lint and type checks for that side; run `./check --fast` after a chunk of work or a round of review fixes; run the full `./check` before opening each pull request, again on the final commit after the last fixes, for release pull requests, and whenever a dependency, lock file or the Dockerfile changes. The checker trusts a pasted summary whose commit matches the pull request's latest commit, and runs only the screenshot review and that feature's browser tests. See spec section 9.
- **Models and effort (cabledrawer 17 Oct, from 0.3):** the lead runs on Opus at the usual effort. Helpers start fresh for each pull request and close when it merges. Use Opus at high effort for the hardest, riskiest work (in 0.3: the sync design, the server sync code, the device's offline queue, and the checker's reviews of those) and Sonnet for everything else. If usage gets tight, move the lead to Sonnet before taking Opus off the risky work. Helpers read only the spec sections their pull request needs, not the whole spec.
- **Working lessons (cabledrawer 18 Oct, from 0.3):** see spec section 9, "Working lessons from 0.3": summaries for long design docs; decisions copied into `progress.md` and checked by the checker; all product questions before the first code pull request; side-by-side pull requests only when they don't overlap; mockups changed only before a screen is built.

## Reference material in this repo

- `docs/spec.md` is the source of truth. It covers the ethos, UX principles, scope, data model, security, release and roadmap.
- `docs/mockups/*.dc.html` holds the 62 mockup screens: phone and desktop, light and dark. They were exported from cabledrawer's design canvas, so they use the canvas's own tags (`<sc-if>`, `{{…}}`) and won't render perfectly on their own. Read them as markup with inline styles: exact colours, sizes, spacing, wording and layout. `docs/mockups/canvas.json` lists every file with its title. They are a **visual reference**, not code to copy. Their links show the intended navigation. cabledrawer can show the live canvas if something is unclear.
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
| 0.7.0 | Cooking: Cook mode, "Cooked it", deductions |
| 0.8.0 | Household, settings, notifications, backups |
| 0.9.0 | Mealie importer, docs, polish, pre-release checks |
| 1.0.0 | First public release |

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
- Checks in `./check`, run before every pull request: lint, type-check, backend and frontend tests, outbound-gate test, licence allow-list check (spec section 8), dependency vulnerability scan (pip-audit and osv-scanner), code scan (Bandit, not Semgrep: cabledrawer 17 Oct), image build and scan (Trivy). Use open tools only; nothing GitHub-specific (no Dependabot or CodeQL).
- Image builds during 0.x are **amd64 only** (arm64 under emulation on the home server is slow; it's added in 0.9). Images are never pushed to any registry; cabledrawer copies them to the home server with `scp` and `docker load`. Claude Code never pushes images. Never push anywhere public.
- Docker: one container serving the API and the static frontend; non-root user; health check.

**Done when:**

- `docker compose up` on a fresh volume → create admin → sign in → see the empty shell on phone and desktop widths, light and dark.
- `./check` passes, including the outbound-gate test, the licence check, the scanners, and the Trivy and no-telemetry checks on the built image.
- Following `docs/dev/test-on-homelab.md`, cabledrawer can build a `0.1.0` image, copy it to the home server with `scp`, and load and run it there.
- A test proves the CSP blocks an external script.

**cabledrawer checks:** install it on his homelab and sign in from phone and desktop.

**Meanwhile (not code):** run the non-technical prototype test from `docs/prototype-test-plan.md` if it hasn't been done. 0.1 has no feature screens yet, so any findings can still shape 0.2 onwards.

---

## 0.2.0 Foods, pantry, history and undo

**Spec:** section 2 (Foods and units, Pantry), section 6 (Foods and units, Stock, History and undo, Everything Mealwright stores).

**Build:**

- Data: food (name, other names, pantry unit, usual place, preferred shop, staple flag, running-low level, weight of one item, weight of a cup), sale units (packet = 500 g, dozen = 12, loaf = 20 slices), "can use instead" links, merge history, stock lots (each packet with its own use-by), places (Fridge, Freezer, Cupboard, Spice rack; renameable), shops (with aisle order).
- Stored in g, ml or count; shown "as sold" ("1½ packets · about 750 g").
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

**Build:**

- Data: recipe (title, servings, steps, photos, tags, nutrition per serving, source URL / import date / source note, version number), ingredients pointing to a food **or another recipe**, original wording kept, a homemade link (a recipe made ahead gets its own pantry food). Guard against loops.
- Manual create and edit, photos (resized, stored on the volume), tags, search, scaling servings, nutrition fields (unknown shows as unknown, never zero).
- Screens: All recipes on phone (`Recipes-Phone`: search, Import button placeholder, filters, Drafts and Ingredients buttons), Recipe page (`Recipe`), desktop three-pane Recipes (`Desktop-Recipe`) with the sidebar tree (All recipes · Drafts · Ingredients). "From: <site>" credit. Keep-screen-awake switch (Wake Lock).
- Tapping any ingredient opens the ingredient editor from 0.2.

**Done when:** a recipe with a recipe inside it can be created, scaled and searched; the loop guard is tested; the screens match the mockups.

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

**Done when:** a test suite of saved real-world recipe pages (stored as files, never fetched in tests) parses correctly; SSRF tests cover private IPs, DNS rebinding and redirects; with the Privacy switch off, import is refused.

---

## 0.6.0 Meal plan, batch cooks and Today

**Spec:** section 2 (Meal plan, Shopping list), section 6 (Plan and batch cooks), UX "Meal planner interactions", Layout decisions (Plan, Month, Meals, Today, Cook once, Plan phone long-press).

**Build:**

- Data: meal slots (rename, reorder, on/off), meals (date + slot, status), meal items (recipe, tub or plain food), batch cooks (recipe, cook date, tub count, spread pattern, prep note, colour), tubs (amount in quarters, place or meal, member, use-by).
- Week view (`Plan`, `Desktop-Plan`) and Month view (`Month-*`). Desktop: drag to move, Alt-drag to copy, drop for leftovers, recipe tray below the grid. Phone: long-press sheet (Whose tub? · Move to… · Copy to… · To freezer · Remove). Undo on everything.
- "Cook once, eat for…" (`CookOnce-*`): tub count, patterns (Lunches · Lunch & dinner · Dinners · I'll pick), who's eating, extras to the freezer, preview where you can add or remove tubs.
- Tub use-by defaults (3 days fridge, 3 months freezer), editable.
- Shopping list generation: plan − stock − staples, with "can use instead" stand-ins counted; plan-made items keyed by food + shop; hand edits never overwritten; staples check card (Got it / dismiss).
- Today (`Main`, `Desktop-Today`): tubs left / use soon / to buy, eating today, use soon, next cook, "Did you cook <meal>?" card (Cooked it · Didn't · Move it), first-day empty state.

**Done when:** a week can be planned by drag (desktop) and long-press (phone); a batch cook spreads tubs correctly, skips filled meals and lets you place them by hand; regenerating the list never duplicates items or overwrites hand edits (tested).

---

## 0.7.0 Cooking: Cook mode, "Cooked it", deductions

**Spec:** section 2 "Cooking — how deduction works" (all 8 points), section 6 (Plan and batch cooks: cooked record, recipe edited after planning; Recipes: recipes inside recipes), Layout decisions (Cook mode, "Cooked it" review), section 6 gaps (Cook mode ingredients).

**Build:**

- Cook mode (`CookMode-*`): big text, one step at a time, timers, screen kept awake, "Show ingredients" sheet, experimental per-step ingredients (guessed, labelled, off unless switched on; fixable when editing the recipe).
- Deduction engine: scale, convert only when units differ, soonest-expiring packet first, fridge and cupboard before freezer, staples never deducted, never below zero (offer "add to list"), "ask once" questions with "Remember for next time", stand-ins via "can use instead", inner recipes taken from the pantry (offer "Make it first?").
- "Cooked it" review (`Cooked-*`): every proposed change with Before → After, a Use switch, Used/Left plus stepper for count foods, "Bought some — used them" for missing items, tubs made and where they go. Confirm → one change-log group with Undo.
- Cooked record: a snapshot of the recipe as cooked plus its stock changes. Future meals follow the latest recipe.
- Batch cooks deduct once on the cook day and create the tubs; eating a tub uses the tub (¼ steps).

**Done when:** the deduction engine has thorough unit tests (each of the 8 rules, stand-ins, inner recipes, ask-once); cook → review → confirm → undo works end to end.

**cabledrawer checks:** cook a real sambar with it.

---

## 0.8.0 Household, settings, notifications, backups

**Spec:** section 3 (Users and households), section 7 (all), Layout decisions (Onboarding, Settings, Settings additions, Sign-in, Sign-out warning).

**Build:**

- Members (profiles without logins), Admin/Member roles, portions assigned to members. Optional "Who's this?" picker for shared logins.
- OIDC sign-in with Authlib (PKCE, refresh tokens), auto-create on first login, group → role mapping, option to turn off password logins (Sign in then shows only the SSO button).
- API tokens: read-only or full, optional expiry.
- Full Onboarding (`Onboard-*`): admin account, then Amounts, Household and Shops; Skip always available after the admin step.
- Settings (`Settings-*`), every section in the spec order: Appearance, Amounts (incl. tub use-by, remembered sizes), Household, Meal slots, Shops & places, Notifications, Privacy (every outside connection with its own switch), Sign-in, Your data, About.
- Notifications through Apprise, only to targets the household sets up: use-soon and defrost reminders, each recorded so it's never sent twice. Secrets (Apprise URLs, SSO client secret) encrypted at rest.
- Backups: daily, keep 7, into the data volume (adjustable). Export everything (optional password encryption).
- Logs: errors and sign-ins only, 14 days, never content.
- Updates: version-age note (no connection), admin "Check now", optional daily check (off by default, in Privacy). Requests go through the outbound gate and send nothing about the install.
- "Report a problem" (About): report built on the server, shown in full with personal details removed, editable; Open on GitHub (pre-filled issue in the user's browser), Copy, or Download.
- Starter ingredient packs (spec section 2, cabledrawer 18 Oct): the optional onboarding step and the "Add a starter pack" button on Ingredients, with the four packs bundled as data files in the repo. cabledrawer agrees the item lists before the first code pull request.

**Done when:** a member-only household, an SSO-only household and a mixed one all work; with every Privacy switch off, the outbound-gate test proves nothing leaves; backup → restore works on a fresh container.

---

## 0.9.0 Mealie importer, docs, polish, pre-release checks

**Build:**

- Mealie importer (recipes, foods, nutrition fields).
- Accessibility pass to WCAG AA: contrast in both themes, keyboard, screen reader labels, large text.
- Performance pass: fast on a Raspberry Pi 4 class device and an older phone.
- Docs: install (Docker / compose, both image names), upgrade, backups, SSO setup, reverse proxy, the API, and the **README Privacy section** listing every possible outbound connection. README notes that Mealwright is a spare-time project with replies taking about a week, plus the AI disclosure.
- Install docs, HTTPS (cabledrawer 17 Oct): say plainly that HTTPS is required for sign-in on other devices, the installable app, offline shopping and keep-screen-awake, and why. Give short, tested reverse-proxy examples for Caddy, Traefik, nginx and Nginx Proxy Manager, each showing HTTPS, the forwarded headers and the matching `MEALWRIGHT_TRUSTED_PROXIES` value.
- Prepare the move to GitHub (ready but unused): GitHub Actions workflows in `.github/workflows/` that run the same checks as `./check` (CI starts here, at 1.0: cabledrawer 17 Oct); add arm64 to image builds; a release workflow that, on a `v1.*` tag on GitHub, builds multi-arch and pushes to GHCR and Docker Hub with tags 1.2.3 / 1.2 / 1 / latest, and creates the GitHub release from `CHANGELOG.md`. Write `docs/dev/move-to-github.md` for cabledrawer: create the GitHub repo, set a push mirror in Forgejo, add secrets, turn on private vulnerability reporting, issue form and Discussions.
- Pre-release checklist from spec section 8: licence allow list green and the food table checked by hand; a manual network-watch run with every Privacy switch off; trademark search (UK, EU, US) recorded by cabledrawer; scanners clean; web-app security checklist gone through.
- **The 1.0 promise (spec section 8):** document and version the export format in `docs/`; add upgrade tests: a saved database from each earlier 0.x tag upgrades cleanly to the latest, with the 0.9 database kept as a fixture for later tests.
- **Plan for stepping away:** `docs/dev/architecture.md` (how the pieces fit together, in plain words) and `docs/dev/build-and-release.md` (how to build, test, tag and publish), so someone else could carry on or fork cleanly.
- **README "Not planned" section:** built from spec section 1 non-goals, the ethos hard rules, "Not in v1" and spec section 8.

**Done when:** every "v1.0 must have" item in spec section 2 is built and ticked off in a checklist in `docs/`; the pre-release checklist is complete.

**cabledrawer checks:** asks the self-hosting community for a review, runs a private trial with two or three invited self-hosters for about a month (how they get the build is decided then; no public image or release), and fixes what comes back (as 0.9.x patches).

---

## 1.0.0 First public release

cabledrawer decides when. He makes the GitHub repo public (Forgejo push-mirrors to it, so Forgejo can stay his working copy), then tags `v1.0.0`; the GitHub pipeline publishes the images and the release. After that, version numbers follow spec section 8: patch for security and tiny fixes, minor for smaller features, major for big functionality or anything needing user action. Features are bundled into minor releases about once a month at most; security fixes go out whenever needed. Every release is tested upgrading from a 1.0.0 database (the 1.0 promise).

## After 1.0.0

Plans after 1.0 are kept outside the repo.
