// Tests of the flaky-test rule and of flaky.mjs, with made-up Playwright reports (node --test).
import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import { mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { failedTests, flakyTests, incompleteReason, judge, keyOf, rerunSelection } from './flaky-lib.mjs';

const script = fileURLToPath(new URL('./flaky.mjs', import.meta.url));

// A report with one file, one describe and the given [project, title, status] tests.
function report(tests, { file = 'plan.spec.ts', errors = [], unexpected = 0 } = {}) {
  return {
    errors,
    stats: { unexpected },
    suites: [
      {
        title: file,
        file,
        suites: [
          {
            title: 'Plan',
            specs: tests.map(([project, title, status], i) => ({
              title,
              file,
              line: 10 + i,
              tests: [{ projectName: project, status }],
            })),
          },
        ],
      },
    ],
  };
}

test('a key is "[project] file › titles", with no line number', () => {
  const [t] = flakyTests(report([['phone', 'moves a card', 'flaky']]));
  assert.equal(keyOf(t), '[phone] plan.spec.ts › Plan › moves a card');
});

test('only flaky tests are flaky, only unexpected ones failed', () => {
  const r = report([['phone', 'a', 'flaky'], ['phone', 'b', 'expected'], ['phone', 'c', 'unexpected'], ['phone', 'd', 'skipped']]);
  assert.deepEqual(flakyTests(r).map((t) => t.titles.at(-1)), ['a']);
  assert.deepEqual(failedTests(r).map((t) => t.titles.at(-1)), ['c']);
});

test('flaky now and in the previous full run fails; flaky only now does not', () => {
  const now = [{ key: '[phone] plan.spec.ts › Plan › a', file: 'plan.spec.ts' }, { key: '[phone] plan.spec.ts › Plan › b', file: 'plan.spec.ts' }];
  const verdict = judge({ flaky: now, previous: ['[phone] plan.spec.ts › Plan › a', '[desktop] plan.spec.ts › Plan › other'] });
  assert.deepEqual(verdict.twice, ['[phone] plan.spec.ts › Plan › a']);
  assert.deepEqual(verdict.newFile, []);
});

test('a test in a spec file new on the branch fails when flaky even once', () => {
  const now = [{ key: '[phone] fresh.spec.ts › x', file: 'fresh.spec.ts' }, { key: '[phone] old.spec.ts › y', file: 'old.spec.ts' }];
  const verdict = judge({ flaky: now, newFiles: ['e2e/tests/fresh.spec.ts'] });
  assert.deepEqual(verdict.newFile, ['[phone] fresh.spec.ts › x']);
  assert.deepEqual(verdict.twice, []);
});

test('no flaky tests, no history: nothing fails', () => {
  assert.deepEqual(judge({ flaky: [] }), { twice: [], newFile: [] });
});

test('a report with errors, or as many failures as the limit, is not a complete run', () => {
  assert.equal(incompleteReason(report([]), 20), '');
  assert.match(incompleteReason(report([], { errors: [{ message: 'Timed out waiting 2700s for the entire test run' }] }), 20), /Timed out/);
  assert.match(incompleteReason(report([], { unexpected: 20 }), 20), /reached the limit of 20/);
  assert.equal(incompleteReason(report([], { unexpected: 19 }), 20), '');
});

test('a rerun selection matches exactly the failed tests, by project, file and titles', () => {
  const r = report([['phone 0.7 x', 'it’s (1) [ok]', 'unexpected'], ['phone 0.7 x', 'fine', 'expected'], ['desktop 0.7 x', 'it’s (1) [ok]', 'flaky']]);
  const pick = rerunSelection(r);
  assert.equal(pick.count, 1);
  assert.deepEqual(pick.projects, ['phone 0.7 x']);
  assert.deepEqual(pick.files, ['plan.spec.ts']);
  // Playwright matches --grep against "project file describe… title", joined with spaces.
  const re = new RegExp(pick.grep);
  assert.ok(re.test(' phone 0.7 x plan.spec.ts Plan it’s (1) [ok]'));
  assert.ok(!re.test(' desktop 0.7 x plan.spec.ts Plan it’s (1) [ok]'));
  assert.ok(!re.test(' phone 0.7 x plan.spec.ts Plan fine'));
  assert.equal(rerunSelection(report([['phone', 'a', 'flaky']])), null);
});

test('flaky.mjs on fake report files: list, judge, complete, failed', () => {
  const dir = mkdtempSync(join(tmpdir(), 'flaky-test-'));
  try {
    const path = join(dir, 'r.json');
    writeFileSync(path, JSON.stringify(report([['phone', 'a', 'flaky'], ['desktop', 'b', 'unexpected']], { file: 'fresh.spec.ts' })));
    const prev = join(dir, 'prev.txt');
    writeFileSync(prev, '[phone] fresh.spec.ts › Plan › a\n');
    const run = (...a) => execFileSync('node', [script, ...a], { encoding: 'utf8' });
    assert.equal(run(path), '[phone] fresh.spec.ts › Plan › a\n');
    assert.equal(
      run('--judge', '--previous', prev, '--new-files', 'fresh.spec.ts', path),
      'twice\t[phone] fresh.spec.ts › Plan › a\nnew\t[phone] fresh.spec.ts › Plan › a\n',
    );
    assert.equal(run('--judge', path), '');
    assert.equal(run('--failed', path), 'desktop\tfresh.spec.ts\tPlan › b\n');
    assert.equal(
      run('--rerun', path),
      'project\tdesktop\nfile\tfresh.spec.ts\ngrep\t^\\s*(?:desktop fresh\\.spec\\.ts Plan b)$\ncount\t1\n',
    );
    assert.equal(run('--complete', '20', path), '');
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});

test('flaky.mjs fails on a missing or broken report, never "no flaky tests"', () => {
  const dir = mkdtempSync(join(tmpdir(), 'flaky-test-'));
  try {
    const broken = join(dir, 'broken.json');
    writeFileSync(broken, '{ not json');
    for (const path of [broken, join(dir, 'missing.json')]) {
      const result = spawnSync('node', [script, path], { encoding: 'utf8' });
      assert.notEqual(result.status, 0, path);
      assert.equal(result.stdout, '');
    }
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
});
