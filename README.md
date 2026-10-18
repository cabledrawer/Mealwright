# Mealwright

Self-hosted meal planning, pantry and shopping for your household. Private by design: no telemetry, nothing leaves your server unless you switch it on.

Recipe → plan → shopping list → pantry → cook. Plan meals and batch cooks, get a shopping list built from what's actually missing, and keep the pantry up to date as you shop and cook.

## Status

Early development. Versions 0.x are not published: there is no public image or release yet. The first public release will be 1.0.0.

## Privacy

Mealwright collects nothing. No telemetry, analytics or crash reporting, not even opt-in. It never asks for your location. It has no account with the developer and never phones home.

The built-in telemetry of the libraries Mealwright uses is switched off (FastAPI's OpenTelemetry support included), and the tests check that no telemetry exporter is installed, in the code and in the Docker image.

Outbound connections happen only when you switch them on in Settings → Privacy. Every one of them goes through a single gate in the code, which checks its switch first, and while Mealwright runs any other attempt to connect out, or even to look up an address, is refused. The full list of every possible outbound connection will be written here before 1.0.0.

## HTTPS required

Run Mealwright behind your own reverse proxy (Caddy, Traefik, nginx, Nginx Proxy Manager…) that provides HTTPS. Browsers only allow signing in from other devices, installing the app, offline shopping and keep-screen-awake over HTTPS. On a plain `http://` address, Mealwright says so instead of failing. Live updates (a second phone seeing a tick at once) use one long-lived request, `/api/v1/events`. Mealwright sends `X-Accel-Buffering: no` for nginx-style proxies; if you've turned response buffering on elsewhere, switch it off for `/api/v1/events` or live updates will arrive late. Install docs with proxy examples come before 1.0.

**Installing and offline.** The app can be added to your phone's or computer's home screen, only over HTTPS: browsers don't allow installing or offline use on a plain `http://` address (except `localhost`). Your shopping list works offline: once you've opened it while connected, the device keeps a copy, and what you tick or add with no connection is kept on the device and sent when you're back ("Offline — 3 changes waiting", then "Back online — all saved"). Pantry, Ingredients and Settings still need your server, and say so. Signing out removes the household's data from the device, and warns you first if changes haven't been sent yet. On an iPhone, Safari can clear a website's offline data after about 7 days without use; adding Mealwright to the Home Screen helps. The offline helper (service worker) keeps only the app's own files (its code, fonts and icons); the list copy and the changes waiting are kept in the browser's own storage on the device, never in its web cache.

## Licence

[AGPL-3.0](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). To report a security problem, see [SECURITY.md](SECURITY.md).

Mealwright is a spare-time project, so replies may take a week or so.

Parts of Mealwright are written with AI help (Claude Code). Every change is reviewed and signed off by the maintainer.
