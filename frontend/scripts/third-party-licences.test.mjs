// Tests for third-party-licences.mjs, on the real package folder (needs `npm ci` done, as the
// build does). Run by ./check with the other scripts' tests: `node --test scripts/`.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { build, RUNTIME } from './third-party-licences.mjs';

const ROOT = join(dirname(fileURLToPath(import.meta.url)), '..');
const own = JSON.parse(readFileSync(join(ROOT, 'package.json'), 'utf8'));
const text = build(ROOT);

test('lists every production dependency with its version and licence', () => {
  for (const name of Object.keys(own.dependencies)) {
    assert.match(text, new RegExp(`^${name.replace(/[/.]/g, '\\$&')} \\d+\\.\\d+`, 'm'), name);
  }
  for (const name of RUNTIME) assert.ok(text.includes(`\n${name} `), name);
});

test('lists the bundled fonts under their OFL-1.1 licence, with its text', () => {
  for (const font of [
    '@fontsource-variable/newsreader',
    '@fontsource-variable/plus-jakarta-sans'
  ]) {
    const at = text.indexOf(`\n${font} `);
    assert.ok(at >= 0, font);
    const section = text.slice(at, text.indexOf('\n====', at + 1) + 1 || undefined);
    assert.match(section, /Licence: OFL-1\.1/, font);
    assert.match(section, /SIL OPEN FONT LICENSE Version 1\.1/i, font);
  }
});

test('every entry carries a licence text or says it has none', () => {
  const entries = text.split('='.repeat(78)).slice(1);
  assert.ok(entries.length >= Object.keys(own.dependencies).length);
  for (const entry of entries) assert.ok(entry.trim().split('\n').length >= 3, entry.slice(0, 60));
});
