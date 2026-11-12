// Settings → About → Report a problem (spec section 7, "Bug reports", cabledrawer 17 Oct; mockup
// Dark-Report09-Phone; plan row X2). The words from the mockup are the mockup's; every other
// sentence here is "proposed, for cabledrawer" (docs/dev/words.md section 71).
//
// The report is built in the browser from what the server sent and what the person kept and
// typed. Copy, Download and Open on GitHub all use the same text, so what is sent is what was
// seen. Nothing here connects anywhere: Open on GitHub is a link the person clicks.

import type { ProblemReport } from './client/problemReport';
import { todayHere } from './aboutWords';

/** About's Help heading and its row (mockup Dark-About09-Phone). */
export const HELP_HEADING = 'Help';
export const TITLE = 'Report a problem';
export const INTRO =
  'Mealwright never sends this. You see all of it first, change anything, then send it yourself.';
export const DOING = 'What were you doing?';
export const IN_REPORT = 'What’s in the report';
export const REMOVED_NOTE =
  'Already removed: names, recipes, pantry contents and your server’s address.';
export const OPEN_ON_GITHUB = 'Open on GitHub';
export const GITHUB_HINT = 'Opens a new issue in your browser, filled in. Needs a GitHub account.';
export const COPY = 'Copy';
export const DOWNLOAD = 'Download';
export const REMOVE_LINE = 'Remove this line';

// Proposed, for cabledrawer.
export const LINE_REMOVED = 'Line removed';
export const COPIED = 'Report copied';
export const COPY_FAILED = 'Couldn’t copy. Use Download instead.';
export const NO_ERRORS = 'No errors in the last 24 hours';
export const MEMBER_NOTE = 'Errors from the server’s log are only in an admin’s report.';
export const NO_LINES = 'Every line is removed. Only what you typed will be sent.';
export const TRIMMED_NOTE =
  'Too long for one link, so GitHub gets the start of it. Copy or Download has all of it.';
/** Put at the end of the text GitHub gets when it had to be cut. */
export const TRIMMED_MARK = '[Cut short to fit in a link.]';
export const lineLabel = (n: number) => `Report line ${n}`;

/** The lines the screen starts with: version, browser, then the errors. */
export function startingLines(report: ProblemReport): string[] {
  const errors = report.errors_included ? (report.errors.length ? report.errors : [NO_ERRORS]) : [];
  return [report.version, report.browser, ...errors];
}

/** The whole report as text: the same for Copy, Download and GitHub. */
export function reportText(doing: string, lines: string[]): string {
  const kept = lines.map((line) => line.trim()).filter(Boolean);
  const parts = [DOING, doing.trim() || '(left empty)'];
  if (kept.length) parts.push('', IN_REPORT, ...kept);
  return parts.join('\n') + '\n';
}

/** The new issue's title: "Problem: " and the start of what they were doing. */
export function issueTitle(doing: string): string {
  const first = doing.trim().split('\n')[0]!.trim();
  if (!first) return 'Problem report';
  // Counted and cut by character (code point), so an emoji is never split in half.
  const chars = Array.from(first);
  const cut = chars.length > 60 ? `${chars.slice(0, 59).join('').trimEnd()}…` : first;
  return `Problem: ${cut}`;
}

/** GitHub refuses addresses much longer than about 8 KB, so the link stays under this. */
export const LINK_LIMIT = 8000;

function linkFor(page: string, title: string, body: string): string {
  return `${page}?title=${encodeURIComponent(wellFormed(title))}&body=${encodeURIComponent(wellFormed(body))}`;
}

/** Half an emoji (a lone surrogate) becomes "�": encodeURIComponent throws on it. */
function wellFormed(text: string): string {
  return text.replace(
    /[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/g,
    '�'
  );
}

/**
 * The new-issue link with the title and text filled in. If it would be longer than LINK_LIMIT,
 * the text is cut (at a line end where that keeps most of it) and TRIMMED_MARK added; `trimmed` says so.
 */
export function issueLink(
  page: string,
  title: string,
  body: string,
  limit: number = LINK_LIMIT
): { href: string; trimmed: boolean } {
  const whole = linkFor(page, title, body);
  if (whole.length <= limit) return { href: whole, trimmed: false };
  const fits = (n: number) => linkFor(page, title, cutAt(body, n)).length <= limit;
  // The most characters of the text that still fit, found by halving.
  let low = 0;
  let high = body.length;
  while (low < high) {
    const mid = Math.ceil((low + high) / 2);
    if (fits(mid)) low = mid;
    else high = mid - 1;
  }
  return { href: linkFor(page, title, cutAt(body, low)), trimmed: true };
}

function cutAt(body: string, n: number): string {
  let start = body.slice(0, n);
  // Never split a character made of two code units (an emoji).
  if (/[\uD800-\uDBFF]$/.test(start)) start = start.slice(0, -1);
  const lineEnd = start.lastIndexOf('\n');
  // Cut at the last line end, unless that would lose most of what fits (one long paragraph):
  // then cut mid-line.
  const kept = lineEnd > 0 && lineEnd >= start.length / 2 ? start.slice(0, lineEnd) : start;
  return `${kept}\n${TRIMMED_MARK}\n`;
}

/** "mealwright-problem-report-2026-11-12.txt". */
export function fileName(now: Date = new Date()): string {
  return `mealwright-problem-report-${todayHere(now)}.txt`;
}
