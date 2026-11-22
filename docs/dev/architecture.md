# Architecture: how Mealwright fits together

For someone who has never seen the code. It says where things are and which rules hold everywhere. It links the longer docs instead of repeating them. If it disagrees with `docs/spec.md`, the spec wins. Written for 0.9.5; keep it up to date when a part moves.

## In one paragraph

Mealwright is one Docker container. A Python server (FastAPI) serves two things: the public, versioned API under `/api/v1`, and the web app (a SvelteKit static build, an installable PWA). The web app talks only to that API. Data lives in one SQLite database in the `/data` folder, next to recipe photos, backups and logs. Live updates reach open screens by Server-Sent Events. A phone keeps its own copy of the shopping list and queues changes while offline. Background jobs run inside the same process. The server connects to nothing outside, except through one gate that is shut unless the household switched that connection on.

## The parts

```
 Browser or phone (PWA, SvelteKit static build)
   |  IndexedDB: offline copy of the lists + queue of waiting changes
   |  service worker: keeps the app files, so it opens offline
   v
 HTTPS (your reverse proxy)  ->  one container, port 8080
   |
   |  /api/v1/...          requests, JSON       (OpenAPI at /api/v1/openapi.json)
   |  /api/v1/events       live updates (SSE; numbers only, never names)
   |  everything else      the web app's files (index.html for any page address)
   v
 FastAPI app  (backend/src/mealwright/main.py)
   |-- routers  (api/v1/*.py)        thin: check who is signed in, call the code below
   |-- the rules  (plan, shopping, stock, recipes, ... *.py)
   |-- SQLAlchemy 2  ->  SQLite  <data>/mealwright.db   (Alembic migrations)
   |-- APScheduler jobs (jobs.py)    tidy-up, backups, daily checks
   |-- events.py                     tells open screens "something changed"
   |
   +-- outbound gate (outbound.py)  ->  optional outside services
         (recipe pages, update check, single sign-on provider, ...)
         blocked unless that connection's Privacy switch is on;
         network_guard.py refuses any other connection or DNS lookup
```

Sources: `backend/src/mealwright/main.py`, `api/v1/__init__.py`, `jobs.py`, `events.py`, `outbound.py`, `network_guard.py`, `frontend.py`; `Dockerfile`.

## Where each part lives

### Backend: `backend/src/mealwright/`

One flat package of modules (about 100), each with a docstring that says what it does and which spec section it follows. The groups:

| Where | What it does |
| --- | --- |
| `__main__.py`, `main.py`, `config.py` | Starting the server, building the app, settings from `MEALWRIGHT_*` variables ([environment.md](../environment.md)) |
| `api/v1/*.py` | The public API, one router per area (plan, shopping, pantry, recipes, imports, sync, events, tokens, sso, your_data, ...). Collected in `api/v1/__init__.py` |
| `models.py`, `db.py`, `migrate.py`, `migrations/versions/` | Tables, database sessions, running migrations at start-up, the Alembic migrations |
| `auth.py`, `sso.py`, `sso_accounts.py`, `api_tokens.py`, `roles.py`, `people.py`, `household.py`, `setup_code.py`, `reset_admin.py` | Sign-in, single sign-on, API tokens, admin and member roles, households, the first-run setup code, the admin way back in |
| `security.py`, `secret_box.py`, `private_files.py`, `limits.py` | Browser security headers (strict CSP), secrets kept encrypted, file modes in `/data`, request size limits |
| `outbound.py`, `network_guard.py`, `page_fetch.py`, `own_network.py`, `updates.py` | The outbound gate, the guard behind it, safe page fetching, the "your own network" list, the update check |
| `recipes.py`, `recipe_import.py`, `page_reader.py`, `page_budget.py`, `pasted_recipe.py`, `ingredient_reader.py`, `drafts.py`, `photos.py` | Recipes, importing from a link or pasted text, drafts, photo cleaning ([recipe-import.md](recipe-import.md), [ingredient-reader.md](ingredient-reader.md)) |
| `foods.py`, `stock.py`, `amounts.py`, `conversions.py`, `pack_sizes.py`, `pints.py`, `aisles.py`, `starter_packs.py`, `data/*.csv` | Ingredients (called "foods" in the API), the cupboard, amounts and units, bundled tables ([conversions.md](conversions.md)) |
| `plan.py`, `shop_from_plan.py`, `shopping.py`, `buying.py`, `deduction.py`, `today.py`, `start_ahead.py` | The meal plan, the shopping list built from it, what cooking takes out of stock |
| `batch_*.py`, `batches.py`, `cooking.py`, `cooked.py`, `step_*.py` | Batch cooking and cook mode |
| `sync.py`, `events.py`, `devices.py`, `kitchen_changes.py`, `history.py`, `removals.py` | Offline sync, live updates, the change log behind Undo ([sync-protocol.md](sync-protocol.md)) |
| `backups.py`, `export.py`, `jobs.py`, `logs.py` | Backups, "Your data" export, scheduled jobs, the log file |
| `frontend.py` | Serves the built web app next to the API |

### Web app: `frontend/`

SvelteKit with the static adapter. Rules for screens are in `frontend/CLAUDE.md`.

| Where | What it does |
| --- | --- |
| `frontend/src/routes/(app)/` | The signed-in screens: today, plan, recipes, shopping, pantry, batch-cook, settings, onboarding |
| `frontend/src/routes/(auth)/` | Sign-in, first-run setup, joining a household |
| `frontend/src/routes/auth/`, `routes/dev/gallery/` | The single sign-on return page; a component gallery used by tests (left out of the image, see the `image: no gallery` step in `./check`) |
| `frontend/src/lib/components/` | Shared pieces (buttons, switches, sheets, tabs, ...) |
| `frontend/src/lib/client/` | Typed calls to `/api/v1` |
| `frontend/src/lib/offline/`, `lib/shopping/` | The phone's offline store (IndexedDB, through the `idb` library) and the queue of waiting list changes |
| `frontend/src/lib/*.svelte.ts` | Shared screen state (Svelte runes) |
| `frontend/src/service-worker/index.ts` | The service worker: keeps the app files, answers the version check itself |
| `frontend/src/lib/styles/` | Theme and styles (light and dark; fonts bundled, no CDN) |

### Other folders

| Where | What it does |
| --- | --- |
| `e2e/` | Playwright browser tests (`e2e/tests/*.spec.ts`), the test server, `test-map.json` ([browser-tests.md](browser-tests.md)) |
| `backend/tests/` | Backend tests (pytest) |
| `backend/scripts/` | Scripts `./check` runs: licence allow list, no-telemetry test, the test server |
| `docs/` | Spec, build plan, install and upgrade guides, mockups; `docs/dev/` for developers |
| `check`, `Dockerfile`, `compose.example.yaml` | The check script, the image, an example install |
| `.github/workflows/` | CI for GitHub (`check.yml`, `release.yml` from 1.0, and the manual `trial-image.yml` for the 0.9.5 trial image), switched off on Forgejo ([move-to-github.md](move-to-github.md)) |

## Rules that hold everywhere

These come from `CLAUDE.md` and the spec. Tests enforce most of them.

- **Every table has `household_id`.** One household can never read or change another's data; another household's id is a 404.
- **Every schema change is an Alembic migration** in `backend/src/mealwright/migrations/versions/`. They run at start-up, after a safety copy of the database. A test upgrades saved databases from earlier tags (`backend/tests/test_upgrade_from_tags.py`).
- **API-first.** The web app uses only the public `/api/v1`. No private endpoints. The offline sync protocol is part of the API. Conventions and errors: [api-endpoints.md](api-endpoints.md).
- **The outbound gate.** Every outgoing request goes through `mealwright.outbound`, blocked unless its Privacy switch is on. Never call `httpx`, `requests`, `urllib` or sockets directly. `backend/tests/test_outbound.py` and `test_telemetry.py` fail if you do, and `network_guard.py` refuses stray connections while the app runs.
- **No telemetry, no location, no CDNs or third-party assets at runtime.** Fonts, icons and scripts are bundled; the CSP in `security.py` stays strict. Recipe photos are downloaded and kept locally.
- **Words on screen** say "ingredient"; the API says "food". Check wording in [words.md](words.md).
- **Amounts** are stored as whole thousandths of a base unit (g, ml, count). The server sends the as-sold wording ready made; screens never rebuild it ([api-endpoints.md](api-endpoints.md) sections 2 and 5).

## Data on disk

Everything is in the folder mounted at `/data` (`MEALWRIGHT_DATA_DIR`). Files are mode 0600, folders 0700, owned by UID 10001 ([hardening.md](../hardening.md)).

| Path under `/data` | What it is | Made by |
| --- | --- | --- |
| `mealwright.db` (and `-wal`, `-shm`) | The SQLite database | `config.py`, `db.py` |
| `photos/<household id>/` | Recipe photos (cleaned copies only; the upload is never kept) | `photos.py` |
| `backups/` | Mealwright's own database backups (daily by default, last 7) | `backups.py` |
| `logs/mealwright.log` | Errors and sign-ins only; put aside daily, 14 days kept | `logs.py` |
| `secret.key` | The key that encrypts stored secrets (never in the database) | `secret_box.py` |

Restoring and upgrading: [restore.md](../restore.md), [upgrade.md](../upgrade.md), [backups.md](../backups.md).

## Sign-in

Summary of `auth.py`, `sso.py` and `api_tokens.py`; the spec's section 7 has the decisions.

- **Passwords** are hashed with Argon2. A sign-in is a random token in an HttpOnly cookie (`__Host-` prefix in https mode); only its SHA-256 is stored. Wrong guesses slow down a username. Writes from a browser must come from the same origin.
- **Single sign-on** (OIDC) with the household's own identity provider. Every request to the provider goes through the outbound gate, under its own Privacy switch. The provider's client secret and refresh tokens are stored encrypted (`secret_box.py`). Setup: [sso.md](../sso.md).
- **API tokens** (`mw_ro_...` read only, `mw_rw_...` read and change) are sent as `Authorization: Bearer`, to `/api/v1` only; only their SHA-256 is stored. See [api.md](../api.md).
- **First run:** while nobody has set Mealwright up, the server prints a one-time setup code in its own log, and the first-admin form needs it (`setup_code.py`). A locked-out only-admin uses `python -m mealwright reset-admin <username>` inside the container.

## Offline sync

The shopping list works offline. Each change is a small action with its own random id. The phone queues actions in IndexedDB and sends them when it can; the server applies them in the order it receives them, numbering each with a counter, and ignores a repeated id. Online use is the same path with a queue that empties at once. Only the server changes the pantry. Open screens hear about changes over `/api/v1/events` and then ask for "changes since N". Code: `sync.py`, `events.py`, `frontend/src/lib/offline/`, `frontend/src/lib/shopping/`. Full contract: [sync-protocol.md](sync-protocol.md) (read its "Map of this file" first).

## Tests and `./check`

| Kind | Where | Run by |
| --- | --- | --- |
| Backend (pytest, Hypothesis, `-n` workers) | `backend/tests/` | `./check`, or `uv run pytest` in `backend/` |
| Frontend unit tests (Vitest) | `frontend/src/**/*.test.ts` | `./check`, or `npm test` in `frontend/` |
| Browser tests (Playwright: desktop, phone, WebKit) | `e2e/tests/*.spec.ts` | `./check` only; see [browser-tests.md](browser-tests.md) |
| Outbound gate / no telemetry | `backend/tests/test_outbound.py`, `test_telemetry.py`, `backend/scripts/check_no_telemetry.py` | `./check` |
| Upgrade from earlier tags | `backend/tests/test_upgrade_from_tags.py`, `backend/tests/upgrade/` | `./check` |

`./check` is the one command that replaces CI during 0.x: lint, types, all tests, licence allow list, scanners when libraries change, the image build and its checks. Its steps and settings are in [build-and-release.md](build-and-release.md). A new test file must also be added to `e2e/test-map.json`; `node scripts/test-map.mjs validate`, run from `e2e/`, fails if one is missing.

## Other dev docs

[build-and-release.md](build-and-release.md) · [sync-protocol.md](sync-protocol.md) · [api-endpoints.md](api-endpoints.md) and [api-0.4-recipes.md](api-0.4-recipes.md) · [recipe-import.md](recipe-import.md) · [ingredient-reader.md](ingredient-reader.md) · [conversions.md](conversions.md) · [browser-tests.md](browser-tests.md) · [performance.md](performance.md) · [dev-tools-privacy.md](dev-tools-privacy.md) · [words.md](words.md) · [test-on-homelab.md](test-on-homelab.md) · [move-to-github.md](move-to-github.md) · [forgejo-runner.md](forgejo-runner.md) (on hold)
