// Run with: node --test scripts/slowest.test.mjs
import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { mkdtempSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';

const test_ = (title, durations) => ({
  title,
  file: 'a.spec.ts',
  line: 1,
  tests: [{ projectName: 'desktop', results: durations.map((duration) => ({ duration })) }],
});

test('a retried test shows the total of every try and says how many', () => {
  const dir = mkdtempSync(join(tmpdir(), 'slowest-'));
  const file = join(dir, 'r.json');
  const report = {
    suites: [{ title: 'a.spec.ts', specs: [test_('retried', [6000, 5000]), test_('single', [9000])] }],
  };
  writeFileSync(file, JSON.stringify(report));
  const out = execFileSync('node', [join(import.meta.dirname, 'slowest.mjs'), '5', file], {
    encoding: 'utf8',
  }).split('\n');
  assert.match(out[0], /^ {2}11\.0 s {2}\[desktop\] a\.spec\.ts:1 › retried \(2 tries\)$/);
  assert.match(out[1], /^ {3}9\.0 s {2}\[desktop\] a\.spec\.ts:1 › single$/);
});
