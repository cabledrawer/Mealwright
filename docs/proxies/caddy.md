# Caddy

Caddy gets and renews a real certificate by itself for a public name. It sets `X-Forwarded-For`, `-Proto` and `-Host` itself, replacing any a visitor sent.

`Caddyfile`:

```
mealwright.example.com {
	reverse_proxy mealwright:8080
}
```

Mealwright's own settings are in `compose.example.yaml` (copied to `compose.yaml`; see [install.md](../install.md)), including the fixed Docker network `172.28.10.0/24` that `MEALWRIGHT_TRUSTED_PROXIES` names. Add Caddy to the same file, so it joins that network. Add only this, and don't publish port 8080:

```yaml
services:
  caddy:
    image: caddy:2.10-alpine
    ports: ["80:80", "443:443"]
    volumes:
      - ./Caddyfile:/etc/caddy/Caddyfile:ro
      - caddy_data:/data
volumes:
  caddy_data:
```

On a home network with no public name, use `tls internal` inside the site block: Caddy then makes its own certificate, and you install its root certificate on your devices (`/data/caddy/pki/authorities/local/root.crt` in the Caddy container).

**Tested:** `scripts/test-proxies.sh caddy` (Caddy 2.10, `tls internal`): HTTPS answers, sign-in sets the `__Host-` cookie, Mealwright logs the visitor's address (not Caddy's), the right host name is seen, and no "not trusted" warning.
