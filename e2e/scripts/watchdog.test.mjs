// Tests of ./check's step watchdog (start_watchdog), run in bash with the functions taken from
// ./check itself (node --test). The limit is shrunk by replacing `sleep` and `limit_minutes`.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, readFileSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const checkScript = readFileSync(fileURLToPath(new URL('../../check', import.meta.url)), 'utf8');

function fn(name) {
  const m = checkScript.match(new RegExp(`^${name}\\(\\) \\{\\n[\\s\\S]*?^\\}\\n`, 'm'));
  assert.ok(m, `${name} is in ./check`);
  return m[0];
}

// Runs `body` in bash with ./check's stop_group and start_watchdog; the watchdog's wait is 1 s.
function run(body) {
  const dir = mkdtempSync(join(tmpdir(), 'mealwright-watchdog-'));
  try {
    const script = [
      'set -m',
      fn('stop_group'),
      'limit_minutes() { echo 0; }',
      'sleep() { command sleep "$([[ $1 == 30 ]] && echo 1 || echo "$1")"; }',
      fn('start_watchdog'),
      `T=${JSON.stringify(dir)}`,
      body,
    ].join('\n');
    const r = spawnSync('bash', ['-c', script], { encoding: 'utf8', timeout: 30_000 });
    assert.equal(r.status, 0, r.stderr);
    return r.stdout.trim();
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

test('a step that ended before its limit is not marked stopped, though the check collects it later', () => {
  // pytest beside the browsers: it ends in 15 min, the check waits for it after the browsers (30 min).
  const out = run(`
    ( exit 0 ) & J=$!
    start_watchdog $J "backend: pytest" "$T/flag"
    command sleep 3
    wait $J
    [[ -e "$T/flag" ]] && echo flagged || echo clean`);
  assert.equal(out, 'clean');
});

test('a step still running at its limit is marked stopped and stopped', () => {
  const out = run(`
    ( command sleep 60 ) & J=$!
    start_watchdog $J "backend: pytest" "$T/flag"
    command sleep 8
    [[ -e "$T/flag" ]] && echo flagged || echo clean
    st="$(ps -o stat= -p $J)"; [[ -z "$st" || "$st" == Z* ]] && echo gone || echo running`);
  assert.equal(out, 'flagged\ngone');
});

