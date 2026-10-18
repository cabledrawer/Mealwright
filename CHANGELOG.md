# Changelog

All notable changes to Mealwright are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/). Version numbers follow the plan in `docs/spec.md` section 8: 0.N.0 per build milestone (not published), then MAJOR.MINOR.PATCH from 1.0.0.

## [Unreleased]

### Added (0.3, pull request 5)

- **Live updates.** A second phone or window sees a tick, an added item or a pantry change within a moment, without reloading. They come from your own Mealwright server only (`GET /api/v1/events`, Server-Sent Events); the stream carries numbers, never names. An open screen doesn't count as activity, so the 12-hour sign-out still happens; a kitchen tablet should use "Remember this phone".
- **Installable app.** A manifest, icons made from the brand icon, and a service worker that keeps only the app's own files, so the app's own files (its code, fonts and icons) load without a connection. The screens still need your server, so opening the app cold with no connection shows an error; showing saved lists while offline comes in the next pull request. It never keeps anything from the server (`/api`) and never updates itself mid-use: a new version starts the next time every window has been closed. No Install button yet.
- **Connection bar.** "Offline" with Try now on every page (above the tabs on a phone, at the foot of the sidebar on desktop), a short "Back online" toast, and "12 to buy · offline" on Shopping. A blip under 3 seconds shows nothing. The "N changes waiting" wording is ready for the offline queue in the next pull request.

## [0.2.1] - 2026-10-18

Fixes from cabledrawer's hand test of 0.2.0, plus a few small Pantry improvements from his friction log. Not published; for testing on cabledrawer's homelab.

**Before you install it: back up your data.** This version changes the database (one small addition), and the old version can't read a database the new one has changed. On the server (from `docs/dev/test-on-homelab.md`, section 5):

```bash
cd ~/mealwright
docker compose stop mealwright
sudo tar -C ~/mealwright --exclude=data/logs -czf "backups/data-0.2.0-$(date +%Y%m%d-%H%M).tar.gz" data
ls -lh backups/
```

- `cd` goes to the Mealwright folder.
- `docker compose stop mealwright` stops the app, so the database file is copied in one piece.
- The `tar` line makes a dated, compressed copy of the `data` folder in `backups/`, leaving out the log folder.
- `ls -lh backups/` shows the new file; it should be there and not tiny.

To go back, follow section 6 of the same file (restore that backup and set the image tag back to 0.2.0).

### Fixed

- **Pantry search finds other names.** Typing "thuvaram" in "Find in pantry" now finds Toor dal, the same way Recipes › Ingredients does (one shared piece of matching code). The count at the top of each place now matches what is shown.
- **Recent changes "before → after" counts what was already there.** "Added 1 pack Paneer" with 200 g already in the Fridge now reads "1 pack · 200 g → 2 packs · 400 g", not "0 g → 1 pack · 200 g". The same for Used, and for the "Undid:" lines. Each new change saves the whole amounts it saw, so the line stays right after later changes. Undo itself is unchanged; tests now check it puts back exactly the right amounts. Changes recorded before 0.2.1 keep their old wording (the packets that change touched).
- **"+ Staple" can make a new ingredient.** Type a name nobody has used and choose "+ New ingredient: …"; it is made with Staple on and no stock is recorded.
- **A size needs a name with letters in it** ("packet", "tub", "dozen"). "1" is refused on screen and by the server, with "Give the size a name, like tub or packet." The Name box now hints "packet, tub, dozen…".
- **A full, unopened pack has the ¼ · ½ · ¾ · Full choices** in its menu too (Full is ticked), not only once it is open.
- **Undoing an older "Used" for a removed ingredient says so:** "Undone: Used about ½ tub Yogurt. Yogurt is back in Ingredients, with ½ tub in the Fridge."

### Changed

- **Add to pantry** has a "Today" use-by choice next to No date, +3 days, +1 week and Pick a date.
- The grey example in the amount box suits the unit (200 for g, 1 for kg or a size, 250 for ml, 6 for items).
- In an opened pantry row, "Used" (and "Save" for counted foods) stays greyed out until an amount is typed.
- The pack lines in an opened pantry row ("1 pack · 200 g · use by today") show an arrow and a press colour, so it is clear they open the pack menu.

### Database

- One migration: two empty columns on `change_line` (`total_before_milli`, `total_after_milli`) hold the whole amounts a change saw. Nothing is rewritten. Checked by a test that builds a 0.2.0 database with real-looking data, upgrades it, and also goes back down and up again.

## [0.2.0] - 2026-10-17

Milestone 0.2 (Ingredients, pantry, history and undo): the shared ingredient list, a pantry that counts things the way they're sold, and Undo for every change. Not published; for testing on cabledrawer's homelab.

### Added

- **Ingredients** (Recipes › Ingredients): one list of everything you buy and cook with, shared by recipes, the pantry and (from 0.3) shopping. Search finds an ingredient by any of its names. Filters: All · Staples · Maybe the same.
- **The ingredient editor**, the same one from anywhere: a side panel on desktop, a sheet on phone. Everything saves as you go:
  - name and other names ("thuvaram paruppu", "arhar dal");
  - how it's counted (by weight, by volume, one by one) and how it's sold ("Packet = 500 g", one marked Usual);
  - weight of 1 cup or of one, running low at, where it lives, usual shop ("+ Shop" adds one), Staple;
  - "Can use instead".
- **Merge** two ingredients into one (their stock and sizes move across), **split** a name back out, and "**Not the same**" for a "Maybe the same" hint. The server decides which ingredient of a pair would be merged away.
- **"Remove from Ingredients"**, only when nothing depends on the ingredient (today: nothing in the pantry). After the 7 days of Undo it's deleted for good, with its monthly history totals. An Undo that would put stock back into a removed ingredient brings it back and says so.
- **Pantry:** places as tabs on phone (All · Fridge · Freezer · Cupboard · More, with Use soon under More) and as four columns beside a side panel on desktop.
  - Amounts **as sold**: "1½ packets · about 750 g", "9 left · bought as a dozen".
  - Each packet is kept with its own use-by date, the oldest is used first, and stock never goes below zero.
  - Tap a packet for Used · Binned · To freezer · Move to… · Change use-by date…, and ¼ · ½ · ¾ · Full for an open pack.
  - "Used some" and "How many left?" (type 0 when it's all gone) for a whole ingredient.
  - **"+ Add to pantry"**: what, how much, where, use by.
- **Use soon:** anything with a use-by of today, tomorrow or the day after (or already past), in the household's local time, with Used · Binned · To freezer.
- **Staples:** assumed in stock and never counted; shown as chips.
- **Recent changes** with Undo: what each change did, one line per ingredient ("Paneer: 0 g → 2 packs · 400 g").
- **Undo for every ingredient and pantry change**, by anyone in the household, for 7 days ("Not the same" and adding a shop aren't undone): the Undo toast, and Ctrl+Z / Cmd+Z on desktop. Inside a text box, Ctrl+Z undoes your typing instead. If something has been used since, Undo puts back what it can and says so.
- **Instant changes:** the screen updates straight away and saves in the background. If saving fails, it goes back and says "Couldn't save — try again".
- **"Ask once":** when Mealwright needs a weight it doesn't know ("About how much does 1 cup of Toor dal weigh?"), it asks once and can remember the answer. Your answers always beat the built-in table.
- **A built-in conversion table** of 221 common ingredients from USDA FoodData Central, SR Legacy (public domain, CC0 1.0). Credit: "Food conversion data: U.S. Department of Agriculture, Agricultural Research Service. FoodData Central, SR Legacy, 2018. fdc.nal.usda.gov."
- **Places** Fridge, Freezer, Cupboard and Spice rack, added to every household.
- **History:** pantry changes older than 12 months are summarised as monthly totals by a background job (at start-up and every hour), so it also works on a server that's off at night.
- **API** under `/api/v1` for ingredients, places, shops, the pantry, changes and Undo, with safe retries (`Idempotency-Key`). It's described in `docs/dev/api-0.2.md` and the OpenAPI document.

### Changed

- **"Ingredient", never "food", on screen** (cabledrawer's rule). A test fails if "food" appears in any on-screen text or server message.
- **Names appear exactly as typed** everywhere, screen-reader labels included.
- **The household's time zone and cup size** are taken once from an admin's browser (never from location) and never changed silently. No `TZ` setting is needed. "Weight of 1 cup" follows the household's cup: 240 ml for a US English browser, otherwise 250 ml.
- **The nightly log tidy** from 0.1.1 now runs on the app's scheduler (APScheduler). It still keeps 14 days, and catches up if the server was asleep at midnight.
- **Recipes** in the desktop sidebar is a tree: All recipes · Drafts · Ingredients. Drafts is empty until 0.5.

### Privacy and security

- No new outside connections. The conversion table is bundled; the app never fetches it.
- Nothing about what people cook or buy is written to the log.
- One household can never see or change another's ingredients, places, shops, pantry or changes (tested on every endpoint).

### For developers

- New dependencies: **APScheduler 3.11.3** and **tzlocal 5.4.4** (MIT, ship in the image). For tests only: **Hypothesis** (MPL-2.0) with sortedcontainers (Apache-2.0), and **@axe-core/playwright** with axe-core (MPL-2.0).
- `./check` allows 0BSD, Unlicense, CC0-1.0 and Zlib for development-only packages (cabledrawer's standing rule), and `CHECK_IMAGE` lets two copies run at once.
- Accessibility checks (axe in light and dark, 44 px targets, no sideways scroll) run in the browser tests, and there's a screenshot tool for mockup reviews (`e2e/review/`).

## [0.1.1] - 2026-10-17

### Fixed

- **Sign-in shows the real wait** after too many wrong passwords: "30 seconds" at first, then 1 minute, 2 minutes and so on, up to 15 minutes. It used to say "1 minute" when the wait was 30 seconds. (Found by cabledrawer while testing 0.1.0.)
- **Every sign-in is logged**, including the one at first setup, which signs the admin in. A test checks there is exactly one "Signed in" line per sign-in. (Found by cabledrawer.)

### Changed

- **Log lines carry the time** (UTC, e.g. `2026-10-17T18:21:50Z`).
- **The app keeps its own log for 14 days**, in `/data/logs/mealwright.log`, readable by Mealwright's own user only. Just after each midnight (UTC) it starts a new file and deletes files last written more than 14 days ago, even on a quiet server. Later, "Report a problem" will read recent errors from it. **Sign-in lines go only to this file, never to the container output** (`docker logs`), because Docker can only limit its copy by size, so on a quiet server it would keep them for months. The container output now holds start-up messages, warnings and errors. `compose.example.yaml` also limits Docker's copy to 2 files of 1 MB as a safety net. Leave `data/logs` out of backups (the update backup in the homelab guide already does). (Asked by cabledrawer.)
- **The sign-in slow-down is logged** when it starts or doubles ("Sign-in slowed down for tess from 192.168.1.20 (wait 30 s)"). Each refused try isn't logged, so nobody can fill the disk by hammering the sign-in page. (Asked by cabledrawer.)
- The sign-in slow-down no longer keeps memory for usernames and addresses that were only looked up.

### Privacy and security

- **A blocked outside connection is logged in plain words and names only the switch** ("recipe import is switched off"), never the site or address, which could show what someone was cooking. A test checks it. (Asked by cabledrawer.)
- **Database errors no longer show what people typed.** Such an error's text used to include the values in the query (for example a typed username), and it would reach the log as part of the error. The values are now hidden. (Found by the review of this patch.)
- **Usernames that don't exist aren't written to the log.** Someone who types their password into the username box would otherwise have it logged. The log says "unknown user" instead. (Found by cabledrawer.)

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

[Unreleased]: https://git.example.org/tess/mealwright/compare/v0.2.0...main
[0.2.0]: https://git.example.org/tess/mealwright/src/tag/v0.2.0
[0.1.1]: https://git.example.org/tess/mealwright/src/tag/v0.1.1
[0.1.0]: https://git.example.org/tess/mealwright/src/tag/v0.1.0
