// Settings → Household → a person (0.9 A1): Save sends only what changed, Remove has Undo,
// giving a login makes a one-time sign-in link, and a member changes nothing.

import { flushSync, mount, unmount } from 'svelte';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { page } from 'vitest/browser';
import { goto } from '$app/navigation';
import { network } from '#lib/network.svelte.js';
import { household } from '#lib/people.svelte.js';
import { toasts } from '#lib/toast.svelte.js';
import { undoHistory } from '#lib/undo.svelte.js';
import { fakeApi, type FakeRequest } from '#lib/testing/fakeApi.js';
import { JOSS, HOUSEHOLD, TESS, people } from '#lib/testing/fakePeople.js';
import PersonPage from './[id]/+page.svelte';
import '#lib/styles/tokens.css';
import '#lib/styles/base.css';

const params = vi.hoisted(() => ({ id: '3' }));
vi.mock('$app/navigation', () => ({ goto: vi.fn(), beforeNavigate: vi.fn() }));
vi.mock('$app/state', () => ({ page: { params, url: new URL('http://x/') } }));

const CHANGE = (id: number, kind: string, summary: string) => ({
  id,
  kind,
  summary,
  at: '2026-11-11T10:00:00Z',
  who: { login_id: 1, name: 'Tess' },
  lines: [],
  can_undo: true,
  undo_until: null,
  undone: null
});

const pendingJoss = {
  ...JOSS,
  login: {
    username: 'joss',
    role: 'member' as const,
    shared: false,
    has_password: false,
    signs_in: false,
    link_pending: true,
    link_used_at: null,
    reset_pending: false
  }
};

// Someone single sign-on made: no password, no link, and they sign in.
const ssoJoss = {
  ...JOSS,
  created_by_name: '',
  login: {
    username: 'joss',
    role: 'member' as const,
    shared: false,
    has_password: false,
    signs_in: true,
    link_pending: false,
    link_used_at: null,
    reset_pending: false
  }
};

// Someone who chose their password with a sign-in link (Pe1, link hardening).
const passwordJoss = (extra: Partial<NonNullable<(typeof JOSS)['login']>> = {}) => ({
  ...JOSS,
  login: {
    username: 'joss',
    role: 'member' as const,
    shared: false,
    has_password: true,
    signs_in: true,
    link_pending: false,
    link_used_at: null,
    reset_pending: false,
    ...extra
  }
});

const clock = (at: Date) =>
  `${String(at.getHours()).padStart(2, '0')}:${String(at.getMinutes()).padStart(2, '0')}`;

describe('Settings → Household → a person', () => {
  let component: ReturnType<typeof mount> | null = null;
  let requests: FakeRequest[] = [];

  function open(routes: Parameters<typeof fakeApi>[0] = {}) {
    requests = fakeApi({
      'GET /people': [200, people()],
      'GET /household': [200, HOUSEHOLD],
      ...routes
    });
    component = mount(PersonPage, { target: document.body });
    flushSync();
  }

  const sent = (method: string, path: string) =>
    requests.filter((r) => r.method === method && r.path === path);

  beforeEach(async () => {
    await page.viewport(390, 844);
    params.id = '3';
    network.reset();
    household.forget();
    undoHistory.clear();
    toasts.dismiss();
    vi.mocked(goto).mockClear();
  });

  afterEach(() => {
    if (component) unmount(component);
    component = null;
    document.body.innerHTML = '';
    vi.unstubAllGlobals();
    network.reset();
    household.forget();
    undoHistory.clear();
    toasts.dismiss();
  });

  it('shows the person as drawn: name, colour, portion and "Profile only"', async () => {
    open();
    await expect.element(page.getByRole('heading', { name: 'Joss', level: 1 })).toBeVisible();
    await expect.element(page.getByText('Added 3 Nov by Tess')).toBeVisible();
    await expect.element(page.getByLabelText('Name')).toHaveValue('Joss');
    await expect
      .element(page.getByRole('button', { name: 'Amber' }))
      .toHaveAttribute('aria-pressed', 'true');
    await expect
      .element(page.getByRole('button', { name: '½ portion' }))
      .toHaveAttribute('aria-pressed', 'true');
    await expect
      .element(page.getByRole('button', { name: 'Profile only' }))
      .toHaveAttribute('aria-pressed', 'true');
    await expect
      .element(
        page.getByText(
          'Joss has no login, but still counts for portions and can be picked in “Who’s this?”.'
        )
      )
      .toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Remove Joss' })).toBeVisible();
    await expect
      .element(page.getByText('Recent changes shows “Joss (removed)”', { exact: false }))
      .toBeVisible();
  });

  it('Save sends only what changed, then goes back, with Undo', async () => {
    open({
      'PATCH /people/3': [
        200,
        people([TESS, { ...JOSS, colour: 'blue', portion_quarters: 6 }], {
          change: CHANGE(60, 'person_changed', 'Changed Joss: colour, portion')
        })
      ]
    });
    await page.getByRole('button', { name: 'Blue' }).click();
    await page.getByRole('button', { name: '1½ portions' }).click();
    await page.getByRole('button', { name: 'Save' }).click();
    await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/settings/household'));
    expect(sent('PATCH', '/people/3')[0]!.body).toEqual({ colour: 'blue', portion_quarters: 6 });
    expect(toasts.current?.message).toBe('Changed Joss: colour, portion');
  });

  it('Save with nothing changed just goes back', async () => {
    open();
    await page.getByRole('button', { name: 'Save' }).click();
    await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/settings/household'));
    expect(sent('PATCH', '/people/3')).toHaveLength(0);
  });

  it('Remove goes back with Undo', async () => {
    open({
      'DELETE /people/3': [
        200,
        people([TESS], {
          change: CHANGE(61, 'person_removed', 'Removed Joss from the household')
        })
      ],
      'POST /changes/61/undo': [
        200,
        { result: 'done', message: 'Undone', undone: { kind: 'person_removed' } }
      ]
    });
    await page.getByRole('button', { name: 'Remove Joss' }).click();
    await vi.waitFor(() => expect(goto).toHaveBeenCalledWith('/settings/household'));
    expect(toasts.current?.message).toBe('Removed Joss from the household');
    // The toast's Undo (and Ctrl+Z) undo the server's own change.
    await undoHistory.undoLast();
    await vi.waitFor(() => expect(sent('POST', '/changes/61/undo')).toHaveLength(1));
  });

  it('gives a login: a one-time sign-in link to copy', async () => {
    let given = false;
    open({
      'GET /people': () => [200, people([TESS, given ? pendingJoss : JOSS])],
      'POST /people/3/login': (r) => {
        given = true;
        expect(r.body).toEqual({ username: 'joss', role: 'member' });
        return [201, { path: '/join#secret-token', expires_at: '2026-11-12T10:00:00Z' }];
      }
    });
    await page.getByRole('button', { name: 'Give a login' }).click();
    await expect.element(page.getByLabelText('Username')).toHaveValue('joss');
    await page.getByRole('button', { name: 'Make the sign-in link' }).click();
    await expect
      .element(page.getByText('Sign-in link made. It works once, for 24 hours', { exact: false }))
      .toBeVisible();
    await expect.element(page.getByText(`${location.origin}/join#secret-token`)).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Copy the link' })).toBeVisible();
  });

  it('an unused link can be made again, or taken back with "Profile only"', async () => {
    let pending = true;
    open({
      'GET /people': () => [200, people([TESS, pending ? pendingJoss : JOSS])],
      'DELETE /people/3/login': () => {
        pending = false;
        return [204, null];
      }
    });
    await expect.element(page.getByText('Joss hasn’t used the sign-in link yet.')).toBeVisible();
    await expect.element(page.getByRole('button', { name: 'Make a new link' })).toBeVisible();
    await page.getByRole('button', { name: 'Profile only' }).click();
    await vi.waitFor(() => expect(sent('DELETE', '/people/3/login')).toHaveLength(1));
    await expect
      .element(page.getByRole('button', { name: 'Profile only' }))
      .toHaveAttribute('aria-pressed', 'true');
  });

  it('a single sign-on person signs in: no "link has run out", and the shared switch shows', async () => {
    open({ 'GET /people': [200, people([TESS, ssoJoss])] });
    await expect.element(page.getByText('Shared login', { exact: true })).toBeVisible();
    expect(page.getByText('sign-in link has run out', { exact: false }).query()).toBeNull();
    expect(page.getByRole('button', { name: 'Make a new link' }).query()).toBeNull();
  });

  it('says only when a person was added, when nobody is named as having added them', async () => {
    open({ 'GET /people': [200, people([TESS, ssoJoss])] });
    await expect.element(page.getByText('Added 3 Nov', { exact: true })).toBeVisible();
  });

  it('you cannot remove yourself or change your own role', async () => {
    params.id = '1';
    open();
    await expect.element(page.getByRole('heading', { name: 'Tess', level: 1 })).toBeVisible();
    expect(page.getByRole('button', { name: /^Remove/ }).query()).toBeNull();
    await expect.element(page.getByRole('button', { name: 'Admin' })).toBeDisabled();
  });

  it('says so when the person is not in the household any more', async () => {
    params.id = '99';
    open();
    await expect
      .element(page.getByRole('alert'))
      .toHaveTextContent('This person isn’t in the household any more. Household');
  });

  it('Reset password makes a one-time link to copy, and the data stays (Pe1)', async () => {
    let made = false;
    open({
      'GET /people': () => [200, people([TESS, passwordJoss({ reset_pending: made })])],
      'POST /people/3/reset-password': () => {
        made = true;
        return [201, { path: '/reset#reset-secret', expires_at: '2026-11-15T10:00:00Z' }];
      }
    });
    await expect.element(page.getByText('Password', { exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Reset password' }).click();
    await vi.waitFor(() => expect(sent('POST', '/people/3/reset-password')).toHaveLength(1));
    const panel = page.getByRole('status');
    await expect
      .element(panel)
      .toHaveTextContent(
        'Reset link made. It works once, for 24 hours. Send it to Joss: they pick a new password, and their recipes, plans and history stay as they are. ' +
          `${location.origin}/reset#reset-secret`
      );
    await expect.element(page.getByText(`${location.origin}/reset#reset-secret`)).toBeVisible();
    const writeText = vi.fn(() => Promise.resolve());
    vi.stubGlobal('navigator', { ...navigator, clipboard: { writeText } });
    await page.getByRole('button', { name: 'Copy the link' }).click();
    await vi.waitFor(() =>
      expect(writeText).toHaveBeenCalledWith(`${location.origin}/reset#reset-secret`)
    );
  });

  it('an unused reset link says so', async () => {
    open({ 'GET /people': [200, people([TESS, passwordJoss({ reset_pending: true })])] });
    await expect.element(page.getByText('Joss hasn’t used the reset link yet.')).toBeVisible();
  });

  it('your own unused reset link shows, admin or not, and you can cancel it', async () => {
    // 16b security pass S-M1 e (proposed, for cabledrawer): Joss is a member, on her own page.
    let pending = true;
    const me = () => ({ ...passwordJoss({ reset_pending: pending }), is_me: true });
    open({
      'GET /people': () => [
        200,
        people([{ ...TESS, is_me: false }, me()], { can_change: false })
      ],
      'DELETE /me/reset-link': () => {
        pending = false;
        return [204, null];
      }
    });
    const line = page.getByText('Someone made a reset link for your password', { exact: false });
    await expect.element(line).toBeVisible();
    expect(page.getByText('Joss hasn’t used the reset link yet.').query()).toBeNull();
    await page.getByRole('button', { name: 'Cancel the link' }).click();
    await vi.waitFor(() => expect(sent('DELETE', '/me/reset-link')).toHaveLength(1));
    await vi.waitFor(() => expect(line.query()).toBeNull());
    expect(toasts.current?.message).toBe('Reset link cancelled');
  });

  it('says when a link was used: "Link used today 21:40" (cabledrawer 13 Nov)', async () => {
    const now = new Date();
    open({
      'GET /people': [200, people([TESS, passwordJoss({ link_used_at: now.toISOString() })])]
    });
    await expect.element(page.getByText(`Link used today ${clock(now)}`)).toBeVisible();
  });

  it('an older use says the day: "Link used 12 Nov 21:40"', async () => {
    // Ten days ago at 21:40, in this device's time: older than a week, so the date shows.
    const at = new Date();
    at.setDate(at.getDate() - 10);
    at.setHours(21, 40, 0, 0);
    const month = at.toLocaleString('en-GB', { month: 'short' }).slice(0, 3);
    open({
      'GET /people': [200, people([TESS, passwordJoss({ link_used_at: at.toISOString() })])]
    });
    await expect.element(page.getByText(`Link used ${at.getDate()} ${month} 21:40`)).toBeVisible();
  });

  it('no Reset password on your own page; the only admin learns about reset-admin', async () => {
    params.id = '1';
    open();
    await expect.element(page.getByRole('heading', { name: 'Tess', level: 1 })).toBeVisible();
    expect(page.getByRole('button', { name: 'Reset password' }).query()).toBeNull();
    await expect
      .element(
        page.getByText('Forgotten your own password and you’re the only admin?', { exact: false })
      )
      .toBeVisible();
  });

  it('a member cannot reset anyone’s password', async () => {
    open({
      'GET /people': [200, people([TESS, passwordJoss()], { can_change: false })]
    });
    await expect.element(page.getByText('Password', { exact: true })).toBeVisible();
    expect(page.getByRole('button', { name: 'Reset password' }).query()).toBeNull();
  });

  it('a member sees the person and changes nothing', async () => {
    open({ 'GET /people': [200, people(undefined, { can_change: false })] });
    await expect.element(page.getByLabelText('Name')).toBeDisabled();
    await expect.element(page.getByRole('button', { name: 'Peach' })).toBeDisabled();
    expect(page.getByRole('button', { name: 'Save' }).query()).toBeNull();
    expect(page.getByRole('button', { name: 'Remove Joss' }).query()).toBeNull();
  });
});
