#!/usr/bin/env bash
# Proves docs/restore.md: a backup Mealwright made restores into a FRESH container, and
# signing in there shows the data (0.9, D1).
#
#   backend/scripts/restore_test.sh [image]        (default: $CHECK_IMAGE, else mealwright:check)
#
# 1. Starts Mealwright in a throwaway container with its own empty volume, sets it up, adds a
#    recipe and presses "Back up now" (POST /api/v1/backups).
# 2. Takes the newest backup-*.db out of that container's /data/backups.
# 3. Puts it into a second, brand-new volume as /data/mealwright.db, the way docs/restore.md
#    says (owned by Mealwright's user, readable by it only), and starts a fresh container on it.
# 4. Signs in there with the same password and finds the recipe.
#
# Only its own containers and volumes (named mw-restore-test-<pid>-…) are made and removed.
# Everything stays on this computer: the containers are reached on 127.0.0.1 only, on
# RESTORE_PORT (default 19509). No fixed waits: it polls until ready, with a time limit.
set -euo pipefail

IMAGE="${1:-${CHECK_IMAGE:-mealwright:check}}"
PORT="${RESTORE_PORT:-19509}"
NAME="mw-restore-test-$$"
WORK="$(mktemp -d "${TMPDIR:-/tmp}/mw-restore-test.XXXXXX")"
JAR="$WORK/cookies"
RECIPE="Restore test dal $$"
PASSWORD="restore test password $$"

cleanup() {
  docker rm -f "$NAME-old" "$NAME-new" >/dev/null 2>&1 || true
  docker volume rm "$NAME-old" "$NAME-new" >/dev/null 2>&1 || true
  rm -rf "$WORK"
}
trap cleanup EXIT

say() { printf 'restore test: %s\n' "$*"; }
fail() { say "FAILED: $*"; exit 1; }

start() {  # start <container and volume name>
  docker run -d --name "$1" -v "$1:/data" -p "127.0.0.1:$PORT:8080" \
    -e MEALWRIGHT_ALLOW_PLAIN_HTTP=true "$IMAGE" >/dev/null
  local deadline=$((SECONDS + 90))
  until curl -fsS "http://127.0.0.1:$PORT/api/v1/version" >/dev/null 2>&1; do
    if ((SECONDS > deadline)); then
      docker logs "$1" 2>&1 | tail -20
      fail "$1 didn't answer within 90 s"
    fi
    if [[ "$(docker inspect -f '{{.State.Running}}' "$1")" != "true" ]]; then
      docker logs "$1" 2>&1 | tail -20
      fail "$1 stopped"
    fi
    sleep 0.2  # a poll, not a wait for something to happen
  done
}

api() {  # api <method> <path> [json]: prints the body, fails on an error status
  local args=(-fsS -b "$JAR" -c "$JAR" -X "$1" "http://127.0.0.1:$PORT/api/v1$2")
  if [[ $# -ge 3 ]]; then args+=(-H 'Content-Type: application/json' --data "$3"); fi
  curl "${args[@]}"
}

say "image $IMAGE, port $PORT"

# 1. An install with something in it, and a backup of it.
docker volume create "$NAME-old" >/dev/null
start "$NAME-old"
api POST /setup "{\"name\": \"Tess\", \"username\": \"tess\", \"password\": \"$PASSWORD\"}" >/dev/null
api POST /recipes "{\"name\": \"$RECIPE\"}" >/dev/null
api POST /backups | grep -q '"problem":null' || fail "Back up now reported a problem"
BACKUP="$(docker exec "$NAME-old" sh -c 'ls /data/backups | grep -E "^backup-[0-9]{8}-[0-9]{6}\.db$" | sort | tail -1')"
[[ -n "$BACKUP" ]] || fail "no backup file in /data/backups"
say "made $BACKUP"

# 2. Take it out, and the old install goes away completely.
docker cp "$NAME-old:/data/backups/$BACKUP" "$WORK/$BACKUP"
docker rm -f "$NAME-old" >/dev/null
docker volume rm "$NAME-old" >/dev/null
rm -f "$JAR"

# 3. A brand-new data volume, with the backup in place of the database (docs/restore.md,
#    step 3), written by Mealwright's own user so it owns the file.
docker volume create "$NAME-new" >/dev/null
docker run --rm -i -v "$NAME-new:/data" --entrypoint sh "$IMAGE" \
  -c 'cat > /data/mealwright.db && chmod 600 /data/mealwright.db' <"$WORK/$BACKUP"
start "$NAME-new"

# 4. No first-run setup: the restored install signs in, and the recipe is there.
api GET /setup | grep -q '"needs_setup":false' || fail "the restored install asks for setup"
api POST /session "{\"username\": \"tess\", \"password\": \"$PASSWORD\"}" >/dev/null \
  || fail "couldn't sign in to the restored install"
api GET /recipes | grep -qF "$RECIPE" || fail "the recipe isn't in the restored install"
say "passed: signed in to a fresh container restored from $BACKUP and found the recipe"
