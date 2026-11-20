// Settings › Backups & your data (0.9, D1): an admin changes the backups and backs up now; a member only
// looks; Delete everything waits for the words and the password, and says why it was refused.
// D3: an admin who signs in only with single sign-on confirms at the sign-in server instead.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page, userEvent } from 'vitest/browser';
import type { Backups } from '#lib/client/yourData.js';
import { network } from '#lib/network.svelte.js';
import { session } from '#lib/session.svelte.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import { ME } from '#lib/testing/fakeShopping.js';
import {
  confirmingFor,
  markConfirming,
  rememberAction,
  takeAction,
  wasConfirming
} from '#lib/client/sso.js';
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
const leave = vi.hoisted(() => ({
  goToSignInServer: vi.fn<(url: string, keepHistory?: boolean) => void>()
}));
vi.mock('#lib/client/sso.js', async (original) => ({
  ...(await original<typeof import('#lib/client/sso.js')>()),
  goToSignInServer: leave.goToSignInServer
}));

const BACKUPS: Backups = {
  every: 'daily',
  keep: 7,
  photos: true,
  photos_size: 410_000_000,
  database_size: 2_140_000,
  last: { at: new Date().toISOString(), size: 2_140_000, photos: false },
  problem: null,
  problem_at: null,
  count: 3,
  folder: '/data/backups'
};

const WHEN = whenWords(BACKUPS.last!.at);

const HOUSEHOLD = { history_months: 12, undo_days: 7 };

describe('Settings › Backups & your data', () => {
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
    leave.goToSignInServer.mockClear();
    sessionStorage.clear();
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
    session.me = null;
  });

  it('Export is a button that is off while offline, like the page’s other buttons (L11)', async () => {
    open(YourData);
    await expect.element(page.getByRole('link', { name: 'Export' })).toBeVisible();
    network.offline = true;
    await expect.element(page.getByRole('button', { name: 'Export' })).toBeDisabled();
    expect(page.getByRole('link', { name: 'Export' }).elements()).toEqual([]);
    network.offline = false;
    await expect.element(page.getByRole('link', { name: 'Export' })).toBeVisible();
  });

  it('shows the backups, the same-disk warning, export, history and Start again to an admin', async () => {
    open(YourData);
    await expect
      .element(page.getByRole('heading', { level: 1, name: 'Backups & your data' }))
      .toBeVisible();
    await expect.element(page.getByLabelText('How often')).toHaveValue('daily');
    await expect.element(page.getByLabelText('Keep')).toHaveValue('7');
    await expect
      .element(page.getByTestId('last-backup'))
      .toHaveTextContent(`${WHEN} · 2.1 MB · all fine`);
    await expect
      .element(page.getByText(/^Backups sit on the same disk as Mealwright/))
      .toBeVisible();
    await expect
      .element(page.getByText('The safety copy made before each upgrade follows the same choice.'))
      .toBeVisible();
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
    // The optional password for the export, with the mockup's words and the rule.
    const box = page.getByLabelText('Password (optional)');
    await expect.element(box).toHaveAttribute('type', 'password');
    await expect.element(box).toHaveAttribute('autocomplete', 'new-password');
    await expect.element(box).toHaveValue('');
    await expect
      .element(
        page.getByText(
          'With a password, the file is encrypted. Without it you can’t open the file, so keep it safe.'
        )
      )
      .toBeVisible();
    await expect
      .element(
        page.getByText(
          'Use 8 to 1,024 characters. Mealwright doesn’t keep the password and can’t recover it.'
        )
      )
      .toBeVisible();
    expect(box.element().getBoundingClientRect().height).toBeGreaterThanOrEqual(44);
    expect(getComputedStyle(box.element()).fontSize).toBe('16px');
  });

  describe('Export with a password', () => {
    const box = () => page.getByLabelText('Password (optional)');

    it('sends the password in the body only, then empties the box', async () => {
      const made = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:made');
      open(YourData, { 'POST /export': [200, { fine: true }] });
      await userEvent.fill(box(), 'lorna and noor');
      await userEvent.click(page.getByRole('button', { name: 'Export' }));
      await vi.waitFor(() => expect(requests.some((r) => r.method === 'POST')).toBe(true));
      const sent = requests.find((r) => r.method === 'POST')!;
      expect(sent.path).toBe('/export');
      expect(sent.url).toBe('/export'); // nothing in the address
      expect(sent.body).toEqual({ password: 'lorna and noor' });
      await vi.waitFor(() => expect(made).toHaveBeenCalled());
      await expect.element(box()).toHaveValue('');
      expect(document.querySelector('[role="alert"]')).toBeNull();
      made.mockRestore();
    });

    it('leaving the page stops the download and saves nothing', async () => {
      const made = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:made');
      let signal: AbortSignal | null | undefined;
      vi.stubGlobal('fetch', (input: string, init: RequestInit = {}) => {
        if (init.method === 'POST') {
          signal = init.signal;
          return new Promise((_resolve, reject) =>
            init.signal?.addEventListener('abort', () => reject(new DOMException('', 'AbortError')))
          );
        }
        const body = String(input).endsWith('/backups') ? BACKUPS : HOUSEHOLD;
        return Promise.resolve(new Response(JSON.stringify(body)));
      });
      component = mount(YourData, { target: document.body });
      flushSync();
      await userEvent.fill(box(), 'lorna and noor');
      await userEvent.click(page.getByRole('button', { name: 'Export' }));
      await vi.waitFor(() => expect(signal).toBeTruthy());
      expect(signal!.aborted).toBe(false);
      unmount(component);
      component = null;
      expect(signal!.aborted).toBe(true);
      expect(made).not.toHaveBeenCalled();
      made.mockRestore();
    });

    it('works in a browser without AbortSignal.any, and leaving still stops it', async () => {
      vi.stubGlobal('AbortSignal', {
        timeout: AbortSignal.timeout.bind(AbortSignal),
        abort: AbortSignal.abort.bind(AbortSignal)
      }); // no `any`
      expect((AbortSignal as unknown as { any?: unknown }).any).toBeUndefined();
      const made = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:made');
      open(YourData, { 'POST /export': [200, { fine: true }] });
      await userEvent.fill(box(), 'lorna and noor');
      await userEvent.click(page.getByRole('button', { name: 'Export' }));
      await vi.waitFor(() => expect(made).toHaveBeenCalled());
      await expect.element(box()).toHaveValue('');
      expect(document.querySelector('[role="alert"]')).toBeNull();
      made.mockRestore();
    });

    it('Enter in the box exports too', async () => {
      const made = vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:made');
      open(YourData, { 'POST /export': [200, {}] });
      await userEvent.fill(box(), 'lorna and noor');
      await userEvent.keyboard('{Enter}');
      await vi.waitFor(() => expect(requests.some((r) => r.method === 'POST')).toBe(true));
      made.mockRestore();
    });

    it('a password that is too short is refused on the page and nothing is sent', async () => {
      open(YourData);
      await userEvent.fill(box(), 'short');
      await userEvent.click(page.getByRole('button', { name: 'Export' }));
      await expect
        .element(page.getByRole('alert'))
        .toHaveTextContent('Use a password of 8 to 1,024 characters.');
      expect(requests.some((r) => r.method === 'POST')).toBe(false);
    });

    it('says why the server refused, and keeps what was typed so it can be tried again', async () => {
      open(YourData, {
        'POST /export': [403, { detail: 'Only the household’s admin can change this.' }]
      });
      await userEvent.fill(box(), 'lorna and noor');
      await userEvent.click(page.getByRole('button', { name: 'Export' }));
      await expect
        .element(page.getByRole('alert'))
        .toHaveTextContent('Only the household’s admin can change this.');
      await expect.element(box()).toHaveValue('lorna and noor');
    });

    it('with no password the Export link is still the plain file', async () => {
      open(YourData);
      await expect
        .element(page.getByRole('link', { name: 'Export' }))
        .toHaveAttribute('href', '/api/v1/export');
      await userEvent.fill(box(), 'lorna and noor');
      await expect.element(page.getByRole('link', { name: 'Export' })).not.toBeInTheDocument();
      await userEvent.clear(box());
      await expect.element(page.getByRole('link', { name: 'Export' })).toBeVisible();
    });

    it('is off while offline', async () => {
      open(YourData);
      await expect.element(box()).toBeEnabled();
      network.offline = true;
      await expect.element(box()).toBeDisabled();
      await expect.element(page.getByRole('button', { name: 'Export' })).toBeDisabled();
    });

    it('a member has no box at all', async () => {
      session.me = { ...ME, role: 'member' };
      open(YourData);
      // A member sees the value, not a choice: the label has no control to find by label.
      await expect.element(page.getByText('How often')).toBeVisible();
      await expect.element(page.getByText('Daily, 03:00')).toBeVisible();
      expect(document.querySelector('select')).toBeNull();
      expect(document.querySelector('input[type="password"]')).toBeNull();
      // Nothing points at a field that isn't there (a label with a dead `for`).
      for (const label of document.querySelectorAll('label[for]'))
        expect(document.getElementById(label.getAttribute('for')!)).not.toBeNull();
    });
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

  describe('Include photos', () => {
    const photos = () => page.getByRole('switch', { name: 'Include photos in backups' });

    it('is on, with the mockup’s words, and the last backup says when it holds photos', async () => {
      open(YourData, {
        'GET /backups': [
          200,
          { ...BACKUPS, last: { ...BACKUPS.last!, size: 412_140_000, photos: true } }
        ]
      });
      await expect.element(photos()).toBeChecked();
      await expect
        .element(
          page.getByText(
            'Recipe photos, 410.0\u00a0MB. Without them a backup is about 2.1\u00a0MB, but photos can’t be restored from it.'
          )
        )
        .toBeVisible();
      await expect
        .element(page.getByTestId('last-backup'))
        .toHaveTextContent(`${WHEN} · 412.1 MB with photos · all fine`); // the matcher reads a no-break space as a plain one
    });

    it('is saved as it is picked, and nothing else is sent', async () => {
      open(YourData, {
        'PATCH /backups': (request) => [200, { ...BACKUPS, ...(request.body as object) }]
      });
      await photos().click();
      await vi.waitFor(() =>
        expect(requests.filter((r) => r.method === 'PATCH').map((r) => r.body)).toEqual([
          { photos: false }
        ])
      );
      await expect.element(photos()).not.toBeChecked();
      await photos().click();
      await vi.waitFor(() =>
        expect(requests.filter((r) => r.method === 'PATCH').map((r) => r.body)).toEqual([
          { photos: false },
          { photos: true }
        ])
      );
      await expect.element(photos()).toBeChecked();
    });

    it('goes back, and says why, when the server refuses', async () => {
      open(YourData, {
        'PATCH /backups': [403, { detail: 'Only the household’s admin can change this.' }]
      });
      await photos().click();
      await expect
        .element(page.getByRole('alert'))
        .toHaveTextContent('Only the household’s admin can change this.');
      await expect.element(photos()).toBeChecked();
    });

    it('is off while offline, and a member sees it but cannot switch it', async () => {
      open(YourData);
      await expect.element(photos()).toBeEnabled(); // the page has loaded
      network.offline = true;
      await expect.element(photos()).toBeDisabled();
      network.offline = false;
      session.me = { ...ME, role: 'member' };
      document.body.innerHTML = '';
      open(YourData);
      await expect.element(photos()).toBeChecked();
      await expect.element(photos()).toBeDisabled();
    });

    it('says plainly when there are no photos yet', async () => {
      open(YourData, { 'GET /backups': [200, { ...BACKUPS, photos_size: 0 }] });
      await expect.element(page.getByText(/^No recipe photos yet\./)).toBeVisible();
    });
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

  it('Import from Mealie is a row under Import, for the admin (0.9.5)', async () => {
    session.me = { ...ME, role: 'admin' };
    open(YourData);
    await expect.element(page.getByRole('heading', { name: 'Import' })).toBeVisible();
    const row = page.getByRole('link', { name: /Import from Mealie/ });
    await expect.element(row).toBeVisible();
    await expect
      .element(page.getByText('Recipes and ingredients from a Mealie backup file'))
      .toBeVisible();
    expect(row.element().getAttribute('href')).toBe('/settings/your-data/mealie');
  });

  it('a member does not see Import from Mealie (0.9.5 round 1: the server refuses them)', async () => {
    session.me = { ...ME, role: 'member' };
    open(YourData);
    await expect.element(page.getByRole('link', { name: /How to restore/ })).toBeVisible();
    await expect.element(page.getByRole('heading', { name: 'Import' })).not.toBeInTheDocument();
    await expect
      .element(page.getByRole('link', { name: /Import from Mealie/ }))
      .not.toBeInTheDocument();
  });

  it('How to restore has the steps', async () => {
    open(Restore);
    await expect
      .element(page.getByRole('heading', { level: 1, name: 'How to restore' }))
      .toBeVisible();
    await expect
      .element(page.getByText(/sudo chown 10001:10001 data\/mealwright\.db/))
      .toBeVisible();
    await expect.element(page.getByText('The photos, when Include photos was on')).toBeVisible();
    await expect
      .element(
        page.getByText(/sudo cp -an data\/backups\/backup-<date>-<time>-photos\/\. data\/photos\//)
      )
      .toBeVisible();
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
      const sent = requests.find((r) => r.method === 'POST' && r.path === '/delete-everything');
      expect(sent?.body).toEqual({
        words: 'Delete everything',
        password: 'secret'
      });
      expect(session.me).toBeNull();
    });

    it('a wrong password says so, empties the box, and deletes nothing', async () => {
      open(DeleteEverything, {
        'POST /delete-everything': [
          403,
          { detail: 'That isn’t your current password.', code: 'wrong_password' }
        ]
      });
      await userEvent.fill(page.getByLabelText(/to confirm/), 'delete everything');
      await userEvent.fill(page.getByLabelText('Your password'), 'wrong');
      await button().click();
      await expect
        .element(page.getByRole('alert'))
        .toHaveTextContent('That isn’t your current password.');
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

    describe('Back up now first (R6, round 2)', () => {
      const FULL = { ...BACKUPS, keep: 3, count: 3 };
      const backupPosts = () =>
        requests.filter((r) => r.method === 'POST' && r.path === '/backups');

      it('never sends the password typed for Delete everything', async () => {
        open(DeleteEverything, {
          'GET /backups': [200, BACKUPS],
          'POST /backups': [200, BACKUPS]
        });
        await userEvent.fill(page.getByLabelText('Your password'), 'typed for the delete');
        await page.getByRole('button', { name: 'Back up now first' }).click();
        await vi.waitFor(() => expect(backupPosts().map((r) => r.body)).toEqual([undefined]));
      });

      it('at a full folder says it replaces the oldest and asks for its own password', async () => {
        open(DeleteEverything, {
          'GET /backups': [200, FULL],
          'POST /backups': [200, FULL],
          'GET /delete-everything': [200, { confirm_with: 'password', confirmed: false }]
        });
        await userEvent.fill(page.getByLabelText('Your password'), 'typed for the delete');
        await page.getByRole('button', { name: 'Back up now first' }).click();
        await expect.element(page.getByText('This replaces the oldest backup.')).toBeVisible();
        expect(backupPosts()).toEqual([]);
        await userEvent.fill(page.getByLabelText('Your password for backing up'), 'its own');
        await page.getByRole('button', { name: 'Back up now', exact: true }).click();
        await vi.waitFor(() =>
          expect(backupPosts().map((r) => r.body)).toEqual([{ password: 'its own' }])
        );
      });

      it('an admin with single sign-on confirms that action, and nothing is sent first', async () => {
        open(DeleteEverything, {
          'GET /backups': [200, FULL],
          'GET /delete-everything': [200, { confirm_with: 'single_sign_on', confirmed: false }],
          'POST /sso/confirm': [200, { url: 'https://id.example.org/authorize?x=1' }]
        });
        await page.getByRole('button', { name: 'Back up now first' }).click();
        await expect.element(page.getByText('This replaces the oldest backup.')).toBeVisible();
        await page.getByRole('button', { name: 'Confirm at your sign-in server' }).first().click();
        await vi.waitFor(() => expect(leave.goToSignInServer).toHaveBeenCalled());
        const sent = requests.find((r) => r.method === 'POST' && r.path === '/sso/confirm');
        expect(sent?.body).toEqual({ action: 'backup_now' });
        expect(backupPosts()).toEqual([]);
      });
    });

    const SSO_ONLY = { confirm_with: 'single_sign_on', confirmed: false };
    const CONFIRM_LINE =
      'You sign in with single sign-on, so confirm at your sign-in server instead of with a password. It asks you to sign in again.';

    it('asks the password when the server says so', async () => {
      open(DeleteEverything, {
        'GET /delete-everything': [200, { confirm_with: 'password', confirmed: false }]
      });
      await expect.element(page.getByLabelText('Your password')).toBeVisible();
      await expect.element(page.getByText(CONFIRM_LINE)).not.toBeInTheDocument();
    });

    it('an admin with single sign-on only confirms at the sign-in server, not with a password (D3)', async () => {
      open(DeleteEverything, {
        'GET /delete-everything': [200, SSO_ONLY],
        'POST /sso/confirm': [200, { url: 'https://id.example.org/authorize?x=1' }]
      });
      await expect.element(page.getByText(CONFIRM_LINE)).toBeVisible();
      await expect.element(page.getByLabelText('Your password')).not.toBeInTheDocument();
      await userEvent.fill(page.getByLabelText(/to confirm/), 'Delete everything');
      await expect.element(button()).toBeDisabled();
      await page.getByRole('button', { name: 'Confirm at your sign-in server' }).click();
      await vi.waitFor(() => expect(leave.goToSignInServer).toHaveBeenCalled());
      expect(leave.goToSignInServer.mock.calls[0]).toEqual([
        'https://id.example.org/authorize?x=1',
        true
      ]);
      expect(wasConfirming()).toBe(true);
      expect(requests.some((r) => r.path === '/delete-everything' && r.method === 'POST')).toBe(
        false
      );
    });

    it('once confirmed there, the words alone delete (D3)', async () => {
      open(DeleteEverything, {
        'GET /delete-everything': [200, { ...SSO_ONLY, confirmed: true }],
        'POST /delete-everything': [204, null],
        'DELETE /session': [401, {}]
      });
      await expect
        .element(page.getByRole('status'))
        .toHaveTextContent('Confirmed at your sign-in server. Delete within 10 minutes.');
      await expect.element(button()).toBeDisabled();
      await userEvent.fill(page.getByLabelText(/to confirm/), 'Delete everything');
      await button().click();
      await vi.waitFor(() => expect(navigation.goto).toHaveBeenCalled());
      const sent = requests.find((r) => r.method === 'POST' && r.path === '/delete-everything');
      expect(sent?.body).toEqual({ words: 'Delete everything' });
    });

    it('when the confirming has run out, it asks for it again (D3)', async () => {
      const detail = 'Confirm with your sign-in server first, then delete within 10 minutes.';
      open(DeleteEverything, {
        'GET /delete-everything': [200, { ...SSO_ONLY, confirmed: true }],
        'POST /delete-everything': [403, { detail, code: 'confirm_first' }]
      });
      await userEvent.fill(page.getByLabelText(/to confirm/), 'Delete everything');
      await button().click();
      await expect.element(page.getByRole('alert')).toHaveTextContent(detail);
      await expect
        .element(page.getByRole('button', { name: 'Confirm at your sign-in server' }))
        .toBeVisible();
      expect(navigation.goto).not.toHaveBeenCalled();
    });

    it('a member is told only the admin can, with no form', async () => {
      session.me = { ...ME, role: 'member' };
      open(DeleteEverything);
      await expect.element(page.getByText('Only the household’s admin can do this.')).toBeVisible();
      await expect.element(button()).not.toBeInTheDocument();
    });
  });

  describe('Keep fewer than there are (R6)', () => {
    const patches = () => requests.filter((r) => r.method === 'PATCH').map((r) => r.body);
    const go = () => page.getByRole('button', { name: 'Keep fewer backups' });
    const ROUTES = {
      'PATCH /backups': (request: FakeRequest) => [
        200,
        { ...BACKUPS, ...(request.body as object), count: 2 }
      ]
    } as Parameters<typeof fakeApi>[0];

    it('lowering Keep so that backups go sends nothing until the password is typed', async () => {
      open(YourData, {
        ...ROUTES,
        'GET /delete-everything': [200, { confirm_with: 'password', confirmed: false }]
      });
      await page.getByLabelText('Keep').selectOptions('Last 2');
      await expect.element(page.getByText('This deletes the oldest backup.')).toBeVisible();
      await expect.element(go()).toBeDisabled();
      expect(patches()).toEqual([]);
      await userEvent.fill(page.getByLabelText('Your password'), 'correct horse battery');
      await go().click();
      await vi.waitFor(() =>
        expect(patches()).toEqual([{ keep: 2, password: 'correct horse battery' }])
      );
      await expect.element(page.getByLabelText('Keep')).toHaveValue('2');
      await expect.element(go()).not.toBeInTheDocument();
    });

    it('says how many go', async () => {
      open(YourData, {
        'GET /delete-everything': [200, { confirm_with: 'password', confirmed: false }]
      });
      await page.getByLabelText('Keep').selectOptions('Last 1');
      await expect.element(page.getByText('This deletes the 2 oldest backups.')).toBeVisible();
    });

    it('a Keep that deletes nothing is sent at once, with no password', async () => {
      open(YourData, ROUTES);
      await page.getByLabelText('Keep').selectOptions('Last 3');
      await vi.waitFor(() => expect(patches()).toEqual([{ keep: 3 }]));
      expect(requests.some((r) => r.path === '/delete-everything')).toBe(false);
    });

    it('Cancel puts Keep back and sends nothing', async () => {
      open(YourData, {
        'GET /delete-everything': [200, { confirm_with: 'password', confirmed: false }]
      });
      await page.getByLabelText('Keep').selectOptions('Last 2');
      await page.getByRole('button', { name: 'Cancel' }).click();
      await expect.element(page.getByLabelText('Keep')).toHaveValue('7');
      await expect.element(go()).not.toBeInTheDocument();
      expect(patches()).toEqual([]);
    });

    it('a wrong password is said, and nothing changes', async () => {
      open(YourData, {
        'GET /delete-everything': [200, { confirm_with: 'password', confirmed: false }],
        'PATCH /backups': [
          403,
          { detail: 'That isn’t your current password.', code: 'wrong_password' }
        ]
      });
      await page.getByLabelText('Keep').selectOptions('Last 2');
      await userEvent.fill(page.getByLabelText('Your password'), 'nope');
      await go().click();
      await expect
        .element(page.getByRole('alert'))
        .toHaveTextContent('That isn’t your current password.');
      await expect.element(page.getByLabelText('Keep')).toHaveValue('2');
      await expect.element(page.getByLabelText('Your password')).toHaveValue('');
    });

    it('an admin with single sign-on only confirms at the sign-in server, no password box', async () => {
      open(YourData, {
        'GET /delete-everything': [200, { confirm_with: 'single_sign_on', confirmed: false }],
        'POST /sso/confirm': [200, { url: 'https://id.example.org/authorize?x=1' }]
      });
      await page.getByLabelText('Keep').selectOptions('Last 2');
      await expect.element(page.getByLabelText('Your password')).not.toBeInTheDocument();
      await expect.element(go()).toBeDisabled();
      await page.getByRole('button', { name: 'Confirm at your sign-in server' }).click();
      await vi.waitFor(() => expect(leave.goToSignInServer).toHaveBeenCalled());
      expect(wasConfirming()).toBe(true);
      expect(confirmingFor()).toBe('backups');
      expect(patches()).toEqual([]);
    });

    it('once confirmed there, Keep fewer sends no password', async () => {
      open(YourData, {
        ...ROUTES,
        'GET /delete-everything': [200, { confirm_with: 'single_sign_on', confirmed: true }]
      });
      await page.getByLabelText('Keep').selectOptions('Last 2');
      await expect
        .element(page.getByRole('status'))
        .toHaveTextContent(
          'Confirmed at your sign-in server. Keep fewer backups within 10 minutes.'
        );
      await go().click();
      await vi.waitFor(() => expect(patches()).toEqual([{ keep: 2 }]));
    });

    it('after the sign-in server, the box opens again with the chosen Keep, confirmed', async () => {
      markConfirming(true, Date.now(), 'backups');
      rememberAction({ keep: 2 });
      open(YourData, {
        ...ROUTES,
        'GET /delete-everything': [200, { confirm_with: 'single_sign_on', confirmed: true }]
      });
      await expect.element(page.getByText('This deletes the oldest backup.')).toBeVisible();
      await expect.element(page.getByLabelText('Keep')).toHaveValue('2');
      await go().click();
      await vi.waitFor(() => expect(patches()).toEqual([{ keep: 2 }]));
    });

    it('going to confirm remembers the chosen Keep for the way back', async () => {
      open(YourData, {
        'GET /delete-everything': [200, { confirm_with: 'single_sign_on', confirmed: false }],
        'POST /sso/confirm': [200, { url: 'https://id.example.org/authorize?x=1' }]
      });
      await page.getByLabelText('Keep').selectOptions('Last 2');
      await page.getByRole('button', { name: 'Confirm at your sign-in server' }).click();
      await vi.waitFor(() => expect(leave.goToSignInServer).toHaveBeenCalled());
      expect(takeAction()).toEqual({ keep: 2 });
      const began = requests.find((r) => r.method === 'POST' && r.path === '/sso/confirm');
      expect(began?.body).toEqual({ action: 'keep', keep: 2 });
    });

    it('a remembered action that has run out opens nothing', async () => {
      rememberAction({ keep: 2 }, Date.now() - 11 * 60_000);
      open(YourData);
      await expect.element(page.getByLabelText('Keep')).toHaveValue('7');
      await expect.element(go()).not.toBeInTheDocument();
    });
  });

  describe('Back up now at a full folder (R6)', () => {
    const FULL = { ...BACKUPS, keep: 3, count: 3 };
    const posts = () => requests.filter((r) => r.method === 'POST' && r.path === '/backups');

    it('below Keep it backs up at once', async () => {
      open(YourData, { 'POST /backups': [200, BACKUPS] });
      await page.getByRole('button', { name: 'Back up now' }).click();
      await vi.waitFor(() => expect(posts().map((r) => r.body)).toEqual([undefined]));
    });

    it('at Keep it says it replaces the oldest, and sends the password with the backup', async () => {
      open(YourData, {
        'GET /backups': [200, FULL],
        'POST /backups': [200, FULL],
        'GET /delete-everything': [200, { confirm_with: 'password', confirmed: false }]
      });
      await page.getByRole('button', { name: 'Back up now' }).click();
      await expect.element(page.getByText('This replaces the oldest backup.')).toBeVisible();
      expect(posts()).toEqual([]);
      await userEvent.fill(page.getByLabelText('Your password'), 'correct horse battery');
      await page.getByRole('button', { name: 'Back up now' }).last().click();
      await vi.waitFor(() =>
        expect(posts().map((r) => r.body)).toEqual([{ password: 'correct horse battery' }])
      );
      await expect.element(page.getByLabelText('Your password')).not.toBeInTheDocument();
    });

    it('an admin with single sign-on confirms first, and the box comes back for Back up now', async () => {
      open(YourData, {
        'GET /backups': [200, FULL],
        'GET /delete-everything': [200, { confirm_with: 'single_sign_on', confirmed: false }],
        'POST /sso/confirm': [200, { url: 'https://id.example.org/authorize?x=1' }]
      });
      await page.getByRole('button', { name: 'Back up now' }).click();
      await page.getByRole('button', { name: 'Confirm at your sign-in server' }).click();
      await vi.waitFor(() => expect(leave.goToSignInServer).toHaveBeenCalled());
      expect(takeAction()).toEqual({ backUpNow: true });
      expect(posts()).toEqual([]);
    });
  });
});
