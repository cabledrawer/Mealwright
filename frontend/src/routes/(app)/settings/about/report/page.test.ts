// Settings → About → Report a problem (X2; mockup Dark-Report09-Phone): every line can be
// changed or removed (with Undo), "What were you doing?" is typed here, and Copy, Download and
// Open on GitHub all carry the same text.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { ProblemReport } from '#lib/client/problemReport.js';
import { toasts } from '#lib/toast.svelte.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import Report from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const PAGE = 'https://github.com/placeholder_until_1_0/mealwright/issues/new';

function report(over: Partial<ProblemReport> = {}): ProblemReport {
  return {
    version: 'Mealwright 0.9.0',
    browser: 'Firefox 133 · Linux',
    errors: ['12 Nov 12:41 UTC mealwright.sync: change [ingredient] failed (KeyError)'],
    errors_included: true,
    new_issue_page: PAGE,
    ...over
  };
}

let component: ReturnType<typeof mount> | null = null;
let requests: FakeRequest[] = [];

function open(answer: [number, unknown] = [200, report()]) {
  requests = fakeApi({ 'GET /problem-report': answer });
  component = mount(Report, { target: document.body });
  flushSync();
}

const line = (n: number) => page.getByRole('textbox', { name: `Report line ${n}` });
const github = () => page.getByRole('link', { name: 'Open on GitHub' });
const body = () => new URL(github().element().getAttribute('href')!).searchParams.get('body');

beforeEach(async () => {
  await page.viewport(390, 844);
  toasts.dismiss();
});

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
  toasts.dismiss();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('Report a problem (X2)', () => {
  it('shows every line of the report, each with its own ✕', async () => {
    open();
    await expect
      .element(page.getByRole('heading', { name: 'Report a problem', level: 1 }))
      .toBeVisible();
    await expect.element(line(1)).toHaveValue('Mealwright 0.9.0');
    await expect.element(line(2)).toHaveValue('Firefox 133 · Linux');
    await expect.element(line(3)).toHaveValue(report().errors[0]);
    expect(page.getByRole('button', { name: 'Remove this line' }).elements()).toHaveLength(3);
    await expect
      .element(page.getByText('Already removed: names, recipes, pantry contents', { exact: false }))
      .toBeVisible();
    // Only the report is asked for: nothing else is sent anywhere.
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['GET /problem-report']);
  });

  it('the GitHub link carries what they typed and every line, and opens in a new tab', async () => {
    open();
    await expect.element(line(1)).toBeVisible();
    await page.getByRole('textbox', { name: 'What were you doing?' }).fill('Moving a meal');
    const link = github();
    await expect.element(link).toHaveAttribute('target', '_blank');
    await expect.element(link).toHaveAttribute('rel', 'noopener noreferrer');
    const href = new URL(link.element().getAttribute('href')!);
    expect(`${href.origin}${href.pathname}`).toBe(PAGE);
    expect(href.searchParams.get('title')).toBe('Problem: Moving a meal');
    expect(href.searchParams.get('body')).toBe(
      'What were you doing?\nMoving a meal\n\nWhat’s in the report\nMealwright 0.9.0\n' +
        `Firefox 133 · Linux\n${report().errors[0]}\n`
    );
  });

  it('a changed line is sent as changed', async () => {
    open();
    await line(2).fill('Firefox');
    expect(body()).toContain('\nFirefox\n');
    expect(body()).not.toContain('133');
  });

  it('removing a line takes it out, and Undo puts it back in its place', async () => {
    open();
    await expect.element(line(3)).toBeVisible();
    await page.getByRole('button', { name: 'Remove this line' }).nth(1).click();
    await expect.element(line(3)).not.toBeInTheDocument();
    await expect.element(line(2)).toHaveValue(report().errors[0]);
    expect(body()).not.toContain('Firefox');
    expect(toasts.current?.message).toBe('Line removed');
    // The keyboard stays near: the ✕ now in that place has focus.
    expect(document.activeElement).toBe(
      page.getByRole('button', { name: 'Remove this line' }).nth(1).element()
    );
    toasts.act();
    await expect.element(line(2)).toHaveValue('Firefox 133 · Linux');
    await expect.element(line(3)).toHaveValue(report().errors[0]);
    expect(body()).toContain('Firefox 133 · Linux');
    expect(toasts.current?.message).toBe('Undone: Line removed');
  });

  it('with every line removed, says only what they typed is sent', async () => {
    open();
    await expect.element(line(1)).toBeVisible();
    for (let i = 0; i < 3; i++) {
      await page.getByRole('button', { name: 'Remove this line' }).first().click();
    }
    await expect
      .element(page.getByText('Every line is removed. Only what you typed will be sent.'))
      .toBeVisible();
    expect(body()).toBe('What were you doing?\n(left empty)\n');
  });

  it('a member’s report says errors are only in an admin’s', async () => {
    open([200, report({ errors: [], errors_included: false })]);
    await expect
      .element(page.getByText('Errors from the server’s log are only in an admin’s report.'))
      .toBeVisible();
    expect(page.getByRole('button', { name: 'Remove this line' }).elements()).toHaveLength(2);
  });

  it('an admin’s report with no errors says so', async () => {
    open([200, report({ errors: [] })]);
    await expect.element(line(3)).toHaveValue('No errors in the last 24 hours');
  });

  it('Copy puts the same text on the clipboard', async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    vi.spyOn(navigator, 'clipboard', 'get').mockReturnValue({ writeText } as unknown as Clipboard);
    open();
    await expect.element(line(1)).toBeVisible();
    await page.getByRole('button', { name: 'Copy' }).click();
    await vi.waitFor(() => expect(writeText).toHaveBeenCalledOnce());
    expect(writeText.mock.calls[0]![0]).toBe(body());
    expect(toasts.current?.message).toBe('Report copied');
  });

  it('says so when the clipboard refuses', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('no'));
    vi.spyOn(navigator, 'clipboard', 'get').mockReturnValue({ writeText } as unknown as Clipboard);
    open();
    await expect.element(line(1)).toBeVisible();
    await page.getByRole('button', { name: 'Copy' }).click();
    await vi.waitFor(() =>
      expect(toasts.current?.message).toBe('Couldn’t copy. Use Download instead.')
    );
    expect(toasts.current?.tone).toBe('problem');
  });

  it('Download makes a text file here with the same text', async () => {
    let blob: Blob | null = null;
    vi.spyOn(URL, 'createObjectURL').mockImplementation((b) => {
      blob = b as Blob;
      return 'blob:report';
    });
    const click = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(function (
      this: HTMLAnchorElement
    ) {
      expect(this.download).toMatch(/^mealwright-problem-report-\d{4}-\d{2}-\d{2}\.txt$/);
      expect(this.href).toBe('blob:report');
    });
    open();
    await expect.element(line(1)).toBeVisible();
    await page.getByRole('button', { name: 'Download' }).click();
    expect(click).toHaveBeenCalledOnce();
    expect(await blob!.text()).toBe(body());
    expect(requests).toHaveLength(1);
  });

  it('a very long report is cut for the link, and says Copy or Download has all of it', async () => {
    const errors = Array.from({ length: 20 }, (_, i) => `error ${i} ${'x'.repeat(290)}`);
    open([200, report({ errors })]);
    await expect.element(line(22)).toBeVisible();
    await page.getByRole('textbox', { name: 'What were you doing?' }).fill('y'.repeat(2500));
    await expect.element(page.getByText('Too long for one link', { exact: false })).toBeVisible();
    expect(github().element().getAttribute('href')!.length).toBeLessThanOrEqual(8000);
    expect(body()).toContain('[Cut short to fit in a link.]');
  });

  it('every ✕ is at least 44 px', async () => {
    open();
    await expect.element(line(1)).toBeVisible();
    for (const button of page.getByRole('button', { name: 'Remove this line' }).elements()) {
      const box = button.getBoundingClientRect();
      expect(box.width).toBeGreaterThanOrEqual(44);
      expect(box.height).toBeGreaterThanOrEqual(44);
    }
  });

  it('says when the report could not be made, and Try again asks again', async () => {
    open([500, { detail: 'Something went wrong.' }]);
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('Something went wrong. Try again');
    expect(page.getByRole('link', { name: 'Open on GitHub' }).elements()).toHaveLength(0);
    requests = fakeApi({ 'GET /problem-report': [200, report()] });
    await page.getByRole('button', { name: 'Try again' }).click();
    await expect.element(line(1)).toHaveValue('Mealwright 0.9.0');
    await expect.element(page.getByRole('alert')).not.toBeInTheDocument();
  });
});
