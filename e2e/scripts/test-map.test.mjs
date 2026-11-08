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
