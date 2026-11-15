// Turns the results files of perf/measure.ts into the markdown tables of docs/dev/performance.md.
//   node perf/table.ts perf/results-phone.json perf/results-desktop.json
import { readFileSync } from 'node:fs';

const median = (xs: number[]) => {
  const s = [...xs].sort((a, b) => a - b);
  return s.length % 2 ? s[(s.length - 1) / 2]! : Math.round((s[s.length / 2 - 1]! + s[s.length / 2]!) / 2);
};
const fmt = (xs: number[]) => (xs.length ? `${median(xs)} / ${Math.max(...xs)}` : 'n/a');

for (const file of process.argv.slice(2)) {
  const r = JSON.parse(readFileSync(file, 'utf8')) as {
    profile: string;
    runs: number;
    results: Record<string, Record<string, { ms: number; api: { path: string; wait: number }[] }[]>>;
    server: Record<string, number[]>;
  };
  console.log(`\n### ${r.profile}: median / slowest, in ms, of ${r.runs} runs\n`);
  console.log('| What | First load | Repeat load | Slowest API wait seen (first load) |\n|---|---|---|---|');
  const names = [...new Set([...Object.keys(r.results.first), ...Object.keys(r.results.repeat)])];
  for (const name of names) {
    const first = r.results.first[name] ?? [];
    const slowest = first.flatMap((s) => s.api).sort((a, b) => b.wait - a.wait)[0];
    console.log(`| ${name} | ${fmt(first.map((s) => s.ms))} | ${fmt((r.results.repeat[name] ?? []).map((s) => s.ms))} | ${slowest ? `${slowest.wait} (${slowest.path.split('?')[0]})` : 'n/a'} |`);
  }
  const ready = r.results.ready?.['Ready for offline'] ?? [];
  if (ready.length) console.log(`\nReady for offline (first open until the page is under the worker with its files on the device), median / slowest, in ms: ${fmt(ready.map((x) => x.ms))}`);
  console.log('\n| Action | Time to show | Slowest API wait |\n|---|---|---|');
  for (const [name, samples] of Object.entries(r.results.action)) {
    const slowest = samples.flatMap((s) => s.api).sort((a, b) => b.wait - a.wait)[0];
    console.log(`| ${name} | ${fmt(samples.map((s) => s.ms))} | ${slowest ? `${slowest.wait} (${slowest.path.split('?')[0]})` : 'none'} |`);
  }
  console.log('\n| API call (no slowing, on the container) | ms |\n|---|---|');
  for (const [name, xs] of Object.entries(r.server)) console.log(`| ${name} | ${fmt(xs)} |`);
}
