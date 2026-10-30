// The flaky tests in a Playwright JSON report: each failed once and passed on its retry. One
// line each, "[project] file:line › title", for ./check's summary. Nothing printed if none.
// Usage: node scripts/flaky.mjs <report.json>
import { readFileSync } from 'node:fs';

const report = JSON.parse(readFileSync(process.argv[2], 'utf8'));

function* specs(suite, titles = []) {
  const here = suite.title && !suite.title.endsWith('.ts') ? [...titles, suite.title] : titles;
  for (const spec of suite.specs ?? []) yield { spec, titles: here };
  for (const child of suite.suites ?? []) yield* specs(child, here);
}

for (const suite of report.suites ?? []) {
  for (const { spec, titles } of specs(suite)) {
    for (const test of spec.tests) {
      if (test.status === 'flaky') {
        console.log(`[${test.projectName}] ${spec.file}:${spec.line} › ${[...titles, spec.title].join(' › ')}`);
      }
    }
  }
}
