# Mealwright: notes for Claude Code

Self-hosted meal-prep and pantry app: recipe → plan → shopping list → pantry → cook. Owner: cabledrawer. Licence AGPL-3.0.

## Read first

- `docs/BUILD-PLAN.md`: what to build, in which order. Work one milestone at a time and stop for cabledrawer's OK at the end of each.
- `docs/spec.md`: the source of truth for every product decision. If code and spec disagree, the spec wins. If neither covers something, ask cabledrawer, then record his answer in the spec, credited to him.
- `docs/mockups/`: the intended look, exported from the design canvas. Read the markup for exact colours, sizes, wording and layout. Visual reference only, not code to copy.

## The ethos (never break these)

- No telemetry, analytics, crash reporting or usage stats, not even opt-in. Logs stay local.
- No location access, ever.
- Every outgoing network request goes through the **outbound gate** module and is blocked unless its Privacy switch is on. Never call `httpx`, `requests`, `urllib`, sockets etc. directly. The test suite fails if you do.
- No CDNs or third-party assets at runtime. Bundle fonts, icons and scripts. Keep the CSP strict.
- Recipe images are downloaded and stored locally, never hotlinked.
- Nothing about the install is ever sent anywhere.

## UX rules (from spec "UX — CORE")

- Phone and desktop both first-class; **phone breaks ties**. Bottom tabs on phone, collapsible sidebar on desktop.
- Plain words ("cupboard", "use soon", "tubs left"), never database words.
- Undo, not "Are you sure?". Optimistic updates. One switch component for every on/off.
- Auto · Light · Dark switch always in plain sight. A designed dark theme, not inverted.
- Vertical scrolling only; no chunky scrollbars.
- Show connection status (offline bar with waiting changes; "Back online — all saved").
- WCAG AA in both themes; touch targets ≥ 44 px.

## Stack

- Backend: Python, FastAPI, SQLAlchemy 2, Alembic, SQLite (Postgres later), APScheduler, Authlib (OIDC), Argon2, Apprise.
- Frontend: SvelteKit static build served by the backend; installable PWA; Server-Sent Events for live updates; IndexedDB offline queue.
- One Docker container, amd64 + arm64, data on `/data`.

## Engineering rules

- API-first: the web app uses only the public, versioned `/api/v1` (OpenAPI). No private endpoints. The offline sync protocol is part of the API.
- Every table has `household_id`. Every schema change is an Alembic migration.
- Tests for every feature. Run `./check` before every PR (lint, types, tests, outbound-gate test, licence allow list, scanners, image checks) and paste its summary into the PR description. It must pass.
- Dependencies must be AGPL-compatible (MIT, BSD, Apache-2.0, ISC, LGPL, GPL-3.0, AGPL, PSF-2.0, MPL-2.0), plus OFL-1.1 for fonts only (cabledrawer 17 Oct). Reject MPL-2.0 packages marked "Incompatible With Secondary Licenses". No GPL-2.0-only. Ask before adding a new dependency.
- Commits are small, and each builds and passes. **cabledrawer is the author and signs off every commit** (cabledrawer 17 Oct): the repo's git identity is set to him, so always commit with `git commit -s --trailer "Assisted-by: Claude Code"`. Never change the git identity and never add a `Signed-off-by` for Claude. Also note AI help in PR descriptions.
- Versions: 0.N.0 per milestone while building (not published). From 1.0.0: MAJOR.MINOR.PATCH per spec section 8. Update `CHANGELOG.md` with each version.
- Code home during 0.x is cabledrawer's private **Forgejo** at `https://<code server>/<owner>/mealwright` (homelab; the address is in `CLAUDE.local.md`, heading "The code server"). Use `git` over **HTTPS** (SSH is off on that Forgejo) and the `tea` CLI, not `gh`. You push as the restricted `claude` account, which can push branches but not `main`.
- Workflow: work on a branch per feature (e.g. `m0.1/app-shell`), push it, and open a pull request with `tea pr create`. Only cabledrawer can push to or merge into `main`, and only he can create `v*` tags. See "Pull requests" below.
- **No self-hosted CI runner during 0.x (cabledrawer 17 Oct):** running untrusted build code on the homelab needs more isolation than it's worth for a one-person project. `./check` replaces it. CI starts at 1.0 on GitHub Actions. 0.x images go only to Forgejo's private registry, and cabledrawer pushes them himself (`docs/dev/test-on-homelab.md`). GitHub becomes the public home at 1.0.0.
- Never publish images or releases yourself. Never push images to any registry, including Forgejo's private one, and never push to any public registry or repo. cabledrawer merges, tags releases and manages the servers.

## Pull requests (cabledrawer 17 Oct)

- **One PR per feature**, not per small piece. Small commits inside a PR are fine (each still builds and passes).
- **Start every PR description with a plain-English section, "What cabledrawer needs to check".** List any new dependencies or licences, anything touching privacy or outbound connections, and any change from the plan or spec. If there's nothing, write "Nothing needs a decision."
- **Paste the `./check` summary into every PR.**
- **cabledrawer usually merges in batches.** Keep working on the next piece rather than waiting for a merge, unless you need a decision. Milestone boundaries still apply: stop at the end of each milestone for his OK.
- **cabledrawer isn't a developer.** Explain things in plain English, and give copy-paste commands with what each one does.
