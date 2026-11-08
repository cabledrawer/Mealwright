// The browser tests' flaky-test rule and report readers, for ./check (cabledrawer 8 Nov, T2).
// A key is "[project] file › title" (no line number).
//   node scripts/flaky.mjs <report.json>...         the flaky tests (failed once, passed on their
//                                                   retry), one key per line; nothing if none
//   node scripts/flaky.mjs --judge [--previous <file>] [--new-files a.spec.ts,b.spec.ts] <report.json>...
//                                                   "twice<TAB>key" and "new<TAB>key" lines for the
//                                                   tests that break the rule (see flaky-lib.mjs)
//   node scripts/flaky.mjs --complete <max failures> <report.json>...
//                                                   exit 0 when every report is of a run that went to
//                                                   the end, else 1 and the reason on stderr
//   node scripts/flaky.mjs --failed <report.json>...  "project<TAB>file<TAB>title › title" per failed test
// Any error (a missing or broken report) exits with an error: ./check records that as a failure,
// never as "no flaky tests".
import { existsSync, readFileSync } from 'node:fs';
import { failedTests, flakyTests, incompleteReason, judge, keyOf, readReport } from './flaky-lib.mjs';

const args = process.argv.slice(2);
const mode = args[0]?.startsWith('--') ? args.shift() : '';

function option(name) {
  const i = args.indexOf(name);
  if (i === -1) return '';
  return args.splice(i, 2)[1] ?? '';
}

function flakyOf(paths) {
  const seen = new Map();
  for (const path of paths) {
    for (const t of flakyTests(readReport(path))) seen.set(keyOf(t), { key: keyOf(t), file: t.file });
  }
  return [...seen.values()];
}

try {
  if (mode === '' || mode === '--list') {
    if (!args.length) throw new Error('Usage: node scripts/flaky.mjs <report.json>...');
    for (const t of flakyOf(args)) console.log(t.key);
  } else if (mode === '--judge') {
    const previousFile = option('--previous');
    const newFiles = option('--new-files').split(',').filter(Boolean);
    const previous =
      previousFile && existsSync(previousFile) ? readFileSync(previousFile, 'utf8').split('\n').filter(Boolean) : [];
    const { twice, newFile } = judge({ flaky: flakyOf(args), previous, newFiles });
    for (const k of twice) console.log(`twice\t${k}`);
    for (const k of newFile) console.log(`new\t${k}`);
  } else if (mode === '--complete') {
    const max = Number(args.shift());
    for (const path of args) {
      const why = incompleteReason(readReport(path), max);
      if (why) {
        console.error(`${path}: ${why}`);
        process.exit(1);
      }
    }
  } else if (mode === '--failed') {
    for (const path of args) {
      for (const t of failedTests(readReport(path))) console.log(`${t.project}\t${t.file}\t${t.titles.join(' › ')}`);
    }
  } else {
    throw new Error(`Unknown option ${mode}`);
  }
} catch (error) {
  console.error(`flaky.mjs: ${error.message}`);
  process.exit(1);
}
