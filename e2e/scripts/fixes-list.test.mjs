// Tests of fixes-list.mjs: the grouping, and the command against a made-up git repo (node --test).
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { fixesLines, prOf } from './fixes-list.mjs';

const script = fileURLToPath(new URL('./fixes-list.mjs', import.meta.url));

test('prOf reads "PR 134" and "(#134)" from a subject, nothing otherwise', () => {
  assert.equal(prOf('Docs: x (cabledrawer 6 Nov, PR 134)'), '134');
  assert.equal(prOf('Fix y (#77)'), '77');
  assert.equal(prOf('Tests: plain'), '');
});

test('failures are grouped by the commit that last changed their file', () => {
  const failed = [
    { project: 'phone', file: 'a.spec.ts', line: 3, titles: ['A', 'one'] },
    { project: 'desktop', file: 'a.spec.ts', line: 3, titles: ['A', 'one'] },
    { project: 'desktop', file: 'b.spec.ts', line: 9, titles: ['two'] },
    { project: 'desktop', file: 'c.spec.ts', line: 1, titles: ['three'] },
  ];
  const changes = { 'a.spec.ts': { hash: 'abc1234', subject: 'Plan (PR 12)' }, 'b.spec.ts': { hash: 'def5678', subject: 'No number' } };
  const lines = fixesLines(failed, (f) => changes[f] ?? null);
  assert.deepEqual(lines, [
    'PR 12: last changed a.spec.ts in abc1234 "Plan (PR 12)"',
    '  - [phone] a.spec.ts:3 › A › one',
    '  - [desktop] a.spec.ts:3 › A › one',
    'No PR number in the commit: def5678 "No number" last changed b.spec.ts',
    '  - [desktop] b.spec.ts:9 › two',
    'Not changed on this line (spec file as on main)',
    '  - [desktop] c.spec.ts:1 › three',
  ]);
});

test('the command finds the PR in a real git history, and says nothing when no test failed', () => {
  const dir = mkdtempSync(join(tmpdir(), 'fixes-list-'));
  try {
    const git = (...a) => execFileSync('git', ['-C', dir, '-c', 'user.name=t', '-c', 'user.email=t@example.test', ...a], { encoding: 'utf8' });
    git('init', '-q');
    mkdirSync(join(dir, 'tests'));
    writeFileSync(join(dir, 'tests/a.spec.ts'), '1\n');
    writeFileSync(join(dir, 'tests/c.spec.ts'), '1\n');
    git('add', '.');
    git('commit', '-q', '-m', 'main commit');
    const base = git('rev-parse', 'HEAD').trim();
    writeFileSync(join(dir, 'tests/a.spec.ts'), '2\n');
    git('commit', '-q', '-am', 'Plan change (PR 12)');
    const report = (failed) =>
      JSON.stringify({
        suites: [{ title: 'a.spec.ts', file: 'a.spec.ts', specs: [{ title: 'one', file: 'a.spec.ts', line: 3, tests: [{ projectName: 'desktop', status: failed ? 'unexpected' : 'expected' }] }] }],
      });
    const bad = join(dir, 'bad.json');
    const good = join(dir, 'good.json');
    writeFileSync(bad, report(true));
    writeFileSync(good, report(false));
    const run = (file) => spawnSync('node', [script, '--base', base, file], { cwd: dir, encoding: 'utf8' });
    const out = run(bad);
    assert.equal(out.status, 0, out.stderr);
    assert.match(out.stdout, /PR 12: last changed a\.spec\.ts in [0-9a-f]+ "Plan change \(PR 12\)"/);
    assert.match(out.stdout, /\[desktop\] a\.spec\.ts:3 › one/);
    assert.equal(run(good).stdout, '');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
