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
      .element(page.getByText('One request to GitHub’s public release list; nothing about you is sent'))
      .toBeVisible();
    await page.getByRole('button', { name: 'Check now' }).click();
    const row = page.getByRole('link', { name: /Mealwright 0\.9\.1 is out/ });
    await expect.element(row).toHaveTextContent('Checked just now · see what’s new');
    await expect.element(row).toHaveTextContent('Update');
    await expect.element(row).toHaveAttribute('href', PAGE);
    expect(sent('POST', '/updates/check')).toHaveLength(1);
    await expect
      .element(page.getByRole('link', { name: /Daily check/ }))
      .toHaveTextContent('On');
  });

  it.each([
    ['up_to_date', 'You have the newest version'],
    ['failed', 'Couldn’t check for updates']
  ] as const)('Check now answering %s says so', async (outcome, words) => {
    open({ 'POST /updates/check': [200, info({ last: last(outcome) })] });
    await page.getByRole('button', { name: 'Check now' }).click();
    await expect.element(page.getByText(words, { exact: true })).toBeVisible();
  });

  it('with the switch off, Check now says to turn it on in Privacy', async () => {
    open({ 'POST /updates/check': [200, info({ last: last('off') })] });
    await page.getByRole('button', { name: 'Check now' }).click();
    const row = page.getByRole('link', { name: /Update checks are off/ });
    await expect
      .element(row)
      .toHaveTextContent('Turn on “Check for updates daily” in Privacy first.');
    await expect.element(row).toHaveAttribute('href', '/settings/privacy#outside-connections');
    await expect
      .element(page.getByRole('link', { name: /Daily check/ }))
      .toHaveTextContent('Turn on in Privacy');
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
});
