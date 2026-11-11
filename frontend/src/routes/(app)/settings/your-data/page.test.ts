// Settings → Your data (0.9, D1): an admin changes the backups and backs up now; a member only
// looks; Delete everything waits for the words and the password, and says why it was refused.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import type { Backups } from '#lib/client/yourData.js';
import { network } from '#lib/network.svelte.js';
import { session } from '#lib/session.svelte.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import { ME } from '#lib/testing/fakeShopping.js';
import { whenWords } from '#lib/yourDataWords.js';
import YourData from './+page.svelte';
import DeleteEverything from './delete/+page.svelte';
import Restore from './restore/+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const navigation = vi.hoisted(() => ({
  goto: vi.fn<(to: string, options?: object) => Promise<void>>(async () => {})
}));
vi.mock('$app/navigation', () => navigation);

const BACKUPS: Backups = {
  every: 'daily',
  keep: 7,
  last: { at: new Date().toISOString(), size: 2_140_000 },
  problem: null,
  problem_at: null,
  count: 3,
  folder: '/data/backups'
};

const WHEN = whenWords(BACKUPS.last!.at);

const HOUSEHOLD = { history_months: 12, undo_days: 7 };

describe('Settings → Your data', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[] = [];

  function open(
    screen: typeof YourData | typeof DeleteEverything | typeof Restore,
    routes: Parameters<typeof fakeApi>[0] = {}
  ) {
    requests = fakeApi({
      'GET /backups': [200, BACKUPS],
      'GET /household': [200, HOUSEHOLD],
      ...routes
    });
    component = mount(screen, { target: document.body });
    flushSync();
  }

  beforeEach(async () => {
    await page.viewport(390, 844);
    network.reset();
    session.me = { ...ME };
    navigation.goto.mockClear();
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
    session.me = null;
  });

  it('shows the backups, the same-disk warning, export, history and Start again to an admin', async () => {
    open(YourData);
    await expect.element(page.getByRole('heading', { level: 1, name: 'Your data' })).toBeVisible();
    await expect.element(page.getByLabelText('How often')).toHaveValue('daily');
    await expect.element(page.getByLabelText('Keep')).toHaveValue('7');
    await expect
      .element(page.getByTestId('last-backup'))
      .toHaveTextContent(`${WHEN} · 2.1 MB · all fine`);
    await expect
      .element(page.getByText(/^Backups sit on the same disk as Mealwright/))
      .toBeVisible();
    await expect.element(page.getByText(/Recipe photos are files beside it/)).toBeVisible();
    await expect
      .element(page.getByRole('link', { name: /How to restore/ }))
      .toHaveAttribute('href', '/settings/your-data/restore');
    await expect
      .element(page.getByRole('link', { name: 'Export' }))
      .toHaveAttribute('href', '/api/v1/export');
    await expect.element(page.getByText('12 months')).toBeVisible();
    await expect.element(page.getByText('Undo reaches back 7 days.')).toBeVisible();
    await expect
      .element(page.getByRole('link', { name: 'Delete everything…' }))
      .toHaveAttribute('href', '/settings/your-data/delete');
    // No password box for the export yet: it comes with the encryption.
    expect(document.querySelector('input[type="password"]')).toBeNull();
  });

  it('an admin changes how often and how many, and it is sent', async () => {
    open(YourData, {
      'PATCH /backups': (request) => [200, { ...BACKUPS, ...(request.body as object) }]
    });
    await page.getByLabelText('How often').selectOptions('Weekly, Mondays 03:00');
    await vi.waitFor(() =>
      expect(requests.filter((r) => r.method === 'PATCH').map((r) => r.body)).toEqual([
        { every: 'weekly' }
      ])
    );
    await page.getByLabelText('Keep').selectOptions('Last 14');
    await vi.waitFor(() =>
      expect(requests.filter((r) => r.method === 'PATCH').map((r) => r.body)).toEqual([
        { every: 'weekly' },
        { keep: 14 }
      ])
    );
    await expect.element(page.getByLabelText('Keep')).toHaveValue('14');
  });

  it('a change the server refuses goes back, and says why', async () => {
    open(YourData, {
      'PATCH /backups': [403, { detail: 'Only the household’s admin can change this.' }]
    });
    await page.getByLabelText('Keep').selectOptions('Last 3');
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('Only the household’s admin can change this.');
    await expect.element(page.getByLabelText('Keep')).toHaveValue('7');
  });

  it('Back up now shows the new backup, or why it failed', async () => {
    open(YourData, {
      'POST /backups': [
        200,
        { ...BACKUPS, problem: 'The disk is full.', problem_at: BACKUPS.last!.at }
      ]
    });
    await page.getByRole('button', { name: 'Back up now' }).click();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent(`The last backup failed (${WHEN}): The disk is full.`);
    await expect.element(page.getByTestId('last-backup')).not.toHaveTextContent('all fine');
  });

  it('a member sees everything and changes nothing', async () => {
    session.me = { ...ME, role: 'member' };
    open(YourData);
    await expect
      .element(page.getByText('Only the household’s admin can change these.'))
      .toBeVisible();
    await expect.element(page.getByText('Daily, 03:00')).toBeVisible();
    await expect.element(page.getByText('Last 7')).toBeVisible();
    expect(document.querySelector('select')).toBeNull();
    await expect.element(page.getByRole('button', { name: 'Back up now' })).not.toBeInTheDocument();
    await expect.element(page.getByRole('link', { name: 'Export' })).not.toBeInTheDocument();
    await expect
      .element(page.getByRole('link', { name: 'Delete everything…' }))
      .not.toBeInTheDocument();
    await expect.element(page.getByRole('link', { name: /How to restore/ })).toBeVisible();
  });

  it('How to restore has the steps', async () => {
    open(Restore);
    await expect
      .element(page.getByRole('heading', { level: 1, name: 'How to restore' }))
      .toBeVisible();
    await expect
      .element(page.getByText(/sudo chown 10001:10001 data\/mealwright\.db/))
      .toBeVisible();
    await expect.element(page.getByText('Not the photos.')).toBeVisible();
  });

  describe('Delete everything', () => {
    const button = () => page.getByRole('button', { name: 'Delete everything' });

    it('waits for the words and the password, then deletes and goes to setup', async () => {
      open(DeleteEverything, {
        'POST /delete-everything': [204, null],
        'DELETE /session': [401, {}]
      });
      await expect
        .element(page.getByRole('heading', { level: 1, name: 'Delete everything?' }))
        .toBeVisible();
      await expect.element(button()).toBeDisabled();
      await userEvent.fill(page.getByLabelText(/to confirm/), 'delete every');
      await userEvent.fill(page.getByLabelText('Your password'), 'secret');
      await expect.element(button()).toBeDisabled();
      await userEvent.fill(page.getByLabelText(/to confirm/), 'Delete everything');
      await expect.element(button()).toBeEnabled();
      await button().click();
      await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
      expect(navigation.goto.mock.calls[0]![0]).toBe('/setup');
      expect(requests.find((r) => r.path === '/delete-everything')?.body).toEqual({
        words: 'Delete everything',
        password: 'secret'
      });
      expect(session.me).toBeNull();
    });

    it('a wrong password says so, empties the box, and deletes nothing', async () => {
      open(DeleteEverything, {
        'POST /delete-everything': [403, { detail: 'That password isn’t right.' }]
      });
      await userEvent.fill(page.getByLabelText(/to confirm/), 'delete everything');
      await userEvent.fill(page.getByLabelText('Your password'), 'wrong');
      await button().click();
      await expect.element(page.getByRole('alert')).toHaveTextContent('That password isn’t right.');
      await expect.element(page.getByLabelText('Your password')).toHaveValue('');
      expect(navigation.goto).not.toHaveBeenCalled();
      expect(session.me).not.toBeNull();
    });

    it('Back up now first says when it is done', async () => {
      open(DeleteEverything, { 'POST /backups': [200, BACKUPS] });
      await page.getByRole('button', { name: 'Back up now first' }).click();
      await expect
        .element(page.getByRole('status'))
        .toHaveTextContent(`Backed up: ${WHEN} · 2.1 MB · all fine`);
    });

    it('a member is told only the admin can, with no form', async () => {
      session.me = { ...ME, role: 'member' };
      open(DeleteEverything);
      await expect.element(page.getByText('Only the household’s admin can do this.')).toBeVisible();
      await expect.element(button()).not.toBeInTheDocument();
    });
  });
});
