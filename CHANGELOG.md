# Changelog

All notable changes to Mealwright are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Version numbers follow the plan in `docs/spec.md` section 8: 0.N.0 per build milestone (not published), then MAJOR.MINOR.PATCH from 1.0.0.

## [Unreleased]

## [0.1.1] - 2026-10-17

### Fixed

- **Sign-in shows the real wait** after too many wrong passwords: "30 seconds" at first, then 1 minute, 2 minutes and so on, up to 15 minutes. It used to say "1 minute" when the wait was 30 seconds. (Found by cabledrawer while testing 0.1.0.)

## [0.1.0] - 2026-10-17

Milestone 0.1, Foundation: an empty but real Mealwright you can install, sign in to and click around, with the safety rails built in. Not published; for testing on cabledrawer's homelab.

### Added

- **One Docker image** with the web app and its API. It runs as an unprivileged user (UID 10001), keeps everything in `/data`, has a health check, and contains no `pip`. `compose.example.yaml` shows how to run it behind a reverse proxy.
- **First run:** the first visitor creates the admin account (there's no default admin), then the app opens.
- **Sign in and out**, with "Remember this device" for 30 days. Passwords need at least 10 characters and are stored scrambled (Argon2). After 5 wrong guesses, sign-in slows down, per account and per real address, so one person's guesses don't slow down anyone else.
- **The app shell:** bottom tabs on phone and a collapsible sidebar on desktop, with empty Today, Plan, Shopping, Pantry and Recipes pages and a Settings page with Sign out.
- **Auto · Light · Dark** in plain sight, saved to your account. A designed dark theme, with fonts bundled.
- **One switch component** for every on/off.
- **API** under `/api/v1`, described at `/api/v1/openapi.json`. `GET /api/v1/version` reports the version for update tools such as Diun.
- **Database changes are applied on start-up** (migrations: household, Privacy switches, logins and sessions).
- **`./check`** runs every check before each pull request: lint, types, tests, browser tests, licence allow list, pip-audit, osv-scanner, Bandit, and Trivy plus a no-telemetry check on the image.
- Licence (AGPL-3.0), README, contributing guide, security policy, this changelog, and the homelab testing guide (`docs/dev/test-on-homelab.md`).

### Privacy and security

- **The outbound gate:** the only way Mealwright connects to anything outside your server. Each kind of connection has its own Privacy switch, and **all of them are off**. While the app runs, any other connection or address lookup is refused, whether it comes from our code or a library.
- **No telemetry:** FastAPI's built-in telemetry is switched off, and no telemetry package is installed (checked in the code and in the image).
- **Strict browser rules (Content Security Policy):** pages load files only from your own server. A real-browser test proves an outside script is blocked. Location, camera and microphone are off; referrers aren't sent.
- **Logs** hold only sign-ins and errors, never what people view or search for (the web server's request log is off).
- **HTTPS is required for sign-in.** On a plain `http://` address, Mealwright says so instead of failing silently; `MEALWRIGHT_ALLOW_PLAIN_HTTP` allows it for testing, with a warning.
- **Works behind any reverse proxy.** Its forwarded headers are believed only from `MEALWRIGHT_TRUSTED_PROXIES` (off by default).
- Requests from other sites are refused, and the session cookie can't be read by scripts and is stored only as a fingerprint.

[Unreleased]: https://git.example.org/tess/mealwright/compare/v0.1.1...main
[0.1.1]: https://git.example.org/tess/mealwright/src/tag/v0.1.1
[0.1.0]: https://git.example.org/tess/mealwright/src/tag/v0.1.0
