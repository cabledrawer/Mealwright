// What ./check needs from Playwright's JSON reports, and the flaky-test rule (cabledrawer 8 Nov, T2).
// Used by flaky.mjs (the command line) and tested by flaky.test.mjs with made-up reports.
//
// A test is named by its KEY, "[project] file › title" (describe titles joined with " › "), with no
// line number: lines move when a file is edited, and the history must still match.
import { readFileSync } from 'node:fs';
import { basename } from 'node:path';

export function readReport(path) {
  return JSON.parse(readFileSync(path, 'utf8'));
}

/** Every test in a report: { project, file, line, titles, status }. */
export function* tests(report) {
  function* walk(suite, titles) {
    const here = suite.title && !suite.title.endsWith('.ts') ? [...titles, suite.title] : titles;
    for (const spec of suite.specs ?? []) {
      for (const test of spec.tests ?? []) {
        yield {
          project: test.projectName,
          file: spec.file,
          line: spec.line,
          titles: [...here, spec.title],
          status: test.status,
        };
      }
    }
    for (const child of suite.suites ?? []) yield* walk(child, here);
  }
  for (const suite of report.suites ?? []) yield* walk(suite, []);
}

export const keyOf = (t) => `[${t.project}] ${t.file} › ${t.titles.join(' › ')}`;

/** The tests that failed once and passed on their retry. */
export const flakyTests = (report) => [...tests(report)].filter((t) => t.status === 'flaky');

/** The tests that failed every try. */
export const failedTests = (report) => [...tests(report)].filter((t) => t.status === 'unexpected');

/** Why a report is not a complete run, or "" when it is: Playwright stopped early (too many
 *  failures, the time limit, a broken start-up: these leave "errors" or at least maxFailures
 *  failed tests), so the tests that didn't run say nothing. */
export function incompleteReason(report, maxFailures) {
  if ((report.errors ?? []).length) return `Playwright reported an error: ${report.errors[0].message ?? 'unknown'}`.split('\n')[0];
  const failed = report.stats?.unexpected ?? 0;
  if (maxFailures > 0 && failed >= maxFailures) return `${failed} failed tests reached the limit of ${maxFailures}`;
  return '';
}

/** The rule. `flaky` is this run's flaky tests ({ key, file }), `previous` the keys flaky in the
 *  last completed full run, `newFiles` the spec files (names) added on this branch.
 *  - twice: flaky now and in the previous completed full run;
 *  - newFile: flaky even once, in a spec file that is new on the branch. */
export function judge({ flaky, previous = [], newFiles = [] }) {
  const before = new Set(previous);
  const fresh = new Set(newFiles.map((f) => basename(f)));
  const twice = [];
  const newFile = [];
  for (const t of flaky) {
    if (before.has(t.key)) twice.push(t.key);
    if (fresh.has(basename(t.file))) newFile.push(t.key);
  }
  return { twice, newFile };
}
