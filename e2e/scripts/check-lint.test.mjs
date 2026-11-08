// ./check lints the web app with the two commands of `npm run lint` plus an ESLint cache (T2c L7). This
// fails when that script changes, so the two can't drift apart: change both, on purpose.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));

test('frontend `npm run lint` is still what ./check runs, apart from the ESLint cache', () => {
  const lint = JSON.parse(readFileSync(`${root}frontend/package.json`, 'utf8')).scripts.lint;
  assert.equal(lint, 'prettier --check . && eslint .');
  const check = readFileSync(`${root}check`, 'utf8');
  assert.ok(check.includes('npx prettier --check . && npx eslint --cache --cache-location node_modules/.cache/eslint/ .'));
});
