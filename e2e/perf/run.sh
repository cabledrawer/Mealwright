#!/usr/bin/env bash
# Speed baseline: build the image, run it as a Pi 4 class box, seed it, measure the phone and the
# desktop, and stop it. Not part of ./check. See docs/dev/performance.md.
#   cd e2e && ./perf/run.sh
# Needs: docker, and the e2e dependencies installed (npm ci in e2e/; the Playwright Chromium).
# Settings you can change in the environment:
#   PERF_PORT=7795  PERF_IMAGE=mealwright:perf  PERF_NAME=mw-perf  PERF_CPUS=0.5  PERF_RUNS=5
set -euo pipefail
cd "$(dirname "$0")/.."
PORT="${PERF_PORT:-7795}" IMAGE="${PERF_IMAGE:-mealwright:perf}" NAME="${PERF_NAME:-mw-perf}"
CPUS="${PERF_CPUS:-0.5}" RUNS="${PERF_RUNS:-5}"
# --cpus 0.5 means half of one of this PC's cores: see "Why 0.5 cores" in docs/dev/performance.md.
# The 10 ms scheduling period makes the limit slow short requests too, not only long ones.
QUOTA=$(awk -v c="$CPUS" 'BEGIN { printf "%d", c * 10000 }')

cleanup() { docker rm -f "$NAME" >/dev/null 2>&1 || true; docker volume rm "$NAME-data" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

[[ "${PERF_SKIP_BUILD:-0}" == 1 ]] || docker build -t "$IMAGE" ..
docker volume create "$NAME-data" >/dev/null
# No outgoing connection: the image's own outbound switches are all off by default, and the
# container is on the default bridge with no published port except the one on loopback.
docker run -d --name "$NAME" -p "127.0.0.1:$PORT:8080" \
  --cpu-period 10000 --cpu-quota "$QUOTA" --memory 4g --memory-swap 4g \
  -e MEALWRIGHT_ALLOW_PLAIN_HTTP=true -e MEALWRIGHT_HOST=0.0.0.0 \
  -v "$NAME-data:/data" "$IMAGE" >/dev/null
for _ in $(seq 1 120); do
  curl -fs "http://127.0.0.1:$PORT/api/v1/version" >/dev/null 2>&1 && break
  sleep 1
done
CODE=$(docker logs "$NAME" 2>&1 | grep -o '[A-Z2-9]\{4\}-[A-Z2-9]\{4\}-[A-Z2-9]\{4\}' | tail -1)
node perf/seed.ts --base "http://127.0.0.1:$PORT" --setup-code "$CODE"
node perf/measure.ts --profile phone --runs "$RUNS" --out perf/results-phone.json
node perf/measure.ts --profile desktop --runs "$RUNS" --out perf/results-desktop.json
node perf/table.ts perf/results-phone.json perf/results-desktop.json
