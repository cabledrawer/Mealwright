// ./check lints the web app with the two commands of `npm run lint` plus an ESLint cache (T2c L7). This
// fails when that script changes, so the two can't drift apart: change both, on purpose.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdtempSync, openSync, readFileSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));

test('frontend `npm run lint` is still what ./check runs; only the fast run adds the ESLint cache', () => {
  const lint = JSON.parse(readFileSync(`${root}frontend/package.json`, 'utf8')).scripts.lint;
  assert.equal(lint, 'prettier --check . && eslint .');
  const check = readFileSync(`${root}check`, 'utf8');
  const cached = check.split('\n').filter((l) => l.includes('eslint --cache'));
  assert.equal(cached.length, 1);
  assert.ok(cached[0].includes('npx prettier --check . && npx eslint --cache --cache-location node_modules/.cache/eslint/ .'));
  // The cache only in the fast run (type-aware rules: a type change in another file would be missed), and
  // the full run uses `npm run lint` as it is.
  const i = check.indexOf('eslint --cache');
  assert.match(check.slice(check.lastIndexOf('if ((FAST))', i), i), /^if \(\(FAST\)\); then\s+start_beside "frontend: lint"/);
  assert.ok(check.includes('start_beside "frontend: lint" "ran beside the unit tests" sh -c \'cd frontend && npm run lint\''));
  // The listing runs with its own worker count: a bad E2E_WORKERS in the shell can't fail it.
  assert.ok(check.includes('env -u E2E_PROJECTS E2E_WORKERS=1 '));
});

test('a failed step\'s lines are not overwritten when the screen is a file (T2c run 5)', () => {
  // print_failure from ./check, run with the same fd layout (screen on fd 3, stdout to a log) and the
  // screen redirected to a file, then one more line written to the screen the way show() does.
  const dir = mkdtempSync(join(tmpdir(), 'check-fd-'));
  try {
    writeFileSync(join(dir, 'step.log'), Array.from({ length: 45 }, (_, i) => `line ${i + 1}`).join('\n') + '\n');
    const script = `
      ROOT=${JSON.stringify(root)}; declare -A STREAM_REPORT=()
      eval "$(sed -n '/^print_failure() {/,/^}/p' "$ROOT/check")"
      exec 3>&1 >${JSON.stringify(join(dir, 'log.txt'))} 2>&1
      printf 'first screen line\\n' >&3
      print_failure "browser: x" ${JSON.stringify(join(dir, 'step.log'))}
      printf 'after the failure\\n' >&3
    `;
    const r = spawnSync('bash', ['-c', script], { encoding: 'utf8', stdio: ['ignore', openSync(join(dir, 'screen.txt'), 'w'), 'pipe'] });
    assert.equal(r.status, 0, r.stderr);
    const screen = readFileSync(join(dir, 'screen.txt'), 'utf8').split('\n');
    assert.equal(screen[0], 'first screen line');
    assert.equal(screen.filter((l) => l.startsWith('    line ')).length, 40, 'the 40 last lines');
    assert.equal(screen.at(-2), 'after the failure');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
