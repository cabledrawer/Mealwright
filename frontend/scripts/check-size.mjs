// The browser code size limit (spec "Keeping the UI good", item 5). Fails when the largest
// page's code has grown past the limit in browser-code-limit.txt.
//
//   cd frontend && npm run build && node scripts/check-size.mjs
//   node scripts/check-size.mjs <build folder> <limit file>    (the tests use this form)
//
// What is measured, page by page: everything a browser fetches to open that page from
// cold. That is SvelteKit's start code, the app's own code, the layouts the page sits in
// and the page itself, with every shared chunk they import, plus their CSS and theme.js.
// Each file is compressed on its own with gzip at the highest level (the way a browser
// receives it), then added up. The largest page is checked against the limit. Fonts and
// images are not counted.
//
// The total of every .js and .css file in the build (the service worker included) is
// printed too, for information only: it is never checked.
//
// The pages and their files come from the build's own route table: the app's entry file
// lists each page's layouts, and each page's loader lists the files it needs. If those
// can't be found, the check fails rather than guessing. Node only; nothing is installed
// or sent.
import { existsSync, readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

const HERE = dirname(fileURLToPath(import.meta.url));
const BUILD = resolve(process.argv[2] ?? join(HERE, '..', 'build'));
const LIMIT_FILE = resolve(process.argv[3] ?? join(HERE, '..', 'browser-code-limit.txt'));
const IMMUTABLE = join(BUILD, '_app', 'immutable');

const kb = (n) => `${(n / 1024).toFixed(1)} KiB`;

function fail(message) {
  console.error(message);
  process.exit(1);
}

function files(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    return entry.isDirectory() ? files(path) : [path];
  });
}

function readLimit() {
  const line = readFileSync(LIMIT_FILE, 'utf8')
    .split('\n')
    .map((l) => l.trim())
    .find((l) => l && !l.startsWith('#'));
  const limit = Number(line);
  if (!Number.isInteger(limit) || limit <= 0) {
    fail(`${LIMIT_FILE}: the first line that isn't a comment must be a number of bytes`);
  }
  return limit;
}

const gzipped = new Map();
function gzipSize(file) {
  if (!gzipped.has(file)) gzipped.set(file, gzipSync(readFileSync(file), { level: 9 }).length);
  return gzipped.get(file);
}

/** A file and every file it imports by name ("import ... from './x.js'"), however deep. */
function withImports(file, seen) {
  if (seen.has(file)) return;
  seen.add(file);
  const source = readFileSync(file, 'utf8');
  for (const match of source.matchAll(/(?:from|import)\s*["'`](\.\.?\/[^"'`]+\.js)["'`]/g)) {
    const imported = resolve(dirname(file), match[1]);
    if (existsSync(imported)) withImports(imported, seen);
  }
}

function inFolder(folder, test, what) {
  const dir = join(IMMUTABLE, folder);
  const name = existsSync(dir) && readdirSync(dir).find(test);
  if (!name) fail(`The build has no _app/immutable/${folder}/${what}: can't measure the pages.`);
  return join(dir, name);
}

/** Each page with every file it needs, read from the app's entry file. */
function pages() {
  const start = inFolder('entry', (n) => n.startsWith('start.') && n.endsWith('.js'), 'start.*.js');
  const app = inFolder('entry', (n) => n.startsWith('app.') && n.endsWith('.js'), 'app.*.js');
  const source = readFileSync(app, 'utf8');
  const where = relative(BUILD, app);

  // Vite's list of the files the page loaders need, then each loader's picks from it.
  const list = source.match(/__vite__mapDeps=[^[]*\[([^\]]*)\]/);
  const needs = list ? [...list[1].matchAll(/["'`]([^"'`]+)["'`]/g)].map((m) => m[1]) : [];
  const loaders = new Map();
  const loader =
    /import\(\s*["'`]\.\.\/nodes\/(\d+)\.[^"'`]*["'`]\s*\)\s*(?:,\s*__vite__mapDeps\(\[([\d,\s]*)\]\))?/g;
  for (const m of source.matchAll(loader)) {
    const picks = (m[2] ?? '')
      .split(',')
      .filter((s) => s.trim())
      .map((i) => needs[Number(i)]);
    if (picks.includes(undefined)) fail(`${where}: a page loader names a file that isn't listed.`);
    loaders.set(
      Number(m[1]),
      picks.map((p) => join(BUILD, p))
    );
  }
  if (loaders.size === 0) fail(`${where}: no page loaders found.`);

  const table = /["'`](\/[^"'`]*)["'`]\s*:\s*\[\s*~?(\d+)\s*(?:,\s*\[([\d,\s]*)\])?/g;
  const routes = [...source.matchAll(table)];
  if (routes.length === 0) fail(`${where}: no route table found.`);

  const theme = join(BUILD, 'theme.js');
  return routes.map(([, route, leaf, layouts]) => {
    const numbers = (layouts ?? '').split(',').filter((s) => s.trim());
    const nodes = [0, ...numbers.map(Number), Number(leaf)];
    const seen = new Set();
    for (const file of [start, app]) withImports(file, seen);
    for (const n of nodes) {
      const own = (f) => f.startsWith(`${n}.`) && f.endsWith('.js');
      withImports(inFolder('nodes', own, `${n}.*.js`), seen);
      for (const file of loaders.get(n) ?? []) {
        if (!existsSync(file)) fail(`A page needs ${relative(BUILD, file)}, which isn't there.`);
        if (file.endsWith('.js')) withImports(file, seen);
        else seen.add(file);
      }
    }
    if (existsSync(theme)) seen.add(theme);
    const name = route.replace(/\/\([^)]*\)/g, '') || '/';
    return { name, files: seen.size, gzip: [...seen].reduce((sum, f) => sum + gzipSize(f), 0) };
  });
}

if (!existsSync(BUILD)) fail('There is no frontend/build. Run `npm run build` first.');
const code = files(BUILD).filter((f) => /\.(js|css)$/.test(f));
if (code.length === 0) fail('frontend/build has no .js or .css files: nothing to measure.');

const limit = readLimit();
const measured = pages().sort((a, b) => b.gzip - a.gzip);
const largest = measured[0];
const total = code.reduce((sum, f) => sum + gzipSize(f), 0);

console.log('Largest pages (gzip, shared code included):');
for (const page of measured.slice(0, 5)) {
  console.log(`  ${kb(page.gzip).padStart(10)}  ${page.name}  (${page.files} files)`);
}
console.log(`Largest page: ${largest.name}, ${kb(largest.gzip)} (${largest.gzip} bytes).`);
console.log(
  `Limit: ${kb(limit)} (${limit} bytes), ${((largest.gzip / limit) * 100).toFixed(0)}% used.`
);
console.log(
  `Everything in the build: ${code.length} files, ${kb(total)} gzip (for information, not checked).`
);

if (largest.gzip > limit) {
  fail(
    `FAIL: ${largest.name} is ${largest.gzip - limit} bytes over the limit.\n` +
      "Make it smaller. Raising the limit needs cabledrawer's OK (spec: Keeping the UI good, item 5)."
  );
}
console.log('PASS');
