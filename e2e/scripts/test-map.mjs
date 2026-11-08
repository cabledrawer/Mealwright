// Which tests a change touches (cabledrawer 8 Nov, T2b item 2), for ./check --fast. Reads e2e/test-map.json.
//   node scripts/test-map.mjs validate
//       Fails (exit 1, the reasons on stderr) when a backend test file or a browser spec file is
//       named by no area, or a name in the map matches no file. A test anyone adds must be mapped.
//   node scripts/test-map.mjs select [--base <commit>]
//       The changed files (against the base, default the merge base with origin/main, plus work not
//       committed yet), as tab-separated lines: "all<TAB>reason" when everything must run, else
//       "backend<TAB>tests/test_x.py" and "browser<TAB>plan.spec.ts" lines, then "why<TAB>text".
//       Without a base to compare with it says "all".
// The full ./check never reads the map for choosing: it always runs everything.
import { execFileSync } from 'node:child_process';
import { readdirSync, readFileSync, statSync } from 'node:fs';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const E2E = fileURLToPath(new URL('..', import.meta.url));
const ROOT = join(E2E, '..');

/** A glob as a regular expression: ** goes through folders, * and ? stay inside one. */
export function globToRegex(glob) {
  let out = '';
  for (let i = 0; i < glob.length; i++) {
    const c = glob[i];
    if (c === '*' && glob[i + 1] === '*') {
      i++;
      if (glob[i + 1] === '/') {
        i++;
        out += '(?:.*/)?';
      } else out += '.*';
    } else if (c === '*') out += '[^/]*';
    else if (c === '?') out += '[^/]';
    else out += c.replace(/[.+^${}()|[\]\\]/g, '\\$&');
  }
  return new RegExp(`^${out}$`);
}
const matches = (globs, path) => globs.some((g) => globToRegex(g).test(path));

export const readMap = () => JSON.parse(readFileSync(join(E2E, 'test-map.json'), 'utf8'));

function walk(dir, keep) {
  const found = [];
  for (const name of readdirSync(dir)) {
    const full = join(dir, name);
    if (statSync(full).isDirectory()) found.push(...walk(full, keep));
    else if (keep(name)) found.push(full);
  }
  return found;
}
/** backend/tests test files relative to backend/tests; spec files relative to e2e/tests. */
export const backendTests = () =>
  walk(join(ROOT, 'backend/tests'), (n) => /^test_.*\.py$/.test(n)).map((f) => relative(join(ROOT, 'backend/tests'), f)).sort();
export const browserSpecs = () => readdirSync(join(E2E, 'tests')).filter((n) => n.endsWith('.spec.ts')).sort();

/** The reasons the map is not complete: [] when it is. */
export function problems(map, backend, browser) {
  const out = [];
  const lists = (kind) => [...(kind === 'backend' ? map.always?.backend ?? [] : []), ...map.areas.flatMap((a) => a[kind] ?? [])];
  for (const [kind, files, label] of [
    ['backend', backend, 'backend test file'],
    ['browser', browser, 'browser spec file'],
  ]) {
    const globs = lists(kind);
    for (const f of files) if (!matches(globs, f)) out.push(`${label} not in e2e/test-map.json: ${f}`);
    for (const g of globs) if (!files.some((f) => globToRegex(g).test(f))) out.push(`e2e/test-map.json names no ${label}: ${g}`);
  }
  return out;
}

/** The sentences (quoted or in backticks) a diff adds or removes, to look for in the specs. */
export function wordsOf(diff) {
  const words = new Set();
  for (const line of diff.split('\n')) {
    if (!/^[+-][^+-]/.test(line)) continue;
    const text = line.slice(1);
    for (const m of text.matchAll(/“([^”]{5,})”|"([^"]{5,})"|'([^']{5,})'|`([^`]{5,})`|>([^<>{}]{5,})</g)) {
      const w = (m[1] ?? m[2] ?? m[3] ?? m[4] ?? m[5]).trim();
      if (/[A-Za-z]{3}/.test(w) && !/^[\w./\\$-]+$/.test(w)) words.add(w);
    }
  }
  return [...words];
}

/** Spec files whose text holds any of the words (case-insensitive; curly and straight apostrophes alike). */
export function specsWith(words, specTexts) {
  const norm = (s) => s.toLowerCase().replace(/[’‘]/g, "'");
  const hits = new Map();
  for (const [name, text] of Object.entries(specTexts)) {
    const t = norm(text);
    const found = words.filter((w) => t.includes(norm(w)));
    if (found.length) hits.set(name, found);
  }
  return hits;
}

/** What to run for these changed paths. `wordHits` is specsWith's answer. */
export function select(map, changed, wordHits = new Map()) {
  const backend = new Set();
  const browser = new Set();
  const why = [];
  const backendAll = backendTests();
  const specs = browserSpecs();
  const pick = (globs, files) => files.filter((f) => matches(globs, f));
  let everything = '';
  let anyBackend = false;
  for (const path of changed) {
    if (matches(map.ignore_paths ?? [], path)) continue;
    if (path.startsWith('backend/')) anyBackend = true;
    const own = /^backend\/tests\/(.*test_[^/]*\.py)$/.exec(path);
    if (own) {
      backend.add(own[1]);
      why.push(`${path}: a test file changed`);
      continue;
    }
    const spec = /^e2e\/tests\/([^/]*\.spec\.ts)$/.exec(path);
    if (spec) {
      browser.add(spec[1]);
      why.push(`${path}: a spec file changed`);
      continue;
    }
    if (matches(map.all_paths ?? [], path)) {
      everything = `${path} is shared by every test`;
      break;
    }
    const areas = map.areas.filter((a) => matches(a.paths ?? [], path));
    if (!areas.length) {
      everything = `${path} is in no area of e2e/test-map.json`;
      break;
    }
    for (const a of areas) {
      for (const f of pick(a.backend ?? [], backendAll)) backend.add(f);
      for (const f of pick(a.browser ?? [], specs)) browser.add(f);
      why.push(`${path}: ${a.name}`);
    }
  }
  if (everything) return { all: everything, backend, browser, why };
  if (anyBackend) for (const f of pick(map.always?.backend ?? [], backendAll)) backend.add(f);
  for (const [name, found] of wordHits) {
    browser.add(name);
    why.push(`${name}: looks for ${found.slice(0, 3).map((w) => `"${w}"`).join(', ')}${found.length > 3 ? ' …' : ''}`);
  }
  return { all: '', backend, browser, why };
}

const git = (args) => execFileSync('git', ['-C', ROOT, ...args], { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'], maxBuffer: 64 << 20 });

function changedSince(base) {
  const tracked = git(['diff', '--name-only', base]).split('\n');
  const fresh = git(['ls-files', '--others', '--exclude-standard']).split('\n');
  return [...new Set([...tracked, ...fresh].filter(Boolean))];
}

if (import.meta.url === `file://${process.argv[1]}`) {
  try {
    const [mode, ...args] = process.argv.slice(2);
    const map = readMap();
    if (mode === 'validate') {
      const bad = problems(map, backendTests(), browserSpecs());
      if (bad.length) {
        console.error(bad.join('\n'));
        process.exit(1);
      }
    } else if (mode === 'select') {
      let base = args[0] === '--base' ? args[1] : '';
      if (!base) {
        try {
          base = git(['merge-base', 'HEAD', 'origin/main']).trim();
        } catch {
          console.log('all\tno origin/main to compare with');
          process.exit(0);
        }
      }
      const changed = changedSince(base);
      let hits = new Map();
      const wordFiles = changed.filter((p) => p === 'docs/dev/words.md' || p.startsWith('frontend/src/'));
      if (wordFiles.length) {
        const diff = git(['diff', '-U0', base, '--', 'docs/dev/words.md', 'frontend/src']);
        const texts = Object.fromEntries(browserSpecs().map((n) => [n, readFileSync(join(E2E, 'tests', n), 'utf8')]));
        hits = specsWith(wordsOf(diff), texts);
      }
      const r = select(map, changed, hits);
      if (r.all) console.log(`all\t${r.all}`);
      else {
        for (const f of [...r.backend].sort()) console.log(`backend\ttests/${f}`);
        for (const f of [...r.browser].sort()) console.log(`browser\t${f}`);
      }
      for (const w of r.why) console.log(`why\t${w}`);
      if (!changed.length) console.log('why\tnothing changed');
    } else throw new Error('Usage: node scripts/test-map.mjs validate | select [--base <commit>]');
  } catch (error) {
    console.error(`test-map.mjs: ${error.message}`);
    process.exit(1);
  }
}
