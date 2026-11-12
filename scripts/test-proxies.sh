#!/usr/bin/env bash
# Tries the reverse-proxy examples in docs/proxies/ for real, in throwaway containers.
#
#   scripts/test-proxies.sh [nginx|npm|traefik|caddy ...]     (default: all four)
#
# For each proxy it starts Mealwright and the proxy on a private Docker network (no host
# ports), with a self-signed certificate for mealwright.example.com, and checks through the
# proxy that: the app answers on https; setup and sign-in set the `__Host-` cookie; the
# server sees the visitor's address (a client container here), not the proxy's; the host
# name is right and a visitor's own X-Forwarded-Host is replaced (a forged one is refused
# as another site); and no "not trusted" warning is logged. It then removes what it made.
#
# `npm` runs nginx with the headers Nginx Proxy Manager writes plus the line from its
# Advanced box (Nginx Proxy Manager itself is not started).
#
# Not part of ./check. Needs docker and openssl (the client is Python from the Mealwright image), and these images (pulled from Docker
# Hub if missing). Nothing is pushed anywhere.
#   MEALWRIGHT_IMAGE  the Mealwright image to try (default mealwright:check-m1; build one
#                     with `docker build -t mealwright:check-m1 .`)
set -euo pipefail

IMAGE=${MEALWRIGHT_IMAGE:-mealwright:check-m1}
NGINX_IMAGE=nginx:1.28-alpine
TRAEFIK_IMAGE=traefik:v3.4
CADDY_IMAGE=caddy:2.10-alpine

NET=mw-m1-net
SUBNET=172.29.91.0/24
PROXY_IP=172.29.91.10
APP=mw-m1-app
PROXY=mw-m1-proxy
HOST=mealwright.example.com
PASSWORD='correct horse battery staple 42'

WORK=$(mktemp -d "${TMPDIR:-/tmp}/mw-m1-proxies.XXXXXX")
chmod 755 "$WORK"
FAILED=0

cleanup() {
  docker rm -f "$APP" "$PROXY" mw-m1-client >/dev/null 2>&1 || true
  docker network rm "$NET" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

say() { printf '%s\n' "$*"; }
ok() { say "  ok    $*"; }
bad() { say "  FAIL  $*"; FAILED=1; }
check() { # check "what it proves" command...
  local what=$1
  shift
  if "$@"; then ok "$what"; else bad "$what"; fi
}

make_certificate() {
  mkdir -p "$WORK/certs"
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 2 \
    -subj "/CN=$HOST" -addext "subjectAltName=DNS:$HOST" \
    -keyout "$WORK/certs/privkey.pem" -out "$WORK/certs/fullchain.pem" 2>/dev/null
  chmod 644 "$WORK/certs/"*.pem
}

nginx_config() { # $1 = the headers block
  cat >"$WORK/mealwright.conf" <<CONF
server {
    listen 80;
    server_name $HOST;
    return 301 https://\$host\$request_uri;
}

server {
    listen 443 ssl;
    http2 on;
    server_name $HOST;

    ssl_certificate     /etc/nginx/certs/fullchain.pem;
    ssl_certificate_key /etc/nginx/certs/privkey.pem;

    location / {
        proxy_pass http://$APP:8080;
$1
    }
}
CONF
}

start_proxy() { # $1 = which
  case $1 in
    nginx | npm)
      if [ "$1" = nginx ]; then
        # The block in docs/proxies/nginx.md.
        nginx_config "        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$remote_addr;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Host \$host;"
      else
        # What Nginx Proxy Manager writes for a proxy host (it appends to X-Forwarded-For),
        # plus the line from docs/proxies/nginx-proxy-manager.md (Advanced tab).
        nginx_config "        proxy_set_header Host \$host;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header X-Forwarded-Scheme \$scheme;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-Host \$host;"
      fi
      docker run -d --name "$PROXY" --network "$NET" --ip "$PROXY_IP" \
        -v "$WORK/mealwright.conf:/etc/nginx/conf.d/default.conf:ro" \
        -v "$WORK/certs:/etc/nginx/certs:ro" "$NGINX_IMAGE" >/dev/null
      cp "$WORK/certs/fullchain.pem" "$WORK/cacert.pem"
      ;;
    traefik)
      cat >"$WORK/dynamic.yml" <<CONF
http:
  routers:
    mealwright:
      rule: Host(\`$HOST\`)
      entryPoints: [websecure]
      service: mealwright
      tls: {}
  services:
    mealwright:
      loadBalancer:
        servers:
          - url: http://$APP:8080
tls:
  certificates:
    - certFile: /certs/fullchain.pem
      keyFile: /certs/privkey.pem
CONF
      docker run -d --name "$PROXY" --network "$NET" --ip "$PROXY_IP" \
        -v "$WORK/dynamic.yml:/etc/traefik/dynamic.yml:ro" -v "$WORK/certs:/certs:ro" \
        "$TRAEFIK_IMAGE" \
        --providers.file.filename=/etc/traefik/dynamic.yml \
        --entrypoints.web.address=:80 \
        --entrypoints.web.http.redirections.entrypoint.to=websecure \
        --entrypoints.websecure.address=:443 >/dev/null
      cp "$WORK/certs/fullchain.pem" "$WORK/cacert.pem"
      ;;
    caddy)
      printf '%s {\n\ttls internal\n\treverse_proxy %s:8080\n}\n' "$HOST" "$APP" >"$WORK/Caddyfile"
      docker run -d --name "$PROXY" --network "$NET" --ip "$PROXY_IP" \
        -v "$WORK/Caddyfile:/etc/caddy/Caddyfile:ro" "$CADDY_IMAGE" >/dev/null
      for _ in $(seq 1 30); do # wait for Caddy's own certificate authority
        docker cp "$PROXY:/data/caddy/pki/authorities/local/root.crt" "$WORK/caddy-root.crt" \
          >/dev/null 2>&1 && break
        sleep 1
      done
      cp "$WORK/caddy-root.crt" "$WORK/cacert.pem"
      ;;
  esac
}

# The visitor: a small Python client run from the Mealwright image on the same private
# network, at its own address, so the proxy has someone to report. It reaches the proxy by
# the host name, trusting only the proxy's certificate. Prints the status, then the headers.
CLIENT_IP=172.29.91.20
write_client() {
  cat >"$WORK/client.py" <<'PY'
import http.client, ssl, sys

method, path, origin, forwarded_host, body = sys.argv[1:6]
context = ssl.create_default_context(cafile="/work/cacert.pem")
conn = http.client.HTTPSConnection("mealwright.example.com", 443, timeout=15, context=context)
headers = {"Content-Type": "application/json"}
if origin:
    headers["Origin"] = origin
if forwarded_host:
    headers["X-Forwarded-Host"] = forwarded_host
conn.request(method, path, body=body or None, headers=headers)
response = conn.getresponse()
print(response.status)
for name, value in response.getheaders():
    print(f"{name.lower()}: {value}")
PY
}

# web METHOD PATH ORIGIN FORWARDED_HOST BODY > headers-file (first line is the status)
web() {
  docker run --rm --network "$NET" --ip "$CLIENT_IP" --name mw-m1-client \
    --add-host "$HOST:$PROXY_IP" -v "$WORK:/work:ro" --entrypoint python "$IMAGE" \
    /work/client.py "$@" 2>/dev/null
}

run_case() {
  local which=$1
  say "== $which"
  docker network create --subnet "$SUBNET" "$NET" >/dev/null
  # The proxy is the one address Mealwright trusts (the value the docs tell you to set).
  docker run -d --name "$APP" --network "$NET" --tmpfs /data:uid=10001,gid=10001 \
    -e MEALWRIGHT_TRUSTED_PROXIES="$PROXY_IP" "$IMAGE" >/dev/null
  start_proxy "$which"

  local up=0
  for _ in $(seq 1 60); do
    if [ "$(web GET /api/v1/version '' '' '' | head -1)" = 200 ]; then
      up=1
      break
    fi
    sleep 1
  done
  check "the app answers on https through $which" test "$up" = 1
  if [ "$up" = 0 ]; then
    docker logs "$PROXY" 2>&1 | tail -5
    docker logs "$APP" 2>&1 | tail -5
    return
  fi

  local code
  code=$(docker logs "$APP" 2>&1 | sed -n 's/.*type this setup code: \([A-Z0-9-]*\).*/\1/p' | head -1)
  check "the setup code is in the app's log" test -n "$code"

  # A forged X-Forwarded-Host (with a matching Origin) must be replaced by the proxy, so the
  # request is refused as coming from another site.
  web POST /api/v1/session https://evil.example.org evil.example.org \
    '{"username":"x","password":"x"}' >"$WORK/forged.out"
  check "a visitor's own X-Forwarded-Host is not believed (got $(head -1 "$WORK/forged.out"), want 403)" \
    test "$(head -1 "$WORK/forged.out")" = 403

  web POST /api/v1/setup "https://$HOST" '' \
    "{\"name\":\"Tester\",\"username\":\"tester\",\"password\":\"$PASSWORD\",\"setup_code\":\"$code\"}" \
    >"$WORK/setup.out"
  check "setup through the proxy works, from the https address (got $(head -1 "$WORK/setup.out"))" \
    test "$(head -1 "$WORK/setup.out")" = 201
  check "setup sets the __Host- cookie" grep -q '^set-cookie: __Host-mealwright_session=' "$WORK/setup.out"

  web POST /api/v1/session "https://$HOST" '' \
    "{\"username\":\"tester\",\"password\":\"$PASSWORD\"}" >"$WORK/signin.out"
  check "sign-in through the proxy works (got $(head -1 "$WORK/signin.out"))" \
    test "$(head -1 "$WORK/signin.out")" = 200
  check "sign-in sets the __Host- cookie" grep -q '^set-cookie: __Host-mealwright_session=' "$WORK/signin.out"
  check "the answer says https only (HSTS)" grep -q '^strict-transport-security:' "$WORK/signin.out"

  local seen
  # Sign-in lines go to the log file in the data folder, not to the container output.
  seen=$(docker exec "$APP" sh -c 'cat /data/logs/*' 2>&1 | sed -n 's/.*Signed in: tester from \([^ ]*\).*/\1/p' | tail -1)
  check "the server logged the visitor's address ($seen), not the proxy's ($PROXY_IP)" \
    test "$seen" = "$CLIENT_IP"
  check "no 'not trusted' warning in the app's log" \
    bash -c '! { docker logs "$0" 2>&1; docker exec "$0" sh -c "cat /data/logs/*" 2>&1; } | grep -q "A request came through a reverse proxy"' "$APP"

  if [ "$FAILED" != 0 ]; then
    say "  --- the app's log:"
    docker exec "$APP" sh -c 'cat /data/logs/*' 2>&1 | tail -12
  fi
  docker rm -f "$APP" "$PROXY" >/dev/null
  docker network rm "$NET" >/dev/null
}

main() {
  local cases=("$@")
  [ ${#cases[@]} -gt 0 ] || cases=(nginx npm traefik caddy)
  for image in "$IMAGE" "$NGINX_IMAGE" "$TRAEFIK_IMAGE" "$CADDY_IMAGE"; do
    docker image inspect "$image" >/dev/null 2>&1 || docker pull -q "$image" >/dev/null
  done
  make_certificate
  write_client
  for which in "${cases[@]}"; do
    run_case "$which"
  done
  if [ "$FAILED" = 0 ]; then say "All proxies passed."; else say "Some checks failed."; fi
  return "$FAILED"
}

main "$@"
