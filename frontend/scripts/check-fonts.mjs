// Fails when the web build carries a font file for any script but latin and latin-ext (0.9.5: the
// bundled fonts ship only those two subsets). Fontsource names each file
// "<font>-<subset>-<axes>-<style>.<hash>.woff2", so the subset is read from the name.
//
//   node scripts/check-fonts.mjs [build folder]
//
// Node only; nothing is installed or sent. Run by ./check after the web build.
import { existsSync, readdirSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

export const KEPT = ['latin', 'latin-ext'];
const FONT_FILE = /\.(woff2?|ttf|otf|eot)$/i;
const SUBSET = /-(latin-ext|latin|[a-z]+(?:-ext)?)-(?:wght|[a-z]*\d*)-(?:normal|italic)\./;

/** Every font file under a folder, as a path relative to it. */
export function fontFiles(folder, base = folder) {
  const found = [];
  for (const entry of readdirSync(folder, { withFileTypes: true })) {
    const path = join(folder, entry.name);
    if (entry.isDirectory()) found.push(...fontFiles(path, base));
    else if (FONT_FILE.test(entry.name)) found.push(path.slice(base.length + 1));
  }
  return found.sort();
}

/** The font files that are not latin or latin-ext (a file whose subset can't be read counts). */
export function unwanted(files) {
  return files.filter((file) => {
    const name = file.split('/').pop() ?? file;
    const subset = SUBSET.exec(name)?.[1];
    return !subset || !KEPT.includes(subset);
  });
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const build = resolve(
    process.argv[2] ?? join(dirname(fileURLToPath(import.meta.url)), '..', 'build')
  );
  if (!existsSync(build)) throw new Error(`No build folder at ${build}: run the build first.`);
  const files = fontFiles(build);
  const extra = unwanted(files);
  if (files.length === 0) {
    console.error('The build holds no font files at all: the fonts are missing.');
    process.exit(1);
  }
  if (extra.length) {
    console.error(
      `These font files are not latin or latin-ext:\n${extra.map((f) => `  ${f}`).join('\n')}`
    );
    process.exit(1);
  }
  console.log(`${files.length} font files, all latin or latin-ext.`);
}
