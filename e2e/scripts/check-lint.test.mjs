// ./check lints the web app with the two commands of `npm run lint` plus an ESLint cache (T2c L7). This
// fails when that script changes, so the two can't drift apart: change both, on purpose.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
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
