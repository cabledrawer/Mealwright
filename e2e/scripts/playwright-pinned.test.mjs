// The browser tests run on the exact Playwright the lock files hold: no range ("^", "~", "latest") in
// package.json, the same version in e2e/ and frontend/, and no Playwright container image named anywhere
// in the repo's own files (there is none; if one is ever added it must be pinned by digest).
// A browser build is fetched by `playwright install` for exactly the locked version, so a version that
// moves would change the browser under the tests.
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('../../', import.meta.url));
const read = (path) => readFileSync(join(root, path), 'utf8');
const wanted = (file) => {
  const info = JSON.parse(read(file));
  const all = { ...info.dependencies, ...info.devDependencies };
  return Object.entries(all).filter(([name]) => /^(playwright|playwright-core|@playwright\/.+)$/.test(name));
};

test('every Playwright package is an exact version, the same one in e2e/ and frontend/', () => {
  const versions = new Set();
  for (const file of ['e2e/package.json', 'frontend/package.json']) {
    const found = wanted(file);
    assert.ok(found.length > 0, `${file} names no Playwright package`);
    for (const [name, version] of found) {
      assert.match(version, /^\d+\.\d+\.\d+$/, `${file}: ${name} is "${version}", not an exact version`);
      versions.add(version);
    }
  }
  assert.equal(versions.size, 1, `Playwright versions differ: ${[...versions].join(', ')}`);
});

test('no Playwright image, and no image at all without a digest, in the Dockerfile and compose files', () => {
  const files = ['Dockerfile', ...readdirSync(root).filter((n) => /^compose.*\.ya?ml$/.test(n))];
  for (const file of files) {
    const text = read(file);
    assert.doesNotMatch(text, /mcr\.microsoft\.com\/playwright/i, `${file} names a Playwright image: pin it by digest`);
  }
  for (const line of read('Dockerfile').split('\n').filter((l) => /^FROM /.test(l))) {
    assert.match(line, /@sha256:[0-9a-f]{64}/, `Dockerfile: "${line}" is not pinned by digest`);
  }
});
