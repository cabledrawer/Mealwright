// Tests of test-map.mjs: the globs, the words, the choice, and that the real map names every test file.
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { test } from 'node:test';
import { fileURLToPath } from 'node:url';
import { backendTests, browserSpecs, globToRegex, problems, readMap, select, specsWith, wordsOf } from './test-map.mjs';

const script = fileURLToPath(new URL('./test-map.mjs', import.meta.url));

test('globs: * stays in a folder, ** goes through folders', () => {
  assert.ok(globToRegex('a/*.py').test('a/x.py'));
  assert.ok(!globToRegex('a/*.py').test('a/b/x.py'));
  assert.ok(globToRegex('a/**').test('a/b/c/x.py'));
  assert.ok(globToRegex('**/*.md').test('docs/dev/x.md'));
  assert.ok(globToRegex('**/*.md').test('x.md'));
  assert.ok(globToRegex('frontend/src/routes/(app)/plan/**').test('frontend/src/routes/(app)/plan/+page.svelte'));
});

test('the real map names every backend test file and every browser spec file, and nothing else', () => {
  assert.deepEqual(problems(readMap(), backendTests(), browserSpecs()), []);
  const r = spawnSync('node', [script, 'validate'], { encoding: 'utf8' });
  assert.equal(r.status, 0, r.stderr);
});

test('a test file that is not in the map, and a name that matches no file, are reported', () => {
  const map = { areas: [{ name: 'A', backend: ['test_a.py', 'test_gone.py'], browser: ['a.spec.ts'] }] };
  const bad = problems(map, ['test_a.py', 'test_new.py'], ['a.spec.ts', 'new.spec.ts']);
  assert.deepEqual(bad.sort(), [
    'backend test file not in e2e/test-map.json: test_new.py',
    'browser spec file not in e2e/test-map.json: new.spec.ts',
    'e2e/test-map.json names no backend test file: test_gone.py',
  ].sort());
});

test('a change selects its area’s tests; docs select none; a shared file or an unknown one selects everything', () => {
  const map = readMap();
  const plan = select(map, ['backend/src/mealwright/plan.py']);
  assert.equal(plan.all, '');
  assert.ok(plan.backend.has('test_plan.py'));
  assert.ok(plan.backend.has('test_wording.py'), 'the always tests run with any backend change');
  assert.ok(plan.browser.has('plan.spec.ts'));
  assert.ok(!plan.browser.has('shopping.spec.ts'));
  const docs = select(map, ['docs/spec.md', 'CHANGELOG.md']);
  assert.equal(docs.all, '');
  assert.equal(docs.backend.size + docs.browser.size, 0);
  assert.match(select(map, ['backend/src/mealwright/models.py']).all, /shared by every test/);
  assert.match(select(map, ['backend/src/mealwright/brand_new.py']).all, /no area/);
  assert.match(select(map, ['check']).all, /shared/);
});

test('a change to the web app or the browser tests alone picks no backend test (T2c S3)', () => {
  const map = readMap();
  const web = select(map, ['frontend/src/routes/(app)/plan/+page.svelte', 'frontend/src/lib/components/plan/Card.svelte']);
  assert.equal(web.all, '');
  assert.equal(web.backend.size, 0, 'no backend path changed');
  assert.ok(web.browser.has('plan.spec.ts'));
  // A shared or unknown web app / browser-test file: no browser file can be chosen, still no backend test.
  for (const path of ['frontend/package.json', 'frontend/src/lib/brand-new-shared.ts', 'e2e/tests/clock.ts', 'e2e/playwright.config.ts']) {
    const r = select(map, [path]);
    assert.equal(r.all, '', path);
    assert.ok(r.allBrowser, path);
    assert.equal(r.backend.size, 0, path);
  }
  // With a backend path too, that path still picks its tests.
  const both = select(map, ['frontend/package.json', 'backend/src/mealwright/plan.py']);
  assert.ok(both.backend.has('test_plan.py'));
  assert.ok(both.allBrowser);
  assert.match(select(map, ['frontend/package.json', 'backend/src/mealwright/models.py']).all, /models\.py/);
  assert.match(select(map, ['Dockerfile']).all, /shared/);
});

test('the reasons are one line per area, with a count and up to three names (T2c S6)', () => {
  const paths = ['a', 'b', 'c', 'd', 'e'].map((n) => `frontend/src/lib/components/plan/${n}.svelte`);
  const r = select(readMap(), paths);
  assert.deepEqual(r.why, ['Plan: 5 files (a.svelte, b.svelte, c.svelte, …)']);
  const one = select(readMap(), ['backend/src/mealwright/plan.py']);
  assert.deepEqual(one.why, ['Plan: 1 file (plan.py)']);
});

test('a deleted or renamed spec file or test file is not listed to run (T2b light review)', () => {
  const r = select(readMap(), ['e2e/tests/gone-for-good.spec.ts', 'e2e/tests/today.spec.ts', 'backend/tests/test_gone_for_good.py']);
  assert.deepEqual([...r.browser], ['today.spec.ts']);
  assert.ok(![...r.backend].some((f) => f.includes('gone_for_good')));
  assert.ok(r.why.some((w) => /deleted or renamed/.test(w)));
});

test('a changed test file selects itself (and the always tests)', () => {
  const r = select(readMap(), ['backend/tests/test_plan.py', 'e2e/tests/today.spec.ts']);
  assert.ok(r.backend.has('test_plan.py'));
  assert.ok(!r.backend.has('test_today.py'), 'only itself and the always tests');
  assert.deepEqual([...r.browser], ['today.spec.ts']);
});

test('words in a diff are found in the specs that look for them', () => {
  const diff = [
    '--- a/docs/dev/words.md',
    '+++ b/docs/dev/words.md',
    '@@ -1 +1 @@',
    '-Toast: “Moved to Tomorrow”',
    '+Toast: “Moved to Friday”',
    '+<p>Nothing planned yet</p>',
    "+const id = 'abc';",
  ].join('\n');
  const words = wordsOf(diff);
  assert.deepEqual(words.sort(), ['Moved to Friday', 'Moved to Tomorrow', 'Nothing planned yet'].sort());
  const hits = specsWith(words, {
    'plan.spec.ts': "await expect(toast).toHaveText('Moved to tomorrow')",
    'shell.spec.ts': 'nothing here',
  });
  assert.deepEqual([...hits.keys()], ['plan.spec.ts']);
  const r = select(readMap(), ['docs/dev/words.md'], hits);
  assert.ok(r.browser.has('plan.spec.ts'));
  assert.equal(r.backend.size, 0);
});
