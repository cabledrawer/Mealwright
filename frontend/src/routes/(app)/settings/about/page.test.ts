// Settings → About, the update parts (X1; mockup Dark-About09-Phone): the version and its release
// day, the version-age note, "New version ready" and the admins' Updates card with Check now.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import type { CheckOutcome, Updates } from '#lib/client/updates.js';
import { network } from '#lib/network.svelte.js';
import { newVersion } from '#lib/newVersion.svelte.js';
import { updates } from '#lib/updates.svelte.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import About from './+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const PAGE = 'https://github.com/placeholder_until_1_0/mealwright/releases';
const daysAgo = (days: number) => {
  const d = new Date();
  d.setDate(d.getDate() - days);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
};

function info(over: Partial<Updates> = {}): Updates {
  return {
    version: '0.9.0',
    released: '2026-11-12',
    releases_page: PAGE,
    can_check: true,
    daily: false,
    last: null,
    ...over
  };
}

const last = (outcome: CheckOutcome, latest: string | null = null) => ({
  outcome,
  latest,
  checked_at: new Date().toISOString()
});

let component: ReturnType<typeof mount> | null = null;
let requests: FakeRequest[] = [];

function open(routes: Parameters<typeof fakeApi>[0] = {}) {
  requests = fakeApi({
    'GET /updates': [200, info({ released: daysAgo(3) })],
    ...routes
  });
  component = mount(About, { target: document.body });
  flushSync();
}

const sent = (method: string, path: string) =>
  requests.filter((r) => r.method === method && r.path === path);

beforeEach(async () => {
  await page.viewport(390, 844);
  network.reset();
  updates.forget();
  newVersion.reset();
});

afterEach(() => {
  if (component) unmount(component);
  component = null;
  document.body.innerHTML = '';
  vi.unstubAllGlobals();
  network.reset();
  updates.forget();
  newVersion.reset();
});

describe('Settings → About (X1)', () => {
  it('shows the version and its release day, with no note while it is new', async () => {
    open({ 'GET /updates': [200, info({ released: '2026-11-12' })] });
    await expect.element(page.getByRole('heading', { name: 'About', level: 1 })).toBeVisible();
    await expect.element(page.getByText('Mealwright 0.9.0')).toBeVisible();
    await expect.element(page.getByText('Released 12 Nov 2026')).toBeVisible();
    // Loading About asks the server only; no check is made.
    expect(sent('POST', '/updates/check')).toEqual([]);
  });

  it('says how old the version is after three months, with the releases link', async () => {
    open({ 'GET /updates': [200, info({ released: daysAgo(130) })] });
    await expect.element(page.getByText(/^This version is 4 months old\./)).toBeVisible();
    const link = page.getByRole('link', { name: 'github.com/…/mealwright/releases' });
    await expect.element(link).toHaveAttribute('href', PAGE);
    await expect.element(link).toHaveAttribute('rel', 'noopener noreferrer');
  });

  it('no age note under three months', async () => {
    open({ 'GET /updates': [200, info({ released: daysAgo(80) })] });
    await expect.element(page.getByText('Mealwright 0.9.0')).toBeVisible();
    expect(page.getByText(/months old/).elements()).toEqual([]);
  });

  it('a member sees the version but no Updates card', async () => {
    open({ 'GET /updates': [200, info({ can_check: false, daily: null })] });
    await expect.element(page.getByText('Mealwright 0.9.0')).toBeVisible();
    expect(page.getByRole('heading', { name: 'Updates (admins)' }).elements()).toEqual([]);
    expect(page.getByRole('button', { name: 'Check now' }).elements()).toEqual([]);
  });

  it('an admin checks now and hears a newer version is out', async () => {
    open({
      'POST /updates/check': [200, info({ daily: true, last: last('newer', 'v0.9.1') })]
    });
    await expect
      .element(
        page.getByText('One request to GitHub’s public release list; nothing about you is sent')
      )
      .toBeVisible();
    await page.getByRole('button', { name: 'Check now' }).click();
    const row = page.getByRole('link', { name: /Mealwright 0\.9\.1 is out/ });
    await vi.waitFor(() =>
      expect(row.element().textContent).toMatch(/Checked just now · see what’s new/)
    );
    await vi.waitFor(() => expect(row.element().textContent).toMatch(/Update\s*$/));
    await expect.element(row).toHaveAttribute('href', PAGE);
    expect(sent('POST', '/updates/check')).toHaveLength(1);
    await vi.waitFor(() =>
      expect(page.getByRole('link', { name: /Daily check/ }).element().textContent).toMatch(
        /On\s*$/
      )
    );
  });

  it.each([
    ['up_to_date', 'You have the newest version'],
    ['failed', 'Couldn’t check for updates']
  ] as const)('Check now answering %s says so', async (outcome, words) => {
    open({ 'POST /updates/check': [200, info({ last: last(outcome) })] });
    await page.getByRole('button', { name: 'Check now' }).click();
    await expect.element(page.getByText(words, { exact: true })).toBeVisible();
  });

  it('with the daily switch off, Check now is still there with its note, and asks', async () => {
    // cabledrawer 12 Nov: the switch only controls the automatic check.
    open({ 'POST /updates/check': [200, info({ daily: false, last: last('up_to_date') })] });
    await expect.element(page.getByRole('button', { name: 'Check now' })).toBeEnabled();
    await expect
      .element(
        page.getByText('One request to GitHub’s public release list; nothing about you is sent')
      )
      .toBeVisible();
    await page.getByRole('button', { name: 'Check now' }).click();
    await expect.element(page.getByText('You have the newest version')).toBeVisible();
    expect(sent('POST', '/updates/check')).toHaveLength(1);
    expect(page.getByText(/Privacy first/).elements()).toEqual([]);
    await vi.waitFor(() =>
      expect(page.getByRole('link', { name: /Daily check/ }).element().textContent).toMatch(
        /Turn on in Privacy/
      )
    );
  });

  it('Check now is greyed out offline', async () => {
    open();
    const button = page.getByRole('button', { name: 'Check now' });
    await expect.element(button).toBeEnabled();
    network.offline = true;
    await expect.element(button).toBeDisabled();
  });

  it('says when Check now could not reach the server', async () => {
    open({ 'POST /updates/check': [500, { detail: 'Something went wrong.' }] });
    await page.getByRole('button', { name: 'Check now' }).click();
    await expect.element(page.getByRole('alert')).toHaveTextContent('Something went wrong.');
  });

  it('"New version ready" shows while a new version waits, and never reloads', async () => {
    newVersion.ready = true;
    open();
    await expect
      .element(page.getByRole('status').filter({ hasText: 'New version ready.' }))
      .toHaveTextContent(
        'New version ready. Close every Mealwright tab and window, then open it again to finish updating.'
      );
  });

  it('Help has "Report a problem" for everyone, a link to its own screen (X2)', async () => {
    open({ 'GET /updates': [200, info({ can_check: false })] });
    await expect.element(page.getByRole('heading', { name: 'Help', level: 2 })).toBeVisible();
    const row = page.getByRole('link', { name: 'Report a problem' });
    await expect.element(row).toHaveAttribute('href', '/settings/about/report');
    const box = row.element().getBoundingClientRect();
    expect(box.height).toBeGreaterThanOrEqual(44);
  });
  it('Licences and credits show the licence, the source link, the USDA credit and the fonts (U1)', async () => {
    open({ 'GET /updates': [200, info({ can_check: false })] });
    await expect
      .element(page.getByRole('heading', { name: 'Licences and credits', level: 2 }))
      .toBeVisible();
    await expect.element(page.getByText('AGPL-3.0', { exact: true })).toBeVisible();
    // The code is not on GitHub yet (the placeholder address): a note, not a dead link.
    expect(page.getByRole('link', { name: /Source code/ }).elements()).toHaveLength(0);
    await expect.element(page.getByText('Source code (AGPL-3.0)')).toBeVisible();
    await expect
      .element(page.getByText('The code is not on GitHub yet; the link comes with 1.0.0'))
      .toBeVisible();
    await expect.element(page.getByText('USDA FoodData Central (public domain)')).toBeVisible();
    await expect
      .element(page.getByText('Plus Jakarta Sans · Newsreader · SIL Open Font License 1.1'))
      .toBeVisible();
    // Showing them asks only for the About answer; nothing else, and no check.
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['GET /updates']);
  });
  it('the source row links to the source at this version once there is a real address (16g)', async () => {
    open({
      'GET /updates': [
        200,
        info({
          version: '0.9.5',
          can_check: false,
          releases_page: 'https://github.com/sam-kitchen/mealwright/releases'
        })
      ]
    });
    const source = page.getByRole('link', { name: /Source code \(AGPL-3\.0\)/ });
    await expect
      .element(source)
      .toHaveAttribute('href', 'https://github.com/sam-kitchen/mealwright/tree/v0.9.5');
    await expect.element(source).toHaveAttribute('rel', 'noopener noreferrer');
    await expect.element(page.getByText('The exact code of this version')).toBeVisible();
    expect(requests.map((r) => `${r.method} ${r.path}`)).toEqual(['GET /updates']);
  });
});
