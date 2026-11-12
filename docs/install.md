# Installing Mealwright behind HTTPS

Mealwright is meant to sit behind your own reverse proxy, which provides HTTPS. This page says why, what to set, and where the short, tested examples are.

## Why HTTPS is needed

A web page on a plain `http://` address (anything not `localhost`) can be read and changed by anyone on the network path. Browsers therefore switch off the features that matter most here:

- **Signing in from other devices.** Mealwright's sign-in cookie is marked HTTPS-only (its name starts with `__Host-`). Over plain `http://` the browser would drop it, and you'd seem to sign in and be signed straight out. Mealwright refuses the sign-in and says why instead. Your password would also cross the network in the clear.
- **The installable app.** Adding Mealwright to a home screen needs HTTPS.
- **Offline shopping.** The offline helper (a service worker) that keeps your shopping list on the phone only runs over HTTPS.
- **Keep-screen-awake while you cook.** Browsers allow it only on HTTPS pages.

`localhost` counts as secure, so trying Mealwright on the same computer needs no HTTPS. On any other plain `http://` address, the web app shows a "not secure" note saying what won't work.

For a test on a network you trust, the admin can set `MEALWRIGHT_ALLOW_PLAIN_HTTP=true`. Sign-in then works over plain HTTP, with the password and cookie unprotected, and Mealwright logs a warning at start-up. Don't use it for anything you rely on.

## Give Mealwright its own host name

Use a host name of its own, such as `mealwright.example.com`, not a path on a shared name and not a bare address.

Every answer from Mealwright tells the browser to use only `https` for that host name for a year (HSTS). The rule covers every port on the name, not only the one Mealwright answers on. If another service on the same name still uses plain `http://` on a different port, the browser will stop opening it. Sub-domains are not affected (no `includeSubDomains`, no `preload`). A name of its own avoids all of that.

## Tell Mealwright which proxy to trust

Behind a proxy, every request reaches Mealwright from the proxy's address. The proxy adds headers saying who the visitor really is:

- `X-Forwarded-For`: the visitor's address.
- `X-Forwarded-Proto`: `https`.
- `X-Forwarded-Host`: the name the browser used (`mealwright.example.com`).

Mealwright believes these only from the proxies you list in `MEALWRIGHT_TRUSTED_PROXIES`: addresses or networks, comma-separated. Use the proxy's address, or the range of the Docker network it shares with Mealwright (`docker network inspect <network>` shows it), for example `172.18.0.0/16`.

- **Unset (the default):** Mealwright believes nobody's headers. Every visitor looks like the proxy, so a few wrong passwords from one person slow sign-in down for the whole household. Mealwright logs "A request came through a reverse proxy…" once after it starts.
- **Too wide (`*`, or a range that includes machines other than your proxy):** anyone who can reach Mealwright directly can claim to be any address and dodge the sign-in slow-down. Keep it to the proxy. Don't publish Mealwright's own port (8080) on the network; let only the proxy reach it.

The proxy must set `X-Forwarded-Host` itself, replacing any a visitor sent. Caddy and Traefik do. nginx and Nginx Proxy Manager need the line shown in their examples.

## Examples

Each one shows HTTPS, the three headers and the matching `MEALWRIGHT_TRUSTED_PROXIES`:

- [Caddy](proxies/caddy.md)
- [Traefik](proxies/traefik.md)
- [nginx](proxies/nginx.md)
- [Nginx Proxy Manager](proxies/nginx-proxy-manager.md)

Live updates (a second phone seeing a tick at once) use one long-lived request, `/api/v1/events`. Mealwright sends `X-Accel-Buffering: no`; if your proxy buffers responses, switch that off for `/api/v1/events`.

`example.com` and `192.0.2.x` are documentation values: use your own name and addresses.

## What was tested

`scripts/test-proxies.sh` starts Mealwright and a proxy (nginx, Traefik or Caddy) in throwaway Docker containers with a self-signed certificate, and checks through the proxy that the app answers on HTTPS, that sign-in sets the `__Host-` cookie, that Mealwright sees the visitor's address and the right host name, and that it logs no "not trusted" warning. Each proxy page says exactly what was tested for it.
