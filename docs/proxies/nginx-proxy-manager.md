# Nginx Proxy Manager

Nginx Proxy Manager (NPM) is nginx with a web page to set it up. Open its admin page and add a proxy host.

**Details tab**

1. Domain Names: `mealwright.example.com`.
2. Scheme `http`, Forward Hostname / IP: the name or address of the Mealwright container (for example `mealwright`, if NPM and Mealwright share a Docker network), Forward Port `8080`.
3. Turn on Websockets Support (harmless; Mealwright's live updates use a plain long-lived request) and leave Cache Assets off.

**SSL tab**

1. SSL Certificate: Request a new SSL Certificate (Let's Encrypt), or pick one you added under SSL Certificates.
2. Turn on Force SSL and HTTP/2 Support. Leave HSTS off here: Mealwright sends its own.

**Advanced tab**, in the Custom Nginx Configuration box:

```
proxy_set_header X-Forwarded-Host $host;
```

NPM already sends `X-Forwarded-For`, `X-Forwarded-Proto` and the host itself. It leaves `X-Forwarded-Host` to you, so add that line (see [nginx](nginx.md)).

**Mealwright's side:** put NPM on the Docker network from `compose.example.yaml` (`172.28.10.0/24`, which `MEALWRIGHT_TRUSTED_PROXIES` already names there), or set `MEALWRIGHT_TRUSTED_PROXIES` to NPM's own address. Don't publish port 8080.

**What was tested:** Nginx Proxy Manager itself was not started. It writes nginx's configuration from the screens above, so `scripts/test-proxies.sh npm` runs nginx with the proxy headers as Nginx Proxy Manager writes them (`Host`, `X-Forwarded-For` appended to, `X-Forwarded-Proto`) plus the line from the Advanced box, and checks that HTTPS answers, sign-in sets the `__Host-` cookie, Mealwright logs the visitor's address (not the proxy's), the right host name is seen, and no "not trusted" warning appears. If your Nginx Proxy Manager version writes its headers differently, tell us.
