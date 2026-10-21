// Tests for check-size.mjs, on a small fake build folder made in a temporary folder.
//
//   cd frontend && node --test scripts/
//
// Node's own test runner: nothing is installed. ./check runs these before the size check.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { randomBytes } from 'node:crypto';
import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

const SCRIPT = join(dirname(fileURLToPath(import.meta.url)), 'check-size.mjs');

/** Text that gzip can't make much smaller, so sizes are easy to reason about. */
const noise = (bytes) => `/*${randomBytes(bytes).toString('base64')}*/`;
const gz = (text) => gzipSync(Buffer.from(text), { level: 9 }).length;

/**
 * A build shaped like SvelteKit's: two pages, "/" (node 2) and "/big" (node 3), both in the
 * layout node 1 under the root node 0. "/big" imports a chunk of `big` bytes of its own;
 * every page shares `shared.js` and the root CSS. Returns the folder and what each file
 * gzips to.
 */
function fakeBuild({ big = 1000, shared = 1000, worker = 0 } = {}) {
  const root = mkdtempSync(join(tmpdir(), 'mw-size-'));
  const files = {
    'theme.js': `${noise(50)}`,
    '_app/immutable/entry/start.A1.js': `import{a}from"../chunks/shared.S1.js";${noise(100)}`,
    '_app/immutable/entry/app.B1.js':
      'const __vite__mapDeps=(i,m=__vite__mapDeps,d=(m.f||(m.f=["/_app/immutable/nodes/0.N0.js",' +
      '"/_app/immutable/chunks/shared.S1.js","/_app/immutable/assets/0.C0.css",' +
      '"/_app/immutable/nodes/1.N1.js","/_app/immutable/nodes/2.N2.js",' +
      '"/_app/immutable/nodes/3.N3.js","/_app/immutable/chunks/big.G1.js"])))=>i.map(i=>d[i]);' +
      'import{a}from"../chunks/shared.S1.js";' +
      'const n=[()=>T(()=>import(`../nodes/0.N0.js`),__vite__mapDeps([0,1,2]),import.meta.url),' +
      '()=>T(()=>import(`../nodes/1.N1.js`),__vite__mapDeps([3,1]),import.meta.url),' +
      '()=>T(()=>import(`../nodes/2.N2.js`),__vite__mapDeps([4,1]),import.meta.url),' +
      '()=>T(()=>import(`../nodes/3.N3.js`),__vite__mapDeps([5,6,1]),import.meta.url)];' +
      `const r={"/(app)":[2,[1]],"/(app)/big":[3,[1]]};${noise(100)}`,
    '_app/immutable/nodes/0.N0.js': `import{a}from"../chunks/shared.S1.js";${noise(100)}`,
    '_app/immutable/nodes/1.N1.js': `${noise(100)}`,
    '_app/immutable/nodes/2.N2.js': `${noise(100)}`,
    '_app/immutable/nodes/3.N3.js': `import{b}from"../chunks/big.G1.js";${noise(100)}`,
    '_app/immutable/chunks/shared.S1.js': noise(shared),
    '_app/immutable/chunks/big.G1.js': noise(big),
    '_app/immutable/assets/0.C0.css': `body{}${noise(200)}`
  };
  if (worker) files['service-worker.js'] = noise(worker);
  for (const [path, text] of Object.entries(files)) {
    mkdirSync(dirname(join(root, path)), { recursive: true });
    writeFileSync(join(root, path), text);
  }
  const size = Object.fromEntries(Object.entries(files).map(([p, t]) => [p, gz(t)]));
  const everyPage = [
    'theme.js',
    '_app/immutable/entry/start.A1.js',
    '_app/immutable/entry/app.B1.js',
    '_app/immutable/nodes/0.N0.js',
    '_app/immutable/nodes/1.N1.js',
    '_app/immutable/chunks/shared.S1.js',
    '_app/immutable/assets/0.C0.css'
  ].reduce((sum, p) => sum + size[p], 0);
  const home = everyPage + size['_app/immutable/nodes/2.N2.js'];
  const bigPage =
    everyPage + size['_app/immutable/nodes/3.N3.js'] + size['_app/immutable/chunks/big.G1.js'];
  const total = Object.values(size).reduce((a, b) => a + b, 0);
  return { root, home, bigPage, total };
}

function run(build, limit) {
  const limitFile = join(build.root, 'limit.txt');
  writeFileSync(limitFile, `# a comment\n${limit}\n`);
  const result = spawnSync(process.execPath, [SCRIPT, build.root, limitFile], {
    encoding: 'utf8'
  });
  rmSync(build.root, { recursive: true, force: true });
  return { code: result.status, out: result.stdout, err: result.stderr };
}

test('passes when the largest page is under the limit, and says which page it is', () => {
  const build = fakeBuild();
  const { code, out } = run(build, build.bigPage + 1);
  assert.equal(code, 0);
  assert.match(out, new RegExp(`Largest page: /big, .* \\(${build.bigPage} bytes\\)`));
  assert.match(out, new RegExp(`Limit: .* \\(${build.bigPage + 1} bytes\\)`));
  assert.match(out, /\(for information, not checked\)/);
  assert.match(out, /PASS/);
});

test('counts a page’s shared chunks, its layouts and its CSS, not other pages’ code', () => {
  const build = fakeBuild({ big: 4000 });
  const { out } = run(build, 10 ** 6);
  const line = (bytes, page, count) =>
    new RegExp(`${(bytes / 1024).toFixed(1)} KiB {2}${page} {2}\\(${count} files\\)`);
  assert.match(out, line(build.bigPage, '/big', 9));
  assert.match(out, line(build.home, '/', 8));
});

test('fails when the largest page is over the limit, naming the page', () => {
  const build = fakeBuild();
  const { code, err } = run(build, build.bigPage - 1);
  assert.equal(code, 1);
  assert.match(err, /FAIL: \/big is 1 bytes over the limit/);
});

test('the total of the whole build never fails the check', () => {
  const build = fakeBuild({ big: 3000, shared: 500, worker: 5000 });
  assert.ok(build.total > build.bigPage + 5000);
  const { code, out } = run(build, build.bigPage);
  assert.equal(code, 0);
  assert.match(
    out,
    new RegExp(`Everything in the build: 11 files, ${(build.total / 1024).toFixed(1)} KiB gzip`)
  );
});

test('fails, rather than guessing, when it can’t find the pages in the build', () => {
  const build = fakeBuild();
  writeFileSync(join(build.root, '_app/immutable/entry/app.B1.js'), 'export{}');
  const { code, err } = run(build, 10 ** 6);
  assert.equal(code, 1);
  assert.match(err, /no page loaders found/);
});
