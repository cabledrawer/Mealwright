// The slowest browser tests across one or more Playwright JSON reports, slowest first. One line
// each, "12.3 s  [project] file:line › title" (the time of its last try). For ./check (cabledrawer 8 Nov).
// Usage: node scripts/slowest.mjs <how many> <report.json>...
import { existsSync, readFileSync } from 'node:fs';

const [count, ...files] = process.argv.slice(2);

function* specs(suite, titles = []) {
  const here = suite.title && !suite.title.endsWith('.ts') ? [...titles, suite.title] : titles;
  for (const spec of suite.specs ?? []) yield { spec, titles: here };
  for (const child of suite.suites ?? []) yield* specs(child, here);
}

const found = [];
for (const file of files.filter((f) => existsSync(f))) {
  const report = JSON.parse(readFileSync(file, 'utf8'));
  for (const suite of report.suites ?? []) {
    for (const { spec, titles } of specs(suite)) {
      for (const test of spec.tests) {
        const last = test.results.at(-1);
        if (!last) continue;
        const name = `[${test.projectName}] ${spec.file}:${spec.line} › ${[...titles, spec.title].join(' › ')}`;
        found.push({ ms: last.duration, name });
      }
    }
  }
}
found.sort((a, b) => b.ms - a.ms);
for (const { ms, name } of found.slice(0, Number(count))) {
  console.log(`${(ms / 1000).toFixed(1).padStart(6)} s  ${name}`);
}
