// Precompresses the built web app, once, at build time (0.9.5 speed work; proposed, for cabledrawer).
// Next to each text file of the build (code, styles, pages, the manifest, icons drawn as text)
// it writes `<name>.br` (Brotli) and `<name>.gz` (gzip). The server sends one of them, as it is,
// to a browser that says it can read it, and the plain file to every other. Nothing is
// compressed while the app runs, so a small server pays no processor time for it.
//
//   node scripts/compress.mjs [build folder]      (`npm run build` runs it last)
//
// Photos, fonts and other files that are already compressed are left alone, and so is any file
// the compressed copy would not make smaller. Node's own zlib: nothing is installed or sent.
import {
  readdirSync,
  readFileSync,
  statSync,
  writeFileSync,
  unlinkSync,
  existsSync
} from 'node:fs';
import { dirname, extname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';
import { brotliCompressSync, constants, gzipSync } from 'node:zlib';

/** The kinds of file worth compressing: text. Fonts (woff2) and png are compressed already. */
export const TEXT = new Set([
  '.js',
  '.css',
  '.html',
  '.svg',
  '.json',
  '.webmanifest',
  '.txt',
  '.map'
]);
/** Under this a file is not worth the second request's bookkeeping. */
export const MIN_BYTES = 512;

function files(dir) {
  return readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    return entry.isDirectory() ? files(path) : [path];
  });
}

/** Write the .br and .gz of every text file under `build`; returns what was written. */
export function compressBuild(build) {
  const written = [];
  for (const file of files(build)) {
    if (!TEXT.has(extname(file))) continue;
    const plain = readFileSync(file);
    for (const [suffix, packed] of [
      [
        '.br',
        () =>
          brotliCompressSync(plain, {
            params: {
              [constants.BROTLI_PARAM_QUALITY]: 11,
              [constants.BROTLI_PARAM_SIZE_HINT]: plain.length
            }
          })
      ],
      ['.gz', () => gzipSync(plain, { level: 9 })]
    ]) {
      const target = file + suffix;
      if (existsSync(target)) unlinkSync(target); // never leave a copy of an older file
      if (plain.length < MIN_BYTES) continue;
      const out = packed();
      if (out.length >= plain.length) continue;
      writeFileSync(target, out);
      written.push(target);
    }
  }
  return written;
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const build = resolve(
    process.argv[2] ?? join(dirname(fileURLToPath(import.meta.url)), '..', 'build')
  );
  if (!existsSync(build) || !statSync(build).isDirectory()) {
    console.error(`No built web app at ${build}: run the build first.`);
    process.exit(1);
  }
  const written = compressBuild(build);
  const total = written.reduce((sum, file) => sum + statSync(file).size, 0);
  console.log(`compress: ${written.length} files, ${(total / 1024).toFixed(0)} KiB`);
}
