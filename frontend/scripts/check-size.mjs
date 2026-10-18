// The browser code size limit (spec "Keeping the UI good", item 5). Fails when the app's
// code sent to the browser has grown past the limit in browser-code-limit.txt.
//
//   cd frontend && npm run build && node scripts/check-size.mjs
//
// What is measured: every .js and .css file in build/ (the app's code and styles, the
// service worker and theme.js), each compressed on its own with gzip at the highest level
// (the way a browser receives it), then added up. Fonts and images are not counted. The
// uncompressed total is printed for information. Node only; nothing is installed or sent.
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { gzipSync } from 'node:zlib';

const HERE = dirname(fileURLToPath(import.meta.url));
const BUILD = join(HERE, '..', 'build');
const LIMIT_FILE = join(HERE, '..', 'browser-code-limit.txt');

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
    throw new Error(`${LIMIT_FILE}: the first line that isn't a comment must be a number of bytes`);
  }
  return limit;
}

let code;
try {
  code = files(BUILD).filter((f) => /\.(js|css)$/.test(f));
} catch {
  console.error('There is no frontend/build. Run `npm run build` first.');
  process.exit(1);
}
if (code.length === 0) {
  console.error('frontend/build has no .js or .css files: nothing to measure.');
  process.exit(1);
}

const sizes = code.map((file) => {
  const bytes = readFileSync(file);
  return {
    file: relative(BUILD, file),
    raw: bytes.length,
    gzip: gzipSync(bytes, { level: 9 }).length
  };
});
const raw = sizes.reduce((sum, s) => sum + s.raw, 0);
const gzip = sizes.reduce((sum, s) => sum + s.gzip, 0);
const limit = readLimit();
const kb = (n) => `${(n / 1024).toFixed(1)} KiB`;

console.log(
  `Browser code: ${code.length} files, ${kb(raw)} uncompressed, ${kb(gzip)} gzip (${gzip} bytes).`
);
console.log('Largest files (gzip):');
for (const s of [...sizes].sort((a, b) => b.gzip - a.gzip).slice(0, 5)) {
  console.log(`  ${kb(s.gzip).padStart(10)}  ${s.file}`);
}
console.log(`Limit: ${kb(limit)} (${limit} bytes), ${((gzip / limit) * 100).toFixed(0)}% used.`);

if (gzip > limit) {
  console.error(
    `FAIL: the browser code is ${gzip - limit} bytes over the limit.\n` +
      "Make it smaller. Raising the limit needs cabledrawer's OK (spec: Keeping the UI good, item 5)."
  );
  process.exit(1);
}
console.log('PASS');
