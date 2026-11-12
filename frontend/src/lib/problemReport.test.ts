// Report a problem (X2): the lines the screen starts with, the one text for Copy, Download and
// GitHub, the issue's title and the link's length limit.

import { describe, expect, it } from 'vitest';
import {
  LINK_LIMIT,
  NO_ERRORS,
  TRIMMED_MARK,
  fileName,
  issueLink,
  issueTitle,
  reportText,
  startingLines
} from './problemReport';

const PAGE = 'https://github.com/placeholder_until_1_0/mealwright/issues/new';
const base = {
  version: 'Mealwright 0.9.0',
  browser: 'Safari 18 · iPhone',
  new_issue_page: PAGE
};

describe('startingLines', () => {
  it('starts with the version and browser, then the errors', () => {
    expect(startingLines({ ...base, errors: ['a', 'b'], errors_included: true })).toEqual([
      'Mealwright 0.9.0',
      'Safari 18 · iPhone',
      'a',
      'b'
    ]);
  });

  it('says so when an admin’s report has no errors', () => {
    expect(startingLines({ ...base, errors: [], errors_included: true })).toEqual([
      'Mealwright 0.9.0',
      'Safari 18 · iPhone',
      NO_ERRORS
    ]);
  });

  it('a member’s report has no error lines', () => {
    expect(startingLines({ ...base, errors: [], errors_included: false })).toEqual([
      'Mealwright 0.9.0',
      'Safari 18 · iPhone'
    ]);
  });
});

describe('reportText', () => {
  it('has what they typed, then every kept line', () => {
    expect(reportText('  Adding a recipe \n', ['Mealwright 0.9.0', ' x '])).toBe(
      'What were you doing?\nAdding a recipe\n\nWhat’s in the report\nMealwright 0.9.0\nx\n'
    );
  });

  it('leaves out emptied lines, and the heading when none is left', () => {
    expect(reportText('', ['  ', ''])).toBe('What were you doing?\n(left empty)\n');
  });
});

describe('issueTitle', () => {
  it('uses the first line of what they were doing', () => {
    expect(issueTitle('The plan froze\nThen more')).toBe('Problem: The plan froze');
  });

  it('cuts a long line at 60 characters', () => {
    const title = issueTitle('x'.repeat(100));
    expect(title).toBe(`Problem: ${'x'.repeat(59)}…`);
  });

  it('cuts by character, never leaving half an emoji (review r1)', () => {
    const typed = `${'x'.repeat(58)}🍅🍅 and more`;
    const title = issueTitle(typed);
    expect(title).toBe(`Problem: ${'x'.repeat(58)}🍅…`);
    expect(() => encodeURIComponent(title)).not.toThrow();
    expect(() => issueLink(PAGE, title, 'x')).not.toThrow();
  });

  it('counts an emoji as one character when deciding to cut', () => {
    const typed = `${'x'.repeat(59)}🍅`;
    expect(issueTitle(typed)).toBe(`Problem: ${typed}`);
  });

  it('has a plain title when nothing was typed', () => {
    expect(issueTitle('  ')).toBe('Problem report');
  });
});

describe('issueLink', () => {
  it('fills in the title and text', () => {
    const { href, trimmed } = issueLink(PAGE, 'Problem: a & b', 'line 1\nline 2');
    expect(trimmed).toBe(false);
    const url = new URL(href);
    expect(`${url.origin}${url.pathname}`).toBe(PAGE);
    expect(url.searchParams.get('title')).toBe('Problem: a & b');
    expect(url.searchParams.get('body')).toBe('line 1\nline 2');
  });

  it('stays under the limit, cutting at a line end and saying so', () => {
    const body = Array.from({ length: 2000 }, (_, i) => `error line ${i} ✕ “quoted”`).join('\n');
    const { href, trimmed } = issueLink(PAGE, 'Problem: x', body);
    expect(trimmed).toBe(true);
    expect(href.length).toBeLessThanOrEqual(LINK_LIMIT);
    const sent = new URL(href).searchParams.get('body')!;
    expect(sent.endsWith(`\n${TRIMMED_MARK}\n`)).toBe(true);
    const kept = sent.slice(0, -`\n${TRIMMED_MARK}\n`.length);
    expect(body.startsWith(kept)).toBe(true);
    expect(body[kept.length]).toBe('\n');
    // Near the limit: one more line would not have fitted.
    expect(href.length).toBeGreaterThan(LINK_LIMIT - 200);
  });

  it('never splits an emoji when one line is too long', () => {
    const body = '🍅'.repeat(3000);
    const { href, trimmed } = issueLink(PAGE, 'Problem report', body, 2000);
    expect(trimmed).toBe(true);
    expect(href.length).toBeLessThanOrEqual(2000);
    // decodeURIComponent throws on half an emoji.
    expect(() => new URL(href).searchParams.get('body')).not.toThrow();
    expect(new URL(href).searchParams.get('body')).not.toContain('�');
  });
});

describe('issueLink with half an emoji typed or pasted (review r2, L8)', () => {
  it('never throws, and sends a replacement character for the lone half', () => {
    const lone = 'broke at \uD83C here and \uDF45 there';
    const title = issueTitle(lone);
    expect(() => issueLink(PAGE, title, lone)).not.toThrow();
    const url = new URL(issueLink(PAGE, title, lone).href);
    expect(url.searchParams.get('title')).toBe('Problem: broke at � here and � there');
    expect(url.searchParams.get('body')).toBe('broke at � here and � there');
  });

  it('keeps a whole emoji', () => {
    const { href } = issueLink(PAGE, 'Problem: 🍅', 'a 🍅 b');
    expect(new URL(href).searchParams.get('body')).toBe('a 🍅 b');
  });

  it('never throws when the text is too long to fit', () => {
    const body = `\uD83C ${'x'.repeat(9000)}`;
    expect(() => issueLink(PAGE, 'Problem: x', body)).not.toThrow();
    expect(issueLink(PAGE, 'Problem: x', body).trimmed).toBe(true);
  });
});

describe('issueLink with one long paragraph', () => {
  it('cuts mid-line when cutting at a line end would lose most of what was typed (review r1)', () => {
    const typed = 'word '.repeat(2000);
    const body = reportText(typed, ['Mealwright 0.9.0', 'Safari 18 · iPhone']);
    const { href, trimmed } = issueLink(PAGE, 'Problem: x', body);
    expect(trimmed).toBe(true);
    expect(href.length).toBeLessThanOrEqual(LINK_LIMIT);
    const sent = new URL(href).searchParams.get('body')!;
    const kept = sent.slice(0, -`\n${TRIMMED_MARK}\n`.length);
    expect(body.startsWith(kept)).toBe(true);
    // Most of the room is what they typed, not just the heading.
    expect(kept.length).toBeGreaterThan(4000);
  });
});

describe('fileName', () => {
  it('names the day', () => {
    expect(fileName(new Date(2026, 10, 12, 9))).toBe('mealwright-problem-report-2026-11-12.txt');
  });
});
