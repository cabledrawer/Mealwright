// For the fixes pull request after a failed full check (cabledrawer 8 Nov, T2b item 4): the failed
// browser tests, grouped by the pull request that last changed their spec file on this line of
// work (the commits since the merge base with origin/main), so each failure can be filed in one
// fixes PR on top of the line.
//   node scripts/fixes-list.mjs [--base <commit>] <report.json>...
// A pull request is named by the commit subject ("PR 134" or "(#134)"); a commit that names none
// is listed by its hash and subject. A spec file the line never changed says so (the failure came
// from the app or from an earlier line, not from this file). Reads reports only; changes nothing.
import { execFileSync } from 'node:child_process';
import { failedTests, readReport } from './flaky-lib.mjs';

/** The pull request a commit subject names, or "". */
export function prOf(subject) {
  const m = /\bPR\s*#?(\d+)\b/i.exec(subject) ?? /\(#(\d+)\)/.exec(subject);
  return m ? m[1] : '';
}

/** Group failed tests by their last-changing commit. `lastChange(file)` gives { hash, subject } or
 *  null (not changed on this line). Returns lines of text. */
export function fixesLines(failed, lastChange) {
  const groups = new Map();
  for (const t of failed) {
    const change = lastChange(t.file);
    const pr = change ? prOf(change.subject) : '';
    const heading = !change
      ? 'Not changed on this line (spec file as on main)'
      : pr
        ? `PR ${pr}: last changed ${t.file} in ${change.hash} "${change.subject}"`
        : `No PR number in the commit: ${change.hash} "${change.subject}" last changed ${t.file}`;
    if (!groups.has(heading)) groups.set(heading, []);
    groups.get(heading).push(`[${t.project}] ${t.file}:${t.line} › ${t.titles.join(' › ')}`);
  }
  const out = [];
  for (const [heading, items] of groups) {
    out.push(heading);
    for (const item of [...new Set(items)]) out.push(`  - ${item}`);
  }
  return out;
}

function git(args) {
  return execFileSync('git', args, { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }).trim();
}

// Only when run as a command.
if (import.meta.url === `file://${process.argv[1]}`) {
  try {
    const args = process.argv.slice(2);
    let base = '';
    const i = args.indexOf('--base');
    if (i !== -1) base = args.splice(i, 2)[1] ?? '';
    if (!args.length) throw new Error('Usage: node scripts/fixes-list.mjs [--base <commit>] <report.json>...');
    if (!base) {
      try {
        base = git(['merge-base', 'HEAD', 'origin/main']);
      } catch {
        base = '';
      }
    }
    const cache = new Map();
    const lastChange = (file) => {
      if (!cache.has(file)) {
        const range = base ? [`${base}..HEAD`] : [];
        const line = git(['log', '-1', '--format=%h%x09%s', ...range, '--', `tests/${file}`]);
        const [hash, ...rest] = line.split('\t');
        cache.set(file, line ? { hash, subject: rest.join('\t') } : null);
      }
      return cache.get(file);
    };
    const failed = args.flatMap((p) => failedTests(readReport(p)));
    if (!failed.length) process.exit(0);
    console.log(`${failed.length} failed browser test(s), by the PR that last changed their spec file${base ? ` since ${base.slice(0, 8)}` : ''}:`);
    for (const line of fixesLines(failed, lastChange)) console.log(line);
  } catch (error) {
    console.error(`fixes-list.mjs: ${error.message}`);
    process.exit(1);
  }
}
