# Traefik

Traefik sets `X-Forwarded-For`, `-Proto` and `-Host` itself. A visitor's own copies are dropped unless you list the visitor's network under `forwardedHeaders.trustedIPs`, so leave that out.

Compose, with Traefik's settings as command flags and Mealwright's as labels. Don't publish port 8080:

```yaml
services:
  traefik:
    image: traefik:v3.4
    command:
      - --providers.docker=true
      - --providers.docker.exposedbydefault=false
      - --entrypoints.web.address=:80
      - --entrypoints.web.http.redirections.entrypoint.to=websecure
      - --entrypoints.websecure.address=:443
      - --certificatesresolvers.le.acme.tlschallenge=true
      - --certificatesresolvers.le.acme.email=you@example.com
      - --certificatesresolvers.le.acme.storage=/letsencrypt/acme.json
    ports: ["80:80", "443:443"]
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./letsencrypt:/letsencrypt
  mealwright:
    image: mealwright:<version>
    volumes:
      - ./data:/data
    environment:
      # The Docker network Traefik and Mealwright share (docker network inspect <network>).
      MEALWRIGHT_TRUSTED_PROXIES: "172.18.0.0/16"
    labels:
      - traefik.enable=true
      - traefik.http.routers.mealwright.rule=Host(`mealwright.example.com`)
      - traefik.http.routers.mealwright.entrypoints=websecure
      - traefik.http.routers.mealwright.tls.certresolver=le
      - traefik.http.services.mealwright.loadbalancer.server.port=8080
```

Traefik can read the Docker socket, which is a lot of power: some people put a socket proxy in front of it. For a home network with no public name, give Traefik your own certificate with the file provider instead of Let's Encrypt.

**Tested:** `scripts/test-proxies.sh traefik` (Traefik v3.4, own certificate through the file provider, Mealwright reached by a file-provider route rather than Docker labels): HTTPS answers, sign-in sets the `__Host-` cookie, Mealwright logs the visitor's address (not Traefik's), the right host name is seen, and no "not trusted" warning. The Docker labels and Let's Encrypt lines above were not run: they need the Docker socket and a public name.
