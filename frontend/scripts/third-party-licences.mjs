// Writes build/third-party-licences.txt: the licence notices of the libraries and fonts the web
// app carries, so the image holds them (cabledrawer 12 Nov: "Other open-source parts" stays out of
// About for 0.9.0 as long as the image still carries the other libraries' licence notices; a
// licences screen in About is a 0.9.5 follow-up). Run by `npm run build` (its build script); served as
// /third-party-licences.txt. Node only; nothing is installed or sent.
//
//   node scripts/third-party-licences.mjs [package folder] [build folder]
//
// What is listed: every production dependency in package.json (the bundled fonts and idb), plus
// every package whose code is in the browser bundle, as the build's own plugin recorded it
// (src/build/bundledPackages.ts, .svelte-kit/bundled-packages.json; #207 review M1). Each gets
// its name, version, the licence its package.json names, and the text of its licence file. A
// package with no licence named, or no list from the build, stops the build.
import { existsSync, readdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = resolve(process.argv[2] ?? join(HERE, '..'));
const BUILD = resolve(process.argv[3] ?? join(ROOT, 'build'));

export const BUNDLED_LIST = join('.svelte-kit', 'bundled-packages.json');

/** The packages the build put in the browser bundle (it fails if the build left no list). */
export function bundledNames(root) {
  const file = join(root, BUNDLED_LIST);
  if (!existsSync(file)) throw new Error(`No list of bundled packages at ${file}: run the build.`);
  const names = JSON.parse(readFileSync(file, 'utf8'));
  if (!Array.isArray(names) || names.length === 0) throw new Error(`${file} lists no packages.`);
  return names;
}

const LICENCE_FILE = /^(licen[cs]e|copying|ofl)([-._].*)?(\.txt|\.md)?$/i;

export function licenceFileOf(folder) {
  const names = readdirSync(folder).filter((name) => LICENCE_FILE.test(name));
  names.sort();
  return names.length ? join(folder, names[0]) : null;
}

export function noticeFor(root, name) {
  const folder = join(root, 'node_modules', ...name.split('/'));
  const info = JSON.parse(readFileSync(join(folder, 'package.json'), 'utf8'));
  const licence = typeof info.license === 'string' ? info.license : (info.license?.type ?? '');
  if (!licence) throw new Error(`${name} names no licence in its package.json`);
  const file = licenceFileOf(folder);
  const text = file ? readFileSync(file, 'utf8').trim() : null;
  return { name, version: info.version, licence, text };
}

export function build(root = ROOT, bundled = bundledNames(root)) {
  const own = JSON.parse(readFileSync(join(root, 'package.json'), 'utf8'));
  const names = [...new Set([...Object.keys(own.dependencies ?? {}), ...bundled])].sort();
  const parts = [
    'Mealwright carries these open-source libraries and fonts in its web app.',
    'Each is listed with its version, its licence and its licence text.',
    'Mealwright itself is AGPL-3.0-only. The Python libraries of the server keep their notices in',
    'the image beside their code (each package’s dist-info folder).',
    ''
  ];
  for (const name of names) {
    const found = noticeFor(root, name);
    parts.push('='.repeat(78), `${found.name} ${found.version}`, `Licence: ${found.licence}`, '');
    parts.push(
      found.text ?? '(this package ships no licence file; its licence is named above)',
      ''
    );
  }
  return parts.join('\n');
}

if (process.argv[1] && resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  if (!existsSync(BUILD)) throw new Error(`No build folder at ${BUILD}: run the build first.`);
  writeFileSync(join(BUILD, 'third-party-licences.txt'), build(ROOT));
}
