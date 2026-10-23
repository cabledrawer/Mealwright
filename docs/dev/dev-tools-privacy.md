# What the development tools send

Checked 17 Oct 2026, after Trivy turned out to send usage data by default (cabledrawer asked for every tool to be checked). These tools run only on the development machine (WSL) and in `./check`; none of them is part of the Mealwright app. The app itself is covered by the outbound gate and network guard (spec section 7).

**How it was checked:** each tool was run in a container on a watched network, and every address it looked up (DNS) was recorded. Each step was recorded on its own, with the same versions and settings as `./check`. Lookups show where a tool connects; they can't show what it sends, so the "what's sent" column comes from each tool's documentation and its log output.

| Tool | Version | Connects to | What's sent | Usage data or update check? | Action |
|---|---|---|---|---|---|
| **Trivy** (image scan) | 0.75.0 | nothing, with the vulnerability database cached; otherwise its database download | — | **Yes, by default:** usage data to Aqua and an update check (`check.trivy.dev`, seen in a run with defaults) | **Switched off** in `./check`: `--disable-telemetry --skip-version-check`. With them, it contacted nothing. |
| **npm** (installs packages) | 11.19 | `registry.npmjs.org` | package downloads; by default also the project's full package list (its "audit") and a check for newer npm versions (both seen in the log) | **Yes:** the update check, and the audit upload | **Switched off** in `./check` (`NPM_CONFIG_AUDIT=false`, `NPM_CONFIG_UPDATE_NOTIFIER=false`, `NPM_CONFIG_FUND=false`) and in the Dockerfile. `frontend/.npmrc` and `e2e/.npmrc` get the same settings in the frontend session's PR, so running npm by hand in those folders behaves the same. |
| **uv** (installs Python packages) | 0.13.1 | `files.pythonhosted.org` and `pypi.org` | package downloads. Like pip, uv adds standard download statistics to its requests (uv and Python versions, operating system, CPU type). | No usage data or update check. **The download statistics can't be switched off** in uv. They describe the machine type, not the project or the homelab. | None possible; accepted. |
| **pip-audit** | 2.10.1 | `pypi.org` (and `files.pythonhosted.org` the first time, to download itself) | package names and versions, to look up known vulnerabilities | No | None needed |
| **Bandit** (code scan) | 1.9.4 | nothing (PyPI only the first time, to download itself) | — | No | None needed |
| **osv-scanner** | 2.6.0 | `api.osv.dev` only | package names and versions from the lock files | No. Its program includes telemetry libraries (common in Google's Go code), but in the watched run it contacted only `api.osv.dev`. | None needed |
| **Playwright** (browser tests) | 1.63.0 | nothing while testing; the browser download (Microsoft's servers) only when installing a browser | — | No | None needed |
| **Vite / SvelteKit** (build) | 8.3.1 / 2.70.3 | nothing | — | No | None needed |
| **Vitest** (frontend tests, in Chromium) | 5.0.3 | nothing | — | No | None needed |
| **ESLint, Prettier** (lint) | 10.11.0, 3.9.9 | nothing | — | No | None needed |
| **svelte-check, TypeScript** | 4.7.6, 6.0.3 | nothing | — | No | None needed |
| **import_check.py** (real-recipe check; dev only) | our own script, `backend/scripts/import_check.py` | contacts only the recipe sites in the list kept outside the repo | a normal page request with the app's user agent ("Mealwright"); no photos | No | run by hand, never in `./check`; not in the image |

**Outside the project, for cabledrawer to switch off himself:** **Docker Desktop**, if you use it, sends usage statistics to Docker by default. To stop it: open Docker Desktop → **Settings → General** → switch off **"Send usage statistics"** → **Apply & restart**.

**When adding a tool:** check it the same way before it goes into `./check`, add it to this table, and switch off anything that sends usage data or checks for updates.
