# Mealwright

Self-hosted meal planning, pantry and shopping for your household. Private by design: no telemetry, nothing leaves your server unless you switch it on, or press Check now in About.

Recipe → plan → shopping list → pantry → cook. Plan meals and batch cooks, get a shopping list built from what's actually missing, and keep the pantry up to date as you shop and cook.

## Status

Early development. Versions 0.x are not published: there is no public image or release yet. The first public release will be 1.0.0.

## Privacy

Mealwright collects nothing. No telemetry, analytics or crash reporting, not even opt-in. It never asks for your location. It has no account with the developer and never phones home.

The built-in telemetry of the libraries Mealwright uses is switched off (FastAPI's OpenTelemetry support included), and the tests check that no telemetry exporter is installed, in the code and in the Docker image.

Outbound connections happen only when you switch them on in Settings → Privacy. Every one of them goes through a single gate in the code, which checks its switch first, and while Mealwright runs any other attempt to connect out, or even to look up an address, is refused. The full list of every possible outbound connection will be written here before 1.0.0.

## HTTPS required

Run Mealwright behind your own reverse proxy (Caddy, Traefik, nginx, Nginx Proxy Manager…) that provides HTTPS. Browsers only allow signing in from other devices, installing the app, offline shopping and keep-screen-awake over HTTPS. On a plain `http://` address, Mealwright says so instead of failing. Live updates (a second phone seeing a tick at once) use one long-lived request, `/api/v1/events`. Mealwright sends `X-Accel-Buffering: no` for nginx-style proxies; if you've turned response buffering on elsewhere, switch it off for `/api/v1/events` or live updates will arrive late. The install guide ([docs/install.md](docs/install.md)) says why, and has short, tested examples for [Caddy](docs/proxies/caddy.md), [Traefik](docs/proxies/traefik.md), [nginx](docs/proxies/nginx.md) and [Nginx Proxy Manager](docs/proxies/nginx-proxy-manager.md).

**Installing and offline.** The app can be added to your phone's or computer's home screen, only over HTTPS: browsers don't allow installing or offline use on a plain `http://` address (except `localhost`). Your shopping list works offline: once you've opened it while connected, the device keeps a copy, and what you tick or add with no connection is kept on the device and sent when you're back ("Offline — 3 changes waiting", then "Back online — all saved"). Pantry, Ingredients and Settings still need your server, and say so. Signing out removes the household's data from the device, and warns you first if changes haven't been sent yet. On an iPhone, Safari can clear a website's offline data after about 7 days without use; adding Mealwright to the Home Screen helps. The offline helper (service worker) keeps only the app's own files (its code, fonts and icons); the list copy and the changes waiting are kept in the browser's own storage on the device, never in its web cache.

## Single sign-on

Mealwright can sign people in through your own sign-in server (Settings → Sign-in → Single sign-on, on a computer). Taking an admin out at your sign-in server doesn't stop their API tokens on its own: make them a Member or remove them in Settings → Household.

**Removing someone (cabledrawer 12 Nov):** first make sure another admin can get in (a working password, or their own single sign-on), then remove them in Settings → Household. Disabling them only at the sign-in server isn't enough while they're the only admin: Mealwright keeps the only admin signed in so the household isn't locked out, and that admin keeps every admin power. They can't simply keep an API token that never stops, but they can still change the setup or give someone else an admin login. The real fix is at the sign-in server, or a second admin.

## Troubleshooting

**Setting up: where's the setup code?** The first time Mealwright starts, before anyone has an account, it prints a setup code in its log, and the first-run page asks for it, so only someone who can read the server's log can create the admin account. Run `docker logs mealwright` (use your container's name) and look for "setup code". A new code is made each time Mealwright restarts until the admin account exists.

**The only admin forgot their password.** Another admin can't see passwords, so run this on the server (use your container's name and the admin's username):

```
docker exec -it mealwright python -m mealwright reset-admin tess
```

It sets a new random password for that admin, prints it once, and signs that admin out on every device. For ten minutes after, the new password gets in even while someone is guessing at that username. It also forgets the devices that had signed in as that admin before. Sign in with it, then change it in Settings → Sign-in → Change password. It works only for an admin.

**A phone or computer was lost or stolen.** In Settings → Sign-in, sign that device out, then change your password: that also forgets it as a known device, so it can no longer skip the pause after wrong passwords. Signing it out alone leaves it known until the password changes.

**Behind a reverse proxy, everyone is slowed down after one person's wrong passwords.** Mealwright logs "A request came through a reverse proxy…" once after it starts. Set `MEALWRIGHT_TRUSTED_PROXIES` to your proxy's address or network (for example `172.28.10.0/24`) and restart: Mealwright then believes the proxy's `X-Forwarded-For`, `X-Forwarded-Proto` and `X-Forwarded-Host` headers, and nobody else's.

**The proxy must set `X-Forwarded-Host` itself.** Mealwright believes a trusted proxy's `X-Forwarded-Host`, so the proxy must replace any that a visitor sends, not pass it on. Caddy and Traefik do this themselves. In nginx and Nginx Proxy Manager (in the proxy host's Advanced tab), add:

```
proxy_set_header X-Forwarded-Host $host;
```

Mealwright uses the host name only to check that a request came from its own pages; it never builds links from it.

**The sign-in page says the phone couldn't delete its offline copy, and Try again doesn't help.** First close any other Mealwright tabs and restart the browser, then press Try again. If it still won't go, clear this site's data in the browser's settings. That removes the offline copy of the household and anything still waiting to be sent on that phone (nothing on the server is touched). Then sign in again.

## Licence

[AGPL-3.0](LICENSE).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). To report a security problem, see [SECURITY.md](SECURITY.md).

Mealwright is a spare-time project, so replies may take a week or so.

Parts of Mealwright are written with AI help (Claude Code). Every change is reviewed and signed off by the maintainer.
