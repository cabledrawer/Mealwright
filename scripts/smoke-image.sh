#!/usr/bin/env bash
# Smoke run of a built Mealwright image (0.9.5, ./check's "image: smoke run").
#
#   scripts/smoke-image.sh <image>
#
# Starts the image the way compose.example.yaml does (read-only, no extra rights, a small /tmp)
# on a new, empty data volume, with its own container name and a host port Docker picks
# (127.0.0.1 only), so it can never clash with another container or port. Then:
#   1. waits (up to 150 s) for Docker to call the container healthy,
#   2. fetches the sign-in page and the health endpoint,
#   3. checks the answers carry no Server header,
#   4. checks the container's log holds no error lines,
# and always removes the container and the volume, also when something failed or this is
# stopped. Prints what it did; exits 0 only when every step passed.
set -uo pipefail

IMAGE="${1:?usage: smoke-image.sh <image>}"
SUFFIX="$$-$RANDOM"
NAME="mealwright-smoke-$SUFFIX"
VOLUME="mealwright-smoke-data-$SUFFIX"
WORK="$(mktemp -d)"
STARTED=0

cleanup() {
  if ((STARTED)); then docker rm -f "$NAME" >/dev/null 2>&1; fi
  docker volume rm "$VOLUME" >/dev/null 2>&1
  rm -rf -- "${WORK:?}"
}
trap cleanup EXIT
trap 'exit 130' INT TERM

fail() { echo "SMOKE FAIL: $*"; exit 1; }

docker volume create "$VOLUME" >/dev/null || fail "could not make the data volume"
docker run -d --name "$NAME" \
  --read-only --tmpfs /tmp:size=64m,mode=1777 --cap-drop ALL \
  --security-opt no-new-privileges:true --init --memory 512m \
  -e MEALWRIGHT_ALLOW_PLAIN_HTTP=true \
  -v "$VOLUME:/data" -p 127.0.0.1::8080 "$IMAGE" >/dev/null || fail "the container did not start"
STARTED=1

# 1. Healthy: the image's own HEALTHCHECK (it asks /api/v1/health).
state=""
for _ in $(seq 1 75); do
  state="$(docker inspect --format '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' "$NAME" 2>/dev/null)"
  case "$state" in
    "running healthy") break ;;
    running\ *|"") ;;
    *) fail "the container is '$state' (it stopped); the log ends: $(docker logs --tail 20 "$NAME" 2>&1)" ;;
  esac
  sleep 2
done
[[ "$state" == "running healthy" ]] || fail "not healthy after 150 s (state: $state); the log ends: $(docker logs --tail 20 "$NAME" 2>&1)"
echo "healthy"

port="$(docker port "$NAME" 8080/tcp | sed -n 's/^127\.0\.0\.1://p' | head -n 1)"
[[ "$port" =~ ^[0-9]+$ ]] || fail "could not find the host port"

# 2. The sign-in page and the health endpoint, from outside the container.
fetch() {   # fetch <path> <body file>: prints the status; the headers go to $WORK/headers
  curl -sS --max-time 10 -o "$2" -D "$WORK/headers" -w '%{http_code}' "http://127.0.0.1:$port$1"
}
code="$(fetch /sign-in "$WORK/page")" || fail "the sign-in page did not answer"
[[ "$code" == 200 ]] || fail "the sign-in page answered $code"
grep -qi '<html' "$WORK/page" || fail "the sign-in page is not a web page"
grep -qi '^server:' "$WORK/headers" && fail "the sign-in page carries a Server header"
echo "sign-in page: 200"

code="$(fetch /api/v1/health "$WORK/health")" || fail "the health endpoint did not answer"
[[ "$code" == 200 ]] || fail "the health endpoint answered $code"
[[ "$(tr -d '[:space:]' <"$WORK/health")" == '{"status":"ok"}' ]] || fail "the health answer is not just ok: $(cat "$WORK/health")"
grep -qi '^server:' "$WORK/headers" && fail "the health endpoint carries a Server header"
echo "health: 200 ok"

# 4. No error lines in the container's log (its format: "<time> <LEVEL> <name>: <message>").
docker logs "$NAME" >"$WORK/log" 2>&1
if grep -E ' (ERROR|CRITICAL) |Traceback \(most recent call last\)' "$WORK/log"; then
  fail "the log has error lines (above)"
fi
echo "log: no error lines"
echo "smoke run passed"
