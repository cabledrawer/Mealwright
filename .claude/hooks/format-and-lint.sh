#!/usr/bin/env bash
# After Claude Code edits or writes a file: format it, then lint it, with the tools already
# installed in that checkout (backend/.venv, frontend/node_modules). Nothing is downloaded and
# nothing goes online. Formatting is applied quietly; lint problems are handed back to Claude
# (exit 2) so it fixes them. A missing tool or a file outside backend/ and frontend/ is skipped.
#
# The file can be in a helper's worktree, so the checkout is found from the file, not from
# where Claude Code was started.

set -uo pipefail

file="$(python3 -I -c 'import json, sys; print(json.load(sys.stdin).get("tool_input", {}).get("file_path", ""))')" || exit 0
[[ -n "$file" && -f "$file" ]] || exit 0

root="$(git -C "$(dirname "$file")" rev-parse --show-toplevel 2>/dev/null)" || exit 0
[[ -f "$root/backend/pyproject.toml" && -f "$root/frontend/package.json" ]] || exit 0   # not a Mealwright checkout
rel="${file#"$root"/}"

problems=""
case "$rel" in
  backend/*.py)
    ruff="$root/backend/.venv/bin/ruff"
    [[ -x "$ruff" ]] || exit 0
    cd "$root/backend" || exit 0
    "$ruff" format --quiet "$file" >/dev/null 2>&1
    problems="$("$ruff" check --quiet --no-fix "$file" 2>&1)" || true
    ;;
  frontend/*.ts | frontend/*.js | frontend/*.svelte | frontend/*.css | frontend/*.html | frontend/*.json | frontend/*.md)
    bin="$root/frontend/node_modules/.bin"
    [[ -x "$bin/prettier" ]] || exit 0
    cd "$root/frontend" || exit 0
    "$bin/prettier" --write --ignore-unknown --log-level silent "${rel#frontend/}" >/dev/null 2>&1
    case "$rel" in
      *.ts | *.js | *.svelte)
        [[ -x "$bin/eslint" ]] && { problems="$("$bin/eslint" --no-warn-ignored "${rel#frontend/}" 2>&1)" || true; } ;;
    esac
    ;;
  *) exit 0 ;;
esac

if [[ -n "$problems" ]]; then
  printf 'Lint problems in %s (fix them):\n%s\n' "$rel" "$problems" >&2
  exit 2
fi
exit 0
