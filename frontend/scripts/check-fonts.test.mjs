// Tests for check-fonts.mjs, on fake build folders made in a temporary folder.
//
//   cd frontend && node --test scripts/
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { unwanted } from './check-fonts.mjs';

const SCRIPT = join(dirname(fileURLToPath(import.meta.url)), 'check-fonts.mjs');

function run(names) {
  const root = mkdtempSync(join(tmpdir(), 'mw-fonts-'));
  try {
    mkdirSync(join(root, '_app', 'immutable', 'assets'), { recursive: true });
    for (const name of names) writeFileSync(join(root, '_app', 'immutable', 'assets', name), 'x');
    return spawnSync(process.execPath, [SCRIPT, root], { encoding: 'utf8' });
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
}

test('latin and latin-ext files pass', () => {
  const r = run([
    'plus-jakarta-sans-latin-wght-normal.eXO_dkmS.woff2',
    'plus-jakarta-sans-latin-ext-wght-normal.DmpS2jIq.woff2',
    'newsreader-latin-wght-normal.CCVVNp6i.woff2'
  ]);
  assert.equal(r.status, 0, r.stderr);
  assert.match(r.stdout, /3 font files/);
});

test('a vietnamese or cyrillic file fails, and is named', () => {
  const r = run([
    'newsreader-latin-wght-normal.CCVVNp6i.woff2',
    'newsreader-vietnamese-wght-normal.Czsa-EzN.woff2',
    'plus-jakarta-sans-cyrillic-ext-wght-normal.lLTsRRxN.woff2'
  ]);
  assert.equal(r.status, 1);
  assert.match(r.stderr, /vietnamese/);
  assert.match(r.stderr, /cyrillic-ext/);
  assert.doesNotMatch(r.stderr, /newsreader-latin-wght/);
});

test('a font file whose subset can not be read counts as wrong; no fonts at all fails', () => {
  assert.deepEqual(unwanted(['mystery.woff2']), ['mystery.woff2']);
  assert.equal(run([]).status, 1);
});
